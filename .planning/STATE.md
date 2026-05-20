# Project State

## Current Position

Phase: COMPLETO (todas Fases 3-9 shippadas)
Plan: —
Status: Milestone v2.1 entregue, aguardando próxima decisão de milestone
Last activity: 2026-05-20 — Milestone v2.1 (Grupo Robusto) entregue end-to-end

## Active Milestone

**v2.1 — Grupo WhatsApp Robusto** ✅ COMPLETO (Fases 3-9)

| Fase | Nome | Status | Commit |
|------|------|--------|--------|
| 3 | Fix @lid base | ✅ deployed | `ac301fd` |
| 4 | Captura @lid via MESSAGES_UPSERT | ✅ deployed | `6b0295b` |
| 5 | Endpoints admin | ✅ deployed | `6b0295b` + `207a3a9` |
| 6 | Alerta LEAD_LID + delay 180s | ✅ deployed | `0e4c335` |
| 7 | qualificacao_lock multi-template | ✅ deployed | `0717e1c` |
| 8 backend | Auth bridge JWT+admin | ✅ deployed | `8d9fe5c` |
| 8 frontend | Dashboard /admin/grupos | ✅ deployed | `f97686c` |
| 9 | Suite testes regressão (13 testes) | ✅ commitada | `6159af5` |

## Casos resolvidos nesta milestone

- ✅ **Karla** (5581988280629, Liliane) — auto-promovida via Phase 3/4
- ✅ **Crislaine** (5566996076259, Liliane, reunião 21/05 13h) — convite re-enviado via endpoint Phase 5
- ✅ **Patrícia** (5555984248339, Liliane) — Phase 7 corrige Q1/Q2 dupla para persona custom

## Pending Tasks (opcional, próxima sessão)

- [ ] Rodar suite testes localmente após `pip install pytest pytest-asyncio` (validar 13 testes pass)
- [ ] Smoke test do frontend dashboard `/admin/grupos` em prod
- [ ] Expandir suite testes: Phase 4 (LID-CAPTURE-MSG), Phase 6 (alerta LEAD_LID check), TestClient FastAPI nos endpoints admin
- [ ] Verificar Crislaine após 21/05 (reunião) — entrou no grupo? Notif foi pro DM?

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
