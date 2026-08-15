import json
import plistlib
from pathlib import Path

from system_info.email_accounts import (
    _collect_apple_mail,
    _collect_outlook_classic_windows,
    _collect_outlook_mac,
    _collect_outlook_new_windows,
    _collect_thunderbird,
    _outlook_mac_mode_to_protocol,
    _parse_prefs_js,
    collect_email_accounts,
)


def test_parse_prefs_js_types():
    prefs = _parse_prefs_js(
        'user_pref("mail.accountmanager.accounts", "a1,a2");\n'
        'user_pref("mail.server.s1.type", "imap");\n'
        'user_pref("mail.server.s1.port", 993);\n'
        'user_pref("mail.server.s1.socketType", 2);\n'
        'user_pref("mail.flag", true);\n'
    )
    assert prefs["mail.accountmanager.accounts"] == "a1,a2"
    assert prefs["mail.server.s1.port"] == 993
    assert prefs["mail.server.s1.socketType"] == 2
    assert prefs["mail.flag"] is True


def test_collect_thunderbird(tmp_path, monkeypatch):
    prof = tmp_path / "Library" / "Thunderbird" / "Profiles" / "abc.default"
    prof.mkdir(parents=True)
    (prof / "prefs.js").write_text(
        'user_pref("mail.accountmanager.accounts", "acct1,acct2");\n'
        'user_pref("mail.account.acct1.server", "srv1");\n'
        'user_pref("mail.account.acct1.identities", "id1");\n'
        'user_pref("mail.account.acct1.smtpServer", "smtp1");\n'
        'user_pref("mail.server.srv1.type", "imap");\n'
        'user_pref("mail.server.srv1.hostname", "imap.example.com");\n'
        'user_pref("mail.server.srv1.userName", "jane");\n'
        'user_pref("mail.server.srv1.port", 993);\n'
        'user_pref("mail.server.srv1.socketType", 2);\n'
        'user_pref("mail.identity.id1.email", "jane@example.com");\n'
        'user_pref("mail.identity.id1.fullName", "Jane Doe");\n'
        'user_pref("mail.smtpserver.smtp1.hostname", "smtp.example.com");\n'
        'user_pref("mail.smtpserver.smtp1.port", 465);\n'
        'user_pref("mail.smtpserver.smtp1.try_ssl", 2);\n'
        'user_pref("mail.account.acct2.server", "srv2");\n'
        'user_pref("mail.server.srv2.type", "pop3");\n'
        'user_pref("mail.server.srv2.hostname", "pop.example.com");\n'
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    accounts = _collect_thunderbird()
    assert len(accounts) == 2
    imap = next(a for a in accounts if a.protocol == "imap")
    assert imap.email == "jane@example.com"
    assert imap.username == "jane"
    assert imap.incoming_host == "imap.example.com"
    assert imap.incoming_port == 993
    assert imap.outgoing_host == "smtp.example.com"
    assert imap.outgoing_port == 465
    assert imap.security == "ssl"
    pop = next(a for a in accounts if a.protocol == "pop3")
    assert pop.incoming_host == "pop.example.com"


def test_collect_apple_mail(tmp_path, monkeypatch):
    prefs = tmp_path / "Library" / "Preferences"
    prefs.mkdir(parents=True)
    (prefs / "com.apple.mail.plist").write_bytes(
        plistlib.dumps(
            {
                "MailAccounts": [
                    {
                        "AccountEmailAddress": "alice@example.com",
                        "AccountUsername": "alice",
                        "AccountFullName": "Alice",
                        "AccountType": "EmailAccountTypeIMAP",
                        "AccountHostname": "imap.example.com",
                        "DeliveryAccountIdentifier": "del1",
                    }
                ],
                "DeliveryAccounts": [
                    {
                        "DeliveryIdentifier": "del1",
                        "DeliveryHostname": "smtp.example.com",
                        "DeliveryPort": 587,
                        "DeliveryUseSSL": True,
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    accounts = _collect_apple_mail()
    assert len(accounts) == 1
    acc = accounts[0]
    assert acc.email == "alice@example.com"
    assert acc.username == "alice"
    assert acc.protocol == "imap"
    assert acc.incoming_host == "imap.example.com"
    assert acc.outgoing_host == "smtp.example.com"
    assert acc.outgoing_port == 587
    assert acc.security == "ssl"


def test_collect_outlook_mac(tmp_path, monkeypatch):
    accts = (
        tmp_path
        / "Library"
        / "Group Containers"
        / "UBF8T346G9.Office"
        / "Outlook"
        / "Outlook 15 Profiles"
        / "Main Profile"
        / "Accounts"
    )
    accts.mkdir(parents=True)
    (accts / "account.plist").write_bytes(
        plistlib.dumps(
            {
                "EmailAddress": "bob@example.com",
                "AccountUser": "bob",
                "AccountDisplayName": "Bob",
                "AccountHostName": "imap.example.com",
                "Protocol": "IMAP",
                "SMTPHost": "smtp.example.com",
            }
        )
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    accounts = _collect_outlook_mac()
    assert len(accounts) == 1
    acc = accounts[0]
    assert acc.email == "bob@example.com"
    assert acc.username == "bob"
    assert acc.protocol == "imap"
    assert acc.incoming_host == "imap.example.com"
    assert acc.outgoing_host == "smtp.example.com"


def test_collect_email_accounts_no_config(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    info = collect_email_accounts()
    assert info.count == 0


def test_outlook_mac_mode_to_protocol():
    assert _outlook_mac_mode_to_protocol("ActiveSyncExchange") == "exchange"
    assert _outlook_mac_mode_to_protocol("O365") == "exchange"
    assert _outlook_mac_mode_to_protocol("Imap") == "imap"
    assert _outlook_mac_mode_to_protocol("Pop") == "pop3"
    assert _outlook_mac_mode_to_protocol("Exchange") == "exchange"
    assert _outlook_mac_mode_to_protocol("Omc_Direct") == "exchange"


def test_collect_outlook_mac_profiles(tmp_path, monkeypatch):
    """Modern Outlook for Mac: account list lives in ProfilePreferences.plist
    as SortedAccounts entries like 'email_ActiveSyncExchange_HxS'."""
    prefs = (
        tmp_path
        / "Library"
        / "Group Containers"
        / "UBF8T346G9.Office"
        / "Outlook"
        / "Outlook 15 Profiles"
        / "Main Profile"
    )
    prefs.mkdir(parents=True)
    (prefs / "ProfilePreferences.plist").write_bytes(
        plistlib.dumps(
            {
                "SortedAccounts": [
                    "developer.eight@neutrix.co_ActiveSyncExchange_HxS",
                    "personal@example.com_Imap_HxS",
                ],
                "OutlookGatewayURLFordeveloper.eight@neutrix.co_ActiveSyncExchange_HxS": (
                    "https://outlook.office365.com"
                ),
            }
        )
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    accounts = _collect_outlook_mac()
    assert len(accounts) == 2
    ex = next(a for a in accounts if a.email == "developer.eight@neutrix.co")
    assert ex.client == "outlook_mac"
    assert ex.protocol == "exchange"
    assert ex.incoming_host == "outlook.office365.com"
    imap = next(a for a in accounts if a.email == "personal@example.com")
    assert imap.protocol == "imap"
    assert imap.incoming_host is None


def test_collect_outlook_new_windows(tmp_path, monkeypatch):
    """New Outlook for Windows: account JSON under the packaged app LocalState."""
    local = tmp_path / "LOCALAPPDATA" / "Packages" / "Microsoft.OutlookForWindows_8wekyb3d8bbwe" / "LocalState"
    (local / "Accounts").mkdir(parents=True)
    (local / "Accounts" / "account1.json").write_text(
        json.dumps(
            {"emailAddress": "carol@winoutlook.com", "username": "carol", "protocol": "IMAP"}
        )
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LOCALAPPDATA"))
    accounts = _collect_outlook_new_windows()
    assert len(accounts) == 1
    acc = accounts[0]
    assert acc.email == "carol@winoutlook.com"
    assert acc.username == "carol"
    assert acc.protocol == "imap"
    assert acc.client == "outlook_new"


def test_collect_outlook_classic_windows(tmp_path, monkeypatch):
    """Classic Outlook for Windows: email addrs in outlook.xml (no registry needed)."""
    appdata = tmp_path / "APPDATA" / "Microsoft" / "Outlook"
    appdata.mkdir(parents=True)
    (appdata / "outlook.xml").write_text(
        "<xml><account><email>dave@classic.com</email>"
        "<sendhost>smtp.classic.com</sendhost></account><account>"
        "<email>erin@corp.com</email><sendhost>smtp.corp.com</sendhost></account></xml>"
    )
    monkeypatch.setenv("APPDATA", str(tmp_path / "APPDATA"))
    accounts = _collect_outlook_classic_windows()
    assert len(accounts) == 2
    emails = {a.email for a in accounts}
    assert emails == {"dave@classic.com", "erin@corp.com"}
    assert all(a.client == "outlook_classic" for a in accounts)
