---
phase: 14
slug: testes-regressao-doc-observabilidade
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-10
---

# Phase 14 — Security

> Per-phase security contract. Lowest-surface phase of v2.2 (tests + 2 additive
> healthcheck fields + version string + in-repo doc). Verified by the orchestrator
> via direct code inspection during execution.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| operator → `/admin/grupo-membership/health` | unauthenticated (inherits Phase 10/11 AR-11-01) — aggregate ops metrics only | cache_hit_rate, total_rows_24h (no PII) |
| (tests / doc) | no runtime code, no network, no auth | — |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Status | Evidence |
|-----------|----------|-----------|-------------|--------|----------|
| T-14-01 | Tampering | placeholder/false test assertions | mitigate | closed | TEST-V2-G5 uses `pytest.mark.skip(reason="blocked-pending-data...")`, never `assert True`; CI shows the skip; G1-G4 assert `probe_called['count']==0` |
| T-14-02 | Information Disclosure | test docstrings cite real phone numbers | accept | closed | same numbers already in committed STATE.md/REQUIREMENTS.md; case-traceability; private repo (AR-14-01) |
| T-14-03 | Information Disclosure | healthcheck adds cache_hit_rate + total_rows_24h unauthenticated | accept | closed | aggregate ops metrics only (rate + count), zero PII/lead content; inherits AR-11-01; div0-guarded (admin.py:1212) |
| T-14-04 | DoS | total_rows_24h adds a count query per request | accept | closed | count exact + limit(1), indexed on criado_em; operator-frequency endpoint; wrapped in isolated try/except (admin.py:1280) |
| T-14-05 | Information Disclosure | in-repo doc cites real phone numbers | accept | closed | same numbers already committed elsewhere; traceability; private repo (AR-14-01) |
| T-14-06 | Tampering | regression gate masked by over-broad --ignore | mitigate | closed | exactly 2 named ignores (tzdata + httpx/idna env failures), justified in research; no directory-wide ignore, no -k filter dropping v2.2 cases |

*Status: open · closed* — *Disposition: mitigate · accept · transfer*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-14-01 | T-14-02, T-14-05 | Real phone numbers of the 5 motivating cases appear in test docstrings + the arch doc. They are case-traceability keys already present in committed STATE.md/REQUIREMENTS.md; the repo is private. No new exposure. | jcfroesjr | 2026-06-10 |
| (inherited) | T-14-03 | AR-11-01: `/admin/grupo-membership/health` is unauthenticated by design (Phase 10/11); exposes only aggregate operational metrics. Phase 14 adds two more aggregate fields — no new sensitivity. | jcfroesjr | 2026-06-09 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-10 | 6 | 6 | 0 | gsd-secure-phase (orchestrator, direct verification) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-10
