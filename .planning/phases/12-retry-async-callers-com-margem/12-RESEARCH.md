# Phase 12: Retry Async + Callers com Margem — Research

**Researched:** 2026-06-09
**Domain:** APScheduler `trigger='date'` one-shot retry jobs, max_age guard, `schedule_retry_on_negative` activation, caller migration in `confirmacao_agendamento.py` and `warmup_grupo.py`
**Confidence:** HIGH (codebase introspection direta — todos os símbolos verificados via grep + leitura dos arquivos)

---

## Summary

A Fase 12 ativa o stub `schedule_retry_on_negative` que a Fase 11 deixou como no-op em `lead_in_group()`. Quando essa flag é `True` e o probe retorna negativo com a tabela vazia, em vez de retornar imediatamente `{in_group: False}`, a função enfileira retries one-shot via APScheduler em 30s / 2min / 5min com um guard de `max_age_seconds=600` absoluto. Isso resolve dois casos reais:

**Rosania (08/06 23:57):** webhook `GROUP_PARTICIPANTS_UPDATE` chegou T+138s depois do aquecimento. Com retry de 30s + 2min + 5min, o segundo ou terceiro retry encontraria a row já na tabela `grupo_membership` e retornaria `source='membership'` sem chamar Evolution. A função `_retry_probe_job` deve consultar `grupo_membership` PRIMEIRO (via `_query_membership_row`) antes de qualquer probe HTTP — se a row já existe, encerra com sucesso silencioso.

**Valquiria (06/06):** aquec #4 falhou, recovery reagendou o job 47h depois. O `max_age_seconds=600` absoluto garante que um retry enfileirado às T=0 seja descartado se executar após T=600s, independente da razão do atraso (restart, fila cheia, job zumbi). O guard é verificado DENTRO do job handler (não no scheduler), usando `enqueued_at` passado como argumento.

A decisão arquitetural central da Fase 12: `schedule_probe_retry()` é uma função nova em `app/services/grupo_membership.py` (mesmo módulo de `lead_in_group()`) que é chamada internamente quando `schedule_retry_on_negative=True`. Os dois callers a migrar são `confirmacao_agendamento.py:291` (notif D-1 — tem margem de horas antes da reunião) e a probe dentro de `warmup_grupo.py` (chamada via `ativar_fallback_se_necessario` — tem margem de minutos por `delay_minutos`). O aquec (`_executar_aquecimento_grupo_job`) é decisão SÍNCRONA — mantém probe síncrono via `ativar_fallback_se_necessario` consultando `grupo_membership` PRIMEIRO (já faz isso via Fase 11).

**Primary recommendation:** Implementar `schedule_probe_retry()` em `grupo_membership.py`, ativar `schedule_retry_on_negative` nos 2 callers com margem, e adicionar `recuperar_probe_retries_pendentes()` no startup seguindo o padrão das recoveries de aquecimento/confirmação já existentes.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

CONTEXT.md não foi gerado para a Fase 12. O `additional_context` do prompt orquestrador funciona como discussão.

### Locked Decisions (do REQUIREMENTS.md + STATE.md + objective do prompt)

- **PROBE-RETRY-01:** `schedule_probe_retry(empresa_id, grupo_jid, telefone, lid, attempts_left=3, max_age_seconds=600)` — job APScheduler one-shot `trigger='date'`. Tentativas em 30s/2min/5min.
- **PROBE-RETRY-02:** Migrar `confirmacao_agendamento.py:291` (notif D-1) e `_executar_timeout_grupo_aguardando` (timeout 30min FALLBACK) para `schedule_retry_on_negative=True`; aquec mantém síncrono.
- **max_age_seconds=600 absoluto:** descarta job se `now - enqueued_at > 600s` (cobre Valquiria).
- **Webhook table-first short-circuit (caso Rosania):** retry handler consulta `grupo_membership` PRIMEIRO; se row existe, encerra com sucesso silencioso sem chamar Evolution.
- **APScheduler in-memory com recovery startup:** jobs perdidos em restart re-enfileirados via recovery baseado em estado DB (padrão dos recoveries existentes).
- **`asyncio.create_task` naked PROIBIDO no retry path:** todos os agendamentos passam por `scheduler.add_job`.
- **Job id format:** `probe_retry:{grupo_jid}:{telefone}:{attempt}` + `replace_existing=True`.

### Claude's Discretion

- Nome interno da função de retry handler (`_probe_retry_job` sugerido)
- Como armazenar `enqueued_at` (sugerido: parâmetro direto no job args — não depende de estado externo)
- Recovery startup: query pode ser em `conversas` (marker `PROBE_RETRY_PENDING`) ou em `grupo_membership` (rows recentes sem `saiu_em`); escolha baseada na complexidade da query
- Exatamente quais callsites dentro de `warmup_grupo.py` recebem `schedule_retry_on_negative=True` (via `ativar_fallback_se_necessario` ou diretamente em `lead_in_group`)

### Deferred Ideas (OUT OF SCOPE)

- LEAVE handler / `saiu_em` consumer (Fase 13)
- FSM audit log (Fase 13)
- Testes regressão (Fase 14)
- Cache `probe_cache` TTL ajuste
- Migração Postgres jobstore (decisão STATE.md: in-memory + reschedule startup)
- Endpoint `/health/grupo-membership` (Fase 14)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **PROBE-RETRY-01** | `schedule_probe_retry(empresa_id, grupo_jid, telefone, lid, attempts_left=3, max_age_seconds=600)` — job APScheduler one-shot `trigger='date'`. Tentativas 30s/2min/5min. `max_age_seconds` absoluto descarta job velho. | §1 APScheduler wiring; §2 retry handler design; §3 max_age guard; §4 Rosania short-circuit; §5 Valquiria guard |
| **PROBE-RETRY-02** | Migrar callers com margem temporal (notif pre-reuniao, timeout 30min FALLBACK) para `schedule_retry_on_negative=True`; aquec mantém síncrono. | §6 caller migration map; §7 aquec não migra; §8 confirmacao_agendamento:291; §9 timeout_grupo_aguardando |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

O `CLAUDE.md` do backend é focado no fluxo Q1/Q2 de `agente.py`. Mas as regras gerais valem para a Fase 12:

- NÃO refatorar fluxos sem necessidade — Fase 12 é aditiva: nova função `schedule_probe_retry()` + ativação do stub
- NÃO mexer em `google_calendar.py`
- Preservar comportamento atual — probe síncrono permanece como fallback quando `schedule_retry_on_negative=False`
- USAR o que já existe: `scheduler` singleton (`app/scheduler.py`), padrão `trigger='date'` + `replace_existing=True` já em uso por `_agendar_timeout_grupo_aguardando`, padrão recovery startup já em `recuperar_aquecimentos_pendentes`

---

## Standard Stack

### Core (TODOS já em prod — Fase 12 não adiciona dependências)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `apscheduler.schedulers.asyncio.AsyncIOScheduler` | 3.10.4 | One-shot retry jobs `trigger='date'` | Singleton já em `app/scheduler.py:5`; todos os callers importam `from app.scheduler import scheduler` |
| `asyncio` | stdlib Python 3.13 | Mesmo event loop FastAPI + APScheduler | Single-worker Easypanel — zero overhead; coalescing locks Fase 11 já usam |
| `datetime.utcnow()` | stdlib | `enqueued_at` + `run_date` cálculo | Padrão uniforme em todo o projeto (UTC-naive) |
| `supabase-py` | >=2.18 | `_query_membership_row()` no retry handler | Já usado por `lead_in_group()` |
| `cachetools.TTLCache` | 5.5.0 | Cache invalidação pós-retry (via `probe_cache`) | Já em prod via Fase 10 |

### Já entregue pelas Fases 10-11 (consumidos pela Fase 12)

| Symbol | Módulo | Como Fase 12 usa |
|--------|--------|-----------------|
| `scheduler` | `app/scheduler.py` | `scheduler.add_job(trigger='date', ...)` em `schedule_probe_retry()` |
| `lead_in_group()` | `app/services/grupo_membership.py` | Chama `schedule_probe_retry()` quando `schedule_retry_on_negative=True` + probe negativo |
| `_query_membership_row()` | `app/services/grupo_membership.py` | `_probe_retry_job` consulta tabela PRIMEIRO (caso Rosania) |
| `probe_cache.set()` | `app/services/probe_cache.py` | Cacheia resultado se `in_group=True` no retry |
| `verificar_lead_no_grupo()` | `app/services/evolution.py` | Probe Evolution no retry handler (fallback) |
| `upsert_grupo_membership()` | `app/services/grupo_membership.py` | Opcional: backfill se probe retorna True e tabela estava vazia |

