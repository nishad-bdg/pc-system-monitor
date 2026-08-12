import platform
import socket
from dataclasses import dataclass


@dataclass
class OSInfo:
    system: str
    release: str
    version: str
    machine: str
    processor: str
    architecture: str
    python_version: str
    hostname: str
    platform_detail: str

    def to_dict(self) -> dict:
        return {
            "system": self.system,
            "release": self.release,
            "version": self.version,
            "machine": self.machine,
            "processor": self.processor,
            "architecture": self.architecture,
            "python_version": self.python_version,
            "hostname": self.hostname,
            "platform_detail": self.platform_detail,
        }


def collect_os_info() -> OSInfo:
    """Collect OS + runtime info. Uses only stdlib `platform`/`socket`, so it
    is portable between macOS and Windows (no POSIX-only APIs)."""
    return OSInfo(
        system=platform.system(),
        release=platform.release(),
        version=platform.version(),
        machine=platform.machine(),
        processor=platform.processor() or "unknown",
        architecture=" ".join(platform.architecture()),
        python_version=platform.python_version(),
        hostname=socket.gethostname(),
        platform_detail=platform.platform(),
    )
