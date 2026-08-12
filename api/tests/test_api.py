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
    monkeypatch.setattr(db, "list_reports", lambda limit=20: [])
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
    resp = client.post(
        "/reports",
        json={"os": {"system": "Darwin"}, "public_ip": "8.8.8.8"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert resp.status_code == 201
    assert "id" in resp.json()


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