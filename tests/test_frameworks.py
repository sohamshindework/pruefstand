"""Real optional SDK contract tests; no model endpoints or API keys."""
import asyncio

import pytest

from pruefstand import Recorder


def test_real_langgraph_node_execution():
    pytest.importorskip("langgraph")
    from langgraph.graph import END, START, StateGraph
    from typing import TypedDict
    from pruefstand.adapters.langgraph import recorded_tools
    class State(TypedDict):
        result: int
    recorder = Recorder("langgraph", "tool-contract")
    tools = recorded_tools(recorder, {"double": lambda value: value * 2})
    graph = StateGraph(State)
    graph.add_node("tool", lambda state: {"result": tools["double"](state["result"])})
    graph.add_edge(START, "tool")
    graph.add_edge("tool", END)
    assert graph.compile().invoke({"result": 4})["result"] == 8
    assert recorder.run.events[0].output == 8


def test_real_openai_agents_function_tool_invocation():
    pytest.importorskip("agents")
    from agents.tool_context import ToolContext
    from pruefstand.adapters.openai_agents import function_tools
    recorder = Recorder("openai-agents", "tool-contract")
    def double(value: int) -> int:
        """Double a test number."""
        return value * 2
    tool = function_tools(recorder, {"test_double": double})[0]
    assert tool.name == "test_double"
    assert tool.params_json_schema["properties"]["value"]["type"] == "integer"
    context = ToolContext(context=None, tool_name="test_double", tool_call_id="test-call", tool_arguments='{"value":4}')
    result = asyncio.run(tool.on_invoke_tool(context, '{"value":4}'))
    assert result in (8, "8")
    assert recorder.run.events[0].output == 8


def test_real_mcp_result_normalization():
    pytest.importorskip("mcp")
    from mcp.types import CallToolResult, TextContent
    from pruefstand.adapters.mcp import RecordedMCP
    class Session:
        async def call_tool(self, name, arguments):
            return CallToolResult(content=[TextContent(type="text", text="Prüfung erfolgreich")])
    recorder = Recorder("mcp", "tool-contract")
    result = asyncio.run(RecordedMCP(Session(), recorder).call_tool("test", {}))
    assert result["content"][0]["text"] == "Prüfung erfolgreich"
    assert recorder.run.events[0].output["content"][0]["type"] == "text"
