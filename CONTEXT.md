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
| `admin` | ❌ | ❌ | ✅ CRUD | ✅ all |
| `user` | ❌ | ❌ | 🔍 own only | ✅ own groups only |

- Seed `ADMIN_USERNAME`/`ADMIN_PASSWORD` is auto-created (and legacy `admin` promoted) to `super_admin` on startup.
- **Users page** (`/users`, super admin only): create users with a role + a set of groups (multi-select). One user can belong to **multiple groups** and then sees every PC in each assigned group. `PATCH /users/{id}` edits role/groups/password (can't change your own role); deleting yourself is blocked.
- **Group scoping is enforced server-side**: for a `user`, `GET /reports`, `/reports/export`, and `/reports/{id}` are filtered to the user's groups; `GET /groups` returns only their groups. `admin`/`super_admin` are unrestricted.
- **API keys** (`/api-keys` page + routes) are **super admin only** (403 otherwise).
- **Dashboard:** session carries `role` + `groups` (fetched from `/auth/me` at login); sidebar hides API Keys/Users unless `super_admin`; Groups page is read-only for `user`.
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
uv run system-info --pc-name Office-PC-3     # Windows custom name
uv run system-info --printers | --disk | --network | --sys | --security | --health
```

Env: `SYSTEM_INFO_API_URL`, `SYSTEM_INFO_API_KEY`, `SYSTEM_INFO_PC_NAME`.

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

`{ name, device, media_type: "ssd" | "hdd" | "unknown", smart_status, internal, health: "ok" | "warning" | "fail" | "unknown" }`

- Windows: `Get-PhysicalDisk` (FriendlyName/MediaType/HealthStatus/BusType).
- macOS: `system_profiler SPStorageDataType -json`, physical drives de-duplicated by bsd base (`disk3s1s1` → `disk3`).

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

---

## API (`api/`)

### Report model extras

Optional on `Report`: `pc_name`, `device_id`, `disk`, `printers`, `network`, `uptime`, `security`, `health` (plus original OS/IP/geo/resources).

### `GET /reports` query params

| Param | Behavior |
|-------|----------|
| `limit` | 1–500 |
| `device_id` | Exact match |
| `pc_name` | Case-insensitive contains on `pc_name` **or** `os.hostname` |
| `from_ts`, `to_ts` | Unix seconds on `created_at` |
| `country` | Regex on `location.country` or `location.country_code` |
| `os` | Regex on `os.system` |

Sorted by `created_at` **descending** (newest first). Auth: admin JWT.

### Other routes

- `POST /reports` — API key; stores `source_key` prefix.
- `GET /reports/{id}` — JWT.
- `GET /reports/export` — JWT; same filters as `/reports` plus `group_id`; streams CSV with **every report field flattened** (`a.b.c` columns, arrays as JSON).
- `GET/POST/PATCH/DELETE /api-keys` — admin JWT; `PATCH` renames / toggles active; secret shown only at create.
- `GET/POST/PATCH/DELETE /groups` — admin JWT; a machine key belongs to **one group only** (assigning removes it from others).
- Auth, users, health — unchanged pattern.

`GET /reports` also accepts `group_id` (matches machine keys `id:`/`mac:`/`name:` in the group).

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
| `/api-keys` | Manage desktop API keys (create/copy/rename/toggle/delete) — **super admin only** |
| `/groups` | Create/rename/delete groups, assign PCs (one group per PC); read-only for `user` role |
| `/users` | Manage dashboard users (role + groups) — **super admin only** |
| `/reports/export` | **Report export** — date presets + filters, CSV download |

### Fleet (`/dashboard`)

- Sidebar: filter by name, select PC, Refresh, **group filter**, link to Reports.
- Detail tabs (`machine-detail.tsx`): **Summary (default) / Overview / Printers / Uptime / Storage / Health**.
  - **Summary:** total uptime + session, network total + bandwidth, full CPU spec (model/arch/cores/clock + **brand**), full RAM spec (total/available/free/swap + **bus speed** `ram_speed_mhz` + `ram_type`), storage health (SSD/HDD badge + brand, SMART, Healthy/Failing), battery health (condition, health %, cycle count), internet security, printers + total prints.
  - **Overview:** CPU/RAM/swap tiles, compact UptimeState (session + days tracked) + DiskState (devices/used/free), location/machine, Battery stat card (laptops only), Network bandwidth chart, Printers, Security card.
  - **Printers:** stat cards (connected printers, total prints, avg prints/printer) + per-group lists (USB/Network/Other) with name, port, IP, print counts.
  - **Uptime:** session + UTC day bars with BD labels; day bars load in batches (default 14, Load more for the rest).
  - **Storage:** device count + partition bars (blue &lt;50%, amber 50–80%, red &gt;80%).
  - **Health:** storage health cards (SSD/HDD badge, SMART status, Internal/External, Healthy/Failing) + battery health (condition, health %, cycle count, max capacity).
- Shared detail UI: `src/components/dashboard/machine-detail.tsx`.

### Reports (`/reports`)

- Same slate+blue **sidebar + detail** layout as Fleet.
- Sidebar filters: date from/to, PC name, country, OS, **group**.
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

Dashboard **Refresh** only reloads API data. It does **not** push collect commands to desktops. Re-run `system-info` on each PC for new snapshots.


---

## Windows packaging (release updates)

See `desktop-app/packaging/windows/README.md`.

- **Installer (Inno Setup):** installs exe under `%LOCALAPPDATA%\SystemInfo`, writes
  `%APPDATA%\system-info\config.env` (API URL/key/PC name/update URL), creates
  Task Scheduler job **SystemInfoReport** every hour.
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
- `docs/superpowers/plans/2026-08-12-multi-pc-monitoring.md`
- `docs/superpowers/plans/2026-08-12-uptime-bandwidth.md`
