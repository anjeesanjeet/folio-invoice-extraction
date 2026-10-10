"""Provider-agnostic vision extraction (Claude or OpenAI) with structured output via a forced tool call."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from app.config import Settings


class ProviderConfigError(RuntimeError):
    """Raised when a provider is selected but not configured (e.g. missing API key)."""


@dataclass
class StructuredResult:
    data: dict
    input_tokens: int
    output_tokens: int
    cost_usd: float


class BaseProvider:
    name = "base"

    def __init__(self, model: str, price_in: float, price_out: float, temperature: float | None):
        self.model, self.price_in, self.price_out, self.temperature = model, price_in, price_out, temperature

    def cost(self, i: int, o: int) -> float:
        return (i * self.price_in + o * self.price_out) / 1_000_000

    def _create(self, fn, kwargs: dict):
        """Calls the SDK; if it rejects `temperature`, retries without it for the rest of the session."""
        try:
            return fn(**kwargs)
        except Exception as exc:
            if "temperature" in kwargs and "temperature" in str(exc).lower():
                kwargs.pop("temperature")
                self.temperature = None
                return fn(**kwargs)
            raise

    def extract(self, system: str, text: str, images: list[bytes], name: str, schema: dict,
                max_tokens: int = 3000) -> StructuredResult:  # pragma: no cover
        raise NotImplementedError


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def __init__(self, s: Settings):
        if not s.anthropic_api_key:
            raise ProviderConfigError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
        super().__init__(s.anthropic_model, s.anthropic_price_input, s.anthropic_price_output, s.temperature)
        import anthropic
        self.client = anthropic.Anthropic(api_key=s.anthropic_api_key)

    def extract(self, system, text, images, name, schema, max_tokens=3000):
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                "data": base64.b64encode(img).decode()}} for img in images]
        content.append({"type": "text", "text": text})
        kwargs = dict(model=self.model, max_tokens=max_tokens, system=system,
                      messages=[{"role": "user", "content": content}],
                      tools=[{"name": name, "description": f"Submit the {name} result.", "input_schema": schema}],
                      tool_choice={"type": "tool", "name": name})
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        resp = self._create(self.client.messages.create, kwargs)
        data = next((dict(b.input) for b in resp.content if b.type == "tool_use"), {})
        i, o = resp.usage.input_tokens, resp.usage.output_tokens
        return StructuredResult(data, i, o, self.cost(i, o))


class OpenAIProvider(BaseProvider):
    name = "openai"

    def __init__(self, s: Settings):
        if not s.openai_api_key:
            raise ProviderConfigError("OPENAI_API_KEY is not set. Add it to your .env file.")
        super().__init__(s.openai_model, s.openai_price_input, s.openai_price_output, s.temperature)
        import openai
        self.client = openai.OpenAI(api_key=s.openai_api_key)

    def extract(self, system, text, images, name, schema, max_tokens=3000):
        content = [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(img).decode()}}
                   for img in images]
        content.append({"type": "text", "text": text})
        kwargs = dict(model=self.model, max_tokens=max_tokens,
                      messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
                      tools=[{"type": "function", "function": {"name": name, "description": f"Submit the {name} result.",
                                                               "parameters": schema}}],
                      tool_choice={"type": "function", "function": {"name": name}})
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        resp = self._create(self.client.chat.completions.create, kwargs)
        calls = resp.choices[0].message.tool_calls or []
        try:
            data = json.loads(calls[0].function.arguments) if calls else {}
        except json.JSONDecodeError:
            data = {}
        i = getattr(resp.usage, "prompt_tokens", 0) or 0
        o = getattr(resp.usage, "completion_tokens", 0) or 0
        return StructuredResult(data, i, o, self.cost(i, o))


def get_provider(s: Settings, name: str | None = None) -> BaseProvider:
    name = (name or s.llm_provider).lower()
    if name in ("anthropic", "claude"):
        return AnthropicProvider(s)
    if name in ("openai", "gpt"):
        return OpenAIProvider(s)
    raise ProviderConfigError(f"Unknown LLM_PROVIDER '{name}'. Use 'anthropic' or 'openai'.")
