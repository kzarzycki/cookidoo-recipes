from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

# --- Thermomix machine-setting vocabulary (from the Cookidoo web editor bundle) ---
# Temperature is a fixed enum, not continuous. Values are stored as strings.
TEMP_C_ENUM = (
    "OFF", "37", "40", "45", "50", "55", "60", "65", "70", "75",
    "80", "85", "90", "95", "98", "100", "105", "110", "115", "120",
)
TEMP_F_ENUM = (
    "OFF", "100", "105", "110", "120", "130", "140", "150", "160", "170",
    "175", "185", "195", "200", "205", "212", "220", "230", "240", "250",
)
# Manual / TTS speeds. "soft" is the Spoon / soft-stir setting.
SPEED_TTS_ENUM = ("soft", "0.5", "1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5")
# High-speed blend mode speeds (BLEND mode only).
SPEED_BLEND_ENUM = ("6", "6.5", "7", "7.5", "8")
# MODE names. The created-recipe API expects LOWERCASE wire literals (proven live:
# uppercase is tolerated/normalized but the canonical literal is lowercase, matching
# the recode-software/cookidoo-api client and the editor's mode registry keys).
MODE_NAMES = (
    "DOUGH", "BLEND", "TURBO", "WARM_UP", "RICE_COOKER", "STEAMING", "BROWNING",
)
# BROWNING uses its OWN temperature enum (not the manual C enum). Live: 140..160 °C
# persist; manual-range temps (e.g. 105) are 400-rejected for browning.
TEMP_BROWNING_C_ENUM = ("140", "145", "150", "155", "160")
# BROWNING power is an enum, NOT a speed. Live: "Gentle"/"Intense" persist; numeric
# values (e.g. "5") cause the whole MODE annotation to be silently stripped.
BROWNING_POWER_ENUM = ("Gentle", "Intense")
# TURBO requires pulseCount on the wire (live: omitting it 400-rejects the PATCH).
TURBO_DEFAULT_PULSE_COUNT = 1
# TURBO time is an enum of seconds, not a duration. Live: 1 and 2 persist;
# time:3 and an absent time both 400/strip. Out-of-range turbo settings fall
# back to a surviving TTS/prose encoding rather than emit a stripped annotation.
TURBO_TIME_ENUM = (1, 2)
TIME_MIN_S = 1
TIME_MAX_S = 5940  # 99 min

# Blade direction. Forward = "CW", reverse / Linkslauf = "CCW" (live-verified,
# case-sensitive uppercase; closes GH #2). On TTS the forward "CW" is OMITTED
# (the captured forward TTS carries no `direction` key); STEAMING MODE, by
# contrast, REQUIRES a direction, so it defaults to "CW" when not reverse.
FORWARD_DIRECTION = "CW"
REVERSE_DIRECTION = "CCW"


def _format_duration(seconds: int) -> str:
    minutes, secs = divmod(int(seconds), 60)
    if minutes and secs:
        return f"{minutes} min {secs} sec"
    if minutes:
        return f"{minutes} min"
    return f"{secs} sec"


def _snap_temperature(value: Any, unit: str) -> str | None:
    """Map a requested temperature onto the fixed C/F enum.

    Returns the matching enum string, or None if it cannot be represented
    (caller then leaves the temperature in prose instead of faking a setting).
    """
    if value is None:
        return None
    enum = TEMP_F_ENUM if unit == "F" else TEMP_C_ENUM
    text = str(value).strip()
    if text.upper() == "OFF":
        return "OFF"
    if text in enum:
        return text
    try:
        requested = float(text)
    except ValueError:
        return None
    numeric = [(float(v), v) for v in enum if v != "OFF"]
    lo = numeric[0][0]
    hi = numeric[-1][0]
    if requested < lo or requested > hi:
        return None  # out of range -> not a real setting, keep in prose
    # snap to nearest allowed step
    return min(numeric, key=lambda pair: abs(pair[0] - requested))[1]


