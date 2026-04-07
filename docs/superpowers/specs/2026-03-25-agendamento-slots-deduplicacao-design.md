# Design Spec — Agendamento: Slots 3 Turnos + Deduplicação + Slots de Hoje

**Data:** 2026-03-25
**Arquivo principal backend:** `leadflow-backend/app/routers/agente.py`
**Arquivo calendar:** `leadflow-backend/app/services/google_calendar.py`

---

## Contexto

O agente IA (Bia) agenda sessões estratégicas via WhatsApp com leads qualificados. Três bugs foram identificados em produção:

1. A IA sugeria horários de hoje que já tinham passado (slots antes do horário atual)
2. "Super te entendo 💛" aparecia duas vezes na conversa com o lead
3. Os 3 slots (manhã/tarde/noite) às vezes não eram apresentados quando um turno não tinha vaga nos próximos 5 dias

---

## Bug 1 — Horários de hoje já passados

### Regra de negócio (atualizada)
Se o lead preenche o formulário hoje e ainda há horários disponíveis após o horário atual, a IA **deve** oferecer slots de hoje. Se não houver mais slots hoje, vai para o próximo dia útil.

A IA precisa saber o **horário exato atual** (não só a data) para filtrar corretamente.

### Causa raiz
Dois problemas independentes:

**a) `agente.py` — contexto injetado no LLM:**
O `_data_ctx` injeta apenas a data (`DATA DE HOJE: DD/MM/YYYY`) sem o horário atual. O LLM não sabe que são, por exemplo, 19h — pode sugerir "hoje às 8h" sem perceber que já passou.

**b) `agente.py` — defaults de `_expediente_encerrado`:**
O check `_expediente_encerrado` usa `fim_h=18, fim_m=30` em dois lugares (OpenAI path linhas ~341-342 e Gemini path linhas ~602-603). Deve ser `fim_h=20, fim_m=15`.

**c) `google_calendar.py` — buffer insuficiente para hoje:**
Quando `data_especifica` = hoje, o buffer mínimo é `agora + 15min`. Esse buffer é pequeno demais — o lead pode receber a mensagem e o slot já ter passado quando ele responder. Aumentar para `agora + 60min`.

### Fix

**`agente.py` — injetar hora atual no contexto do LLM (ambos OpenAI e Gemini):**
```python
# ANTES:
_data_ctx = f"\n\nDATA DE HOJE: {_hoje.strftime('%d/%m/%Y')}. Ano atual: {_hoje.year}."

# DEPOIS:
_agora_fmt = datetime.now(ZoneInfo(fuso)).strftime('%d/%m/%Y %H:%M')
_data_ctx = f"\n\nDATA E HORA ATUAL: {_agora_fmt}. Ano atual: {_hoje.year}. Só sugira horários de hoje se forem APÓS {_agora_fmt}."
```

**`agente.py` — dois callsites de `_expediente_encerrado`:**
- OpenAI path: `fim_h=18` → `fim_h=20`, `fim_m=30` → `fim_m=15`
- Gemini path: mesma correção (código duplicado)

**`google_calendar.py` — aumentar buffer de hoje:**
```python
# ANTES:
hoje + timedelta(minutes=15)

# DEPOIS:
hoje + timedelta(minutes=60)
```

### Regra
> Retornar slots de hoje somente se forem 60+ minutos após o horário atual. Se não houver, ir para próximo dia útil. A IA conhece a hora exata atual via contexto injetado.

---

## Bug 2 — "Super te entendo" duplicado

### Causa raiz
O código pré-LLM envia "Super te entendo 💛" e a mensagem de empatia via WhatsApp **sem salvar no DB** (`conversas`). O LLM, seguindo instruções do system prompt, inclui o texto novamente na resposta principal. `_super_te_entendo_ja_enviado` não detecta as mensagens pré-enviadas por não estarem no DB.

### Fix (Abordagem A — Salvar no DB + post-process)

**1. Salvar pré-LLM no DB:**
Após enviar cada mensagem pré-LLM, inserir em `conversas` como `role="assistant"`, com timestamps que **precedem** `agora_user` para manter a ordem correta do histórico:

```python
# Timestamps (exemplos):
agora_pre1 = (agora - timedelta(seconds=4)).isoformat()  # "Super te entendo 💛"
agora_pre2 = (agora - timedelta(seconds=3)).isoformat()  # empatia
agora_user = agora.isoformat()                            # mensagem do lead
agora_bot  = (agora + timedelta(seconds=1)).isoformat()  # resposta principal LLM
```

Inserir **2 rows separadas** em `conversas`:
- Row 1: `role="assistant"`, `conteudo="Super te entendo 💛"`, `criado_em=agora_pre1`
- Row 2: `role="assistant"`, `conteudo=<texto empatia>`, `criado_em=agora_pre2`

**2. Post-processing da resposta do LLM:**
Quando `_eh_passo3=True`, remover "Super te entendo" do início da resposta do LLM:

```python
if _eh_passo3:
    import re as _re_ste
    resposta = _re_ste.sub(
        r'(?i)super te entendo\s*💛?\s*[\n\r]*', '', resposta, count=1
    ).strip()
```

### Fluxo corrigido
```
_eh_passo3=True:
  → envia "Super te entendo 💛" via WhatsApp
  → envia empatia via WhatsApp
  → SALVA ambas no DB (role="assistant", timestamps antes de agora_user)
  → chama LLM
  → post-process: strip "Super te entendo" da resposta
  → envia resposta principal (só slots)
  → SALVA user + resposta no DB (timestamps agora_user / agora_bot)
```

