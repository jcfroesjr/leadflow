# Technology Stack — Milestone v2.2 Webhook-First grupo membership

**Project:** Leadflow Backend
**Milestone:** v2.2 — Identificação Definitiva de Lead no Grupo (Webhook-First)
**Researched:** 2026-06-09
**Overall confidence:** HIGH

---

## Scope Note

This research covers ONLY incremental stack additions for v2.2 capabilities:

1. Tabela materializada `grupo_membership` (schema/index choices)
2. Probe retry exponencial 30s/2min/5min (mechanism)
3. Cache in-memory 5min TTL (library choice)
4. Audit log de FSM transitions (storage strategy)
5. Webhook handler reliability (idempotency mechanism)

Stack validado em prod (FastAPI 0.115.0, APScheduler 3.10.4, supabase-py >=2.18, httpx 0.27, Python 3.13, Postgres via Supabase) **não é alterado**. v2.2 reusa toda a infra existente.

---

## TL;DR — Decision Matrix

| Capability | Recommendation | Library/Mechanism | New Dep? | Confidence |
|------------|----------------|-------------------|----------|------------|
| Materialized membership table | Postgres table + 2 indexes | Supabase (existente) | No | HIGH |
| Probe async retry 30s/2min/5min | APScheduler `add_job(trigger='date', run_date=...)` one-shot | apscheduler 3.10.4 (existente) | No | HIGH |
| Cache in-memory 5min TTL | `cachetools.TTLCache` + `threading.RLock` | **cachetools (NEW, ~6kB)** | YES (1) | HIGH |
| FSM audit log | Marker `GRUPO_STATE_CHANGE:...` em `conversas` (mesma tabela existente) | Supabase (existente) | No | HIGH |
| Webhook idempotency | Unique constraint `(grupo_jid, telefone, evento, message_id)` na `grupo_membership` + UPSERT `ON CONFLICT DO UPDATE` | Postgres (existente) | No | HIGH |
| Probe coalescing (concorrência) | `asyncio.Lock` por chave `(grupo_jid, telefone)` + futuro compartilhado | stdlib (existente) | No | HIGH |

**Total novas dependências: 1** (`cachetools`).

---

## 1. Persistence — `grupo_membership` Table

### Recommended Schema

```sql
CREATE TABLE grupo_membership (
    id BIGSERIAL PRIMARY KEY,
    empresa_id UUID NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    grupo_jid TEXT NOT NULL,                    -- "120363xxx@g.us"
    telefone TEXT NOT NULL,                     -- normalizado E.164 sem '+', BR 12 ou 13 dig
    lid TEXT NULL,                              -- "xxxxxx@lid" se conhecido
    entrou_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    saiu_em TIMESTAMPTZ NULL,
    fonte TEXT NOT NULL,                        -- 'GROUP_PARTICIPANTS_UPDATE' | 'MESSAGES_UPSERT' | 'BACKFILL' | 'CREATE_GROUP'
    last_event_id TEXT NULL,                    -- message_id do webhook que escreveu (idempotência)
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Único: 1 row vivo por (empresa, grupo, telefone) — UPSERT alvo
CREATE UNIQUE INDEX uq_grupo_membership_alive
    ON grupo_membership (empresa_id, grupo_jid, telefone)
    WHERE saiu_em IS NULL;

-- Lookup primário (lead_in_group): empresa + telefone + grupo + alive
CREATE INDEX idx_grupo_membership_lookup
    ON grupo_membership (empresa_id, telefone, grupo_jid)
    WHERE saiu_em IS NULL;

-- Lookup por @lid (webhook MESSAGES_UPSERT chega com lid, precisa correlacionar)
CREATE INDEX idx_grupo_membership_lid
    ON grupo_membership (empresa_id, grupo_jid, lid)
    WHERE lid IS NOT NULL AND saiu_em IS NULL;

-- Idempotência de eventos webhook
CREATE UNIQUE INDEX uq_grupo_membership_event
    ON grupo_membership (grupo_jid, telefone, last_event_id)
    WHERE last_event_id IS NOT NULL;
```

