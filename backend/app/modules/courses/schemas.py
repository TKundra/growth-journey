"""Course schemas: the admin authoring contract (also the ETL import shape) and
the learner-facing catalog / enrollment / certificate views.

Authoring is nested — a course is created with its modules and lessons in one
payload; `position` is derived from list order, not supplied. This same payload
is what an org-data ETL job will build and POST, so internal authoring and
import share one contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Level = Literal["beginner", "intermediate", "advanced"]

# ── admin authoring / ETL contract ─────────────────────────────────────────────
class LessonUpsertIn(BaseModel):
    title: str
    content: str = ""                                   # markdown body
    topics: list[str] = Field(default_factory=list)     # feeds study/quiz generation
    est_minutes: int | None = Field(default=None, ge=0)

class ModuleUpsertIn(BaseModel):
    title: str
    summary: str = ""
    lessons: list[LessonUpsertIn] = Field(default_factory=list)

class CourseUpsertIn(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1)
    subtitle: str = ""
    description: str = ""
    level: Level = "beginner"
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    emoji: str = "📘"
    est_minutes: int | None = Field(default=None, ge=0)
    is_published: bool = False
    # import provenance: set both for org-imported courses; leave null for internal
    source: Literal["internal", "import"] = "internal"
    external_ref: str | None = None
    modules: list[ModuleUpsertIn] = Field(default_factory=list)

# ── learner-facing output ──────────────────────────────────────────────────────
class LessonOut(BaseModel):
    public_id: UUID
    position: int
    title: str
    content: str = ""
    topics: list[str] = Field(default_factory=list)
    est_minutes: int | None = None
    is_completed: bool = False          # only meaningful when the user is enrolled

class ModuleOut(BaseModel):
    public_id: UUID
    position: int
    title: str
    summary: str = ""
    lessons: list[LessonOut] = Field(default_factory=list)

class CourseSummary(BaseModel):
    """Catalog card / list row — no module bodies."""
    public_id: UUID
    slug: str
    title: str
    subtitle: str = ""
    level: Level
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    emoji: str = "📘"
    est_minutes: int | None = None
    module_count: int = 0
    lesson_count: int = 0
    is_published: bool = True
    # per-user enrollment overlay (null/false when not enrolled)
    is_enrolled: bool = False
    progress: int = 0
    status: str | None = None

class CourseDetail(CourseSummary):
    """Full syllabus tree + the user's progress overlay."""
    description: str = ""
    modules: list[ModuleOut] = Field(default_factory=list)

class CertificateOut(BaseModel):
    public_id: UUID
    serial: str
    issued_at: datetime
    revoked_at: datetime | None = None
    course_title: str | None = None
    learner_name: str | None = None

class EnrollmentOut(BaseModel):
    public_id: UUID
    status: str
    progress: int
    enrolled_at: datetime
    completed_at: datetime | None = None
    course: CourseSummary
    certificate: CertificateOut | None = None

# ── topics for study/quiz linking ──────────────────────────────────────────────
class CourseTopicsOut(BaseModel):
    """Aggregated lesson topics for a course (or a single module), the override
    set fed into study-material / quiz generation."""
    course_id: UUID
    module_id: UUID | None = None
    topics: list[str] = Field(default_factory=list)
