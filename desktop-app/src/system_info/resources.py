from dataclasses import dataclass

import psutil


@dataclass
class SystemResources:
    cpu_count: int
    cpu_count_physical: int
    cpu_percent: float
    cpu_freq_mhz: float | None
    ram_total: int
    ram_used: int
    ram_available: int
    ram_free: int
    ram_percent: float
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
            "ram_total": self.ram_total,
            "ram_used": self.ram_used,
            "ram_available": self.ram_available,
            "ram_free": self.ram_free,
            "ram_percent": self.ram_percent,
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
    unlimited = getattr(psutil, "POWER_TIME_UNLIMITED", 2**24 - 1)
    if isinstance(secsleft, int) and 0 <= secsleft < unlimited:
        seconds_left = secsleft
    return {
        "percent": float(batt.percent),
        "power_plugged": bool(batt.power_plugged),
        "seconds_left": seconds_left,
    }


def collect_resources() -> SystemResources:
    """Collect CPU and memory stats via psutil (cross-platform mac/Windows)."""
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    try:
        freq = psutil.cpu_freq()
        cpu_freq_mhz = freq.current if freq else None
    except (NotImplementedError, OSError):
        cpu_freq_mhz = None

    return SystemResources(
        cpu_count=psutil.cpu_count(logical=True) or 0,
        cpu_count_physical=psutil.cpu_count(logical=False) or 0,
        cpu_percent=psutil.cpu_percent(interval=0.2),
        cpu_freq_mhz=cpu_freq_mhz,
        ram_total=vm.total,
        ram_used=vm.used,
        ram_available=vm.available,
        ram_free=vm.free,
        ram_percent=vm.percent,
        swap_total=sw.total,
        swap_used=sw.used,
        swap_percent=sw.percent,
        battery=_collect_battery(),
    )