### Rationale

- **`empresa_id` FK + RLS**: alinhado com migration 003 (RLS hardening 08/06).
- **`saiu_em` nullable em vez de DELETE row**: preserva histórico — caso Fernanda (grupo órfão) precisa diferenciar "nunca entrou" de "saiu". Permite query "ativo agora" via `WHERE saiu_em IS NULL`.
- **Partial index `WHERE saiu_em IS NULL`**: reduz tamanho do índice + acelera o caso comum (consulta de membros ativos). Postgres docs ratificam padrão. [PostgreSQL Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html)
- **`fonte` enum-like**: rastreia origem da row (debug + decisão se confiar mais em CREATE_GROUP fresh vs MESSAGES_UPSERT). Não usar `ENUM` type Postgres — `TEXT` + check constraint é mais flex pra adicionar fontes depois.
- **`last_event_id` único partial**: idempotência ao reprocessar webhook (Evolution às vezes redispara). `UPSERT ... ON CONFLICT (last_event_id) DO NOTHING` torna handler resiliente.
- **`lid` separado de `telefone`**: matcher alternativo quando webhook MESSAGES_UPSERT chega com `@lid` mas sem telefone resolvido. Permite backfill quando `@lid` é descoberto depois.

### Integration with Existing supabase-py

```python
# UPSERT idempotente — usa unique constraint pra no-op em retry
sb.table("grupo_membership").upsert({
    "empresa_id": empresa_id,
    "grupo_jid": grupo_jid,
    "telefone": telefone,
    "lid": lid,
    "fonte": "GROUP_PARTICIPANTS_UPDATE",
    "last_event_id": message_id,
    "entrou_em": "now()",
    "atualizado_em": "now()",
}, on_conflict="grupo_jid,telefone,last_event_id").execute()
```

**Limitação supabase-py atual**: `on_conflict` em partial unique indexes pode exigir UUID separado ou condição duplicada na query. Validar em Phase 10 — fallback é executar via RPC function SQL.

### Alternatives Considered

| Alternative | Why Not |
|-------------|---------|
| Coluna `lid_whatsapp` em `leads` | v2.2 já decidiu N:N (lead × grupo) — coluna escalar não modela isso. PROJECT.md L118. |
| Marker `LEAD_IN_GROUP:{jid}` em `conversas` | v2.1 já tentou — não permite query eficiente "quem está no grupo X" (full scan markers). |
| Tabela `grupo_evento` append-only + view materializada | Overengineering. CRUD direto em `grupo_membership` resolve com mesma idempotência via unique constraint. |
| Postgres `JSONB` array em `grupos.membros` | Não atômico (UPDATE...SET membros = jsonb_set tem race), indexável só com GIN (lento). |

---

## 2. Probe Retry — Async Exponential Backoff

### Recommendation: APScheduler one-shot `date` trigger

APScheduler 3.10.4 (já em prod) suporta agendamento one-shot via `date` trigger. Não precisa Celery/ARQ/Redis. Padrão validado pela docs APScheduler. [APScheduler User Guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html)

```python
# app/services/probe_retry.py
from datetime import datetime, timedelta
from app.scheduler import scheduler

PROBE_DELAYS = [30, 120, 300]  # segundos: 30s, 2min, 5min

async def _executar_probe_retry(empresa_id: str, telefone: str, grupo_jid: str, tentativa: int):
    # 1. consulta grupo_membership PRIMEIRO (pode ter chegado webhook entre tentativas)
    if await lead_in_group_db(empresa_id, telefone, grupo_jid):
        return  # webhook chegou, encerra retry
    # 2. probe live Evolution
    ok = await verificar_lead_no_grupo_evolution(...)
    if ok:
        # backfill row em grupo_membership com fonte='PROBE_RETRY'
        await registrar_membro(...)
        return
    # 3. agenda próxima tentativa, se ainda há
    if tentativa + 1 < len(PROBE_DELAYS):
        scheduler.add_job(
            _executar_probe_retry,
            trigger="date",
            run_date=datetime.now() + timedelta(seconds=PROBE_DELAYS[tentativa + 1]),
            args=[empresa_id, telefone, grupo_jid, tentativa + 1],
            id=f"probe_retry:{grupo_jid}:{telefone}:{tentativa+1}",
            replace_existing=True,  # idempotência
            max_instances=1,
            misfire_grace_time=None,
        )

def enfileirar_probe_retry(empresa_id: str, telefone: str, grupo_jid: str):
    scheduler.add_job(
        _executar_probe_retry,
        trigger="date",
        run_date=datetime.now() + timedelta(seconds=PROBE_DELAYS[0]),
        args=[empresa_id, telefone, grupo_jid, 0],
        id=f"probe_retry:{grupo_jid}:{telefone}:0",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=None,
    )
```

