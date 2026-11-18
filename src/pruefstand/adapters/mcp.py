"""MCP client call_tool interception, independent of a particular MCP SDK."""


class RecordedMCP:
    def __init__(self, session, recorder):
        self.session, self.recorder = session, recorder

    async def call_tool(self, name: str, arguments: dict | None = None):
        async def dispatch(**kwargs):
            result = await self.session.call_tool(name, arguments=kwargs)
            return result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        return await self.recorder.acall(name, dispatch, arguments or {}, attributes={"rpc.system": "jsonrpc", "protocol": "mcp"})