**Instalação:** nenhuma nova dependência.

---

## Architecture Patterns

### Recommended Module Structure (após Fase 12)

```
app/services/
├── grupo_membership.py    # +schedule_probe_retry(), +_probe_retry_job(), +recuperar_probe_retries_pendentes()
├── probe_cache.py         # SEM mudanças
├── evolution.py           # SEM mudanças
├── grupo_fallback.py      # SEM mudanças (Fase 11 já migrou os 7 callsites)
└── grupo_state.py         # SEM mudanças (Fase 13)

app/routers/
├── confirmacao_agendamento.py  # MODIFICADO: probe em linha 291 → lead_in_group(..., schedule_retry_on_negative=True)
├── warmup_grupo.py             # MODIFICADO: probe em notif job → lead_in_group(..., schedule_retry_on_negative=True)
├── main.py                     # MODIFICADO: adiciona recuperar_probe_retries_pendentes() no lifespan
└── (todos os demais)           # SEM mudanças
```

### Pattern 1: `schedule_probe_retry()` — one-shot job com id idempotente

**What:** Enfileira retry via `scheduler.add_job(trigger='date', ...)`. O `job_id` usa attempt number, garantindo idempotência por `replace_existing=True`. Passa `enqueued_at` como arg — o handler verifica `now - enqueued_at < max_age_seconds` antes de executar.

**When to use:** Chamado de dentro de `lead_in_group()` quando `schedule_retry_on_negative=True` e probe retornou False/None com row ausente.

```python
# app/services/grupo_membership.py — novo helper
# [VERIFIED: codebase — padrão idêntico ao _agendar_timeout_grupo_aguardando:857-871]
from datetime import datetime, timedelta

_RETRY_DELAYS_SEC = [30, 120, 300]  # 30s, 2min, 5min

def schedule_probe_retry(
    empresa_id: str,
    grupo_jid: str,
    telefone: str,
    lid: str,
    attempts_left: int = 3,
    max_age_seconds: int = 600,
    evo_url: str = "",
    evo_key: str = "",
    evo_inst: str = "",
    agendamento_id: str = "",
) -> None:
    """Enfileira probe retry one-shot via APScheduler.

    Attempt index = 3 - attempts_left (0-based: 0→30s, 1→2min, 2→5min).
    Job id: probe_retry:{grupo_jid}:{telefone}:{attempt} — replace_existing=True
    para idempotência (re-enfileirar não duplica).

    enqueued_at passado como arg — handler verifica age dentro do job
    (não fora; APScheduler in-memory não tem misfire_grace_time neste contexto).
    """
    from app.scheduler import scheduler

    attempt = 3 - attempts_left  # 0, 1, 2
    if attempt >= len(_RETRY_DELAYS_SEC):
        print(f"[PROBE-RETRY] esgotado empresa={empresa_id[:8]} grupo={grupo_jid[:24]} tel={telefone}")
        return

    delay = _RETRY_DELAYS_SEC[attempt]
    enqueued_at = datetime.utcnow()
    run_date = enqueued_at + timedelta(seconds=delay)
    job_id = f"probe_retry:{grupo_jid}:{telefone}:{attempt}"

    try:
        scheduler.add_job(
            _probe_retry_job,
            "date",
            run_date=run_date,
            kwargs={
                "empresa_id": empresa_id,
                "grupo_jid": grupo_jid,
                "telefone": telefone,
                "lid": lid,
                "attempts_left": attempts_left - 1,
                "max_age_seconds": max_age_seconds,
                "enqueued_at": enqueued_at,
                "evo_url": evo_url,
                "evo_key": evo_key,
                "evo_inst": evo_inst,
                "agendamento_id": agendamento_id,
            },
            id=job_id,
            replace_existing=True,
            timezone="UTC",
            misfire_grace_time=None,
        )
        print(f"[PROBE-RETRY] enfileirado attempt={attempt} delay={delay}s "
              f"job_id={job_id} empresa={empresa_id[:8]}")
    except Exception as e:
        print(f"[PROBE-RETRY] erro agendar job_id={job_id}: {e}")
```

### Pattern 2: `_probe_retry_job()` — handler com max_age guard + table-first short-circuit

**What:** Handler do job. Primeiro verifica `max_age_seconds` (Valquiria). Depois consulta `grupo_membership` PRIMEIRO via `_query_membership_row` (Rosania — short-circuit sem Evolution). Só então faz probe HTTP Evolution se tabela ainda vazia.

```python
# app/services/grupo_membership.py — novo handler
# [VERIFIED: codebase — estrutura idêntica a _retry_send_text_job em evolution_router.py:423]
async def _probe_retry_job(
    empresa_id: str,
    grupo_jid: str,
    telefone: str,
    lid: str,
    attempts_left: int,
    max_age_seconds: int,
    enqueued_at: datetime,
    evo_url: str,
    evo_key: str,
    evo_inst: str,
    agendamento_id: str = "",
) -> None:
    """Job APScheduler: verifica se lead entrou no grupo após probe negativo inicial.

    Ordem de verificação:
    1. max_age guard — descarta se janela passou (Valquiria)
    2. grupo_membership table — short-circuit se row já existe (Rosania)
    3. probe Evolution — fallback se tabela ainda vazia
    4. Se positivo: invalida cache + opcionalmente upsert backfill
    5. Se negativo e attempts_left > 0: enfileira próxima tentativa
    """
    from app.db.client import get_supabase
    from app.services import probe_cache

    # ─── GUARD 1: max_age absoluto (caso Valquiria) ──────────────────────────
    age_sec = (datetime.utcnow() - enqueued_at).total_seconds()
    if age_sec > max_age_seconds:
        print(f"[PROBE-RETRY] [JOB_EXPIRED] age={age_sec:.0f}s > max_age={max_age_seconds}s "
              f"empresa={empresa_id[:8]} grupo={grupo_jid[:24]} tel={telefone} — descartado")
        return

    sb = get_supabase()

    # ─── SHORT-CIRCUIT: consulta grupo_membership PRIMEIRO (caso Rosania) ────
    try:
        row = _query_membership_row(sb, empresa_id, grupo_jid, telefone, lid)
    except Exception as _e_row:
        print(f"[PROBE-RETRY] erro query membership: {_e_row} — prossegue com probe")
        row = None

    if row is not None:
        # Row existe — lead entrou entre T=0 e agora. Sucesso silencioso.
        probe_cache.set(empresa_id, grupo_jid, telefone, lid, True)
        print(f"[PROBE-RETRY] [TABLE_HIT] row encontrado empresa={empresa_id[:8]} "
              f"grupo={grupo_jid[:24]} tel={telefone} — probe cancelado")
        return

    # ─── Probe Evolution (tabela ainda vazia) ────────────────────────────────
    if not all([evo_url, evo_key, evo_inst]):
        print(f"[PROBE-RETRY] sem creds Evolution — encerrando empresa={empresa_id[:8]}")
        return

    try:
        from app.services.evolution import verificar_lead_no_grupo
        probe_result = await verificar_lead_no_grupo(
            evo_url, evo_key, evo_inst, grupo_jid, telefone or "", lead_lid=lid,
        )
        in_group = probe_result.get("in_group")
    except Exception as _e_probe:
        print(f"[PROBE-RETRY] probe exception: {_e_probe} empresa={empresa_id[:8]}")
        in_group = None

    if in_group is True:
        probe_cache.set(empresa_id, grupo_jid, telefone, lid, True)
        print(f"[PROBE-RETRY] [PROBE_HIT] probe=True empresa={empresa_id[:8]} "
              f"grupo={grupo_jid[:24]} tel={telefone}")
        # Backfill opcional: se tabela estava vazia mas probe confirmou,
        # inserir row via upsert_grupo_membership(..., fonte='probe_backfill')
        # para que próximos lookups usem tabela. PLAN.md decide se incluir aqui.
        return

    # ─── Ainda negativo: enfileira próxima tentativa ─────────────────────────
    if attempts_left > 0:
        schedule_probe_retry(
            empresa_id, grupo_jid, telefone, lid,
            attempts_left=attempts_left,
            max_age_seconds=max_age_seconds,
            evo_url=evo_url, evo_key=evo_key, evo_inst=evo_inst,
            agendamento_id=agendamento_id,
        )
    else:
        print(f"[PROBE-RETRY] [MAX_ATTEMPTS] empresa={empresa_id[:8]} "
              f"grupo={grupo_jid[:24]} tel={telefone} — probe esgotado sem confirmação")
```

