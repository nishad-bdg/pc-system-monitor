import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2PasswordBearer,
)
from pydantic import BaseModel

from . import config, db

API_KEY_PREFIX = "sk-"
SALT_ROUNDS = 12

bearer_scheme = HTTPBearer(auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# --- passwords ---


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=SALT_ROUNDS)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


# --- JWT ---


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=config.JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def create_refresh_token() -> str:
    """Generate an opaque refresh token (kept hashed at rest in Mongo)."""
    return secrets.token_urlsafe(48)


def create_refresh_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def refresh_expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=config.JWT_REFRESH_EXPIRE_DAYS)


def issue_tokens(user_id: str, role: str) -> TokenResponse:
    """Issue an access + refresh token pair, persisting the refresh token."""
    refresh = create_refresh_token()
    db.save_refresh_token(
        create_refresh_token_hash(refresh), user_id, refresh_expires_at()
    )
    return TokenResponse(
        access_token=create_access_token(user_id, role),
        refresh_token=refresh,
    )


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> dict:
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


CurrentUser = Annotated[dict, Depends(_get_current_user)]


# --- API keys (hashed with sha256, compared via token hash) ---


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def _require_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)]
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing API key")
    key = credentials.credentials
    if not key.startswith(API_KEY_PREFIX):
        raise HTTPException(status_code=401, detail="Invalid API key")
    record = db.find_api_key_by_hash(hash_api_key(key))
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    record["_id"] = str(record["_id"])
    record.pop("key_hash", None)
    return record


ApiKey = Annotated[dict, Security(_require_api_key)]