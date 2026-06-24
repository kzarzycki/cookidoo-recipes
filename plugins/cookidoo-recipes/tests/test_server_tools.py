import asyncio

from cookidoo_mcp.client import CookidooClient
from cookidoo_mcp.models import RecipeDetail, RecipeSummary
from cookidoo_mcp.server import CookidooTools


class FakeClient:
    async def auth_status(self):
        return {"authenticated": True, "message": "cookie jar ready"}

    async def search(self, query):
        assert query.tm_model is None
        return []

    async def get_recipe(self, recipe_id):
        return {"id": recipe_id, "title": "Recipe"}

    async def list_my_recipes(self, locale="de-CH"):
        return []

    async def get_collection(self, collection_id, locale="pl-PL"):
        return {
            "id": collection_id,
            "title": "SOUS-VIDE",
            "recipes": [{"id": "r500651", "title": "Steki z polędwicy wołowej"}],
            "locale": locale,
        }

    async def upload_recipe_image(self, source_image_url, locale="en"):
        return {
            "image": "prod/img/customer-recipe/uploaded.jpg",
            "source_image_url": source_image_url,
            "locale": locale,
        }

    async def create_recipe(self, draft, dry_run=True):
        return {"dry_run": dry_run, "payload": draft.to_create_payload()}

    async def get_meal_plan(self, day):
        return [
            {
                "id": day.isoformat(),
                "title": "Monday",
                "recipes": [{"id": "r1", "name": "Chicken Chili"}],
                "customer_recipe_ids": [],
            }
        ]

    async def add_recipe_to_plan(self, day, recipe_id, custom=False):
        return {
            "id": day.isoformat(),
            "title": "Monday",
            "recipes": [],
            "customer_recipe_ids": [recipe_id] if custom else [],
            "custom": custom,
        }

    async def remove_recipe_from_plan(self, day, recipe_id, custom=False):
        return {"id": day.isoformat(), "title": "Monday", "recipes": [], "customer_recipe_ids": [], "custom": custom}


class DiscoveryFakeClient:
    def __init__(self):
        self.search_queries = []
        self.collection_ids = []

    async def auth_status(self):
        return {"authenticated": True, "message": "cookie jar ready"}

    async def search(self, query):
        self.search_queries.append((query.country, query.locale, query.language, query.query))
        if query.country == "pl" and query.query == "z osłoną noża miksującego":
            return [RecipeSummary(id="r500651", title="Steki z polędwicy wołowej")]
        return []

    async def get_recipe(self, recipe_id):
        return RecipeDetail.from_upstream(
            {
                "id": recipe_id,
                "name": "Steki z polędwicy wołowej",
                "collections": [{"id": "col272853", "name": "SOUS-VIDE"}],
                "ingredients": [{"description": "4", "name": "steki z polędwicy wołowej"}],
                "total_time": 8400,
            }
        )

    async def get_collection(self, collection_id, locale="pl-PL"):
        self.collection_ids.append(collection_id)
        return {
            "id": collection_id,
            "title": "SOUS-VIDE",
            "recipes": [
                {"id": "r753622", "title": "Steki wołowe sous-vide", "source": "collection"},
                {"id": "r500651", "title": "Steki z polędwicy wołowej", "source": "collection"},
            ],
        }


def test_tools_return_auth_status():
    tools = CookidooTools(FakeClient())

    assert asyncio.run(tools.auth_status()) == {"authenticated": True, "message": "cookie jar ready"}


def test_tools_search_builds_query():
    tools = CookidooTools(FakeClient())

    assert asyncio.run(tools.search(query="chicken", include_my_recipes=True)) == {"results": []}


def test_tools_get_collection_returns_recipes():
    tools = CookidooTools(FakeClient())

    result = asyncio.run(tools.get_collection("col272853", locale="pl-PL"))

    assert result["id"] == "col272853"
    assert result["recipes"][0]["id"] == "r500651"
    assert result["locale"] == "pl-PL"


def test_tools_discover_recipes_searches_multiple_countries_and_expands_collections():
    client = DiscoveryFakeClient()
    tools = CookidooTools(client)

    result = asyncio.run(tools.discover_recipes(
        query="slow-cooking tenderloin in savory sauce",
        localized_queries=[
            {"country": "pl", "language": "pl", "query": "z osłoną noża miksującego"},
            {"country": "pl", "language": "pl", "query": "polędwicy wołowej"},
        ],
        limit_per_query=5,
    ))

    assert ("pl", "pl-PL", "pl", "z osłoną noża miksującego") in client.search_queries
    assert ("ch", "de-CH", "de", "z osłoną noża miksującego") not in client.search_queries
    assert "col272853" in client.collection_ids
    assert [item["id"] for item in result["results"]] == ["r500651", "r753622"]
    assert "polędwicy" in result["results"][0]["matched_terms"]
    assert result["results"][0]["provenance"][0]["kind"] == "search"
    assert result["results"][0]["provenance"][1]["kind"] == "collection"


