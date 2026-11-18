from __future__ import annotations

from typing import Callable

from ..recorder import Recorder


def instrument_tools(recorder: Recorder, tools: dict[str, Callable]) -> dict[str, Callable]:
    """Wrap plain tool functions before registering them with any framework."""
    return {name: recorder.instrument(name)(function) for name, function in tools.items()}
