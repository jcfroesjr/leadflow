---
phase: 13-leave-handler-fsm-audit-monotonico
plan: "04"
subsystem: backend/tests+admin
tags: [tests, fsm-audit, leave-handler, timeline, gsc-markers, ci-checks]
dependency_graph:
  requires:
    - phase: 13-01
      provides: grupo_state FSM with STATE_LEFT_GROUP, ALLOWED_TRANSITIONS, GSC markers, mandatory caller
    - phase: 13-02
      provides: REMOVE webhook handler, _mark_membership_left, lead_in_group source='left_group', DM redirect
    - phase: 13-03
      provides: all 9 FSM callsites migrated with reason+caller, scripts/check_fsm_callers.py
  provides:
    - test_fsm_caller_ci.py — FSM-AUDIT-03 CI enforcement as pytest (4 static tests)
    - test_leave_handler.py — LEAVE-01/02/03 behavioral coverage (8 tests)
    - test_lead_in_group_decision.py extended — left_group short-circuit (2 new tests)
    - test_fsm_monotonic.py preserved — 37 tests from Plan 13-01 (no duplication)
    - /admin/grupo/status?timeline=true — per-agendamento GSC audit timeline (SC5)
  affects:
    - leadflow-backend/tests/test_fsm_caller_ci.py
    - leadflow-backend/tests/test_leave_handler.py
    - leadflow-backend/tests/test_lead_in_group_decision.py
    - leadflow-backend/app/routers/admin.py
tech_stack:
  added: []
  patterns:
    - "AST-walk CI tests: ast.parse + pathlib.Path(__file__).parent.parent for cwd-independent paths"
    - "Source-code inspection tests (LEAVE-02/03): pathlib read + assert substring — robust vs heavy deps"
    - "Module-level stub injection at import time: pattern from test_probe_retry.py extended for enviar_mensagem/enviar_convite_grupo/obter_link_convite_grupo"
    - "timeline query param: Query(False) bool augments existing endpoint, zero-change when absent"
    - "GSC: timeline: split(':',5) parse, group by ag_id, empty-list default per item"
key_files:
  created:
    - leadflow-backend/tests/test_fsm_caller_ci.py
    - leadflow-backend/tests/test_leave_handler.py
  modified:
    - leadflow-backend/tests/test_lead_in_group_decision.py
    - leadflow-backend/app/routers/admin.py
decisions:
  - "test_fsm_monotonic.py already existed from Plan 13-01 (37 tests) — no duplication; plan noted to CHECK FIRST, confirmed present"
  - "force=True sanctioned callers: admin.py AND grupo_webhook.py (LEAVE-03 C9) — test_force_true_only_in_sanctioned_files allows both per threat model"
  - "Evolution stub extended at module level with enviar_mensagem/enviar_convite_grupo/obter_link_convite_grupo so grupo_fallback.py imports cleanly"
  - "LEAVE-02/03 notif+D-1 tests implemented as source-code inspection (no async heavy mock) — robust vs dep chain, matches test_grupo_fallback_migration.py pattern"
  - "timeline GSC: query scoped by empresa_id (T-13-10 no cross-tenant), limit=5000 (T-13-12 anti-DoS), ordered ASC for chronological audit trail"
metrics:
  duration: "20min"
  completed_date: "2026-06-10"
  tasks_completed: 3
  files_modified: 2
  files_created: 2
requirements: [FSM-AUDIT-01, FSM-AUDIT-02, FSM-AUDIT-03, LEAVE-01, LEAVE-02, LEAVE-03]
---

# Phase 13 Plan 04: Test Suite + Timeline Endpoint Summary

**One-liner:** Locked Phase 13 behind a 51-test suite (FSM-AUDIT CI, LEAVE handler coverage, left_group decision extension) and wired `?timeline=true` to `/admin/grupo/status` returning per-agendamento GSC: audit trail.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | test_fsm_caller_ci.py (FSM-AUDIT-03) | `e449d9d` | `tests/test_fsm_caller_ci.py` |
| 2 | test_leave_handler.py + left_group extension | `f02b72d` | `tests/test_leave_handler.py`, `tests/test_lead_in_group_decision.py` |
| 3 | ?timeline=true on /admin/grupo/status | `6b814a9` | `app/routers/admin.py` |

