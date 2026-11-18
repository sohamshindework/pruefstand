import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from pruefstand import ChaosPlan, Fault, Recorder, Store
from pruefstand.adapters import OpenAICompatible, instrument_tools
from pruefstand.adapters.mcp import RecordedMCP
from pruefstand.cli import main
from pruefstand.proxy import make_proxy


def test_openai_compatible_adapter_sends_drift_records_usage_and_keeps_key_out_of_trace():
    httpx = pytest.importorskip("httpx")
    observed = []
    def handler(request):
        observed.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(200, json={"model": "actual-model-v2", "choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 12, "completion_tokens": 3}})
    recorder = Recorder("agent", "task", chaos=ChaosPlan([Fault("model_swap", parameters={"model": "eu-model"})]))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenAICompatible(recorder, base_url="https://eu.example.test/v1", api_key="secret", eu_hosts=["eu.example.test"], client=client)
        result = adapter.complete(model="original-model", messages=[{"role": "user", "content": "hello"}], max_cost_eur=.01)
    assert observed[0]["model"] == "eu-model"
    assert result["model"] == "actual-model-v2"
    event = recorder.run.events[0]
    assert (event.input_tokens, event.output_tokens) == (12, 3)
    assert event.cost_eur == .01
    assert "secret" not in json.dumps(recorder.run.to_dict())
    assert event.attributes["endpoint"]["declared_eu"]
    with pytest.raises(ValueError):
        OpenAICompatible(recorder, base_url="https://user:password@example.test")


def test_mcp_and_generic_tools_work_without_framework_dependency():
    recorder = Recorder("a", "task")
    wrapped = instrument_tools(recorder, {"add": lambda a, b: a + b})
    assert wrapped["add"](2, b=3) == 5
    class Session:
        async def call_tool(self, name, arguments):
            return {"name": name, "result": arguments["a"] * 2}
    result = asyncio.run(RecordedMCP(Session(), recorder).call_tool("double", {"a": 3}))
    assert result["result"] == 6
    assert recorder.run.events[-1].attributes["protocol"] == "mcp"


def test_otel_exports_error_and_usage_to_configured_tracer():
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from pruefstand.telemetry import export_run
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    recorder = Recorder("a", "task")
    recorder.call("tool", lambda: 1)
    run = recorder.finish(success=True)
    assert export_run(run, provider.get_tracer("test")) == 1
    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    assert spans[0].parent.span_id == spans[1].context.span_id
    assert spans[0].attributes["gen_ai.tool.name"] == "tool"
    provider.shutdown()


@pytest.fixture
def upstream():
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append({"path": self.path, "body": body, "headers": dict(self.headers)})
            payload = json.dumps({"status": "ok", "amount": 49.9, "email": "customer@example.test"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, requests
    server.shutdown()
    server.server_close()
    thread.join()


def post(url, data=None, headers=None):
    request = Request(url, data=json.dumps(data or {"amount": 49.9}).encode(), headers={"Content-Type": "application/json", **(headers or {})})
    return urlopen(request, timeout=5)


@pytest.mark.parametrize("fault,expected_status,executions", [(None, 200, 1), ("rate_limit", 429, 0), ("timeout_after", 504, 1)])
def test_proxy_faults_and_transport_only_labels(upstream, tmp_path, fault, expected_status, executions):
    service, requests = upstream
    store = Store(tmp_path / "proxy.db")
    plan = ChaosPlan([Fault(fault)]) if fault else ChaosPlan()
    proxy = make_proxy(f"http://127.0.0.1:{service.server_port}", store=store, plan=plan, port=0)
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    try:
        try:
            with post(f"http://127.0.0.1:{proxy.server_port}/tool", headers={"Authorization": "Bearer caller-secret", "Cookie": "private"}) as response:
                assert response.status == expected_status
        except HTTPError as exc:
            assert exc.code == expected_status
        # Shutdown waits for the request thread's finally block to persist the trace.
    finally:
        proxy.shutdown()
        proxy.server_close()
        thread.join()
    assert len(requests) == executions
    if requests:
        assert "Authorization" not in requests[0]["headers"]
        assert "Cookie" not in requests[0]["headers"]
    runs = store.list()
    assert len(runs) == 1 and runs[0].success is None
    assert "customer@example.test" not in json.dumps(runs[0].to_dict())


def test_proxy_rejects_public_binding(tmp_path):
    with pytest.raises(ValueError):
        make_proxy("https://example.test", store=Store(tmp_path / "p.db"), host="0.0.0.0")


def test_cli_end_to_end_bundle_export_replay_gate_and_import(tmp_path, capsys):
    out = tmp_path / "experiment"
    assert main(["run", "--out", str(out), "--repeats", "2", "--fault", "timeout_after", "--bootstrap", "100"]) == 0
    db = out / "traces.db"
    assert (out / "report.html").exists()
    assert (out / "evidence.zip").exists()
    run_id = Store(db).list()[0].run_id
    assert main(["replay", "--db", str(db), run_id, "--times", "10"]) == 0
    assert main(["gate", "--baseline", str(out / "profiles/vulnerable-retry.json"), "--candidate", str(out / "profiles/idempotent-agent.json")]) == 0
    assert main(["gate", "--baseline", str(out / "profiles/idempotent-agent.json"), "--candidate", str(out / "profiles/vulnerable-retry.json")]) == 1
    target = tmp_path / "new.db"
    assert main(["import", str(out / "traces.jsonl"), "--db", str(target)]) == 0
    assert len(Store(target).list()) == 64
    assert main(["site-data", "--db", str(db), "--out", str(tmp_path / "data.json"), "--bootstrap", "100"]) == 0
    assert len(json.loads((tmp_path / "data.json").read_text())["traces"]) == 32
    assert main(["show", "--db", str(db), "nonexistent"]) == 2
    capsys.readouterr()
