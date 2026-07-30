# Roadmap — Leadflow Platform

**Created:** 2026-05-03
**Updated:** 2026-07-30 — Milestone v3.0 (Cobranças Asaas + Empresa-mãe) adicionado (Fases 15-18)

---

## Milestones

- Concluido **v1.0 MVP — Frontend v2** — Phases 1-6 (shipped 2026-04-XX)
- Concluido **v2.0 — Agente IA Atomic Processing** — Phases 1-3 (shipped ad-hoc 06/05)
- Concluido **v2.1 — Grupo WhatsApp Robusto** — Phases 3-9 (shipped 20/05)
- Concluido **v2.2 — Webhook-First Grupo Membership** — Phases 10-14 (shipped 10/06)
- Em planejamento **v3.0 — Cobranças (Asaas) + Empresa-mãe** — Phases 15-18

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

<details>
<summary>v2.2 — Webhook-First Grupo Membership (Phases 10-14) — SHIPPED 10/06</summary>

**Milestone Goal:** Inverter a fonte da verdade. Webhook `GROUP_PARTICIPANTS_UPDATE` escreve em tabela materializada `grupo_membership` (primaria). Probe Evolution vira fallback com retry exponencial async + cache curto 5min.

### Phase 10: Schema + 3 paths webhook write + cache standalone (completed 2026-06-09)
MEMB-01..04, MEMB-06, PROBE-CACHE-01 — Tabela `grupo_membership` + UPSERT em 3 paths + cache singleton.

### Phase 11: `lead_in_group()` consumer + migrar fallback callers (completed 2026-06-09)
MEMB-05, PROBE-COALESCE-01 — Funcao central tabela-primeira + migra 6 callsites + coalescing async.

### Phase 12: Retry async + callers com margem (completed 2026-06-10)
PROBE-RETRY-01, PROBE-RETRY-02 — APScheduler retry 30s/2min/5min com `max_age_seconds=600`.

### Phase 13: LEAVE handler + FSM audit monotonico (completed 2026-06-10)
LEAVE-01..03, FSM-AUDIT-01..03 — Webhook REMOVE marca `saiu_em` + transicoes monotonicas + audit `GSC:`.

### Phase 14: Testes regressao + doc + observabilidade (completed 2026-06-10)
TEST-V2-G1..G5, DOC-V2-G1..G2, OBS-V2-G1..G2 — Suite pytest 5 casos + memorias + healthcheck.

Casos Ana Carla, Rosania, Fernanda, Valquiria resolvidos. TEST-V2-G5 (553891500357) blocked-pending-data. NAO REVERTER.

</details>

---

## v3.0 — Cobranças (Asaas) + Empresa-mãe (Em planejamento)

**Milestone Goal:** Ligar e completar a monetização do LeadFlow. O MOTOR de billing Asaas já está construído (port AvalancheVendas, gate OFF + grandfather) — esta milestone **ATIVA** o motor (config/operacional, código leve), adiciona a **área "Cobranças"** no painel (código novo: super-admin), **notificações de cobrança** via WhatsApp (código novo: job scheduler), e implanta a **empresa-mãe** do dono (operacional: dados + config via playbook) pra captar leads de venda do próprio sistema.

**Critical path:** Phase 15 (ativar billing). Sem billing ativo e produzindo dados reais de assinatura, a área Cobranças (Phase 16) não tem o que exibir e as notificações (Phase 17) não têm status de assinatura pra disparar.

**NÃO reconstruir o motor** — reusar o portado (`app/services/billing/`, `routers/billing.py`, `webhook_plataforma.py`, `asaas_client.py`, migration `010_plataforma_billing.sql`, `CadastroPage.tsx`).

**NÃO REGREDIR:** todas as camadas defensivas v2.0/v2.1/v2.2 continuam ativas. `BILLING_GATE_ENABLED` mantido OFF até a ativação estar validada (grandfather das empresas atuais preservado).

## Phases

**Phase Numbering:**
- Integer phases (15, 16, 17, 18): Planned milestone work
- Decimal phases (15.1, 16.1): Urgent insertions (marked with INSERTED)

v2.2 terminou em Phase 14 — v3.0 continua numbering em **Phase 15** (nao reseta).

