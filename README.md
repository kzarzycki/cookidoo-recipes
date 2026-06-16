# Cookidoo Recipes MCP

Unofficial local MCP server and Codex/Claude plugin for Cookidoo recipe search, recipe access, translation workflows, image copying, and custom recipe creation.

It runs on your machine, uses your own Cookidoo subscription session, and talks to Cookidoo endpoints that may change.

## Features

- Search Cookidoo catalogue recipes without a machine filter unless one is requested.
- Search across country/language facets when recipe language does not matter.
- Fetch recipe details, ingredients, preparation steps, tags, and official nutrition when Cookidoo returns it.
- Include your own created recipes in search when requested.
- Expand relevant Cookidoo collections during discovery and return provenance for each result.
- Upload/copy official Cookidoo images into customer-recipe images.
- Create custom recipes with dry-run-first write protection.
- Provide a reusable plugin and skill for search, translate, review, save, and read-back workflows.

## Plugin Install

Requires Python 3.12+ and `uv`.

This repository is also a local plugin. It includes:

- `.codex-plugin/plugin.json`
- `.claude-plugin/plugin.json`
- `.mcp.json`
- `commands/cookidoo-login.md`
- `skills/cookidoo-recipes/SKILL.md`
- `scripts/cookidoo-login`
- `scripts/cookidoo-mcp`

After the plugin is published to a Codex marketplace:

```bash
codex plugin add cookidoo-recipes@<marketplace>
```

For Claude, install the same plugin bundle through your Claude Code plugin source. Reload the agent session after installation.

Verify that the plugin loaded:

- `/cookidoo-login` appears in the slash-command menu.
- The Cookidoo Recipes skill appears in the available skills list.
- `cookidoo_auth_status` is available after the MCP server starts.

Then run:

```text
/cookidoo-login
```

The command starts a local terminal login wizard. It asks which Cookidoo site you use, lists Cookidoo's current country/region choices, asks for the valid language for that site, then prompts for email and password locally. The password is not stored and should never be pasted into chat.

Login writes:

```text
~/.cookidoo-recipes/config.yaml
~/.cookidoo-recipes/cookies.json
```

`config.yaml` stores non-secret routing data:

```yaml
site:
  country: <cookidoo-country>
  locale: <cookidoo-locale>
  label: <selected-site-label>
  url: <selected-cookidoo-foundation-url>
cookies:
  file: ~/.cookidoo-recipes/cookies.json
```

Cookie and config files are written with `0600` permissions. Group-readable or world-readable files are refused.

Check auth:

```bash
uv run cookidoo auth-status
```

If `/cookidoo-login` is not available, the plugin did not load. Raw MCP registration connects recipe tools but does not install the slash command.

## Manual CLI And MCP

The plugin wrappers use `uv` when available, so a plugin checkout can sync and run its environment on demand. For development, prepare the checkout explicitly:

```bash
uv sync --extra cookidoo --group dev
```

Console scripts:

- `cookidoo`
- `cookidoo-mcp`

Manual login uses the same wizard:

```bash
uv run cookidoo login
```

Scripted login can pass resolved site settings. It still prompts for the password in a local terminal:

```bash
uv run cookidoo login --country <country> --locale <locale> --email <email>
```

Browser-cookie import:

```bash
uv run cookidoo import-cookies --netscape-file ./cookidoo-cookies.txt --country <country> --locale <locale>
```

Stdin import for the two required cookies:

```bash
python3 -c 'import getpass,json; print(json.dumps({"oauth2_proxy": getpass.getpass("_oauth2_proxy: "), "v_authenticated": getpass.getpass("v-authenticated: "), "domain": "cookidoo.<country>"}))' \
  | uv run cookidoo import-cookies --from-json --country <country> --locale <locale>
```

Run the MCP server over stdio:

```bash
uv run cookidoo-mcp
```

Override local config for scripted clients:

