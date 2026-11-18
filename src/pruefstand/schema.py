"""Versioned JSON-serializable trace contract shared by every adapter."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def finite(value: float, name: str, low: float = 0, high: float = float("inf")) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite and in [{low}, {high}]")


@dataclass
class Event:
    sequence: int
    kind: str
    name: str
    inputs: Any
    output: Any = None
    error: dict[str, Any] | None = None
    fault: str | None = None
    started_at: str = field(default_factory=utcnow)
    duration_ms: float = 0
    cost_eur: float = 0
    input_tokens: int = 0
    output_tokens: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)
    privacy_findings: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 0 or self.kind not in {"tool", "model", "agent", "oversight"}:
            raise ValueError("Invalid event sequence or kind")
        for name in ("duration_ms", "cost_eur", "input_tokens", "output_tokens"):
            finite(getattr(self, name), name)
        if type(self.input_tokens) is not int or type(self.output_tokens) is not int:
            raise ValueError("Token counts must be integers")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Run:
    agent: str
    task_id: str
    condition: str = "baseline"
    seed: int = 42
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    schema_version: int = SCHEMA_VERSION
    started_at: str = field(default_factory=utcnow)
    finished_at: str | None = None
    success: bool | None = None
    confidence: float | None = None
    harmful_actions: int = 0
    loss_eur: float = 0
    output: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported trace schema {self.schema_version}")
        if not self.agent or not self.task_id or not self.run_id:
            raise ValueError("agent, task_id and run_id are required")
        if self.success is not None and type(self.success) is not bool:
            raise ValueError("success must be a boolean or null")
        if self.confidence is not None:
            finite(self.confidence, "confidence", 0, 1)
        finite(self.loss_eur, "loss_eur")
        finite(self.harmful_actions, "harmful_actions")
        if type(self.harmful_actions) is not int:
            raise ValueError("harmful_actions must be an integer")
        if [e.sequence for e in self.events] != list(range(len(self.events))):
            raise ValueError("Event sequence must be contiguous from zero")

    @property
    def cost_eur(self) -> float:
        return sum(e.cost_eur for e in self.events)

    @property
    def duration_ms(self) -> float:
        return sum(e.duration_ms for e in self.events)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> Run:
        value = dict(value)
        value["events"] = [Event(**e) for e in value.get("events", [])]
        return cls(**value)
