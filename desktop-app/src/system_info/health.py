"""Collect storage (SSD/HDD) and battery health (macOS + Windows).

Windows:
  - Disks:  `Get-PhysicalDisk` (FriendlyName, MediaType, HealthStatus)
  - Battery: `root/WMI` BatteryFullChargedCapacity vs BatteryStaticData
             (DesignedCapacity) -> health %, plus cycle count when exposed.

macOS:
  - Disks:  `system_profiler SPStorageDataType` physical_drive entries
             (medium_type ssd/hdd, smart_status)
  - Battery: `system_profiler SPPowerDataType` health info
             (cycle_count, health, maximum_capacity)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field


@dataclass
class DiskHealth:
    name: str
    device: str = ""
    media_type: str = "unknown"  # ssd | hdd | unknown
    brand: str | None = None  # vendor of the physical drive
    smart_status: str | None = None  # Verified | Not Supported | Failing | ...
    internal: bool | None = None
    health: str = "unknown"  # ok | warning | fail | unknown
    size_bytes: int | None = None  # total capacity of the physical disk

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "device": self.device,
            "media_type": self.media_type,
            "brand": self.brand,
            "smart_status": self.smart_status,
            "internal": self.internal,
            "health": self.health,
            "size_bytes": self.size_bytes,
        }


@dataclass
class BatteryHealth:
    cycle_count: int | None = None
    condition: str | None = None
    max_capacity_percent: int | None = None
    health_percent: int | None = None

    def to_dict(self) -> dict:
        return {
            "cycle_count": self.cycle_count,
            "condition": self.condition,
            "max_capacity_percent": self.max_capacity_percent,
            "health_percent": self.health_percent,
        }


@dataclass
class HealthInfo:
    disks: list[DiskHealth] = field(default_factory=list)
    battery: BatteryHealth | None = None

    def to_dict(self) -> dict:
        return {
            "disks": [d.to_dict() for d in self.disks],
            "battery": self.battery.to_dict() if self.battery else None,
        }


def _run(cmd: list[str], timeout: float = 15.0) -> str:
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


def _to_media_type(value: str | None) -> str:
    if not value:
        return "unknown"
    lowered = value.lower()
    if "ssd" in lowered or "solid state" in lowered or "non-rotational" in lowered:
        return "ssd"
    if "hdd" in lowered or "rotat" in lowered or "hard disk" in lowered:
        return "hdd"
    return "unknown"


def _derive_health(smart: str | None) -> str:
    if not smart:
        return "unknown"
    lowered = smart.lower()
    if "fail" in lowered:
        return "fail"
    if "verified" in lowered or "passed" in lowered or "ok" == lowered:
        return "ok"
    if "not supported" in lowered or "unsupported" in lowered:
        return "unknown"
    return "unknown"


def _extract_brand(name: str, manufacturer: str | None = None) -> str | None:
    """Best-effort vendor from a device name / manufacturer.

    Windows Get-PhysicalDisk exposes a Manufacturer (e.g. "Samsung"),
    while macOS device names embed the brand ("APPLE SSD AP0256Z" -> APPLE).
    """
    if manufacturer:
        brand = str(manufacturer).strip()
        if brand and brand.lower() not in ("unknown", "(unknown)"):
            return brand
    tokens = [t for t in name.split() if t]
    if not tokens:
        return None
    lowered = name.lower()
    # Skip words that look like the drive model, keep the leading vendor token.
    if any(kw in lowered for kw in (" ssd ", "ssd ", " hdd ", "hdd ", " solid ", " hard ")):
        vendor = tokens[0]
        return vendor if vendor else None
    # Apple drives: "APPLE SSD AP0256Z", "APPLE HDD HTS.." -> APPLE
    if lowered.startswith("apple"):
        return "Apple"
    return tokens[0]


# ---- Windows ----

def _collect_windows_disks() -> list[DiskHealth]:
    script = (
        "Get-PhysicalDisk -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName, DeviceId, MediaType, HealthStatus, "
        "BusType, Manufacturer, Size | ConvertTo-Json -Compress"
    )
    raw = _run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
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

    disks: list[DiskHealth] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("FriendlyName") or "").strip()
        if not name:
            continue
        media_type = str(item.get("MediaType") or "")
        health_raw = str(item.get("HealthStatus") or "")
        health = (
            "ok"
            if health_raw.lower() in ("healthy", "ok")
            else "fail"
            if health_raw.lower() in ("unhealthy", "failed", "failing")
            else "warning"
            if health_raw.lower() in ("warning", "warning (repair)" )
            else "unknown"
        )
        try:
            size_bytes = int(item.get("Size")) if item.get("Size") is not None else None
        except (TypeError, ValueError):
            size_bytes = None
        disks.append(
            DiskHealth(
                name=name,
                device=str(item.get("DeviceId") or ""),
                media_type=_to_media_type(media_type),
                brand=_extract_brand(name, str(item.get("Manufacturer") or "") or None),
                smart_status=None,
                internal=str(item.get("BusType") or "").lower() not in ("usb", "sas"),
                health=health,
                size_bytes=size_bytes,
            )
        )
    return disks


def _collect_windows_battery() -> BatteryHealth | None:
    script = (
        "$cap = Get-CimInstance -Namespace root/WMI -ClassName "
        "BatteryFullChargedCapacity -ErrorAction SilentlyContinue; "
        "$stat = Get-CimInstance -Namespace root/WMI -ClassName "
        "BatteryStaticData -ErrorAction SilentlyContinue; "
        "$cyc = Get-CimInstance -Namespace root/WMI -ClassName "
        "BatteryCycleCount -ErrorAction SilentlyContinue; "
        "[pscustomobject]@{ "
        "FullChargedCapacity = $cap.FullChargedCapacity; "
        "DesignedCapacity = $stat.DesignedCapacity; "
        "CycleCount = $cyc.CycleCount } | ConvertTo-Json -Compress"
    )
    raw = _run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        timeout=15.0,
    )
    if not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None

    full = payload.get("FullChargedCapacity")
    designed = payload.get("DesignedCapacity")
    try:
        full_int = int(full) if full is not None else None
    except (TypeError, ValueError):
        full_int = None
    try:
        designed_int = int(designed) if designed is not None else None
    except (TypeError, ValueError):
        designed_int = None

    health_percent = None
    if full_int is not None and designed_int:
        health_percent = int(round((full_int / designed_int) * 100))
        health_percent = max(0, min(100, health_percent))

    cycle_count = None
    try:
        cycle = payload.get("CycleCount")
        if cycle is not None:
            cycle_count = int(cycle)
    except (TypeError, ValueError):
        cycle_count = None

    if health_percent is None and full_int is None and cycle_count is None:
        return None
    return BatteryHealth(
        cycle_count=cycle_count,
        condition="Good" if (health_percent or 0) >= 80 else "Warning",
        max_capacity_percent=health_percent,
        health_percent=health_percent,
    )


# ---- macOS ----

def _collect_macos_disks() -> list[DiskHealth]:
    raw = _run(["system_profiler", "SPStorageDataType", "-json"])
    if not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except ValueError:
        return []

    seen: dict[str, DiskHealth] = {}
    for item in payload.get("SPStorageDataType", []):
        if not isinstance(item, dict):
            continue
        physical = item.get("physical_drive") or {}
        if not isinstance(physical, dict):
            continue
        name = str(physical.get("device_name") or "").strip()
        if not name or name == "Disk Image":
            continue
        device = str(item.get("bsd_name") or "")
        # Strip partition suffix (disk3s5 or disk3s1s1 -> disk3).
        disk_base = re.sub(r"(?:s\d+)+$", "", device)
        key = f"{name}|{disk_base}"
        media_type = _to_media_type(str(physical.get("medium_type") or ""))
        smart = str(physical.get("smart_status") or "") or None
        internal_raw = str(physical.get("is_internal_disk") or "").lower()
        # The volume entry carries capacity; the same physical disk shows up
        # once per partition, so take the largest as the disk's total size.
        try:
            volume_bytes = int(item.get("size_in_bytes") or 0) or None
        except (TypeError, ValueError):
            volume_bytes = None
        current = seen.get(key)
        if current is None:
            seen[key] = DiskHealth(
                name=name,
                device=disk_base,
                media_type=media_type,
                brand=_extract_brand(name),
                smart_status=smart,
                internal=True if internal_raw in ("yes", "true") else False,
                health=_derive_health(smart),
                size_bytes=volume_bytes,
            )
        elif volume_bytes and (not current.size_bytes or volume_bytes > current.size_bytes):
            current.size_bytes = volume_bytes
    return sorted(seen.values(), key=lambda d: d.name.lower())


def _collect_macos_battery() -> BatteryHealth | None:
    raw = _run(["system_profiler", "SPPowerDataType", "-json"])
    if not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None

    for item in payload.get("SPPowerDataType", []):
        if not isinstance(item, dict):
            continue
        if item.get("_name") != "spbattery_information":
            continue
        health = item.get("sppower_battery_health_info") or {}
        if not isinstance(health, dict):
            return None

        cycle_count = None
        try:
            cycle = health.get("sppower_battery_cycle_count")
            if cycle is not None:
                cycle_count = int(str(cycle).strip())
        except (TypeError, ValueError):
            cycle_count = None

        condition = str(health.get("sppower_battery_health") or "").strip() or None
        max_cap = None
        raw_cap = str(health.get("sppower_battery_health_maximum_capacity") or "").strip()
        if raw_cap:
            match = re.search(r"(\d+)", raw_cap)
            if match:
                max_cap = min(100, max(0, int(match.group(1))))
        if cycle_count is None and condition is None and max_cap is None:
            return None
        return BatteryHealth(
            cycle_count=cycle_count,
            condition=condition,
            max_capacity_percent=max_cap,
            health_percent=max_cap,
        )
    return None


def collect_health_info() -> HealthInfo:
    """Collect storage and battery health for this machine."""
    if os.name == "nt":
        return HealthInfo(
            disks=_collect_windows_disks(),
            battery=_collect_windows_battery(),
        )
    return HealthInfo(
        disks=_collect_macos_disks(),
        battery=_collect_macos_battery(),
    )
