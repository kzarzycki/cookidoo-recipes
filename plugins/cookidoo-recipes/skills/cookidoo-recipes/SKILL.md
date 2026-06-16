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

Use time, temperature, direction, speed, and mode when the source supports it. If adapting from a recipe that was not written for the requested machine, say the saved method is generated/adapted content.

## Error Handling

- Missing local config: tell the user to run `/cookidoo-login`.
- 401 or 403: tell the user the Cookidoo cookies are stale and need refresh.
- Empty search: try another language or remove filters.
- Missing nutrition: say the official recipe details did not include that value.
- Tool failure: report the operation that failed and the next user action; do not guess recipe data.