### Pattern 3: Ativação do stub em `lead_in_group()`

**What:** O stub `schedule_retry_on_negative: bool = False` já existe na assinatura de `lead_in_group()` (Fase 11 — `grupo_membership.py:160`). Fase 12 ativa: quando `schedule_retry_on_negative=True` e probe retorna `in_group=False` (não None — erro não retries), chama `schedule_probe_retry()`.

**Hook point:** final do STEP 5 (probe com coalescing), dentro do `async with lock:`, após `probe_cache.set()` e antes do `return _emit_log(...)`:

```python
# Trecho a ADICIONAR no final do async with lock: em lead_in_group()
# [VERIFIED: grupo_membership.py:300-332 — ponto de inserção identificado]
# APÓS: probe_cache.set(...) E ANTES do return _emit_log(...)

if schedule_retry_on_negative and probe_in_group is False:
    # probe explicitamente False (não None/erro) → enfileira retry
    schedule_probe_retry(
        empresa_id, grupo_jid, telefone or '', lid,
        attempts_left=3,
        max_age_seconds=600,
        evo_url=evo_url, evo_key=evo_key, evo_inst=evo_inst,
    )
```

**Nota:** `probe_in_group is None` (erro Evolution) NÃO enfileira retry — probe falhou por razão técnica, não por "ainda não propagou". Enfileirar retry em erro pode criar loop. Só `False` explícito retries.

### Pattern 4: Recovery startup — `recuperar_probe_retries_pendentes()`

**What:** Em restart, jobs in-memory são perdidos. Recovery re-enfileira retries pendentes consultando `grupo_membership` rows recentes sem correspondência de `saiu_em`. Padrão idêntico ao `recuperar_aquecimentos_pendentes()` (warmup_grupo.py:161).

**Estratégia:** Query `grupo_membership` rows com `entrou_em > NOW()-600s` E sem `saiu_em` é insuficiente — não sabe se job estava pendente. A estratégia mais simples: usar um marker `PROBE_RETRY_PENDING:{grupo_jid}:{telefone}:{attempt}` em `conversas` que é inserido ao enfileirar e deletado ao completar (positivo ou esgotado). Recovery lê markers ativos.

**Alternativa (menor custo de implementação):** não persistir marker; recovery apenas re-enfileira leads com `agendamentos.status='agendado'` E `grupo_membership` sem row recente E agendamento nas próximas 6h. Esta abordagem é menos precisa mas evita nova tabela/marker. **PLAN.md decide.**

**Recomendação:** usar marker em `conversas` (padrão estabelecido). Marker inserido em `schedule_probe_retry()` com `attempt=0`, deletado em `_probe_retry_job` quando `in_group=True` ou `attempts_left=0`.

```python
# Recovery no startup — adicionar em main.py lifespan (padrão commit ae2b141)
async def _recov_probe_retries():
    try:
        from app.services.grupo_membership import recuperar_probe_retries_pendentes
        await recuperar_probe_retries_pendentes()
        print("[SCHEDULER] Recovery de probe retries concluído (background)")
    except Exception as _e:
        print(f"[SCHEDULER] erro recovery probe retries: {_e}")

_asyncio_recov.create_task(_recov_probe_retries())
```

**NOTA CRÍTICA:** O `asyncio.create_task` em `main.py` (linhas 81-84) é o padrão correto para o recovery startup — está numa coroutine `async def lifespan()` com event loop ativo. DIFERENTE do retry path onde `create_task` é proibido (chamado de código síncrono fora de event loop ou de job handlers onde o task seria órfão). O `asyncio.create_task` em `confirmacao_agendamento.py:926` (recovery de timeout) também está dentro do lifespan — é aceitável. O BAN é somente no caminho `probe retry scheduling` fora do event loop.

### Anti-Patterns to Avoid

- **`asyncio.create_task` em `schedule_probe_retry()`:** essa função é chamada de dentro do `async with lock:` em `lead_in_group()`. `create_task` aqui criaria um task que não está associado a nenhum lifetime — se o lock liberar e o caller retornar, o task fica órfão. `scheduler.add_job` é a forma correta: APScheduler gerencia o ciclo de vida.
- **Retry em `probe_in_group is None`:** probe None = erro HTTP/timeout. Não é "ainda não propagou" — é falha de infraestrutura. Enfileirar retry em erro pode inflar queue e mascarar problema real. Só retry em `False` explícito.
- **`replace_existing=False`:** sem `replace_existing=True`, dois eventos para o mesmo lead podem criar 2 jobs concorrentes com o mesmo `job_id` → APScheduler lança `ConflictingIdError`. `replace_existing=True` garante que o mais recente vence.
- **Job id sem attempt number:** `probe_retry:{jid}:{tel}` sem attempt = jobs de tentativas diferentes conflitariam. O attempt number no id garante que attempt=0, 1, 2 são jobs distintos que podem coexistir na fila.
- **`max_age_seconds` calculado no scheduler:** APScheduler não tem como comparar `datetime.utcnow()` com `enqueued_at` na hora de disparar. O guard DEVE estar dentro do handler (`_probe_retry_job`), não como parâmetro do `add_job`.
- **Enfileirar retry quando `source='orphan'`:** grupo órfão de instância antiga não é resolvido aguardando — requer criar novo grupo. Retry nesse caso seria inútil e enganoso. Fase 12 só enfileira quando `source='probe'` + `in_group=False`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| One-shot delayed execution | `asyncio.sleep` + task | `scheduler.add_job(trigger='date')` | Sleep em task é órfão em restart; APScheduler tem misfire_grace_time + id idempotente |
| Exponential backoff retry | Timer dict + custom loop | `schedule_probe_retry()` com `_RETRY_DELAYS_SEC` | Duplicata do padrão já em `evolution_router.py:450` — mesmo design, delays diferentes |
| Age-window guard | TTL scheduler param | `enqueued_at` arg + guard no handler | APScheduler não suporta "discard if age > X" nativamente; guard explícito no handler é a única forma correta |
| Job dedup | UUID-based ids | `job_id = f"probe_retry:{grupo_jid}:{telefone}:{attempt}"` + `replace_existing=True` | UUID-based (como `evo_retry_{uuid.hex[:8]}`) não permite dedup — cada chamada cria job novo. Id determinístico + replace_existing = idempotente |
| Persistent jobstore | SQLAlchemy jobstore APScheduler | In-memory + recovery startup | Postgres jobstore adiciona dependência + complexidade de migration. Single-worker; recovery via marker pattern já estabelecido |

**Key insight:** O projeto já tem dois padrões de retry async em APScheduler: `evolution_router.py` (backoff 60→960s, UUID id, 5 tentativas) e `_agendar_timeout_grupo_aguardando` (one-shot, id determinístico, replace_existing). A Fase 12 segue o segundo padrão (one-shot determinístico), NÃO o primeiro.

---

## 1. APScheduler Wiring (Infraestrutura Existente)

### 1a. Singleton

```python
# app/scheduler.py:2-5 — [VERIFIED: leitura direta]
from apscheduler.schedulers.asyncio import AsyncIOScheduler
scheduler = AsyncIOScheduler(
    timezone="America/Sao_Paulo",
    job_defaults={"misfire_grace_time": None}
)
```

**Classe:** `AsyncIOScheduler` (não `BackgroundScheduler`). Roda no mesmo event loop do FastAPI — coroutines agendadas como jobs funcionam nativamente.

**misfire_grace_time=None:** jobs disparados com atraso (e.g., após restart) SEMPRE executam, sem descartar por grace period. Isso torna o `max_age_seconds` guard no handler ainda mais crítico — sem ele, jobs antigos seriam executados indefinidamente.

