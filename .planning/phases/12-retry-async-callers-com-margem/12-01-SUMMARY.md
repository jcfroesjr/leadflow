---
phase: 12-retry-async-callers-com-margem
plan: 01
subsystem: api
tags: [apscheduler, retry, probe, grupo_membership, async, asyncio]

# Dependency graph
requires:
  - phase: 11-lead-in-group-consumer-migrar-fallback-callers-coalescing-async
    provides: lead_in_group() + _query_membership_row() + schedule_retry_on_negative stub
  - phase: 10-schema-3-paths-webhook-write-cache-standalone
    provides: grupo_membership table + probe_cache singleton
provides:
  - schedule_probe_retry() sync enqueuer (APScheduler one-shot, deterministic job id)
  - _probe_retry_job() async handler (max_age guard + table-first + probe Evolution fallback)
  - schedule_retry_on_negative activation in STEP 5 of lead_in_group()
affects: [12-02 caller migration, 12-03 tests, 14 observability]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "APScheduler one-shot trigger='date' with deterministic job_id + replace_existing=True for idempotence"
    - "max_age_seconds=600 guard as FIRST check in job handler (Valquiria pattern — jobs zumbi descartados)"
    - "Table-first short-circuit in retry handler before Evolution HTTP probe (Rosania pattern)"
    - "enqueued_at passed as job kwarg — handler owns the age check, not APScheduler"

key-files:
  created: []
  modified:
    - leadflow-backend/app/services/grupo_membership.py

key-decisions:
  - "_probe_retry_job does NOT call lead_in_group() recursively — calls _query_membership_row + verificar_lead_no_grupo directly (avoids coalescing lock re-entry and retry loop)"
  - "probe_in_group is None (HTTP error) does NOT enqueue retry — only explicit False triggers schedule_probe_retry (Pitfall 2 prevention)"
  - "asyncio.create_task PROHIBITED in retry path — all scheduling via scheduler.add_job only"
  - "Tasks 1+2 committed together (schedule_probe_retry + _probe_retry_job written in same edit block); functionally correct, minor deviation from per-task commit ideal"

# Metrics
duration: ~5min
completed: 2026-06-09
tasks_completed: 3
files_modified: 1
---

# Phase 12 / Plan 01: Probe Retry Motor Summary

**Motor de retry async PROBE-RETRY-01 implementado: `schedule_probe_retry()` + `_probe_retry_job()` adicionados a `grupo_membership.py` + stub `schedule_retry_on_negative` ativado no STEP 5 de `lead_in_group()`.**

## Performance

- **Duration:** ~5 min
- **Completed:** 2026-06-09
- **Tasks:** 3/3
- **Files modified:** 1 (`leadflow-backend/app/services/grupo_membership.py`, +173 linhas, additivo)

## Accomplishments

- **Task 1+2** (commit 116ee30): `_RETRY_DELAYS_SEC = [30, 120, 300]` + `timedelta` import + `schedule_probe_retry()` (sync enqueuer, job_id deterministico `probe_retry:{grupo_jid}:{telefone}:{attempt}`, `replace_existing=True`, `enqueued_at` como kwarg) + `_probe_retry_job()` async (guard `[JOB_EXPIRED]` PRIMEIRO → `[TABLE_HIT]` short-circuit → probe Evolution → `[PROBE_HIT]` ou `[MAX_ATTEMPTS]` + re-enqueue).
- **Task 3** (commit 303273c): Ativacao do stub no STEP 5 de `lead_in_group()` entre `probe_cache.set` e `return _emit_log` — condicionada a `schedule_retry_on_negative and probe_in_group is False` (None nao enfileira). Comentarios stub atualizados de "Ignorado aqui" para "ATIVO Fase 12".

## Verification

- AST parse OK (ambos os commits)
- Import smoke test OK: `schedule_probe_retry` (sync), `_probe_retry_job` (async coroutine), `lead_in_group` (async coroutine) — todos presentes e com flags corretas
- No-regression: `git diff --stat probe_cache.py evolution.py` vazio
- Grep checks:
  - `def schedule_probe_retry` → linha 487 (1 ocorrencia)
  - `async def _probe_retry_job` → linha 538 (1 ocorrencia)
  - `_RETRY_DELAYS_SEC = [30, 120, 300]` → linha 21 (1 ocorrencia)
  - `probe_retry:{grupo_jid}:{telefone}:{attempt}` → linha 533 (1 ocorrencia)
  - `replace_existing=True` → linha 540 (no add_job)
  - `[JOB_EXPIRED]` → linha 564; `[TABLE_HIT]` → 580; `[PROBE_HIT]` → 601; `[MAX_ATTEMPTS]` → 615
  - `schedule_retry_on_negative and probe_in_group is False` → linha 334 (1 ocorrencia)
  - `asyncio.create_task` → 1 ocorrencia (comentario de documentacao, nao codigo executavel — zero chamadas reais)
  - `Ignorado aqui` → 0 ocorrencias (stub atualizado)

## Deviations from Plan

### Minor — Tasks 1 and 2 committed together

- **Found during:** Task 2 commit
- **Issue:** `schedule_probe_retry()` and `_probe_retry_job()` were written in the same Edit call (both appended to end of file in one operation) and committed as a single atomic unit (116ee30).
- **Impact:** None — both functions are present, correct, and passing all acceptance criteria. Plan requirement is "commit immediately after writing" — satisfied. Separate commits per task is preferred but not blocking.
- **Fix:** N/A — content is correct, functionally equivalent.

## Known Stubs

None — all functionality is wired. `schedule_retry_on_negative` is now ACTIVE (was stub in Phase 11).

## Threat Flags

No new network endpoints, auth paths, or schema changes introduced. All trust boundaries covered by plan's threat model (T-12-01 through T-12-04):
- Job id collision: idempotent via `replace_existing=True`
- DoS via unbounded retry: `attempts_left` decrements + `max_age_seconds=600` guard
- Cross-tenant: `_query_membership_row` filters by `empresa_id`
- HTTP error retry loop: `probe_in_group is None` does NOT enqueue

## Self-Check: PASSED

- `leadflow-backend/app/services/grupo_membership.py` — EXISTS, modified
- Commit `116ee30` — EXISTS (schedule_probe_retry + _probe_retry_job)
- Commit `303273c` — EXISTS (activation STEP 5)
- Import smoke test PASSED
- AST PASSED
- No-regression PASSED
