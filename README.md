# Cookidoo TM7 MCP

Unofficial local MCP server and Codex/Claude skill for Cookidoo recipe search, recipe access, translation workflows, image copying, and TM7 custom recipe creation.

It runs on your machine, uses your own Cookidoo subscription session, and talks to Cookidoo endpoints that may change.

## Features

- Search Cookidoo catalogue recipes with TM7 as the default machine filter.
- Search across country/language facets when the user does not care about recipe language.
- Fetch recipe details, ingredients, preparation steps, tags, and official nutrition when Cookidoo returns it.
- Include your own created recipes in search when requested.
- Expand relevant Cookidoo collections during discovery and return provenance for each result.
- Upload/copy official Cookidoo images into customer-recipe images.
- Create TM7-tagged custom recipes with dry-run-first write protection.
- Provide a reusable skill for search, translate, review, save, and read-back workflows.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[cookidoo,test]'
```

The optional `cookidoo-api` dependency is pinned to commit `d7fd1faf94550d7051676f4a11ca77678d9624ac`.

## Authentication

No Cookidoo password is stored by this project. Runtime auth uses a local cookie jar.

Interactive login:

```bash
cookidoo-tm7 login --email you@example.com --country ch --locale de-CH --cookie-file ~/.cookidoo-tm7/cookies.json
```

The command prompts for your password, performs the Cookidoo login, then stores only cookies.

Browser-cookie import:

```bash
cookidoo-tm7 import-cookies --cookie-file ~/.cookidoo-tm7/cookies.json --netscape-file ./cookidoo-cookies.txt
```

Stdin import for the two required cookies:

```bash
python3 -c 'import getpass,json; print(json.dumps({"oauth2_proxy": getpass.getpass("_oauth2_proxy: "), "v_authenticated": getpass.getpass("v-authenticated: "), "domain": "cookidoo.ch"}))' \
  | cookidoo-tm7 import-cookies --cookie-file ~/.cookidoo-tm7/cookies.json --from-json
```

Cookie files are written with `0600` permissions. Group-readable or world-readable cookie files are refused.

Check auth:

```bash
cookidoo-tm7 auth-status --cookie-file ~/.cookidoo-tm7/cookies.json
```

## MCP Server

Run over stdio:

```bash
cookidoo-tm7-mcp --cookie-file ~/.cookidoo-tm7/cookies.json
```

MCP registration example:

```bash
claude mcp add cookidoo-tm7 -- /absolute/path/to/.venv/bin/cookidoo-tm7-mcp --cookie-file /Users/you/.cookidoo-tm7/cookies.json
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

`cookidoo_discover_recipes` is the normal entry point. It searches multiple country/language facets, expands relevant collections, deduplicates recipes, and returns provenance metadata.

`cookidoo_search` is for exact country/language/locale searches.

`cookidoo_create_recipe` defaults to `dry_run=true`. A dry run returns a `confirmation_token`; a real write with `dry_run=false` is rejected unless the token matches the exact reviewed payload.

`cookidoo_upload_recipe_image` takes an official Cookidoo image URL and returns a customer-recipe image key. It also defaults to `dry_run=true` and requires the returned `confirmation_token` for the real upload.

## Agent Workflow

Install or copy `skills/cookidoo-tm7/SKILL.md` into your agent skill directory, then connect the MCP server. The skill instructs the agent to:

1. Check `cookidoo_auth_status`.
2. Use `cookidoo_discover_recipes` for language-agnostic search.
3. Fetch selected recipes with `cookidoo_get_recipe`.
4. Translate only visible recipe content.
5. Preserve metric units unless asked to convert.
6. Copy images through `cookidoo_upload_recipe_image` when possible.
7. Show a dry run before saving.
8. Save only after explicit confirmation.
9. Read back the saved recipe and verify title, counts, TM7 tools, and image.

## Development

```bash
pytest -q
python3 -m compileall src tests scripts
python3 -m build
```

The live e2e script uses your local cookie jar and can write to your Cookidoo account only when called with `--write`:

```bash
python3 scripts/live_e2e.py --cookie-file ~/.cookidoo-tm7/cookies.json
python3 scripts/live_e2e.py --cookie-file ~/.cookidoo-tm7/cookies.json --write
```

Keep live outputs under `work/`; that directory is ignored.

## Security Notes

- Do not commit cookie jars, Netscape cookie exports, browser captures, or live network responses.
- The repository `.gitignore` excludes cookie-like filenames, `work/`, `outputs/`, and network capture extensions.
- MCP writes are dry-run-first and confirmation-token gated.
- Tool errors are sanitized so upstream tracebacks do not expose raw cookies or tokens.

## Known Limits

- Cookidoo has no public API.
- Custom recipe listing, image upload, and creation use internal endpoints.
- Regional catalogue coverage depends on what the authenticated Cookidoo session can access.
- Cookidoo search may return a canonical recipe id rather than every serving-size variant.
- Created recipes are not part of catalogue search, so merged search lists them through a separate account call and client-side title matching.