- [ ] **Phase 15: Ativar Billing Asaas** - Rodar migration `010`, setar env Asaas central + webhook, validar `/cadastro` pago sandbox→prod (motor já existe — ativação/config)
- [ ] **Phase 16: Área Cobranças (Super-Admin)** - Endpoint de agregação + tela que lista empresas/assinaturas com status, inadimplência, valor/vencimento, histórico + link fatura Asaas
- [ ] **Phase 17: Notificações de Cobrança (WhatsApp)** - Job scheduler que envia lembrete de vencimento + aviso de atraso pro admin da empresa, idempotente e configurável
- [ ] **Phase 18: Implantação Empresa-mãe** - Criar a empresa do dono (persona/prompt/Q1-Q3/FPs/webhook/instância) pra captar e qualificar leads de venda do LeadFlow (operacional, via playbook)

## Phase Details

### Phase 15: Ativar Billing Asaas
**Goal**: Ligar o motor de billing já portado — novas empresas passam a pagar via Asaas pra se cadastrar, e o status da assinatura (active/past_due/etc) é atualizado automaticamente por webhook. É ativação + config (rodar migration, env, webhook, validar sandbox→prod), não construção de software.
**Depends on**: Nothing (primeira fase v3.0 — desbloqueia dados reais de billing)
**Requirements**: BILL-01, BILL-02, BILL-03, BILL-04, BILL-05, BILL-06
**Success Criteria** (what must be TRUE):
  1. Migration `010_plataforma_billing.sql` rodada no Supabase: 3 tabelas billing existem, preços R$297/R$2970 seedados, empresas atuais grandfathered como `active` (nenhuma empresa em produção é interrompida)
  2. Env Asaas central setado no web+scheduler (`ASAAS_CENTRAL_API_KEY`, `ASAAS_CENTRAL_AMBIENTE`, `ASAAS_CENTRAL_WEBHOOK_TOKEN`) e webhook Asaas configurado (`/webhook/plataforma/asaas` + header `asaas-access-token` + eventos PAYMENT_CONFIRMED/RECEIVED, OVERDUE, REFUNDED, DELETED, SUBSCRIPTION_DELETED)
  3. Fluxo `/cadastro` validado em SANDBOX ponta-a-ponta: signup → checkout Asaas → pagamento → webhook → empresa vira `active`; reenvio do mesmo evento não dupla (dedup via `plataforma_webhook_events`)
  4. Confirmação de e-mail resolvida (SMTP no Supabase + Confirm email ON, ou `SIGNUP_REQUIRE_EMAIL_CONFIRM=0`) — usuário recém-criado consegue logar
  5. Billing ATIVO em produção (ambiente Asaas prod) com CTA "Criar conta" → `app.leadcase.com.br/cadastro`; `BILLING_GATE_ENABLED` mantido OFF até validação final, empresas atuais seguem operando
**Plans**: TBD
**UI hint**: yes

### Phase 16: Área Cobranças (Super-Admin)
**Goal**: Dar ao dono da plataforma uma visão única de gestão financeira — todas as empresas e suas assinaturas num painel, com destaque de inadimplência e detalhe de pagamentos. Código novo (endpoint de agregação + página frontend) que lê as tabelas de billing (populadas na Phase 15) + Asaas.
**Depends on**: Phase 15 (precisa de dados de assinatura reais pra exibir)
**Requirements**: COBR-01, COBR-02, COBR-03, COBR-04, COBR-05
**Success Criteria** (what must be TRUE):
  1. Super-admin abre a tela "Cobranças" e vê todas as empresas listadas com status (`active`/`past_due`/`suspended`/`pending_payment`), plano, valor e próximo vencimento
  2. A tela destaca inadimplência no topo — contagem de empresas em `past_due`/`suspended` visível de imediato
  3. Super-admin abre o detalhe de uma empresa e vê o histórico de pagamentos (pagos/atrasados, valores, datas) + link direto da fatura Asaas
  4. Um endpoint backend (super-admin) agrega empresas + assinatura + status + últimos pagamentos numa única resposta (lê tabelas billing + Asaas)
  5. O acesso é restrito ao super-admin (dono da plataforma) — uma empresa comum/tenant não consegue abrir nem ver a área
**Plans**: TBD
**UI hint**: yes

