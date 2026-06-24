from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
from datetime import date
from typing import Any

from .auth import CookieAuthStore
from .client import CookidooClient, CookidooClientError
from .config import CookidooConfigStore, default_config_path, default_cookie_path
from .models import RecipeDraft, SearchQuery

CATALOGUE_DISCOVERY_FACETS = (
    {"country": "de", "locale": "de-DE", "language": "de"},
    {"country": "es", "locale": "es-ES", "language": "es"},
    {"country": "fr", "locale": "fr-FR", "language": "fr"},
    {"country": "it", "locale": "it-IT", "language": "it"},
    {"country": "pl", "locale": "pl-PL", "language": "pl"},
    {"country": "us", "locale": "en-US", "language": "en"},
    {"country": "ch", "locale": "de-CH", "language": "de"},
)

TECHNIQUE_QUERY_EXPANSIONS_BY_LANGUAGE = {
    "de": ("sous-vide", "Niedertemperatur", "Schongaren"),
    "pl": ("sous-vide", "wolno gotowane", "osłona noża miksującego", "z osłoną noża miksującego"),
    "fr": ("sous-vide", "basse température"),
    "it": ("sous-vide", "bassa temperatura"),
    "es": ("sous-vide", "baja temperatura"),
    "en": ("sous-vide", "slow cooking", "low temperature"),
}


def _default_cookie_path() -> str:
    return str(default_cookie_path())


def _parse_day(day: str) -> date:
    try:
        return date.fromisoformat(day)
    except ValueError as exc:
        raise CookidooClientError(f"invalid date '{day}': expected ISO format YYYY-MM-DD") from exc


