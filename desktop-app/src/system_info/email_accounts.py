"""Collect POP/IMAP email accounts configured in mail clients.

Supported clients:
  - Apple Mail (macOS)          via ~/Library/Preferences/com.apple.mail.plist
  - Thunderbird (macOS/Win)     via prefs.js in each Thunderbird profile
  - Outlook for Mac             via account plists in the Office group container
  - New Outlook for Windows     via account JSON under the packaged app state
  - Classic Outlook (Windows)   best-effort: outlook.xml + registry string scan

Only non-secret config is collected (email address, username, protocol, host,
port, TLS mode). Passwords are encrypted by the OS keychain / credential
manager and are deliberately NOT read. Stdlib only.
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_PROTOCOLS = ("pop3", "imap", "exchange")
_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
)


@dataclass
class EmailAccount:
    client: str
    email: str
    username: str | None = None
    full_name: str | None = None
    protocol: str | None = None  # pop3 | imap | exchange | smtp
    incoming_host: str | None = None
    incoming_port: int | None = None
    outgoing_host: str | None = None
    outgoing_port: int | None = None
    security: str | None = None  # ssl | starttls | none

    def to_dict(self) -> dict:
        return {
            "client": self.client,
            "email": self.email,
            "username": self.username,
            "full_name": self.full_name,
            "protocol": self.protocol,
            "incoming_host": self.incoming_host,
            "incoming_port": self.incoming_port,
            "outgoing_host": self.outgoing_host,
            "outgoing_port": self.outgoing_port,
            "security": self.security,
        }


@dataclass
class EmailInfo:
    accounts: list[EmailAccount] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.accounts)

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "accounts": [a.to_dict() for a in self.accounts],
        }


def _dedupe(accounts: list[EmailAccount]) -> list[EmailAccount]:
    seen: set[tuple] = set()
    out: list[EmailAccount] = []
    for a in accounts:
        key = (
            a.client,
            (a.email or "").lower(),
            (a.incoming_host or "").lower(),
            (a.protocol or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def _norm_protocol(value: object) -> str | None:
    text = str(value or "").lower()
    for proto in _PROTOCOLS:
        if proto in text:
            return proto
    return None


# ---- Apple Mail (macOS) ----

def _collect_apple_mail() -> list[EmailAccount]:
    path = Path.home() / "Library/Preferences/com.apple.mail.plist"
    if not path.is_file():
        return []
    try:
        with open(path, "rb") as fh:
            prefs = plistlib.load(fh)
    except (OSError, plistlib.InvalidFileException):
        return []

    deliveries: dict[str, dict] = {}
    for item in prefs.get("DeliveryAccounts") or []:
        if isinstance(item, dict) and item.get("DeliveryIdentifier"):
            deliveries[str(item["DeliveryIdentifier"])] = item

    accounts: list[EmailAccount] = []
    for acct in prefs.get("MailAccounts") or []:
        if not isinstance(acct, dict):
            continue
        email = str(acct.get("AccountEmailAddress") or "").strip()
        if not email:
            continue
        delivery = deliveries.get(str(acct.get("DeliveryAccountIdentifier") or "")) or {}
        security = None
        if delivery.get("DeliveryUseSSL") is True:
            security = "ssl"
        accounts.append(
            EmailAccount(
                client="apple_mail",
                email=email,
                username=acct.get("AccountUsername"),
                full_name=acct.get("AccountFullName") or acct.get("FullName"),
                protocol=_norm_protocol(acct.get("AccountType")),
                incoming_host=acct.get("AccountHostname"),
                incoming_port=acct.get("AccountPort"),
                outgoing_host=delivery.get("DeliveryHostname"),
                outgoing_port=delivery.get("DeliveryPort"),
                security=security,
            )
        )
    return accounts


# ---- Thunderbird (macOS + Windows) ----

def _thunderbird_profile_dirs() -> list[Path]:
    dirs: list[Path] = []
    if os.name == "nt":
        base = os.getenv("APPDATA") or str(Path.home())
        dirs.append(Path(base) / "Thunderbird" / "Profiles")
    else:
        dirs.append(Path.home() / "Library" / "Thunderbird" / "Profiles")
        dirs.append(Path.home() / ".thunderbird")
    return [d for d in dirs if d.is_dir()]


def _parse_prefs_js(text: str) -> dict:
    prefs: dict = {}
    for match in re.finditer(r'user_pref\(\s*"([^"]+)"\s*,\s*(.*?)\s*\);', text):
        key = match.group(1)
        raw = match.group(2).strip()
        if raw.startswith('"') and raw.endswith('"'):
            value = raw[1:-1].replace("\\\\", "\\").replace('\\"', '"')
        elif raw == "true":
            value = True
        elif raw == "false":
            value = False
        else:
            try:
                value = int(raw)
            except ValueError:
                try:
                    value = float(raw)
                except ValueError:
                    value = raw
        prefs[key] = value
    return prefs


def _collect_thunderbird() -> list[EmailAccount]:
    accounts: list[EmailAccount] = []
    for profiles in _thunderbird_profile_dirs():
        for profile in profiles.iterdir():
            prefs_path = profile / "prefs.js"
            if not prefs_path.is_file():
                continue
            try:
                prefs = _parse_prefs_js(prefs_path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            account_keys = str(prefs.get("mail.accountmanager.accounts") or "").split(",")
            for account_key in (k.strip() for k in account_keys if k.strip()):
                server_key = prefs.get(f"mail.account.{account_key}.server")
                if not server_key:
                    continue
                protocol = _norm_protocol(prefs.get(f"mail.server.{server_key}.type"))
                host = prefs.get(f"mail.server.{server_key}.hostname")
                username = prefs.get(f"mail.server.{server_key}.userName")
                port = prefs.get(f"mail.server.{server_key}.port")
                socket_type = prefs.get(f"mail.server.{server_key}.socketType")
                security = {0: "none", 1: "starttls", 2: "ssl"}.get(socket_type)

                email = ""
                full_name = None
                identity_ids = [
                    i.strip()
                    for i in str(prefs.get(f"mail.account.{account_key}.identities") or "").split(",")
                    if i.strip()
                ]
                for identity_id in identity_ids:
                    value = prefs.get(f"mail.identity.{identity_id}.email")
                    if value and not email:
                        email = str(value)
                    if value := prefs.get(f"mail.identity.{identity_id}.fullName"):
                        full_name = str(value)

                smtp_key = prefs.get(f"mail.account.{account_key}.smtpServer")
                out_host = out_port = out_security = None
                if smtp_key:
                    out_host = prefs.get(f"mail.smtpserver.{smtp_key}.hostname")
                    out_port = prefs.get(f"mail.smtpserver.{smtp_key}.port")
                    try_ssl = prefs.get(f"mail.smtpserver.{smtp_key}.try_ssl")
                    if try_ssl in (1, 2):
                        out_security = "starttls" if try_ssl == 1 else "ssl"

                if not email and not host:
                    continue
                accounts.append(
                    EmailAccount(
                        client="thunderbird",
                        email=email,
                        username=username,
                        full_name=full_name,
                        protocol=protocol,
                        incoming_host=host,
                        incoming_port=port,
                        outgoing_host=out_host,
                        outgoing_port=out_port,
                        security=security or out_security,
                    )
                )
    return accounts


# ---- Outlook for Mac ----

def _collect_outlook_mac() -> list[EmailAccount]:
    base = (
        Path.home()
        / "Library"
        / "Group Containers"
        / "UBF8T346G9.Office"
        / "Outlook"
    )
    if not base.is_dir():
        return []
    accounts: list[EmailAccount] = []
    for plist_path in base.rglob("*.plist"):
        if "Accounts" not in str(plist_path.parent):
            continue
        try:
            with open(plist_path, "rb") as fh:
                data = plistlib.load(fh)
        except (OSError, plistlib.InvalidFileException):
            continue
        email = data.get("EmailAddress") or data.get("Email")
        if not email:
            continue
        protocol = _norm_protocol(data.get("Protocol") or data.get("AccountType"))
        if protocol == "exchange":
            protocol = "exchange"
        accounts.append(
            EmailAccount(
                client="outlook_mac",
                email=str(email),
                username=data.get("AccountUser"),
                full_name=data.get("AccountDisplayName"),
                protocol=protocol,
                incoming_host=data.get("AccountHostName"),
                outgoing_host=data.get("SMTPHost") or data.get("InternalSMTPHost"),
            )
        )
    return accounts


# ---- New Outlook for Windows ----

def _walk_json(value, depth: int = 0) -> list[dict]:
    """Yield all dicts in a JSON document (bounded depth to avoid blowups)."""
    if depth > 12:
        return []
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child, depth + 1)


def _collect_outlook_new_windows() -> list[EmailAccount]:
    local = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or ""
    base = (
        Path(local)
        / "Packages"
        / "Microsoft.OutlookForWindows_8wekyb3d8bbwe"
        / "LocalState"
    )
    if not base.is_dir():
        return []
    accounts: list[EmailAccount] = []
    for json_path in base.rglob("*.json"):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, ValueError):
            continue
        for node in _walk_json(data):
            email = (
                node.get("email")
                or node.get("emailAddress")
                or node.get("Email")
                or node.get("emailId")
                or node.get("mail")
            )
            if not email:
                continue
            host = (
                node.get("mailServerHostName")
                or node.get("imapServer")
                or node.get("popServer")
                or node.get("server")
                or node.get("hostname")
            )
            protocol = _norm_protocol(
                node.get("accountType") or node.get("protocol") or node.get("type")
            )
            accounts.append(
                EmailAccount(
                    client="outlook_new",
                    email=str(email),
                    username=node.get("username"),
                    protocol=protocol,
                    incoming_host=host,
                )
            )
    return accounts


# ---- Classic Outlook for Windows (best-effort) ----

def _collect_outlook_classic_windows() -> list[EmailAccount]:
    accounts: list[EmailAccount] = []

    # Send-account config usually lives in %APPDATA%\Microsoft\Outlook\outlook.xml
    appdata = os.getenv("APPDATA") or ""
    xml_path = Path(appdata) / "Microsoft" / "Outlook" / "outlook.xml"
    if xml_path.is_file():
        try:
            text = xml_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""
        if text:
            for email_match in _EMAIL_RE.finditer(text):
                email = email_match.group(0)
                start = max(0, email_match.start() - 400)
                window = text[start : email_match.end() + 200]
                host = ""
                for tag in ("sendhost", "server", "hostname", "host"):
                    match = re.search(
                        rf"<{tag}[^>]*>([^<]+)</{tag}>", window, re.IGNORECASE
                    )
                    if match:
                        host = match.group(1).strip()
                        break
                accounts.append(
                    EmailAccount(
                        client="outlook_classic",
                        email=email,
                        incoming_host=host or None,
                        protocol="smtp" if host else None,
                    )
                )

    # Fallback: scan the Outlook profile registry blob for readable strings.
    raw = _run_powershell(
        r"""
