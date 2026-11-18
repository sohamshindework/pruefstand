"""Explicit OpenAI-compatible boundary for OpenAI, Mistral, Ollama, and vLLM."""

from __future__ import annotations

from urllib.parse import urlparse

from ..privacy import endpoint_assessment
from ..recorder import Recorder


class OpenAICompatible:
    def __init__(self, recorder: Recorder, *, base_url: str = "http://localhost:11434/v1",
                 api_key: str | None = None, eu_hosts: list[str] | None = None,
                 timeout: float = 30, client=None):
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base_url must be an HTTP(S) origin/path without credentials, query or fragment")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.recorder = recorder
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.assessment = endpoint_assessment(base_url, eu_hosts or [])
        self._client = client

    def complete(self, *, model: str, messages: list[dict], temperature: float = 0,
                 max_tokens: int = 256, max_cost_eur: float = 0, **extra) -> dict:
        if extra.get("stream"):
            raise ValueError("This adapter records complete JSON responses; streaming is unsupported")
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")

        def dispatch(**body):
            try:
                import httpx
            except ImportError as exc:
                raise RuntimeError("Install pruefstand[http] to call model endpoints") from exc
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            if self._client is not None:
                response = self._client.post(self.base_url + "/chat/completions", json=body, headers=headers, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
                    response = client.post(self.base_url + "/chat/completions", json=body, headers=headers)
            response.raise_for_status()
            return response.json()

        result = self.recorder.call("chat.completions", dispatch,
                                    {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens, **extra},
                                    kind="model", max_cost_eur=max_cost_eur,
                                    attributes={"gen_ai.request.model": model, "gen_ai.operation.name": "chat", "endpoint": self.assessment})
        event = self.recorder.run.events[-1]
        if isinstance(result, dict):
            usage = result.get("usage", {})
            for key, destination in (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens")):
                count = usage.get(key, 0)
                if type(count) is int and count >= 0:
                    setattr(event, destination, count)
            if isinstance(result.get("model"), str):
                event.attributes["gen_ai.response.model"] = result["model"]
        return result
