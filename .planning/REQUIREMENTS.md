# Requirements — Leadflow Platform

## Validated (já em produção, NÃO REGREDIR)

### Frontend v2 (milestone v1.0 concluído)
- ✓ AUTH-01 a AUTH-06 — Login Supabase + ProtectedRoute
- ✓ DASH-01 a DASH-07 — Dashboard com KPIs reais + gráfico 7 dias
- ✓ LEAD-01 a LEAD-11 — Tabela leads + ações funcionais
- ✓ CONV-01 a CONV-08 — Inbox conversas com polling
- ✓ AGNT-01 a AGNT-07 — Editor de config IA
- ✓ PIPE-01 a PIPE-04 — Kanban pipeline
- ✓ SETT-01 a SETT-03 — Configurações
- ✓ BILD-01 a BILD-04 — Build & deploy
- ✓ FollowupEditor + AquecimentoEditor + DelayPicker

### Backend Agente IA (em produção)
- ✓ Webhook lead-criação `/webhook/{empresa_id}/{token}`
- ✓ Q1 → Q2 → Q3 (empathy + slots) com templates configuráveis
- ✓ Tool calling Gemini/OpenAI (`buscar_horarios_livres`, `criar_agendamento`)
- ✓ FSM de fases (novo → q1_enviado → q2_enviado → qualificado → slots_oferecidos → agendado/nao_convertido)
- ✓ 4 camadas defesa slots (ANTI-ANUNCIO → SLOTS-RESCUE → FILLUP → ULTRA-FALLBACK)
- ✓ SLOT-OVERRIDE no tool call
- ✓ Slot-pick day+hour matching direto de números
- ✓ MSG_PROCESSED dedup por message_id
- ✓ Audio Whisper (4 paths detector + HTTP 201)
- ✓ FU recovery 14d + tolerância overdue 48h + endpoint retomar-stuck
- ✓ Time-based nao_convertido com atraso configurável
- ✓ Despedidas educadas (OPT-OUT, MENU-ENC, PAUSA-INDEF) ANTES do status terminal
- ✓ SYNC com variantes BR phone (12 e 13 dígitos)
- ✓ Aquecimento grupo: ordem +5s, audio/pdf, auto-save

---

## Active — Milestone v2.0 Agente IA Atomic Processing

**Goal:** Eliminar race conditions, duplicações Q2/Q3 (empathy+slots), e agendamentos em horário errado quando lead manda múltiplas mensagens em sequência (texto + áudio em <10s).

### Cat 1: LOCK ATÔMICO (critical path)

- [ ] **LOCK-01**: Tabela `processing_locks(empresa_id, telefone, msg_id, acquired_at, expires_at)` com PK em (empresa_id, telefone)
- [ ] **LOCK-02**: Função `acquire_lock(empresa_id, telefone, msg_id)` — INSERT atômico; retorna True ou False (já tem detentor)
- [ ] **LOCK-03**: Função `release_lock(empresa_id, telefone, msg_id)` — DELETE; processa próximo da queue se houver
- [ ] **LOCK-04**: Webhook `_processar_webhook_evolution_inner` adquire lock no início, libera no finally
- [ ] **LOCK-05**: Quando lock ocupado, mensagem enfileirada via `QUEUED:{msg_id}:{ts}` em `conversas`
- [ ] **LOCK-06**: Próximo da queue processado em ordem cronológica após release
- [ ] **LOCK-07**: Job APScheduler (30s) limpa locks expirados (`expires_at < NOW()`)
- [ ] **LOCK-08**: Logs estruturados `[LOCK]` em acquire/release/expire pra observabilidade

### Cat 2: DEDUP UNIVERSAL

