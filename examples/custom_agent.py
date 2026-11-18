from pruefstand.scenarios import Outcome


def evaluate(recorder, task):
    """Minimal trusted plugin. Replace the stub and independent check for a real task."""
    result = recorder.call("lookup", lambda query: {"status": "ok", "query": query}, {"query": task["instruction"]})
    return Outcome(success=isinstance(result, dict) and result.get("status") == "ok", confidence=.8, output=result,
                   metadata={"synthetic": True, "protocol_version": "custom-example-v1"})