**Jobstore:** in-memory (default APScheduler — sem configuração de `jobstores`). Confirmado: `scheduler.py:5` não passa `jobstores=`. [VERIFIED: leitura direta scheduler.py]

**Startup:** `scheduler.start()` em `main.py:41` dentro do `lifespan` context manager.

### 1b. Jobs registrados (contexto)

| Job ID | Trigger | Localização |
|--------|---------|-------------|
| `noshow_check` | interval 30min | main.py:20 |
| `sync_messages` | interval 2min | main.py:21 |
| `instance_health` | interval 2min | main.py:22 |
| `grupo_polling` | interval 30min | main.py:29 |
| `health_check_diario` | cron hour=6 | main.py:33 |
| `evolution_keys_sync_diario` | cron hour=7 | main.py:34 |
| `instance_state_guard` | interval 5min | main.py:37 |
| `cleanup_expired_locks` | interval 30s | scheduler.py:18 |
| `cleanup_markers_transient` | cron hour=3 | scheduler.py:34 |
| `timeout_grupo_aguard_{ag_id}` | date (one-shot) | grupo_fallback.py:860 |
| `conf_timeout_{ag_id}` | date (one-shot) | confirmacao_agendamento.py:326, 932 |
| `evo_retry_{uuid}` | date (one-shot) | evolution_router.py:454, 486 |

**Fase 12 adiciona:** `probe_retry:{grupo_jid}:{telefone}:{attempt}` — date one-shot, até 3 por lead+grupo.

### 1c. Padrão de add_job determinístico (modelo para Fase 12)

```python
# grupo_fallback.py:860-869 — [VERIFIED: leitura direta]
scheduler.add_job(
    _executar_timeout_grupo_aguardando,
    "date",
    run_date=run_at,
    args=[empresa_id, telefone, agendamento_id, grupo_jid],
    id=job_id,
    replace_existing=True,
    timezone="UTC",
)
```

**Diferença Fase 12:** usa `kwargs={}` em vez de `args=[]` — `_probe_retry_job` tem muitos parâmetros, kwargs evita erros de ordem.

### 1d. Padrão de retry exponencial já existente (reference, NÃO copiar)

```python
# evolution_router.py:450-464 — [VERIFIED: leitura direta]
delay = _RETRY_BACKOFF_BASE_SEC * (2 ** (tentativa - 1))  # 60, 120, 240, 480, 960
run_at = datetime.utcnow() + timedelta(seconds=delay)
scheduler.add_job(
    _retry_send_text_job,
    "date",
    run_date=run_at,
    args=[empresa_id, numero, texto, tentativa + 1],
    id=f"evo_retry_{uuid.uuid4().hex[:8]}",  # ← UUID, NÃO determinístico
    misfire_grace_time=None,
)
```

**Diferença chave:** `evo_retry` usa UUID no id (sem dedup intencional — cada tentativa é novo job). Fase 12 usa id determinístico (`probe_retry:{jid}:{tel}:{attempt}`) + `replace_existing=True` para idempotência.

---

## 2. O Stub `schedule_retry_on_negative` (Ponto de Ativação)

### 2a. Assinatura atual (Fase 11)

```python
# leadflow-backend/app/services/grupo_membership.py:149-161 — [VERIFIED: leitura direta]
async def lead_in_group(
    sb,
    empresa_id: str,
    telefone,
    grupo_jid: str,
    lid: str = "",
    *,
    evo_url: str = "",
    evo_key: str = "",
    evo_inst: str = "",
    allow_probe_fallback: bool = True,
    schedule_retry_on_negative: bool = False,  # Stub Fase 12 — ignorado aqui
) -> dict:
```

**Comentário no código:** `# Stub Fase 12 (PROBE-RETRY-01). Ignorado aqui.` — [VERIFIED: grupo_membership.py:175]

### 2b. Ponto de inserção da ativação

O probe path está em `grupo_membership.py:297-332` (STEP 5). A ativação do retry deve ocorrer DEPOIS de:
1. `probe_in_group = probe_result.get('in_group')` (linha 316)
2. `if probe_in_group is not None: probe_cache.set(...)` (linhas 324-325)

E ANTES de:
3. `return _emit_log({...})` (linha 327)

**Condição de ativação:**
```python
if schedule_retry_on_negative and probe_in_group is False:
    schedule_probe_retry(
        empresa_id, grupo_jid, telefone or '', lid,
        attempts_left=3, max_age_seconds=600,
        evo_url=evo_url, evo_key=evo_key, evo_inst=evo_inst,
    )
```

**Por que `is False` e não `not probe_in_group`:** `None` (erro probe) deve ser distinto de `False` (probe executou e confirmou ausência). `not None` também seria truthy, enfileirando retry em erros HTTP.

---

## 3. Max Age Guard (Caso Valquiria)

### 3a. O problema

**Caso Valquiria (06/06):** aquec #4 do grupo falhou. Recovery reagendava #4 em cada restart. Backend reiniciou 5x em 08-09/06. Na última reinicialização, recovery reagendou o job já com 47h de atraso — job disparou, enviou mensagem de aquecimento completamente fora de contexto. Esse caso foi mitigado pela `recuperar_aquecimentos_pendentes()` com guard de 6h (commit 0d55888).

**Para Fase 12:** um probe retry enfileirado às T=0 deve ser irrelevante se executar às T=47h. A janela de `max_age_seconds=600` (10 minutos) cobre todos os cenários válidos: Evolution propaga membros em 60-180s (pico); 5min é a última tentativa; total < 600s.

### 3b. Implementação no handler

```python
# PRIMEIRO CHECK no _probe_retry_job — [ASSUMED: design proposto, não código existente]
age_sec = (datetime.utcnow() - enqueued_at).total_seconds()
if age_sec > max_age_seconds:
    print(f"[PROBE-RETRY] [JOB_EXPIRED] age={age_sec:.0f}s > max_age={max_age_seconds}s "
          f"empresa={empresa_id[:8]} grupo={grupo_jid[:24]} tel={telefone} — descartado")
    return
```

**`enqueued_at` como arg:** passado explicitamente ao criar o job. Não depende de estado externo (DB, marker, clock do scheduler). Simples e resiliente a restart.

**Se job foi re-enfileirado no startup recovery:** o `enqueued_at` original é recuperado do marker (se usando strategy marker). Se usando re-schedule direto sem marker, `enqueued_at` seria `datetime.utcnow()` — job nunca expiraria no mesmo restart. **PLAN.md deve decidir:** recomendação é passar `enqueued_at` original do marker se disponível, `datetime.utcnow()` se recovery sem marker.

---

## 4. Table-First Short-Circuit (Caso Rosania)

### 4a. O problema

**Caso Rosania (08/06 23:57):** webhook `GROUP_PARTICIPANTS_UPDATE` chegou T+138s. O probe às T+60s retornou False → aquec caiu pro DM. Com retry async, o segundo retry (T+120s) deveria encontrar a row já em `grupo_membership` (webhook chegou T+138s... mas retry T+120s ainda está antes). O TERCEIRO retry (T+300s) encontraria a row com certeza.

**Ponto crítico:** o handler `_probe_retry_job` deve consultar `grupo_membership` PRIMEIRO, antes de chamar Evolution. Se a row existe, encerra com sucesso silencioso — sem chamar probe HTTP (economiza request, sem ruído em logs Evolution).

### 4b. Sequência esperada com Fase 12 ativa

```
T=0s    Probe inicial: tabela vazia → probe Evolution → False
        → schedule_probe_retry(attempts_left=3) → job attempt=0 em T+30s

T+30s   _probe_retry_job attempt=0:
        → age_sec=30 < 600 ✓
        → _query_membership_row → None (webhook ainda não chegou)
        → probe Evolution → False
        → attempts_left=2 → schedule_probe_retry → job attempt=1 em T+120s

T+60s   (Webhook GROUP_PARTICIPANTS_UPDATE chega) → upsert_grupo_membership → row inserida

T+120s  _probe_retry_job attempt=1:
        → age_sec=120 < 600 ✓
        → _query_membership_row → ROW ENCONTRADA (source='membership') ← Rosania
        → probe_cache.set(True) → sucesso silencioso, sem Evolution call
        → return (sem enfileirar attempt=2)
```

