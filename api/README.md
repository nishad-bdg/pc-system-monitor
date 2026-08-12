# System Info API

FastAPI + MongoDB backend for the desktop client. Stores each machine's
report (OS, IPs, MAC, geolocation, resources, disk) in MongoDB.

## Authentication

Two auth mechanisms are supported:

- **API key** for the desktop client (machine-to-machine). A key is generated
  in the admin dashboard and sent as
  `Authorization: Bearer sk-...` when the CLI posts a report.
  Keys are hashed (SHA-256) at rest in Mongo.
- **JWT (OAuth2 password flow)** for the admin dashboard. Log in with
  `POST /auth/token` to get an expiring bearer token (bcrypt-hashed users).

`/health` is public. Everything else requires auth.

## Run

```bash
uv run sysinfo-api        # serves on http://127.0.0.1:8000
```

Requires MongoDB running locally (default `mongodb://localhost:27017`).

Configuration goes in `api/.env` (copy from `api/.env.example`):

```
SYSTEM_INFO_MONGO_URI=mongodb://localhost:27017
SYSTEM_INFO_MONGO_DB=system_info
JWT_SECRET=use-a-random-32+char-secret
JWT_EXPIRE_MINUTES=60
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
```

An admin user is seeded on startup from `ADMIN_USERNAME`/`ADMIN_PASSWORD`.

`.env` is git-ignored; commit only `.env.example`.

## Endpoints

| Method | Path                | Auth        | Description                               |
|--------|---------------------|-------------|-------------------------------------------|
| GET    | `/health`           | public      | Liveness + MongoDB reachability           |
| POST   | `/auth/token`       | form        | Login -> JWT access token                 |
| GET    | `/auth/me`          | JWT         | Current admin user                        |
| POST   | `/reports`          | API key     | Save a report document                    |
| GET    | `/reports`          | JWT         | List recent reports (`?limit=`)           |
| GET    | `/reports/{id}`     | JWT         | Fetch a single report by ObjectId         |
| GET    | `/users`            | JWT         | List users                                |
| POST   | `/users`            | JWT         | Create a user                             |
| DELETE | `/users/{id}`       | JWT         | Delete a user                             |
| GET    | `/api-keys`         | JWT         | List API keys                             |
| POST   | `/api-keys`         | JWT         | Create an API key (returns `sk-...`)      |
| DELETE | `/api-keys/{id}`    | JWT         | Delete/revoke an API key                  |

## Desktop client

```bash
cd ../desktop-app
uv run system-info --api-key sk-...        # posts report using the key
```

## Tests

```bash
uv run pytest
```
