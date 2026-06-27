"""Structured-ish logging setup. Call configure_logging() once at startup."""

from __future__ import annotations

from app.core.config import settings

import logging

_CONFIGURED = False

def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = logging.DEBUG if settings.app_debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    )

    _CONFIGURED = True

def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
