# Feature Landscape — v2.2 Webhook-First Grupo Membership

**Domain:** WhatsApp group-membership state tracking in a Brazilian CRM/SaaS (Leadflow) using Evolution API
**Researched:** 2026-06-09
**Scope:** ONLY new features for v2.2 milestone. v2.0 (Lock/Dedup/Slot-pick), v2.1 (LID capture/Admin/SPAM/QLock/Tests) and the 6 paliativos de 08/06 já estão em prod e NÃO entram aqui.
**Overall confidence:** HIGH (escopo pré-definido em PROJECT.md, 5 casos motivadores reais, patterns validados em literatura webhook 2026)

---

## Categorias de Features

| Categoria | O que é | Política v2.2 |
|-----------|---------|---------------|
| Table Stakes | Indispensável para a inversão "webhook-first". Sem isso, milestone não fecha. | Build em Fase 10-11 |
| Differentiators | Endurece além do mínimo (cache, FSM monotônico, audit log). | Build em Fase 12 |
| Test/Regression | Bloqueio de regressão dos 5 casos motivadores. | Build em Fase 13 |
| Anti-Features | Explicitamente FORA de escopo (decisão registrada em PROJECT.md). | NÃO buildar |

---

## Table Stakes

Features sem as quais a inversão "webhook = fonte primária" não acontece. Cada uma mapeia 1:1 com REQ-IDs do PROJECT.md.

| Feature | REQ-IDs | Why Expected (table-stake reasoning) | Complexity | Notes |
|---------|---------|--------------------------------------|------------|-------|
| **Tabela materializada `grupo_membership`** | MEMB-01 | Sem persistência dedicada (grupo_jid, telefone, lid, entrou_em, saiu_em), continuar dependente de markers em `conversas` mantém o probe como caminho crítico. É a fundação do "webhook-first". | Low | Migration única + 2 indexes (grupo_jid+telefone unique; empresa_id+telefone). Sem backfill (decisão registrada em PROJECT.md). |
| **Webhook GROUP_PARTICIPANTS_UPDATE → UPSERT em `grupo_membership`** | MEMB-02 | Webhook é o evento de verdade de "lead entrou/saiu". Sem persistir aqui, voltamos ao probe. ADD seta `entrou_em`; REMOVE seta `saiu_em`. | Medium | Handler já existe em `app/routers/grupo_webhook.py`. Estender (não reescrever). Evolution entrega at-least-once → UPSERT idempotente via unique constraint `(grupo_jid, telefone)`. |
| **MESSAGES_UPSERT (msg do lead no grupo) → backfill em `grupo_membership`** | MEMB-03 | Defesa em profundidade: quando GROUP_PARTICIPANTS_UPDATE não dispara (bug conhecido Evolution), msg do lead é evento garantido de presença. Match via @lid + grupo aguardando. | Medium | Reutiliza heurística unique-aguardando da v2.1. Se >1 lead aguardando no mesmo grupo, ignora (log) — mesma regra. |
| **`lead_in_group(empresa_id, telefone, grupo_jid)` consulta tabela PRIMEIRO** | MEMB-04 | Inversão da fonte da verdade. Probe Evolution só roda se row ausente OU `saiu_em != null`. É O switch que define webhook-first. | Low | Função nova em `app/services/grupo_membership.py` (criar). Substitui caller direto do probe nos 3 sistemas (aquec, notif, D-1). |
| **Probe Evolution com retry exponencial async (30s / 2min / 5min)** | PROBE-RETRY-01 | False negative inicial (Evolution leva 60-180s pra propagar) é a causa raiz reaberta. Probe síncrono não dá tempo. Retry assíncrono via APScheduler espera + reverifica sem bloquear caller. | Medium | Usar APScheduler (já dependência). Modo `retry_async=True` em `verificar_lead_no_grupo`. Schedule 3 jobs com `replace_existing=True` por chave `(grupo_jid, telefone)`. |
| **Handler webhook LEAVE/REMOVE marca `saiu_em`** | LEAVE-01 | Hoje sistema não sabe quando lead saiu. Continua mandando confirmação pra grupo vazio. REMOVE chega via mesmo webhook → seta `saiu_em` + insere marker `LEAD_SAIU_GRUPO:{jid}` em conversas (audit). | Low | Mesmo handler de MEMB-02, branch em `action='remove'`. |
| **Notif pré-reunião e D-1 detectam `saiu_em != null` E vão pro DM** | LEAVE-02 | Sem isso, lead que saiu continua recebendo no grupo vazio (ou perdendo a confirmação totalmente). É o consumidor lógico de LEAVE-01. | Low | 2 call-sites em `app/services/grupo_fallback.py` + confirmação D-1. Branch simples: `if saiu_em → DM fallback`. |

