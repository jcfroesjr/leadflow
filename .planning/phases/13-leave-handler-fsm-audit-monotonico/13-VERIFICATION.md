---
phase: 13-leave-handler-fsm-audit-monotonico
verified: 2026-06-10T03:25:00Z
status: passed
score: 6/6
overrides_applied: 0
---

# Phase 13: Leave Handler + FSM Audit Monotônico — Verification Report

**Phase Goal:** Fechar o ciclo de vida da membership. Webhook REMOVE marca saiu_em + marker LEAD_SAIU_GRUPO. Notif/D-1 detectam saiu_em != null e redirecionam pro DM. FSM transições monotônicas com `caller` obrigatório sem default; toda transição grava audit GSC:{ag_id}:{from}:{to}:{reason}:{caller}. Novo estado terminal LEFT_GROUP.
**Verified:** 2026-06-10T03:25:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Webhook GROUP_PARTICIPANTS_UPDATE action=remove marks grupo_membership.saiu_em + inserts marker LEAD_SAIU_GRUPO:{grupo_jid} idempotent | VERIFIED | `_processar_remove` in grupo_webhook.py calls `_mark_membership_left` (UPDATE WHERE saiu_em IS NULL) and `_salvar_lead_saiu_marker` inserting `LEAD_SAIU_GRUPO:{grupo_jid}` (no ts); unique constraint handles replay |
| 2 | Notif pre-reuniao + D-1 detect saiu_em != null via lead_in_group() (source='left_group') and send via DM | VERIFIED | `confirmacao_agendamento.py` lines 308/323: `_left_group_cf` flag + `not _left_group_cf` in `_enviar_no_grupo`; `warmup_grupo.py` lines 815-855: `_left_group_nf` via `lead_in_group(allow_probe_fallback=False)` + `not _left_group_nf` in destino guard and retry enqueue guard |
| 3 | FSM ATIVO->AGUARDANDO BLOCKED without force=True; blocked attempt writes GSC ...:BLOCKED:... audit but no state change | VERIFIED | `ALLOWED_TRANSITIONS[STATE_ATIVO] = {STATE_LEFT_GROUP}` — only LEFT_GROUP allowed from ATIVO without force; `set_grupo_state` calls `_insert_audit_marker(..., reason=f"BLOCKED:{reason}", caller=caller)` and returns False without writing legacy marker; confirmed by FSM assertions + 37 tests |
| 4 | set_grupo_state() requires mandatory `caller` (no default); CI check ensures no caller passes "unknown" or omits | VERIFIED | `set_grupo_state(..., *, reason: str, caller: str, force: bool = False)` — kwonly with no default; `scripts/check_fsm_callers.py` scanned 66 files, 0 violations; `test_fsm_caller_ci.py` 4 AST-based tests enforce this structurally |
| 5 | Every FSM transition writes GSC:{ag_id}:{from}:{to}:{reason}:{caller} marker (prefix GSC:); /admin/grupo/status?timeline=true exposes auditable timeline | VERIFIED | `_insert_audit_marker` in grupo_state.py writes `f"GSC:{agendamento_id}:{from_state}:{to_state}:{reason}:{caller}"`; admin.py line 790 adds `timeline: bool = Query(False)`, line 883 queries `.like("conteudo", "GSC:%")`, attaches `state_timeline` list per agendamento_id |
| 6 | Lead who left -> FSM LEFT_GROUP (new terminal state); LEFT_GROUP distinguished from normal timeout in GSC marker | VERIFIED | `STATE_LEFT_GROUP = "LEFT_GROUP"` in grupo_state.py; `ALLOWED_TRANSITIONS[STATE_LEFT_GROUP] = set()` (terminal); `_trigger_fsm_left_group` calls `set_grupo_state(..., STATE_LEFT_GROUP, reason="lead_saiu_grupo", caller="webhook_remove", force=True)`; GSC marker contains `to_state=LEFT_GROUP` + `reason=lead_saiu_grupo` distinguishing it from `reason=timeout_30min` |

