# Requirements — Leadflow Platform

## Validated (ja em producao, NAO REGREDIR)

### Frontend v2 (milestone v1.0 concluido)
- Validated AUTH-01 a AUTH-06 — Login Supabase + ProtectedRoute
- Validated DASH-01 a DASH-07 — Dashboard com KPIs reais + grafico 7 dias
- Validated LEAD-01 a LEAD-11 — Tabela leads + acoes funcionais
- Validated CONV-01 a CONV-08 — Inbox conversas com polling
- Validated AGNT-01 a AGNT-07 — Editor de config IA
- Validated PIPE-01 a PIPE-04 — Kanban pipeline
- Validated SETT-01 a SETT-03 — Configuracoes
- Validated BILD-01 a BILD-04 — Build & deploy
- Validated FollowupEditor + AquecimentoEditor + DelayPicker

### Backend Agente IA (em producao)
- Validated Webhook lead-criacao `/webhook/{empresa_id}/{token}`
- Validated Q1 -> Q2 -> Q3 (empathy + slots) com templates configuraveis
- Validated Tool calling Gemini/OpenAI (`buscar_horarios_livres`, `criar_agendamento`)
- Validated FSM de fases (novo -> q1_enviado -> q2_enviado -> qualificado -> slots_oferecidos -> agendado/nao_convertido)
- Validated 4 camadas defesa slots (ANTI-ANUNCIO -> SLOTS-RESCUE -> FILLUP -> ULTRA-FALLBACK)
- Validated SLOT-OVERRIDE no tool call
- Validated Slot-pick day+hour matching direto de numeros
- Validated MSG_PROCESSED dedup por message_id
- Validated Audio Whisper (4 paths detector + HTTP 201)
- Validated FU recovery 14d + tolerancia overdue 48h + endpoint retomar-stuck
- Validated Time-based nao_convertido com atraso configuravel
- Validated Despedidas educadas (OPT-OUT, MENU-ENC, PAUSA-INDEF) ANTES do status terminal
- Validated SYNC com variantes BR phone (12 e 13 digitos)
- Validated Aquecimento grupo: ordem +5s, audio/pdf, auto-save

---

## Validated — v2.0 Agente IA Atomic Processing (shippado ad-hoc 04-06/05)

Phases 1-2 do milestone v2.0 foram entregues fora do ciclo GSD durante a sessao 06/05 (10 commits diretos + validacao em prod). Marcadas validated aqui pra que requirements remanescentes (TEST, AUDIO-T, DOC, OBS) possam ser retomados em milestone futuro se necessario.

- Validated **LOCK-01..08** — `processing_locks` + acquire/release/cleanup em prod desde 06/05
- Validated **DEDUP-01..04** — `send_text_uma_vez` + OFERTA_ATIVA + unique index conversas em prod
- Validated **SLOT-01..04** — slot-pick direto nums vs tokens (build 2026-05-03)

### Diferida (proximo milestone se ressurgir)

- AUDIO-T-01..03 (Whisper tolerance — nao ha mais reportes desde 06/05)
- TEST-01..12 (suite regressao — feita ad-hoc por usuario em prod)
- DOC-01..02 (diagrama sequencia)
- OBS-01 (endpoint /admin/queue-stats)

---

## Validated — Milestone v2.1 Grupo WhatsApp Robusto (entregue 20/05)

Phases 3-9 entregues em 20/05/2026 (commits ac301fd, 6b0295b, 207a3a9, 0e4c335, 0717e1c, 8d9fe5c, f97686c, 6159af5). Suite de 13 testes pytest commitada. Casos Karla/Crislaine/Patricia resolvidos. **NAO REGREDIR.**

- Validated **LID-01..08** (Fase 3): Captura @lid via `GROUP_PARTICIPANTS_UPDATE` + match no probe
- Validated **LID-D-01..05** (Fase 4): Captura via `MESSAGES_UPSERT` (segunda fonte)
- Validated **ADMIN-01..04** (Fase 5): Endpoints `/admin/grupo/forcar-revalidacao` + `/admin/grupo/status`
- Validated **SPAM-01..04** (Fase 6): Whitelist `enviar_convite_grupo` em ANTI_SPAM_LOOP
- Validated **QLOCK-01..04** (Fase 7): `qualificacao_lock` multi-template antes de criar grupo
- Validated **TEST-G1..G6** (Fase 9): Suite 13 testes pytest
- Validated **DOC-G1, DOC-G2, OBS-G1**: Memorias `sessao_2026-05-20_grupo_lid_arquitetura.md` + dashboard `/admin/grupos`

