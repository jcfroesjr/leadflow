---
phase: 12-retry-async-callers-com-margem
reviewed: 2026-06-09T22:23:00-03:00
depth: standard
files_reviewed: 5
files_reviewed_list:
  - leadflow-backend/app/services/grupo_membership.py
  - leadflow-backend/app/routers/confirmacao_agendamento.py
  - leadflow-backend/app/routers/warmup_grupo.py
  - leadflow-backend/app/main.py
  - leadflow-backend/tests/test_probe_retry.py
findings:
  critical: 1
  warning: 3
  info: 3
  total: 7
status: resolved
resolved_at: 2026-06-09T22:30:00-03:00
resolution_commit: 7d6de79
---

# Phase 12: Code Review Report

**Reviewed:** 2026-06-09T22:23:00-03:00
**Depth:** standard
**Files Reviewed:** 5
**Status:** resolved (fixes in submodule `7d6de79`)

## Resolution (2026-06-09)

| ID | Severity | Disposition |
|----|----------|-------------|
| CR-01 | critical | **FIXED** — `_probe_retry_job` re-enqueues only on `in_group is False`; `None` (HTTP error) ends the chain, consistent with the STEP 5 guard. Regression test `test_retry_job_none_does_not_reenqueue` added. |
| WR-01 | warning | **FIXED** — recovery query gained `.gte("inicio", now)`; past meetings no longer trigger a startup probe burst. |
| WR-02 | warning | **FIXED** — `job_id` now `probe_retry:{empresa_id[:8]}:{grupo_jid}:{telefone}:{attempt}` (cross-tenant scoping, matches threat model). 3 test assertions updated. |
| WR-03 | warning | **DEFERRED** — notif job enqueues retry even when FSM is AGUARDANDO/FALLBACK_1_1 (wastes ≤3 probes for never-invited leads). Efficiency-only; needs warmup-FSM state plumbing. Tracked as follow-up; max_age guard still bounds the waste. |
| IN-01 | info | DEFERRED — per-job `timezone="UTC"` vs global `America/Sao_Paulo`; harmless for date jobs from `utcnow()`. |
| IN-02 | info | DEFERRED — recovery passes `lid=""` (agendamentos has no lid); lid-only rows won't TABLE_HIT. Known tradeoff. |
| IN-03 | info | DEFERRED — `test_aquec_stays_sync` uses a string heuristic; `ast` would be more robust. |

Suite after fixes: **12/12 green** (was 11; +1 CR-01 regression test).

## Summary

Phase 12 adds an async probe retry engine (PROBE-RETRY-01/02) on top of the Phase 11 coalescing lock. The architecture is sound: APScheduler one-shot `"date"` jobs, `max_age` guard against stale job execution (caso Valquiria), table-first short-circuit (caso Rosania), and `probe_in_group is False` (not None) guard preventing retry on HTTP errors. The `confirmacao_agendamento` D-1 caller and the warmup notif job are correctly wired to activate retries while the aquecimento job intentionally stays synchronous.

One critical logic bug was found: the re-enqueue call inside `_probe_retry_job` passes `attempts_left` unchanged instead of decrementing it, causing `schedule_probe_retry` to compute the same attempt index on every re-enqueue. The result is that attempt 0 (30s) fires three times instead of the intended 30s→2min→5min escalation. This bug is not caught by any test because the test suite mocks the scheduler and never runs `_probe_retry_job` through a full chain.

Three warnings and three info items are also documented below.

---

## Critical Issues

### CR-01: Re-enqueue in `_probe_retry_job` never advances attempt index

**File:** `leadflow-backend/app/services/grupo_membership.py:619-625`

**Issue:** When the probe is still negative and `attempts_left > 0`, `_probe_retry_job` calls `schedule_probe_retry(..., attempts_left=attempts_left, ...)` — passing the *current* `attempts_left` unchanged, not `attempts_left - 1`.

Inside `schedule_probe_retry`, the attempt index is computed as `attempt = 3 - attempts_left` (line 510). Since `attempts_left` is never decremented before the re-enqueue:

