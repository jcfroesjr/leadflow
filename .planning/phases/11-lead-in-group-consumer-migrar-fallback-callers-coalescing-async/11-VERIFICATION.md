---
phase: 11-lead-in-group-consumer-migrar-fallback-callers-coalescing-async
verified: 2026-06-09T23:45:00Z
status: human_needed
score: 5/6 must-haves verified
overrides_applied: 0
deferred:
  - truth: "Janela stale <6min retorna 'pending' (inconclusivo) em vez de False — permite Fase 12 enfileirar retry"
    addressed_in: "Phase 12"
    evidence: "Phase 12 goal: 'Probe negativo inicial NAO conclui definitivo — enfileira retry async'. SC3: 'Webhook entre tentativas (caso Rosania T+138s) faz retry consultar tabela primeiro'. Phase 11 PLAN non_regression doc: 'pending em in_group é Fase 12 — nesta fase janela <6min faz probe sincrono igual hoje.'"
human_verification:
  - test: "Confirm [MEMB-LOOKUP] logs appear in live prod traffic with source=membership on at least 1 lookup (confirms webhook-first inversion active, not just probe fallback every time)"
    expected: "After natural traffic (5-10 min), SSH logs show '[MEMB-LOOKUP] ... source=membership in_group=True latency_ms=...' from a lead whose entry was recorded by a prior webhook write"
    why_human: "Requires live prod traffic with a lead whose grupo_membership row was populated by Phase 10 webhook paths. Can't simulate prod webhook writes in static code analysis."
  - test: "Confirm 42501 permission fix (migration 005) is applied in prod and reads no longer degrade to probe"
    expected: "curl /admin/grupo-membership/health returns total_rows > 0 (or at least no 'total_rows_erro' key) and lookup_stats.lock_dict_size is an int (not lock_dict_size_erro). No '42501 permission denied' in prod logs."
    why_human: "Migration 005 was applied manually via Supabase SQL Editor at checkpoint. Verified by user at checkpoint ('Re-smoke confirmed the *_erro keys gone') but not independently verifiable from code alone — requires prod DB state."
---

# Phase 11: `lead_in_group()` Consumer + Migrate Fallback Callers + Coalescing Async — Verification Report

**Phase Goal:** Inverter fonte da verdade nos callers criticos. `lead_in_group()` consulta `grupo_membership` PRIMEIRO; probe Evolution so roda como fallback. Migra os 7 callsites de `verificar_lead_no_grupo` em `grupo_fallback.py` para usar o novo consumer. Coalescing async via `asyncio.Lock` por chave.
**Verified:** 2026-06-09T23:45:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Step 0: Previous Verification

No previous VERIFICATION.md found. Proceeding with initial mode.

---

## Goal Achievement

### Observable Truths

| # | Truth (from ROADMAP SC) | Status | Evidence |
|---|-------------------------|--------|----------|
| 1 | `lead_in_group()` returns `{in_group, source, last_event_at, instance_key_match}` consulting `grupo_membership` FIRST; probe only if row absent | VERIFIED | `grupo_membership.py:149-332` — full decision tree implemented: cache→_query_membership_row()→orphan check→probe. All 5 source values present. |
| 2 | Stale window <6min returns `pending` (inconclusive) instead of False — enables Phase 12 retry | DEFERRED | Explicitly stubbed as no-op in Phase 11 (comment line 145-146: "pending em in_group e Fase 12"). Phase 12 covers PROBE-RETRY-01. `schedule_retry_on_negative=False` stub present in signature. |
| 3 | 6 (7) callsites in `grupo_fallback.py` call `lead_in_group()` instead of `verificar_lead_no_grupo` directly; probe direct only in admin endpoints | VERIFIED | `await lead_in_group` count=7, `await verificar_lead_no_grupo` count=0 in grupo_fallback.py. Import at line 40. Admin endpoints untouched (non-regression confirmed by plans). |
| 4 | `instance_key_match=False` treated as orphan group (caso Fernanda); sentinel allows caller to create new group | VERIFIED | `grupo_membership.py:261-269` — `source='orphan'` path returns `in_group=False, instance_key_match=False`. grupo_fallback.py has 6 `ORPHAN` handling blocks + `caso Fernanda` comments. |
| 5 | `asyncio.Lock` per-key prevents concurrent probe: 3 parallel jobs for same group fire 1 Evolution call (PROBE-COALESCE-01) | VERIFIED | `_probe_locks` dict + `_probe_locks_dict_lock` meta-lock + `_get_probe_lock()` present. Double-checked cache after lock acquisition at line 302. `test_coalesce_three_concurrent_lookups_one_probe` passes (46/52 green). |
| 6 | Logs `[MEMB-LOOKUP] source=... grupo=... verdict=...` appear in ALL lookups | VERIFIED | `_emit_log()` nested function called in every return path (lines 199, 211, 225, 255, 265, 275, 290, 304, 327). Format key=value with `latency_ms`. |

