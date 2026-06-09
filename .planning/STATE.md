# Project State

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Milestone v2.2 iniciado — pesquisa de domínio em curso
Last activity: 2026-06-09 — Milestone v2.2 (Webhook-First) iniciado

## Active Milestone

**v2.2 — Identificação Definitiva de Lead no Grupo (Webhook-First)**

**Goal:** Inverter a fonte da verdade. Webhook GROUP_PARTICIPANTS_UPDATE escreve em tabela materializada `grupo_membership` (primária). Probe Evolution vira fallback com retry exponencial + cache curto.

**Phases planejadas:** começam em Fase 10 (continua numbering — v2.1 terminou em Fase 9).

**Casos motivadores (sessão 08-09/06):**

- Ana Carla 5514998151089 (08/06 08:31) — entrou direto na createGroup, probe T+60s viu False, aquec foi pro DM
- Rosânia 5562984551622 (08/06 23:57) — webhook chegou T+138s, aquec já tinha falhado em T+60s
- Fernanda 5551999532715 (07/06) — grupo órfão de instância antiga (bia-rejane) reusado
- Valquíria 5582981291203 (06/06) — aquec #4 falhou, recovery reagendou 47h depois (corrigido em 0d55888 mas é palilativo)
- 553891500357 (09/06) — caso reportado pelo user, persiste mesmo após 6 fixes

## Accumulated Context (preservado entre milestones)

### v2.0 Validated em prod (ad-hoc, sem ciclo GSD)

- ✅ Lock atômico (`processing_locks` + `acquire/release/cleanup`)
- ✅ Dedup universal (`send_text_uma_vez` + `OFERTA_ATIVA` + unique index conversas)
- ✅ Slot-pick determinístico (build 2026-05-03 em prod)

### v2.1 Validated (entregue 20/05) — NÃO REVERTER

- ✅ Phase 3-4: Captura `@lid` via GROUP_PARTICIPANTS_UPDATE + MESSAGES_UPSERT (ac301fd, 6b0295b)
- ✅ Phase 5: Endpoints admin `/admin/grupo/forcar-revalidacao` + `/admin/grupo/status` (207a3a9)
- ✅ Phase 6: Alerta LEAD_LID + delay 180s (0e4c335)
- ✅ Phase 7: qualificacao_lock multi-template antes de criar grupo (0717e1c)
- ✅ Phase 8: Auth bridge JWT + Dashboard frontend `/admin/grupos` (8d9fe5c + f97686c)
- ✅ Phase 9: Suite 13 testes pytest regressão (6159af5)

### Camadas defensivas grupo (18-19/05) — NÃO REVERTER

- ✅ Fase 1 18/05: removida presunção `@lid=True` (4 patches: evolution.py:251, grupo_fallback.py:524, agente.py:8847, leads.py:73)
- ✅ Fase 4 18/05: regra unificada probe Evolution + FSM (AND) em aquec/notif/D-1
- ✅ Fix 19/05 commit ee132b9: FSM=ATIVO herdado sempre revalida via probe live
- ✅ Fix 19/05: convite nativo nominal com `nome_responsavel` configurável
- ✅ Selador `qualificacao_lock.py` 18/05 (Q1+Q2+Q3+empatia ao virar agendado)
- ✅ Guard webhook 18/05: não cria lead fake se telefone desconhecido
- ✅ Whitelist `safety_net` 18/05: 23 motivos
- ✅ Pipeline kanban Fase 3 18/05: colunas `agendamento_confirmado` + `no_show`

### Sessão 08-09/06 — 6 fixes paliativos (NÃO REVERTER, v2.2 substitui a base mas mantém estas camadas)

- ✅ MIN_FLOOR_SEG 30s→180s (commit 53bd05a) — atrasa primeiro aquec pra Evolution propagar
- ✅ Remove alerta grupo "lead não entrou" (commit 07d7341)
- ✅ Marker GRUPO_LEAD_ENTROU_CRIACAO + bypass probe <5min (commit 96b72cc)
- ✅ Valida acesso ao grupo antes de reusar (commit 7e366bd) — fix caso Fernanda
- ✅ Recoveries startup async (commit ae2b141) — fix backend bloqueado 10+ min
- ✅ Recovery aquec janela 6h (commit 0d55888) — fix caso Valquíria

### Outros do dia 08/06

- ✅ Reconexão instância Rejane (bia-rejane → rejane-leal-mentora, novo evolution_key 75818F69)
- ✅ Migration RLS 003: processing_locks/convites_pendentes ENABLE + v_agendamentos_painel SECURITY INVOKER (commit 073c93f)

### Infra existente (não reinventar em v2.2 — só ampliar)

- `app/services/lock.py` — acquire/release/cleanup (v2.0)
- `app/services/grupo_state.py` — FSM AGUARDANDO/FALLBACK_1_1/ATIVO + transition guards (v2.2 endurece)
- `app/services/grupo_fallback.py:177` — `ativar_fallback_se_necessario` (entry point principal)
- `app/services/qualificacao_lock.py` — `popular_qs_se_faltando`
- `app/routers/grupo_webhook.py` — `GROUP_PARTICIPANTS_UPDATE` handler (v2.2 escreve em `grupo_membership`)
- 23+ markers em `conversas` com unique constraint pra idempotência

### Casos reais resolvidos (consultar memórias)

**v2.0/v2.1:**
- Caca 03/05, Andressa 04/05, Luciane 11/05, Vanusa 13/05, Luciane 18-19/05, Karla 20/05, Patrícia 20/05

**08/06 (motivadores v2.2):**
- Ana Carla, Rosânia, Fernanda (grupo órfão), Valquíria (recovery 47h late), Rosângela (vídeo→texto erro user), 553891500357 (caso atual)

## Next Action

1. Spawn 4 researchers em paralelo (Stack/Features/Architecture/Pitfalls)
2. Synthesize → SUMMARY.md
3. Definir REQUIREMENTS.md v2.2
4. Spawn roadmapper → ROADMAP.md (começa Fase 10)
5. Aguardar aprovação user → `/gsd-plan-phase 10`

---

*Last updated: 2026-06-09 — milestone v2.2 (Webhook-First) iniciado, research em curso*
