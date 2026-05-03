# ANÁLISE DETALHADA DE DEFEITOS — Agente IA Leadflow

**Data:** 2026-05-03
**Build atual em prod:** `2026-05-03-slot-pick-direto-numeros-vs-tokens`
**Autor:** Sessão de debug intensiva 03/05 (8h de iteração)

---

## SUMÁRIO EXECUTIVO

O agente IA do Leadflow (Bia) está em estado funcional para casos isolados mas **falha sistematicamente** quando:
1. Lead manda 2+ mensagens em <10 segundos (Q1+Q2 duplicados, slots duplicados)
2. Lead manda áudio (Whisper transcreve com ruído, regex falha)
3. Lead reescolhe horário fora dos slots oferecidos
4. Múltiplos sets de SLOTS_TOKENS no histórico (slot-pick não sabe qual usar)
5. LLM hallucina bullets sem chamar tool

**Root cause comum:** ausência de lock atômico por (empresa_id, telefone). Webhooks paralelos compartilham o mesmo `historico` lido do DB sem ordenação.

---

## DEFEITO 1 — Race condition em mensagens consecutivas

### Caso real: Caca (5521982822554), 03/05 17:20

**Sequência de mensagens do lead em 9 segundos:**
```
20:20:40.123 user "Sim !"      (msg id A52577AA)
20:20:40-46  user [audio]
20:20:46.789 user "Sim"        (msg id A5B9A5DA)
20:20:49.456 user "Correto!"   (msg id A5A0B343)
```

**Sequência de mensagens do bot (13 mensagens em 7 segundos):**
```
20:20:42 assistant "Vi também que você comentou..." (Q2 trigger)
20:20:54 assistant "Super te entendo 💛"           ← #1
20:20:55 assistant "Baseado nisso tudo..."         ← empathy #1
20:20:58 assistant "Super te entendo 💛"           ← #2 DUPLICADO
20:20:59 assistant "Baseado nisso tudo..."         ← empathy #2 DUPLICADO
20:21:02 assistant "Tem horário disponível: • 07/05 10h30 • 08/05 16h • 04/05 10:00..." ← slots SET A
20:21:06 assistant "Tem horário disponível: • 07/05 15h30 • 04/05 10:00 • 05/05 13:00..." ← slots SET B (DIFERENTES!)
20:21:35 user "Vai ser dia 4 às 10 da manhã."
20:21:42 assistant "Marcadinho!"
20:21:44 sistema EVENTO_ID:...|DATA:07/05/2026 às 15:30   ← AGENDOU NO SLOT ERRADO
```

### Análise

- O webhook do agente recebeu 4+ mensagens em paralelo
- Cada uma fez fetch do histórico no DB (historico não inclui as respostas concorrentes)
- Cada uma decidiu independentemente: enviar empathy, buscar slots, oferecer
- Resultado: 2 empathies + 2 sets de slots
- Cada `buscar_horarios_livres` foi feito em momentos diferentes → calendar retornou slots diferentes (calendar é real-time)
- Quando lead respondeu "dia 4 às 10", `_ultima_slots_content` é o LAST do histórico = Set B
- Slot-pick direto encontrou (4, 10:00) em Set B mas ainda assim agendou no primeiro slot

### Por que o slot-pick falhou mesmo com a lógica nova

Hipóteses (sem logs de produção em mãos):
- INSTRUÇÃO foi injetada mas LLM ignorou
- OVERRIDE no tool call (linha 1031) deveria ter pegado mas talvez não rodou
- Ou Set B foi modificado entre o slot-pick e o tool call (race)

---

## DEFEITO 2 — LLM hallucina bullets sem chamar tool

### Caso real: Andressa (5541995937881), 03/05 14:32

**Bot respondeu (sem tool call):**
```
Entendi totalmente, Andressa 💛 Essa dúvida é super comum...
A Rejane Leal é especialista justamente...

Tem horário disponível:
• 04/05 (segunda) às 16h
• 05/05 (terça) às 10h
• 06/05 (quarta) às 14h

Qual desses você prefere? 😊
```

**O que está salvo no DB:**
- Mensagem assistant **SEM** sufixo `[SLOTS_TOKENS:...]` → `_slots_oferecidos` ficou empty na hora do save

### Análise

