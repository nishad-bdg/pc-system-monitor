from __future__ import annotations

import platform
import uuid

from desktop_monitoring.transport import StdoutPublisher, run_once


def main() -> None:
    # getnode may be MAC-derived, but hostname remains a required identity anchor.
    run_once(
        publisher=StdoutPublisher(),
        hostname=platform.node(),
        machine_guid=str(uuid.getnode()),
    )


if __name__ == "__main__":
    main()
