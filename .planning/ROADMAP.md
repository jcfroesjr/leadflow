# Roadmap — Leadflow Platform

**Created:** 2026-05-03

---

## Milestone v1.0 — Frontend v2 (CONCLUÍDO)

Phases 1-6 do frontend v2 (Auth, Dashboard, Leads, Conversas, Agente IA, Pipeline+Settings) deployadas em produção em https://leadflow-frontend.bqvcbz.easypanel.host. Detalhes preservados em git history.

---

## Milestone v2.0 — Agente IA Atomic Processing

**Goal:** Eliminar race conditions e duplicações no webhook handler do agente IA. Garantir agendamento correto mesmo com múltiplas mensagens consecutivas (texto + áudio em <10s) e Whisper imperfeito.

**Critical path:** Phase 1 (Lock atômico). Sem isso, defesas acumuladas continuam sendo ineficazes contra race.

---

### Phase 1: Lock Atômico + Queue
**Goal:** Webhook handler processa uma mensagem por vez por (empresa_id, telefone). Múltiplas mensagens em paralelo são serializadas em ordem cronológica.

**Requirements:** LOCK-01, LOCK-02, LOCK-03, LOCK-04, LOCK-05, LOCK-06, LOCK-07, LOCK-08

**Deliverables:**
- Migration SQL: tabela `processing_locks(empresa_id, telefone, msg_id, acquired_at, expires_at)` com PK em (empresa_id, telefone)
- `app/services/lock.py` com `acquire_lock()`, `release_lock()`, `cleanup_expired_locks()`
- `_processar_webhook_evolution_inner` envolvido em `try/finally` com lock
- Marker `QUEUED:{msg_id}:{ts}` no DB pra mensagens enfileiradas
- Job APScheduler `cleanup_expired_locks` a cada 30s
- Logs `[LOCK]` estruturados em todas as operações

**Success criteria:**
1. Lock adquirido atomicamente — 2 webhooks simultâneos só 1 ganha
2. Lock liberado mesmo se processamento falhar (try/finally)
3. Queue processada em ordem cronológica de chegada
4. Lock órfão limpo após 60s pelo job de cleanup
5. Logs `[LOCK]` permitem debug de contention/queue depth

**Plans:** ~2-3 plans
- 01-01-PLAN.md — Migration SQL + service `lock.py` + testes unitários
- 01-02-PLAN.md — Integração no webhook handler (try/finally)
- 01-03-PLAN.md — Queue processing + cleanup job + observability

**Status:** 📋 Aguardando início

---

### Phase 2: Dedup Universal + OFERTA_ATIVA
**Goal:** Antes de qualquer send_text (Q1, Q2, empathy, slots, "Marcadinho!", despedidas), checar DB pra mesmo conteúdo nos últimos 30s. Slot offer único por ciclo via marker `OFERTA_ATIVA`.

**Requirements:** DEDUP-01, DEDUP-02, DEDUP-03, DEDUP-04

**Deliverables:**
- Helper `enviar_uma_vez(empresa_id, telefone, conteudo)` em `app/services/evolution_router.py` ou similar
- Substituir todos os `evo_router.send_text()` em `agente.py` por `enviar_uma_vez()`
- Marker `OFERTA_ATIVA:{ts}` salvo junto com SLOTS_TOKENS; segunda tentativa <2min retorna oferta vigente
- Migration: unique partial index em `conversas(empresa_id, telefone, conteudo)` WHERE role='sistema'
- Logs `[DEDUP]` em skips

**Success criteria:**
1. Q1, Q2, empathy enviados no máximo 1× por turno mesmo com webhooks paralelos
2. Slot offer único por ciclo — nunca 2 sets de SLOTS_TOKENS no histórico
3. "Marcadinho!" enviado apenas após criação real de evento (não no retry)
4. Despedidas educadas enviadas no máximo 1× / 24h

**Plans:** ~1-2 plans
- 02-01-PLAN.md — Helper `enviar_uma_vez` + refator dos send_text
- 02-02-PLAN.md — Marker OFERTA_ATIVA + integração com slot-pick

**Status:** 📋 Aguardando início

---

### Phase 3: Slot-Pick Determinístico via OFERTA_ATIVA
**Goal:** Slot-pick sempre usa OFERTA_ATIVA mais recente, não "última msg do histórico". Quando ambíguo ou sem match, BLOQUEIA tool e re-apresenta os slots vigentes.

**Requirements:** SLOT-01, SLOT-02, SLOT-03, SLOT-04