## Validated — Sessao 08/06 (6 fixes paliativos do problema raiz v2.2 vai resolver)

- Validated **AQUEC-FLOOR-01**: MIN_FLOOR_SEG 30s->180s (commit 53bd05a)
- Validated **ALERTA-GRUPO-01**: Remove alerta "lead nao entrou" no grupo (commit 07d7341)
- Validated **PROBE-BYPASS-01**: Marker GRUPO_LEAD_ENTROU_CRIACAO + bypass <5min (commit 96b72cc)
- Validated **GRUPO-REUSO-01**: Valida acesso a grupo antes de reusar (commit 7e366bd)
- Validated **RECOVERY-STARTUP-01**: Recoveries do startup async (commit ae2b141)
- Validated **RECOVERY-AQUEC-01**: Recovery aquec janela 6h (commit 0d55888)
- Validated **RLS-HARD-01**: Migration 003 RLS hardening (commit 073c93f)

## Active — Milestone v2.2 Webhook-First Grupo Membership

**Goal:** Eliminar falsos negativos persistentes do probe Evolution invertendo a fonte da verdade — webhook `GROUP_PARTICIPANTS_UPDATE` torna-se primario via tabela materializada `grupo_membership`, probe Evolution vira fallback com retry exponencial + cache curto.

**Causa-raiz reaberta (08-09/06):** v2.1 manteve probe Evolution como fonte primaria com `@lid` como matcher alternativo. Quando Evolution mente ou demora (60-180s pra propagar membros — caso comum), todos os patches caem. Os 6 fixes do dia 08/06 sao paliativos sobre a mesma base nao-confiavel. Esta milestone inverte: webhook e fonte primaria, probe e backup.

### Cat 1: MEMBERSHIP TABLE (Fase 10 — schema + 3 paths de escrita)

- [ ] **MEMB-01**: Migration `004_grupo_membership.sql` criando tabela `(empresa_id UUID, grupo_jid TEXT, telefone TEXT NULL, lid TEXT NULL, instance_key TEXT NOT NULL, entrou_em TIMESTAMPTZ, saiu_em TIMESTAMPTZ NULL, last_event_id TEXT, criado_em, atualizado_em)` + partial unique `WHERE saiu_em IS NULL` em `(empresa_id, grupo_jid, COALESCE(telefone, lid))` + indexes + RLS service_role only
- [ ] **MEMB-02**: Webhook `GROUP_PARTICIPANTS_UPDATE` (Path 1) UPSERT em `grupo_membership` quando `action="add"` (entrou_em = `messageTimestamp` do payload, NAO `NOW()`)
- [ ] **MEMB-03**: Webhook `MESSAGES_UPSERT` (Path 2) UPSERT em `grupo_membership` quando msg vem de grupo + 1 lead aguardando + @lid nao-mapped ainda
- [ ] **MEMB-04**: `_criar_grupo_agendamento` (Path 3 — createGroup response) faz INSERT direto em `grupo_membership` pro participant retornado por Evolution (caso Ana Carla: webhook ADD nao dispara aqui)
- [x] **MEMB-05**: Funcao `lead_in_group(sb, empresa_id, telefone, grupo_jid, lid="") -> dict {in_group, source, last_event_at, instance_key_match}` consulta `grupo_membership` PRIMEIRO; so vai pro probe Evolution se row ausente OU saiu_em != null
- [ ] **MEMB-06**: Query filtra `WHERE instance_key = empresa.evolution_key_atual` — rows de instancia antiga (Fernanda) NAO contam

### Cat 2: PROBE FALLBACK COM RETRY + CACHE (Fases 10-12)

- [ ] **PROBE-CACHE-01** (Fase 10): Singleton `app/services/probe_cache.py` com `cachetools.TTLCache(maxsize=512, ttl=300)` + `RLock`; chave `(empresa_id, grupo_jid, telefone, lid)`; invalidacao automatica em todo UPSERT de `grupo_membership` via helper centralizado
- [x] **PROBE-COALESCE-01** (Fase 11 — movido da Fase 10 em 09/06 pos plan-checker): `asyncio.Lock` por chave evita 3 jobs probando o mesmo grupo simultaneamente. Materializa junto do consumer `lead_in_group()` que dispara os probes concorrentes.
- [x] **PROBE-RETRY-01**: Funcao `schedule_probe_retry(empresa_id, grupo_jid, telefone, lid, attempts_left=3, max_age_seconds=600)` — job APScheduler one-shot `trigger='date'`. Tentativas em 30s/2min/5min. **`max_age_seconds` absoluto** descarta job se janela passou (cobre Rosania + Valquiria).
- [x] **PROBE-RETRY-02**: Migrar callers com margem temporal (notif pre-reuniao, timeout 30min FALLBACK) pra usar retry async em vez de probe sincrono. Aquec mantem sincrono mas consulta `grupo_membership` primeiro.

