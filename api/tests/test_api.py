from fastapi.testclient import TestClient

from sysinfo_api import db, security
from sysinfo_api.main import app

client = TestClient(app)


_REFRESH_STORE: dict[str, dict] = {}


def _patch_db(monkeypatch, user=None):
    user = user or {
        "_id": "64b000000000000000000001",
        "username": "admin",
        "role": "admin",
        "groups": [],
    }
    monkeypatch.setattr(db, "save_report", lambda doc: "64b00000000000000000000a")

    def fake_find_user(username):
        return dict(user) if username == user.get("username") else None

    monkeypatch.setattr(db, "find_user_by_username", fake_find_user)
    monkeypatch.setattr(db, "get_user_by_id", lambda uid: dict(user) if uid == user["_id"] else None)
    monkeypatch.setattr(
        db,
        "list_reports",
        lambda limit=20, device_id=None, pc_name=None, from_ts=None, to_ts=None, country=None, os_name=None, group_id=None, group_ids=None, disk_health=None, battery=None, battery_health_min=None: [],
    )
    monkeypatch.setattr(db, "get_report", lambda rid: None)
    monkeypatch.setattr(db, "list_users", lambda: [dict(user)])
    monkeypatch.setattr(db, "list_api_keys", lambda: [])
    monkeypatch.setattr(db, "list_groups", lambda: [])
    monkeypatch.setattr(db, "create_user", lambda *a, **k: True)
    monkeypatch.setattr(db, "update_user", lambda *a, **k: True)
    monkeypatch.setattr(db, "delete_user", lambda uid: True)
    monkeypatch.setattr(db, "touch_machine", lambda device_id, pc_name=None, seen_at=None: True)
    monkeypatch.setattr(db, "get_machine_seen_at", lambda device_id: 2_000_000_000.0)
    monkeypatch.setattr(db, "machines_seen_map", lambda: {})

    # Reset in-process WebSocket presence cache so tests stay isolated.
    from sysinfo_api import realtime as _rt

    _rt._clients.clear()
    _rt._presence.clear()

    # Refresh-token store: in-memory, shared across tests in this module.
    global _REFRESH_STORE
    _REFRESH_STORE.clear()

    def fake_save(token_hash, user_id, expires_at):
        _REFRESH_STORE[token_hash] = {"token_hash": token_hash, "user_id": user_id, "expires_at": expires_at, "revoked": False}
        return True

    def fake_find(token_hash):
        rec = _REFRESH_STORE.get(token_hash)
        return dict(rec) if rec else None

    def fake_revoke(token_hash):
        if token_hash in _REFRESH_STORE:
            _REFRESH_STORE[token_hash]["revoked"] = True
            return True
        return False

    monkeypatch.setattr(db, "save_refresh_token", fake_save)
    monkeypatch.setattr(db, "find_refresh_token", fake_find)
    monkeypatch.setattr(db, "revoke_refresh_token", fake_revoke)
    monkeypatch.setattr(db, "revoke_all_refresh_tokens_for_user", lambda uid: True)

    def _current_store():
        return _REFRESH_STORE

    monkeypatch.setattr(db, "get_refresh_store", _current_store)

    # Password helpers.
    monkeypatch.setattr(db, "update_user_password", lambda uid, h: True)
    monkeypatch.setattr(
        db, "get_user_password_hash", lambda uid: user["password_hash"] if user else None
    )


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
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


def test_login_wrong_password(monkeypatch):
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "admin",
        "role": "admin",
        "password_hash": security.hash_password("secret"),
    })
    resp = client.post("/auth/token", data={"username": "admin", "password": "nope"})
    assert resp.status_code == 401


def test_refresh_success(monkeypatch):
    import hashlib
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "admin",
        "role": "admin",
        "password_hash": security.hash_password("secret"),
    })
    login = client.post("/auth/token", data={"username": "admin", "password": "secret"}).json()
    first_refresh = login["refresh_token"]
    first_hash = hashlib.sha256(first_refresh.encode()).hexdigest()

    resp = client.post("/auth/refresh", json={"refresh_token": first_refresh})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    # Rotation: the old token is now revoked.
    from sysinfo_api import db as d
    assert d.get_refresh_store()[first_hash]["revoked"] is True


