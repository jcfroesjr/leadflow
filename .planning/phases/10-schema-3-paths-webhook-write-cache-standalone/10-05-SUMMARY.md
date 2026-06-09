---
plan: 10-05
phase: 10-schema-3-paths-webhook-write-cache-standalone
title: Wave 4 — testes pytest + healthcheck endpoint + BUILD_VERSION bump + smoke deploy
status: completed
completed_at: 2026-06-09T18:30:00-03:00
wave: 4
autonomous: false
checkpoints_resolved:
  - task: 5
    type: human-action
    resolution: "User confirmou aprovado — BUILD_VERSION em prod, healthcheck retornando JSON válido, RLS smoke OK (service_role insert funciona, anon SELECT bloqueado), idempotência validada na Wave 2 (count=1)"
commits:
  - hash: 3ee7c2f
    message: "test(10-05): add 6 pytest tests for grupo_membership helper"
    task: 1
  - hash: 038e39e
    message: "test(10-05): add 6 pytest tests for probe_cache singleton"
    task: 2
  - hash: 55e278d
    message: "feat(10-05): add GET /admin/grupo-membership/health skinny endpoint"
    task: 3
  - hash: 86cd509
    message: "chore(10-05): bump BUILD_VERSION to 2026-06-09-grupo-membership-v2-fundacao"
    task: 4
key_files:
  created:
    - leadflow-backend/tests/test_grupo_membership_upsert.py
    - leadflow-backend/tests/test_probe_cache.py
  modified:
    - leadflow-backend/app/routers/admin.py
    - leadflow-backend/app/main.py
---

## Objective Recap

Verificação + observability skinny + ship. Fecha Fase 10 entregando:
- 12 testes pytest (6 helper + 6 cache) cobrindo idempotência, out-of-order, instance_key filter, parse_evolution_timestamp, multi-tenant isolation, lid normalization
- Endpoint healthcheck pra detectar cache mascarando falha de persistência
- BUILD_VERSION rastreável pro deploy
- Smoke manual final em prod

## What Was Built

### 1. Testes pytest — helper (commit `3ee7c2f`)

`tests/test_grupo_membership_upsert.py` (182 linhas, 6 testes):
- `test_upsert_basico_insert` — primeira chamada retorna `was_insert=true`
- `test_upsert_out_of_order_noop` — msg antiga não sobrescreve msg nova (out-of-order guard)
- `test_invalida_cache_apos_upsert` — write-through atomic: cache invalidado APÓS RPC success
- `test_get_instance_key_le_empresa` — lê `empresas.evolution_instancia` corretamente
- `test_parse_evolution_timestamp_epoch_seconds` — epoch s (int)
- `test_parse_evolution_timestamp_ms_iso_fallback` — epoch ms, ISO string, fallback utcnow

### 2. Testes pytest — cache (commit `038e39e`)

`tests/test_probe_cache.py` (135 linhas, 6 testes):
- `test_set_get_basic` — happy path get/set
- `test_invalidate_removes_and_counts` — invalidate remove + incrementa stat
- `test_clear_for_group` — limpa todas entries de um grupo
- `test_multi_tenant_isolation` — empresa A não vê cache da empresa B (chave inclui empresa_id)
- `test_set_none_silently_rejected` — None não é cacheado
- `test_lid_lowercase_normalization` — '@LID' e '@lid' batem como mesma chave

### 3. Endpoint skinny (commit `55e278d`)

`GET /admin/grupo-membership/health` em `app/routers/admin.py` (+80 linhas):

```json
{
  "total_rows": 0,
  "last_write_at": null,
  "writes_by_source_24h": {},
  "cache_stats": { "size": 0, "hits": 0, "misses": 0, ... },
  "phase": "10-fundacao"
}
```

Auth via header `X-Admin-Key` (mesmo padrão dos outros endpoints admin). Full healthcheck (com alertas de "0 inserts em horário ativo" etc.) virá em Fase 14.

### 4. BUILD_VERSION bump (commit `86cd509`)

`app/main.py:239` mudado de `2026-06-08-aquec-recovery-janela-6h` → **`2026-06-09-grupo-membership-v2-fundacao`**. Permite confirmar via `/version` que o deploy subiu.

### 5. Smoke deploy (Task 5 — user resolved)

User confirmou em prod:
- ✅ `/version` retorna `2026-06-09-grupo-membership-v2-fundacao`
- ✅ `/admin/grupo-membership/health` retorna JSON válido
- ✅ RLS smoke OK (anon bloqueado, service_role autorizado)
- ✅ Idempotência da RPC já validada na Wave 2 (count=1 após 2 upserts)

## Verification

✓ 12 testes pytest criados (mock-based, sem Supabase real)
✓ Endpoint healthcheck responde em prod
✓ BUILD_VERSION rastreável (deploy 2026-06-09-grupo-membership-v2-fundacao confirmado)
✓ Smoke RLS confirma policy service_role-only
✓ Nada regredido — todos os 6 fixes 08/06 + v2.1 Phases 3-9 + camadas 18-19/05 intactos

## What This Enables

**Fase 10 está COMPLETA** — fundação webhook-first viva em prod, escrevendo em real time via 3 paths independentes (webhook ADD, MESSAGES_UPSERT, createGroup direct). Próximos passos:

- **Fase 11** consome a tabela via `lead_in_group()` + migra 6 callsites de `verificar_lead_no_grupo` em `grupo_fallback.py`
- **Fase 12** adiciona retry exponencial async pra cobrir Rosânia (T+138s) e Valquíria (47h late)
- **Fase 13** LEAVE handler + FSM audit monotônico
- **Fase 14** suite testes regressão dos 5 casos motivadores

## Non-Regression Guards (Final Wave Check)

NÃO TOCADO em nenhuma das tasks:
- 6 fixes 08/06: AQUEC-FLOOR-01, ALERTA-GRUPO-01, PROBE-BYPASS-01, GRUPO-REUSO-01, RECOVERY-STARTUP-01, RECOVERY-AQUEC-01
- v2.1 Phases 3-9 (LID-01..08, ADMIN-01..04, QLOCK-01..04, TEST-G1..G6)
- Camadas 18-19/05 (Fase 1 sem presunção @lid, Fix 19/05 FSM=ATIVO revalida)
- Markers `LEAD_LID`, `GRUPO_LEAD_ENTROU_CRIACAO`, `GRUPO_AGUARDANDO_ENTRADA`, etc.
