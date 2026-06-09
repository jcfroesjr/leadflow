# Phase 10: Schema + 3 paths webhook write + cache standalone — Research

**Researched:** 2026-06-09
**Domain:** Postgres schema design + FastAPI webhook idempotency + in-memory cache singleton + APScheduler hooks (Leadflow backend, single-worker Easypanel)
**Confidence:** HIGH

## Summary

Esta fase entrega a **fundação infraestrutural** do milestone v2.2: a tabela materializada `grupo_membership`, três paths idempotentes de escrita nela (webhook ADD, MESSAGES_UPSERT, createGroup response direto) e o módulo de cache standalone (`probe_cache.py`) com coalescing assíncrono. Nada consome essas estruturas ainda — Fase 11 (`lead_in_group()` + migração de callsites) e Fase 12 (retry async) são as consumidoras. Isolar produção de consumo nesta fase **garante zero risco de regressão** dos 6 fixes paliativos do 08/06 e das 7 phases v2.1 já em prod.

O risco técnico real está concentrado em **dois pontos verificáveis com spike de minutos**: (1) `supabase-py` 2.18 + PostgREST **não suporta** `on_conflict` em partial unique index — error `"unique or exclusion constraint matching the ON CONFLICT"` é garantido. Workaround documentado por maintainer Supabase é RPC function SQL [VERIFIED: GitHub discussions/12565]. (2) Path 3 (`_criar_grupo_agendamento`) tem um callsite exato bem definido **após** `promover_admin_grupo` parsing (linhas 245-271 de `leads.py`), onde já existe o marker `GRUPO_LEAD_ENTROU_CRIACAO` — substitui/complementa esse bloco.

**Primary recommendation:** Schema via SQL migration aplicada manualmente no Supabase Studio (segue padrão de migrations 001-003). Helper UPSERT via **RPC function** (SQL) chamada de `app/services/grupo_membership.py` — contorna a limitação supabase-py. Path 3 integrado ao bloco "FIX 01/06 Ana Carla" já existente em `leads.py:263-271` (substitui o marker por UPSERT real, mantém o marker como backwards compat). Cache singleton com `cachetools.TTLCache(512, ttl=300)` + `threading.RLock` defensivo. Coalescing via `asyncio.Lock` por chave (sem dep nova).

<user_constraints>
## User Constraints (from CONTEXT.md)

> CONTEXT.md não foi gerado para esta fase (não houve `/gsd-discuss-phase`). Locked decisions vêm de STATE.md ("Decisions Log v2.2") + REQUIREMENTS.md (v2.2 Active).

### Locked Decisions (de STATE.md L106-118)

| Decisão | Justificativa |
|---|---|
| Tabela dedicada `grupo_membership` (não marker em conversas) | Relação N:N lead×grupo, queries eficientes por grupo_jid, suporta REMOVE/saiu_em explícito |
| Webhook = fonte primária, probe = fallback | v2.1 manteve probe como primário e falhou em 4+ casos do 08/06 |
| `instance_key` column no schema | Caso Fernanda (grupo órfão de instância antiga) não regride |
| 3 paths de escrita (webhook ADD + MESSAGES_UPSERT + createGroup direct) | Caso Ana Carla repete sem Path 3 — webhook não dispara para participants do POST /group/create |
| Cache in-memory `cachetools.TTLCache` (não Redis) | Single-worker Easypanel; 5-10 probes/min; in-memory suficiente |
| Continua phase numbering — v2.2 começa em Fase 10 | v2.1 terminou em Fase 9 |
| Sem backfill retroativo de `grupo_membership` | Grupos antigos seguem com markers atuais |

### Claude's Discretion

- Forma exata da RPC function SQL (parâmetros, return type, naming)
- Localização exata do callsite Path 3 (antes vs depois de `promover_admin_grupo` — research confirma DEPOIS)
- Estratégia de invalidação de cache (key-level vs group-level vs all)
- Granularidade do log estruturado `[MEMB-WRITE]` (campos mínimos)
- Forma exata do healthcheck preview (skinny em Fase 10 vs full em Fase 14)

### Deferred Ideas (OUT OF SCOPE Fase 10)

| Item | Vai para |
|---|---|
| `lead_in_group()` function + migração de 6 callsites | Fase 11 |
| `schedule_probe_retry` + `max_age_seconds=600` | Fase 12 |
| LEAVE handler (action=remove) | Fase 13 |
| FSM audit + `caller` arg obrigatório | Fase 13 |
| TEST-V2-G1..G5 regressão completa | Fase 14 |
| OBS-V2-G2 healthcheck `/health/grupo-membership` completo | Fase 14 (Fase 10 entrega só endpoint skinny) |
| Coluna `leads.lid_whatsapp` | Out-of-scope v2.2 inteiro |
| Reescrita probe/FSM/Redis/Celery | Out-of-scope v2.2 inteiro |
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MEMB-01 | Migration 004 — tabela `grupo_membership` com `instance_key`, partial unique index, RLS service_role only | §2 Schema design + §3 RPC workaround + §4 RLS strategy |
| MEMB-02 | Path 1 — webhook GROUP_PARTICIPANTS_UPDATE escreve em grupo_membership quando action=add | §5.1 Path 1 callsite + idempotency via `messageTimestamp` |
| MEMB-03 | Path 2 — webhook MESSAGES_UPSERT escreve quando msg de grupo + 1 lead aguardando + @lid não-mapped | §5.2 Path 2 strategy (reusa heurística v2.1 unique-aguardando) |
| MEMB-04 | Path 3 — `_criar_grupo_agendamento` (callsite createGroup response) escreve direto INSERT pro participant que entrou | §5.3 Path 3 callsite EXATO (`leads.py:245-271`) — DEPOIS de promover_admin parsing, JUNTO com marker GRUPO_LEAD_ENTROU_CRIACAO |
| MEMB-06 | Query filtra `WHERE instance_key = empresa.evolution_key_atual` — rows de instância antiga (Fernanda) não contam | §6 instance_key source of truth — `empresas.evolution_instancia` + `config_apis.evolution_instancia` (fallback) |
| PROBE-CACHE-01 | Singleton `app/services/probe_cache.py` com `cachetools.TTLCache(512, ttl=300)` + RLock, invalidação automática em UPSERT | §7 Cache design + §8 invalidation centralizada via helper |
| PROBE-COALESCE-01 | `asyncio.Lock` por chave evita probes concorrentes pro mesmo grupo | §9 Coalescing pattern (stdlib, sem dep nova) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

> `leadflow-backend/CLAUDE.md` é instrução focada em **agente.py qualificação Q1/Q2 trava** — não impõe constraints diretas a esta fase (que mexe em schema + webhook + cache). Não há overlap com Q1/Q2 flow. Inferência: manter padrão do projeto:

- NÃO refatorar fluxo sem necessidade — Fase 10 é puramente aditiva (nova tabela, novas funções, nenhum delete/rename)
- NÃO mexer em código fora do escopo (este princípio explica por quê 6 callsites de `grupo_fallback.py` vão para Fase 11, não 10)
- USAR padrões já existentes (`scheduler.add_job(replace_existing=True)`, marker UNIQUE em `conversas`, RLS service_role only — todos os 3 já em produção)

## Standard Stack

### Core (já em produção — não adicionar versão nova)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| supabase-py | >=2.18.0,<3.0.0 | CRUD em Postgres via REST | Já em prod (requirements.txt:5) [VERIFIED: requirements.txt] |
| apscheduler | 3.10.4 | Job scheduler (cleanup, futuros retries) | Já em prod (requirements.txt:25); singleton em `app/scheduler.py:5` [VERIFIED: codebase] |
| httpx | 0.27.0 | HTTP async client Evolution | Já em prod (requirements.txt:12) [VERIFIED: requirements.txt] |
| fastapi | 0.115.0 | Webhook router | Já em prod (requirements.txt:1) [VERIFIED: requirements.txt] |
| python | 3.13 (Easypanel) | Runtime | Confirmado em sessões anteriores [CITED: STATE.md] |
| pytest + pytest-asyncio | (já em uso, ver tests/) | Test framework | 4 arquivos de teste existem; padrão já estabelecido na Fase 9 v2.1 [VERIFIED: tests/ glob] |

### Supporting (NOVA dependência)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| cachetools | >=5.5.0,<6.0.0 | TTLCache singleton (~6kB pure-python) | `app/services/probe_cache.py` único consumer; nenhum decorator `@cached` (cache manual via get/set) [CITED: research/STACK.md] |

**Version verification:**
- `cachetools` 5.5.0 confirmado May 2026 release [CITED: research/STACK.md L193, PyPI link L405]. Antes de adicionar ao requirements.txt, **verificar com `npm view` equivalente em Python:** `pip index versions cachetools` ou `pip install cachetools== 2>&1 | tail -1`. Se 5.5.0 não estiver disponível, downgrade aceitável até `>=5.3.0` (também tem TTLCache + thread-safety patterns idênticos).