**Score:** 5/6 truths verified (SC2 deferred to Phase 12, see Deferred Items section)

---

### Deferred Items

Items not yet met but explicitly addressed in later milestone phases.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Stale window <6min returns `pending` (inconclusive) instead of False | Phase 12 | Phase 12 SC1: "Probe negativo inicial NAO conclui definitivo — enfileira retry async". Phase 11 plan non_regression: "pending em in_group e Fase 12 (PROBE-RETRY-01). Nesta fase, janela <6min faz probe sincrono igual hoje." `schedule_retry_on_negative=False` stub in signature confirms intentional deferral. |

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `leadflow-backend/app/services/grupo_membership.py` | `lead_in_group()` + `_query_membership_row()` + `_get_probe_lock()` + `_probe_locks` dict | VERIFIED | File exists, 459 lines. All symbols present at top of module. `lead_in_group` is async coroutine. |
| `leadflow-backend/app/services/grupo_membership.py` | `[MEMB-LOOKUP]` log format in all paths | VERIFIED | `_emit_log` nested function called in all 8 return branches. Line 189 confirms format. |
| `leadflow-backend/app/services/grupo_fallback.py` | `from app.services.grupo_membership import lead_in_group` + 7 substitutions | VERIFIED | Import at line 40. `await lead_in_group` count=7. `await verificar_lead_no_grupo` count=0. |
| `leadflow-backend/app/services/grupo_fallback.py` | PROBE-BYPASS-01 marker preserved | VERIFIED | `GRUPO_LEAD_ENTROU_CRIACAO` at lines 305, 314, 317. `bypass probe (NAO ativa)` at line 317. |
| `leadflow-backend/tests/test_lead_in_group_decision.py` | 5+ decision tree tests | VERIFIED | 7 async test functions: cache_hit, membership_hit, orphan_instance_skips_probe, no_row_falls_to_probe, db_error, no_creds, allow_probe_fallback_false. autouse fixture resets state. |
| `leadflow-backend/tests/test_lead_in_group_coalesce.py` | 2+ coalescing integration tests | VERIFIED | 3 async test functions: 3-concurrent-1-probe, different-keys-parallel, same-key-reuses-lock. |
| `leadflow-backend/tests/test_grupo_fallback_migration.py` | CI grep assertions for 7 substitutions | VERIFIED | 9 test functions including test_no_verificar_lead_no_grupo_in_grupo_fallback, test_seven_lead_in_group_calls, test_probe_bypass_marker_preserved, test_alerta_grupo_skip_preserved. |
| `leadflow-backend/app/main.py` | BUILD_VERSION contains "lead-in-group-consumer" | VERIFIED | Line 239: `BUILD_VERSION = "2026-06-09-lead-in-group-consumer"` |
| `leadflow-backend/app/routers/admin.py` | `/admin/grupo-membership/health` with `lookup_stats.lock_dict_size` + `phase="11-consumer"` | VERIFIED | Lines 1155-1175: `lookup_stats` dict initialized, `phase: "11-consumer"` at line 1163, `_probe_locks` imported and `len()` taken defensively. `10-fundacao` string count=0. |
| `leadflow-backend/app/db/migrations/005_grupo_membership_grants.sql` | GRANT SELECT/INSERT/UPDATE/DELETE to service_role (42501 fix) | VERIFIED | File exists, grants `SELECT, INSERT, UPDATE, DELETE ON public.grupo_membership TO service_role` + sequence USAGE. Applied to prod at checkpoint per SUMMARY. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `lead_in_group()` | `probe_cache.get()` / `probe_cache.set()` | cache fast-path (line 209) + post-probe write (line 325) | WIRED | 2 `probe_cache.get` calls (fast-path + double-check), 1 `probe_cache.set` call |
| `lead_in_group()` | `get_instance_key(sb, empresa_id)` | orphan check at line 239 | WIRED | Called inside `if row is not None` block to compare instance keys |
| `lead_in_group()` | `verificar_lead_no_grupo` (evolution.py) | local import + probe call at line 313 | WIRED | Local import at line 182; called inside `async with lock` block |
| `lead_in_group()` | `_get_probe_lock(key)` | coalescing at line 298 | WIRED | `key = _make_probe_lock_key(...)` then `lock = await _get_probe_lock(key)` then `async with lock:` |
| `grupo_fallback.py:ativar_fallback_se_necessario` | `lead_in_group()` | blocks 1b, 1c, 2 (3 calls) | WIRED | `await lead_in_group` with explicit kwargs `sb=sb, empresa_id=empresa_id, telefone=telefone, grupo_jid=grupo_jid` |
| `grupo_fallback.py:_disparar_convite_lead_se_aguardando` | `lead_in_group()` | live probe before sending DM invite | WIRED | 1 `await lead_in_group` call with orphan guard |
| `grupo_fallback.py:_disparar_alerta_grupo_se_aguardando` | `lead_in_group()` | live probe before FSM sync | WIRED | 1 `await lead_in_group` call; ALERTA-GRUPO-01 skip preserved at line 697 |
| `grupo_fallback.py:polling_grupos_aguardando` | `lead_in_group()` | 2 branches (AGUARDANDO + FALLBACK_1_1) | WIRED | 2 `await lead_in_group` calls using `cfg["url"]/cfg["key"]/cfg["inst"]` as kwargs |
| `admin.py:grupo_membership_health` | `_probe_locks` from `grupo_membership.py` | defensive import + `len()` at lines 1172-1173 | WIRED | `from app.services.grupo_membership import _probe_locks` inside try/except; `lock_dict_size = len(_probe_locks)` |
| `BUILD_VERSION` in `main.py` | `/version` endpoint | FastAPI route at line 242 | WIRED | `@app.get("/version")` returns dict containing `BUILD_VERSION`; confirmed by prod smoke |

