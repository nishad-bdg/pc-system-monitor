# Project context — Desktop Monitoring App

Last updated: 2026-08-17

Use this file as the source of truth for current product behavior when continuing work.
Detailed design notes also live under `docs/superpowers/specs/`.

## Purpose

Collect system info from many Windows/macOS PCs via a desktop CLI, store reports in MongoDB through a FastAPI backend, and manage/view them in a Next.js admin dashboard.

## Layout

```
desktop-app/   Python CLI (`system-info`) — collect + POST reports
api/           FastAPI + MongoDB — auth, API keys, reports
dashboard/     Next.js admin UI — Fleet + Reports
docs/          Specs/plans (superpowers)
```

## Stack

| Area | Tech |
|------|------|
| Desktop | Python 3.14, `psutil`, `requests`, `Pillow`, `pystray`, `websocket-client`, `uv` |
| API | FastAPI, MongoDB, JWT + API keys, `uv` |
| Dashboard | Next.js 16, NextAuth v5, TanStack Query, Recharts, Tailwind, pnpm |

## Auth

- **Desktop → API:** `Authorization: Bearer sk-...` (API key). Create via `POST /api-keys` (admin JWT) or the dashboard `/api-keys` page. Full secret shown only once at create time (auto-generated `sk-`); can rename / toggle active / delete.
- **Roles:** `super_admin`, `admin`, `user` (see below).
- **Dashboard → API:** NextAuth Credentials → `POST /auth/token` → JWT stored on session as `apiToken`. If the API is restarted and the stored JWT is rejected (401 on `/reports`), **sign out and back in** to refresh the token.
- **Refresh tokens:** `POST /auth/token` also returns `refresh_token` (opaque, 30 days, stored hashed in Mongo `refresh_tokens` collection). `POST /auth/refresh` rotates it for a new access + refresh pair (old one revoked). `POST /auth/revoke` revokes a refresh token. The dashboard (`auth.ts`) stores the refresh token in the NextAuth JWT and silently calls `/auth/refresh` ~60s before the access token expires — no manual sign-in needed unless the refresh token itself is invalidated.
- **Password change:** `POST /auth/change-password` (JWT) takes `current_password` + `new_password` (min 6 chars); verifies current, updates the hash, and revokes **all** refresh tokens so other sessions must re-login. UI: `UserNav` in the top bar — profile avatar + name + role badge with **Change password** + **Sign out** buttons (`user-nav.tsx`, modal).

### Roles & group-scoped access

| Role | Users mgmt | API keys | Groups | Reports |
|------|-----------|----------|--------|---------|
| `super_admin` (seed default) | ✅ CRUD | ✅ | ✅ CRUD | ✅ all |
| `admin` | ❌ | ❌ | 🔍 (read-only) | ✅ all |
| `user` | ❌ | ❌ | 🔍 own only | ✅ own groups only |

- Seed `ADMIN_USERNAME`/`ADMIN_PASSWORD` is auto-created (and legacy `admin` promoted) to `super_admin` on startup.
- **Users page** (`/users`, super admin only): create users with a role + a set of groups (multi-select). One user can belong to **multiple groups** and then sees every PC in each assigned group. **A non-`super_admin` user must be assigned at least one group** (enforced in the UI — submit disabled + inline hint — and server-side, `POST /users` and `PATCH /users/{id}` return 422 if the effective role isn't super_admin and the group list is empty); only `super_admin` can be created/edited group-less. `PATCH /users/{id}` edits role/groups/password (can't change your own role); deleting yourself is blocked.
- **Group scoping is enforced server-side**: for a `user`, `GET /reports`, `/reports/export`, and `/reports/{id}` are filtered to the user's groups; `GET /groups` returns only their groups. `admin`/`super_admin` are unrestricted.
- **Sub-categories**: a many-to-many refinement of groups. A sub-category can belong to **many groups** (group doc holds `subcategory_ids`; sub-category holds `group_ids`) and holds its own `machine_keys`. A PC sits in **exactly one bucket** — a main group **or** one sub-category. Assigning a machine key to either bucket removes it from ALL other groups and sub-categories (enforced server-side via `remove_machine_keys_from_groups`/`remove_machine_keys_from_sub_categories`). Group scoping (filters + `user` role) automatically includes the sub-categories linked to a group, so a sub-category's PCs show up under every parent group. `GET /reports`/`/reports/export` accept `sub_category_id`; `GET /sub-categories` returns all for admin, only those linked to the user's groups otherwise; CRUD is `super_admin` only (groups CRUD is likewise `super_admin` only).
- **API keys** (`/api-keys` page + routes) are **super admin only** (403 otherwise).
- **Dashboard:** session carries `role` + `groups` (fetched from `/auth/me` at login); top-bar nav hides API Keys/Users unless `super_admin`; Groups page is read-only for `admin`/`user` (only `super_admin` can create/rename/delete groups/sub-categories or assign PCs).
- A `user` with no groups assigned sees no reports (empty fleet).

## Data flow

```
Desktop CLI (full collect)
  → POST /reports (API key)
  → MongoDB reports collection

Admin dashboard
  → GET /reports?... (JWT)
  → groupMachines() for fleet / reports table
```

Restart the API after model/query changes; old processes strip unknown fields (e.g. `printers`, `pc_name`, `network`).

---

## Desktop app (`desktop-app/`)

### Commands

```bash
uv run system-info --api-key sk-...          # full collect + save
uv run system-info --no-save                 # print only
uv run system-info --heartbeat               # lightweight online ping (one-shot)
uv run system-info --watch                   # always-on daemon: heartbeats, live metrics, hourly reports, tray Exit
uv run system-info --pc-name Office-PC-3     # Windows custom name
uv run system-info --printers | --disk | --network | --sys | --security | --health | --emails | --processes
uv run system-info --print-jobs              # flush new print jobs, then exit
uv run system-info --check-update            # Windows: compare local version to SYSTEM_INFO_UPDATE_URL
uv run system-info --auto-update             # Windows: download + swap exe and relaunch --watch
uv run system-info --version
```

