"""Explicit integration boundaries; optional dependencies import lazily."""

from .generic import instrument_tools
from .openai_compatible import OpenAICompatible

__all__ = ["OpenAICompatible", "instrument_tools"]