def test_refresh_invalid_token(monkeypatch):
    _patch_db(monkeypatch)
    resp = client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert resp.status_code == 401


def test_refresh_revoked_token(monkeypatch):
    import hashlib
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "admin",
        "role": "admin",
        "password_hash": security.hash_password("secret"),
    })
    login = client.post("/auth/token", data={"username": "admin", "password": "secret"}).json()
    refresh = login["refresh_token"]
    # Revoke it, then try to use it.
    client.post("/auth/revoke", json={"refresh_token": refresh}, headers=_auth_header())
    resp = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 401


def test_revoke(monkeypatch):
    import hashlib
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "admin",
        "role": "admin",
        "password_hash": security.hash_password("secret"),
    })
    login = client.post("/auth/token", data={"username": "admin", "password": "secret"}).json()
    refresh = login["refresh_token"]
    resp = client.post("/auth/revoke", json={"refresh_token": refresh}, headers=_auth_header())
    assert resp.status_code == 200
    from sysinfo_api import db as d
    store = d.get_refresh_store()
    h = hashlib.sha256(refresh.encode()).hexdigest()
    assert store[h]["revoked"] is True


# ---- password change ----

def test_change_password_success(monkeypatch):
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "admin",
        "role": "admin",
        "password_hash": security.hash_password("oldpass"),
    })
    resp = client.post("/auth/change-password", json={
        "current_password": "oldpass",
        "new_password": "newpass99",
    }, headers=_auth_header())
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_change_password_wrong_current(monkeypatch):
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "admin",
        "role": "admin",
        "password_hash": security.hash_password("oldpass"),
    })
    resp = client.post("/auth/change-password", json={
        "current_password": "wrong",
        "new_password": "newpass99",
    }, headers=_auth_header())
    assert resp.status_code == 401


def test_change_password_short(monkeypatch):
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "admin",
        "role": "admin",
        "password_hash": security.hash_password("oldpass"),
    })
    resp = client.post("/auth/change-password", json={
        "current_password": "oldpass",
        "new_password": "abc",
    }, headers=_auth_header())
    assert resp.status_code == 400


def test_change_password_requires_auth(monkeypatch):
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "admin",
        "role": "admin",
        "password_hash": security.hash_password("oldpass"),
    })
    resp = client.post("/auth/change-password", json={
        "current_password": "oldpass",
        "new_password": "newpass99",
    })
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
            "security": {
                "count": 1,
                "installed": [
                    {"name": "Windows Defender", "vendor": "Windows Defender", "active": True}
                ],
                "platform": "windows",
            },
        },
        headers={"Authorization": f"Bearer {key}"},
    )
    assert resp.status_code == 201
    assert "id" in resp.json()
    assert saved["pc_name"] == "MacBook-Pro"
    assert saved["device_id"] == "dev-1"
    assert saved["uptime"]["by_day"]["2026-08-12"] == 3600.0
    assert saved["security"]["count"] == 1
    assert saved["security"]["installed"][0]["name"] == "Windows Defender"


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
        group_id=None,
        group_ids=None,
        disk_health=None,
        battery=None,
        battery_health_min=None,
    ):
        seen["limit"] = limit
        seen["device_id"] = device_id
        seen["pc_name"] = pc_name
        seen["from_ts"] = from_ts
        seen["to_ts"] = to_ts
        seen["country"] = country
        seen["os_name"] = os_name
        seen["group_id"] = group_id
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
        "group_id": None,
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


def test_list_reports_with_group_id(monkeypatch):
    _patch_db(monkeypatch)
    seen = {}
    monkeypatch.setattr(db, "get_group", lambda gid: {"_id": gid, "name": "Ops", "machine_keys": ["id:dev-1"]})

    def fake_list(
        limit=20,
        device_id=None,
        pc_name=None,
        from_ts=None,
        to_ts=None,
        country=None,
        os_name=None,
        group_id=None,
        group_ids=None,
        disk_health=None,
        battery=None,
        battery_health_min=None,
    ):
        seen["group_id"] = group_id
        return []

    monkeypatch.setattr(db, "list_reports", fake_list)
    resp = client.get("/reports?group_id=64b00000000000000000000c", headers=_auth_header())
    assert resp.status_code == 200
    assert seen["group_id"] == "64b00000000000000000000c"


