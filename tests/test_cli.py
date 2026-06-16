import json
import os

from cookidoo_mcp.config import CookidooConfig, CookidooConfigStore
from cookidoo_mcp import cli


def test_login_with_explicit_site_writes_config(monkeypatch, tmp_path, capsys):
    cookie_file = tmp_path / "cookies.json"
    config_file = tmp_path / "config.yaml"
    calls = []

    async def fake_login(store, email, password, country, locale):
        calls.append((store.path, email, password, country, locale))
        store.import_cookie_entries(
            [
                {"key": "_oauth2_proxy", "value": "oauth", "domain": "cookidoo.de", "path": "/"},
                {"key": "v-authenticated", "value": "v", "domain": "cookidoo.de", "path": "/"},
            ]
        )

    monkeypatch.setattr(cli, "_login_and_save", fake_login)
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "secret")
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)

    rc = cli.main(
        [
            "login",
            "--country",
            "de",
            "--locale",
            "de-DE",
            "--email",
            "user@example.com",
            "--cookie-file",
            str(cookie_file),
            "--config-file",
            str(config_file),
        ]
    )

    assert rc == 0
    assert calls == [(cookie_file, "user@example.com", "secret", "de", "de-DE")]
    saved = CookidooConfigStore(config_file).load()
    assert saved.country == "de"
    assert saved.locale == "de-DE"
    assert saved.label == "de - de-DE"
    assert saved.cookie_file == str(cookie_file)
    assert json.loads(capsys.readouterr().out)["config_file"] == str(config_file)


def test_login_without_site_requires_interactive_terminal(monkeypatch, tmp_path, capsys):
    class NonInteractiveStdin:
        def isatty(self):
            return False

    monkeypatch.setattr(cli.sys, "stdin", NonInteractiveStdin())

    rc = cli.main(["login", "--cookie-file", str(tmp_path / "cookies.json")])

    assert rc == 2
    assert "Interactive login needs a terminal" in capsys.readouterr().err


def test_login_with_site_and_email_requires_terminal_for_password(monkeypatch, tmp_path, capsys):
    class NonInteractiveStdin:
        def isatty(self):
            return False

    monkeypatch.setattr(cli.sys, "stdin", NonInteractiveStdin())

    rc = cli.main(
        [
            "login",
            "--country",
            "de",
            "--locale",
            "de-DE",
            "--email",
            "user@example.com",
            "--cookie-file",
            str(tmp_path / "cookies.json"),
            "--config-file",
            str(tmp_path / "config.yaml"),
        ]
    )

    assert rc == 2
    err = capsys.readouterr().err
    assert "Interactive login needs a terminal" in err
    assert "traceback" not in err.lower()


def test_auth_status_reports_unsafe_config_without_traceback(tmp_path, capsys):
    config_file = tmp_path / "config.yaml"
    CookidooConfigStore(config_file).save(
        CookidooConfig(
            country="de",
            locale="de-DE",
            label="Germany - German",
            cookie_file=str(tmp_path / "cookies.json"),
        )
    )
    os.chmod(config_file, 0o640)

    rc = cli.main(["auth-status", "--config-file", str(config_file)])

    assert rc == 2
    err = capsys.readouterr().err
    assert "chmod 600" in err
    assert "traceback" not in err.lower()


def test_auth_status_reports_malformed_config_without_traceback(tmp_path, capsys):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("site: [", encoding="utf-8")
    config_file.chmod(0o600)

    rc = cli.main(["auth-status", "--config-file", str(config_file)])

    assert rc == 2
    err = capsys.readouterr().err
    assert "Config file" in err
    assert "traceback" not in err.lower()
