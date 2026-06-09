# Domain Pitfalls — v2.2 Webhook-First Grupo Membership

**Domain:** Migração probe-síncrono → webhook+materialized table em backend FastAPI/APScheduler single-instance
**Researched:** 2026-06-09
**Scope:** Pitfalls específicos da inversão de fonte da verdade (probe Evolution → tabela `grupo_membership`) com retry exponencial, cache in-memory, FSM monotônico e audit log
**Confidence overall:** HIGH (pitfalls baseados em casos reais + best practices 2026 verificados)

---

## Resumo dirigido pro roadmap

A milestone v2.2 não falha por escrever código novo errado — falha por **integração mal feita com camadas existentes** e **falsa sensação de segurança da nova fonte da verdade**. Os 6 fixes paliativos do 08/06 são layers válidos que **não podem ser regredidos** quando a base mudar. Os pitfalls abaixo estão ordenados por severidade: críticos são o que vai causar regressão dos 5 casos motivadores; moderados causam novos bugs sutis; menores degradam observabilidade.

**Os 5 casos do 08/06 que podem REPETIR mesmo após v2.2:**

| Caso | Pitfall que reabre o bug | Phase v2.2 que deve cobrir |
|------|--------------------------|----------------------------|
| Ana Carla (entrou direto em createGroup) | Webhook não dispara em participants vindos do POST /group/create — Evolution só notifica em ADD posterior | MEMB-02 + MEMB-03 (escrita defensiva no createGroup, não só no webhook) |
| Rosânia (webhook chegou T+138s) | Cache TTL muito curto OU retry exponencial converge antes da chegada do webhook | PROBE-RETRY-01 com backoff total ≥ 180s + cache invalidação por webhook |
| Fernanda (grupo órfão) | `grupo_membership` herda grupo_jid antigo no UPSERT, mas instância nova não vê o grupo | MEMB-04 deve verificar **instance_key atual da empresa** ao consultar |
| Valquíria (recovery 47h late) | Job retry exponencial enfileira muito longe no futuro sem TTL absoluto | PROBE-RETRY-01 precisa de `max_age` absoluto, não só max_retries |
| 553891500357 (atual) | Race entre webhook ADD + job dispatch lendo `grupo_membership` antes da escrita commitar | MEMB-02 deve usar `ON CONFLICT DO UPDATE` + advisory lock por grupo_jid |

---

## Critical Pitfalls (causam regressão dos casos motivadores)

### Pitfall 1: Confiar que webhook GROUP_PARTICIPANTS_UPDATE dispara pra TODOS os adds