- LLM hallucinou os 3 bullets sem chamar `buscar_horarios_livres`
- ANTI-ANUNCIO regex não bateu (texto não tem "vou conferir"/"deixa eu ver")
- SLOTS-RESCUE deveria ter capturado os bullets e validado contra calendar (FreeBusy), mas não há nenhum log `[SLOTS-RESCUE]` para essa lead → RESCUE silenciosamente não rodou
- `_slots_oferecidos` ficou empty → save sem `[SLOTS_TOKENS:]`
- Lead quando responder vai ter problema (tokens não existem para o LLM matchar)

### Causa provável

- `if not _slots_oferecidos and resposta` — se já havia SLOTS_TOKENS de turno anterior em `_slots_oferecidos`, RESCUE não roda
- Ou exception silenciosa no try/except de RESCUE

---

## DEFEITO 3 — Whisper transcrição imperfeita quebra slot-pick

### Caso real: Caca (5521982822554), 03/05 16:24

**Lead falou áudio:** "dia 4 às 10" (provável intenção)
**Whisper transcreveu:** `"Eu queria 4h25min às 10h da manhã."`

### Como o sistema processou (build deployado naquele momento):

1. Hour regex 1 `(\d{1,2})[h:](\d{0,2})` matched `4h25` → `_h_l2 = 4`, `_m_l2 = 25` ❌
2. Day regex falhou (sem prefixo "dia" pra "4")
3. Token matching: nenhum slot tem hora 4:25 → `_time_matches = []`
4. INSTRUÇÃO não injetada
5. LLM pegou primeiro slot do menu (07/05 10:30)
6. Bot agendou em 07/05 10:30 (errado)

### Fix tentado (commit `c16aefc`, deployado): direct matching

```python
nums = [4, 25, 10]  # extraídos por (?<!\d)(\d{1,2})(?!\d)
tokens_disp = [(7, 10, 30), (8, 18, 0), (4, 10, 0)]
hits = [(4, 10, 0)]  # day=4 in nums + hour=10 in nums
```

→ Match único, INSTRUÇÃO injetada com SLOT_20260504_1000.

**Validado localmente.** Mas em produção (após redeploy) ainda agendou errado em outro caso (Defeito 1) — provavelmente porque RACE entre múltiplas mensagens fez o histórico ter MÚLTIPLOS sets de SLOTS_TOKENS.

---

## DEFEITO 4 — Múltiplos sets de SLOTS_TOKENS no histórico

### Como acontece

1. Lead manda Q2-confirm
2. Webhook A inicia processamento → vai pra passo3 → busca slots → oferece Set A
3. Lead manda outra msg simultaneamente (audio, Sim, Correto)
4. Webhook B inicia processamento → também vai pra passo3 → busca slots (calendar mudou ligeiramente) → oferece Set B
5. Histórico agora tem 2 sets diferentes

### Quando lead responde escolhendo

- `_ultima_bia_com_slots` pega o LAST (Set B em ordem cronológica)
- Slot-pick busca em Set B
- Mas LLM no tool call pode ter visto Set A no contexto e usar slot daquele
- Inconsistência

### O agendamento errado

Caca's case: Set B tinha (07/15:30, 04/10, 05/13). Bot escolheu 07/15:30 — primeiro slot de Set B. Isso sugere que LLM ignorou INSTRUCAO (se foi injetada) e pegou o primeiro do menu visível.

---

## DEFEITO 5 — Q2 duplicada quando lead manda 2 "Sim"

### Caso real: Caca (build antes do dedup)

```
14:14:53 user "Sim"          → bot processa, fase=q1_enviado
14:14:55 bot Q2 enviada
14:14:56 user "Sim !"        → bot processa, fase ainda q1_enviado (race!)
14:14:57 bot Q2 enviada DUPLICADA
```

### Fix (commit `3264ee4`, deployado)

Adicionado dedup no `_enviar_trava`:
- Antes de enviar Q1/Q2, query DB pra mensagem assistant idêntica nos últimos 30s
- Se existe → aborta

**Mas isso só cobre Q1/Q2 (templates fixos).** Não cobre empathy + slots, que vão por path diferente (passo3 LLM).

---

## DEFEITO 6 — SYNC re-entrega mensagens antigas

### Comportamento

`sync_messages.py` roda a cada 5min. Busca em Evolution API mensagens da última hora. Compara com DB. Se faltar → reprocessa via webhook local.

### Bug histórico (corrigido, build `79331b7`)