- [ ] **DEDUP-01**: Helper `enviar_uma_vez(empresa_id, telefone, conteudo)` — antes de send_text, query DB last 30s; se mesmo conteúdo já existe → skip
- [ ] **DEDUP-02**: Aplicar em: Q1 template, Q2 template, empathy, slot offer, "Marcadinho!", despedidas
- [ ] **DEDUP-03**: Marker `OFERTA_ATIVA:{ts_iso}` por lead — segunda tentativa de oferecer slots em <2min retorna a oferta vigente (NÃO cria novo SLOTS_TOKENS)
- [ ] **DEDUP-04**: Unique partial index em `conversas(empresa_id, telefone, conteudo)` WHERE role='sistema' (impede markers duplicados via race)

### Cat 3: SLOT-PICK DETERMINÍSTICO

- [ ] **SLOT-01**: Lookup de SLOTS_TOKENS usa SEMPRE OFERTA_ATIVA mais recente (NÃO "última msg do histórico")
- [ ] **SLOT-02**: Matching mantém lógica atual (extrai nums 1-31, cruza day+hour vs tokens, 1 hit → usa)
- [ ] **SLOT-03**: 0 hits ou >1 hits → BLOQUEIA tool e re-apresenta os 3 slots vigentes pedindo clarificação
- [ ] **SLOT-04**: SLOT-OVERRIDE valida slot_token retornado pelo LLM contra OFERTA_ATIVA; corrige se diverge

### Cat 4: AUDIO TOLERANCE

- [ ] **AUDIO-T-01**: Whisper transcription tratada como hint, slot-pick sempre cruza nums vs tokens
- [ ] **AUDIO-T-02**: Áudio "Sim" curto não dispara Q1/Q2 confirmation se Q1/Q2 já foi confirmado anteriormente (idempotência semântica)
- [ ] **AUDIO-T-03**: Se Whisper retorna vazio/erro, bot pergunta clarificação ("não entendi, pode escrever?")

### Cat 5: TESTES REGRESSÃO

- [ ] **TEST-01**: Suite T1-T8 documentada em ANALISE_DETALHADA_DEFEITOS.md
- [ ] **TEST-02**: Test harness pytest + httpx mocking
- [ ] **TEST-03**: Stub Evolution API
- [ ] **TEST-04**: Stub Google Calendar
- [ ] **TEST-05**: Stub LLM (responses fixos)
- [ ] **TEST-06**: T1: 3 "Sim" em 5s → 3 msgs do bot (não 9)
- [ ] **TEST-07**: T2: Áudio Whisper imperfeito → identifica slot ou pergunta
- [ ] **TEST-08**: T3: Ordem chegada respeitada na queue
- [ ] **TEST-09**: T4: Slot-pick correto "dia X às Y"
- [ ] **TEST-10**: T5: Não regredir flow happy path
- [ ] **TEST-11**: Lock contention: 5 webhooks simultâneos
- [ ] **TEST-12**: Lock TTL: lock órfão limpo após 60s

### Cat 6: DOCUMENTAÇÃO + OBSERVABILIDADE

- [ ] **DOC-01**: Memória `agente_ia_fixes.md` atualizada com fluxo lock + queue
- [ ] **DOC-02**: Diagrama sequência webhook handler
- [ ] **OBS-01**: Endpoint `/admin/queue-stats?empresa_id=X` retorna queue depth e lock status
- [ ] **OBS-02**: Logs `[LOCK]` + `[QUEUE]` + `[DEDUP]` estruturados

---

## Future (próximos milestones)

- Multi-instance backend (advisory locks Postgres ou Redis)
- WebSocket / SSE realtime no frontend
- Frontend admin pra visualizar queue depth e locks ativos
- Refator FSM de fases pra suportar paralelo seguro

## Out of Scope (deste milestone)

| Feature | Reason |
|---------|--------|
| Migração Postgres → Redis | Postgres handle 1 worker single-instance |
| Rewrite FSM completo | Só ajustes pontuais necessários |
| Mudança LLM provider | gpt-4.1 funcional, segue |
| Nova feature do frontend | Foco backend |
| Multi-tenant onboarding | Empresa única hoje, multi-tenant ready estrutural |

---

## Traceability (preenchida pelo roadmapper)

(empty)

---

*Last updated: 2026-05-03 — milestone v2.0 iniciado, foco em lock atômico*
