---
phase: 10-schema-3-paths-webhook-write-cache-standalone
type: validation
covers_plans: [10-01, 10-02, 10-03, 10-04, 10-05]
created: 2026-06-09
source: 10-RESEARCH.md (sections "Verification" + "Testing pattern")
---

## Validation Strategy

Esta fase entrega a fundacao standalone de `grupo_membership` (tabela + 3 paths de escrita + cache singleton + helper centralizado). Nenhum consumer le ainda — Fase 11 introduz `lead_in_group()`. A estrategia de validacao reflete isso:

**Layers:**

1. **Unit tests com mocks (Plan 05 Tasks 1+2)** — cobertura do helper e do cache em isolacao. Mock Supabase RPC, sem dependencia de DB real. Custo: ~2s por arquivo. Garantia: regressao em refactor do helper/cache e detectada pre-deploy.

2. **Smoke SQL no Supabase Studio (Plan 02 Task 2 — checkpoint humano)** — aplica migration 004 e valida RPC com payload real. Garantia: schema + RPC + RLS funcionam end-to-end no Postgres de prod.

3. **Smoke import + grep ortogonal (Plan 03 Task 2 + Plan 04 Task 3)** — confirma que patches em grupo_webhook.py / agente.py / leads.py nao quebram imports nem regridem fixes v2.1 / fixes 08/06. Garantia: integracao com codigo existente preservada.

4. **Smoke manual em prod (Plan 05 Task 5 — checkpoint humano)** — pos-deploy: `/version` confirma redeploy real, `/admin/grupo-membership/health` confirma persistencia + cache live, observabilidade de logs `[MEMB-WRITE]` por 24h. Garantia: 3 paths escrevem em prod conforme esperado.

**Anti-patterns ativamente evitados:**

- Nenhum teste E2E com Evolution API real (caro + flaky) — paths sao validados via smoke logs em prod
- Nenhum teste de RLS no pytest (Supabase service_role bypassa RLS no client de teste) — RLS validada manualmente no Studio
- Nenhum teste de TTL real (`TTLCache` timing-based, flaky em CI) — comportamento `clear_all()` substitui

## Test Matrix

| Test Name | File | Type | Covers REQ-IDs | Layer |
|-----------|------|------|----------------|-------|
| `test_upsert_basico_insert` | tests/test_grupo_membership_upsert.py | unit (mock RPC) | MEMB-01, MEMB-06 | Helper smoke — was_insert=True path |
| `test_upsert_segundo_call_eh_update` | tests/test_grupo_membership_upsert.py | unit (mock RPC) | MEMB-01, MEMB-06 | Idempotencia — was_update=True path |
| `test_invalida_cache_apos_upsert` | tests/test_grupo_membership_upsert.py | unit (helper + cache) | MEMB-06, PROBE-CACHE-01 | Write-through cache invalidation (Pitfall 2) |
| `test_telefone_e_lid_nulos_retorna_invalid` | tests/test_grupo_membership_upsert.py | unit (mock) | MEMB-06 | Input validation guard — RPC nunca chamada |
| `test_upsert_out_of_order_noop` | tests/test_grupo_membership_upsert.py | unit (mock RPC) | MEMB-01, MEMB-06 | Out-of-order guard (Pitfall 4) — was_insert=False, was_update=False |
| `test_parse_evolution_timestamp_4_shapes` | tests/test_grupo_membership_upsert.py | unit (puro) | MEMB-02, MEMB-03 | Parser timestamp — epoch s, epoch ms, ISO, None |
| `test_set_get_basic` | tests/test_probe_cache.py | unit (puro) | PROBE-CACHE-01 | TTLCache set + get + stats |
| `test_invalidate_removes_and_counts` | tests/test_probe_cache.py | unit (puro) | PROBE-CACHE-01 | invalidate() retorna count correto + metric |
| `test_clear_for_group` | tests/test_probe_cache.py | unit (puro) | PROBE-CACHE-01 | Bulk invalidate por (empresa, grupo) |
| `test_multi_tenant_isolation` | tests/test_probe_cache.py | unit (puro) | PROBE-CACHE-01 | Cross-tenant isolation (T-10-03) |
| `test_set_none_silently_rejected` | tests/test_probe_cache.py | unit (puro) | PROBE-CACHE-01 | None nao cacheado (evita hit/miss ambiguity) |
| `test_lid_lowercase_normalization` | tests/test_probe_cache.py | unit (puro) | PROBE-CACHE-01 | Case-insensitive lid em _make_key |
| Smoke SQL upsert via Studio | 10-02 Task 2 (checkpoint) | manual integration | MEMB-01 | RPC retorna was_insert + was_update conforme esperado |
| Smoke SQL RLS via Studio (anon bloqueado) | 10-02 Task 2 + 10-05 Task 5 (checkpoint) | manual integration | MEMB-01 | RLS service_role-only ativa (T-10-02) |
| Smoke import grupo_webhook | 10-03 Task 2 | manual sanity | MEMB-02 | Modulo importa pos-patch |
| Smoke import agente + leads | 10-04 Task 3 | manual sanity | MEMB-03, MEMB-04 | Modulos importam pos-patch |
| Endpoint /admin/grupo-membership/health | 10-05 Task 3 + Task 5 (curl) | manual integration | MEMB-01, PROBE-CACHE-01 | Healthcheck retorna JSON com 4 chaves |
| Logs `[MEMB-WRITE]` em prod 24h | 10-05 Task 5 (observabilidade) | manual smoke | MEMB-02, MEMB-03, MEMB-04 | 3 fontes (webhook_add, messages_upsert, create_group) aparecem em logs |

