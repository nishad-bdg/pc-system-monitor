# Deploy to Render

Two services, deployed with Docker:

| Service  | Image source          | Route              |
|----------|-----------------------|--------------------|
| API      | `api/Dockerfile`      | FastAPI + Mongo   |
| Dashboard| `dashboard/Dockerfile`| Next.js 16 (pnpm) |

## 1. Prerequisites

1. **MongoDB Atlas** (free M0 cluster). Generated connection string:
   `mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/`
2. Push this repo to **GitHub** and note `<owner>/<repo>`.

## 2. Configure `render.yaml` (one-time)

Edit `render.yaml` in the repo root:

- `repo: https://github.com/OWNER/REPO` → your repo (both services)
- `SYSTEM_INFO_MONGO_URI` → your Atlas connection string
- `ADMIN_PASSWORD` → a strong admin password
- Default service names: `sysinfo-api` and `sysinfo-dashboard`
  → if you change them, update `CORS_ORIGINS`, `API_URL`,
  `NEXT_PUBLIC_API_URL`, and `NEXTAUTH_URL` to the matching
  `https://<service>.onrender.com` URLs.

`JWT_SECRET` and `AUTH_SECRET` use `generateValue` (auto-generated on Render).

## 3. Deploy

1. Render dashboard → **New → Blueprint** → pick the repo.
2. Render reads `render.yaml`, creates both web services, and builds the
   two Docker images. First deploy takes a few minutes.
3. Open `https://sysinfo-api.onrender.com/health` — expect
   `{"status":"ok","mongo":true}`.
4. Open `https://sysinfo-dashboard.onrender.com/login` and sign in with
   `ADMIN_USERNAME` / `ADMIN_PASSWORD`.

## 4. Point desktop clients at the deployed API

```bash
export SYSTEM_INFO_API_URL=https://sysinfo-api.onrender.com
export SYSTEM_INFO_API_KEY=sk-...        # create in dashboard → API Keys
uv run system-info
```

Or bake it into the Windows installer's `config.env`
(`desktop-app/packaging/windows/README.md`).

## 5. Verifying again after changes

```bash
docker build --build-arg NEXT_PUBLIC_API_URL=https://sysinfo-api.onrender.com -t dash ./dashboard
docker run --rm -p 3000:3000 -e API_URL=https://sysinfo-api.onrender.com \
  -e NEXT_PUBLIC_API_URL=https://sysinfo-api.onrender.com \
  -e NEXTAUTH_URL=http://localhost:3000 \
  -e AUTH_SECRET=$(openssl rand -base64 32) dash
```

## Notes

- `NEXT_PUBLIC_API_URL` is baked into the dashboard JS at **build time**, so
  re-deploy the dashboard (changes to `render.yaml` or code) whenever the API
  URL changes.
- The API binds `0.0.0.0` on Render's injected `$PORT` (default 8000).
- Render free services sleep when idle; first request after sleep takes a few
  seconds to wake up.