---
phase: 13-leave-handler-fsm-audit-monotonico
plan: "03"
subsystem: backend/fsm-callsite-migration
tags: [fsm, audit, callsite-migration, grupo_state, monotonic, caller]
dependency_graph:
  requires: [13-01]
  provides: [FSM-AUDIT-03, all_callsites_named]
  affects:
    - leadflow-backend/app/routers/admin.py
    - leadflow-backend/app/routers/leads.py
    - leadflow-backend/app/services/grupo_fallback.py
    - leadflow-backend/scripts/check_fsm_callers.py
tech_stack:
  added: []
  patterns:
    - "All set_grupo_state/transition_grupo_state callers pass reason= + caller= kwargs"
    - "force=True restricted to admin path (C2) and webhook leave handler (C9 from Plan 02)"
    - "scripts/check_fsm_callers.py: AST-walk sweep asserting no anonymous callsite"
key_files:
  modified:
    - leadflow-backend/app/routers/admin.py
    - leadflow-backend/app/routers/leads.py
    - leadflow-backend/app/services/grupo_fallback.py
  created:
    - leadflow-backend/scripts/check_fsm_callers.py
decisions:
  - "force=True added only at C2 (admin_promover_ativo) per plan — operator-confirmed visual check is the one sanctioned bypass"
  - "sweep script uses ast.Walk over Call nodes, skips FunctionDef lines — robust vs line-pattern false positives"
  - "scripts/check_fsm_callers.py lives in scripts/ (reusable by Plan 04 pytest CI test)"
metrics:
  duration: "5min"
  completed_date: "2026-06-10"
  tasks_completed: 3
  files_modified: 3
  files_created: 1
requirements: [FSM-AUDIT-03]
---

# Phase 13 Plan 03: FSM Callsite Migration (C2–C8) Summary

**One-liner:** Migrated all 7 external `set_grupo_state`/`transition_grupo_state` callsites in `admin.py`, `leads.py`, and `grupo_fallback.py` to the mandatory `reason=`/`caller=` signature from Plan 01; added `scripts/check_fsm_callers.py` AST sweep that exits 0 (0 violations across 66 files).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Migrate admin.py C2 + leads.py C3, C4 | `e59c0da` | `app/routers/admin.py`, `app/routers/leads.py` |
| 2 | Migrate grupo_fallback.py C5, C6, C7, C8 | `8f94dc1` | `app/services/grupo_fallback.py` |
| 3 | Whole-repo no-anonymous-caller sweep script | `5dbdc60` | `scripts/check_fsm_callers.py` |

## What Was Built

### Callsite migrations

All 7 external callers of the FSM API now pass `reason=` and `caller=` explicitly:

| # | File | Line | caller= value | force= |
|---|------|------|--------------|--------|
| C2 | `app/routers/admin.py` | 917 | `admin_promover_ativo` | `True` |
| C3 | `app/routers/leads.py` | 137 | `leads_reuso_grupo` | default (False) |
| C4 | `app/routers/leads.py` | 256 | `leads_promote_admin` | default (False) |
| C5 | `app/services/grupo_fallback.py` | 278 | `fallback_retroativo_ativo` | default (False) |
| C6 | `app/services/grupo_fallback.py` | 415 | `fallback_criar_grupo` | default (False) |
| C7 | `app/services/grupo_fallback.py` | ~893 | `fallback_timeout_30min` | default (False) |
| C8 | `app/services/grupo_fallback.py` | ~998 | `fallback_lead_entrou` | default (False) |

C1 (internal delegation in `grupo_state.py`) was handled in Plan 01.
C9 (webhook_remove) was added in Plan 02 with `caller="webhook_remove"`, `force=True`.

### `scripts/check_fsm_callers.py`

AST-walk sweep over `app/**/*.py`:
- Finds `ast.Call` nodes whose func resolves to `set_grupo_state` or `transition_grupo_state`
- Asserts `caller` is present in `node.keywords`
- Asserts `caller` value is not `"unknown"`
- Skips `FunctionDef`/`AsyncFunctionDef` nodes (definition lines)
- Reads files with `encoding='utf-8'` (Windows cp1252-safe)
- Exits 0 / prints pass message; exits 1 with file:line list on violation

Result: **66 files scanned, 0 violations.**

## Deviations from Plan

None — plan executed exactly as written. All 7 callsites migrated with the exact `caller=` values specified in the plan interfaces. The sweep script was implemented as specified in Task 3.

## Known Stubs

None.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced.
`force=True` usage confirmed: only `admin.py` (C2 — operator action behind `_check_auth`) and `grupo_webhook.py` (C9 — webhook leave handler from Plan 02). Both are sanctioned paths per the threat model.

## Self-Check

- [x] `app/routers/admin.py` contains `caller="admin_promover_ativo"` and `force=True`
- [x] `app/routers/leads.py` contains `caller="leads_reuso_grupo"` and `caller="leads_promote_admin"`
- [x] `app/services/grupo_fallback.py` contains all 4 caller= values: `fallback_retroativo_ativo`, `fallback_criar_grupo`, `fallback_timeout_30min`, `fallback_lead_entrou`
- [x] `scripts/check_fsm_callers.py` exists and exits 0
- [x] No `caller="unknown"` in any file
- [x] All 3 modified source files ast.parse clean (verified via `python -c "import ast; ast.parse(...)"`)
- [x] All 3 submodule commits exist: `e59c0da`, `8f94dc1`, `5dbdc60`
