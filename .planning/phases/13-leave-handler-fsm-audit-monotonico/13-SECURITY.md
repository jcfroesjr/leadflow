---
phase: 13
slug: leave-handler-fsm-audit-monotonico
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-10
---

# Phase 13 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Verified against implemented code (file:line evidence). The security auditor
> agent gathered evidence but was interrupted before writing; the orchestrator
> completed verification with targeted greps and authored this report.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Evolution webhook → backend | `GROUP_PARTICIPANTS_UPDATE action=remove` is unauthenticated (no signature — inherits Phase 10 T-10-09) | grupo_jid / telefone / lid / messageTimestamp |
| `reason`/`caller` → conversas GSC marker | written verbatim into marker conteudo (role=sistema) | code-supplied literals only |
| any code → FSM state | `force=True` bypasses the monotonic guard | state transition |
| client → `/admin/grupo/status?timeline=true` | authenticated admin endpoint returning audit data | empresa-scoped GSC timeline |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Status | Evidence |
|-----------|----------|-----------|-------------|--------|----------|
| T-13-01 | Tampering | set_grupo_state force=True | mitigate | closed | `force=True` only at admin.py:964 + grupo_webhook.py:348; `test_fsm_caller_ci.py::test_force_true_only_in_admin` asserts sanctioned files only |
| T-13-02 | Injection | reason/caller → GSC marker | accept | closed | reason/caller are code literals (e.g. caller='fallback_timeout_30min'); never user/lead input; marker role=sistema, not rendered to lead |
| T-13-03 | Repudiation | FSM change without audit | mitigate | closed | grupo_state.py:101 writes GSC on accept; :167/:210 write `GSC:...:BLOCKED:...` on rejection — full audit |
| T-13-04 | Spoofing | forged action=remove webhook | accept | closed | Inherits Phase 10 T-10-09 (no webhook signature); operational mitigation: instance→empresa lookup + Easypanel network isolation. Webhook signing out of scope (touches all 4 paths). Residual risk documented. |
| T-13-05 | Tampering | messageTimestamp → saiu_em | mitigate | closed | parse_evolution_timestamp falls back to utcnow() on garbage; saiu_em used for ordering/display, not auth; `_mark_membership_left` gated by `.is_('saiu_em','null')` (grupo_membership.py:464) |
| T-13-06 | DoS / Replay | repeated REMOVE events | mitigate | closed | `_mark_membership_left` idempotent (saiu_em IS NULL → 0 rows on replay); LEAD_SAIU_GRUPO marker idempotent; FSM LEFT_GROUP terminal |
| T-13-07 | Tampering | bare @lid remove, unknown telefone | accept | closed | bare-lid REMOVE only marks saiu_em on the lid row; no FSM change / no marker; cannot evict a phone-identified lead. Low impact |
| T-13-08 | Elevation of Privilege | force=True in non-admin callsite | mitigate | closed | force=True added to exactly one app callsite (C2 admin promover_ativo behind _check_auth) + the sanctioned webhook REMOVE; CI test enforces |
| T-13-09 | Repudiation | anonymous FSM mutation | mitigate | closed | `scripts/check_fsm_callers.py` AST sweep: 66 files, 0 violations; no "unknown" sentinel permitted; mandatory caller kwarg (no default) |
| T-13-10 | Information Disclosure | timeline cross-tenant GSC leak | mitigate | closed | All three timeline queries empresa-scoped: leads (admin.py:851), agendamentos (:857 — code-review WR-03 fix), GSC markers (:883) |
| T-13-11 | Elevation of Privilege | unauthenticated timeline access | mitigate | closed | `await _check_auth(authorization)` at admin.py:803 runs before any query; timeline is a param on the already-gated endpoint |
| T-13-12 | DoS | unbounded timeline query | mitigate | closed | GSC query bounded `.limit(5000)` (admin.py:885); ~150 markers/day → realistic volumes tiny |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-13-01 | T-13-04 | Evolution webhook has no signature validation (inherited Phase 10 T-10-09). A forged `action=remove` could falsely evict a lead, but the attacker must know a valid instance name (instance→empresa lookup) and reach the Easypanel-isolated endpoint. Adding webhook signing is cross-cutting (all 4 webhook paths) — deferred to a dedicated hardening pass. saiu_em is non-authoritative (display/ordering only); the LEAVE is recoverable (a subsequent ADD re-activates). | jcfroesjr | 2026-06-10 |
| AR-13-02 | T-13-02 | reason/caller are compile-time code literals, never user input. If a future caller ever passes user-derived data, escape colons (see 13-REVIEW.md IN-01). | jcfroesjr | 2026-06-10 |
| AR-13-03 | T-13-07 | bare-@lid REMOVE (unknown telefone) only marks the lid row's saiu_em — no FSM/marker side effects. Low impact. | jcfroesjr | 2026-06-10 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-10 | 12 | 12 | 0 | gsd-secure-phase (orchestrator; auditor interrupted, completed via direct grep verification) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-10
