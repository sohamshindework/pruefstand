# Integration boundaries

Use the generic decorator for any framework that accepts Python functions. This registers recorded tools; it does not automatically intercept all framework-internal model calls. For model calls, use the model adapter or proxy. Versioned traces can combine instrumented boundaries within one recorder.

## Custom evaluation entrypoint

```python
from pruefstand.scenarios import Outcome

def evaluate(recorder, task):
    answer = recorder.call("lookup", lambda query: {"status": "ok"}, {"query": task["instruction"]})
    # Replace with an independent check of your actual task and side effects.
    return Outcome(success=answer["status"] == "ok", confidence=0.8,
                   harmful_actions=0, loss_eur=0, output=answer)
```

```bash
PYTHONPATH=. pruefstand run --agent examples.custom_agent:evaluate \
  --tasks src/pruefstand/data/enterprise-de.json --fault rate_limit --repeats 5
```

An error in the entrypoint becomes a failed run with a screened runner error. Do not execute untrusted plugins in the worker pool. A third-party agent is labelled non-synthetic by the runner, but that flag does not independently verify provenance or quality. Provide evaluation-specific `protocol_version` metadata and task-specific expectations.

## LangGraph

```python
from pruefstand.adapters.langgraph import recorded_tools
tools = recorded_tools(recorder, {"refund": refund_function})
# Register tools["refund"] with your ToolNode/StructuredTool, or call it in a graph node.
```

See [`examples/langgraph_refund.py`](../examples/langgraph_refund.py) for a real `StateGraph` with no API key. This adapter wraps callables before registration; it is not a LangGraph callback handler. [Official workflow documentation](https://docs.langchain.com/oss/python/langgraph/workflows-agents).

## OpenAI Agents SDK

```python
from pruefstand.adapters.openai_agents import function_tools
from agents import Agent
agent = Agent(name="Support", tools=function_tools(recorder, {"refund": refund_function}))
```

The wrapper preserves signatures/docstrings so the SDK can construct schemas. A real model run still needs its own provider configuration. Framework tool exception handling can change agent control flow; test it. [Official function-tool documentation](https://openai.github.io/openai-agents-python/tools/).

## MCP

```python
from pruefstand.adapters.mcp import RecordedMCP
recorded_session = RecordedMCP(connected_session, recorder)
result = await recorded_session.call_tool("lookup_order", {"order_id": "test-001"})
```

Pydantic MCP results are normalized to JSON. The return value is a normalized dictionary, not a native `CallToolResult`; callers expecting the native class must reconstruct it. This wraps a client session; the local HTTP proxy also accepts buffered JSON-RPC POST payloads but is not a complete MCP transport server (no SSE/streamable transport lifecycle).

## Sovereign / OpenAI-compatible model endpoints

```python
import os
from pruefstand.adapters import OpenAICompatible
model = OpenAICompatible(
    recorder, base_url=os.environ.get("MODEL_BASE_URL", "http://localhost:11434/v1"),
    api_key=os.environ.get("MODEL_API_KEY"), eu_hosts=["models.example.eu"],
)
response = model.complete(model="your-installed-model", messages=[{"role": "user", "content": "Guten Tag!"}],
                          max_tokens=128, max_cost_eur=0.01)
```

The same boundary supports OpenAI-compatible Mistral/vLLM/Ollama services; provider differences may need additional parameters. HTTPX has automatic connection retries disabled by default, preserving visible application retry behavior. Streaming is rejected. Populate actual provider prices separately: reserved euro costs are upper-bound inputs and no conversion or pricing service is implied. EU host allowlists are operator declarations, not proof of residency.