**What goes wrong:** Evolution API documentadamente atrasa webhooks 5min-horas em casos comuns ([n8n community](https://community.n8n.io/t/whatsapp-cloud-api-webhooks-delayed-by-minutes-to-hours/265580)). Pior: participantes adicionados via `POST /group/create` no momento da criação podem **não disparar** webhook separado (apenas o evento "grupo criado"). Caso Ana Carla 08/06 confirma — entrou direto na createGroup e probe T+60s viu False.

**Why it happens:** Webhooks WhatsApp são at-least-once mas também **sometimes-never** — Evolution depende do WhatsApp Web underlying que tem propagação eventual. POST /group/create já tem os participants no payload de resposta, mas o webhook ADD pode não vir.

**Consequences:** v2.2 deploya. Tabela `grupo_membership` fica vazia pra leads que entraram via createGroup. `lead_in_group` consulta tabela primeiro (vazia), cai pro probe (também viu False), conclui "lead não entrou", aquec vai pro DM. **Bug Ana Carla repete identicamente.**

**Prevention:**
- Webhook **NÃO é a única escrita** em `grupo_membership`. O caller que chama `POST /group/create` da Evolution **deve fazer UPSERT direto** com os participants recebidos no response, **antes** de aguardar webhook.
- Adicionar uma 3a fonte: handler MESSAGES_UPSERT já escreve `grupo_membership` quando msg do lead chega no grupo (matching @lid). Mantém defesa-em-profundidade da v2.1.
- Test case obrigatório: TEST-V2-G1 deve simular createGroup retornando participants + zero webhooks ADD posteriores → `lead_in_group` retorna True por causa da escrita direta.

**Detection:**
- Métrica: ratio de rows em `grupo_membership` criadas via webhook vs. via createGroup-response. Se >50% só vem via webhook em produção, algo está errado.
- Log obrigatório em createGroup callsite: `[GRUPO_MEMBERSHIP_DIRECT] grupo={jid} participants_inserted={n}`.

**Phase v2.2:** MEMB-02 (Phase 10/11) — definir 3 paths de escrita: webhook ADD, MESSAGES_UPSERT match, createGroup response. Não 1 só.

---

### Pitfall 2: Cache in-memory perdido em redeploy mascarando falha de webhook persistence

**What goes wrong:** Cache TTL 5min mantém resultado positivo em memória. Redeploy reseta cache. Próxima consulta refaz query em `grupo_membership` que **deveria** ter row do webhook recebido — mas se o INSERT do webhook falhou silenciosamente, descobre tarde demais.

**Why it happens:** Em single-worker Easypanel, cache in-memory é "OK" mas cria **falso sinal de saúde**: sistema parece funcionando porque cache hit responde correto, mascarando que escrita persistente nunca aconteceu. ([Cache invalidation pitfalls](https://dev.to/nk_sk_6f24fdd730188b284bf/cache-invalidation-the-hardest-problem-in-computer-science-3imd))

**Consequences:** Webhook handler tem bug (ex: schema mismatch, RLS bloqueando insert, deadlock). Em pico, cache absorve as consultas e tudo parece OK. Easypanel redeploya à noite (push automático). Manhã seguinte, cache zerado, `lead_in_group` consulta tabela vazia, conclui False, **todos os aquecimentos pendentes vão pro DM**.

**Prevention:**
- Cache deve ser **write-through**: webhook que escreve em `grupo_membership` **também** invalida/atualiza cache na mesma transação lógica (via NOTIFY ou call direto).
- Healthcheck endpoint `/health/grupo-membership` retorna contagem últimas 24h e timestamp último write. Alerta se delta zero por >1h em horário de pico.
- Job daily de reconciliação: para grupos com FSM=ATIVO criados nas últimas 24h, verifica se tem pelo menos 1 row em `grupo_membership`. Logs WARN se faltam.

**Detection:**
- Métrica Prometheus/log: `grupo_membership_writes_total{source=webhook,createGroup,messages_upsert}` — todos os 3 devem ter contagem > 0 por hora.
- Alerta operacional: 0 inserts via webhook GROUP_PARTICIPANTS_UPDATE por 30 min seguidos em horário ativo.

**Phase v2.2:** PROBE-CACHE-01 + MEMB-04 — cache não é trivial; tratar invalidação na escrita.

---

### Pitfall 3: Retry exponencial converge antes do webhook chegar (caso Rosânia)

**What goes wrong:** Caso Rosânia 08/06: webhook chegou em T+138s. Se PROBE-RETRY-01 fizer 30s/2min/5min = backoff total chega em T+30+120+300 = T+450s (7.5min). Bom — cobre Rosânia. **MAS** se a lógica for "max 3 retries e depois conclui negativo definitivo", o T+138s do webhook **chega entre o retry #2 e #3** e o resultado pode ser ignorado se o job já marcou status "negativo" provisório.

**Why it happens:** Webhook arrival e job convergence rodam em paralelo. Job dispatcher pode ler `grupo_membership` em T+125s (entre retries), ver vazio, cair pro probe (ainda False), e enfileirar próximo retry — mas em T+138s o webhook escreve, e em T+150s outro caller (outro job) lê e vê True. Job original já decidiu pro DM em T+125s.

**Consequences:** Bug Rosânia repete em variante mais sutil. Webhook chegou, tabela populada, mas decisão de aquec foi tomada antes e mandou DM.

**Prevention:**
- Job dispatch **não decide DM definitivo até** `max_age` absoluto (ex: T+8min). Antes disso, se `lead_in_group` retorna False, **enfileira retry**, não conclui.
- Lock pessimista em `grupo_membership` consultado pelo job dispatcher: `SELECT ... FOR UPDATE` no row aguardando, com timeout. Ou usar Postgres advisory lock por `grupo_jid`.
- FSM=AGUARDANDO tem **deadline absoluto** (ex: T+10min). Não é "max retries", é "max wall-clock time". Webhook que chegar até deadline vence o job dispatch.

**Detection:**
- Log obrigatório no retry handler: `[PROBE_RETRY] attempt={n} grupo={jid} elapsed_s={delta} verdict={true/false/pending}`.
- Audit: contar quantos jobs concluíram negativo definitivo e webhook chegou **depois** com positivo. Se >5/dia, retry config está errado.

**Phase v2.2:** PROBE-RETRY-01 — deve ser implementado com `max_wallclock` + `force_check_grupo_membership_before_dispatch`, não só `max_retries`.

---

### Pitfall 4: Grupo órfão de instância antiga ressurge via reuso (caso Fernanda)

**What goes wrong:** Lead reagendado em 07/06. Sistema verifica `agendamentos.grupo_jid` antigo (criado em 17/04 na instância bia-rejane), tenta reusar. Tabela `grupo_membership` retorna row velha (lead estava no grupo em abril!), `lead_in_group` retorna True. Sistema manda aquec pro grupo — **mas grupo está na instância antiga que foi desconectada**. Mensagens caem.

**Why it happens:** v2.2 introduz `grupo_membership` mas não atrela o row a uma `instance_key`. Reuso herda grupo_jid de qualquer agendamento histórico do lead. Fix 7e366bd (GRUPO-REUSO-01) já valida acesso ao grupo via Evolution — mas se v2.2 prioriza `grupo_membership` sobre probe, o fix do 08/06 **regride**.

**Consequences:** Fernanda repete. Pior: silenciosamente, porque `grupo_membership` retorna True confiantemente.

**Prevention:**
- Coluna `instance_key` em `grupo_membership` (qual instância criou). Query consulta `WHERE grupo_jid=X AND telefone=Y AND instance_key = (empresa.instance_key_atual)`.
- Quando empresa muda instância (caso Rejane 08/06: bia-rejane → rejane-leal-mentora), rodar migration soft: rows antigas com instância órfã ficam com `saiu_em = NOW()` automático ou flag `instance_orphan=true`.
- Fix GRUPO-REUSO-01 (commit 7e366bd) **deve permanecer ativo** como camada extra mesmo após v2.2. Probe live antes de reusar grupo continua valendo.

**Detection:**
- Query operacional: `SELECT empresa_id, grupo_jid, instance_key FROM grupo_membership WHERE instance_key != empresas.instance_key_atual` — deve ser 0 em produção saudável.
- Log no callsite de reuso: `[GRUPO_REUSO] jid={jid} instance_match={true/false} validated_access={true/false}`.

**Phase v2.2:** MEMB-01 (schema deve ter `instance_key`) + MEMB-04 (filtro na query).

---

### Pitfall 5: Job retry enfileirado pra futuro distante sem TTL absoluto (caso Valquíria)

**What goes wrong:** Caso Valquíria 06/06 — aquec #4 falhou no send original. Recovery job re-enfileirou. Por bug de relógio/cron, executou **47h depois**. Mensagem foi entregue fora de contexto. Commit 0d55888 (RECOVERY-AQUEC-01) limitou janela 6h — paliativo. **Em v2.2**, o retry exponencial do PROBE-RETRY-01 pode reintroduzir o problema se max_retries=N permitir alcançar horas no futuro.

**Why it happens:** APScheduler com `DateTrigger` enfileira no datastore. Se sistema cai e volta, jobs antigos podem disparar tarde. Sem TTL absoluto, retry exponencial 30s/2min/5min/15min/... acumula até horas.

**Consequences:** Aquec/notif dispara T+horas, lead já contextualizou outra coisa, conversa quebra.

**Prevention:**
- Todo retry job tem campo `max_age_seconds` (ex: 600s = 10min). Handler verifica `now - enqueued_at < max_age_seconds` antes de executar; se velho, descarta + log.
- APScheduler jobs persistidos: limitar `misfire_grace_time` (ex: 60s). Default APScheduler é 1s o que dropa silenciosamente — explicitar configurações.
- Manter RECOVERY-AQUEC-01 (commit 0d55888) ativo. v2.2 **adiciona** retry mas **não substitui** as proteções existentes.

**Detection:**
- Log obrigatório quando job descartado por idade: `[JOB_EXPIRED] type={probe_retry} grupo={jid} age_s={delta}`. Métrica `jobs_expired_total`.
- Alerta se jobs APScheduler pending com `next_run_time > NOW + 30min` aparecerem (sintoma de bug).

**Phase v2.2:** PROBE-RETRY-01 spec deve incluir `max_age_seconds`. Não apenas `max_retries`.

---

### Pitfall 6: Race entre webhook ADD escrevendo + job dispatcher lendo

**What goes wrong:** Webhook GROUP_PARTICIPANTS_UPDATE chega. Handler inicia INSERT em `grupo_membership`. **Antes** do COMMIT, job dispatcher do aquec (worker do APScheduler) lê `grupo_membership` (não vê row), cai pro probe, probe (no mesmo instante) também não vê (Evolution propagação). Job conclui False. INSERT commita 50ms depois. Próxima consulta vê True — tarde.

**Why it happens:** APScheduler + FastAPI + asyncio rodam corrotinas concorrentes mesmo em single-worker. Postgres sem lock pessimista no telefone+grupo_jid não serializa as duas operações.

**Consequences:** Janela curta (centenas de ms) mas reproduzível sob carga. Caso 553891500357 09/06 pode ser exatamente isso.

**Prevention:**
- Webhook handler usa `INSERT ... ON CONFLICT (grupo_jid, telefone) DO UPDATE SET entrou_em=EXCLUDED.entrou_em, atualizado_em=NOW()` — atomicidade per-row garantida ([Postgres ON CONFLICT](https://oneuptime.com/blog/post/2026-01-25-postgresql-race-conditions/view)).
- Job dispatcher antes de **decidir DM definitivo**, faz `SELECT ... FROM grupo_membership WHERE grupo_jid=X AND telefone=Y FOR UPDATE` numa transação curta. Se webhook handler estiver no meio do INSERT, bloqueia até commitar.
- Alternativa: Postgres advisory lock por hash(grupo_jid). Caller do dispatch e webhook handler ambos `SELECT pg_advisory_xact_lock(hash)` antes de operar.

**Detection:**
- Métrica: distribuição de tempo entre webhook recebido e primeira consulta bem-sucedida em `grupo_membership` por consumer. P99 deve ser < 200ms.
- Log de auditoria: quando job dispatcher decide DM em T < T_webhook_arrived, registra `[RACE_DETECTED]`.

**Phase v2.2:** MEMB-02 (UPSERT spec) + MEMB-04 (lock pattern no read path).

---

### Pitfall 7: FSM transição não-monotônica via caller esquecido

**What goes wrong:** FSM-AUDIT-01 endurece `set_grupo_state`. Mas codebase tem 3+ callsites que setam estado direto via UPDATE SQL (ou via marker em conversas que outro path interpreta como state). Caller esquecido bypassa guard, regressão silenciosa: ATIVO → AGUARDANDO acontece, audit log não captura.

**Why it happens:** v2.1 já tem FSM (AGUARDANDO/FALLBACK_1_1/ATIVO) com transições em `grupo_state.py`. Mas testes da v2.1 cobriram só os callers conhecidos. v2.2 adiciona webhook LEAVE-01 que pode setar `LEFT_GROUP` — mais um caller. Sem grep exaustivo, alguém adiciona caller futuro sem audit.

**Consequences:** Bug fantasma. State regride, comportamento muda, debugger não acha origem porque audit log não registrou.

**Prevention:**
- **Único entrypoint:** todos os callers devem passar por `set_grupo_state(empresa_id, grupo_jid, from_state, to_state, reason, caller)`. UPDATEs diretos proibidos por convention (linter custom ou code review checklist).
- Função verifica transição válida via matrix dict. Levanta `InvalidTransition` se inválida (não bypass via flag de override exceto em endpoint admin explícito).
- Audit log obrigatório (FSM-AUDIT-02). Caller passado como argumento, não inferido por stack frame.
- Grep validation no CI: `grep -r "UPDATE.*grupo_state" --include="*.py"` deve só retornar o código de `grupo_state.py`.

**Detection:**
- Query operacional: rows em `agendamentos` com FSM=AGUARDANDO mas com `criado_em > 4h atrás` (FSM travado). Sinal de transição faltando.
- Métrica: contagem de transições por dia, agrupada por `(from, to)`. Padrão monotônico esperado: AGUARDANDO→ATIVO predominante. Se ATIVO→AGUARDANDO aparece (>0), bug presente.

**Phase v2.2:** FSM-AUDIT-01 + FSM-AUDIT-02 — checklist de callers no PR review. Não confiar só na guard function.

---

## Moderate Pitfalls (novos bugs sutis)

### Pitfall 8: Webhook idempotency key collision entre eventos distintos

**What goes wrong:** Webhook Evolution sends `messageId` ou `event_id`. v2.2 usa esse ID como dedup key. **Mas** múltiplos eventos legítimos (ADD seguido de outro ADD do mesmo participant após REMOVE) podem reusar o mesmo ID em casos de retry da Evolution, ou IDs podem ser baseados em hash do payload (colidem em ADDs idênticos).

**Why it happens:** [Webhook idempotency best practices](https://hookdeck.com/webhooks/guides/implement-webhook-idempotency) recomendam dedup com TTL > janela de retry do provider. Mas dedup TTL longo demais bloqueia eventos legítimos de mesmo tipo + ator.

**Prevention:**
- Dedup key = `(event_id, event_type, occurred_at)`. TTL alinhado com retry window Evolution (~5min).
- UPSERT em `grupo_membership` é a defesa real — dedup é otimização. Se dedup falhar, UPSERT no-op.
- Não usar `INSERT ... ON CONFLICT DO NOTHING` se semântica esperada é UPDATE — `DO UPDATE` é correto pra refletir o evento mais recente.

**Phase v2.2:** MEMB-02 implementation detail.

---

### Pitfall 9: Webhook out-of-order REMOVE chegando antes do ADD

**What goes wrong:** Evolution entrega webhook REMOVE (lead saiu) em T+5s e ADD (lead entrou) em T+10s. Lógica processa na ordem de chegada: marca `saiu_em` numa row inexistente (no-op ou cria row "fantasma"), depois ADD cria row sem `saiu_em`. Estado final: ATIVO. Aparentemente correto. **Mas** se ordem real era inversa (entrou e depois saiu), estado final deveria ser saiu.

**Why it happens:** [Webhook ordering não é garantido](https://hackernoon.com/you-cant-guarantee-webhook-ordering-heres-why). Provedor envia em ordem, rede e proxies podem entregar fora de ordem.

**Prevention:**
- Cada evento webhook traz `occurred_at` (timestamp do Evolution). UPSERT compara: `SET entrou_em = GREATEST(EXCLUDED.entrou_em, grupo_membership.entrou_em)` ou explicit `WHERE EXCLUDED.occurred_at > grupo_membership.atualizado_em`.
- Schema `grupo_membership` tem `last_event_at` que **só atualiza pra adiante**. Eventos com `occurred_at < last_event_at` são logged e ignorados (após UPSERT condicional).

**Detection:**
- Métrica: contagem de eventos `out_of_order_ignored` por tipo. Alerta se >10/hora (problema de provedor ou rede).

**Phase v2.2:** MEMB-02 spec deve incluir comparação por `occurred_at`.

---

### Pitfall 10: Cache in-memory crescimento ilimitado (memory leak)

**What goes wrong:** PROBE-CACHE-01 implementado como `dict` global Python sem max_size. Multi-tenant SaaS → chaves `(grupo_jid, telefone, lid)` × N empresas crescem indefinidamente. Backend OOM após semanas.

**Why it happens:** [unbounded cache é causa #1 de memory leak Python](https://knowledgelib.io/software/debugging/python-memory-leaks/2026). `@lru_cache(maxsize=None)` é trap clássico.

**Prevention:**
- Usar `cachetools.TTLCache(maxsize=10_000, ttl=300)` ou similar. Bounded + TTL.
- Monitoring: expor métrica `cache_size_entries` e `cache_evictions_total`. Alerta se size próximo do maxsize por horas (sinal de undersized).
- Cache key inclui `empresa_id` pra isolar tenants. Eviction LRU respeita carga por tenant.

**Phase v2.2:** PROBE-CACHE-01 implementation — não inventar cache; usar `cachetools` (battle-tested).

---

### Pitfall 11: asyncio.create_task() perdendo referência (silent task drop)

**What goes wrong:** Retry exponencial implementado via `asyncio.create_task(retry_probe(...))` sem manter strong reference. Python 3.12+ garbage collector pode coletar a task antes de executar ([SuperFastPython](https://superfastpython.com/asyncio-disappearing-task-bug/)). Em produção sob load, retry simplesmente **não dispara**, sem erro visível.

**Why it happens:** Event loop só mantém weak references. Task sem strong ref pode ser coletada.

**Prevention:**
- Pattern obrigatório:
```python
_background_tasks: set[asyncio.Task] = set()

def schedule_retry(...):
    task = asyncio.create_task(retry_probe(...))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
```
- Preferir APScheduler `AsyncIOScheduler.add_job(...)` ao invés de `create_task` para retries com delay — APScheduler persiste e mantém ref.
- Code review checklist: nenhum `asyncio.create_task` solto sem set de refs.

**Phase v2.2:** PROBE-RETRY-01 — usar APScheduler, não create_task naked. Já está no stack.

---

### Pitfall 12: APScheduler job duplicação após restart

**What goes wrong:** APScheduler com persistence (datastore SQLAlchemy/MongoDB) preserva jobs entre restarts. Mas se jobstore não é configurado corretamente em ambiente Easypanel (Docker volume não persistido?), jobs duplicam ou perdem. Worse: dois workers (improvável aqui mas defensivo) leem mesmo jobstore, ambos disparam.

**Why it happens:** Single-instance Easypanel hoje. Mas migration futura ou redeploy com Docker volume não atrelado → jobstore in-memory implícito → jobs perdidos.

**Prevention:**
- Decisão arquitetural explícita: **APScheduler em modo in-memory** (jobs perdidos em restart) **OU** persistido em Postgres via SQLAlchemy jobstore.
- Se persistido: testar restart scenarios. Jobs do PROBE-RETRY-01 não devem disparar 2x.
- Se in-memory: garantir que reschedule no startup re-enfileira jobs pendentes a partir de `grupo_membership.entrou_em IS NULL AND criado_em > NOW - 10min`.

**Phase v2.2:** PROBE-RETRY-01 — definir explicitamente o modo. Default seguro: in-memory + reschedule no startup baseado em estado DB.

---

### Pitfall 13: RLS bloqueando webhook handler silenciosamente

**What goes wrong:** Migration 003 (commit 073c93f) hardening RLS. Webhook handler usa service role key — **se** algum caller acidentalmente usar anon key (ex: refactor que troca client), INSERT em `grupo_membership` retorna sem erro mas linha não persiste (RLS DENY).

**Why it happens:** Supabase RLS silenciosamente filtra. INSERT pode retornar 0 rows affected sem exception. ([RLS pitfalls Supabase community])

**Prevention:**
- Webhook handler **sempre** usa `supabase.client_admin()` (service role). Code review verifica não usa `client_anon()`.
- Após INSERT, verificar `rowcount` ou ler de volta. Se 0, log ERROR.
- Migration 003 mantém RLS em `grupo_membership` desde o início (não retroativo). Policy explícita: service role full access, anon zero.

**Detection:**
- Métrica: ratio inserts solicitados vs commits. Se discrepância, RLS interferindo.

**Phase v2.2:** MEMB-01 schema + RLS policy desde o deploy inicial.

---

### Pitfall 14: Webhook signature validation ausente

**What goes wrong:** v2.2 confia em `GROUP_PARTICIPANTS_UPDATE` como fonte da verdade. Endpoint exposto sem validação de signature/token. Atacante pode POST falso → marca lead como "no grupo" → bot manda dados sensíveis pro grupo errado.

**Why it happens:** Evolution API webhook config tem `webhookByEvents` + URL. Endpoint Leadflow não tem hoje signature check.

**Prevention:**
- Header de auth no webhook (Evolution suporta `apikey` no header). Endpoint valida `request.headers['apikey'] == EVOLUTION_WEBHOOK_TOKEN`.
- Whitelist IPs Evolution (Easypanel reverse proxy permite).
- HTTPS only (já é).

**Phase v2.2:** MEMB-02 — adicionar guard de auth no handler novo.

---

## Minor Pitfalls (degradam observabilidade ou DX)

### Pitfall 15: Audit log GRUPO_STATE_CHANGE sem `caller`

**What goes wrong:** FSM-AUDIT-02 grava transições. Mas se `caller` for inferido por stack frame, refactor quebra. Se passado como string, callers preguiçosos passam "unknown".

**Prevention:** `caller` é argumento **obrigatório** (sem default). Enum tipado se possível: `Caller.WEBHOOK_ADD`, `Caller.PROBE_RETRY`, etc.

**Phase v2.2:** FSM-AUDIT-02.

---

### Pitfall 16: Tabela `grupo_membership` crescendo sem retention

**What goes wrong:** Cada grupo criado adiciona N rows. Após anos, milhões de rows. Queries `WHERE saiu_em IS NULL` lentas.

**Prevention:**
- Indexes em `(empresa_id, grupo_jid)` + `(telefone, saiu_em)` + partial index `WHERE saiu_em IS NULL`.
- Job de archive trimestral pra rows com `saiu_em < NOW - 90 days`. Out-of-scope v2.2 mas planejar.

**Phase v2.2:** MEMB-01 — indexes definidos no schema desde início.

---

### Pitfall 17: Testes pytest do v2.2 sem fixture pra Evolution mock

**What goes wrong:** TEST-V2-G1..G5 não tem mock confiável da Evolution API. Testes flaky ou desabilitados em CI. Bug não detectado.

**Prevention:**
- Mock da Evolution como fixture pytest: `monkeypatch` `httpx.AsyncClient.post/get` para retornar payloads canônicos.
- Casos motivadores têm payloads reais salvos como JSON fixtures (Ana Carla webhook payload, Rosânia, etc.).
- CI gate: testes não podem ser skipped sem aprovação.

**Phase v2.2:** TEST-V2-G1..G5.

---

### Pitfall 18: Frontend `/admin/grupos` não reflete tabela nova

**What goes wrong:** Dashboard admin (v2.1 commit f97686c) consulta markers `LEAD_LID` em conversas. v2.2 escreve em `grupo_membership`. Dashboard fica defasado, operador não vê estado real.

**Prevention:** Endpoint `/admin/grupo/status` atualizado para consultar `grupo_membership` primeiro, marker como fallback. Frontend muda zero (só backend).

**Phase v2.2:** Fora do escopo principal, mas mencionar em ADMIN-update.

---

## Phase-Specific Warnings

| Phase v2.2 | Likely Pitfall | Mitigation |
|------------|---------------|------------|
| Phase 10 — Schema + RLS (`grupo_membership`) | Pitfall 4 (instance_key faltando), Pitfall 13 (RLS silently denying) | Schema review: instance_key column + RLS policy explícita service-role-only para writes |
| Phase 11 — Webhook handlers (3 paths) | Pitfall 1 (createGroup não dispara webhook), Pitfall 6 (race UPSERT), Pitfall 9 (out-of-order events), Pitfall 14 (signature missing) | UPSERT com `occurred_at` comparison + 3 paths (webhook ADD + MESSAGES_UPSERT + createGroup response) + auth header check |
| Phase 12 — `lead_in_group` read API + cache | Pitfall 2 (cache mascarando), Pitfall 10 (unbounded cache), Pitfall 6 (read race) | `cachetools.TTLCache` bounded + healthcheck `/health/grupo-membership` + advisory lock no read path |
| Phase 13 — Probe retry async | Pitfall 3 (retry converge antes webhook), Pitfall 5 (job 47h late), Pitfall 11 (create_task drop), Pitfall 12 (APScheduler duplication) | `max_age_seconds` absoluto + APScheduler `AsyncIOScheduler` (não create_task naked) + decisão explícita persistence in-memory vs DB |
| Phase 14 — LEAVE handler + saiu_em | Pitfall 9 (REMOVE before ADD), Pitfall 7 (FSM regression) | `occurred_at` ordering + LEAVE só transiciona via `set_grupo_state` com audit |
| Phase 15 — FSM hardening + audit | Pitfall 7 (caller esquecido bypassa), Pitfall 15 (caller field weak) | Single entrypoint enforce + grep CI check + `caller: Caller` enum tipado obrigatório |
| Phase 16 — Test suite regressão | Pitfall 17 (mock flaky) | Fixtures JSON com payloads reais dos 5 casos + CI gate sem skip |

---

## Compatibilidade com fixes do 08/06 (não regredir)

| Fix 08/06 | Risco em v2.2 | Como preservar |
|-----------|---------------|----------------|
| AQUEC-FLOOR-01 (180s) | Inverter probe→webhook pode tentar reduzir floor pra 30s pois "tabela é confiável" | Manter floor 180s mesmo com v2.2 — defesa em profundidade pra Evolution lenta + tempo do retry exponencial cobrir |
| ALERTA-GRUPO-01 (remove alerta grupo) | LEAVE-02 envia notif via DM — não confundir com alerta no grupo | LEAVE-02 sempre DM-first, nunca grupo |
| PROBE-BYPASS-01 (marker GRUPO_LEAD_ENTROU_CRIACAO <5min) | Substituível por `grupo_membership` se escrita no createGroup response — mas manter marker como camada extra | MEMB-02 path 3 (createGroup direct write) substitui marker funcionalmente; manter marker até v2.2 estável em prod |
| GRUPO-REUSO-01 (valida acesso) | `grupo_membership` retorna True falso pra grupo de instância antiga | Pitfall 4 — `instance_key` column + manter probe live no reuso |
| RECOVERY-STARTUP-01 (async) | APScheduler de v2.2 também rodar no startup | Padrão already established: tudo async no startup |
| RECOVERY-AQUEC-01 (janela 6h) | Retry exponencial pode reintroduzir items velhos | Pitfall 5 — `max_age_seconds` no retry handler + manter recovery janela 6h |

---

## "What might I have missed?" review

- **Multi-tenant cross-talk:** Cache key inclui `empresa_id`. Tabela `grupo_membership` filtra por `empresa_id`. Confirmar em todos os queries.
- **Convite-pendente vs grupo criado:** v2.1 tem `convites_pendentes` (Phase 9). `grupo_membership` é ortogonal — convite é DM/email pra entrar; membership é estado no grupo. Não confundir.
- **Backfill explicit out-of-scope:** PROJECT.md confirma. Não criar pitfall de "grupos antigos sem rows" — é decisão consciente.
- **MESSAGES_UPSERT match @lid → grupo_membership:** Path 2 da escrita. Reusa heurística unique-aguardando da v2.1 (commits 6b0295b). Se >1 lead aguardando no mesmo grupo, ignora — mesma regra.
- **Confirmação D-1:** Fase 4 18/05 já tem regra AND probe+FSM nos 3 sistemas. v2.2 muda probe pra "consulta `grupo_membership` primeiro". D-1 deve usar mesmo `lead_in_group()` central, não duplicar lógica.

---

## Sources

- [Webhook Reliability 2026: Idempotency & Retry Reference](https://www.digitalapplied.com/blog/webhook-reliability-idempotency-retries-engineering-reference-2026) — HIGH confidence
- [Hookdeck: How to Implement Webhook Idempotency](https://hookdeck.com/webhooks/guides/implement-webhook-idempotency) — HIGH
- [Webhook Best Practices: Idempotency and Event Ordering (BoldSign)](https://boldsign.com/blogs/webhook-best-practices-retries-idempotency/) — HIGH
- [You Can't Guarantee Webhook Ordering (HackerNoon)](https://hackernoon.com/you-cant-guarantee-webhook-ordering-heres-why) — MEDIUM
- [Treezor: Webhook Race Conditions](https://docs.treezor.com/guide/webhooks/race-conditions.html) — HIGH (provider docs)
- [Postgres ON CONFLICT race conditions (oneuptime)](https://oneuptime.com/blog/post/2026-01-25-postgresql-race-conditions/view) — HIGH
- [Postgres Upsert: INSERT ON CONFLICT in Practice (QueryPlane)](https://queryplane.com/docs/blog/postgres-upsert) — HIGH
- [PostgreSQL docs INSERT (official)](https://www.postgresql.org/docs/current/sql-insert.html) — HIGH
- [Asyncio Disappearing Task Bug (SuperFastPython)](https://superfastpython.com/asyncio-disappearing-task-bug/) — HIGH
- [Taming Asyncio: Production Patterns](https://timderzhavets.com/blog/taming-asyncio-production-patterns-that-prevent-silent/) — MEDIUM
- [Python Background Tasks — Asyncio Traps (DEV 2026)](https://dev.to/kaushikcoderpy/python-background-tasks-asyncio-traps-fastapi-celery-2026-381i) — MEDIUM
- [How to Find and Fix Memory Leaks in Python](https://knowledgelib.io/software/debugging/python-memory-leaks/2026) — HIGH
- [cachetools — Extensible memoizing collections (docs)](https://cachetools.readthedocs.io/) — HIGH (library docs)
- [APScheduler docs (Read the Docs)](https://apscheduler.readthedocs.io/en/master/api.html) — HIGH
- [Cache made consistent (Meta Engineering)](https://engineering.fb.com/2022/06/08/core-infra/cache-made-consistent/) — HIGH
- [Cache Invalidation: The Hardest Problem in Computer Science](https://dev.to/nk_sk_6f24fdd730188b284bf/cache-invalidation-the-hardest-problem-in-computer-science-3imd) — MEDIUM
- [Evolution API Webhooks Documentation](https://doc.evolution-api.com/v2/en/configuration/webhooks) — HIGH
- [WhatsApp Cloud API webhooks delayed (n8n community)](https://community.n8n.io/t/whatsapp-cloud-api-webhooks-delayed-by-minutes-to-hours/265580) — MEDIUM (community reports)
- [Reliable Webhook Handling Strategies (Sesame Disk)](https://sesamedisk.com/reliable-webhook-handling-strategies/) — MEDIUM
- Casos motivadores Leadflow 08-09/06 (Ana Carla, Rosânia, Fernanda, Valquíria, 553891500357) — HIGH (in-house evidence)
- Memórias projeto: `sessao_2026-05-20_grupo_lid_arquitetura.md`, `sessao_2026-05-19_fsm_bypass_e_convite_nominal.md` — HIGH (in-house)
