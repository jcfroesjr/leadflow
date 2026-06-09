# Leadflow Platform

## What This Is

Plataforma SaaS de qualificação e agendamento automatizado de leads via WhatsApp. Composta por:
- **Backend FastAPI** (Python) com agente IA (Bia) que conduz qualificação Q1/Q2, oferta de horários e agendamento via Google Calendar + Zoom
- **Frontend v2** (React 19 + TypeScript + Tailwind + shadcn/ui) com Dashboard, Leads, Conversas, Pipeline, Agente IA, Configurações
- **Integrações**: Supabase (Postgres), Evolution API (WhatsApp), Google Calendar OAuth, OpenAI Whisper, OpenAI/Gemini LLMs
- **Deploy**: Easypanel (Docker) na Hostinger VPS

Empresa única em produção hoje (Rejane Leal Mentora). Arquitetura SaaS multi-tenant ready (campo `empresa_id` em todas as entidades; configs por empresa em `config_agendamento`/`config_ia`/`config_apis`).

## Core Value

Lead preenche formulário externo → webhook cria lead no Leadflow → agente IA qualifica via WhatsApp → oferece horários reais do calendário → agenda evento + cria reunião Zoom + cria grupo WhatsApp com lead+mentor → segue follow-up automático até conversão ou desinteresse.

**Operador (admin)** entra no frontend, vê leads/conversas em tempo real, configura prompt e horários, monitora pipeline, sem abrir outras ferramentas.

## Current Milestone: v2.2 Identificação Definitiva de Lead no Grupo (Webhook-First)

**Goal:** Eliminar falsos negativos persistentes do probe Evolution invertendo a fonte da verdade — webhook `GROUP_PARTICIPANTS_UPDATE` torna-se primário via tabela materializada `grupo_membership`, probe Evolution vira fallback com retry exponencial + cache curto.

**Target features:**
- Tabela `grupo_membership` (grupo_jid, telefone, @lid, entrou_em, saiu_em) — fonte primária consultada antes do probe
- Probe Evolution com retry exponencial (30s/2min/5min) — false negative inicial não conclui
- Cache de resultado de probe (5min TTL) — evita bombardear API quando múltiplos jobs consultam mesmo grupo
- Handler webhook LEAVE/REMOVE — lead que sai dispara notif via DM, FSM marca `LEFT_GROUP`
- FSM transições estritamente monotônicas + audit log (`GRUPO_STATE_CHANGE:{from}:{to}:{reason}`)
- Suite testes regressão pros 5 casos do dia 08/06 (Ana Carla, Rosânia, Fernanda, Valquíria, 553891500357)

**Causa-raiz reaberta (sessão 08-09/06):** v2.1 entregou captura `@lid` + endpoints admin + 13 testes. Casos Karla/Crislaine/Patrícia resolvidos. **Mas** v2.1 manteve probe Evolution como fonte primária com `@lid` como matcher alternativo. Quando Evolution mente ou demora (caso comum: 60-180s pra propagar membros), todos os patches caem. Os 6 fixes do dia 08/06 (floor 180s, sem alerta, valida reuso, recovery 6h, etc) são paliativos sobre a mesma base não-confiável. Esta milestone inverte: webhook é fonte primária, probe é backup com retry.

**Histórico v2.1 (Grupo Robusto):** Fases 3-9 entregues (commits ac301fd, 6b0295b, 207a3a9, 0e4c335, 0717e1c, 8d9fe5c, f97686c, 6159af5). Suite 13 testes pytest commitada. Casos Karla/Crislaine/Patrícia resolvidos. Out-of-scope `leads.lid_whatsapp` mantido (marker em conversas) — v2.2 usa tabela dedicada `grupo_membership` em vez de coluna no leads.

**Histórico v2.0 (Agente IA Atomic Processing):** Phases 1-2 (Lock Atômico + Dedup Universal) shippadas ad-hoc 06/05. Phase 3 (OFERTA_ATIVA + slot-pick determinístico) em prod. Phase 4 (Whisper) + T1-T8 reabertos se ressurgirem.

