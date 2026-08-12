from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, db, security
from .routes import api_keys, auth, health, reports, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_admin()
    yield


def _cors_origins() -> list[str]:
    raw = config.CORS_ORIGINS
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(
    title="System Info API",
    description="Store and query system monitoring reports (macOS/Windows).",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(reports.router)
app.include_router(users.router)
app.include_router(api_keys.router)


def seed_admin() -> None:
    """Ensure the default admin user exists. No-op if Mongo is unreachable."""
    if db.find_user_by_username(config.ADMIN_USERNAME) is None:
        db.create_user(config.ADMIN_USERNAME, security.hash_password(config.ADMIN_PASSWORD), role="admin")


def main() -> None:
    import uvicorn

    seed_admin()
    uvicorn.run("sysinfo_api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()