"""FastAPI application entrypoint.

Feature routers (auth, study_material, assessments, ...) get included here as
each phase lands. Phase 0 wires only health checks so the skeleton is runnable.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health
from app.core.config import settings
from app.core.logging import configure_logging
from app.modules.assessments.router import router as assessments_router
from app.modules.auth.router import router as auth_router
from app.modules.preferences.router import router as preferences_router
from app.modules.study_material.router import router as study_material_router
from app.modules.users.router import router as users_router

configure_logging()

app = FastAPI(
    title="Student Journey API",
    version=__version__,
    debug=settings.app_debug,
)

# Permissive CORS for local dev; tighten per-environment in Phase 9.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(preferences_router)
app.include_router(study_material_router)
app.include_router(assessments_router)

@app.get("/")
def root() -> dict:
    return {"service": "student-journey", "docs": "/docs"}
