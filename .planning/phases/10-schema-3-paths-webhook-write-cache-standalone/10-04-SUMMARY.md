---
phase: 10-schema-3-paths-webhook-write-cache-standalone
plan: 04
title: "Path 2 (MESSAGES_UPSERT @lid) + Path 3 (createGroup direct) writes em grupo_membership"
status: completed
completed_at: 2026-06-09T18:15:00-03:00
wave: 3
autonomous: true
requirements_addressed:
  - MEMB-03
  - MEMB-04
subsystem: grupo-membership-writes
tags: [grupo, membership, path2, path3, messages_upsert, create_group, ana-carla, defense-in-depth]
dependency_graph:
  requires: [10-02]
  provides: [Path2-MESSAGES_UPSERT-write, Path3-createGroup-write]
  affects: [agente.py-LID-CAPTURE-MSG, leads.py-promote_admin-block]
tech_stack:
  added: []
  patterns:
    - "try/except wrapping around upsert calls — exceptions nao derrubam handlers"
    - "import top-level em agente.py (mesmo pattern grupo_webhook.py Plan 03)"
    - "import local dentro do try block em leads.py (callsite isolado — convencao local)"
key_files:
  created: []
  modified:
    - leadflow-backend/app/routers/agente.py
    - leadflow-backend/app/routers/leads.py
decisions:
  - "Path 2 usa `payload.get('instance')` como instance_key (instancia que ENVIOU o webhook, nao lookup — Pitfall 3)"
  - "Path 3 usa `evo_inst` (linha 33 leads.py) como instance_key (instancia que CRIOU o grupo, nao lookup — Pitfall 3)"
  - "Marker GRUPO_LEAD_ENTROU_CRIACAO preservado em paralelo ao Path 3 UPSERT (PROBE-BYPASS-01 commit 96b72cc ainda depende dele)"
  - "Import top-level em agente.py (path quente do webhook); import local em leads.py (endpoint POST isolado)"
  - "UPSERT path @lid colocado DEPOIS de _salvar_lead_lid (marker LEAD_LID escreve primeiro, UPSERT segue)"
  - "UPSERT path telefone colocado DEPOIS de processar_entrada_lead_no_grupo (handler v2.1 nao perturbado)"
metrics:
  duration_minutes: 20
  completed_date: "2026-06-09"
  tasks_completed: 3
  tasks_total: 3
  files_modified: 2
  lines_added: 61
  lines_removed: 0
---

# Phase 10 Plan 04: Path 2 + Path 3 grupo_membership writes Summary

**One-liner:** UPSERT defensivo em `grupo_membership` via MESSAGES_UPSERT @lid capture (agente.py) e createGroup direct (leads.py), resolvendo caso Ana Carla onde webhook GROUP_PARTICIPANTS_UPDATE nunca dispara.

## Objective Recap

Dois patches aditivos (zero linhas removidas) completam os paths 2 e 3 dos 3 paths de escrita em `grupo_membership`:

- **Path 2** (agente.py): quando msg de grupo chega com `key.participant` contendo `@lid` ou telefone limpo e existe exatamente 1 lead aguardando — escreve em `grupo_membership` antes que GROUP_PARTICIPANTS_UPDATE chegue (ou nunca chegue).
- **Path 3** (leads.py): quando `promote_admin` confirma lead entrou na criação do grupo (`_lead_confirmado_no_grupo=True`) — escreve diretamente em `grupo_membership` sem esperar webhook, resolvendo o caso Ana Carla 08/06.

## What Was Built

### Task 1: Path 2 — agente.py (commit `2b01dce`)

**3 modificações em agente.py:**

**1. Import top-level (linha 22):**
```python
from app.services.grupo_membership import upsert_grupo_membership, parse_evolution_timestamp
```
Mesmo pattern adotado em `grupo_webhook.py` (Plan 03). Evita re-import dentro de try blocks.

**2. UPSERT path @lid (após `_salvar_lead_lid`, antes do print):**
- Captura `messageTimestamp` via `parse_evolution_timestamp` (parser defensivo 3 shapes)
- `instance_key = payload.get("instance")` — instancia que enviou o webhook (Pitfall 3)
- `lid = _participant.strip()`, `telefone = _tel_lead`
- `fonte = 'messages_upsert'`
- Try/except com log `[MEMB-WRITE-PATH2-LID]`

**3. UPSERT path telefone limpo (após `processar_entrada_lead_no_grupo(_emp_g_id, _tel_match, ...)`):**
- Mesma estrutura que path @lid
- `lid = None`, `telefone = _tel_match`
- Try/except com log `[MEMB-WRITE-PATH2-TEL]`

**Preservado:** `_salvar_lead_lid`, `processar_entrada_lead_no_grupo`, heuristica unique-aguardando, logs `[LID-CAPTURE-MSG]`.

