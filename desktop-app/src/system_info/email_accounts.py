"""Collect POP/IMAP email accounts configured in mail clients.

Supported clients:
  - Apple Mail (macOS)          via ~/Library/Preferences/com.apple.mail.plist
  - Thunderbird (macOS/Win)     via prefs.js in each Thunderbird profile
  - Outlook for Mac             via account plists, plus modern Outlook
    (Office 365) via ProfilePreferences.plist SortedAccounts entries like
    '<email>_ActiveSyncExchange_HxS' (extracts the email + mode/server)
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
import sqlite3
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

_YAHOO = ("aol", "yahoo")
# Outlook for Mac account identifiers look like:
#   developer.eight@neutrix.co_ActiveSyncExchange_HxS
#   user@example.com_O365_HxS
#   user@example.com_Imap_HxS
_ACCOUNT_ID_RE = re.compile(
    r"^(?P<email>[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})"
    r"_(?P<mode>[^_]+)(?:_HxS)?$"
)


def _outlook_mac_mode_to_protocol(mode: str) -> str | None:
    text = (str(mode or "")).lower()
    if "exchange" in text or "activesync" in text:
        return "exchange"
    if "imap" in text:
        return "imap"
    if "pop" in text:
        return "pop3"
    if text in ("oc", "o365", "omc_direct", "direct"):
        return "exchange"
    return None


def _collect_outlook_mac_profiles() -> list[EmailAccount]:
    """Modern Outlook for Mac: read SortedAccounts from ProfilePreferences.plist.

    Outlook 15+/Microsoft-365 keeps the account list in
    .../Outlook 15 Profiles/<Profile>/ProfilePreferences.plist under the
    SortedAccounts key. Each entry is '<email>_<AccountType>_HxS' (e.g.
    'a@b.com_ActiveSyncExchange_HxS'), so the email address is extracted
    directly and the server (e.g. outlook.office365.com) usually appears in a
    matching 'OutlookGatewayURLFor<email>' / '<int>GatewayURLFor...' key.
    """
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
    for prefs_path in base.rglob("ProfilePreferences.plist"):
        try:
            with open(prefs_path, "rb") as fh:
                prefs = plistlib.load(fh)
        except (OSError, plistlib.InvalidFileException):
            continue
        sorted_accounts = prefs.get("SortedAccounts") or []
        gateways: dict[str, str] = {}
        for key, value in prefs.items():
            if not isinstance(value, str):
                continue
            if "GatewayURLFor" not in key:
                continue
            # key like OutlookGatewayURLFor<email>_ActiveSyncExchange_HxS
            rest = key.split("GatewayURLFor", 1)[1]
            match = _ACCOUNT_ID_RE.match(rest)
            if match:
                gateways[match.group("email").lower()] = value

        for entry in sorted_accounts:
            entry = str(entry or "")
            match = _ACCOUNT_ID_RE.match(entry)
            if not match:
                continue
            email = match.group("email")
            protocol = _outlook_mac_mode_to_protocol(match.group("mode"))
            host = None
            gateway = gateways.get(email.lower())
            if gateway:
                host = gateway.split("://", 1)[-1].split("/", 1)[0]
            accounts.append(
                EmailAccount(
                    client="outlook_mac",
                    email=email,
                    protocol=protocol,
                    incoming_host=host or None,
                    outgoing_host=host or None,
                )
            )
    return accounts


def _collect_outlook_mac() -> list[EmailAccount]:
    base = (
        Path.home()
        / "Library"
        / "Group Containers"
        / "UBF8T346G9.Office"
        / "Outlook"
    )
    if not base.is_dir():
        return _collect_outlook_mac_profiles()
    accounts: list[EmailAccount] = []
    # Legacy (Outlook 2016 era): account plists under .../Accounts/
    for plist_path in base.rglob("*.plist"):
        if "Accounts" not in str(plist_path.parent):
            if plist_path.name == "ProfilePreferences.plist":
                continue
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
    accounts.extend(_collect_outlook_mac_profiles())
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


_SKIP_EMAIL_LOCAL = re.compile(
    r"^(image\d+|pid-|noreply|no-reply|mailer-daemon|postmaster)$",
    re.I,
)


def _plausible_email(value: object) -> str | None:
    text = str(value or "").strip().strip("<>").strip('"').strip()
    if "#EXT#" in text:
        text = text.split("#", 1)[0]
    match = _EMAIL_RE.search(text)
    if not match:
        return None
    email = match.group(0)
    local, _, domain = email.partition("@")
    if not local or not domain or _SKIP_EMAIL_LOCAL.match(local):
        return None
    if domain.lower() in {"example.com", "email.microsoft.com"}:
        return None
    return email


def _node_email(node: dict) -> str | None:
    lowered = {str(key).lower(): value for key, value in node.items()}
    for key in (
        "email",
        "emailaddress",
        "smtpaddress",
        "userprincipalname",
        "preferred_username",
        "unique_name",
        "emailid",
        "mail",
        "upn",
        "address",
        "account",
    ):
        if key not in lowered:
            continue
        found = _plausible_email(lowered[key])
        if found:
            return found
    return None


def _accounts_from_office_identity_json(raw: str) -> list[EmailAccount]:
    """Parse PowerShell JSON from Office Identity\\Identities (signed-in M365)."""
    if not (raw or "").strip():
        return []
    try:
        payload = json.loads(raw)
    except ValueError:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []
    accounts: list[EmailAccount] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        email = _plausible_email(item.get("Email") or item.get("email"))
        if not email or email.lower() in seen:
            continue
        seen.add(email.lower())
        name = str(item.get("Name") or item.get("FriendlyName") or "").strip() or None
        accounts.append(
            EmailAccount(
                client="outlook_classic",
                email=email,
                full_name=name,
                username=email,
                protocol="exchange",
                incoming_host="outlook.office365.com",
                outgoing_host="smtp.office365.com",
            )
        )
    return accounts


def _outlook_windows_scan_roots() -> list[tuple[Path, str]]:
    """(directory, client) pairs to search for New/classic Outlook account files."""
    roots: list[tuple[Path, str]] = []
    local = os.getenv("LOCALAPPDATA") or ""
    appdata = os.getenv("APPDATA") or ""
    if local:
        local_path = Path(local)
        roots.append((local_path / "Microsoft" / "Olk", "outlook_new"))
        packages = local_path / "Packages"
        if packages.is_dir():
            for pkg in packages.glob("Microsoft.OutlookForWindows_*"):
                roots.append((pkg / "LocalState", "outlook_new"))
        else:
            roots.append(
                (
                    local_path
                    / "Packages"
                    / "Microsoft.OutlookForWindows_8wekyb3d8bbwe"
                    / "LocalState",
                    "outlook_new",
                )
            )
        roots.append((local_path / "Microsoft" / "Outlook", "outlook_classic"))
    if appdata:
        roots.append((Path(appdata) / "Microsoft" / "Outlook", "outlook_classic"))
    return roots


def _iter_outlook_text_files(base: Path):
    if not base.is_dir():
        return
    count = 0
    for path in base.rglob("*"):
        if count >= 250:
            return
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".json", ".xml", ".txt", ".config"}:
            continue
        try:
            if path.stat().st_size > 2_000_000:
                continue
        except OSError:
            continue
        count += 1
        yield path


def _collect_outlook_new_windows() -> list[EmailAccount]:
    accounts: list[EmailAccount] = []
    for base, client in _outlook_windows_scan_roots():
        if client != "outlook_new":
            continue
        for json_path in _iter_outlook_text_files(base):
            try:
                text = json_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            try:
                data = json.loads(text)
            except ValueError:
                email = _plausible_email(json_path.stem) or _plausible_email(text)
                if email:
                    accounts.append(EmailAccount(client=client, email=email))
                continue
            for node in _walk_json(data):
                email = _node_email(node)
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
                username = node.get("username")
                username_text = (
                    _plausible_email(username) or (str(username).strip() if username else None)
                )
                accounts.append(
                    EmailAccount(
                        client=client,
                        email=email,
                        username=username_text,
                        protocol=protocol,
                        incoming_host=str(host).strip() if host else None,
                    )
                )
    return accounts


def _collect_outlook_cache_files_windows() -> list[EmailAccount]:
    """Autodiscover XML / files named like user@domain under Microsoft\\Outlook."""
    accounts: list[EmailAccount] = []
    for base, client in _outlook_windows_scan_roots():
        if client != "outlook_classic":
            continue
        for path in _iter_outlook_text_files(base):
            from_name = _plausible_email(path.stem)
            if from_name:
                accounts.append(
                    EmailAccount(
                        client=client,
                        email=from_name,
                        protocol="exchange",
                    )
                )
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in _EMAIL_RE.finditer(text):
                email = _plausible_email(match.group(0))
                if email:
                    accounts.append(EmailAccount(client=client, email=email))
    return accounts


def _collect_office_identity_windows() -> list[EmailAccount]:
    """Signed-in Microsoft 365 / Outlook identity from HKCU Office Identity."""
    raw = _run_powershell(
        r"""
$out = @()
$versions = Get-ChildItem "HKCU:\Software\Microsoft\Office" -ErrorAction SilentlyContinue |
  Where-Object { $_.PSChildName -match '^\d+\.\d+$' }
foreach ($ver in $versions) {
  $root = Join-Path $ver.PSPath "Common\Identity"
  $rootProp = Get-ItemProperty $root -ErrorAction SilentlyContinue
  if ($rootProp -and $rootProp.EmailAddress) {
    $out += [pscustomobject]@{ Email = [string]$rootProp.EmailAddress; Name = [string]$rootProp.FriendlyName }
  }
  Get-ChildItem (Join-Path $root "Identities") -ErrorAction SilentlyContinue | ForEach-Object {
    $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
    if ($p -and $p.EmailAddress) {
      $out += [pscustomobject]@{ Email = [string]$p.EmailAddress; Name = [string]$p.FriendlyName }
    }
  }
}
if ($out.Count -eq 0) { "[]" } else { $out | ConvertTo-Json -Compress }
"""
    )
    return _accounts_from_office_identity_json(raw)


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
