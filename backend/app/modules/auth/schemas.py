"""Auth request/response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class VerifyEmailIn(BaseModel):
    token: UUID

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserOut(BaseModel):
    public_id: UUID
    email: EmailStr
    full_name: str | None = None
    user_type: str | None = None
    is_email_verified: bool
    created_at: datetime

class SignupOut(UserOut):
    # Surfaced only until the email engine (Phase 5) sends it for real.
    email_verification_token: UUID | None = None
