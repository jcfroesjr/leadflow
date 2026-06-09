# Architecture Patterns — v2.2 Webhook-First Grupo Membership

**Domain:** Leadflow backend (FastAPI single-instance + APScheduler + Supabase Postgres + Evolution API webhook)
**Researched:** 2026-06-09
**Confidence:** HIGH (codebase introspection direta — paths e linhas confirmadas)

---

## TL;DR — Decisões arquiteturais propostas

| Pergunta | Resposta curta |
|---|---|
| 1. Onde escrever em `grupo_membership`? | `app/routers/grupo_webhook.py` — duas funções helper (`_upsert_membership_add`, `_upsert_membership_remove`) chamadas DENTRO de `_processar_grupo_payload` **antes** dos handlers existentes (claim de marker + `processar_entrada_lead_no_grupo`). Idempotência via UNIQUE `(grupo_jid, telefone_ou_lid)` + comparação de timestamp do payload. |
| 2. `lead_in_group()` decisão | **NOVA função** em `app/services/grupo_membership.py`. Tabela primeiro; só consulta probe se row ausente OU `saiu_em IS NOT NULL` mais recente que `entrou_em` OU `entrou_em` < 10s atrás (gap de race do webhook). Janela "stale" = `entrou_em IS NULL AND criado_em < now - 6min` (Evolution já deveria ter propagado). |
| 3. Retry exponencial | **Job APScheduler separado** (`probe_retry_{ag_id}_{attempt}`) — NÃO wrap em `ativar_fallback_se_necessario` (que é síncrono e já complexo). Chamador agenda retry; cada tentativa é um job independente em 30s/2min/5min. |
| 4. Cache | Módulo singleton `app/services/probe_cache.py` com `cachetools.TTLCache(maxsize=512, ttl=300)` + `threading.RLock`. Single-worker no Easypanel = thread-safety trivial. |
| 5. FSM audit log | **Append-only em conversas** (marker `GRUPO_STATE_CHANGE:{ag_id}:{from}:{to}:{reason}:{caller}`). Reusa unique constraint + RLS. Volume esperado: ~3-5 transições por agendamento × ~30 ag/dia = ~150 rows/dia (desprezível). |
| 6. Build order | MEMB schema → MEMB write (webhook ADD) → `lead_in_group()` consumer → PROBE cache → PROBE retry → MEMB write (REMOVE/LEAVE) → FSM audit → testes regressão |

---

## 1. Mapa de Integração com Arquitetura Existente

### Componentes envolvidos

| Componente | Arquivo | Linhas-chave | Papel hoje | Papel v2.2 |
|---|---|---|---|---|
| Webhook handler grupo | `app/routers/grupo_webhook.py` | 53-78 (rota); 81-226 (`_processar_grupo_payload`) | Captura ADD, salva `LEAD_LID` em conversas, dispara `processar_entrada_lead_no_grupo` | **EXPANDIDO**: também escreve em `grupo_membership` (ADD + REMOVE); LEAD_LID continua redundante para backwards compat de markers legados |
| Probe síncrono Evolution | `app/services/evolution.py:198-290` (`verificar_lead_no_grupo`) | 198 | Fonte primária via HTTP GET findGroupInfos | **FALLBACK**: chamado por `lead_in_group()` só quando `grupo_membership` ausente/stale; nova assinatura aceita `use_cache=True` |
| Entry point fallback | `app/services/grupo_fallback.py:177-435` (`ativar_fallback_se_necessario`) | 177 | 8 níveis aninhados de check (markers legacy, FSM, probe, etc) | **SIMPLIFICADO**: substitui chamadas a `verificar_lead_no_grupo(...)` por `lead_in_group(...)` (tabela primeiro); blocos 1b/1c/2 ficam mais finos |
| FSM grupo state | `app/services/grupo_state.py:76-127` (`get/set/transition_grupo_state`) | 130-142 (`transition_grupo_state`) | Append-only marker `GRUPO_STATE:{ag}:{state}` em conversas; `transition_grupo_state` já valida `from_states` mas é OPCIONAL — callers usam `set_grupo_state` direto sem validação | **ENDURECIDO**: `set_grupo_state` ganha guard interno de monotonicidade (BLOQUEIA `ATIVO→AGUARDANDO` sem flag `force=True`); todo set escreve audit log auxiliar |
| Scheduler global | `app/scheduler.py:5` (`scheduler = AsyncIOScheduler(...)`) | 8-45 (`registrar_jobs_internos`) | Singleton para jobs delayed (alerta 180s, convite 60s, lembrete 4h, timeout 30min) | **+ Nova categoria**: `probe_retry_*` jobs com 3 tentativas escalonadas |
| Consumers do probe | 5 callers em `grupo_fallback.py` (251, 311, 337, 477, 624, 1173, 1256), `confirmacao_agendamento.py:291`, `leads.py:123`, `admin.py:769,981` | — | Cada caller chama `verificar_lead_no_grupo` direto, sem cache | **MIGRADOS** gradualmente para `lead_in_group()` — admin/teste mantém probe direto para diagnóstico |

