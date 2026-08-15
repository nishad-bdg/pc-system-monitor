from datetime import UTC, datetime

from pydantic import BaseModel

from fastapi import APIRouter, HTTPException

from .. import db, security

router = APIRouter(prefix="/sub-categories", tags=["sub-categories"])


class SubCategoryCreate(BaseModel):
    name: str
    group_ids: list[str] = []


class SubCategoryUpdate(BaseModel):
    name: str | None = None
    group_ids: list[str] | None = None
    machine_keys: list[str] | None = None


class SubCategoryOut(BaseModel):
    id: str
    name: str
    group_ids: list[str]
    machine_keys: list[str]
    created_at: float | None = None


def _to_out(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "group_ids": doc.get("group_ids") or [],
        "machine_keys": doc.get("machine_keys") or [],
        "created_at": doc.get("created_at"),
    }


def _user_visible_sub_categories(user: dict) -> list[dict]:
    """Sub-categories the caller may see.

    Admin/super_admin: all. `user`: only those linked to at least one of the
    user's assigned groups.
    """
    all_subs = [_to_out(d) for d in db.list_sub_categories()]
    if user.get("role") == security.ROLE_USER:
        allowed = set(user.get("groups") or [])
        return [s for s in all_subs if set(s["group_ids"]) & allowed]
    return all_subs


@router.get("", response_model=list[SubCategoryOut])
def list_sub_categories(user: security.CurrentUser) -> list[dict]:
    return _user_visible_sub_categories(user)


@router.post("", status_code=201, response_model=SubCategoryOut)
def create_sub_category(payload: SubCategoryCreate, user: security.AdminOrSuperUser) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Sub-category name is required")
    sub_id = db.create_sub_category(name, group_ids=payload.group_ids)
    if sub_id is None:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    group_ids = [g for g in payload.group_ids if g in {g["_id"] for g in db.list_groups()}]
    return _to_out(
        {
            "_id": str(sub_id),
            "name": name,
            "group_ids": group_ids,
            "machine_keys": [],
            "created_at": datetime.now(UTC).timestamp(),
        }
    )


@router.patch("/{sub_id}", response_model=SubCategoryOut)
def update_sub_category(
    sub_id: str, payload: SubCategoryUpdate, user: security.AdminOrSuperUser
) -> dict:
    name = payload.name.strip() if payload.name is not None else None
    if name == "":
        raise HTTPException(status_code=422, detail="Sub-category name cannot be empty")

    if payload.machine_keys is not None:
        # One bucket per PC: taking keys here removes them from every group AND
        # every other sub-category.
        db.remove_machine_keys_from_groups(payload.machine_keys)
        db.remove_machine_keys_from_sub_categories(payload.machine_keys, except_sub_id=sub_id)

    if not db.update_sub_category(
        sub_id, name=name, group_ids=payload.group_ids, machine_keys=payload.machine_keys
    ):
        raise HTTPException(status_code=404, detail="Sub-category not found")

    sub = db.get_sub_category(sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Sub-category not found")
    return _to_out(sub)


@router.delete("/{sub_id}", status_code=204)
def delete_sub_category(sub_id: str, user: security.AdminOrSuperUser) -> None:
    if db.delete_sub_category(sub_id):
        return None
    raise HTTPException(status_code=404, detail="Sub-category not found")