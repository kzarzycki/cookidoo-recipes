import asyncio
from datetime import date

from cookidoo_api.types import CookidooCalendarDay, CookidooCalendarDayRecipe
from cookidoo_mcp.client import CookidooClient, CookidooClientError
from cookidoo_mcp.models import RecipeDraft, SearchQuery
from yarl import URL


class FakeUpstream:
    def __init__(self):
        self.created_payloads = []
        self.calendar_calls = []

    async def search_recipes(self, **kwargs):
        return [
            {"id": "r1", "name": "Chicken Chili", "url": "/recipes/r1", "totalTime": 30},
            {"id": "r2", "title": "Beef Stew", "url": "/recipes/r2"},
        ]

    async def get_recipe(self, recipe_id):
        return {
            "id": recipe_id,
            "name": "Chicken Chili",
            "ingredients": ["chicken", "cream cheese"],
            "steps": [{"title": "Cook", "text": "Cook gently."}],
            "nutrition": {"carbohydrates": "19 g", "protein": "58 g"},
        }

    async def get_recipe_details(self, recipe_id):
        return await self.get_recipe(recipe_id)

    async def list_created_recipes(self, locale):
        return [
            {"id": "mine1", "name": "Chicken translated", "url": "/created/mine1"},
            {"id": "mine2", "name": "Chocolate cake", "url": "/created/mine2"},
        ]

    async def create_recipe(self, payload, dry_run=False):
        self.created_payloads.append((payload, dry_run))
        if dry_run:
            return {"dry_run": True, "payload": payload}
        return {"id": "created1", "url": "/created/created1", "payload": payload}

    async def get_recipes_in_calendar_week(self, day):
        self.calendar_calls.append(("get", day))
        return [
            CookidooCalendarDay(
                id=day.isoformat(),
                title="Monday",
                recipes=[
                    CookidooCalendarDayRecipe(
                        id="r1", name="Chicken Chili", total_time="30", thumbnail="", image="", url="/recipes/r1"
                    )
                ],
                customer_recipe_ids=[],
            )
        ]

    async def add_recipes_to_calendar(self, day, recipe_ids):
        self.calendar_calls.append(("add", day, recipe_ids))
        return CookidooCalendarDay(id=day.isoformat(), title="Monday", recipes=[], customer_recipe_ids=[])

    async def remove_recipe_from_calendar(self, day, recipe_id):
        self.calendar_calls.append(("remove", day, recipe_id))
        return CookidooCalendarDay(id=day.isoformat(), title="Monday", recipes=[], customer_recipe_ids=[])

    async def add_custom_recipes_to_calendar(self, day, recipe_ids):
        self.calendar_calls.append(("add_custom", day, recipe_ids))
        return CookidooCalendarDay(
            id=day.isoformat(), title="Monday", recipes=[], customer_recipe_ids=list(recipe_ids)
        )

    async def remove_custom_recipe_from_calendar(self, day, recipe_id):
        self.calendar_calls.append(("remove_custom", day, recipe_id))
        return CookidooCalendarDay(id=day.isoformat(), title="Monday", recipes=[], customer_recipe_ids=[])


class FailingUpstream:
    async def search_recipes(self, **kwargs):
        raise RuntimeError("Cookie: secret-token raw upstream failure")


class InternalEndpointUpstream:
    def __init__(self):
        self.api_endpoint = URL("https://cookidoo.ch")
        self.calls = []

    async def _request_json(self, method, url, operation, **kwargs):
        self.calls.append((method, str(url), operation, kwargs.get("json")))
        if method == "post":
            return {"recipeId": "created-live-test"}
        return None


def test_search_merges_my_recipes_client_side():
    client = CookidooClient(upstream=FakeUpstream())
    query = SearchQuery(query="chicken", include_my_recipes=True)

    results = asyncio.run(client.search(query))

    assert [item.source for item in results] == ["cookidoo", "cookidoo", "my_recipes"]
    assert results[-1].id == "mine1"


def test_get_recipe_normalizes_nutrition_source():
    client = CookidooClient(upstream=FakeUpstream())

    detail = asyncio.run(client.get_recipe("r1"))

    assert detail.id == "r1"
    assert detail.nutrition["carbohydrates"] == "19 g"
    assert detail.nutrition_source == "official"


