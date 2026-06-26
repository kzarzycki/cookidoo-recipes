---
name: cookidoo-recipes
description: Search Cookidoo recipes, inspect official details and nutrition, translate/adapt recipes, and save custom recipes through the local Cookidoo MCP server.
---

# Cookidoo Recipes

Use this skill when the user asks about Cookidoo, Thermomix recipes, recipe search across languages, translating Cookidoo recipes, nutrition values, or saving custom recipes to Cookidoo.

## Tools

Use the local MCP tools when available:

- `cookidoo_auth_status`
- `cookidoo_discover_recipes`
- `cookidoo_search`
- `cookidoo_get_recipe`
- `cookidoo_list_my_recipes`
- `cookidoo_get_collection`
- `cookidoo_upload_recipe_image`
- `cookidoo_create_recipe`

If the tools are missing, tell the user the Cookidoo MCP server is not connected.

`cookidoo_create_recipe` accepts an optional `image` field. Pass only Cookidoo-compatible customer recipe image keys such as `prod/img/customer-recipe/example.jpg`; official asset URLs are not accepted by the recipe patch endpoint.

Use `cookidoo_upload_recipe_image` to copy an official Cookidoo asset URL into a customer recipe image key. It uses the same dry-run and confirmation-token pattern as recipe creation.

## Defaults

- Search: language-agnostic. Use `cookidoo_discover_recipes` unless the user asks for a specific language, country, locale, or exact filter.
- Machine: no default. Pass `tm_model` only when the user asks for a Thermomix model or has configured a preference.
- Save language: use the user-requested target language. If none is given, use `en`.

## Search Workflow

1. Check `cookidoo_auth_status`.
2. Call `cookidoo_discover_recipes` for normal recipe discovery. Pass the user's intent as `query`. Put locale-specific helper terms in `localized_queries`, not global `related_queries`.
3. Use `cookidoo_search` when the user asks for a specific language, country, locale, machine, ingredient filter, or exact narrow search.
4. For technique-driven searches, add local technique and accessory terms. For slow/low-temperature meat, use localized queries such as `basse température`, `Niedertemperatur`, `baja temperatura`, `wolno gotowane`, `osłona noża miksującego`, and meat-cut terms in the matching local language.
5. `cookidoo_discover_recipes` expands relevant collections internally. Do not expose collection mechanics unless the user asks why something was or was not found.
6. Track provenance for each candidate: query, country, language, source, rank if returned by search, and collection id if found through internal collection expansion.
7. If the user asks about a known recipe id that did not appear, state whether it was absent from raw search results, absent because of country/language facets, hidden as a variant, or represented by a sibling recipe id.
8. If the user asks to include saved translations or own recipes, set `include_my_recipes=true`.
9. For diet or nutrition constraints, fetch details for candidate recipes with `cookidoo_get_recipe`.
10. Quote carb, protein, calorie, or other nutrition values only when returned by `cookidoo_get_recipe`.
11. Label sources as official Cookidoo recipes, collection recipes, or user-created recipes.

Search results do not reliably include nutrition. Do not filter by carbs from search hits alone.

## Translation And Save Workflow

1. Search in the source language.
2. Fetch the selected recipe details.
3. Translate only visible recipe content into the target language: title, ingredients, steps, notes, and serving unit text.
4. Keep control details out of visible fields. Do not append labels such as `(English metric)`, `(translated)`, source locale, target locale, model name, or workflow notes to the title.
5. Preserve quantities and metric units unless the user asks to convert them.
6. Preserve Cookidoo step annotations when translating text. Update annotation offsets and lengths to match the translated marker text.
7. Copy the source image when possible. If the source image is already a customer-recipe image key, pass it as `image` to `cookidoo_create_recipe`. If the source image is an official Cookidoo asset URL, run `cookidoo_upload_recipe_image` and pass the returned `image` key to `cookidoo_create_recipe`. Do not pass official asset URLs directly as recipe images.
8. Pass `tm_model` only when the saved recipe should be tagged for a specific Thermomix model.
9. Show a dry run with title, language, servings, machine tag if any, image status, ingredients, steps, notes, and the returned confirmation token.
10. Ask for explicit confirmation before setting `dry_run=false`.
11. Save with `cookidoo_create_recipe` using the confirmation token from the reviewed dry run.
12. Read back the saved recipe and verify title, ingredients count, steps count, machine tag if any, and image.

Never write to the user's Cookidoo account without an explicit confirmation in the current conversation.

## Thermomix Conventions

- Browning: searing meat, sauteing onion, toasting rice, lid off.
- Open Cooking: reductions, risotto, braises, and sauces that need evaporation.
- Reverse blade: chunky meat or vegetables that should stay intact.
- Varoma: steaming.
- Dairy: add near the end and keep at or below 90 C unless the source says otherwise.

Encode time, temperature, direction, and speed as TTS settings when the source supports them (see Structured Steps below). MODE annotations (Browning, Varoma, etc.) are not persisted by the created-recipe API today — encode their settings as TTS and name the program in prose. If adapting from a recipe that was not written for the requested machine, say the saved method is generated/adapted content.