def test_tools_create_defaults_to_dry_run():
    tools = CookidooTools(FakeClient())

    result = asyncio.run(tools.create_recipe(
        title="Saved recipe",
        ingredients=["1 egg"],
        steps=[{"title": "Mix", "text": "Mix.", "speed": "3"}],
    ))

    assert result["dry_run"] is True
    assert "tools" not in result["payload"]
    assert result["confirmation_token"]


def test_tools_create_accepts_machine_when_supplied():
    tools = CookidooTools(FakeClient())

    result = asyncio.run(tools.create_recipe(
        title="Saved recipe",
        ingredients=["1 egg"],
        steps=[{"title": "Mix", "text": "Mix.", "speed": "3"}],
        tm_model="TM7",
    ))

    assert result["payload"]["tools"] == ["TM7"]


def test_tools_create_accepts_image_key():
    tools = CookidooTools(FakeClient())

    result = asyncio.run(tools.create_recipe(
        title="Saved recipe",
        ingredients=["1 egg"],
        steps=["Mix."],
        image="prod/img/customer-recipe/saved.jpg",
    ))

    assert result["payload"]["image"] == "prod/img/customer-recipe/saved.jpg"
    assert result["payload"]["cookidoo"]["patch"]["image"] == "prod/img/customer-recipe/saved.jpg"


def test_tools_upload_recipe_image_defaults_to_dry_run():
    tools = CookidooTools(FakeClient())

    result = asyncio.run(tools.upload_recipe_image(
        source_image_url="https://assets.tmecosys.com/image/upload/{transformation}/img/recipe/source",
        locale="en",
    ))

    assert result["dry_run"] is True
    assert result["payload"]["source_image_url"].startswith("https://assets.tmecosys.com/")
    assert result["confirmation_token"]


def test_tools_upload_recipe_image_requires_confirmation_token_for_write():
    tools = CookidooTools(FakeClient())

    result = asyncio.run(tools.upload_recipe_image(
        source_image_url="https://assets.tmecosys.com/image/upload/{transformation}/img/recipe/source",
        locale="en",
        dry_run=False,
    ))

    assert result["error"]["code"] == "confirmation_required"


def test_tools_upload_recipe_image_allows_write_after_matching_dry_run():
    tools = CookidooTools(FakeClient())
    dry_run = asyncio.run(tools.upload_recipe_image(
        source_image_url="https://assets.tmecosys.com/image/upload/{transformation}/img/recipe/source",
        locale="en",
    ))

    result = asyncio.run(tools.upload_recipe_image(
        source_image_url="https://assets.tmecosys.com/image/upload/{transformation}/img/recipe/source",
        locale="en",
        dry_run=False,
        confirmation_token=dry_run["confirmation_token"],
    ))

    assert result["image"] == "prod/img/customer-recipe/uploaded.jpg"
    assert result["locale"] == "en"


def test_tools_create_requires_confirmation_token_for_write():
    tools = CookidooTools(FakeClient())

    result = asyncio.run(tools.create_recipe(
        title="Saved recipe",
        ingredients=["1 egg"],
        steps=[{"title": "Mix", "text": "Mix.", "speed": "3"}],
        dry_run=False,
    ))

    assert result["error"]["code"] == "confirmation_required"


def test_tools_create_allows_write_after_matching_dry_run():
    tools = CookidooTools(FakeClient())
    dry_run = asyncio.run(tools.create_recipe(
        title="Saved recipe",
        ingredients=["1 egg"],
        steps=[{"title": "Mix", "text": "Mix.", "speed": "3"}],
    ))

    result = asyncio.run(tools.create_recipe(
        title="Saved recipe",
        ingredients=["1 egg"],
        steps=[{"title": "Mix", "text": "Mix.", "speed": "3"}],
        dry_run=False,
        confirmation_token=dry_run["confirmation_token"],
    ))

    assert result["dry_run"] is False


def test_tools_get_meal_plan_groups_days():
    tools = CookidooTools(FakeClient())

    result = asyncio.run(tools.get_meal_plan(day="2026-06-22"))

    assert result["days"][0]["id"] == "2026-06-22"
    assert result["days"][0]["recipes"][0]["id"] == "r1"


def test_tools_add_to_plan_defaults_to_dry_run():
    tools = CookidooTools(FakeClient())

    result = asyncio.run(tools.add_recipe_to_plan(day="2026-06-22", recipe_id="r1"))

    assert result["dry_run"] is True
    assert result["confirmation_token"]