### Componentes NOVOS

| Componente | Arquivo NOVO | Responsabilidade |
|---|---|---|
| Tabela `grupo_membership` | Migration `004_grupo_membership.sql` | Fonte primária materializada (1 row por par grupo×lead) |
| Função `lead_in_group()` | `app/services/grupo_membership.py` | Decision tree: tabela → probe (com cache) |
| Helper UPSERT add/remove | `app/services/grupo_membership.py` | `record_lead_entered(...)`, `record_lead_left(...)`, `mark_left(...)` |
| Cache de probe | `app/services/probe_cache.py` | TTLCache singleton + invalidate hooks |
| Retry exponencial probe | `app/services/grupo_membership.py` (`schedule_probe_retry`) + handler em `_executar_probe_retry` | Agenda 3 jobs APScheduler escalonados |
| Audit FSM | `app/services/grupo_state.py` (expandir `set_grupo_state`) | Inserir 2º marker `GRUPO_STATE_CHANGE` ao lado do `GRUPO_STATE` |

---

## 2. Onde inserir write em `grupo_membership` (Pergunta 1)

### 2a. ADD (lead entrou no grupo)

**Local exato:** `app/routers/grupo_webhook.py:_processar_grupo_payload` linhas 130-160 — **ANTES** do loop atual `for tel in telefones_entraram:`.

**Pseudocódigo do patch:**

```
linha ~131 (depois de "if not telefones_entraram and not lids_entraram: return"):

  # ── v2.2 MEMB-02: persiste membership ANTES dos handlers atuais ──
  # Idempotência via UNIQUE (grupo_jid, COALESCE(telefone, lid))
  # Ordem importante: persistimos PRIMEIRO porque processar_entrada_lead_no_grupo
  # já pode consultar lead_in_group() ao decidir saudação.
  from app.services.grupo_membership import record_lead_entered

  payload_ts_iso = data.get("timestamp") or _now_iso()  # Evolution manda em ms epoch
  for tel in telefones_entraram:
      record_lead_entered(sb, empresa_id, grupo_jid, telefone=tel,
                          lid=None, evento_ts=payload_ts_iso)
  for lid_jid in lids_entraram:
      record_lead_entered(sb, empresa_id, grupo_jid, telefone=None,
                          lid=lid_jid, evento_ts=payload_ts_iso)
  # ── fim MEMB-02 ──

  # Resto do handler atual (linha 161+) segue inalterado — fluxo de markers
  # GRUPO_AGUARDANDO_ENTRADA continua escrevendo, idempotente.
```

**Por que ANTES do loop atual:**
- `processar_entrada_lead_no_grupo` (linha 180) pode chamar `lead_in_group()` internamente em v2.2 para idempotência de saudação. Garantir que row já existe evita lookup → False → bypass indevido.
- Falha no INSERT de membership não pode bloquear o handler atual (caller `process_entrada_lead_no_grupo` é crítico). Logo, `record_lead_entered` é **try/except interno** com `print` + return — nunca propaga exception.

### 2b. REMOVE (lead saiu)

**Atualmente:** `_processar_grupo_payload` linha 100-102 retorna cedo para `action != "add"`. Precisa virar:

```
linha 100:
  if action not in ("add", "remove"):
      return {"ok": True, "ignorado": True, "motivo": f"action={action}"}

# após coletar participants:
  if action == "remove":
      from app.services.grupo_membership import record_lead_left
      for tel in telefones_entraram:
          record_lead_left(sb, empresa_id, grupo_jid, telefone=tel, lid=None, evento_ts=payload_ts_iso)
      for lid_jid in lids_entraram:
          record_lead_left(sb, empresa_id, grupo_jid, telefone=None, lid=lid_jid, evento_ts=payload_ts_iso)
      # Dispara handler de leave (notif DM, marca conversas)
      await _handle_lead_left_group(sb, empresa_id, grupo_jid, telefones_entraram, lids_entraram)
      return {"ok": True, "action": "remove", "processados": ...}
```

`_handle_lead_left_group` é função nova em `grupo_fallback.py` (LEAVE-01) que:
1. Insere marker `LEAD_SAIU_GRUPO:{grupo_jid}` em `conversas` (claim atômico)
2. Avalia se há agendamento ativo → se sim, FSM transition `ATIVO → LEFT_GROUP` (novo estado)
3. Notif pré-reunião/D-1 detecta `saiu_em != NULL` e vai pro DM (LEAVE-02)

### 2c. Idempotência detalhada

**Estratégia: UPSERT por `(empresa_id, grupo_jid, COALESCE(telefone, lid))` + comparação de timestamp.**

```sql
-- pseudocódigo da função record_lead_entered:
INSERT INTO grupo_membership
  (empresa_id, grupo_jid, telefone, lid, entrou_em, saiu_em, criado_em, atualizado_em)
VALUES ($1, $2, $3, $4, $5, NULL, NOW(), NOW())
ON CONFLICT (empresa_id, grupo_jid, COALESCE(telefone, lid))
DO UPDATE SET
  entrou_em = EXCLUDED.entrou_em,
  saiu_em = NULL,              -- entrou de novo após saída
  atualizado_em = NOW()
WHERE
  -- só atualiza se evento é mais recente que último registro
  EXCLUDED.entrou_em > grupo_membership.atualizado_em
  OR grupo_membership.saiu_em IS NOT NULL;
```

