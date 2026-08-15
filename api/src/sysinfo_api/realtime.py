"""In-process WebSocket broadcaster + presence cache.

Holds the set of connected admin clients and lets handlers push
`report.created` / `presence.changed` events (with printers) to every open
socket. Because the app may run multiple uvicorn workers, this is best-effort
per-process; the dashboard also refetches on reconnect, so no event is
permanently lost in practice.

The presence cache mirrors the `machines` collection in memory so that:
  - a connected `/ws/agent` socket (or heartbeat) flips a dot to green instantly, and
  - a freshly-connected dashboard receives the current online/offline map.
"""

from __future__ import annotations

import json
import time
from typing import Set

from starlette.websockets import WebSocket

_clients: Set[WebSocket] = set()

# device_id -> {"online": bool, "last_seen": float, "pc_name": str | None}
_presence: dict[str, dict] = {}

# device_id -> list of connected desktop-agent sockets (API-key authed /ws/agent).
# Commands (restart/shutdown) are pushed to these instantly.
_agent_clients: dict[str, list[WebSocket]] = {}


def connect_agent(device_id: str, ws: WebSocket) -> None:
    """Register a connected desktop agent socket for immediate command push."""
    sockets = _agent_clients.setdefault(device_id, [])
    if ws not in sockets:
        sockets.append(ws)


def disconnect_agent(device_id: str, ws: WebSocket) -> int:
    """Drop a desktop agent socket on disconnect/close.

    Returns the number of remaining sockets for this device (0 = last one).
    """
    sockets = _agent_clients.get(device_id)
    if not sockets:
        return 0
    try:
        sockets.remove(ws)
    except ValueError:
        pass
    if not sockets:
        _agent_clients.pop(device_id, None)
        return 0
    return len(sockets)


def agent_sockets(device_id: str) -> list[WebSocket]:
    """All currently-connected agent sockets for a device (best-effort)."""
    return list(_agent_clients.get(device_id) or [])


def connected_agent_device_ids() -> list[str]:
    """Every device_id with at least one live desktop-agent socket."""
    return [dev for dev, sockets in _agent_clients.items() if sockets]


async def push_command_to_agent(command: dict) -> None:
    """Push a command to every connected desktop agent of a device (if any).

    The agent executes immediately and acks; when offline it stays pending in
    Mongo and is picked up via the heartbeat poll instead.
    """
    payload = json.dumps(
        {
            "type": "command",
            "command": {
                "id": str(command.get("_id") or command.get("id") or ""),
                "device_id": command.get("device_id"),
                "type": command.get("type"),
                "status": command.get("status"),
                "created_at": command.get("created_at"),
            },
            "ts": time.time(),
        }
    )
    device_id = command.get("device_id")
    stale: list[WebSocket] = []
    for ws in list(_agent_clients.get(device_id) or []):
        try:
            await ws.send_text(payload)
        except Exception:
            stale.append(ws)
    for ws in stale:
        remaining = disconnect_agent(device_id, ws)
        if remaining == 0:
            await broadcast_presence(
                device_id, online=False, last_seen=time.time()
            )


def connect(ws: WebSocket) -> None:
    _clients.add(ws)


def disconnect(ws: WebSocket) -> None:
    _clients.discard(ws)


def presence_snapshot() -> list[dict]:
    """Current in-process presence for all known machines."""
    return [
        {
            "device_id": dev,
            "online": info.get("online", False),
            "last_seen": info.get("last_seen"),
            "pc_name": info.get("pc_name"),
        }
        for dev, info in _presence.items()
    ]


def update_presence(
    device_id: str,
    *,
    online: bool,
    last_seen: float,
    pc_name: str | None = None,
) -> None:
    """Update the in-process presence map and broadcast the change."""
    prev = _presence.get(device_id)
    if prev and prev.get("online") == online:
        # Already in this state; just refresh the seen time so no spam.
        prev["last_seen"] = last_seen
        if pc_name:
            prev["pc_name"] = pc_name
        return
    _presence[device_id] = {
        "online": online,
        "last_seen": last_seen,
        "pc_name": pc_name or (prev or {}).get("pc_name"),
    }


async def broadcast_presence(
    device_id: str,
    *,
    online: bool,
    last_seen: float,
    pc_name: str | None = None,
) -> None:
    """Broadcast a `presence.changed` event to every connected client."""
    update_presence(
        device_id, online=online, last_seen=last_seen, pc_name=pc_name
    )
    await _send({
        "type": "presence.changed",
        "presence": {
            "device_id": device_id,
            "online": online,
            "last_seen": last_seen,
            "pc_name": pc_name,
        },
        "ts": time.time(),
    })


async def broadcast(report: dict) -> None:
    await _send({
        "type": "report.created",
        "report": _strip_mongo_ids(report),
        "ts": time.time(),
    })


async def broadcast_print_job(job: dict) -> None:
    """Broadcast a `print.job` event so open dashboards show it live."""
    await _send({
        "type": "print.job",
        "job": _strip_mongo_ids(job),
        "ts": time.time(),
    })


async def _send(payload: dict) -> None:
    message = json.dumps(payload)
    stale: list[WebSocket] = []
    for ws in list(_clients):
        try:
            await ws.send_text(message)
        except Exception:
            stale.append(ws)
    for ws in stale:
        _clients.discard(ws)


def _strip_mongo_ids(report: dict) -> dict:
    out = dict(report)
    if "_id" in out:
        out["_id"] = str(out["_id"])
    return out