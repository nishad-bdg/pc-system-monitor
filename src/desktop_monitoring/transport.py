from __future__ import annotations

import json
import platform
import sys
from typing import Any, Protocol

from desktop_monitoring.network.models import Adapter
from desktop_monitoring.snapshot import build_snapshot, collect_snapshot


class Publisher(Protocol):
    def publish(self, snapshot: dict[str, Any]) -> None:
        """Publish one snapshot without removing previously published data."""


class StdoutPublisher:
    def publish(self, snapshot: dict[str, Any]) -> None:
        json.dump(snapshot, sys.stdout, indent=2)
        sys.stdout.write("\n")


class HttpPublisher:
    """Future HTTP transport; intentionally not implemented yet."""

    def __init__(self, url: str, token: str | None = None) -> None:
        self.url = url
        self.token = token

    def publish(self, snapshot: dict[str, Any]) -> None:
        raise NotImplementedError(
            "HttpPublisher will POST snapshot JSON when the API is added"
        )


def run_once(
    publisher: Publisher,
    hostname: str | None = None,
    machine_guid: str | None = None,
    adapters: list[Adapter] | None = None,
) -> dict[str, Any]:
    """Collect one snapshot and publish it, retaining all prior data."""
    if adapters is None:
        snapshot = collect_snapshot(hostname, machine_guid)
    else:
        snapshot = build_snapshot(
            hostname=hostname if hostname is not None else platform.node(),
            machine_guid=machine_guid,
            adapters=adapters,
        )
    publisher.publish(snapshot)
    return snapshot
