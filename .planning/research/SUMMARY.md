# Research Summary — Milestone v2.2 Webhook-First Grupo Membership

**Project:** Leadflow Backend (FastAPI + APScheduler + Supabase + Evolution API)
**Milestone:** v2.2 — Inverter fonte da verdade probe→webhook via tabela materializada `grupo_membership`
**Synthesized:** 2026-06-09
**Overall confidence:** HIGH

## Executive Summary

A milestone v2.2 nasce porque a v2.1 (Grupo Robusto, entregue 20/05) deixou o probe Evolution como **fonte primária** da decisão `lead_in_group`. Quando Evolution mente ou demora 60-180s pra propagar membros (4+ casos do 08/06: Ana Carla, Rosânia, Fernanda, Valquíria + 553891500357 09/06), o probe retorna falso negativo, aquec é desviado pro DM. A inversão arquitetural: **webhook GROUP_PARTICIPANTS_UPDATE → tabela `grupo_membership` é primária; probe vira fallback com retry exponencial async (30s/2min/5min) + cache 5min**. Migration cirúrgica sobre infra existente single-worker Easypanel — **não** introduz Redis, Celery ou nova coluna em `leads`.

Os 4 researchers convergem em **HIGH confidence**. **1 nova dependência** (`cachetools>=5.5.0`, ~6kB pure-python). **1 nova tabela** (`grupo_membership`); audit log reusa `conversas`. **6 arquivos novos + 8 modificados**. **5 fases consolidadas (10-14)**, começando por schema, terminando em test regression + doc.

O risco principal não está em código novo — está em **integração com camadas existentes**: os 6 fixes paliativos do 08/06 **não podem ser regredidos**. O pitfall mais crítico, descoberto pelo PITFALLS researcher e ratificado por FEATURES: **webhook GROUP_PARTICIPANTS_UPDATE NÃO dispara para participants vindos do POST /group/create**. Sem **3 paths de escrita** (webhook ADD + MESSAGES_UPSERT + createGroup response), o caso Ana Carla repete identicamente.

## Key Findings

### STACK (HIGH)
- **1 nova dep:** `cachetools>=5.5.0,<6.0.0` (~6kB pure-python)
- Reusa: FastAPI 0.115.0, APScheduler 3.10.4, supabase-py>=2.18, httpx 0.27, Python 3.13, Postgres Supabase
- Mecanismos: UPSERT `ON CONFLICT (empresa_id, grupo_jid, COALESCE(telefone, lid))` + comparação por `messageTimestamp`; APScheduler `add_job(trigger='date', run_date=...)` com `replace_existing=True`; `TTLCache(maxsize=256-512, ttl=300)` + `RLock`; marker `GRUPO_STATE_CHANGE` em `conversas`
- **Anti-stack:** Redis, Celery, ARQ, SQLAlchemy, coluna `leads.lid_whatsapp`, tabela `grupo_audit_log`

### FEATURES (HIGH)
- **Table-stakes (7):** MEMB-01, MEMB-02, MEMB-03, MEMB-04, PROBE-RETRY-01, LEAVE-01, LEAVE-02
- **Differentiators (3):** PROBE-CACHE-01, FSM-AUDIT-01, FSM-AUDIT-02
- **Tests (6):** TEST-V2-G1..G5 + DOC-V2-G1 (G5 **bloqueado** em trace do 553891500357)
- **Anti-features:** sem `leads.lid_whatsapp`, Redis, reescrita FSM/probe, backfill retroativo, multi-instance

### ARCHITECTURE (HIGH)
- 6 decisões arquiteturais, **6 NEW files** (migration 004, grupo_membership.py, probe_cache.py, probe_coalesce.py + 3 test files) + **8 MODIFIED files** (grupo_webhook.py, grupo_state.py, grupo_fallback.py, confirmacao_agendamento.py, warmup_grupo.py, admin.py, leads.py, requirements.txt)
- `lead_in_group()` é NOVA função em `app/services/grupo_membership.py` com decision tree (tabela → cache → probe → janela stale 6min)
- Retry exponencial = job APScheduler separado (`probe_retry_{ag}_{attempt}`), NÃO wrap em `ativar_fallback_se_necessario` (já tem 450 linhas, 8 blocos aninhados)
- Cache singleton com `RLock` (defensivo mesmo em single-worker)
- Migrar 6 chamadas de `verificar_lead_no_grupo` em `grupo_fallback.py` (linhas 251, 311, 337, 477, 624, 1173, 1256) → `lead_in_group()`

