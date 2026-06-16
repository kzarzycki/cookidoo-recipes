# Cookidoo TM7 Design

## Product

Build a local Cookidoo assistant for a TM7 owner who wants recipe search, recipe access, translation, and custom recipe creation across languages. The first workflow is: search Cookidoo in any useful language, inspect official recipe details and nutrition, translate or adapt the recipe for TM7, then save it as a Cookidoo custom recipe. Saved translations should be searchable together with official catalogue results when requested.

The tool is local and subscription-backed. It does not claim official Vorwerk support. It uses the user's own Cookidoo session and treats every upstream endpoint as unofficial and likely to change.

## Scope

In scope:

- MCP server exposing `cookidoo_search`, `cookidoo_get_recipe`, `cookidoo_list_my_recipes`, `cookidoo_upload_recipe_image`, `cookidoo_create_recipe`, and `cookidoo_auth_status`.
- Auth helpers for importing browser cookies and validating a local cookie jar.
- Multi-language search with per-call language/locale options.
- Optional merge of custom recipes into search results.
- Recipe detail normalization: title, id, source, URL, ingredients, steps, timings, difficulty, servings, nutrition, and tags. Raw upstream payload is returned only when `include_raw=true`.
- Skill instructions for search → detail → nutrition filter → translate/adapt → confirm → save.
- Tests that do not require real Cookidoo credentials.

Out of scope:

- Sending recipes directly to the TM7 device.
- Bypassing Cookidoo subscription, region, or account restrictions.
- Browser automation that extracts private cookies without explicit user action.
- Guaranteed compatibility with every future Cookidoo API change.

## Architecture

The implementation has four layers:

1. `models`: typed internal recipe/search/auth objects.
2. `client`: a Cookidoo adapter that wraps `cookidoo-api` when available and exposes stable methods to the rest of the project.
3. `tools`: MCP tool functions with validation, normalization, and stderr logging.
4. `skill`: operational guidance for agents so normal requests use the tools in the right order.

The MCP layer never exposes upstream objects directly. It returns JSON-friendly dictionaries shaped by the internal model layer. That makes tests deterministic and gives one place to patch if `cookidoo-api` changes. The verified upstream base is `miaucl/cookidoo-api` at commit `d7fd1faf94550d7051676f4a11ca77678d9624ac`, including `search_recipes`, `get_recipe_details`, `get_custom_recipe`, and `ThermomixMachineType.TM7`.

## Auth

Primary auth is a cookie jar file containing Cookidoo session cookies. The cookie import helper accepts stdin JSON or a Netscape-format cookie export so cookie values do not appear in process listings. It writes the jar with `0600` permissions. The MCP server refuses account tools when auth is missing or expired and returns a plain stale-cookie message.

The project does not store the Cookidoo password. If an interactive login helper is added later, it must use the password only in memory and must not log request bodies, tokens, or cookies.

## Search

`cookidoo_search` supports:

- query text
- language, locale, country
- include and exclude ingredients
- difficulty
- max prep time
- max total time
- servings
- minimum rating
- tags
- TM model, default `TM7`
- pagination
- `include_my_recipes`

Catalogue search and custom recipe listing are separate upstream calls. When `include_my_recipes=true`, the server merges custom recipes client-side and marks each result with `source: "my_recipes"` or `source: "cookidoo"`. The created-recipe list endpoint is verified in captured upstream API docs, not as a stable `cookidoo-api` library method, so this path is best-effort.

## Detail And Nutrition

`cookidoo_get_recipe` returns full details for one recipe id. Nutrition values are only quoted when present in details. Low-carb workflows must search first, fetch details for candidates, then filter by the returned nutrition values.

## Create

`cookidoo_create_recipe` accepts a normalized recipe draft with target language/locale, servings, ingredients, steps, notes, tags, optional customer-recipe image key, and TM model. The default model is `TM7`. The tool is designed for translated or agent-authored custom recipes. A dry run returns a confirmation token, and server-side write calls require that token for the exact reviewed payload.

## Translation Workflow

Agents should search in the source language, fetch details, translate visible content into the requested target language, preserve measurable quantities, upload official source images with `cookidoo_upload_recipe_image`, adapt method text for TM7 conventions, and save only after confirmation. Control details such as language or metric policy stay out of the recipe title. Default target locale is `de-CH` unless the user requests Polish, English, or another locale.

## TM7 Conventions

- Use Browning for searing and sauteing steps.
- Use Open Cooking for reductions, risotto-like stirring, and braises where lid-off evaporation matters.
- Use reverse blade for chunky meat or vegetables.
- Keep dairy finishing steps at or below 90 C unless the source recipe says otherwise.
- Prefer explicit time, temperature, direction, and speed in saved custom steps.

## Error Handling

Tool errors should identify the failing operation and likely user action: refresh cookies, narrow search, fetch fewer details, or retry later. Internal tracebacks and tokens are not returned to the model client.

## Acceptance Criteria

- The MCP server starts as a stdio server.
- All tools are importable and have JSON-schema-friendly signatures.
- Missing auth produces a controlled error.
- Search parameters normalize language, locale, country, and TM7 defaults.
- Custom recipe search merge is deterministic and source-labelled.
- Nutrition filtering workflow is encoded in the skill.
- Cookie files are written with owner-only permissions.
- Tests cover model normalization, auth file behavior, search merge, tool validation, and create payload shaping.
