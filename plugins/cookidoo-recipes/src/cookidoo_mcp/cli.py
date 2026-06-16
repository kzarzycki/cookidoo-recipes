from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import sys

from .auth import CookieAuthStore
from .config import CookidooConfig, CookidooConfigStore, default_config_path, default_cookie_path
from .http import cookidoo_connector
from .sites import SelectedSite, choose_site_interactively, fetch_site_options, site_from_url


class InteractiveLoginRequired(RuntimeError):
    pass


def _cookidoo_base_url(country: str, locale: str) -> str:
    host = {
        "gb": "cookidoo.co.uk",
        "tr": "cookidoo.com.tr",
        "us": "cookidoo.thermomix.com",
        "vn": "cookidoo.thermomix.vn",
    }.get(country, f"cookidoo.{country}")
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


def _config_from_site(selected: SelectedSite, cookie_file: str) -> CookidooConfig:
    return CookidooConfig(
        country=selected.country,
        locale=selected.locale,
        label=selected.label,
        cookie_file=cookie_file,
        url=selected.url,
    )


def _resolve_login_config(args: argparse.Namespace, existing: CookidooConfig | None) -> CookidooConfig:
    cookie_file = args.cookie_file or (existing.cookie_file if existing else str(default_cookie_path()))
    if args.country and args.locale:
        return CookidooConfig(
            country=args.country.lower(),
            locale=args.locale,
            label=f"{args.country.lower()} - {args.locale}",
            cookie_file=cookie_file,
            url=_cookidoo_base_url(args.country.lower(), args.locale),
        )
    if args.country or args.locale:
        raise ValueError("--country and --locale must be provided together")
    if args.site_url:
        sites = fetch_site_options()
        selected = site_from_url(args.site_url, sites)
        if selected is None:
            raise ValueError("Could not resolve Cookidoo country and locale from --site-url")
        return _config_from_site(selected, cookie_file)
    if existing is not None:
        return CookidooConfig(
            country=existing.country,
            locale=existing.locale,
            label=existing.label,
            cookie_file=cookie_file,
            url=existing.url,
        )
    if not sys.stdin.isatty():
        raise InteractiveLoginRequired("Interactive login needs a terminal.")
    sites = fetch_site_options()
    selected = choose_site_interactively(sites, sys.stdin, sys.stderr)
    return _config_from_site(selected, cookie_file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cookidoo helper CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    login_cmd = sub.add_parser("login", help="Log in to Cookidoo and save a persistent local cookie jar.")
    login_cmd.add_argument("--config-file", default=str(default_config_path()))
    login_cmd.add_argument("--cookie-file")
    login_cmd.add_argument("--email")
    login_cmd.add_argument("--country", help="Cookidoo country/TLD. Usually selected through the site picker.")
    login_cmd.add_argument("--locale", help="Cookidoo locale. Usually selected through the site picker.")
    login_cmd.add_argument("--site-url", help="Cookidoo URL such as https://cookidoo.<site>/foundation/<locale>/explore.")

    import_cmd = sub.add_parser("import-cookies", help="Import Cookidoo cookies from stdin JSON or a Netscape export.")
    import_cmd.add_argument("--config-file", default=str(default_config_path()))
    import_cmd.add_argument("--cookie-file")
    import_cmd.add_argument("--country", help="Cookidoo country/TLD for the imported cookies.")
    import_cmd.add_argument("--locale", help="Cookidoo locale for the imported cookies.")
    import_cmd.add_argument("--site-url", help="Cookidoo URL used to resolve country and locale.")
    import_cmd.add_argument("--from-json", action="store_true", help="Read JSON from stdin.")
    import_cmd.add_argument("--netscape-file", help="Path to a Netscape-format cookie export.")

    status_cmd = sub.add_parser("auth-status", help="Check local cookie auth file.")
    status_cmd.add_argument("--config-file", default=str(default_config_path()))
    status_cmd.add_argument("--cookie-file")

    try:
        args = parser.parse_args(argv)
        config_store = CookidooConfigStore(getattr(args, "config_file", default_config_path()))
        existing_config = config_store.load_or_none()
        cookie_file = args.cookie_file or (existing_config.cookie_file if existing_config else str(default_cookie_path()))
        store = CookieAuthStore(cookie_file)

        if args.command == "login":
            login_config = _resolve_login_config(args, existing_config)
            if not sys.stdin.isatty():
                raise InteractiveLoginRequired("Interactive login needs a terminal.")
            store = CookieAuthStore(login_config.cookie_file)
            email = args.email or input("Cookidoo email: ")
            password = getpass.getpass("Cookidoo password: ")
            try:
                asyncio.run(_login_and_save(store, email, password, login_config.country, login_config.locale))
            except Exception as exc:
                print(json.dumps({"ok": False, "error": "Cookidoo login failed. Check credentials, 2FA, or region."}))
                print(f"cookidoo: {exc.__class__.__name__}", file=sys.stderr)
                return 1
            config_store.save(login_config)
            print(json.dumps({"ok": True, "cookie_file": str(store.path), "config_file": str(config_store.path)}))
            return 0

        if args.command == "import-cookies":
            if args.netscape_file:
                store.import_netscape_file(args.netscape_file)
            else:
                payload = json.loads(sys.stdin.read())
                store.import_cookie_payload(payload)
            if args.country or args.locale or args.site_url:
                import_config = _resolve_login_config(args, existing_config)
                config_store.save(import_config)
            print(json.dumps({"ok": True, "cookie_file": str(store.path), "config_file": str(config_store.path)}))
            return 0
        if args.command == "auth-status":
            payload = store.status().to_dict()
            payload["config_file"] = str(config_store.path)
            payload["site_configured"] = existing_config is not None
            if existing_config is not None:
                payload["site"] = {
                    "country": existing_config.country,
                    "locale": existing_config.locale,
                    "label": existing_config.label,
                }
            print(json.dumps(payload))
            return 0
        return 2
    except InteractiveLoginRequired as exc:
        print(str(exc), file=sys.stderr)
        print("Run this command in a terminal: cookidoo login", file=sys.stderr)
        return 2
    except (PermissionError, ValueError) as exc:
        print(f"cookidoo: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
