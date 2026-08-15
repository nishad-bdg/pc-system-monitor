import json
import os
import platform
import re
import subprocess
from dataclasses import dataclass

import psutil

from .win_runtime import hidden_subprocess_kwargs


@dataclass
class SystemResources:
    cpu_count: int
    cpu_count_physical: int
    cpu_percent: float
    cpu_freq_mhz: float | None
    cpu_brand: str | None
    ram_total: int
    ram_used: int
    ram_available: int
    ram_free: int
    ram_percent: float
    ram_speed_mhz: int | None
    ram_type: str | None
    swap_total: int
    swap_used: int
    swap_percent: float
    battery: dict | None

    def to_dict(self) -> dict:
        return {
            "cpu_count": self.cpu_count,
            "cpu_count_physical": self.cpu_count_physical,
            "cpu_percent": self.cpu_percent,
            "cpu_freq_mhz": self.cpu_freq_mhz,
            "cpu_brand": self.cpu_brand,
            "ram_total": self.ram_total,
            "ram_used": self.ram_used,
            "ram_available": self.ram_available,
            "ram_free": self.ram_free,
            "ram_percent": self.ram_percent,
            "ram_speed_mhz": self.ram_speed_mhz,
            "ram_type": self.ram_type,
            "swap_total": self.swap_total,
            "swap_used": self.swap_used,
            "swap_percent": self.swap_percent,
            "battery": self.battery,
        }


def _collect_battery() -> dict | None:
    """Battery info (percent, plugged, time left) — None on desktops."""
    try:
        batt = psutil.sensors_battery()
    except (NotImplementedError, OSError):
        return None
    if batt is None:
        return None
    secsleft = getattr(batt, "secsleft", -1)
    seconds_left = None
    # psutil uses -1 (unknown) and -2 (unlimited) sentinels; a sane positive
    # time-left value is real wall-clock seconds.
    if isinstance(secsleft, int) and secsleft > 0:
        seconds_left = secsleft
    plugged = bool(getattr(batt, "power_plugged", False))
    percent = float(batt.percent)
    status = "discharging"
    if plugged:
        status = "full" if percent >= 100 else "charging"
    return {
        "percent": percent,
        "power_plugged": plugged,
        "seconds_left": seconds_left,
        "status": status,
    }


def _run(cmd: list[str], timeout: float = 15.0) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            **hidden_subprocess_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout or ""


# Windows SMBIOSMemoryType codes -> DDR generation label
_SMBIOS_MEMORY_TYPES = {
    24: "DDR3",
    26: "DDR4",
    27: "DDR4E",
    28: "LPDDR3",
    29: "LPDDR4",
    34: "DDR5",
    35: "LPDDR5",
}


def _collect_macos_ram() -> tuple[int | None, str | None]:
    """RAM speed (MHz) + type via `system_profiler SPMemoryDataType`."""
    raw = _run(["system_profiler", "SPMemoryDataType", "-json"])
    if not raw.strip():
        return None, None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None, None

    speed: int | None = None
    typ: str | None = None
    for item in payload.get("SPMemoryDataType", []):
        if not isinstance(item, dict):
            continue
        # Modern macOS (Apple Silicon): fields at the top level of each item.
        raw_type_new = str(item.get("dimm_type") or "").strip()
        if raw_type_new and typ is None:
            typ = raw_type_new
        # Intel macOS: slots list with per-DIMM speed + type.
        for slot in item.get("SPSlotInfoList", []) or []:
            if not isinstance(slot, dict):
                continue
            raw_speed = str(slot.get("spps_memory_speed") or "").strip()
            match = re.search(r"(\d+(?:\.\d+)?)", raw_speed)
            if match and speed is None:
                speed = int(float(match.group(1)))
            raw_type = str(slot.get("spps_memory_type") or "").strip()
            if raw_type and typ is None:
                typ = raw_type
    return speed, typ


