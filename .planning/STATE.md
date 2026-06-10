---
gsd_state_version: 1.0
milestone: v2.2
milestone_name: — Webhook-First Grupo Membership
status: verifying
last_updated: "2026-06-10T04:38:40.719Z"
last_activity: 2026-06-10
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 19
  completed_plans: 19
  percent: 100
---

# Project State

## Current Position

Phase: 14 (Testes regressao + doc + observabilidade) — EXECUTING
Plan: 3 of 3
Status: Phase complete — ready for verification
Last activity: 2026-06-10

## Active Milestone

**v2.2 — Identificacao Definitiva de Lead no Grupo (Webhook-First)**

**Goal:** Inverter a fonte da verdade. Webhook GROUP_PARTICIPANTS_UPDATE escreve em tabela materializada `grupo_membership` (primaria). Probe Evolution vira fallback com retry exponencial + cache curto.

**Phases planejadas:** Fase 10-14 (continua numbering — v2.1 terminou em Fase 9).

**Casos motivadores (sessao 08-09/06):**

- Ana Carla 5514998151089 (08/06 08:31) — entrou direto na createGroup, probe T+60s viu False, aquec foi pro DM
- Rosania 5562984551622 (08/06 23:57) — webhook chegou T+138s, aquec ja tinha falhado em T+60s
- Fernanda 5551999532715 (07/06) — grupo orfao de instancia antiga (bia-rejane) reusado
- Valquiria 5582981291203 (06/06) — aquec #4 falhou, recovery reagendou 47h depois (corrigido em 0d55888 mas e paliativo)
- 553891500357 (09/06) — caso reportado pelo user, persiste mesmo apos 6 fixes (trace pendente do user pra TEST-V2-G5)

## Phase Sequence v2.2

| Phase | Goal | Requirements | Status |
|-------|------|--------------|--------|
| 10 | Schema + 3 paths webhook write + cache standalone | MEMB-01..04, MEMB-06, PROBE-CACHE-01, PROBE-COALESCE-01 | Not started |
| 11 | `lead_in_group()` consumer + migrar fallback callers | MEMB-05 (+ migra 6 callsites grupo_fallback.py) | Not started |
| 12 | Retry async + callers com margem | PROBE-RETRY-01, PROBE-RETRY-02 | Not started |
| 13 | LEAVE handler + FSM audit monotonico | LEAVE-01..03, FSM-AUDIT-01..03 | Not started |
| 14 | Testes regressao + doc + observabilidade | TEST-V2-G1..G5, DOC-V2-G1..G2, OBS-V2-G1..G2 | Not started |

## Performance Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Coverage requisitos v2.2 | 100% (24/24) | 100% (24/24) mapped |
| Casos regressao bloqueados | 5/5 | 4/5 (G5 blocked-pending-data) |
| Nao regredir fixes 08/06 | 6/6 | 6/6 (todos mantidos ativos) |
| Nova dependencia stack | <2 | 1 (`cachetools>=5.5.0`) |
| Phase 11 P11-02 | 25 | 4 tasks | 1 files |
| Phase 11 P03 | 45 | 4 tasks | 4 files |
| Phase 11 P11-04 | 15 | 4 tasks | 2 files |
| Phase 12 P01 | 5 | 3 tasks | 1 files |
| Phase 12 P12-02 | 10 | 3 tasks | 4 files |
| Phase 12-retry-async-callers-com-margem P03 | 8min | 3 tasks | 1 files |
| Phase 13 P01 | 7 | 2 tasks | 2 files |
| Phase 13-leave-handler-fsm-audit-monotonico P02 | 25 | 3 tasks | 4 files |
| Phase 13-leave-handler-fsm-audit-monotonico P03 | 5min | 3 tasks | 4 files |
| Phase 13-leave-handler-fsm-audit-monotonico P04 | 20min | 3 tasks | 4 files |
| Phase 14-testes-regressao-doc-observabilidade P14-01 | 3min | 2 tasks | 1 files |
| Phase 14-testes-regressao-doc-observabilidade P02 | 5 | 2 tasks | 2 files |
| Phase 14-testes-regressao-doc-observabilidade P14-03 | 5 | 2 tasks | 1 files |

## Accumulated Context (preservado entre milestones)

