from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value if str(item)]


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _seconds_to_minutes(value: Any) -> int | None:
    if not isinstance(value, int):
        return None
    return value // 60


@dataclass
class AuthStatus:
    authenticated: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"authenticated": self.authenticated, "message": self.message}


@dataclass
class SearchQuery:
    query: str = ""
    country: str | None = None
    locale: str = "en"
    language: str | None = None
    include_ingredients: list[str] | tuple[str, ...] | None = None
    exclude_ingredients: list[str] | tuple[str, ...] | None = None
    difficulty: str | None = None
    max_prep_time_minutes: int | None = None
    max_total_time_minutes: int | None = None
    servings: int | None = None
    min_rating: float | None = None
    tags: list[str] | tuple[str, ...] | None = None
    tm_model: str | None = None
    page: int = 1
    limit: int = 10
    include_my_recipes: bool = False

    def __post_init__(self) -> None:
        country = _optional_text(self.country)
        language = _optional_text(self.language)
        tm_model = _optional_text(self.tm_model)
        self.country = country.lower() if country else None
        self.locale = _optional_text(self.locale) or "en"
        self.language = language.lower() if language else None
        self.tm_model = tm_model.upper() if tm_model else None
        self.include_ingredients = _list(self.include_ingredients)
        self.exclude_ingredients = _list(self.exclude_ingredients)
        self.tags = _list(self.tags)
        self.page = max(1, int(self.page or 1))
        self.limit = min(50, max(1, int(self.limit or 10)))

    def upstream_params(self) -> dict[str, Any]:
        endpoint_locale = self.language or self.locale.split("-")[0].lower()
        return {
            "query": self.query,
            "locale": endpoint_locale,
            "languages": [self.language] if self.language else None,
            "countries": [self.country] if self.country else None,
            "ingredients": self.include_ingredients,
            "exclude_ingredients": self.exclude_ingredients,
            "difficulty": self.difficulty,
            "preparation_time": self.max_prep_time_minutes * 60 if self.max_prep_time_minutes else None,
            "total_time": self.max_total_time_minutes * 60 if self.max_total_time_minutes else None,
            "portions": self.servings,
            "ratings": [str(int(self.min_rating))] if self.min_rating else None,
            "tags": self.tags,
            "tmv": [self.tm_model] if self.tm_model else None,
            "page": self.page,
            "page_size": self.limit,
        }


@dataclass
class RecipeSummary:
    id: str
    title: str
    source: str = "cookidoo"
    url: str | None = None
    total_time_minutes: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_upstream(cls, payload: Any, source: str = "cookidoo") -> "RecipeSummary":
        if is_dataclass(payload):
            payload = asdict(payload)
        elif not isinstance(payload, dict):
            payload = {
                "id": getattr(payload, "id", ""),
                "name": getattr(payload, "name", ""),
                "url": getattr(payload, "url", None),
                "total_time_minutes": getattr(payload, "total_time", None),
            }
        content = payload.get("recipeContent") if isinstance(payload.get("recipeContent"), dict) else {}
        return cls(
            id=str(payload.get("id") or payload.get("recipeId") or payload.get("uuid") or ""),
            title=str(payload.get("title") or payload.get("name") or content.get("name") or ""),
            source=source,
            url=payload.get("url") or payload.get("link") or payload.get("recipeUrl"),
            total_time_minutes=payload.get("total_time_minutes")
            or _seconds_to_minutes(payload.get("totalTime"))
            or _seconds_to_minutes(payload.get("total_time")),
            raw=payload,
        )

    def to_dict(self, include_raw: bool = False) -> dict[str, Any]:
        data = {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "total_time_minutes": self.total_time_minutes,
        }
        if include_raw:
            data["raw"] = self.raw
        return data


