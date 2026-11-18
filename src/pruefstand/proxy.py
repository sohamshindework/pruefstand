"""Local JSON HTTP/JSON-RPC fault proxy. Fixed upstream; bounded buffered bodies.

This is a development proxy, not an internet-facing gateway or streaming interceptor.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request

from .faults import ChaosPlan, InjectedFault
from .recorder import Recorder
from .store import Store


class UpstreamError(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(f"Upstream HTTP {status_code}")


def make_proxy(upstream: str, *, store: Store, plan: ChaosPlan | None = None,
               host: str = "127.0.0.1", port: int = 8787, api_key: str | None = None,
               timeout: float = 30, max_body_bytes: int = 1_048_576) -> ThreadingHTTPServer:
    parsed = urlparse(upstream)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Use a fixed HTTP(S) upstream without credentials, query or fragment")
    if timeout <= 0 or max_body_bytes < 1:
        raise ValueError("timeout and max_body_bytes must be positive")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("The development proxy only binds to loopback")

    class Handler(BaseHTTPRequestHandler):
        server_version = "Pruefstand/0.1"

        def log_message(self, *_):
            pass  # Never print raw paths, queries, authorization headers or payloads.

        def send_json(self, code, value):
            body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self.send_json(200, {"status": "ok", "upstream_host": parsed.hostname})
            else:
                self.send_json(405, {"error": "Only JSON POST forwarding is supported"})

        def do_POST(self):
            if self.headers.get("Transfer-Encoding"):
                self.close_connection = True
                self.send_json(400, {"error": "Chunked request bodies are unsupported"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= max_body_bytes:
                    self.close_connection = True
                    self.send_json(413, {"error": "Request size outside configured bounds"})
                    return
                self.connection.settimeout(timeout)
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or payload.get("stream"):
                    self.send_json(400, {"error": "Expected a non-streaming JSON object"})
                    return
            except (ValueError, OSError):
                self.close_connection = True
                self.send_json(400, {"error": "Invalid JSON body or Content-Length"})
                return
            # Never use urljoin: a user-supplied //host must not replace the upstream.
            route = self.path
            if not route.startswith("/") or route.startswith("//") or ".." in route.split("?")[0].split("/"):
                self.send_json(400, {"error": "Invalid upstream route"})
                return
            path_only = route.split("?", 1)[0]
            recorder = Recorder("http-proxy", path_only, chaos=plan,
                                metadata={"transport_only": True, "upstream_host": parsed.hostname})

            def dispatch(**body):
                headers = {"Content-Type": "application/json"}
                # Only explicit upstream credentials are forwarded. Never reuse browser/caller cookies.
                if api_key:
                    headers["Authorization"] = "Bearer " + api_key
                request = Request(upstream.rstrip("/") + route, data=json.dumps(body).encode(), headers=headers, method="POST")
                try:
                    # urllib follows redirects; use a handler that refuses them to avoid moving credentials.
                    from urllib.request import HTTPRedirectHandler, build_opener
                    class NoRedirect(HTTPRedirectHandler):
                        def redirect_request(self, *_args, **_kwargs):
                            return None
                    with build_opener(NoRedirect).open(request, timeout=timeout) as response:
                        data = response.read(max_body_bytes + 1)
                        if len(data) > max_body_bytes:
                            raise ValueError("Upstream response exceeds configured size limit")
                        return json.loads(data)
                except HTTPError as exc:
                    raise UpstreamError(exc.code) from exc

            try:
                result = recorder.call("http.request", dispatch, payload,
                                       kind="model" if "completions" in path_only else "tool")
                self.send_json(200, result)
            except Exception as exc:
                status = getattr(exc, "status_code", None) or (504 if isinstance(exc, (TimeoutError, InjectedFault)) else 502)
                self.send_json(status, {"error": {"type": type(exc).__name__, "fault": getattr(exc, "fault", None)}})
            finally:
                # HTTP success is not a task-success label. Such traces cannot be scored until labelled.
                recorder.flush()
                store.save(recorder.run)

    return ThreadingHTTPServer((host, port), Handler)