## Coverage Matrix (REQ → Test)

| REQ ID | Covered By | Layer |
|--------|------------|-------|
| MEMB-01 (schema + RPC) | Smoke SQL Studio (10-02 T2) + endpoint health (10-05 T3) | manual + integration |
| MEMB-02 (Path 1 webhook ADD) | Smoke import (10-03 T2) + logs prod (10-05 T5) | manual + observabilidade |
| MEMB-03 (Path 2 MESSAGES_UPSERT) | Smoke import (10-04 T3) + logs prod (10-05 T5) + parse_evolution_timestamp_4_shapes | manual + unit |
| MEMB-04 (Path 3 createGroup) | Smoke import (10-04 T3) + logs prod (10-05 T5) | manual + observabilidade |
| MEMB-06 (helper centralizado) | 5 dos 6 testes em test_grupo_membership_upsert.py | unit (mock) |
| PROBE-CACHE-01 (TTLCache standalone) | 6 dos 6 testes em test_probe_cache.py + write-through em test_invalida_cache_apos_upsert | unit (puro + integration helper) |

PROBE-COALESCE-01 esta deferred pra Fase 11 (materializa com consumer `lead_in_group()` — coalescing so faz sentido quando ha consumer concorrente).

## Out-of-Scope Validations (flagged pra Fase 11+)

- Performance benchmarks de TTLCache sob carga (Pitfall 10 ja mitigado via maxsize=512)
- E2E test com Evolution API real disparando GROUP_PARTICIPANTS_UPDATE
- Webhook signature validation (Pitfall 14 — flag pra Fase 12)
- asyncio.Lock coalescing em `lead_in_group()` (PROBE-COALESCE-01 — Fase 11)
- Backfill de leads existentes (`probe_backfill` fonte declarada no SQL CHECK constraint mas nao executada nesta fase)

## Success Criteria

Validacao desta fase considerada completa quando:

- [ ] 12 testes unit green (`pytest tests/test_grupo_membership_upsert.py tests/test_probe_cache.py -v` retorna `12 passed`)
- [ ] 4+ testes v2.1 ainda green (zero regressao em qualificacao_lock_phase7, verificar_lead_no_grupo_phase3, agente_fixes, calendar_buffer)
- [ ] Smoke SQL no Supabase Studio: RPC retorna was_insert/was_update conforme esperado + RLS bloqueia anon
- [ ] Smoke imports pos-patch: 3 modulos (grupo_webhook, agente, leads) importam sem erro
- [ ] `curl /version` retorna `2026-06-09-grupo-membership-v2-fundacao`
- [ ] `curl /admin/grupo-membership/health` retorna JSON com 4 chaves
- [ ] Logs prod 24h pos-deploy: 3 fontes (webhook_add, messages_upsert, create_group) confirmadas em pelo menos 1 evento real