Env: `SYSTEM_INFO_API_URL`, `SYSTEM_INFO_API_KEY`, `SYSTEM_INFO_PC_NAME`, `SYSTEM_INFO_UPDATE_URL`, `SYSTEM_INFO_NO_STARTUP=1` (skip HKCU Run registration), `SYSTEM_INFO_CONFIG` (explicit env file). Frozen Windows with no one-shot flags defaults to `--watch`.

### Online / offline status

- Each PC keeps its online status alive via heartbeats: the always-on Windows watcher (`--watch`) sends them every **60 seconds** (and `POST /heartbeat`); one-shot `--heartbeat` still works for manual/portable use.
- The API tracks `last_seen` per `device_id` in a `machines` Mongo collection; a machine is **online** if `last_seen` is within `SYSTEM_INFO_ONLINE_TIMEOUT_SECONDS` (default 300s).
- Agent WebSocket `hello` also marks the PC online immediately; the last `/ws/agent` disconnect marks it offline.
- `GET /reports`, `GET /reports/{id}`, and `GET /reports/export` annotate every report with `online` (bool) + `last_seen`. Old reports without a `device_id` are marked offline.
- The dashboard shows a **green (online) / red (offline)** dot next to each PC in the Fleet sidebar, Reports browser, and detail header. The client timer starts from **when the presence event was received**, not by comparing `last_seen` to the browser clock (avoids false-offline from clock skew).
- **Windows activation** is on the hourly/Collect report (`os.windows_activation`), not the 5s live metrics stream. Dashboard: identity bar **Windows** (green Activated / amber Not activated or grace), Summary **Operating system** card, Overview Machine card. Fleet/Reports sidebar shows an amber badge when `licensed` is false. Older reports without the field omit it until Collect now / a new desktop build.
- Admin **Ping** (`POST /commands/ping`) live-checks the agent socket (any OS); **Connect** (`POST /commands` type `reconnect`) asks an offline PC to reopen `/ws/agent` if the desktop app is running and has internet; **Connect all** (`POST /commands/batch` type `reconnect`) does the same for every PC in the current sidebar list (or the whole fleet on pages without a PC list); **Collect now** (`POST /commands` type `collect`) asks that PC to send a fresh report. See Remote control. **Connect all** (`admin`/`super_admin`) and **Update all apps** (`super_admin`) appear in the **sidebar footer of every dashboard page**.

### Identity

- **`device_id`:** stable UUID from `device.py` (`get_or_create_device_id`), persisted in OS config dir (`~/.config/system-info/device.json` or `%APPDATA%/system-info`).
- **`pc_name`:**
  - **macOS:** always OS hostname (custom `--pc-name` ignored).
  - **Windows:** `--pc-name` / `SYSTEM_INFO_PC_NAME`, else hostname.

### Collected payload (full run)

| Field | Source | Notes |
|-------|--------|--------|
| `pc_name`, `device_id` | `device.py` | Always on save |
| `app_version` | `version.py` | Desktop **System Info Reporter** version (e.g. `0.2.21`). Always on save. Dashboard shows it as `v0.2.21` on the machine identity bar, Fleet/Reports sidebar, and Overview Machine card. Older reports without the field show **—**. |
| `os` | `os_info.py` | Includes hostname. On **Windows**, `windows_activation` from WMI `SoftwareLicensingProduct` (`licensed`, `status`, `label`, channel, last-5 `partial_key`). `null` on macOS and when WMI fails. |
| `private_ip`, `public_ip`, `mac_address`, `mac_addresses` | `ip.py` | |
| `location` | `geo.py` | ip-api.com |
| `resources` | `resources.py` | CPU/RAM/swap + laptop `battery` + RAM `ram_speed_mhz`/`ram_type`. CPU **`cpu_brand`** is the vendor (Intel/AMD/Apple). **`cpu_name`** is the marketing model (`Intel Core i5-10400`, `AMD Ryzen 7 5800X 8-Core Processor`, `Apple M2`). Windows prefers registry `ProcessorNameString`, then WMI `Win32_Processor.Name`; vendor-only labels (`AMD`, `Intel`) and Family/Model strings are dropped. Dashboard **Name** uses live `metrics.sample.cpu_name` (cached, sent every 5s) then the report field — never Brand alone. |
| `uptime` | `uptime.py` | Session + UTC day-wise on-seconds (`by_day`) |
| `network` | `network.py` | NIC totals/rates |

| `disk` | `disk.py` | Physical devices + partitions (mac + Win) |
| `printers` | `printers.py` | See below |
| `security` | `security.py` | Internet-security products, see below |
| `health` | `health.py` | Disk + battery health, see below |
| `email_accounts` | `email_accounts.py` | POP/IMAP accounts, see below |
| `processes` | `processes.py` | Top 10 CPU / RAM / network processes. Hourly + Collect now store a snapshot. **Live** lists ride `metrics.sample` every 5s (not Mongo). Network rank is open inet connection count, not bytes/sec. |

### Battery (`resources.battery`)

Laptop only (`psutil.sensors_battery()`), `null` on desktops:

`battery: { percent, power_plugged, seconds_left, status }`.

`status` is derived from psutil: `"charging"` (plugged, <100%), `"full"`
(plugged, 100%), `"discharging"` (on battery, shows `seconds_left`
remaining). The dashboard Overview Battery card shows this state
(Charging · time to full / Fully charged / On battery · time remaining).

### Windows activation (`os.windows_activation`)

Windows only (macOS `null`). WMI `SoftwareLicensingProduct` for the Windows
app ID, SKUs that have a `PartialProductKey` (the installed product).

`{ licensed, status, label, name, channel, partial_key, grace_minutes }`

- `licensed` is true only when `LicenseStatus` is **1**.
- `label`: Activated / Not activated / Out-of-box grace / Out-of-tolerance grace / Non-genuine grace / Notification / Extended grace.
- `partial_key` is the last 5 characters only (never the full key).
- Collected on hourly reports and Collect now, not the 5s live metrics stream.

