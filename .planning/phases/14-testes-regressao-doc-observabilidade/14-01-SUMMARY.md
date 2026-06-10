---
phase: 14-testes-regressao-doc-observabilidade
plan: "01"
subsystem: backend-tests
tags: [regression, pytest, observability, v2.2, webhook-first]
dependency_graph:
  requires:
    - "13-04 (FSM audit GSC: marker in grupo_state.py)"
    - "12-01 (probe retry motor _probe_retry_job + schedule_probe_retry)"
    - "11-01 (lead_in_group decision tree + _query_membership_row)"
    - "10-01 (upsert_grupo_membership + [MEMB-WRITE] markers)"
  provides:
    - "TEST-V2-G1..G4: case-named regression guards (4 passing tests)"
    - "TEST-V2-G5: blocked-pending-data stub (1 skipped test)"
    - "OBS-V2-G1: source-audit test locking 4 log marker families against regression"
  affects:
    - "leadflow-backend/tests/ (new file: test_v2_regression.py)"
tech_stack:
  added: []
  patterns:
    - "pytest.mark.asyncio for async unit tests"
    - "sys.modules stub injection for APScheduler + supabase-py (reused from test_probe_retry.py)"
    - "pathlib.read_text source-inspection for marker audit (reused from test_probe_retry.py PROBE-RETRY-02)"
    - "monkeypatch on 'app.services.evolution.verificar_lead_no_grupo' (correct patch target — local import in lead_in_group)"
key_files:
  created:
    - "leadflow-backend/tests/test_v2_regression.py"
  modified: []
decisions:
  - "test_v2_g4 uses @pytest.mark.asyncio + async def (not asyncio.get_event_loop().run_until_complete) — consistent with rest of suite"
  - "TEST-V2-G5 is pytest.mark.skip with explicit reason string (never assert True) — stays visible in CI output"
  - "OBS-V2-G1 audit maps [GRUPO-STATE-CHANGE] criterion to 'GSC:' prefix — Phase 13 naming decision documented in test docstring"
  - "utcnow() DeprecationWarnings left as-is — pre-existing pattern throughout codebase including production code"
metrics:
  duration: "~3 minutes"
  completed: "2026-06-10T04:23:31Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 1
  files_modified: 0
  commits:
    - hash: "bfa18ae"
      repo: "leadflow-backend"
      message: "test(14-01): add v2.2 regression suite (TEST-V2-G1..G5 + OBS-V2-G1)"
requirements: [TEST-V2-G1, TEST-V2-G2, TEST-V2-G3, TEST-V2-G4, TEST-V2-G5, OBS-V2-G1]
---

# Phase 14 Plan 01: V2.2 Regression Suite Summary

**One-liner:** Pytest case-named regression suite locking 5 motivating v2.2 cases (4 pass + 1 skip) + source-audit test for 4 structured log marker families.

## What Was Built

`leadflow-backend/tests/test_v2_regression.py` — 317 lines, 6 tests:

| Test | Case | Mechanism Verified | Result |
|------|------|--------------------|--------|
| `test_v2_g1_ana_carla_path3_create_group` | Ana Carla 08/06 | Path 3 createGroup row → source='membership', probe count=0 | PASS |
| `test_v2_g2_rosania_table_hit_at_138s` | Rosania 08/06 | TABLE_HIT in _probe_retry_job at T+138s, probe count=0 | PASS |
| `test_v2_g3_fernanda_orphan_instance_key` | Fernanda 07/06 | instance_key mismatch → source='orphan', in_group=False, probe count=0 | PASS |
| `test_v2_g4_valquiria_max_age_discard` | Valquiria 06/06 | enqueued_at=47h ago, max_age=600 → discard, probe count=0 | PASS |
| `test_v2_g5_lead_553891500357` | 553891500357 09/06 | Stub pending incident trace | SKIP |
| `test_v2_obs_g1_log_markers_present` | OBS-V2-G1 | [MEMB-WRITE], [MEMB-LOOKUP], [PROBE-RETRY] in grupo_membership.py; GSC: in grupo_state.py | PASS |

**Final pytest output:** `5 passed, 1 skipped in 0.09s`

## Deviations from Plan

None — plan executed exactly as written.

The skeleton from 14-RESEARCH.md was used as base. One adjustment from research Assumption A1: `test_v2_g4` uses `@pytest.mark.asyncio + async def` (not `asyncio.get_event_loop().run_until_complete`) — consistent with the rest of the test suite. No other deviations.

## Known Stubs

- `test_v2_g5_lead_553891500357` — intentional `pytest.mark.skip`. Tracked stub awaiting user-provided incident trace for lead 553891500357 (09/06 incident). Will be un-skipped when timestamps + webhook payloads + conversas log are provided. See REQUIREMENTS.md TEST-V2-G5.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced. Plan adds only a test file.

## Self-Check: PASSED

- File exists: `leadflow-backend/tests/test_v2_regression.py` — FOUND
- Submodule commit `bfa18ae` — FOUND (`git log --oneline -1` in leadflow-backend confirms)
- `pytest tests/test_v2_regression.py -q` → `5 passed, 1 skipped, 0 failed` — VERIFIED
- `grep -c "def test_v2_g"` → 5 — VERIFIED
- `grep "blocked-pending-data"` → found in skip reason — VERIFIED
- `grep "app.services.evolution.verificar_lead_no_grupo"` → correct patch target present — VERIFIED