### PITFALLS (HIGH)
**7 críticos (causam regressão dos 5 casos motivadores):**
1. Webhook NÃO dispara pra participants do createGroup → **3 paths de escrita obrigatórios**
2. Cache mascarando falha de persistência → write-through + healthcheck `/health/grupo-membership`
3. Retry converge antes do webhook (Rosânia T+138s) → `max_wallclock` absoluto, não só `max_retries`
4. Grupo órfão de instância antiga (Fernanda) → **`instance_key` column** no schema
5. Job retry 47h late (Valquíria) → `max_age_seconds` no handler + manter RECOVERY-AQUEC-01
6. Race webhook ADD escrevendo + dispatcher lendo → UPSERT atômico + advisory lock no read path
7. FSM transição não-monotônica via caller esquecido → entrypoint único + grep CI check + `caller` argumento obrigatório

**Compatibilidade não-negociável com fixes 08/06:** AQUEC-FLOOR-01 (180s), ALERTA-GRUPO-01, PROBE-BYPASS-01, GRUPO-REUSO-01, RECOVERY-STARTUP-01, RECOVERY-AQUEC-01 — **todos mantidos ativos** em v2.2.

## Cross-Cutting Concerns

1. **Idempotência forte:** UPSERT com `messageTimestamp` do payload (não `NOW()` servidor); comparação `EXCLUDED.entrou_em > grupo_membership.atualizado_em`
2. **3 paths de escrita em grupo_membership:** webhook ADD + MESSAGES_UPSERT match @lid + **escrita direta no callsite createGroup response** (insight crítico do PITFALLS researcher)
3. **Schema com `instance_key`:** sem isso, caso Fernanda repete silenciosamente. Query filtra `WHERE instance_key = empresas.instance_key_atual`
4. **Retry com `max_age_seconds` absoluto:** complementa `max_retries` para cobrir Valquíria + Rosânia
5. **FSM audit em `conversas`:** ~150 rows/dia (desprezível); `caller` argumento obrigatório sem default
6. **Anti-features explícitas:** sem Redis, sem Celery, sem `leads.lid_whatsapp`, sem backfill, sem nova tabela audit, sem reescrita FSM/probe

## Implications for Roadmap — 5 Fases Consolidadas (10-14)

**Reconciliação:** Features sugeria 4 fases (10-13), Architecture sugeria 5 (10-14), Pitfalls sugeria 7 (10-16). Architecture (5 fases) escolhida como base; pitfalls viram acceptance criteria por fase.

### Fase 10 — Schema + Webhook Write (3 paths) + Cache standalone
- MEMB-01 (com `instance_key` column), MEMB-02 (Path 1 webhook + **Path 3 createGroup direct write**), MEMB-03 (Path 2 MESSAGES_UPSERT), PROBE-CACHE-01
- Avoids pitfalls: 1, 4, 6, 9, 10, 13, 14

### Fase 11 — `lead_in_group()` consumer + migrar fallback
- MEMB-04 + migrar 6 callsites em `grupo_fallback.py`
- Avoids: 2, 4, 6

### Fase 12 — Retry async + callers com margem
- PROBE-RETRY-01 com `max_age_seconds=600` absoluto; migrar `confirmacao_agendamento.py:291` + `_executar_timeout_grupo_aguardando`
- Avoids: 3, 5, 11, 12
- Flag: **LIGHT VALIDATION** — supabase-py `on_conflict` em partial unique index pode exigir RPC fallback

### Fase 13 — LEAVE + FSM audit + saiu_em consumers
- LEAVE-01, LEAVE-02, FSM-AUDIT-01, FSM-AUDIT-02
- Avoids: 7, 9, 15

### Fase 14 — Test regression suite + doc
- TEST-V2-G1..G5 + DOC-V2-G1 + refactor incremental callers de `set_grupo_state`
- Avoids: 17, 18
- Flag: **USER INPUT NEEDED** — TEST-V2-G5 bloqueado em trace do 553891500357

## Confidence Assessment

| Area | Confidence |
|---|---|
| Stack | HIGH |
| Features | HIGH |
| Architecture | HIGH |
| Pitfalls | HIGH |

**MEDIUM em pontos específicos:**
- supabase-py `on_conflict` em partial index (spike Phase 10)
- coalescing via `asyncio.Lock`
- FSM-AUDIT-01 risco de break de transição rara
- TEST-V2-G5 bloqueado em dados do incidente

## Gaps to Address During Planning

1. **TEST-V2-G5 trace** — user precisa fornecer timestamps + payloads webhook + conversas do 553891500357 antes da Fase 14
2. **supabase-py `on_conflict` em partial unique index** — Phase 10 spike de 5min antes do schema final; fallback é RPC function SQL
3. **`instance_key` source of truth** — confirmar onde mora (`empresas.instance_key_atual` vs `config_apis.evolution_key`); pode exigir column add
4. **Callsite exato do createGroup response (Path 3)** — ARCHITECTURE não mapeia; identificar em kickoff Fase 10 (provavelmente `grupo_fallback.py` criação ou helper dedicado)
5. **Decisão APScheduler persistence** — in-memory vs Postgres jobstore; PROJECT.md L122 diz "in-memory suficiente" — confirmar com user antes Fase 12
6. **Multi-tenant cache isolation** — confirmar `cache_key` inclui `empresa_id`
