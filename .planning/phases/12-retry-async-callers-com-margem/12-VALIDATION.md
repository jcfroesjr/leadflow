---
phase: 12
slug: retry-async-callers-com-margem
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-09
---

# Phase 12 — Validation Strategy

> Per-phase validation contract. Both requirements have automated, requirement-tagged
> pytest coverage that runs green (12/12).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (+ pytest-asyncio for async retry-job tests) |
| **Config file** | `leadflow-backend/tests/conftest.py` (evolution stub) + module-level `sys.modules` stubs for `app.scheduler` / `app.db.client` (apscheduler not installed in the Py3.14 venv; mock-scheduler pattern) |
| **Quick run command** | `cd leadflow-backend && python -m pytest tests/test_probe_retry.py -q` |
| **Full suite command** | `cd leadflow-backend && python -m pytest -q` |
| **Estimated runtime** | ~0.1s (phase-12 subset) |

---

## Sampling Rate

- **After every task commit:** Run the quick command (`test_probe_retry.py`)
- **After every plan wave:** Run the full suite
- **Before `/gsd-verify-work`:** Phase-12 subset must be green
- **Max feedback latency:** ~1 second

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 12-01 | 01 | 1 | PROBE-RETRY-01 | T-12-01/02/03/04 | deterministic+empresa-scoped job id; max_age=600 drops zombie; table-first short-circuit; activation only on `is False` | unit + async | `pytest tests/test_probe_retry.py` | ✅ | ✅ green |
| 12-02 | 02 | 2 | PROBE-RETRY-02 | T-12-05/06/07 | D-1 + warmup callers activate retry; aquec stays sync; recovery bounded (limit 200 + `gte(now)`) | unit (source inspection) | `pytest tests/test_probe_retry.py::test_confirmacao_caller_activates_retry tests/test_probe_retry.py::test_aquec_stays_sync` | ✅ | ✅ green |
| 12-03 | 03 | 3 | PROBE-RETRY-01, PROBE-RETRY-02 | T-12-08/09 | test suite captures real args, tests behavior not just calls | meta/test | `pytest tests/test_probe_retry.py -q` | ✅ | ✅ green (12) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Test-to-criterion map (12 tests)

| Success Criterion | Tests |
|-------------------|-------|
| SC1 deterministic scheduling + idempotent id | `test_schedule_creates_job`, `test_idempotent_job_id` |
| SC2 max_age guard (Valquiria) | `test_max_age_guard_expired`, `test_max_age_guard_valid` |
| SC3 table-first short-circuit (Rosania) | `test_table_hit_skips_probe`, `test_rosania_sequence` |
| SC1 attempts/activation | `test_max_attempts_no_reschedule`, `test_stub_false_no_retry`, `test_none_probe_no_retry`, `test_retry_job_none_does_not_reenqueue` (CR-01 regression) |
| SC4 callers (D-1 retry / aquec sync) | `test_confirmacao_caller_activates_retry`, `test_aquec_stays_sync` |

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. The 12 tests were authored in Plan 12-03 (+1 CR-01 regression added during code-review fix) and run green.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Retry chain fires in prod under real timing (30s/2min/5min) | PROBE-RETRY-01 | Real APScheduler + real Evolution timing; unit tests mock the scheduler | After deploy, watch `[PROBE-RETRY]` log markers (`scheduled`/`JOB_EXPIRED`/`TABLE_HIT`/`PROBE_HIT`/`MAX_ATTEMPTS`) under live group traffic |
| Recovery re-enqueues correctly on restart | PROBE-RETRY-02 | Requires a real container restart with pending appointments | After next Easypanel restart, watch `[PROBE-RETRY-RECOVERY] re-enfileirados=N` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or are documented Manual-Only
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none — existing infra sufficient)
- [x] No watch-mode flags
- [x] Feedback latency < 2s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-09
