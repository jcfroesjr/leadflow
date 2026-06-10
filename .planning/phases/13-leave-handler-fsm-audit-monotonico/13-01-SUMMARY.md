---
phase: 13-leave-handler-fsm-audit-monotonico
plan: "01"
subsystem: backend/grupo_state
tags: [fsm, audit, monotonic, grupo, left_group, gsc_marker]
dependency_graph:
  requires: []
  provides: [STATE_LEFT_GROUP, ALLOWED_TRANSITIONS, GSC_audit_markers, monotonic_guard]
  affects:
    - leadflow-backend/app/services/grupo_state.py
    - leadflow-backend/tests/test_fsm_monotonic.py
tech_stack:
  added: []
  patterns:
    - "GSC:{ag_id}:{from}:{to}:{reason}:{caller} audit marker in conversas"
    - "ALLOWED_TRANSITIONS dict for monotonic FSM guard"
    - "force=True bypass for admin paths only"
key_files:
  modified:
    - leadflow-backend/app/services/grupo_state.py
  created:
    - leadflow-backend/tests/test_fsm_monotonic.py
decisions:
  - "GSC: prefix (not GRUPO_STATE_CHANGE:) avoids collision with get_grupo_state .like('GRUPO_STATE:%') query"
  - "LEFT_GROUP is a new terminal FSM state — not FALLBACK_1_1 — per SC6 and locked decision D-1"
  - "set_grupo_state writes BOTH legacy GRUPO_STATE: marker (read path) and GSC: audit marker (audit path)"
  - "reason/caller are kwonly with no default — TypeError at callsite if omitted (intentional; Plan 03 migrates 9 callsites)"
  - "force=True bypasses monotonic guard — only admin endpoint should pass it"
metrics:
  duration: "7min"
  completed_date: "2026-06-10"
  tasks_completed: 2
  files_modified: 1
  files_created: 1
requirements: [FSM-AUDIT-01, FSM-AUDIT-02]
---

# Phase 13 Plan 01: FSM Monotonic Guard + GSC Audit Markers Summary

**One-liner:** Hardened `grupo_state.py` into a strictly monotonic FSM with mandatory `caller` audit trail: `LEFT_GROUP` terminal state, `ALLOWED_TRANSITIONS` table, `GSC:` audit markers on every accepted/blocked transition, and kwonly `reason`/`caller` with no default so callers that omit them fail immediately at `TypeError`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| TDD-RED | Failing tests for FSM monotonic guard | `5b9f304` | `tests/test_fsm_monotonic.py` (37 tests) |
| 1 | Add LEFT_GROUP state + ALLOWED_TRANSITIONS table | `afaab99` | `app/services/grupo_state.py` |
| 2 | Mandatory caller + GSC audit marker + monotonic guard | `880e9d2` | `app/services/grupo_state.py` |
| fix | Fix test mock chain + missing import (Rule 1) | `2d25c06` | `tests/test_fsm_monotonic.py` |

## What Was Built

### `grupo_state.py` changes

**New constants:**
- `STATE_LEFT_GROUP = "LEFT_GROUP"` — terminal state for leads who leave the group
- `VALID_STATES` expanded to include `STATE_LEFT_GROUP`
- `ALLOWED_TRANSITIONS: dict` — monotonic transition table; `LEFT_GROUP -> set()` (terminal)

**New helper:**
- `_is_transition_allowed(from_state, to_state) -> bool` — checks `ALLOWED_TRANSITIONS`
- `_insert_audit_marker(...)` — inserts `GSC:{ag_id}:{from}:{to}:{reason}:{caller}` in `conversas`

**Rewritten `set_grupo_state` signature:**
```python
set_grupo_state(sb, empresa_id, telefone, agendamento_id, state,
                *, reason: str, caller: str, force: bool = False) -> bool
```
- Accepted transition: writes legacy `GRUPO_STATE:{ag_id}:{state}` + `GSC:` audit marker, returns True
- Blocked transition (not force): writes `GSC:...:BLOCKED:{reason}:{caller}`, returns False, no legacy write
- `force=True` bypasses monotonic guard (admin path only)

**Rewritten `transition_grupo_state` signature:**
```python
transition_grupo_state(sb, empresa_id, telefone, agendamento_id,
                       from_states, to_state,
                       *, reason: str, caller: str, force: bool = False) -> bool
```
- Writes `GSC:...:BLOCKED:...` on `from_states` mismatch (before returning False)
- Delegates to `set_grupo_state` passing `reason/caller/force`

**`get_grupo_state` unchanged** — still reads `GRUPO_STATE:{ag_id}:{state}` via `.like("GRUPO_STATE:{ag_id}:%)`. The `GSC:` prefix does not collide with this query.

## Test Coverage

37 tests in `tests/test_fsm_monotonic.py`:
- `TestStateConstants` — STATE_LEFT_GROUP, VALID_STATES, ALLOWED_TRANSITIONS
- `TestIsTransitionAllowed` — 13 transition assertions (allowed + blocked)
- `TestSetGrupoStateSignature` — caller/reason kwonly no-default; force default=False
- `TestSetGrupoStateAcceptedTransition` — returns True, writes legacy + GSC markers, format check
- `TestSetGrupoStateBlockedTransition` — returns False, writes BLOCKED marker, no legacy write; force bypass
- `TestTransitionGrupoState` — passes reason/caller, BLOCKED on from_states mismatch, kwonly sig
- `TestGetGrupoStateUnchanged` — reads legacy GRUPO_STATE:, handles GSC: gracefully (returns None)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Missing STATE_AGUARDANDO import in test method**
- Found during: Task 2 test run
- Issue: `test_transition_blocked_on_from_mismatch_returns_false` used `STATE_AGUARDANDO` name without importing it in that method (NameError)
- Fix: Added `STATE_AGUARDANDO` to the import in that test method
- Files modified: `tests/test_fsm_monotonic.py`
- Commit: `2d25c06`

**2. [Rule 1 - Bug] Wrong mock chain depth for get_grupo_state**
- Found during: Task 2 test run
- Issue: Mock chain had 3 `.eq()` calls but `get_grupo_state` only has 2 (`.eq("empresa_id",...).eq("role","sistema")`). The extra `.eq` in the chain caused `execute()` to return a fresh MagicMock instead of the seeded data, so `get_grupo_state` returned None.
- Fix: Corrected mock chain to `.select().eq().eq().like().order().limit().execute()`
- Files modified: `tests/test_fsm_monotonic.py`
- Commit: `2d25c06`

## Known Stubs

None — implementation is complete. The 9 callsites that now call the old signature without `reason`/`caller` will raise `TypeError` at runtime until Plan 03 (Wave 2) migrates them. This is intentional by design (callers that omit them fail loudly).

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The `GSC:` marker writes to the existing `conversas` table (same path as `GRUPO_STATE:` markers). No new threat surface beyond what the plan's threat model already covers.

## Self-Check

- [x] `leadflow-backend/app/services/grupo_state.py` exists and contains `STATE_LEFT_GROUP`, `ALLOWED_TRANSITIONS`, `_is_transition_allowed`, `_insert_audit_marker`, new `set_grupo_state`, new `transition_grupo_state`
- [x] `leadflow-backend/tests/test_fsm_monotonic.py` exists with 37 tests all passing
- [x] All 4 submodule commits exist: `5b9f304`, `afaab99`, `880e9d2`, `2d25c06`
- [x] `get_grupo_state` unchanged — still reads `GRUPO_STATE:` legacy marker
- [x] GSC: prefix confirmed distinct from `GRUPO_STATE:` (no query collision)
