"""OpenAI chat-completion LLM provider (production)."""

from __future__ import annotations

from .base import LLMProvider


class OpenAILLMProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None,
        base_url: str | None,
        model: str,
        temperature: float,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI API key is required for the openai llm provider")
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._temperature = temperature

    async def complete(self, system: str, user: str) -> str:
        res = await self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return res.choices[0].message.content or ""