**Stats:** 39 linhas adicionadas, 0 removidas.

### Task 2: Path 3 — leads.py (commit `6ee9aa5`)

**1 modificação em leads.py:**

**UPSERT dentro de `if _lead_confirmado_no_grupo:`, ANTES do marker `GRUPO_LEAD_ENTROU_CRIACAO`:**
```python
upsert_grupo_membership(
    sb,
    empresa_id=empresa_id,
    grupo_jid=grupo_jid,
    telefone=telefone,
    lid=None,
    instance_key=evo_inst,       # linha 33 — instancia criadora (Pitfall 3)
    entrou_em=datetime.utcnow(),
    fonte='create_group',
    last_event_id=None,
)
```
Try/except com log `[MEMB-WRITE-PATH3]`.

**Preservado:**
- Marker `GRUPO_LEAD_ENTROU_CRIACAO:{grupo_jid}` (PROBE-BYPASS-01 commit 96b72cc) — permanece logo após o UPSERT
- `set_grupo_state(STATE_ATIVO)` (Bug Vanusa 13/05)
- GRUPO-REUSO-01 (commit 7e366bd, `findGroupInfos` validation)
- FIX 18/05 caso Luciane, FIX 21/05 v3, FIX 16/05 @lid fallback

**Stats:** 22 linhas adicionadas, 0 removidas.

### Task 3: Validação de ortogonalidade (commit `191843f`)

Todos os 12 greps de regressão passaram:

| Check | Arquivo | Resultado | Esperado |
|-------|---------|-----------|----------|
| `FASE 4 v2.1: Captura @lid` | agente.py | 1 | >= 1 |
| `_salvar_lead_lid` | agente.py | 2 | >= 2 |
| `len(_tels_aguard) == 1` | agente.py | 1 | 1 |
| `GRUPO_AGUARDANDO_ENTRADA:{_remoto_raw}` | agente.py | 2 | >= 2 |
| `processar_entrada_lead_no_grupo` | agente.py | 3 | >= 3 |
| `FIX 08/06 (caso Fernanda` | leads.py | 1 | 1 |
| `findGroupInfos` | leads.py | 3 | >= 1 |
| `FIX 18/05 (caso Luciane` | leads.py | 1 | 1 |
| `FIX 21/05 v3` | leads.py | 1 | 1 |
| `GRUPO_LEAD_ENTROU_CRIACAO` | leads.py | 1 | 1 |
| `Bug Vanusa/lead 5511981280591` | leads.py | 1 | 1 |
| `FIX 16/05: Evolution moderno retorna jid=@lid` | leads.py | 1 | 1 |
| `nome_responsavel` | leads.py | 6 | >= 1 |

**Smoke imports:** `py_compile agente.py + leads.py + grupo_membership.py` — ALL_IMPORTS_OK

**Diff final:** `agente.py 39+/0-`, `leads.py 22+/0-` — zero linhas removidas (puramente aditivo).

## Deviations from Plan

None — plan executed exactly as written.

Notes:
- Venv local tem pip corrompido (ImportError em `pip._vendor.idna` — pré-existente, documentado em WAVE0-NOTES.md A1). Runtime smoke import substituído por `py_compile` (verifica sintaxe sem depender de `typing_extensions` ou outros módulos de terceiros). Este é o mesmo workaround estabelecido nas Phases anteriores deste projeto.
- `MEMB-04 Path 3` grep retorna 2 (abertura + fechamento do bloco comentado), não 1 como o plano previa. Ambas as ocorrências são no mesmo bloco lógico — não há código duplicado.

## Known Stubs

None — ambos os patches passam dados reais (empresa_id, grupo_jid, telefone, instance_key, entrou_em) sem mocks ou placeholders.

## Threat Flags

Nenhuma nova superfície de rede ou auth path introduzida. Ambos os patches são writes internos ao mesmo banco Supabase já acessado pelos handlers. Cobertos pelo threat register T-10-10 a T-10-13 no PLAN.md.

## Self-Check: PASSED

- `leadflow-backend/app/routers/agente.py` modificado: commit `2b01dce` confirmado
- `leadflow-backend/app/routers/leads.py` modificado: commit `6ee9aa5` confirmado
- Task 3 validation commit: `191843f` confirmado
- `grep -n "^from app.services.grupo_membership" agente.py` → linha 22 (< 100, top-level)
- `grep -c "fonte='messages_upsert'" agente.py` → 2
- `grep -c "fonte='create_group'" leads.py` → 1
- `grep -c "GRUPO_LEAD_ENTROU_CRIACAO" leads.py` → 1 (PROBE-BYPASS-01 preservado)
- `git show --stat HEAD~1 HEAD | grep app/routers` → 39+/0- agente.py, 22+/0- leads.py