**Deliverables:**
- `agente.py` slot-pick refatorado pra ler OFERTA_ATIVA marker (em vez de scanning histórico por SLOTS_TOKENS)
- Quando 0 hits ou >1 hits → injeta BLOQUEAR_CONFIRMAR + re-apresenta slots vigentes
- SLOT-OVERRIDE no tool call valida slot_token contra OFERTA_ATIVA; corrige se diverge
- Logs `[SLOT-PICK]` mostrando OFERTA_ATIVA usada e match resultado

**Success criteria:**
1. Lead diz "dia 4 às 10" → bot agenda no dia 4 às 10 (não primeiro slot do menu)
2. Lead diz "dia 99 às 99" (inválido) → bot pergunta de novo, NÃO chuta
3. Lead diz "10 horas" (ambíguo entre 2 slots) → bot pergunta qual dia
4. Áudio Whisper imperfeito → ainda funciona via cruzamento direto nums vs tokens

**Plans:** ~1 plan
- 03-01-PLAN.md — Refator slot-pick pra usar OFERTA_ATIVA + ajustes na lógica de bloqueio

**Status:** 📋 Aguardando início

---

### Phase 4: Audio Tolerance & Idempotência Semântica
**Goal:** Áudio "Sim" curto não dispara Q1/Q2 confirmation se Q1/Q2 já foi confirmado. Whisper falhou → bot pergunta clarificação ao invés de ficar em silêncio.

**Requirements:** AUDIO-T-01, AUDIO-T-02, AUDIO-T-03

**Deliverables:**
- Check no início do agente: se "Sim"/"Correto"/"Isso" e fase já é qualificado/slots_oferecidos → NÃO redisparar Q1/Q2; só prosseguir o fluxo natural
- Se Whisper retorna vazio/erro 3x consecutivas → bot pergunta "Não estou conseguindo entender seu áudio, pode escrever?"
- Logs `[AUDIO-IDEM]` em ignores semânticos

**Success criteria:**
1. Lead manda "Sim" texto + "Sim" áudio quase simultâneos → bot envia Q2 só uma vez
2. Lead manda "Sim" áudio depois de já estar em fase=qualificado → bot ignora (não reseta fluxo)
3. Whisper falha 3× → bot pede texto

**Plans:** ~1 plan
- 04-01-PLAN.md — Check de idempotência semântica + fallback Whisper

**Status:** 📋 Aguardando início

---

### Phase 5: Testes Regressão T1-T8
**Goal:** Suite de testes pytest cobrindo casos reais documentados. Cada commit que toca o agente roda essa suite antes de deploy.

**Requirements:** TEST-01 a TEST-12

**Deliverables:**
- `tests/test_agente_atomic.py` com fixtures de Evolution stub, Calendar stub, LLM stub
- Test T1: 3 "Sim" em 5s → 3 msgs do bot
- Test T2: Áudio Whisper imperfeito → identifica slot ou pergunta
- Test T3: Ordem chegada respeitada
- Test T4: Slot-pick correto "dia X às Y"
- Test T5: Happy path não regrediu
- Test T11: Lock contention (5 webhooks simultâneos)
- Test T12: Lock TTL (lock órfão limpo após 60s)
- Documentação de como rodar (`pytest tests/test_agente_atomic.py -v`)
- CI: GitHub Actions roda testes em cada push (opcional)

**Success criteria:**
1. Suite passa 100% após Phase 1-4 implementadas
2. Cobertura cobre cenários reais (Caca, Andressa, Jakeline)
3. Tests rodam em <30s

**Plans:** ~2 plans
- 05-01-PLAN.md — Test harness + fixtures + stubs
- 05-02-PLAN.md — Implementação dos 8 testes T1-T8

**Status:** 📋 Aguardando início

---

### Phase 6: Documentação + Observabilidade + Rollout
**Goal:** Documentação operacional do novo fluxo. Endpoint admin pra monitorar lock/queue. Rollout com flag pra rollback rápido.

**Requirements:** DOC-01, DOC-02, OBS-01, OBS-02

**Deliverables:**
- Memória `agente_ia_fixes.md` atualizada com fluxo lock + queue + dedup + slot OFERTA_ATIVA
- Diagrama sequência (mermaid) do webhook handler
- Endpoint `GET /admin/queue-stats?empresa_id=X` retorna queue depth, lock status, lock duration p50/p95
- Logs estruturados `[LOCK]`, `[QUEUE]`, `[DEDUP]`, `[SLOT-PICK]`
- Feature flag `ATOMIC_PROCESSING_ENABLED` em config_ia (default true; rollback rápido se algo falhar)
- Runbook: como diagnosticar lock contention, queue backlog, lock órfão