### Cat 3: LEAVE HANDLER (Fase 13)

- [ ] **LEAVE-01**: Webhook `GROUP_PARTICIPANTS_UPDATE action="remove"` marca `grupo_membership.saiu_em = messageTimestamp` + insere marker `LEAD_SAIU_GRUPO:{grupo_jid}` em conversas (sem `{ts}` — timestamp ja persiste em `saiu_em`; idempotencia via guard `saiu_em IS NULL` no UPDATE) [amenda 2026-06-09 pos plan-check]
- [ ] **LEAVE-02**: Notif pre-reuniao + D-1 detectam `saiu_em != null` na `lead_in_group()` E redirecionam pro DM (nao pra grupo vazio)
- [ ] **LEAVE-03**: FSM de grupo do lead que saiu vai pra `LEFT_GROUP` (novo estado terminal naquele agendamento; marker GSC carrega flag LEFT_GROUP pra diferenciar de timeout normal) [amenda 2026-06-09: LEFT_GROUP terminal em vez de FALLBACK_1_1, decisao do usuario, alinha com SC6]

### Cat 4: FSM MONOTONICO + AUDIT LOG (Fase 13)

- [x] **FSM-AUDIT-01**: `set_grupo_state()` valida transicao estritamente monotonica: `AGUARDANDO->FALLBACK_1_1->ATIVO` e ok; `ATIVO->AGUARDANDO` BLOQUEADO sem flag `force=True` (so endpoint admin pode forcar)
- [x] **FSM-AUDIT-02**: Toda transicao grava marker `GSC:{ag_id}:{from}:{to}:{reason}:{caller}` em conversas; argumento `caller` e obrigatorio sem default [amenda 2026-06-09: prefixo `GSC:` em vez de `GRUPO_STATE_CHANGE:` — este ultimo colide com `.like("GRUPO_STATE:%")` do get_grupo_state e corromperia o parser de estado]
- [ ] **FSM-AUDIT-03**: Audit log volume ~150 rows/dia (desprezivel); CI grep check garante que nenhum caller chama `set_grupo_state` sem `reason` e `caller`

### Cat 5: TESTES REGRESSAO (Fase 14)

- [ ] **TEST-V2-G1**: Caso Ana Carla 08/06 — lead adicionado direto em `createGroup`, `grupo_membership` populada via Path 3, FSM=ATIVO em <60s sem precisar probe live
- [ ] **TEST-V2-G2**: Caso Rosania 08/06 — webhook GROUP_PARTICIPANTS_UPDATE chega T+138s, sistema espera (probe retry com `max_age=600s`) em vez de cair pro DM
- [ ] **TEST-V2-G3**: Caso Fernanda 07/06 — grupo orfao de instancia antiga detectado em `lead_in_group` (instance_key mismatch) E novo grupo criado automatico
- [ ] **TEST-V2-G4**: Caso Valquiria 06/06 — aquec recovery nao dispara item velho (cobertura adicional ao RECOVERY-AQUEC-01); job retry descartado por `max_age_seconds`
- [ ] **TEST-V2-G5**: Caso 553891500357 09/06 — reproducao completa *(blocked-pending-data: precisa de trace do webhook + conversas do incidente)*

### Cat 6: DOC + OBSERVABILIDADE (Fase 14)

- [ ] **DOC-V2-G1**: Memoria `sessao_2026-06-XX_grupo_membership_v2.md` + nova `grupo_membership_arquitetura.md` em memory
- [ ] **DOC-V2-G2**: Atualizar `agente_referencia_compilada.md` com tabela `grupo_membership` + `lead_in_group()` + retry async + FSM audit
- [ ] **OBS-V2-G1**: Logs `[MEMB-WRITE]`, `[MEMB-LOOKUP]`, `[PROBE-RETRY]`, `[GRUPO-STATE-CHANGE]` estruturados
- [ ] **OBS-V2-G2**: Endpoint `/health/grupo-membership` retorna `{total_rows, last_write_at, cache_size, cache_hit_rate}` pra detectar cache mascarando falha de persistencia

---

## Future (proximos milestones)

- Coluna `leads.lid_whatsapp` (se >100 leads com @lid persistido, marker pode pesar)
- Endpoint Evolution alternativo (`checkNumberStatus`) como fallback de probe
- Dashboard frontend pra `/admin/grupo/status` (hoje so JSON)
- Suite testes T1-T8 do v2.0 (audio + queue regression)
- Multi-instance backend (advisory locks Postgres)
- WebSocket / SSE realtime

