import asyncio
import json
import re
import time
from typing import AsyncGenerator

from fastapi import HTTPException, Request

from app.utils.logging import get_logger

logger = get_logger(__name__)

from app.database import AppDatabase
from app.evaluation import RewardEvaluator
from app.retrieval.adaptive import AdaptiveRetrievalService
from app.services.llm import LLMClient
from app.services.metrics import MetricsService
from app.services.sessions import ChatSessionService
from app.utils.ids import new_id
from app.utils.sse import sse_event
from app.utils.time import utc_now

FOLLOWUP_SYSTEM_PROMPT = (
    "You suggest concise follow-up questions a user might ask next in a chat. "
    "Reply ONLY with a JSON array of exactly 3 short question strings. "
    "No markdown, no numbering, no extra text."
)

# Map threshold depths to legacy arm names for backwards compat with frontend
DEPTH_TO_ARM = {
    0: "standard_rag",
    1: "graph_rag_1hop",
    2: "graph_rag_2hop",
}

_GREETING_RE = re.compile(r"^(hi|hello|hey|hola|namaste|good\s+(morning|afternoon|evening)|yo)(\b|!|\.|,)", re.I)
_GREETING_EXACT = {"hello man", "hey man", "hi man", "hello", "hi", "hey", "hello there", "hey there"}
GREETING_TEXT = (
    "## Hello! 👋\n\n"
    "I'm **RAGnostic** — your adaptive RAG assistant. I can answer from your uploaded documents with citations, "
    "or just chat.\n\n"
    "Try asking something like:\n"
    "- *Summarize my documents*\n"
    "- *What are the key findings?*\n"
    "- Or upload a PDF/TXT/MD and ask about it."
)
GREETING_FOLLOWUPS = ["Summarize my documents", "How does adaptive retrieval work?", "What can you do?"]


def _is_greeting(message: str) -> bool:
    clean = message.strip().lower().split("?")[0].split("!")[0].strip()
    return bool(_GREETING_RE.match(clean)) or clean in _GREETING_EXACT


def _is_short_message(message: str, max_words: int = 4) -> bool:
    return len(message.strip().split()) <= max_words


