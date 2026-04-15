from __future__ import annotations

import logging
from dataclasses import dataclass

try:
    import anthropic
except ImportError:
    anthropic = None


@dataclass(frozen=True)
class AnthropicConfig:
    api_key: str
    model: str = "claude-sonnet-4-5"
    max_tokens: int = 4096


class AnthropicHelper:
    """Thin wrapper around the Anthropic SDK used for video-brief script generation."""

    def __init__(self, config: AnthropicConfig):
        if anthropic is None:
            raise RuntimeError(
                "The 'anthropic' package is not installed. "
                "Add 'anthropic' to requirements.txt to enable Anthropic support."
            )
        self.config = config
        self._client = anthropic.AsyncAnthropic(api_key=config.api_key)

    async def generate(self, system_prompt: str, user_prompt: str) -> tuple[str, int, int]:
        """Return (text, prompt_tokens, completion_tokens)."""
        logging.info("Anthropic: generating response with model %s", self.config.model)
        response = await self._client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "input_tokens", 0) or 0
        completion_tokens = getattr(usage, "output_tokens", 0) or 0
        return "\n".join(parts).strip(), int(prompt_tokens), int(completion_tokens)
