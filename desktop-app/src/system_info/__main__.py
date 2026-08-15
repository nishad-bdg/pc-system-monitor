"""PyInstaller entrypoint."""

from system_info.win_runtime import install_crash_handler
from system_info.cli import main

if __name__ == "__main__":
    install_crash_handler()
    raise SystemExit(main())
