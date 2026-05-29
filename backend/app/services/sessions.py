from app.database import AppDatabase
from app.utils.ids import new_id
from app.utils.time import utc_now


class ChatSessionService:
    def __init__(self, db: AppDatabase):
        self.db = db

    async def create(self, user_id: str, title: str | None = None) -> dict:
        now = utc_now()
        session = {
            "_id": new_id("chat"),
            "user_id": user_id,
            "title": title or "New chat",
            "created_at": now,
            "updated_at": now,
        }
        await self.db.collection("chat_sessions").insert_one(session)
        return session

    async def get_or_create(
        self, user_id: str, session_id: str | None, first_message: str
    ) -> dict:
        if session_id:
            session = await self.db.collection("chat_sessions").find_one(
                {"_id": session_id, "user_id": user_id}
            )
            if session:
                return session
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
            )
        title = first_message.strip().splitlines()[0][:80] or "New chat"
        return await self.create(user_id, title)

    async def list(self, user_id: str) -> list[dict]:
        return (
            await self.db.collection("chat_sessions")
            .find({"user_id": user_id})
            .sort("updated_at", -1)
            .to_list(100)
        )

    async def touch(self, session_id: str) -> None:
        await self.db.collection("chat_sessions").update_one(
            {"_id": session_id},
            {"$set": {"updated_at": utc_now()}},
        )

    async def cleanup_expired(self, max_age_days: int = 30) -> int:
        """Remove sessions older than max_age_days."""
        from datetime import timedelta

        cutoff = utc_now() - timedelta(days=max_age_days)
        result = await self.db.collection("chat_sessions").delete_many(
            {"updated_at": {"$lt": cutoff}}
        )
        return result.deleted_count