### Alternatives Considered (já rejeitadas em research/STACK.md §3.5b)

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| cachetools | functools.lru_cache | Sem TTL nativo. Workarounds são frágeis. |
| cachetools | dict custom + manual expiry | Reinventa roda; cachetools é 6kB battle-tested |
| Redis | — | OUT-OF-SCOPE explícito (STATE.md L141) |
| Celery/ARQ | — | OUT-OF-SCOPE explícito (STATE.md L141) |

**Installation:**
```bash
# Adicionar 1 linha em requirements.txt (entre apscheduler:25 e pytz:26)
cachetools>=5.5.0,<6.0.0

# Local dev:
pip install -r requirements.txt
# Easypanel: redeploy automático após push (já confirmado em sessões anteriores)
```

## Architecture Patterns

### Recommended File Structure (NEW files apenas — MODIFIED separados em §11)

```
leadflow-backend/
├── app/
│   ├── db/
│   │   └── migrations/
│   │       └── 004_grupo_membership.sql   # NEW: schema + RPC + RLS
│   ├── services/
│   │   ├── grupo_membership.py            # NEW: upsert_grupo_membership() + helpers
│   │   └── probe_cache.py                 # NEW: TTLCache singleton + invalidação
│   └── routers/
│       └── grupo_webhook.py               # MODIFIED: chama upsert em ADD + (futuro) handler MESSAGES_UPSERT
└── tests/
    ├── test_grupo_membership_upsert.py    # NEW: idempotência UPSERT (REQ MEMB-01..04)
    └── test_probe_cache.py                # NEW: TTL + invalidação + thread-safety smoke
```

### Pattern 1: SQL Migration via Supabase Studio (aplica padrão das migrations 001-003)

**What:** Single .sql file aplicado manualmente via Supabase Studio SQL Editor. Comentário cabeçalho explica purpose + impact. Tudo idempotente (`IF NOT EXISTS`, `DROP POLICY IF EXISTS` + recriação).

**When to use:** Schema changes em produção single-instance sem CI/CD migration runner. Padrão já validado por migrations 001-003.

**Example (skeleton baseado em 003_rls_fixes.sql):**

```sql
-- Migration: grupo_membership table + RPC upsert
-- Purpose: v2.2 fonte primaria de identificacao de lead no grupo
-- Created: 2026-06-XX
-- Apply via Supabase Studio SQL Editor (uma vez).
--
-- Impact zero pro backend ativo: tabela e funcoes novas, nada consome ainda
-- (Fase 11 introduz lead_in_group consumer).

-- 1. Tabela
CREATE TABLE IF NOT EXISTS public.grupo_membership (
    id BIGSERIAL PRIMARY KEY,
    empresa_id UUID NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    grupo_jid TEXT NOT NULL,
    telefone TEXT NULL,
    lid TEXT NULL,
    instance_key TEXT NOT NULL,
    entrou_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    saiu_em TIMESTAMPTZ NULL,
    fonte TEXT NOT NULL CHECK (fonte IN ('webhook_add','messages_upsert','create_group','admin_force','probe_backfill')),
    last_event_id TEXT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Partial unique index (alvo do UPSERT — exige COALESCE pra cobrir telefone OU lid)
CREATE UNIQUE INDEX IF NOT EXISTS uq_grupo_membership_alive
    ON public.grupo_membership (empresa_id, grupo_jid, COALESCE(telefone, lid))
    WHERE saiu_em IS NULL;

-- 3. Indexes de lookup
CREATE INDEX IF NOT EXISTS idx_grupo_membership_lookup
    ON public.grupo_membership (empresa_id, telefone, grupo_jid)
    WHERE saiu_em IS NULL;

CREATE INDEX IF NOT EXISTS idx_grupo_membership_lid
    ON public.grupo_membership (empresa_id, grupo_jid, lid)
    WHERE lid IS NOT NULL AND saiu_em IS NULL;

-- 4. RLS — service_role only (mesmo padrao de migrations 001/002/003)
ALTER TABLE public.grupo_membership ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS grupo_membership_service_all ON public.grupo_membership;
CREATE POLICY grupo_membership_service_all
    ON public.grupo_membership
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- 5. RPC function — contorna limitacao supabase-py com partial unique index
-- (PostgREST nao suporta on_conflict com COALESCE — ver §3)
CREATE OR REPLACE FUNCTION public.upsert_grupo_membership(
    p_empresa_id UUID,
    p_grupo_jid TEXT,
    p_telefone TEXT,
    p_lid TEXT,
    p_instance_key TEXT,
    p_entrou_em TIMESTAMPTZ,
    p_fonte TEXT,
    p_last_event_id TEXT
) RETURNS TABLE (
    id BIGINT,
    was_insert BOOLEAN,
    was_update BOOLEAN
) LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_id BIGINT;
    v_existing_atualizado TIMESTAMPTZ;
BEGIN
    -- Try update first (alive row only)
    UPDATE public.grupo_membership
       SET entrou_em = GREATEST(p_entrou_em, entrou_em),
           saiu_em = NULL,
           instance_key = p_instance_key,
           last_event_id = COALESCE(p_last_event_id, last_event_id),
           fonte = p_fonte,
           atualizado_em = NOW()
     WHERE empresa_id = p_empresa_id
       AND grupo_jid = p_grupo_jid
       AND COALESCE(telefone, lid) = COALESCE(p_telefone, p_lid)
       AND saiu_em IS NULL
       AND p_entrou_em >= atualizado_em  -- out-of-order guard
     RETURNING grupo_membership.id, atualizado_em
       INTO v_id, v_existing_atualizado;

    IF v_id IS NOT NULL THEN
        RETURN QUERY SELECT v_id, FALSE, TRUE;
        RETURN;
    END IF;

    -- No alive row, try insert
    BEGIN
        INSERT INTO public.grupo_membership
            (empresa_id, grupo_jid, telefone, lid, instance_key,
             entrou_em, fonte, last_event_id)
        VALUES
            (p_empresa_id, p_grupo_jid, p_telefone, p_lid, p_instance_key,
             p_entrou_em, p_fonte, p_last_event_id)
        RETURNING grupo_membership.id INTO v_id;
        RETURN QUERY SELECT v_id, TRUE, FALSE;
    EXCEPTION WHEN unique_violation THEN
        -- Race: another writer inserted between UPDATE and INSERT. Try update again.
        UPDATE public.grupo_membership
           SET entrou_em = GREATEST(p_entrou_em, entrou_em),
               atualizado_em = NOW()
         WHERE empresa_id = p_empresa_id
           AND grupo_jid = p_grupo_jid
           AND COALESCE(telefone, lid) = COALESCE(p_telefone, p_lid)
           AND saiu_em IS NULL
         RETURNING grupo_membership.id INTO v_id;
        RETURN QUERY SELECT v_id, FALSE, TRUE;
    END;
END;
$$;

GRANT EXECUTE ON FUNCTION public.upsert_grupo_membership(UUID, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT)
    TO service_role;
```

### Pattern 2: Centralized UPSERT helper (single entrypoint)

**What:** Toda escrita em `grupo_membership` passa por **uma única função** `upsert_grupo_membership()` em `app/services/grupo_membership.py`. Essa função: (a) chama RPC `upsert_grupo_membership`, (b) invalida cache, (c) loga `[MEMB-WRITE]`.

**When to use:** Sempre que qualquer caller (webhook ADD, MESSAGES_UPSERT, createGroup direct, futuro probe backfill) precisar escrever.

**Why single entrypoint:** Pitfall 6 (race) e Pitfall 13 (RLS silent deny) ficam triviais de detectar — 1 lugar para logar `rowcount`/exception. Pitfall 2 (cache mascarando falha) impossível: invalidação acoplada à escrita.

**Example:**

