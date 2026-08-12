# Windows installer (release-based updates)

Creates a per-user install of `system-info.exe`, writes API settings, registers a
**Task Scheduler** job every **30 minutes**, and supports **auto-update from a
release manifest URL** (not live `git pull`).

## Prerequisites (build machine)

- Windows with Python 3.12+ (3.14 if your PyInstaller build supports it)
- [uv](https://github.com/astral-sh/uv)
- [Inno Setup 6](https://jrsoftware.org/isinfo.php)

## 1. Build the exe

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

Writes `%APPDATA%\system-info\config.env` and creates task **SystemInfoReport** (every 30 minutes).

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

On each scheduled run the app checks the manifest; if newer, it downloads and stages a replace via `apply-update.cmd`. The **next** 30‑minute run uses the new binary.

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

Add/Remove Programs removes files and deletes the **SystemInfoReport** scheduled task.