**Dependências table-stakes:**

```
MEMB-01 (tabela)
  ├─→ MEMB-02 (webhook → tabela)
  ├─→ MEMB-03 (msg → tabela)
  ├─→ LEAVE-01 (webhook leave → tabela.saiu_em)
  └─→ MEMB-04 (lead_in_group consulta tabela)
        └─→ PROBE-RETRY-01 (fallback async quando tabela vazia)
        └─→ LEAVE-02 (DM quando saiu_em != null)
```

**MEMB-01 deve ser Fase 10 isolada.** MEMB-02/03/LEAVE-01 podem ser Fase 11 juntas. MEMB-04/PROBE-RETRY-01/LEAVE-02 são Fase 12 (consumidores).

---

## Differentiators

Acima do mínimo. Endurecem a base contra regressão futura e dão observabilidade.

| Feature | REQ-IDs | Value Proposition | Complexity | Notes |
|---------|---------|-------------------|------------|-------|
| **Cache in-memory de probe (TTL 5min)** | PROBE-CACHE-01 | Múltiplos jobs (aquec #1..#4 + notif + D-1) consultam o mesmo grupo em janela curta. Sem cache, cada um dispara HTTP pra Evolution = burst de 5-10 calls em segundos. Cache colapsa em 1. | Low | Dict Python + lock + TTL — single-worker Easypanel não precisa Redis (anti-feature explícito em PROJECT.md). Invalidate on UPSERT em grupo_membership. |
| **FSM transições estritamente monotônicas** | FSM-AUDIT-01 | Hoje FSM aceita regressão (ATIVO→AGUARDANDO) e isso causou bugs históricos (Luciane 11/05). Endurecer transição = invariante de safety. Bloqueia regressão sem flag explícita `override=True`. | Low | Edit guard em `app/services/grupo_state.py:set_grupo_state`. Whitelist de transições válidas. Raise `InvalidTransition` se inválida sem override. |
| **Audit log `GRUPO_STATE_CHANGE:{from}:{to}:{reason}:{caller}` em conversas** | FSM-AUDIT-02 | Debug de bugs grupo hoje exige `grep agente.py` + correlação manual de timestamps. Audit estruturado em conversas (tabela já com unique constraint pra idempotência) = timeline auditável por lead. | Low | Insert em `set_grupo_state` antes do commit do novo estado. Marker já tem precedente (23+ markers em conversas). |

**Dependências differentiators:**

- PROBE-CACHE-01 depende de MEMB-04 (caller que se beneficia). Pode shipar junto na Fase 12.
- FSM-AUDIT-01 e FSM-AUDIT-02 são independentes entre si, mas devem shipar juntas (audit confirma o guard funcionou). Fase 12 ou 13.

---

## Test / Regression Suite

Reprodução completa dos 5 casos motivadores. Cada teste deve falhar contra o build atual (08/06) e passar contra o build v2.2.

| Feature | REQ-IDs | Caso reproduzido | Complexity | Notes |
|---------|---------|------------------|------------|-------|
| **Teste regressão Ana Carla 08/06** | TEST-V2-G1 | Lead adicionado direto no createGroup → probe T+60s viu False → aquec foi pro DM. Cenário valida: webhook GROUP_PARTICIPANTS_UPDATE de createGroup escreve em `grupo_membership` ANTES do aquec rodar; MEMB-04 lê e retorna True; aquec vai pro grupo. | Medium | Mockar evolution + APScheduler. Usar pytest-asyncio (já no projeto via v2.1 suite). |
| **Teste regressão Rosânia 08/06** | TEST-V2-G2 | Webhook chegou T+138s, aquec falhou em T+60s. Cenário valida: probe inicial negativo enfileira retry; antes do retry concluir, webhook escreve em `grupo_membership`; retry consulta tabela primeiro → True → aquec vai pro grupo. | High | Cenário com timing controlado via `asyncio.Event`. Padrão pytest-asyncio recomendado pra race conditions (ver Sources). |
| **Teste regressão Fernanda 07/06** | TEST-V2-G3 | Grupo órfão de instância antiga reusado. Cenário valida: `lead_in_group` detecta grupo inexistente na instância atual → MEMB-04 retorna "grupo_invalido" → caller cria novo grupo. (Cobre integração com fix GRUPO-REUSO-01 já em prod.) | Medium | Mock Evolution retornando 404 no probe → MEMB-04 retorna sentinel. |
| **Teste regressão Valquíria 06/06** | TEST-V2-G4 | Aquec recovery reagendou item velho 47h depois. Cenário valida: recovery do startup descarta items >6h (cobre RECOVERY-AQUEC-01 já em prod com asserção extra). | Low | Teste unit em `slots_recovery.py` (ou módulo do aquec recovery). |
| **Teste regressão 553891500357 09/06** | TEST-V2-G5 | Caso ativo do user — reproduzir passo a passo. **Pendente**: user precisa fornecer trace completo (timestamps, payloads webhook, conversas) pra montar fixture. | Medium-High | Bloqueado em dados do incidente. Researcher anota como dependência humana. |
| **Doc memory `grupo_membership_arquitetura.md`** | DOC-V2-G1 | Atualizar `agente_ia_fixes.md` + criar memória nova explicando inversão webhook-first. Garante que próxima sessão não regrida acidentalmente. | Low | Markdown na pasta memory. |

**Dependências test suite:**

- Todos os testes dependem das features table-stakes (MEMB-01 a LEAVE-02) estarem em código.
- Suite roda em Fase 13 após features estabilizadas.
- 13 testes existentes da v2.1 (commit 6159af5) NÃO devem ser tocados — só estendidos.

---

## Anti-Features

Features explicitamente FORA de escopo. Listadas em `PROJECT.md → Out of Scope`. Roadmapper NÃO deve incluir.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|--------------------|
| **Coluna `leads.lid_whatsapp`** | Relação lead × grupo é N:N (lead pode estar em múltiplos grupos via reagendamento; grupo pode ter múltiplos leads no aguardando-entrada). Coluna em `leads` força 1:1. | Tabela dedicada `grupo_membership` (MEMB-01) com PK composta. |
| **Redis para cache de probe** | Single-worker no Easypanel; 5-10 probes/min de pico em janelas curtas; dict in-memory + lock + TTL é suficiente e zero infra nova. | Dict Python in-process (PROBE-CACHE-01). |
| **Reescrita do FSM AGUARDANDO/FALLBACK_1_1/ATIVO** | FSM existente em `app/services/grupo_state.py` funciona; reescrever introduz risco grande. Endurecer transições + adicionar audit log é suficiente. | FSM-AUDIT-01 (guard) + FSM-AUDIT-02 (log), sem mudar estados ou transições válidas. |
| **Reescrita do probe Evolution** | Probe em si funciona; problema é timing (Evolution não propagou). Reescrever HTTP client não resolve. | PROBE-RETRY-01 (wrapper async com retry) + PROBE-CACHE-01 (deduplica calls). |
| **Backfill retroativo de `grupo_membership` pros grupos antigos** | Custo de migration de dados > benefício; grupos antigos já estão estabilizados via markers atuais; v2.2 começa "do deploy em diante". | Registrar a partir do deploy. Grupos antigos seguem com markers `LEAD_LID` + probe (paths legados continuam funcionando). |
| **Multi-instance backend** | Out-of-scope desde v2.0/v2.1. Single-worker Easypanel cobre carga atual. | Mantém single-worker. Decisão revisada em milestone futuro se carga crescer. |
| **Novos eventos webhook Evolution além dos atuais** | GROUP_PARTICIPANTS_UPDATE, MESSAGES_UPSERT, CONNECTION_UPDATE, MESSAGES_UPDATE já cobrem todos os casos. | Estender handlers existentes (MEMB-02, MEMB-03, LEAVE-01). |
| **Migrar APScheduler pra Celery/RQ** | APScheduler resolve retry assíncrono em single-worker. Celery exige Redis/Rabbit (anti-feature acima) + worker separado. | APScheduler com `replace_existing=True` (PROBE-RETRY-01). |
| **Substituir markers em `conversas` por event store dedicado** | Conversas já tem unique constraint + 23+ markers em produção. Event store novo = refactor massivo sem ganho proporcional. | Continuar usando markers em conversas (LEAVE-01, FSM-AUDIT-02). |

---

## Feature Dependencies (Grafo Completo)

```
MEMB-01 (tabela grupo_membership)
   ├─→ MEMB-02 (webhook ADD → UPSERT)
   │      └─→ TEST-V2-G1 (Ana Carla)
   ├─→ MEMB-03 (msg upsert → UPSERT)
   ├─→ LEAVE-01 (webhook REMOVE → saiu_em)
   │      └─→ LEAVE-02 (notif/D-1 detecta saiu_em)
   └─→ MEMB-04 (lead_in_group consulta tabela primeiro)
          ├─→ PROBE-RETRY-01 (retry async se tabela vazia)
          │      ├─→ TEST-V2-G2 (Rosânia — race timing)
          │      └─→ TEST-V2-G5 (553891500357)
          ├─→ PROBE-CACHE-01 (cache TTL 5min)
          └─→ TEST-V2-G3 (Fernanda grupo órfão)

FSM-AUDIT-01 (transições monotônicas)
   └─→ FSM-AUDIT-02 (audit log GRUPO_STATE_CHANGE)
        └─→ (consumido por todos os call-sites de set_grupo_state)

RECOVERY-AQUEC-01 (já em prod, paliativo 08/06)
   └─→ TEST-V2-G4 (Valquíria — cobertura adicional)

DOC-V2-G1 (memory)
   └─→ depende de TODAS as features acima estarem em código
```

---

## MVP Recommendation (ordem sugerida pro roadmapper)

**Fase 10 — Fundação (1-2 dias):**
1. MEMB-01 — Migration + indexes (table stakes, sem dependências)

**Fase 11 — Coleta (2-3 dias):**
2. MEMB-02 — Webhook ADD → UPSERT
3. MEMB-03 — MESSAGES_UPSERT → UPSERT
4. LEAVE-01 — Webhook REMOVE → saiu_em

**Fase 12 — Consumo + Endurecimento (3-4 dias):**
5. MEMB-04 — `lead_in_group` consulta tabela primeiro
6. PROBE-RETRY-01 — Retry async via APScheduler
7. PROBE-CACHE-01 — Cache in-memory 5min
8. LEAVE-02 — Notif/D-1 detecta saiu_em
9. FSM-AUDIT-01 — Guard monotônico
10. FSM-AUDIT-02 — Audit log

**Fase 13 — Regressão (1-2 dias):**
11. TEST-V2-G1..G5 — Suite pytest-asyncio
12. DOC-V2-G1 — Memory updates

**Defer (não fazer em v2.2):** todos os anti-features acima.

---

## Pitfalls Específicos das Features (cross-link com PITFALLS.md)

| Feature | Pitfall conhecido | Mitigação |
|---------|-------------------|-----------|
| MEMB-02 | Webhook Evolution at-least-once → duplicata vai gerar 2 INSERTs | Unique constraint `(grupo_jid, telefone)` + UPSERT (ON CONFLICT DO UPDATE) |
| MEMB-03 | >1 lead aguardando no mesmo grupo → match @lid → telefone ambíguo | Heurística unique-aguardando da v2.1: se >1, ignora + log (regra preservada) |
| PROBE-RETRY-01 | 3 jobs em paralelo pro mesmo (grupo, telefone) → 3x HTTP burst | APScheduler `replace_existing=True` por job_id determinístico |
| PROBE-CACHE-01 | TTL longo → cache stale após webhook chegar | Invalidate explícito em todos os UPSERTs de grupo_membership |
| FSM-AUDIT-01 | Quebra de transição legítima rara em produção → backend crash | Flag `override=True` explícito + log de WARNING (não exception) |
| TEST-V2-G2 | Race condition difícil de reproduzir flake | Usar `asyncio.Event` pra controle determinístico (padrão pytest-asyncio) |

---

## Confidence Assessment por Feature

| Feature | Confidence | Reason |
|---------|------------|--------|
| MEMB-01..04 | HIGH | Escopo definido em PROJECT.md, padrão materialized view + UPSERT idempotente é table stake em CRM/messaging (literatura webhook 2026 valida) |
| LEAVE-01, LEAVE-02 | HIGH | Consequência lógica da tabela materializada + casos motivadores explícitos |
| PROBE-RETRY-01 | HIGH | APScheduler já dependência; padrão exponential backoff async é canônico (backoff/tenacity/riprova) |
| PROBE-CACHE-01 | HIGH | Single-worker + TTL curto é solução padrão; anti-feature Redis registrada |
| FSM-AUDIT-01, FSM-AUDIT-02 | MEDIUM | Mudança em código stable (grupo_state.py) — risco de break de transição rara não-documentada. Mitigação: override flag + dry-run em staging. |
| TEST-V2-G1..G4 | HIGH | Casos com timestamps e payloads conhecidos |
| TEST-V2-G5 | LOW | Bloqueado em dados do incidente 553891500357 — user precisa fornecer trace |

---

## Sources

- [Webhook Reliability 2026: Idempotency & Retry Reference — digitalapplied.com](https://www.digitalapplied.com/blog/webhook-reliability-idempotency-retries-engineering-reference-2026)
- [How to Implement Webhook Idempotency — hookdeck.com](https://hookdeck.com/webhooks/guides/implement-webhook-idempotency)
- [At-Least-Once vs. Exactly-Once Webhook Delivery Guarantees — hookdeck.com](https://hookdeck.com/webhooks/guides/webhook-delivery-guarantees)
- [Idempotency and Deduplication — Svix Webhook University](https://www.svix.com/resources/webhook-university/reliability/idempotency-and-deduplication/)
- [Event Sourcing Pattern — Microsoft Azure Architecture Center](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing)
- [Event sourcing pattern — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/event-sourcing.html)
- [Evolution API Webhooks Documentation](https://doc.evolution-api.com/v2/en/configuration/webhooks)
- [Evolution API CHANGELOG — group participants / LID conversion](https://github.com/EvolutionAPI/evolution-api/blob/main/CHANGELOG.md)
- [WhatsApp Cloud API webhooks delayed by minutes to hours — n8n Community](https://community.n8n.io/t/whatsapp-cloud-api-webhooks-delayed-by-minutes-to-hours/265580)
- [backoff — Python decorator library for exponential backoff (PyPI)](https://pypi.org/project/backoff/)
- [Tenacity — General-purpose retry library docs](https://tenacity.readthedocs.io/)
- [Python State Machines: FSMs, The State Pattern & Transitions (2026) — DEV Community](https://dev.to/kaushikcoderpy/python-state-machines-fsms-the-state-pattern-transitions-2026-147d)
- [Build a Finite State Machine in Python — Bob Belderbos](https://belderbos.dev/blog/build-finite-state-machine-python/)
- [Preventing Race Conditions in Async Python Code](https://johal.in/preventing-race-conditions-in-async-python-code/)
- [async test patterns for Pytest — Anthony Shaw](https://tonybaloney.github.io/posts/async-test-patterns-for-pytest-and-unittest.html)
- [Pytest-asyncio Guide: Test Async Functions in Python 2026 — qaskills.sh](https://qaskills.sh/blog/pytest-asyncio-testing-guide)

**Internal references:**
- `c:/Projetos/Leadflow/.planning/PROJECT.md` (REQ-IDs autoritativos)
- `c:/Projetos/Leadflow/.planning/STATE.md` (casos motivadores)
- `c:/Users/Caca Froes/.claude/projects/c--Projetos-Leadflow/memory/sessao_2026-05-20_grupo_lid_arquitetura.md` (v2.1 completa)
- `c:/Projetos/Leadflow/leadflow-backend/app/services/grupo_state.py` (FSM atual — não reescrever)
- `c:/Projetos/Leadflow/leadflow-backend/app/services/grupo_fallback.py` (callers de probe — alvos de MEMB-04)
- `c:/Projetos/Leadflow/leadflow-backend/app/routers/grupo_webhook.py` (handler atual — alvo de MEMB-02/03/LEAVE-01)
