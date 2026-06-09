# Phase 11: `lead_in_group()` Consumer + Migrar Fallback Callers + Coalescing Async — Research

**Researched:** 2026-06-09
**Domain:** Backend FastAPI single-instance, async consumer da tabela `grupo_membership` (Fase 10), `asyncio.Lock` coalescing, migração de 6 callsites de probe Evolution
**Confidence:** HIGH (codebase introspection direta — todos os callsites confirmados via grep; estado da Fase 10 confirmado via SUMMARYs)

---

## Summary

A Fase 11 fecha o loop webhook-first iniciado na Fase 10. A fundação já está em prod desde 2026-06-09 (build `2026-06-09-grupo-membership-v2-fundacao`): tabela `grupo_membership` com `instance_key`, helper `upsert_grupo_membership` (único write path), cache singleton `probe_cache` (`TTLCache 512/300s` + `RLock`) com invalidação write-through, e 3 paths de escrita ativos (webhook ADD, MESSAGES_UPSERT, createGroup direct). **Nada consome ainda.**

A Fase 11 introduz `lead_in_group()` em `app/services/grupo_membership.py` — função central que consulta `grupo_membership` PRIMEIRO + cache, caindo no probe Evolution apenas quando row ausente/stale ou `saiu_em != null`. Migra os **6 callsites confirmados** em `grupo_fallback.py` (linhas 251, 311, 337, 477, 624, 1173, 1256 — sim, são **7 chamadas** quando contadas no grep, mas 6 funcionalmente distintas porque a 1173 e 1256 são duas branches do mesmo polling job). Adiciona `asyncio.Lock` per-chave para coalescer probes concorrentes (PROBE-COALESCE-01, movido da Fase 10).

**Primary recommendation:** Implementar `lead_in_group()` como wrapper aditivo — `verificar_lead_no_grupo` continua existindo intocado e segue sendo chamado por admin endpoints diagnósticos. Os 6 callsites de `grupo_fallback.py` migram em uma única wave (são auto-contidos, todos no mesmo arquivo). Coalescing mora no próprio `grupo_membership.py` (perto do consumer), usando `asyncio.Lock` global por chave `(empresa_id, grupo_jid, telefone, lid)`, com cleanup quando a coroutine termina (não TTL — cleanup natural de `try/finally`).

---

<user_constraints>
## User Constraints (from CONTEXT.md)

CONTEXT.md **não foi gerado** para a Fase 11 — `/gsd-research-phase` está sendo invocado direto. O `additional_context` do prompt funciona como discussão:

### Locked Decisions (do prompt orquestrador + ROADMAP)
- **Função:** `lead_in_group(sb, empresa_id, telefone, grupo_jid, lid="") -> dict {in_group, source, last_event_at, instance_key_match}`
- **Decisão tree:** consulta `grupo_membership` PRIMEIRO; só vai pro probe Evolution se row ausente OU `saiu_em != null` OU `instance_key` mismatch
- **Janela stale 6min:** se grupo criado <6min atrás E sem row, retorna `pending` (não conclusivo) para permitir Fase 12 enfileirar retry
- **Sentinel para órfão de instância:** `instance_key_match=False` retorna sentinel que permite caller decidir criar novo grupo (caso Fernanda)
- **Coalescing:** `asyncio.Lock` por chave evita probe concorrente (3 jobs paralelos → 1 chamada Evolution)
- **6 callsites:** migrar em `grupo_fallback.py` (251, 311, 337, 477, 624, 1173, 1256); probe direto permanece em endpoint admin diagnóstico
- **Logs:** `[MEMB-LOOKUP] source={membership|cache|probe|stale} grupo={jid} verdict={...}` em todas as consultas
- **Build atual em prod:** `2026-06-09-grupo-membership-v2-fundacao` (escreve, não lê ainda)

### Claude's Discretion
- Estrutura interna do dict de retorno (campos adicionais, ex: `latency_ms`, `cache_hit`)
- Localização do dict de locks (`grupo_membership.py` recomendado — perto do consumer; alternativa `probe_cache.py` rejeitada por mixing concerns)
- Schema/level dos logs (recomendado: INFO key=value formato, mesmo padrão `[MEMB-WRITE]` já em prod)
- Estratégia de cleanup de locks (recomendado: `try/finally` natural, NÃO TTL)
- Comportamento ANTES da Fase 12 deployar (recomendado: probe Evolution direto mesmo em grupos <6min; Fase 12 troca pra `pending`)

### Deferred Ideas (OUT OF SCOPE)
- Retry async APScheduler 30s/2min/5min (Fase 12 — PROBE-RETRY-01/02)
- LEAVE handler / `saiu_em` consumer (Fase 13 — LEAVE-02)
- FSM audit log `caller` obrigatório (Fase 13 — FSM-AUDIT-02)
- Migrar `confirmacao_agendamento.py:291` (Fase 12, junto com retry)
- Migrar `leads.py:123` (probe de reuso é validação "vivo agora" — NÃO migra)
- Migrar `warmup_grupo.py` (Fase 12 — caller de margem)
- Migrar `admin.py:769, 981` (endpoints diagnóstico — NÃO migra, mantém probe direto)
- Endpoint `/health/grupo-membership` (Fase 14)
- Backfill retroativo de grupos antigos
- Multi-instance backend / migration in-memory → Redis
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **MEMB-05** | Função `lead_in_group(sb, empresa_id, telefone, grupo_jid, lid="") -> dict {in_group, source, last_event_at, instance_key_match}` consulta `grupo_membership` PRIMEIRO; só vai pro probe Evolution se row ausente OU `saiu_em != null` OU `instance_key` mismatch | §3 Decision tree completa + §4 sentinel órfão; §6 query SQL com filtro `instance_key` |
| **PROBE-COALESCE-01** | `asyncio.Lock` por chave evita 3 jobs probando o mesmo grupo simultaneamente | §5 design completo: chave, ownership, cleanup, comportamento sob load |
| **(migração 6 callsites)** | Os 6 callsites em `grupo_fallback.py` chamam `lead_in_group()` em vez de `verificar_lead_no_grupo` direto | §2 mapa exato linha-por-linha; §7 padrão de substituição |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

Backend `CLAUDE.md` é específico para edição cirúrgica em `agente.py` (trava Q1/Q2). NÃO se aplica diretamente à Fase 11 (que mexe em `grupo_membership.py` e `grupo_fallback.py`). Mas as **regras gerais valem**:
- NÃO refatorar fluxo sem necessidade
- NÃO mexer em `google_calendar.py`
- Preservar comportamento atual
- USAR o que já existe como fonte de verdade

Aplicado à Fase 11:
- Wrapper aditivo (`lead_in_group()`), NÃO refactor de `verificar_lead_no_grupo`
- NÃO mexer em FSM (`grupo_state.py`) — isso é Fase 13
- Preservar todos os fixes 08/06 + v2.1 markers
- USAR `upsert_grupo_membership`, `parse_evolution_timestamp`, `probe_cache.get/set` como contratos já em prod

---

## Standard Stack

### Core (TODOS já em prod — Fase 11 não adiciona dependências)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `asyncio.Lock` | stdlib Python 3.13 | Coalescing per-key | Mesmo event loop FastAPI+APScheduler → zero overhead |
| `cachetools.TTLCache` | 5.5.0 | Cache hit fast-path | Já validado em Fase 10 (`probe_cache.py`) |
| `supabase-py` | >=2.18 | Query `grupo_membership` | Mesma client `sb` já usada pelo helper |
| `httpx.AsyncClient` | 0.27 | Probe Evolution fallback | Já em `verificar_lead_no_grupo` |
| `apscheduler.AsyncIOScheduler` | 3.10.4 | (Fase 12) | Singleton `app.scheduler.scheduler` — NÃO usado nesta fase |

### Já entregue pela Fase 10 (consumidos pela Fase 11)
| Module | Public exports | Como Fase 11 usa |
|--------|---------------|------------------|
| `app.services.grupo_membership` | `upsert_grupo_membership`, `get_instance_key`, `parse_evolution_timestamp` | Adiciona `lead_in_group()` no MESMO arquivo + helper `_query_membership_row` |
| `app.services.probe_cache` | `get`, `set`, `invalidate`, `clear_for_group`, `stats`, `clear_all` | `lead_in_group()` chama `get` no fast-path + `set` após probe |
| `app.services.evolution` | `verificar_lead_no_grupo` | Continua INTOCADO — `lead_in_group()` chama como fallback |

### Alternatives Considered
| Instead of | Could Use | Tradeoff | Decisão |
|------------|-----------|----------|---------|
| `asyncio.Lock` por chave | Global lock único | Serializa TODOS os lookups (degrada P99) | Per-key |
| Locks em `probe_cache.py` | Locks em `grupo_membership.py` | Mistura concerns (cache != coalescing) | Em `grupo_membership.py` |
| TTL nos locks | Cleanup via `try/finally` | TTL precisa background task | `try/finally` natural |
| `asyncio.Event` + future compartilhado | `asyncio.Lock` simples | Event futures dão piggyback mas complicam exception path | `asyncio.Lock` (mais simples; coalesce via "lock → re-check cache") |
| Reescrever `verificar_lead_no_grupo` | Wrapper `lead_in_group()` | Reescrita quebra v2.1 testes + 4 admin/diagnóstico callers | Wrapper |
| Migrar tudo de uma vez (incluindo confirmacao/warmup/leads) | Migrar SÓ os 6 de grupo_fallback.py | Aumenta blast radius da Fase 11 sem ganho — outros têm dependência de retry (Fase 12) | Apenas os 6 |

