---
phase: 11
slug: lead-in-group-consumer-migrar-fallback-callers-coalescing-async
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-09
---

# Phase 11 — Validation Strategy

> Per-phase validation contract. Reconstructed from artifacts (State B). All phase
> requirements have automated, requirement-tagged pytest coverage that runs green.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (+ pytest-asyncio for coalescing tests) |
| **Config file** | `leadflow-backend/tests/conftest.py` (stubs `app.services.evolution` to dodge httpx→idna crash in the Py3.14 venv) |
| **Quick run command** | `cd leadflow-backend && python -m pytest tests/test_lead_in_group_decision.py tests/test_lead_in_group_coalesce.py tests/test_grupo_fallback_migration.py -q` |
| **Full suite command** | `cd leadflow-backend && python -m pytest -q` |
| **Estimated runtime** | ~0.4s (phase-11 subset) |

---

## Sampling Rate

- **After every task commit:** Run the quick command (3 phase-11 files)
- **After every plan wave:** Run the full suite
- **Before `/gsd-verify-work`:** Phase-11 subset must be green
- **Max feedback latency:** ~1 second

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 11-01 | 01 | 1 | MEMB-05 | T-11-01 | empresa_id-scoped membership lookup; orphan sentinel on instance_key mismatch | unit | `pytest tests/test_lead_in_group_decision.py` | ✅ | ✅ green (7) |
| 11-01 | 01 | 1 | PROBE-COALESCE-01 | — | N concurrent same-key jobs → 1 Evolution call | integration (asyncio.gather) | `pytest tests/test_lead_in_group_coalesce.py` | ✅ | ✅ green (3) |
| 11-02 | 02 | 2 | MEMB-05 | — | 7 callsites migrated; PROBE-BYPASS-01 + ALERTA-GRUPO-01 preserved literally | regression (CI grep) | `pytest tests/test_grupo_fallback_migration.py` | ✅ | ✅ green (9) |
| 11-03 | 03 | 3 | MEMB-05 / PROBE-COALESCE-01 | — | test suite authored | — | (the tests above) | ✅ | ✅ green |
| 11-04 | 04 | 4 | — | T-11-03 | BUILD_VERSION bump + healthcheck lookup_stats | manual (prod smoke) | curl /version + /admin/grupo-membership/health | n/a | see Manual-Only |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. The 19 tests (7 decision-tree + 3 coalescing + 9 migration CI) were authored in Plan 11-03 and run green.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `source=membership` hit under live prod traffic | MEMB-05 | Requires real group traffic + prod DB rows; can't be asserted in unit tests | SSH: `docker logs <container> --tail 200 -f \| grep "\[MEMB-LOOKUP\]"` — expect a `source=membership`/`cache` hit (tracked in 11-HUMAN-UAT.md) |
| Migration 005 grant persists across restart | MEMB-05 (infra) | DB-state persistence across container restart | After next Easypanel restart, `curl /admin/grupo-membership/health` returns no `*_erro` keys (tracked in 11-HUMAN-UAT.md) |
| Prod deploy smoke (BUILD_VERSION + healthcheck shape) | — | Live deployment | Validated at 11-04 checkpoint 2026-06-09 (✅ passed) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or are documented Manual-Only
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none — existing infra sufficient)
- [x] No watch-mode flags
- [x] Feedback latency < 2s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-09
