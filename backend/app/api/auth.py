from fastapi import APIRouter, Depends, Request, Response

from app.api.dependencies import current_public_user, get_auth_service, refresh_cookie
from app.models import AuthResponse, LoginRequest, SignupRequest
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse)
async def signup(payload: SignupRequest, response: Response, auth: AuthService = Depends(get_auth_service)):
    return await auth.signup(payload.email, payload.password, payload.name, response)


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, response: Response, auth: AuthService = Depends(get_auth_service)):
    return await auth.login(payload.email, payload.password, response)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(request: Request, response: Response, auth: AuthService = Depends(get_auth_service)):
    return await auth.refresh(refresh_cookie(request), response)


@router.post("/logout")
async def logout(request: Request, response: Response, auth: AuthService = Depends(get_auth_service)):
    return await auth.logout(refresh_cookie(request), response)


@router.get("/me")
async def me(user: dict = Depends(current_public_user)):
    return user

