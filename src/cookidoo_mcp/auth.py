from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import AuthStatus


class UnsafeCookieFileError(PermissionError):
    """Raised when a cookie jar can be read by group or world."""


@dataclass
class CookieAuthStore:
    path: Path | str

    def __post_init__(self) -> None:
        self.path = Path(self.path).expanduser()

    def import_cookie_values(
        self,
        oauth2_proxy: str,
        v_authenticated: str,
        domain: str,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {"key": "_oauth2_proxy", "value": oauth2_proxy, "domain": domain, "path": "/"},
            {"key": "v-authenticated", "value": v_authenticated, "domain": domain, "path": "/"},
        ]
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(self.path, flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        finally:
            os.chmod(self.path, 0o600)

    def import_cookie_entries(self, cookies: list[dict[str, Any]]) -> None:
        normalized: list[dict[str, str]] = []
        for cookie in cookies:
            name = cookie.get("key") or cookie.get("name")
            value = cookie.get("value")
            if not name or value is None:
                continue
            normalized.append(
                {
                    "key": str(name),
                    "value": str(value),
                    "domain": str(cookie.get("domain") or ""),
                    "path": str(cookie.get("path") or "/"),
                }
            )
        names = {cookie["key"] for cookie in normalized}
        if not {"_oauth2_proxy", "v-authenticated"}.issubset(names):
            raise ValueError("Cookidoo login did not return the required auth cookies")
        self._write_cookie_payload(normalized)

    def import_netscape_file(self, netscape_path: Path | str) -> None:
        cookies: list[dict[str, str]] = []
        for raw_line in Path(netscape_path).read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 7:
                continue
            domain, _include_subdomains, path, _secure, _expires, name, value = parts
            if name in {"_oauth2_proxy", "v-authenticated"}:
                cookies.append({"key": name, "value": value, "domain": domain.lstrip("."), "path": path})
        names = {cookie["key"] for cookie in cookies}
        if not {"_oauth2_proxy", "v-authenticated"}.issubset(names):
            raise ValueError("Netscape cookie export is missing required Cookidoo cookies")
        self._write_cookie_payload(cookies)

    def import_cookie_payload(self, payload: dict[str, Any]) -> None:
        oauth2_proxy = payload.get("oauth2_proxy") or payload.get("_oauth2_proxy")
        v_authenticated = payload.get("v_authenticated") or payload.get("v-authenticated")
        domain = payload.get("domain")
        if not oauth2_proxy or not v_authenticated or not domain:
            raise ValueError("Cookie payload must contain oauth2_proxy, v_authenticated, and domain")
        self.import_cookie_values(str(oauth2_proxy), str(v_authenticated), str(domain))

    def _write_cookie_payload(self, cookies: list[dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(self.path, flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(cookies, handle, indent=2)
        finally:
            os.chmod(self.path, 0o600)

    def _ensure_safe_permissions(self) -> None:
        mode = self.path.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise UnsafeCookieFileError(
                f"Cookie file {self.path} must be readable only by the owner; run chmod 600."
            )

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            raise FileNotFoundError(f"Cookie file {self.path} not found")
        self._ensure_safe_permissions()
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def status(self) -> AuthStatus:
        try:
            data = self.load()
        except FileNotFoundError:
            return AuthStatus(False, f"Cookie file {self.path} not found")
        except UnsafeCookieFileError as exc:
            return AuthStatus(False, str(exc))
        except json.JSONDecodeError:
            return AuthStatus(False, f"Cookie file {self.path} is not valid JSON")
        cookies = data.get("cookies", []) if isinstance(data, dict) else data
        names = {cookie.get("name") or cookie.get("key") for cookie in cookies}
        ok = {"_oauth2_proxy", "v-authenticated"}.issubset(names)
        return AuthStatus(ok, "cookie jar ready" if ok else "required Cookidoo cookies are missing")
