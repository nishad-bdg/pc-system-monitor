import pytest

from system_info import startup


@pytest.fixture
def fake_winreg(monkeypatch):
    class _RegKey:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    calls = {"set": [], "delete": [], "open": 0}

    class _FakeWinreg:
        HKEY_CURRENT_USER = "hku"
        KEY_SET_VALUE = 1
        REG_SZ = 1

        def OpenKey(self, root, path, reserved, access):
            calls["open"] += 1
            return _RegKey()

        def SetValueEx(self, key, name, reserved, kind, value):
            calls["set"].append((name, value))

        def DeleteValue(self, key, name):
            calls["delete"].append(name)

    monkeypatch.setattr(startup, "_winreg", _FakeWinreg())
    monkeypatch.setattr(startup, "os", type("OS", (), {"name": "nt"})())
    monkeypatch.setattr(startup, "sys", type("SYS", (), {"executable": r"C:\SystemInfo\system-info.exe"})())
    monkeypatch.setattr(startup, "is_frozen", lambda: True)
    return calls


def test_startup_command(fake_winreg):
    cmd = startup.startup_command()
    assert cmd == '"C:\\SystemInfo\\system-info.exe" --heartbeat'


def test_register_startup_first_run(monkeypatch, fake_winreg, tmp_path):
    monkeypatch.setattr(startup, "user_config_dir", lambda: tmp_path)
    assert not startup.already_registered()
    assert startup.register_startup() is True
    assert fake_winreg["set"] == [
        (startup.RUN_VALUE_NAME, '"C:\\SystemInfo\\system-info.exe" --heartbeat')
    ]
    assert (tmp_path / startup.MARKER).is_file()
    assert startup.already_registered()


def test_register_startup_idempotent(monkeypatch, fake_winreg, tmp_path):
    monkeypatch.setattr(startup, "user_config_dir", lambda: tmp_path)
    (tmp_path / startup.MARKER).write_text("1", encoding="utf-8")
    assert startup.register_startup() is True
    assert fake_winreg["set"] == []
    assert fake_winreg["open"] == 0


def test_register_startup_not_supported_on_macos(monkeypatch):
    monkeypatch.setattr(startup, "os", type("OS", (), {"name": "posix"})())
    monkeypatch.setattr(startup, "is_frozen", lambda: True)
    assert startup.register_startup() is False
    assert not startup.already_registered()


def test_unregister_startup(monkeypatch, fake_winreg, tmp_path):
    monkeypatch.setattr(startup, "user_config_dir", lambda: tmp_path)
    (tmp_path / startup.MARKER).write_text("1", encoding="utf-8")
    assert startup.unregister_startup() is True
    assert fake_winreg["delete"] == [startup.RUN_VALUE_NAME]
    assert not (tmp_path / startup.MARKER).exists()