def test_tools_add_to_plan_requires_confirmation_token_for_write():
    tools = CookidooTools(FakeClient())

    result = asyncio.run(tools.add_recipe_to_plan(day="2026-06-22", recipe_id="r1", dry_run=False))

    assert result["error"]["code"] == "confirmation_required"


def test_tools_add_to_plan_rejects_mismatched_token():
    tools = CookidooTools(FakeClient())
    dry_run = asyncio.run(tools.add_recipe_to_plan(day="2026-06-22", recipe_id="r1"))

    result = asyncio.run(tools.add_recipe_to_plan(
        day="2026-06-22",
        recipe_id="r2",
        dry_run=False,
        confirmation_token=dry_run["confirmation_token"],
    ))

    assert result["error"]["code"] == "confirmation_mismatch"


def test_tools_add_to_plan_allows_write_after_matching_dry_run():
    tools = CookidooTools(FakeClient())
    dry_run = asyncio.run(tools.add_recipe_to_plan(day="2026-06-22", recipe_id="r1"))

    result = asyncio.run(tools.add_recipe_to_plan(
        day="2026-06-22",
        recipe_id="r1",
        dry_run=False,
        confirmation_token=dry_run["confirmation_token"],
    ))

    assert result["id"] == "2026-06-22"
    assert result["custom"] is False


def test_tools_add_to_plan_custom_routes_to_custom_recipe():
    tools = CookidooTools(FakeClient())
    dry_run = asyncio.run(tools.add_recipe_to_plan(day="2026-06-22", recipe_id="mine1", custom=True))

    result = asyncio.run(tools.add_recipe_to_plan(
        day="2026-06-22",
        recipe_id="mine1",
        custom=True,
        dry_run=False,
        confirmation_token=dry_run["confirmation_token"],
    ))

    assert result["custom"] is True
    assert result["customer_recipe_ids"] == ["mine1"]


def test_tools_remove_from_plan_allows_write_after_matching_dry_run():
    tools = CookidooTools(FakeClient())
    dry_run = asyncio.run(tools.remove_recipe_from_plan(day="2026-06-22", recipe_id="r1"))

    result = asyncio.run(tools.remove_recipe_from_plan(
        day="2026-06-22",
        recipe_id="r1",
        dry_run=False,
        confirmation_token=dry_run["confirmation_token"],
    ))

    assert result["id"] == "2026-06-22"


def test_default_client_can_be_constructed_without_upstream_import():
    client = CookidooClient(upstream=None, allow_missing_upstream=True)

    assert client is not None


def test_build_tools_uses_real_upstream_mode(tmp_path):
    from cookidoo_mcp.server import build_tools

    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text(
        '[{"key":"_oauth2_proxy","value":"oauth","domain":"cookidoo.ch","path":"/"},'
        '{"key":"v-authenticated","value":"v","domain":"cookidoo.ch","path":"/"}]',
        encoding="utf-8",
    )
    cookie_file.chmod(0o600)

    tools = build_tools(str(cookie_file))

    assert tools.client.allow_missing_upstream is False


def test_build_tools_accepts_account_localization(tmp_path):
    from cookidoo_mcp.server import build_tools

    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text(
        '[{"key":"_oauth2_proxy","value":"oauth","domain":"cookidoo.de","path":"/"},'
        '{"key":"v-authenticated","value":"v","domain":"cookidoo.de","path":"/"}]',
        encoding="utf-8",
    )
    cookie_file.chmod(0o600)

    tools = build_tools(str(cookie_file), default_country="de", default_locale="de-DE")

    assert tools.client.default_country == "de"
    assert tools.client.default_locale == "de-DE"


def test_build_tools_loads_localization_from_config(tmp_path):
    from cookidoo_mcp.config import CookidooConfig, CookidooConfigStore
    from cookidoo_mcp.server import build_tools

    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text(
        '[{"key":"_oauth2_proxy","value":"oauth","domain":"cookidoo.pl","path":"/"},'
        '{"key":"v-authenticated","value":"v","domain":"cookidoo.pl","path":"/"}]',
        encoding="utf-8",
    )
    cookie_file.chmod(0o600)
    config_file = tmp_path / "config.yaml"
    CookidooConfigStore(config_file).save(
        CookidooConfig(
            country="pl",
            locale="pl",
            label="Poland - Polish",
            cookie_file=str(cookie_file),
        )
    )

    tools = build_tools(config_file=str(config_file))

    assert tools.client.default_country == "pl"
    assert tools.client.default_locale == "pl"
    assert tools.client.auth_store.path == cookie_file
