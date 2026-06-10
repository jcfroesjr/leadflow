# Roadmap — Leadflow Platform

**Created:** 2026-05-03
**Updated:** 2026-06-09 — Milestone v2.2 (Webhook-First Grupo Membership) adicionado (Fases 10-14)

---

## Milestones

- Concluido **v1.0 MVP — Frontend v2** — Phases 1-6 (shipped 2026-04-XX)
- Concluido **v2.0 — Agente IA Atomic Processing** — Phases 1-3 (shipped ad-hoc 06/05)
- Concluido **v2.1 — Grupo WhatsApp Robusto** — Phases 3-9 (shipped 20/05)
- Em planejamento **v2.2 — Webhook-First Grupo Membership** — Phases 10-14

---

<details>
<summary>v1.0 MVP — Frontend v2 (Phases 1-6) — SHIPPED 2026-04-XX</summary>

Phases 1-6 do frontend v2 (Auth, Dashboard, Leads, Conversas, Agente IA, Pipeline+Settings) deployadas em producao em https://leadflow-frontend.bqvcbz.easypanel.host. Detalhes preservados em git history.

</details>

<details>
<summary>v2.0 — Agente IA Atomic Processing (Phases 1-3) — SHIPPED 06/05</summary>

### Phase 1: Lock Atomico + Queue (shippado ad-hoc 06/05)
**Goal:** Webhook handler processa uma mensagem por vez por (empresa_id, telefone).
**Requirements:** LOCK-01..08
**Status:** Complete (validated em prod, sem ciclo GSD)

### Phase 2: Dedup Universal + OFERTA_ATIVA (shippado ad-hoc 06/05)
**Goal:** Antes de qualquer send_text, dedup por conteudo. Slot offer unico por ciclo.
**Requirements:** DEDUP-01..04
**Status:** Complete (build em prod 06/05)

### Phase 3: Slot-Pick Deterministico (shippado ad-hoc 06/05)
**Goal:** Slot-pick sempre via OFERTA_ATIVA mais recente.
**Requirements:** SLOT-01..04
**Status:** Complete (build `2026-05-03-slot-pick-direto-numeros-vs-tokens` em prod)

### Phase 4-6 (v2.0): Diferidos
Audio Tolerance, Testes T1-T8, Doc+Observabilidade — diferidos pra milestone futuro (sem reportes desde 06/05).

</details>

<details>
<summary>v2.1 — Grupo WhatsApp Robusto (Phases 3-9) — SHIPPED 20/05</summary>

### Phase 3: Fix `@lid` Base (ac301fd)
LID-01..08 — Captura @lid via GROUP_PARTICIPANTS_UPDATE + matcher no probe.

### Phase 4: Captura `@lid` via MESSAGES_UPSERT (6b0295b)
LID-D-01..05 — Segunda fonte de captura.

### Phase 5: Endpoints Admin (207a3a9)
ADMIN-01..02 — `/admin/grupo/forcar-revalidacao` + `/admin/grupo/status`.

### Phase 6: Whitelist ANTI_SPAM_LOOP (0e4c335)
SPAM-01..02 — Convite nativo bypassa anti-spam.

### Phase 7: qualificacao_lock antes do grupo (0717e1c)
QLOCK-01 — Q1/Q2/Q3/empatia selada antes de criar grupo.

### Phase 8: Auth bridge + Dashboard `/admin/grupos` (8d9fe5c + f97686c)
ADMIN-03..04 — JWT auth bridge + frontend dashboard.

### Phase 9: Suite 13 testes pytest + Doc (6159af5)
TEST-G1..G6 + DOC-G1..G2 + OBS-G1 — Suite regressao + memorias.

Casos Karla, Crislaine, Patricia resolvidos. NAO REVERTER.

</details>

---

## v2.2 — Webhook-First Grupo Membership (Em planejamento)

**Milestone Goal:** Inverter a fonte da verdade. Webhook `GROUP_PARTICIPANTS_UPDATE` escreve em tabela materializada `grupo_membership` (primaria). Probe Evolution vira fallback com retry exponencial async + cache curto 5min. Elimina os 4+ casos persistentes de 08-09/06 (Ana Carla, Rosania, Fernanda, Valquiria + 553891500357) que os 6 fixes paliativos do 08/06 nao cobriram.

**Critical path:** Fase 10 (Schema + 3 paths webhook write + cache). Sem ela, todo o resto fica sem fundacao.

