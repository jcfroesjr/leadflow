---
gsd_state_version: 1.0
milestone: v3.0
milestone_name: — Cobranças (Asaas) + Empresa-mãe
status: roadmap_ready
last_updated: "2026-07-30"
last_activity: 2026-07-30
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Current Position

Phase: 15 — Ativar Billing Asaas (not started)
Plan: —
Status: Roadmap pronto — aguardando `/gsd-plan-phase 15`
Last activity: 2026-07-30 — Roadmap v3.0 criado (Fases 15-18)

Progress: [░░░░░░░░░░] 0% (0/4 fases)

## Active Milestone

**v3.0 — Cobranças (Asaas) + Empresa-mãe**

**Goal:** Ligar e completar a monetização do LeadFlow — ativar o billing Asaas já portado (plataforma cobra as empresas), adicionar a área "Cobranças" no painel, notificações de cobrança da mensalidade via WhatsApp, e implantar a empresa-mãe (a do dono) pra captar leads de venda do próprio sistema.

**Contexto-chave:** o MOTOR de billing JÁ EXISTE (port AvalancheVendas — `app/services/billing/`, `routers/billing.py`, `webhook_plataforma.py`, `asaas_client.py`, migration `010_plataforma_billing.sql`, `CadastroPage.tsx`), gate OFF + grandfather. Esta milestone ATIVA + adiciona UI + notificações + implantação. NÃO reconstruir o motor.

**Phases planejadas:** Fase 15-18 (continua numbering — v2.2 terminou em Fase 14).

## Phase Sequence v3.0

| Phase | Goal | Requirements | Depends on | Status |
|-------|------|--------------|------------|--------|
| 15 | Ativar Billing Asaas (migration 010 + env + webhook + validar cadastro pago sandbox→prod) | BILL-01..06 | — (critical path) | Not started |
| 16 | Área Cobranças super-admin (endpoint agregação + tela: status/inadimplência/histórico/fatura) | COBR-01..05 | Phase 15 | Not started |
| 17 | Notificações de cobrança WhatsApp (lembrete vencimento + aviso atraso, idempotente, configurável) | NOTIF-01..04 | Phase 15 | Not started |
| 18 | Implantação empresa-mãe (persona/prompt/Q1-Q3/FPs/webhook/instância + teste ponta-a-ponta) | IMPL-01..07 | — (operacional, paralelo) | Not started |

**Execução:** 15 → 16 → 17 em ordem (16/17 dependem de dados do billing). Phase 18 é operacional e independente — pode correr em paralelo com 15-17.

## Performance Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Coverage requisitos v3.0 | 100% (22/22) | 100% (22/22) mapped |
| Fases | 4 | 0/4 completas |
| Reuso motor billing (não reconstruir) | 100% | pendente (Phase 15) |
| Empresa-mãe qualifica lead ponta-a-ponta | 1 teste E2E | pendente (Phase 18) |

## Accumulated Context (preservado entre milestones)

### v3.0 — Infra existente a REUSAR (não reinventar)

- **Motor billing (port AvalancheVendas, gate OFF + grandfather):**
  - `app/services/billing/` — lógica de assinatura/planos
  - `app/routers/billing.py` — endpoints de billing
  - `app/routers/webhook_plataforma.py` — handler `/webhook/plataforma/asaas` (dedup via `plataforma_webhook_events`)
  - `app/services/asaas_client.py` — client Asaas (sandbox + prod)
  - `migrations/010_plataforma_billing.sql` — 3 tabelas + seed preços R$297/R$2970 + grandfather empresas atuais
  - `CadastroPage.tsx` (frontend) — fluxo `/cadastro` pago (pay-first, sem trial)
- **Infra WhatsApp de envio** (reusar em NOTIF): senders existentes do agente + Evolution
- **Playbook de implantação** (reusar em IMPL): `playbook_implantacao_empresa.md` + `onboarding_aplicar_template.md` (TEMPLATE Rejane 6213bf16)
- **Multi-tenant:** `empresa_id` em todas as entidades; `config_ia`/`config_agendamento`/`config_apis` por empresa

### Flags / envs a configurar (Phase 15)

