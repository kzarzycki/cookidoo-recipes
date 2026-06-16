import os

import pytest

from cookidoo_mcp.auth import CookieAuthStore, UnsafeCookieFileError


def test_cookie_import_writes_owner_only_file(tmp_path):
    path = tmp_path / "cookies.json"
    store = CookieAuthStore(path)

    store.import_cookie_values(
        oauth2_proxy="oauth-cookie",
        v_authenticated="v-cookie",
        domain="cookidoo.ch",
    )

    mode = path.stat().st_mode & 0o777
    assert mode == 0o600
    assert store.status().authenticated is True


def test_cookie_store_rejects_world_readable_file(tmp_path):
    path = tmp_path / "cookies.json"
    store = CookieAuthStore(path)
    store.import_cookie_values("oauth-cookie", "v-cookie")
    os.chmod(path, 0o644)

    with pytest.raises(UnsafeCookieFileError):
        store.load()


def test_missing_cookie_store_reports_missing(tmp_path):
    store = CookieAuthStore(tmp_path / "missing.json")

    status = store.status()

    assert status.authenticated is False
    assert "not found" in status.message


def test_cookie_import_reads_netscape_export(tmp_path):
    netscape = tmp_path / "cookies.txt"
    netscape.write_text(
        "\n".join(
            [
                "# Netscape HTTP Cookie File",
                ".cookidoo.ch\tTRUE\t/\tTRUE\t0\t_oauth2_proxy\toauth-cookie",
                ".cookidoo.ch\tTRUE\t/\tTRUE\t0\tv-authenticated\tv-cookie",
            ]
        ),
        encoding="utf-8",
    )
    store = CookieAuthStore(tmp_path / "cookies.json")

    store.import_netscape_file(netscape)

    assert store.status().authenticated is True
    assert store.load()[0]["key"] == "_oauth2_proxy"


def test_cookie_import_entries_writes_owner_only_file(tmp_path):
    path = tmp_path / "cookies.json"
    store = CookieAuthStore(path)

    store.import_cookie_entries(
        [
            {"key": "_oauth2_proxy", "value": "oauth-cookie", "domain": "cookidoo.ch", "path": "/"},
            {"key": "v-authenticated", "value": "v-cookie", "domain": "cookidoo.ch", "path": "/"},
            {"key": "extra", "value": "ok", "domain": "cookidoo.ch", "path": "/"},
        ]
    )

    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert store.status().authenticated is True
    assert {cookie["key"] for cookie in store.load()} == {"_oauth2_proxy", "v-authenticated", "extra"}