### v2.0 Validated em prod (ad-hoc, sem ciclo GSD)

- Validated Lock atomico (`processing_locks` + `acquire/release/cleanup`)
- Validated Dedup universal (`send_text_uma_vez` + `OFERTA_ATIVA` + unique index conversas)
- Validated Slot-pick deterministico (build 2026-05-03 em prod)

### v2.1 Validated (entregue 20/05) — NAO REVERTER

- Validated Phase 3-4: Captura `@lid` via GROUP_PARTICIPANTS_UPDATE + MESSAGES_UPSERT (ac301fd, 6b0295b)
- Validated Phase 5: Endpoints admin `/admin/grupo/forcar-revalidacao` + `/admin/grupo/status` (207a3a9)
- Validated Phase 6: Alerta LEAD_LID + delay 180s (0e4c335)
- Validated Phase 7: qualificacao_lock multi-template antes de criar grupo (0717e1c)
- Validated Phase 8: Auth bridge JWT + Dashboard frontend `/admin/grupos` (8d9fe5c + f97686c)
- Validated Phase 9: Suite 13 testes pytest regressao (6159af5)

### Camadas defensivas grupo (18-19/05) — NAO REVERTER

- Validated Fase 1 18/05: removida presuncao `@lid=True` (4 patches: evolution.py:251, grupo_fallback.py:524, agente.py:8847, leads.py:73)
- Validated Fase 4 18/05: regra unificada probe Evolution + FSM (AND) em aquec/notif/D-1
- Validated Fix 19/05 commit ee132b9: FSM=ATIVO herdado sempre revalida via probe live
- Validated Fix 19/05: convite nativo nominal com `nome_responsavel` configuravel
- Validated Selador `qualificacao_lock.py` 18/05 (Q1+Q2+Q3+empatia ao virar agendado)
- Validated Guard webhook 18/05: nao cria lead fake se telefone desconhecido
- Validated Whitelist `safety_net` 18/05: 23 motivos
- Validated Pipeline kanban Fase 3 18/05: colunas `agendamento_confirmado` + `no_show`

### Sessao 08-09/06 — 6 fixes paliativos (NAO REVERTER, v2.2 substitui a base mas mantem estas camadas)

- Validated MIN_FLOOR_SEG 30s->180s (commit 53bd05a) — atrasa primeiro aquec pra Evolution propagar
- Validated Remove alerta grupo "lead nao entrou" (commit 07d7341)
- Validated Marker GRUPO_LEAD_ENTROU_CRIACAO + bypass probe <5min (commit 96b72cc)
- Validated Valida acesso ao grupo antes de reusar (commit 7e366bd) — fix caso Fernanda
- Validated Recoveries startup async (commit ae2b141) — fix backend bloqueado 10+ min
- Validated Recovery aquec janela 6h (commit 0d55888) — fix caso Valquiria

### Outros do dia 08/06

- Validated Reconexao instancia Rejane (bia-rejane -> rejane-leal-mentora, novo evolution_key 75818F69)
- Validated Migration RLS 003: processing_locks/convites_pendentes ENABLE + v_agendamentos_painel SECURITY INVOKER (commit 073c93f)

### Infra existente (nao reinventar em v2.2 — so ampliar)

- `app/services/lock.py` — acquire/release/cleanup (v2.0)
- `app/services/grupo_state.py` — FSM AGUARDANDO/FALLBACK_1_1/ATIVO + transition guards (v2.2 endurece em Fase 13)
- `app/services/grupo_fallback.py:177` — `ativar_fallback_se_necessario` (entry point principal; Fase 11 migra 6 callsites)
- `app/services/qualificacao_lock.py` — `popular_qs_se_faltando`
- `app/routers/grupo_webhook.py` — `GROUP_PARTICIPANTS_UPDATE` handler (Fase 10 escreve em `grupo_membership`)
- 23+ markers em `conversas` com unique constraint pra idempotencia

### Casos reais resolvidos (consultar memorias)

**v2.0/v2.1:**

- Caca 03/05, Andressa 04/05, Luciane 11/05, Vanusa 13/05, Luciane 18-19/05, Karla 20/05, Patricia 20/05

**08/06 (motivadores v2.2 — em escopo):**

