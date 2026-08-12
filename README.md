# Desktop Monitoring App

Monitors machine info (OS, IPs, MAC, geolocation, CPU/RAM, disk) and stores
reports via a FastAPI + MongoDB backend, with an admin web dashboard.

## Layout

```
desktop-app/   CLI that collects system info (macOS & Windows)
api/           FastAPI + MongoDB backend that stores the reports
dashboard/     Next.js admin dashboard (NextAuth + TanStack Query + charts)
```

## Stack

- **desktop-app** — Python 3.14 CLI (`psutil`, `requests`)
- **api** — FastAPI + MongoDB (JWT for admin, API keys for the client CLI)
- **dashboard** — Next.js 16, NextAuth v5, TanStack Query, Recharts
  (Node 24, pnpm)

## Quick start

### 1. API

```bash
cd api
uv sync
cp .env.example .env      # edit the MongoDB URI if needed
uv run sysinfo-api        # serves on http://127.0.0.1:8000
```

An admin user is seeded from `ADMIN_USERNAME`/`ADMIN_PASSWORD` in `.env`.

### 2. Desktop app

```bash
cd desktop-app
uv sync
uv run system-info --api-key sk-...   # collect + post report to API
uv run system-info --no-save          # just print, don't save
```

### 3. Dashboard

```bash
cd dashboard
cp .env.local.example .env.local      # set API_URL to point at the API
pnpm install
pnpm dev                              # serves on http://localhost:3000
```

Login with the admin user, then the dashboard plots CPU / RAM / swap usage and
machines over time, plus a report table.

## Auth model

- Desktop CLI authenticates to the API with an **API key** (`Authorization: Bearer sk-...`)
- Dashboard login uses **JWT** (`POST /api/auth/token`) via NextAuth Credentials
- Admin can create/revoke API keys from the API (`POST /api-keys`)

## Tests

```bash
cd desktop-app && uv run pytest
cd api && uv run pytest
cd dashboard && pnpm build      # typecheck + production build
```