```python
# app/services/grupo_membership.py
import os
from datetime import datetime
from typing import Literal

FonteWrite = Literal['webhook_add', 'messages_upsert', 'create_group', 'admin_force', 'probe_backfill']


def upsert_grupo_membership(
    sb,
    *,
    empresa_id: str,
    grupo_jid: str,
    telefone: str | None,
    lid: str | None,
    instance_key: str,
    entrou_em: datetime,
    fonte: FonteWrite,
    last_event_id: str | None = None,
) -> dict:
    """
    UPSERT centralizado em grupo_membership.

    - Idempotente: chama RPC SQL que faz UPDATE-then-INSERT-with-fallback
    - Invalida cache atomicamente apos sucesso
    - Loga [MEMB-WRITE] sempre, com action (insert|update|skip_stale)
    - Try/except interno — NUNCA propaga exception (webhook handler nao pode falhar)

    Pre-condicao: pelo menos um de telefone ou lid e nao-nulo.

    Returns: {'ok': bool, 'id': int|None, 'action': str, 'erro': str}
    """
    from app.services import probe_cache

    if not telefone and not lid:
        return {'ok': False, 'id': None, 'action': 'invalid', 'erro': 'telefone e lid ambos nulos'}

    try:
        result = sb.rpc('upsert_grupo_membership', {
            'p_empresa_id': empresa_id,
            'p_grupo_jid': grupo_jid,
            'p_telefone': telefone,
            'p_lid': lid,
            'p_instance_key': instance_key,
            'p_entrou_em': entrou_em.isoformat(),
            'p_fonte': fonte,
            'p_last_event_id': last_event_id,
        }).execute()

        if not result.data:
            print(f"[MEMB-WRITE] FAIL empresa={empresa_id[:8]} grupo={grupo_jid[:24]} fonte={fonte} rpc_returned_empty")
            return {'ok': False, 'id': None, 'action': 'rpc_empty', 'erro': 'rpc retornou vazio'}

        row = result.data[0] if isinstance(result.data, list) else result.data
        action = 'insert' if row.get('was_insert') else ('update' if row.get('was_update') else 'noop')
        row_id = row.get('id')

        # Invalida cache APENAS apos sucesso confirmado (write-through)
        probe_cache.invalidate(empresa_id=empresa_id, grupo_jid=grupo_jid,
                                telefone=telefone, lid=lid)

        print(f"[MEMB-WRITE] OK empresa={empresa_id[:8]} grupo={grupo_jid[:24]} "
              f"tel={telefone or '-'} lid={(lid or '-')[:24]} fonte={fonte} "
              f"action={action} id={row_id}")
        return {'ok': True, 'id': row_id, 'action': action, 'erro': ''}

    except Exception as e:
        print(f"[MEMB-WRITE] EXC empresa={empresa_id[:8]} grupo={grupo_jid[:24]} "
              f"fonte={fonte} erro={e}")
        return {'ok': False, 'id': None, 'action': 'exception', 'erro': str(e)}


def get_instance_key(sb, empresa_id: str) -> str:
    """Source of truth: empresas.evolution_instancia (fallback config_apis).

    Pattern identico ao grupo_webhook.py:147 — manter coerencia.
    """
    try:
        res = sb.table('empresas').select('evolution_instancia, config_apis') \
            .eq('id', empresa_id).limit(1).execute()
        if not res.data:
            return ''
        emp = res.data[0]
        return (emp.get('evolution_instancia')
                or (emp.get('config_apis') or {}).get('evolution_instancia', '')
                or '').strip()
    except Exception as e:
        print(f"[MEMB-INSTANCE-KEY] erro empresa={empresa_id[:8]}: {e}")
        return ''
```

### Pattern 3: Cache singleton com invalidação centralizada

**What:** Módulo `probe_cache.py` expõe `get/set/invalidate/clear_for_group/stats`. Tudo via `with _lock`. Chave inclui `empresa_id` (multi-tenant isolation).

**When to use:** Apenas pelo helper `upsert_grupo_membership` (invalidate) e pela futura `lead_in_group()` Fase 11 (get/set). Não exportar para outros consumers em Fase 10.

**Example:**

```python
# app/services/probe_cache.py
import threading
from typing import Optional
from cachetools import TTLCache

_MAXSIZE = 512
_TTL_SECONDS = 300

_cache: TTLCache = TTLCache(maxsize=_MAXSIZE, ttl=_TTL_SECONDS)
_lock = threading.RLock()

_stats = {'hits': 0, 'misses': 0, 'writes': 0, 'invalidations': 0}


def _make_key(empresa_id: str, grupo_jid: str,
              telefone: Optional[str], lid: Optional[str]) -> tuple:
    """Chave: (empresa_id, grupo_jid, telefone_or_empty, lid_or_empty_lower).

    Multi-tenant isolation via empresa_id como primeiro componente.
    lid lowercase para evitar mismatch case-sensitive ('@LID' vs '@lid').
    """
    return (empresa_id, grupo_jid, telefone or '', (lid or '').lower())


def get(empresa_id: str, grupo_jid: str,
        telefone: Optional[str] = None, lid: Optional[str] = None) -> Optional[bool]:
    """Retorna True/False/None se cacheado; sentinela MISS=None se ausente.

    NOTE: None ambiguo (cache hit com valor None vs miss). Para Fase 10
    standalone OK — Fase 11 pode trocar pra objeto sentinela se virar dor.
    """
    with _lock:
        result = _cache.get(_make_key(empresa_id, grupo_jid, telefone, lid))
        if result is None:
            _stats['misses'] += 1
        else:
            _stats['hits'] += 1
        return result


def set(empresa_id: str, grupo_jid: str,
        telefone: Optional[str], lid: Optional[str],
        value: bool) -> None:
    with _lock:
        _cache[_make_key(empresa_id, grupo_jid, telefone, lid)] = value
        _stats['writes'] += 1


def invalidate(*, empresa_id: str, grupo_jid: str,
               telefone: Optional[str] = None, lid: Optional[str] = None) -> int:
    """Invalida chave especifica. Retorna 1 se removeu, 0 se ausente."""
    with _lock:
        removed = _cache.pop(_make_key(empresa_id, grupo_jid, telefone, lid), None)
        if removed is not None:
            _stats['invalidations'] += 1
            return 1
        return 0


def clear_for_group(empresa_id: str, grupo_jid: str) -> int:
    """Invalida todas as entradas para um grupo (UPSERT pode afetar varios leads)."""
    with _lock:
        keys_to_drop = [k for k in list(_cache.keys())
                        if k[0] == empresa_id and k[1] == grupo_jid]
        for k in keys_to_drop:
            _cache.pop(k, None)
        _stats['invalidations'] += len(keys_to_drop)
        return len(keys_to_drop)


def stats() -> dict:
    """Snapshot pra healthcheck."""
    with _lock:
        return {
            **_stats,
            'size': len(_cache),
            'maxsize': _MAXSIZE,
            'ttl_seconds': _TTL_SECONDS,
        }


def clear_all() -> None:
    """SO para uso em testes pytest (fixture limpa entre testes)."""
    with _lock:
        _cache.clear()
        for k in _stats:
            _stats[k] = 0
```

### Anti-Patterns to Avoid