**Instalação:** nenhuma (zero novas dependências).

---

## Architecture Patterns

### Recommended Module Structure (após Fase 11)

```
app/services/
├── grupo_membership.py    # +lead_in_group, +_query_membership_row, +probe_lock_for, +_LOCKS dict
├── probe_cache.py         # SEM mudanças (intocado da Fase 10)
├── evolution.py           # SEM mudanças (verificar_lead_no_grupo intocado)
├── grupo_fallback.py      # MODIFICADO: 6 callsites trocam verificar_lead_no_grupo → lead_in_group
└── grupo_state.py         # SEM mudanças (Fase 13 mexe aqui)

app/routers/
├── grupo_webhook.py       # SEM mudanças (Fase 10 entregou)
├── leads.py               # SEM mudanças (Fase 10 entregou Path 3)
├── agente.py              # SEM mudanças (Fase 10 entregou Path 2)
├── confirmacao_agendamento.py  # SEM mudanças (Fase 12 migra)
├── warmup_grupo.py        # SEM mudanças (Fase 12 migra)
└── admin.py               # SEM mudanças (mantém probe direto pra diagnóstico)
```

### Pattern 1: Wrapper Aditivo (não invasivo)
**What:** `lead_in_group()` é função NOVA. `verificar_lead_no_grupo` continua existindo intocado e segue funcionando.
**When to use:** Sempre que migrar fonte primária de dados — manter o caminho legacy operacional como fallback de emergência + diagnóstico.
**Example:**
```python
# app/services/grupo_membership.py — pseudocódigo conceitual (NÃO normativo)
# Sources: [VERIFIED: codebase introspection — assinatura espelha probe atual evolution.py:198]
async def lead_in_group(
    sb,
    empresa_id: str,
    telefone: Optional[str],
    grupo_jid: str,
    lid: str = "",
    *,
    evo_url: str = "", evo_key: str = "", evo_inst: str = "",
    allow_probe_fallback: bool = True,
) -> dict:
    """
    Retorna {in_group, source, last_event_at, instance_key_match}.

    source ∈ {'membership', 'cache', 'probe', 'stale_window', 'left_group', 'orphan', 'unknown'}
    in_group ∈ {True, False, 'pending'}
    """
    ...
```

### Pattern 2: Cache fast-path antes da query SQL
**What:** `probe_cache.get(...)` é fast-path. Hit → return imediato. Miss → query Postgres.
**Why:** Cache é write-through invalidado pelo helper. Hit é correto por construção.
**Example:** Ver §6.

### Pattern 3: Coalescing via Lock + Re-check Cache (double-checked locking)
**What:** Antes de adquirir lock, check cache. Após adquirir lock, **re-check cache** (outro consumer pode ter populado durante a espera).
**Why:** Evita probe redundante quando jobs concorrentes esperaram pelo lock.
**Example:**
```python
# app/services/grupo_membership.py — design conceitual
# Sources: [CITED: superfastpython.com/asyncio-lock-tutorial — coalescing pattern]
_probe_locks: dict[tuple, asyncio.Lock] = {}
_locks_meta_lock = asyncio.Lock()  # protege _probe_locks dict

async def _get_lock(key: tuple) -> asyncio.Lock:
    async with _locks_meta_lock:
        lock = _probe_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _probe_locks[key] = lock
        return lock

async def _probe_with_coalesce(key, probe_fn):
    lock = await _get_lock(key)
    async with lock:
        # re-check cache (outro consumer pode ter populado)
        cached = probe_cache.get(*key_to_args(key))
        if cached is not None:
            return {'in_group': cached, 'source': 'cache'}
        # ainda miss → realmente probe
        result = await probe_fn()
        probe_cache.set(*key_to_args(key), result)
        return result
    # NOTA: NÃO removemos lock do dict — entries pequenas, cleanup é Fase 12+ se necessário
```

### Anti-Patterns to Avoid
- **TTL nos locks:** complica com background task. Locks são objetos pequenos (~200 bytes). Ao máximo 512 entries (mesma cota do `probe_cache`) — ~100KB. Não é problema.
- **Lock global único:** serializa TODAS as consultas, transforma cache hit (1μs) em fila de espera. Per-key é mandatório.
- **Reescrever `verificar_lead_no_grupo`:** quebra 4 callers fora do escopo (admin endpoints, leads.py reuso, confirmacao, warmup) + 6 testes pytest da v2.1. Wrapper é o padrão correto.
- **Cachear `pending`:** `pending` é estado temporal (janela <6min). Cachear bloqueia descoberta quando webhook chega na janela. NÃO cachear None nem `pending` (já é o comportamento de `probe_cache.set(value=None)` que rejeita silenciosamente — confirmado em `probe_cache.py:62`).
- **Atualizar `grupo_membership` no path do consumer:** dispersa lógica de materialização. Só os 3 paths da Fase 10 + admin force escrevem. Consumer SÓ LÊ. Exceção: se probe Evolution confirma `in_group=True` e tabela estava vazia, **opcionalmente** chamar `upsert_grupo_membership(..., fonte='probe_backfill')` — mas isso é decisão do PLAN.md, não obrigatório nesta fase.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cache TTL/eviction | Custom dict + datetime expiry | `probe_cache` (Fase 10 — `cachetools.TTLCache`) | Race conditions em cleanup, OOM, edge cases. Já entregue. |
| Coalescing primitivos | Future compartilhado, Event, Condition | `asyncio.Lock` + re-check cache | Pattern documentado, simples, correto. Future-sharing tem edge case com exceptions. |
| Parser timestamp Evolution | int → datetime ad-hoc | `parse_evolution_timestamp` (Fase 10) | Cobre 3 shapes (epoch s/ms, ISO, None). Já em prod. |
| Lookup instance_key da empresa | Query inline em cada caller | `get_instance_key(sb, empresa_id)` (Fase 10) | Centralizado, fallback `evolution_instancia` → `config_apis`. |
| Cache invalidação write-through | Pós-UPSERT chamar invalidate manual | `upsert_grupo_membership` já faz | Helper invalida atomicamente após RPC success. NÃO replicar. |
| Probe HTTP Evolution | Refazer findGroupInfos | `verificar_lead_no_grupo` (existente) | 92 linhas de matcher @lid + 3-shape participants parsing + Karla bug fix. NÃO tocar. |

**Key insight:** A Fase 10 entregou contratos limpos. Fase 11 é PURE CONSUMER — chama API existente, não constrói nada novo de infra. O único pedaço de infra nova é o `_probe_locks` dict + helper de coalesce (~20 linhas).

---

## 1. Mapa Exato dos 6 Callsites

Confirmado via `grep -n "verificar_lead_no_grupo" leadflow-backend/app/services/grupo_fallback.py` (em 2026-06-09):

| # | Linha | Função/Contexto | Argumentos | Veredicto pós-migração | Flag `schedule_retry_on_negative` (Fase 12) |
|---|-------|-----------------|------------|-----------------------|---------------------------------------------|
| 1 | **251** | `ativar_fallback_se_necessario` — bloco 1b "legacy markers detectados, valida via Evolution" | `(evo_url, evo_key, evo_inst, grupo_jid, telefone, lead_lid=_lid_leg)` | `lead_in_group(sb, empresa_id, telefone, grupo_jid, lid=_lid_leg, evo_url=..., evo_key=..., evo_inst=...)` | False (decisão SÍNCRONA — ativar Phase 7 agora) |
| 2 | **311** | `ativar_fallback_se_necessario` — bloco 1c "FSM=ATIVO + bypass marker, probe live" | mesmo padrão | mesmo padrão | False (decisão SÍNCRONA) |
| 3 | **337** | `ativar_fallback_se_necessario` — bloco 2 "log informativo (sempre ativa Phase 7)" | mesmo padrão | mesmo padrão | False (só informativo) |
| 4 | **477** | `_disparar_convite_lead_se_aguardando` — "Bug Vanusa: probe live antes de mandar DM convite (60s delayed)" | mesmo padrão | mesmo padrão | False (decisão SÍNCRONA — disparar convite agora) |
| 5 | **624** | `_disparar_alerta_grupo_se_aguardando` — "FIX Luciane: probe live antes do alerta (180s delayed)" | mesmo padrão | mesmo padrão | False (decisão SÍNCRONA) |
| 6 | **1173** | `polling_grupos_aguardando` — branch "leads em GRUPO_AGUARDANDO_ENTRADA" | `(cfg["url"], cfg["key"], cfg["inst"], grupo_jid, telefone, lead_lid=_lid_pl)` | mesmo padrão | False (polling é o retry — não escalar) |
| 7 | **1256** | `polling_grupos_aguardando` — branch "leads em FALLBACK_1_1 (FIX 26/05)" | `(cfg["url"], cfg["key"], cfg["inst"], grupo_jid, tel, lead_lid=_lid_fb)` | mesmo padrão | False (polling) |