- Ana Carla, Rosania, Fernanda (grupo orfao), Valquiria (recovery 47h late), Rosangela (video->texto erro user), 553891500357 (caso atual)

## Decisions Log v2.2

| Decision | Rationale | When |
|----------|-----------|------|
| Tabela dedicada `grupo_membership` em vez de marker em conversas | Relacao N:N (lead x grupo), queries por grupo_jid eficientes, suporta REMOVE/saiu_em explicito | 2026-06-09 |
| Webhook = fonte primaria, probe = fallback | v2.1 manteve probe como primario e falhou em 4+ casos do 08/06 | 2026-06-09 |
| Probe com retry exponencial 30s/2min/5min async via APScheduler | Probe sincrono nao da tempo pra Evolution propagar | 2026-06-09 |
| `max_age_seconds=600` absoluto no retry handler | Cobre Rosania + Valquiria (jobs zumbi 47h late) | 2026-06-09 |
| `instance_key` column no schema | Caso Fernanda nao regride (grupo orfao de instancia antiga) | 2026-06-09 |
| 3 paths de escrita (webhook ADD + MESSAGES_UPSERT + createGroup direct) | Caso Ana Carla repete sem Path 3 | 2026-06-09 |
| Cache in-memory `cachetools.TTLCache` (nao Redis) | Single-worker Easypanel; 5-10 probes/min; in-memory suficiente | 2026-06-09 |
| FSM `caller` argumento obrigatorio sem default | CI grep check garante audit completo | 2026-06-09 |
| GSC: prefix (not GRUPO_STATE_CHANGE:) para audit marker | Evita colisao com .like("GRUPO_STATE:%") em get_grupo_state | 2026-06-10 |
| LEFT_GROUP e estado terminal real (nao FALLBACK_1_1) | Lead saiu nao e fallback — e estado definitivo; monotonia exige terminal | 2026-06-10 |
| set_grupo_state escreve 2 markers: legacy GRUPO_STATE: + GSC: audit | Backward compat com get_grupo_state + audit trail completo | 2026-06-10 |
| Continua phase numbering — v2.2 comeca em Fase 10 | v2.1 terminou em Fase 9, timeline continua mais facil de rastrear | 2026-06-09 |
| Sem backfill retroativo de `grupo_membership` | Grupos antigos seguem com markers atuais | 2026-06-09 |
| TEST-V2-G5 (553891500357) marcado `blocked-pending-data` | User precisa fornecer trace completo do incidente | 2026-06-09 |

## Gaps / TODOs

- **TEST-V2-G5 trace pendente** — user precisa fornecer timestamps + payloads webhook + conversas do 553891500357 antes da Fase 14 fechar
- **supabase-py `on_conflict` em partial unique index** — spike de 5min antes do schema final da Fase 10; fallback e RPC function SQL
- **`instance_key` source of truth** — confirmar onde mora (`empresas.instance_key_atual` vs `config_apis.evolution_key`); pode exigir column add em Fase 10
- **Callsite exato do createGroup response (Path 3)** — identificar em kickoff Fase 10 (provavelmente `grupo_fallback.py` criacao ou helper dedicado)
- **APScheduler persistence in-memory vs Postgres jobstore** — Fase 12 decide explicitamente; default seguro e in-memory + reschedule no startup

## Next Action

1. `/gsd-plan-phase 10` — decompor Fase 10 em plans executaveis
2. Spike inicial 5min: validar supabase-py `on_conflict` em partial unique index antes do schema final
3. Confirmar `instance_key` source of truth com user
4. Execute Fase 10 — schema + 3 paths webhook write + cache

## Session Continuity

**Para retomar de outra sessao:**

- ROADMAP.md tem todas as 5 fases v2.2 com success criteria observaveis
- REQUIREMENTS.md tem traceability MEMB-* / PROBE-* / LEAVE-* / FSM-AUDIT-* / TEST-V2-* / DOC-V2-* / OBS-V2-* mapeados
- research/ tem SUMMARY + STACK + FEATURES + ARCHITECTURE + PITFALLS (consultar antes de mexer em codigo)
- Camadas defensivas 08/06 (6 fixes) — NAO REGREDIR em nenhuma fase

---

*Last updated: 2026-06-09 — Roadmap v2.2 criado, aguardando `/gsd-plan-phase 10`*
