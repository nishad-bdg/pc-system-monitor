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
    # Push presence to open dashboards immediately (Messenger-style online).
    await realtime.broadcast_presence(
        body.device_id, online=True, last_seen=seen, pc_name=body.pc_name
    )
    return {"status": "ok", "online": True, "last_seen": seen}


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
