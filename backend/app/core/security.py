"""Password hashing + JWT helpers.

Passwords use bcrypt directly (no passlib — it's unmaintained and breaks with
bcrypt 4.x). Access tokens are HS256 JWTs signed with ``app_secret_key``; the
token subject (``sub``) is the user's ``public_id``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt

import bcrypt

from app.core.config import settings

# bcrypt only ever uses the first 72 bytes of the password; longer inputs raise
# in bcrypt 4.x. Truncate consistently (hash + verify) so behavior is well-defined.
_BCRYPT_MAX_BYTES = 72

# ── passwords ────────────────────────────────────────────────────────────────
def _prepare(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_prepare(plain), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(_prepare(plain), hashed.encode("utf-8"))

# ── tokens ───────────────────────────────────────────────────────────────────
def create_access_token(subject: str, *, expires_minutes: int | None = None) -> str:
    minutes = expires_minutes or settings.access_token_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.app_secret_key, algorithm=settings.jwt_algorithm)

def decode_access_token(token: str) -> str | None:
    """Return the token subject (user public_id) or None if invalid/expired."""
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    return payload.get("sub")
