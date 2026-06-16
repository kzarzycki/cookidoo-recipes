from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cookidoo_mcp.server import build_tools


def _default_cookie_path() -> str:
    return str(Path.home() / ".cookidoo-recipes" / "cookies.json")


def _print(label: str, payload: Any) -> None:
    print(json.dumps({"step": label, "payload": payload}, ensure_ascii=False, indent=2))


async def run(args: argparse.Namespace) -> int:
    tools = build_tools(args.cookie_file)
    try:
        return await _run_with_tools(args, tools)
    finally:
        close = getattr(tools.client, "close", None)
        if close is not None:
            await close()


async def _run_with_tools(args: argparse.Namespace, tools: Any) -> int:

    auth = await tools.auth_status()
    _print("auth_status", auth)
    if not auth.get("authenticated"):
        return 1

    search = await tools.search(
        query=args.query,
        country=args.country,
        locale=args.locale,
        language=args.language,
        tm_model=args.tm_model,
        limit=3,
        include_my_recipes=False,
    )
    _print("search", search)
    if search.get("error") or not search.get("results"):
        return 1

    first = search["results"][0]
    detail = await tools.get_recipe(first["id"], include_raw=False)
    _print("get_recipe", detail)
    if detail.get("error") or not detail.get("ingredients"):
        return 1

    mine = await tools.list_my_recipes(args.locale)
    _print("list_my_recipes", mine)
    if mine.get("error"):
        return 1

    title = f"Codex Live E2E {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    dry_run = await tools.create_recipe(
        title=title,
        language=args.locale,
        servings=1,
        ingredients=["100 g water"],
        steps=[
            {
                "text": "Add 100 g water.",
            },
            {
                "text": "Mix 10 sec/speed 3.",
                "time_seconds": 10,
                "speed": "3",
            },
        ],
        notes="Created by Codex live e2e verification.",
        tags=["codex-live-e2e"],
        tm_model=args.tm_model,
        dry_run=True,
    )
    _print("create_recipe_dry_run", dry_run)
    if dry_run.get("error") or "confirmation_token" not in dry_run:
        return 1

    if not args.write:
        _print("create_recipe_write", {"skipped": True, "reason": "pass --write to create the test recipe"})
        return 0

    written = await tools.create_recipe(
        title=title,
        language=args.locale,
        servings=1,
        ingredients=["100 g water"],
        steps=[
            {
                "text": "Add 100 g water.",
            },
            {
                "text": "Mix 10 sec/speed 3.",
                "time_seconds": 10,
                "speed": "3",
            },
        ],
        notes="Created by Codex live e2e verification.",
        tags=["codex-live-e2e"],
        tm_model=args.tm_model,
        dry_run=False,
        confirmation_token=dry_run["confirmation_token"],
    )
    _print("create_recipe_write", written)
    return 0 if not written.get("error") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live Cookidoo MCP e2e checks.")
    parser.add_argument("--cookie-file", default=_default_cookie_path())
    parser.add_argument("--country", default="ch")
    parser.add_argument("--locale", default="de-CH")
    parser.add_argument("--language", default="de")
    parser.add_argument("--tm-model")
    parser.add_argument("--query", default="pasta")
    parser.add_argument("--write", action="store_true", help="Create a real test recipe in Cookidoo.")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
