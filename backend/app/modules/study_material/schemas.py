"""Study-material schemas: generation request, the LLM curation contract, and
the API-facing resource / saved-resource / search shapes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

Difficulty = Literal["beginner", "intermediate", "advanced"]
Kind = Literal["article", "docs", "video", "course", "tutorial", "other"]

# ── generation request ───────────────────────────────────────────────────────
class GenerateIn(BaseModel):
    """Optional overrides; by default we use the user's preferences + profile."""
    topics: list[str] = Field(default_factory=list, description="Override preference topics")
    difficulty: Difficulty | None = None
    per_topic: int = Field(default=5, ge=1, le=10, description="Search results per topic")
    max_topics: int = Field(default=4, ge=1, le=8)

# ── LLM curation contract (what parse() validates into) ──────────────────────
class CuratedItem(BaseModel):
    url: str  # the only hard requirement — grounds the item to a real source
    title: str = ""
    # title/summary/topic are backfilled from the candidate if the model omits them,
    # so they carry defaults rather than being required (models are inconsistent).
    summary: str = Field(
        default="", description="1-2 sentences on why this resource is worth the learner's time"
    )
    topic: str = Field(default="", description="Which of the learner's topics this serves")
    tags: list[str] = Field(default_factory=list)
    difficulty: Difficulty = "beginner"
    kind: Kind = "article"
    est_minutes: int = Field(default=10, ge=1, le=600)
    relevance: int = Field(default=50, ge=0, le=100)

class Curation(BaseModel):
    items: list[CuratedItem] = Field(default_factory=list)

# ── API outputs ──────────────────────────────────────────────────────────────
class StudyResourceOut(BaseModel):
    public_id: UUID
    title: str
    url: str
    source_domain: str | None = None
    summary: str | None = None
    topic: str | None = None
    tags: list[str] = Field(default_factory=list)
    difficulty: str | None = None
    kind: str | None = None
    est_minutes: int | None = None
    relevance: int | None = None
    is_saved: bool = False
    created_at: datetime

class GenerateOut(BaseModel):
    generated: int
    resources: list[StudyResourceOut] = Field(default_factory=list)

class SaveIn(BaseModel):
    note: str | None = None

class SavedResourceOut(BaseModel):
    public_id: UUID  # the saved-row id
    note: str | None = None
    created_at: datetime
    resource: StudyResourceOut

class SemanticHit(BaseModel):
    score: float
    resource: StudyResourceOut
