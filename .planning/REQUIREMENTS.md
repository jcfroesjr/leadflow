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

## Validated — v2.0 Agente IA Atomic Processing (shippado ad-hoc 04-06/05)

Phases 1-2 do milestone v2.0 foram entregues fora do ciclo GSD durante a sessão 06/05 (10 commits diretos + validação em prod). Marcadas validated aqui pra que requirements remanescentes (TEST, AUDIO-T, DOC, OBS) possam ser retomados em milestone futuro se necessário.

- ✓ **LOCK-01..08** — `processing_locks` + acquire/release/cleanup em prod desde 06/05
- ✓ **DEDUP-01..04** — `send_text_uma_vez` + OFERTA_ATIVA + unique index conversas em prod
- ✓ **SLOT-01..04** — slot-pick direto nums vs tokens (build 2026-05-03)

### Diferida (próximo milestone se ressurgir)

- AUDIO-T-01..03 (Whisper tolerance — não há mais reportes desde 06/05)
- TEST-01..12 (suite regressão — feita ad-hoc por usuário em prod)
- DOC-01..02 (diagrama sequência)
- OBS-01 (endpoint /admin/queue-stats)

---

## Active — Milestone v2.1 Grupo WhatsApp Robusto

**Goal:** Eliminar bugs recorrentes de detecção `@lid` no grupo WhatsApp ao capturar Linked ID em múltiplas fontes (`GROUP_PARTICIPANTS_UPDATE` + `MESSAGES_UPSERT` + backfill admin) e persistir como marker, usado como matcher alternativo ao telefone em todos os probes Evolution.

**Causa-raiz comprovada:** WhatsApp esconde telefone do lead como `@lid` interno por privacidade. Sem mapping `phone ↔ @lid`, probe retorna chute. Cada patch anterior foi trade-off entre falso positivo e falso negativo. Esta milestone elimina o trade-off ao tornar `@lid` identidade persistida e match-able.

### Cat 1: LID-CAPTURE (Fase 3 — fix base @lid)

- [ ] **LID-01**: Webhook `GROUP_PARTICIPANTS_UPDATE` separa `@lid` de telefones limpos no array `participants` *(workdir 20/05)*
- [ ] **LID-02**: Quando só `@lid` entrou E exatamente 1 lead aguardando no grupo → grava marker `LEAD_LID:{grupo_jid}:{lid}` + chama `processar_entrada_lead_no_grupo` *(workdir 20/05)*
- [ ] **LID-03**: Quando >1 lead aguardando → loga ambiguidade, não promove, aguarda próximo sinal *(workdir 20/05)*
- [ ] **LID-04**: `verificar_lead_no_grupo` aceita parâmetro opcional `lead_lid: str = ""` *(workdir 20/05)*
- [ ] **LID-05**: No loop de participants do probe, casa por `pjid == lead_lid` (case-insensitive) além do telefone limpo *(workdir 20/05)*
- [ ] **LID-06**: Helper `_get_lead_lid_for_group(sb, empresa_id, telefone, grupo_jid)` lê marker LEAD_LID mais recente *(workdir 20/05)*
- [ ] **LID-07**: 6 callers em `grupo_fallback.py` threadeados pra ler lid antes de chamar probe *(workdir 20/05)*
- [ ] **LID-08**: Caller em `confirmacao_agendamento.py:289` threadeado *(workdir 20/05)*

### Cat 2: LID-CAPTURE-DEFESA (Fase 4 — segunda fonte)

- [ ] **LID-D-01**: Webhook agente (`_processar_webhook_evolution_inner`) detecta msg com `key.remoteJid` terminando em `@g.us` (grupo)
- [ ] **LID-D-02**: Extrai `key.participant` (formato `<lid>@lid` ou `<phone>@s.whatsapp.net`)
- [ ] **LID-D-03**: Se grupo tem GRUPO_AGUARDANDO_ENTRADA + 1 único lead aguardando → grava `LEAD_LID` + promove via `processar_entrada_lead_no_grupo` (idempotente)
- [ ] **LID-D-04**: Não interfere no processamento normal da msg (1-1 message handler continua sua lógica)
- [ ] **LID-D-05**: Logs `[LID-CAPTURE-MSG]` estruturados pra observabilidade

### Cat 3: ADMIN (Fase 5 — backfill + observabilidade)

- [ ] **ADMIN-01**: Endpoint `POST /admin/grupo/forcar-revalidacao` body `{ empresa_id, telefone, agendamento_id }` — re-probe Evolution live + sincroniza FSM
- [ ] **ADMIN-02**: Suporta override manual: se admin adicionou lead no grupo via WhatsApp da Rejane, endpoint força FSM=ATIVO e atualiza `criado_em` do marker mais recente
- [ ] **ADMIN-03**: Endpoint `GET /admin/grupo/status?empresa_id=X[&state=FALLBACK_1_1]` — JSON com (lead_id, nome, telefone, grupo_jid, agendamento_id, FSM_state, probe_live_now, has_lead_lid, tempo_aguardando)
- [ ] **ADMIN-04**: Auth via header `X-Admin-Key` (Supabase service role key) — sem auth normal de usuário admin

### Cat 4: ANTI-SPAM AUDIT (Fase 6)

