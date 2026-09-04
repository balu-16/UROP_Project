import functools
import secrets
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── App ──
    app_name: str = "RAGnostic"
    environment: str = "local"
    # Deprecated: routers declare both bare + /api-prefixed paths explicitly
    # in main.py; api_prefix is kept only so old .env files still parse.
    api_prefix: str = "/api"
    port: int = 8000
    # Deprecated: CORS is driven by cors_origins (cors_origin_list);
    # frontend_origin is kept only so old .env files still parse.
    frontend_origin: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # ── Supabase (Postgres truth) ──
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    database_url: str = ""  # postgresql://... (or memory://... for offline tests)

    # ── ChromaDB (vector index, local PersistentClient) ──
    chroma_path: str = ".chromadb"
    chroma_collection: str = "ragnostic"

    # ── LLM (NVIDIA NIM, OpenAI-compatible, structured output) ──
    llm_api_key: str = ""
    llm_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    llm_timeout_seconds: float = Field(
        default=12.0,
        validation_alias=AliasChoices("llm_timeout_seconds", "llm_timeout"),
    )
    llm_temperature: float = 0.7
    llm_top_p: float = 0.95
    llm_max_tokens: int = 2048
    mock_llm: bool = False

    # ── Auth (JWT custom HS256) ──
    jwt_secret: str = ""
    jwt_algorithm: str = Field(default="HS256", pattern="^HS256$")
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    cookie_secure: bool = False

    # ── Embeddings ──
    embedding_model_name: str = Field(
        default="Snowflake/snowflake-arctic-embed-s",
        validation_alias=AliasChoices("embedding_model_name", "embedding_model"),
    )
    embedding_batch_size: int = 8
    embedding_dimension: int = Field(
        default=384,
        validation_alias=AliasChoices("embedding_dimension", "embedding_dim"),
    )
    disable_local_models: bool = False

    # ── Chunking / Context ──
    chunk_size: int = 400
    chunk_overlap: int = 50
    chunk_min_tokens: int = 320
    chunk_max_tokens: int = Field(
        default=400,
        validation_alias=AliasChoices("chunk_max_tokens", "chunk_size"),
    )
    chunk_overlap_tokens: int = Field(
        default=50,
        validation_alias=AliasChoices("chunk_overlap_tokens", "chunk_overlap"),
    )
    max_context_tokens: int = 3500
    retrieval_top_k: int = Field(
        default=6,
        validation_alias=AliasChoices("retrieval_top_k", "top_k"),
    )
    top_k: int = Field(
        default=6,
        validation_alias=AliasChoices("top_k", "retrieval_top_k"),
    )  # alias for retrieval_top_k

    # ── Retrieval Policy (deterministic threshold) ──
    high_threshold: float = 0.75
    low_threshold: float = 0.60
    max_hops: int = 2
    max_graph_nodes: int = 40

    # ── Hybrid retrieval (vector + keyword RRF) ──
    vector_top_k: int = 50
    keyword_top_k: int = 50
    rrf_k: int = 60

    # ── Cross-encoder reranking (runs AFTER 0/1/2-hop, never before) ──
    # NOTE: rerank_top_k=5 < top_k=6 by design — the final context is capped
    # to the top-5 reranked chunks even though 6 seeds start expansion.
    reranker_enabled: bool = True
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_candidate_cap: int = 100
    rerank_top_k: int = 5

    # ── Storage / Ops ──
    storage_dir: Path = Path("storage")
    upload_max_mb: int = 25
    total_upload_max_mb: int = 100
    greeting_confidence_threshold: float = 0.45
    rate_limit_per_minute: int = 90
    rate_limit_auth_per_minute: int = 10
    rate_limit_chat_per_minute: int = 30
    rate_limit_ingest_per_minute: int = 12
    debug_retrieval: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Derived ──
    @property
    def resolved_storage_dir(self) -> Path:
        path = self.storage_dir
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        return path

    @property
    def resolved_chroma_path(self) -> Path:
        # If STORAGE_DIR is a test directory, isolate Chroma there (avoid polluting real .chromadb)
        try:
            storage = self.resolved_storage_dir
            if "test" in str(storage):
                test_chroma = storage / ".chromadb"
                return test_chroma
        except Exception:
            pass
        path = Path(self.chroma_path)
        if not path.is_absolute():
            # In container (/app) chroma lives at /app/.chromadb
            try:
                if Path.cwd() == Path("/app") or Path("/app").exists():
                    container_candidate = Path("/app") / path
                    # If env explicitly points to .chromadb and we are in container layout,
                    # prefer /app/.chromadb over repo-root /.
                    if Path(__file__).resolve().as_posix().startswith("/app/"):
                        return container_candidate
            except Exception:
                pass
            # .chromadb relative to repo root (one above server/)
            repo_root = Path(__file__).resolve().parents[3]
            # Guard against resolving to filesystem root in container
            if str(repo_root) == "/":
                repo_root = Path(__file__).resolve().parents[2]
            candidate = repo_root / path
            if candidate.exists() or not (Path(__file__).resolve().parents[2] / path).exists():
                return candidate
            return Path(__file__).resolve().parents[2] / path
        return path

    @property
    def resolved_jwt_secret(self) -> str:
        if not self.jwt_secret:
            return secrets.token_urlsafe(48)
        return self.jwt_secret

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def effective_database_url(self) -> str:
        """Database URL: memory://... for offline tests, else DATABASE_URL."""
        return self.database_url

    @property
    def is_memory_db(self) -> bool:
        url = self.effective_database_url
        return url.startswith("memory://")

    @property
    def is_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