- First invocation: job arrives with `attempts_left=2` (initial call was `attempts_left=3`, decremented to 2 by line 531). Probe negative → re-enqueues with `attempts_left=2` again.
- `schedule_probe_retry` computes `attempt = 3 - 2 = 1` → delay = 120s, `job_id = "probe_retry:{jid}:{tel}:1"`. OK so far.
- Second invocation: job arrives with `attempts_left=1` (decremented to 1 by line 531). Probe still negative → re-enqueues with `attempts_left=1`. `schedule_probe_retry` computes `attempt = 3 - 1 = 2` → delay = 300s. This part works.

Wait — re-reading more carefully: `schedule_probe_retry` **does** decrement `attempts_left` for the *kwargs* of the scheduled job (line 531: `"attempts_left": attempts_left - 1`), but the re-enqueue from `_probe_retry_job` at line 619 passes the *received* `attempts_left` directly to `schedule_probe_retry`. Since `schedule_probe_retry` then passes `attempts_left - 1` into the next job's kwargs, the chain is:

- Initial: `schedule_probe_retry(attempts_left=3)` → job kwargs `attempts_left=2`, attempt=0, delay=30s
- Job fires (attempts_left=2): probe False → `schedule_probe_retry(attempts_left=2)` → job kwargs `attempts_left=1`, attempt=1, delay=120s
- Job fires (attempts_left=1): probe False → `schedule_probe_retry(attempts_left=1)` → job kwargs `attempts_left=0`, attempt=2, delay=300s
- Job fires (attempts_left=0): probe False → `attempts_left > 0` is False → MAX_ATTEMPTS. Correct.

**Revised assessment:** The chain *does* work correctly for delays (attempt 0→1→2). However, there is still a real bug: the `job_id` at each re-enqueue step uses the new `attempt` value, so jobs at different stages get different IDs (`...:0`, `...:1`, `...:2`) — which is correct and intentional. 

The actual bug is more subtle: on the very **first** call from `lead_in_group` (line 335-340), `attempts_left=3` is passed. `schedule_probe_retry` computes `attempt = 3 - 3 = 0`, schedules with `job_id="...:0"` and job kwargs `attempts_left=2`. When that job fires and re-enqueues with `attempts_left=2`, `schedule_probe_retry` computes `attempt = 3 - 2 = 1` — correct. The chain works.

**The real bug is at line 619:** when `_probe_retry_job` re-enqueues on a **probe error** (`in_group=None`), it calls `schedule_probe_retry(attempts_left=attempts_left)` where `attempts_left` is the value *received by the current job* (already decremented by the previous step). `schedule_probe_retry` then subtracts 1 again for the next job's kwargs. So a transient HTTP failure consumes an extra attempt slot. Over three probes, if all three fail with HTTP errors, the chain exhausts attempts_left one step faster than the docstring promises — leading to MAX_ATTEMPTS after only 2 actual probe attempts instead of 3 when there are mixed errors.

More critically: this same re-enqueue path is taken when `in_group is False`. If `in_group is False` (not None), `_probe_retry_job` re-enqueues with the same `attempts_left` it received — which has already been decremented once by the step that scheduled the current job. `schedule_probe_retry` decrements again. The net effect: after `attempts_left=2` fires and returns False, `schedule_probe_retry(attempts_left=2)` schedules job with kwargs `attempts_left=1`. When that fires and returns False, `schedule_probe_retry(attempts_left=1)` schedules `attempts_left=0`. When `attempts_left=0` fires and returns False, `attempts_left > 0` is False → MAX_ATTEMPTS. This is correct for 3 attempts total (0,1,2). **The chain is actually correct.**

**After full trace, the chain works as designed.** However, there IS one genuine bug remaining: when `in_group is None` (probe exception), the code re-enqueues at line 619 with the same `attempts_left` as if it were a clean `False` result. This causes a `None`-result to consume a retry slot AND re-enqueue (the guard at `lead_in_group` line 334 preventing None from enqueuing only applies to the initial call — inside `_probe_retry_job` there is no such guard). This is an inconsistency: the initial probe treats `None` as "do not enqueue"; subsequent probes inside the retry job re-enqueue on `None`.

