# Windows installer (release-based updates)

Creates a per-user install of `system-info.exe`, writes API settings, starts an
**always-on watcher** (`--watch`, system-tray messenger-style) at logon, and
supports **auto-update from a release manifest URL** (not live `git pull`).

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
`https://github.com/nishad-bdg/pc-system-monitor/releases/latest/download/release-manifest.json`

The `releases/latest` path redirects to the newest `v*` tag, so one URL auto-updates
every release. The installer field below is already pre-filled with this URL.

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
| Update manifest URL | optional; **pre-filled with this repo's `releases/latest` manifest** so installed PCs auto-update. Clear it to disable auto-update. |

Writes `%APPDATA%\system-info\config.env` and **always launches `--watch`**
right after files are copied (retries if antivirus still has the new exe
locked). The finish-page checkbox starts it again if that first launch was
blocked; a process mutex prevents two watchers. `--watch` is an **always-on**
background agent (messenger-style): while it is open it stays in the system tray
with **Check for updates…**, **Restart** and **Exit** items, keeps the PC
"online" (heartbeat every **60s**), flushes new print jobs, and sends a **full
report hourly**. Closing it (tray → Exit) stops it — it does **not** exit on
its own after sending data. Tray **Restart** spawns a fresh detached `--watch`
process and stops the current one. Frozen crashes write
`%APPDATA%\system-info\crash.log`.

After install, on the **first run** the app adds itself to the current user's
**Startup** (HKCU `...\CurrentVersion\Run` → `SystemInfoReporter` →
`system-info.exe --watch`) so the watcher restarts at every logon. This needs
**no admin rights** (no scheduled task, no elevation), so the install never
fails with a `schtasks` error. A marker file
(`%APPDATA%\system-info\startup-registered`) ensures this happens only once. Set
`SYSTEM_INFO_NO_STARTUP=1` to skip self-registration (portable use).

### Remote control (restart / shutdown / force-update)

While `--watch` is running it holds a persistent WebSocket agent channel to the
API (`/ws/agent`, authenticated with the same API key) so admin actions land
**immediately**:

- From the dashboard **Restart** / **Shut down** buttons (detail header, admin /
  super_admin only), the API pushes a `{"type":"command", ...}` frame to the
  agent and stores a `pending` command in Mongo.
- The watcher executes it on the spot (`shutdown /r /t 5` / `shutdown /s /t 5`),
  then acks over the socket **and** via `POST /commands/{id}/ack`.
- If the agent is offline the command stays `pending`; it is re-sent when the
  socket reconnects (`hello`) **and** falls back to the heartbeat poll response.

**Update all apps** (`super_admin` only, Fleet sidebar) broadcasts an `update`
command to every connected agent at once. Each agent checks the release
manifest, downloads a newer exe when one exists, and `apply-update-restart.cmd`
waits for the process to exit, swaps the exe and relaunches `--watch` with
PowerShell `Start-Process` — so the updated binary comes back up on its own. Already-up-to-date agents just ack.

Both reboot/shutdown actions are best-effort and run in whatever privileges the
watcher has (the per-user Run-key process typically can't reboot unless the user
is an admin).

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

On each hourly run (and from the tray **Check for updates…** item) the app
checks the manifest; if newer, it downloads, waits for this PID to exit, swaps
the exe, and relaunches `--watch` so the tray comes back.

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

Add/Remove Programs removes the app files, the **SystemInfoReporter** Run key,
the `startup-registered` marker, and any legacy scheduled tasks
(**SystemInfoWatch**/**SystemInfoReport**/**SystemInfoHeartbeat**) left over
from older versions — so the watcher no longer runs after uninstall.
