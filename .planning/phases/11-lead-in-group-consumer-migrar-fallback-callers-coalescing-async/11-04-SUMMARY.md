---
phase: 11-lead-in-group-consumer-migrar-fallback-callers-coalescing-async
plan: 04
subsystem: api
tags: [deploy, build_version, healthcheck, observability, grupo_membership]

# Dependency graph
requires:
  - phase: 11-lead-in-group-consumer-migrar-fallback-callers-coalescing-async
    plan: 01
    provides: lead_in_group() async consumer + _probe_locks dict
  - phase: 11-lead-in-group-consumer-migrar-fallback-callers-coalescing-async
    plan: 02
    provides: grupo_fallback.py with 7 callsite migrations
  - phase: 11-lead-in-group-consumer-migrar-fallback-callers-coalescing-async
    plan: 03
    provides: 19 pytest tests passing

provides:
  - BUILD_VERSION = "2026-06-09-lead-in-group-consumer" in app/main.py
  - /admin/grupo-membership/health with lookup_stats.lock_dict_size + phase=11-consumer
  - Submodule + parent repo pushed to GitHub (Easypanel webhook triggered)

affects: [/version endpoint, /admin/grupo-membership/health, Easypanel deploy pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "BUILD_VERSION slug convention: YYYY-MM-DD-feature-slug in app/main.py line 239"
    - "Healthcheck grows incrementally: Fase 10 skinny -> Fase 11 adds lookup_stats -> Fase 14 full alerting"
    - "Defensive try/except around _probe_locks import in healthcheck (edge import failure protection)"

key-files:
  created: []
  modified:
    - leadflow-backend/app/main.py
    - leadflow-backend/app/routers/admin.py

key-decisions:
  - "BUILD_VERSION date kept as 2026-06-09 (actual deploy day) matching convention from prior builds"
  - "lookup_stats nested under its own key (not flattened) to allow Fase 14 expansion without breaking clients"
  - "lock_dict_size initialized to 0 in dict before try/except so field always present even on import error"

requirements-completed: [MEMB-05, PROBE-COALESCE-01]

# Metrics
duration: ~15min
completed: 2026-06-09T23:15:33Z
---

# Phase 11 / Plan 04: Deploy — BUILD_VERSION bump + healthcheck extension Summary

**BUILD_VERSION bumped to `2026-06-09-lead-in-group-consumer` and `/admin/grupo-membership/health` extended with `lookup_stats.lock_dict_size` + `phase=11-consumer`. Submodule and parent repo pushed to GitHub. Easypanel deploy pipeline triggered. Awaiting Task 5 human prod-validation checkpoint.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-06-09
- **Tasks:** 4/4 executed (Task 5 is human-verify checkpoint — pending)
- **Files modified:** 2 (`app/main.py`, `app/routers/admin.py`)

## Accomplishments

- **Task 1** (commit 33ba1ef): `app/main.py` line 239 — `BUILD_VERSION` changed from `"2026-06-09-grupo-membership-v2-fundacao"` to `"2026-06-09-lead-in-group-consumer"`. `/version` endpoint will return new string after Easypanel redeploy.

- **Task 2** (commit 5d6ffd6): `app/routers/admin.py` — healthcheck function `grupo_membership_health` extended:
  - Added `lookup_stats: {"lock_dict_size": 0}` to `out` dict
  - Added `phase: "11-consumer"` (was `"10-fundacao"`)
  - Added `try/except` block importing `_probe_locks` from `grupo_membership` and setting `lock_dict_size = len(_probe_locks)`
  - All Fase 10 fields preserved intact (`total_rows`, `last_write_at`, `writes_by_source_24h`, `cache_stats`)

- **Task 3** (verification-only, no commit): Full pytest run — 46/52 passed. Pre-existing failures (`test_calendar_buffer.py` tzdata, `test_verificar_lead_no_grupo_phase3.py` httpx/idna) excluded. Phase 11 tests (7 decision + 3 coalesce + 9 migration grep) all green. 4 smoke static-analysis checks passed (BUILD_VERSION, grupo_membership symbols, grupo_fallback functions, healthcheck endpoint).

- **Task 4** (push): Submodule pushed to `origin/main` — 12 commits ahead cleared (`git log origin/main..HEAD` empty). SHA: `5d6ffd6f82d5b9c4325bd6717da7d2884c5a1f6e`.

## Verification

- `grep -n "lead-in-group-consumer" app/main.py` — line 239 matches
- `grep -n "11-consumer" app/routers/admin.py` — line 1163 matches
- `grep -n "lookup_stats" app/routers/admin.py` — lines 1160, 1173, 1175 match
- `grep -n "lock_dict_size" app/routers/admin.py` — lines 1161, 1173, 1175 match
- `grep -c "10-fundacao" app/routers/admin.py` == 0 (fully replaced)
- `pytest --ignore=test_calendar_buffer.py --ignore=test_verificar_lead_no_grupo_phase3.py` → 46 passed
- Smoke: "TODOS OS SMOKES PASSARAM"
- Submodule: `git log origin/main..HEAD` empty (up to date)

## Deviations from Plan

None — plan executed exactly as written. Task 1 and Task 2 were committed individually (per task-commit-protocol) rather than in a single combined commit as the plan's Task 4 suggested; this is correct per GSD execution rules and results in cleaner git history. The verification smoke used `ast.Constant.value` instead of `.s` (Python 3.14 compatibility) — cosmetic fix, no plan deviation.

## Pending: Task 5 — Human Prod Validation

Task 5 is `type="checkpoint:human-verify" gate="blocking"`. The following prod validation is awaiting the user:

1. **Redeploy on Easypanel** — GitHub push should have triggered Easypanel auto-build. Wait ~2-3 min.
2. **curl /version** — expect `"2026-06-09-lead-in-group-consumer"` in response
3. **curl /admin/grupo-membership/health** — expect `"phase": "11-consumer"` + `"lookup_stats": {"lock_dict_size": <int>}`
4. **SSH logs** — `docker logs 3e74f7da5a68 --tail 200 -f | grep -E "\[MEMB-LOOKUP\]|\[FALLBACK-1_1\]"` to confirm new consumer active in prod traffic

## Known Stubs

None — both modified files are production code with no placeholders.

## Threat Flags

None — changes are limited to a constant string bump (BUILD_VERSION) and adding an observability field to an existing internal admin endpoint. No new network endpoints, auth paths, or schema changes introduced.

## Self-Check: PASSED

- File `leadflow-backend/app/main.py` modified — VERIFIED (line 239 contains `lead-in-group-consumer`)
- File `leadflow-backend/app/routers/admin.py` modified — VERIFIED (lookup_stats + 11-consumer present)
- Commit 33ba1ef exists in submodule git log — FOUND
- Commit 5d6ffd6 exists in submodule git log — FOUND
- Submodule pushed to GitHub — CONFIRMED (`git log origin/main..HEAD` empty)
- pytest 46/52 — VERIFIED
- Smoke "TODOS OS SMOKES PASSARAM" — VERIFIED
