from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any


class PowerShellError(RuntimeError):
    pass


def _powershell_executable() -> str:
    for name in ("pwsh", "pwsh.exe", "powershell", "powershell.exe"):
        path = shutil.which(name)
        if path:
            return path
    raise PowerShellError("PowerShell executable not found")


def run_powershell_json(script: str, timeout_seconds: float = 15.0) -> Any:
    exe = _powershell_executable()
    try:
        completed = subprocess.run(
            [
                exe,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PowerShellError(
            f"PowerShell command timed out after {timeout_seconds}s"
        ) from exc
    if completed.returncode != 0:
        raise PowerShellError(completed.stderr.strip() or "PowerShell failed")
    try:
        return json.loads(completed.stdout.strip() or "null")
    except json.JSONDecodeError as exc:
        raise PowerShellError(f"Invalid JSON from PowerShell: {exc}") from exc


_ADAPTERS_SCRIPT = r"""
$adapters = Get-NetAdapter -ErrorAction Stop | Select-Object `
  Name, InterfaceDescription, ifIndex, InterfaceGuid, MacAddress, `
  PermanentAddress, Status, MediaType, LinkSpeed, HardwareInterface
$adapters | ConvertTo-Json -Compress -Depth 5
"""

_IP_SCRIPT = r"""
$configs = Get-NetIPConfiguration -ErrorAction Stop | Select-Object `
  InterfaceAlias, InterfaceIndex, IPv4Address, IPv6Address, `
  IPv4DefaultGateway, DNSServer
$configs | ConvertTo-Json -Compress -Depth 6
"""

_ROUTE_SCRIPT = r"""
$route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
  Sort-Object RouteMetric, InterfaceMetric |
  Select-Object -First 1 -Property InterfaceIndex, NextHop, RouteMetric
if ($null -eq $route) { 'null' } else { $route | ConvertTo-Json -Compress }
"""


def fetch_net_adapters(timeout_seconds: float = 15.0) -> list[dict[str, Any]]:
    data = run_powershell_json(_ADAPTERS_SCRIPT, timeout_seconds=timeout_seconds)
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    return list(data)


def fetch_net_ip_configuration(timeout_seconds: float = 15.0) -> list[dict[str, Any]]:
    data = run_powershell_json(_IP_SCRIPT, timeout_seconds=timeout_seconds)
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    return list(data)


def fetch_default_route_interface_index(timeout_seconds: float = 15.0) -> int | None:
    data = run_powershell_json(_ROUTE_SCRIPT, timeout_seconds=timeout_seconds)
    if not data:
        return None
    idx = data.get("InterfaceIndex")
    return int(idx) if idx is not None else None