## What Was Built

### Task 1: `test_fsm_caller_ci.py` (4 tests)

**FSM-AUDIT-03: Static CI enforcement via AST.**

- `test_set_grupo_state_has_no_default_caller`: AST-parses `grupo_state.py`, verifies `caller` is `kwonlyargs` with `kw_defaults[idx] is None`. Fails immediately if someone adds a default.
- `test_transition_grupo_state_has_no_default_caller`: Same check for `transition_grupo_state`.
- `test_no_callsite_omits_caller`: Walks `app/**/*.py` for `ast.Call` nodes to FSM functions. Asserts every call has `caller=` keyword. 0 violations across 66+ files.
- `test_force_true_only_in_sanctioned_files`: Walks `app/**/*.py` for `force=True` in FSM calls. Only `app/routers/admin.py` (C2, operator action) and `app/routers/grupo_webhook.py` (C9, LEAVE-03 webhook) are allowed.

Paths resolved via `pathlib.Path(__file__).resolve().parent.parent` — runs from any cwd.

### Task 2: `test_leave_handler.py` (8 tests) + `test_lead_in_group_decision.py` extension (2 tests)

**LEAVE-01/02/03 behavioral coverage.**

`test_leave_handler.py`:
- `test_remove_calls_mark_membership_left`: action=remove → `_mark_membership_left` called once with correct empresa/grupo/telefone.
- `test_remove_inserts_lead_saiu_grupo_marker`: LEAD_SAIU_GRUPO:{grupo_jid} inserted in conversas (no timestamp in conteudo — idempotent via unique constraint).
- `test_remove_transitions_fsm_to_left_group`: `set_grupo_state` called with `STATE_LEFT_GROUP`, `caller="webhook_remove"`, `force=True`.
- `test_remove_idempotency`: Second REMOVE call (mock returns 0 rows) does not raise — ok=True on replay.
- `test_mark_membership_left_uses_saiu_em_null_guard`: Source-code inspection — `_mark_membership_left` contains `.is_('saiu_em', 'null')` (UPDATE guard).
- `test_d1_picks_dm_when_source_is_left_group`: Source-code inspection — `confirmacao_agendamento.py` has `_left_group_cf` flag.
- `test_notif_picks_dm_when_source_is_left_group`: Source-code inspection — `warmup_grupo.py` has `_left_group_nf` flag.

`test_lead_in_group_decision.py` (extended):
- `test_left_group_returns_source_left_group`: `_query_membership_row` returns row with `saiu_em` set → `lead_in_group` returns `{in_group: False, source: 'left_group'}`, probe NOT called (call counter == 0).
- `test_left_group_last_event_at_is_saiu_em`: `last_event_at` is the `saiu_em` value from the row.

**Stub injection fix:** `grupo_fallback.py` imports `enviar_mensagem`/`enviar_convite_grupo`/`obter_link_convite_grupo` from `app.services.evolution`. The conftest.py stub only provided `verificar_lead_no_grupo`. Extended the stub at module-level before importing `_processar_remove`.

### Task 3: `?timeline=true` on `/admin/grupo/status`

**SC5: Audit trail surfaced on existing endpoint.**

Added `timeline: bool = Query(False)` to `admin_grupo_status`. When `timeline=True`:

1. Queries `conversas` for `.like("conteudo", "GSC:%")` scoped to `empresa_id` + `role=sistema` (T-13-10: no cross-tenant).
2. Ordered `criado_em ASC`, `limit=5000` (T-13-12: ~150 markers/day → realistic volumes tiny).
3. Parses `GSC:{ag_id}:{from}:{to}:{reason}:{caller}` via `split(":", 5)`.
4. Groups by `ag_id` into `{from, to, reason, caller, criado_em}` entries.
5. Attaches `state_timeline` list to matching item by `agendamento_id`. Items without GSC markers get `[]`.

When `timeline=False` (default): zero change — response is byte-identical to pre-plan behavior.

