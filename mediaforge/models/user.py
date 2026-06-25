from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class User(BaseModel):
    user_id: UUID
    tenant_id: UUID
    email: str
    display_name: str | None = None
    email_verified_at: datetime | None = None
    status: str = "active"
    created_at: datetime | None = None


class UserPublic(BaseModel):
    """Shape exposed via API responses (never leaks password hash)."""

    user_id: UUID
    tenant_id: UUID
    email: str
    display_name: str | None = None
    status: str = "active"


def _normalize_email(v: str) -> str:
    if not v:
        raise ValueError("email is required")
    return v.strip().lower()


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)

    _normalize = field_validator("email", mode="before")(_normalize_email)


class UserSignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str | None = None

    _normalize = field_validator("email", mode="before")(_normalize_email)