**Observação:** O ROADMAP/CONTEXT diz "6 callsites" — funcionalmente são 6 *blocos lógicos*. O grep conta 7 (251, 311, 337, 477, 624, 1173, 1256) mas o callsite #6 (`polling_grupos_aguardando`) tem 2 branches (1173 + 1256). PLAN.md deve tratar como **7 substituições mecânicas em 6 blocos lógicos**.

**Linha 35 (import):** `verificar_lead_no_grupo` importado de `app.services.evolution`. **Manter o import** — outros consumers via `from app.services.evolution import` (linha 475, 622) ainda usam. Adicionar nova linha: `from app.services.grupo_membership import lead_in_group`.

**NÃO migrar (mantém probe direto):**
- `admin.py:769` (endpoint admin diagnóstico — explicit ROADMAP success criterion #3)
- `admin.py:981` (endpoint admin diagnóstico — mesmo motivo)
- `leads.py:123` (probe de reuso é validação "vivo agora" — Pitfall 4: grupo órfão; admin endpoint cuida do bookkeeping)
- `confirmacao_agendamento.py:291` (Fase 12 — tem margem temporal D-1, ganha retry async)
- `warmup_grupo.py:781` (Fase 12)
- `tests/test_verificar_lead_no_grupo_phase3.py` (testes da v2.1 — preservar)

---

## 2. `lead_in_group()` Decision Tree Completa

```
                lead_in_group(sb, empresa_id, telefone, grupo_jid, lid, evo_url, evo_key, evo_inst, allow_probe_fallback=True)
                                                     │
                                                     ▼
                                  ┌──────────────────────────────────────┐
                                  │ STEP 1 — CACHE FAST-PATH              │
                                  │ probe_cache.get(empresa_id,           │
                                  │   grupo_jid, telefone, lid)           │
                                  └──────────────────────────────────────┘
                                                     │
                          ┌──────────────────────────┼──────────────────────────┐
                          ▼                          ▼                          ▼
                       HIT True/False             MISS (None)
                          │                          │
                          ▼                          ▼
            { in_group: cached,            ┌─────────────────────────┐
              source: 'cache',             │ STEP 2 — QUERY MEMBERSHIP│
              instance_key_match: True,    │  SELECT entrou_em,       │
              last_event_at: None }        │    saiu_em, instance_key,│
              [MEMB-LOOKUP source=cache]   │    atualizado_em         │
                                           │  FROM grupo_membership   │
                                           │  WHERE empresa_id=$1     │
                                           │    AND grupo_jid=$2      │
                                           │    AND (telefone=$3      │
                                           │      OR lid=$4)          │
                                           │    AND saiu_em IS NULL   │
                                           │  ORDER BY atualizado_em  │
                                           │    DESC LIMIT 1          │
                                           └─────────────────────────┘
                                                     │
                          ┌──────────────────────────┼──────────────────────────┐
                          ▼                          ▼                          ▼
                       ROW found alive            NO row (saiu_em NULL)        DB error
                          │                          │                          │
                          ▼                          ▼                          ▼
              ┌─────────────────────┐      ┌──────────────────┐    { in_group: None,
              │ STEP 3a:            │      │ STEP 4 — STALE   │      source: 'unknown',
              │ instance_key match? │      │   WINDOW CHECK   │      detail: 'db_error' }
              │ row.instance_key == │      │ Look up          │      [MEMB-LOOKUP source=unknown]
              │   get_instance_key( │      │ agendamento.     │
              │   sb, empresa_id) ? │      │   grupo_criado_em│
              └─────────────────────┘      │ (or grupo_       │
                          │                 │  agendamento.    │
              ┌───────────┼─────────┐       │  criado_em)      │
              ▼           ▼         ▼       │ AND now - criado │
            YES         NO        DB error  │ < 6min           │
              │           │                 └──────────────────┘
              ▼           ▼                            │
   { in_group: True,  { in_group: False,    ┌─────────┼──────────┐
     source:           source: 'orphan',    ▼         ▼          ▼
     'membership',     instance_key_       <6min     >6min     no agendamento
     instance_key_     match: False,         │         │      (skip stale check)
     match: True,      last_event_at:        ▼         ▼          ▼
     last_event_at:    row.atualizado_em }   STEP 5    STEP 5     STEP 5
     row.atualizado_   [MEMB-LOOKUP          (sync     (sync      (sync probe;
     em }              source=orphan]        probe)    probe)     same flow)
     [MEMB-LOOKUP                              │
      source=                  Notes Fase 12 (NÃO Fase 11):
      membership]              em vez de STEP 5 sync probe, retorna
                               { in_group: 'pending', source: 'stale_window' }
                               + schedule_probe_retry(...)


            STEP 5 — PROBE FALLBACK (when allow_probe_fallback=True)
                          │
                          ▼
              ┌────────────────────────────────────────┐
              │ COALESCING (PROBE-COALESCE-01)         │
              │ lock = await _get_lock(key)            │
              │ async with lock:                       │
              │   # double-check cache                 │
              │   cached = probe_cache.get(...)        │
              │   if cached is not None:               │
              │     return cache hit                   │
              │   # really probe                       │
              │   probe = await verificar_lead_no_grupo│
              │   probe_cache.set(..., probe.in_group) │
              └────────────────────────────────────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        probe.in_group  False      None (evolution error)
            =True
              │           │           │
              ▼           ▼           ▼
   { in_group: True,  { in_group:    { in_group: None,
     source: 'probe',  False,         source: 'probe',
     instance_key_     source:        detail: probe.erro,
     match: True,      'probe',       instance_key_match:
     last_event_at:    instance_key_  None }
     None }            match: True,   [MEMB-LOOKUP source=probe verdict=None]
     [MEMB-LOOKUP      last_event_at:
      source=probe     None }
      verdict=True]    [MEMB-LOOKUP
                        source=probe
                        verdict=False]
```

### Retorno: contrato exato

```python
# Tipos (TypedDict conceitual — NÃO normativo; PLAN.md decide se usar TypedDict ou plain dict)
{
    'in_group': True | False | None,    # None se erro probe; nunca 'pending' nesta fase
    'source': Literal[
        'cache',         # cache hit (qualquer valor)
        'membership',    # row em grupo_membership com instance_key match
        'orphan',        # row mas instance_key mismatch (caso Fernanda)
        'probe',         # caiu pro probe Evolution + sucesso
        'unknown',       # erro DB OU probe falhou + Fase 11 não enfileira retry
        # 'stale_window',  # NÃO usado nesta fase — Fase 12 reativa para pending
        # 'left_group',    # NÃO usado nesta fase — Fase 13 ativa quando saiu_em != null
    ],
    'instance_key_match': bool | None,   # True se row matched ou probe (n/a); False só em 'orphan'
    'last_event_at': datetime | None,    # row.atualizado_em em 'membership'/'orphan'; None em 'cache'/'probe'/'unknown'
}
```

**Notas sobre o contrato:**
- `last_event_at` em `'cache'` é `None` porque cache não armazena timestamp (apenas bool). PLAN.md pode decidir cachear tupla `(in_group, last_event_at)` — mas isso muda contrato do `probe_cache.set` da Fase 10. **Recomendação:** manter `None` em cache hit. Callers que precisam de timestamp consultam `grupo_membership` direto (raro).
- `instance_key_match=None` em `'probe'`: probe Evolution retornou sem que tabela tenha row — não há instance_key para comparar. Documenta como "irrelevante para este source".
- A flag `'pending'` em `in_group` é reservada para Fase 12 (stale window). Fase 11 sempre retorna True/False/None.

---

## 3. Janela Stale 6min — Comportamento Fase 11 vs Fase 12

| Cenário | Fase 11 (esta) | Fase 12 (futura) |
|---------|----------------|------------------|
| Row ausente + grupo criado <6min atrás | Probe síncrono Evolution + cache result | Retorna `{in_group: 'pending', source: 'stale_window'}` + `schedule_probe_retry()` |
| Row ausente + grupo >6min atrás | Probe síncrono + cache | Probe síncrono + cache (igual) |
| Row ausente + sem agendamento associado | Probe síncrono + cache | Probe síncrono + cache |

**Recomendação:** **NÃO implementar `pending` nesta fase**. Justificativa:
1. PROBE-RETRY-01/02 (mecanismo retry) só existe na Fase 12. Retornar `pending` sem caller saber tratar = deadlock silencioso.
2. Os 6 callers migrados (todos em `grupo_fallback.py`) tomam decisão SÍNCRONA — não têm margem para esperar retry async. Eles confirmam isso via "False (decisão SÍNCRONA)" na tabela do §1.
3. O comportamento atual (probe síncrono em janela <6min) já é o que está em prod e validado pelos 6 fixes 08/06.

**Como PLAN.md pode preparar para Fase 12:** adicionar parâmetro `schedule_retry_on_negative: bool = False` na assinatura, ignorado nesta fase. Fase 12 ativa.

### Como identificar "grupo criado <6min atrás" (para Fase 12 quando implementar)
Confirmado via Fase 10 SUMMARY 10-04 (Path 3 createGroup): `leads.py` insere marker `GRUPO_LEAD_ENTROU_CRIACAO:{grupo_jid}` em `conversas` ao criar grupo. Pode-se também consultar `agendamentos.grupo_jid` + `agendamentos.criado_em`. Recomendação: query `conversas` para o marker mais recente (mais simples). Plano Fase 12.

---

## 4. Caso Fernanda (Grupo Órfão de Instância Antiga)

**Caso real (07/06):** Lead reagendado, sistema consulta `agendamentos.grupo_jid` antigo (criado em 17/04 na instância `bia-rejane`), tenta reusar. Tabela `grupo_membership` retorna row velha (lead estava lá em abril). Mas Rejane migrou para instância `rejane-leal-mentora` — grupo está órfão.

### Resolução Fase 11

```python
# Pseudo-código do STEP 3a
row_instance_key = row.get('instance_key')
current_instance_key = get_instance_key(sb, empresa_id)  # helper Fase 10
if not current_instance_key:
    # Sem instance_key configurada → conservador, trata como match (não bloqueia v1)
    instance_match = True
elif row_instance_key.lower() == current_instance_key.lower():
    instance_match = True
else:
    instance_match = False  # ÓRFÃO — caso Fernanda
    return {
        'in_group': False,
        'source': 'orphan',
        'instance_key_match': False,
        'last_event_at': row.get('atualizado_em'),
    }
```

**Caller decide o que fazer:**
- `ativar_fallback_se_necessario` linha 251 (`_check_leg`): se `source='orphan'` → `_confirmado_grupo_atual = False` → ativa Phase 7 (cria novo grupo no convite delayed).
- `ativar_fallback_se_necessario` linha 311 (`_probe_top` FSM=ATIVO bypass): se `source='orphan'` → segue conservador (ativa fallback).
- `polling_grupos_aguardando` (1173, 1256): se `source='orphan'` → não promove ATIVO; deixa em FALLBACK_1_1 (próximo ciclo polling pega ou Phase 13 LEAVE handler).

**NÃO REGREDIR:** Fix `GRUPO-REUSO-01` (commit 7e366bd) em `leads.py:123` mantém probe direto via `findGroupInfos` ao reusar grupo — defesa em profundidade.

---

## 5. `asyncio.Lock` Coalescing Design (PROBE-COALESCE-01)

### 5a. Onde mora

**Decisão:** `app/services/grupo_membership.py` (perto do consumer).

**Justificativa:**
- Coalescing é uma preocupação de READ — `probe_cache.py` é puramente STORAGE (key-value + TTL). Separação de concerns.
- `grupo_membership.py` já é o módulo que entende a decisão tree. Locks são detalhe de implementação do `lead_in_group()`.
- Evita import cycle: `probe_cache.py` não conhece nem `lead_in_group`, nem `verificar_lead_no_grupo` — mantém standalone.

### 5b. Estrutura do dict

```python
# app/services/grupo_membership.py
import asyncio

# Type alias da chave (igual à do probe_cache pra consistência)
ProbeLockKey = tuple  # (empresa_id, grupo_jid, telefone_or_empty, lid_lower)

_probe_locks: dict[ProbeLockKey, asyncio.Lock] = {}
_probe_locks_dict_lock = asyncio.Lock()  # protege mutação do dict _probe_locks

async def _get_probe_lock(key: ProbeLockKey) -> asyncio.Lock:
    """Retorna lock per-key. Cria sob demanda (thread-safe via meta-lock)."""
    async with _probe_locks_dict_lock:
        lock = _probe_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _probe_locks[key] = lock
        return lock
```

### 5c. Chave do lock

**Igual à chave do `probe_cache`:** `(empresa_id, grupo_jid, telefone_or_empty, lid_lower)`.

**Por quê não simplificar para `(empresa_id, grupo_jid)`:**
- Aquec dispara probe para 1 telefone. Notif D-1 dispara para mesmo telefone. Timeout 30min para mesmo telefone. **Mesma chave** → coalesce 3 jobs em 1 probe.
- Telefones DIFERENTES no mesmo grupo (raro: 1 grupo tem 1 lead em v2.1, mas defensivo) → chaves diferentes, podem rodar em paralelo.

**Por quê não usar telefone OU lid (XOR):**
- Helper de Fase 10 já trata: callers passam `telefone, lid` separados. Se ambos estão presentes, são informação complementar — mesmo lead. Chave inclui ambos para tracking, mas matching é OR no SQL.

### 5d. Cleanup dos locks

**Decisão:** **NÃO** remover do dict. Justificativa:
- Locks são objetos pequenos (~200 bytes cada). 512 entries (mesma cota que `probe_cache.maxsize`) → ~100KB. Negligível.
- Cleanup ativo requer background task ou TTL — complexidade desproporcional ao ganho.
- Single-worker Easypanel restarta a cada deploy (~1x/dia em fase ativa). Dict zera natural.
- Fase 12+ pode adicionar cleanup se profiling mostrar crescimento (improvável).

**Cap defensivo opcional (PLAN.md decide):** se `len(_probe_locks) > 2048`, drop oldest via FIFO. Provavelmente desnecessário — mesmas 30 empresas × ~5 grupos ativos = ~150 chaves esteady-state. Margem alta de 13x.

### 5e. Comportamento sob load (3 jobs concorrentes mesma chave)

```
T=0ms    Job A: lead_in_group(...)
         → cache miss → query membership miss → probe path
         → _get_probe_lock(key) → cria lock A
         → async with lock A: (acquired imediato)

T=1ms    Job B: lead_in_group(...) MESMA chave
         → cache miss → query membership miss → probe path
         → _get_probe_lock(key) → retorna lock A existente
         → async with lock A: (BLOCKED, espera lock A)

T=2ms    Job C: lead_in_group(...) MESMA chave
         → mesmo caminho → BLOCKED no lock A

T=15ms   Job A: probe Evolution responde in_group=True
         → probe_cache.set(key, True)
         → libera lock A

T=15.1ms Job B: adquire lock A
         → DOUBLE-CHECK CACHE: probe_cache.get(key) → True (hit!)
         → return { in_group: True, source: 'cache' } SEM CHAMAR PROBE
         → libera lock A

T=15.2ms Job C: adquire lock A → mesmo flow do Job B → cache hit → libera
```

**Resultado:** 3 lookups paralelos, **1 chamada HTTP Evolution**. Atinge sucesso PROBE-COALESCE-01.

**Chaves diferentes (Job D para outro grupo):** `_get_probe_lock(key_D)` retorna lock diferente. Rodam em paralelo, zero contenção entre A/B/C e D.

### 5f. Lock granularidade vs read miss penalty

**Concern:** todo lookup adquire `_probe_locks_dict_lock` (meta-lock) para criar/obter lock per-key. Isso serializa **a criação** de locks.

**Resolução:** meta-lock é mantido por <1μs (apenas dict.get + dict.set). Sob 1000 lookups/s, é overhead de ~1ms total. Insignificante.

**Alternativa rejeitada (`defaultdict(asyncio.Lock)`):** `defaultdict` não é thread-safe sob asyncio em todos os cenários edge — duas tasks simultâneas no mesmo key podem criar 2 locks diferentes. Meta-lock é a forma segura.

---

## 6. Query SQL `grupo_membership` Lookup

Confirmado via Fase 10 migration 004 (SUMMARY 10-02): tabela tem `instance_key`, partial unique index `WHERE saiu_em IS NULL`, lookup indexes `(empresa_id, grupo_jid, telefone) WHERE saiu_em IS NULL` + `(empresa_id, grupo_jid, lid) WHERE lid IS NOT NULL AND saiu_em IS NULL`.

### Query recomendada (Postgres via supabase-py)

```python
# app/services/grupo_membership.py — helper de leitura
def _query_membership_row(sb, empresa_id: str, grupo_jid: str,
                          telefone: Optional[str], lid: Optional[str]) -> Optional[dict]:
    """
    Retorna dict com {entrou_em, saiu_em, instance_key, atualizado_em} ou None.

    NOTA: filtra por saiu_em IS NULL nesta fase (Fase 13 muda para incluir saiu_em
    para LEAVE handler).
    """
    try:
        q = sb.table('grupo_membership') \
            .select('entrou_em, saiu_em, instance_key, atualizado_em') \
            .eq('empresa_id', empresa_id) \
            .eq('grupo_jid', grupo_jid) \
            .is_('saiu_em', 'null') \
            .order('atualizado_em', desc=True) \
            .limit(1)

        # match por telefone OR lid (supabase-py: .or_)
        # Pelo menos um deve ser não-nulo (precondicao caller)
        if telefone and lid:
            q = q.or_(f'telefone.eq.{telefone},lid.eq.{lid}')
        elif telefone:
            q = q.eq('telefone', telefone)
        else:
            q = q.eq('lid', lid)

        result = q.execute()
        return result.data[0] if result.data else None
    except Exception as e:
        # Sinaliza erro DB para caller decidir 'unknown'
        print(f"[MEMB-LOOKUP] query_error empresa={empresa_id[:8]} grupo={grupo_jid[:24]} erro={e}")
        return None  # Caller verifica via flag separada se queremos distinguir
```

**Edge case:** `_query_membership_row` retorna `None` em DOIS cenários: (1) sem row, (2) erro DB. PLAN.md pode decidir retornar tupla `(row, error_flag)` para distinguir. **Recomendação:** distinguir via try/except no caller `lead_in_group()` — se exception, retorna `source='unknown'`. Manter helper retornando `Optional[dict]` simples.

**Performance:** index partial `(empresa_id, grupo_jid, telefone) WHERE saiu_em IS NULL` cobre. Lookup é index seek O(log n). Esperado <5ms P99 em prod.

---

## 7. Padrão de Substituição nos 6 Callsites

### Template antes (atual em prod)

```python
try:
    _lid_xxx = _get_lead_lid_for_group(sb, empresa_id, telefone, grupo_jid)
    _check_xxx = await verificar_lead_no_grupo(
        evo_url, evo_key, evo_inst, grupo_jid, telefone, lead_lid=_lid_xxx,
    )
    if _check_xxx.get("in_group") is True:
        # tomar decisão "está no grupo"
        ...
    else:
        # tomar decisão "fora ou incerto"
        ...
except Exception as _e_xxx:
    print(f"[XXX] erro: {_e_xxx}")
```

### Template depois (Fase 11)

```python
try:
    _lid_xxx = _get_lead_lid_for_group(sb, empresa_id, telefone, grupo_jid)
    _check_xxx = await lead_in_group(
        sb, empresa_id, telefone, grupo_jid,
        lid=_lid_xxx,
        evo_url=evo_url, evo_key=evo_key, evo_inst=evo_inst,
        allow_probe_fallback=True,
    )
    _in_group = _check_xxx.get("in_group")
    _source = _check_xxx.get("source")
    _instance_match = _check_xxx.get("instance_key_match")

    # Caso Fernanda: grupo órfão → mesma decisão de "fora" mas com sentinel
    if _source == 'orphan' or _instance_match is False:
        # Caller-specific: log + tratar como fora
        print(f"[XXX] {telefone} ORPHAN grupo={grupo_jid[:24]} (instance_key mismatch)")
        # No bloco 1c (linha 311), isso significa: FSM=ATIVO inválido, ativa fallback
        # No bloco 1b (linha 251): legacy markers ok mas grupo não é deste; ativa Phase 7

    if _in_group is True:
        # MESMA decisão "está no grupo" que antes
        ...
    else:
        # MESMA decisão "fora ou incerto" que antes
        ...
except Exception as _e_xxx:
    print(f"[XXX] erro: {_e_xxx}")
```

### Por callsite — observações específicas

| Callsite | Observação especial |
|----------|---------------------|
| **251 (`_check_leg`)** | Já tem fallback de exception ativa Phase 7 (conservador). Mantém. |
| **311 (`_probe_top` FSM=ATIVO)** | Tem o bypass do marker `GRUPO_LEAD_ENTROU_CRIACAO < 5min` ANTES do probe (linhas 296-308). **PRESERVAR esse bypass** — é PROBE-BYPASS-01. `lead_in_group` é chamado SÓ se bypass falha. |
| **337 (`check` informativo)** | Linha 323 diz "ESTRATÉGIA: ignora verificar_lead_no_grupo". Probe aqui é **só log informativo**, fluxo sempre ativa Phase 7. Migração mantém isso — não muda lógica de decisão. |
| **477 (`_check_live` convite-delayed)** | Tem `from app.services.evolution import verificar_lead_no_grupo` LOCAL (linha 475). Substituir por `from app.services.grupo_membership import lead_in_group`. |
| **624 (`_check_live` alerta-delayed)** | Mesmo padrão — import local linha 622. Substituir. |
| **1173 / 1256 (polling)** | Job APScheduler — single dispatch loop. Sem decisão urgente. Coalescing aqui ajuda **menos** (1 job só), mas mantém consistência. Importante: `cfg` é `(url, key, inst)` da empresa lookup, não `evo_url`/`evo_key`/`evo_inst` locais — adaptar nome. |

**Import:** adicionar 1 linha no topo de `grupo_fallback.py` (perto da linha 35):
```python
from app.services.grupo_membership import lead_in_group
```

**Não remover** o import de `verificar_lead_no_grupo` (linha 35) — callsites de exception path podem ainda querer probe direto como último recurso (decisão do PLAN.md).

---

## 8. Endpoint Admin "Probe Direto" (mantido para diagnóstico)

Confirmado:

| Arquivo | Linha | Endpoint | Por que NÃO migra |
|---------|-------|----------|-------------------|
| `admin.py` | 754, 769 | `/admin/grupo/forcar-revalidacao` (POST) ação `verificar` | Operador quer FRESH probe ignorando cache. Migração roubaria essa garantia. |
| `admin.py` | 898, 981 | `/admin/grupo/forcar-revalidacao` ação `auto` | Mesma razão. |

**Sugestão para PLAN.md:** adicionar **um único endpoint admin** novo `/admin/grupo/lead-in-group?empresa_id=...&grupo_jid=...&telefone=...` que invoca `lead_in_group()` para inspeção do consumer (retornando dict completo). Útil para debug do consumer em si. Marcar como **opcional** — sucess criterion ROADMAP só pede "probe direto permanece em endpoint admin", já satisfeito pelos endpoints existentes intocados.

---

## 9. Logs `[MEMB-LOOKUP]` Design

Padrão recomendado (alinhado com `[MEMB-WRITE]` da Fase 10, confirmado em `grupo_membership.py:74`):

```python
# Formato: key=value, espaços separadores, todos os campos em uma linha
print(f"[MEMB-LOOKUP] empresa={empresa_id[:8]} grupo={grupo_jid[:24]} "
      f"tel={telefone or '-'} lid={(lid or '-')[:24]} "
      f"source={source} in_group={in_group} "
      f"instance_match={instance_key_match} latency_ms={int(elapsed*1000)}")
```

### Campos
| Campo | Sempre presente | Valores |
|-------|----------------|---------|
| `empresa` | sim | `empresa_id[:8]` (privacidade + brevidade) |
| `grupo` | sim | `grupo_jid[:24]` (truncado — JID completo é longo) |
| `tel` | sim | `telefone` ou `-` |
| `lid` | sim | `lid[:24]` ou `-` |
| `source` | sim | `cache`/`membership`/`orphan`/`probe`/`unknown` |
| `in_group` | sim | `True`/`False`/`None` |
| `instance_match` | sim | `True`/`False`/`None` |
| `latency_ms` | recomendado | `int` ms — útil para monitorar P99 |

### Log level
**INFO em todas as consultas** (recomendação): match com `[MEMB-WRITE]` (também INFO) — alinha observabilidade. Volume estimado: ~50 lookups/min em pico × 1440 min/dia = ~72K linhas/dia. Aceitável para print direct (Easypanel docker logs handle).

**Alternativa DEBUG:** só promover INFO em casos interessantes (`source='orphan'`, `source='unknown'`, `latency_ms > 200`). Reduz volume 10x. **Trade-off:** debug fica mais difícil. **Decisão para PLAN.md.** Recomendação default: INFO em todas, igual `[MEMB-WRITE]`.

### Formato JSON vs key-value
**key-value** (escolhido): consistente com `[MEMB-WRITE]`, `[VERIFY-LEAD]`, `[FALLBACK-1_1]` (todos key-value). Easypanel docker logs grep-friendly. JSON estruturado quebra padrão e exigeparser.

---

## 10. Backward Compat

**Garantido por construção:**
- `verificar_lead_no_grupo` em `app/services/evolution.py` — **NÃO TOCADO** (intocado desde 21/05 v3 fix).
- 4 callers fora do escopo continuam funcionando: `admin.py:769`, `admin.py:981`, `leads.py:123`, `confirmacao_agendamento.py:291`, `warmup_grupo.py:781`.
- 6 testes pytest em `tests/test_verificar_lead_no_grupo_phase3.py` continuam passing (testam `verificar_lead_no_grupo` direto, não `lead_in_group`).
- Markers v2.1 (`LEAD_LID:{grupo_jid}:{lid}`, `GRUPO_AGUARDANDO_ENTRADA`, `GRUPO_STATE:*`, `GRUPO_LEAD_ENTROU_CRIACAO`) — intocados.
- FSM em `grupo_state.py` — intocado (Fase 13 mexe).
- 6 fixes 08/06 — intocados:
  - **AQUEC-FLOOR-01** (180s) — nem `lead_in_group` nem fallback caller mexem com aquec floor
  - **ALERTA-GRUPO-01** — alerta-delayed (callsite 624) continua skip envio (linha 647)
  - **PROBE-BYPASS-01** (`GRUPO_LEAD_ENTROU_CRIACAO < 5min`) — bypass mantido em linhas 296-308 ANTES de chamar `lead_in_group`
  - **GRUPO-REUSO-01** (`leads.py:123` `findGroupInfos` antes de reusar) — não tocado
  - **RECOVERY-STARTUP-01** — não tocado
  - **RECOVERY-AQUEC-01** — não tocado

**Pontos de cuidado para PLAN.md:**
- Substituição mecânica dos 7 calls com `lead_in_group()` precisa **manter sintaxe consistente** — não inverter argumentos `(grupo_jid, telefone)` vs `(telefone, grupo_jid)` (sim, são diferentes ordens! `verificar_lead_no_grupo(..., grupo_jid, telefone, ...)` vs assinatura `lead_in_group(sb, empresa_id, telefone, grupo_jid, ...)`).
- Adicionar `sb` (Supabase client) em todos os callsites — `verificar_lead_no_grupo` não precisava, `lead_in_group` precisa. `sb = get_supabase()` já está disponível em todos os 7 locations (`grupo_fallback.py` importa `get_supabase` no topo).
- `empresa_id` está disponível em todos os 7 callsites (argumento da função pai).

---

## 11. Testes para Coalescing

### 11a. Setup pytest

Já existe infraestrutura em `tests/` (Fase 9 do v2.1: `test_verificar_lead_no_grupo_phase3.py` é o padrão de mock).

```python
# tests/test_lead_in_group_coalesce.py — recomendação para PLAN.md
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from app.services.grupo_membership import lead_in_group
from app.services import probe_cache

@pytest.fixture(autouse=True)
def reset_state():
    """Reset cache + locks entre testes (evita Anti-pattern 2 do ARCHITECTURE)."""
    probe_cache.clear_all()
    # Acessa _probe_locks via import privado se PLAN.md decidir expor reset helper
    from app.services import grupo_membership as gm
    gm._probe_locks.clear()
    yield
    probe_cache.clear_all()
    gm._probe_locks.clear()
```

### 11b. Teste: 3 lookups concorrentes → 1 probe

```python
@pytest.mark.asyncio
async def test_coalesce_three_concurrent_lookups_one_probe(monkeypatch):
    """3 jobs paralelos pra mesma chave disparam 1 única chamada HTTP."""
    probe_call_count = 0
    probe_call_args = []

    async def fake_probe(base_url, api_key, instancia, grupo_jid, telefone, lead_lid=""):
        nonlocal probe_call_count
        probe_call_count += 1
        probe_call_args.append((grupo_jid, telefone, lead_lid))
        # Simula latência do probe Evolution
        await asyncio.sleep(0.05)
        return {"ok": True, "in_group": True, "erro": ""}

    monkeypatch.setattr(
        "app.services.grupo_membership.verificar_lead_no_grupo",
        fake_probe,
    )
    # Mock _query_membership_row para retornar None (miss)
    monkeypatch.setattr(
        "app.services.grupo_membership._query_membership_row",
        lambda *a, **k: None,
    )

    sb_mock = AsyncMock()  # ou Mock — não importa, helper retorna None

    # 3 chamadas paralelas, MESMA chave
    args = ("emp-uuid", "5511999999999", "123@g.us")
    results = await asyncio.gather(
        lead_in_group(sb_mock, *args, lid="", evo_url="x", evo_key="y", evo_inst="z"),
        lead_in_group(sb_mock, *args, lid="", evo_url="x", evo_key="y", evo_inst="z"),
        lead_in_group(sb_mock, *args, lid="", evo_url="x", evo_key="y", evo_inst="z"),
    )

    # Asserts
    assert probe_call_count == 1, f"esperado 1 probe, teve {probe_call_count}"
    assert all(r['in_group'] is True for r in results)
    # 1º caller é probe, 2º+3º são cache (re-check dentro do lock)
    sources = sorted(r['source'] for r in results)
    assert sources == ['cache', 'cache', 'probe']
```

### 11c. Teste: chaves diferentes → 2 probes paralelos

```python
@pytest.mark.asyncio
async def test_different_keys_run_in_parallel(monkeypatch):
    """2 chaves diferentes não bloqueiam — 2 probes paralelos."""
    timings = []

    async def fake_probe(base_url, api_key, instancia, grupo_jid, telefone, lead_lid=""):
        start = asyncio.get_event_loop().time()
        await asyncio.sleep(0.1)
        timings.append((start, asyncio.get_event_loop().time(), telefone))
        return {"ok": True, "in_group": True, "erro": ""}

    monkeypatch.setattr(
        "app.services.grupo_membership.verificar_lead_no_grupo", fake_probe,
    )
    monkeypatch.setattr(
        "app.services.grupo_membership._query_membership_row",
        lambda *a, **k: None,
    )

    sb_mock = AsyncMock()

    # 2 telefones diferentes (chaves diferentes)
    start = asyncio.get_event_loop().time()
    await asyncio.gather(
        lead_in_group(sb_mock, "emp", "5511AAA", "123@g.us", lid="", evo_url="x", evo_key="y", evo_inst="z"),
        lead_in_group(sb_mock, "emp", "5511BBB", "123@g.us", lid="", evo_url="x", evo_key="y", evo_inst="z"),
    )
    elapsed = asyncio.get_event_loop().time() - start

    assert len(timings) == 2
    assert elapsed < 0.15, f"esperado <150ms (paralelo), teve {elapsed*1000:.1f}ms"
```

### 11d. Outros testes recomendados (PLAN.md detalha)
- Decision tree: cache hit retorna sem query
- Decision tree: membership hit retorna sem probe
- Decision tree: instance_key mismatch retorna `source='orphan'`
- Decision tree: row ausente cai pro probe
- Decision tree: erro DB retorna `source='unknown'`
- Migração callsite 251: legacy markers + orphan → `_confirmado_grupo_atual = False`
- Lock reuse: chamadas sequenciais com mesma chave reusam lock object

---

## 12. Runtime State Inventory (não aplicável)

Phase 11 é uma fase de **consumer + refactor de callers**, NÃO uma rename/migration. Nada renomeia nem migra dados existentes.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — `grupo_membership` é tabela já em prod pela Fase 10, sem rename | Nenhuma |
| Live service config | None — sem mudança Evolution / n8n / etc | Nenhuma |
| OS-registered state | None | Nenhuma |
| Secrets/env vars | None | Nenhuma |
| Build artifacts | `BUILD_VERSION` será bumpado para `2026-06-XX-lead-in-group-consumer` (cosmético) | Bump em deploy |

---

## 13. Common Pitfalls

### Pitfall 1: Cache armazena `None` ou `'pending'`
**What goes wrong:** `probe_cache.set(value=None)` armazena `None`, depois `get()` retorna `None` ambíguo (miss vs cached miss).
**Why it happens:** Decision tree retorna `in_group=None` em erro probe ou `'pending'` em stale window. Caller esquece e cacheia.
**How to avoid:** `probe_cache.set` da Fase 10 já rejeita `None` silenciosamente (probe_cache.py:62 — `if value is None: return`). **NÃO cachear `'pending'` ou `None` em Fase 11.**
**Warning signs:** Logs `[MEMB-LOOKUP] source=cache in_group=None` → bug.

### Pitfall 2: Substituir argumentos na ordem errada
**What goes wrong:** `verificar_lead_no_grupo(base_url, api_key, instancia, grupo_jid, telefone, lead_lid)` vs `lead_in_group(sb, empresa_id, telefone, grupo_jid, lid)`. Ordem diferente. PLAN.md substitui mecanicamente, troca `grupo_jid` ↔ `telefone`.
**Why it happens:** Cópia sem inspecionar contrato novo.
**How to avoid:** PLAN.md usa **kwargs explícitos** sempre: `lead_in_group(sb=sb, empresa_id=empresa_id, telefone=telefone, grupo_jid=grupo_jid, lid=lid, evo_url=evo_url, evo_key=evo_key, evo_inst=evo_inst)`.
**Warning signs:** Lookup retorna sempre miss (telefone com formato `120363xxx@g.us`).

### Pitfall 3: PROBE-BYPASS-01 marker bypass omitido
**What goes wrong:** Callsite 311 tem bypass de 5min via marker `GRUPO_LEAD_ENTROU_CRIACAO` (linhas 296-308) que precede o probe. Migração para `lead_in_group()` mata esse bypass.
**Why it happens:** Refactor "limpa" o bypass por considerar coberto pelo grupo_membership.
**How to avoid:** **PRESERVAR LITERALMENTE** o bloco do bypass. `lead_in_group` é chamado SÓ se bypass não disparou. Comentário inline no PLAN.md ressaltando.
**Warning signs:** Casos Ana Carla 08/06 voltam (FSM=ATIVO + probe negativo → bot ativa fallback).

### Pitfall 4: Cache não respeita instance_key
**What goes wrong:** Cache key não inclui `instance_key`. Empresa migra instância. Cache antigo retorna True para grupo de instância anterior.
**Why it happens:** `probe_cache` key tem `(empresa_id, grupo_jid, telefone, lid)` — empresa muda instance_key DENTRO da mesma `empresa_id`.
**How to avoid:** Mitigação dupla:
  1. `lead_in_group()` SEMPRE verifica `instance_key_match` via query SQL ANTES de aceitar cache hit como autoritativo (mas isso ANULA o ganho de cache).
  2. **Recomendação:** quando empresa migra instância (raro — único caso histórico: Rejane bia-rejane → rejane-leal-mentora 08/06), invalidar cache via `probe_cache.clear_all()`. Documentar.
**Warning signs:** Após migração de instância, leads aparecem como `source='cache' in_group=True` para grupos órfãos.

### Pitfall 5: Lock dict cresce sem bound
**What goes wrong:** `_probe_locks` cresce indefinidamente com cada par novo. Em 100 empresas × N grupos × M leads → milhões de entries.
**Why it happens:** Sem TTL, sem cap. Pitfall 10 de PITFALLS.md.
**How to avoid:**
  - v1 (Fase 11): aceitar. Single-worker restarta diariamente. ~150 entries esteady-state.
  - v2 (futuro): cap defensivo via `if len(_probe_locks) > 2048: drop oldest`. Não fazer agora.
**Warning signs:** Endpoint healthcheck (Fase 14) mostra `lock_dict_size > 1000`.

### Pitfall 6: Try/except externo engole exception do probe e retorna `unknown`
**What goes wrong:** Caller atual em `grupo_fallback.py` linhas 251/311 tem try/except envolvendo `verificar_lead_no_grupo`. Migração mantém try/except mas `lead_in_group` JÁ tem try/except interno → exception nunca propaga, mas caller espera flow normal. Logic inversion.
**Why it happens:** Cópia mecânica do try/except antigo.
**How to avoid:** PLAN.md detalha: try/except EXTERNO continua, mas trate `_check_xxx.get('source') == 'unknown'` como o "erro" que o try/except antigo capturava. NÃO assumir exception.
**Warning signs:** Decisões ficam "incertas" mais frequente em logs — porque `unknown` ≠ exception.

### Pitfall 7: Aquec floor regression via PROBE-BYPASS-01 não aplicado a `lead_in_group`
**What goes wrong:** AQUEC-FLOOR-01 (180s) está em `warmup_grupo.py`, NÃO em callsites de Fase 11. Mas se developer "decidir" migrar warmup_grupo.py também (out of scope!), pode quebrar floor.
**Why it happens:** "Migrar tudo que chama verificar_lead_no_grupo" — não é o escopo.
**How to avoid:** PLAN.md lista EXPLICITAMENTE os 7 callsites alvo. Warmup_grupo:781 NÃO está na lista. Fase 12.
**Warning signs:** Caso Karla / Crislaine voltam.

---

## 14. Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 stdlib `asyncio.Lock` | Coalescing | ✓ | 3.13 | — |
| `cachetools.TTLCache` | Cache hit | ✓ | 5.5.0 (Fase 10) | — |
| `supabase-py` | Query membership | ✓ | >=2.18 (Fase 10) | — |
| Tabela `grupo_membership` | SELECT query | ✓ | Migration 004 aplicada 2026-06-09 | — |
| RPC `upsert_grupo_membership` | NÃO chamada por Fase 11 | ✓ | Aplicada | n/a (consumer não escreve) |
| `verificar_lead_no_grupo` | Fallback probe | ✓ | `evolution.py:198` em prod | — |
| `probe_cache` singleton | Cache wrapper | ✓ | `probe_cache.py` em prod | — |
| `get_supabase()` factory | Client em callers | ✓ | `app.db.client` já usado em todos os 7 callsites | — |
| APScheduler | Fase 12, NÃO Fase 11 | ✓ | 3.10.4 | n/a |

**Missing dependencies:** none.

**Skip condition:** Fase 11 é puramente code/config. Nenhuma migration de schema, nenhuma nova dependência, nenhum tool externo. **TODOS os pre-requisitos foram entregues pela Fase 10.**

---

## 15. Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (já em prod — `tests/test_verificar_lead_no_grupo_phase3.py`) |
| Config file | nenhum dedicado — usa default pytest discovery |
| Quick run command | `pytest tests/test_lead_in_group*.py -x -v` (PLAN.md cria) |
| Full suite command | `pytest tests/ -x` (13 testes v2.1 + 5 novos esperados) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MEMB-05 | Cache hit retorna sem query DB | unit | `pytest tests/test_lead_in_group_decision.py::test_cache_hit_returns -x` | ❌ Wave 0 |
| MEMB-05 | Membership hit retorna sem probe | unit | `pytest tests/test_lead_in_group_decision.py::test_membership_hit -x` | ❌ Wave 0 |
| MEMB-05 | Orphan (instance_key mismatch) | unit | `pytest tests/test_lead_in_group_decision.py::test_orphan_instance -x` | ❌ Wave 0 |
| MEMB-05 | Row ausente → probe fallback | unit | `pytest tests/test_lead_in_group_decision.py::test_no_row_falls_to_probe -x` | ❌ Wave 0 |
| MEMB-05 | Erro DB → `unknown` | unit | `pytest tests/test_lead_in_group_decision.py::test_db_error -x` | ❌ Wave 0 |
| PROBE-COALESCE-01 | 3 concorrentes → 1 probe | integration (asyncio.gather) | `pytest tests/test_lead_in_group_coalesce.py::test_coalesce_three -x` | ❌ Wave 0 |
| PROBE-COALESCE-01 | Chaves diferentes em paralelo | integration | `pytest tests/test_lead_in_group_coalesce.py::test_different_keys_parallel -x` | ❌ Wave 0 |
| (migração) | 6 callsites usam `lead_in_group` | grep CI | `grep -c "await lead_in_group" leadflow-backend/app/services/grupo_fallback.py` → expect 7 | ✓ (script) |
| (migração) | Imports não-regressão | grep CI | `grep -c "from app.services.evolution import verificar_lead_no_grupo" grupo_fallback.py` → expect 2 (linhas 475 + 622 intactas) | ✓ (script) |

### Sampling Rate
- **Per task commit:** `pytest tests/test_lead_in_group_decision.py tests/test_lead_in_group_coalesce.py -x` (5-10s)
- **Per wave merge:** `pytest tests/ -x` (full suite ~30s)
- **Phase gate:** full suite green + manual smoke (1 probe + 1 cache hit + 1 polling cycle em staging)

### Wave 0 Gaps
- [ ] `tests/test_lead_in_group_decision.py` — decision tree (5 testes)
- [ ] `tests/test_lead_in_group_coalesce.py` — coalescing (2 testes)
- [ ] `tests/conftest.py` — fixture `reset_state()` autouse para limpar `probe_cache` + `_probe_locks` entre testes (anti-Pattern 2 do ARCHITECTURE.md)
- [ ] Framework install: já tem pytest 8.x + pytest-asyncio 0.23 em prod (commit 6159af5 v2.1)
- [ ] Script CI grep para confirmar 7 substituições mecânicas em `grupo_fallback.py`

---

## 16. Security Domain

Fase 11 NÃO introduz nova superfície de ataque:
- Sem novo endpoint exposto (PLAN.md pode adicionar `/admin/grupo/lead-in-group` opcional — protegido pelo auth `_check_auth` existente em `admin.py`)
- Sem nova ingestão de webhook (Fase 10 já tem)
- Sem novo path de escrita (consumer puro)
- `lead_in_group()` é interna — chamada apenas por `grupo_fallback.py` em código backend

**ASVS check:**
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No (chamadas internas) | n/a |
| V3 Session Management | No | n/a |
| V4 Access Control | Yes — query `grupo_membership` filtra por `empresa_id` | Multi-tenant isolation via `empresa_id` em todo query (mesmo padrão do Fase 10 cache key) |
| V5 Input Validation | Yes — `empresa_id`, `telefone`, `grupo_jid`, `lid` recebidos de callers internos | Callers já validam (mesma validação que `verificar_lead_no_grupo`) |
| V6 Cryptography | No | n/a |

**Multi-tenant isolation:** `empresa_id` é primeiro componente da chave de cache + filtro WHERE primeiro da query SQL. Garantido por construção. Cobertura: PITFALLS.md "What might I have missed?" §multi-tenant cross-talk.

**Não regredir:** Migration 003 (RLS service_role only) já protege `grupo_membership`. Helper `upsert_grupo_membership` da Fase 10 já loga FAIL se RLS bloquear. Consumer só LÊ — RLS service_role permite.

---

## 17. Code Examples (verificados — patterns já em prod)

### Pattern: try/except no helper (Fase 10 estabelecido)
```python
# Source: [VERIFIED: codebase introspection grupo_membership.py:79]
try:
    result = sb.rpc('upsert_grupo_membership', {...}).execute()
    # ...
    return {'ok': True, ...}
except Exception as e:
    print(f"[MEMB-WRITE] EXC empresa={empresa_id[:8]} erro={e}")
    return {'ok': False, 'erro': str(e)}
```
Fase 11 adota mesmo padrão em `lead_in_group()`: helper retorna dict com `source='unknown'` em vez de propagar.

### Pattern: probe_cache.get with empresa_id first
```python
# Source: [VERIFIED: codebase introspection probe_cache.py:40]
def get(empresa_id: str, grupo_jid: str,
        telefone: Optional[str] = None, lid: Optional[str] = None) -> Optional[bool]:
    with _lock:
        result = _cache.get(_make_key(empresa_id, grupo_jid, telefone, lid))
        # ...
```
Fase 11: `lead_in_group()` chama exatamente assim — sem mudança no contrato.

### Pattern: APScheduler add_job idempotente (Fase 12 referência)
```python
# Source: [VERIFIED: codebase introspection grupo_fallback.py:666]
scheduler.add_job(
    _executar_xxx, 'date', run_date=run_at, args=[...],
    id=f"prefix_{empresa_id[:8]}_{telefone}_{grupo_jid[:20]}",
    replace_existing=True, max_instances=1, misfire_grace_time=None,
)
```
Fase 12 (NÃO Fase 11) usa esse padrão para `schedule_probe_retry`. PLAN.md Fase 11 pode adicionar **stub no-op** para `schedule_probe_retry` (vazio nesta fase) para evitar future-rebase pain — mas é opcional.

---

## 18. State of the Art

| Old Approach (em prod hoje) | Fase 11 Approach | Impact |
|--------------|------------------|--------|
| Caller chama `verificar_lead_no_grupo` direto (HTTP Evolution toda vez) | Caller chama `lead_in_group()` → cache → DB → HTTP (em ordem) | 3 jobs paralelos = 1 chamada Evolution (não 3); cache hit O(1) em vez de 500ms HTTP |
| Cada caller faz `_get_lead_lid_for_group` independente | Mantido (caller passa lid pra `lead_in_group`) | Sem mudança — mais simples |
| `grupo_membership` write-only (Fase 10) | `grupo_membership` read+write | Fundação webhook-first em pleno uso |

**Deprecated/outdated em código que NÃO MUDA:**
- Comentário linha 323 em `grupo_fallback.py`: "ESTRATÉGIA: ignora verificar_lead_no_grupo do Evolution" — escrito 01/06 quando Evolution era a única fonte. Pós-Fase 11, a estratégia muda: "consulta `grupo_membership` PRIMEIRO". PLAN.md atualiza comentário.
- Block 1b/1c comentários — referenciam "Bug Aline 13/05" e "FIX 19/05 caso Luciane" — manter comentários históricos. Adicionar nota: "FASE 11 2026-06-09: agora via lead_in_group() consulta grupo_membership primeiro".

---

## 19. Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `grupo_membership` query com `OR (telefone=$1 OR lid=$2)` via supabase-py `.or_()` funciona com filter syntax `f'telefone.eq.{tel},lid.eq.{lid}'` | §6 SQL Query | Médio — supabase-py syntax `.or_()` documentação ambígua; **VERIFICAR no Wave 0** com smoke query (mesmo padrão usado em grupo_fallback.py:240-246 com `.or_(...)` JÁ FUNCIONANDO em prod, então RISCO BAIXO). [ASSUMED] |
| A2 | `agendamento.grupo_jid` + `agendamento.criado_em` é a fonte primária para determinar "grupo criado <6min atrás" (Fase 12) | §3 stale window | Baixo — Fase 12 confirma. Fase 11 não usa. [ASSUMED] |
| A3 | Logs INFO em todo lookup (volume ~72K linhas/dia) não estouram Easypanel docker log limits | §9 Logs | Médio — depende de configuração Docker. **DECISÃO PLAN.md:** começar INFO; se volume problemático, downgrade a DEBUG. [ASSUMED] |
| A4 | Locks dict não-bounded é seguro com restart diário do Easypanel | §5d cleanup | Baixo — confirmado em PITFALLS.md §Pitfall 10 + cap defensivo opcional. [ASSUMED, baixo risco] |
| A5 | `lead_in_group()` em testes pode mockar `verificar_lead_no_grupo` via `monkeypatch.setattr("app.services.grupo_membership.verificar_lead_no_grupo", ...)` (ou seja, lead_in_group importa probe localmente) | §11 testes | Baixo — PLAN.md decide se import top-level ou local. Padrão Fase 10 helper (grupo_membership.py:44 `from app.services import probe_cache` LOCAL dentro de função) sugere import local. Mock funciona ambos os jeitos. [ASSUMED] |
| A6 | `asyncio.Lock` em `app/services/grupo_membership.py` no escopo de módulo é criado uma única vez no import (Python convention) | §5b structure | Baixo — Python lang spec garante. [VERIFIED: Python docs] |
| A7 | Migração mecânica dos 7 callsites mantém ordem de imports do arquivo `grupo_fallback.py` | §7 padrão substituição | Baixo — PLAN.md detalha. [ASSUMED] |

---

## 20. Open Questions

1. **PLAN.md cacheia `(in_group, last_event_at)` tupla ou só bool?**
   - What we know: contrato Fase 10 `probe_cache.set(value: bool)` aceita só bool. Mudar quebra invalidação write-through.
   - What's unclear: Callers precisam de `last_event_at` em cache hits?
   - Recommendation: Manter `None` em cache hits. Callers que precisam de timestamp consultam DB (raro — só Fase 13 LEAVE handler).

2. **`lead_in_group()` recebe `evo_url/evo_key/evo_inst` como kwargs ou faz lookup interno via `get_evolution_creds(empresa_id)`?**
   - What we know: Lookup interno reduz boilerplate em 7 callsites. Mas adiciona latência DB pra cada chamada (mesmo cache hit).
   - What's unclear: Qual é mais ergonômico para callers?
   - Recommendation: kwargs (callers já têm creds carregadas — economia 1 query Postgres por lookup).

3. **`source='orphan'` deveria FORÇAR re-probe ou retornar False sem probe?**
   - What we know: Caso Fernanda → grupo órfão = "como se lead não estivesse no grupo atual". Probe Evolution retornaria False pois não tem acesso ao grupo da instância antiga.
   - What's unclear: Vale a chamada HTTP?
   - Recommendation: **NÃO probe** em orphan — retorna False imediato. Economiza 200ms. Caller já tem info suficiente.

4. **PLAN.md deve adicionar `schedule_retry_on_negative` (stub no-op) na assinatura agora ou esperar Fase 12?**
   - What we know: Adicionar stub agora evita signature break na Fase 12.
   - What's unclear: Adiciona complexidade visível sem benefício imediato.
   - Recommendation: **Adicionar stub** com docstring "ignored in Phase 11; activated in Phase 12". 5 linhas de código.

5. **Há corner case onde cache hit é Wrong porque webhook ADD ainda não invalidou?**
   - What we know: Pitfall 6 de PITFALLS.md — race entre webhook ADD escrevendo + caller lendo cache.
   - What's unclear: Fase 10 `upsert_grupo_membership` invalida cache APÓS RPC success. Tem janela: RPC commitou Postgres MAS cache.invalidate() ainda não rodou → caller lê cache stale True/False.
   - Recommendation: Aceitar como BAIXO risco — janela <1ms. PITFALLS.md confirma RPC + cache invalidation atômicos por padrão.

---

## 21. Sources

### Primary (HIGH confidence — codebase introspection direta)
- `c:/Projetos/Leadflow/.planning/REQUIREMENTS.md` — MEMB-05, PROBE-COALESCE-01 specs
- `c:/Projetos/Leadflow/.planning/ROADMAP.md` lines 124-135 — Phase 11 success criteria
- `c:/Projetos/Leadflow/.planning/research/ARCHITECTURE.md` lines 144-241 — `lead_in_group()` decision tree base
- `c:/Projetos/Leadflow/.planning/research/STACK.md` lines 316-349 — Coalescing pattern proposto
- `c:/Projetos/Leadflow/.planning/research/PITFALLS.md` Pitfalls 2, 4, 6, 10, 11 — riscos críticos
- `c:/Projetos/Leadflow/leadflow-backend/app/services/grupo_membership.py` — helper Fase 10 (143 linhas)
- `c:/Projetos/Leadflow/leadflow-backend/app/services/probe_cache.py` — cache Fase 10 (126 linhas)
- `c:/Projetos/Leadflow/leadflow-backend/app/services/evolution.py:198-290` — `verificar_lead_no_grupo` (intocado)
- `c:/Projetos/Leadflow/leadflow-backend/app/services/grupo_fallback.py` — 7 callsites confirmados via grep nos 6 blocos lógicos
- `c:/Projetos/Leadflow/leadflow-backend/app/scheduler.py` — singleton confirmação
- `c:/Projetos/Leadflow/.planning/phases/10-*/10-02-SUMMARY.md` — schema + helper entregues
- `c:/Projetos/Leadflow/.planning/phases/10-*/10-03-SUMMARY.md` — Path 1 confirmado
- `c:/Projetos/Leadflow/.planning/phases/10-*/10-04-SUMMARY.md` — Paths 2+3 confirmados

### Secondary (MEDIUM confidence — patterns validados externamente)
- `asyncio.Lock` coalescing pattern — Python docs + SuperFastPython tutorial
- Double-checked locking — Wikipedia + cachetools best practices
- supabase-py `.or_()` syntax — uso já em prod em `grupo_fallback.py:240-246` (confirmado funcionando)

### Tertiary (LOW confidence — não verificados via tool nesta fase)
- Volume real de lookups em prod (estimativa ~50/min × 1440 = 72K/dia) — não medido, baseado em uso atual de `verificar_lead_no_grupo`
- Latência P99 esperada de query Postgres com index partial (<5ms) — não medido, baseado em índices definidos

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Fase 10 entregou contratos. Sem novas deps.
- Architecture (decision tree, coalescing): HIGH — codebase introspection + pattern validado
- 6 callsites: HIGH — confirmados via grep com linhas exatas
- Logs design: MEDIUM — assumption de volume (~72K/dia OK em Easypanel) precisa confirmação operacional
- Backward compat: HIGH — wrapper aditivo não toca código legacy

**Research date:** 2026-06-09 18:30 GMT-3
**Valid until:** 2026-07-09 (30 dias — código backend estável, pouca rotatividade arquitetural pós-v2.2)