- [ ] **SPAM-01**: Mapear o que `ANTI_SPAM_LOOP:rate_alto` bloqueia hoje (grep `agente.py:4170-4268`)
- [ ] **SPAM-02**: Validar via logs Easypanel se convite nativo da Patrícia (20/05 16:27:25) chegou no WhatsApp dela
- [ ] **SPAM-03**: Whitelist `enviar_convite_grupo` e `enviar_mensagem` do fluxo de grupo no anti-spam (não devem ser bloqueados por rate_alto da conversa do lead)
- [ ] **SPAM-04**: Loga `[ANTI-SPAM-BYPASS]` quando convite nativo passa apesar de marker rate_alto

### Cat 5: QUALIFICACAO LOCK ORDEM (Fase 7)

- [ ] **QLOCK-01**: `popular_qs_se_faltando(sb, empresa_id, telefone, nome_lead, when_iso)` chamada ANTES de `_criar_grupo_agendamento` retornar (em `leads.py`)
- [ ] **QLOCK-02**: Mesma chamada antes do tool path do agente (em `agente.py` onde tool `criar_agendamento` é executado)
- [ ] **QLOCK-03**: Validar que persona (nome do agente) fica selada junto — agente.py não pode trocar Maia/Bia mid-conversa
- [ ] **QLOCK-04**: Backfill validado: caso Patrícia regressão (Q1/Q2 não dispara 2x após lock selado)

### Cat 6: TESTES (Fase 9)

- [ ] **TEST-G1**: Lead entra com telefone limpo → webhook GROUP_PARTICIPANTS_UPDATE → match por telefone → FSM=ATIVO
- [ ] **TEST-G2**: Lead entra só com `@lid` + 1 único lead aguardando → marker `LEAD_LID` salvo → probe casa por lid → FSM=ATIVO
- [ ] **TEST-G3**: Lead nunca entra → 30s convite DM + 90s alerta grupo + 30min FALLBACK_1_1 transition
- [ ] **TEST-G4**: 2 leads aguardando + `@lid` ambíguo → log de ambiguidade, FSM permanece AGUARDANDO até próximo sinal
- [ ] **TEST-G5**: Caso Patrícia regressão: agendamento → `qualificacao_lock` selada → próxima msg do lead não dispara Q1/Q2 de novo
- [ ] **TEST-G6**: Caso Karla regressão: lead em FALLBACK_1_1, admin chama `/admin/grupo/forcar-revalidacao` → probe confirma in_group=True → FSM=ATIVO

### Cat 7: DOC + OBSERVABILIDADE

- [ ] **DOC-G1**: Memória nova `sessao_2026-05-XX_grupo_robusto.md` com arquitetura `@lid` + casos resolvidos
- [ ] **DOC-G2**: Atualizar `agente_referencia_compilada.md` com novos markers + endpoints admin
- [ ] **OBS-G1**: Logs `[LEAD-LID]`, `[LID-CAPTURE-MSG]`, `[ANTI-SPAM-BYPASS]` estruturados em todas as operações

---

## Future (próximos milestones)

- Coluna `leads.lid_whatsapp` (se >100 leads com @lid persistido, marker pode pesar)
- Endpoint Evolution alternativo (`checkNumberStatus`) como fallback de probe
- Dashboard frontend pra `/admin/grupo/status` (hoje só JSON)
- Suite testes T1-T8 do v2.0 (audio + queue regression)
- Multi-instance backend (advisory locks Postgres)
- WebSocket / SSE realtime

## Out of Scope (deste milestone)

| Feature | Reason |
|---------|--------|
| Coluna `leads.lid_whatsapp` | Marker em conversas é suficiente, evita migration |
| Endpoint Evolution alternativo (`checkNumberStatus`) | `findGroupInfos` cobre com `@lid` mapped |
| Reescrita FSM AGUARDANDO/FALLBACK_1_1/ATIVO | Já funciona, só faltava o match |
| Cache de probe Evolution | Taxa atual ~5-10/min, sem pressão |
| Reescrever ANTI_SPAM_LOOP detector | Só whitelist o convite nativo |
| Eventos webhook adicionais (CONNECTION_UPDATE, CONTACTS_UPSERT) | Os 2 atuais cobrem |
| Multi-instance backend | Single-instance hoje (carryover v2.0 decision) |
| Migração Postgres → Redis | Postgres handle 1 worker bem |

---

## Traceability (preenchida pelo roadmapper)

| Requirement | Phase | Plan |
|-------------|-------|------|
| LID-01..08 | Fase 3 (Fix @lid base) | 03-01-PLAN.md |
| LID-D-01..05 | Fase 4 (Captura via MESSAGES_UPSERT) | 04-01-PLAN.md |
| ADMIN-01..04 | Fase 5 (Endpoints admin) | 05-01-PLAN.md |
| SPAM-01..04 | Fase 6 (Whitelist anti-spam) | 06-01-PLAN.md |
| QLOCK-01..04 | Fase 7 (qualificacao_lock antes do grupo) | 07-01-PLAN.md |
| (ADMIN-03..04) | Fase 8 (Observabilidade dashboard) | 08-01-PLAN.md |
| TEST-G1..G6 + DOC-G1..G2 + OBS-G1 | Fase 9 (Testes regressão + doc) | 09-01-PLAN.md |

---

*Last updated: 2026-05-20 — v2.0 phases validated (shippado ad-hoc), milestone v2.1 Grupo Robusto iniciado*