**Ordem ADD/REMOVE:** webhook Evolution pode entregar fora de ordem (re-delivery, race). Comparação `EXCLUDED.entrou_em > grupo_membership.atualizado_em` impede REMOVE antigo sobrescrever ADD novo. Para REMOVE:

```sql
UPDATE grupo_membership
SET saiu_em = $5, atualizado_em = NOW()
WHERE empresa_id = $1 AND grupo_jid = $2 AND COALESCE(telefone, lid) = $3
  AND ($5::timestamptz > atualizado_em);  -- REMOVE antigo é no-op
```

**Confiabilidade do timestamp:** Evolution Baileys envia `messageTimestamp` em segundos epoch. Usar esse timestamp do payload (em vez de `NOW()` do servidor) é mais fiel à ordem real. Fallback para `NOW()` se ausente.

---

## 3. `lead_in_group()` — Decisão tabela vs probe (Pergunta 2)

### 3a. Assinatura proposta

```python
# app/services/grupo_membership.py
async def lead_in_group(
    sb,
    empresa_id: str,
    telefone: str,
    grupo_jid: str,
    *,
    lead_lid: str = "",
    evo_url: str = "", evo_key: str = "", evo_inst: str = "",
    allow_probe_fallback: bool = True,
    schedule_retry_on_negative: bool = False,
) -> dict:
    """
    Retorna {'in_group': True|False|None, 'source': 'membership'|'probe'|'probe_cache'|'unknown',
             'stale': bool, 'detail': str}.
    """
```

### 3b. Decision tree

```
                        lead_in_group(empresa_id, telefone, grupo_jid, lid)
                                          │
                                          ▼
                  ┌──────────────────────────────────────────────────┐
                  │ SELECT entrou_em, saiu_em, atualizado_em          │
                  │   FROM grupo_membership                            │
                  │  WHERE empresa_id = $1 AND grupo_jid = $2          │
                  │    AND (telefone = $3 OR lid = $4)                 │
                  │  ORDER BY atualizado_em DESC LIMIT 1               │
                  └──────────────────────────────────────────────────┘
                                          │
            ┌─────────────────────────────┼─────────────────────────────┐
            │                             │                             │
            ▼                             ▼                             ▼
       Row ENCONTRADA              Row AUSENTE                   Erro DB
            │                             │                             │
   ┌────────┴────────┐                    │                             │
   │ saiu_em IS NULL?│                    │                             │
   └────────┬────────┘                    │                             │
       SIM  │   NAO                       │                             │
            │   │                         │                             │
            │   ▼                         │                             │
            │   { in_group: FALSE,        │                             │
            │     source: 'membership',   │                             │
            │     detail: 'left_at=...' } │                             │
            │                             │                             │
            ▼                             ▼                             ▼
       { in_group: TRUE,           probe_fallback(...)            { in_group: None,
         source: 'membership' }    (3c abaixo)                      source: 'unknown',
                                                                    detail: 'db_error' }
```

### 3c. probe_fallback (sub-fluxo)

```
probe_fallback:
  1. cache_hit = probe_cache.get((grupo_jid, telefone, lid))
     se hit:
       return { in_group: cached, source: 'probe_cache' }

  2. probe_result = await verificar_lead_no_grupo(...)  # HTTP Evolution

  3. probe_cache.set((grupo_jid, telefone, lid), probe_result.in_group, ttl=300)

  4. se probe_result.in_group == True:
       # Materializa na tabela (Evolution viu, webhook não chegou — chegará ou não)
       record_lead_entered(sb, empresa_id, grupo_jid, telefone, lid, evento_ts=NOW())
       return { in_group: TRUE, source: 'probe', detail: 'materialized' }

  5. se probe_result.in_group == False AND schedule_retry_on_negative:
       # NÃO conclui negativo definitivo — agenda 3 retries (30s/2min/5min)
       schedule_probe_retry(empresa_id, telefone, grupo_jid, lid, attempt=1)
       return { in_group: None, source: 'probe', detail: 'retry_scheduled' }

  6. se probe_result.in_group == None (Evolution erro):
       return { in_group: None, source: 'probe', detail: probe_result.erro }

  7. caso contrário: return { in_group: False, source: 'probe', stale: True }
```

### 3d. Janela "stale" para fallback ao probe

**Stale 1 — Row de ADD muito recente sem confirmação:**
- Se `entrou_em` < 10s atrás E `saiu_em IS NULL` → confia na tabela (webhook chegou). **Não probe.**
- Se NÃO há row e o `agendamento.criado_em` (grupo criado) < 6min atrás → probe com `schedule_retry_on_negative=True`. Webhook Evolution pode ainda chegar.
- Se NÃO há row e grupo > 6min atrás → probe síncrono (lead provavelmente nunca entrou; cache hit OK).

