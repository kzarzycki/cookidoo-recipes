# Public Repo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the local Cookidoo recipe MCP project into a shareable git repository without tracking private Cookidoo artifacts.

**Architecture:** Keep the Python package and skill unchanged. Add repository metadata, public documentation, CI, and strict ignore rules around cookies and live outputs.

**Tech Stack:** Python 3.11+, setuptools, pytest, FastMCP, aiohttp, GitHub Actions.

---

### Task 1: Public Repository Files

**Files:**
- Create: `.gitignore`
- Create: `LICENSE`
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `pyproject.toml`

- [x] Add ignore rules for Python generated files, virtual environments, cookie files, `work/`, `outputs/`, and network captures.
- [x] Add MIT license text.
- [x] Add contributor setup and credential-handling rules.
- [x] Add security policy for cookie and write-operation risks.
- [x] Add CI for unit tests and compile checks.
- [x] Update package metadata for README and license.

### Task 2: Verification

**Files:**
- Read: staged git index
- Read: ignored-file report

- [ ] Run `pytest -q`.
- [ ] Run `python3 -m compileall src tests scripts`.
- [ ] Run `python3 -m build`.
- [ ] Run `git check-ignore` against known cookie and work artifacts.
- [ ] Stage only curated public files.
- [ ] Inspect staged files for credential-like content.
- [ ] Commit the initial public baseline.