class CustomRecipeUpstream:
    """Records which recipe endpoint was hit; public endpoint 404s on ULIDs."""

    def __init__(self):
        self.calls = []

    async def get_recipe_details(self, recipe_id):
        self.calls.append(("public", recipe_id))
        raise RuntimeError("Cookidoo request failed (404) for custom recipe")

    async def get_custom_recipe(self, recipe_id):
        self.calls.append(("custom", recipe_id))
        return {"id": recipe_id, "name": "My Custom Dish", "ingredients": ["a"], "instructions": ["mix"]}


def test_get_recipe_routes_ulid_to_custom_endpoint():
    upstream = CustomRecipeUpstream()
    client = CookidooClient(upstream=upstream)

    detail = asyncio.run(client.get_recipe("01K2ABCDEFGHJKMNPQRSTVWXYZ"))

    assert detail.title == "My Custom Dish"
    # ULID id must hit the custom endpoint first, never falling to the public 404.
    assert upstream.calls == [("custom", "01K2ABCDEFGHJKMNPQRSTVWXYZ")]


def test_get_recipe_public_id_falls_back_to_custom():
    upstream = CustomRecipeUpstream()
    client = CookidooClient(upstream=upstream)

    detail = asyncio.run(client.get_recipe("r123456"))

    # Non-ULID tries public first (raises), then falls back to custom.
    assert detail.title == "My Custom Dish"
    assert [c[0] for c in upstream.calls] == ["public", "custom"]


def test_create_recipe_supports_dry_run():
    upstream = FakeUpstream()
    client = CookidooClient(upstream=upstream)
    draft = RecipeDraft(title="Test", ingredients=["x"], steps=[])

    result = asyncio.run(client.create_recipe(draft, dry_run=True))

    assert result["dry_run"] is True
    assert "tools" not in result["payload"]
    assert result["payload"]["cookidoo"]["create"] == {"recipeName": "Test"}


def test_create_recipe_uses_cookidoo_post_then_patch_fallback():
    upstream = InternalEndpointUpstream()
    client = CookidooClient(upstream=upstream)
    draft = RecipeDraft(
        title="Live Test",
        language="de-CH",
        servings=2,
        ingredients=["1 egg"],
        steps=[{"text": "Mix 10 sec/speed 3.", "time_seconds": 10, "speed": "3"}],
        tm_model="TM7",
    )

    result = asyncio.run(client.create_recipe(draft, dry_run=False))

    assert result["id"] == "created-live-test"
    assert upstream.calls[0] == (
        "post",
        "https://cookidoo.ch/created-recipes/de-CH",
        "create recipe",
        {"recipeName": "Live Test"},
    )
    assert upstream.calls[1][0:3] == (
        "patch",
        "https://cookidoo.ch/created-recipes/de-CH/created-live-test",
        "update recipe",
    )
    assert upstream.calls[1][3]["ingredients"] == [{"type": "INGREDIENT", "text": "1 egg"}]
    assert upstream.calls[1][3]["tools"] == ["TM7"]


def test_get_meal_plan_returns_days_with_recipes():
    client = CookidooClient(upstream=FakeUpstream())

    days = asyncio.run(client.get_meal_plan(date(2026, 6, 22)))

    assert days[0]["id"] == "2026-06-22"
    assert days[0]["recipes"][0]["id"] == "r1"


def test_add_recipe_to_plan_routes_standard_vs_custom():
    upstream = FakeUpstream()
    client = CookidooClient(upstream=upstream)

    asyncio.run(client.add_recipe_to_plan(date(2026, 6, 22), "r1"))
    asyncio.run(client.add_recipe_to_plan(date(2026, 6, 22), "mine1", custom=True))

    assert ("add", date(2026, 6, 22), ["r1"]) in upstream.calendar_calls
    assert ("add_custom", date(2026, 6, 22), ["mine1"]) in upstream.calendar_calls


def test_remove_recipe_from_plan_routes_standard_vs_custom():
    upstream = FakeUpstream()
    client = CookidooClient(upstream=upstream)

    asyncio.run(client.remove_recipe_from_plan(date(2026, 6, 22), "r1"))
    asyncio.run(client.remove_recipe_from_plan(date(2026, 6, 22), "mine1", custom=True))

    assert ("remove", date(2026, 6, 22), "r1") in upstream.calendar_calls
    assert ("remove_custom", date(2026, 6, 22), "mine1") in upstream.calendar_calls


def test_sanitizes_upstream_errors():
    client = CookidooClient(upstream=FailingUpstream())
    query = SearchQuery(query="chicken")

    try:
        asyncio.run(client.search(query))
    except CookidooClientError as exc:
        assert "secret-token" not in str(exc)
        assert "search failed" in str(exc)
    else:
        raise AssertionError("expected sanitized error")
