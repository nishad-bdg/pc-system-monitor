from pydantic import BaseModel

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .. import db, security

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "admin"


class UserOut(BaseModel):
    id: str
    username: str
    role: str


@router.get("", response_model=list[UserOut])
def list_users(user: security.CurrentUser) -> list:
    return [{"id": u["_id"], "username": u["username"], "role": u["role"]} for u in db.list_users()]


@router.post("", status_code=201)
def create_user(payload: UserCreate, user: security.CurrentUser) -> JSONResponse:
    if db.find_user_by_username(payload.username):
        raise HTTPException(status_code=409, detail="Username already exists")
    ok = db.create_user(payload.username, security.hash_password(payload.password), payload.role)
    if not ok:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    return JSONResponse(status_code=201, content={"username": payload.username, "role": payload.role})


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: str, user: security.CurrentUser) -> None:
    if db.delete_user(user_id):
        return None
    raise HTTPException(status_code=404, detail="User not found")