**Sessão 08-09/06 — 6 fixes paliativos preservar (não reverter):** Floor 30s→180s (53bd05a), Remove alerta grupo (07d7341), Marker GRUPO_LEAD_ENTROU_CRIACAO + bypass probe < 5min (96b72cc), Grupo reuso valida acesso (7e366bd), Recoveries startup async (ae2b141), Recovery aquec janela 6h (0d55888). RLS hardening migration 003 (073c93f). Reconexão instância Rejane (bia-rejane→rejane-leal-mentora) sem commit.

## Requirements

### Validated (já em produção)

- ✓ Webhook lead-criação (`/webhook/{empresa_id}/{token}`) — recebe payload, cria lead, dispara Q1
- ✓ Agente IA conduz Q1 (apresentação) e Q2 (validação desafio) com templates configuráveis
- ✓ Empathy template + busca de slots após Q2-confirm (passo 3)
- ✓ Tool calling Gemini/OpenAI (`buscar_horarios_livres`, `criar_agendamento`)
- ✓ FSM de fases (novo → q1_enviado → q2_enviado → qualificado → slots_oferecidos → agendado/nao_convertido)
- ✓ 4 camadas de defesa de slots: ANTI-ANUNCIO → SLOTS-RESCUE → FILLUP → ULTRA-FALLBACK
- ✓ SLOT-OVERRIDE: força slot_token correto se LLM ignorar INSTRUCAO
- ✓ Slot-pick com day+hour matching direto de números
- ✓ MSG_PROCESSED dedup por message_id da Evolution
- ✓ Áudio: detector amplo (path 1-4) + Whisper transcription + HTTP 201 aceito
- ✓ Follow-ups Não Agendados: cutoff dinâmico por empresa, tolerância overdue 48h, recovery 14d, retomar-stuck endpoint, time-based nao_convertido com atraso configurável
- ✓ Despedida educada (OPT-OUT, MENU-ENC, PAUSA-INDEF) antes de mudar status terminal
- ✓ SYNC com variantes BR phone (12 e 13 dígitos)
- ✓ Aquecimento de grupo: ordem garantida +5s, suporte audio/pdf, AquecimentoEditor com auto-save
- ✓ Confirmação 24h antes da reunião (grupo + 1-1 fallback)
- ✓ Reagendamento + no-show detection
- ✓ Frontend v2 deployado: Dashboard, Leads, Conversas, Pipeline, Agente IA, Configurações com dados reais
- ✓ FollowupEditor + AquecimentoEditor com upload mídia + DelayPicker

### Validated (shippado ad-hoc em prod durante sessões 04-06/05, sem ciclo GSD)

- ✓ **LOCK-01..04**: Tabela `processing_locks` + acquire/release/cleanup em `app/services/lock.py`, integrada no webhook em prod desde 06/05
- ✓ **DEDUP-01..03**: `send_text_uma_vez` + marker `OFERTA_ATIVA` + unique index conversas em prod
- ✓ **SLOT-01..02**: Slot-pick direto nums vs tokens (build `2026-05-03-slot-pick-direto-numeros-vs-tokens`)

### Validated (sessões 18-19/05, grupo WhatsApp camadas defesa)

- ✓ Fase 1 grupo 18/05: removida presunção `@lid=True` em `verificar_lead_no_grupo` + revalidação em 3 paths que não validavam (commits 4 patches)
- ✓ Fase 4 18/05: regra unificada probe Evolution + FSM (AND) nos 3 sistemas (aquec, notif, confirmação D-1)
- ✓ FSM bypass fix 19/05: `FSM=ATIVO` herdado sempre revalida via probe live
- ✓ Convite nativo nominal 19/05: descrição com `nome_responsavel` configurável por empresa
- ✓ Selador qualificação `qualificacao_lock.py` 18/05 (Q1+Q2+Q3+empatia ao virar agendado)
- ✓ Guard webhook 18/05: não cria lead fake se telefone desconhecido
- ✓ Whitelist `safety_net` 18/05: 23 motivos (autoresposta WA Business etc)
- ✓ Pipeline kanban Fase 3 18/05: colunas `agendamento_confirmado` + `no_show` com auto-move via D-1

