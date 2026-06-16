from __future__ import annotations

import argparse
import asyncio
import getpass
import json
from pathlib import Path
import sys

from .auth import CookieAuthStore
from .http import cookidoo_connector


def _default_cookie_path() -> Path:
    return Path.home() / ".cookidoo-recipes" / "cookies.json"


def _cookidoo_base_url(country: str, locale: str) -> str:
    host = "cookidoo.thermomix.com" if country == "us" else f"cookidoo.{country}"
    return f"https://{host}/foundation/{locale}"


async def _login_and_save(
    store: CookieAuthStore,
    email: str,
    password: str,
    country: str,
    locale: str,
) -> None:
    try:
        from aiohttp import ClientSession, CookieJar
        from cookidoo_api import Cookidoo
        from cookidoo_api.types import CookidooConfig, CookidooLocalizationConfig
    except Exception as exc:  # pragma: no cover - depends on optional package
        raise RuntimeError("cookidoo-api and aiohttp are required. Install with: pip install -e '.[cookidoo]'") from exc

    async with ClientSession(cookie_jar=CookieJar(unsafe=True), connector=cookidoo_connector()) as session:
        cfg = CookidooConfig(
            localization=CookidooLocalizationConfig(
                country_code=country,
                language=locale,
                url=_cookidoo_base_url(country, locale),
            ),
            email=email,
            password=password,
        )
        client = Cookidoo(session, cfg)
        await client.login()
        cookies = [
            {
                "key": cookie.key,
                "value": cookie.value,
                "domain": cookie["domain"],
                "path": cookie["path"],
            }
            for cookie in session.cookie_jar
        ]
    store.import_cookie_entries(cookies)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cookidoo helper CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    login_cmd = sub.add_parser("login", help="Log in to Cookidoo and save a persistent local cookie jar.")
    login_cmd.add_argument("--cookie-file", default=str(_default_cookie_path()))
    login_cmd.add_argument("--email")
    login_cmd.add_argument("--country", default="ch", help="Cookidoo country/TLD, for example ch, de, pl, us.")
    login_cmd.add_argument("--locale", default="de-CH", help="Cookidoo locale, for example de-CH, de-DE, pl-PL.")

    import_cmd = sub.add_parser("import-cookies", help="Import Cookidoo cookies from stdin JSON or a Netscape export.")
    import_cmd.add_argument("--cookie-file", default=str(_default_cookie_path()))
    import_cmd.add_argument("--from-json", action="store_true", help="Read JSON from stdin.")
    import_cmd.add_argument("--netscape-file", help="Path to a Netscape-format cookie export.")

    status_cmd = sub.add_parser("auth-status", help="Check local cookie auth file.")
    status_cmd.add_argument("--cookie-file", default=str(_default_cookie_path()))

    try:
        args = parser.parse_args(argv)
        store = CookieAuthStore(args.cookie_file)

        if args.command == "login":
            email = args.email or input("Cookidoo email: ")
            password = getpass.getpass("Cookidoo password: ")
            try:
                asyncio.run(_login_and_save(store, email, password, args.country, args.locale))
            except Exception as exc:
                print(json.dumps({"ok": False, "error": "Cookidoo login failed. Check credentials, 2FA, or region."}))
                print(f"cookidoo: {exc.__class__.__name__}", file=sys.stderr)
                return 1
            print(json.dumps({"ok": True, "cookie_file": str(store.path)}))
            return 0

        if args.command == "import-cookies":
            if args.netscape_file:
                store.import_netscape_file(args.netscape_file)
            else:
                payload = json.loads(sys.stdin.read())
                store.import_cookie_payload(payload)
            print(json.dumps({"ok": True, "cookie_file": str(store.path)}))
            return 0
        if args.command == "auth-status":
            print(json.dumps(store.status().to_dict()))
            return 0
        return 2
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
