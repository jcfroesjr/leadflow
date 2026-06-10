---
phase: 12
slug: retry-async-callers-com-margem
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-09
---

# Phase 12 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| APScheduler job kwargs → handler | grupo_jid/telefone/lid originate from internal agendamentos/conversas; compose the job_id. empresa_id scoping added (WR-02). | Internal UUIDs + phone digits — no external input |
| handler → grupo_membership table | _query_membership_row filters by empresa_id (tenant isolation inherited from Phase 11) | Boolean membership result per tenant |
| handler → Evolution API | evo_url/evo_key/evo_inst passed as kwargs from the enqueuer; no runtime re-fetch | Probe HTTP result (in_group bool) |
| recovery query → agendamentos/grupo_membership | Filters status='agendado' + empresa_id from each row + time-bounded window | Appointment data scoped per tenant |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-12-01 | Tampering/Spoofing | job_id `probe_retry:{empresa_id[:8]}:{grupo_jid}:{telefone}:{attempt}` collision/injection | accept | grupo_jid/telefone from internal data only; WR-02 fix added empresa_id[:8] prefix (line 521); replace_existing=True makes collision idempotent | closed |
| T-12-02 | DoS | re-enqueue unbounded retries | mitigate | `_RETRY_DELAYS_SEC=[30,120,300]` (line 21); `attempt >= len(_RETRY_DELAYS_SEC)` guard (line 511); max_age_seconds=600 guard in `_probe_retry_job` (line 577) | closed |
| T-12-03 | Information Disclosure | cross-tenant table-first query | mitigate | `_query_membership_row` filters `.eq('empresa_id', empresa_id)` (line 99); empresa_id comes from enqueuer kwargs (line 529) — no query without tenant filter | closed |
| T-12-04 | DoS | retry on HTTP error (None) creates error-loop | mitigate | STEP 5 guard: `if schedule_retry_on_negative and probe_in_group is False` (line 334); CR-01 fix: `_probe_retry_job` re-enqueue path checks `if in_group is None: log+stop` then `elif attempts_left > 0: schedule` — None never re-enqueues (lines 622-632) | closed |
| T-12-05 | DoS | recovery startup volume burst | mitigate | `.limit(200)` (line 667); skip existing row (lines 682-687); skip no-creds (lines 703-704); WR-01 fix: `.gte("inicio", now.isoformat())` lower bound excludes past meetings (line 664) | closed |
| T-12-06 | Information Disclosure | recovery cross-tenant creds | mitigate | creds fetched per empresa_id via `.eq("id", empresa_id)` on empresas table (lines 689-701); same pattern as warmup_grupo.py — no cross-tenant bleed | closed |
| T-12-07 | Tampering | caller migration changes routing destination | accept | `_in_group_real_cf = (_result_cf.get("in_group") is True)` preserves bool semantics (confirmacao_agendamento.py line 304); `_in_group_real_nf = not _fallback_nf` unchanged (warmup_grupo.py line 815); retry is best-effort separate from sync routing decision | closed |
| T-12-08 | Tampering | test false-positive via mock masking real bugs | mitigate | mock_scheduler captures real args; test asserts job["id"], replace_existing, run_date delta, enqueued_at in kwargs (test_probe_retry.py lines 137-151); max_age/table-first tests verify behavior (probe_called count), not just invocation; CR-01 regression test `test_retry_job_none_does_not_reenqueue` added (lines 403-441); 12/12 green | closed |
| T-12-09 | Test integrity | conftest stub hides evolution import | accept | conftest validated in Phases 9/11; patch pattern replicated from existing passing tests; accepted per design | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-12-01 | T-12-01 | job_id collision across tenants sharing the same grupo_jid is low-probability at current prod scale (few tenants); WR-02 fix added empresa_id[:8] prefix which eliminates the class entirely; replace_existing=True makes any residual collision idempotent (worst case: one tenant's job overwrites another's, both are best-effort). Source data (grupo_jid/telefone) is internal, not attacker-controlled. | gsd-secure-phase audit | 2026-06-09 |
| AR-12-02 | T-12-07 | Caller migration preserves bool routing semantics. Retry is explicitly best-effort and separate from the synchronous destination decision. Acceptance documented in 12-02-PLAN.md threat model. | gsd-secure-phase audit | 2026-06-09 |
| AR-12-03 | T-12-09 | conftest.py stub for app.services.evolution was validated in Phases 9 and 11; test suite runs 12/12 green against real production module code. The stub intercepts only the evolution HTTP call, not the retry logic under test. | gsd-secure-phase audit | 2026-06-09 |

---

## Unregistered Threat Flags

None. No `## Threat Flags` section present in SUMMARY.md for Phase 12.

---

## Deferred Items (from 12-REVIEW.md — not security threats)

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| WR-03 | warning | Notif job enqueues retry even when FSM=AGUARDANDO/FALLBACK_1_1 (efficiency waste, not security). max_age guard bounds the waste. | deferred — efficiency only |
| IN-01 | info | Per-job timezone="UTC" vs global scheduler America/Sao_Paulo; harmless for date jobs from utcnow(). | deferred |
| IN-02 | info | Recovery passes lid="" — lid-only membership rows won't TABLE_HIT. Known design tradeoff. | deferred |
| IN-03 | info | test_aquec_stays_sync uses string-boundary heuristic; fragile if inner async defs added to aquecimento. | deferred |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-09 | 9 | 9 | 0 | gsd-secure-phase (claude-sonnet-4-6) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-09
