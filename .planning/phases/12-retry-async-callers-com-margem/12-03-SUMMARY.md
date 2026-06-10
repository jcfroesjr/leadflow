---
phase: 12-retry-async-callers-com-margem
plan: 03
subsystem: tests
tags: [pytest, probe-retry, apscheduler, mock, grupo_membership, regression]

# Dependency graph
requires:
  - phase: 12-01
    provides: schedule_probe_retry() + _probe_retry_job() + schedule_retry_on_negative activation
  - phase: 12-02
    provides: confirmacao D-1 caller migrated + warmup notif retry + recovery startup
provides:
  - tests/test_probe_retry.py (11 tests, PROBE-RETRY-01 + PROBE-RETRY-02 coverage)
  - Regression guard for retry motor and caller migration
affects: [14-observability]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "sys.modules stub injection at module level for unavailable deps (apscheduler, supabase-py) — identical to conftest.py pattern for evolution"
    - "patch.object on pre-injected stub module (not string patch path) for scheduler mock"
    - "Source file inspection via pathlib.Path.read_text() for caller tests — avoids importing heavy deps"

key-files:
  created:
    - leadflow-backend/tests/test_probe_retry.py
  modified: []

key-decisions:
  - "patch target for scheduler is app.scheduler.scheduler via patch.object (local import in schedule_probe_retry — not module-level attribute)"
  - "app.scheduler stub injected at test module load time (apscheduler absent in venv) — same pattern as conftest evolution stub"
  - "app.db.client stub injected at module level (supabase create_client API mismatch in test venv)"
  - "PROBE-RETRY-02 tests use source file inspection (pathlib) — avoids importing confirmacao_agendamento.py and warmup_grupo.py which have heavy transitive deps"
  - "Task 3 tests written in same file as Tasks 1-2 — committed as part of 7f86983 (no separate commit needed since git status showed no new changes)"

# Metrics
duration: ~8min
completed: 2026-06-10
tasks_completed: 3
files_modified: 1
---

# Phase 12 / Plan 03: Test Suite test_probe_retry.py Summary

**Suite pytest 11/11 passing cobrindo PROBE-RETRY-01 (motor de retry) + PROBE-RETRY-02 (callers com margem). APScheduler e supabase-py mockados via stub injection em sys.modules.**

## Performance

- **Duration:** ~8 min
- **Completed:** 2026-06-10
- **Tasks:** 3/3
- **Files created:** 1 (`leadflow-backend/tests/test_probe_retry.py`, 11 testes)

## Accomplishments

- **Task 1** (commit 9290068): Skeleton `test_probe_retry.py` com fixtures `mock_scheduler` + `reset_state` (autouse). Stubs de `app.scheduler` e `app.db.client` injetados em `sys.modules` no nivel de modulo. Patch target confirmado: `schedule_probe_retry` usa import local → `patch.object(app.scheduler, 'scheduler', mock)`. AST parse OK.

- **Task 2** (commit 7f86983): 9 testes PROBE-RETRY-01 implementados e passing:
  - `test_schedule_creates_job` — id deterministico + replace_existing + run_date ~+30s
  - `test_idempotent_job_id` — 2 enqueues mesma chave = mesmo job_id
  - `test_max_age_guard_expired` — enqueued_at=47h ago → probe NAO chamado (Valquiria)
  - `test_max_age_guard_valid` — enqueued_at recente → probe chamado
  - `test_table_hit_skips_probe` — row na tabela → sem probe + cache True (Rosania)
  - `test_rosania_sequence` — sequencia completa T=0 False→job0 / T+30 TABLE_HIT
  - `test_max_attempts_no_reschedule` — attempts_left=0 → 0 novos jobs
  - `test_stub_false_no_retry` — schedule_retry_on_negative=False → 0 jobs
  - `test_none_probe_no_retry` — probe None (erro HTTP) → 0 jobs (Pitfall 2)

- **Task 3** (included in 7f86983): 2 testes PROBE-RETRY-02 + suite completa green:
  - `test_confirmacao_caller_activates_retry` — source inspection confirma `schedule_retry_on_negative=True` + `lead_in_group` import em `confirmacao_agendamento.py`
  - `test_aquec_stays_sync` — source inspection confirma `_executar_aquecimento_job` SEM `schedule_probe_retry` + `_executar_notificacao_grupo_job` COM `schedule_probe_retry`
  - Suite completa: 57/57 passing (11 novos + 46 existentes das Fases 10-11)

## Verification

- `pytest tests/test_probe_retry.py -x -q` → **11 passed** (exits 0)
- `pytest tests/ -q --ignore=test_calendar_buffer.py --ignore=test_verificar_lead_no_grupo_phase3.py` → **57 passed** (exits 0)
- Pre-existing env failures (excluded, nao regressions):
  - `test_calendar_buffer.py` — `ZoneInfoNotFoundError: America/Sao_Paulo` (tzdata ausente no venv Python 3.14)
  - `test_verificar_lead_no_grupo_phase3.py` — `httpx→idna circular import` no venv Python 3.14

## Deviations from Plan

### Minor — Task 3 committed as part of Task 2 commit

- **Found during:** Task 3 completion
- **Issue:** All 11 tests were written in the initial file creation (Task 1 write). Task 2 commit (`7f86983`) captured the full file including the 2 Task 3 tests — Task 3 left no unstaged changes to commit separately.
- **Impact:** None — all 11 tests present, passing, and committed.
- **Fix:** N/A — content correct, functionally equivalent.

### Minor — Two additional sys.modules stubs required (app.scheduler + app.db.client)

- **Found during:** Task 2 test execution
- **Issue:** `apscheduler` not installed in test venv (APScheduler import fails when `app.scheduler` is imported). `supabase-py` has `create_client` API mismatch in venv. Both prevent `patch("app.scheduler.scheduler")` string path and `monkeypatch.setattr("app.db.client.get_supabase")` from working.
- **Fix:** Module-level stub injection in `test_probe_retry.py` (same pattern as `conftest.py` for `app.services.evolution`). `patch.object` used instead of string patch for scheduler.
- **Files modified:** `leadflow-backend/tests/test_probe_retry.py`
- **Impact:** None — tests isolated from real APScheduler/Supabase; mock captures correct job args.

## Known Stubs

None — all test assertions verify real behavior of the production code. Mocks isolate external deps (APScheduler, Supabase, Evolution HTTP) while testing the logic paths directly.

## Threat Flags

No new network endpoints, auth paths, file access, or schema changes. Tests only import and inspect production code — no new trust boundaries.

## Self-Check: PASSED

- `leadflow-backend/tests/test_probe_retry.py` — EXISTS, created
- Commit `9290068` — EXISTS (task 1 skeleton)
- Commit `7f86983` — EXISTS (tasks 2+3 — 11 tests)
- `grep -c "def test_"` → 11
- `pytest tests/test_probe_retry.py -x -q` → 11 passed
- `pytest tests/ -q --ignore=...` → 57 passed, 0 regressions
