from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]


class SessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=160)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    session_id: str | None = None
    debug: bool = False


class FeedbackRequest(BaseModel):
    message_id: str
    session_id: str
    rating: float = Field(ge=0.0, le=1.0)
    comment: str | None = Field(default=None, max_length=2000)


class MessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime
    selected_arm: str | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    reward: float | None = None
    latency_ms: float | None = None
    reasoning_metadata: dict[str, Any] = Field(default_factory=dict)
    retrieval_diagnostics: dict[str, Any] = Field(default_factory=dict)

