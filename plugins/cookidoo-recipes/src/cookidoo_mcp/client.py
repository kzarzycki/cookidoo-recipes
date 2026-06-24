from __future__ import annotations

import dataclasses
from datetime import date
from http import HTTPStatus
import json
import sys
import time
from typing import Any
from urllib.parse import urlparse

from .auth import CookieAuthStore
from .http import cookidoo_connector
from .models import RecipeDetail, RecipeDraft, RecipeSummary, SearchQuery

ALLOWED_IMAGE_HOSTS = ("assets.tmecosys.com", "ugc.assets.tmecosys.com")
COOKIDOO_IMAGE_TRANSFORMATION = "t_web_rdp_recipe_584x480"
CLOUDINARY_API_KEY = "993585863591145"
CLOUDINARY_UPLOAD_PRESET = "prod-customer-recipe-signed"
CLOUDINARY_UPLOAD_URL = "https://api-eu.cloudinary.com/v1_1/vorwerk-users-gc/image/upload"


def _cookidoo_base_url(country: str, locale: str) -> str:
    host = {
        "gb": "cookidoo.co.uk",
        "tr": "cookidoo.com.tr",
        "us": "cookidoo.thermomix.com",
        "vn": "cookidoo.thermomix.vn",
    }.get(country, f"cookidoo.{country}")
    return f"https://{host}/foundation/{locale}"


class CookidooClientError(RuntimeError):
    pass


def _sanitize_error(operation: str, exc: Exception) -> CookidooClientError:
    name = exc.__class__.__name__.lower()
    if "auth" in name or "unauthor" in str(exc).lower() or "forbidden" in str(exc).lower():
        return CookidooClientError(
            f"{operation} failed: Cookidoo authentication is missing or stale. Refresh the cookie jar."
        )
    return CookidooClientError(f"{operation} failed: Cookidoo request failed. Check filters or refresh cookies.")


def _calendar_day_to_dict(day: Any) -> dict[str, Any]:
    if dataclasses.is_dataclass(day) and not isinstance(day, type):
        return dataclasses.asdict(day)
    return day


