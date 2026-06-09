---
plan: 10-02
phase: 10-schema-3-paths-webhook-write-cache-standalone
title: Foundation — migration 004 + helper grupo_membership + cache singleton
status: completed
completed_at: 2026-06-09T17:50:00-03:00
wave: 2
autonomous: false
checkpoints_resolved:
  - task: 2
    type: human-action
    resolution: "User aplicou migration 004 via Supabase Studio SQL Editor. Smoke test validado: count=1 após 2 UPSERTs idênticos (idempotência confirmada)."
commits:
  - hash: ce743ef
    message: "feat(10-02): migration 004 grupo_membership table + RPC upsert"
    task: 1
  - hash: 4662bbe
    message: "feat(10-02): add probe_cache singleton (TTLCache 512/300s + RLock)"
    task: 3
  - hash: 37eecdb
    message: "feat(10-02): add grupo_membership helper (upsert + instance_key + ts_parser)"
    task: 4
requirements_addressed:
  - MEMB-01
  - MEMB-06
  - PROBE-CACHE-01
key_files:
  created:
    - leadflow-backend/app/db/migrations/004_grupo_membership.sql
    - leadflow-backend/app/services/probe_cache.py
    - leadflow-backend/app/services/grupo_membership.py
  modified: []
---

## Objective Recap

Fundação webhook-first da v2.2:
- Tabela `grupo_membership` com `instance_key`, partial unique index, RLS service_role only
- RPC `upsert_grupo_membership` contorna limitação supabase-py com partial unique (UPDATE-then-INSERT-with-fallback)
- Helper Python centralizado `upsert_grupo_membership(...)` é o único write path
- Cache singleton standalone (`probe_cache.py`) com write-through invalidate em todo UPSERT

Nada consome ainda — Plans 03/04 fazem writes via helper, Fase 11 (`lead_in_group()`) consome para ler.

## What Was Built

### 1. Migration 004 (commit `ce743ef`)

**Arquivo:** `leadflow-backend/app/db/migrations/004_grupo_membership.sql` (117 linhas)

- **Tabela:** `grupo_membership(id BIGSERIAL, empresa_id UUID FK empresas, grupo_jid TEXT, telefone TEXT NULL, lid TEXT NULL, instance_key TEXT NOT NULL, entrou_em TIMESTAMPTZ, saiu_em TIMESTAMPTZ NULL, fonte TEXT CHECK, last_event_id TEXT NULL, criado_em, atualizado_em)`
- **Partial unique index:** `WHERE saiu_em IS NULL` em `(empresa_id, grupo_jid, COALESCE(telefone, lid))` — alvo do UPSERT
- **2 indexes de lookup:** por telefone + por lid (ambos partial WHERE saiu_em IS NULL)
- **RLS:** service_role only (mesmo padrão migrations 001/002/003)
- **RPC `upsert_grupo_membership`:** UPDATE-first-INSERT-fallback handling `unique_violation EXCEPTION` em race; out-of-order guard via `p_entrou_em >= atualizado_em` no UPDATE

**Smoke validado pelo user no Supabase Studio:**
- INSERT inicial: `was_insert=true, was_update=false`
- 2ª chamada idêntica: `was_insert=false, was_update=true`
- `count(*) = 1` (não duplicou — idempotência confirmada)

### 2. probe_cache.py singleton (commit `4662bbe`)

**Arquivo:** `leadflow-backend/app/services/probe_cache.py` (126 linhas)

**Publics:**
- `get(empresa_id, grupo_jid, telefone, lid) -> Optional[dict]` — incrementa hits/misses
- `set(empresa_id, grupo_jid, telefone, lid, value)` — incrementa writes
- `invalidate(empresa_id, grupo_jid, telefone, lid)` — chamado por helper write-through
- `clear_for_group(grupo_jid)` — limpa todas entries de um grupo (após REMOVE em Fase 13)
- `stats() -> dict` — métricas pra endpoint healthcheck Plan 05
- `clear_all()` — exposto APENAS pra fixture pytest

