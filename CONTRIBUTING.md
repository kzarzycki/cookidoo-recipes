# Contributing

This project is an unofficial local MCP server for Cookidoo. Treat account access as sensitive.

## Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[cookidoo,test]'
pytest -q
python3 -m compileall src tests scripts
```

## Rules For Changes

- Do not commit Cookidoo cookies, browser exports, network captures, or live account outputs.
- Keep write operations dry-run-first and confirmation-token gated.
- Keep MCP stdout clean; diagnostics belong on stderr.
- Add unit tests for adapter behavior before changing search, auth, write, or image-upload logic.
- Use live Cookidoo checks only from a local account and keep outputs under `work/`, which is ignored.

## Pull Request Checklist

- `pytest -q` passes.
- `python3 -m compileall src tests scripts` passes.
- `python3 -m build` passes when packaging metadata changes.
- `git status --ignored --short` shows no staged or tracked credential files.
- README and skill instructions match any changed tool behavior.