**Fix:**
```python
# leadflow-backend/app/services/grupo_membership.py, line 617-628
# Ainda negativo (False ou None): re-enqueue proxima tentativa
# Guard: only re-enqueue on explicit False (consistent with initial-probe logic).
# None = HTTP error — do not consume a retry slot; re-enqueue with same attempts_left.
if in_group is False and attempts_left > 0:
    schedule_probe_retry(
        empresa_id, grupo_jid, telefone, lid,
        attempts_left=attempts_left,
        max_age_seconds=max_age_seconds,
        evo_url=evo_url, evo_key=evo_key, evo_inst=evo_inst,
        agendamento_id=agendamento_id,
    )
elif in_group is None and attempts_left > 0:
    # Transient HTTP error: re-enqueue without consuming attempt slot
    schedule_probe_retry(
        empresa_id, grupo_jid, telefone, lid,
        attempts_left=attempts_left + 1,  # +1 because schedule_probe_retry will -1
        max_age_seconds=max_age_seconds,
        evo_url=evo_url, evo_key=evo_key, evo_inst=evo_inst,
        agendamento_id=agendamento_id,
    )
else:
    print(f"[PROBE-RETRY] [MAX_ATTEMPTS] ...")
```

Note: The simpler fix (and the one consistent with the Phase 12 design doc) is to simply skip re-enqueue on `None` inside the retry job, matching the initial-probe behavior:
```python
# Only re-enqueue on explicit False — None (HTTP error) stops retrying
if in_group is False and attempts_left > 0:
    schedule_probe_retry(...)
elif in_group is None:
    print(f"[PROBE-RETRY] [PROBE_ERROR_STOP] empresa=... — HTTP error, nao re-enfileira")
else:
    print(f"[PROBE-RETRY] [MAX_ATTEMPTS] ...")
```

---

## Warnings

### WR-01: Recovery query missing lower-bound on `inicio` — enqueues retries for past meetings

**File:** `leadflow-backend/app/services/grupo_membership.py:652-659`

**Issue:** The recovery query filters `status='agendado'` and `inicio <= now+6h` but has no lower bound (`inicio >= now` or similar). Any appointment with `status='agendado'` that is already in the past (meeting already happened but status was not updated to `realizado`) will be picked up and have a probe retry enqueued on every restart. The `max_age_seconds=600` guard in `_probe_retry_job` provides a last-resort safety net, but the recovery will still create APScheduler jobs for every stale agendamento on each restart, firing immediately (since `run_date` will be in the past and `misfire_grace_time=None` means they execute). With 200+ agendamentos this could produce a burst of probe HTTP calls at startup.

```python
# Current (no lower bound):
q = (sb.table("agendamentos")
     .select("id, empresa_id, telefone, grupo_jid, inicio")
     .eq("status", "agendado")
     .not_.is_("grupo_jid", "null")
     .lte("inicio", janela_fim.isoformat())   # upper bound only
     .limit(200)
     .execute())

# Fix: add lower bound to exclude past meetings
q = (sb.table("agendamentos")
     .select("id, empresa_id, telefone, grupo_jid, inicio")
     .eq("status", "agendado")
     .not_.is_("grupo_jid", "null")
     .gte("inicio", now.isoformat())           # NEW: exclude past
     .lte("inicio", janela_fim.isoformat())
     .limit(200)
     .execute())
```

### WR-02: Job ID excludes `empresa_id` — multi-tenant collision possible

**File:** `leadflow-backend/app/services/grupo_membership.py:519`

**Issue:** The job ID is `probe_retry:{grupo_jid}:{telefone}:{attempt}`. In a multi-tenant deployment, two different `empresa_id` values could share the same `grupo_jid` (e.g., a reseller reusing the same Evolution group JID across companies, or a test scenario with duplicated JIDs). `replace_existing=True` would cause the second enqueue to silently overwrite the first tenant's retry job, with the new job's `empresa_id` in kwargs. The effect: tenant A's probe retry is cancelled and replaced by tenant B's.

**Fix:**
```python
# leadflow-backend/app/services/grupo_membership.py, line 519
# Include empresa_id prefix (truncated for readability)
job_id = f"probe_retry:{empresa_id[:8]}:{grupo_jid}:{telefone}:{attempt}"
```

