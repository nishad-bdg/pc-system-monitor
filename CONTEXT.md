# Project context — Desktop Monitoring App

Last updated: 2026-08-13

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
| Desktop | Python 3.14, `psutil`, `requests`, `uv` |
| API | FastAPI, MongoDB, JWT + API keys, `uv` |
| Dashboard | Next.js 16, NextAuth v5, TanStack Query, Recharts, Tailwind, pnpm |

## Auth

- **Desktop → API:** `Authorization: Bearer sk-...` (API key). Create via `POST /api-keys` (admin JWT) or the dashboard `/api-keys` page. Full secret shown only once at create time (auto-generated `sk-`); can rename / toggle active / delete.
- **Roles:** `super_admin`, `admin`, `user` (see below).
- **Dashboard → API:** NextAuth Credentials → `POST /auth/token` → JWT stored on session as `apiToken`. If the API is restarted and the stored JWT is rejected (401 on `/reports`), **sign out and back in** to refresh the token.
- **Refresh tokens:** `POST /auth/token` also returns `refresh_token` (opaque, 30 days, stored hashed in Mongo `refresh_tokens` collection). `POST /auth/refresh` rotates it for a new access + refresh pair (old one revoked). `POST /auth/revoke` revokes a refresh token. The dashboard (`auth.ts`) stores the refresh token in the NextAuth JWT and silently calls `/auth/refresh` ~60s before the access token expires — no manual sign-in needed unless the refresh token itself is invalidated.
- **Password change:** `POST /auth/change-password` (JWT) takes `current_password` + `new_password` (min 6 chars); verifies current, updates the hash, and revokes **all** refresh tokens so other sessions must re-login. UI: `UserNav` in every sidebar footer — profile avatar + name + role badge with **Change password** + **Sign out** buttons (`user-nav.tsx`, modal).

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
- **Dashboard:** session carries `role` + `groups` (fetched from `/auth/me` at login); sidebar hides API Keys/Users unless `super_admin`; Groups page is read-only for `admin`/`user` (only `super_admin` can create/rename/delete groups/sub-categories or assign PCs).
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
uv run system-info --watch                   # always-on daemon (Windows messenger-style, tray Exit)
uv run system-info --pc-name Office-PC-3     # Windows custom name
uv run system-info --printers | --disk | --network | --sys | --security | --health | --emails
```

Env: `SYSTEM_INFO_API_URL`, `SYSTEM_INFO_API_KEY`, `SYSTEM_INFO_PC_NAME`.

### Online / offline status

- Each PC keeps its online status alive via heartbeats: the always-on Windows watcher (`--watch`) sends them roughly every 5 minutes (and `POST /heartbeat`); one-shot `--heartbeat` still works for manual/portable use.
- The API tracks `last_seen` per `device_id` in a `machines` Mongo collection; a machine is **online** if `last_seen` is within `SYSTEM_INFO_ONLINE_TIMEOUT_SECONDS` (default 300s).
- `GET /reports`, `GET /reports/{id}`, and `GET /reports/export` annotate every report with `online` (bool) + `last_seen`. Old reports without a `device_id` are marked offline.
- The dashboard shows a **green (online) / red (offline)** dot next to each PC in the Fleet sidebar, Reports browser, and detail header.

### Identity

- **`device_id`:** stable UUID from `device.py` (`get_or_create_device_id`), persisted in OS config dir (`~/.config/system-info/device.json` or `%APPDATA%/system-info`).
- **`pc_name`:**
  - **macOS:** always OS hostname (custom `--pc-name` ignored).
  - **Windows:** `--pc-name` / `SYSTEM_INFO_PC_NAME`, else hostname.

### Collected payload (full run)

| Field | Source | Notes |
|-------|--------|--------|
| `pc_name`, `device_id` | `device.py` | Always on save |
| `os` | `os_info.py` | Includes hostname |
| `private_ip`, `public_ip`, `mac_address`, `mac_addresses` | `ip.py` | |
| `location` | `geo.py` | ip-api.com |
| `resources` | `resources.py` | CPU/RAM/swap + laptop `battery` + RAM `ram_speed_mhz`/`ram_type` |
| `uptime` | `uptime.py` | Session + UTC day-wise on-seconds (`by_day`) |
| `network` | `network.py` | NIC totals/rates |

| `disk` | `disk.py` | Physical devices + partitions (mac + Win) |
| `printers` | `printers.py` | See below |
| `security` | `security.py` | Internet-security products, see below |
| `health` | `health.py` | Disk + battery health, see below |
| `email_accounts` | `email_accounts.py` | POP/IMAP accounts, see below |

### Battery (`resources.battery`)

Laptop only (`psutil.sensors_battery()`), `null` on desktops:

`battery: { percent, power_plugged, seconds_left }`.

### Internet Security (`security`)

Detects installed internet-security products:

- **Windows:** Security Center via `root/SecurityCenter2` (WMI `productState` bit 0x1000 = active); falls back to scanning running processes + Program Files dirs when Security Center is empty.
- **macOS:** scans `/Applications` + `~/Applications`, running processes, and launch agents/daemons for known vendors (McAfee, ESET, AVG, F-Secure, CrowdStrike, …); defaults to **XProtect** when nothing else is found.

`security: [{ name, status: "active" | "inactive" }]` (best-effort; can be `null`/`[]`).

### Health (`health`)

`health: { disk: [...], battery: {...} }`.

**Disk:** physical drives with media type + SMART status:

`{ name, device, media_type: "ssd" | "hdd" | "unknown", smart_status, internal, health: "ok" | "warning" | "fail" | "unknown", size_bytes }`

- Windows: `Get-PhysicalDisk` (FriendlyName/MediaType/HealthStatus/BusType/Size).
- macOS: `system_profiler SPStorageDataType -json`, physical drives de-duplicated by bsd base (`disk3s1s1` → `disk3`), capacity taken from the largest volume entry.
- The dashboard shows total storage (`size_bytes`, formatted) beside the drive name in the Summary + Health tabs.

**Battery (laptop):**

`{ cycle_count, condition, max_capacity_percent, health_percent }`

- Windows: `root/WMI` BatteryFullChargedCapacity / BatteryStaticData / BatteryCycleCount.
- macOS: `SPPowerDataType` (`sppower_battery_cycle_count`, `sppower_battery_health`, `sppower_battery_health_maximum_capacity` like `"82%"`).

### Printers

Grouped as **usb / network / other**.

Each printer: `{ name, port, ip, print_count }`.

- **ip:** extracted from network port/URI when IPv4 present; else `null`.
- **print_count:** best-effort (macOS IPP/`ipptool`; Windows `Get-PrinterProperty`); else `null`.
- macOS: CUPS `lpstat -v`; Windows: PowerShell `Get-Printer`.

### Network bandwidth

`network: { bytes_sent, bytes_recv, send_rate_bps, recv_rate_bps }` —
totals since boot + ~0.5s NIC sample rates (`psutil`).

### Uptime (day-wise)

`uptime: { boot_time, uptime_seconds, by_day: { "YYYY-MM-DD": seconds }, day_timezone: "UTC" }` —
agent accumulates on-seconds per UTC day in `uptime.json`; admin labels days in Asia/Dhaka (BD).

### Email accounts (`email_accounts`)

Detects POP/IMAP accounts configured in mail clients (address + server config only —
**passwords are encrypted in the OS keychain / credential manager and are not read**):

`email_accounts: { count, accounts: [{ client, email, username, full_name, protocol, incoming_host, incoming_port, outgoing_host, outgoing_port, security }] }`

- **Apple Mail (macOS):** `~/Library/Preferences/com.apple.mail.plist` (`MailAccounts` + `DeliveryAccounts` for SMTP).
- **Thunderbird (mac + Win):** `prefs.js` in each profile (`mail.account.*`, `mail.server.*.type|hostname|port|socketType`, `mail.identity.*.email`, SMTP via `mail.smtpserver.*`). `socketType`/`try_ssl` map to `none|starttls|ssl`.
- **Outlook for Mac:** account plists under `~/Library/Group Containers/UBF8T346G9.Office/Outlook/*/Accounts/`.
- **New Outlook (Win):** account JSON under `%LOCALAPPDATA%\Packages\Microsoft.OutlookForWindows_8wekyb3d8bbwe\LocalState`.
- **Classic Outlook (Win, best-effort):** `%APPDATA%\Microsoft\Outlook\outlook.xml` + registry profile blob string scan.

`client` is one of `apple_mail | thunderbird | outlook_mac | outlook_new | outlook_classic`.

---

## API (`api/`)

### Report model extras

Optional on `Report`: `pc_name`, `device_id`, `disk`, `printers`, `network`, `uptime`, `security`, `health`, `email_accounts` (plus original OS/IP/geo/resources).

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
- `POST /print-jobs` — API key; batch `{device_id, pc_name, jobs:[...]}` → Mongo `print_jobs` + WS `print.job`. `GET /print-jobs`, `GET /print-jobs/summary` — JWT (see Print Activity below).
- Auth, users, health — unchanged pattern.

### Realtime (`WebSocket /ws`, hi `--heartbeat`)

- **`POST /heartbeat`** (API key) — desktop pings with `{device_id, pc_name}`; records `last_seen` in the `machines` collection.
- **`GET/POST /reports`** — every saved report is annotated with `online` + `last_seen` and broadcasts a `report.created` event (full report incl. `printers`) over the WebSocket so the dashboard updates in realtime (print counts included).
- **`WebSocket /ws`** (`routes/realtime.py`) — the dashboard connects with its JWT passed as the WS **subprotocol** (or `?token=`); only `admin`/`super_admin` roles are allowed; `Origin` must match `CORS_ORIGINS`. On connect the server sends `{"type":"hello"}` then seeds `{"type":"presence.changed","presence":{device_id,online,last_seen,pc_name}}` for every known machine (in-process snapshot). Events: `{"type":"report.created","report":{...},"ts":...}`, `{"type":"presence.changed","presence":{...},"ts":...}`, and `{"type":"print.job","job":{...},"ts":...}`.
- **Live presence (Messenger-style):** `POST /heartbeat` and `POST /reports` (when `device_id` present) call `realtime.broadcast_presence(device_id, online=True, last_seen, pc_name)` so an open dashboard flips that PC's dot green instantly. The `broadcast_presence`/`update_presence` pair dedupes same-state flips. `realtime.py` keeps an in-process `_presence` map (`device_id -> {online,last_seen,pc_name}`); `presence_snapshot()` seeds newly-connected clients (notably **no initial fetch from Mongo** — the machine's known presence only reaches a fresh dashboard after a heartbeat/report from it, so a PC idle for >`ONLINE_TIMEOUT_SECONDS` starts grey until seen). The `presence.changed` payload goes out via the shared `_send` helper (never through `broadcast()`, which is `report.created`-only).
- Dashboard `RealtimeProvider` (`src/components/realtime-provider.tsx`) holds one socket, reconnects with capped backoff, and invalidates `reports`/`reports-browse`/`report-pc` queries on each event — no manual Refresh needed. It keeps a live presence map and **client-side flips a dot to offline after `ONLINE_TIMEOUT_SECONDS` (300s)** of silence via per-device timers, so a machine that stops heartbeating goes red even without a server event (Messenger-style). `isOnline(deviceId)` and `lastSeenFor(deviceId, fallback)` feed the Fleet/Reports sidebar rows, report detail, and `machine-detail` identity bar. On `print.job` it invalidates `print-jobs`/`print-summary` so the Print Activity page updates live.
- Broadcasting is in-process (best-effort per uvicorn worker); the dashboard also refetches on reconnect so nothing is permanently lost.

### Print Activity (`/print-jobs`)

Desktops report **completed print jobs** so the dashboard shows who is printing what, live:

- **Desktop (`print_jobs.py`):** collects new completed print jobs with a persistent watermark (no duplicates).
  - **Windows:** `Microsoft-Windows-PrintService/Operational` Event ID **307** ("document printed") via PowerShell; watermark = last `RecordId`; parse document/user/printer/pages from the localized message.
  - **macOS:** tails `/var/log/cups/page_log`; watermark = latest completion column; fields printer/user/job/pages/title.
  - Every `--watch` cycle (5-min on Windows) also flushes any new print jobs to the API, so activity shows within ~5 min. `system-info --print-jobs` flushes on demand.
- **API:** `POST /print-jobs` (API key, batch `{device_id, pc_name, jobs:[{printer,document,user,pages,completed_at}]}`) stores in the Mongo `print_jobs` collection and broadcasts a **`print.job`** WS event per job; `GET /print-jobs?limit=` (JWT, group-scoped for `user` role, newest first) and `GET /print-jobs/summary?hours=` (per-hour counts of the last N hours). `source_key` prefix stored like reports.
- **Dashboard:** `/print-jobs` page (slate+blue, sidebar + detail like Reports) with a **per-hour bar chart** (last 24h), live **recent-prints feed**, per-PC counts, and stat cards (jobs / pages / printers). The WS `print.job` event refreshes it with no manual refresh.

---

## Dashboard (`dashboard/`)

### Visual direction

Slate + blue: dark fleet sidebar, light detail panes. Avoid purple/glow themes.

### Routes

| Path | Purpose |
|------|---------|
| `/login` | Admin sign-in |
| `/dashboard` | **Fleet** — sidebar PC list + live detail for selected machine |
| `/reports` | **Reports browser** — filters + one row per PC |
| `/reports/[key]` | PC detail from reports (encoded machine key) |
| `/api-keys` | Manage desktop API keys (create/copy/rename/toggle/delete) — **super admin only**; optionally link a key to a group (auto-assignment) |
| `/groups` | Create/rename/delete groups, assign PCs (one bucket per PC); manage **sub-categories** (many-to-many group membership); read-only for `user` role |
| `/users` | Manage dashboard users (role + groups) — **super admin only** |
| `/reports/export` | **Report export** — date presets + filters, CSV download |
| `/print-jobs` | **Print Activity** — live recent prints + per-hour chart (via WS) |

### Fleet (`/dashboard`)

- Sidebar: filter by name, select PC, Refresh, **group filter**, link to Reports. Each PC row and the detail header show a **green (online) / red (offline)** status dot; data updates live via WebSocket.
- Detail tabs (`machine-detail.tsx`): **Summary (default) / Overview / Printers / Uptime / Storage / Health / Emails**.
  - **Summary:** total uptime + session, network total + bandwidth, full CPU spec (model/arch/cores/clock + **brand**), full RAM spec (total/available/free/swap + **bus speed** `ram_speed_mhz` + `ram_type`), storage health (SSD/HDD badge + brand, SMART, Healthy/Failing), battery health (condition, health %, cycle count), internet security, printers + total prints.
  - **Overview:** CPU/RAM/swap tiles, compact UptimeState (session + days tracked) + DiskState (devices/used/free), location/machine, Battery stat card (laptops only), Network bandwidth chart, Printers, Security card.
  - **Printers:** stat cards (connected printers, total prints, avg prints/printer) + per-group lists (USB/Network/Other) with name, port, IP, print counts.
  - **Uptime:** session + UTC day bars with BD labels; day bars load in batches (default 14, Load more for the rest).
  - **Storage:** device count + partition bars (blue &lt;50%, amber 50–80%, red &gt;80%).
  - **Health:** storage health cards (SSD/HDD badge, SMART status, Internal/External, Healthy/Failing) + battery health (condition, health %, cycle count, max capacity).
- Shared detail UI: `src/components/dashboard/machine-detail.tsx`.

### Reports (`/reports`)

- Same slate+blue **sidebar + detail** layout as Fleet.
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

Dashboard **Refresh** only reloads API data. It does **not** push collect commands to desktops. Re-run `system-info` on each PC for new snapshots. New reports are pushed to open dashboards automatically over the WebSocket (no Refresh needed).


---

## Windows packaging (release updates)

See `desktop-app/packaging/windows/README.md`.

- **Installer (Inno Setup):** installs exe under `%LOCALAPPDATA%\SystemInfo`, writes
  `%APPDATA%\system-info\config.env` (API URL/key/PC name/update URL), creates a
  **SystemInfoWatch** Task Scheduler job (runs `--watch` at every logon), and
  launches `--watch` right after install so the PC is online immediately.
- **Always-on watcher (`--watch`, messenger-style):** a single persistent
  background process (system-tray icon with **Exit**) that keeps the PC "online"
  (heartbeat ~ every 5 min), flushes new print jobs, and sends a **full report
  hourly**. It stays open until the user exits it from the tray — it does **not**
  exit after sending data. This replaces the old hourly `SystemInfoReport` +
  every-5-min `SystemInfoHeartbeat` scheduled tasks (one-shot `--heartbeat`
  still works for manual/portable use).
- **Auto-start on logon:** on the **first run** after install the app registers a
  `SystemInfoReporter` value under HKCU `...\CurrentVersion\Run` pointing to
  `system-info.exe --watch`, so the watcher restarts at login even without the
  scheduled task. Idempotent via the `startup-registered` marker file in
  `%APPDATA%\system-info`; set `SYSTEM_INFO_NO_STARTUP=1` to skip. Uninstall
  removes the Run value + marker + scheduled task.
- **Updates:** host a JSON release manifest (`SYSTEM_INFO_UPDATE_URL`); app checks
  on each run and stages a new exe (not live `git pull`).

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
