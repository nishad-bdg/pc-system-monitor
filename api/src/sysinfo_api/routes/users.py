from pydantic import BaseModel, field_validator

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .. import db, security

router = APIRouter(prefix="/users", tags=["users"])

VALID_ROLES = (
    security.ROLE_SUPER_ADMIN,
    security.ROLE_ADMIN,
    security.ROLE_USER,
)


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = security.ROLE_USER
    groups: list[str] = []

    @field_validator("role")
    @classmethod
    def check_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"Role must be one of {', '.join(VALID_ROLES)}")
        return v

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        name = v.strip()
        if not name:
            raise ValueError("Username is required")
        return name


class UserUpdate(BaseModel):
    role: str | None = None
    groups: list[str] | None = None
    password: str | None = None

    @field_validator("role")
    @classmethod
    def check_role(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_ROLES:
            raise ValueError(f"Role must be one of {', '.join(VALID_ROLES)}")
        return v


class UserOut(BaseModel):
    id: str
    username: str
    role: str
    groups: list[str]


def _to_out(doc: dict) -> dict:
    return {
        "id": doc["_id"],
        "username": doc["username"],
        "role": doc.get("role") or security.ROLE_USER,
        "groups": doc.get("groups") or [],
    }


@router.get("", response_model=list[UserOut])
def list_users(user: security.SuperAdminUser) -> list[dict]:
    return [_to_out(d) for d in db.list_users()]


@router.post("", status_code=201, response_model=UserOut)
def create_user(
    payload: UserCreate, user: security.SuperAdminUser
) -> dict:
    if db.find_user_by_username(payload.username):
        raise HTTPException(status_code=409, detail="Username already exists")
    # Only a super admin can create another super admin; group-less non-super
    # users would be able to see nothing, which is fine.
    ok = db.create_user(
        payload.username,
        security.hash_password(payload.password),
        payload.role,
        payload.groups,
    )
    if not ok:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    doc = db.find_user_by_username(payload.username)
    return _to_out(doc)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str, payload: UserUpdate, user: security.SuperAdminUser
) -> dict:
    current = db.get_user_by_id(user_id)
    if current is None:
        raise HTTPException(status_code=404, detail="User not found")

    if str(current["_id"]) == str(user["_id"]) and (
        payload.role not in (None, current.get("role"))
    ):
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    if not db.update_user(
        user_id,
        role=payload.role,
        groups=payload.groups,
        password_hash=(
            security.hash_password(payload.password) if payload.password else None
        ),
    ):
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    updated = db.get_user_by_id(user_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_out(updated)


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: str, user: security.SuperAdminUser) -> None:
    if str(user_id) == str(user["_id"]):
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    if db.delete_user(user_id):
        return None
    raise HTTPException(status_code=404, detail="User not found")