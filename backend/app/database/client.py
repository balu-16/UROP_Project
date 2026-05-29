from typing import Any

from app.config import Settings
from app.database.memory import MemoryDatabase
from app.utils.logging import get_logger

logger = get_logger(__name__)


class AppDatabase:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Any | None = None
        self.db: Any | None = None

    async def connect(self) -> None:
        if self.settings.mongodb_url.startswith("memory://"):
            self.db = MemoryDatabase()
            logger.info("Using in-memory database")
            return
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(
            self.settings.mongodb_url, uuidRepresentation="standard"
        )
        db = client[self.settings.mongodb_db_name]
        self.client = client
        self.db = db
        await db.command("ping")
        logger.info("Connected to MongoDB database %s", self.settings.mongodb_db_name)

    async def close(self) -> None:
        if self.client is not None:
            self.client.close()

    def collection(self, name: str):
        if self.db is None:
            raise RuntimeError("Database has not been initialized")
        return self.db[name]

    async def ensure_indexes(self) -> None:
        await self.collection("users").create_index("email", unique=True)
        await self.collection("sessions").create_index(
            [("user_id", 1), ("created_at", -1)]
        )
        await self.collection("chat_sessions").create_index(
            [("user_id", 1), ("updated_at", -1)]
        )
        await self.collection("messages").create_index(
            [("session_id", 1), ("created_at", 1)]
        )
        await self.collection("retrieval_logs").create_index(
            [("session_id", 1), ("created_at", -1)]
        )
        await self.collection("reward_logs").create_index(
            [("session_id", 1), ("created_at", -1)]
        )
        await self.collection("indexed_documents").create_index(
            [("user_id", 1), ("created_at", -1)]
        )


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
