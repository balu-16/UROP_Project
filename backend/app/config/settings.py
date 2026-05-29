import functools
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RAGnostic"
    environment: str = "local"
    api_prefix: str = ""
    frontend_origin: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    mongodb_url: str = "memory://ragnostic"
    mongodb_db_name: str = "ragnostic"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "moonshotai/kimi-k2.6:free"
    openrouter_timeout_seconds: float = 60.0
    mock_openrouter: bool = False

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    cookie_secure: bool = False

    embedding_model_name: str = "BAAI/bge-large-en-v1.5"
    embedding_batch_size: int = 8
    embedding_dimension: int = 1024
    disable_local_models: bool = False

    chunk_min_tokens: int = 400
    chunk_max_tokens: int = 500
    chunk_overlap_tokens: int = 80
    max_context_tokens: int = 3500
    retrieval_top_k: int = 6

    storage_dir: Path = Path("storage")
    upload_max_mb: int = 25
    rate_limit_per_minute: int = 90

    linucb_alpha: float = 0.8
    bandit_feature_dim: int = 7

    debug_retrieval: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def resolved_storage_dir(self) -> Path:
        path = self.storage_dir
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        return path

    @property
    def resolved_jwt_secret(self) -> str:
        if not self.jwt_secret:
            return secrets.token_urlsafe(48)
        return self.jwt_secret

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