## Out of Scope (milestone v2.2)

| Feature | Reason |
|---------|--------|
| Coluna `leads.lid_whatsapp` | Tabela dedicada `grupo_membership` cobre N:N (lead x grupo) |
| Backfill retroativo de `grupo_membership` pra grupos antigos | Custo de migration alto; grupos antigos seguem com markers v2.1 |
| Reescrita FSM AGUARDANDO/FALLBACK_1_1/ATIVO | So endurecer transicoes (monotonico) + audit log |
| Reescrita do probe Evolution em si | So adicionar retry+cache em volta |
| Migracao Postgres -> Redis pro cache | In-memory `cachetools.TTLCache` e suficiente (single-worker) |
| Multi-instance backend | Single-instance hoje (carryover v2.0/v2.1 decision) |
| Eventos webhook adicionais alem dos 4 ja usados | GROUP_PARTICIPANTS_UPDATE + MESSAGES_UPSERT + CONNECTION_UPDATE + MESSAGES_UPDATE cobrem |
| Nova tabela `grupo_audit_log` separada | Audit log via marker em `conversas` reusa unique constraint + RLS |
| Frontend dashboard pra `grupo_membership` view | Dashboard `/admin/grupos` (v2.1) continua suficiente pra observabilidade humana |

---

## Traceability

### v2.1 (Fases 3-9 — shippadas 20/05)

| Requirement | Phase | Status |
|-------------|-------|--------|
| LID-01..08 | Fase 3 | shippado (ac301fd) |
| LID-D-01..05 | Fase 4 | shippado (6b0295b) |
| ADMIN-01..04 | Fase 5 | shippado (207a3a9) |
| SPAM-01..04 | Fase 6 | shippado (0e4c335) |
| QLOCK-01..04 | Fase 7 | shippado (0717e1c) |
| (ADMIN-03..04 frontend) | Fase 8 | shippado (8d9fe5c + f97686c) |
| TEST-G1..G6 + DOC-G1..G2 + OBS-G1 | Fase 9 | commitado (6159af5) |

### v2.2 (Fases 10-14 — em planejamento)

| Requirement | Phase | Plan | Status |
|-------------|-------|------|--------|
| MEMB-01 | Fase 10 | TBD | Pending |
| MEMB-02 | Fase 10 | TBD | Pending |
| MEMB-03 | Fase 10 | TBD | Pending |
| MEMB-04 | Fase 10 | TBD | Pending |
| MEMB-06 | Fase 10 | TBD | Pending |
| PROBE-CACHE-01 | Fase 10 | TBD | Pending |
| MEMB-05 | Fase 11 | 11-01, 11-02 | Planned |
| PROBE-COALESCE-01 | Fase 11 (movido da 10 em 09/06) | 11-01 | Planned |
| (migracao 6 callsites grupo_fallback.py) | Fase 11 | 11-02 | Planned |
| PROBE-RETRY-01 | Fase 12 | TBD | Pending |
| PROBE-RETRY-02 | Fase 12 | TBD | Pending |
| LEAVE-01 | Fase 13 | TBD | Pending |
| LEAVE-02 | Fase 13 | TBD | Pending |
| LEAVE-03 | Fase 13 | TBD | Pending |
| FSM-AUDIT-01 | Fase 13 | TBD | Pending |
| FSM-AUDIT-02 | Fase 13 | TBD | Pending |
| FSM-AUDIT-03 | Fase 13 | TBD | Pending |
| TEST-V2-G1 | Fase 14 | TBD | Pending |
| TEST-V2-G2 | Fase 14 | TBD | Pending |
| TEST-V2-G3 | Fase 14 | TBD | Pending |
| TEST-V2-G4 | Fase 14 | TBD | Pending |
| TEST-V2-G5 | Fase 14 | TBD | blocked-pending-data (trace 553891500357) |
| DOC-V2-G1 | Fase 14 | TBD | Pending |
| DOC-V2-G2 | Fase 14 | TBD | Pending |
| OBS-V2-G1 | Fase 14 | TBD | Pending |
| OBS-V2-G2 | Fase 14 | TBD | Pending |

**Coverage check:** 24/24 requirements v2.2 mapeados (100%). Nenhum orfao. Nenhuma duplicacao.

---

*Last updated: 2026-06-09 — v2.1 entregue 20/05; v2.2 (Webhook-First Grupo Membership) Traceability preenchida pelo roadmapper (Fases 10-14)*