- **Escrever em `grupo_membership` direto via `sb.table(...).insert/update`:** dispersa logging + invalidação de cache. SEMPRE via `upsert_grupo_membership()`.
- **Cache global compartilhado entre testes:** testes não-determinísticos. Fixture pytest chama `probe_cache.clear_all()` no setup.
- **Aceitar `NOW()` server-side como `entrou_em`:** webhook re-entregue 5min depois sobrescreve dado mais novo. Sempre usar `messageTimestamp` do payload Evolution (fallback `datetime.utcnow()` se ausente).
- **Decorator `@cached(cache=...)` em volta de função com efeito colateral:** complicado invalidar. Cache manual via get/set é mais explícito.
- **`@cached` decorator do cachetools sem `@cachedmethod(...lock=...)`:** Não é thread-safe por default ([CITED: cachetools issues#294](https://github.com/tkem/cachetools/issues/294)).
- **`asyncio.create_task(coalesce_probe(...))` sem strong reference:** Python 3.12+ GC pode coletar a task. [CITED: superfastpython.com/asyncio-disappearing-task-bug] — usar `_in_flight: dict[key, Future]` mantém ref.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TTL cache | `dict + datetime` manual expiry | `cachetools.TTLCache(maxsize, ttl)` | Reinventa roda; race conditions em expiry sutis; cachetools é 6kB battle-tested [CITED: research/STACK.md] |
| Thread safety em cache | Próprio mutex Python | `threading.RLock` ao redor de `TTLCache` | `TTLCache` NÃO é thread-safe por default ([CITED: cachetools#294](https://github.com/tkem/cachetools/issues/294)). RLock permite re-entrada na mesma thread (safe). |
| UPSERT idempotente em partial unique index | `INSERT` + try/except + retry manual | RPC function SQL com UPDATE-then-INSERT-with-fallback | supabase-py 2.18 não suporta `on_conflict` com `COALESCE` [VERIFIED: GitHub supabase/discussions/12565] — RPC é workaround oficial recomendado por maintainer Supabase. |
| Coalescing de probes concorrentes | `set[Task]` + manual cleanup | `asyncio.Lock` + `dict[key, Future]` (Fase 11 pattern, hoje só placeholder) | Stdlib. `asyncio.Lock` é per-event-loop. Coalescing real só faz sentido com `lead_in_group()` consumer (Fase 11) — Fase 10 entrega só o módulo. |
| Webhook idempotency dedup | Hash payload + timestamp window | UNIQUE constraint + `last_event_id` na própria `grupo_membership` | RPC SQL trata duplicate insert como `unique_violation EXCEPTION` (parte do contrato). Dedup explícito por `last_event_id` em coluna dedicada é defesa adicional. |
| Schema migration runner | Alembic + autogenerate | SQL file aplicado manualmente via Supabase Studio | Padrão já estabelecido nas migrations 001-003. CI/CD não existe pra schema. Override seria scope creep. |

**Key insight:** A combinação **RPC SQL + helper Python centralizado** elimina TODA a categoria de pitfalls de race + cache + dedup com 80 linhas de SQL bem-escrito. Alternativa (UPSERT via supabase-py + locks Python + cache invalidation espalhada) tem 5-10x mais código + bugs invisíveis.

## Common Pitfalls

### Pitfall 1: supabase-py `on_conflict` em partial unique index — FALHA GARANTIDA

**What goes wrong:**
```python
sb.table('grupo_membership').upsert({...}, on_conflict='empresa_id,grupo_jid,COALESCE(telefone,lid)').execute()
# → PostgreSQL erro: "there is no unique or exclusion constraint matching the ON CONFLICT specification"
```

**Why it happens:** PostgREST não permite passar `WHERE` predicate na cláusula ON CONFLICT (necessário para inferir o partial unique index). [VERIFIED: GitHub supabase/discussions/12565 — maintainer steve-chavez confirma]. PostgreSQL infere arbiter index só quando o predicate exato é especificado.

**How to avoid:** Usar RPC SQL function (workaround oficial). Helper Python `upsert_grupo_membership()` chama `sb.rpc('upsert_grupo_membership', {...})`. SQL faz UPDATE-then-INSERT-with-fallback handling `unique_violation EXCEPTION` para race entre transações.

**Warning signs:** Erro PostgreSQL com mensagem `"no unique or exclusion constraint matching"`. Se aparecer em prod, alguém bypassou o helper.

### Pitfall 2: Caso Ana Carla repete se Path 3 escolher local errado

**What goes wrong:** Path 3 escrito ANTES de `promover_admin_grupo` (linha ~205 de leads.py) ainda não tem confirmação que lead entrou — Evolution pode ter ignorado por privacidade. UPSERT marca "lead no grupo" mas Evolution não promoveu = lead ficou fora.

**Why it happens:** `criar_grupo` retorna `participants` no response, mas o `code` por participant só confirma "tentou adicionar". `promover_admin_grupo` retorna `updateParticipants[].status=200` que é a **confirmação real** que o membro foi aceito (caso Vanusa 13/05 estabeleceu este padrão).

**How to avoid:** Path 3 deve ser plugado **DEPOIS** do bloco "FIX 16/05 fallback @lid" (linhas 240-244 de leads.py) onde `_lead_confirmado_no_grupo = True` é setado. Substituir/complementar o bloco que insere `GRUPO_LEAD_ENTROU_CRIACAO` (linhas 263-271):

```python
# Linha 263 (atual):
sb.table("conversas").insert({
    "empresa_id": empresa_id, "telefone": telefone,
    "role": "sistema",
    "conteudo": f"GRUPO_LEAD_ENTROU_CRIACAO:{grupo_jid}",
    "criado_em": datetime.utcnow().isoformat(),
}).execute()

# Linha 263 (Fase 10 — substituir/complementar):
from app.services.grupo_membership import upsert_grupo_membership, get_instance_key
instance_key = get_instance_key(sb, empresa_id)
upsert_grupo_membership(
    sb,
    empresa_id=empresa_id, grupo_jid=grupo_jid,
    telefone=telefone, lid=None,
    instance_key=instance_key,
    entrou_em=datetime.utcnow(),  # createGroup é syncrono — NOW é OK aqui
    fonte='create_group',
    last_event_id=None,
)
# Manter o marker GRUPO_LEAD_ENTROU_CRIACAO em paralelo durante v2.2:
# - bypass <5min em ativar_fallback_se_necessario (96b72cc) ainda confia nele
# - remover marker so apos Fase 11 migrar todos consumers pra lead_in_group()
sb.table("conversas").insert({...marker como antes...}).execute()
```

**Warning signs:** Caso Ana Carla repete em produção 24-48h após deploy. Mitigação preventiva: logar `[MEMB-WRITE] action=insert fonte=create_group` em todo create — operador verifica em logs Easypanel se path está disparando.

### Pitfall 3: `instance_key` ausente em payload do webhook quebra Path 1

**What goes wrong:** Webhook `GROUP_PARTICIPANTS_UPDATE` traz `payload.instance` (string nome instância), não a chave UUID interna. Helper `get_instance_key(sb, empresa_id)` lê de `empresas.evolution_instancia`. Se houver desync (empresa.evolution_instancia=novo, mas webhook chegou da instância antiga ainda registrada na Evolution), `instance_key` na row vira o da instância nova — query `WHERE instance_key = empresa.evolution_key_atual` retorna match e Pitfall Fernanda regride.

**Why it happens:** Source of truth para "qual instância está ativa AGORA" é `empresas.evolution_instancia`. Mas o webhook vem da instância **que enviou o evento** (pode ser ativa ou ser instância antiga que ainda manda webhook).

**How to avoid:** Path 1 (webhook ADD) deve usar `payload.instance` diretamente como `instance_key`, NÃO `get_instance_key()`. Path 3 (createGroup) deve usar `evo_inst` que veio de `emp.get('evolution_instancia') or config_apis.get('evolution_instancia')` (line 33 leads.py — fonte é a instância **que criou** o grupo). Path 2 (MESSAGES_UPSERT) também usa `payload.instance`. **Regra:** `instance_key` SEMPRE = instância que originou o evento, nunca lookup da tabela atual.

**Warning signs:** Em Fase 11, `lead_in_group()` consultar `WHERE instance_key = X` e retornar 0 rows para grupos sabidamente ativos. Detectar pela auditoria: `SELECT DISTINCT instance_key FROM grupo_membership` — se houver mais de 1 valor para mesma empresa, OK (transição); se nenhum bater com `empresas.evolution_instancia` atual, BUG.

### Pitfall 4: UPSERT que aceita `entrou_em` no passado sobrescreve estado mais novo

**What goes wrong:** Webhook entregue fora-de-ordem: REMOVE chega em T+5s (saiu_em populado), ADD com `messageTimestamp` mais antigo chega em T+10s. Sem guard, UPDATE zera saiu_em e marca lead como ATIVO incorretamente.

**Why it happens:** Webhook ordering **não é garantido** ([CITED: hackernoon.com/you-cant-guarantee-webhook-ordering-heres-why]). Network proxies + Evolution retry podem reordenar.

**How to avoid:** A RPC function SQL no §Pattern 1 já tem o guard `AND p_entrou_em >= atualizado_em`. ADD com timestamp mais antigo que último update é no-op (RETURN 0 rows, RPC retorna `noop`). Logar `[MEMB-WRITE] action=noop` para auditoria.

**Warning signs:** Métrica de `action=noop` > 5/hora indica problema de ordering do provider. Em produção saudável deve ser <1/hora.

### Pitfall 5: Cache `None` value ambíguo (hit vs miss)

**What goes wrong:** `probe_cache.get(...)` retorna `None`. Caller não sabe se é "miss" (chave ausente) ou "hit com valor None" (probe Evolution erro/incerto previamente cacheado).

**Why it happens:** Em Fase 11, `lead_in_group()` pode cachear `None` (Evolution erro = incerto, evita retry imediato dentro do TTL). Get retornar `None` é ambíguo.

**How to avoid:** Para Fase 10 standalone, **não cachear `None`** — só `True` ou `False`. Helper `probe_cache.set(...)` rejeita `value is None` (silent skip) OU sentinela `MISS = object()` retornado de `get()`. Documentar trade-off em docstring.

**Recommended:** Implementar sentinela já em Fase 10 mesmo sem consumidor (Fase 11 vai precisar). Custo: 3 linhas a mais.

```python
_MISS = object()

def get(...):
    with _lock:
        v = _cache.get(_make_key(...), _MISS)
        return None if v is _MISS else v  # ainda ambiguo mas pelo menos cacheia None
```

Alternativa mais limpa para Fase 10: rejeitar `None` em set. Decisão **DEFERRED para implementação** — qualquer das duas funciona, não é decisão arquitetural.

### Pitfall 6: RLS silenciosa derruba write em produção sem exception

**What goes wrong:** Webhook handler usa `get_supabase()` que poderia (refactor futuro) retornar anon client. RLS policy é `service_role only`. INSERT retorna 0 rows affected sem exception.

**Why it happens:** Supabase RLS filtra silenciosamente. ([CITED: research/PITFALLS.md Pitfall 13])

**How to avoid:** RPC `upsert_grupo_membership` é `SECURITY DEFINER` — roda como criador (service_role) independente de quem chama. Defesa adicional: helper Python verifica `result.data` não-vazio + `was_insert OR was_update` true; senão loga `[MEMB-WRITE] FAIL rpc_returned_empty` (ver §Pattern 2). Garantir que `app/db/client.py:get_supabase()` retorna service_role (já é o padrão em produção — verificar permanece em Fase 10).

**Warning signs:** `[MEMB-WRITE] FAIL rpc_returned_empty` em logs Easypanel. Métrica preview no healthcheck (§13) ajuda detectar.

### Pitfall 7: Race entre webhook ADD escrita + leitor concorrente (Pitfall 6 do PITFALLS.md)

**What goes wrong:** Em Fase 10 não há consumidor de leitura (consumer entra em Fase 11). Race **não se materializa** em Fase 10. Mas o **design** desta fase precisa permitir mitigação em Fase 11.

**Why it happens:** Janela curta entre INSERT começar e COMMIT. Em Fase 11, `lead_in_group()` pode ler vazio bem nesse instante.

**How to avoid:** RPC `upsert_grupo_membership` é uma única statement Postgres (UPDATE-then-INSERT em mesma transação implícita). COMMIT atomic. Em Fase 11, `lead_in_group()` deve fazer SELECT com pequeno delay/retry — out-of-scope desta fase. **Garantia desta fase:** RPC é serializável por linha; once committed, qualquer leitor subsequente vê.

## Code Examples

### Path 1 — Webhook GROUP_PARTICIPANTS_UPDATE (modificar grupo_webhook.py)

```python
# app/routers/grupo_webhook.py — adicionar dentro de _processar_grupo_payload
# DEPOIS da linha 156 (print empresa_id resolvido), ANTES do for tel loop existente (linha 161)

from datetime import datetime
from app.services.grupo_membership import upsert_grupo_membership

# Extrai messageTimestamp do payload (Baileys envia em segundos epoch)
_evento_ts_raw = (payload.get('data') or {}).get('messageTimestamp') or payload.get('date_time')
try:
    if isinstance(_evento_ts_raw, (int, float)):
        evento_ts = datetime.fromtimestamp(int(_evento_ts_raw))
    elif isinstance(_evento_ts_raw, str):
        # ISO format ou epoch string
        try:
            evento_ts = datetime.fromisoformat(_evento_ts_raw.replace('Z', '+00:00'))
        except ValueError:
            evento_ts = datetime.fromtimestamp(int(_evento_ts_raw))
    else:
        evento_ts = datetime.utcnow()
except Exception:
    evento_ts = datetime.utcnow()

# instance_key = nome da instancia que ENVIOU o webhook (NAO lookup)
# Pitfall 3 — instancia origem do evento, nao instancia atual da empresa
instance_key = (payload.get('instance') or '').strip()

# message_id como last_event_id (idempotencia)
_msg_id = (payload.get('data') or {}).get('key', {}).get('id') or payload.get('id') or ''

# UPSERT para cada telefone
for tel in telefones_entraram:
    upsert_grupo_membership(
        sb,
        empresa_id=empresa_id, grupo_jid=grupo_jid,
        telefone=tel, lid=None,
        instance_key=instance_key,
        entrou_em=evento_ts,
        fonte='webhook_add',
        last_event_id=_msg_id,
    )

# UPSERT para cada @lid
for lid_jid in lids_entraram:
    upsert_grupo_membership(
        sb,
        empresa_id=empresa_id, grupo_jid=grupo_jid,
        telefone=None, lid=lid_jid,
        instance_key=instance_key,
        entrou_em=evento_ts,
        fonte='webhook_add',
        last_event_id=_msg_id,
    )

# RESTO DO HANDLER EXISTENTE PERMANECE INALTERADO (linhas 161-225):
# - marker GRUPO_AGUARDANDO_ENTRADA lookup + processar_entrada_lead_no_grupo
# - heuristica @lid unique-aguardando + _salvar_lead_lid (LEAD_LID marker)
# Backwards compat: Fase 11+ consumidores migram pra grupo_membership.
```

### Path 2 — MESSAGES_UPSERT handler (NEW handler em grupo_webhook.py ou agente.py)

```python
# Path 2 é triggered quando msg de grupo chega + heuristica unique-aguardando.
# v2.1 ja tinha isso parcialmente em agente.py (handler MESSAGES_UPSERT) salvando
# LEAD_LID. Fase 10 adiciona UPSERT em grupo_membership no mesmo ponto.

# Localizacao exata: SE handler MESSAGES_UPSERT esta em agente.py, identificar
# em kickoff de implementacao (research nao mapeou linha exata — pendente).
# Pattern:

# Quando msg chega de @g.us:
if grupo_jid_msg and lid_remetente:
    # Heuristica v2.1 reusada (sessao_2026-05-20_grupo_lid_arquitetura.md):
    # se EXATAMENTE 1 lead aguardando neste grupo, correlaciona @lid->telefone
    aguardando = sb.table('conversas').select('telefone').eq('empresa_id', empresa_id) \
        .eq('role', 'sistema') \
        .eq('conteudo', f'GRUPO_AGUARDANDO_ENTRADA:{grupo_jid_msg}').execute()
    telefones_aguardando = list({(r.get('telefone') or '').strip()
                                  for r in (aguardando.data or []) if r.get('telefone')})
    if len(telefones_aguardando) == 1:
        tel_lead = telefones_aguardando[0]
        upsert_grupo_membership(
            sb,
            empresa_id=empresa_id, grupo_jid=grupo_jid_msg,
            telefone=tel_lead, lid=lid_remetente,
            instance_key=payload.get('instance', ''),
            entrou_em=datetime.fromtimestamp(int(payload['data']['messageTimestamp'])),
            fonte='messages_upsert',
            last_event_id=payload['data']['key']['id'],
        )
```

### Path 3 — createGroup direct write (modificar leads.py)

```python
# app/routers/leads.py — DENTRO do try block em volta de promote_admin parse
# Substitui/complementa linhas 263-271 (insert do marker GRUPO_LEAD_ENTROU_CRIACAO)
# Codigo abaixo vai DEPOIS de `if _lead_confirmado_no_grupo:` (linha 245)

from app.services.grupo_membership import upsert_grupo_membership, get_instance_key

if _lead_confirmado_no_grupo:
    from app.services.grupo_state import set_grupo_state, STATE_ATIVO
    # ... codigo existente de set_grupo_state (linhas 246-257) ...

    # ── v2.2 MEMB-04: persiste membership direto (Path 3) ──
    # Caso Ana Carla: webhook GROUP_PARTICIPANTS_UPDATE nao dispara pra
    # participants do POST /group/create. Sem este UPSERT, Fase 11
    # `lead_in_group()` consulta tabela vazia e cai pro probe (que tambem
    # mente em T+60s). Defesa em profundidade.
    try:
        upsert_grupo_membership(
            sb,
            empresa_id=empresa_id, grupo_jid=grupo_jid,
            telefone=telefone, lid=None,
            instance_key=evo_inst,  # instancia que criou o grupo (linha 33)
            entrou_em=datetime.utcnow(),
            fonte='create_group',
            last_event_id=None,
        )
    except Exception as _e_memb:
        # Helper ja faz try/except interno — este e ultra-defensivo
        print(f"[MEMB-WRITE-PATH3] exc inesperada: {_e_memb}")
    # ── fim MEMB-04 ──

    # MANTER marker GRUPO_LEAD_ENTROU_CRIACAO em paralelo durante v2.2:
    # bypass <5min em ativar_fallback_se_necessario (commit 96b72cc) ainda confia
    # nele. Remover apenas em Fase 11+ apos migrar consumers pra lead_in_group().
    try:
        sb.table("conversas").insert({
            "empresa_id": empresa_id, "telefone": telefone,
            "role": "sistema",
            "conteudo": f"GRUPO_LEAD_ENTROU_CRIACAO:{grupo_jid}",
            "criado_em": datetime.utcnow().isoformat(),
        }).execute()
    except Exception:
        pass
```

### Test fixture pattern (idempotência UPSERT)

```python
# tests/test_grupo_membership_upsert.py
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

@pytest.fixture
def fresh_cache():
    """Limpa cache global entre testes (Anti-pattern 2 prevention)."""
    from app.services import probe_cache
    probe_cache.clear_all()
    yield probe_cache
    probe_cache.clear_all()


@pytest.fixture
def mock_sb_rpc():
    """Mock supabase client retornando RPC success."""
    sb = MagicMock()
    sb.rpc.return_value.execute.return_value.data = [
        {'id': 42, 'was_insert': True, 'was_update': False}
    ]
    return sb


def test_upsert_basico_insert(mock_sb_rpc, fresh_cache):
    from app.services.grupo_membership import upsert_grupo_membership
    result = upsert_grupo_membership(
        mock_sb_rpc,
        empresa_id='emp-uuid',
        grupo_jid='120363@g.us',
        telefone='5511999999999', lid=None,
        instance_key='rejane-leal-mentora',
        entrou_em=datetime.utcnow(),
        fonte='webhook_add',
        last_event_id='msg_id_123',
    )
    assert result['ok'] is True
    assert result['action'] == 'insert'
    assert result['id'] == 42
    # Verifica RPC chamada com argumentos corretos
    mock_sb_rpc.rpc.assert_called_once()
    args = mock_sb_rpc.rpc.call_args
    assert args[0][0] == 'upsert_grupo_membership'
    assert args[0][1]['p_telefone'] == '5511999999999'


def test_upsert_segundo_call_eh_update(mock_sb_rpc, fresh_cache):
    """Segunda chamada com mesmo (empresa,grupo,telefone) retorna was_update=True
    pela RPC. Helper deve retornar action='update'."""
    from app.services.grupo_membership import upsert_grupo_membership
    # 1a chamada: insert
    mock_sb_rpc.rpc.return_value.execute.return_value.data = [
        {'id': 42, 'was_insert': True, 'was_update': False}
    ]
    upsert_grupo_membership(mock_sb_rpc, empresa_id='e', grupo_jid='g',
                            telefone='t', lid=None, instance_key='i',
                            entrou_em=datetime.utcnow(), fonte='webhook_add')
    # 2a chamada: update (RPC retorna was_update=True)
    mock_sb_rpc.rpc.return_value.execute.return_value.data = [
        {'id': 42, 'was_insert': False, 'was_update': True}
    ]
    result = upsert_grupo_membership(mock_sb_rpc, empresa_id='e', grupo_jid='g',
                                      telefone='t', lid=None, instance_key='i',
                                      entrou_em=datetime.utcnow() + timedelta(seconds=10),
                                      fonte='webhook_add')
    assert result['action'] == 'update'
    assert result['id'] == 42  # mesmo id


def test_invalida_cache_apos_upsert(mock_sb_rpc, fresh_cache):
    """write-through: cache invalidado apos UPSERT bem-sucedido."""
    from app.services.grupo_membership import upsert_grupo_membership
    from app.services import probe_cache
    # Popula cache com valor stale
    probe_cache.set('emp-uuid', '120363@g.us', '5511999999999', None, True)
    assert probe_cache.get('emp-uuid', '120363@g.us', '5511999999999', None) is True

    upsert_grupo_membership(mock_sb_rpc, empresa_id='emp-uuid',
                             grupo_jid='120363@g.us', telefone='5511999999999',
                             lid=None, instance_key='i',
                             entrou_em=datetime.utcnow(), fonte='webhook_add')

    # Cache foi invalidado
    assert probe_cache.get('emp-uuid', '120363@g.us', '5511999999999', None) is None


def test_telefone_e_lid_nulos_retorna_invalid(mock_sb_rpc, fresh_cache):
    from app.services.grupo_membership import upsert_grupo_membership
    result = upsert_grupo_membership(mock_sb_rpc, empresa_id='e', grupo_jid='g',
                                      telefone=None, lid=None, instance_key='i',
                                      entrou_em=datetime.utcnow(), fonte='webhook_add')
    assert result['ok'] is False
    assert result['action'] == 'invalid'
    # RPC nao deve ter sido chamada
    mock_sb_rpc.rpc.assert_not_called()
```

## State of the Art

| Old Approach (pre-v2.2) | Current Approach (v2.2 Fase 10) | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Marker `LEAD_LID:{grupo_jid}:{lid}` em `conversas` como source-of-truth indireto | Tabela `grupo_membership` materializada com unique constraint | Esta fase (2026-06-09+) | Query "quem está no grupo X" passa de full-scan markers para index seek; idempotência por UNIQUE em vez de duplicate-insert-then-catch |
| `verificar_lead_no_grupo` (Evolution probe) como fonte primária | Webhook → tabela (Fase 11); probe vira fallback | Esta fase prepara, Fase 11 consome | Probe Evolution mente em 60-180s — eliminar como primário cobre 4+ casos do 08/06 |
| `INSERT INTO conversas` com try/except duplicate como dedup | RPC SQL `SECURITY DEFINER` com UPDATE-then-INSERT-with-fallback | Esta fase | Race conditions tratadas explicitamente (`unique_violation EXCEPTION`); RLS bypassed corretamente; logging centralizado |
| Cache: nenhum (probe síncrono direto) | `cachetools.TTLCache(512, ttl=300)` + RLock | Esta fase | Reduz carga Evolution API em picos de aquec dispatch (5-10 probes/min em mesma janela) |

**Deprecated/outdated (em Fase 10 — restantes em fases seguintes):**

- Marker `LEAD_LID:` continua sendo escrito (backwards compat) — só remover quando todos os consumers v2.1 migrarem em Fase 11+
- Marker `GRUPO_LEAD_ENTROU_CRIACAO:` continua sendo escrito (bypass <5min em `ativar_fallback_se_necessario` ainda confia nele) — remover em Fase 11+
- Probe síncrono `verificar_lead_no_grupo` permanece como fallback indireto (Fase 12 vira retry async)

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `cachetools` 5.5.0 está disponível em PyPI como descrito em research/STACK.md | Standard Stack | BAIXO — fallback `>=5.3.0` (também com TTLCache thread-safety patterns); verificar com `pip index versions cachetools` em kickoff |
| A2 | `payload.data.messageTimestamp` está presente em todo evento GROUP_PARTICIPANTS_UPDATE da Evolution Baileys | Path 1 code example | MÉDIO — se ausente, fallback `datetime.utcnow()` (não-ideal pra out-of-order guard, mas funcional); validar com payload real em prod ou em test fixture |
| A3 | `empresas.evolution_instancia` é o nome único e estável que match com `payload.instance` (case-insensitive) | Pattern 2 `get_instance_key` | BAIXO — padrão idêntico ao `grupo_webhook.py:147` já em prod; mesma fonte de verdade |
| A4 | Path 2 (MESSAGES_UPSERT) handler vive em `agente.py` (não em `grupo_webhook.py`) | §11 Code Examples Path 2 | MÉDIO — research **não mapeou linha exata**; identificar em kickoff com grep `MESSAGES_UPSERT` ou `messages.upsert` em `app/routers/agente.py`; impacto: localização do patch muda mas não a forma |
| A5 | `app/db/client.py:get_supabase()` retorna service_role client em produção | Pitfall 6 mitigation | BAIXO — padrão estabelecido (backend inteiro depende disso); confirmar lendo `app/db/client.py` em kickoff |
| A6 | RPC SQL `SECURITY DEFINER` é executável por service_role automaticamente após `GRANT EXECUTE` | Pattern 1 RPC | BAIXO — padrão Postgres bem documentado; testar manualmente após aplicar migration via Studio |
| A7 | Cache key tupla `(empresa_id, grupo_jid, telefone, lid)` é correta para multi-tenant isolation | Pattern 3 cache | BAIXO — empresa_id primeiro garante isolation; lid lowercase evita case-sensitive mismatch |
| A8 | Healthcheck endpoint pode ser skinny em Fase 10 (3 métricas) e expandir em Fase 14 (OBS-V2-G2) | §13 Healthcheck preview | BAIXO — decisão de discretion; user pode pedir expansão antecipada |

**Trigger para resolver A2 e A4:** Antes de implementar Path 1 e Path 2, fazer 1 dump de payload real de cada evento em produção (logging temporário `print(json.dumps(payload))` no webhook) — investimento <30min, elimina 2 ASSUMED.

## Open Questions

1. **Coluna `fonte` vs separação Path 1/2/3 — vale a pena tracking?**
   - What we know: research/STACK.md L52 e Pattern 1 SQL incluem `fonte TEXT CHECK IN (...)`.
   - What's unclear: se vamos consultar `fonte` em alguma query analítica/audit. Se não, a coluna é dead weight.
   - Recommendation: **MANTER** — custo: 8 bytes/row. Em 3000 rows/dia × 1 ano = 8.7MB. Trivial. Benefício: debug de "qual path escreveu este row" salva horas em produção.

2. **Path 2 (MESSAGES_UPSERT) localização exata pendente**
   - What we know: v2.1 Fase 4 (commit 6b0295b) implementou captura de `@lid` via MESSAGES_UPSERT — handler existe.
   - What's unclear: arquivo + linha exata. Research mapeou só "agente.py provavelmente".
   - Recommendation: kickoff faz `Grep "messages.upsert\|MESSAGES_UPSERT" app/routers/` para localizar em <2min. Plano da fase ajusta linha.

3. **Healthcheck endpoint nesta fase OU Fase 14?**
   - What we know: OBS-V2-G2 está oficialmente em Fase 14.
   - What's unclear: se vale entregar **endpoint skinny** já em Fase 10 (3 métricas: `cache.stats`, `total_rows`, `last_write_at`) para detectar problemas de persistência DURANTE Fase 11/12 desenvolvimento.
   - Recommendation: **endpoint skinny em Fase 10** dentro de `/admin/grupo-membership/health` (path admin já existe). Fase 14 expande com cache_hit_rate detalhado + alerting hooks. Decisão final: planner.

4. **Deletar marker `LEAD_LID:` em Fase 11 ou manter forever?**
   - What we know: Fase 11 migra consumers de markers para `grupo_membership`.
   - What's unclear: se marker permanece sendo escrito (defesa em profundidade) ou se vira código morto removido.
   - Recommendation: **MANTER escrita em Fase 11**, considerar remoção em Fase 14 após Phase 13 LEAVE handler estabilizar. Decisão fora desta fase.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | Runtime backend | ✓ (Easypanel) | 3.13 | — |
| supabase-py | RPC call + table ops | ✓ | >=2.18.0 | — |
| apscheduler | Singleton scheduler (Fase 12 plug) | ✓ | 3.10.4 | — |
| cachetools | TTLCache singleton | ✗ (precisa add) | >=5.5.0 | downgrade `>=5.3.0` se 5.5 indisponível |
| pytest + pytest-asyncio | Test framework | ✓ (4 arquivos test/*.py) | (não-pinned, já em uso) | — |
| Supabase Studio (acesso SQL Editor) | Aplicar migration 004 | ✓ (uso humano operacional) | — | psql direto via service_role (fallback se Studio indisponível) |
| Postgres `SECURITY DEFINER` + `LANGUAGE plpgsql` | RPC function | ✓ (Postgres Supabase managed) | 15+ | — |

**Missing dependencies with no fallback:** Nenhuma.

**Missing dependencies with fallback:** `cachetools` 5.5.0 (improvável indisponível — release May 2026 [CITED: research/STACK.md L193]).

## Validation Architecture

> `workflow.nyquist_validation` não está definido em `.planning/config.json` → tratar como enabled.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (versão pinned em requirements futura — hoje não-pinned) |
| Config file | nenhum (tests/ + convenção pytest default) |
| Quick run command | `cd leadflow-backend && pytest tests/test_grupo_membership_upsert.py tests/test_probe_cache.py -x` |
| Full suite command | `cd leadflow-backend && pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MEMB-01 | Migration 004 aplicada gera tabela + 3 indexes + RLS policy + RPC function | manual-only (DDL no Supabase Studio) | Validação humana: `SELECT * FROM grupo_membership LIMIT 0; SELECT pg_get_functiondef('upsert_grupo_membership'::regproc);` | ❌ manual (sem ambiente DB de teste) |
| MEMB-02 | Path 1 webhook ADD chama RPC com instance_key correto + timestamp do payload | unit (mock supabase) | `pytest tests/test_grupo_membership_upsert.py::test_path1_webhook_add -x` | ❌ Wave 0 |
| MEMB-03 | Path 2 MESSAGES_UPSERT escreve quando 1 lead aguardando + @lid não-mapped | unit (mock supabase + heurística) | `pytest tests/test_grupo_membership_upsert.py::test_path2_messages_upsert_unique_aguardando -x` | ❌ Wave 0 |
| MEMB-04 | Path 3 createGroup direct write após `_lead_confirmado_no_grupo=True` | unit (mock leads.py path) | `pytest tests/test_grupo_membership_upsert.py::test_path3_create_group_direct -x` | ❌ Wave 0 |
| MEMB-06 | RPC respeita `entrou_em >= atualizado_em` guard (out-of-order rejeitado) | unit (RPC mock retornando was_update=False) | `pytest tests/test_grupo_membership_upsert.py::test_upsert_out_of_order_noop -x` | ❌ Wave 0 |
| MEMB-06 (instance_key) | Helper `get_instance_key` lê de `empresas.evolution_instancia` com fallback `config_apis` | unit (mock supabase) | `pytest tests/test_grupo_membership_upsert.py::test_get_instance_key_fallback -x` | ❌ Wave 0 |
| PROBE-CACHE-01 | TTL expira após 300s (smoke com TTLCache + freezegun ou manipulação de ttl=1) | unit | `pytest tests/test_probe_cache.py::test_ttl_expires -x` | ❌ Wave 0 |
| PROBE-CACHE-01 | Invalidação remove chave + métrica counter | unit | `pytest tests/test_probe_cache.py::test_invalidate_removes_and_counts -x` | ❌ Wave 0 |
| PROBE-CACHE-01 | clear_for_group remove todas as entradas do grupo | unit | `pytest tests/test_probe_cache.py::test_clear_for_group -x` | ❌ Wave 0 |
| PROBE-CACHE-01 | Multi-tenant isolation (empresa_id diferente = chaves separadas) | unit | `pytest tests/test_probe_cache.py::test_multi_tenant_isolation -x` | ❌ Wave 0 |
| PROBE-COALESCE-01 | `asyncio.Lock` por chave evita 2 probes simultâneos | unit (asyncio + AsyncMock) | `pytest tests/test_probe_cache.py::test_coalescing_same_key -x` | ❌ Wave 0 |
| Write-through | UPSERT bem-sucedido invalida cache stale | unit (integração helper + cache) | `pytest tests/test_grupo_membership_upsert.py::test_invalida_cache_apos_upsert -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_grupo_membership_upsert.py tests/test_probe_cache.py -x` (~3-5s esperado)
- **Per wave merge:** `pytest tests/ -x` (suite completa, ~10-15s — inclui 13 testes v2.1 já existentes)
- **Phase gate:** Full suite green + smoke manual no Supabase Studio (1 INSERT manual + 1 SELECT confirma RLS service_role)

### Wave 0 Gaps

- [ ] `tests/test_grupo_membership_upsert.py` — cobre MEMB-01..04, MEMB-06
- [ ] `tests/test_probe_cache.py` — cobre PROBE-CACHE-01, PROBE-COALESCE-01
- [ ] Framework install: confirmar `pytest`/`pytest-asyncio` pinned em requirements.txt — hoje não-pinned (testes Fase 9 rodam mas instalação implícita)
- [ ] Pip install `freezegun` se for usar para TTL test (alternativa: usar TTLCache com ttl=1s + sleep curto)
- [ ] Fixture `mock_sb_rpc` em `tests/conftest.py` (se não existir, criar — outros testes futuros vão reusar)
- [ ] Documentar `pytest -m asyncio` convention nos novos testes async

## Security Domain

> `security_enforcement` não definido em `.planning/config.json` → tratar como enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (webhook endpoint exposto) | Header `apikey` validation no webhook handler (já existente em outros routers — Pitfall 14 do PITFALLS.md flagou ausência neste). Fase 10 OUT-OF-SCOPE adicionar — research PITFALLS.md flag pra próxima fase. |
| V3 Session Management | no (server-to-server webhook) | — |
| V4 Access Control | yes (RLS Postgres) | RLS policy `grupo_membership_service_all FOR ALL TO service_role` — anon e authenticated bloqueados |
| V5 Input Validation | yes (payload Evolution webhook) | Pydantic não usado no handler atual (pattern do projeto é dict access defensivo); `instance_key`, `grupo_jid`, `telefone` validados em `_normalizar_jid_telefone` + RPC SQL valida `fonte CHECK IN (...)` |
| V6 Cryptography | no | — (TIMESTAMPTZ + texto plain) |

### Known Threat Patterns para stack (Postgres + supabase-py + FastAPI webhook)

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via grupo_jid/telefone payload | Tampering | supabase-py + RPC parametrizada (não string concat); RPC `LANGUAGE plpgsql` com params tipados [VERIFIED: §Pattern 1 SQL] |
| Webhook spoofing (atacante POST falso → marca lead no grupo errado) | Spoofing | Header `apikey` check (Evolution-set env var) — **OUT-OF-SCOPE Fase 10**, flagged como Pitfall 14 do PITFALLS.md para próxima |
| RLS bypass por anon client | Elevation of Privilege | Helper Python depende de `get_supabase()` retornar service_role; RPC `SECURITY DEFINER` blinda mesmo se anon chamar |
| Data exfiltration via cross-tenant queries | Information Disclosure | Cache key inclui `empresa_id` (Pattern 3); RPC valida `p_empresa_id` em todas operations |
| Webhook replay DoS | Denial of Service | UPSERT idempotente por `(grupo_jid, COALESCE(tel,lid))`; `last_event_id` permite dedup explícito; rate-limit no FastAPI (slowapi já em deps) — config nesta fase opcional |
| Cache poisoning | Tampering | Cache só populado por `upsert_grupo_membership` write-through; nenhum consumer externo escreve direto |

## Sources

### Primary (HIGH confidence)

- **Codebase introspection:**
  - `c:/Projetos/Leadflow/leadflow-backend/app/routers/grupo_webhook.py` linhas 81-226 (handler atual GROUP_PARTICIPANTS_UPDATE — Path 1 callsite confirmado entre L130-160)
  - `c:/Projetos/Leadflow/leadflow-backend/app/routers/leads.py` linhas 12-400 (`_criar_grupo_agendamento` — Path 3 callsite confirmado entre L245-271 dentro de `if _lead_confirmado_no_grupo`)
  - `c:/Projetos/Leadflow/leadflow-backend/app/services/evolution.py` linhas 11-69 (`criar_grupo` confirma `nao_adicionados` parsing + `participants` no response)
  - `c:/Projetos/Leadflow/leadflow-backend/app/scheduler.py` (singleton AsyncIOScheduler + padrão `replace_existing=True`)
  - `c:/Projetos/Leadflow/leadflow-backend/app/db/migrations/003_rls_fixes.sql` (template estilo migration manual)
  - `c:/Projetos/Leadflow/leadflow-backend/requirements.txt` (versões confirmadas)
  - `c:/Projetos/Leadflow/leadflow-backend/tests/test_verificar_lead_no_grupo_phase3.py` (pattern pytest+asyncio+mock httpx)

- **Planning artifacts:**
  - `.planning/REQUIREMENTS.md` (MEMB-01..06, PROBE-CACHE-01, PROBE-COALESCE-01)
  - `.planning/STATE.md` (locked decisions L106-118, 6 fixes 08/06 não-regredir L73-80)
  - `.planning/research/SUMMARY.md`, STACK.md, ARCHITECTURE.md, PITFALLS.md (synthesis dos 4 researchers)

- **External (HIGH):**
  - [PostgreSQL Partial Indexes (official)](https://www.postgresql.org/docs/current/indexes-partial.html)
  - [PostgreSQL INSERT (official, ON CONFLICT inference rules)](https://www.postgresql.org/docs/current/sql-insert.html)
  - [cachetools 5.5.0 PyPI](https://pypi.org/project/cachetools/) — release May 2026
  - [cachetools docs](https://cachetools.readthedocs.io/) — TTLCache API
  - [APScheduler 3.x User Guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html)

### Secondary (MEDIUM confidence — verified spike)

- [supabase/discussions/12565 — upserts on partial indexes](https://github.com/orgs/supabase/discussions/12565) — Maintainer steve-chavez confirma RPC workaround [VERIFIED: WebFetch]
- [PostgREST issues/2123 — Allow upserting by exclusion constraints and index expressions](https://github.com/PostgREST/postgrest/issues/2123)
- [Why Can't PostgreSQL's ON CONFLICT Find My Partial Unique Index? (betakuang/Medium)](https://betakuang.medium.com/why-postgresqls-on-conflict-cannot-find-my-partial-unique-index-552327b85e1)
- [cachetools issues#294 thread safety](https://github.com/tkem/cachetools/issues/294) — confirms RLock required

### Tertiary (training knowledge — flagged ASSUMED)

- Nenhum claim deste research depende SÓ de training knowledge. Tudo verificado em codebase introspection ou web sources.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — versões confirmadas via requirements.txt; cachetools 5.5.0 cross-referenced com research/STACK.md (verified PyPI)
- Architecture (schema + 3 paths + cache): HIGH — codebase introspection direta confirma callsites Path 1 e Path 3; Path 2 localização tem 1 ASSUMED (A4)
- RPC workaround: HIGH — verified via WebFetch direto do GitHub discussion 12565 (maintainer Supabase)
- Pitfalls (7 catalogados): HIGH — todos amparados em casos reais (Ana Carla, Fernanda, Rosânia) + sources externas verificadas (PITFALLS.md)
- Test architecture: MEDIUM — pattern pytest+mock estabelecido (tests/ existe); 12 testes specificados mas nenhum implementado (Wave 0 gap natural)
- Healthcheck preview: LOW — decisão de discretion; planner pode ajustar

**Research date:** 2026-06-09 13:30 GMT-3

**Valid until:** 2026-07-09 (30 dias) — stack é estável; revisitar SE: (a) supabase-py 3.0 release antes desta data com suporte nativo a partial unique index, (b) cachetools 6.0 release com breaking changes, (c) Evolution API deprecar GROUP_PARTICIPANTS_UPDATE em favor de novo evento.

---

## RESEARCH COMPLETE

**Phase:** 10 - Schema + 3 paths webhook write + cache standalone
**Confidence:** HIGH

### Key Findings

1. **`supabase-py` 2.18 NÃO suporta `on_conflict` com partial unique index** [VERIFIED via GitHub discussions/12565 — maintainer Supabase confirma]. Workaround: **RPC function SQL** `upsert_grupo_membership` com UPDATE-then-INSERT-with-fallback handling `unique_violation EXCEPTION`. ~80 linhas de SQL bem-escrito eliminam race + dedup + RLS-silent-deny de uma vez.

2. **Path 3 callsite EXATO identificado:** `leads.py` linhas 263-271 (DENTRO de `if _lead_confirmado_no_grupo:`, DEPOIS de `set_grupo_state(STATE_ATIVO)`, JUNTO com marker `GRUPO_LEAD_ENTROU_CRIACAO` que já existe). UPSERT substitui/complementa o marker; marker permanece em paralelo durante v2.2 para backwards compat (commit 96b72cc ainda confia nele).

3. **`instance_key` source-of-truth resolvido:** Path 1 e Path 2 usam `payload.instance` (instância origem do evento). Path 3 usa `evo_inst` (instância que CRIOU o grupo). Lookup futuro em `lead_in_group()` Fase 11 compara com `empresas.evolution_instancia` atual.

4. **APScheduler já está pronto para Fase 12** — `app/scheduler.py:5` é singleton `AsyncIOScheduler`, padrão `replace_existing=True` usado em 4 callsites em prod. Fase 10 não toca aqui.

5. **Cache singleton design completo:** `cachetools.TTLCache(512, ttl=300)` + `threading.RLock` + helper centralizado `upsert_grupo_membership` faz write-through invalidate. Multi-tenant isolation via `empresa_id` no primeiro componente da chave. `clear_all()` exposto para fixture pytest.

6. **Helper centralizado é o multiplicador de valor desta fase.** `upsert_grupo_membership()` único entrypoint elimina Pitfalls 6 (race), 13 (RLS silent deny), 2 (cache mascarando) e 8 (dedup) de uma vez. 60 linhas de Python.

### File Created

`c:/Projetos/Leadflow/.planning/phases/10-schema-3-paths-webhook-write-cache-standalone/10-RESEARCH.md`

### Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Standard Stack | HIGH | Versões confirmadas em requirements.txt; cachetools 5.5.0 cross-ref'd |
| Architecture (3 paths + helper + cache) | HIGH | Codebase introspection direta confirma 2 de 3 callsites exatos; Path 2 tem 1 ASSUMED (A4 — handler MESSAGES_UPSERT em agente.py) resolvível em 2min de grep no kickoff |
| supabase-py workaround (RPC) | HIGH | Verified via WebFetch GitHub discussion — maintainer Supabase oficial |
| Pitfalls | HIGH | 7 catalogados, todos amparados em casos reais + sources externas verificadas |
| Test architecture | MEDIUM | Pattern estabelecido (pytest+mock); 12 testes spec mas nenhum implementado (Wave 0 gap natural) |
| Healthcheck preview | LOW | Discretion — recomenda endpoint skinny em Fase 10, full em Fase 14 |

### Open Questions (4 identified, none blocking)

1. Coluna `fonte` — recomendação: manter (custo trivial, valor de debug alto)
2. Path 2 localização exata — resolvível em 2min de grep no kickoff
3. Healthcheck skinny em Fase 10 vs full em Fase 14 — planner decide
4. Deletar marker `LEAD_LID:` em Fase 11 vs manter — fora desta fase

### Assumptions Log (8 ASSUMED, 6 baixo risco / 2 médio)

A2 (`messageTimestamp` sempre presente) e A4 (Path 2 em agente.py) são os 2 MÉDIO — ambos resolvíveis em <30min de investigação no kickoff (1 dump de payload real + 1 grep).

### Ready for Planning

Research complete. Planner pode criar PLAN.md files. **Sugestão de wave structure para a fase:**

- **Wave 0 (paralelo, pré-deps):** confirmar versão cachetools disponível em PyPI; localizar Path 2 exato em agente.py (grep); 1 dump payload real GROUP_PARTICIPANTS_UPDATE
- **Wave 1 (foundation):** Migration 004 SQL + aplicar via Supabase Studio + helper `grupo_membership.py:upsert_grupo_membership` + `probe_cache.py` singleton + add cachetools em requirements.txt
- **Wave 2 (paths — paralelizável):** Path 1 patch em grupo_webhook.py | Path 2 patch em agente.py | Path 3 patch em leads.py
- **Wave 3 (tests + healthcheck skinny):** tests/test_grupo_membership_upsert.py + tests/test_probe_cache.py + endpoint `/admin/grupo-membership/health` skinny
- **Wave 4 (verification):** suite green + smoke manual Supabase Studio + 24h obs em prod via `[MEMB-WRITE]` logs antes de fechar fase
