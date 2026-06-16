# Public Repository Design

## Goal

Make the Cookidoo TM7 MCP project safe to share as a git repository without exposing local Cookidoo cookies, browser exports, network captures, or live account outputs.

## Public Surface

The repository tracks the Python package, tests, live e2e helper script, local Codex skill, Superpowers docs, README, license, security policy, contribution guide, and CI workflow.

Generated files and local account artifacts stay untracked: `.venv/`, Python caches, `.pytest_cache/`, `*.egg-info/`, `work/`, `outputs/`, cookie exports, cookie jars, and network capture files.

## Documentation

`README.md` is the main public entry point. It covers purpose, install, auth, MCP registration, tool list, workflows, verification, and limits. `SECURITY.md` documents credential handling. `CONTRIBUTING.md` documents local setup, test commands, and credential rules for future changes.

## Verification

The baseline must pass:

- `pytest -q`
- `python3 -m compileall src tests scripts`
- package build
- git ignore checks for cookie-like paths and `work/`