def _normalize_speed(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("soft", "spoon", "soft-stir", "softstir"):
        return "soft"
    # allow "5" or "5.0" -> "5"; "3.5" stays "3.5"
    try:
        num = float(text)
    except ValueError:
        return None
    rendered = ("%g" % num)
    if rendered in SPEED_TTS_ENUM or rendered in SPEED_BLEND_ENUM:
        return rendered
    return None


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
    """One recipe step plus its optional Thermomix machine setting.

    Setting fields drive a structured ``TTS`` or ``MODE`` annotation on the
    Cookidoo created-recipe PATCH. They are independent of how the step prose is
    worded: the annotation is anchored to ``anchor`` (a substring of ``text``) or,
    if that is absent/not found, to a canonical marker appended to ``text``.

    Fields:
      text            instruction prose (required)
      time_seconds    1..5940 (mode-specific max); duration of the setting
      temperature_c   manual temperature; snapped to the fixed C enum (37..120/OFF)
      temperature_f   manual temperature in Fahrenheit (snapped to the F enum)
      speed           "soft" (Spoon) | "0.5".."5" (manual) | "6".."8" (BLEND mode)
      reverse         True -> counter-clockwise / Linkslauf blade direction
      mode            one of DOUGH, BLEND, TURBO, WARM_UP, RICE_COOKER, STEAMING,
                      BROWNING -> emits a MODE annotation instead of plain TTS
      accessory       physical accessory for the mode; only "Varoma" (STEAMING)
                      is a structured value, everything else must go in prose
      pulse_count     TURBO pulse count (TM7 only)
      power           BROWNING power level (TM7 only)
      tm_model        "TM6"|"TM7" (gates TM7-only params); inherited from the draft
      anchor          substring of text the annotation attaches to; if omitted the
                      canonical marker is appended to text and anchored there
      annotations     pre-built annotation dicts (pass-through, advanced use)
    """

    title: str = ""
    text: str = ""
    time_seconds: int | None = None
    temperature_c: int | None = None
    temperature_f: int | None = None
    speed: str | None = None
    reverse: bool = False
    mode: str | None = None
    accessory: str | None = None
    pulse_count: int | None = None
    power: str | None = None
    tm_model: str | None = None
    anchor: str | None = None
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
            temperature_f=value.get("temperature_f"),
            speed=value.get("speed"),
            reverse=bool(value.get("reverse", False)),
            mode=value.get("mode"),
            accessory=value.get("accessory"),
            pulse_count=value.get("pulse_count"),
            power=value.get("power"),
            tm_model=value.get("tm_model"),
            anchor=value.get("anchor"),
            annotations=list(value.get("annotations") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "text": self.text,
            "time_seconds": self.time_seconds,
            "temperature_c": self.temperature_c,
            "temperature_f": self.temperature_f,
            "speed": self.speed,
            "reverse": self.reverse,
            "mode": self.mode,
            "accessory": self.accessory,
            "pulse_count": self.pulse_count,
            "power": self.power,
            "anchor": self.anchor,
            "annotations": self.annotations,
        }

    # --- annotation building --------------------------------------------------

    def _temp_for_annotation(self) -> dict[str, str] | None:
        if self.temperature_f is not None:
            value = _snap_temperature(self.temperature_f, "F")
            return {"value": value, "unit": "F"} if value is not None else None
        if self.temperature_c is not None:
            value = _snap_temperature(self.temperature_c, "C")
            return {"value": value, "unit": "C"} if value is not None else None
        return None

    def _has_setting(self) -> bool:
        return bool(
            self.mode
            or self.speed
            or self.time_seconds
            or self.temperature_c is not None
            or self.temperature_f is not None
            or self.reverse
        )

    def _anchored_text_and_position(self, marker: str) -> tuple[str, dict[str, int]]:
        """Anchor an annotation to text. Prefer self.anchor, else find the marker,
        else append the canonical marker so the annotation always anchors."""
        if self.anchor and self.anchor in self.text:
            offset = self.text.find(self.anchor)
            return self.text, {"offset": offset, "length": len(self.anchor)}
        if marker and marker in self.text:
            offset = self.text.find(marker)
            return self.text, {"offset": offset, "length": len(marker)}
        if not marker:
            # nothing human-readable to anchor; attach to the whole step text
            return self.text, {"offset": 0, "length": len(self.text)}
        text = self.text.rstrip()
        joined = f"{text} {marker}".strip()
        offset = joined.rfind(marker)
        return joined, {"offset": offset, "length": len(marker)}

    def to_cookidoo_instruction(self) -> dict[str, Any]:
        if self.annotations:
            return {"type": "STEP", "text": self.text, "annotations": self.annotations}
        if not self._has_setting():
            return {"type": "STEP", "text": self.text, "annotations": [], "missedUsages": []}

        mode = self.mode.strip().upper().replace(" ", "_").replace("-", "_") if self.mode else None
        if mode in MODE_NAMES:
            # TURBO time is an enum {1,2}; anything else would 400/strip on save.
            # Fall back to a surviving TTS/prose encoding instead.
            if mode == "TURBO" and (self.time_seconds is None or int(self.time_seconds) not in TURBO_TIME_ENUM):
                return self._tts_instruction()
            return self._mode_instruction(mode)
        # Unknown mode names (named TM programs etc.) cannot be structured: keep
        # whatever speed/time/temp can be, but never invent a MODE annotation.
        return self._tts_instruction()

    def _tts_instruction(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        speed = _normalize_speed(self.speed)
        if speed is not None:
            data["speed"] = speed
        if self.time_seconds:
            data["time"] = int(self.time_seconds)
        temp = self._temp_for_annotation()
        if temp is not None:
            data["temperature"] = temp
        if self.reverse:
            data["direction"] = REVERSE_DIRECTION
        if not data:
            return {"type": "STEP", "text": self.text, "annotations": [], "missedUsages": []}
        text, position = self._anchored_text_and_position(self._tts_marker())
        return {
            "type": "STEP",
            "text": text,
            "annotations": [{"type": "TTS", "position": position, "data": data}],
            "missedUsages": [],
        }

    # Per-mode data keys, mirroring the editor's getAnnotationData() bodies.
    # Only these keys are emitted for each MODE (null values dropped, like k()).
    _MODE_DATA_KEYS = {
        "DOUGH": ("time",),
        "BLEND": ("time", "speed"),
        "TURBO": ("time", "pulseCount"),  # pulseCount TM7-only
        "WARM_UP": ("temperature", "speed"),
        "RICE_COOKER": (),
        "STEAMING": ("time", "speed", "direction", "accessory"),
        "BROWNING": ("time", "temperature", "power"),  # power TM7-only
    }

    def _mode_instruction(self, mode: str) -> dict[str, Any]:
        is_tm7 = (self.tm_model or "").upper() == "TM7"
        candidates: dict[str, Any] = {}
        speed = _normalize_speed(self.speed)
        if speed is not None:
            candidates["speed"] = speed
        if self.time_seconds:
            candidates["time"] = int(self.time_seconds)
        # BROWNING has its own temperature enum (140..160) and a required power enum.
        if mode == "BROWNING":
            temp = self._browning_temp()
            if temp is not None:
                candidates["temperature"] = temp
            candidates["power"] = self._browning_power()
        else:
            temp = self._temp_for_annotation()
            if temp is not None:
                candidates["temperature"] = temp
        if self.reverse:
            candidates["direction"] = REVERSE_DIRECTION
        elif mode == "STEAMING":
            # STEAMING MODE requires a direction; default forward when not reverse.
            candidates["direction"] = FORWARD_DIRECTION
        accessory = self.accessory or ("Varoma" if mode == "STEAMING" else None)
        if accessory:
            candidates["accessory"] = accessory
        # TURBO requires pulseCount on the wire; default it if unset.
        if mode == "TURBO":
            candidates["pulseCount"] = int(self.pulse_count) if self.pulse_count is not None else TURBO_DEFAULT_PULSE_COUNT
        allowed = self._MODE_DATA_KEYS.get(mode, ())
        data = {key: candidates[key] for key in allowed if key in candidates}
        text, position = self._anchored_text_and_position(self._mode_marker(mode))
        return {
            "type": "STEP",
            "text": text,
            # Lowercase wire literal — the API's canonical MODE name (live-verified).
            "annotations": [{"type": "MODE", "name": mode.lower(), "position": position, "data": data}],
            "missedUsages": [],
        }

    def _browning_temp(self) -> dict[str, str] | None:
        """Snap a requested browning temperature to the browning enum (140..160 C).

        Browning rejects manual-range temps; below 140 -> None (prose), above 160
        -> clamp to 160, in-between -> nearest enum step.
        """
        raw = self.temperature_c if self.temperature_c is not None else self.temperature_f
        if raw is None:
            return None
        try:
            requested = float(str(raw).strip())
        except ValueError:
            return None
        numeric = [(float(v), v) for v in TEMP_BROWNING_C_ENUM]
        if requested < numeric[0][0] - 5:
            return None  # well below browning range -> keep in prose
        if requested > numeric[-1][0]:
            return {"value": numeric[-1][1], "unit": "C"}
        nearest = min(numeric, key=lambda pair: abs(pair[0] - requested))[1]
        return {"value": nearest, "unit": "C"}

    def _browning_power(self) -> str:
        """Coerce the power field to the BROWNING power enum (Gentle/Intense).

        Numeric/invalid values would silently strip the whole annotation, so we map
        them to a valid level: high speeds/levels -> Intense, else Gentle.
        """
        if self.power is None:
            return "Gentle"
        text = str(self.power).strip()
        for level in BROWNING_POWER_ENUM:
            if text.lower() == level.lower():
                return level
        try:
            return "Intense" if float(text) >= 5 else "Gentle"
        except ValueError:
            return "Gentle"

    def _tts_marker(self) -> str:
        parts: list[str] = []
        if self.time_seconds:
            parts.append(_format_duration(int(self.time_seconds)))
        temp = self._temp_for_annotation()
        if temp is not None and temp["value"] != "OFF":
            symbol = "°C" if temp["unit"] == "C" else "°F"
            parts.append(f"{temp['value']}{symbol}")
        if self.reverse:
            parts.append("reverse")
        speed = _normalize_speed(self.speed)
        if speed is not None:
            parts.append(f"speed {speed}")
        return "/".join(parts)

    def _mode_marker(self, mode: str) -> str:
        label = mode.replace("_", " ").title()
        if mode == "STEAMING":
            label = "Varoma"
        duration = _format_duration(int(self.time_seconds)) if self.time_seconds else ""
        return f"{label} {duration}".strip() if duration else label


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
        # Propagate the draft's machine model to steps so TM7-only params
        # (pulseCount, power) are gated correctly per step.
        for step in self.steps:
            if step.tm_model is None:
                step.tm_model = self.tm_model

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
