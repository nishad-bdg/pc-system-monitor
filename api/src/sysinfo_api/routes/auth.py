from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from .. import db, security

router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


@router.post("/token", response_model=security.TokenResponse)
def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> security.TokenResponse:
    user = db.find_user_by_username(form_data.username)
    if not user or not security.verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = security.create_access_token(str(user["_id"]), user["role"])
    return security.TokenResponse(access_token=token)


@router.get("/me")
def me(user: security.CurrentUser) -> dict:
    return user