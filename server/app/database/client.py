from typing import Any

from app.config import Settings
from app.database.memory import MemoryDatabase
from app.database.supabase import SupabaseDatabase
from app.utils.logging import get_logger

logger = get_logger(__name__)


class AppDatabase:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Any | None = None  # supabase client
        self.db: Any | None = None  # SupabaseDatabase | MemoryDatabase

    async def connect(self) -> None:
        # 1. Memory database (tests, offline)
        effective_url = self.settings.effective_database_url
        if effective_url.startswith("memory://"):
            self.db = MemoryDatabase()
            logger.info("Using in-memory database")
            return
        if not self.settings.supabase_url:
            self.db = MemoryDatabase()
            logger.warning("No Supabase URL configured — falling back to in-memory DB")
            return
        # 2. Supabase (primary)
        if self.settings.supabase_url and self.settings.supabase_service_role_key:
            try:
                from supabase import create_client

                supabase_client = create_client(
                    self.settings.supabase_url,
                    self.settings.supabase_service_role_key,
                )
                # Ping: try a lightweight query (table may not exist yet before migration)
                try:
                    supabase_client.table("users").select("_id").limit(1).execute()
                    logger.info("Connected to Supabase %s", self.settings.supabase_url)
                except Exception as ping_exc:
                    # Table missing before migration is okay; log but don't fail
                    logger.warning("Supabase ping warning (run migrations if tables missing): %s", ping_exc)
                self.client = supabase_client
                self.db = SupabaseDatabase(supabase_client)
                return
            except Exception as exc:
                logger.exception("Supabase connection failed: %s", exc)
                raise RuntimeError(f"Failed to connect to Supabase: {exc}") from exc

        # 3. No DB configured — fallback to memory with warning
        self.db = MemoryDatabase()
        logger.warning("No Supabase URL configured — falling back to in-memory DB")

    async def close(self) -> None:
        # Supabase client is stateless (REST); nothing to close
        if self.client is not None and hasattr(self.client, "close"):
            try:
                self.client.close()
            except Exception:
                pass

    def collection(self, name: str):
        if self.db is None:
            raise RuntimeError("Database has not been initialized")
        # MemoryDatabase and SupabaseDatabase both support __getitem__
        if hasattr(self.db, "__getitem__"):
            return self.db[name]
        # fallback (should not happen)
        return self.db[name]

    async def ensure_indexes(self) -> None:
        # For Supabase: indexes are via migrations (supabase/migrations/001_initial.sql)
        # For Memory: create indexes via MemoryCollection
        if isinstance(self.db, MemoryDatabase):
            await self.collection("users").create_index("email", unique=True)
            await self.collection("sessions").create_index([("user_id", 1), ("created_at", -1)])
            await self.collection("chat_sessions").create_index([("user_id", 1), ("updated_at", -1)])
            await self.collection("messages").create_index([("session_id", 1), ("created_at", 1)])
            await self.collection("retrieval_logs").create_index([("session_id", 1), ("created_at", -1)])
            await self.collection("reward_logs").create_index([("session_id", 1), ("created_at", -1)])
            await self.collection("indexed_documents").create_index([("user_id", 1), ("created_at", -1)])
            # New PG truth tables indexes are in migration; no-op for memory
            return
        if isinstance(self.db, SupabaseDatabase):
            # Fast path: if tables already exist, skip migration (avoid slow asyncpg connect)
            try:
                # Quick check via supabase client (postgrest) — if succeeds, tables exist
                self.db.client.table("users").select("_id").limit(1).execute()
                return
            except Exception:
                # Tables missing — fall through to migration
                pass
            if self.settings.database_url and not self.settings.database_url.startswith("memory://"):
                try:
                    import asyncpg  # type: ignore
                    import asyncio

                    from pathlib import Path

                    sql_path = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "001_initial.sql"
                    alt_path = Path(__file__).resolve().parents[3] / "supabase" / "migrations" / "001_initial.sql"
                    sql_file = sql_path if sql_path.exists() else alt_path
                    if sql_file.exists():
                        dsn = self.settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
                        try:
                            conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=5.0)
                            try:
                                sql = sql_file.read_text()
                                await asyncio.wait_for(conn.execute(sql), timeout=10.0)
                                logger.info("Supabase migrations applied from %s", sql_file)
                            finally:
                                await conn.close()
                        except asyncio.TimeoutError:
                            logger.warning("Supabase migration timed out — skipping (tables may already exist)")
                        except Exception as mig_exc:
                            logger.warning("Supabase migration skipped/failed (may already applied): %s", mig_exc)
                except ImportError:
                    logger.info("asyncpg not installed, skipping auto-migration")
                except Exception as exc:
                    logger.warning("ensure_indexes supabase warning: %s", exc)
            return


_database: AppDatabase | None = None


async def init_database(settings: Settings) -> AppDatabase:
    global _database
    database = AppDatabase(settings)
    await database.connect()
    await database.ensure_indexes()
    _database = database
    return database


async def close_database() -> None:
    if _database is not None:
        await _database.close()


def get_database() -> AppDatabase:
    if _database is None:
        raise RuntimeError("Database has not been initialized")
    return _database