Dashboard: identity bar, Summary Operating system card, Overview Machine card.
Amber Fleet/Reports badge when not licensed. Old reports without the field
show nothing until a new desktop collect.

### Internet Security (`security`)

Detects installed internet-security products:

- **Windows:** Security Center via `root/SecurityCenter2` (WMI `productState` bit 0x1000 = active); falls back to scanning running processes + Program Files dirs when Security Center is empty. Licence expiry is best-effort from vendor registry (and ESET `license.lf`): Bitdefender only if it still writes local `days_left` / expiry keys (cloud Central / GravityZone often have none).
- **macOS:** scans `/Applications` + `~/Applications`, running processes, and launch agents/daemons for known vendors (McAfee, ESET, AVG, F-Secure, CrowdStrike, …); defaults to **XProtect** when nothing else is found (no expiry).

`security: { count, platform, installed: [{ name, vendor, active, expiry_date, expired, days_remaining }] }`.

Dashboard: if `expired` → **Expired**; else if `expiry_date` → **N days remaining · expires &lt;date&gt;** (amber if ≤30 days). Missing expiry is omitted (typical for Windows Defender).

### Health (`health`)

`health: { disks: [...], battery: {...} }`.

**Disk:** physical drives with media type + SMART status:

`{ name, device, media_type: "ssd" | "hdd" | "unknown", smart_status, brand, internal, health: "ok" | "warning" | "fail" | "unknown", size_bytes }`

- Windows: `Get-PhysicalDisk` (FriendlyName/MediaType/HealthStatus/BusType/Manufacturer/Size). `internal` from BusType: USB/SD/MMC → external; SATA/SAS/NVMe/RAID/SCM → internal; unknown bus → `null`.
- macOS: `system_profiler SPStorageDataType -json`, physical drives de-duplicated by bsd base (`disk3s1s1` → `disk3`), capacity taken from the largest volume entry. `brand` from the device name (e.g. APPLE).
- The dashboard shows total storage (`size_bytes`, formatted) beside the drive name in the Summary + Health tabs.

**Battery (laptop):**

`{ cycle_count, condition, max_capacity_percent, health_percent }`

- Windows: `powercfg /batteryreport /xml` first (broad Win8+ support — exposes `DesignCapacity`/`FullChargeCapacity`/`CycleCount` directly). Cycle count `0`, `-1`, and ACPI sentinel `4294967295` are **unknown** (OEM firmware often writes 0 when unsupported). If powercfg has capacities but no usable cycle count, overlay `root/WMI` `BatteryCycleCount`. Full WMI fallback (`BatteryFullChargedCapacity` / `BatteryStaticData` / `BatteryCycleCount`, `Win32_Battery.DesignCapacity` included) when the report is unavailable. Unknown `condition` is `null` (not `"unknown"`). Dashboard Cycle count shows **—** for null or `<= 0` (covers old stored `0` reports).
- macOS: `SPPowerDataType` (`sppower_battery_cycle_count`, `sppower_battery_health`, `sppower_battery_health_maximum_capacity` like `"82%"`).

### Printers

Grouped as **usb / network / other**.

Each printer: `{ name, port, connection, ip, print_count }`. `connection` is `usb | network | other` (also used to group the lists).

- **ip:** extracted from the network port/URI or Windows `Get-PrinterPort` address when a valid IPv4 is present (octets 0–255); else `null`.
- **print_count:** best-effort. macOS IPP/`ipptool` (test file written to a temp file because `ipptool` rejects stdin `-`). Windows `Get-PrinterProperty` allowlist only (`PageCount`, `PrintCount`, `TotalPages`, `Impressions`, `PagesPrinted`, `Config:PageCount`) — a device/driver counter, **not** pages printed from this PC; job IDs / queue length / names that merely contain “count” are ignored. Else `null`.
- macOS: CUPS `lpstat -v`.
- Windows: `Get-Printer` for names/ports; **`Get-PrinterPort` is authoritative** for `PrinterHostAddress` / `DeviceURL`. Classification uses the resolved address **and** the port name (USB00n, Standard TCP/IP, custom TCP/IP, WSD, IPP/IPPS, SMB `\\server\share`, hostname ports). `FILE:`, `LPT1:`, `PORTPROMPT:` (Microsoft Print to PDF) stay `other`.

### Network bandwidth

`network: { bytes_sent, bytes_recv, send_rate_bps, recv_rate_bps }` —
totals since boot + ~0.5s NIC sample rates (`psutil`). Hourly/Collect only.

**Live Ethernet (Task Manager style):** the 5s `metrics` sample also includes
`eth_name`, `eth_kind` (`ethernet|wifi|other`), `eth_send_rate_bps`,
`eth_recv_rate_bps`, and `eth_link_mbps` when known. The agent picks the
preferred **up** physical NIC (Ethernet over other adapters over Wi-Fi; skips
loopback/virtual) and reports send/receive since the last sample. Dashboard
Overview/Summary show **Send** / **Receive** as bit rates (Mbps) plus a live
sparkline of the last ~7 minutes. All-NIC boot totals stay on the same card.

### Uptime (day-wise)

`uptime: { boot_time, uptime_seconds, by_day: { "YYYY-MM-DD": seconds }, day_timezone: "UTC" }` —
agent accumulates on-seconds per UTC day in `uptime.json`; admin labels days in Asia/Dhaka (BD).

### Email accounts (`email_accounts`)

Detects POP/IMAP accounts configured in mail clients (address + server config only —
**passwords are encrypted in the OS keychain / credential manager and are not read**):

`email_accounts: { count, accounts: [{ client, email, username, full_name, protocol, incoming_host, incoming_port, outgoing_host, outgoing_port, security }] }`