$keys = Get-ChildItem "HKCU:\Software\Microsoft\Office" -ErrorAction SilentlyContinue |
    Where-Object { $_.PSChildName -match '^\d+\.\d+$' } |
    ForEach-Object { Get-ChildItem "$($_.PSPath)\Outlook\Profiles" -Recurse -ErrorAction SilentlyContinue }
$out = @()
foreach ($k in $keys) {
  if ($k.PSChildName -ne '9375CFF0413111d3B88A00104B2A6676') { continue }
  foreach ($v in $k.GetValueNames()) {
    $bytes = (Get-ItemProperty -Path $k.PSPath -Name $v).$v
    if ($bytes -is [byte[]]) {
      $ascii = [System.Text.Encoding]::ASCII.GetString($bytes)
      $utf16 = [System.Text.Encoding]::Unicode.GetString($bytes)
      $text = "$ascii $utf16"
      $matches = [regex]::Matches($text, '[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
      foreach ($m in $matches) { $out += $m.Value }
    }
  }
}
$out | Sort-Object -Unique | ConvertTo-Json -Compress
"""
    )
    if raw:
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = []
        if isinstance(parsed, str):
            parsed = [parsed]
        for email in parsed or []:
            email = str(email).strip()
            if email and not any(a.email == email for a in accounts):
                accounts.append(
                    EmailAccount(
                        client="outlook_classic",
                        email=email,
                        protocol="smtp",
                    )
                )
    return accounts


def _run_powershell(script: str, timeout: float = 12.0) -> str:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def collect_email_accounts() -> EmailInfo:
    """List configured POP/IMAP email accounts across supported clients."""
    accounts: list[EmailAccount] = []
    if os.name == "nt":
        accounts.extend(_collect_outlook_new_windows())
        accounts.extend(_collect_outlook_classic_windows())
        accounts.extend(_collect_thunderbird())
    else:
        accounts.extend(_collect_apple_mail())
        accounts.extend(_collect_thunderbird())
        accounts.extend(_collect_outlook_mac())
    return EmailInfo(accounts=_dedupe(accounts))