### Validated (Milestone v2.1 — entregue 20/05)

- ✓ **LID-01..05**: Captura `@lid` via webhook GROUP_PARTICIPANTS_UPDATE + MESSAGES_UPSERT + helper `_get_lead_lid_for_group` + backfill manual (commits ac301fd, 6b0295b)
- ✓ **ADMIN-01..02**: Endpoints `/admin/grupo/forcar-revalidacao` + `/admin/grupo/status` + auth bridge JWT (commits 207a3a9, 8d9fe5c)
- ✓ **SPAM-01..02**: Whitelist `enviar_convite_grupo` em ANTI_SPAM_LOOP + delay 180s alerta (commit 0e4c335)
- ✓ **QLOCK-01**: `qualificacao_lock` multi-template selada antes de criar grupo (commit 0717e1c)
- ✓ **TEST-G1..G5 + DOC-G1**: 13 testes pytest commitados (suite regressão) + frontend dashboard `/admin/grupos` (commits f97686c + 6159af5)

### Validated (Sessão 08/06 — 6 fixes paliativos do problema raiz que v2.2 vai resolver)

- ✓ **AQUEC-FLOOR-01**: MIN_FLOOR_SEG aumentado 30s→180s pra Evolution propagar membros (commit 53bd05a)
- ✓ **ALERTA-GRUPO-01**: Remove envio de alerta "lead não entrou" dentro do grupo (commit 07d7341)
- ✓ **PROBE-BYPASS-01**: Marker `GRUPO_LEAD_ENTROU_CRIACAO` bypassa probe se <5min (commit 96b72cc)
- ✓ **GRUPO-REUSO-01**: Valida acesso ao grupo antes de reusar (caso Fernanda, commit 7e366bd)
- ✓ **RECOVERY-STARTUP-01**: Recoveries do startup async pra não bloquear Uvicorn (commit ae2b141)
- ✓ **RECOVERY-AQUEC-01**: Recovery aquec descarta items pendentes >6h do START (commit 0d55888)
- ✓ **RLS-HARD-01**: Migration 003 — RLS em processing_locks/convites_pendentes + SECURITY INVOKER em v_agendamentos_painel (commit 073c93f)

### Active (Milestone v2.2 — Webhook-First)

- [ ] **MEMB-01**: Migration `grupo_membership` (grupo_jid, telefone, lid, entrou_em, saiu_em, criado_em, atualizado_em) + indexes
- [ ] **MEMB-02**: Webhook GROUP_PARTICIPANTS_UPDATE escreve row em `grupo_membership` (UPSERT por grupo_jid+telefone), eventos ADD/REMOVE
- [ ] **MEMB-03**: Webhook MESSAGES_UPSERT (msg do lead no grupo) UPSERT em `grupo_membership` quando match @lid + grupo aguardando
- [ ] **MEMB-04**: Função `lead_in_group(empresa_id, telefone, grupo_jid)` consulta `grupo_membership` PRIMEIRO; só vai pro probe Evolution se row ausente OU saiu_em != null
- [ ] **PROBE-RETRY-01**: `verificar_lead_no_grupo` ganha modo `retry_async=True` que enfileira retry em 30s/2min/5min via APScheduler antes de concluir negativo definitivo
- [ ] **PROBE-CACHE-01**: Cache em memória (TTL 5min) por chave `(grupo_jid, telefone, lid)` — múltiplos callers no mesmo job dispatch compartilham resultado
- [ ] **LEAVE-01**: Handler webhook REMOVE marca `grupo_membership.saiu_em` + insere marker `LEAD_SAIU_GRUPO:{jid}` em conversas
- [ ] **LEAVE-02**: Notif pré-reunião e D-1 detectam `saiu_em != null` E vai pro DM (não grupo vazio)
- [ ] **FSM-AUDIT-01**: `set_grupo_state` valida transição estritamente monotônica (AGUARDANDO→ATIVO ok; ATIVO→AGUARDANDO BLOQUEADO sem flag de override)
- [ ] **FSM-AUDIT-02**: Toda transição grava `GRUPO_STATE_CHANGE:{from}:{to}:{reason}:{caller}` em conversas (audit log)
- [ ] **TEST-V2-G1**: Caso Ana Carla 08/06 — lead adicionado direto em createGroup, FSM=ATIVO em <60s sem precisar probe live
- [ ] **TEST-V2-G2**: Caso Rosânia 08/06 — webhook GROUP_PARTICIPANTS_UPDATE chega T+138s, sistema espera (probe retry) em vez de cair pro DM
- [ ] **TEST-V2-G3**: Caso Fernanda 07/06 — grupo órfão de instância antiga detectado em `lead_in_group` E novo grupo criado automático
- [ ] **TEST-V2-G4**: Caso Valquíria 06/06 — aquec recovery não dispara item velho (cobertura adicional ao RECOVERY-AQUEC-01)
- [ ] **TEST-V2-G5**: Caso 553891500357 09/06 — reprodução completa (passo a passo do incidente)
- [ ] **DOC-V2-G1**: Atualizar `agente_ia_fixes.md` + criar `grupo_membership_arquitetura.md` em memory

