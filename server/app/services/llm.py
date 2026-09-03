"""LLMClient — NVIDIA NIM OpenAI-compatible via `openai` SDK, structured output.

Uses:
  from openai import AsyncOpenAI
  client = AsyncOpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=...)
Supports streaming + reasoning (thinking) + structured JSON.
"""
import asyncio
import json
from typing import Any, AsyncGenerator

from app.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None
        # Lazy import openai to avoid hard dependency at import time
        self._openai = None
        try:
            from openai import AsyncOpenAI

            self._openai = AsyncOpenAI
        except Exception:
            self._openai = None

    def _get_client(self):
        if self.settings.mock_llm or not self.settings.llm_api_key:
            return None
        if self._client is not None:
            return self._client
        if self._openai is None:
            return None
        # Short timeout so Hello doesn't hang for 60s (fallback triggers fast)
        try:
            timeout = float(getattr(self.settings, "llm_timeout_seconds", 12.0) or 12.0)
        except Exception:
            timeout = 12.0
        self._client = self._openai(
            base_url=self.settings.llm_base_url,
            api_key=self.settings.llm_api_key,
            timeout=timeout,
            max_retries=0,
        )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass

    async def complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 256,
        temperature: float = 0.6,
        reasoning: bool = False,
        structured: bool = False,
    ) -> str:
        if self.settings.mock_llm or not self.settings.llm_api_key:
            return ""
        client = self._get_client()
        if client is None:
            return ""
        kwargs: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": self.settings.llm_top_p,
            "stream": False,
        }
        if structured:
            kwargs["response_format"] = {"type": "json_object"}
        if reasoning:
            kwargs["extra_body"] = {"chat_template_kwargs": {"thinking": True, "reasoning_effort": "high"}}
        # Retry
        for attempt in range(2):
            try:
                resp = await client.chat.completions.create(**kwargs)
                choice = resp.choices[0] if resp.choices else None
                if not choice:
                    return ""
                msg = choice.message
                # Extract reasoning if present
                reasoning_content = getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)
                # For non-stream, just return content
                return msg.content or ""
            except Exception as exc:
                logger.warning("LLM complete attempt %s failed: %s", attempt, exc)
                if attempt == 1:
                    return ""
                await asyncio.sleep(1)
        return ""

    async def structured_complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Request JSON structured output. Returns parsed dict or {} on failure."""
        raw = await self.complete(messages, max_tokens=self.settings.llm_max_tokens, temperature=0.2, structured=True)
        if not raw:
            return {}
        try:
            # Try to extract JSON
            import re
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                return json.loads(m.group(0))
            return json.loads(raw)
        except Exception:
            return {"raw": raw}

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        reasoning: bool = True,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if self.settings.mock_llm or not self.settings.llm_api_key:
            text = (
                "## Mock mode\n\n"
                "RAGnostic is running **without a live LLM connection**, so this "
                "response is generated locally.\n\n"
                "### What still works\n\n"
                "- Retrieval over your indexed documents\n"
                "- Graph expansion and adaptive threshold selection\n"
                "- Structured streaming responses like this one\n\n"
                "| Component | Status |\n"
                "| --- | --- |\n"
                "| Retriever | Active (Chroma + PG) |\n"
                "| Policy | Threshold (0/1/2-hop) |\n"
                "| LLM | Mock |"
            )
            for word in text.split(" "):
                yield {"event": "token", "delta": word + " "}
                await asyncio.sleep(0.005)
            yield {"event": "usage", "usage": {"prompt_tokens": 32, "completion_tokens": len(text.split())}}
            return

        client = self._get_client()
        if client is None:
            yield {"event": "token", "delta": "[LLM not configured]"}
            return

        kwargs: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "stream": True,
            "temperature": self.settings.llm_temperature,
            "top_p": self.settings.llm_top_p,
            "max_tokens": self.settings.llm_max_tokens,
        }
        # Reasoning/thinking extra_body is only supported by reasoning models.
        # Send it first, retry without it if the provider rejects it.
        thinking_body = {"chat_template_kwargs": {"thinking": bool(reasoning), "reasoning_effort": "high"}}
        attempts: list[dict[str, Any]] = [
            {**kwargs, "extra_body": thinking_body},
            dict(kwargs),
        ]

        for attempt, call_kwargs in enumerate(attempts):
            try:
                stream = await client.chat.completions.create(**call_kwargs)
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    delta = choice.delta
                    # Content
                    content = getattr(delta, "content", None)
                    if content:
                        yield {"event": "token", "delta": content}
                    # Reasoning
                    reasoning_content = getattr(delta, "reasoning", None) or getattr(delta, "reasoning_content", None)
                    if reasoning_content:
                        yield {"event": "reasoning", "reasoning": reasoning_content}
                    # Usage (last chunk)
                    if getattr(chunk, "usage", None):
                        yield {"event": "usage", "usage": chunk.usage.model_dump() if hasattr(chunk.usage, "model_dump") else chunk.usage}
                return
            except Exception as exc:
                logger.warning("LLM stream attempt %s failed: %s", attempt, exc)
                if attempt == 1:
                    # Tell the frontend the LLM failed, then fall back to a
                    # friendly greeting so basic Hello never hangs
                    yield {
                        "event": "error",
                        "message": "The LLM service is unavailable right now — showing a basic reply.",
                    }
                    fallback = (
                        "Hello! I'm RAGnostic — your adaptive RAG assistant. "
                        "Ask me anything, or upload a PDF/TXT/MD and I'll answer with citations. "
                        "How can I help today?"
                    )
                    for word in fallback.split(" "):
                        yield {"event": "token", "delta": word + " "}
                        await asyncio.sleep(0.005)
                    yield {"event": "usage", "usage": {"prompt_tokens": 12, "completion_tokens": len(fallback.split())}}
                    return
                await asyncio.sleep(1)
