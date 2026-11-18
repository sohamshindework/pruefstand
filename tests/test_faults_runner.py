import pytest

from pruefstand import ChaosPlan, Fault, Recorder, Replay
from pruefstand.faults import CATALOG
from pruefstand.runner import SuiteConfig, run_demo, run_suite
from pruefstand.scenarios import load_tasks


@pytest.mark.parametrize("fault", CATALOG)
def test_each_fault_is_applied_recorded_and_replayable(fault):
    recorder = Recorder("a", "task", chaos=ChaosPlan([Fault(fault)]))
    try:
        recorder.call("tool", lambda **kwargs: {"status": "ok", "amount": 5, "customer": "Prüfkunde"}, {"model": "test"})
    except Exception:
        pass
    recorder.finish(success=False)
    assert recorder.run.events[0].fault == fault
    assert Replay(recorder.run).verify()["verified"]


def test_probability_schedule_is_stable_and_targeted():
    plan = ChaosPlan([Fault("rate_limit", at_call=None, probability=.5, target="refund", kind="tool")], seed=7)
    draws = [plan.select(i, "refund", "tool") is not None for i in range(100)]
    assert any(draws) and not all(draws)
    assert draws == [ChaosPlan.from_dict(plan.to_dict()).select(i, "refund", "tool") is not None for i in range(100)]
    assert plan.select(0, "other", "tool") is None
    assert plan.select(0, "refund", "model") is None


def test_demo_reproduces_duplicate_refund_and_injection_then_fixes_both():
    runs = run_demo(repeats=2)
    for run in runs:
        if run.agent == "idempotent-agent" or run.condition == "baseline":
            assert run.success is True
            assert run.harmful_actions == 0
        else:
            assert run.success is False
            assert run.harmful_actions > 0
            assert run.loss_eur > 0
    duplicate = next(r for r in runs if r.agent == "vulnerable-retry" and r.condition == "timeout_after")
    assert len(duplicate.output["committed_actions"]) == 2
    assert duplicate.loss_eur == 49.9


def test_seeded_suite_verdicts_equal_across_worker_counts():
    kwargs = {"tasks": load_tasks()[:2], "faults": ["timeout_after", "prompt_injection", "malformed_json"]}
    serial = run_suite(**kwargs, config=SuiteConfig(repeats=2, workers=1))
    parallel = run_suite(**kwargs, config=SuiteConfig(repeats=2, workers=4))
    def observed(runs):
        return [(r.agent, r.task_id, r.condition, r.seed, r.success, r.harmful_actions, r.loss_eur) for r in runs]
    assert observed(serial) == observed(parallel)


@pytest.mark.parametrize("config", [{"repeats": 0}, {"workers": 33}, {"budget_eur": -1}])
def test_runner_rejects_invalid_configuration(config):
    with pytest.raises(ValueError):
        SuiteConfig(**config)


def test_invalid_faults_and_untrusted_entrypoint_name_rejected():
    with pytest.raises(ValueError):
        Fault("nonexistent")
    with pytest.raises(ValueError):
        Fault("slow_response", parameters={"delay_ms": float("inf")})
    with pytest.raises(ValueError):
        run_suite(agents=["unknown"], tasks=load_tasks()[:1], faults=[])