### Out of Scope (milestone v2.2)

- Coluna `leads.lid_whatsapp` (tabela dedicada `grupo_membership` substitui — relação N:N lead × grupo)
- Reescrita do FSM AGUARDANDO/FALLBACK_1_1/ATIVO — só endurecer transições + audit log
- Multi-instance backend (segue out-of-scope do v2.0/v2.1)
- Redis pra cache de probe — in-memory é suficiente (single-worker no Easypanel)
- Eventos webhook Evolution adicionais além de GROUP_PARTICIPANTS_UPDATE, MESSAGES_UPSERT, CONNECTION_UPDATE, MESSAGES_UPDATE (já usados)
- Reescrita do probe Evolution em si — só adicionar retry+cache em volta
- Backfill retroativo de `grupo_membership` pra grupos antigos — só registra a partir do deploy (grupos antigos seguem com markers atuais)

## Context

**Backend** em `c:/Projetos/Leadflow/leadflow-backend` (Python 3.13 + FastAPI + APScheduler + supabase-py + httpx). Single-instance no Easypanel (1 worker). Build atual em prod: `2026-05-03-slot-pick-direto-numeros-vs-tokens`.

**Frontend** em `c:/Projetos/Leadflow/leadflow-frontend` (React 19 + TypeScript + Tailwind + shadcn/ui). Deployado em https://leadflow-frontend.bqvcbz.easypanel.host.

**Supabase** (Postgres): tabelas `leads`, `conversas`, `agendamentos`, `empresas`, `membros`, `webhooks`, `calendario_tokens`.

**Defeitos observados (sessão 03/05):**
- Lead Caca: 13 mensagens do bot em 7s, agendou em horário errado
- Lead Andressa: bullets sem [SLOTS_TOKENS:] salvos
- Lead Jakeline: LLM hallucinou "probleminha técnico" e bot ficou em silêncio
- Lead Magda: áudio ignorado por detector incompleto
- Lead Ariélle: nao_convertido marcado sem despedida (NameError silencioso)

Detalhes em `c:/Projetos/Leadflow/ANALISE_DETALHADA_DEFEITOS.md` (11 defeitos, casos reais, plano T1-T8).

## Constraints

- **Stack backend**: Python/FastAPI/APScheduler — não migrar
- **Single-instance**: 1 worker no Easypanel — locks podem ser DB-based (Postgres advisory lock ou tabela com unique constraint)
- **Backwards compat**: Não regredir os 10 commits de defesa (camadas válidas)
- **Multi-tenant**: Toda lógica deve trabalhar com `empresa_id` — sem hardcode da Rejane
- **Deploy**: Easypanel via Dockerfile — sem migrações zero-downtime obrigatórias hoje