---

### Data-Flow Trace (Level 4)

The main artifacts that render dynamic data are `lead_in_group()` (reads from `grupo_membership` table) and the healthcheck endpoint (reads `_probe_locks` dict and table counts).

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `lead_in_group()` | `row` from `_query_membership_row` | `sb.table('grupo_membership').select(...).execute()` | Yes — real DB query with `saiu_em IS NULL` filter + `ORDER BY atualizado_em DESC LIMIT 1` | FLOWING |
| `lead_in_group()` | `probe_in_group` | `verificar_lead_no_grupo()` HTTP call to Evolution | Yes — live HTTP probe (fallback path only) | FLOWING |
| `grupo_membership_health` | `lock_dict_size` | `len(_probe_locks)` in-process dict | Yes — reflects actual lock objects created by `lead_in_group()` calls | FLOWING |
| `grupo_membership_health` | `total_rows` | `sb.table("grupo_membership").select("id", count="exact")` | Yes — real DB count query | FLOWING |
| Prod reads (migration 005) | All `grupo_membership` direct reads | Supabase PostgREST as `service_role` | Yes — GRANT applied at checkpoint; prod smoke confirmed `*_erro` keys gone | FLOWING (prod-validated) |

---

### Behavioral Spot-Checks

Step 7b skipped for `lead_in_group()` itself — it requires a live Supabase client and Evolution instance. The pytest suite (46/52 green) covers all decision tree branches via monkeypatching.

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `lead_in_group` is async coroutine | `asyncio.iscoroutinefunction(lead_in_group)` (confirmed in SUMMARY Task 4 smoke) | True | PASS |
| `_probe_locks` is dict, `_probe_locks_dict_lock` is asyncio.Lock | Module-level globals verified by smoke test "TODOS OS SMOKES PASSARAM" in 11-04 | Both confirmed | PASS |
| 7 callsites migrated, 0 remaining | Grep `await lead_in_group`=7, `await verificar_lead_no_grupo`=0 | Verified directly in codebase | PASS |
| PROBE-BYPASS-01 preserved | Grep `GRUPO_LEAD_ENTROU_CRIACAO` + `bypass probe (NAO ativa)` | Both present, line 317 | PASS |
| BUILD_VERSION in prod | `curl /version` → `"2026-06-09-lead-in-group-consumer"` (per 11-04 SUMMARY checkpoint) | APPROVED by user | PASS |
| healthcheck phase=11-consumer + lookup_stats | `curl /admin/grupo-membership/health` (per 11-04 checkpoint) | APPROVED by user | PASS |
| Migration 005 applied, 42501 gone | Re-smoke at checkpoint confirmed `*_erro` keys gone | APPROVED by user | PASS |

