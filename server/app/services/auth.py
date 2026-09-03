import hashlib
import secrets
from datetime import timedelta
from typing import Any

import bcrypt
from fastapi import HTTPException, Response, status
from jose import JWTError, jwt

from app.config import Settings
from app.database import AppDatabase
from app.utils.ids import new_id
from app.utils.time import utc_now


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["_id"],
        "email": user["email"],
        "name": user["name"],
        "created_at": user["created_at"],
    }


class AuthService:
    def __init__(self, db: AppDatabase, settings: Settings):
        self.db = db
        self.settings = settings

    def hash_password(self, password: str) -> str:
        secret = password.encode("utf-8")[:72]
        return bcrypt.hashpw(secret, bcrypt.gensalt(rounds=12)).decode("utf-8")

    def verify_password(self, password: str, password_hash: str) -> bool:
        secret = password.encode("utf-8")[:72]
        return bcrypt.checkpw(secret, password_hash.encode("utf-8"))

    def hash_refresh_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_access_token(self, user_id: str) -> str:
        now = utc_now()
        jti = new_id("tkn")
        payload = {
            "sub": user_id,
            "iat": int(now.timestamp()),
            "exp": int(
                (
                    now + timedelta(minutes=self.settings.access_token_minutes)
                ).timestamp()
            ),
            "type": "access",
            "jti": jti,
        }
        return jwt.encode(
            payload, self.settings.jwt_secret, algorithm=self.settings.jwt_algorithm
        )

    def decode_access_token(self, token: str) -> dict[str, Any]:
        try:
            payload = jwt.decode(
                token,
                self.settings.jwt_secret,
                algorithms=[self.settings.jwt_algorithm],
            )
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            ) from exc
        if payload.get("type") != "access" or not payload.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )
        return payload

    async def validate_access_token(self, token: str) -> dict:
        """Decode JWT and verify the token hasn't been revoked by a refresh rotation.
        Returns the authenticated user dict."""
        payload = self.decode_access_token(token)
        user_id = str(payload["sub"])
        user = await self.db.collection("users").find_one({"_id": user_id})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
            )
        # Check if token was issued before the last token rotation
        token_iat = payload.get("iat", 0)
        invalid_before = user.get("token_invalid_before")
        if invalid_before:
            rotation_ts = (
                invalid_before.timestamp()
                if hasattr(invalid_before, "timestamp")
                else float(invalid_before)
            )
            # Use int comparison to avoid false positives when token and rotation are in same second
            # (new token's iat is int seconds, rotation has ms). e.g., rotation 1000.123, token 1000 should be valid.
            if token_iat < int(rotation_ts):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                )
        return user

    async def signup(
        self, email: str, password: str, name: str, response: Response
    ) -> dict[str, Any]:
        existing = await self.db.collection("users").find_one({"email": email.lower()})
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered",
            )
        now = utc_now()
        user = {
            "_id": new_id("usr"),
            "email": email.lower(),
            "name": name.strip(),
            "password_hash": self.hash_password(password),
            "created_at": now,
            "updated_at": now,
        }
        await self.db.collection("users").insert_one(user)
        access_token, refresh_token = await self.create_session(user["_id"])
        self.set_refresh_cookie(response, refresh_token)
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": public_user(user),
        }

    async def login(
        self, email: str, password: str, response: Response
    ) -> dict[str, Any]:
        user = await self.db.collection("users").find_one({"email": email.lower()})
        if not user or not self.verify_password(password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        access_token, refresh_token = await self.create_session(user["_id"])
        self.set_refresh_cookie(response, refresh_token)
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": public_user(user),
        }

    async def create_session(self, user_id: str) -> tuple[str, str]:
        refresh_token = secrets.token_urlsafe(48)
        now = utc_now()
        session = {
            "_id": new_id("sess"),
            "user_id": user_id,
            "refresh_hash": self.hash_refresh_token(refresh_token),
            "created_at": now,
            "updated_at": now,
            "expires_at": now + timedelta(days=self.settings.refresh_token_days),
            "revoked": False,
        }
        await self.db.collection("sessions").insert_one(session)
        return self.create_access_token(user_id), refresh_token

    async def refresh(
        self, refresh_token: str | None, response: Response
    ) -> dict[str, Any]:
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token"
            )
        token_hash = self.hash_refresh_token(refresh_token)
        session = await self.db.collection("sessions").find_one(
            {"refresh_hash": token_hash, "revoked": False}
        )
        if not session or session["expires_at"] < utc_now():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            )
        user = await self.db.collection("users").find_one({"_id": session["user_id"]})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists"
            )
        # Atomically revoke the session — if another concurrent request already
        # revoked it, this update matches 0 documents and we bail out.
        revoke_result = await self.db.collection("sessions").update_one(
            {"_id": session["_id"], "revoked": False},
            {"$set": {"revoked": True, "updated_at": utc_now()}},
        )
        if revoke_result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token already used",
            )
        # Invalidate all existing access tokens by recording the rotation time
        await self.db.collection("users").update_one(
            {"_id": user["_id"]},
            {"$set": {"token_invalid_before": utc_now()}},
        )
        access_token, next_refresh = await self.create_session(user["_id"])
        self.set_refresh_cookie(response, next_refresh)
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": public_user(user),
        }

    async def logout(
        self, refresh_token: str | None, response: Response
    ) -> dict[str, bool]:
        if refresh_token:
            await self.db.collection("sessions").update_one(
                {"refresh_hash": self.hash_refresh_token(refresh_token)},
                {"$set": {"revoked": True, "updated_at": utc_now()}},
            )
        response.delete_cookie("refresh_token", path="/")
        return {"ok": True}

    def set_refresh_cookie(self, response: Response, token: str) -> None:
        response.set_cookie(
            "refresh_token",
            token,
            httponly=True,
            secure=self.settings.cookie_secure,
            samesite="lax",
            max_age=self.settings.refresh_token_days * 24 * 60 * 60,
            path="/",
        )