class ChatService:
    def __init__(
        self,
        db: AppDatabase,
        sessions: ChatSessionService,
        retrieval: AdaptiveRetrievalService,
        llm: LLMClient,
        reward_evaluator: RewardEvaluator,
        metrics: MetricsService,
    ):
        self.db = db
        self.sessions = sessions
        self.retrieval = retrieval
        self.llm = llm
        self.reward_evaluator = reward_evaluator
        self.metrics = metrics
        self._background_tasks: set[asyncio.Task] = set()

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def stream(
        self,
        user: dict,
        message: str,
        session_id: str | None,
        request: Request,
        reasoning: bool = True,
    ) -> AsyncGenerator[str, None]:
        """SSE stream — never dies silently: any unhandled failure is converted
        into an `error` event the frontend can display instead of a dead stream."""
        start = time.perf_counter()
        ctx: dict = {"session_id": session_id}
        try:
            async for event in self._stream_events(
                user, message, session_id, request, reasoning, start, ctx
            ):
                yield event
        except Exception as exc:
            logger.exception("Chat stream failed: %s", exc)
            yield sse_event(
                "error",
                {"message": "Something went wrong while processing your message. Please try again."},
            )
            yield sse_event("done", {"message_id": None, "session_id": ctx["session_id"]})

    async def _stream_events(
        self,
        user: dict,
        message: str,
        session_id: str | None,
        request: Request,
        reasoning: bool,
        start: float,
        ctx: dict,
    ) -> AsyncGenerator[str, None]:
        try:
            chat_session = await self.sessions.get_or_create(
                user["_id"], session_id, message
            )
        except HTTPException as exc:
            yield sse_event("error", {"message": exc.detail, "code": exc.status_code})
            yield sse_event("done", {"message_id": None, "session_id": session_id})
            return
        except Exception as exc:
            yield sse_event("error", {"message": str(exc)})
            yield sse_event("done", {"message_id": None, "session_id": session_id})
            return
        ctx["session_id"] = chat_session["_id"]
        user_message = {
            "_id": new_id("msg"),
            "user_id": user["_id"],
            "session_id": chat_session["_id"],
            "role": "user",
            "content": message,
            "created_at": utc_now(),
        }
        # Early greeting fast-path — before retrieval/LLM, so Hello always works instantly.
        # Strategy stays ZERO_HOP (strategy enum untouched); diagnostics mirror retrieval.
        if _is_greeting(message) and _is_short_message(message):
            # For pure greetings, skip retrieval entirely
            await self.db.collection("messages").insert_one(user_message)
            greeting_text = GREETING_TEXT
            yield sse_event("stage", {"stage": "thinking"})
            yield sse_event("metadata", {"session_id": chat_session["_id"], "sources": [], "retrieval": {"depth": 0, "confidence": 1.0, "strategy": "ZERO_HOP"}})
            yield sse_event("stage", {"stage": "writing"})
            for tok in greeting_text.split(" "):
                if await request.is_disconnected():
                    break
                yield sse_event("token", {"delta": tok + " "})
                await asyncio.sleep(0.008)
            greeting_retrieval = {"depth": 0, "confidence": 1.0, "strategy": "ZERO_HOP"}
            greeting_msg = {
                "_id": new_id("msg"),
                "user_id": user["_id"],
                "session_id": chat_session["_id"],
                "role": "assistant",
                "content": greeting_text,
                "selected_arm": "standard_rag",
                "sources": [],
                "reward": 0.5,
                "latency_ms": int((time.perf_counter() - start) * 1000),
                "reasoning_metadata": {},
                "retrieval_diagnostics": {"depth": 0, "confidence": 1.0, "strategy": "ZERO_HOP"},
                "retrieval": greeting_retrieval,
                "retrieval_log_id": None,
                "created_at": utc_now(),
            }
            await self.db.collection("messages").insert_one(greeting_msg)
            try:
                self.metrics.record_chat("standard_rag", (time.perf_counter() - start) * 1000, 0.5)
            except Exception:
                pass
            await self.sessions.touch(chat_session["_id"])
            yield sse_event("done", {"message_id": greeting_msg["_id"], "session_id": chat_session["_id"]})
            yield sse_event("followups", {"questions": GREETING_FOLLOWUPS})
            return

        yield sse_event("stage", {"stage": "retrieving"})
        # Persist user message and run adaptive retrieval concurrently.
        # A retrieval failure must not kill the stream — report it so the
        # frontend can show the message instead of spinning forever.
        try:
            _, adaptive_payload = await asyncio.gather(
                self.db.collection("messages").insert_one(user_message),
                self.retrieval.retrieve(
                    message, user_id=user["_id"], session_id=chat_session["_id"]
                ),
            )
        except Exception as exc:
            logger.exception("Retrieval failed: %s", exc)
            yield sse_event(
                "error",
                {"message": "Document search is unavailable right now — please try again in a moment."},
            )
            yield sse_event("done", {"message_id": None, "session_id": chat_session["_id"]})
            return

        retrieval_meta = adaptive_payload["retrieval"]
        depth = retrieval_meta["depth"]
        confidence = retrieval_meta["confidence"]
        strategy = retrieval_meta["strategy"]
        selected_arm = DEPTH_TO_ARM.get(depth, "standard_rag")

        # Context is already built inside adaptive_payload
        context_text = adaptive_payload["context"]
        chunks = adaptive_payload["chunks"]

        # Prepare client sources (truncate for SSE). Raw reranker logits are
        # sort-only server-side signals — never ship scores to the client.
        client_sources = []
        for rank, s in enumerate(chunks, start=1):
            text = s.get("text", "")
            client_sources.append(
                {
                    "chunk_id": s.get("chunk_id"),
                    "document_id": s.get("document_id"),
                    "text": text[:600],
                    "truncated": len(text) > 600,
                    "metadata": s.get("metadata", {}),
                    "rank": rank,
                    "entity_ids": s.get("entity_ids", []),
                }
            )

        metadata: dict = {
            "session_id": chat_session["_id"],
            "sources": client_sources,
            "retrieval": {
                "depth": depth,
                "confidence": confidence,
                "strategy": strategy,
                "initial_confidence": retrieval_meta.get("initial_confidence", confidence),
                "retrieval_mode": retrieval_meta.get("retrieval_mode", "hybrid"),
                "candidate_count": retrieval_meta.get("candidate_count", 0),
                "reranked_count": retrieval_meta.get("reranked_count", 0),
                "reranker_model": retrieval_meta.get("reranker_model"),
            },
        }
        # Keep legacy fields for frontend compatibility
        if self.retrieval.settings.debug_retrieval:
            metadata["selected_arm"] = selected_arm
            metadata["arm_scores"] = {selected_arm: confidence}

        # Log retrieval for observability (§59)
        retrieval_log_id = new_id("ret")
        retrieval_log = {
            "_id": retrieval_log_id,
            "user_id": user["_id"],
            "session_id": chat_session["_id"],
            "message_id": user_message["_id"],
            "selected_arm": selected_arm,
            "arm_scores": {selected_arm: confidence},
            "feature_vector": [],  # reserved; threshold policy uses confidence only
            "retrieved_chunks": self._source_payload(chunks),
            "diagnostics": {
                **adaptive_payload.get("diagnostics", {}),
                "depth": depth,
                "confidence": confidence,
                "strategy": strategy,
            },
            "created_at": utc_now(),
        }
        self._spawn(self._safe_insert("retrieval_logs", retrieval_log))
        yield sse_event("metadata", metadata)
        yield sse_event("stage", {"stage": "thinking"})

        # Fast-path for simple greetings / no-document Hello — avoid LLM roundtrip.
        # Threshold lives in Settings so it can be tuned without code changes.
        if _is_greeting(message) and confidence < self.retrieval.settings.greeting_confidence_threshold:
            greeting_text = GREETING_TEXT
            yield sse_event("stage", {"stage": "writing"})
            for tok in greeting_text.split(" "):
                yield sse_event("token", {"delta": tok + " "})
                await asyncio.sleep(0.008)
            # Persist as assistant message (keep retrieval so reload badge matches live)
            latency_ms = (time.perf_counter() - start) * 1000
            greeting_msg = {
                "_id": new_id("msg"),
                "user_id": user["_id"],
                "session_id": chat_session["_id"],
                "role": "assistant",
                "content": greeting_text,
                "selected_arm": selected_arm,
                "sources": [],
                "reward": 0.5,
                "latency_ms": int(latency_ms),
                "reasoning_metadata": {},
                "retrieval_diagnostics": adaptive_payload.get("diagnostics", {}),
                "retrieval": retrieval_meta,
                "retrieval_log_id": retrieval_log_id,
                "created_at": utc_now(),
            }
            await self.db.collection("messages").insert_one(greeting_msg)
            try:
                self.metrics.record_chat(selected_arm, latency_ms, 0.5)
            except Exception:
                pass
            await self.sessions.touch(chat_session["_id"])
            yield sse_event("done", {"message_id": greeting_msg["_id"], "session_id": chat_session["_id"]})
            yield sse_event("followups", {"questions": ["Summarize my documents", "How does adaptive retrieval work?", "What can you do?"]})
            return

        system_prompt = (
            "You are RAGnostic, an adaptive retrieval-augmented assistant. "
            "Answer using the provided context when relevant and cite sources with "
            "bracket numbers like [1]. If the context is insufficient, say what is "
            "missing and answer carefully.\n\n"
            "Format every answer as well-structured Markdown:\n"
            "- Open with a one- or two-sentence direct summary.\n"
            "- Use '##' section headings for multi-part answers.\n"
            "- Use bullet points for unordered lists and numbered steps.\n"
            "- Use **bold** for key terms.\n"
            "- Use a Markdown table when comparing items.\n"
            "- Use fenced code blocks with language tag for code/queries.\n"
            "- Close with '## Sources' listing [n] references when citations were used."
        )
        llm_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context_text}\n\nQuestion:\n{message}"},
        ]

        answer_parts: list[str] = []
        reasoning_details: list = []
        usage = {}
        first_token_seen = False
        try:
            async for event in self.llm.stream_chat(llm_messages, reasoning=reasoning):
                if await request.is_disconnected():
                    break
                if event["event"] == "token":
                    if not first_token_seen:
                        first_token_seen = True
                        yield sse_event("stage", {"stage": "writing"})
                    answer_parts.append(event["delta"])
                    yield sse_event("token", {"delta": event["delta"]})
                elif event["event"] == "reasoning":
                    reasoning_details.append(event["reasoning"])
                    yield sse_event("reasoning", {"reasoning": event["reasoning"]})
                elif event["event"] == "usage":
                    usage = event["usage"]
                    yield sse_event("usage", usage)
                elif event["event"] == "error":
                    yield sse_event("error", {"message": event.get("message", "LLM error")})
        except Exception as exc:
            logger.exception("Chat stream error: %s", exc)
            yield sse_event("error", {"message": str(exc)})
            yield sse_event("done", {"message_id": None, "session_id": chat_session["_id"]})
            return

        answer = "".join(answer_parts).strip()
        if not answer:
            yield sse_event(
                "error",
                {"message": "The model returned an empty response. Please try again."},
            )
            yield sse_event("done", {"message_id": None, "session_id": chat_session["_id"]})
            return

        latency_ms = (time.perf_counter() - start) * 1000
        try:
            reward = await self.reward_evaluator.evaluate(
                message, answer, chunks, latency_ms, usage
            )
            if not isinstance(reward, dict):
                reward = {"reward": 0.0}
        except Exception:
            logger.exception("Reward evaluation failed — persisting partial answer")
            reward = {"reward": 0.0, "truncated": True}

        assistant_message = {
            "_id": new_id("msg"),
            "user_id": user["_id"],
            "session_id": chat_session["_id"],
            "role": "assistant",
            "content": answer,
            "selected_arm": selected_arm,
            "sources": self._source_payload(chunks),
            "reward": float(reward.get("reward", 0)) if isinstance(reward, dict) else 0.0,
            "latency_ms": int(latency_ms),
            "reasoning_metadata": {"reasoning_details": reasoning_details},
            "retrieval_diagnostics": adaptive_payload.get("diagnostics", {}),
            "retrieval": retrieval_meta,
            "retrieval_log_id": retrieval_log_id,
            "created_at": utc_now(),
        }
        await self.db.collection("messages").insert_one(assistant_message)
        # Ensure reward_log latency_ms is int for PG
        reward_payload = dict(reward) if isinstance(reward, dict) else {}
        if "latency_ms" in reward_payload:
            try:
                reward_payload["latency_ms"] = int(float(reward_payload["latency_ms"]))
            except Exception:
                reward_payload["latency_ms"] = 0
        reward_log = {
            "_id": new_id("rew"),
            "user_id": user["_id"],
            "session_id": chat_session["_id"],
            "message_id": assistant_message["_id"],
            **reward_payload,
            "created_at": utc_now(),
        }
        self._spawn(self._safe_insert("reward_logs", reward_log))
        await self.sessions.touch(chat_session["_id"])
        try:
            self.metrics.record_chat(selected_arm, latency_ms, reward.get("reward", 0.0))
        except Exception:
            pass
        yield sse_event("reward", reward)
        done_payload = {
            "message_id": assistant_message["_id"],
            "session_id": chat_session["_id"],
            "retrieval": retrieval_meta,
        }
        yield sse_event("done", done_payload)
        if not await request.is_disconnected():
            followups = await self._generate_followups(message, answer)
            if followups:
                yield sse_event("followups", {"questions": followups})

    async def _generate_followups(self, question: str, answer: str) -> list[str]:
        try:
            raw = await self.llm.complete(
                [
                    {"role": "system", "content": FOLLOWUP_SYSTEM_PROMPT},
                    {"role": "user", "content": f"User question:\n{question[:1000]}\n\nAssistant answer:\n{answer[:2000]}"},
                ],
                max_tokens=180,
                temperature=0.7,
            )
            if not raw:
                return []
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if not match:
                return []
            parsed = json.loads(match.group(0))
            if not isinstance(parsed, list):
                return []
            return [str(q).strip()[:120] for q in parsed if isinstance(q, str) and q.strip()][:3]
        except Exception:
            return []

    async def _safe_insert(self, collection: str, document: dict) -> None:
        try:
            await self.db.collection(collection).insert_one(document)
        except Exception:
            logger.exception("Background insert into %s failed", collection)

    def _source_payload(self, chunks: list[dict]) -> list[dict]:
        # Persisted sources mirror the SSE shape: rank order + text, no raw
        # logits. Diagnostics/keys stay server-side in retrieval_logs.
        payload = []
        for rank, chunk in enumerate(chunks, start=1):
            text = chunk.get("text", "")
            payload.append(
                {
                    "chunk_id": chunk.get("chunk_id"),
                    "document_id": chunk.get("document_id"),
                    "text": text[:600],
                    "truncated": len(text) > 600,
                    "rank": rank,
                    "metadata": chunk.get("metadata", {}),
                    "entity_ids": chunk.get("entity_ids", []),
                }
            )
        return payload