def test_list_reports_user_role_scoped_by_groups(monkeypatch):
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "ops1",
        "role": "user",
        "groups": ["g1", "g2"],
    })
    seen = {}

    def fake_list(
        limit=20,
        device_id=None,
        pc_name=None,
        from_ts=None,
        to_ts=None,
        country=None,
        os_name=None,
        group_id=None,
        group_ids=None,
        disk_health=None,
        battery=None,
        battery_health_min=None,
    ):
        seen["group_ids"] = group_ids
        return []

    monkeypatch.setattr(db, "list_reports", fake_list)
    resp = client.get("/reports", headers=_auth_header())
    assert resp.status_code == 200
    assert seen["group_ids"] == ["g1", "g2"]


def test_list_reports_user_role_no_groups_returns_empty(monkeypatch):
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "ops1",
        "role": "user",
        "groups": [],
    })
    seen = {}

    def fake_list(
        limit=20,
        device_id=None,
        pc_name=None,
        from_ts=None,
        to_ts=None,
        country=None,
        os_name=None,
        group_id=None,
        group_ids=None,
        disk_health=None,
        battery=None,
        battery_health_min=None,
    ):
        seen["group_ids"] = group_ids
        return []

    monkeypatch.setattr(db, "list_reports", fake_list)
    resp = client.get("/reports", headers=_auth_header())
    assert resp.status_code == 200
    assert seen["group_ids"] == []


def test_list_reports_health_filters_passed(monkeypatch):
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
        group_id=None,
        group_ids=None,
        disk_health=None,
        battery=None,
        battery_health_min=None,
    ):
        seen["disk_health"] = disk_health
        seen["battery"] = battery
        seen["battery_health_min"] = battery_health_min
        return []

    monkeypatch.setattr(db, "list_reports", fake_list)
    resp = client.get(
        "/reports?disk_health=problem&battery=has&battery_health_min=80",
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    assert seen["disk_health"] == "problem"
    assert seen["battery"] == "has"
    assert seen["battery_health_min"] == 80.0


def test_list_groups_user_sees_only_own(monkeypatch):
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "ops1",
        "role": "user",
        "groups": ["g1"],
    })
    monkeypatch.setattr(
        db,
        "list_groups",
        lambda: [
            {"_id": "g1", "name": "Ops", "machine_keys": [], "created_at": 1.0},
            {"_id": "g2", "name": "Sales", "machine_keys": [], "created_at": 1.0},
        ],
    )
    resp = client.get("/groups", headers=_auth_header())
    assert resp.status_code == 200
    body = resp.json()
    assert [g["id"] for g in body] == ["g1"]


def test_user_cannot_create_group(monkeypatch):
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "ops1",
        "role": "user",
        "groups": ["g1"],
    })
    resp = client.post("/groups", json={"name": "Rogue"}, headers=_auth_header())
    assert resp.status_code == 403


def test_user_cannot_get_out_of_group_report(monkeypatch):
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "ops1",
        "role": "user",
        "groups": ["g1"],
    })
    report = {"_id": "1", "device_id": "dev-x", "os": {"hostname": "other"}}
    monkeypatch.setattr(db, "get_report", lambda rid: report)
    monkeypatch.setattr(
        db,
        "list_groups",
        lambda: [{"_id": "g1", "name": "Ops", "machine_keys": ["id:dev-mine"]}],
    )
    resp = client.get("/reports/1", headers=_auth_header())
    assert resp.status_code == 403