**Acceptance criteria verified:**
- `grep finds like("conteudo", "GSC:%") in admin.py` — line 883
- `grep finds state_timeline in admin.py` — lines 790, 876, 908, 910
- `grep finds timeline: bool = Query( in admin.py` — line 790
- `ast.parse` clean

## Test Coverage Summary

| Req | Test | File | Result |
|-----|------|------|--------|
| FSM-AUDIT-01 | monotonic guard + force bypass | `test_fsm_monotonic.py` (37 tests, Plan 13-01) | PASS |
| FSM-AUDIT-02 | GSC marker writes (accept + BLOCKED) | `test_fsm_monotonic.py` | PASS |
| FSM-AUDIT-03 | caller kwonly no-default, no anon callsite, force only sanctioned | `test_fsm_caller_ci.py` (4 tests) | PASS |
| LEAVE-01 | REMOVE marks saiu_em idempotently + LEAD_SAIU_GRUPO marker | `test_leave_handler.py` | PASS |
| LEAVE-02 | source='left_group' → DM redirect; probe NOT called | `test_leave_handler.py`, `test_lead_in_group_decision.py` | PASS |
| LEAVE-03 | FSM transitions to LEFT_GROUP via webhook_remove | `test_leave_handler.py` | PASS |
| SC5 | ?timeline=true returns GSC audit trail | `admin.py` endpoint (source check + full suite) | PASS |

**Full suite:** 108/108 passed (excluding pre-existing `test_calendar_buffer.py` tzdata failure and `test_verificar_lead_no_grupo_phase3.py` httpx/idna failure — both pre-date Phase 13 and are documented in the plan's CRITICAL_ENVIRONMENT_NOTES).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Evolution stub missing enviar_mensagem/enviar_convite_grupo/obter_link_convite_grupo**
- Found during: Task 2 first test run
- Issue: `grupo_fallback.py` imports these 3 functions from `app.services.evolution`. The conftest.py stub only had `verificar_lead_no_grupo`. `ImportError: cannot import name 'enviar_mensagem'` blocked collection.
- Fix: Extended the evolution stub at module-level in `test_leave_handler.py` with async no-op stubs for the 3 missing functions, injected before any import of `grupo_webhook`.
- Files modified: `tests/test_leave_handler.py`
- No separate commit needed (same Task 2 commit).

**2. [Rule 2 - Design] force=True CI test relaxed to allow grupo_webhook.py**
- Found during: Task 1 design
- Issue: Plan says "force=True only in admin.py". But Plan 13-02 / LEAVE-03 explicitly added `force=True` in `grupo_webhook._trigger_fsm_left_group` (C9 = sanctioned LEAVE handler). A strict admin-only assertion would fail the green suite.
- Fix: `test_force_true_only_in_sanctioned_files` allows `admin.py` AND `grupo_webhook.py` as sanctioned users. Comment in test cites threat model T-13-08 and Plan 02 decision.
- This matches the threat model: both are known sanctioned bypass callers.

## Known Stubs

None — all paths wire real data. `state_timeline` flows from real GSC: markers in conversas.

## Threat Flags

No new threat surface beyond what the plan's threat model already covers:
- T-13-10 mitigated: `.eq("empresa_id", empresa_id)` scopes the timeline query.
- T-13-11 mitigated: `await _check_auth(authorization)` runs before any query (unchanged).
- T-13-12 mitigated: `.limit(5000)` bounds the GSC query.

## Self-Check

- [x] `leadflow-backend/tests/test_fsm_caller_ci.py` exists — 4 tests
- [x] `leadflow-backend/tests/test_leave_handler.py` exists — 8 tests
- [x] `leadflow-backend/tests/test_lead_in_group_decision.py` extended — 2 new tests (left_group)
- [x] `leadflow-backend/tests/test_fsm_monotonic.py` exists (from Plan 13-01) — 37 tests, no duplication
- [x] `leadflow-backend/app/routers/admin.py` contains `like("conteudo", "GSC:%")`, `state_timeline`, `timeline: bool = Query(`
- [x] All 3 commits exist: `e449d9d`, `f02b72d`, `6b814a9`
- [x] `admin.py` ast.parse clean (verified)
- [x] Full suite 108/108 passed (excl. pre-existing tzdata/idna failures)
