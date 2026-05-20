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

## Current Milestone: v2.1 Grupo WhatsApp Robusto

**Goal:** Eliminar definitivamente bugs de detecção de lead no grupo WhatsApp, capturando `@lid` (Linked ID de privacidade) em múltiplas fontes e usando como chave alternativa ao telefone em todos os probes, preservando 100% das camadas defensivas já implementadas.

**Target features:**
- Captura `@lid` via webhook `GROUP_PARTICIPANTS_UPDATE` + heurística unique-aguardando (Fase 3 — parcial no workdir, 20/05)
- Captura `@lid` via `MESSAGES_UPSERT` no grupo (defesa-em-profundidade — Fase 4)
- Endpoint admin `/admin/grupo/forcar-revalidacao` (substitui SQL manual — Fase 5)
- Audit + whitelist `ANTI_SPAM_LOOP` pra convite nativo (Fase 6)
- Selar `qualificacao_lock` ANTES de criar grupo (corrige Q1/Q2 duplicada — Fase 7)
- Dashboard admin `/admin/grupo/status?empresa_id=X` (observabilidade — Fase 8)
- Suite testes regressão T1-T5 (Fase 9)

**Causa-raiz comprovada (sessão 2026-05-20):** WhatsApp esconde o telefone do lead como `@lid` (Linked ID) quando a privacidade é alta. Sem mapping bidirecional confiável `phone ↔ @lid`, `verificar_lead_no_grupo` retorna chute. Todos os bugs catalogados desde 04/05 (Gessiana, Luciane 11/05, Vanusa 13/05, Luciane 18-19/05, Karla 20/05, Patrícia 20/05) são manifestações dessa causa única — cada patch anterior foi um trade-off diferente entre falso positivo e falso negativo. Esta milestone elimina o trade-off ao tornar o `@lid` uma identidade persistida e match-able.

**Histórico v2.0 (Agente IA Atomic Processing):** Phases 1-2 (Lock Atômico + Dedup Universal) foram shippadas ad-hoc em prod durante a sessão 06/05 (10 commits) e validadas. Phase 3 (OFERTA_ATIVA + slot-pick determinístico) também em prod. Phase 4 (Whisper) e suite testes T1-T8 ficam abertas pra próximo milestone se ressurgirem.

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

### Active (Milestone v2.1)

- [ ] **LID-01**: Webhook `GROUP_PARTICIPANTS_UPDATE` separa `@lid` de telefones limpos, grava marker `LEAD_LID:{grupo_jid}:{lid}` quando há exatamente 1 lead aguardando no grupo *(no workdir 20/05)*
- [ ] **LID-02**: `verificar_lead_no_grupo` aceita parâmetro `lead_lid` e usa como matcher alternativo ao telefone no loop de participants *(no workdir 20/05)*
- [ ] **LID-03**: Helper `_get_lead_lid_for_group(sb, empresa_id, telefone, grupo_jid)` lê marker mais recente; 7 callers threadeados (grupo_fallback.py 6x + confirmacao_agendamento.py 1x) *(no workdir 20/05)*
- [ ] **LID-04**: Webhook agente captura `@lid` via `MESSAGES_UPSERT.data.key.participant` quando msg vem de grupo aguardando; promove FSM se exatamente 1 lead aguardando
- [ ] **LID-05**: Backfill manual: leads existentes em FALLBACK_1_1 podem ser re-validados via endpoint admin
- [ ] **ADMIN-01**: Endpoint `POST /admin/grupo/forcar-revalidacao { empresa_id, telefone, agendamento_id }` — re-probe + sincroniza FSM
- [ ] **ADMIN-02**: Endpoint `GET /admin/grupo/status?empresa_id=X` — lista (lead, telefone, grupo_jid, FSM state, probe_live, has_lead_lid, tempo aguardando)
- [ ] **SPAM-01**: Audit `ANTI_SPAM_LOOP:rate_alto` — mapear quais envios bloqueia (caso Patrícia 20/05: convite nativo card pode ter sido bloqueado)
- [ ] **SPAM-02**: Whitelist `enviar_convite_grupo` no fluxo anti-spam — fluxo crítico de entrada não deve ser bloqueado
- [ ] **QLOCK-01**: `popular_qs_se_faltando` chamada ANTES de `_criar_grupo_agendamento` retornar (leads.py + agente.py tool path) — fecha janela de race que permitiu Q1/Q2 dupla em Patrícia
- [ ] **TEST-G1**: Caso lead entra com telefone limpo (sem `@lid`) → FSM=ATIVO via webhook
- [ ] **TEST-G2**: Caso lead entra só com `@lid` → FSM=ATIVO via match `LEAD_LID`
- [ ] **TEST-G3**: Caso lead nunca entra → FSM=FALLBACK_1_1 + DM convite + alerta grupo
- [ ] **TEST-G4**: Caso 2 leads aguardando + `@lid` ambíguo → log, não-promove, aguarda próximo sinal
- [ ] **TEST-G5**: Caso Patrícia regressão: Q1/Q2 não dispara 2x após `qualificacao_lock` selada
- [ ] **DOC-G1**: Atualizar `agente_ia_fixes.md` / criar nota em memory com nova arquitetura

### Out of Scope (deste milestone)

- Coluna `leads.lid_whatsapp` (marker em conversas é suficiente, evita migration)
- Endpoint Evolution alternativo (`checkNumberStatus`, `fetchProfile`) pra probe — `findGroupInfos` cobre se `@lid` mapped
- Reescrita do FSM AGUARDANDO/FALLBACK_1_1/ATIVO — já funciona, só faltava o match
- Cache de resultado de probe Evolution — taxa atual (~5-10/min) não exige
- Reescrever ANTI_SPAM_LOOP detector — só whitelist o convite nativo
- Multi-instance backend (segue out-of-scope do v2.0)
- Eventos webhook Evolution adicionais (CONNECTION_UPDATE, CONTACTS_UPSERT) — só os 2 que já usamos

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

### v2.1 (Grupo Robusto)

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| `@lid` persistido como marker `LEAD_LID` em conversas (não coluna em leads) | Reusa tabela + unique constraint pra idempotência; evita migration | — Pending |
| Probe Evolution aceita `lead_lid` opcional como matcher alternativo | Mantém backwards compat; callers gradualmente passam o lid | — Pending |
| Captura `@lid` em 2 fontes paralelas (`GROUP_PARTICIPANTS_UPDATE` + `MESSAGES_UPSERT`) | Defesa-em-profundidade: webhook de grupo pode não disparar, msg do lead no grupo é evento garantido | — Pending |
| Heurística unique-aguardando pra correlacionar `@lid` ↔ telefone | Quando >1 lead aguardando no mesmo grupo, ignora (log) e aguarda próximo sinal | — Pending |
| Endpoint admin pra forçar revalidação em vez de SQL manual | Substitui workflow Karla 20/05; operador opera via frontend | — Pending |
| Whitelist `enviar_convite_grupo` em ANTI_SPAM_LOOP | Convite de entrada é fluxo crítico, não spam | — Pending |
| `qualificacao_lock` selada ANTES da criação do grupo | Fecha janela de race que permitiu Q1/Q2 dupla em Patrícia | — Pending |
| Continua phase numbering (Fase 3-9) — não reseta | v2.0 terminou em Fase 2, timeline contínua é mais fácil de rastrear | — Decidido |

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
*Last updated: 2026-05-20 — v2.0 phases shippadas ad-hoc validadas, milestone v2.1 (Grupo Robusto) iniciado*