**NAO REGREDIR (camadas defensivas mantidas ativas em todas as fases v2.2):**
- AQUEC-FLOOR-01 (180s, commit 53bd05a) — defesa em profundidade contra Evolution lenta
- ALERTA-GRUPO-01 (commit 07d7341) — sem alerta dentro do grupo
- PROBE-BYPASS-01 (marker GRUPO_LEAD_ENTROU_CRIACAO, commit 96b72cc) — bypass <5min
- GRUPO-REUSO-01 (commit 7e366bd) — valida acesso ao grupo antes de reusar (caso Fernanda)
- RECOVERY-STARTUP-01 (commit ae2b141) — recoveries async no startup
- RECOVERY-AQUEC-01 (commit 0d55888) — recovery aquec janela 6h

## Phases

**Phase Numbering:**
- Integer phases (10, 11, 12, 13, 14): Planned milestone work
- Decimal phases (10.1, 11.1): Urgent insertions (marked with INSERTED)

v2.1 terminou em Phase 9 — v2.2 continua numbering em **Phase 10** (nao reseta).

- [x] **Phase 10: Schema + 3 paths webhook write + cache standalone** - Tabela `grupo_membership` com `instance_key` + UPSERT em 3 paths (webhook ADD, MESSAGES_UPSERT, createGroup direct) + cache singleton (coalescing movido pra Fase 11)
 (completed 2026-06-09)
- [x] **Phase 11: `lead_in_group()` consumer + migrar fallback callers + coalescing async** - Funcao central de leitura tabela-primeira + migra 6 callsites + asyncio.Lock coalescing
 (completed 2026-06-09)
- [x] **Phase 12: Retry async + callers com margem** - APScheduler retry exponencial 30s/2min/5min com `max_age_seconds=600` absoluto + migra callers com margem temporal
 (completed 2026-06-10)
- [x] **Phase 13: LEAVE handler + FSM audit monotonico** - Webhook REMOVE marca `saiu_em` + notif DM-first + transicoes estritamente monotonicas + audit log com `caller` obrigatorio
 (completed 2026-06-10)
- [ ] **Phase 14: Testes regressao + doc + observabilidade** - Suite pytest 5 casos motivadores + memorias + healthcheck endpoint

## Phase Details

### Phase 10: Schema + 3 paths webhook write + cache standalone
**Goal**: Fundacao webhook-first. Tabela `grupo_membership` populada em tempo real via 3 paths independentes garante que `lead_in_group()` (Fase 11) ja encontre dados confiaveis ao consultar. Cache standalone reduz pressao em Evolution sem mudar callers existentes ainda. **Coalescing async movido pra Fase 11** (materializa com consumer).
**Depends on**: Nothing (primeira fase v2.2 — fundacao)
**Requirements**: MEMB-01, MEMB-02, MEMB-03, MEMB-04, MEMB-06, PROBE-CACHE-01
**Success Criteria** (what must be TRUE):
  1. Lead que entra via `POST /group/create` tem row em `grupo_membership` em <1s sem aguardar webhook (Path 3 — caso Ana Carla resolvido na fundacao)
  2. Tabela `grupo_membership` tem coluna `instance_key` populada em todos os writes; query por instancia antiga retorna vazio quando empresa migrou (caso Fernanda nao regride)
  3. Webhook `GROUP_PARTICIPANTS_UPDATE action=add` faz UPSERT idempotente comparando `messageTimestamp` do payload (re-delivery nao duplica linha; out-of-order respeitado)
  4. Cache singleton `cachetools.TTLCache(maxsize=512, ttl=300)` + write-through invalidate em todo UPSERT (Pitfall 2: cache mascarando falha de persistencia eliminado)
  5. RLS service_role-only ativo desde o deploy inicial — INSERT via anon key retorna 0 rows (verificavel via teste)
**Plans**: 5 plans
- [x] 10-01-PLAN.md — Wave 0 pre-deps: confirmar cachetools + localizar Path 2 callsite + parse messageTimestamp shape
- [x] 10-02-PLAN.md — Wave 1 foundation: migration 004 (tabela + RLS + RPC) + helper upsert_grupo_membership + cache singleton
- [x] 10-03-PLAN.md — Wave 2 Path 1: webhook GROUP_PARTICIPANTS_UPDATE add → UPSERT em grupo_membership
- [x] 10-04-PLAN.md — Wave 2 Paths 2+3: MESSAGES_UPSERT @lid capture + createGroup direct write (caso Ana Carla)
- [x] 10-05-PLAN.md — Wave 3 tests + healthcheck skinny + BUILD_VERSION bump + smoke RLS manual