**Stale 2 — Row de saída:**
- Se `saiu_em IS NOT NULL` e `> entrou_em` → `in_group = False`. **Não probe** (webhook é definitivo para REMOVE).
- Exceção: admin endpoint pode forçar re-probe com `bypass_cache=True`.

**Stale 3 — Tabela diz TRUE, mas suspeita de grupo órfão:**
- Caso Fernanda 07/06 (grupo de instância antiga reusado). Se `lead_in_group()` retorna `membership.in_group=True` MAS `verificar_lead_no_grupo` consultado posteriormente para um caller específico (ex: `leads.py:123` na validação de reuso) volta `False`, NÃO sobrescreve a tabela automaticamente — admin endpoint cuida do bookkeeping.

---

## 4. Retry exponencial — onde plugar (Pergunta 3)

### 4a. Decisão: Job APScheduler separado (NÃO wrap)

**Justificativa:**
- `ativar_fallback_se_necessario` já tem ~450 linhas, 8 blocos aninhados, 3 paths de probe (linha 251, 311, 337). Encapsular retry interno explode a complexidade.
- Retry assíncrono **bloqueia** o caller original (aquec/notif rodando agora não pode esperar 5min). Job APScheduler desacopla.
- Padrão já existe no codebase: `_agendar_alerta_grupo_apos_delay`, `_agendar_convite_lead_apos_delay`, `_agendar_lembrete_convite_4h`, `_agendar_timeout_grupo_aguardando` (linhas 652, 683, 718, 797 de `grupo_fallback.py`).

### 4b. Implementação proposta

```python
# app/services/grupo_membership.py
RETRY_DELAYS_SECONDS = [30, 120, 300]  # 30s, 2min, 5min

def schedule_probe_retry(empresa_id, telefone, grupo_jid, lid, attempt: int):
    """attempt = 1, 2, 3. Após 3 tentativas falharem, conclui negativo definitivo."""
    if attempt > len(RETRY_DELAYS_SECONDS):
        return
    delay = RETRY_DELAYS_SECONDS[attempt - 1]
    from app.scheduler import scheduler
    job_id = f"probe_retry_{empresa_id[:8]}_{telefone}_{grupo_jid[:20]}_{attempt}"
    run_at = datetime.utcnow() + timedelta(seconds=delay)
    scheduler.add_job(
        _executar_probe_retry,
        "date",
        run_date=run_at,
        args=[empresa_id, telefone, grupo_jid, lid, attempt],
        id=job_id,
        replace_existing=True,
        timezone="UTC",
    )

async def _executar_probe_retry(empresa_id, telefone, grupo_jid, lid, attempt):
    # 1. Membership chegou nesse intervalo? Pula.
    sb = get_supabase()
    row = _get_membership_row(sb, empresa_id, grupo_jid, telefone, lid)
    if row and row.get("entrou_em") and not row.get("saiu_em"):
        print(f"[PROBE-RETRY] attempt={attempt} {telefone}: webhook chegou — pula")
        # Sucesso silencioso, FSM já foi atualizado pelo webhook
        return

    # 2. Probe again (invalida cache pra forçar fresh)
    probe_cache.invalidate((grupo_jid, telefone, lid))
    cfg = _load_evolution_config(sb, empresa_id)
    probe = await verificar_lead_no_grupo(**cfg, grupo_jid=grupo_jid,
                                           telefone=telefone, lead_lid=lid)

    if probe.get("in_group") is True:
        record_lead_entered(sb, empresa_id, grupo_jid, telefone, lid, NOW())
        # Aciona handler de entrada tardia (sincroniza FSM + aquec)
        await processar_entrada_lead_no_grupo(empresa_id, telefone, grupo_jid)
        return

    if probe.get("in_group") is False and attempt < len(RETRY_DELAYS_SECONDS):
        schedule_probe_retry(empresa_id, telefone, grupo_jid, lid, attempt + 1)
        return

    # Esgotou tentativas: conclui definitivo
    print(f"[PROBE-RETRY] {telefone}: esgotou {attempt} tentativas, conclui not_in_group")
    # Caller original já tomou decisão pessimista (fallback DM); aqui só audit.
```

### 4c. Quem agenda o primeiro retry?

Quando `lead_in_group()` é chamado por um caller que pode esperar (ex: timeout de 30min → ainda há margem), passa `schedule_retry_on_negative=True`. Para callers que precisam decisão SÍNCRONA (ex: enviar aquec AGORA), passa `False` e aceita decisão pessimista.

**Callers e `schedule_retry_on_negative`:**

| Caller | arquivo:linha | Síncrono ou pode esperar? | Flag |
|---|---|---|---|
| `ativar_fallback_se_necessario` block 1c | `grupo_fallback.py:311` | Síncrono — decisão de ativar DM agora | `False` |
| Aquec job ao executar item | `warmup_grupo.py` (vários) | Síncrono — item está sendo disparado | `False` |
| Notif pré-reunião / D-1 | `confirmacao_agendamento.py:291` | Tem margem (24h antes) | `True` |
| Timeout 30min AGUARDANDO→FALLBACK_1_1 | `grupo_fallback.py:_executar_timeout_grupo_aguardando` | Tem margem | `True` |
| Endpoint admin | `admin.py:769,981` | Diagnóstico — fresh probe sempre | `False`, bypass cache |

