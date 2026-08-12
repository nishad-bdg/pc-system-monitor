"""Collect installed printers and classify USB / network / other.

macOS uses CUPS (`lpstat`); Windows uses PowerShell `Get-Printer`.
No extra dependencies beyond the stdlib.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field


_NETWORK_HINTS = (
    "ipp://",
    "ipps://",
    "socket://",
    "http://",
    "https://",
    "smb://",
    "lpd://",
    "dnssd://",
    "wsd",
    "tcp://",
    "ip_",
    "network",
)


@dataclass
class Printer:
    name: str
    port: str
    connection: str  # usb | network | other

    def to_dict(self) -> dict:
        return {"name": self.name, "port": self.port}


@dataclass
class PrinterInfo:
    usb: list[Printer] = field(default_factory=list)
    network: list[Printer] = field(default_factory=list)
    other: list[Printer] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.usb) + len(self.network) + len(self.other)

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "usb": [p.to_dict() for p in self.usb],
            "network": [p.to_dict() for p in self.network],
            "other": [p.to_dict() for p in self.other],
        }


def classify_connection(port: str) -> str:
    """Map a device URI / Windows port name to usb | network | other."""
    value = (port or "").strip().lower()
    if not value:
        return "other"
    if "usb" in value:
        return "usb"
    if any(hint in value for hint in _NETWORK_HINTS):
        return "network"
    # Windows often uses bare hostnames or host:port for TCP printers.
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}(:\d+)?$", value):
        return "network"
    if re.match(r"^[a-z0-9._-]+.\w+:\d+$", value):
        return "network"
    return "other"


def _run(cmd: list[str], timeout: float = 8.0) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout or ""


def _collect_macos() -> list[Printer]:
    # `lpstat -v` → "device for Name: uri"
    raw = _run(["lpstat", "-v"])
    printers: list[Printer] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.lower().startswith("device for "):
            continue
        body = line[len("device for ") :]
        if ":" not in body:
            continue
        name, port = body.split(":", 1)
        name = name.strip()
        port = port.strip()
        if not name:
            continue
        printers.append(
            Printer(name=name, port=port, connection=classify_connection(port))
        )
    return printers


def _collect_windows() -> list[Printer]:
    # Prefer PowerShell Get-Printer for Name + PortName.
    script = (
        "Get-Printer | Select-Object Name, PortName | "
        "ConvertTo-Json -Compress"
    )
    raw = _run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        timeout=15.0,
    )
    if not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except ValueError:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []

    printers: list[Printer] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or "").strip()
        port = str(item.get("PortName") or "").strip()
        if not name:
            continue
        printers.append(
            Printer(name=name, port=port, connection=classify_connection(port))
        )
    return printers


def collect_printers() -> PrinterInfo:
    """List printers on this machine, grouped by connection type."""
    if os.name == "nt":
        items = _collect_windows()
    else:
        items = _collect_macos()

    info = PrinterInfo()
    for printer in sorted(items, key=lambda p: p.name.lower()):
        if printer.connection == "usb":
            info.usb.append(printer)
        elif printer.connection == "network":
            info.network.append(printer)
        else:
            info.other.append(printer)
    return info