### Phase 17: Notificações de Cobrança (WhatsApp)
**Goal**: Reduzir inadimplência e churn silencioso avisando a empresa pela WhatsApp antes e depois do vencimento da mensalidade. Código novo (job no scheduler + config), reusando a infra de envio WhatsApp existente e o status de assinatura da Phase 15.
**Depends on**: Phase 15 (precisa do status de assinatura e vencimentos)
**Requirements**: NOTIF-01, NOTIF-02, NOTIF-03, NOTIF-04
**Success Criteria** (what must be TRUE):
  1. N dias antes do vencimento da mensalidade, o contato admin da empresa recebe um lembrete por WhatsApp
  2. Quando a assinatura vira `past_due`, o admin da empresa recebe um aviso de atraso por WhatsApp
  3. As notificações são idempotentes — não se repetem no mesmo ciclo/fatura mesmo se o job rodar múltiplas vezes
  4. As notificações são configuráveis — dias de antecedência, on/off e texto da mensagem ajustáveis sem alterar código
**Plans**: TBD

### Phase 18: Implantação Empresa-mãe
**Goal**: Colocar o próprio LeadFlow pra vender LeadFlow — implantar a empresa do dono como um tenant real que capta leads de venda e os qualifica ponta-a-ponta com o agente IA. É trabalho operacional (criação de dados + config via playbook de implantação), não software a construir. Independente das outras fases — pode rodar em paralelo.
**Depends on**: Nothing (operacional/independente — pode correr em paralelo com 15-17)
**Requirements**: IMPL-01, IMPL-02, IMPL-03, IMPL-04, IMPL-05, IMPL-06, IMPL-07
**Success Criteria** (what must be TRUE):
  1. Empresa-mãe existe no LeadFlow (nome, fuso, plano) com o dono cadastrado como admin (membro papel=admin)
  2. `config_ia` (persona/nome_agente/nome_responsavel + `prompt_sistema` vendendo o LeadFlow + Q1/Q2/Q3 + empatia) e `config_agendamento` (horários, duração, plataforma de reunião, confirmação D-1) estão preenchidos
  3. FPs (follow-ups de prospecção) configurados para os leads de venda
  4. Webhook de captação criado (com `mapeamento_campos`/`ordem_campos` do formulário de venda) + instância WhatsApp conectada + webhook Evolution (`MESSAGES_UPSERT`) configurado
  5. Teste ponta-a-ponta valida: um lead de venda entra → Q1 → Q2 → Q3 → empatia → slots → agendamento, sem intervenção manual
**Plans**: TBD

## Progress

**Execution Order:**
Phases 15 → 16 → 17 executam em ordem (16 e 17 dependem de 15). Phase 18 é operacional e independente — pode correr em paralelo.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 15. Ativar Billing Asaas | 0/? | Not started | - |
| 16. Área Cobranças (Super-Admin) | 0/? | Not started | - |
| 17. Notificações de Cobrança (WhatsApp) | 0/? | Not started | - |
| 18. Implantação Empresa-mãe | 0/? | Not started | - |

## Phase Order Rationale (v3.0)

1. **Phase 15 primeiro (CRITICAL PATH)** — Ativar o billing desbloqueia os dados reais de assinatura. É pré-requisito de dados pras Phases 16 e 17. Código leve (ativação/config); o motor já existe.
2. **Phase 16 depois** — A área Cobranças exibe o que o billing produz. Sem billing ativo (15) não há empresas/assinaturas/pagamentos pra listar.
3. **Phase 17** — Notificações disparam a partir do status da assinatura (`past_due`) e dos vencimentos, que só existem depois de 15. Reusa infra WhatsApp existente.
4. **Phase 18 (paralela)** — Implantação da empresa-mãe é operacional (dados + config via playbook), não depende do billing nem da UI. Pode rodar a qualquer momento, inclusive em paralelo com 15-17.

---

## Proximo passo imediato

```
/gsd-plan-phase 15
```

Gera o plano detalhado da Fase 15 (ativar billing Asaas). Phase 18 (empresa-mãe) pode ser iniciada em paralelo via `/gsd-plan-phase 18` por ser operacional e independente.

---

*Roadmap criado: 2026-05-03 — milestone v2.0*
*Atualizado: 2026-05-20 — milestone v2.1 Grupo Robusto (Fases 3-9)*
*Atualizado: 2026-06-09 — milestone v2.2 Webhook-First (Fases 10-14)*
*Atualizado: 2026-07-30 — milestone v3.0 Cobranças Asaas + Empresa-mãe (Fases 15-18)*
