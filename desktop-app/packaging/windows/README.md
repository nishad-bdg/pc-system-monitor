# Windows installer (release-based updates)

Creates a per-user install of `system-info.exe`, writes API settings, registers
**Task Scheduler** jobs (an **hourly** report plus a **5-minute heartbeat** for
live online status), and supports **auto-update from a release manifest URL**
(not live `git pull`).

## Prerequisites (build machine)

- Windows with Python 3.14 (the project pins `requires-python = ">=3.14"`; PyInstaller must be on a build that supports 3.14)
- [uv](https://github.com/astral-sh/uv)
- [Inno Setup 6](https://jrsoftware.org/isinfo.php)

## 1. Build the exe

**Option A — GitHub Actions (no Windows machine needed).**

The repo ships a workflow (`.github/workflows/windows-release.yml`) that builds the
exe, compiles the installer with Inno Setup, and creates a GitHub Release with
`system-info.exe`, `SystemInfoSetup-<version>.exe`, and `release-manifest.json`.

```bash
git tag v0.2.0 && git push origin v0.2.0   # version taken from the tag
# or: GitHub -> Actions -> Windows Release -> Run workflow (enter version)
```

Point `SYSTEM_INFO_UPDATE_URL` at:
`https://github.com/<owner>/<repo>/releases/latest/download/release-manifest.json`

The `releases/latest` path redirects to the newest `v*` tag, so one URL auto-updates
every release. The installer field below is already pre-filled with this URL for this
repo (`nishad-bdg/pc-system-monitor`).

**Option B — local Windows machine.**

```powershell
cd desktop-app
.\packaging\windows\build.ps1
```

Output: `desktop-app/dist/system-info.exe`

## 2. Compile the installer

1. Open `packaging/windows/SystemInfoSetup.iss` in Inno Setup
2. Build → Compile  
   Output: `desktop-app/dist/installer/SystemInfoSetup-0.1.0.exe`

## 3. Install on a PC

Run `SystemInfoSetup-0.1.0.exe` (no admin required — installs under `%LOCALAPPDATA%\SystemInfo`).

Wizard asks for:

| Field | Purpose |
|-------|---------|
| API URL | e.g. `https://your-api.example.com` |
| API key | `sk-...` from admin `POST /api-keys` |
| PC name | optional Windows display name |
| Update manifest URL | optional HTTPS JSON (see below) |

Writes `%APPDATA%\system-info\config.env` and creates tasks **SystemInfoReport** (every hour) and **SystemInfoHeartbeat** (every 5 minutes, `--heartbeat`) so the PC shows as online.

## 4. Release updates (not git)

Publish a new `system-info.exe` (GitHub Release, S3, etc.) and a manifest JSON:

```json
{
  "version": "0.2.0",
  "windows": {
    "url": "https://…/system-info.exe",
    "sha256": "optional-hex"
  }
}
```

Set `SYSTEM_INFO_UPDATE_URL` in `config.env` (installer field) to that JSON URL.

On each scheduled run the app checks the manifest; if newer, it downloads and stages a replace via `apply-update.cmd`. The **next** hourly run uses the new binary.

Manual check:

```text
system-info.exe --check-update
system-info.exe --auto-update
```

## Security notes

- Prefer **per-site / org API keys**, not embedding a master key in a public download.
- Use HTTPS for API and update URLs.
- Optional `sha256` in the manifest is verified before replace.

## Uninstall

Add/Remove Programs removes files and deletes the **SystemInfoReport** and **SystemInfoHeartbeat** scheduled tasks.
