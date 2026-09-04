from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, chat, ingestion, observability, sessions
from app.config import get_settings
from app.database import close_database, init_database
from app.embeddings import EmbeddingService
from app.evaluation import RewardEvaluator
from app.graph_store.pg_store import PGGraphStore
from app.retrieval.adaptive import AdaptiveRetrievalService
from app.retrieval.confidence import RetrievalConfidenceEvaluator
from app.retrieval.keyword import PostgresKeywordRetriever, extract_supa_client, supa_rpc_caller
from app.retrieval.reranking import NullReranker, build_reranker
from app.retrieval.policy import ThresholdRetrievalPolicy
from app.services.chat import ChatService
from app.services.context import ContextBuilder
from app.services.entity_extraction import EntityExtractor
from app.services.ingestion import IngestionService
from app.services.llm import LLMClient
from app.services.metrics import MetricsService
from app.services.sessions import ChatSessionService
from app.utils.logging import configure_logging, get_logger
from app.utils.rate_limit import InMemoryRateLimiter, RateLimitMiddleware
from app.vectorstore import VectorStore

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Keep top_k / retrieval_top_k in sync (both env aliases now, but be safe)
    try:
        if settings.top_k != settings.retrieval_top_k:
            settings.retrieval_top_k = settings.top_k
    except Exception:
        pass
    if (
        not settings.jwt_secret
        or settings.jwt_secret.startswith("change-this")
    ):
        if settings.environment == "production":
            raise RuntimeError("JWT_SECRET must be set in production")
        import secrets as _secrets

        settings.jwt_secret = _secrets.token_urlsafe(48)
        logger.warning("JWT secret not configured — using ephemeral secret (tokens won't survive restart)")
    settings.resolved_storage_dir.mkdir(parents=True, exist_ok=True)
    # Ensure Chroma path exists (strict boot: fail fast if unwritable)
    try:
        settings.resolved_chroma_path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise RuntimeError(
            f"Chroma path not writable (strict boot): {settings.resolved_chroma_path}: {exc}"
        ) from exc

    db = await init_database(settings)
    embeddings = EmbeddingService(settings)
    await embeddings.startup()
    if not settings.disable_local_models and embeddings.model is None:
        raise RuntimeError(
            "Embedding model failed to load (strict boot). "
            f"Check EMBEDDING_MODEL={settings.embedding_model_name}, "
            "HF_HOME cache, and network access. "
            "Set DISABLE_LOCAL_MODELS=true only for offline unit tests."
        )
    if not settings.mock_llm and not settings.llm_api_key:
        raise RuntimeError(
            "LLM_API_KEY is empty with MOCK_LLM=false (strict boot). "
            "Set a real NVIDIA NIM key or MOCK_LLM=true for offline tests."
        )
    vector_store = VectorStore(settings)
    try:
        vector_store.startup()
    except Exception as exc:
        # Strict boot: fail fast so missing/corrupt Chroma is visible immediately.
        raise RuntimeError(
            f"Vector store startup failed (strict boot): {exc}. "
            f"Fix: .venv/bin/pip install chromadb==0.5.23 and ensure {settings.resolved_chroma_path} is writable."
        ) from exc
    if vector_store.collection is None:
        raise RuntimeError(
            f"Vector store collection is None after startup (strict boot): {settings.resolved_chroma_path}"
        )
    # PG graph store (entity graph over Supabase tables)
    graph_store = PGGraphStore(settings, db)
    graph_store.startup()
    extractor = EntityExtractor(settings)
    extractor.startup()

    metrics = MetricsService()
    session_service = ChatSessionService(db)
    confidence = RetrievalConfidenceEvaluator()
    policy = ThresholdRetrievalPolicy(settings)
    context_builder = ContextBuilder(settings)
    # Lexical branch of hybrid retrieval. Degrades to vector-only when no PG
    # client exists (memory-DB tests, offline mode) — never crashes boot.
    _supa_client = extract_supa_client(db)
    keyword_retriever = PostgresKeywordRetriever(
        settings, supa_rpc_caller(_supa_client) if _supa_client is not None else None
    )
    # Cross-encoder reranker (post-hop). build_reranker never raises: worst
    # case is NullReranker, so strict boot is unaffected by model availability.
    try:
        reranker = build_reranker(settings)
    except Exception as exc:
        logger.warning("reranker wiring failed (%s) — continuing without reranking", exc)
        reranker = NullReranker("wiring_failed")
    adaptive_retrieval = AdaptiveRetrievalService(
        settings, embeddings, vector_store, graph_store, confidence, policy, context_builder,
        keyword_retriever=keyword_retriever,
        reranker=reranker,
    )
    reward_evaluator = RewardEvaluator(embeddings)
    llm = LLMClient(settings)

    app.state.settings = settings
    app.state.db = db
    app.state.embeddings = embeddings
    app.state.vector_store = vector_store
    app.state.graph_store = graph_store
    app.state.extractor = extractor
    app.state.metrics = metrics
    app.state.session_service = session_service
    app.state.ingestion_service = IngestionService(
        settings, db, embeddings, vector_store, graph_store, extractor
    )
    app.state.chat_service = ChatService(
        db,
        session_service,
        adaptive_retrieval,
        llm,
        reward_evaluator,
        metrics,
    )

    # Clean up expired and revoked auth sessions on startup
    try:
        from app.utils.time import utc_now

        result = await db.collection("sessions").delete_many(
            {
                "$or": [
                    {"expires_at": {"$lt": utc_now()}},
                    {"revoked": True},
                ]
            }
        )
        if result.deleted_count:
            logger.info("Cleaned up %d stale sessions", result.deleted_count)
    except Exception:
        pass
    logger.info("RAGnostic backend started (PG+Chroma, threshold=%s/%s, max_hops=%s)", settings.high_threshold, settings.low_threshold, settings.max_hops)

    # Periodic purge of expired chat sessions (memory + PG). Runs daily;
    # cancelled on shutdown.
    import asyncio as _asyncio

    _stop_cleanup = _asyncio.Event()

    async def _cleanup_loop() -> None:
        try:
            while not _stop_cleanup.is_set():
                try:
                    await _asyncio.wait_for(_stop_cleanup.wait(), timeout=24 * 3600)
                except _asyncio.TimeoutError:
                    pass
                if _stop_cleanup.is_set():
                    break
                try:
                    removed = await session_service.cleanup_expired()
                    if removed:
                        logger.info("Cleaned up %d expired chat sessions", removed)
                except Exception:
                    logger.exception("Periodic chat-session cleanup failed")
        except _asyncio.CancelledError:
            pass

    _cleanup_task = _asyncio.create_task(_cleanup_loop())
    # Keep a handle so shutdown can cancel it deterministically.
    chat_service = app.state.chat_service
    try:
        yield
    finally:
        _stop_cleanup.set()
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except Exception:
            pass
        # Drain pending background inserts (retrieval/reward logs) before
        # closing the DB so buffered writes are not lost on shutdown.
        try:
            pending = list(getattr(chat_service, "_background_tasks", set()))
            if pending:
                await _asyncio.wait_for(
                    _asyncio.gather(*pending, return_exceptions=True), timeout=10.0
                )
        except Exception:
            logger.exception("Error draining background tasks")
        try:
            await llm.close()
        except Exception:
            logger.exception("Error closing LLM client")
        try:
            await embeddings.shutdown()
        except Exception:
            logger.exception("Error shutting down embeddings")
        try:
            vector_store.shutdown()
        except Exception:
            logger.exception("Error shutting down vector store")
        try:
            graph_store.shutdown()
        except Exception:
            logger.exception("Error saving graph store")
        try:
            await close_database()
        except Exception:
            logger.exception("Error closing database")
        logger.info("RAGnostic backend stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    # Support both /api prefix and legacy root paths for backward compat
    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

    sse_paths = {"/chat", "/api/chat"}

    class SSENoGzipMiddleware:
        """Strip gzip from Accept-Encoding on SSE endpoints.

        GZipMiddleware buffers compressed output, so streaming responses
        (chat token events) only arrive when the stream ends — the browser
        sees the whole answer in one lump instead of live tokens.
        """

        def __init__(self, app, paths: set[str]):
            self.app = app
            self.paths = paths

        async def __call__(self, scope, receive, send):
            _p = scope.get("path") or "/"
            _norm = _p[:-1] if len(_p) > 1 and _p.endswith("/") else _p
            if scope["type"] == "http" and _norm in {p if len(p) == 1 or not p.endswith("/") else p[:-1] for p in self.paths}:
                scope["headers"] = [
                    (key, b"identity" if key == b"accept-encoding" else value)
                    for key, value in scope["headers"]
                ]
            await self.app(scope, receive, send)

    # Added after GZipMiddleware so it wraps it (outermost wins for the
    # request headers GZipMiddleware observes).
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(SSENoGzipMiddleware, paths=sse_paths)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        max_age=600,
    )
    limiter = InMemoryRateLimiter(
        settings.rate_limit_per_minute,
        per_route_limits={
            "/auth": settings.rate_limit_auth_per_minute,
            "/api/auth": settings.rate_limit_auth_per_minute,
            "/chat": settings.rate_limit_chat_per_minute,
            "/api/chat": settings.rate_limit_chat_per_minute,
            "/index-documents": settings.rate_limit_ingest_per_minute,
            "/api/index-documents": settings.rate_limit_ingest_per_minute,
            "/ingestion": settings.rate_limit_ingest_per_minute,
            "/api/ingestion": settings.rate_limit_ingest_per_minute,
        },
    )
    app.add_middleware(
        RateLimitMiddleware, limiter=limiter, exempt_paths={"/health", "/app-config", "/api/health", "/api/app-config"}
    )

    @app.exception_handler(Exception)
    async def unhandled_exception(_: Request, exc: Exception):
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    # Routers already define paths with /api prefix internally where needed; include both
    app.include_router(observability.router)
    app.include_router(auth.router)
    app.include_router(auth.api_router)
    app.include_router(sessions.router)
    app.include_router(sessions.api_router)
    app.include_router(ingestion.router)
    app.include_router(chat.router)
    return app


app = create_app()