```bash
uv run cookidoo-mcp \
  --config-file /path/to/config.yaml \
  --cookie-file /path/to/cookies.json \
  --country <country> \
  --locale <locale> \
  --url <cookidoo-foundation-url>
```

`country` and `locale` choose the account host and account endpoints. They are not recipe-result filters unless passed to `cookidoo_search`.

MCP registration example:

```bash
claude mcp add cookidoo -- /absolute/path/to/repo/scripts/cookidoo-mcp
```

Use the equivalent MCP registration command for Codex or another MCP client.

## MCP Tools

- `cookidoo_auth_status`
- `cookidoo_discover_recipes`
- `cookidoo_search`
- `cookidoo_get_recipe`
- `cookidoo_list_my_recipes`
- `cookidoo_get_collection`
- `cookidoo_upload_recipe_image`
- `cookidoo_create_recipe`

`cookidoo_discover_recipes` is the normal entry point. It searches multiple country/language facets, expands relevant collections, deduplicates recipes, and returns provenance metadata. It does not apply a machine filter unless `tm_model` is supplied.

`cookidoo_search` is for exact country, language, locale, machine, ingredient, time, rating, serving, and tag filters. Country, language, and machine are optional.

`cookidoo_create_recipe` defaults to `dry_run=true`. A dry run returns a `confirmation_token`; a real write with `dry_run=false` is rejected unless the token matches the exact reviewed payload.

`cookidoo_upload_recipe_image` takes an official Cookidoo image URL and returns a customer-recipe image key. It also defaults to `dry_run=true` and requires the returned `confirmation_token` for the real upload.

## Agent Workflow

Install the plugin or copy `skills/cookidoo-recipes/SKILL.md` into your agent skill directory, then connect the MCP server. The skill instructs the agent to:

1. Check `cookidoo_auth_status`.
2. Use `cookidoo_discover_recipes` for language-agnostic search.
3. Fetch selected recipes with `cookidoo_get_recipe`.
4. Translate only visible recipe content.
5. Preserve metric units unless asked to convert.
6. Copy images through `cookidoo_upload_recipe_image` when possible.
7. Show a dry run before saving.
8. Save only after explicit confirmation.
9. Read back the saved recipe and verify title, counts, machine tag if any, and image.

## Development

```bash
uv run pytest -q
uv run python -m compileall src tests scripts
uv build
```

Build and publish from a clean checkout. `work/`, `outputs/`, `.venv/`, `dist/`, and `*.egg-info/` are local artifacts; do not zip or upload them as part of a plugin release.

The live e2e script uses your local cookie jar and can write to your Cookidoo account only when called with `--write`:

```bash
uv run python scripts/live_e2e.py --cookie-file ~/.cookidoo-recipes/cookies.json
uv run python scripts/live_e2e.py --cookie-file ~/.cookidoo-recipes/cookies.json --write
```

Keep live outputs under `work/`; that directory is ignored.

## Security Notes

- Do not commit cookie jars, Netscape cookie exports, browser captures, or live network responses.
- The repository `.gitignore` excludes cookie-like filenames, `work/`, `outputs/`, and network capture extensions.
- MCP writes are dry-run-first and confirmation-token gated.
- Tool errors are sanitized so upstream tracebacks do not expose raw cookies or tokens.

## Known Limits

- Cookidoo has no public API, so this project uses reverse-engineered endpoints. Cookidoo can change request shapes, auth behavior, image upload flow, or search responses without notice.
- Custom recipe listing, image upload, and creation use internal endpoints. These features need live verification after Cookidoo frontend changes.
- The upstream client needs an account country and locale to choose the Cookidoo host. Those settings do not guarantee access to every regional catalogue.
- Search can omit machine filters, but Cookidoo may still rank or hide recipes according to its own compatibility rules.
- Cookidoo search may return a canonical recipe id rather than every serving-size variant.
- Created recipes are not part of catalogue search, so merged search lists them through a separate account call and client-side title matching.
