---
plan: 10-03
phase: 10-schema-3-paths-webhook-write-cache-standalone
title: Path 1 — webhook GROUP_PARTICIPANTS_UPDATE ADD escreve em grupo_membership
status: completed
completed_at: 2026-06-09T18:10:00-03:00
wave: 3
autonomous: true
commits:
  - hash: 31b7442
    message: "feat(10-03): Path 1 — UPSERT grupo_membership no webhook ADD (MEMB-02)"
    task: 1
requirements_addressed:
  - MEMB-02
key_files:
  created: []
  modified:
    - leadflow-backend/app/routers/grupo_webhook.py
decisions:
  - "instance_key = payload.get('instance') — instancia ORIGEM do evento, nao lookup atual (Pitfall 3)"
  - "UPSERT inserido APOS lookup empresa_id e ANTES do loop handlers v2.1 — garante escrita sempre que empresa_id e resolvido"
  - "try/except ja esta dentro do helper — nao adicionar segundo try/except no webhook (duplicaria logging)"
metrics:
  duration_minutes: 16
  tasks_completed: 2
  files_modified: 1
  lines_added: 50
  lines_removed: 0
---

## Objective Recap

Path 1 dos 3 paths de escrita v2.2: webhook `GROUP_PARTICIPANTS_UPDATE` com `action=add`
persiste cada participant em `grupo_membership` ANTES dos handlers v2.1 existentes.

Aditivo, não-regressivo — handlers v2.1 (`processar_entrada_lead_no_grupo`, `_salvar_lead_lid`,
heurística @lid, markers `GRUPO_AGUARDANDO_ENTRADA`) continuam executando depois do bloco MEMB-02.

## What Was Built

### Task 1: UPSERT Path 1 em `grupo_webhook.py` (commit `31b7442`)

**Arquivo modificado:** `leadflow-backend/app/routers/grupo_webhook.py` (+50 linhas, 0 removidas)

**Inserção 1 — import (linha 17):**
```python
# v2.2 MEMB-02: Path 1 write em grupo_membership (Fase 10)
from app.services.grupo_membership import upsert_grupo_membership, parse_evolution_timestamp
```

**Inserção 2 — bloco MEMB-02 após `print("[WEBHOOK-GRUPO] instancia=...")`, antes do loop existente:**

- `_evento_ts = parse_evolution_timestamp(data.get("messageTimestamp") or payload.get("date_time"))` — parser defensivo cobre epoch s/ms/ISO/None
- `_last_event_id` extraído de `data.key.id` → `data.id` → `payload.id` (fallback chain para idempotência adicional)
- `_instance_key_evento = payload.get("instance").strip()` — instância ORIGEM do evento (Pitfall 3: não usar lookup atual da empresa)
- Loop `for _tel_memb in telefones_entraram`: chama `upsert_grupo_membership(sb, ..., telefone=tel, lid=None, fonte='webhook_add')`
- Loop `for _lid_memb in lids_entraram`: chama `upsert_grupo_membership(sb, ..., telefone=None, lid=lid, fonte='webhook_add')`
- Helper tem try/except interno — exception nunca derruba o webhook handler

### Task 2: Validação ortogonal (sem alteração de código)

Todos os 7 greps de regressão passaram:

| Check | Esperado | Resultado |
|-------|----------|-----------|
| `from app.services.grupo_fallback import processar_entrada_lead_no_grupo` | >= 1 | 1 OK |
| `telefones_aguardando` | >= 2 | 5 OK |
| `_salvar_lead_lid` | >= 2 | 2 OK |
| `GRUPO_AGUARDANDO_ENTRADA:{grupo_jid}` | >= 2 | 2 OK |
| `GRUPO_FALLBACK_ATIVADO:{grupo_jid}` | 1 | 1 OK |
| `_i.lower() == instancia.lower()` | 1 | 1 OK |
| `@router.post("/agente/evolution/webhook/grupo")` | 1 | 1 OK |

Smoke test `parse_evolution_timestamp`: todos os 5 shapes cobertos — PARSE_TS OK.

`git diff --stat`: `1 file changed, 50 insertions(+)` — zero linhas removidas.

## Verification

- `wc -l grupo_webhook.py`: 227 (original) → 277 (patched) — +50 linhas, nenhuma removida
- `fonte='webhook_add'` aparece exatamente 2 vezes (1 por loop)
- `_instance_key_evento = (payload.get("instance")` — Pitfall 3 implementado corretamente
- AST parse: `ast.parse(src)` OK — sintaxe válida
- Diff puramente aditivo confirmado: `1 file changed, 50 insertions(+)`
- parse_evolution_timestamp smoke: epoch s (2024), epoch ms (2024), ISO (2024), None (datetime), garbage (datetime) — todos OK

## Non-Regression Confirmation

NÃO ALTERADOS (confirmados via grep post-patch):
- `processar_entrada_lead_no_grupo` — import + 3 chamadas intactas
- `_salvar_lead_lid` — def + chamada intactas
- Heurística @lid unique-aguardando (linhas 236-269) — preservada
- `GRUPO_AGUARDANDO_ENTRADA:{grupo_jid}` — ambos os paths de check preservados
- `GRUPO_FALLBACK_ATIVADO:{grupo_jid}` — compat legado preservado
- Case-insensitive empresa lookup (`_i.lower() == instancia.lower()`) — fix 21/05 preservado
- Rota `@router.post("/agente/evolution/webhook/grupo")` — inalterada
- Marker `GRUPO_LEAD_ENTROU_CRIACAO` (PROBE-BYPASS-01 commit 96b72cc) — não tocado (não está em grupo_webhook.py)
- Early return `if action != "add"` — LEAVE/REMOVE + Fase 13 preservado

## What This Enables

**Plans 04** (Path 2 — MESSAGES_UPSERT @lid capture) e **Plan 05** (healthcheck) podem agora
assumir que Path 1 está funcionando.

**Fase 11** (`lead_in_group()`) terá dados em `grupo_membership` preenchidos pelo webhook ADD
como fonte primária, antes mesmo de qualquer probe Evolution.

Logs esperados em prod após próximo webhook GROUP_PARTICIPANTS_UPDATE:
```
[WEBHOOK-GRUPO] instancia=... -> empresa_id=...
[MEMB-WRITE] OK empresa=... grupo=... tel=... fonte=webhook_add action=insert id=...
[WEBHOOK-GRUPO] ... entrou em ... — disparando handler
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — Path 1 writes to `grupo_membership` unconditionally when `empresa_id` is resolved.
No placeholder data, no hardcoded empty values introduced.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: T-10-09 (accepted) | grupo_webhook.py | POST falso com payload.instance de outra empresa — sem signature validation (Fase 10 OUT-OF-SCOPE per threat model). Mitigação parcial: instance fake retorna empresa_id='' e handler aborta linha 154 antes do bloco MEMB-02. |

## Self-Check: PASSED

- File exists: `leadflow-backend/app/routers/grupo_webhook.py` — FOUND
- Commit `31b7442` exists — FOUND (`git log` confirms)
- 7 orthogonality greps — ALL PASSED
- parse_evolution_timestamp smoke — PARSE_TS OK
- Diff purely additive (50 insertions, 0 deletions) — CONFIRMED