class CookidooClient:
    def __init__(
        self,
        upstream: Any | None = None,
        auth_store: CookieAuthStore | None = None,
        allow_missing_upstream: bool = False,
        default_country: str | None = None,
        default_locale: str | None = None,
        default_url: str | None = None,
    ) -> None:
        self._upstream = upstream
        self.auth_store = auth_store
        self.allow_missing_upstream = allow_missing_upstream
        self.default_country = default_country.lower() if default_country else None
        self.default_locale = default_locale
        self.default_url = default_url

    async def _get_upstream(self) -> Any:
        if self._upstream is not None:
            return self._upstream
        if self.allow_missing_upstream:
            raise CookidooClientError("Cookidoo upstream client is not configured")
        if self.auth_store is None:
            raise CookidooClientError("Cookidoo cookie auth store is not configured")
        if not self.default_country or not self.default_locale:
            raise CookidooClientError("Cookidoo site is not configured. Run /cookidoo-login.")
        try:
            from aiohttp import ClientSession, CookieJar
            from cookidoo_api import Cookidoo
            from cookidoo_api.types import CookidooConfig, CookidooLocalizationConfig
        except Exception as exc:  # pragma: no cover - depends on optional package
            raise CookidooClientError(
                "cookidoo-api and aiohttp are required. Install the cookidoo extra or configure a fake upstream for tests."
            ) from exc
        status = self.auth_store.status()
        if not status.authenticated:
            raise CookidooClientError(status.message)
        session = ClientSession(cookie_jar=CookieJar(unsafe=True), connector=cookidoo_connector())
        cfg = CookidooConfig(
            localization=CookidooLocalizationConfig(
                country_code=self.default_country,
                language=self.default_locale,
                url=self.default_url or _cookidoo_base_url(self.default_country, self.default_locale),
            )
        )
        upstream = Cookidoo(session, cfg)
        upstream.load_cookies(self.auth_store.path)
        self._upstream = upstream
        return upstream

    async def close(self) -> None:
        upstream = self._upstream
        session = getattr(upstream, "_session", None)
        if session is not None and not session.closed:
            await session.close()

    async def auth_status(self) -> dict[str, Any]:
        if self.auth_store is None:
            return {"authenticated": False, "message": "cookie auth store is not configured"}
        status = self.auth_store.status().to_dict()
        if status.get("authenticated") and (not self.default_country or not self.default_locale):
            return {
                "authenticated": False,
                "message": "Cookidoo site is not configured. Run /cookidoo-login.",
                "cookies_authenticated": True,
            }
        return status

    async def search(self, query: SearchQuery) -> list[RecipeSummary]:
        upstream = await self._get_upstream()
        try:
            try:
                raw_results = await upstream.search_recipes(**query.upstream_params())
            except TypeError:
                raw_results = await upstream.search_recipes(
                    query=query.query,
                    locale=query.upstream_params()["locale"],
                )
        except Exception as exc:
            raise _sanitize_error("search", exc) from exc
        hits = raw_results.recipes if hasattr(raw_results, "recipes") else raw_results
        results = [RecipeSummary.from_upstream(item, "cookidoo") for item in hits]
        if query.include_my_recipes:
            own = await self.list_my_recipes(query.locale)
            needle = query.query.lower().strip()
            if needle:
                own = [item for item in own if needle in item.title.lower()]
            results.extend(own)
        return results

    async def get_recipe(self, recipe_id: str) -> RecipeDetail:
        upstream = await self._get_upstream()
        try:
            if hasattr(upstream, "get_recipe_details"):
                payload = await upstream.get_recipe_details(recipe_id)
            else:
                payload = await upstream.get_recipe(recipe_id)
        except Exception as exc:
            raise _sanitize_error("get recipe", exc) from exc
        return RecipeDetail.from_upstream(payload)

    async def list_my_recipes(self, locale: str | None = None) -> list[RecipeSummary]:
        upstream = await self._get_upstream()
        selected_locale = locale or self.default_locale
        if not selected_locale:
            raise CookidooClientError("Cookidoo site is not configured. Run /cookidoo-login.")
        try:
            if not hasattr(upstream, "list_created_recipes"):
                payloads = await self._list_created_recipes_via_internal_endpoint(upstream, selected_locale)
            else:
                payloads = await upstream.list_created_recipes(selected_locale)
        except Exception as exc:
            raise _sanitize_error("list created recipes", exc) from exc
        return [RecipeSummary.from_upstream(item, "my_recipes") for item in payloads]

    async def get_collection(self, collection_id: str, locale: str | None = None) -> dict[str, Any]:
        upstream = await self._get_upstream()
        selected_locale = locale or self.default_locale
        if not selected_locale:
            raise CookidooClientError("Cookidoo site is not configured. Run /cookidoo-login.")
        try:
            return await self._get_collection_via_internal_endpoint(upstream, collection_id, selected_locale)
        except Exception as exc:
            raise _sanitize_error("get collection", exc) from exc

    async def get_meal_plan(self, day: date) -> list[dict[str, Any]]:
        upstream = await self._get_upstream()
        try:
            days = await upstream.get_recipes_in_calendar_week(day)
        except Exception as exc:
            raise _sanitize_error("get meal plan", exc) from exc
        return [_calendar_day_to_dict(item) for item in days]

    async def add_recipe_to_plan(self, day: date, recipe_id: str, custom: bool = False) -> dict[str, Any]:
        upstream = await self._get_upstream()
        try:
            if custom:
                result = await upstream.add_custom_recipes_to_calendar(day, [recipe_id])
            else:
                result = await upstream.add_recipes_to_calendar(day, [recipe_id])
        except Exception as exc:
            raise _sanitize_error("add recipe to plan", exc) from exc
        return _calendar_day_to_dict(result)

    async def remove_recipe_from_plan(self, day: date, recipe_id: str, custom: bool = False) -> dict[str, Any]:
        upstream = await self._get_upstream()
        try:
            if custom:
                result = await upstream.remove_custom_recipe_from_calendar(day, recipe_id)
            else:
                result = await upstream.remove_recipe_from_calendar(day, recipe_id)
        except Exception as exc:
            raise _sanitize_error("remove recipe from plan", exc) from exc
        return _calendar_day_to_dict(result)

    async def create_recipe(self, draft: RecipeDraft, dry_run: bool = True) -> dict[str, Any]:
        upstream = await self._get_upstream()
        payload = draft.to_create_payload()
        if dry_run:
            return {"dry_run": True, "payload": payload}
        try:
            if hasattr(upstream, "create_recipe"):
                return await upstream.create_recipe(payload, dry_run=False)
            return await self._create_recipe_via_internal_endpoint(upstream, payload, draft.language)
        except Exception as exc:
            raise _sanitize_error("create recipe", exc) from exc

    async def upload_recipe_image(self, source_image_url: str, locale: str = "en") -> dict[str, Any]:
        upstream = await self._get_upstream()
        if not hasattr(upstream, "_session") or not hasattr(upstream, "_request_json") or not hasattr(upstream, "api_endpoint"):
            raise CookidooClientError("Cookidoo upstream does not support custom recipe image upload")
        image_url = self._normalize_source_image_url(source_image_url)
        try:
            image_bytes, content_type = await self._download_image(upstream._session, image_url)
            timestamp = int(time.time())
            signature = await upstream._request_json(
                "post",
                upstream.api_endpoint / "created-recipes" / locale / "image" / "signature",
                "sign recipe image upload",
                json={"source": "uw", "timestamp": timestamp},
                accepted_statuses=(HTTPStatus.OK,),
            )
            if not isinstance(signature, dict) or not signature.get("signature"):
                raise CookidooClientError("Cookidoo image upload signature response was invalid")
            uploaded = await self._upload_image_to_cloudinary(
                upstream._session,
                image_bytes=image_bytes,
                content_type=content_type,
                timestamp=timestamp,
                signature=str(signature["signature"]),
            )
        except CookidooClientError:
            raise
        except Exception as exc:
            raise _sanitize_error("upload recipe image", exc) from exc
        public_id = uploaded.get("public_id")
        image_format = uploaded.get("format")
        if not public_id or not image_format:
            raise CookidooClientError("Cloudinary image upload response did not contain an image key")
        return {
            "image": f"{public_id}.{image_format}",
            "public_id": public_id,
            "format": image_format,
            "secure_url": uploaded.get("secure_url"),
            "source_image_url": image_url,
            "locale": locale,
        }

    async def _list_created_recipes_via_internal_endpoint(self, upstream: Any, locale: str) -> list[dict[str, Any]]:
        if not hasattr(upstream, "_request_json") or not hasattr(upstream, "api_endpoint"):
            print("Cookidoo upstream does not support created recipe listing", file=sys.stderr)
            return []
        result = await upstream._request_json(
            "get",
            upstream.api_endpoint / "created-recipes" / locale,
            "list created recipes",
        )
        if isinstance(result, dict):
            items = result.get("items") or result.get("recipes") or result.get("data") or []
        elif isinstance(result, list):
            items = result
        else:
            items = []
        return items

    async def _get_collection_via_internal_endpoint(
        self, upstream: Any, collection_id: str, locale: str
    ) -> dict[str, Any]:
        if not hasattr(upstream, "_request_json") or not hasattr(upstream, "api_endpoint"):
            raise CookidooClientError("Cookidoo upstream does not support collection lookup")
        result = await upstream._request_json(
            "get",
            upstream.api_endpoint / "collection" / collection_id,
            "get collection",
            accepted_statuses=(HTTPStatus.OK,),
        )
        collection = result.get("collection") if isinstance(result, dict) else None
        if not isinstance(collection, dict):
            raise CookidooClientError("Cookidoo collection response did not contain collection data")
        recipes = collection.get("recipes") or []
        return {
            "id": str(collection.get("id") or collection_id),
            "title": collection.get("title") or "",
            "description": collection.get("description") or "",
            "image": collection.get("image"),
            "locale": locale,
            "recipes": [RecipeSummary.from_upstream(item, "collection").to_dict(include_raw=True) for item in recipes],
            "raw": collection,
        }

    async def _create_recipe_via_internal_endpoint(
        self, upstream: Any, payload: dict[str, Any], locale: str
    ) -> dict[str, Any]:
        if not hasattr(upstream, "_request_json") or not hasattr(upstream, "api_endpoint"):
            raise CookidooClientError("Cookidoo upstream does not support custom recipe creation")
        create_payload = payload["cookidoo"]["create"]
        patch_payload = payload["cookidoo"]["patch"]
        created = await upstream._request_json(
            "post",
            upstream.api_endpoint / "created-recipes" / locale,
            "create recipe",
            json=create_payload,
            accepted_statuses=(HTTPStatus.OK, HTTPStatus.CREATED),
        )
        if not isinstance(created, dict):
            raise CookidooClientError("Cookidoo create recipe response did not contain a recipe id")
        recipe_id = created.get("recipeId") or created.get("id")
        if not recipe_id:
            raise CookidooClientError("Cookidoo create recipe response did not contain a recipe id")
        updated = await upstream._request_json(
            "patch",
            upstream.api_endpoint / "created-recipes" / locale / str(recipe_id),
            "update recipe",
            json=patch_payload,
            accepted_statuses=(HTTPStatus.OK, HTTPStatus.NO_CONTENT),
        )
        return {
            "id": str(recipe_id),
            "url": str(upstream.api_endpoint / "created-recipes" / locale / str(recipe_id)),
            "create": created,
            "patch": updated or {"ok": True},
        }

    def _normalize_source_image_url(self, source_image_url: str) -> str:
        parsed = urlparse(source_image_url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_IMAGE_HOSTS:
            raise CookidooClientError("image upload failed: source image URL must be a Cookidoo image asset URL")
        return source_image_url.replace("{transformation}", COOKIDOO_IMAGE_TRANSFORMATION)

    async def _download_image(self, session: Any, image_url: str) -> tuple[bytes, str]:
        async with session.get(image_url) as response:
            if response.status != HTTPStatus.OK:
                raise CookidooClientError("image upload failed: source image could not be downloaded")
            content_type = response.headers.get("Content-Type", "image/jpeg").split(";", 1)[0]
            if not content_type.startswith("image/"):
                raise CookidooClientError("image upload failed: source URL did not return an image")
            return await response.read(), content_type

    async def _upload_image_to_cloudinary(
        self,
        session: Any,
        image_bytes: bytes,
        content_type: str,
        timestamp: int,
        signature: str,
    ) -> dict[str, Any]:
        try:
            from aiohttp import FormData
        except Exception as exc:  # pragma: no cover - depends on optional package
            raise CookidooClientError("aiohttp is required for Cookidoo image uploads") from exc
        form = FormData()
        form.add_field("file", image_bytes, filename="recipe-image.jpg", content_type=content_type)
        form.add_field("api_key", CLOUDINARY_API_KEY)
        form.add_field("timestamp", str(timestamp))
        form.add_field("source", "uw")
        form.add_field("upload_preset", CLOUDINARY_UPLOAD_PRESET)
        form.add_field("signature", signature)
        async with session.post(CLOUDINARY_UPLOAD_URL, data=form) as response:
            text = await response.text()
            if response.status > 299:
                raise CookidooClientError("image upload failed: Cloudinary rejected the upload")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise CookidooClientError("image upload failed: Cloudinary response was invalid") from exc
        if not isinstance(payload, dict):
            raise CookidooClientError("image upload failed: Cloudinary response was invalid")
        return payload