### 4c. Se webhook NÃO chegar (Evolution atrasado sem webhook)

```
T=300s  _probe_retry_job attempt=2:
        → age_sec=300 < 600 ✓
        → _query_membership_row → None
        → probe Evolution → True (Evolution finalmente atualizou) ← fallback
        → probe_cache.set(True) → retorna
        OU
        → probe Evolution → False
        → attempts_left=0 → [MAX_ATTEMPTS] log → desiste
```

---

## 5. Os 2 Callers a Migrar (PROBE-RETRY-02)

### 5a. Caller 1: `confirmacao_agendamento.py:291` — notif D-1

**Contexto atual (leitura direta linha 288-297):**
```python
# confirmacao_agendamento.py:288-297 — [VERIFIED: leitura direta]
from app.services.evolution import verificar_lead_no_grupo
from app.services.grupo_fallback import _get_lead_lid_for_group
_lid_cf = _get_lead_lid_for_group(sb, empresa_id, telefone, grupo_jid)
_probe_cf = await verificar_lead_no_grupo(
    evo_url, evo_key, evo_inst, grupo_jid, telefone, lead_lid=_lid_cf,
)
_in_group_real_cf = (_probe_cf.get("in_group") is True)
```

**Por que tem margem:** D-1 confirmação é enviada no dia anterior à reunião. Probe negativo às 10:00 com retry até 10:10 (600s) é irrelevante para reunião às 14:00. Margem de horas.

**Migração:**
```python
# Substitui as 6 linhas acima
from app.services.grupo_membership import lead_in_group
_lid_cf = _get_lead_lid_for_group(sb, empresa_id, telefone, grupo_jid)
_result_cf = await lead_in_group(
    sb, empresa_id, telefone, grupo_jid,
    lid=_lid_cf,
    evo_url=evo_url, evo_key=evo_key, evo_inst=evo_inst,
    schedule_retry_on_negative=True,  # ← ATIVAÇÃO Fase 12
)
_in_group_real_cf = (_result_cf.get("in_group") is True)
```

**Impacto no resto da função:** `_in_group_real_cf` continua sendo um bool. Linhas 299-308 (decisão destino grupo vs DM) não mudam. O retry enfileirado pelo `lead_in_group()` não bloqueia o caller — a confirmação D-1 segue sua lógica atual (probe False = envia pro DM). O retry é "best-effort": se Evolution propagar depois, próximo lookup usará cache/tabela.

**ATENÇÃO:** A confirmação D-1 tem comportamento idempotente via `confirmacao_status`. Se o retry confirma `in_group=True` DEPOIS de a confirmação já ter sido enviada pro DM, não há efeito — o retry só atualiza cache/tabela, não re-envia a confirmação. Isso é correto.

### 5b. Caller 2: `_executar_timeout_grupo_aguardando` em `grupo_fallback.py`

**IMPORTANTE — Correção da especificação do objetivo:**

O objetivo do prompt menciona "_executar_timeout_grupo_aguardando" como o "timeout 30min FALLBACK" a migrar. Mas após leitura direta, essa função (grupo_fallback.py:874-900) NÃO faz probe Evolution — ela apenas transiciona o FSM de `AGUARDANDO → FALLBACK_1_1` quando o timer de 30min expira. Não há `verificar_lead_no_grupo` nem `lead_in_group` nela.

**Onde realmente está o probe com margem temporal em `warmup_grupo.py`:**

O probe que tem margem temporal é o da notificação pré-reunião (`_executar_notificacao_grupo_job`, warmup_grupo.py:796-809), que chama `ativar_fallback_se_necessario()` para decidir se envia no grupo ou DM. Esse path indiretamente usa `lead_in_group()` via `grupo_fallback.py` (Fase 11 já migrou os callsites de `ativar_fallback_se_necessario`).

**Interpretação correta do objetivo:**

"Timeout 30min FALLBACK" provavelmente se refere ao fato de que quando o lead está em `AGUARDANDO` por 30min e o probe diz False, isso dispara o fallback. O probe que esse timeout DISPARA é feito na próxima execução do polling ou do próximo job de aquec/notif — não no `_executar_timeout_grupo_aguardando` em si.

**Para a Fase 12, o que faz sentido migrar:**

1. `confirmacao_agendamento.py:291` — confirmado (tem probe direto com margem D-1)
2. Probe em `_executar_notificacao_grupo_job` (`warmup_grupo.py`) — tem margem de horas/minutos antes da reunião

**Probe em warmup_grupo.py (notif):** atualmente usa `ativar_fallback_se_necessario()` que internamente chama `lead_in_group()` (Fase 11). Para ativar `schedule_retry_on_negative=True` aqui, seria necessário expor o parâmetro para `ativar_fallback_se_necessario()` ou fazer a chamada direta a `lead_in_group()` na notificação. PLAN.md decide a abordagem menos invasiva.

### 5c. O que NÃO migrar (mantém síncrono)

| Caller | Arquivo | Por que NÃO migra |
|--------|---------|-------------------|
| `_executar_aquecimento_grupo_job` | warmup_grupo.py | Decisão SÍNCRONA ("AGORA") — se lead não está no grupo, manda pro DM imediatamente. Retry async criaria inconsistência: aquec já enviou pro DM, retry depois atualiza cache mas não re-envia pro grupo |
| `ativar_fallback_se_necessario` callsites (7 em grupo_fallback.py) | grupo_fallback.py | Já migrados Fase 11 com `schedule_retry_on_negative=False` explícito. São decisões síncronas (convidar, alertar, polling) |
| `admin.py:769, 981` | admin.py | Endpoints diagnóstico — operador quer resultado IMEDIATO |
| `leads.py:123` | leads.py | Validação de reuso "vivo agora" — não tem margem |
| `polling_grupos_aguardando` | grupo_fallback.py:1173, 1256 | O polling EM SI é o retry mechanism — enfileirar retry dentro do polling criaria loops |

---

## 6. Idempotência e Interação com Coalescing (Fase 11)

### 6a. Job id format

```
probe_retry:{grupo_jid}:{telefone}:{attempt}
```

- `attempt` é o índice 0-based (0→30s, 1→2min, 2→5min)
- `replace_existing=True` — se o mesmo lead+grupo+attempt é enfileirado duas vezes, o segundo sobrescreve o primeiro (reset do timer)
- Chaves diferentes (empresa diferente para o mesmo grupo_jid, improvável mas possível): `grupo_jid` inclui o timestamp do grupo no formato `120363xxx@g.us` — suficientemente único

**Potencial colisão:** dois empresas com mesmo `grupo_jid` e mesmo `telefone`. Na prática impossível — `grupo_jid` é específico da instância WhatsApp da empresa. Mas se necessário: adicionar `empresa_id[:8]` no job_id.

### 6b. Interação com coalescing lock (Fase 11)

O coalescing lock (`_probe_locks` dict) protege chamadas CONCORRENTES ao probe HTTP dentro de `lead_in_group()`. O retry job é executado por APScheduler no event loop — é uma NOVA chamada a `lead_in_group()` (via `_probe_retry_job` que chama `_query_membership_row` diretamente, sem passar pelo coalescing).

**Correção:** o handler `_probe_retry_job` NÃO chama `lead_in_group()` recursivamente — chama `_query_membership_row()` e `verificar_lead_no_grupo()` diretamente. Isso evita:
1. Lock recursivo (não há reentrância no asyncio.Lock)
2. Enfileirar retry dentro do retry (loop)

Se PLAN.md decidir que `_probe_retry_job` chame `lead_in_group()` recursivamente, DEVE passar `schedule_retry_on_negative=False` para evitar loop.

---

## 7. `asyncio.create_task` — Onde está, onde é proibido

### 7a. Usos existentes nos arquivos relevantes

```
confirmacao_agendamento.py:926  → _asyncio_rc.create_task(_executar_timeout_job(ag["id"]))
main.py:81-84                   → create_task(_recov_followups/aquec/notif/conf)
```

**Ambos são no recovery startup (lifespan coroutine)** — event loop ativo, task tem lifetime claro (recovery termina sozinho). São aceitáveis.

