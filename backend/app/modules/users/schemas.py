"""Profile schemas. The profile body is a discriminated union on ``user_type``
so professional vs student validate against their own fields."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union
from uuid import UUID
from pydantic import BaseModel, Field

from app.modules.auth.schemas import UserOut

# ── inputs (PUT /users/me/profile) ───────────────────────────────────────────
class ProfessionalProfileIn(BaseModel):
    user_type: Literal["professional"]
    experience_years: int | None = Field(default=None, ge=0, le=80)
    role: str | None = None
    industry: str | None = None
    skills: list[str] = Field(default_factory=list)
    goal: str | None = None

class StudentProfileIn(BaseModel):
    user_type: Literal["student"]
    education_level: str | None = None
    stream: str | None = None
    subjects: list[str] = Field(default_factory=list)
    target_exams: list[str] = Field(default_factory=list)
    preferred_colleges: list[str] = Field(default_factory=list)
    # Level-specific scalars (e.g. degree, current_year, specialization,
    # knowledge_level). Shape depends on education_level — see 0008 migration.
    details: dict[str, str] = Field(default_factory=dict)

ProfileIn = Annotated[
    Union[ProfessionalProfileIn, StudentProfileIn],
    Field(discriminator="user_type"),
]

# ── outputs ──────────────────────────────────────────────────────────────────
class ProfessionalProfileOut(BaseModel):
    public_id: UUID
    experience_years: int | None = None
    role: str | None = None
    industry: str | None = None
    skills: list[str] = Field(default_factory=list)
    goal: str | None = None
    updated_at: datetime

class StudentProfileOut(BaseModel):
    public_id: UUID
    education_level: str | None = None
    stream: str | None = None
    subjects: list[str] = Field(default_factory=list)
    target_exams: list[str] = Field(default_factory=list)
    preferred_colleges: list[str] = Field(default_factory=list)
    details: dict[str, str] = Field(default_factory=dict)
    updated_at: datetime

class PreferencesOut(BaseModel):
    public_id: UUID
    topics: list[str] = Field(default_factory=list)
    goal: str | None = None
    cadence: str
    difficulty: str | None = None
    notifications_enabled: bool
    updated_at: datetime

class ProfileAggregateOut(BaseModel):
    """Everything a dashboard needs in one call: user + profile + preferences."""
    user: UserOut
    profile: Union[ProfessionalProfileOut, StudentProfileOut, None] = None
    preferences: PreferencesOut | None = None