### Rationale

- **`AsyncIOScheduler` (existente em `app/scheduler.py:5`)**: mesma event loop do FastAPI, sem cross-thread. Padrão já em uso (cleanup_expired_locks roda assim).
- **`trigger='date'` one-shot**: APScheduler 3.x suporta agendamento único; "date" reagenda da próxima vez que `_executar_probe_retry` decidir. Sem necessidade de `interval` + cancel manual.
- **`replace_existing=True` + `id` determinístico**: idempotência. Se webhook GROUP_PARTICIPANTS_UPDATE chegar entre tentativas e marcar membership, próxima tentativa vê db e encerra (early exit). Re-enfileiramento por handler concurrent não duplica.
- **`max_instances=1`**: defesa adicional contra concorrência.
- **`misfire_grace_time=None`**: alinhado com padrão do `scheduler.py:5` — preferimos disparar atrasado a descartar.

### Alternatives Considered

| Alternative | Why Not |
|-------------|---------|
| `asyncio.sleep(30); await probe(); asyncio.sleep(120); ...` | Bloqueia coroutine por até 7.5min. Worker single-instance — não escala se 10 leads esperando. |
| Celery + Redis | **Out of scope** (PROJECT.md L121-122). 1 worker Easypanel não justifica complexidade. |
| ARQ + Redis | Mesma razão — Redis out-of-scope. |
| `BackgroundTasks` do FastAPI | Vinculado ao request lifecycle — se request termina antes do delay, task pode morrer (depende do uvicorn worker reload). |
| `asyncio.create_task` + `asyncio.sleep` | Sem persistência se processo restartar mid-flight (Easypanel redeploy mata todas tasks). APScheduler `MemoryJobStore` tem o mesmo problema, mas é o trade-off aceito (PROJECT.md L122: "in-memory é suficiente"). |
| APScheduler `IntervalTrigger` com `end_date` | Mais código de gerenciar — `date` trigger one-shot reagendado é mais direto pra delays não-uniformes. |

**Persistência de retry**: APScheduler 3.10.4 padrão = `MemoryJobStore`. Restart do processo perde retries pendentes. Mitigação: webhook eventualmente chega e marca membership; recovery startup (já existente `ae2b141`) pode opcionalmente varrer leads em estado `AGUARDANDO_GRUPO` mais novos que 10min e re-enfileirar. Tratado como out-of-scope da Phase 10 (já flagged).

---

## 3. Cache In-Memory — 5min TTL

### Recommendation: `cachetools.TTLCache` + `threading.RLock`

