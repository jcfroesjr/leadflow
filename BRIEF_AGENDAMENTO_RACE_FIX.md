# BRIEF — Refator: Processamento Atômico de Mensagens do Lead

**Contexto:** Agente IA do Leadflow (Bia) recebe múltiplas mensagens em rápida sucessão de um mesmo lead e processa em paralelo, causando duplicação de respostas e estado inconsistente. Slot-pick falha porque o histórico contém múltiplas ofertas de slot (cada uma com horários diferentes — calendar é real-time).

---

## DEFEITOS OBSERVADOS (por caso real)

### Caso 1: Caca (5521982822554) — múltiplos "Sim" causam duplicação

**Mensagens do lead em 9 segundos:**
- 20:20:40 `Sim !`
- 20:20:46 `Sim`
- 20:20:49 `Correto!`
- + 1 áudio nesse intervalo

**Resposta do bot (13 mensagens em 7s):**
- Q1 (esperado)
- Q2 (esperado)
- "Super te entendo 💛" × **2** (duplicado)
- Empathy template × **2** (duplicado)
- Slots offer × **2** (DIFERENTES! Set A: 07/10:30, 08/16, 04/10. Set B: 07/15:30, 04/10, 05/13)
- Quando lead disse "Vai ser dia 4 às 10 da manhã" → bot agendou 07/05 15:30 (1º slot de Set B), não 04/05 10:00.

### Caso 2: Andressa (5541995937881)

LLM gerou 3 bullets sem chamar `buscar_horarios_livres`. SLOTS-RESCUE não populou `_slots_oferecidos`. Salvou mensagem sem `[SLOTS_TOKENS:...]`. Lead viu 3 horários inválidos.

### Caso 3: Jakeline (5543999614878)

LLM em vez de chamar tool, mandou "Estou com um probleminha técnico pra buscar os horários agora". ANTI-ANUNCIO regex não pegava esse padrão (corrigido depois mas sintoma de fragilidade).

### Caso 4: Áudio Whisper (recorrente)

Whisper transcreve "dia 4 às 10" como "4h25min às 10h" (alucinação). Regex de extração de hora não lida bem com pontuação/transcrição imperfeita.

### Caso 5: Q2 duplicada

Lead manda "Sim" (Q1 confirm), Q2 dispara. Lead manda "Sim !" 1s depois (mesma intenção mas msg id diferente). Q2 dispara DE NOVO. Race entre 2 webhooks do mesmo lead.

---

## CAUSA RAIZ ÚNICA

**FALTA DE TRAVA POR TELEFONE.** O webhook do agente (`/agente/evolution/webhook`) não serializa o processamento por número. N webhooks chegam em paralelo → N processamentos concorrentes lendo o mesmo `historico` (que ainda não foi atualizado pelas iterações anteriores) → cada um decide independentemente → estado divergente.

Sintomas derivados:
- Múltiplos slot offers (cada um com calendar diferente)
- Q2/Q1 duplicados
- Slot-pick falha porque "última msg com SLOTS_TOKENS" muda enquanto matching corre
- Empathy template enviada N vezes

---

## LÓGICA CORRETA (proposta)

### Princípio 1: Lock atômico por (empresa_id, telefone)

Ao receber webhook:
1. Tenta inserir marker `LOCK:{empresa_id}:{telefone}` em tabela com unique constraint
2. Se sucesso → tem o lock, processa
3. Se conflito (outro lock ativo) → enfileira marker `QUEUED:{empresa_id}:{telefone}:{msg_id}`, retorna 200 imediato
4. Ao terminar processamento, libera lock E processa próximo da queue se houver
5. Lock expira em 60s automaticamente (deadlock prevention)

**Resultado:** uma mensagem por vez por lead, ordenada por chegada.

### Princípio 2: SLOTS_TOKENS único por ciclo

Cada vez que slots são oferecidos, marca um `OFERTA_ATIVA` com timestamp. Só uma oferta ativa por vez. Tentativas de oferecer slots quando já há oferta ativa <2min → reusa a oferta atual.

### Princípio 3: Slot-pick determinístico

Quando lead responde no contexto de uma oferta:
1. Pega APENAS a OFERTA_ATIVA mais recente
2. Extrai todos números 1-31 da msg do lead
3. Cruza diretamente: `(day, hour) ambos nos números` → match
4. Exatamente 1 match → usa
5. >1 match ou 0 match → bot pergunta de novo (não chuta)

Idêntico ao que foi implementado em `c16aefc` mas com a garantia de que `_ultima_slots_content` é atomicamente o "currente ofertado", não "última de N".

### Princípio 4: Audio transcription tolerante a erros

Whisper pode trazer ruído. NÃO confiar 100% no texto transcrito pra extrair semantica. Usar regex como hint, mas SEMPRE cruzar com tokens. Se Whisper deu "4h25min", os números livres `[4, 25, 10]` ainda batem com slot `(4, 10)` se ambos existirem na oferta.

### Princípio 5: Dedup robusto de mensagens enviadas