@dataclass
class RecipeStep:
    title: str = ""
    text: str = ""
    time_seconds: int | None = None
    temperature_c: int | None = None
    speed: str | None = None
    reverse: bool = False
    mode: str | None = None
    annotations: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_any(cls, value: "RecipeStep | dict[str, Any] | str") -> "RecipeStep":
        if isinstance(value, RecipeStep):
            return value
        if isinstance(value, str):
            return cls(text=value)
        return cls(
            title=str(value.get("title") or ""),
            text=str(value.get("text") or value.get("description") or ""),
            time_seconds=value.get("time_seconds"),
            temperature_c=value.get("temperature_c"),
            speed=value.get("speed"),
            reverse=bool(value.get("reverse", False)),
            mode=value.get("mode"),
            annotations=list(value.get("annotations") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "text": self.text,
            "time_seconds": self.time_seconds,
            "temperature_c": self.temperature_c,
            "speed": self.speed,
            "reverse": self.reverse,
            "mode": self.mode,
            "annotations": self.annotations,
        }

    def to_cookidoo_instruction(self) -> dict[str, Any]:
        if self.annotations:
            return {"type": "STEP", "text": self.text, "annotations": self.annotations}
        annotations: list[dict[str, Any]] = []
        if self.speed and self.time_seconds:
            marker = self._tts_marker()
            offset = self.text.find(marker) if marker else -1
            if offset >= 0:
                data: dict[str, Any] = {"speed": str(self.speed), "time": int(self.time_seconds)}
                if self.temperature_c:
                    data["temperature"] = {"value": str(self.temperature_c), "unit": "C"}
                annotations.append(
                    {
                        "type": "TTS",
                        "data": data,
                        "position": {"offset": offset, "length": len(marker)},
                    }
                )
        return {"type": "STEP", "text": self.text, "annotations": annotations}

    def _tts_marker(self) -> str:
        if not self.speed or not self.time_seconds:
            return ""
        minutes, seconds = divmod(int(self.time_seconds), 60)
        duration = f"{minutes} min" if seconds == 0 and minutes else f"{self.time_seconds} sec"
        temp = f"/{self.temperature_c}°C" if self.temperature_c else ""
        return f"{duration}{temp}/speed {self.speed}"


@dataclass
class RecipeDetail:
    id: str
    title: str
    source: str = "cookidoo"
    url: str | None = None
    servings: int | None = None
    difficulty: str | None = None
    active_time_seconds: int | None = None
    total_time_seconds: int | None = None
    ingredients: list[str] = field(default_factory=list)
    steps: list[RecipeStep] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    nutrition: dict[str, Any] = field(default_factory=dict)
    nutrition_source: str = "missing"
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_upstream(cls, payload: Any, source: str = "cookidoo") -> "RecipeDetail":
        original_payload = payload
        if is_dataclass(payload):
            payload = asdict(payload)
        elif not isinstance(payload, dict):
            payload = {
                "id": getattr(payload, "id", ""),
                "name": getattr(payload, "name", ""),
                "url": getattr(payload, "url", None),
                "servings": getattr(payload, "serving_size", None),
                "ingredients": getattr(payload, "ingredients", []),
                "nutrition": getattr(payload, "nutrition", {}),
            }
        nutrition = payload.get("nutrition") or payload.get("nutritions") or {}
        nutrition_groups = payload.get("nutrition_groups") or []
        if not nutrition and nutrition_groups:
            nutrition = {"groups": nutrition_groups}
        steps = payload.get("steps") or payload.get("preparationSteps") or payload.get("instructions") or []
        return cls(
            id=str(payload.get("id") or payload.get("recipeId") or payload.get("uuid") or ""),
            title=str(payload.get("title") or payload.get("name") or ""),
            source=source,
            url=payload.get("url") or payload.get("link"),
            servings=payload.get("servings") or payload.get("portions") or payload.get("serving_size"),
            difficulty=payload.get("difficulty"),
            active_time_seconds=payload.get("active_time") or payload.get("active_time_seconds"),
            total_time_seconds=payload.get("total_time") or payload.get("total_time_seconds"),
            ingredients=[cls._format_ingredient(item) for item in (payload.get("ingredients") or [])],
            steps=[RecipeStep.from_any(step) for step in steps],
            notes=[str(item) for item in (payload.get("notes") or [])],
            tags=[str(item) for item in (payload.get("tags") or payload.get("categories") or [])],
            nutrition=nutrition,
            nutrition_source="official" if nutrition else "missing",
            raw=payload if isinstance(original_payload, dict) else asdict(original_payload) if is_dataclass(original_payload) else payload,
        )

    @staticmethod
    def _format_ingredient(item: Any) -> str:
        if is_dataclass(item):
            item = asdict(item)
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("ingredientNotation") or "").strip()
            description = str(item.get("description") or "").strip()
            if description and name:
                return f"{description} {name}".strip()
            return name or description or str(item)
        return str(item)

    def to_dict(self, include_raw: bool = False) -> dict[str, Any]:
        data = {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "servings": self.servings,
            "difficulty": self.difficulty,
            "active_time_seconds": self.active_time_seconds,
            "total_time_seconds": self.total_time_seconds,
            "ingredients": self.ingredients,
            "steps": [step.to_dict() for step in self.steps],
            "notes": self.notes,
            "tags": self.tags,
            "nutrition": self.nutrition,
            "nutrition_source": self.nutrition_source,
        }
        if include_raw:
            data["raw"] = self.raw
        return data


@dataclass
class RecipeDraft:
    title: str
    language: str = "en"
    servings: int | None = None
    ingredients: list[str] = field(default_factory=list)
    steps: list[RecipeStep | dict[str, Any] | str] = field(default_factory=list)
    image: str | None = None
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    tm_model: str | None = None

    def __post_init__(self) -> None:
        self.steps = [RecipeStep.from_any(step) for step in self.steps]
        tm_model = _optional_text(self.tm_model)
        self.tm_model = tm_model.upper() if tm_model else None

    def to_create_payload(self) -> dict[str, Any]:
        patch_payload = self.to_cookidoo_patch_payload()
        payload = {
            "title": self.title,
            "language": self.language,
            "servings": self.servings,
            "ingredients": self.ingredients,
            "steps": [step.to_dict() for step in self.steps],
            "image": self.image,
            "notes": self.notes,
            "tags": self.tags,
            "source": "generated_adapted",
            "cookidoo": {
                "create": self.to_cookidoo_create_payload(),
                "patch": patch_payload,
            },
        }
        if self.tm_model:
            payload["tools"] = [self.tm_model]
        return payload

    def to_cookidoo_create_payload(self) -> dict[str, Any]:
        return {"recipeName": self.title}

    def to_cookidoo_patch_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ingredients": [{"type": "INGREDIENT", "text": ingredient} for ingredient in self.ingredients],
            "instructions": [step.to_cookidoo_instruction() for step in self.steps],
            "yield": {"value": self.servings or 1, "unitText": "portion"},
        }
        if self.tm_model:
            payload["tools"] = [self.tm_model]
        total_time = sum(step.time_seconds or 0 for step in self.steps)
        if total_time:
            payload["prepTime"] = total_time
            payload["totalTime"] = total_time
        if self.image:
            payload["image"] = self.image
        return payload