---

## 5. Cache in-memory (Pergunta 4)

### 5a. Decisão: módulo singleton com `cachetools.TTLCache` + `threading.RLock`

**Por quê não Redis:** já decidido em PROJECT.md ("in-memory é suficiente — single-worker no Easypanel"). Confirmo viabilidade:
- Pico estimado: 30 grupos ativos × 4-5 probes/dia ≈ 150 probes/dia. TTL 5min agrupa em janelas.
- Memória: 512 entradas × ~100 bytes = ~50KB. Trivial.
- Single-worker Uvicorn → single processo Python → uma instância de cache cobre tudo.

### 5b. Implementação

```python
# app/services/probe_cache.py
import threading
from cachetools import TTLCache

_cache: TTLCache = TTLCache(maxsize=512, ttl=300)  # 5min
_lock = threading.RLock()

def _key(grupo_jid: str, telefone: str | None, lid: str | None) -> tuple:
    return (grupo_jid, telefone or "", (lid or "").lower())

def get(grupo_jid, telefone, lid) -> bool | None | str:
    """Retorna True/False/None se cacheado, ou sentinel MISS."""
    with _lock:
        return _cache.get(_key(grupo_jid, telefone, lid), MISS)

def set(grupo_jid, telefone, lid, in_group: bool | None) -> None:
    with _lock:
        _cache[_key(grupo_jid, telefone, lid)] = in_group

def invalidate(grupo_jid, telefone, lid) -> None:
    with _lock:
        _cache.pop(_key(grupo_jid, telefone, lid), None)

def invalidate_all_for_group(grupo_jid: str) -> int:
    """Útil quando webhook ADD/REMOVE chega — invalida todas as entradas pro grupo."""
    with _lock:
        keys_to_drop = [k for k in _cache.keys() if k[0] == grupo_jid]
        for k in keys_to_drop:
            del _cache[k]
        return len(keys_to_drop)

MISS = object()
```

### 5c. Thread-safety com single-worker

**APScheduler `AsyncIOScheduler`** (confirmado em `scheduler.py:5`) usa o **mesmo event loop** do Uvicorn. Logo:
- Webhook handler (async) + jobs APScheduler (coroutines no mesmo loop) → não há concorrência real entre tasks Python. `RLock` é **defensivo** (não estritamente necessário em event loop puro), mas barato.
- Se algum dia migrar para `BackgroundScheduler` (thread pool), `RLock` já cobre.

### 5d. Invalidação

**Pontos de invalidação obrigatórios:**
- `record_lead_entered(...)` → `probe_cache.invalidate_all_for_group(grupo_jid)` (lead novo entrou → todas as decisões in_group=False naquele grupo viraram potencialmente stale)
- `record_lead_left(...)` → idem
- Endpoint admin `forcar-revalidacao` (`admin.py:769`) → `invalidate(...)` para o par específico + força probe

---

## 6. FSM audit log (Pergunta 5)

### 6a. Decisão: append-only em `conversas` (marker dedicado)

**Por quê não nova tabela:**
- Volume baixo (~150 rows/dia estimado, ver §TL;DR).
- Reusa unique constraint `conversas_sistema_unique_idx` para idempotência.
- Reusa RLS já configurado (`empresa_id` filtro).
- Frontend admin (`/admin/grupos`) já lê `conversas` — facilita exibir timeline de transições sem JOIN.

**Formato do marker:**
```
GRUPO_STATE_CHANGE:{ag_id}:{from}:{to}:{reason}:{caller}
```
- `{from}` = `AGUARDANDO|FALLBACK_1_1|ATIVO|LEFT_GROUP|null`
- `{reason}` = `webhook_add|webhook_remove|timeout_30min|admin_force|probe_confirm|leave_handler|...`
- `{caller}` = nome do módulo/função para tracing (ex: `grupo_webhook.py`, `ativar_fallback.b1c`, `admin.forcar`)

### 6b. Patch em `grupo_state.py`

`set_grupo_state` (linha 104-127) ganha **2 modificações**:

1. **Guard de monotonicidade:**
```python
MONOTONIC_RANK = {None: 0, "AGUARDANDO": 1, "FALLBACK_1_1": 2, "ATIVO": 3, "LEFT_GROUP": 4}

def set_grupo_state(sb, empresa_id, telefone, agendamento_id, state, *,
                     reason: str = "", caller: str = "", force: bool = False) -> bool:
    current = get_grupo_state(sb, empresa_id, agendamento_id)
    if not force and MONOTONIC_RANK.get(state, -1) < MONOTONIC_RANK.get(current, 0):
        print(f"[GRUPO-STATE] {agendamento_id[:8]} BLOQUEADO: {current} → {state} (não monotônico)")
        # Audit do bloqueio também — vital pra debug
        _insert_audit(sb, empresa_id, telefone, agendamento_id,
                      current, state, f"BLOCKED:{reason}", caller)
        return False
    # ... insert GRUPO_STATE normal ...
    _insert_audit(sb, empresa_id, telefone, agendamento_id,
                  current, state, reason, caller)
    return True
```

