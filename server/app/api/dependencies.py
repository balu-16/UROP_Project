from fastapi import Depends, Header, HTTPException, Request, status

from app.config import Settings, get_settings
from app.database import AppDatabase, get_database
from app.services.auth import AuthService, public_user


def get_db() -> AppDatabase:
    return get_database()


def get_auth_service(
    db: AppDatabase = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    return AuthService(db, settings)


async def current_user(
    authorization: str | None = Header(default=None),
    auth: AuthService = Depends(get_auth_service),
) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token"
        )
    token = authorization.split(" ", 1)[1]
    return await auth.validate_access_token(token)


async def current_public_user(user: dict = Depends(current_user)) -> dict:
    return public_user(user)


def refresh_cookie(request: Request) -> str | None:
    return request.cookies.get("refresh_token")


def app_state(request: Request):
    return request.app.state