**New dependency: `cachetools>=5.5.0`** (released May 2026, ~6kB pure-python, no native deps). [cachetools PyPI](https://pypi.org/project/cachetools/)

```python
# requirements.txt addition
cachetools>=5.5.0,<6.0.0
```

```python
# app/services/probe_cache.py
from cachetools import TTLCache
from threading import RLock

# 256 entries × 5min TTL → suficiente p/ pico 5-10 probes/min com folga
_probe_cache: TTLCache = TTLCache(maxsize=256, ttl=300)
_lock = RLock()

def cache_get(grupo_jid: str, telefone: str, lid: str | None) -> bool | None:
    key = (grupo_jid, telefone, lid or "")
    with _lock:
        return _probe_cache.get(key)

def cache_set(grupo_jid: str, telefone: str, lid: str | None, value: bool) -> None:
    key = (grupo_jid, telefone, lid or "")
    with _lock:
        _probe_cache[key] = value

def cache_invalidate(grupo_jid: str, telefone: str) -> None:
    """Invalida ao receber webhook (membership mudou — cache stale)."""
    with _lock:
        for k in list(_probe_cache.keys()):
            if k[0] == grupo_jid and k[1] == telefone:
                _probe_cache.pop(k, None)
```

### Rationale

- **`cachetools.TTLCache`**: maintained, current version 5.5.0, padrão Python community. Per-item TTL nativo. [cachetools docs](https://cachetools.readthedocs.io/)
- **`threading.RLock`**: `TTLCache` NÃO é thread-safe por default (issue #294 cachetools). Single-worker FastAPI ainda tem GIL, mas APScheduler executor pode rodar em thread — RLock é seguro. [Thread safety #294](https://github.com/tkem/cachetools/issues/294)
- **Não usar `@cached(cache=...)` decorator**: nossa função `verificar_lead_no_grupo` tem efeito colateral (mete probe Evolution + escreve marker) — cache em volta da função inteira complica invalidação. Cache manual de get/set é mais explícito.
- **`maxsize=256`**: ~10 grupos ativos × ~25 leads = 250 chaves no pior cenário. Margem de segurança. LRU evicta os menos usados.
- **Invalidação on-webhook**: quando GROUP_PARTICIPANTS_UPDATE chega, invalida cache pra forçar reconsulta. Caso contrário, valor stale poderia mascarar mudança.

### Alternatives Considered

| Alternative | Why Not |
|-------------|---------|
| `functools.lru_cache` | Não tem TTL nativo. Workarounds (timed_lru_cache) são frágeis. |
| Custom `dict` + manual expiry | Reinventar roda. `cachetools` é 6kB, testado, mantido. |
| `async-lru` | Async-aware mas adiciona dep + sem TTL nativo. |
| `aiocache` | Async-only, multi-backend (overkill). |
| Redis `SETEX` | **Out of scope** (PROJECT.md L121). |
| Sem cache | Probe Evolution custa 100-500ms + bandwidth Webshare proxy. Picos de 10-30 probes em janelas de 60s (aquec dispatch) bombardeiam API. Cache resolve em <1ms. |

### TTL Choice Rationale

- **5min curto suficiente** pra capturar mudança de membership "razoavelmente fresh" (webhook chega em <60s no caso normal, propagação Evolution máx 180s).
- **5min longo suficiente** pra evitar bombardear API em picos.
- Invalidação on-webhook reduz risco de stale a ~0 quando webhook funciona.
- Trade-off explícito: lead que sai do grupo + 0-300s de janela em que cache pode dizer "ainda dentro". Mitigado pelo handler LEAVE invalidar.

---

## 4. FSM Audit Log — Marker em `conversas`

### Recommendation: Marker existente, sem nova tabela

```python
# app/services/grupo_state.py — endurecer set_grupo_state existente
def set_grupo_state(empresa_id, telefone, novo_estado, reason, caller, override=False):
    estado_atual = get_grupo_state(...)

    # 1. Valida monotonicidade
    TRANSICOES_VALIDAS = {
        None: {"AGUARDANDO", "ATIVO"},
        "AGUARDANDO": {"FALLBACK_1_1", "ATIVO", "LEFT_GROUP"},
        "FALLBACK_1_1": {"ATIVO", "LEFT_GROUP"},
        "ATIVO": {"LEFT_GROUP"},  # ATIVO→AGUARDANDO bloqueado sem override
        "LEFT_GROUP": {"ATIVO"},  # re-entrou
    }
    if not override and novo_estado not in TRANSICOES_VALIDAS.get(estado_atual, set()):
        raise GrupoStateInvalidTransition(f"{estado_atual}→{novo_estado} bloqueado")

    # 2. Insere marker audit log
    marker = f"GRUPO_STATE_CHANGE:{estado_atual}:{novo_estado}:{reason}:{caller}"
    sb.table("conversas").insert({
        "empresa_id": empresa_id,
        "telefone": telefone,
        "role": "system",
        "conteudo": marker,
        "criado_em": "now()",
    }).execute()

    # 3. Atualiza marker FSM_ESTADO atual (existente em v2.1)
    ...
```

### Rationale

- **Reusa tabela `conversas` existente** + unique constraint de markers (PROJECT.md L75 — "23+ markers em conversas").
- **Sem nova tabela** = sem migration adicional pra audit (Phase 10 já tem migration `grupo_membership`).
- **Query natural por timeline**: audit log aparece intercalado com mensagens do lead — debug investiga 1 lugar só.
- **Idempotência**: unique constraint em `conversas` já existente (índice por `criado_em + telefone + conteudo`) previne duplicação.

### Alternatives Considered

| Alternative | Why Not |
|-------------|---------|
| Nova tabela `grupo_audit_log` | Overengineering pra v2.2. `conversas` já é o "event log" do lead. Pode-se extrair depois se virar problema. |
| Postgres `pg_audit` | Auditoria de schema/role-level, não de business logic. |
| Logger Python → arquivo | Volátil no Easypanel (container restart perde). |

---

## 5. Webhook Handler Reliability — Idempotência

### Recommendation: Postgres UPSERT com `last_event_id` + idempotência por marker em conversas

Já coberto na seção 1 (schema). Pontos chave:

1. **`message_id` do webhook Evolution** vira `last_event_id` na linha de `grupo_membership`.
2. **`UPSERT ON CONFLICT (last_event_id) DO NOTHING`** = retry/replay do webhook não duplica row.
3. **Marker `WEBHOOK_GRUPO_PROC:{message_id}` em conversas** (padrão v2.0 já usado) = handler completo idempotente.

### Concurrent Probe Coalescing (bonus)

Cenário: 3 jobs (aquec, notif D-1, confirmação) consultam `lead_in_group` no mesmo instante pro mesmo lead. Sem coordenação, 3 probes Evolution em paralelo.

**Solução com stdlib (sem nova dep):**

```python
# app/services/probe_coalesce.py
import asyncio
from typing import Dict, Tuple

_in_flight: Dict[Tuple[str, str, str], asyncio.Future] = {}
_lock = asyncio.Lock()

async def probe_coalesced(empresa_id, telefone, grupo_jid, probe_fn):
    key = (empresa_id, telefone, grupo_jid)
    async with _lock:
        if key in _in_flight:
            return await _in_flight[key]  # piggyback no probe em curso
        future = asyncio.get_event_loop().create_future()
        _in_flight[key] = future
    try:
        result = await probe_fn()
        future.set_result(result)
        return result
    except Exception as e:
        future.set_exception(e)
        raise
    finally:
        async with _lock:
            _in_flight.pop(key, None)
```

Stdlib `asyncio.Lock` + dict — zero dependências. AsyncIOScheduler executa tudo no mesmo event loop, então é seguro.

---

## Final requirements.txt Delta

```diff
 fastapi==0.115.0
 apscheduler==3.10.4
 supabase>=2.18.0,<3.0.0
 httpx==0.27.0
+cachetools>=5.5.0,<6.0.0
```

**1 nova dependência**, ~6kB, pure-python, zero native compile, mantida ativamente.

---

## What NOT to Add (explicit non-goals)

| Avoided | Reason |
|---------|--------|
| `redis` (cache/broker) | Out-of-scope PROJECT.md L121. Single-worker Easypanel — in-memory resolve. |
| `celery` | Out-of-scope. APScheduler 3.10.4 já cobre uso assíncrono. |
| `arq` | Mesma razão. Adicionaria Redis e service worker novo. |
| `sqlalchemy` | Toda persistência via supabase-py (REST). Manter consistência. |
| `pydantic-settings` | Configs já leem env direto. |
| `pgmq` (Postgres queue extension) | Não habilitado no Supabase managed. APScheduler suficiente. |
| `aiocache` | Multi-backend overkill pra 1 in-memory cache. |
| Nova tabela `grupo_audit_log` | `conversas` markers já cobre (v2.2 reusa padrão). |
| Coluna `leads.lid_whatsapp` | Decisão arquitetural N:N (tabela `grupo_membership`). |

---

## Integration Touchpoints (where new code lands)

| New File | Purpose | Talks To |
|----------|---------|----------|
| `migrations/004_grupo_membership.sql` | DDL tabela + 4 indexes | Postgres |
| `app/services/grupo_membership.py` | CRUD: `registrar_entrada`, `registrar_saida`, `lead_in_group_db`, `get_membros_ativos` | supabase-py |
| `app/services/probe_cache.py` | TTLCache wrapper (get/set/invalidate) | cachetools (NEW) |
| `app/services/probe_retry.py` | Enqueue retry chain via APScheduler | scheduler (existente), grupo_membership, evolution_router |
| `app/services/probe_coalesce.py` | Coalescing in-flight probes | asyncio (stdlib) |
| `app/services/grupo_state.py` (UPDATE) | Adiciona validação monotônica + audit marker | conversas via supabase-py |
| `app/routers/grupo_webhook.py` (UPDATE) | Handler ADD/REMOVE escreve em grupo_membership + invalida cache | grupo_membership, probe_cache |

Existente reaproveitado:
- `app/scheduler.py` — AsyncIOScheduler instance
- `app/services/lock.py` — não tocar
- `app/services/grupo_fallback.py:177` — `ativar_fallback_se_necessario` chama `lead_in_group` que ganha primeiro check DB
- `app/routers/grupo_webhook.py` — handler GROUP_PARTICIPANTS_UPDATE existente é ponto de extensão

---

## Sources

- [cachetools — PyPI](https://pypi.org/project/cachetools/) — latest 5.5.0, May 2026
- [cachetools — Read the Docs](https://cachetools.readthedocs.io/) — TTLCache API + thread safety note
- [cachetools thread safety #294](https://github.com/tkem/cachetools/issues/294) — confirms RLock required
- [APScheduler User Guide 3.x](https://apscheduler.readthedocs.io/en/3.x/userguide.html) — AsyncIOScheduler + date trigger
- [APScheduler API reference](https://apscheduler.readthedocs.io/en/master/api.html) — `add_job(trigger='date', run_date=...)`
- [PostgreSQL Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html) — `WHERE saiu_em IS NULL` pattern
- [PostgreSQL B-Tree Indexes](https://www.postgresql.org/docs/current/btree.html) — composite index ordering
- [PostgreSQL CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — unique partial index syntax
- Internal: `c:/Projetos/Leadflow/leadflow-backend/requirements.txt` (versões em prod)
- Internal: `c:/Projetos/Leadflow/leadflow-backend/app/scheduler.py:5` (AsyncIOScheduler config existente)
- Internal: `c:/Projetos/Leadflow/.planning/PROJECT.md` (L116-124 out-of-scope, L177-187 key decisions v2.2)

---

## Confidence Assessment

| Choice | Confidence | Verified Via |
|--------|------------|--------------|
| Postgres schema/indexes | HIGH | Official Postgres docs + existing migration patterns (003) |
| APScheduler retry pattern | HIGH | Existing in-prod usage (`app/scheduler.py`) + official docs |
| `cachetools.TTLCache` | HIGH | PyPI current + official docs + GitHub issue confirm thread safety caveat |
| FSM audit via marker | HIGH | Existing pattern (23+ markers em conversas, PROJECT.md L75) |
| Webhook idempotency UPSERT | HIGH | Standard Postgres pattern + existing dedup precedent (v2.0 DEDUP-01..03) |
| Coalescing via asyncio.Lock | MEDIUM | Stdlib pattern, not yet in codebase — validate em Phase 10 spike |
| supabase-py `on_conflict` on partial index | MEDIUM | Docs not explicit — may require RPC fallback. Validate em Phase 10. |