2. **Exceção LEFT_GROUP:** estado terminal sem reversão (sai do grupo é definitivo nesse agendamento). Rank 4 garante que `ATIVO → LEFT_GROUP` é permitido mas reverso bloqueado.

### 6c. Todos os callers de `set_grupo_state` no codebase

Precisam adaptar para passar `reason` + `caller`:
- `grupo_fallback.py:266` (`set_grupo_state(..., STATE_ATIVO)` — após Evolution confirma legacy)
- `grupo_fallback.py:385` (`set_grupo_state(..., STATE_AGUARDANDO)` — ativação inicial)
- `_executar_timeout_grupo_aguardando` (`grupo_fallback.py:797+`) — transição AGUARDANDO → FALLBACK_1_1
- `processar_entrada_lead_no_grupo` (chamado por webhook + polling) — AGUARDANDO/FALLBACK_1_1 → ATIVO
- `leads.py` (após `promote_admin` sucesso)

---

## 7. Build Order — Dependências entre features (Pergunta 6)

### 7a. Grafo de dependências

```
                ┌──────────────────────────────┐
                │ MEMB-01: Schema migration     │  ← FUNDAÇÃO (nada compila sem isso)
                │  grupo_membership table       │
                └──────────────┬────────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
  ┌────────────────┐  ┌────────────────┐  ┌─────────────────┐
  │ MEMB-02:       │  │ PROBE-CACHE-01:│  │ FSM-AUDIT-01:   │
  │ Webhook ADD    │  │ probe_cache.py │  │ guard monotonic │
  │ → record_      │  │ (standalone)   │  │ + audit log     │
  │   lead_entered │  │                │  │ (standalone)    │
  └────────┬───────┘  └───────┬────────┘  └────────┬────────┘
           │                  │                    │
           │                  │ usado por          │
           └──────┬───────────┘                    │
                  ▼                                │
       ┌──────────────────────────┐                │
       │ lead_in_group() function │                │
       │  (tabela → probe+cache)  │                │
       └──────────────┬───────────┘                │
                      │                            │
                      ▼                            │
       ┌──────────────────────────────┐            │
       │ PROBE-RETRY-01:              │            │
       │  schedule_probe_retry +      │            │
       │  _executar_probe_retry job   │            │
       │  (consome lead_in_group +    │            │
       │   probe_cache)               │            │
       └──────────────┬───────────────┘            │
                      │                            │
                      ▼                            │
       ┌──────────────────────────────┐            │
       │ MEMB-03/04 consumers:        │            │
       │  migrar ativar_fallback,     │◀───────────┘
       │  notif, aquec → lead_in_group│  audit log já ativo
       │  (NÃO mais probe direto)     │
       └──────────────┬───────────────┘
                      │
                      ▼
       ┌──────────────────────────────┐
       │ LEAVE-01:                    │
       │  Webhook REMOVE handler +    │
       │  record_lead_left            │
       └──────────────┬───────────────┘
                      │
                      ▼
       ┌──────────────────────────────┐
       │ LEAVE-02:                    │
       │  Notif pré-reunião/D-1       │
       │  detecta saiu_em → DM        │
       │  (depende de LEAVE-01 dados) │
       └──────────────┬───────────────┘
                      │
                      ▼
       ┌──────────────────────────────┐
       │ FSM-AUDIT-02:                │
       │  callers passam reason+caller│
       │  (refactor opcional;         │
       │   adicionar gradualmente)    │
       └──────────────┬───────────────┘
                      │
                      ▼
       ┌──────────────────────────────┐
       │ TEST-V2-G1..G5:              │
       │  testes regressão dos 5 casos│
       │  (depende de TUDO acima)     │
       └──────────────────────────────┘
```

### 7b. Build order recomendado para roadmapper (Fases 10-14)

| Fase | Ítens | Por que esta ordem? |
|---|---|---|
| **10** | MEMB-01 (schema) + MEMB-02 (webhook write ADD) + PROBE-CACHE-01 | Schema é fundação. Webhook write isoladamente já cria dados úteis (mesmo sem `lead_in_group()` consumir — só registra). Cache standalone, sem deps. |
| **11** | `lead_in_group()` + migrar `ativar_fallback_se_necessario` (3 paths de probe → 1 chamada) | `lead_in_group()` precisa de MEMB-02 já gerando dados. Migra os 3 callers internos de `grupo_fallback.py` (linhas 251, 311, 337) primeiro porque são auto-contidos. |
| **12** | PROBE-RETRY-01 + migrar callers com margem (`confirmacao_agendamento.py`, `_executar_timeout_grupo_aguardando`) | Retry depende de `lead_in_group()` + cache + APScheduler. Callers com margem ganham `schedule_retry_on_negative=True`. |
| **13** | LEAVE-01 + LEAVE-02 + FSM-AUDIT-01 (guard + audit insert) | LEAVE precisa de MEMB schema com `saiu_em`. FSM-AUDIT é refactor cirúrgico em `grupo_state.py` — pode ir em paralelo mas mais seguro depois das migrações estarem estáveis. |
| **14** | FSM-AUDIT-02 (refactor callers para passar reason/caller) + TEST-V2-G1..G5 + DOC-V2-G1 | Testes precisam de toda a infra. FSM-AUDIT-02 é cosmético/observabilidade — pode rolar incremental enquanto testes rodam. |