**Success criteria:**
1. Equipe consegue diagnosticar problemas via `/admin/queue-stats`
2. Rollback é 1 toggle (`ATOMIC_PROCESSING_ENABLED=false`)
3. Memórias atualizadas pra próximas sessões

**Plans:** ~1 plan
- 06-01-PLAN.md — Documentação + endpoint admin + feature flag

**Status:** 📋 Aguardando início

---

## Phase Order Rationale (v2.0)

1. **Phase 1 primeiro (CRITICAL PATH)** — sem lock, todo o resto continua quebrado
2. **Phase 2 depois** — dedup universal só faz sentido com lock garantindo ordenação
3. **Phase 3-6 (v2.0)** — slot-pick + audio + testes + docs

---

## v2.0 Status (validated em prod)

| Phase | Status | Notas |
|-------|--------|-------|
| Phase 1: Lock Atômico + Queue | ✓ shippado ad-hoc 06/05 | Validated em prod, sem ciclo GSD |
| Phase 2: Dedup Universal + OFERTA_ATIVA | ✓ shippado ad-hoc 06/05 | Validated em prod |
| Phase 3: Slot-Pick Determinístico | ✓ shippado ad-hoc 06/05 | Build `2026-05-03-slot-pick-direto-numeros-vs-tokens` em prod |
| Phase 4: Audio Tolerance | ⏸ diferido | Sem reportes desde 06/05, próximo milestone se ressurgir |
| Phase 5: Testes Regressão T1-T8 | ⏸ diferido | Validação ad-hoc em prod via casos reais |
| Phase 6: Doc + Observabilidade | ⏸ parcial | Memórias atualizadas, endpoint queue-stats não criado |

---

## Milestone v2.1 — Grupo WhatsApp Robusto

**Goal:** Eliminar bugs `@lid` no grupo WhatsApp capturando Linked ID em múltiplas fontes (`GROUP_PARTICIPANTS_UPDATE` + `MESSAGES_UPSERT` + backfill admin) e usando como matcher alternativo ao telefone em todos os probes Evolution.

**Critical path:** Phase 3 (fix base `@lid`) — já implementada no workdir, falta commit + validação. Sem ela, fases 4-9 ficam sem fundação.

**Não reverter:** 10 commits 03/05 (sync_loop + slots fillup), 4 patches Fase 1 grupo 18/05 (removeu presunção @lid), Fase 4 18/05 (probe + FSM unificado), fixes 19/05 (FSM=ATIVO bypass + convite nominal).

---

### Phase 3: Fix `@lid` Base (workdir 20/05)
**Goal:** Webhook `GROUP_PARTICIPANTS_UPDATE` captura `@lid` quando lead entra com privacidade alta. Probe Evolution aceita `lead_lid` como matcher alternativo. 7 callers threadeados.

**Requirements:** LID-01, LID-02, LID-03, LID-04, LID-05, LID-06, LID-07, LID-08

**Deliverables (implementados no workdir):**
- `app/services/evolution.py:198-302` — `verificar_lead_no_grupo` aceita `lead_lid: str = ""` e casa por @lid no loop de participants
- `app/routers/grupo_webhook.py` — separa `@lid` de telefones; heurística unique-aguardando salva marker `LEAD_LID:{grupo_jid}:{lid}`
- `app/services/grupo_fallback.py` — helper `_get_lead_lid_for_group` + 6 callers threadeados
- `app/routers/confirmacao_agendamento.py:289` — caller threadeado

**Faltam (esta fase fecha):**
- Validação sintaxe + import — ✓ feito
- Commit + push backend
- Redeploy Easypanel
- Smoke test em produção (1 lead novo)
- Atualizar memória com novo padrão

**Success criteria:**
1. Lead novo entra no grupo com @lid → webhook salva marker `LEAD_LID` → probe casa por lid → FSM=ATIVO
2. Lead que entra com telefone limpo continua funcionando como antes
3. Probe legacy (callers sem `lead_lid`) continua funcionando (backwards compat)
4. Build em prod sem erros nos logs `[VERIFY-LEAD]` e `[LEAD-LID]`

**Plans:** ~1 plan
- 03-01-PLAN.md — Validação + commit + redeploy + smoke test

**Status:** ⚡ Workdir pronto, aguardando aprovação pra commit

---

### Phase 4: Captura `@lid` via `MESSAGES_UPSERT` (defesa-em-profundidade)
**Goal:** Quando webhook do agente recebe msg de lead no grupo com `key.participant` formato `@lid`, captura o lid e promove FSM se exatamente 1 lead aguardando. Cobre casos onde `GROUP_PARTICIPANTS_UPDATE` não dispara.