**Score:** 6/6 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `leadflow-backend/app/services/grupo_state.py` | Monotonic FSM with mandatory caller + GSC audit + LEFT_GROUP terminal state | VERIFIED | Contains `STATE_LEFT_GROUP`, `ALLOWED_TRANSITIONS`, `_is_transition_allowed`, `_insert_audit_marker`, new `set_grupo_state`/`transition_grupo_state` signatures |
| `leadflow-backend/app/routers/grupo_webhook.py` | action=remove branch: mark saiu_em + LEAD_SAIU_GRUPO marker + FSM LEFT_GROUP | VERIFIED | `_processar_remove`, `_salvar_lead_saiu_marker`, `_trigger_fsm_left_group` all present and wired |
| `leadflow-backend/app/services/grupo_membership.py` | saiu_em-aware _query_membership_row + lead_in_group left_group branch + _probe_retry_job guard + _mark_membership_left helper | VERIFIED | No `.is_('saiu_em', 'null')` in SELECT; `saiu_em` check at line 248 returns `source='left_group'`; `_probe_retry_job` guards `saiu_em` before caching True; `_mark_membership_left` exists with UPDATE WHERE saiu_em IS NULL |
| `leadflow-backend/app/services/grupo_fallback.py` | 4 migrated callsites (C5, C6, C7/T1, C8/T2) with reason+caller | VERIFIED | All 4 caller values present: `fallback_retroativo_ativo`, `fallback_criar_grupo`, `fallback_timeout_30min`, `fallback_lead_entrou` |
| `leadflow-backend/app/routers/admin.py` | C2 promover_ativo migrated + ?timeline=true returning GSC: timeline | VERIFIED | `caller="admin_promover_ativo"`, `force=True` at line 963; `timeline: bool = Query(False)` at line 790; `like("conteudo", "GSC:%")` at line 883; `state_timeline` attached per item |
| `leadflow-backend/app/routers/leads.py` | C3 + C4 migrated | VERIFIED | `caller="leads_reuso_grupo"` at line 138; `caller="leads_promote_admin"` at line 258 |
| `leadflow-backend/scripts/check_fsm_callers.py` | AST sweep asserting no anonymous callsite | VERIFIED | Exists, exits 0, scanned 66 files, 0 violations (confirmed by live run) |
| `leadflow-backend/tests/test_fsm_monotonic.py` | Monotonic FSM + audit marker tests | VERIFIED | 37 tests covering STATE constants, ALLOWED_TRANSITIONS, signature enforcement, accepted/blocked transitions, GSC marker format |
| `leadflow-backend/tests/test_fsm_caller_ci.py` | AST-based CI grep test for mandatory caller | VERIFIED | 4 tests: kwonly no-default (set + transition), no anonymous callsite, force=True only in sanctioned files |
| `leadflow-backend/tests/test_leave_handler.py` | LEAVE-01/02/03 coverage | VERIFIED | 8 tests: REMOVE marks saiu_em, LEAD_SAIU_GRUPO marker, FSM LEFT_GROUP, idempotency, saiu_em null guard, D-1 DM redirect, notif DM redirect |
| `leadflow-backend/tests/test_lead_in_group_decision.py` | Extended with left_group case | VERIFIED | 2 new tests: `test_left_group_returns_source_left_group` (probe NOT called), `test_left_group_last_event_at_is_saiu_em` |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `grupo_webhook.py action=remove` | `grupo_membership.saiu_em (UPDATE)` | `_mark_membership_left` | WIRED | Called in `_processar_remove` for each `tel in telefones_saiu`; UPDATE WHERE saiu_em IS NULL |
| `grupo_webhook.py action=remove` | `conversas LEAD_SAIU_GRUPO marker` | `_salvar_lead_saiu_marker` | WIRED | Called in `_processar_remove` for each `tel in telefones_saiu`; conteudo = `f"LEAD_SAIU_GRUPO:{grupo_jid}"` (no ts) |
| `grupo_webhook.py action=remove` | `FSM LEFT_GROUP via set_grupo_state` | `_trigger_fsm_left_group` | WIRED | Calls `set_grupo_state(..., STATE_LEFT_GROUP, reason="lead_saiu_grupo", caller="webhook_remove", force=True)` |
| `lead_in_group` | `callers (D-1, notif)` | `source='left_group' verdict` | WIRED | confirmacao_agendamento.py checks `_result_cf.get("source") == "left_group"`; warmup_grupo.py checks `_r_nf.get("source") == "left_group"` |
| `confirmacao_agendamento + warmup_grupo` | `DM destination` | `source check forces telefone destino` | WIRED | `_enviar_no_grupo = bool(...and not _left_group_cf)`; `if _in_group_real_nf and ... and not _left_group_nf:` |
| `set_grupo_state` | `conversas (GSC: marker)` | `_insert_audit_marker on every call` | WIRED | Called on both accepted AND blocked transitions; format `GSC:{agendamento_id}:{from_state}:{to_state}:{reason}:{caller}` |
| `/admin/grupo/status` | `conversas GSC: markers` | `timeline query param` | WIRED | `timeline: bool = Query(False)` at line 790; `.like("conteudo", "GSC:")` at line 883; `state_timeline` attached to each item |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `grupo_state.py set_grupo_state` | `current` (from get_grupo_state) | `conversas` DB query `.like("GRUPO_STATE:{ag_id}:%)` | Yes — reads real DB rows | FLOWING |
| `grupo_membership.py lead_in_group` | `row` (from _query_membership_row) | `grupo_membership` DB table | Yes — SELECT with saiu_em included | FLOWING |
| `grupo_webhook.py _processar_remove` | `_evento_ts` | `data.messageTimestamp` via `parse_evolution_timestamp` | Yes — fallback to utcnow() | FLOWING |
| `admin.py ?timeline=true` | `gsc_q.data` | `conversas` DB `.like("GSC:%")` | Yes — real DB query scoped by empresa_id | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| FSM transition assertions | `python -c "...assert not _is_transition_allowed(STATE_ATIVO, STATE_AGUARDANDO)..."` | `FSM assertions OK` | PASS |
| FSM caller sweep | `python scripts/check_fsm_callers.py` | `FSM-AUDIT-03 PASSED — 66 files scanned, 0 violations.` | PASS |
| Phase-13 test suite | `pytest tests/test_fsm_monotonic.py tests/test_fsm_caller_ci.py tests/test_leave_handler.py tests/test_lead_in_group_decision.py -q` | `57 passed, 27 warnings in 4.95s` | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| LEAVE-01 | 13-02, 13-04 | Webhook REMOVE marks saiu_em + LEAD_SAIU_GRUPO marker (idempotent) | SATISFIED | `_mark_membership_left` with `WHERE saiu_em IS NULL`; `_salvar_lead_saiu_marker` inserting `LEAD_SAIU_GRUPO:{grupo_jid}` (no ts); 3 tests in test_leave_handler.py |
| LEAVE-02 | 13-02, 13-04 | Notif pre-reuniao + D-1 detect saiu_em != null via lead_in_group(); redirect to DM | SATISFIED | `_left_group_cf` in confirmacao_agendamento.py; `_left_group_nf` in warmup_grupo.py; `source='left_group'` in lead_in_group; test_leave_handler.py test_d1_picks_dm + test_notif_picks_dm; test_lead_in_group_decision.py 2 new left_group tests |
| LEAVE-03 | 13-02, 13-04 | FSM transitions to LEFT_GROUP (new terminal state); GSC marker distinguishes from timeout | SATISFIED | `STATE_LEFT_GROUP = "LEFT_GROUP"`, `ALLOWED_TRANSITIONS[STATE_LEFT_GROUP] = set()`; `_trigger_fsm_left_group` with `reason="lead_saiu_grupo"` distinct from `reason="timeout_30min"`; test_leave_handler.py test_remove_transitions_fsm_to_left_group |
| FSM-AUDIT-01 | 13-01, 13-04 | ATIVO->AGUARDANDO blocked without force=True | SATISFIED | `ALLOWED_TRANSITIONS[STATE_ATIVO] = {STATE_LEFT_GROUP}` only; `_is_transition_allowed(ATIVO, AGUARDANDO)` returns False; blocked path writes GSC:...:BLOCKED:... and returns False; 37 tests in test_fsm_monotonic.py |
| FSM-AUDIT-02 | 13-01, 13-04 | Every transition writes GSC:{ag_id}:{from}:{to}:{reason}:{caller}; caller mandatory no default | SATISFIED | `_insert_audit_marker` called on every accepted AND blocked transition; `set_grupo_state(..., *, reason: str, caller: str, ...)` — kwonly no default; test_fsm_caller_ci.py test_set_grupo_state_has_no_default_caller |
| FSM-AUDIT-03 | 13-03, 13-04 | CI check: no callsite omits caller; none passes "unknown" | SATISFIED | `scripts/check_fsm_callers.py` 66 files, 0 violations (live run confirmed); test_fsm_caller_ci.py test_no_callsite_omits_caller + test_force_true_only_in_sanctioned_files |

