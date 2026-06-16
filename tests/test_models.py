from dataclasses import dataclass

from cookidoo_mcp.models import RecipeDetail, RecipeDraft, RecipeStep, RecipeSummary, SearchQuery


def test_search_query_defaults_to_swiss_tm7():
    query = SearchQuery(query="Hähnchen")

    assert query.country == "ch"
    assert query.locale == "de-CH"
    assert query.language == "de"
    assert query.tm_model == "TM7"
    assert query.page == 1
    assert query.limit == 10


def test_search_query_normalizes_lists_and_bounds():
    query = SearchQuery(
        query="kurczak",
        include_ingredients=("chicken", "cream"),
        exclude_ingredients=("rice",),
        tags=("low-carb",),
        page=0,
        limit=200,
    )

    assert query.include_ingredients == ["chicken", "cream"]
    assert query.exclude_ingredients == ["rice"]
    assert query.tags == ["low-carb"]
    assert query.page == 1
    assert query.limit == 50


def test_search_query_maps_to_upstream_signature():
    query = SearchQuery(
        query="chicken",
        language="en",
        country="ch",
        include_ingredients=["chicken"],
        max_total_time_minutes=30,
        max_prep_time_minutes=10,
        min_rating=4,
        limit=12,
    )

    params = query.upstream_params()

    assert params["locale"] == "en"
    assert params["countries"] == ["ch"]
    assert params["ingredients"] == ["chicken"]
    assert params["total_time"] == 1800
    assert params["preparation_time"] == 600
    assert params["ratings"] == ["4"]
    assert params["tmv"] == ["TM7"]
    assert params["page_size"] == 12


def test_recipe_draft_payload_marks_generated_and_tm7():
    draft = RecipeDraft(
        title="Kremowy kurczak",
        language="pl-PL",
        servings=3,
        ingredients=["600 g udek z kurczaka", "150 ml śmietany"],
        steps=[
            RecipeStep(
                title="Podsmaż",
                text="Podsmaż kurczaka.",
                time_seconds=360,
                temperature_c=140,
                speed="1",
                reverse=True,
                mode="Browning",
            )
        ],
        notes="Translated and adapted for TM7.",
    )

    payload = draft.to_create_payload()

    assert payload["title"] == "Kremowy kurczak"
    assert payload["language"] == "pl-PL"
    assert payload["tools"] == ["TM7"]
    assert payload["source"] == "generated_adapted"
    assert payload["steps"][0]["reverse"] is True
    assert payload["steps"][0]["mode"] == "Browning"


def test_recipe_draft_includes_cookidoo_image_key_when_supplied():
    draft = RecipeDraft(
        title="Chocolate Lava Cake",
        ingredients=["150 g dark chocolate"],
        steps=["Mix."],
        image="prod/img/customer-recipe/lava-cake.jpg",
    )

    payload = draft.to_create_payload()

    assert payload["image"] == "prod/img/customer-recipe/lava-cake.jpg"
    assert payload["cookidoo"]["patch"]["image"] == "prod/img/customer-recipe/lava-cake.jpg"


def test_recipe_draft_preserves_explicit_cookidoo_annotations():
    draft = RecipeDraft(
        title="Lava cake",
        ingredients=["150 g dark chocolate"],
        steps=[
            {
                "text": "Mix 20 sec/speed 5.",
                "annotations": [
                    {
                        "type": "TTS",
                        "data": {"speed": "5", "time": 20},
                        "position": {"offset": 4, "length": 14},
                    }
                ],
            }
        ],
    )

    payload = draft.to_create_payload()

    assert payload["cookidoo"]["patch"]["instructions"][0]["annotations"][0]["type"] == "TTS"
    assert payload["steps"][0]["annotations"][0]["data"]["speed"] == "5"


@dataclass
class UpstreamIngredient:
    name: str
    description: str


@dataclass
class UpstreamDetail:
    id: str
    name: str
    ingredients: list[UpstreamIngredient]
    difficulty: str
    serving_size: int
    active_time: int
    total_time: int
    nutrition_groups: list[dict]
    notes: list[str]
    url: str


def test_recipe_detail_normalizes_upstream_dataclass_shape():
    detail = RecipeDetail.from_upstream(
        UpstreamDetail(
            id="r1",
            name="Official Chicken",
            ingredients=[UpstreamIngredient("chicken", "600 g")],
            difficulty="easy",
            serving_size=3,
            active_time=600,
            total_time=1800,
            nutrition_groups=[{"name": "per serving"}],
            notes=["Use fresh chicken."],
            url="https://cookidoo.ch/recipes/r1",
        )
    )

    data = detail.to_dict(include_raw=True)

    assert data["difficulty"] == "easy"
    assert data["servings"] == 3
    assert data["active_time_seconds"] == 600
    assert data["total_time_seconds"] == 1800
    assert data["ingredients"] == ["600 g chicken"]
    assert data["nutrition_source"] == "official"
    assert "raw" in data


def test_recipe_detail_omits_raw_by_default():
    detail = RecipeDetail.from_upstream({"id": "r1", "name": "Recipe", "private": "metadata"})

    assert "raw" not in detail.to_dict()


def test_recipe_summary_reads_created_recipe_content_name():
    summary = RecipeSummary.from_upstream(
        {
            "recipeId": "created1",
            "recipeContent": {"name": "Płynące ciasto czekoladowe"},
        },
        "my_recipes",
    )

    assert summary.id == "created1"
    assert summary.title == "Płynące ciasto czekoladowe"


def test_recipe_summary_converts_upstream_total_time_seconds_to_minutes():
    summary = RecipeSummary.from_upstream({"id": "r1", "title": "Sous-vide", "totalTime": 4200})

    assert summary.total_time_minutes == 70
