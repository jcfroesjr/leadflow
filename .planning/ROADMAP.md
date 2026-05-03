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

## Phase Order Rationale

1. **Phase 1 primeiro (CRITICAL PATH)** — sem lock, todo o resto continua quebrado
2. **Phase 2 depois** — dedup universal só faz sentido com lock garantindo ordenação
3. **Phase 3** — slot-pick deterministic depende de OFERTA_ATIVA criado em Phase 2
4. **Phase 4** — idempotência semântica é defesa adicional, mais robusta com lock
5. **Phase 5** — testes validam tudo acima e protegem contra regressão
6. **Phase 6** — documentação e observabilidade pra operação contínua

---

## Próximo passo imediato

```
/gsd-discuss-phase 1
```

Vai discutir abordagens pra Phase 1 (Lock Atômico) com você antes de criar o plano detalhado.

Ou direto:

```
/gsd-plan-phase 1
```

Pula a discussão e vai direto pro plano executável.

---

*Roadmap criado: 2026-05-03 — milestone v2.0*