All 6 requirement IDs from the plans are accounted for. No orphaned requirements found for Phase 13 in REQUIREMENTS.md — all 6 show `[x]` (completed) in the Active section.

Note: The traceability table in REQUIREMENTS.md still shows these as "Pending" in the v2.2 table (bottom section) because that table was pre-filled at planning time and not updated post-execution. The inline `[x]` markers in the Cat 3/4 sections are the authoritative status and correctly reflect completion.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `app/services/grupo_state.py` | 102 | `datetime.utcnow()` deprecated in Python 3.12+ | Info | DeprecationWarning only; no functional impact in Python 3.11; pre-existing pattern throughout codebase |
| `app/routers/grupo_webhook.py` | 305 | `datetime.utcnow()` deprecated | Info | Same as above |

No blockers or warnings found. No TODO/FIXME/placeholder comments in phase-13 files. No empty implementations or hardcoded empty returns. No `return null` / `return {}` stubs. The `utcnow()` deprecations are pre-existing project-wide patterns not introduced by this phase.

---

## Human Verification Required

None — all success criteria are verifiable programmatically. The `?timeline=true` endpoint behavior (correct JSON shape, grouping by agendamento_id) is covered by source-code inspection and the full test suite.

---

## Gaps Summary

No gaps. All 6 success criteria are verified in code. The full 57-test suite passes. The FSM caller sweep finds 0 violations across 66 files.

---

_Verified: 2026-06-10T03:25:00Z_
_Verifier: Claude (gsd-verifier)_