- `ASAAS_CENTRAL_API_KEY`, `ASAAS_CENTRAL_AMBIENTE`, `ASAAS_CENTRAL_WEBHOOK_TOKEN` (web + scheduler)
- `SUPABASE_ANON_KEY` conferido (resend e-mail)
- Confirmação e-mail: SMTP no Supabase + Confirm email ON, OU `SIGNUP_REQUIRE_EMAIL_CONFIRM=0`
- `BILLING_GATE_ENABLED` — mantido OFF até validação final (grandfather preservado)
- Webhook Asaas: `/webhook/plataforma/asaas` + header `asaas-access-token` + eventos PAYMENT_CONFIRMED/RECEIVED, OVERDUE, REFUNDED, DELETED, SUBSCRIPTION_DELETED
- Domínios: `app.leadcase.com.br/cadastro` (CTA "Criar conta")

### Out of Scope v3.0 (não fazer)

- Empresa cobrando os PRÓPRIOS clientes finais dela via Asaas (só plataforma→empresas nesta milestone)
- Gateway além do Asaas (Stripe/PayPal)
- Reescrita do motor de billing (só ativar + UI + notificações em volta)
- Metered/usage billing (só assinatura fixa mensal/anual)
- Dunning automático complexo (retry cartão, downgrade auto) — só notificação + status de inadimplência

### Marcos anteriores — NÃO REGREDIR

- v1.0 Frontend v2 (Phases 1-6) — em prod
- v2.0 Agente IA Atomic Processing (Lock/Dedup/Slot-pick) — em prod
- v2.1 Grupo Robusto (Phases 3-9) — shippado 20/05
- v2.2 Webhook-First Grupo Membership (Phases 10-14) — shippado 10/06 (tabela `grupo_membership`, retry async, FSM audit `GSC:`)
- Todas as camadas defensivas 08/06 (6 fixes paliativos) — mantidas ativas

## Decisions Log v3.0

| Decision | Rationale | When |
|----------|-----------|------|
| Continua phase numbering — v3.0 começa em Fase 15 | v2.2 terminou em Fase 14; timeline contínua mais fácil de rastrear | 2026-07-30 |
| 1 fase por categoria (BILL/COBR/NOTIF/IMPL) | Categorias são fronteiras de entrega coerentes e independentes; sem split artificial | 2026-07-30 |
| BILL primeiro (critical path) | Ativar billing produz os dados de assinatura que COBR exibe e NOTIF consome | 2026-07-30 |
| IMPL (empresa-mãe) como fase paralela/independente | Operacional (dados + config via playbook), não depende de billing nem UI | 2026-07-30 |
| NÃO reconstruir o motor de billing | Já portado do AvalancheVendas; Phase 15 é ativação/config, não construção | 2026-07-30 |
| `BILLING_GATE_ENABLED` OFF até validar | Grandfather das empresas em produção preservado durante a ativação | 2026-07-30 |

## Gaps / TODOs

- **`instance_key`/instância WhatsApp da empresa-mãe** — decidir número/instância dedicada antes da Fase 18 (IMPL-06)
- **SMTP Supabase vs flag** — decidir em Phase 15 (BILL-05) qual caminho de confirmação de e-mail
- **Sandbox Asaas** — garantir credenciais sandbox antes de BILL-04; prod só após validação
- **Contato admin p/ notificação** — confirmar de onde vem o telefone do admin da empresa (Phase 17, NOTIF-01)
- **Prompt de venda da empresa-mãe** — redigir `prompt_sistema` vendendo o LeadFlow (Phase 18, IMPL-02)

## Next Action

1. `/gsd-plan-phase 15` — decompor a Fase 15 (ativar billing Asaas) em plans executáveis
2. Em paralelo: `/gsd-plan-phase 18` — empresa-mãe é operacional/independente
3. Antes de BILL-04: garantir credenciais sandbox Asaas + decidir caminho de confirmação de e-mail (BILL-05)

## Session Continuity

**Para retomar de outra sessao:**

- ROADMAP.md tem as 4 fases v3.0 (15-18) com success criteria observáveis
- REQUIREMENTS.md tem a Traceability v3.0 (BILL/COBR/NOTIF/IMPL) mapeada — 22/22
- Motor de billing JÁ EXISTE (port AvalancheVendas) — Phase 15 ATIVA, não reconstrói
- Camadas defensivas v2.0/v2.1/v2.2 + fixes 08/06 — NÃO REGREDIR
- Memórias relevantes: `feature_billing_plataforma_asaas.md`, `playbook_implantacao_empresa.md`, `onboarding_aplicar_template.md`

---

*Last updated: 2026-07-30 — Roadmap v3.0 criado (Fases 15-18), aguardando `/gsd-plan-phase 15`*
