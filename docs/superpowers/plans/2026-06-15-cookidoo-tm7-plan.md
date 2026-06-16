# Cookidoo TM7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local MCP server and skill for Cookidoo search, access, translation workflow, and TM7 custom recipe creation.

**Architecture:** A Python package contains normalized models, a Cookidoo adapter, MCP tools, and auth helpers. The MCP tools return stable JSON dictionaries and keep unofficial upstream behavior behind one adapter.

**Tech Stack:** Python 3.13, FastMCP, pytest, optional `cookidoo-api` from Git main, stdio MCP.

---

### Task 1: Project Skeleton And Models

**Files:**
- Create: `pyproject.toml`
- Create: `src/cookidoo_mcp/__init__.py`
- Create: `src/cookidoo_mcp/models.py`
- Test: `tests/test_models.py`

- [ ] Write tests for `SearchQuery`, `RecipeSummary`, `RecipeDetail`, and `RecipeDraft` normalization.
- [ ] Implement dataclasses with `to_dict()` methods.
- [ ] Run `python3 -m pytest tests/test_models.py -q`.

### Task 2: Auth Store

**Files:**
- Create: `src/cookidoo_mcp/auth.py`
- Create: `src/cookidoo_mcp/cli.py`
- Test: `tests/test_auth.py`

- [ ] Write tests for cookie jar creation, missing auth status, and `0600` permissions.
- [ ] Implement `CookieAuthStore`, `import_cookie_values`, and CLI commands.
- [ ] Run `python3 -m pytest tests/test_auth.py -q`.

### Task 3: Cookidoo Adapter

**Files:**
- Create: `src/cookidoo_mcp/client.py`
- Test: `tests/test_client.py`

- [ ] Write tests with a fake upstream client for search, details, my-recipes listing, and create payloads.
- [ ] Implement `CookidooClient` with lazy optional `cookidoo-api` import and fake-client injection.
- [ ] Run `python3 -m pytest tests/test_client.py -q`.

### Task 4: MCP Tools

**Files:**
- Create: `src/cookidoo_mcp/server.py`
- Test: `tests/test_server_tools.py`

- [ ] Write tests for auth status, search merge, detail return shape, and create validation.
- [ ] Implement FastMCP tool registration and pure async tool functions.
- [ ] Run `python3 -m pytest tests/test_server_tools.py -q`.

### Task 5: Skill And Docs

**Files:**
- Create: `skills/cookidoo-tm7/SKILL.md`
- Create: `README.md`
- Create: `outputs/cookidoo-tm7-summary.md`

- [ ] Write the skill with triggers, workflow, tool order, TM7 conventions, and write-confirmation guardrail.
- [ ] Write installation and verification docs.
- [ ] Link the completed deliverable from `outputs/`.

### Task 6: Verification

**Files:**
- Create: `work/verification-report.md`

- [ ] Run unit tests.
- [ ] Run package build/import checks.
- [ ] Run MCP initialization smoke test.
- [ ] Dispatch independent review agents and record findings.
