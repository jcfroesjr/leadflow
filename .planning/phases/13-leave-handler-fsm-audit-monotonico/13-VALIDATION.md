---
phase: 13
slug: leave-handler-fsm-audit-monotonico
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-09
---

# Phase 13 — Validation Strategy

> Per-phase validation contract. All 6 requirements have automated, requirement-tagged
> pytest coverage that runs green (57 tests).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (+ pytest-asyncio) |
| **Config file** | `leadflow-backend/tests/conftest.py` (evolution stub) + module-level sys.modules stubs (apscheduler/supabase) |
| **Quick run command** | `cd leadflow-backend && python -m pytest tests/test_fsm_monotonic.py tests/test_fsm_caller_ci.py tests/test_leave_handler.py tests/test_lead_in_group_decision.py -q` |
| **Full suite command** | `cd leadflow-backend && python -m pytest -q` |
| **Estimated runtime** | ~5s (phase-13 subset) |

---

## Sampling Rate

- **After every task commit:** Run the quick command
- **After every plan wave:** Run the full suite
- **Before `/gsd-verify-work`:** Phase-13 subset must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 13-01 | 01 | 1 | FSM-AUDIT-01/02 | T-13-01/03 | monotonic guard (ATIVO→AGUARDANDO blocked w/o force); GSC audit on accept+blocked; mandatory caller | unit | `pytest tests/test_fsm_monotonic.py` | ✅ | ✅ green (37) |
| 13-02 | 02 | 2 | LEAVE-01/02/03 | T-13-04/05/06/07 | webhook REMOVE idempotent saiu_em + LEAD_SAIU_GRUPO + LEFT_GROUP; source='left_group'→DM | unit | `pytest tests/test_leave_handler.py tests/test_lead_in_group_decision.py` | ✅ | ✅ green (7+9) |
| 13-03 | 02→03 | 2 | FSM-AUDIT-03 | T-13-08/09 | every callsite passes caller (no "unknown"); force only admin+webhook | static/AST | `pytest tests/test_fsm_caller_ci.py` + `python scripts/check_fsm_callers.py` | ✅ | ✅ green (4) |
| 13-04 | 04 | 3 | all 6 | T-13-10/11/12 | timeline empresa-scoped + auth-gated + bounded | unit | (test files above) | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Test-to-requirement map (57 tests)

| Requirement | Tests |
|-------------|-------|
| FSM-AUDIT-01 (monotonic guard + force) | test_fsm_monotonic.py (subset of 37) |
| FSM-AUDIT-02 (GSC audit marker, mandatory caller) | test_fsm_monotonic.py |
| FSM-AUDIT-03 (caller CI, force-only-admin, no-anonymous) | test_fsm_caller_ci.py (4) + scripts/check_fsm_callers.py |
| LEAVE-01 (REMOVE → saiu_em + marker, idempotent) | test_leave_handler.py (subset of 7) |
| LEAVE-02 (D-1/notif DM redirect) | test_leave_handler.py (source checks) |
| LEAVE-03 (FSM → LEFT_GROUP) | test_leave_handler.py + test_fsm_monotonic.py |
| left_group consumer | test_lead_in_group_decision.py (+2 new of 9) |

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. The 57 tests (37 monotonic + 4 caller-CI + 7 leave + 9 decision) were authored across Plans 13-01 and 13-04 and run green.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real Evolution `action=remove` webhook fires the LEAVE path in prod | LEAVE-01 | Requires a real participant-leave event from Evolution | After deploy, watch logs for `[WEBHOOK-GRUPO] REMOVE` + `LEAD_SAIU_GRUPO` + a `GSC:...:LEFT_GROUP:...` marker |
| Audit timeline renders in the dashboard | FSM-AUDIT-02 | Requires the deployed frontend consuming `?timeline=true` | `curl /admin/grupo/status?empresa_id=...&timeline=true` returns `state_timeline` arrays |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or are documented Manual-Only
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none — existing infra sufficient)
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-10
