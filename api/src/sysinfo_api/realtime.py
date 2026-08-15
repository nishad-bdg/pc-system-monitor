"""In-process WebSocket broadcaster + presence cache.

Holds the set of connected admin clients and lets handlers push
`report.created` / `presence.changed` events (with printers) to every open
socket. Because the app may run multiple uvicorn workers, this is best-effort
per-process; the dashboard also refetches on reconnect, so no event is
permanently lost in practice.

The presence cache mirrors the `machines` collection in memory so that:
  - a heartbeat flips a dot to green instantly (Messenger-style), and
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