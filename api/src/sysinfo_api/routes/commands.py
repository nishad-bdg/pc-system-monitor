"""Remote-command endpoints (WebSocket-push control of desktop agents).

Admins (JWT) enqueue a command (`restart` / `shutdown` / `update` / `collect`
/ `reconnect`) for a device. The command is persisted in Mongo and pushed
**immediately** to the desktop agent over its `/ws/agent` WebSocket channel;
the agent executes and acks (`done` / `failed`). When the agent is offline,
the command stays pending and is echoed back on the agent's next heartbeat
poll as a fallback.
"""

from fastapi import APIRouter, HTTPException

from .. import db, realtime, security
from ..models import CommandAck, CommandBroadcast, CommandCreate, DevicePing
from ..security import AdminOrSuperUser, ApiKey, CurrentUser, SuperAdminUser

router = APIRouter(prefix="/commands", tags=["commands"])

COMMAND_TYPES = {"restart", "shutdown", "update", "collect", "reconnect"}
ACK_STATUSES = {db.COMMAND_STATUS_DONE, db.COMMAND_STATUS_FAILED}


def _to_out(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "device_id": doc.get("device_id"),
        "type": doc.get("type"),
        "status": doc.get("status"),
        "requested_by": doc.get("requested_by"),
        "created_at": doc.get("created_at"),
        "acked_at": doc.get("acked_at"),
        "error": doc.get("error"),
    }


@router.post("", status_code=201)
async def create_command(
    body: CommandCreate, user: AdminOrSuperUser = CurrentUser
) -> dict:
    """Enqueue a remote command and push it to the agent (admin/super_admin only)."""
    device_id = (body.device_id or "").strip()
    command_type = (body.type or "").strip()
    if not device_id:
        raise HTTPException(status_code=422, detail="device_id is required")
    if command_type not in COMMAND_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported command type")
    command_id = db.create_command(device_id, command_type, user.get("_id", ""))
    if command_id is None:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    record = db.get_command(str(command_id))
    if record is None:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    # Push to any connected agent socket so the machine acts immediately.
    await realtime.push_command_to_agent(record)
    return _to_out(record)


@router.post("/ping")
async def ping_device(
    body: DevicePing, user: AdminOrSuperUser = CurrentUser
) -> dict:
    """Live-check whether the desktop agent is connected (admin/super_admin).

    Sends a ping over `/ws/agent` and waits briefly for pong. Does not enqueue
    a persistent command. Offline or silent agents return connected=false.
    """
    device_id = (body.device_id or "").strip()
    if not device_id:
        raise HTTPException(status_code=422, detail="device_id is required")
    return await realtime.ping_agent(device_id)


@router.post("/broadcast", status_code=201)
async def broadcast_command(
    body: CommandBroadcast, user: SuperAdminUser = CurrentUser
) -> dict:
    """Push a command to every currently-connected desktop agent (super_admin
    only) — used e.g. to force-update all running apps at once.

    Each connected device gets its own persisted command so acks are tracked
    per device; offline agents are skipped (no socket to push to) and can be
    targeted individually.
    """
    command_type = (body.type or "").strip()
    if not command_type:
        raise HTTPException(status_code=422, detail="type is required")
    if command_type not in COMMAND_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported command type")
    device_ids = realtime.connected_agent_device_ids()
    sent: list[dict] = []
    for device_id in device_ids:
        command_id = db.create_command(device_id, command_type, user.get("_id", ""))
        if command_id is None:
            continue
        record = db.get_command(str(command_id))
        if record is None:
            continue
        await realtime.push_command_to_agent(record)
        sent.append({
            "device_id": device_id,
            "command_id": str(command_id),
            "type": command_type,
        })
    return {"total": len(sent), "sent": sent, "connected": len(device_ids)}


@router.get("")
def list_commands(
    limit: int = 50,
    device_id: str | None = None,
    user: AdminOrSuperUser = CurrentUser,
) -> dict:
    """Recent commands (admin/super_admin). Newest first."""
    records = db.list_commands(
        min(max(limit, 1), 500),
        device_id=device_id or None,
    )
    return {"total": len(records), "commands": [_to_out(r) for r in records]}


@router.post("/{command_id}/ack")
def ack_command(command_id: str, body: CommandAck, api_key: ApiKey) -> dict:
    """Desktop agent reports a command as done/failed (API key auth)."""
    if body.status not in ACK_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid ack status")
    record = db.get_command(command_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Command not found")
    if record.get("status") != db.COMMAND_STATUS_PENDING:
        raise HTTPException(status_code=409, detail="Command already resolved")
    ok = db.ack_command(command_id, body.status, body.error)
    if not ok:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    updated = db.get_command(command_id)
    return _to_out(updated or record)