---

### Requirements Coverage

Requirements claimed in plan frontmatter: `MEMB-05`, `PROBE-COALESCE-01`

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| MEMB-05 | 11-01, 11-02 | `lead_in_group()` consumer consulting `grupo_membership` FIRST, with orphan sentinel, instance_key_match check | SATISFIED | `lead_in_group()` implemented with full decision tree. 7 callsites migrated in `grupo_fallback.py`. 7 unit tests + 9 CI grep tests covering this requirement. |
| PROBE-COALESCE-01 | 11-01 | `asyncio.Lock` per-key prevents concurrent probe: N parallel jobs fire 1 Evolution call | SATISFIED | `_probe_locks` dict + meta-lock + `_get_probe_lock()` + double-checked cache in probe path. 3 coalescing integration tests passing (3-concurrent-1-probe verified). |

**Orphaned requirements check:** REQUIREMENTS.md traceability table maps MEMB-05 to "Fase 11, 11-01, 11-02" and PROBE-COALESCE-01 to "Fase 11 (movido da 10 em 09/06), 11-01" — both accounted for. No orphaned requirements for Phase 11.

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `grupo_membership.py:160` | `schedule_retry_on_negative: bool = False` — stub parameter, ignored | INFO | Intentional stub for Phase 12 (PROBE-RETRY-01). Documented in comment at line 175 and RESEARCH §20. Not a blocker. |
| `grupo_membership.py:145-146` | `pending` state deferred — stale window does probe sync in Phase 11 | INFO | Documented deferral per ROADMAP SC2. Phase 12 activates via `schedule_retry_on_negative`. No regression risk. |

No blockers or warnings found. The two INFO items are documented intentional deferrals.

---

### Human Verification Required

#### 1. Prod traffic confirms `source=membership` (webhook-first inversion active)

**Test:** SSH into Hostinger VPS and tail prod logs: `docker logs 3e74f7da5a68 --tail 500 -f | grep MEMB-LOOKUP`
**Expected:** At least one log line showing `source=membership` for a lead whose `grupo_membership` row was written by a prior Phase 10 webhook event. This is the primary behavioral signal that the inversion is working — the consumer is hitting the DB table instead of defaulting to probe on every call.
**Why human:** Requires waiting for real prod traffic with a lead that has a `grupo_membership` row. Phase 10 wrote rows; Phase 11 reads them. The 42501 fix was applied, so reads should work. But confirming `source=membership` appears (not just `source=probe` on every call) requires live traffic and can't be asserted from static code review alone.

#### 2. Confirm migration 005 permanently fixed 42501 (no regression after restart)

**Test:** After the next Easypanel container restart (daily), re-run `curl /admin/grupo-membership/health` and check there is no `total_rows_erro` or `lookup_stats.lock_dict_size_erro` key in the JSON response.
**Expected:** Clean response with `total_rows: <int>` and `lookup_stats: {"lock_dict_size": 0}` (lock dict resets on restart). No `*_erro` keys present.
**Why human:** Migration 005 grants are permanent in Postgres (not lost on restart), but the container restart will reset in-memory state. The first prod call post-restart should still read DB successfully. User confirmed this at checkpoint but a post-restart verification closes the loop definitively.

---

### Gaps Summary

No gaps blocking goal achievement. All 5 verifiable must-haves are VERIFIED (SC2 is deferred to Phase 12 as explicitly designed in the plan). The 2 human verification items are behavioral/prod-state checks that cannot be asserted from static analysis — they do not represent implementation holes, but rather prod validation completion.

**Phase 11 delivered:**
- `lead_in_group()` async consumer with complete 5-step decision tree
- PROBE-COALESCE-01 via per-key `asyncio.Lock` + double-checked locking
- 7/7 callsite migrations in `grupo_fallback.py` (PROBE-BYPASS-01 and ALERTA-GRUPO-01 preserved literally)
- 19 pytest tests (7 decision + 3 coalescing + 9 CI grep) — 46/52 suite green (6 pre-existing env failures excluded)
- BUILD_VERSION `2026-06-09-lead-in-group-consumer` confirmed in prod
- `/admin/grupo-membership/health` extended with `lookup_stats.lock_dict_size` + `phase=11-consumer`
- Migration 005 fixing 42501 permission error applied to prod — direct reads now work

---

_Verified: 2026-06-09T23:45:00Z_
_Verifier: Claude (gsd-verifier)_
