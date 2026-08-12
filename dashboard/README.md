# Admin Dashboard (dashboard/)

Next.js 16 admin dashboard for the system-info API. Shows live charts of CPU /
RAM / swap usage and machine reports after login.

## Stack

- **Next.js 16** (App Router, Turbopack)
- **NextAuth v5 (beta)** — Credentials provider calling the API's `/auth/token`
- **TanStack Query v5** — data fetching + caching
- **Recharts v3** — line/bar charts
- Node **24**, **pnpm**

## Run

```bash
pnpm install
cp .env.local.example .env.local   # set the API URL
pnpm dev                            # http://localhost:3000
```

Login with the admin user seeded by the API
(`ADMIN_USERNAME` / `ADMIN_PASSWORD` in `api/.env`).

## Notes for Next 16

- `middleware.ts` is renamed to `proxy.ts` (not used here — routes are protected
  server-side via `auth()` redirects instead).
- Layout props are typed (`LayoutProps<"/">`).

## Scripts

```bash
pnpm dev      # dev server
pnpm build    # production build (typecheck included)
pnpm start    # serve production build
pnpm lint     # eslint
```