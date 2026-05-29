import asyncio
import json
from typing import Any, AsyncGenerator

import httpx

from app.config import Settings


class OpenRouterClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            timeout = httpx.Timeout(self.settings.openrouter_timeout_seconds)
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        reasoning: bool = True,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if self.settings.mock_openrouter or not self.settings.openrouter_api_key:
            text = "RAGnostic is running in local mock mode. I used the retrieved context to generate this answer."
            for word in text.split(" "):
                yield {"event": "token", "delta": word + " "}
            yield {
                "event": "usage",
                "usage": {"prompt_tokens": 32, "completion_tokens": len(text.split())},
            }
            return
        payload = {
            "model": self.settings.openrouter_model,
            "messages": messages,
            "stream": True,
        }
        if reasoning:
            payload["reasoning"] = {"enabled": True}
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.frontend_origin,
            "X-Title": self.settings.app_name,
        }
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                client = await self._get_client()
                async with client.stream(
                    "POST",
                    f"{self.settings.openrouter_base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        raw = line.removeprefix("data:").strip()
                        if raw == "[DONE]":
                            return
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue  # skip malformed SSE lines
                        choice = data.get("choices", [{}])[0]
                        delta = choice.get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield {"event": "token", "delta": content}
                        reasoning_details = delta.get("reasoning_details") or delta.get(
                            "reasoning"
                        )
                        if reasoning_details:
                            yield {"event": "reasoning", "reasoning": reasoning_details}
                        if data.get("usage"):
                            yield {"event": "usage", "usage": data["usage"]}
                    return
            except Exception as exc:
                last_error = exc
                if attempt == 2:
                    raise
                await asyncio.sleep(2**attempt)  # exponential backoff: 1s, 2s
        if last_error:
            raise last_error
