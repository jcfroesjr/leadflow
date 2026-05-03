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

## Current Milestone: v2.0 Agente IA Atomic Processing

**Goal:** Eliminar race conditions e duplicações no processamento de webhooks do agente IA, garantindo agendamento determinístico mesmo com múltiplas mensagens consecutivas, áudios com Whisper imperfeito, e respostas LLM fora do trilho.

**Target features:**
- Lock atômico por (empresa_id, telefone) com queue serializando webhooks paralelos
- Dedup universal antes de qualquer send (Q1, Q2, empathy, slots, agendamento)
- Single slot offer per cycle (nunca 2 sets de SLOTS_TOKENS no histórico)
- Slot-pick determinístico (matching direto de números na msg vs tokens disponíveis)
- Suite de testes regressão T1-T8 (casos reais documentados)

**Histórico imediato:** sessão de 03/05 produziu 10 commits de band-aids (e7a9a88, a2e236d, b85e7ef, b982972, 8d3147d, 3264ee4, cce4591, 9acbe42, c16aefc, abb9168) que mitigaram sintomas mas não resolveram a causa raiz: ausência de lock atômico. Os band-aids ficam (ANTI-ANUNCIO regex, SLOTS-RESCUE, FILLUP, ULTRA-FALLBACK, OVERRIDE, dedup local Q1/Q2) — são camadas de defesa válidas. Esta milestone resolve a causa raiz.

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

### Active (Milestone v2.0)

- [ ] **LOCK-01**: Tabela `processing_locks` com unique constraint (empresa_id, telefone) e auto-expire 60s
- [ ] **LOCK-02**: Webhook handler adquire lock atômico antes de processar mensagem; libera ao final
- [ ] **LOCK-03**: Mensagens enfileiradas (QUEUED marker) quando lock ativo; processadas em ordem após release
- [ ] **LOCK-04**: TTL/cleanup de locks órfãos (processo morreu no meio) via job periódico
- [ ] **DEDUP-01**: Dedup universal antes de send_text (Q1, Q2, empathy, slots, "Marcadinho!"): query DB last 30s para conteúdo idêntico → skip
- [ ] **DEDUP-02**: Marker `OFERTA_ATIVA:{ts}` por lead — segunda oferta em <2min reusa a primeira (não cria novo SLOTS_TOKENS)
- [ ] **DEDUP-03**: Unique index em `conversas(empresa_id, telefone, conteudo, role)` para markers de sistema (impede duplicatas via race)
- [ ] **SLOT-01**: Slot-pick atômico — sempre usa OFERTA_ATIVA mais recente (não "última msg do histórico"); matching direto nums vs tokens
- [ ] **SLOT-02**: Quando ambíguo ou sem match, BLOQUEIA tool e re-apresenta os 3 slots vigentes pedindo clarificação
- [ ] **AUDIO-01**: Whisper transcription tolerante a ruído — números livres extraídos, cruzados com tokens; nunca confia 100% no texto transcrito
- [ ] **TEST-01**: Suite de testes T1-T8 (casos reais documentados em ANALISE_DETALHADA_DEFEITOS.md)
- [ ] **TEST-02**: Test harness com webhook mocking + Evolution stub + Calendar stub
- [ ] **DOC-01**: Documentação operacional do novo fluxo (lock, queue, dedup) em `agente_ia_fixes.md`

### Out of Scope (deste milestone)

- Multi-instance backend / horizontal scaling — single Easypanel hoje
- WebSockets / Server-Sent Events para realtime — polling é suficiente
- Migration pra Redis / outro store de lock — Postgres é suficiente
- Refator do FSM de fases — só ajustes pontuais necessários para suportar o lock
- Frontend admin pra ver locks ativos — debug via SQL direto

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

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Lock em tabela Postgres com unique constraint | Mais simples que Redis; postgres já é dependência | — Pending |
| Queue em markers `QUEUED:{msg_id}` em conversas | Reusa tabela existente; sem nova infra | — Pending |
| TTL 60s + cleanup job periódico | Previne deadlock de lock órfão | — Pending |
| Dedup window de 30s pra mensagens idênticas | Curto suficiente pra não bloquear retry legítimo | — Pending |
| OFERTA_ATIVA window de 2min | Lead que demora pra responder não gera 2 ofertas | — Pending |
| Não migrar pra Redis | Postgres handle 1 worker single-instance bem | — Pending |
| Reseta phase numbering pra v2.0 | Marco diferente, fase 1 começa do zero | — Pending |

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
*Last updated: 2026-05-03 — escopo expandido para Plataforma Leadflow (frontend+backend), milestone v2.0 iniciado*