SYNC consultava DB com telefone em formato **12 dígitos** (`554797089796`), mas agente salvava em **13 dígitos** (`5547997089796`). Lookup nunca achava → marcava como "faltante" → reprocessava em loop infinito.

### Fix aplicado

`_variantes_telefone_br()` retorna ambos formatos. SYNC agora usa `.in_("telefone", variantes)`.

### Bug residual

Mesmo com fix, SYNC pode re-entregar mensagens antigas que coincidentemente **coincidem com nova interação**. Exemplo: cleanup deletou conversas. Webhook fresh cria lead. SYNC vê msg antiga "Sim" do Evolution buffer. Reprocessa contra novo lead. Confusão.

---

## DEFEITO 7 — Áudio não detectado

### Casos reais: Magda (5524999530908), Jakeline (5543999614878)

Áudio enviado pelo lead. Bot ignorou com marker `MSG_IGNORED:sem texto`.

### Causa

Detector antigo só checava `message.audioMessage` ou `message.pttMessage` direto. Evolution v2 às vezes embrulha em `viewOnceMessage`, `ephemeralMessage`, ou usa campo top-level `messageType`.

### Fix (commit `a2e236d`)

Detector com 4 paths:
1. Direto: `audioMessage` / `pttMessage`
2. Wrapped: `viewOnceMessage`, `viewOnceMessageV2`, `ephemeralMessage`, `deviceSentMessage`
3. Top-level: `data.messageType` == "audioMessage"/"pttMessage"
4. `documentMessage` com mimetype audio/*

Plus log `[WEBHOOK-NOTEXT]` com keys do payload pra debug futuro.

### Bug adicional encontrado (commit `e7a9a88`)

Evolution `getBase64FromMediaMessage` retorna **HTTP 201** (Created), mas código só aceitava 200. Áudio era baixado com sucesso mas rejeitado como erro. Whisper nunca rodava. Fix: aceitar 200 OU 201.

---

## DEFEITO 8 — ANTI-ANUNCIO regex incompleto

### Caso real: Jakeline

LLM em vez de chamar `buscar_horarios_livres`, escreveu:
```
"Estou com um probleminha técnico pra buscar os horários agora,
mas já já te trago as opções, tá bom? Vou te avisando por aqui!"
"Ops, caiu aqui um errinho técnico rapidinho..."
```

### Como ANTI-ANUNCIO deveria pegar

Regex extenso que detecta padrões "vou já buscar", "deixa eu conferir", "errinho na busca", etc → força sync `buscar_horarios_livres` → injeta bullets reais.

### Bug

Regex não cobria "probleminha técnico", "errinho técnico", "fico por aqui", "vou te avisando", "em instantes". LLM fugiu via essas frases.

### Fix (commit `b982972`, deployado)

Regex extendido com novos padrões. Validado localmente.

---

## DEFEITO 9 — Slot offer sem SLOTS_TOKENS

### Como acontece

LLM sai do trilho e escreve bullets sem chamar tool. SLOTS-RESCUE devia capturar mas:
- Se já há `_slots_oferecidos` populado por outra coisa, RESCUE skip
- Se exception, swallow silently
- Se LLM escreve em formato que regex não pega

### Fix em camadas (todos deployados)

1. **SLOTS-RESCUE** — extrai bullets do texto, valida via FreeBusy, gera tokens
2. **SLOTS-FILLUP** — se RESCUE achou 1-2, busca calendar pra completar até 3
3. **ULTRA-FALLBACK** — se TUDO falhou, busca calendar do zero e substitui resposta

### Bug residual

Mesmo com 3 camadas, se ANTI-ANUNCIO + RESCUE + FILLUP + ULTRA-FALLBACK silenciosamente não rodarem (exception swallowed, condições falsas), `_slots_oferecidos` fica empty e save vai sem [SLOTS_TOKENS:].

---

## DEFEITO 10 — `nao_convertido` marcado sem despedida

### Caso real: Ariélle (5542999425618)

Lead respondeu "2" ao menu de encerramento ("Sua prioridade mudou / Sem tempo / Continuar como está"). Bot marcou `status=nao_convertido` mas NUNCA enviou mensagem de despedida.

### Causa raiz

`NameError: name 'timedelta' is not defined` dentro do try/except do MENU-ENC. Status mudou ANTES do envio. Try/except outer engoliu o erro silenciosamente.

### Fix (commit `8d3147d`, deployado)

1. `timedelta` adicionado ao import top-level
2. Reordenado: send_text PRIMEIRO, status MUDA SÓ APÓS sucesso
3. Mesmo padrão aplicado a OPT-OUT e PAUSA-INDEF

---

## DEFEITO 11 — FP completion baixa (sequência interrompida)

### Caso real: 139 leads da Rejane analisados

- 1 lead (0.7%) recebeu todos os 11 FPs
- 27 leads pararam em idx 9 (faltou só último)
- 22 leads receberam 10 FPs

### Causa raiz

1. Recovery cutoff de 7d não cobria sequência de 8d
2. Política overdue=PULA descartava qualquer FP overdue mesmo por minutos

### Fix (commits `79dc6ca`, `a748ebd`)

1. Cutoff dinâmico por empresa (max delay + 72h buffer)
2. Tolerância overdue 48h (reagenda em vez de pular)
3. `nao_convertido` time-based dedicado (independente de envio do último FP)
4. Endpoint `/retomar-stuck` pra recovery em massa

### Status

112 leads retomados manualmente. Todos os 4 fixes deployados.

---

## CAUSA RAIZ ÚNICA

**LACK OF ATOMIC PROCESSING.**

O webhook do agente é stateless e processa mensagens em paralelo. Sem lock por (empresa_id, telefone), múltiplas requests do mesmo lead correm em paralelo lendo histórico defasado. Resultado:
- Estado divergente
- Mensagens duplicadas
- Slot offers múltiplos
- Q1/Q2 duplicados

Todos os outros defeitos (slot-pick falha, dedup empathy, etc) são SINTOMAS desse problema raiz. Os 30+ commits desta sessão (em 8 horas) foram band-aids que mitigaram mas não resolveram.

---

## SOLUÇÃO PROPOSTA — ARQUITETURA

### Componente 1: Lock Atômico

Tabela nova `processing_locks`:
```sql
CREATE TABLE processing_locks (
  empresa_id UUID NOT NULL,
  telefone TEXT NOT NULL,
  msg_id TEXT NOT NULL,
  acquired_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (empresa_id, telefone)
);
```

Webhook handler:
```python
async def webhook_handler(payload):
    msg_id = extract_msg_id(payload)
    empresa_id, telefone = resolve(payload)
    lock_key = (empresa_id, telefone)

    # Tenta adquirir lock atômico (insert com unique constraint)
    try:
        sb.table("processing_locks").insert({
            "empresa_id": empresa_id,
            "telefone": telefone,
            "msg_id": msg_id,
            "expires_at": now + timedelta(seconds=60),
        }).execute()
        # Sucesso — temos o lock
    except UniqueConstraintViolation:
        # Outro processamento ativo — enfileira via marker
        sb.table("conversas").insert({
            "empresa_id": empresa_id,
            "telefone": telefone,
            "role": "sistema",
            "conteudo": f"QUEUED:{msg_id}",
        }).execute()
        return {"ok": True, "queued": True}

    try:
        await processar_mensagem(payload)
    finally:
        # Libera lock
        sb.table("processing_locks").delete().eq("empresa_id", empresa_id).eq("telefone", telefone).execute()
        # Processa próximo da queue se houver
        await processar_queue(empresa_id, telefone)
```

### Componente 2: Single Slot Offer Per Cycle

Ao oferecer slots, marca `OFERTA_ATIVA:{timestamp}`. Próximas tentativas em <2min reusam.

### Componente 3: Slot-Pick Determinístico (já implementado em c16aefc)

Direct matching nums vs tokens. Se 1 hit → usa, 0 ou >1 → pergunta.

### Componente 4: Dedup Universal

Antes de QUALQUER send, query DB last 30s para conteúdo idêntico → skip. Aplicar em:
- Q1/Q2 templates
- Empathy template
- Slot offer
- "Marcadinho!" agendamento confirm

---

## PLANO DE TESTES (acceptance)

### T1: Race condition resolvida
Lead manda 3 "Sim" em 5 segundos.
**Esperado:** 1 Q2 enviada, 1 empathy, 1 slot offer. Total 3 msgs do bot, não 9.

### T2: Audio com Whisper imperfeito
Lead manda áudio que Whisper transcreve com alucinação ("4h25min às 10h").
**Esperado:** Bot identifica 04/05 10:00 ou pergunta clarificação.

### T3: Múltiplas mensagens em segundos
Lead manda Q1-confirm + texto + audio em 4 segundos.
**Esperado:** Bot processa em ordem chegada, sem duplicação. Cada msg tem 1 resposta.

### T4: Slot-pick correto
Lead diz "dia 4 às 10". Slots oferecidos incluem (4, 10:00).
**Esperado:** Bot agenda no horário correto (não primeiro do menu).

### T5: Não regredir Q1/Q2/empathy
Lead novo. Q1 → Sim. Q2 → Sim. Empathy + slots.
**Esperado:** Fluxo padrão funciona, sem regressão.

### T6: SYNC não reprocessa antigas
Cleanup. Webhook novo. SYNC roda.
**Esperado:** SYNC não acha "missing" porque variantes telefone funcionam.

### T7: nao_convertido com despedida
Lead responde "2" ao menu de encerramento.
**Esperado:** Bot envia despedida ANTES de mudar status. Se send falhar, status NÃO muda.

### T8: FP completion 100%
Lead novo qualificado. Aguarda 8 dias sem responder.
**Esperado:** Recebe TODOS os 11 FPs. Marcado `nao_convertido` em start + max_delay + atraso configurável.

---

## ARQUIVOS RELEVANTES

### Backend
- `app/routers/agente.py` — webhook handler, slot-pick, ANTI-ANUNCIO, RESCUE, FILLUP, ULTRA-FALLBACK
- `app/routers/sync_messages.py` — sync periódico (causa de loops históricos)
- `app/routers/followup_agenda.py` — FP scheduler, recovery, retomar-stuck
- `app/routers/leads.py` — criação grupo, agendamento
- `app/services/google_calendar.py` — buscar_horarios_livres
- `app/services/evolution.py` — Evolution API client
- `app/services/fsm_agendamento.py` — FSM de fases

### Frontend
- `src/modules/agenda/AgendaPage.tsx` — main config
- `src/modules/agenda/AquecimentoEditor.tsx` — config aquec (com auto-save recente)
- `src/modules/agenda/followups/FollowupEditor.tsx` — config FUs
- `src/modules/agenda/DelayPicker.tsx` — picker reutilizável

### Memórias (`.claude/projects/.../memory/`)
- `agente_ia_fixes.md` — fluxo Bia
- `agendamento_config.md` — Google Calendar
- `agendamento_fsm.md` — FSM
- `confirmacao_fluxo.md` — confirmação grupo, @lid
- `sessao_2026-04-25_agendamentos.md` — 9 fixes anti-alucinação
- `sessao_2026-05-01_5fixes_agendamento.md` — slot validation
- `sessao_2026-05-02_fp_completion_fix.md` — FP recovery
- `sessao_2026-05-03_sync_loop_e_slots_fillup.md` — variantes telefone

---

## COMMITS DA SESSÃO 03/05 (cronológico)

```
e7a9a88 fix(audio): aceita HTTP 200 OU 201 do Evolution
a2e236d fix(audio): detector ampliado (viewOnce/ephemeral/messageType)
b85e7ef fix(slots): ULTRA-FALLBACK garante 3 slots reais
b982972 fix(anti-anuncio): probleminha tecnico/errinho tecnico + reorders
8d3147d fix(menu-enc): import timedelta + send antes de status
3264ee4 fix(q2): dedup race condition 30s
cce4591 fix(slot-pick): hora 'às NN' prioritario
9acbe42 fix(slot-pick): bloqueia tool quando ambiguo
c16aefc fix(slot-pick): direct matching nums vs tokens
abb9168 fix(aquec): auto-persist no DB (frontend)
```

---

## RECOMENDAÇÃO FINAL

Não tentar mais fixes pontuais. **Refator com lock atômico** é o caminho. Os 10 commits desta sessão são band-aids sobre band-aids — viraram complexidade sem resolver o root cause.

Sequência sugerida:
1. **Phase 1**: Implementar `processing_locks` + queue
2. **Phase 2**: Migrar webhook handler pra usar lock
3. **Phase 3**: Dedup universal (não só Q1/Q2)
4. **Phase 4**: Single slot offer per cycle
5. **Phase 5**: Testes regressão T1-T8
6. **Phase 6**: Rollout gradual + monitoring

Estimativa: 1-2 dias de trabalho focado.
