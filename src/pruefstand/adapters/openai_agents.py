"""OpenAI Agents SDK tool registration, with a lazy optional framework import."""


def function_tools(recorder, tools):
    try:
        from agents import function_tool
    except ImportError as exc:
        raise RuntimeError("Install openai-agents to register these tools") from exc
    return [function_tool(recorder.instrument(name)(function), name_override=name) for name, function in tools.items()]
