from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class UnsafeConfigFileError(PermissionError):
    """Raised when local Cookidoo config can be read by group or world."""


@dataclass(frozen=True)
class CookidooConfig:
    country: str
    locale: str
    label: str
    cookie_file: str
    url: str | None = None

    @property
    def cookie_path(self) -> Path:
        return Path(self.cookie_file).expanduser()

    def to_yaml_payload(self) -> dict[str, Any]:
        site: dict[str, Any] = {
            "country": self.country,
            "locale": self.locale,
            "label": self.label,
        }
        if self.url:
            site["url"] = self.url
        return {
            "site": site,
            "cookies": {
                "file": self.cookie_file,
            },
        }

    @classmethod
    def from_yaml_payload(cls, payload: dict[str, Any]) -> "CookidooConfig":
        site = payload.get("site") if isinstance(payload, dict) else None
        cookies = payload.get("cookies") if isinstance(payload, dict) else None
        if not isinstance(site, dict) or not isinstance(cookies, dict):
            raise ValueError("Config must contain site and cookies sections")
        country = str(site.get("country") or "").strip().lower()
        locale = str(site.get("locale") or "").strip()
        label = str(site.get("label") or "").strip()
        url = str(site.get("url") or "").strip() or None
        cookie_file = str(cookies.get("file") or "").strip()
        if not country or not locale or not cookie_file:
            raise ValueError("Config must contain site.country, site.locale, and cookies.file")
        return cls(
            country=country,
            locale=locale,
            label=label or f"{country} - {locale}",
            cookie_file=cookie_file,
            url=url,
        )


def default_config_path() -> Path:
    return Path.home() / ".cookidoo-recipes" / "config.yaml"


def default_cookie_path() -> Path:
    return Path.home() / ".cookidoo-recipes" / "cookies.json"


@dataclass
class CookidooConfigStore:
    path: Path | str

    def __post_init__(self) -> None:
        self.path = Path(self.path).expanduser()

    def save(self, config: CookidooConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(self.path, flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                yaml.safe_dump(
                    config.to_yaml_payload(),
                    handle,
                    sort_keys=False,
                    allow_unicode=True,
                )
        finally:
            os.chmod(self.path, 0o600)

    def _ensure_safe_permissions(self) -> None:
        mode = self.path.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise UnsafeConfigFileError(
                f"Config file {self.path} must be readable only by the owner; run chmod 600."
            )

    def load(self) -> CookidooConfig:
        if not self.path.exists():
            raise FileNotFoundError(f"Config file {self.path} not found")
        self._ensure_safe_permissions()
        with self.path.open("r", encoding="utf-8") as handle:
            try:
                payload = yaml.safe_load(handle) or {}
            except yaml.YAMLError as exc:
                raise ValueError(f"Config file {self.path} is not valid YAML") from exc
        return CookidooConfig.from_yaml_payload(payload)

    def load_or_none(self) -> CookidooConfig | None:
        try:
            return self.load()
        except FileNotFoundError:
            return None
