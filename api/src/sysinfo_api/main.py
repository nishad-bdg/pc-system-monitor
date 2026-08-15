from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, db, security
from .routes import (
    api_keys,
    auth,
    groups,
    health,
    print_jobs,
    realtime,
    reports,
    sub_categories,
    users,
)


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
app.include_router(groups.router)
app.include_router(sub_categories.router)
app.include_router(print_jobs.router)
app.include_router(realtime.router)


def seed_admin() -> None:
    """Ensure the default admin user exists as super_admin. No-op if Mongo is unreachable."""
    user = db.find_user_by_username(config.ADMIN_USERNAME)
    if user is None:
        db.create_user(
            config.ADMIN_USERNAME,
            security.hash_password(config.ADMIN_PASSWORD),
            role=security.ROLE_SUPER_ADMIN,
        )
    elif user.get("role") != security.ROLE_SUPER_ADMIN:
        # Promote the legacy seeded admin so it keeps full control.
        db.update_user(str(user["_id"]), role=security.ROLE_SUPER_ADMIN)

    # Also promote a legacy username "admin" that predates the role system, so
    # the original default login keeps full (super admin) control even if
    # ADMIN_USERNAME was customized to something else later.
    if config.ADMIN_USERNAME != "admin":
        legacy = db.find_user_by_username("admin")
        if legacy and legacy.get("role") != security.ROLE_SUPER_ADMIN:
            db.update_user(str(legacy["_id"]), role=security.ROLE_SUPER_ADMIN)


def main() -> None:
    import uvicorn

    seed_admin()
    uvicorn.run("sysinfo_api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()