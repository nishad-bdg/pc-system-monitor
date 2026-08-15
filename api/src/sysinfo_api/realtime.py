"""In-process WebSocket broadcaster.

Holds the set of connected admin clients and lets handlers push
`report.created` events (with printers) to every open socket. Because the
app may run multiple uvicorn workers, this is best-effort per-process;
the dashboard also refetches on reconnect, so no event is permanently
lost in practice.
"""

from __future__ import annotations

import json
import time
from typing import Set

from starlette.websockets import WebSocket

_clients: Set[WebSocket] = set()


def connect(ws: WebSocket) -> None:
    _clients.add(ws)


def disconnect(ws: WebSocket) -> None:
    _clients.discard(ws)


async def broadcast(report: dict) -> None:
    payload = {
        "type": "report.created",
        "report": _strip_mongo_ids(report),
        "ts": time.time(),
    }
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