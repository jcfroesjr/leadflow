---
phase: 11
slug: lead-in-group-consumer-migrar-fallback-callers-coalescing-async
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-09
---

# Phase 11 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Built from artifacts (State B) — the autonomous code plans carried no formal `<threat_model>`,
> so the register below was derived from the phase's actual attack surface.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Backend ↔ Supabase (PostgREST as `service_role`) | `lead_in_group()` reads `grupo_membership` directly | empresa_id-scoped membership rows (telefone/lid, instance_key) |
| Public internet ↔ Backend `/admin` | `/admin/grupo-membership/health` reachable without auth | Aggregate operational counters (no PII) |
| Evolution API ↔ Backend | Probe fallback HTTP call (coalesced) | grupo_jid / telefone / lid |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-11-01 | Information Disclosure (cross-tenant) | `grupo_membership.py` `_query_membership_row` / `lead_in_group` | mitigate | Query enforces `.eq('empresa_id', empresa_id)` — membership lookups are tenant-scoped; no cross-empresa read path | closed |
| T-11-02 | Elevation of Privilege | `migrations/005_grupo_membership_grants.sql` | mitigate | GRANT scoped `TO service_role` only (no anon/authenticated/public). RLS remains enabled on the table (migration 004) with a service_role-only policy. Least privilege preserved | closed |
| T-11-03 | Information Disclosure | `admin.py` `GET /admin/grupo-membership/health` | accept | Endpoint is unauthenticated by design (inherited from Fase 10). Exposes only aggregate operational counters (total_rows, writes_by_source_24h, cache_stats, lookup_stats.lock_dict_size, phase). No PII, no lead data, no per-tenant breakdown. See Accepted Risks | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-11-01 | T-11-03 | `/admin/grupo-membership/health` returns aggregate operational metrics only (no PII, no lead/conversation data, no per-tenant breakdown). Consistent with existing unauthenticated `/admin/grupo/*` operational endpoints, and used as the deploy-smoke curl. Low severity. Revisit in Fase 14 (full healthcheck + alerting hooks) — gate with `_check_auth` then if scope expands | jcfroesjr | 2026-06-09 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-09 | 3 | 3 | 0 | gsd-secure-phase (orchestrator) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-09
