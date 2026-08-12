from __future__ import annotations

import copy
import platform
from typing import Any

from desktop_monitoring.host_id import build_host_id
from desktop_monitoring.network.collector import (
    build_network_payload,
    collect_network,
)
from desktop_monitoring.network.models import Adapter


def _ensure_mac_contract(network: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(network)
    payload.setdefault("primary_mac_address", None)

    preferred = payload.setdefault("preferred_adapter", {})
    preferred.setdefault("current_mac_address", None)
    preferred.setdefault("permanent_mac_address", None)

    for collection_name in ("active_adapters", "all_adapters"):
        for adapter in payload.setdefault(collection_name, []):
            adapter.setdefault("current_mac_address", None)
            adapter.setdefault("permanent_mac_address", None)
    return payload


def build_snapshot(
    hostname: str,
    machine_guid: str | None,
    adapters: list[Adapter] | None = None,
    network: dict[str, Any] | None = None,
) -> dict[str, Any]:
    network_payload = (
        network
        if network is not None
        else build_network_payload(adapters or [])
    )
    network_payload = _ensure_mac_contract(network_payload)
    return {
        "host_id": build_host_id(
            hostname=hostname,
            machine_guid=machine_guid,
            primary_mac=network_payload["primary_mac_address"],
        ),
        "network": network_payload,
    }


def collect_snapshot(
    hostname: str | None = None,
    machine_guid: str | None = None,
) -> dict[str, Any]:
    return build_snapshot(
        hostname=hostname if hostname is not None else platform.node(),
        machine_guid=machine_guid,
        network=collect_network(),
    )
