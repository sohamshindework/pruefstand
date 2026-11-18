import asyncio
import json

import pytest

from pruefstand import BudgetExceeded, ChaosPlan, Fault, InjectedFault, Recorder, Replay, ReplayDivergence, Store
from pruefstand.schema import Run


def test_record_redact_store_and_replay_ten_times(tmp_path):
    store = Store(tmp_path / "trace.db")
    with Recorder("agent", "task", store=store) as recorder:
        value = recorder.call("lookup", lambda email: {"email": email, "status": "ok"}, {"email": "person@example.test"})
        assert value["email"] == "person@example.test"  # Tool receives the original, not redacted, input.
        recorder.finish(success=True, confidence=.9)
    run = store.get(recorder.run.run_id)
    assert "person@example.test" not in json.dumps(run.to_dict())
    assert run.events[0].privacy_findings
    for _ in range(10):
        replay = Replay(run)
        assert replay.call("lookup", {"email": "person@example.test"})["status"] == "ok"
        replay.assert_consumed()


def test_replay_rejects_changed_arguments_order_and_unconsumed_trace():
    recorder = Recorder("agent", "task")
    recorder.call("first", lambda value: value, {"value": 7})
    recorder.call("second", lambda: "done")
    recorder.finish(success=True)
    replay = Replay(recorder.run)
    with pytest.raises(ReplayDivergence):
        replay.call("first", {"value": 8})
    assert replay.position == 0
    with pytest.raises(ReplayDivergence):
        replay.call("second")
    replay.call("first", {"value": 7})
    with pytest.raises(ReplayDivergence):
        replay.assert_consumed()


def test_timeout_after_commits_and_replays_without_committing():
    ledger = []
    recorder = Recorder("agent", "task", chaos=ChaosPlan([Fault("timeout_after")]))
    with pytest.raises(InjectedFault):
        recorder.call("refund", lambda: ledger.append(49.9))
    assert ledger == [49.9]
    recorder.finish(success=False)
    with pytest.raises(InjectedFault):
        Replay(recorder.run).call("refund")
    assert ledger == [49.9]
    assert Replay(recorder.run).verify()["verified"]


def test_exception_is_recorded_and_context_is_not_swallowed(tmp_path):
    store = Store(tmp_path / "trace.db")
    with pytest.raises(ValueError):
        with Recorder("agent", "task", store=store) as recorder:
            recorder.call("bad", lambda: (_ for _ in ()).throw(ValueError("invalid person@example.test")))
    run = store.get(recorder.run.run_id)
    assert run.success is False
    assert "person@example.test" not in json.dumps(run.to_dict())
    with pytest.raises(ValueError):
        Replay(run).call("bad")


def test_cost_and_call_budgets_stop_before_dispatch():
    calls = []
    recorder = Recorder("agent", "task", budget_eur=.05, max_calls=2)
    recorder.call("paid", lambda: calls.append(1), max_cost_eur=.03)
    with pytest.raises(BudgetExceeded):
        recorder.call("too_expensive", lambda: calls.append(2), max_cost_eur=.03)
    assert calls == [1]
    recorder.call("free", lambda: None)
    with pytest.raises(BudgetExceeded):
        recorder.call("third", lambda: calls.append(3))
    assert recorder.run.cost_eur == .03


def test_async_recording_cancellation_and_decorator():
    async def scenario():
        recorder = Recorder("agent", "async")

        @recorder.instrument()
        async def add(value: int, other: int = 1):
            await asyncio.sleep(0)
            return value + other

        assert await add(2, other=3) == 5
        async def slow():
            await asyncio.sleep(1)
        with pytest.raises(TimeoutError):
            await recorder.acall("slow", slow, timeout=.001)
        recorder.finish(success=False)
        assert recorder.run.events[1].error["type"] == "TimeoutError"
        assert Replay(recorder.run).verify()["verified"]
    asyncio.run(scenario())


def test_drift_replays_original_request():
    recorder = Recorder("agent", "task", chaos=ChaosPlan([Fault("model_swap")]))
    result = recorder.call("model", lambda model: model, {"model": "original"}, kind="model")
    assert result == "sovereign-test-model"
    recorder.finish(success=True)
    assert Replay(recorder.run).call("model", {"model": "original"}, kind="model") == result


def test_unlabelled_run_stays_unlabelled():
    with Recorder("agent", "task") as recorder:
        recorder.call("ok", lambda: True)
    assert recorder.run.success is None


def test_decorator_preserves_positional_only_and_variadic_calling_conventions():
    recorder = Recorder("agent", "signature")
    @recorder.instrument()
    def tool(first, /, *rest, flag=False, **extra):
        return {"total": first + sum(rest), "flag": flag, "extra": extra}
    assert tool(1, 2, 3, flag=True, label="test") == {"total": 6, "flag": True, "extra": {"label": "test"}}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_invalid_cost_rejected(value):
    with pytest.raises(ValueError):
        Recorder("agent", "task", budget_eur=value)


def test_schema_rejects_invalid_values_and_incomplete_event_sequences():
    with pytest.raises(ValueError):
        Run.from_dict({"agent": "a", "task_id": "b", "schema_version": 999})
    with pytest.raises(ValueError):
        Run("a", "b", confidence=1.1)
    with pytest.raises(ValueError):
        Run("a", "b", success="true")


def test_jsonl_roundtrip_and_import_is_atomic(tmp_path):
    store = Store(tmp_path / "one.db")
    with Recorder("a", "task", store=store) as recorder:
        recorder.finish(success=True)
    path = tmp_path / "runs.jsonl"
    assert store.export_jsonl(path) == 1
    second = Store(tmp_path / "two.db")
    assert second.import_jsonl(path) == 1
    assert second.get(recorder.run.run_id).to_dict() == recorder.run.to_dict()
    path.write_text(path.read_text() + '{"agent":"broken"}\n')
    third = Store(tmp_path / "three.db")
    with pytest.raises(TypeError):
        third.import_jsonl(path)
    assert third.list() == []


def test_parquet_export(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    store = Store(tmp_path / "runs.db")
    with Recorder("a", "task", store=store) as recorder:
        recorder.call("tool", lambda: {"amount": 2})
        recorder.finish(success=True)
    path = tmp_path / "runs.parquet"
    assert store.export_parquet(path) == 1
    with duckdb.connect() as db:
        assert db.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()[0] == 1
