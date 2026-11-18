"""LangGraph tool-node boundary. Graph ownership remains with the application."""

from .generic import instrument_tools


def recorded_tools(recorder, tools):
    """Return callable wrappers for use in ToolNode/StructuredTool registration."""
    return instrument_tools(recorder, tools)
