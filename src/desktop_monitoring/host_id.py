from __future__ import annotations


def build_host_id(
    hostname: str,
    machine_guid: str | None,
    primary_mac: str | None = None,
) -> str:
    """Build identity from hostname and machine GUID, never from MAC alone."""
    del primary_mac
    host_component = hostname.strip() or "unknown-host"
    guid_component = (machine_guid or "").strip() or "unknown-guid"
    return f"{host_component}|{guid_component}"