**Design:**
- `cachetools.TTLCache(maxsize=512, ttl=300)` — bounded + 5min TTL
- `threading.RLock` defensivo (single-worker Easypanel mas barato)
- Chave multi-tenant: `(empresa_id, grupo_jid, telefone_or_empty, lid_lower)` — isolamento via empresa_id como primeiro componente
- `lid` normalizado lowercase para evitar mismatch case-sensitive

### 3. grupo_membership.py helper (commit `37eecdb`)

**Arquivo:** `leadflow-backend/app/services/grupo_membership.py` (143 linhas)

**Publics:**
- `upsert_grupo_membership(sb, empresa_id, grupo_jid, telefone, lid, instance_key, entrou_em, fonte, last_event_id=None) -> dict` — único write path do projeto v2.2. Chama RPC via `sb.rpc(...).execute()`, invalida cache atomicamente **após** RPC success, loga `[MEMB-WRITE] source=... result=insert|update`
- `get_instance_key(sb, empresa_id) -> str` — lê `empresas.evolution_instancia` (fonte de verdade pra Fase 11)
- `parse_evolution_timestamp(raw) -> datetime` — parser defensivo 3 shapes:
  - int/float: epoch s ou ms (guard `> 10**12` → divide por 1000)
  - str: ISO via `datetime.fromisoformat(...)` com fallback `int(raw)` epoch
  - fallback: `datetime.utcnow()`

`fonte` validado contra CHECK constraint da tabela: `webhook_add | messages_upsert | create_group | admin_force | probe_backfill`.

## Verification

✓ Migration aplicada via Supabase Studio + smoke test passou (idempotência via RPC validada com `count=1`)
✓ probe_cache.py: 126 linhas, 6 publics + 1 private helper
✓ grupo_membership.py: 143 linhas, 3 publics
✓ Cache invalidation atomic post-RPC (write-through): `probe_cache.invalidate(...)` chamado APÓS `result.data` check
✓ Multi-tenant isolation: chave de cache inclui `empresa_id` como primeiro componente
✓ Pitfall 2 (cache mascarando falha de persistência) eliminado via write-through
✓ Pitfall 4 (grupo órfão Fernanda) coberto via coluna `instance_key`
✓ Pitfall 6 (race UPSERT vs read) coberto via atomicidade RPC + `unique_violation` handler

## What This Enables

**Plans 03 + 04 (Wave 3)** podem agora importar `upsert_grupo_membership` e `parse_evolution_timestamp` e fazer os 3 paths de escrita:
- Path 1 webhook GROUP_PARTICIPANTS_UPDATE add (grupo_webhook.py)
- Path 2 MESSAGES_UPSERT @lid capture (agente.py)
- Path 3 createGroup direct write (leads.py — resolve caso Ana Carla)

**Fase 11** vai criar `lead_in_group()` que consulta `grupo_membership` PRIMEIRO + usa probe_cache pra reduzir Evolution API calls.

## Non-Regression Guards

NÃO TOCADO:
- AQUEC-FLOOR-01, ALERTA-GRUPO-01, PROBE-BYPASS-01, GRUPO-REUSO-01, RECOVERY-STARTUP-01, RECOVERY-AQUEC-01
- v2.1 Phase 4 `_salvar_lead_lid`, Phase 7 `qualificacao_lock`
- Markers existentes em `conversas` (LEAD_LID, GRUPO_LEAD_ENTROU_CRIACAO, etc)

## Notes

- supabase-py limitação confirmada: tentar `.upsert(..., on_conflict="empresa_id,grupo_jid,COALESCE(...)")` quebra com "no unique or exclusion constraint matching the ON CONFLICT" → RPC SQL é o único caminho
- `parse_evolution_timestamp` shape real (epoch s vs ms) será logado em Plans 03/04 no primeiro webhook em prod — parser cobre os 3 shapes defensivamente até confirmação
- `last_event_id` mantido NULL na maioria dos casos — usado em Phase 13 LEAVE handler pra correlação webhook ADD/REMOVE