### Phase 11: `lead_in_group()` consumer + migrar fallback callers + coalescing async
**Goal**: Inverter fonte da verdade nos callers criticos. Funcao central `lead_in_group()` consulta `grupo_membership` PRIMEIRO; probe Evolution so roda como fallback. Migra os 6 callsites de `verificar_lead_no_grupo` em `grupo_fallback.py` (linhas 251, 311, 337, 477, 624, 1173, 1256) para usar o novo consumer. Coalescing async via `asyncio.Lock` por chave materializa AQUI (movido da Fase 10), junto do consumer que dispara probes concorrentes.
**Depends on**: Phase 10 (tabela + writes funcionando)
**Requirements**: MEMB-05, PROBE-COALESCE-01
**Success Criteria** (what must be TRUE):
  1. `lead_in_group(empresa_id, telefone, grupo_jid, lid)` retorna `{in_group, source, last_event_at, instance_key_match}` consultando `grupo_membership` PRIMEIRO; so vai pro probe se row ausente OU `saiu_em != null`
  2. Janela stale: se grupo criado <6min atras E sem row, fallback retorna `pending` (nao concluivo) em vez de False — permite Fase 12 enfileirar retry
  3. Os 6 callsites em `grupo_fallback.py` chamam `lead_in_group()` em vez de `verificar_lead_no_grupo` direto; probe direto so permanece em endpoint admin para diagnostico
  4. Quando `instance_key_match=False`, funcao trata como grupo orfao (caso Fernanda) e retorna sentinel que permite ao caller decidir criar novo grupo
  5. `asyncio.Lock` por chave evita probe concorrente: 3 jobs paralelos pro mesmo grupo disparam 1 unica chamada HTTP Evolution (PROBE-COALESCE-01)
  6. Logs `[MEMB-LOOKUP] source={membership|cache|probe|stale} grupo={jid} verdict={...}` aparecem em todas as consultas
**Plans**: 4 plans
- [x] 11-01-PLAN.md — Wave 1 foundation: lead_in_group() consumer + decision tree + asyncio.Lock coalescing per-chave em grupo_membership.py
- [x] 11-02-PLAN.md — Wave 2 migracao: 7 substituicoes mecanicas em grupo_fallback.py (linhas 251/311/337/477/624/1173/1256) preservando PROBE-BYPASS-01 + ALERTA-GRUPO-01
- [x] 11-03-PLAN.md — Wave 3 tests: 7 testes decision tree + 3 testes coalescing + 8 testes CI grep migration
- [x] 11-04-PLAN.md — Wave 4 deploy: BUILD_VERSION bump + healthcheck endpoint estendido + smoke prod (CHECKPOINT)

### Phase 12: Retry async + callers com margem
**Goal**: Probe negativo inicial NAO conclui definitivo — enfileira retry async via APScheduler em 30s/2min/5min com `max_age_seconds=600` absoluto. Resolve race timing (caso Rosania T+138s) e evita jobs zumbi (caso Valquiria 47h late). Migra callers com margem temporal (notif pre-reuniao, timeout 30min FALLBACK) para usar retry async; aquec mantem sincrono mas consulta `grupo_membership` primeiro.
**Depends on**: Phase 11 (`lead_in_group` existir)
**Requirements**: PROBE-RETRY-01, PROBE-RETRY-02
**Success Criteria** (what must be TRUE):
  1. Probe negativo inicial nao conclui — enfileira retry async via APScheduler `add_job(trigger='date', run_date=NOW+30s)` com `id=f"probe_retry:{grupo_jid}:{telefone}:{attempt}"` + `replace_existing=True`
  2. Retry handler verifica `now - enqueued_at < max_age_seconds (600s)` antes de executar; job velho descartado com log `[JOB_EXPIRED]` (caso Valquiria nao regride mesmo com retry adicionado)
  3. Webhook que chegar entre tentativas (caso Rosania T+138s) faz retry consultar tabela primeiro, encontrar row, encerrar com sucesso silencioso sem chamar Evolution
  4. Notif D-1 (`confirmacao_agendamento.py:291`) e notif pre-reuniao (`warmup_grupo.py`) migrados para `schedule_retry_on_negative=True`; aquec mantem sincrono (decisao "AGORA"). NOTA (research): `_executar_timeout_grupo_aguardando` NAO tem probe — so transiciona FSM; o segundo caller-com-margem real e a notif do warmup.
  5. APScheduler em modo in-memory explicito (jobs perdidos em restart sao re-enfileirados via recovery startup baseado em estado DB)
  6. `asyncio.create_task` naked PROIBIDO no retry path — todos os agendamentos passam por `scheduler.add_job` (evita silent task drop)
