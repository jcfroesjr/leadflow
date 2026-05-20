# Project State

## Current Position

Phase: 3 (Fix @lid Base — workdir 20/05)
Plan: 03-01-PLAN.md (a criar via `/gsd-plan-phase 3`)
Status: Workdir pronto, aguardando validação + commit
Last activity: 2026-05-20 — Milestone v2.1 (Grupo Robusto) iniciado

## Active Milestone

**v2.1 — Grupo WhatsApp Robusto** (Fases 3-9)

| Fase | Nome | Status | Bloqueador |
|------|------|--------|------------|
| 3 | Fix @lid base | ⚡ Workdir pronto | — |
| 4 | Captura @lid via MESSAGES_UPSERT | 📋 Aguardando | Phase 3 mergeada |
| 5 | Endpoints admin | 📋 Aguardando | Phase 3 mergeada |
| 6 | Whitelist anti-spam | 📋 Aguardando | — (independente) |
| 7 | qualificacao_lock antes do grupo | 📋 Aguardando | — (independente) |
| 8 | Frontend dashboard grupos | 📋 Opcional / próximo milestone | Phase 5 mergeada |
| 9 | Testes regressão + doc | 📋 Aguardando | Phases 3-7 mergeadas |

## Pending Tasks (this session)

- [ ] Commit + push backend (Fase 3 workdir: evolution.py, grupo_webhook.py, grupo_fallback.py, confirmacao_agendamento.py)
- [ ] Redeploy backend no Easypanel
- [ ] Smoke test em prod com lead novo
- [ ] (Manual) UPDATE no Supabase Editor pra Karla 5581988280629 sair de FALLBACK_1_1 — depois substitui pelo endpoint Phase 5
- [ ] Investigar logs Easypanel: convite nativo Patrícia 5555984248339 chegou? (input pra Phase 6)
- [ ] Atualizar memória `sessao_2026-05-20_grupo_lid_arquitetura.md` (preserva contexto pra próxima sessão)

## Accumulated Context (preservado entre milestones)

### v2.0 Validated em prod (ad-hoc, sem ciclo GSD)

- ✅ Lock atômico (`processing_locks` + `acquire/release/cleanup`)
- ✅ Dedup universal (`send_text_uma_vez` + `OFERTA_ATIVA` + unique index conversas)
- ✅ Slot-pick determinístico (build 2026-05-03 em prod)

### Camadas defensivas grupo (18-19/05) — NÃO REVERTER

- ✅ Fase 1 18/05: removida presunção `@lid=True` (4 patches: evolution.py:251, grupo_fallback.py:524, agente.py:8847, leads.py:73)
- ✅ Fase 4 18/05: regra unificada probe Evolution + FSM (AND) em aquec/notif/D-1
- ✅ Fix 19/05 commit ee132b9: FSM=ATIVO herdado sempre revalida via probe live
- ✅ Fix 19/05: convite nativo nominal com `nome_responsavel` configurável
- ✅ Selador `qualificacao_lock.py` 18/05 (Q1+Q2+Q3+empatia ao virar agendado)
- ✅ Guard webhook 18/05: não cria lead fake se telefone desconhecido
- ✅ Whitelist `safety_net` 18/05: 23 motivos
- ✅ Pipeline kanban Fase 3 18/05: colunas `agendamento_confirmado` + `no_show`

### Infra existente (não reinventar)

- `app/services/lock.py` — acquire/release/cleanup (v2.0)
- `app/services/grupo_state.py` — FSM AGUARDANDO/FALLBACK_1_1/ATIVO + transition guards
- `app/services/grupo_fallback.py:177` — `ativar_fallback_se_necessario` (entry point principal)
- `app/services/qualificacao_lock.py` — `popular_qs_se_faltando` (Q1-Q3 + empatia sintéticas)
- `app/routers/grupo_webhook.py` — `GROUP_PARTICIPANTS_UPDATE` handler
- 23+ markers em `conversas` com unique constraint pra idempotência

### Casos reais resolvidos por bugs anteriores (consultar memórias)

- Caca 03/05 (race condition mensagens consecutivas) → v2.0 Phase 1
- Andressa 04/05 (LLM hallucina bullets sem tool) → v2.0 SLOTS-RESCUE
- Luciane 11/05 (Evolution mentiu in_group=True) → Phase 7 FSM
- Vanusa 13/05 (propagação 10-20s) → aquec floor 30s + DM convite delay 60s
- Luciane 18/05 (FSM ATIVO herdado) → Fase 1 18/05 revalidação
- Luciane 19/05 (notif #2 grupo vazio) → Fix ee132b9 sem bypass
- Karla 20/05 (@lid removido = FALLBACK_1_1 errado) → Fase 3 v2.1 (esta milestone)
- Patrícia 20/05 (Q1/Q2 dupla + persona switch + convite não chegou) → Fases 6+7 v2.1

## Next Action

1. Aprovar roadmap v2.1 (apresentado em conversa)
2. `/gsd-plan-phase 3` — gera plano detalhado pra Fase 3 (validação + commit fix @lid base)
3. Executar plano
4. Mover pra Fase 4

---

*Last updated: 2026-05-20 — milestone v2.1 iniciado*