Antes de enviar QUALQUER mensagem fixa (Q1, Q2, empathy, slots), checa DB last 30s para mesmo conteúdo. Se já existe → skip. (Já implementado em `_enviar_trava` mas só pra Q1/Q2 — estender pra empathy + slots).

---

## ARQUITETURA EXISTENTE (não revertir)

### O que JÁ funciona e NÃO mexer
- Qualificação Q1/Q2 fixa via `_q1_template` e `_q2_template`
- Tool calling Gemini/OpenAI com `criar_agendamento` e `buscar_horarios_livres`
- 4 camadas de defesa de slots: ANTI-ANUNCIO → RESCUE → FILLUP → ULTRA-FALLBACK
- SLOT-OVERRIDE: força slot_token correto se LLM ignorar INSTRUCAO
- Marker MSG_PROCESSED por id pra evitar reprocessar webhook duplicado da Evolution
- FOLLOWUP_AGENDA_START + scheduler de FUs
- nao_convertido após max_delay + atraso configurável (frontend)
- Fallback grupo→1-1 quando lead não entra no grupo

### Onde mexer (mínimo)
- `app/routers/agente.py` — adicionar lock no início de `_processar_webhook_evolution_inner`
- `app/db/` — nova tabela `processing_locks` ou usar `conversas` com markers
- Possivelmente novo módulo `app/services/lock.py`

### Tabelas envolvidas
- `conversas` (markers + msgs)
- `leads`
- `agendamentos`
- (nova?) `processing_locks` ou usar markers em `conversas`

---

## COMMITS DEPLOYADOS HOJE (que ficam)

- `e7a9a88` — audio HTTP 201 do Evolution
- `a2e236d` — detector de áudio amplo (viewOnce/ephemeral/messageType)
- `b85e7ef` — ULTRA-FALLBACK garante 3 slots
- `b982972` — ANTI-ANUNCIO regex extendido
- `8d3147d` — MENU-ENC/OPT-OUT/PAUSA-INDEF send antes do status
- `3264ee4` — Q2 dedup 30s (sintoma do problema raiz)
- `c16aefc` — slot-pick direto numeros vs tokens

Build atual em prod: `2026-05-03-slot-pick-direto-numeros-vs-tokens`

---

## CRITÉRIOS DE ACEITAÇÃO (Definition of Done)

1. Lead manda 3 "Sim" em 5 segundos → bot responde Q1 once, Q2 once, empathy once, slots once. Total: 4 mensagens de bot, não 12.
2. Áudio transcrito com ruído ("4h25min às 10h") → bot identifica corretamente o slot pretendido (cruzando com tokens disponíveis) ou pergunta clarificação.
3. Lead diz "dia 4 às 10" + slots disponíveis incluem (4, 10:00) → bot agenda no horário correto, não no primeiro do menu.
4. Múltiplos webhooks paralelos do mesmo lead → processados em ORDEM CHEGADA, não em paralelo.
5. Não regredir nenhum teste real existente (Welma, Juliana, Tatiana, Thaís, Priscila, etc — ver memórias `sessao_2026-04-25_agendamentos.md` e similares).

---

## MEMÓRIAS RELEVANTES (já em `.claude/memory/`)

- `agente_ia_fixes.md` — fluxo da Bia, regras
- `agendamento_config.md` — Google Calendar, slots
- `agendamento_fsm.md` — FSM de fases
- `confirmacao_fluxo.md` — confirmação grupo, @lid, reagendamento
- `sessao_2026-04-25_agendamentos.md` — 9 fixes anti-alucinação
- `sessao_2026-05-01_5fixes_agendamento.md` — slot validation, race pre-check, anti-anúncio
- `sessao_2026-05-02_fp_completion_fix.md` — FP recovery + nao_convertido
- `sessao_2026-05-03_sync_loop_e_slots_fillup.md` — variantes telefone BR + slots fill-up

## FRAGMENTOS DE CÓDIGO RELEVANTES

- `app/routers/agente.py:2779-` — `_processar_webhook_evolution_inner` (entry point)
- `app/routers/agente.py:4326-4470` — slot-pick logic (atual)
- `app/routers/agente.py:1020-1042` — SLOT-OVERRIDE (LLM corrigido)
- `app/routers/agente.py:5544-5705` — ANTI-ANUNCIO + RESCUE + FILLUP + ULTRA-FALLBACK
- `app/routers/sync_messages.py` — sync que pode re-entregar mensagens (causa loops históricos)

---

## PERGUNTAS ABERTAS

1. Lock em DB (Supabase) ou em memória do processo? Backend é single-instance hoje, mas pode escalar.
2. Como tratar locks órfãos se o processo morrer no meio? TTL 60s é suficiente?
3. Mensagens enfileiradas: processadas após release do lock OU descartadas (idempotência via MSG_PROCESSED)?
4. Race com SYNC: SYNC pode re-entregar msg antiga. Já tem MSG_PROCESSED check, mas precisa interagir corretamente com novo lock.