### 7c. Justificativas de ordem (trade-offs explícitos)

| Decisão de ordem | Trade-off | Por que escolhi esta |
|---|---|---|
| Schema (MEMB-01) ANTES de tudo | Custo: 1 dia bloqueado em migration + Supabase deploy. Benefício: nada compila sem schema. | Schema é dependência hard. RLS + indexes + UNIQUE constraint precisam estar em prod antes do webhook escrever. Migration 003 (073c93f) já mostrou padrão funcional. |
| PROBE-CACHE antes de PROBE-RETRY | Cache é standalone; retry depende de cache (cada retry invalida antes de chamar). | Inverter ordem cria janela de "retry hammered API" sem cache. |
| Migrar `ativar_fallback` ANTES de `confirmacao_agendamento`/`aquec` | `ativar_fallback` é o caller mais quente (1 vez por agendamento criado). Falha aqui é detectada em <24h. | Caller crítico primeiro = validação rápida do `lead_in_group()`. Aquec/notif são caudais de longo prazo, podem migrar depois. |
| LEAVE depois de ADD/probe/cache | LEAVE adiciona complexidade (FSM novo estado `LEFT_GROUP`, notif DM redirecionada). | Casos motivadores 08/06 são todos de **falsa ausência** (lead estava no grupo). Saída do lead é raro hoje. Resolver entrada primeiro elimina 80% dos casos. |
| FSM-AUDIT-01 (guard) standalone, FSM-AUDIT-02 (callers) depois | Guard ativo sem callers passando reason é OK (default `reason="legacy"`). Refactor de callers pode ser incremental. | Não bloqueia roadmap se FSM-AUDIT-02 escorregar. Guard imediato pega regressões. |
| Testes regressão na ÚLTIMA fase | Custo: testes só rodam end-to-end perto do fim. Benefício: testes pra arquitetura final, não pra mid-state. | Suite 13 testes do v2.1 (commit 6159af5) mostrou que escrever teste durante refactor cria churn. Melhor consolidar primeiro. |

---

## 8. Anti-patterns a evitar

### Anti-pattern 1: Polling de Evolution dentro do `lead_in_group()`
**Por quê ruim:** mascara a inversão "webhook-first". Probe deve ser último recurso, não rotina.
**Em vez:** `lead_in_group()` consulta tabela; só vai pro probe se row ausente E criação do grupo < 6min (janela de race do webhook).

### Anti-pattern 2: Cache global compartilhado entre testes
**Por quê ruim:** testes não-determinísticos. Test_A polui cache pra Test_B.
**Em vez:** Expor `probe_cache.clear()` ou usar fixture `pytest` que cria nova instância de `TTLCache` por teste.

### Anti-pattern 3: Escrever `grupo_membership` no caller de probe
**Por quê ruim:** dispersa lógica de materialização. Difícil rastrear quem escreveu o quê.
**Em vez:** SÓ `record_lead_entered` (webhook) e `lead_in_group()` step 4 (probe confirmou) escrevem. Caller nunca escreve direto.

### Anti-pattern 4: Aceitar timestamp `NOW()` server-side como autoridade
**Por quê ruim:** webhook re-entregue 5min depois sobrescreve dado mais novo se compararmos com `atualizado_em`.
**Em vez:** usar `data.messageTimestamp` do payload Evolution como `evento_ts`. Comparar `evento_ts > membership.atualizado_em` antes de UPSERT.

### Anti-pattern 5: Bypass do guard FSM com flag `force=True` em código de produção
**Por quê ruim:** quebra a invariante de monotonicidade silenciosamente.
**Em vez:** `force=True` SÓ em endpoint admin (`/admin/grupo/forcar-revalidacao`) com log explícito.

---

## 9. Considerações de escala

| Concern | Hoje (1 empresa) | 10 empresas | 100 empresas |
|---|---|---|---|
| Volume `grupo_membership` | ~30 rows/dia | ~300 rows/dia | ~3K rows/dia |
| Volume markers audit | ~150/dia | ~1.5K/dia | ~15K/dia (considerar pruning) |
| Cache hit ratio | Alto (poucos grupos) | Alto (TTL 5min cobre) | Pode precisar aumentar `maxsize=512`→4096 |
| Probe API calls | ~5/min pico | ~50/min | ~500/min (Evolution rate limit?) |
| APScheduler jobs concorrentes | ~10 ativos | ~100 ativos | ~1K (revisar `max_instances`) |