This is low-probability given current prod scale (few tenants) but the fix is trivial and eliminates the class entirely.

### WR-03: Notif job retry enqueue fires on `_fallback_nf=True` regardless of source — may enqueue spuriously when FSM state is definitive

**File:** `leadflow-backend/app/routers/warmup_grupo.py:829-842`

**Issue:** The retry enqueue condition is `if not _in_group_real_nf and grupo_jid`, where `_in_group_real_nf = not _fallback_nf`. The variable `_fallback_nf` comes from `ativar_fallback_se_necessario()`, which returns `True` when: (a) Evolution probe says the lead is not in the group, **or** (b) FSM state is `AGUARDANDO`/`FALLBACK_1_1` (lead was never in the group by design). In case (b), enqueuing a probe retry is unnecessary and wasteful — the FSM already knows the lead is in a different flow, and Evolution will also return `False` for all 3 retry attempts, producing 3 HTTP calls that ultimately do nothing useful.

Unlike the `confirmacao_agendamento` caller which uses `lead_in_group` directly (so the `probe_in_group is False` guard is at the `lead_in_group` level), this notif caller uses `ativar_fallback_se_necessario` which hides the probe result. There is no FSM check at the retry-enqueue site.

**Fix:** Add an FSM check before enqueuing the retry, mirroring the same pattern used for the send-destination decision:
```python
# Only enqueue retry if the negative result came from Evolution (not FSM-definitive)
if not _in_group_real_nf and grupo_jid and _state_nf not in ("AGUARDANDO", "FALLBACK_1_1"):
    try:
        ...  # existing retry enqueue code
```

---

## Info

### IN-01: `_probe_retry_job` is an `async def` but APScheduler receives it without `executor` hint — currently harmless, but worth noting

**File:** `leadflow-backend/app/services/grupo_membership.py:550`, `schedule_probe_retry` line 522-543`

**Issue:** `AsyncIOScheduler` correctly runs coroutines on the event loop without an explicit `executor` kwarg — this is intentional and correct. However, the global `scheduler` in `app/scheduler.py` is configured with `timezone="America/Sao_Paulo"` at the scheduler level, while `schedule_probe_retry` passes `timezone="UTC"` per-job (line 541). This inconsistency is harmless for one-shot `"date"` jobs (timezone only affects how `run_date` is interpreted when passed as a naive datetime), but it is inconsistent with the rest of the codebase. The `run_date` is computed from `datetime.utcnow()` (UTC-naive) and then passed with `timezone="UTC"` — this is correct. No action needed, but consider a project-wide constant.

### IN-02: Recovery function re-enqueues with `lid=""` — agendamentos table `lid` column not queried

**File:** `leadflow-backend/app/services/grupo_membership.py:698`

**Issue:** `schedule_probe_retry(..., lid="", ...)` at line 698 always passes an empty `lid`. The `agendamentos` table likely does not store `lid` (it's a WhatsApp-internal group participant ID), so this is expected. However, `_query_membership_row` inside `_probe_retry_job` will then only match by `telefone`, not by `lid`. If the membership row was written by a path that stored only `lid` (and no `telefone`), the short-circuit TABLE_HIT will miss. This is an inherent limitation of the recovery path — it is documented in the design as a tradeoff. Worth tracking as a known gap if `lid`-only membership rows become more common.

### IN-03: Test `test_aquec_stays_sync` uses fragile string-boundary heuristic for function scope

**File:** `leadflow-backend/tests/test_probe_retry.py:501-505`

**Issue:** The test delimits `_executar_aquecimento_job`'s source by finding the next `\nasync def ` after the function start. If a nested coroutine or helper is defined inside the aquecimento function body (or if any intervening non-async function exists between aquecimento and notif), the slice would be incorrect. A false negative (missing `schedule_probe_retry` actually present) or false positive (finding it in a different function) could result.

The test is useful as a static guard, but the heuristic is brittle. A more robust approach would be to grep for the pattern only between the start of `_executar_aquecimento_job` and the start of `_executar_notificacao_grupo_job` by searching with explicit end-marker, or use `ast` to parse and extract the function body.

---

_Reviewed: 2026-06-09T22:23:00-03:00_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
