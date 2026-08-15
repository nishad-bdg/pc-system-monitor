from datetime import UTC, datetime

from pydantic import BaseModel

from fastapi import APIRouter, HTTPException

from .. import db, security

router = APIRouter(prefix="/groups", tags=["groups"])


class GroupCreate(BaseModel):
    name: str


class GroupUpdate(BaseModel):
    name: str | None = None
    machine_keys: list[str] | None = None


class GroupOut(BaseModel):
    id: str
    name: str
    machine_keys: list[str]
    subcategory_ids: list[str] = []
    created_at: float | None = None


def _to_out(doc: dict) -> dict:
    return {
        "id": doc["_id"],
        "name": doc["name"],
        "machine_keys": doc.get("machine_keys") or [],
        "subcategory_ids": doc.get("subcategory_ids") or [],
        "created_at": doc.get("created_at"),
    }


@router.get("", response_model=list[GroupOut])
def list_groups(user: security.CurrentUser) -> list[dict]:
    """All groups for admin/super_admin; only a user's assigned groups otherwise."""
    all_groups = [_to_out(d) for d in db.list_groups()]
    if user.get("role") == security.ROLE_USER:
        allowed = set(user.get("groups") or [])
        return [g for g in all_groups if g["id"] in allowed]
    return all_groups


@router.post("", status_code=201, response_model=GroupOut)
def create_group(payload: GroupCreate, user: security.AdminOrSuperUser) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Group name is required")
    group_id = db.create_group(name)
    if group_id is None:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    return _to_out({"_id": str(group_id), "name": name, "machine_keys": [], "created_at": datetime.now(UTC).timestamp()})


@router.patch("/{group_id}", response_model=GroupOut)
def update_group(
    group_id: str, payload: GroupUpdate, user: security.AdminOrSuperUser
) -> dict:
    name = payload.name.strip() if payload.name is not None else None
    if name == "":
        raise HTTPException(status_code=422, detail="Group name cannot be empty")

    if payload.machine_keys is not None:
        # A PC sits in exactly ONE bucket: its main group OR a sub-category.
        # Take the keys away from every other group AND every sub-category
        # before assigning them here.
        db.remove_machine_keys_from_groups(payload.machine_keys, except_group_id=group_id)
        db.remove_machine_keys_from_sub_categories(payload.machine_keys)

    if not db.update_group(group_id, name=name, machine_keys=payload.machine_keys):
        raise HTTPException(status_code=404, detail="Group not found")

    for g in db.list_groups():
        if g["_id"] == group_id:
            return _to_out(g)
    raise HTTPException(status_code=404, detail="Group not found")


@router.delete("/{group_id}", status_code=204)
def delete_group(group_id: str, user: security.AdminOrSuperUser) -> None:
    if db.delete_group(group_id):
        return None
    raise HTTPException(status_code=404, detail="Group not found")
