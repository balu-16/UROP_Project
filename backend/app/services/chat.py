import time
from typing import AsyncGenerator

from fastapi import Request

from app.bandit import LinUCB
from app.database import AppDatabase
from app.evaluation import RewardEvaluator
from app.retrieval import RetrievalOrchestrator
from app.services.context import ContextBuilder
from app.services.features import FeatureExtractor
from app.services.metrics import MetricsService
from app.services.openrouter import OpenRouterClient
from app.services.sessions import ChatSessionService
from app.utils.ids import new_id
from app.utils.sse import sse_event
from app.utils.time import utc_now


class ChatService:
    def __init__(
        self,
        db: AppDatabase,
        sessions: ChatSessionService,
        retrieval: RetrievalOrchestrator,
        features: FeatureExtractor,
        bandit: LinUCB,
        context_builder: ContextBuilder,
        openrouter: OpenRouterClient,
        reward_evaluator: RewardEvaluator,
        metrics: MetricsService,
    ):
        self.db = db
        self.sessions = sessions
        self.retrieval = retrieval
        self.features = features
        self.bandit = bandit
        self.context_builder = context_builder
        self.openrouter = openrouter
        self.reward_evaluator = reward_evaluator
        self.metrics = metrics

    async def stream(
        self, user: dict, message: str, session_id: str | None, request: Request
    ) -> AsyncGenerator[str, None]:
        start = time.perf_counter()
        chat_session = await self.sessions.get_or_create(
            user["_id"], session_id, message
        )
        user_message = {
            "_id": new_id("msg"),
            "user_id": user["_id"],
            "session_id": chat_session["_id"],
            "role": "user",
            "content": message,
            "created_at": utc_now(),
        }
        await self.db.collection("messages").insert_one(user_message)
        query_vector, prefetch = await self.retrieval.prefetch(
            message, user_id=user["_id"]
        )
        feature_payload = await self.features.extract(message, prefetch)
        selected_arm, arm_scores = self.bandit.select(feature_payload["vector"])
        retrieval_payload = await self.retrieval.retrieve(
            selected_arm, query_vector, prefetch
        )
        context_payload = self.context_builder.build(retrieval_payload["chunks"])
        # Strip internal scores from sources before sending to client
        client_sources = [
            {
                "chunk_id": s.get("chunk_id"),
                "document_id": s.get("document_id"),
                "text": s.get("text", "")[:600],
                "metadata": s.get("metadata", {}),
            }
            for s in context_payload["chunks"]
        ]
        metadata: dict = {
            "session_id": chat_session["_id"],
            "sources": client_sources,
        }
        if self.context_builder.settings.debug_retrieval:
            metadata["selected_arm"] = selected_arm
            metadata["arm_scores"] = arm_scores
        retrieval_log_id = new_id("ret")
        await self.db.collection("retrieval_logs").insert_one(
            {
                "_id": retrieval_log_id,
                "user_id": user["_id"],
                "session_id": chat_session["_id"],
                "message_id": user_message["_id"],
                "selected_arm": selected_arm,
                "arm_scores": arm_scores,
                "feature_vector": feature_payload["vector"],
                "retrieved_chunks": self._source_payload(retrieval_payload["chunks"]),
                "diagnostics": retrieval_payload["diagnostics"],
                "created_at": utc_now(),
            }
        )
        yield sse_event("metadata", metadata)
        system_prompt = (
            "You are RAGnostic, an adaptive retrieval-augmented assistant. "
            "Answer using the provided context when relevant. Cite source bracket numbers where useful. "
            "If the context is insufficient, say what is missing and answer carefully."
        )
        llm_messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Context:\n{context_payload['context']}\n\nQuestion:\n{message}",
            },
        ]
        answer_parts: list[str] = []
        reasoning_details: list = []
        usage = {}
        try:
            async for event in self.openrouter.stream_chat(
                llm_messages, reasoning=True
            ):
                if await request.is_disconnected():
                    break
                if event["event"] == "token":
                    answer_parts.append(event["delta"])
                    yield sse_event("token", {"delta": event["delta"]})
                elif event["event"] == "reasoning":
                    reasoning_details.append(event["reasoning"])
                    yield sse_event("reasoning", {"reasoning": event["reasoning"]})
                elif event["event"] == "usage":
                    usage = event["usage"]
                    yield sse_event("usage", usage)
        except Exception as exc:
            yield sse_event("error", {"message": str(exc)})
            yield sse_event(
                "done", {"message_id": None, "session_id": chat_session["_id"]}
            )
            return
        answer = "".join(answer_parts).strip()
        if not answer:
            yield sse_event(
                "done", {"message_id": None, "session_id": chat_session["_id"]}
            )
            return
        latency_ms = (time.perf_counter() - start) * 1000
        reward = await self.reward_evaluator.evaluate(
            message, answer, context_payload["chunks"], latency_ms, usage
        )
        # Bandit update is handled via user feedback in observability.py
        assistant_message = {
            "_id": new_id("msg"),
            "user_id": user["_id"],
            "session_id": chat_session["_id"],
            "role": "assistant",
            "content": answer,
            "selected_arm": selected_arm,
            "sources": self._source_payload(context_payload["chunks"]),
            "reward": reward["reward"],
            "latency_ms": latency_ms,
            "reasoning_metadata": {"reasoning_details": reasoning_details},
            "retrieval_diagnostics": retrieval_payload["diagnostics"],
            "retrieval_log_id": retrieval_log_id,
            "created_at": utc_now(),
        }
        await self.db.collection("messages").insert_one(assistant_message)
        await self.db.collection("reward_logs").insert_one(
            {
                "_id": new_id("rew"),
                "user_id": user["_id"],
                "session_id": chat_session["_id"],
                "message_id": assistant_message["_id"],
                **reward,
                "created_at": utc_now(),
            }
        )
        await self.sessions.touch(chat_session["_id"])
        self.metrics.record_chat(selected_arm, latency_ms, reward["reward"])
        yield sse_event("reward", reward)
        yield sse_event(
            "done",
            {"message_id": assistant_message["_id"], "session_id": chat_session["_id"]},
        )

    def _source_payload(self, chunks: list[dict]) -> list[dict]:
        return [
            {
                "chunk_id": chunk.get("chunk_id"),
                "document_id": chunk.get("document_id"),
                "text": chunk.get("text", "")[:600],
                "score": chunk.get("score", 0),
                "metadata": chunk.get("metadata", {}),
                "entity_ids": chunk.get("entity_ids", []),
            }
            for chunk in chunks
        ]
