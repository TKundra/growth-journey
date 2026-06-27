"""Auth routes: signup, login, email verification, current user."""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.errors import UniqueViolation

from app.core.security import create_access_token, hash_password, verify_password
from app.db import get_conn
from app.modules.auth import repository as users_repo
from app.modules.auth.deps import get_current_user
from app.modules.auth.schemas import (
    LoginIn,
    SignupIn,
    SignupOut,
    TokenOut,
    UserOut,
    VerifyEmailIn,
)

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/signup", response_model=SignupOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, conn: psycopg.Connection = Depends(get_conn)) -> dict:
    email = body.email.lower()
    try:
        return users_repo.create_user(
            conn,
            email=email,
            password_hash=hash_password(body.password),
            full_name=body.full_name,
        )
    except UniqueViolation:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, conn: psycopg.Connection = Depends(get_conn)) -> dict:
    user = users_repo.get_by_email_with_hash(conn, body.email.lower())
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    token = create_access_token(str(user["public_id"]))
    return {"access_token": token, "token_type": "bearer"}

@router.post("/verify-email", response_model=UserOut)
def verify_email(body: VerifyEmailIn, conn: psycopg.Connection = Depends(get_conn)) -> dict:
    user = users_repo.verify_email(conn, str(body.token))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or already-used verification token",
        )
    return user

@router.get("/me", response_model=UserOut)
def me(current_user: dict = Depends(get_current_user)) -> dict:
    return current_user