### 7b. Onde `create_task` é PROIBIDO na Fase 12

Qualquer chamada a `create_task` dentro de:
- `schedule_probe_retry()` — função síncrona chamada de dentro do `async with lock:` de `lead_in_group()`
- `_probe_retry_job` — job APScheduler; task criado aqui seria órfão quando o job handler retornar
- `confirmacao_agendamento.py` probe path — seria task órfão

**Regra:** qualquer async scheduling no retry path usa `scheduler.add_job()`, não `create_task`. [VERIFIED: objetivo do prompt — "asyncio.create_task naked PROIBIDO no retry path"]

---

## Common Pitfalls

### Pitfall 1: `misfire_grace_time=None` + sem max_age guard = job zumbi

**What goes wrong:** `scheduler.py:5` define `job_defaults={"misfire_grace_time": None}`. Isso significa que jobs atrasados SEMPRE executam após restart. Um probe retry de T+30s enfileirado antes de um restart de 47h executará 47h depois sem o max_age guard.

**Why it happens:** misfire_grace_time=None é a configuração correta para todos os outros jobs (noshow, polling, etc.) — eles devem sempre executar. Mas para probe retry, "stale" é o conceito crítico.

**How to avoid:** SEMPRE verificar `age_sec = (datetime.utcnow() - enqueued_at).total_seconds()` como PRIMEIRO check em `_probe_retry_job`. `enqueued_at` deve ser passado como `kwargs` ao registrar o job.

**Warning signs:** log `[PROBE-RETRY]` executando com `age_sec > 600` — indica job zumbi.

### Pitfall 2: Loop infinito de retry

**What goes wrong:** `_probe_retry_job` chama `lead_in_group()` com `schedule_retry_on_negative=True` → `lead_in_group` enfileira retry → `_probe_retry_job` executa de novo → loop.

**Why it happens:** Se o handler chamar `lead_in_group()` recursivamente sem controle.

**How to avoid:** `_probe_retry_job` NÃO chama `lead_in_group()`. Chama `_query_membership_row()` + `verificar_lead_no_grupo()` diretamente. O controle de attempts é via `attempts_left` decrementado a cada chamada de `schedule_probe_retry()`.

**Warning signs:** logs `[PROBE-RETRY]` com attempt sempre 0 ou ids duplicados sem o counter incrementando.

### Pitfall 3: `replace_existing=True` apaga retry legítimo

**What goes wrong:** Dois eventos paralelos para o mesmo lead+grupo (aquec + notif) ambos enfileiram `probe_retry:{jid}:{tel}:0` — o segundo sobrescreve o primeiro, resetando o timer.

**Why it happens:** `replace_existing=True` é intencional para idempotência, mas tem efeito colateral.

**How to avoid:** O reset do timer é aceitável — ambos os eventos querem o mesmo resultado (confirmar se lead está no grupo). O segundo job executa com delay a partir do segundo enqueue. Pior caso: delay efetivo de 30s em vez de 0s desde o primeiro evento.

**Warning signs:** se o log mostrar `[PROBE-RETRY] enfileirado attempt=0` para o mesmo `(jid, tel)` múltiplas vezes em sequência rápida — é o replace happening, não um bug.

### Pitfall 4: `enqueued_at` do recovery restart não é o `enqueued_at` original

**What goes wrong:** Recovery no startup cria novo job com `enqueued_at=datetime.utcnow()`. O max_age guard passa (age=0s), mas o retry deveria ter sido descartado (era de 47h atrás).

**Why it happens:** Recovery não preserva o timestamp original do enqueue.

**How to avoid:** Se usando strategy de marker em `conversas`, o marker inclui `enqueued_at` no conteúdo: `PROBE_RETRY_PENDING:{grupo_jid}:{telefone}:{attempt}:{enqueued_at_iso}`. Recovery lê o `enqueued_at` original do marker. Se `datetime.utcnow() - enqueued_at > max_age_seconds`, SKIP sem enfileirar.

**Warning signs:** recovery log mostrando `PROBE_RETRY_PENDING` markers com mais de 10min de idade sendo re-enfileirados.

### Pitfall 5: Probe negativo em `source='probe'` re-enfileira mesmo com `source='orphan'`

**What goes wrong:** Lead em grupo órfão (caso Fernanda, `source='orphan'`) retorna `in_group=False`. Se o código ativar retry na condição `in_group is False` sem checar `source`, enfileira retry inútil — grupo órfão nunca terá row na tabela da instância atual.

**Why it happens:** A condição `probe_in_group is False` dentro do `async with lock:` é verdadeira em dois cenários: (1) probe Evolution confirmou ausência; (2) `source='orphan'` retornou False antes do STEP 5. Mas `source='orphan'` retorna ANTES de chegar ao STEP 5 (short-circuit no STEP 3).

**How to avoid:** O retry é enfileirado SOMENTE no STEP 5 (dentro do `async with lock:`), onde `source` implicitamente é `'probe'`. Não é possível chegar ao STEP 5 com `source='orphan'` — o orphan retorna em STEP 3. Pitfall é teórico, mas documentar para clareza.

---

## Code Examples

### Exemplo 1: schedule_probe_retry() + _probe_retry_job() completos

```python
# app/services/grupo_membership.py — ADIÇÕES Fase 12
# [ASSUMED: design proposto; padrão verificado via evolution_router.py e grupo_fallback.py]

_RETRY_DELAYS_SEC = [30, 120, 300]  # attempt 0=30s, 1=2min, 2=5min

def schedule_probe_retry(
    empresa_id: str,
    grupo_jid: str,
    telefone: str,
    lid: str,
    attempts_left: int = 3,
    max_age_seconds: int = 600,
    evo_url: str = "",
    evo_key: str = "",
    evo_inst: str = "",
    agendamento_id: str = "",
) -> None:
    from app.scheduler import scheduler
    attempt = 3 - attempts_left
    if attempt >= len(_RETRY_DELAYS_SEC):
        return
    delay = _RETRY_DELAYS_SEC[attempt]
    enqueued_at = datetime.utcnow()
    run_date = enqueued_at + timedelta(seconds=delay)
    job_id = f"probe_retry:{grupo_jid}:{telefone}:{attempt}"
    try:
        scheduler.add_job(
            _probe_retry_job,
            "date",
            run_date=run_date,
            kwargs={
                "empresa_id": empresa_id, "grupo_jid": grupo_jid,
                "telefone": telefone, "lid": lid,
                "attempts_left": attempts_left - 1,
                "max_age_seconds": max_age_seconds,
                "enqueued_at": enqueued_at,
                "evo_url": evo_url, "evo_key": evo_key, "evo_inst": evo_inst,
                "agendamento_id": agendamento_id,
            },
            id=job_id, replace_existing=True,
            timezone="UTC", misfire_grace_time=None,
        )
        print(f"[PROBE-RETRY] scheduled attempt={attempt} delay={delay}s "
              f"job={job_id} empresa={empresa_id[:8]}")
    except Exception as e:
        print(f"[PROBE-RETRY] erro schedule job={job_id}: {e}")


async def _probe_retry_job(
    empresa_id: str, grupo_jid: str, telefone: str, lid: str,
    attempts_left: int, max_age_seconds: int, enqueued_at: "datetime",
    evo_url: str, evo_key: str, evo_inst: str, agendamento_id: str = "",
) -> None:
    from app.db.client import get_supabase
    from app.services import probe_cache

    # GUARD: max_age absoluto
    age_sec = (datetime.utcnow() - enqueued_at).total_seconds()
    if age_sec > max_age_seconds:
        print(f"[PROBE-RETRY] [JOB_EXPIRED] age={age_sec:.0f}s empresa={empresa_id[:8]} "
              f"grupo={grupo_jid[:24]} tel={telefone}")
        return

    sb = get_supabase()

    # SHORT-CIRCUIT: tabela primeiro (caso Rosania)
    try:
        row = _query_membership_row(sb, empresa_id, grupo_jid, telefone, lid)
    except Exception:
        row = None

    if row is not None:
        probe_cache.set(empresa_id, grupo_jid, telefone, lid, True)
        print(f"[PROBE-RETRY] [TABLE_HIT] empresa={empresa_id[:8]} grupo={grupo_jid[:24]} "
              f"tel={telefone} — row found, no probe needed")
        return

    # Probe Evolution
    if not all([evo_url, evo_key, evo_inst]):
        return
    try:
        from app.services.evolution import verificar_lead_no_grupo
        res = await verificar_lead_no_grupo(evo_url, evo_key, evo_inst, grupo_jid, telefone or "", lead_lid=lid)
        in_group = res.get("in_group")
    except Exception as _e:
        print(f"[PROBE-RETRY] probe error: {_e}")
        in_group = None

    if in_group is True:
        probe_cache.set(empresa_id, grupo_jid, telefone, lid, True)
        print(f"[PROBE-RETRY] [PROBE_HIT] empresa={empresa_id[:8]} grupo={grupo_jid[:24]} tel={telefone}")
        return

    if attempts_left > 0:
        schedule_probe_retry(
            empresa_id, grupo_jid, telefone, lid,
            attempts_left=attempts_left, max_age_seconds=max_age_seconds,
            evo_url=evo_url, evo_key=evo_key, evo_inst=evo_inst,
            agendamento_id=agendamento_id,
        )
    else:
        print(f"[PROBE-RETRY] [MAX_ATTEMPTS] empresa={empresa_id[:8]} grupo={grupo_jid[:24]} tel={telefone}")
```