### Regra
> "Super te entendo 💛" e empatia aparecem exatamente 1x por conversa, enviadas pré-LLM. O LLM não as repete.

---

## Bug 3 — Sempre 3 slots (manhã, tarde, noite) de dias potencialmente diferentes

### Causa raiz
A seleção atual faz **1 chamada** a `buscar_horarios_livres` e seleciona com `next()` o 1º slot de cada turno dos 8 retornados (janela 5 dias úteis). Se a agenda está ocupada num turno por 5 dias seguidos, esse turno fica vazio.

Esse código está **duplicado** em dois lugares:
- `_gerar_resposta_openai_com_agenda` linhas ~362-365
- `_gerar_resposta_gemini_com_agenda` linhas ~623-626

### Fix — Função auxiliar `_buscar_tres_slots()` em `agente.py`

**Algoritmo exato:**

```
Para cada turno em ["manha", "tarde", "noite"]:
  1. Chamar buscar_horarios_livres com dias=5
     (sem nome_dia, sem data_especifica, sem proxima_semana)
  2. Filtrar slots pelo turno:
     - manha: hora < 12
     - tarde: 12 <= hora < 17
     - noite: hora >= 17
  3. Se len(slots_turno) > 0 → pega slots_turno[0], break
  4. Se len(slots_turno) == 0 → chamar buscar_horarios_livres com dias=15
  5. Filtrar pelo turno novamente
  6. Se encontrou → pega slots_turno[0]
  7. Se não encontrou → turno retorna None (omitido da lista final)
Retornar lista de até 3 slots, cada um no formato "DD/MM/YYYY HH:MM"
```

**Localização:** função interna definida dentro de `_gerar_resposta_openai_com_agenda` e `_gerar_resposta_gemini_com_agenda` (ou extraída como helper async no topo do arquivo — preferível para evitar duplicação).

**Formato de retorno:** mantém o formato `"DD/MM/YYYY HH:MM"` idêntico ao atual — compatível com o código de geração de `slot_token` existente (`SLOT_YYYYMMDD_HHMM`).

**Performance:** até 6 chamadas à API do Google Calendar por turno LLM (2 por turno × 3 turnos). Na prática, será 3 chamadas na maioria dos casos (calendário com vagas nos próximos 5 dias). Aceitável para este contexto.

**Como ambos os paths (OpenAI e Gemini) adotam:**
Substituir os blocos de seleção de slots (linhas ~362-365 e ~623-626) pela chamada à nova função. Os cálculos de `linhas`, `token`, `display`, `_slots_out`, `_var_mapa` permanecem inalterados após obter a lista de 3 slots.

### Exemplo de resultado com dias diferentes
```
- 26/03 às 09:00  (manhã)      [slot_token: SLOT_20260326_0900]
- 27/03 às 14:00  (tarde)      [slot_token: SLOT_20260327_1400]
- 29/03 às 18:00  (noite)      [slot_token: SLOT_20260329_1800]
```

### Regra
> Os 3 slots podem ser de dias diferentes. Cada um exibe sua data. Extensão automática 5→15 dias por turno se necessário.

---

## Arquivos a modificar

| Arquivo | Mudanças |
|---|---|
| `google_calendar.py` | Bug 1c: aumentar buffer de hoje de 15min → 60min |
| `agente.py` | Bug 1a: injetar hora atual no `_data_ctx` (OpenAI e Gemini); Bug 1b: corrigir `_expediente_encerrado` defaults (2 callsites); Bug 2: salvar pré-LLM no DB + post-process strip; Bug 3: nova lógica de busca por turno (substitui código duplicado em OpenAI e Gemini paths) |

---

## Checklist de verificação

- [ ] `data_especifica` = hoje às 9h, agenda com slot às 11h → retorna slot de hoje às 11h ✓
- [ ] `data_especifica` = hoje às 19h, agenda com slot às 19h30 → slot descartado (< 60min), retorna amanhã
- [ ] LLM recebe `DATA E HORA ATUAL: 25/03/2026 19:00` no contexto → não sugere horários passados de hoje
- [ ] Agenda com tardes ocupadas por 5 dias → encontra tarde no dia 6–15
- [ ] Passo 3: lead recebe "Super te entendo" exatamente 1x
- [ ] DB após passo3: 2 rows `role="assistant"` pré-LLM com timestamps antes de `agora_user`
- [ ] `_super_te_entendo_ja_enviado` = True em turnos subsequentes (detecta pré-LLM salvo)
- [ ] [horario1]/[horario2]/[horario3] exibem datas diferentes quando necessário
- [ ] Remarcação: `buscar_tres_slots()` também chamada (não busca genérica)

---

## O que NÃO mudar

- System prompt (editado pelo usuário no frontend)
- Formato `slot_token`: `SLOT_YYYYMMDD_HHMM`
- Detecção de followup: `_lead_ja_interagiu`
- `_get_nested_ag` (suporte a chaves com "..." no final)
- Defaults de horário em `buscar_horarios_livres` e `_parse_hm`: `ini_h=8, ini_m=0, fim_h=20, fim_m=15` — **não alterar esses valores**. O Bug 1b alinha `_expediente_encerrado` para *usar* esses valores, não os muda.
