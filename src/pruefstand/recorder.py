"""Synchronous and asynchronous interception with redaction and budget admission."""

from __future__ import annotations

import asyncio
import functools
import inspect
import threading
import time
from typing import Any, Callable

from .faults import ChaosPlan, after, before, request_fault
from .privacy import scrub
from .schema import Event, Run, finite, utcnow
from .store import Store


class BudgetExceeded(RuntimeError):
    pass


class Recorder:
    def __init__(self, agent: str, task_id: str, *, store: Store | None = None,
                 chaos: ChaosPlan | None = None, condition: str | None = None,
                 seed: int = 42, max_calls: int = 100, budget_eur: float = 1,
                 redact: bool = True, metadata: dict | None = None):
        finite(budget_eur, "budget_eur")
        if max_calls < 1:
            raise ValueError("max_calls must be positive")
        self.chaos = chaos or ChaosPlan(seed=seed)
        self.run = Run(agent=agent, task_id=task_id, condition=condition or ("chaos" if self.chaos.faults else "baseline"), seed=self.chaos.seed)
        self.redact = redact
        self.run.metadata = scrub(metadata or {}, redact=redact)[0]
        self.run.metadata["chaos_plan"] = scrub(self.chaos.to_dict(), redact=redact)[0]
        self.store = store
        self.max_calls = max_calls
        self.budget_eur = budget_eur
        self._reserved = 0.0
        self._active = 0
        self._lock = threading.Lock()
        self._finished = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is not None and not self._finished:
            self.run.success = False
            self.run.metadata["unhandled_error"] = scrub(str(exc), redact=self.redact)[0]
        self.flush()
        return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return self.__exit__(exc_type, exc, tb)

    def _begin(self, name: str, inputs: dict, kind: str, max_cost_eur: float, attributes: dict | None):
        finite(max_cost_eur, "max_cost_eur")
        with self._lock:
            if self._finished:
                raise RuntimeError("A finished run cannot record more calls")
            if len(self.run.events) >= self.max_calls or self.run.cost_eur + self._reserved + max_cost_eur > self.budget_eur + 1e-12:
                raise BudgetExceeded("Call or cost budget would be exceeded before dispatch")
            sequence = len(self.run.events)
            fault = self.chaos.select(sequence, name, kind)
            effective = request_fault(inputs, fault)
            safe_inputs, findings = scrub(effective, redact=self.redact)
            safe_attrs, attr_findings = scrub(attributes or {}, redact=self.redact)
            if kind == "model" and isinstance(safe_inputs, dict) and isinstance(safe_inputs.get("model"), str):
                safe_attrs["gen_ai.request.model"] = safe_inputs["model"]
            event = Event(sequence=sequence, kind=kind, name=name, inputs=safe_inputs,
                          fault=fault.name if fault else None, attributes=safe_attrs,
                          privacy_findings=findings + attr_findings)
            self.run.events.append(event)
            self._reserved += max_cost_eur
            self._active += 1
        return event, effective, fault

    def _end(self, event: Event, start: float, max_cost_eur: float, output: Any = None, error: BaseException | None = None):
        event.duration_ms = (time.perf_counter() - start) * 1000
        if error is not None:
            safe_error, findings = scrub({"type": type(error).__name__, "message": str(error),
                                          "status_code": getattr(error, "status_code", None),
                                          "fault": getattr(error, "fault", None)}, redact=self.redact)
            event.error = safe_error
        else:
            event.output, findings = scrub(output, redact=self.redact)
        event.privacy_findings.extend(findings)
        # Reservation is conservatively charged even for errors: an API may have billed before timeout.
        with self._lock:
            event.cost_eur = max_cost_eur
            self._reserved -= max_cost_eur
            self._active -= 1

    def call(self, name: str, function: Callable[..., Any], inputs: dict | None = None, *,
             kind: str = "tool", max_cost_eur: float = 0, attributes: dict | None = None) -> Any:
        event, effective, fault = self._begin(name, inputs or {}, kind, max_cost_eur, attributes)
        start = time.perf_counter()
        try:
            before(fault)
            if fault and fault.name == "slow_response":
                time.sleep(fault.parameters.get("delay_ms", 5) / 1000)
            output = function(**effective)
            if inspect.isawaitable(output):
                if inspect.iscoroutine(output):
                    output.close()
                raise TypeError("Use acall for asynchronous tools")
            output = after(output, fault)
        except BaseException as exc:
            self._end(event, start, max_cost_eur, error=exc)
            raise
        self._end(event, start, max_cost_eur, output)
        return output

    async def acall(self, name: str, function: Callable[..., Any], inputs: dict | None = None, *,
                    kind: str = "tool", max_cost_eur: float = 0, attributes: dict | None = None,
                    timeout: float | None = None) -> Any:
        event, effective, fault = self._begin(name, inputs or {}, kind, max_cost_eur, attributes)
        start = time.perf_counter()
        try:
            before(fault)
            if fault and fault.name == "slow_response":
                await asyncio.sleep(fault.parameters.get("delay_ms", 5) / 1000)
            output = function(**effective)
            if inspect.isawaitable(output):
                output = await asyncio.wait_for(output, timeout) if timeout is not None else await output
            output = after(output, fault)
        except BaseException as exc:
            self._end(event, start, max_cost_eur, error=exc)
            raise
        self._end(event, start, max_cost_eur, output)
        return output

    def instrument(self, name: str | None = None, *, kind: str = "tool", max_cost_eur: float = 0):
        def decorate(function):
            signature = inspect.signature(function)
            def invoke(**values):
                arguments = inspect.BoundArguments(signature, values)
                return function(*arguments.args, **arguments.kwargs)
            if inspect.iscoroutinefunction(function):
                @functools.wraps(function)
                async def wrapped(*args, **kwargs):
                    bound = signature.bind(*args, **kwargs)
                    return await self.acall(name or function.__name__, invoke, dict(bound.arguments), kind=kind, max_cost_eur=max_cost_eur)
            else:
                @functools.wraps(function)
                def wrapped(*args, **kwargs):
                    bound = signature.bind(*args, **kwargs)
                    return self.call(name or function.__name__, invoke, dict(bound.arguments), kind=kind, max_cost_eur=max_cost_eur)
            return wrapped
        return decorate

    def finish(self, *, success: bool, confidence: float | None = None, harmful_actions: int = 0,
               loss_eur: float = 0, output: Any = None) -> Run:
        if self._active:
            raise RuntimeError("Await all in-flight calls before finishing the run")
        if type(success) is not bool:
            raise ValueError("success must be boolean")
        if confidence is not None:
            finite(confidence, "confidence", 0, 1)
        finite(loss_eur, "loss_eur")
        finite(harmful_actions, "harmful_actions")
        if type(harmful_actions) is not int:
            raise ValueError("harmful_actions must be an integer")
        self.run.success, self.run.confidence = success, confidence
        self.run.harmful_actions, self.run.loss_eur = harmful_actions, loss_eur
        self.run.output = scrub(output, redact=self.redact)[0]
        self._finished = True
        return self.flush()

    def flush(self) -> Run:
        self.run.finished_at = utcnow()
        if self.store is not None:
            self.store.save(self.run)
        return self.run