## Key Decisions

### v2.0 (validated em prod)

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Lock em tabela Postgres com unique constraint | Mais simples que Redis; postgres já é dependência | ✓ shippado 06/05 |
| Queue em markers `QUEUED:{msg_id}` em conversas | Reusa tabela existente; sem nova infra | ✓ shippado 06/05 |
| TTL 60s + cleanup job periódico | Previne deadlock de lock órfão | ✓ shippado 06/05 |
| Dedup window de 30s pra mensagens idênticas | Curto suficiente pra não bloquear retry legítimo | ✓ shippado 06/05 |
| OFERTA_ATIVA window de 2min | Lead que demora pra responder não gera 2 ofertas | ✓ shippado 06/05 |
| Não migrar pra Redis | Postgres handle 1 worker single-instance bem | ✓ validado em prod |

### v2.1 (Grupo Robusto — entregue 20/05)

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| `@lid` persistido como marker `LEAD_LID` em conversas (não coluna em leads) | Reusa tabela + unique constraint pra idempotência; evita migration | ✓ shippado |
| Probe Evolution aceita `lead_lid` opcional como matcher alternativo | Mantém backwards compat; callers gradualmente passam o lid | ✓ shippado |
| Captura `@lid` em 2 fontes paralelas (`GROUP_PARTICIPANTS_UPDATE` + `MESSAGES_UPSERT`) | Defesa-em-profundidade: webhook de grupo pode não disparar, msg do lead no grupo é evento garantido | ✓ shippado |
| Heurística unique-aguardando pra correlacionar `@lid` ↔ telefone | Quando >1 lead aguardando no mesmo grupo, ignora (log) e aguarda próximo sinal | ✓ shippado |
| Endpoint admin pra forçar revalidação em vez de SQL manual | Substitui workflow Karla 20/05; operador opera via frontend | ✓ shippado |
| Whitelist `enviar_convite_grupo` em ANTI_SPAM_LOOP | Convite de entrada é fluxo crítico, não spam | ✓ shippado |
| `qualificacao_lock` selada ANTES da criação do grupo | Fecha janela de race que permitiu Q1/Q2 dupla em Patrícia | ✓ shippado |
| Continua phase numbering (Fase 3-9) — não reseta | v2.0 terminou em Fase 2, timeline contínua é mais fácil de rastrear | ✓ aplicado |

### v2.2 (Webhook-First — em definição)

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Tabela dedicada `grupo_membership` em vez de marker em conversas | Relação N:N (lead × grupo), queries por grupo_jid eficientes, suporta REMOVE/saiu_em explícito | — Decidido (user 09/06) |
| Webhook = fonte primária, probe = fallback | v2.1 manteve probe como primário e falhou em 4+ casos do 08/06. Inversão é única forma de eliminar falso negativo | — Decidido (escopo aprovado) |
| Probe com retry exponencial (30s/2min/5min) async via APScheduler | Probe síncrono não dá tempo pra Evolution propagar — retry assíncrono espera + reverifica sem bloquear | — Pending |
| Cache in-memory 5min TTL (não Redis) | Single-worker Easypanel; 5-10 probes/min de pico; in-memory suficiente | — Pending |
| FSM transições estritamente monotônicas + audit log | Endurece estado contra regressão acidental; rastreabilidade pra debug | — Pending |
| Continua phase numbering — v2.2 começa em Fase 10 | v2.1 terminou em Fase 9, timeline contínua mais fácil de rastrear | — Decidido |
| Sem backfill retroativo de `grupo_membership` | Grupos antigos seguem com markers atuais (não vale custo de migration de dados) | — Decidido |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-09 — v2.1 (Grupo Robusto) entregue 20/05; milestone v2.2 (Webhook-First) iniciado após 6 fixes paliativos do dia 08/06 não cobrirem casos persistentes (553891500357 + 4 do 08/06)*
