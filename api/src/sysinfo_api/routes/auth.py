from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from .. import db, security

router = APIRouter(prefix="/auth", tags=["auth"])


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/token", response_model=security.TokenResponse)
def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> security.TokenResponse:
    user = db.find_user_by_username(form_data.username)
    if not user or not security.verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return security.issue_tokens(str(user["_id"]), user["role"])


@router.post("/refresh", response_model=security.TokenResponse)
def refresh_tokens(payload: RefreshRequest) -> security.TokenResponse:
    """Exchange a still-valid refresh token for a new pair (rotation)."""
    token_hash = security.create_refresh_token_hash(payload.refresh_token)
    record = db.find_refresh_token(token_hash)
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if record.get("revoked"):
        raise HTTPException(status_code=401, detail="Refresh token revoked")
    expires_at = record.get("expires_at")
    if isinstance(expires_at, datetime):
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise HTTPException(status_code=401, detail="Refresh token expired")
    user_id = record.get("user_id") or ""
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    # Rotate: revoke this token, issue a fresh pair.
    db.revoke_refresh_token(token_hash)
    return security.issue_tokens(user_id, user["role"])


@router.post("/revoke")
def revoke(payload: RefreshRequest, user: security.CurrentUser) -> dict:
    """Revoke a refresh token (logged out in the dashboard)."""
    token_hash = security.create_refresh_token_hash(payload.refresh_token)
    db.revoke_refresh_token(token_hash)
    return {"status": "ok"}


@router.get("/me")
def me(user: security.CurrentUser) -> dict:
    return user


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest, user: security.CurrentUser
) -> dict:
    """Change the signed-in user's password. Revokes all refresh tokens."""
    current_hash = db.get_user_password_hash(str(user["_id"]))
    if not current_hash or not security.verify_password(payload.current_password, current_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=400, detail="New password must differ from the current password")
    user_id = str(user["_id"])
    if not db.update_user_password(user_id, security.hash_password(payload.new_password)):
        raise HTTPException(status_code=500, detail="Could not update password")
    db.revoke_all_refresh_tokens_for_user(user_id)
    return {"status": "ok"}