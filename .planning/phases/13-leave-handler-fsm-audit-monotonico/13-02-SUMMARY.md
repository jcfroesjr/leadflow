---
phase: 13-leave-handler-fsm-audit-monotonico
plan: 02
subsystem: grupo-membership
tags: [grupo, membership, leave-handler, fsm, webhook, evolution, confirmacao, warmup]

# Dependency graph
requires:
  - phase: 13-01
    provides: set_grupo_state with mandatory caller/reason, STATE_LEFT_GROUP constant, GSC audit markers, monotonic guard
  - phase: 12
    provides: _probe_retry_job, schedule_probe_retry, lead_in_group with schedule_retry_on_negative
  - phase: 11
    provides: lead_in_group central consumer, _query_membership_row, probe_cache

provides:
  - REMOVE webhook handler marks saiu_em idempotently via _mark_membership_left
  - LEAD_SAIU_GRUPO:{grupo_jid} conversas marker (no ts, idempotent via unique idx)
  - FSM transition to LEFT_GROUP (terminal) via set_grupo_state(force=True, caller="webhook_remove")
  - lead_in_group returns {in_group: False, source: 'left_group'} when row.saiu_em != null
  - _probe_retry_job skips TABLE_HIT caching when row has saiu_em set
  - D-1 confirmation routes to DM (not group) when source == 'left_group'
  - Pre-meeting notif routes to DM and skips retry enqueue when source == 'left_group'

affects:
  - 13-03 (FSM audit — LEFT_GROUP is now a reachable terminal state via webhook)
  - 13-04 (tests — test_leave_handler.py covers Tasks 1-3)
  - warmup_grupo notif destino logic
  - confirmacao_agendamento D-1 destino logic

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "saiu_em-aware SELECT: _query_membership_row no longer filters saiu_em IS NULL — caller (lead_in_group) distinguishes departed via row.get('saiu_em') is not None"
    - "source='left_group' sentinel: returned by lead_in_group before orphan/probe path when saiu_em set"
    - "belt-and-suspenders DM guard: _left_group_cf/_left_group_nf explicit flags even though in_group is already False for departed leads"
    - "allow_probe_fallback=False for left_group check in notif: table-only lookup, no extra HTTP probe"

key-files:
  created: []
  modified:
    - leadflow-backend/app/services/grupo_membership.py
    - leadflow-backend/app/routers/confirmacao_agendamento.py
    - leadflow-backend/app/routers/warmup_grupo.py
    - leadflow-backend/app/routers/grupo_webhook.py  # Task 1 (committed 62e61bb)

key-decisions:
  - "source='left_group' returned BEFORE orphan check in lead_in_group — no probe HTTP call for departed lead"
  - "_probe_retry_job TABLE_HIT guard: departed row (saiu_em set) encerra chain without caching True"
  - "warmup_grupo notif uses allow_probe_fallback=False for left_group check (table/cache only — no extra Evolution HTTP)"
  - "_left_group flags are belt-and-suspenders even though in_group=False already covers it — explicit log + guard"
  - "recuperar_probe_retries_pendentes: existing is not None skip now also covers departed rows correctly (don't retry a departed lead)"

patterns-established:
  - "Departed lead detection: _query_membership_row returns all rows; lead_in_group detects saiu_em != null early → source='left_group'"
  - "DM-redirect on left_group: all callers consuming lead_in_group result check source before routing to group"

requirements-completed: [LEAVE-01, LEAVE-02, LEAVE-03]

# Metrics
duration: 25min
completed: 2026-06-09
---

# Phase 13 Plan 02: Leave Handler FSM Audit — Read Semantics + DM Redirect Summary

**Membership lifecycle closed: departed leads surface as source='left_group', D-1 + notif redirect to DM instead of abandoned group.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-06-09T00:00:00Z
- **Completed:** 2026-06-09
- **Tasks:** 3/3 (Task 1 pre-committed as 62e61bb; Tasks 2-3 in this execution)
- **Files modified:** 4

## Accomplishments

- Task 1 (pre-committed 62e61bb): webhook REMOVE handler marks saiu_em idempotently, inserts LEAD_SAIU_GRUPO:{grupo_jid} marker (no ts), transitions FSM to LEFT_GROUP via set_grupo_state(force=True, caller="webhook_remove")
- Task 2: _query_membership_row no longer filters saiu_em IS NULL; lead_in_group detects departed row before orphan/probe path and returns source='left_group'; _probe_retry_job TABLE_HIT guard skips caching True for departed leads
- Task 3: confirmacao_agendamento D-1 and warmup_grupo pre-meeting notif both check source='left_group' and force DM destination; warmup also suppresses probe retry enqueue for departed leads

## Task Commits

Each task was committed atomically inside the leadflow-backend submodule:

1. **Task 1: Webhook REMOVE branch + _mark_membership_left + FSM LEFT_GROUP** - `62e61bb` (feat) — pre-committed before this execution
2. **Task 2: saiu_em-aware read semantics in grupo_membership** - `3fedd90` (feat)
3. **Task 3: force DM when source=left_group in D-1 + pre-meeting notif** - `a8738b0` (feat)

## Files Created/Modified

- `leadflow-backend/app/routers/grupo_webhook.py` — Task 1: action=remove branch, _processar_remove, _salvar_lead_saiu_marker, _trigger_fsm_left_group (commit 62e61bb)
- `leadflow-backend/app/services/grupo_membership.py` — Task 2: dropped saiu_em IS NULL from SELECT, added left_group branch in lead_in_group, added saiu_em guard in _probe_retry_job, comment in recuperar_probe_retries_pendentes
- `leadflow-backend/app/routers/confirmacao_agendamento.py` — Task 3: _left_group_cf detection + not _left_group_cf in _enviar_no_grupo guard
- `leadflow-backend/app/routers/warmup_grupo.py` — Task 3: _left_group_nf via lead_in_group(allow_probe_fallback=False), not _left_group_nf in destino guard and retry enqueue guard

## Deviations from Plan

None — plan executed exactly as written. All action blocks in Tasks 2-3 followed precisely. The `recuperar_probe_retries_pendentes` comment (plan noted "leave as-is but add comment") was added as directed.

## Known Stubs

None — all paths wire real data. source='left_group' flows from DB saiu_em through lead_in_group to both callers.

## Threat Flags

No new threat surface introduced in Tasks 2-3. Task 1 (62e61bb) threat surface covered in plan's threat model (T-13-04 through T-13-07): forged REMOVE, messageTimestamp tampering, replay, bare @lid remove — all documented with dispositions.

## Self-Check: PASSED

- `app/services/grupo_membership.py` — exists, committed 3fedd90
- `app/routers/confirmacao_agendamento.py` — exists, committed a8738b0
- `app/routers/warmup_grupo.py` — exists, committed a8738b0
- All 4 files pass `ast.parse` (verified)
- `source='left_group'` in grupo_membership.py — verified (line 251)
- `_left_group_cf` in confirmacao_agendamento.py — verified (lines 308, 323)
- `_left_group_nf` in warmup_grupo.py — verified (lines 815, 826, 841, 855)
- `allow_probe_fallback=False` in warmup_grupo.py — verified (line 824)
- `.is_('saiu_em', 'null')` only in _mark_membership_left UPDATE (correct), not in _query_membership_row SELECT — verified
