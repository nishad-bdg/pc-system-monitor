# System Info CLI (desktop-app)

Cross-platform (macOS & Windows) command-line tool that reports:

- OS info (`platform`)
- IP addresses (private + public)
- MAC addresses per network interface
- Geolocation via [ip-api.com](http://ip-api.com)
- CPU / RAM / swap usage (`psutil`)
- Disk storage devices and partitions

By default it POSTs each report to the API (see `../api`) for MongoDB storage,
authenticated with an API key.

## Usage

```bash
uv run system-info                      # full info (requires an API key to save)
uv run system-info --api-key sk-...     # save report with an API key
uv run system-info --json               # JSON output
uv run system-info --os                 # OS only
uv run system-info --ip                 # IP + MAC only
uv run system-info --geo                # geolocation only
uv run system-info --sys                # CPU/RAM/swap only
uv run system-info --disk               # storage only
uv run system-info --printers           # printers only (USB / network / other)
uv run system-info --no-save            # do not send report to API
uv run system-info --api-url http://localhost:8000    # custom API URL
uv run system-info --pc-name Office-PC-3              # Windows custom name
```

Each report includes `pc_name` and a stable `device_id`. On macOS, `pc_name` is
always the OS hostname. On Windows, `--pc-name` / `SYSTEM_INFO_PC_NAME` is used
when set; otherwise it falls back to the hostname. Printers are classified as
USB, network, or other.

The API key can also be set once via the `SYSTEM_INFO_API_KEY` environment
variable (and URL via `SYSTEM_INFO_API_URL`). Packaged Windows installs use
`%APPDATA%\system-info\config.env` (written by the installer).

## Windows installer

See [packaging/windows/README.md](packaging/windows/README.md): PyInstaller +
Inno Setup, Task Scheduler every 30 minutes, release-manifest auto-update.

## Tests

```bash
uv run pytest
```