**Plans**: 3 plans
- [x] 12-01-PLAN.md — Wave 1: schedule_probe_retry() + _probe_retry_job() (max_age guard + table-first) + ativacao stub no STEP 5 de lead_in_group (PROBE-RETRY-01)
- [x] 12-02-PLAN.md — Wave 2: migra 2 callers com margem (confirmacao D-1 + notif warmup) + recovery startup; aquec mantem sincrono (PROBE-RETRY-02)
- [x] 12-03-PLAN.md — Wave 3: suite pytest test_probe_retry.py (Validation Architecture: scheduling, max_age Valquiria, table-first Rosania, callers)

### Phase 13: LEAVE handler + FSM audit monotonico
**Goal**: Fechar o ciclo de vida da membership. Webhook REMOVE marca `saiu_em` + insere marker `LEAD_SAIU_GRUPO`. Notif pre-reuniao e D-1 detectam `saiu_em != null` e redirecionam pro DM (nao grupo vazio). FSM transicoes estritamente monotonicas com argumento `caller` obrigatorio sem default — toda transicao gera audit log `GSC:{from}:{to}:{reason}:{caller}` em conversas.
**Depends on**: Phase 10 (webhook handler existir), Phase 11 (`lead_in_group` consumir `saiu_em`)
**Requirements**: LEAVE-01, LEAVE-02, LEAVE-03, FSM-AUDIT-01, FSM-AUDIT-02, FSM-AUDIT-03
**Success Criteria** (what must be TRUE):
  1. Webhook `GROUP_PARTICIPANTS_UPDATE action=remove` marca `grupo_membership.saiu_em = messageTimestamp` + insere marker `LEAD_SAIU_GRUPO:{grupo_jid}` em conversas (idempotente — sem `{ts}`, ts persiste em saiu_em) [amenda 2026-06-09]
  2. Notif pre-reuniao e D-1 detectam `saiu_em != null` via `lead_in_group()` E enviam confirmacao via DM (nao grupo vazio) — caso lead-saiu nao perde confirmacao
  3. FSM transicao `ATIVO->AGUARDANDO` BLOQUEADA sem flag `force=True` (so endpoint admin pode forcar); tentativas registram audit `BLOCKED:{reason}` mas nao mudam estado
  4. `set_grupo_state()` exige argumento `caller` obrigatorio sem default — CI grep check garante que nenhum chamador passa "unknown" ou omite
  5. Toda transicao FSM grava marker `GSC:{ag_id}:{from}:{to}:{reason}:{caller}` em conversas (prefixo `GSC:` evita colisao com `.like("GRUPO_STATE:%")`); query do dashboard `/admin/grupos` (`?timeline=true`) exibe timeline auditavel [amenda 2026-06-09]
  6. Lead que saiu volta pra FSM `LEFT_GROUP` (novo estado terminal naquele agendamento); flag `LEFT_GROUP` no marker GSC diferencia de timeout normal
**UI hint**: yes
**Plans**: 4 plans
- [x] 13-01-PLAN.md — Wave 1 foundation: FSM monotonico (STATE_LEFT_GROUP + ALLOWED_TRANSITIONS) + caller obrigatorio + marker audit GSC: (FSM-AUDIT-01/02)
- [x] 13-02-PLAN.md — Wave 2 LEAVE handler: webhook REMOVE marca saiu_em + LEAD_SAIU_GRUPO + FSM LEFT_GROUP + lead_in_group source='left_group' + D-1/notif DM redirect (LEAVE-01/02/03)
- [x] 13-03-PLAN.md — Wave 2 migracao: 7 callsites set_grupo_state/transition_grupo_state com reason+caller + sweep script (FSM-AUDIT-03)
- [x] 13-04-PLAN.md — Wave 3 tests + dashboard: test_fsm_monotonic + test_fsm_caller_ci + test_leave_handler + left_group decision + ?timeline=true em /admin/grupo/status

