"""Remote device commands (e.g. speed_test)."""

from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException

from .. import db
from ..security import ApiKey, CurrentUser

router = APIRouter(prefix="/commands", tags=["commands"])

ALLOWED_TYPES = {"speed_test"}


class CreateCommandBody(BaseModel):
    device_id: str = Field(min_length=1)
    type: str = "speed_test"


class CompleteCommandBody(BaseModel):
    status: str = Field(description="done | failed")
    result: dict | None = None
    error: str | None = None


@router.post("", status_code=201)
def create_command(body: CreateCommandBody, user: CurrentUser) -> dict:
    if body.type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported type: {body.type}")
    device_id = body.device_id.strip()
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id required")
    created_by = str(user.get("_id") or user.get("username") or "")
    doc = db.create_command(
        device_id=device_id,
        command_type=body.type,
        created_by=created_by,
    )
    if doc is None:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    return doc


@router.get("/pending")
def claim_pending(device_id: str, api_key: ApiKey) -> dict:
    """Agent: claim the next pending command for this device (or empty)."""
    device_id = (device_id or "").strip()
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id required")
    doc = db.claim_pending_command(device_id)
    return {"command": doc}


@router.post("/{command_id}/complete")
def complete_command(
    command_id: str,
    body: CompleteCommandBody,
    api_key: ApiKey,
) -> dict:
    if body.status not in {"done", "failed"}:
        raise HTTPException(status_code=400, detail="status must be done or failed")
    doc = db.complete_command(
        command_id,
        status=body.status,
        result=body.result,
        error=body.error,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Command not found or already finished")
    return doc


@router.get("/{command_id}")
def get_command(command_id: str, user: CurrentUser) -> dict:
    doc = db.get_command(command_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Command not found")
    return doc


@router.get("")
def list_commands(device_id: str, limit: int = 20, user: CurrentUser = None) -> dict:
    device_id = (device_id or "").strip()
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id required")
    records = db.list_commands(device_id, min(max(limit, 1), 100))
    return {"total": len(records), "commands": records}