def test_user_can_get_own_group_report(monkeypatch):
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "ops1",
        "role": "user",
        "groups": ["g1"],
    })
    report = {"_id": "1", "device_id": "dev-mine", "os": {"hostname": "pc1"}}
    monkeypatch.setattr(db, "get_report", lambda rid: report)
    monkeypatch.setattr(
        db,
        "list_groups",
        lambda: [{"_id": "g1", "name": "Ops", "machine_keys": ["id:dev-mine"]}],
    )
    resp = client.get("/reports/1", headers=_auth_header())
    assert resp.status_code == 200


def test_export_reports_requires_jwt(monkeypatch):
    _patch_db(monkeypatch)
    resp = client.get("/reports/export")
    assert resp.status_code == 401


def test_export_reports_csv(monkeypatch):
    _patch_db(monkeypatch)
    sample = {
        "_id": "1",
        "pc_name": "Office-PC-3",
        "device_id": "dev-2",
        "os": {"system": "Windows", "hostname": "office"},
        "private_ip": "192.168.1.5",
        "resources": {"cpu_percent": 12.5, "ram_percent": 44.0},
        "location": {"country": "Bangladesh", "country_code": "BD"},
        "created_at": 1755000000.0,
    }
    monkeypatch.setattr(db, "list_reports", lambda *a, **kw: [sample])
    resp = client.get("/reports/export", headers=_auth_header())
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    body = resp.text
    assert body.startswith("created_at,")
    assert "pc_name" in body
    assert "device_id" in body
    assert "Office-PC-3" in body
    assert "dev-2" in body


def test_export_reports_flattens_nested_and_lists(monkeypatch):
    _patch_db(monkeypatch)
    sample = {
        "_id": "1",
        "pc_name": "mac",
        "uptime": {"uptime_seconds": 3600.0, "by_day": {"2026-08-12": 3600.0}},
        "mac_addresses": [{"interface": "en0", "mac": "aa:bb"}],
        "disk": {"devices": [{"device": "disk0", "total": 100}]},
        "created_at": 1755000000.0,
    }
    monkeypatch.setattr(db, "list_reports", lambda *a, **kw: [sample])
    resp = client.get("/reports/export", headers=_auth_header())
    lines = resp.text.strip().splitlines()
    header = lines[0]
    row = lines[1]
    assert "uptime.uptime_seconds" in header
    assert "mac_addresses" in header
    assert "disk.devices" in header
    assert '"interface"' in row  # list serialized as JSON


def test_export_reports_includes_summary_columns(monkeypatch):
    _patch_db(monkeypatch)
    sample = {
        "_id": "1",
        "pc_name": "mac",
        "uptime": {"by_day": {"2026-08-10": 86400.0, "2026-08-11": 43200.0}},
        "network": {"bytes_sent": 1000, "bytes_recv": 2000},
        "printers": {
            "usb": [{"name": "p1", "port": "usb", "print_count": 5}, {"name": "p2", "port": "usb"}]
        },
        "health": {
            "disks": [
                {"name": "SSD", "media_type": "ssd", "health": "ok"},
                {"name": "HDD", "media_type": "hdd", "health": "fail"},
            ],
            "battery": {"health_percent": 82, "cycle_count": 471, "condition": "Good"},
        },
        "disk": {"devices": [{"device": "disk0", "total": 100, "used": 50}]},
        "created_at": 1755000000.0,
    }
    monkeypatch.setattr(db, "list_reports", lambda *a, **kw: [sample])
    resp = client.get("/reports/export", headers=_auth_header())
    body = resp.text
    assert "summary.total_uptime_seconds" in body
    assert "summary.network_total_bytes" in body
    assert "summary.print_count_total" in body
    assert "summary.battery_health_percent" in body
    line = body.strip().splitlines()[1]
    # total uptime 86400+43200 = 129600; prints 5; network 3000; disk 50%
    assert "129600" in line
    assert "3000" in line
    assert ",5," in line or line.endswith(",5") or ",5,".replace(",5", ",5,") in line


def test_get_report_not_found(monkeypatch):
    _patch_db(monkeypatch)
    resp = client.get("/reports/64b0000000000000000000ff", headers=_auth_header())
    assert resp.status_code == 404


# ---- api keys admin (super admin only) ----