class CookidooTools:
    def __init__(self, client: Any) -> None:
        self.client = client
        self._confirmation_secret = secrets.token_hex(32)
        self._pending_writes: dict[str, dict[str, Any]] = {}

    def _error(self, operation: str, exc: Exception) -> dict[str, Any]:
        return {
            "error": {
                "code": "cookidoo_error",
                "operation": operation,
                "message": str(exc),
                "action": "Refresh Cookidoo cookies or retry with narrower inputs.",
            }
        }

    def _confirmation_token(self, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hmac.new(
            self._confirmation_secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def auth_status(self) -> dict[str, Any]:
        return await self.client.auth_status()

    async def search(self, **kwargs: Any) -> dict[str, Any]:
        query = SearchQuery(**kwargs)
        try:
            results = await self.client.search(query)
        except CookidooClientError as exc:
            return self._error("search", exc)
        return {"results": [item.to_dict() for item in results]}

    async def discover_recipes(
        self,
        query: str,
        related_queries: list[str] | None = None,
        localized_queries: list[dict[str, str]] | None = None,
        tm_model: str | None = None,
        limit_per_query: int = 8,
        max_results: int = 40,
        expand_collections: bool = True,
    ) -> dict[str, Any]:
        global_queries = self._discovery_queries(query, related_queries)
        candidates: dict[str, dict[str, Any]] = {}
        try:
            for facet in CATALOGUE_DISCOVERY_FACETS:
                for query_text in self._facet_queries(facet, global_queries, localized_queries):
                    search_query = SearchQuery(
                        query=query_text,
                        country=facet["country"],
                        locale=facet["locale"],
                        language=facet["language"],
                        tm_model=tm_model,
                        limit=limit_per_query,
                    )
                    for rank, item in enumerate(await self.client.search(search_query), start=1):
                        data = item.to_dict()
                        self._merge_candidate(
                            candidates,
                            data,
                            {
                                "kind": "search",
                                "query": query_text,
                                "country": facet["country"],
                                "locale": facet["locale"],
                                "language": facet["language"],
                                "rank": rank,
                            },
                        )
            if expand_collections:
                await self._expand_candidate_collections(candidates)
        except CookidooClientError as exc:
            return self._error("discover_recipes", exc)
        ranked = self._rank_candidates(candidates, global_queries, localized_queries)[:max_results]
        return {"results": ranked, "queries": global_queries, "facets": list(CATALOGUE_DISCOVERY_FACETS)}

    def _discovery_queries(self, query: str, related_queries: list[str] | None) -> list[str]:
        values = [query, *(related_queries or [])]
        deduped: list[str] = []
        for value in values:
            normalized = str(value or "").strip()
            if normalized and normalized not in deduped:
                deduped.append(normalized)
        return deduped

    def _facet_queries(
        self,
        facet: dict[str, str],
        global_queries: list[str],
        localized_queries: list[dict[str, str]] | None,
    ) -> list[str]:
        values = [*global_queries, *TECHNIQUE_QUERY_EXPANSIONS_BY_LANGUAGE.get(facet["language"], ())]
        for item in localized_queries or []:
            country = item.get("country")
            language = item.get("language")
            if country and country != facet["country"]:
                continue
            if language and language != facet["language"]:
                continue
            values.append(item.get("query") or "")
        return self._discovery_queries("", values)

    def _merge_candidate(
        self, candidates: dict[str, dict[str, Any]], data: dict[str, Any], provenance: dict[str, Any]
    ) -> None:
        recipe_id = str(data.get("id") or "")
        if not recipe_id:
            return
        if recipe_id not in candidates:
            candidates[recipe_id] = {
                "id": recipe_id,
                "title": data.get("title") or "",
                "source": data.get("source"),
                "url": data.get("url"),
                "total_time_minutes": data.get("total_time_minutes"),
                "provenance": [],
            }
        if provenance not in candidates[recipe_id]["provenance"]:
            candidates[recipe_id]["provenance"].append(provenance)

    async def _expand_candidate_collections(self, candidates: dict[str, dict[str, Any]]) -> None:
        collection_ids: list[str] = []
        for recipe_id in list(candidates):
            detail = await self.client.get_recipe(recipe_id)
            if hasattr(detail, "to_dict"):
                detail_data = detail.to_dict(include_raw=True)
                candidates[recipe_id]["total_time_minutes"] = detail_data.get("total_time_seconds") // 60 if detail_data.get("total_time_seconds") else candidates[recipe_id].get("total_time_minutes")
            raw = detail.raw if hasattr(detail, "raw") and isinstance(detail.raw, dict) else {}
            for collection in raw.get("collections") or []:
                collection_id = collection.get("id") if isinstance(collection, dict) else None
                if collection_id and collection_id not in collection_ids:
                    collection_ids.append(collection_id)
        for collection_id in collection_ids:
            collection = await self.client.get_collection(collection_id)
            for rank, item in enumerate(collection.get("recipes", []), start=1):
                self._merge_candidate(
                    candidates,
                    item,
                    {
                        "kind": "collection",
                        "collection_id": collection_id,
                        "collection_title": collection.get("title"),
                        "rank": rank,
                    },
                )

    def _rank_candidates(
        self,
        candidates: dict[str, dict[str, Any]],
        global_queries: list[str],
        localized_queries: list[dict[str, str]] | None,
    ) -> list[dict[str, Any]]:
        term_source = " ".join(
            [*global_queries, *[item.get("query", "") for item in localized_queries or []]]
        )
        terms = {term for term in re.findall(r"[\wąćęłńóśźżàâçéèêëîïôûùüÿñæœß-]{4,}", term_source.lower())}
        for item in candidates.values():
            title = (item.get("title") or "").lower()
            matched_terms = sorted(term for term in terms if term in title)
            best_rank = min(
                (entry.get("rank", 9999) for entry in item.get("provenance", []) if entry.get("kind") == "search"),
                default=9999,
            )
            collection_bonus = 2 if any(entry.get("kind") == "collection" for entry in item.get("provenance", [])) else 0
            item["score"] = len(matched_terms) * 10 + collection_bonus + max(0, 20 - min(best_rank, 20))
            item["matched_terms"] = matched_terms
        return sorted(candidates.values(), key=lambda item: (-item["score"], item.get("id", "")))

    async def get_recipe(self, recipe_id: str, include_raw: bool = False) -> dict[str, Any]:
        try:
            detail = await self.client.get_recipe(recipe_id)
        except CookidooClientError as exc:
            return self._error("get_recipe", exc)
        return detail.to_dict(include_raw=include_raw) if hasattr(detail, "to_dict") else detail

    async def list_my_recipes(self, locale: str | None = None) -> dict[str, Any]:
        try:
            results = await self.client.list_my_recipes(locale)
        except CookidooClientError as exc:
            return self._error("list_my_recipes", exc)
        return {"results": [item.to_dict() for item in results]}

    async def get_collection(self, collection_id: str, locale: str | None = None) -> dict[str, Any]:
        try:
            return await self.client.get_collection(collection_id, locale)
        except CookidooClientError as exc:
            return self._error("get_collection", exc)

    async def get_meal_plan(self, day: str) -> dict[str, Any]:
        try:
            days = await self.client.get_meal_plan(_parse_day(day))
        except CookidooClientError as exc:
            return self._error("get_meal_plan", exc)
        return {"days": days}

    async def add_recipe_to_plan(
        self,
        day: str,
        recipe_id: str,
        custom: bool = False,
        dry_run: bool = True,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        try:
            parsed_day = _parse_day(day)
        except CookidooClientError as exc:
            return self._error("add_recipe_to_plan", exc)
        payload = {
            "operation": "add_recipe_to_plan",
            "day": day,
            "recipe_id": recipe_id,
            "custom": custom,
        }
        token = self._confirmation_token(payload)
        if dry_run:
            self._pending_writes[token] = payload
            return {"dry_run": True, "payload": payload, "confirmation_token": token}
        if not confirmation_token or confirmation_token not in self._pending_writes:
            return {
                "error": {
                    "code": "confirmation_required",
                    "message": "Run a dry run first, review it, then repeat with the returned confirmation_token.",
                }
            }
        if self._pending_writes[confirmation_token] != payload:
            return {
                "error": {
                    "code": "confirmation_mismatch",
                    "message": "The meal plan change differs from the dry run. Run a new dry run.",
                }
            }
        try:
            result = await self.client.add_recipe_to_plan(parsed_day, recipe_id, custom=custom)
        except CookidooClientError as exc:
            return self._error("add_recipe_to_plan", exc)
        self._pending_writes.pop(confirmation_token, None)
        return result

    async def remove_recipe_from_plan(
        self,
        day: str,
        recipe_id: str,
        custom: bool = False,
        dry_run: bool = True,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        try:
            parsed_day = _parse_day(day)
        except CookidooClientError as exc:
            return self._error("remove_recipe_from_plan", exc)
        payload = {
            "operation": "remove_recipe_from_plan",
            "day": day,
            "recipe_id": recipe_id,
            "custom": custom,
        }
        token = self._confirmation_token(payload)
        if dry_run:
            self._pending_writes[token] = payload
            return {"dry_run": True, "payload": payload, "confirmation_token": token}
        if not confirmation_token or confirmation_token not in self._pending_writes:
            return {
                "error": {
                    "code": "confirmation_required",
                    "message": "Run a dry run first, review it, then repeat with the returned confirmation_token.",
                }
            }
        if self._pending_writes[confirmation_token] != payload:
            return {
                "error": {
                    "code": "confirmation_mismatch",
                    "message": "The meal plan change differs from the dry run. Run a new dry run.",
                }
            }
        try:
            result = await self.client.remove_recipe_from_plan(parsed_day, recipe_id, custom=custom)
        except CookidooClientError as exc:
            return self._error("remove_recipe_from_plan", exc)
        self._pending_writes.pop(confirmation_token, None)
        return result

    async def upload_recipe_image(
        self,
        source_image_url: str,
        locale: str = "en",
        dry_run: bool = True,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "operation": "upload_recipe_image",
            "source_image_url": source_image_url,
            "locale": locale,
        }
        token = self._confirmation_token(payload)
        if dry_run:
            self._pending_writes[token] = payload
            return {"dry_run": True, "payload": payload, "confirmation_token": token}
        if not confirmation_token or confirmation_token not in self._pending_writes:
            return {
                "error": {
                    "code": "confirmation_required",
                    "message": "Run a dry run first, review it, then repeat with the returned confirmation_token.",
                }
            }
        if self._pending_writes[confirmation_token] != payload:
            return {
                "error": {
                    "code": "confirmation_mismatch",
                    "message": "The image upload payload changed after dry run. Run a new dry run.",
                }
            }
        try:
            result = await self.client.upload_recipe_image(source_image_url, locale)
        except CookidooClientError as exc:
            return self._error("upload_recipe_image", exc)
        self._pending_writes.pop(confirmation_token, None)
        return result

    async def create_recipe(
        self,
        title: str,
        ingredients: list[str],
        steps: list[dict[str, Any] | str],
        language: str = "en",
        servings: int | None = None,
        image: str | None = None,
        notes: str = "",
        tags: list[str] | None = None,
        tm_model: str | None = None,
        dry_run: bool = True,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        draft = RecipeDraft(
            title=title,
            language=language,
            servings=servings,
            ingredients=ingredients,
            steps=steps,
            image=image,
            notes=notes,
            tags=tags or [],
            tm_model=tm_model,
        )
        payload = draft.to_create_payload()
        token = self._confirmation_token(payload)
        if dry_run:
            result = await self.client.create_recipe(draft, dry_run=True)
            result["confirmation_token"] = token
            self._pending_writes[token] = payload
            return result
        if not confirmation_token or confirmation_token not in self._pending_writes:
            return {
                "error": {
                    "code": "confirmation_required",
                    "message": "Run a dry run first, review it, then repeat with the returned confirmation_token.",
                }
            }
        if self._pending_writes[confirmation_token] != payload:
            return {
                "error": {
                    "code": "confirmation_mismatch",
                    "message": "The recipe payload changed after dry run. Run a new dry run.",
                }
            }
        try:
            result = await self.client.create_recipe(draft, dry_run=False)
        except CookidooClientError as exc:
            return self._error("create_recipe", exc)
        self._pending_writes.pop(confirmation_token, None)
        return result


def build_tools(
    cookie_file: str | None = None,
    default_country: str | None = None,
    default_locale: str | None = None,
    default_url: str | None = None,
    config_file: str | None = None,
) -> CookidooTools:
    config = CookidooConfigStore(config_file or default_config_path()).load_or_none()
    if config is not None:
        cookie_file = cookie_file or config.cookie_file
        default_country = default_country or config.country
        default_locale = default_locale or config.locale
        default_url = default_url or config.url
    auth_store = CookieAuthStore(cookie_file or str(default_cookie_path()))
    client = CookidooClient(
        auth_store=auth_store,
        allow_missing_upstream=False,
        default_country=default_country,
        default_locale=default_locale,
        default_url=default_url,
    )
    return CookidooTools(client)


def build_mcp(tools: CookidooTools) -> Any:
    try:
        from fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover - depends on optional package
        raise RuntimeError("fastmcp is required to run the MCP server") from exc

    mcp = FastMCP("cookidoo-recipes")

    @mcp.tool()
    async def cookidoo_auth_status() -> dict[str, Any]:
        return await tools.auth_status()

    @mcp.tool()
    async def cookidoo_search(
        query: str = "",
        country: str | None = None,
        locale: str = "en",
        language: str | None = None,
        include_ingredients: list[str] | None = None,
        exclude_ingredients: list[str] | None = None,
        difficulty: str | None = None,
        max_prep_time_minutes: int | None = None,
        max_total_time_minutes: int | None = None,
        servings: int | None = None,
        min_rating: float | None = None,
        tags: list[str] | None = None,
        tm_model: str | None = None,
        page: int = 1,
        limit: int = 10,
        include_my_recipes: bool = False,
    ) -> dict[str, Any]:
        return await tools.search(
            query=query,
            country=country,
            locale=locale,
            language=language,
            include_ingredients=include_ingredients,
            exclude_ingredients=exclude_ingredients,
            difficulty=difficulty,
            max_prep_time_minutes=max_prep_time_minutes,
            max_total_time_minutes=max_total_time_minutes,
            servings=servings,
            min_rating=min_rating,
            tags=tags,
            tm_model=tm_model,
            page=page,
            limit=limit,
            include_my_recipes=include_my_recipes,
        )

    @mcp.tool()
    async def cookidoo_discover_recipes(
        query: str,
        related_queries: list[str] | None = None,
        localized_queries: list[dict[str, str]] | None = None,
        tm_model: str | None = None,
        limit_per_query: int = 8,
        max_results: int = 40,
        expand_collections: bool = True,
    ) -> dict[str, Any]:
        return await tools.discover_recipes(
            query=query,
            related_queries=related_queries,
            localized_queries=localized_queries,
            tm_model=tm_model,
            limit_per_query=limit_per_query,
            max_results=max_results,
            expand_collections=expand_collections,
        )

    @mcp.tool()
    async def cookidoo_get_recipe(recipe_id: str, include_raw: bool = False) -> dict[str, Any]:
        return await tools.get_recipe(recipe_id, include_raw=include_raw)

    @mcp.tool()
    async def cookidoo_list_my_recipes(locale: str | None = None) -> dict[str, Any]:
        return await tools.list_my_recipes(locale)

    @mcp.tool()
    async def cookidoo_get_collection(collection_id: str, locale: str | None = None) -> dict[str, Any]:
        return await tools.get_collection(collection_id, locale=locale)

    @mcp.tool()
    async def cookidoo_get_meal_plan(day: str) -> dict[str, Any]:
        return await tools.get_meal_plan(day)

    @mcp.tool()
    async def cookidoo_add_recipe_to_plan(
        day: str,
        recipe_id: str,
        custom: bool = False,
        dry_run: bool = True,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        return await tools.add_recipe_to_plan(
            day=day,
            recipe_id=recipe_id,
            custom=custom,
            dry_run=dry_run,
            confirmation_token=confirmation_token,
        )

    @mcp.tool()
    async def cookidoo_remove_recipe_from_plan(
        day: str,
        recipe_id: str,
        custom: bool = False,
        dry_run: bool = True,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        return await tools.remove_recipe_from_plan(
            day=day,
            recipe_id=recipe_id,
            custom=custom,
            dry_run=dry_run,
            confirmation_token=confirmation_token,
        )

    @mcp.tool()
    async def cookidoo_upload_recipe_image(
        source_image_url: str,
        locale: str = "en",
        dry_run: bool = True,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        return await tools.upload_recipe_image(
            source_image_url=source_image_url,
            locale=locale,
            dry_run=dry_run,
            confirmation_token=confirmation_token,
        )

    @mcp.tool()
    async def cookidoo_create_recipe(
        title: str,
        ingredients: list[str],
        steps: list[dict[str, Any] | str],
        language: str = "en",
        servings: int | None = None,
        image: str | None = None,
        notes: str = "",
        tags: list[str] | None = None,
        tm_model: str | None = None,
        dry_run: bool = True,
        confirmation_token: str | None = None,
    ) -> dict[str, Any]:
        return await tools.create_recipe(
            title=title,
            ingredients=ingredients,
            steps=steps,
            language=language,
            servings=servings,
            image=image,
            notes=notes,
            tags=tags,
            tm_model=tm_model,
            dry_run=dry_run,
            confirmation_token=confirmation_token,
        )

    return mcp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Cookidoo MCP server.")
    parser.add_argument(
        "--config-file",
        default=os.environ.get("COOKIDOO_CONFIG_FILE", str(default_config_path())),
        help="Path to the local Cookidoo YAML config.",
    )
    parser.add_argument(
        "--cookie-file",
        default=os.environ.get("COOKIDOO_COOKIE_FILE"),
        help="Path to the Cookidoo cookie jar JSON file.",
    )
    parser.add_argument(
        "--country",
        default=os.environ.get("COOKIDOO_COUNTRY"),
        help="Cookidoo account country/TLD used for the upstream host.",
    )
    parser.add_argument(
        "--locale",
        default=os.environ.get("COOKIDOO_LOCALE"),
        help="Cookidoo account locale used for account endpoints.",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("COOKIDOO_URL"),
        help="Cookidoo foundation URL for the selected account site.",
    )
    args = parser.parse_args(argv)
    try:
        tools = build_tools(
            args.cookie_file,
            default_country=args.country,
            default_locale=args.locale,
            default_url=args.url,
            config_file=args.config_file,
        )
        mcp = build_mcp(tools)
        mcp.run(show_banner=False)
        return 0
    except KeyboardInterrupt:
        return 130
    except (CookidooClientError, PermissionError, RuntimeError, ValueError) as exc:
        print(f"cookidoo-mcp: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
