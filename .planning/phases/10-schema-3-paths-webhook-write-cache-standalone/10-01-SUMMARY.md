---
phase: 10-schema-3-paths-webhook-write-cache-standalone
plan: "01"
subsystem: backend
tags: [wave0, cachetools, path2-callsite, messageTimestamp, pre-deps]
dependency_graph:
  requires: []
  provides:
    - cachetools dependency declared in requirements.txt
    - Path 2 callsite localized (agente.py:3822-3867)
    - messageTimestamp parser strategy documented
  affects:
    - leadflow-backend/requirements.txt
    - Plans 02-05 (all consume these findings)
tech_stack:
  added:
    - cachetools>=5.5.0,<6.0.0
  patterns:
    - PyPI JSON API via curl (fallback when local pip is broken)
    - Wave 0 spike pattern: validate before touching production code
key_files:
  created:
    - .planning/phases/10-schema-3-paths-webhook-write-cache-standalone/10-01-WAVE0-NOTES.md
  modified:
    - leadflow-backend/requirements.txt
decisions:
  - "cachetools>=5.5.0,<6.0.0 chosen (not fallback >=5.3.0): 5.5.0 confirmed present on PyPI"
  - "messageTimestamp parser: defensive 3-shape (epoch int / epoch ms >10^12 / ISO string / fallback utcnow) — confirm shape via live log in Wave 2"
  - "Path 2 UPSERT inserts at 2 sub-paths: after _salvar_lead_lid (line 3846) and after _tel_match assignment (line 3863)"
  - "instance_key = payload.get('instance') directly, NOT get_instance_key() lookup — Pitfall 3 avoidance"
metrics:
  duration: "~20 minutes"
  completed: "2026-06-09"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 1
  files_created: 1
---

# Phase 10 Plan 01: Wave 0 Pre-Dependencies Summary

**One-liner:** cachetools 5.5.0 confirmed on PyPI + added to requirements.txt; Path 2 callsite localized at agente.py:3822-3867 with 10 variables in scope documented; messageTimestamp defensive parser strategy defined.

## What Was Done

### Task 1: cachetools version confirmed + requirements.txt updated

Queried PyPI JSON API directly (local venv pip broken due to `pip._vendor.idna` circular import). Confirmed `cachetools 5.5.0` is available — full 5.x range: `5.0.0..5.5.2`. Latest overall is `7.1.4` (out of our `<6.0.0` pin, intentionally).

Added `cachetools>=5.5.0,<6.0.0` to `leadflow-backend/requirements.txt` at line 26, between `apscheduler==3.10.4` (L25) and `pytz>=2024.1` (L27) — correct alphabetical position.

### Task 2: Path 2 callsite localized + WAVE0-NOTES.md created

Confirmed `[LID-CAPTURE-MSG]` block at `agente.py:3822-3867` (MESSAGES_UPSERT handler, `if _remoto_raw.endswith("@g.us"):` branch, `if _emp_g_id:` guard). Documented 10 variables in scope, two insertion points for Plan 04 UPSERT patch, and the `instance_key = _inst_g` rule (Pitfall 3 avoidance).

A2 (`messageTimestamp` shape) documented as pending live log — defensive 3-shape parser strategy defined in NOTES.md for Plan 03 to implement.

## Commits

| Task | Commit | Repo | Description |
|------|--------|------|-------------|
| Task 1 | e1b46a4 | leadflow-backend | chore(10-01): add cachetools>=5.5.0,<6.0.0 to requirements.txt |
| Task 2 | 4cfe3ee | root | chore(10-01): Wave 0 notes — cachetools confirmed + Path 2 callsite localized |

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Environmental Notes

- Local venv pip is broken (ImportError on `pip._vendor.idna`) — used `curl + python` against PyPI JSON API as fallback. This did not block the task; pip on Easypanel's Docker build is unaffected.
- SSH to Easypanel container `3e74f7da5a68` not available during this execution — A2 (`messageTimestamp` shape) documented with "pending" status + fallback parser strategy. Plan 03 Task 1 must log the actual shape from the first webhook that arrives after deploy.

## Verification Results

- `grep -c "^cachetools" leadflow-backend/requirements.txt` → `1` (single entry)
- `grep -n "apscheduler\|cachetools\|pytz" leadflow-backend/requirements.txt` → lines 25/26/27 consecutive
- `grep -q "### A1: cachetools version" 10-01-WAVE0-NOTES.md` → exit 0
- `grep -q "### A2: messageTimestamp shape" 10-01-WAVE0-NOTES.md` → exit 0
- `grep -q "### A4: Path 2 callsite" 10-01-WAVE0-NOTES.md` → exit 0
- `grep -c "LID-CAPTURE-MSG" agente.py` → `4` (>=1 — callsite preexistente intacto)
- WAVE0-NOTES.md line count: 132 lines (>30 minimum)

## Known Stubs

None — this is a Wave 0 validation plan. No production code logic was implemented.

## Threat Flags

None — only `requirements.txt` (new dependency declaration) and a planning `.md` file modified. No new network endpoints, auth paths, or schema changes introduced in this plan.

## Self-Check: PASSED

- `c:/Projetos/Leadflow/leadflow-backend/requirements.txt` — FOUND, contains `cachetools>=5.5.0,<6.0.0` at line 26
- `c:/Projetos/Leadflow/.planning/phases/10-schema-3-paths-webhook-write-cache-standalone/10-01-WAVE0-NOTES.md` — FOUND, 132 lines, all 3 sections present
- Commit `e1b46a4` — FOUND in leadflow-backend (main branch)
- Commit `4cfe3ee` — FOUND in root repo (feat/pipeline-visual-refresh branch)
