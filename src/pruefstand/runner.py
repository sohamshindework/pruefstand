"""Bounded parallel experiment runner with explicit per-run budget partitions."""

from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from .faults import CATALOG, ChaosPlan, Fault
from .privacy import scrub
from .recorder import Recorder
from .schema import Run, finite, fingerprint
from .scenarios import Outcome, load_tasks, resilient, vulnerable
from .store import Store

BUILTINS = {"vulnerable-retry": vulnerable, "idempotent-agent": resilient}
DRIFT = {"model_swap", "temperature_drift", "prompt_paraphrase"}


@dataclass
class SuiteConfig:
    repeats: int = 5
    seed: int = 42
    workers: int = 4
    budget_eur: float = 5
    max_calls: int = 30

    def __post_init__(self):
        if not 1 <= self.repeats <= 1000 or not 1 <= self.workers <= 32 or self.max_calls < 1:
            raise ValueError("repeats: 1..1000, workers: 1..32, max_calls: >=1")
        finite(self.budget_eur, "budget_eur")


def resolve_agent(name: str) -> Callable:
    if name in BUILTINS:
        return BUILTINS[name]
    if ":" not in name:
        raise ValueError("Agent must be a builtin name or trusted module:callable")
    module, function = name.split(":", 1)
    result = getattr(importlib.import_module(module), function)
    if not callable(result):
        raise ValueError("Agent entrypoint must be callable")
    return result


def run_suite(*, agents: list[str] | None = None, tasks: list[dict] | None = None,
              faults: list[str] | None = None, config: SuiteConfig | None = None,
              store: Store | None = None) -> list[Run]:
    agents = list(BUILTINS) if agents is None else agents
    tasks = load_tasks() if tasks is None else tasks
    faults = list(CATALOG) if faults is None else faults
    config = config or SuiteConfig()
    if not agents or not tasks or len(set(agents)) != len(agents) or len({t["id"] for t in tasks}) != len(tasks):
        raise ValueError("Use nonempty unique agents and task IDs")
    if len(set(faults)) != len(faults) or any(f not in CATALOG for f in faults):
        raise ValueError("Faults must be unique known catalog entries")
    functions = {name: resolve_agent(name) for name in agents}
    jobs = [(agent, task, condition, repeat) for agent in agents for task in tasks
            for condition in ["baseline", *faults] for repeat in range(config.repeats)]
    if len(jobs) > 50_000:
        raise ValueError("Suite exceeds the 50,000-run admission limit")
    budget_per_run = config.budget_eur / len(jobs)

    def execute(job):
        agent, task, condition, repeat = job
        seed = config.seed + repeat
        plan = ChaosPlan(seed=seed)
        if condition != "baseline":
            drift = condition in DRIFT
            plan.faults = [Fault(condition, at_call=1 if drift else 2, kind="model" if drift else "tool")]
        recorder = Recorder(agent, task["id"], chaos=plan, condition=condition, max_calls=config.max_calls,
                            budget_eur=budget_per_run,
                            metadata={"synthetic": agent in BUILTINS, "protocol_version": "enterprise-de-v1",
                                      "repeat": repeat, "task": task, "budget_partition_eur": budget_per_run})
        # Rerunning the same experiment replaces its rows instead of silently doubling sample size.
        recorder.run.run_id = fingerprint({"agent": agent, "task": task, "condition": condition,
                                          "repeat": repeat, "seed": seed, "protocol": "enterprise-de-v1"})[:32]
        try:
            outcome = functions[agent](recorder, dict(task))
            if isinstance(outcome, dict):
                outcome = Outcome(**outcome)
            if not isinstance(outcome, Outcome):
                raise TypeError("Agent entrypoint must return Outcome or its dictionary representation")
            recorder.run.metadata.update(scrub(outcome.metadata)[0])
            run = recorder.finish(success=outcome.success, confidence=outcome.confidence,
                                  harmful_actions=outcome.harmful_actions, loss_eur=outcome.loss_eur, output=outcome.output)
        except Exception as exc:
            recorder.run.metadata["runner_error"] = scrub({"type": type(exc).__name__, "message": str(exc)})[0]
            run = recorder.finish(success=False, output={"status": "agent-error"})
        if store:
            store.save(run)
        return run

    with ThreadPoolExecutor(max_workers=config.workers, thread_name_prefix="pruefstand") as executor:
        return list(executor.map(execute, jobs))


def run_demo(store: Store | None = None, repeats: int = 5, seed: int = 42) -> list[Run]:
    return run_suite(tasks=load_tasks()[:1], faults=["timeout_after", "prompt_injection"],
                     config=SuiteConfig(repeats=repeats, seed=seed), store=store)