def _collect_windows_ram() -> tuple[int | None, str | None]:
    """RAM speed (MHz) + type via Win32_PhysicalMemory."""
    raw = _run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_PhysicalMemory | "
            "Select-Object Speed, SMBIOSMemoryType | ConvertTo-Json",
        ]
    )
    if not raw.strip():
        return None, None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None, None
    if isinstance(payload, dict):
        payload = [payload]

    speed: int | None = None
    typ: str | None = None
    for mod in payload:
        if not isinstance(mod, dict):
            continue
        try:
            if speed is None and mod.get("Speed"):
                speed = int(mod["Speed"])
        except (TypeError, ValueError):
            pass
        if typ is None:
            code = mod.get("SMBIOSMemoryType")
            try:
                code = int(code)
            except (TypeError, ValueError):
                code = None
            if code in _SMBIOS_MEMORY_TYPES:
                typ = _SMBIOS_MEMORY_TYPES[code]
    return speed, typ


def _collect_ram_speed() -> tuple[int | None, str | None]:
    """Best-effort RAM speed (MHz) + type. Falls back to (None, None)."""
    if os.name == "nt":
        return _collect_windows_ram()
    if platform.system() == "Darwin":
        return _collect_macos_ram()
    return None, None


def _collect_cpu_brand() -> str | None:
    """Best-effort CPU vendor/brand."""
    if platform.system() == "Darwin":
        raw = _run(["system_profiler", "SPHardwareDataType", "-json"])
        if not raw.strip():
            return None
        try:
            payload = json.loads(raw)
        except ValueError:
            return None
        for item in payload.get("SPHardwareDataType", []):
            if not isinstance(item, dict):
                continue
            chip = str(item.get("chip_type") or "").strip()
            if chip:
                # "Apple M2" -> "Apple", "Intel Core i7-..." -> "Intel"
                return chip.split()[0] if chip.split() else chip
            proc = str(item.get("processor_name") or "").strip()
            if proc and proc.split():
                return proc.split()[0]
        return None

    if os.name == "nt":
        raw = _run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Processor | "
                "Select-Object Name | ConvertTo-Json",
            ]
        )
        if not raw.strip():
            return None
        try:
            payload = json.loads(raw)
        except ValueError:
            return None
        if isinstance(payload, dict):
            payload = [payload]
        for p in payload:
            if not isinstance(p, dict):
                continue
            name = str(p.get("Name") or "").strip()
            if not name:
                continue
            lowered = name.lower()
            if "intel" in lowered:
                return "Intel"
            if "amd" in lowered or "ryzen" in lowered or "athlon" in lowered:
                return "AMD"
            if "qualcomm" in lowered or "snapdragon" in lowered:
                return "Qualcomm"
            if name.split():
                return name.split()[0]
        return None

    return None


def collect_resources() -> SystemResources:
    """Collect CPU and memory stats via psutil (cross-platform mac/Windows)."""
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    try:
        freq = psutil.cpu_freq()
        cpu_freq_mhz = freq.current if freq else None
    except (NotImplementedError, OSError):
        cpu_freq_mhz = None

    ram_speed_mhz, ram_type = _collect_ram_speed()
    cpu_brand = _collect_cpu_brand()

    return SystemResources(
        cpu_count=psutil.cpu_count(logical=True) or 0,
        cpu_count_physical=psutil.cpu_count(logical=False) or 0,
        cpu_percent=psutil.cpu_percent(interval=0.2),
        cpu_freq_mhz=cpu_freq_mhz,
        cpu_brand=cpu_brand,
        ram_total=vm.total,
        ram_used=vm.used,
        ram_available=vm.available,
        ram_free=vm.free,
        ram_percent=vm.percent,
        ram_speed_mhz=ram_speed_mhz,
        ram_type=ram_type,
        swap_total=sw.total,
        swap_used=sw.used,
        swap_percent=sw.percent,
        battery=_collect_battery(),
    )
