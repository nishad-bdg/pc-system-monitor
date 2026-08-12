"""Agent command polling (remote speed tests, etc.)."""

from __future__ import annotations

import os

import requests

from .device import get_or_create_device_id, resolve_pc_name
from .network import run_full_speed_test

POLL_TIMEOUT = 8
COMPLETE_TIMEOUT = 15


def poll_and_run_commands(
    *,
    api_url: str,
    api_key: str,
    pc_name: str = "",
    quiet: bool = True,
) -> int:
    """Claim and execute pending commands for this device. Returns count handled."""
    if not api_key:
        return 0
    name = resolve_pc_name(pc_name)
    device_id = get_or_create_device_id(name)
    headers = {"Authorization": f"Bearer {api_key}"}
    base = api_url.rstrip("/")
    handled = 0

    # Process up to a few queued commands per poll.
    for _ in range(3):
        try:
            resp = requests.get(
                f"{base}/commands/pending",
                params={"device_id": device_id},
                headers=headers,
                timeout=POLL_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError, OSError) as exc:
            if not quiet or os.getenv("SYSTEM_INFO_DEBUG"):
                print(f"[commands] poll failed: {exc}")
            break

        command = payload.get("command") if isinstance(payload, dict) else None
        if not command:
            break

        command_id = command.get("_id")
        command_type = command.get("type")
        handled += 1
        if command_type == "speed_test":
            _run_speed_test(base, headers, command_id, quiet=quiet)
        else:
            _complete(
                base,
                headers,
                command_id,
                status="failed",
                error=f"unsupported command type: {command_type}",
                quiet=quiet,
            )

    return handled


def _run_speed_test(base: str, headers: dict, command_id: str, *, quiet: bool) -> None:
    if not quiet:
        print("[commands] running speed_test…")
    try:
        result = run_full_speed_test()
        _complete(
            base,
            headers,
            command_id,
            status="done",
            result=result,
            quiet=quiet,
        )
        if not quiet:
            print(
                f"[commands] speed_test done: "
                f"down={result.get('download_mbps')} "
                f"up={result.get('upload_mbps')}"
            )
    except Exception as exc:  # noqa: BLE001 — report failure to API
        _complete(
            base,
            headers,
            command_id,
            status="failed",
            error=str(exc),
            quiet=quiet,
        )


def _complete(
    base: str,
    headers: dict,
    command_id: str,
    *,
    status: str,
    result: dict | None = None,
    error: str | None = None,
    quiet: bool,
) -> None:
    try:
        requests.post(
            f"{base}/commands/{command_id}/complete",
            json={"status": status, "result": result, "error": error},
            headers=headers,
            timeout=COMPLETE_TIMEOUT,
        ).raise_for_status()
    except (requests.RequestException, OSError) as exc:
        if not quiet or os.getenv("SYSTEM_INFO_DEBUG"):
            print(f"[commands] complete failed: {exc}")