### Phase 14: Testes regressao + doc + observabilidade
**Goal**: Bloquear regressao dos 5 casos motivadores via suite pytest. Documentacao consolidada em memoria. Healthcheck endpoint detecta cache mascarando falha de persistencia. Conclui o ciclo: ninguem mexe em v2.2 sem que os 5 casos sigam protegidos.
**Depends on**: Phase 10, 11, 12, 13 (toda a infra)
**Requirements**: TEST-V2-G1, TEST-V2-G2, TEST-V2-G3, TEST-V2-G4, TEST-V2-G5, DOC-V2-G1, DOC-V2-G2, OBS-V2-G1, OBS-V2-G2
**Success Criteria** (what must be TRUE):
  1. 5/5 casos regressao passing: TEST-V2-G1 (Ana Carla — Path 3 createGroup), TEST-V2-G2 (Rosania — retry async com max_age=600s), TEST-V2-G3 (Fernanda — instance_key mismatch), TEST-V2-G4 (Valquiria — job retry descartado por max_age)
  2. TEST-V2-G5 (553891500357) marcado `blocked-pending-data` ate user fornecer trace completo (timestamps + payloads webhook + conversas); test stub criado mas pulado em CI ate dados chegarem
  3. Memoria nova `sessao_2026-06-XX_grupo_membership_v2.md` + `grupo_membership_arquitetura.md` documentam inversao webhook-first; `agente_referencia_compilada.md` atualizado com tabela + `lead_in_group()` + retry async + FSM audit
  4. Endpoint `/health/grupo-membership` retorna `{total_rows_24h, last_write_at, cache_size, cache_hit_rate, writes_per_source}` — operador detecta cache mascarando falha de persistencia (0 inserts via webhook por 30min em horario ativo gera alerta)
  5. Logs estruturados `[MEMB-WRITE] source={webhook|createGroup|messages_upsert}`, `[MEMB-LOOKUP]`, `[PROBE-RETRY]`, `[GRUPO-STATE-CHANGE]` aparecem em todos os fluxos novos
  6. 13 testes pytest da v2.1 (commit 6159af5) continuam passing (nao regredidos) + 5 novos = suite completa de 18 testes roda em <60s
**Plans**: 3 plans
- [x] 14-01-PLAN.md — Wave 1: suite regressao test_v2_regression.py (4 pass + 1 skip G5) + source-audit dos 4 log markers (TEST-V2-G1..G5, OBS-V2-G1)
- [ ] 14-02-PLAN.md — Wave 1: healthcheck +cache_hit_rate +total_rows_24h + BUILD_VERSION bump 2026-06-10-v2-2-completo (OBS-V2-G2)
- [ ] 14-03-PLAN.md — Wave 2: doc in-repo grupo_membership_v2.md + checklist memorias + gate suite completa 113 testes (DOC-V2-G1/G2)

## Progress

**Execution Order:**
Phases execute in numeric order: 10 -> 11 -> 12 -> 13 -> 14

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 10. Schema + 3 paths webhook write + cache standalone | 5/5 | Complete    | 2026-06-09 |
| 11. `lead_in_group()` consumer + migrar fallback callers | 4/4 | Complete    | 2026-06-09 |
| 12. Retry async + callers com margem | 3/3 | Complete    | 2026-06-10 |
| 13. LEAVE handler + FSM audit monotonico | 4/4 | Complete    | 2026-06-10 |
| 14. Testes regressao + doc + observabilidade | 1/3 | In Progress|  |

## Phase Order Rationale (v2.2)

1. **Phase 10 primeiro (CRITICAL PATH)** — Schema + 3 paths de escrita sao fundacao. Sem dados na tabela, nada do resto funciona. Cache + coalescing standalone (sem callers ainda) — zero risco de regressao na inversao. **Insight critico: Path 3 (createGroup direct write) resolve caso Ana Carla mesmo antes do consumer existir.**
2. **Phase 11 depois** — `lead_in_group()` consumer migra os callers internos de `grupo_fallback.py` (auto-contidos, alto trafego, validacao rapida em <24h em prod).
3. **Phase 12** — Retry assincrono so faz sentido com `lead_in_group()` ja em uso. Callers com margem temporal (notif, timeout) ganham `schedule_retry_on_negative=True`; aquec mantem sincrono.
4. **Phase 13** — LEAVE handler + FSM audit. Adiciona complexidade nova (saiu_em consumers + estado LEFT_GROUP). Resolver entrada (Fases 10-12) primeiro elimina 80% dos casos motivadores.
5. **Phase 14** — Testes + doc + observabilidade consolidam. Suite roda contra arquitetura final, nao mid-state (licao do v2.1 commit 6159af5).

---

## Proximo passo imediato

```
/gsd-plan-phase 10
```

Gera plano detalhado da Fase 10 (schema + 3 paths webhook write + cache standalone).

---

*Roadmap criado: 2026-05-03 — milestone v2.0*
*Atualizado: 2026-05-20 — milestone v2.1 Grupo Robusto (Fases 3-9)*
*Atualizado: 2026-06-09 — milestone v2.2 Webhook-First (Fases 10-14)*
