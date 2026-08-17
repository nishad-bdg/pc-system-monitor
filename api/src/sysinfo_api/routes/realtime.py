import json
import time

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.params import Query

from .. import config, db, realtime, security
from ..models import Heartbeat

router = APIRouter(tags=["realtime"])


def _is_online(last_seen: float | None) -> bool:
    if last_seen is None:
        return False
    return (time.time() - last_seen) <= config.ONLINE_TIMEOUT_SECONDS


def annotate_online(report: dict, seen_map: dict[str, float] | None = None) -> dict:
    """Add `online` (bool) + `last_seen` to a report based on its device."""
    device = report.get("device_id")
    if not device:
        report["online"] = False
        report["last_seen"] = report.get("created_at")
        return report
    seen = (seen_map or {}).get(device)
    if seen is None and seen_map is None:
        seen = db.get_machine_seen_at(device)
    report["online"] = _is_online(seen)
    report["last_seen"] = seen or report.get("created_at")
    return report


@router.post("/heartbeat")
async def heartbeat(body: Heartbeat, api_key: security.ApiKey) -> dict:
    """Record that a desktop machine is alive (called ~every minute)."""
    seen = time.time()
    ok = db.touch_machine(body.device_id, body.pc_name or None, seen_at=seen)
    if not ok:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    # A key linked to a group auto-assigns the PC to that group (one bucket).
    group_id = api_key.get("group_id")
    if group_id:
        keys = [f"id:{body.device_id}"]
        if body.pc_name:
            keys.append(f"name:{body.pc_name}")
        db.assign_machine_keys_to_group(group_id, keys)
    # Push presence to open dashboards immediately (Messenger-style online).
    await realtime.broadcast_presence(
        body.device_id, online=True, last_seen=seen, pc_name=body.pc_name
    )
    pending = db.list_pending_commands(body.device_id)
    return {
        "status": "ok",
        "online": True,
        "last_seen": seen,
        "commands": [
            {"id": str(c["_id"]), "type": c.get("type"), "device_id": body.device_id}
            for c in pending
        ],
    }


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(default="")):
    """Realtime push channel for the admin dashboard.

    Auth: JWT passed either as a `token` query param or as the WebSocket
    subprotocol (browsers can't set WS headers; we swallow the token so it
    never hits the URL/logs). The user must have admin/super_admin role.
    Origin must match CORS_ORIGINS to prevent cross-site WS hijacking.
    """
    subprotocol = ws.headers.get("sec-websocket-protocol") or ""
    offered = [p.strip() for p in subprotocol.split(",") if p.strip()]
    ws_token = offered[0] if offered else None
    token = token or ws_token or ""

    allowed_origin = not _client_origins(ws) or any(
        o in _origins for o in _client_origins(ws)
    )
    if not allowed_origin:
        await ws.close(code=4008)  # origin not allowed
        return

    user = _authorize(token)
    if user is None or user.get("role") not in security.PROTECTED_ROUTES_ROLES:
        await ws.close(code=4001)  # unauthorized
        return

    await ws.accept(subprotocol=ws_token)
    realtime.connect(ws)
    try:
        await ws.send_json({"type": "hello", "role": user.get("role")})
        # Seed the client with the current presence map so dots are right
        # immediately (no waiting for the first report event).
        for entry in realtime.presence_snapshot():
            await ws.send_json({"type": "presence.changed", "presence": entry})
        while True:
            # We only broadcast server->client; wait for a (silent) client ping.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        realtime.disconnect(ws)


_origins: list[str] = [o.strip() for o in config.CORS_ORIGINS.split(",") if o.strip()]


def _client_origins(ws: WebSocket) -> list[str]:
    origin = ws.headers.get("origin")
    if not origin:
        return []
    return [origin]


def _authorize(token: str) -> dict | None:
    if not token:
        return None
    try:
        payload = security.decode_access_token(token)
    except Exception:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return db.get_user_by_id(user_id)


def _agent_token(ws: WebSocket) -> str:
    """API key supplied as the WS subprotocol (browsers/agents can't set headers)."""
    subprotocol = ws.headers.get("sec-websocket-protocol") or ""
    offered = [p.strip() for p in subprotocol.split(",") if p.strip()]
    return offered[0] if offered else ""


@router.websocket("/ws/agent")
async def websocket_agent_endpoint(ws: WebSocket, token: str = Query(default="")):
    """Realtime command channel for desktop agents.

    Auth: API key passed either as `?key=`/`?token=` query or as the WS
    subprotocol (Python ws clients can set protocol headers). The first
    message must be a JSON `{"type": "hello", "device_id": "...", ...}` that
    registers the socket; afterwards the server pushes `{"type":"command", ...}`
    instantly and the agent replies with `{"type":"command.ack", ...}`. The
    agent also sends `{"type":"metrics", ...}` samples (live CPU/RAM/network
    plus top processes) which are broadcast to dashboards and not stored.
    """
    key = token or _agent_token(ws)
    record = db.find_api_key_by_hash(security.hash_api_key(key)) if key else None
    if record is None:
        await ws.close(code=4001)  # unauthorized
        return
    await ws.accept(subprotocol=_agent_token(ws) or None)
    device_id: str | None = None
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                continue
            msg_type = (msg or {}).get("type")
            if msg_type == "hello" and device_id is None:
                device_id = str(msg.get("device_id") or "").strip()
                if device_id:
                    realtime.connect_agent(device_id, ws)
                    pc_name = str(msg.get("pc_name") or "").strip() or None
                    seen = time.time()
                    db.touch_machine(device_id, pc_name, seen_at=seen)
                    # Watcher is connected: dashboards must show online now,
                    # not after the next heartbeat.
                    await realtime.broadcast_presence(
                        device_id, online=True, last_seen=seen, pc_name=pc_name
                    )
                    # Re-send any still-pending commands so nothing is lost
                    # between the last heartbeat poll and this connection.
                    for cmd in db.list_pending_commands(device_id):
                        await ws.send_json({
                            "type": "command",
                            "command": _to_command_doc(cmd),
                            "ts": time.time(),
                        })
                continue
            if msg_type == "command.ack" and device_id:
                command_id = str((msg or {}).get("command_id") or "").strip()
                status = str((msg or {}).get("status") or "failed").strip()
                error = (msg or {}).get("error")
                if command_id and status in (db.COMMAND_STATUS_DONE, db.COMMAND_STATUS_FAILED):
                    db.ack_command(command_id, status, error)
                continue
            if msg_type == "pong":
                realtime.resolve_pong(str((msg or {}).get("ping_id") or ""))
                continue
            if msg_type == "metrics" and device_id:
                sample = dict(msg or {})
                sample["device_id"] = device_id
                await realtime.broadcast_metrics(sample)
                continue
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if device_id:
            remaining = realtime.disconnect_agent(device_id, ws)
            if remaining == 0:
                await realtime.broadcast_presence(
                    device_id, online=False, last_seen=time.time()
                )


def _to_command_doc(cmd: dict) -> dict:
    return {
        "id": str(cmd["_id"]),
        "device_id": cmd.get("device_id"),
        "type": cmd.get("type"),
        "status": cmd.get("status"),
        "created_at": cmd.get("created_at"),
    }