**Requirements:** LID-D-01, LID-D-02, LID-D-03, LID-D-04, LID-D-05

**Deliverables:**
- Bloco novo em `_processar_webhook_evolution_inner` (`app/routers/agente.py`): detecta `key.remoteJid` terminando em `@g.us`, extrai `key.participant`
- Reuso de `_salvar_lead_lid` + `processar_entrada_lead_no_grupo` (já existentes)
- Não interfere no processamento normal (continua salvando msg do lead, etc)
- Logs `[LID-CAPTURE-MSG]` estruturados

**Success criteria:**
1. Lead manda msg no grupo sem ter sido capturado pelo webhook ParticipantsUpdate → MESSAGES_UPSERT captura @lid e promove FSM=ATIVO
2. Lead já ATIVO no grupo manda msg → captura idempotente, não duplica marker
3. 2 leads aguardando + msg de @lid desconhecido → ambíguo, loga, não promove
4. Lead 1-1 normal (não grupo) → fluxo intacto

**Plans:** ~1 plan
- 04-01-PLAN.md — Detector grupo no webhook + reuso de helpers

**Status:** 📋 Aguardando início

---

### Phase 5: Endpoints Admin (backfill + observabilidade base)
**Goal:** Endpoint pra forçar revalidação FSM (caso Karla 20/05) + endpoint pra listar status de todos leads em grupo (substitui SQL manual).

**Requirements:** ADMIN-01, ADMIN-02, ADMIN-03, ADMIN-04

**Deliverables:**
- `app/routers/admin_grupo.py` (novo) — 2 endpoints com auth via `X-Admin-Key` (service role key)
- `POST /admin/grupo/forcar-revalidacao { empresa_id, telefone, agendamento_id }` — probe live + sincroniza FSM via `processar_entrada_lead_no_grupo` se in_group=True
- `POST /admin/grupo/forcar-revalidacao { ..., override_estado: "ATIVO" }` — força FSM mesmo se probe falhar (operador adicionou manualmente)
- `GET /admin/grupo/status?empresa_id=X[&state=FALLBACK_1_1]` — JSON com leads+FSM+probe_live+has_lead_lid+tempo_aguardando
- Logs `[ADMIN-GRUPO]` estruturados

**Success criteria:**
1. Operador roda `curl POST /admin/grupo/forcar-revalidacao` e Karla muda de FALLBACK_1_1 → ATIVO sem SQL manual
2. `GET /admin/grupo/status?state=FALLBACK_1_1` retorna lista todos leads atualmente sem grupo confirmado
3. Sem auth → 401
4. Endpoints idempotentes (chamadas repetidas não criam dados duplicados)

**Plans:** ~1 plan
- 05-01-PLAN.md — Router admin + auth + 2 endpoints

**Status:** 📋 Aguardando início

---

### Phase 6: Whitelist ANTI_SPAM_LOOP pra Convite Nativo (caso Patrícia)
**Goal:** `enviar_convite_grupo` não é bloqueado por `ANTI_SPAM_LOOP:rate_alto` da conversa do lead. Fluxo crítico de entrada não pode ser confundido com spam.

**Requirements:** SPAM-01, SPAM-02, SPAM-03, SPAM-04

**Deliverables:**
- Audit detalhado de `agente.py:4170-4268` (onde rate_alto é detectado e o que ele bloqueia)
- Validação via logs Easypanel: convite nativo Patrícia 20/05 16:27:25 chegou ou foi bloqueado?
- Whitelist: `enviar_convite_grupo` e `enviar_mensagem` chamados pelo fluxo de grupo (grupo_fallback) bypassam check de anti-spam
- Logs `[ANTI-SPAM-BYPASS]` quando bypass acontece
- Documentar em memória novo whitelist

**Success criteria:**
1. Lead com `ANTI_SPAM_LOOP:rate_alto` recente recebe convite nativo (card) mesmo assim
2. Lead com `ANTI_SPAM_LOOP:rate_alto` recente NÃO recebe resposta normal do agente (mantém suppress)
3. Logs mostram bypass quando ocorre
4. Caso Patrícia regressão validado (probe Evolution mostra que convite chegou)

**Plans:** ~1 plan
- 06-01-PLAN.md — Audit + whitelist + logs

**Status:** 📋 Aguardando início

---

### Phase 7: `qualificacao_lock` ANTES do Grupo (caso Patrícia Q1/Q2 dupla)
**Goal:** `popular_qs_se_faltando` chamada ANTES de `_criar_grupo_agendamento` retornar. Fecha janela de race que permitiu Q1/Q2 dupla em Patrícia 20/05.