SUPER_USER = {
    "_id": "64b000000000000000000001",
    "username": "admin",
    "role": "super_admin",
    "groups": [],
}


def test_create_api_key_requires_jwt(monkeypatch):
    _patch_db(monkeypatch, user=SUPER_USER)
    resp = client.post("/api-keys", json={"name": "desktop-1"})
    assert resp.status_code == 401


def test_create_api_key_requires_super_admin(monkeypatch):
    _patch_db(monkeypatch)
    resp = client.post("/api-keys", json={"name": "desktop-1"}, headers=_auth_header())
    assert resp.status_code == 403


def test_create_api_key(monkeypatch):
    _patch_db(monkeypatch, user=SUPER_USER)
    monkeypatch.setattr(db, "create_api_key", lambda name, kh, prefix: "64b00000000000000000000b")
    resp = client.post("/api-keys", json={"name": "desktop-1"}, headers=_auth_header())
    assert resp.status_code == 201
    body = resp.json()
    assert body["api_key"].startswith("sk-")


def test_update_api_key(monkeypatch):
    _patch_db(monkeypatch, user=SUPER_USER)
    monkeypatch.setattr(
        db,
        "update_api_key",
        lambda key_id, name=None, active=None: True,
    )
    monkeypatch.setattr(
        db,
        "list_api_keys",
        lambda: [
            {
                "_id": "64b00000000000000000000b",
                "name": "renamed",
                "prefix": "sk-old-",
                "active": False,
                "created_at": 1.0,
            }
        ],
    )
    resp = client.patch(
        "/api-keys/64b00000000000000000000b",
        json={"name": "renamed", "active": False},
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "renamed"
    assert body["active"] is False


def test_update_api_key_not_found(monkeypatch):
    _patch_db(monkeypatch, user=SUPER_USER)
    monkeypatch.setattr(db, "update_api_key", lambda key_id, name=None, active=None: False)
    resp = client.patch(
        "/api-keys/64b00000000000000000000b",
        json={"name": "renamed"},
        headers=_auth_header(),
    )
    assert resp.status_code == 404


def test_delete_api_key(monkeypatch):
    _patch_db(monkeypatch, user=SUPER_USER)
    monkeypatch.setattr(db, "delete_api_key", lambda key_id: True)
    resp = client.delete(
        "/api-keys/64b00000000000000000000b", headers=_auth_header()
    )
    assert resp.status_code == 204


def test_regenerate_api_key(monkeypatch):
    _patch_db(monkeypatch, user=SUPER_USER)
    calls: list[tuple] = []

    def fake_update(key_id, name=None, active=None, key_hash=None, prefix=None):
        calls.append((key_id, key_hash, prefix))
        return True

    monkeypatch.setattr(db, "update_api_key", fake_update)
    monkeypatch.setattr(
        db,
        "list_api_keys",
        lambda: [
            {
                "_id": "64b00000000000000000000b",
                "name": "desktop-1",
                "prefix": "sk-replaced-prefix",
                "active": True,
                "created_at": 1.0,
            }
        ],
    )
    resp = client.post(
        "/api-keys/64b00000000000000000000b/regenerate",
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_key"].startswith("sk-")
    assert body["name"] == "desktop-1"
    assert len(calls) == 1
    _, key_hash, prefix = calls[0]
    assert key_hash != "replaced-hash"
    assert prefix == body["api_key"][:20]


def test_regenerate_api_key_not_found(monkeypatch):
    _patch_db(monkeypatch, user=SUPER_USER)
    monkeypatch.setattr(
        db, "update_api_key", lambda key_id, name=None, active=None, key_hash=None, prefix=None: False
    )
    resp = client.post(
        "/api-keys/64b00000000000000000000b/regenerate",
        headers=_auth_header(),
    )
    assert resp.status_code == 404


# ---- groups admin ----

def test_create_group(monkeypatch):
    _patch_db(monkeypatch)
    monkeypatch.setattr(db, "create_group", lambda name: "64b00000000000000000000c")
    resp = client.post("/groups", json={"name": "Operations"}, headers=_auth_header())
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Operations"
    assert body["machine_keys"] == []


def test_create_group_blank_name(monkeypatch):
    _patch_db(monkeypatch)
    resp = client.post("/groups", json={"name": "   "}, headers=_auth_header())
    assert resp.status_code == 422


def test_list_groups(monkeypatch):
    _patch_db(monkeypatch)
    monkeypatch.setattr(
        db,
        "list_groups",
        lambda: [
            {
                "_id": "64b00000000000000000000c",
                "name": "Operations",
                "machine_keys": ["id:dev-1"],
                "created_at": 1.0,
            }
        ],
    )
    resp = client.get("/groups", headers=_auth_header())
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["id"] == "64b00000000000000000000c"
    assert body[0]["machine_keys"] == ["id:dev-1"]


def test_update_group_assigns_keys(monkeypatch):
    _patch_db(monkeypatch)
    groups = [
        {
            "_id": "64b00000000000000000000c",
            "name": "Operations",
            "machine_keys": ["id:dev-1"],
            "created_at": 1.0,
        }
    ]
    monkeypatch.setattr(db, "list_groups", lambda: groups)
    monkeypatch.setattr(
        db,
        "update_group",
        lambda group_id, name=None, machine_keys=None: (groups[0].update({"machine_keys": machine_keys}) if machine_keys is not None else None, True)[1],
    )
    resp = client.patch(
        "/groups/64b00000000000000000000c",
        json={"machine_keys": ["id:dev-1", "id:dev-2"]},
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    assert resp.json()["machine_keys"] == ["id:dev-1", "id:dev-2"]


def test_update_group_removes_from_others(monkeypatch):
    _patch_db(monkeypatch)
    groups = [
        {
            "_id": "g1",
            "name": "Ops",
            "machine_keys": ["id:dev-1"],
            "created_at": 1.0,
        },
        {
            "_id": "g2",
            "name": "Sales",
            "machine_keys": ["id:dev-1", "id:dev-9"],
            "created_at": 1.0,
        },
    ]
    monkeypatch.setattr(db, "list_groups", lambda: groups)
    updates = []
    monkeypatch.setattr(
        db, "update_group", lambda gid, name=None, machine_keys=None: (updates.append((gid, machine_keys)) or True)
    )
    resp = client.patch(
        "/groups/g1",
        json={"machine_keys": ["id:dev-1", "id:dev-2"]},
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    assert ("g2", ["id:dev-9"]) in updates
    assert ("g1", ["id:dev-1", "id:dev-2"]) in updates


def test_delete_group(monkeypatch):
    _patch_db(monkeypatch)
    monkeypatch.setattr(db, "delete_group", lambda gid: True)
    resp = client.delete("/groups/64b00000000000000000000c", headers=_auth_header())
    assert resp.status_code == 204


def test_list_users(monkeypatch):
    _patch_db(monkeypatch, user=SUPER_USER)
    resp = client.get("/users", headers=_auth_header())
    assert resp.status_code == 200
    assert resp.json()[0]["username"] == "admin"


def test_list_users_requires_super_admin(monkeypatch):
    _patch_db(monkeypatch)
    resp = client.get("/users", headers=_auth_header())
    assert resp.status_code == 403


def test_list_users_requires_jwt(monkeypatch):
    _patch_db(monkeypatch)
    resp = client.get("/users")
    assert resp.status_code == 401


def test_create_user_with_groups(monkeypatch):
    _patch_db(monkeypatch, user=SUPER_USER)
    created = {"_id": "64b000000000000000000009", "username": "ops1", "role": "user", "groups": ["g1", "g2"]}
    calls = {"n": 0}

    def fake_find_user(uname):
        if uname == "ops1":
            calls["n"] += 1
            return created if calls["n"] > 1 else None
        return None

    monkeypatch.setattr(db, "find_user_by_username", fake_find_user)
    resp = client.post(
        "/users",
        json={"username": "ops1", "password": "secret123", "role": "user", "groups": ["g1", "g2"]},
        headers=_auth_header(),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "ops1"
    assert body["role"] == "user"
    assert body["groups"] == ["g1", "g2"]


def test_create_user_invalid_role(monkeypatch):
    _patch_db(monkeypatch, user=SUPER_USER)
    resp = client.post(
        "/users",
        json={"username": "ops1", "password": "secret123", "role": "root", "groups": []},
        headers=_auth_header(),
    )
    assert resp.status_code == 422


def test_update_user_role_and_groups(monkeypatch):
    _patch_db(monkeypatch, user=SUPER_USER)
    updated = {"_id": "64b000000000000000000009", "username": "ops1", "role": "user", "groups": ["g3"]}

    def fake_get_user(uid):
        if uid == "64b000000000000000000009":
            return dict(updated)
        return dict(SUPER_USER)

    monkeypatch.setattr(db, "get_user_by_id", fake_get_user)
    resp = client.patch(
        "/users/64b000000000000000000009",
        json={"role": "user", "groups": ["g3"]},
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    assert resp.json()["groups"] == ["g3"]


def test_delete_user(monkeypatch):
    _patch_db(monkeypatch, user=SUPER_USER)
    resp = client.delete("/users/64b000000000000000000009", headers=_auth_header())
    assert resp.status_code == 204


def test_delete_self_forbidden(monkeypatch):
    _patch_db(monkeypatch, user=SUPER_USER)
    resp = client.delete("/users/64b000000000000000000001", headers=_auth_header())
    assert resp.status_code == 400


def test_list_api_keys(monkeypatch):
    _patch_db(monkeypatch, user=SUPER_USER)
    monkeypatch.setattr(
        db,
        "list_api_keys",
        lambda: [
            {
                "_id": "64b00000000000000000000b",
                "name": "desktop-1",
                "prefix": "sk-abcd",
                "active": True,
                "created_at": 1.0,
            }
        ],
    )
    resp = client.get("/api-keys", headers=_auth_header())
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["id"] == "64b00000000000000000000b"
    assert body[0]["name"] == "desktop-1"
    assert body[0]["created_at"] == 1.0


# ---- heartbeat ----

def test_heartbeat_requires_api_key(monkeypatch):
    _patch_db(monkeypatch)
    resp = client.post("/heartbeat", json={"device_id": "dev-1", "pc_name": "PC1"})
    assert resp.status_code == 401


def test_heartbeat_ok(monkeypatch):
    _patch_db(monkeypatch)
    key = security.generate_api_key()
    monkeypatch.setattr(db, "find_api_key_by_hash", lambda h: {"_id": "x", "prefix": key[:20], "active": True})
    touched = {}
    monkeypatch.setattr(db, "touch_machine", lambda device_id, pc_name=None, seen_at=None: touched.update({"device_id": device_id, "pc_name": pc_name, "seen_at": seen_at}) or True)
    resp = client.post(
        "/heartbeat",
        json={"device_id": "dev-1", "pc_name": "PC1"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["online"] is True
    assert touched["device_id"] == "dev-1"
    assert touched["pc_name"] == "PC1"


def test_heartbeat_updates_presence(monkeypatch):
    from sysinfo_api import realtime

    _patch_db(monkeypatch)
    key = security.generate_api_key()
    monkeypatch.setattr(db, "find_api_key_by_hash", lambda h: {"_id": "x", "prefix": key[:20], "active": True})
    resp = client.post(
        "/heartbeat",
        json={"device_id": "dev-1", "pc_name": "PC1"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert resp.status_code == 200
    snapshot = realtime.presence_snapshot()
    assert any(e["device_id"] == "dev-1" and e["online"] is True for e in snapshot)


def test_heartbeat_mongo_down(monkeypatch):
    _patch_db(monkeypatch)
    key = security.generate_api_key()
    monkeypatch.setattr(db, "find_api_key_by_hash", lambda h: {"_id": "x", "prefix": key[:20], "active": True})
    monkeypatch.setattr(db, "touch_machine", lambda device_id, pc_name=None, seen_at=None: False)
    resp = client.post(
        "/heartbeat",
        json={"device_id": "dev-1"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert resp.status_code == 503


# ---- reports annotate online ----

def test_list_reports_annotates_online(monkeypatch):
    _patch_db(monkeypatch)
    monkeypatch.setattr(
        db,
        "list_reports",
        lambda limit=20, device_id=None, pc_name=None, from_ts=None, to_ts=None, country=None, os_name=None, group_id=None, group_ids=None, disk_health=None, battery=None, battery_health_min=None: [
            {"_id": "1", "pc_name": "Mac", "device_id": "dev-live", "created_at": 1.0},
            {"_id": "2", "pc_name": "Win", "device_id": "dev-gone", "created_at": 2.0},
        ],
    )
    monkeypatch.setattr(db, "machines_seen_map", lambda: {"dev-live": 2_000_000_000.0})
    resp = client.get("/reports", headers=_auth_header())
    reports = resp.json()["reports"]
    assert reports[0]["online"] is True
    assert reports[0]["last_seen"] == 2_000_000_000.0
    assert reports[1]["online"] is False


def test_create_report_broadcasts_printers(monkeypatch):
    _patch_db(monkeypatch)
    key = security.generate_api_key()
    monkeypatch.setattr(db, "find_api_key_by_hash", lambda h: {"_id": "x", "prefix": key[:20], "active": True})
    sent = []

    from sysinfo_api import realtime

    async def fake_broadcast(report):
        sent.append(report)

    async def fake_broadcast_presence(*args, **kwargs):
        return None

    monkeypatch.setattr(realtime, "broadcast", fake_broadcast)
    monkeypatch.setattr(realtime, "broadcast_presence", fake_broadcast_presence)
    resp = client.post(
        "/reports",
        json={
            "pc_name": "MacBook",
            "device_id": "dev-1",
            "printers": {"count": 2, "network": [{"name": "R324", "port": "ipp://x", "ip": "10.0.0.9", "print_count": 12}]},
            "os": {"system": "Darwin"},
        },
        headers={"Authorization": f"Bearer {key}"},
    )
    assert resp.status_code == 201
    assert len(sent) == 1
    assert sent[0]["printers"]["network"][0]["print_count"] == 12
    assert sent[0]["device_id"] == "dev-1"


# ---- websocket ----

def _ws_closed_without_hello(monkeypatch, url):
    """Connect to ws and assert the server closes it (no hello frame)."""
    import pytest as _pytest
    from starlette.websockets import WebSocketDisconnect

    try:
        with client.websocket_connect(url, subprotocols=["dash-token"]) as ws:
            # If the server accepted, we must see hello; rejections close early.
            with _pytest.raises(WebSocketDisconnect):
                ws.receive_json()
    except WebSocketDisconnect:
        pass  # server closed during handshake — expected.


def test_websocket_requires_auth(monkeypatch):
    _patch_db(monkeypatch)
    _ws_closed_without_hello(monkeypatch, "/ws")


def test_websocket_rejects_bad_token(monkeypatch):
    _patch_db(monkeypatch)
    _ws_closed_without_hello(monkeypatch, "/ws?token=not-a-real-token")


def test_websocket_rejects_user_role(monkeypatch):
    _patch_db(monkeypatch, user={
        "_id": "64b000000000000000000001",
        "username": "ops1",
        "role": "user",
        "groups": ["g1"],
    })
    _ws_closed_without_hello(monkeypatch, "/ws?token=" + _raw_token())


def test_websocket_hello(monkeypatch):
    _patch_db(monkeypatch)
    with client.websocket_connect("/ws?token=" + _raw_token(), subprotocols=["dash-token"]) as ws:
        data = ws.receive_json()
        assert data["type"] == "hello"


def _raw_token():
    from datetime import datetime, timedelta, timezone
    import jwt as pyjwt
    from sysinfo_api import config
    payload = {"sub": "64b000000000000000000001", "role": "admin", "exp": datetime.now(timezone.utc) + timedelta(minutes=10)}
    return pyjwt.encode(payload, config.JWT_SECRET, algorithm="HS256")