### Exemplo 2: Ativação em confirmacao_agendamento.py

```python
# Substitui linhas 288-297 de confirmacao_agendamento.py
# [VERIFIED: leitura direta do arquivo; padrão de migração da Fase 11 §7]
from app.services.grupo_membership import lead_in_group
_lid_cf = _get_lead_lid_for_group(sb, empresa_id, telefone, grupo_jid)
_result_cf = await lead_in_group(
    sb, empresa_id, telefone, grupo_jid,
    lid=_lid_cf,
    evo_url=evo_url, evo_key=evo_key, evo_inst=evo_inst,
    schedule_retry_on_negative=True,  # D-1: tem margem de horas
)
_in_group_real_cf = (_result_cf.get("in_group") is True)
# Linha 295 (print) pode ser atualizado para logar source também:
print(f"[CONFIRMACAO] {agendamento_id[:8]} lead_in_group: "
      f"in_group={_result_cf.get('in_group')!r} source={_result_cf.get('source')} lid={_lid_cf!r}")
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Probe Evolution síncrono único | Probe com retry async 30s/2min/5min | Fase 12 | Cobre janela propagação Evolution 60-180s |
| Sem max_age guard em jobs one-shot | `max_age_seconds=600` guard no handler | Fase 12 | Cobre Valquiria (47h late job) |
| `verificar_lead_no_grupo` direto em callers | `lead_in_group(schedule_retry_on_negative=True)` | Fase 12 (confirmacao, notif) | Webhook-first + retry via tabela first |
| APScheduler UUID id (evo_retry) | Id determinístico + replace_existing | Já existia em timeout_grupo_aguard | Idempotência: re-enqueue não duplica |
| Recovery aquec com guard 6h fixo | Recovery probe_retry com enqueued_at original + max_age dinâmico | Fase 12 | Guard baseado em quando foi enfileirado, não em quando o backend reiniciou |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `_probe_retry_job` deve chamar `_query_membership_row` diretamente (não via `lead_in_group`) para evitar loop | §2 Pattern 2, §6b | Se PLAN.md escolher chamar `lead_in_group`, deve passar `schedule_retry_on_negative=False` explicitamente |
| A2 | "Timeout 30min FALLBACK" no objetivo se refere à probe em `warmup_grupo.py` notif job, não ao `_executar_timeout_grupo_aguardando` em si | §5b | Se o objetivo for outro caller, PLAN.md precisa identificar o callsite correto |
| A3 | Strategy de marker `PROBE_RETRY_PENDING` em `conversas` para recovery startup | §Architecture Pattern 4 | Alternativa sem marker (re-schedule baseado em estado DB) é mais simples mas menos precisa |
| A4 | `probe_in_group is False` (não `None`) é a condição de ativação do retry | §2b | Se `None` também deve enfileirar (probe HTTP falhou), adicionar `probe_in_group in (False, None)` — mas com risco de retry em erros de infra |
| A5 | Backfill via `upsert_grupo_membership(..., fonte='probe_backfill')` é OPCIONAL quando probe confirma True | §Pattern 2 | Se PLAN.md quer consistência imediata da tabela, deve incluir o upsert |

---

## Open Questions

1. **`_executar_timeout_grupo_aguardando` probe migração**
   - What we know: a função não tem probe direto — apenas transiciona FSM
   - What's unclear: qual é o callsite exato que o objetivo quer migrar ("timeout 30min FALLBACK")
   - Recommendation: migrar `_executar_notificacao_grupo_job` em `warmup_grupo.py` + `confirmacao_agendamento.py:291`; confirmar com user se `_executar_timeout_grupo_aguardando` tem probe que não foi encontrado

2. **Recovery startup com `enqueued_at` original**
   - What we know: recovery via `create_task` em main.py é o padrão; marker em `conversas` pode preservar `enqueued_at`
   - What's unclear: overhead de inserir/deletar marker `PROBE_RETRY_PENDING` em `conversas` vs. não ter recovery preciso
   - Recommendation: PLAN.md pode decidir recovery sem marker (mais simples), documentando que retries após restart têm `enqueued_at = datetime.utcnow()` (janela reiniciada)

3. **`agendamento_id` em `schedule_probe_retry()`**
   - What we know: parâmetro opcional; confirmacao_agendamento.py tem `agendamento_id` disponível; warmup_grupo.py pode ter via query
   - What's unclear: se `agendamento_id` é necessário para recovery ou apenas para logging
   - Recommendation: incluir como kwarg opcional; se ausente, recovery usa `grupo_jid` + `telefone` para lookup

---

## Environment Availability

Step 2.6: SKIPPED — Fase 12 é puramente código Python sobre infra já instalada. Nenhuma nova ferramenta, serviço ou CLI requerida.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (já em prod desde Fase 9, v2.1) |
| Config file | `leadflow-backend/pytest.ini` ou `pyproject.toml` (verificar antes de Wave 0) |
| Quick run command | `pytest tests/test_probe_retry.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROBE-RETRY-01 | `schedule_probe_retry` enfileira job com id determinístico + `replace_existing=True` | unit | `pytest tests/test_probe_retry.py::test_schedule_creates_job -x` | ❌ Wave 0 |
| PROBE-RETRY-01 | max_age guard: job com `enqueued_at` > 600s atrás retorna sem executar ([JOB_EXPIRED]) | unit | `pytest tests/test_probe_retry.py::test_max_age_guard_expired -x` | ❌ Wave 0 |
| PROBE-RETRY-01 | max_age guard: job com `enqueued_at` recente executa normalmente | unit | `pytest tests/test_probe_retry.py::test_max_age_guard_valid -x` | ❌ Wave 0 |
| PROBE-RETRY-01 | Table-first short-circuit: row existente → return sem probe HTTP (caso Rosania) | unit | `pytest tests/test_probe_retry.py::test_table_hit_skips_probe -x` | ❌ Wave 0 |
| PROBE-RETRY-01 | Sequência completa: False → attempt=0 → False → attempt=1 → TABLE_HIT | integration | `pytest tests/test_probe_retry.py::test_rosania_sequence -x` | ❌ Wave 0 |
| PROBE-RETRY-01 | attempts_left=0: [MAX_ATTEMPTS] sem enfileirar próximo job | unit | `pytest tests/test_probe_retry.py::test_max_attempts_no_reschedule -x` | ❌ Wave 0 |
| PROBE-RETRY-01 | Idempotência: 2 enqueues com mesma chave = 1 job (replace_existing) | unit | `pytest tests/test_probe_retry.py::test_idempotent_job_id -x` | ❌ Wave 0 |
| PROBE-RETRY-01 | `schedule_retry_on_negative=False`: probe False NÃO enfileira retry | unit | `pytest tests/test_probe_retry.py::test_stub_false_no_retry -x` | ❌ Wave 0 |
| PROBE-RETRY-01 | `probe_in_group=None` (erro HTTP): NÃO enfileira retry | unit | `pytest tests/test_probe_retry.py::test_none_probe_no_retry -x` | ❌ Wave 0 |
| PROBE-RETRY-02 | `confirmacao_agendamento:291` usa `lead_in_group(schedule_retry_on_negative=True)` | smoke | `pytest tests/test_probe_retry.py::test_confirmacao_caller_activates_retry -x` | ❌ Wave 0 |
| PROBE-RETRY-02 | Aquec mantém síncrono: `ativar_fallback_se_necessario` não ativa retry | smoke | `pytest tests/test_probe_retry.py::test_aquec_stays_sync -x` | ❌ Wave 0 |