- **Apple Mail (macOS):** `~/Library/Preferences/com.apple.mail.plist` (`MailAccounts` + `DeliveryAccounts` for SMTP).
- **Thunderbird (mac + Win):** `prefs.js` in each profile (`mail.account.*`, `mail.server.*.type|hostname|port|socketType`, `mail.identity.*.email`, SMTP via `mail.smtpserver.*`). `socketType`/`try_ssl` map to `none|starttls|ssl`.
- **Outlook for Mac:** account plists under `~/Library/Group Containers/UBF8T346G9.Office/Outlook/*/Accounts/` (legacy) **or** modern Outlook/Office-365 `ProfilePreferences.plist` `SortedAccounts` entries (`<email>_ActiveSyncExchange_HxS` / `_Imap_HxS` / `_Pop_HxS`) — emails + protocol + gateway host extracted.
- **New Outlook (Win):** `%LOCALAPPDATA%\Microsoft\Olk\` plus packaged-app JSON (`Microsoft.OutlookForWindows_*`, `SmtpAddress` / UPN).
- **Classic Outlook (Win):** Office Identity registry (`HKCU\...\Common\Identity`), Autodiscover `user@domain.com.xml` files, `outlook.xml` when present, and profile SMTP property tags (`001f6613`, `001f3003`, …).

`client` is one of `apple_mail | thunderbird | outlook_mac | outlook_new | outlook_classic`.

---

## API (`api/`)

### Report model extras

Optional on `Report`: `pc_name`, `device_id`, `app_version`, `disk`, `printers`, `network`, `uptime`, `security`, `health`, `email_accounts` (plus original OS/IP/geo/resources).

### `GET /reports` query params

| Param | Behavior |
|-------|----------|
| `limit` | 1–500 |
| `device_id` | Exact match |
| `pc_name` | Case-insensitive contains on `pc_name` **or** `os.hostname` |
| `from_ts`, `to_ts` | Unix seconds on `created_at` |
| `country` | Regex on `location.country` or `location.country_code` |
| `os` | Regex on `os.system` |
| `disk_health` | `healthy` (≥1 disk, none warning/fail) or `problem` (has warning/fail) |
| `battery` | `has` (battery present) or `none` |
| `battery_health_min` | Min `health.battery.health_percent` (e.g. 80) |
| `group_id` | Matches machine keys `id:`/`mac:`/`name:` in the group (incl. its linked sub-categories) |
| `sub_category_id` | Matches machine keys in the sub-category |

Sorted by `created_at` **descending** (newest first). Auth: admin JWT.

### Other routes

- `POST /reports` — API key; stores `source_key` prefix.
- `GET /reports/{id}` — JWT.
- `GET /reports/export` — JWT; same filters as `/reports` (incl. `group_id`, `sub_category_id`, `disk_health`, `battery`, `battery_health_min`); streams CSV with **every report field flattened** (`a.b.c` columns, arrays as JSON).
- `GET/POST/PATCH/DELETE /api-keys` — admin JWT; `PATCH` renames / toggles active; secret shown only at create. **A key can optionally be linked to a group (`group_id`)**; reports and heartbeats sent with that key auto-assign the PC's machine keys to the group (one-bucket exclusivity, `db.assign_machine_keys_to_group`). Clearing the link on PATCH is expressed with `group_id: ""`.
- `GET/POST/PATCH/DELETE /groups` — admin JWT; a machine key belongs to **one bucket only** (assigning removes it from other groups AND sub-categories).
- `GET/POST/PATCH/DELETE /sub-categories` — admin JWT; create/update take `group_ids` (many-to-many); `PATCH` machine_keys remove the keys from all groups and other sub-categories (one-bucket).
- `POST /print-jobs` — API key; batch `{device_id, pc_name, jobs:[...]}` → Mongo `print_jobs` + WS `print.job`. `GET /print-jobs?limit=&skip=&group_id=` returns `{total, skip, limit, jobs}`; `GET /print-jobs/summary` — JWT (see Print Activity below).
- `POST /commands` — admin JWT; `{device_id, type: "restart" | "shutdown" | "update" | "collect" | "reconnect"}` → Mongo `commands` collection + push to the agent over `/ws/agent`. `POST /commands/ping` — admin JWT; `{device_id}` live-probes the agent WebSocket (waits ~3s for `pong`; connected with `rtt_ms=null` if the socket exists but the agent is too old to reply). `POST /commands/batch` — admin JWT; `{type: "reconnect", device_ids: [...]}` enqueues the same command for each id (offline agents stay `pending` for the next heartbeat). `POST /commands/broadcast` — **super_admin** only; pushes one `update` command to every connected agent socket at once (force-update all apps). `GET /commands?device_id=&limit=` — admin JWT, newest first. `POST /commands/{id}/ack` — **API key**; sets `status` + `acked_at` (409 if already resolved). See **Remote control** below.
- Auth, users, health — unchanged pattern.

### Remote control (Ping / Connect / Connect all / Collect now / Restart / Shutdown / Update app)

- **Ping** (any OS): detail header **Ping** button (`admin`/`super_admin`) calls
  `POST /commands/ping`. Not a Mongo command. Shows connected + RTT, or not
  connected. A 404 **Not Found** means the **API** was not redeployed with the
  ping route (Restart can still work on an older API).
- **Connect** (any OS): detail header **Connect** button when the PC is
  **offline** (`admin`/`super_admin`, needs `device_id`). Pings first; if the
  socket is already up it reports connected. Otherwise `POST /commands` with
  `type: "reconnect"`. The dashboard cannot open a socket *to* the PC — the
  agent must already be running (`--watch`) with internet. If the agent
  WebSocket is down, the command stays `pending` and the next heartbeat
  (≤60s) kicks `/ws/agent` so it reconnects immediately instead of waiting
  the 30s backoff. The dashboard then polls Ping for about a minute. Success:
  connected (+ RTT). Failure: the app may not be running, or the PC has no
  internet. Connect is **not** part of Update all apps.
- **Connect all** (any OS): sidebar **Connect all** button on **every**
  dashboard page (`admin`/`super_admin`, `sidebar-remote-actions.tsx`) calls
  `POST /commands/batch` with `type: "reconnect"`. On Overview / Graphs /
  Fleet / Reports it uses the `device_id`s of every PC **currently shown in
  that page's sidebar list** (name/group filters apply; PCs without a
  `device_id` are skipped). On other pages (Print Activity, Groups, Export,
  Users, API Keys, PC detail) it targets the whole accessible fleet. Unlike
  **Update all apps**, offline agents are included — the
  command stays `pending` until the next heartbeat. No per-PC Ping polling;
  presence dots flip green over `/ws` as each agent reconnects. Copy: asked
  N PCs to reconnect; if the app is running with internet they should come
  online within a minute. Connect all is **not** part of Update all apps.
- **Collect now** (any OS): detail header **Collect now** button
  (`admin`/`super_admin`, needs `device_id`) calls `POST /commands` with
  `type: "collect"`. No confirm (not destructive). The agent runs a full collect
  and `POST /reports` (same payload as the hourly report, including
  `app_version`; **no** auto-update). The open dashboard picks up the new
  snapshot via the existing `report.created` WebSocket — no extra polling.
  Offline agents keep the command `pending` and run it on the next heartbeat
  (same as restart). Success copy: asked this PC to send a fresh report; the
  view updates when it arrives.
- **Restart / Shut down** are **Windows only** (`os.system` starts with `win`
  on the dashboard). macOS does **not** run `osascript`. Buttons are hidden on
  non-Windows PCs.
- Admin triggers restart/shutdown from the dashboard detail header
  (`admin`/`super_admin` only, needs `device_id`). A confirm dialog calls
  `POST /commands`; the API stores a `pending` command in Mongo **and** pushes
  it immediately to the desktop agent.
- **Agent channel (`GET /ws/agent`):** the always-on watcher (`--watch`) holds a
  persistent WebSocket to the API (same API key, passed as the WS **subprotocol**
  or `?key=`; code **4001** on auth failure). On connect it sends
  `{"type":"hello", device_id, pc_name}`; the server registers it, marks
  presence online, and **re-sends any `pending` commands**. Server → agent:
  `{"type":"command", command:{id,device_id,type,status,created_at}}` or
  `{"type":"ping", ping_id, ts}`; agent → server: `{"type":"command.ack", ...}`
  or `{"type":"pong", ping_id}`. The watcher also sends
  `{"type":"metrics", ...}` every 5s (live CPU/RAM/network); the API
  broadcasts that to dashboards as `metrics.sample`.
- **Desktop execution** (`commands.py`): `System32\shutdown.exe /r` or `/s`
  with `/t 5 /f` and `CREATE_NO_WINDOW` (**Windows only**). Acks over WS **and**
  HTTP `POST /commands/{id}/ack`; a failed execute acks `failed`. `collect`
  runs `collect_and_save` (one-shot namespace, `watch=False`) and HTTP-acks
  when the save finishes. On the agent WebSocket thread, collect runs in a
  **daemon thread** so ping/command traffic is not blocked for 10–30s;
  heartbeat `handle_pending_commands` runs collect inline. `reconnect` on a
  live socket acks `done` without dropping it; on heartbeat it calls
  `WatchCommandSocket.kick()` so the agent skips the 30s reconnect wait.
- **Offline fallback:** without a socket the command stays `pending`; it is
  re-sent on agent `hello` at reconnect **and** echoed in the `commands` field of
  the heartbeat poll response (`GET/POST /heartbeat`).
- **Force-update all apps (`update` command):** the sidebar **Update all
  apps** button on **every** dashboard page (`super_admin` only) calls
  `POST /commands/broadcast {type:
  "update"}` → a per-device command is pushed to **every connected agent
  socket** at once. Collect and Connect/`reconnect` are **not** part of Update
  all apps. Each agent runs
  `update.py::force_update_and_restart()`:
  if a newer build exists it downloads it and `apply_update_and_restart()` writes
  a detached `apply-update-restart.cmd` that **waits for the old PID to exit,
  swaps the exe, then `Start-Process … --watch`** (not cmd `start ""`, which
  often does nothing when the updater runs with no console). Hourly
  auto-update and tray **Check for updates…** use the same restart path (not
  stage-and-wait). Already-up-to-date agents ack `done` but don't restart.
  Offline agents are skipped by the broadcast.
- Broadcasting is in-process (per uvicorn worker), same caveat as print/WS
  events.

### Realtime (`WebSocket /ws`, hi `--heartbeat`)

- **`POST /heartbeat`** (API key) — desktop pings with `{device_id, pc_name}`; records `last_seen` in the `machines` collection.
- **`GET/POST /reports`** — every saved report is annotated with `online` + `last_seen` and broadcasts a `report.created` event (full report incl. `printers`) over the WebSocket so the dashboard updates in realtime (print counts included).
- **`WebSocket /ws`** (`routes/realtime.py`) — the dashboard connects with its JWT passed as the WS **subprotocol** (or `?token=`); only `admin`/`super_admin` roles are allowed; `Origin` must match `CORS_ORIGINS`. On connect the server sends `{"type":"hello"}` then seeds `{"type":"presence.changed","presence":{device_id,online,last_seen,pc_name}}` for every known machine (in-process snapshot). Events: `{"type":"report.created","report":{...},"ts":...}`, `{"type":"presence.changed","presence":{...},"ts":...}`, `{"type":"print.job","job":{...},"ts":...}`, and `{"type":"metrics.sample","metrics":{device_id,cpu_percent,ram_percent,ram_used,ram_total,bytes_sent,bytes_recv,send_rate_bps,recv_rate_bps,eth_name,eth_kind,eth_send_rate_bps,eth_recv_rate_bps,eth_link_mbps,processes:{cpu,ram,network}},"ts":...}`.
- **Live presence (Messenger-style):** `POST /heartbeat` and `POST /reports` (when `device_id` present) call `realtime.broadcast_presence(device_id, online=True, last_seen, pc_name)` so an open dashboard flips that PC's dot green instantly. The `broadcast_presence`/`update_presence` pair dedupes same-state flips. `realtime.py` keeps an in-process `_presence` map (`device_id -> {online,last_seen,pc_name}`); `presence_snapshot()` seeds newly-connected clients (notably **no initial fetch from Mongo** — the machine's known presence only reaches a fresh dashboard after a heartbeat/report from it, so a PC idle for >`ONLINE_TIMEOUT_SECONDS` starts grey until seen). The `presence.changed` payload goes out via the shared `_send` helper (never through `broadcast()`, which is `report.created`-only).
- **Live CPU / RAM / network / processes:** while `--watch` is running the agent sends a cheap sample every **5s** over `/ws/agent` (`{"type":"metrics", device_id, cpu_percent, ram_percent, ram_used, ram_total, bytes_sent, bytes_recv, send_rate_bps, recv_rate_bps, eth_name, eth_kind, eth_send_rate_bps, eth_recv_rate_bps, eth_link_mbps, cpu_name, cpu_brand, processes:{cpu,ram,network}}`). `live_metrics.py` uses non-blocking `psutil.cpu_percent(interval=None)` and rate-since-last-sample — no 3s network window. CPU **name/brand** are cached from registry/WMI once per process (not re-queried every 5s). Ethernet send/receive uses `net_io_counters(pernic=True)` on the preferred up physical NIC (skips loopback/virtual). `processes.py` with `interval=None` is also non-blocking. The API broadcasts `metrics.sample` to dashboard `/ws`. **Not stored in Mongo.** Full hourly reports (and Collect now) still persist snapshots, including `processes` and `cpu_name`.
- Dashboard `RealtimeProvider` (`src/components/realtime-provider.tsx`) holds one socket, reconnects with capped backoff, and invalidates `reports`/`reports-browse`/`report-pc` queries on each event — no manual Refresh needed. It keeps a live presence map and **client-side flips a dot to offline after `ONLINE_TIMEOUT_SECONDS` (300s)** of silence via per-device timers, so a machine that stops heartbeating goes red even without a server event (Messenger-style). `isOnline(deviceId)` and `lastSeenFor(deviceId, fallback)` feed the Fleet/Reports sidebar rows, report detail, `machine-detail` identity bar, and the **Overview** page totals/graphs. On `print.job` it invalidates `print-jobs`/`print-summary` so the Print Activity page updates live, and it bumps a per-device **`printing` badge** (60s window, `isPrinting(deviceId)`/`printingCount(deviceId)`) shown as an amber "printing"/"N prints" pill over the PC card in the Fleet + Reports sidebars (`printing-badge.tsx`). On `metrics.sample` it overlays **live CPU %, RAM %, NIC rates, Ethernet send/receive, and top processes** on Fleet/Reports sidebars, the selected PC Overview/Summary/Network cards, and the **Processes** tab (`metricsFor(deviceId)`). Samples are **not** written to Mongo. If no sample arrives for ~20s the UI falls back to the last saved report. The Overview network card keeps a client-side **Send/Receive sparkline** (~7 minutes of 5s samples, `metricsHistoryFor`). When a **live** sample has CPU or RAM **≥ 90%**, Fleet/Reports cards show a blinking red **CPU high** / **RAM high** / **CPU+RAM high** badge (`load-warning-badge.tsx`) and Overview CPU/RAM tiles switch the Live pill to blinking **High**. Hourly report values alone do not trigger the badge.
- Broadcasting is in-process (best-effort per uvicorn worker); the dashboard also refetches on reconnect so nothing is permanently lost.

### Print Activity (`/print-jobs`)

Desktops report **completed print jobs** so the dashboard shows who is printing what, live:

- **Desktop (`print_jobs.py`):** collects new completed print jobs with a persistent watermark (no duplicates).
  - **Windows:** `Microsoft-Windows-PrintService/Operational` Event ID **307** ("document printed") via PowerShell; watermark = last `RecordId`; parse document/user/printer/pages from the localized message.
  - **macOS:** tails `/var/log/cups/page_log`; watermark = latest completion column; fields printer/user/job/pages/title.
  - Every `--watch` cycle (**60s** heartbeat) also flushes any new print jobs to the API. `system-info --print-jobs` flushes on demand.
- **API:** `POST /print-jobs` (API key, batch `{device_id, pc_name, jobs:[{printer,document,user,pages,completed_at}]}`) stores in the Mongo `print_jobs` collection and broadcasts a **`print.job`** WS event per job; `GET /print-jobs?limit=&skip=&group_id=` (JWT, group-scoped for non-`super_admin`, newest first) returns `{total, skip, limit, jobs}` where `total` is the full match count; `GET /print-jobs/summary?hours=` (per-hour counts of the last N hours). `source_key` prefix stored like reports.
- **Dashboard:** `/print-jobs` page (slate+blue, sidebar + detail like Reports) with a **per-hour bar chart** (last 24h), a **prints-per-PC bar chart** (PC names on the X axis; pick a **group** to compare only that group's PCs, including zeros), **Most prints** / **Least prints** cards, live **recent-prints feed**, and stat cards (jobs / pages / printers). The **Recent prints** table is **paginated** (25 per page; Previous/Next; `GET /print-jobs?skip=&limit=`). The sidebar groups recent jobs **by PC** (newest group first) and has the same group filter; each group is **collapsible** and **expanded by default**. It shows the live **printing** badge when that PC is printing. Counts use the recent print-jobs feed (up to 500). The WS `print.job` event refreshes it with no manual refresh.

---

## Dashboard (`dashboard/`)

### Visual direction

Slate + blue: dark fleet sidebar (PC lists / filters), light detail panes.
The dark sidebar is **collapsible** on desktop (**«** in the sidebar header;
hamburger in the top bar brings it back). Default is **expanded**
(`collapsed = false`). On mobile it stays a slide-over. Page navigation lives
in the **sticky top bar** (not the sidebar). Avoid purple/glow themes.

### Routes

| Path | Purpose |
|------|---------|
| `/login` | Admin sign-in |
| `/overview` | **Overview** — live installed / online / offline counts + graphs (WebSocket) |
| `/graphs` | **Graphs** — live CPU %, RAM %, and network Mbps for every PC (WebSocket, last 15 min) |
| `/dashboard` | **Fleet** — sidebar PC list + live detail for selected machine |
| `/reports` | **Reports browser** — filters + one row per PC |
| `/reports/[key]` | PC detail from reports (encoded machine key) |
| `/api-keys` | Manage desktop API keys (create/copy/rename/toggle/delete) — **super admin only**; optionally link a key to a group (auto-assignment) |
| `/groups` | Create/rename/delete groups, assign PCs (one bucket per PC); manage **sub-categories** (many-to-many group membership); read-only for `user` role |
| `/users` | Manage dashboard users (role + groups) — **super admin only** |
| `/reports/export` | **Report export** — date presets + filters, CSV download |
| `/print-jobs` | **Print Activity** — live recent prints + per-hour chart (via WS) |

### Overview (`/overview`)

- Top-bar nav **Overview** (all roles). Live **installed / online / offline**
  counts for the current fleet (`groupMachines` from reports; a `user` only
  sees their groups). Group filter in the left list scopes the totals.
- Counts use the same live presence map as Fleet (`presence.changed` over
  dashboard `/ws`, plus `isOnline(deviceId) ?? latest.online`). New PCs
  (`report.created`) raise **installed**. Dots and totals flip without Refresh.
- Three stat cards: **Total installed**, **Total online**, **Total offline**.
  A donut shows online vs offline. An area chart records online/offline every
  **5s** and on each presence change (last **15 min**, client-side only — not
  stored in Mongo). LIVE badge matches Print Activity.
- Left list is online-first with status dots; rows link to `/reports/[key]`.

### Graphs (`/graphs`)

- Top-bar nav **Graphs** (all roles). Three live charts — **CPU usage**, **RAM
  usage**, **network usage** — one line per PC from `metrics.sample` (fallback
  to the last saved report). Client-side history is the last **15 minutes** at
  **5s**. Network is send+receive bit rate (Mbps) on the preferred NIC.
  Left list: **group filter**, **PC name filter**, and **PC picker** (All PCs
  or one machine). Click a PC row to graph only that machine; **← All PCs**
  in the detail header (or click the row again) returns to every line. On
  mobile, picking a PC closes the list drawer. Rows show live **printing**
  the same way as Fleet (amber badge for ~60s after `print.job`). Not stored
  in Mongo.

### Fleet (`/dashboard`)

- Sidebar: filter by name, select PC, Refresh, **group filter**, link to Reports. On mobile, picking a PC closes the list; **← PC list** in the detail header opens it again. Each PC row and the detail header show a **green (online) / red (offline)** status dot; data updates live via WebSocket. Each row also shows the desktop **App version** (`v0.2.21`) from the latest report when present. Live CPU/RAM ≥ **90%** shows a blinking red **CPU high** / **RAM high** / **CPU+RAM high** badge on the card (`load-warning-badge.tsx`). Windows that are **not licensed** show an amber activation badge (`activation-badge.tsx`). The detail identity bar lists Private IP, Public IP, MAC, **App version**, and **Windows** activation when present. For `admin`/`super_admin` the detail header has **Ping**, **Connect** (offline PCs), and **Collect now** (any OS) plus **Restart** / **Shut down** (Windows only). The sidebar footer **Connect all** (`admin`/`super_admin`) and **Update all apps** (`super_admin`) buttons are on **every** page (`DashboardShell`), not only Fleet. Connect all on Fleet sends `reconnect` to every PC in the current list. Update all apps pushes a `update` broadcast to every connected desktop app at once.
- Detail tabs (`machine-detail.tsx`): **Summary (default) / Overview / Printers / Uptime / Storage / Processes / Health / Emails**.
  - **Summary:** OS + Windows activation, total uptime + session, network total + bandwidth, full CPU spec (**name** like `AMD Ryzen 7 5800X 8-Core Processor` — not the vendor word `AMD` alone; **—** until a report has `cpu_name`), brand, arch/cores/clock), full RAM spec (total/available/free/swap + **bus speed** `ram_speed_mhz` + `ram_type`), storage health (SSD/HDD badge + brand, SMART, Healthy/Failing), battery health (condition, health %, cycle count), internet security, printers + total prints.
  - **Overview:** CPU/RAM/swap tiles, compact UptimeState (session + days tracked) + DiskState (devices/used/free), location/machine (incl. Windows activation), Battery stat card (laptops only), Network bandwidth chart, Printers, Security card.
  - **Printers:** stat cards (connected printers, total prints, avg prints/printer) + per-group lists (USB/Network/Other) with name, port, IP, print counts.
  - **Uptime:** session + UTC day bars with BD labels; day bars load in batches (default 14, Load more for the rest).
  - **Storage:** device count + partition bars (blue &lt;50%, amber 50–80%, red &gt;80%).
  - **Processes:** three lists (top CPU, top RAM, top network connections), updated live every **5s** over `/ws` while `--watch` is running (falls back to the last hourly/Collect snapshot). Network is open connection count, not per-process bytes. Idle/`kernel_task` omitted.
  - **Health:** storage health cards (SSD/HDD badge, SMART status, Internal/External, Healthy/Failing) + battery health (condition, health %, cycle count, max capacity).
- Shared detail UI: `src/components/dashboard/machine-detail.tsx`.

### Reports (`/reports`)

- Same slate+blue **sidebar + detail** layout as Fleet. On mobile, picking a PC closes the list; **← PC list** in the detail header opens it again.
- Sidebar filters: date from/to, PC name, country, OS, **group**, **sub-category** (scoped to linked groups), and **health** (disk health: healthy / has warning-failing; battery: has / none; min battery health %). Each row shows a **green (online) / red (offline)** dot that updates live.
- **Usage sort** (highest first): Most CPU, Most RAM, Most disk space used, Most network usage (bytes sent+recv), or Last seen.
- **Min thresholds**: Min CPU %, Min RAM %, Min disk % (filters out PCs below threshold).
- Sidebar lists matching PCs with CPU/RAM/Disk/Net; main pane shows `MachineDetail`.
- Permalink: `/reports/[key]`.

### Machine grouping (`groupMachines` in `src/lib/api.ts`)

Prevents duplicate fleet rows when old reports lack `device_id`:

1. Prefer **`device_id`**
2. Else **MAC** (primary + interfaces)
3. Else **pc_name / hostname**
4. **Merge** groups that share a MAC or the same name into the strongest identity

Keys look like `id:…`, `mac:…`, `name:…` (URL-encoded for `/reports/[key]`).

### Important ops note

Dashboard **Refresh** only reloads API data. It does **not** push collect commands to desktops. Use **Collect now** on a selected PC (admin) to push a `collect` command over `/ws/agent`. Use **Connect** on an offline PC (admin) to ask it to reopen `/ws/agent` if the desktop app is running with internet. Use **Connect all** in any page sidebar (`admin`/`super_admin`) to send that reconnect to the current list or the whole fleet. Use **Update all apps** (`super_admin`) from any page sidebar. New reports are pushed to open dashboards automatically over the WebSocket (no Refresh needed).


---

## Windows packaging (release updates)

See `desktop-app/packaging/windows/README.md`. Current desktop version: **0.2.26**.

Tag `v*` (or Actions → Windows Release) builds the exe + Inno installer and publishes a GitHub Release (`system-info.exe`, `SystemInfoSetup-<ver>.exe`, `release-manifest.json`). Render dashboard rebuilds only when `dashboard/**` or `render.yaml` change (`buildFilter`).

- **Product:** tray / installer name is **System Info Reporter**. Frozen
  `version.py` **must** include both `__version__` and `PRODUCT_NAME`. The
  GitHub Action stamp used to write version only, which crashed `--watch`
  (`ImportError: cannot import name 'PRODUCT_NAME'`). That was the 0.2.15
  Windows “starts then vanishes / no tray” bug. Current workflow stamps both
  via Python (`ascii`, no BOM). Watcher also falls back if `PRODUCT_NAME` is
  missing.
- **Installer (Inno Setup):** installs exe under `%LOCALAPPDATA%\SystemInfo`,
  writes `%APPDATA%\system-info\config.env`, then **always** launches
  `--watch` (`SW_SHOWNORMAL`, retries if the new exe is briefly locked). The
  finish-page **Start System Info Reporter now** checkbox is a retry (checked
  by default); a process mutex makes a second start a no-op. Start Menu
  shortcut always; optional desktop shortcut. Silent installs use the same
  post-install launch. No scheduled task — startup is HKCU Run (below).
- **PyInstaller:** `console=False`, `upx=False`, `collect_all` for `pystray` +
  Pillow + `websocket-client`, plus explicit `pystray._win32`. Frozen Windows
  with no one-shot flags defaults to `--watch` (double-click / Start Menu
  shows the tray).
- **Always-on watcher (`--watch`):** persistent tray icon (**Check for
  updates…**, **Restart**, **Exit**; left-click does not start an update). Heartbeat
  + print flush every **60s**, live CPU/RAM/network sample every **5s** over
  `/ws/agent`, full report hourly **on a side thread** so a slow Windows collect
  (WMI/printers/Outlook) never stalls heartbeats. Stays open until tray Exit.
  If the pystray message loop returns without Exit (Explorer restart, balloon
  timeout), the icon is **recreated** — the watcher does not exit.
  One named mutex (`Local\RGM.SystemInfoReporter.Watch`) so installer + Run
  key + shortcuts cannot stack copies. If the tray backend fails, the
  heartbeat loop **keeps running** and appends `%APPDATA%\system-info\crash.log`
  (frozen crashes also MessageBox that path). Tray **Restart** spawns a
  detached `--watch` and stops this instance.
- **Updates:** `SYSTEM_INFO_UPDATE_URL` JSON manifest. Tray **Check for
  updates…** and remote `update` use `apply_update_and_restart`: wait for PID,
  swap exe, PowerShell `Start-Process … --watch` so the **tray comes back**
  (cmd `start ""` from a `CREATE_NO_WINDOW` updater often never launched the
  new process). The hourly/startup full report **does not** apply+exit — that
  left Windows PCs dead after a few minutes when relaunch failed. Do not use
  stage-only `apply_windows_update` for the apply paths. Re-running the Inno
  installer **taskkill**s a live watcher before replacing the exe, then
  launches `--watch` again.
- **Auto-start on logon:** first run registers HKCU `...\Run` →
  `SystemInfoReporter` = `"system-info.exe" --watch`. Marker
  `%APPDATA%\system-info\startup-registered`. `SYSTEM_INFO_NO_STARTUP=1` skips.
  Uninstall removes Run value + marker + legacy scheduled tasks.

---

## Tests / verify

```bash
cd desktop-app && uv run pytest
cd api && uv run pytest
cd dashboard && pnpm build
```

After pulling API changes: restart `uv run sysinfo-api`, then run desktop with a valid API key and refresh the dashboard.

---

## Render deployment

See `docs/render-deploy.md` + `render.yaml` (blueprint) + `api/Dockerfile` + `dashboard/Dockerfile`.

- **API** (`api/Dockerfile`): `python:3.14-slim`, `uv sync --frozen`, uvicorn on `0.0.0.0:$PORT`. Requires MongoDB Atlas URI via `SYSTEM_INFO_MONGO_URI`.
- **Dashboard** (`dashboard/Dockerfile`): multi-stage `node:24` + pnpm; `NEXT_PUBLIC_API_URL` is a build arg (baked at build time). Runtime env: `API_URL`, `NEXT_PUBLIC_API_URL`, `AUTH_SECRET`, `NEXTAUTH_URL`.
- Both images tested locally with Docker (API `/health` responds, dashboard `/login` → 200).

---

## Specs written this cycle

- `docs/superpowers/specs/2026-08-12-multi-pc-monitoring-design.md`
- `docs/superpowers/specs/2026-08-12-printers-design.md`
- `docs/superpowers/specs/2026-08-12-network-printers-metrics-design.md`
- `docs/superpowers/specs/2026-08-12-uptime-bandwidth-design.md`
- `docs/superpowers/specs/2026-08-15-sub-categories-design.md`
- `docs/superpowers/plans/2026-08-12-multi-pc-monitoring.md`
- `docs/superpowers/plans/2026-08-12-uptime-bandwidth.md`