**Requirements:** QLOCK-01, QLOCK-02, QLOCK-03, QLOCK-04

**Deliverables:**
- `app/routers/leads.py:_criar_grupo_agendamento` — call `popular_qs_se_faltando` ANTES do return
- `app/routers/agente.py` no tool path `criar_agendamento` — mesma call ANTES de retornar resultado pra LLM
- Persona (`nome_agente`) salva como variável imutável após qualificação selada
- Smoke test: agendar lead novo, próxima msg do lead NÃO dispara Q1/Q2

**Success criteria:**
1. Lead novo agenda → próxima mensagem dele não trigger Q1/Q2 de novo
2. Persona não troca mid-conversa (Maia continua Maia, Bia continua Bia)
3. `[migracao: historico selado]` aparece SEMPRE antes da primeira msg pós-agendamento, nunca entre Q1/Q2 duplicadas
4. Caso Patrícia regressão (recriado em teste): selador agora dispara antes

**Plans:** ~1 plan
- 07-01-PLAN.md — Mover qualificacao_lock + smoke test

**Status:** 📋 Aguardando início

---

### Phase 8: Dashboard Frontend `/admin/grupo/status` (opcional, pode mover pra v2.2)
**Goal:** Visualização das infos do endpoint `/admin/grupo/status` no frontend admin — tabela com cores por FSM state.

**Requirements:** ADMIN-03 (frontend), ADMIN-04 (frontend auth)

**Deliverables:**
- Frontend page `/admin/grupos` em React/TypeScript
- Tabela leads+FSM com filtro por state, tempo aguardando
- Action "Forçar revalidação" chamando endpoint criado em Phase 5
- Auto-refresh a cada 30s

**Success criteria:**
1. Admin abre `/admin/grupos`, vê leads em FALLBACK_1_1
2. Clica "Forçar revalidação" → recarrega + mostra novo FSM
3. Filtro por empresa + state funciona

**Plans:** ~1 plan
- 08-01-PLAN.md — Componente React + integração API

**Status:** 📋 Opcional, pode mover pra v2.2

---

### Phase 9: Suite Testes Regressão T-G1..G6 + Doc
**Goal:** Suite pytest com 6 cenários do grupo. Memória atualizada com nova arquitetura.

**Requirements:** TEST-G1..G6, DOC-G1, DOC-G2, OBS-G1

**Deliverables:**
- `tests/test_grupo_robusto.py` com fixtures Evolution stub + Supabase stub
- T-G1: lead entra phone limpo → ATIVO
- T-G2: lead entra `@lid` + 1 aguardando → ATIVO via match
- T-G3: lead nunca entra → FALLBACK_1_1 + convite + alerta
- T-G4: 2 leads aguardando + ambíguo → log, não promove
- T-G5: Patrícia regressão (Q1/Q2 não dispara 2x)
- T-G6: Karla regressão (admin endpoint força ATIVO)
- Memória nova `sessao_2026-05-XX_grupo_robusto.md` com arquitetura final
- Atualizar `agente_referencia_compilada.md` com novos markers + endpoints

**Success criteria:**
1. Suite passa 100%
2. Rodar suite < 30s
3. Memórias bem detalhadas pra próxima sessão

**Plans:** ~1 plan
- 09-01-PLAN.md — Tests + docs + memória final

**Status:** 📋 Aguardando início

---

## Phase Order Rationale (v2.1)

1. **Phase 3 primeiro (CRITICAL — workdir pronto)** — fundação do @lid persistido
2. **Phase 4** — segunda fonte de captura, cobre casos do webhook não disparar
3. **Phase 5** — endpoint admin desbloqueia operação (Karla case sem SQL manual)
4. **Phase 6** — whitelist convite nativo (resolve outro sintoma da Patrícia)
5. **Phase 7** — qualificacao_lock ordem (resolve Q1/Q2 dupla da Patrícia)
6. **Phase 8** (opcional) — frontend admin grupos
7. **Phase 9** — testes + doc consolidando tudo

---

## Próximo passo imediato

```
/gsd-discuss-phase 3
```

Discute Phase 3 antes do plano detalhado. Como ela já está em workdir, vai ser curto.

Ou direto:

```
/gsd-plan-phase 3
```

Pula a discussão e gera plano detalhado de validação + commit + smoke test.

---

*Roadmap criado: 2026-05-03 — milestone v2.0*
*Atualizado: 2026-05-20 — milestone v2.1 Grupo Robusto adicionado (Fase 3-9)*