### Padrão de mock APScheduler para testes

```python
# tests/test_probe_retry.py — fixture recomendada (padrão da Fase 11)
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

@pytest.fixture
def mock_scheduler():
    """Mock scheduler.add_job para capturar jobs enfileirados sem APScheduler real."""
    jobs = []
    mock = MagicMock()
    mock.add_job.side_effect = lambda fn, trigger, **kwargs: jobs.append({
        "fn": fn, "trigger": trigger, **kwargs
    })
    with patch("app.services.grupo_membership.scheduler", mock):
        yield mock, jobs

@pytest.fixture(autouse=True)
def reset_state():
    from app.services import probe_cache
    from app.services import grupo_membership as gm
    probe_cache.clear_all()
    gm._reset_probe_locks_for_tests()
    yield
    probe_cache.clear_all()
    gm._reset_probe_locks_for_tests()
```

### Caso Rosania — teste de sequência completa

```python
@pytest.mark.asyncio
async def test_rosania_sequence(mock_scheduler):
    """Webhook chega T+138s. Retry T+120s encontra row na tabela → short-circuit."""
    scheduler_mock, jobs = mock_scheduler
    sb_mock = MagicMock()

    probe_calls = 0
    async def fake_probe(*args, **kwargs):
        nonlocal probe_calls
        probe_calls += 1
        return {"in_group": False, "erro": ""}

    # Step 1: tabela vazia, probe False → schedule retry attempt=0
    from app.services.grupo_membership import lead_in_group
    with patch("app.services.grupo_membership._query_membership_row", return_value=None), \
         patch("app.services.grupo_membership.verificar_lead_no_grupo", fake_probe):
        result = await lead_in_group(
            sb_mock, "emp-uuid", "5562984551622", "123@g.us",
            evo_url="x", evo_key="y", evo_inst="z",
            schedule_retry_on_negative=True,
        )

    assert result["in_group"] is False
    assert result["source"] == "probe"
    assert len(jobs) == 1
    assert jobs[0]["id"] == "probe_retry:123@g.us:5562984551622:0"
    assert probe_calls == 1

    # Step 2: _probe_retry_job attempt=0 — tabela ainda vazia, probe False → schedule attempt=1
    from app.services.grupo_membership import _probe_retry_job
    with patch("app.services.grupo_membership._query_membership_row", return_value=None), \
         patch("app.services.grupo_membership.verificar_lead_no_grupo", fake_probe):
        await _probe_retry_job(
            empresa_id="emp-uuid", grupo_jid="123@g.us", telefone="5562984551622", lid="",
            attempts_left=2, max_age_seconds=600,
            enqueued_at=datetime.utcnow(),
            evo_url="x", evo_key="y", evo_inst="z",
        )
    assert probe_calls == 2

    # Step 3: _probe_retry_job attempt=1 — tabela TEM row (webhook chegou T+138s)
    fake_row = {"entrou_em": "2026-06-09T23:57:00", "saiu_em": None,
                "instance_key": "rejane-leal-mentora", "atualizado_em": "2026-06-09T23:57:00"}
    from app.services import probe_cache as pc
    with patch("app.services.grupo_membership._query_membership_row", return_value=fake_row):
        await _probe_retry_job(
            empresa_id="emp-uuid", grupo_jid="123@g.us", telefone="5562984551622", lid="",
            attempts_left=1, max_age_seconds=600,
            enqueued_at=datetime.utcnow(),
            evo_url="x", evo_key="y", evo_inst="z",
        )
    # Probe não foi chamado (short-circuit)
    assert probe_calls == 2  # sem incremento
    # Cache populado
    cached = pc.get("emp-uuid", "123@g.us", "5562984551622", "")
    assert cached is True
```

### Caso Valquiria — teste de max_age guard

```python
@pytest.mark.asyncio
async def test_max_age_guard_expired():
    """Job com enqueued_at 47h atrás → [JOB_EXPIRED] sem executar probe."""
    from datetime import timedelta
    from app.services.grupo_membership import _probe_retry_job

    probe_called = False
    async def fake_probe(*args, **kwargs):
        nonlocal probe_called
        probe_called = True
        return {"in_group": True}

    old_enqueued = datetime.utcnow() - timedelta(hours=47)
    with patch("app.services.grupo_membership._query_membership_row", return_value=None), \
         patch("app.services.grupo_membership.verificar_lead_no_grupo", fake_probe):
        await _probe_retry_job(
            empresa_id="emp", grupo_jid="123@g.us", telefone="558298129",lid="",
            attempts_left=2, max_age_seconds=600,
            enqueued_at=old_enqueued,
            evo_url="x", evo_key="y", evo_inst="z",
        )

    assert not probe_called, "Probe não deve ser chamado quando job expirado"
```

### Sampling Rate

- **Per task commit:** `pytest tests/test_probe_retry.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green antes de `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_probe_retry.py` — 11 testes acima (cobre PROBE-RETRY-01 + 02)
- [ ] Verificar `pytest.ini` ou `pyproject.toml` em `leadflow-backend/` — se ausente, criar com `asyncio_mode = "auto"`

---

## Security Domain

Fase 12 é puramente lógica de retry e scheduling — não introduce novos endpoints, inputs de usuário, ou fluxos de autenticação. As categorias ASVS não se aplicam como novas superfícies. As chamadas a `verificar_lead_no_grupo` e `upsert_grupo_membership` seguem os mesmos controles de segurança já validados nas Fases 10-11.

---

## Sources

### Primary (HIGH confidence)
- `leadflow-backend/app/services/grupo_membership.py` — assinatura `lead_in_group()` + stub + código completo (leitura direta)
- `leadflow-backend/app/scheduler.py` — `AsyncIOScheduler` + `misfire_grace_time=None` + job defaults (leitura direta)
- `leadflow-backend/app/main.py` — recovery startup pattern com `create_task` no lifespan (leitura direta)
- `leadflow-backend/app/services/evolution_router.py:410-464` — retry queue APScheduler existente (`_retry_send_text_job`, backoff 60→960s, MSG_FALHA_PERSISTENTE) (leitura direta)
- `leadflow-backend/app/services/grupo_fallback.py:840-900` — `_agendar_timeout_grupo_aguardando` + `_executar_timeout_grupo_aguardando` (leitura direta)
- `leadflow-backend/app/routers/warmup_grupo.py:161-252` — `recuperar_aquecimentos_pendentes()` + guard 6h (leitura direta)
- `leadflow-backend/app/routers/confirmacao_agendamento.py:265-337` — probe D-1 atual em linha 291 + `recuperar_confirmacoes_pendentes()` (leitura direta)
- `.planning/phases/11-*/11-RESEARCH.md` + `11-01-SUMMARY.md` — design coalescing + callsite map + `schedule_retry_on_negative` stub decision (leitura direta)

### Secondary (MEDIUM confidence)
- REQUIREMENTS.md `PROBE-RETRY-01` e `PROBE-RETRY-02` — text completo dos requisitos
- STATE.md Decisions Log — `max_age_seconds=600` e in-memory + reschedule startup (decisões registradas)

### Tertiary (LOW confidence)
- Nenhuma — toda research foi baseada em leitura direta do codebase

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — todos os símbolos verificados via grep + leitura direta
- Architecture: HIGH — padrões copiados de código existente em prod (`evolution_router.py`, `grupo_fallback.py`, `main.py`)
- Pitfalls: HIGH — derivados de casos reais (Valquiria, Rosania) + análise de código existente
- Caller migration map: HIGH — leitura direta dos arquivos + Fase 11 SUMMARY confirma o que foi/não foi migrado

**Research date:** 2026-06-09
**Valid until:** 2026-07-09 (infra estável; APScheduler 3.10.4 sem mudanças planejadas)
