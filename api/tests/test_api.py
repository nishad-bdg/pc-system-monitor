from fastapi.testclient import TestClient

from sysinfo_api import db, security
from sysinfo_api.main import app

client = TestClient(app)


def _patch_db(monkeypatch, user=None):
    user = user or {
        "_id": "64b000000000000000000001",
        "username": "admin",
        "role": "admin",
    }
    monkeypatch.setattr(db, "save_report", lambda doc: "64b00000000000000000000a")

    def fake_find_user(username):
        return dict(user) if username == user.get("username") else None

    monkeypatch.setattr(db, "find_user_by_username", fake_find_user)
    monkeypatch.setattr(db, "get_user_by_id", lambda uid: dict(user) if uid == user["_id"] else None)
    monkeypatch.setattr(
        db,
        "list_reports",
        lambda limit=20, device_id=None, pc_name=None, from_ts=None, to_ts=None, country=None, os_name=None: [],
    )
    monkeypatch.setattr(db, "get_report", lambda rid: None)
    monkeypatch.setattr(db, "list_users", lambda: [dict(user)])
    monkeypatch.setattr(db, "list_api_keys", lambda: [])


def _auth_header(sub="64b000000000000000000001", role="admin"):
    from datetime import datetime, timedelta, timezone
    import jwt as pyjwt
    from sysinfo_api import config
    payload = {"sub": sub, "role": role, "exp": datetime.now(timezone.utc) + timedelta(minutes=10)}
    token = pyjwt.encode(payload, config.JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


# ---- health ----

def test_health_degraded(monkeypatch):
    monkeypatch.setattr(db, "ping", lambda: False)
    resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json()["mongo"] is False


def test_health_ok(monkeypatch):
    monkeypatch.setattr(db, "ping", lambda: True)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---- JWT login ----

def test_login_success(monkeypatch):
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "admin",
        "role": "admin",
        "password_hash": security.hash_password("secret"),
    })
    resp = client.post("/auth/token", data={"username": "admin", "password": "secret"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password(monkeypatch):
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "admin",
        "role": "admin",
        "password_hash": security.hash_password("secret"),
    })
    resp = client.post("/auth/token", data={"username": "admin", "password": "nope"})
    assert resp.status_code == 401


def test_auth_me(monkeypatch):
    _patch_db(monkeypatch)
    resp = client.get("/auth/me", headers=_auth_header())
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


def test_auth_me_invalid_token(monkeypatch):
    _patch_db(monkeypatch)
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


# ---- reports require API key for create ----

def test_create_report_missing_key(monkeypatch):
    _patch_db(monkeypatch)
    resp = client.post("/reports", json={"os": {"system": "Darwin"}})
    assert resp.status_code == 401


def test_create_report_with_api_key(monkeypatch):
    _patch_db(monkeypatch)
    key = security.generate_api_key()
    monkeypatch.setattr(db, "find_api_key_by_hash", lambda h: {"_id": "x", "prefix": key[:20], "active": True})
    saved = {}

    def capture(doc):
        saved.update(doc)
        return "64b00000000000000000000a"

    monkeypatch.setattr(db, "save_report", capture)
    resp = client.post(
        "/reports",
        json={
            "os": {"system": "Darwin"},
            "public_ip": "8.8.8.8",
            "pc_name": "MacBook-Pro",
            "device_id": "dev-1",
            "uptime": {
                "boot_time": 1.0,
                "uptime_seconds": 3600.0,
                "by_day": {"2026-08-12": 3600.0},
                "day_timezone": "UTC",
            },
            "network": {
                "bytes_sent": 100,
                "bytes_recv": 200,
                "send_rate_bps": 10,
                "recv_rate_bps": 20,
            },
        },
        headers={"Authorization": f"Bearer {key}"},
    )
    assert resp.status_code == 201
    assert "id" in resp.json()
    assert saved["pc_name"] == "MacBook-Pro"
    assert saved["device_id"] == "dev-1"
    assert saved["uptime"]["by_day"]["2026-08-12"] == 3600.0


def test_list_reports_passes_filters(monkeypatch):
    _patch_db(monkeypatch)
    seen = {}

    def fake_list(
        limit=20,
        device_id=None,
        pc_name=None,
        from_ts=None,
        to_ts=None,
        country=None,
        os_name=None,
    ):
        seen["limit"] = limit
        seen["device_id"] = device_id
        seen["pc_name"] = pc_name
        seen["from_ts"] = from_ts
        seen["to_ts"] = to_ts
        seen["country"] = country
        seen["os_name"] = os_name
        return [
            {
                "_id": "1",
                "pc_name": "Office-PC-3",
                "device_id": "dev-2",
                "created_at": 1.0,
            }
        ]

    monkeypatch.setattr(db, "list_reports", fake_list)
    resp = client.get(
        "/reports?device_id=dev-2&pc_name=Office&limit=50"
        "&from_ts=100&to_ts=200&country=BD&os=Darwin",
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    assert seen == {
        "limit": 50,
        "device_id": "dev-2",
        "pc_name": "Office",
        "from_ts": 100.0,
        "to_ts": 200.0,
        "country": "BD",
        "os_name": "Darwin",
    }
    assert resp.json()["total"] == 1
    assert resp.json()["reports"][0]["pc_name"] == "Office-PC-3"


def test_create_report_invalid_api_key(monkeypatch):
    _patch_db(monkeypatch)
    monkeypatch.setattr(db, "find_api_key_by_hash", lambda h: None)
    resp = client.post(
        "/reports",
        json={"os": {}},
        headers={"Authorization": "Bearer sk-not-real"},
    )
    assert resp.status_code == 401


def test_create_report_mongo_down(monkeypatch):
    _patch_db(monkeypatch)
    key = security.generate_api_key()
    monkeypatch.setattr(db, "find_api_key_by_hash", lambda h: {"_id": "x", "prefix": key[:20], "active": True})
    monkeypatch.setattr(db, "save_report", lambda doc: None)
    resp = client.post(
        "/reports",
        json={"os": {}},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert resp.status_code == 503


# ---- report reads require JWT ----

def test_list_reports_requires_jwt(monkeypatch):
    _patch_db(monkeypatch)
    resp = client.get("/reports")
    assert resp.status_code == 401


def test_list_reports_with_jwt(monkeypatch):
    _patch_db(monkeypatch)
    resp = client.get("/reports", headers=_auth_header())
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_get_report_not_found(monkeypatch):
    _patch_db(monkeypatch)
    resp = client.get("/reports/64b0000000000000000000ff", headers=_auth_header())
    assert resp.status_code == 404


# ---- api keys admin ----

def test_create_api_key_requires_jwt(monkeypatch):
    _patch_db(monkeypatch)
    resp = client.post("/api-keys", json={"name": "desktop-1"})
    assert resp.status_code == 401


def test_create_api_key(monkeypatch):
    _patch_db(monkeypatch)
    monkeypatch.setattr(db, "create_api_key", lambda name, kh, prefix: "64b00000000000000000000b")
    resp = client.post("/api-keys", json={"name": "desktop-1"}, headers=_auth_header())
    assert resp.status_code == 201
    body = resp.json()
    assert body["api_key"].startswith("sk-")


def test_list_users(monkeypatch):
    _patch_db(monkeypatch)
    resp = client.get("/users", headers=_auth_header())
    assert resp.status_code == 200
    assert resp.json()[0]["username"] == "admin"
