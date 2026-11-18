"""Strict offline tool replay. Never executes tools or contacts a model."""

from __future__ import annotations

import json
from typing import Any

from .faults import InjectedFault
from .privacy import scrub
from .schema import Run, canonical


class ReplayDivergence(AssertionError):
    pass


class RecordedError(RuntimeError):
    pass


class Replay:
    def __init__(self, run: Run):
        self.run = Run.from_dict(run.to_dict())
        self.position = 0

    def call(self, name: str, inputs: dict | None = None, *, kind: str = "tool") -> Any:
        if self.position >= len(self.run.events):
            raise ReplayDivergence(f"Unexpected call {name!r} after trace end")
        event = self.run.events[self.position]
        # Apply recorded request drift, then the same redaction used by the recorder.
        from .faults import ChaosPlan, request_fault
        plan = ChaosPlan.from_dict(self.run.metadata.get("chaos_plan", {}))
        fault = plan.select(self.position, name, kind)
        effective = request_fault(inputs or {}, fault)
        safe_inputs = scrub(effective)[0]
        # Raw recording is explicitly opt-in; permit exact raw inputs too.
        if event.name != name or event.kind != kind or (canonical(event.inputs) != canonical(safe_inputs) and canonical(event.inputs) != canonical(effective)):
            raise ReplayDivergence(f"Divergence at event {self.position}: expected {event.kind}:{event.name} with recorded arguments, received {kind}:{name}")
        self.position += 1
        if event.error:
            if event.error.get("fault"):
                raise InjectedFault(event.error["fault"], event.error["message"], event.error.get("status_code"))
            error_type = {"TimeoutError": TimeoutError, "ValueError": ValueError, "ConnectionError": ConnectionError}.get(event.error["type"], RecordedError)
            raise error_type(event.error["message"])
        return json.loads(canonical(event.output))

    async def acall(self, name: str, inputs: dict | None = None, *, kind: str = "tool") -> Any:
        return self.call(name, inputs, kind=kind)

    def assert_consumed(self):
        if self.position != len(self.run.events):
            raise ReplayDivergence(f"Replay consumed {self.position}/{len(self.run.events)} events")

    def verify(self) -> dict:
        """Validate every recorded interaction; this is tape validation, not agent re-execution."""
        for event in self.run.events:
            # The stored input already includes drift; bypass applying it twice.
            expected = self.run.metadata
            self.run.metadata = {}
            try:
                self.call(event.name, event.inputs, kind=event.kind)
            except (InjectedFault, RecordedError, TimeoutError, ValueError, ConnectionError):
                if event.error is None:
                    raise
            finally:
                self.run.metadata = expected
        self.assert_consumed()
        return {"run_id": self.run.run_id, "events": self.position, "verified": True, "mode": "offline tape validation"}
