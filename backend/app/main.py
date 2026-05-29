from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, chat, ingestion, observability, sessions
from app.bandit import LinUCB
from app.config import get_settings
from app.database import close_database, init_database
from app.embeddings import EmbeddingService
from app.evaluation import RewardEvaluator
from app.graph import EntityGraph
from app.retrieval import RetrievalOrchestrator
from app.services.chat import ChatService
from app.services.context import ContextBuilder
from app.services.entity_extraction import EntityExtractor
from app.services.features import FeatureExtractor
from app.services.ingestion import IngestionService
from app.services.metrics import MetricsService
from app.services.openrouter import OpenRouterClient
from app.services.sessions import ChatSessionService
from app.utils.logging import configure_logging, get_logger
from app.utils.rate_limit import InMemoryRateLimiter
from app.vectorstore import VectorStore

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if (
        not settings.jwt_secret
        or settings.jwt_secret == "change-this-local-development-secret"
    ):
        if settings.environment == "production":
            raise RuntimeError("JWT_SECRET must be set in production")
        # Auto-generate an ephemeral secret for local dev so the app still starts
        import secrets as _secrets

        settings.jwt_secret = _secrets.token_urlsafe(48)
        logger.warning(
            "JWT secret not configured — using ephemeral secret (tokens won't survive restart)"
        )
    settings.resolved_storage_dir.mkdir(parents=True, exist_ok=True)
    db = await init_database(settings)
    embeddings = EmbeddingService(settings)
    await embeddings.startup()
    vector_store = VectorStore(settings)
    vector_store.startup()
    entity_graph = EntityGraph(settings)
    entity_graph.startup()
    extractor = EntityExtractor(settings)
    extractor.startup()
    bandit = LinUCB(settings)
    bandit.startup()
    metrics = MetricsService()
    session_service = ChatSessionService(db)
    retrieval = RetrievalOrchestrator(settings, embeddings, vector_store, entity_graph)
    feature_extractor = FeatureExtractor(extractor)
    context_builder = ContextBuilder(settings)
    reward_evaluator = RewardEvaluator(embeddings)
    openrouter = OpenRouterClient(settings)
    app.state.settings = settings
    app.state.db = db
    app.state.embeddings = embeddings
    app.state.vector_store = vector_store
    app.state.entity_graph = entity_graph
    app.state.extractor = extractor
    app.state.bandit = bandit
    app.state.metrics = metrics
    app.state.session_service = session_service
    app.state.ingestion_service = IngestionService(
        settings, db, embeddings, vector_store, entity_graph, extractor
    )
    app.state.chat_service = ChatService(
        db,
        session_service,
        retrieval,
        feature_extractor,
        bandit,
        context_builder,
        openrouter,
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
    logger.info("RAGnostic backend started")
    try:
        yield
    finally:
        await openrouter.close()
        await embeddings.shutdown()
        vector_store.shutdown()
        bandit.shutdown()
        entity_graph.save()
        await close_database()
        logger.info("RAGnostic backend stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        max_age=600,
    )
    limiter = InMemoryRateLimiter(settings.rate_limit_per_minute)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if request.url.path not in {"/health", "/app-config"}:
            await limiter.check(request)
        return await call_next(request)

    @app.exception_handler(Exception)
    async def unhandled_exception(_: Request, exc: Exception):
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )

    app.include_router(observability.router)
    app.include_router(auth.router)
    app.include_router(sessions.router)
    app.include_router(ingestion.router)
    app.include_router(chat.router)
    return app


app = create_app()
