"""Preferences schemas (learning topics, goal, cadence, notifications)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Re-export the output shape so it lives next to its input.
from app.modules.users.schemas import PreferencesOut  # noqa: F401

class PreferencesIn(BaseModel):
    topics: list[str] = Field(default_factory=list)
    goal: str | None = None
    cadence: Literal["none", "daily", "weekly"] = "none"
    difficulty: Literal["beginner", "intermediate", "advanced"] | None = None
    notifications_enabled: bool = True