**Pivot points (quando reavaliar arquitetura):**
- Markers em `conversas` > 100K rows/empresa → considerar partition por mês ou move para tabela dedicada `audit_log`.
- Cache hit ratio < 50% (medir com counter) → aumentar TTL ou usar Redis compartilhado.
- Multi-worker Uvicorn (não single-instance) → cache in-memory inválido, **OBRIGATÓRIO Redis**.

---

## 10. NEW vs MODIFIED files

### NEW files

| Path | Conteúdo |
|---|---|
| `leadflow-backend/migrations/004_grupo_membership.sql` | Migration: tabela + indexes + RLS + grants |
| `leadflow-backend/app/services/grupo_membership.py` | `lead_in_group`, `record_lead_entered`, `record_lead_left`, `mark_left`, `schedule_probe_retry`, `_executar_probe_retry` |
| `leadflow-backend/app/services/probe_cache.py` | TTLCache singleton + `get/set/invalidate/invalidate_all_for_group` |
| `leadflow-backend/tests/test_grupo_membership.py` | Testes regressão TEST-V2-G1..G5 |
| `leadflow-backend/tests/test_probe_cache.py` | Testes unitários do cache |
| `leadflow-backend/tests/test_lead_in_group_decision.py` | Testes decision tree (tabela vs probe vs stale) |

### MODIFIED files

| Path | Mudanças |
|---|---|
| `leadflow-backend/app/routers/grupo_webhook.py` | Adicionar `record_lead_entered` em ADD; adicionar handler REMOVE; manter `_salvar_lead_lid` por compat |
| `leadflow-backend/app/services/grupo_state.py` | `set_grupo_state` ganha `reason`/`caller`/`force` kwargs + guard monotônico + insert audit; adicionar `STATE_LEFT_GROUP` constant |
| `leadflow-backend/app/services/grupo_fallback.py` | Substituir 6 chamadas a `verificar_lead_no_grupo` por `lead_in_group(...)` (linhas 251, 311, 337, 477, 624, 1173, 1256); adicionar `_handle_lead_left_group` (LEAVE-01) |
| `leadflow-backend/app/routers/confirmacao_agendamento.py` | Linha 291: usar `lead_in_group(..., schedule_retry_on_negative=True)`; detectar `saiu_em` → DM (LEAVE-02) |
| `leadflow-backend/app/routers/warmup_grupo.py` | Probe usage: usar `lead_in_group()` (síncrono, sem retry) |
| `leadflow-backend/app/routers/admin.py` | `forcar-revalidacao`: invalidate cache + probe direto + `record_lead_entered` se confirmar; `/admin/grupo/status` retorna `grupo_membership` row |
| `leadflow-backend/app/routers/leads.py` | Linha 123: `_probe_reuso` → `lead_in_group()` (mas mantém probe direto pra reuso porque é uma validação de "vivo agora") |
| `leadflow-backend/requirements.txt` ou `pyproject.toml` | Adicionar `cachetools>=5.3` (~30KB; já é transitive em supabase-py provavelmente) |
| `leadflow-backend/CLAUDE.md` ou `memory/` | DOC-V2-G1: criar `memory/grupo_membership_arquitetura.md` |

---

## 11. Sources

Codebase introspection (HIGH confidence):
- `c:/Projetos/Leadflow/.planning/PROJECT.md` (decisões v2.2 confirmadas)
- `c:/Projetos/Leadflow/.planning/STATE.md` (infra existente)
- `c:/Projetos/Leadflow/leadflow-backend/app/services/grupo_state.py` (FSM atual completo)
- `c:/Projetos/Leadflow/leadflow-backend/app/services/grupo_fallback.py` (entry point fallback, helpers de agendamento de jobs)
- `c:/Projetos/Leadflow/leadflow-backend/app/services/evolution.py` (probe síncrono)
- `c:/Projetos/Leadflow/leadflow-backend/app/routers/grupo_webhook.py` (handler ADD atual)
- `c:/Projetos/Leadflow/leadflow-backend/app/scheduler.py` (AsyncIOScheduler singleton)
- 11 callers de `verificar_lead_no_grupo` mapeados via grep
- 6 fixes paliativos 08/06 (commits 53bd05a, 07d7341, 96b72cc, 7e366bd, ae2b141, 0d55888) confirmam padrão "probe não-confiável"

Best practices verificadas (MEDIUM confidence — padrões já em uso no codebase, validados em prod):
- APScheduler `AsyncIOScheduler` + `replace_existing=True` para idempotência (já em `_agendar_*` linhas 670+ de grupo_fallback.py)
- Marker em `conversas` + UNIQUE constraint para claim atômico (padrão `_claim_marker` linha 157)
- `cachetools.TTLCache` é stdlib-ish (pacote estável, mantido, ~5MB) — alternativa seria implementar TTL manual com `dict + datetime` mas reinventa roda

---

*Generated: 2026-06-09 — Research para milestone v2.2 (Webhook-First grupo membership). Ordem de implementação validada contra grafo de dependências do codebase atual.*