## Structured Steps

A flat recipe is steps passed as plain strings. To get a guided recipe with machine settings, pass each step as a dict and populate the structured fields. A step with no setting fields stays a plain instruction; the moment you set `mode`, `speed`, `time_seconds`, `temperature_c/f`, or `reverse`, the tool emits a structured annotation.

Step fields: `text` (required prose), `time_seconds` (1..5940), `temperature_c`, `temperature_f`, `speed`, `reverse` (bool), `mode`, `accessory`, `pulse_count`, `power`, `anchor`, `annotations` (raw pass-through, advanced only).

**One setting per step.** Matches the real machine and the editor. Split multi-setting source steps into one step each.

**Anchor the marker in prose.** Write the setting into the text the way Cookidoo does ("...whisk 6 min/speed 3.5") so the annotation anchors exactly in place. If the marker is absent from `text`, the tool appends a canonical one. Use `anchor` to point at an existing substring when the wording differs.

### TTS steps (time / temp / speed / direction)

- `temperature_c` enum: OFF, 37, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 98, 100, 105, 110, 115, 120. Off-enum but in-range values snap to nearest. Out-of-range or non-numeric values are dropped and stay in prose (no setting). `temperature_f` has its own enum.
- Varoma (steaming) temperature: the wire enum also accepts `varoma`, but the `temperature_c` int field cannot carry it. Pass a pre-built TTS annotation via the step's raw `annotations` field with `data.temperature = {"value":"varoma"}` (plus `time`/`speed`).
- `speed`: "soft" (Spoon / soft-stir) or 0.5..5 manual. Speeds 6..8 are only reachable via MODE=BLEND, which is not persisted (see below).
- `reverse=true` → counter-clockwise (Linkslauf).

### MODE steps — do NOT rely on them (not persisted today)

Cookidoo's created-recipe API silently strips every MODE annotation on save (BROWNING, STEAMING, DOUGH, BLEND, TURBO, WARM_UP, RICE_COOKER all come back `annotations:[]`). Confirmed by live read-after-write on 2026-06-26. TTS annotations on the same recipe persist. MODE is still modeled in the MCP code for if/when the API accepts it, but it has no effect on saved recipes — never use `mode` for a recipe you want to be guided.

Encode every machine setting through TTS instead, and name the program/accessory (Browning, Varoma, butterfly, sous-vide) in the step prose:

| was MODE | encode as TTS | name in prose |
|----------|---------------|---------------|
| BROWNING (sauté/sear/reduce) | `time_seconds` + `temperature_c` + `speed` (e.g. speed 1 to stir) | "...in Browning, 12 min/105°C/speed 1, measuring cup off" |
| STEAMING (Varoma) | raw `annotations` TTS with `temperature:{value:"varoma"}` + `time` + `speed` | "Arrange broccoli in the Varoma dish and steam 12 min/Varoma/speed 1" |
| WARM_UP / BLEND / DOUGH / TURBO / RICE_COOKER | the matching `time`/`temperature`/`speed` it would have carried | name the program in prose |

`power` and `pulse_count` have no TTS home — describe them in prose. The mode name itself always goes in prose.

### Not doable → keep in prose, never in fields

These have no structured representation. Write them explicitly in `text` and pass no setting fields for them — never approximate with a structured value:

- Named programs: Sous-vide, Slow Cook, Fermentation, Egg boiler, Sugar/Caramelize, TM6/TM7 High-Temperature.
- Non-Varoma accessories: butterfly whisk, simmering basket, spatula, measuring-cup on/off, blade cover, peeler/cutter.
- Exact non-enum temperatures (e.g. 63 °C sous-vide).

Example prose: `"Sous-vide 63 °C / 45 min (set program manually)"`. Passing `temperature_c=63` would snap to 65 and lie about the setting.

### Mapping a source recipe

Read each source step, identify its time/temp/speed/direction, fill the matching TTS fields, and keep the prose readable. A former MODE step becomes a TTS step with its time/temp/speed and the program named in prose. If it is a not-doable program or accessory, render it in prose only.

Worked example — three source steps mapped to `steps`:

```python
steps=[
    # 1. TTS: chop onion
    {"text": "Chop onion 5 sec/speed 5.", "time_seconds": 5, "speed": "5"},
    # 2. Varoma steaming — TTS with temperature=varoma via raw annotations
    {"text": "Place fish in Varoma and steam 15 min/Varoma/speed 1.",
     "annotations": [{"type": "TTS",
                      "position": {"offset": 23, "length": 22},
                      "data": {"time": 900, "speed": "1",
                               "temperature": {"value": "varoma"}}}]},
    # 3. Not doable: sous-vide — prose only, no structured fields
    {"text": "Sous-vide the fillet 63 °C / 45 min (set program manually)."},
]
```

## Error Handling

- Missing local config: tell the user to run `/cookidoo-login`.
- 401 or 403: tell the user the Cookidoo cookies are stale and need refresh.
- Empty search: try another language or remove filters.
- Missing nutrition: say the official recipe details did not include that value.
- Tool failure: report the operation that failed and the next user action; do not guess recipe data.
