"""Export completed traces through an application-configured OpenTelemetry tracer."""

from __future__ import annotations

from datetime import datetime

from .schema import Run, canonical


def export_run(run: Run, tracer=None) -> int:
    try:
        from opentelemetry import trace
        from opentelemetry.trace import Status, StatusCode
    except ImportError as exc:
        raise RuntimeError("Install pruefstand[otel] for OpenTelemetry export") from exc
    tracer = tracer or trace.get_tracer("pruefstand", "0.1.0")
    with tracer.start_as_current_span(f"invoke_agent {run.agent}", attributes={
        "gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": run.agent,
        "pruefstand.run.id": run.run_id, "pruefstand.task.id": run.task_id,
        "pruefstand.condition": run.condition,
    }):
        for event in run.events:
            attrs = {"gen_ai.operation.name": "chat" if event.kind == "model" else "execute_tool",
                     "pruefstand.sequence": event.sequence, "pruefstand.cost.eur": event.cost_eur,
                     "gen_ai.usage.input_tokens": event.input_tokens, "gen_ai.usage.output_tokens": event.output_tokens}
            if event.kind == "tool":
                attrs["gen_ai.tool.name"] = event.name
            attrs.update({k: v for k, v in event.attributes.items() if isinstance(v, (str, bool, int, float))})
            if event.fault:
                attrs["pruefstand.fault"] = event.fault
            start = int(datetime.fromisoformat(event.started_at).timestamp() * 1e9)
            span = tracer.start_span(event.name, attributes=attrs, start_time=start)
            if event.error:
                span.set_status(Status(StatusCode.ERROR, event.error["type"]))
            span.end(end_time=start + max(1, int(event.duration_ms * 1e6)))
    return len(run.events)


def otlp_json(run: Run) -> dict:
    """Portable diagnostic mapping; use export_run for actual OTLP transport."""
    return {"format": "pruefstand-otel-diagnostic-v1", "run_id": run.run_id,
            "spans": [{"name": e.name, "attributes": {"gen_ai.operation.name": "chat" if e.kind == "model" else "execute_tool",
                                                        "gen_ai.tool.name": e.name, "pruefstand.inputs": canonical(e.inputs)},
                       "duration_ms": e.duration_ms} for e in run.events]}
