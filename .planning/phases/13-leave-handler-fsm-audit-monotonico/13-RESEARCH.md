# Phase 13: LEAVE handler + FSM audit monotônico — Research

**Researched:** 2026-06-09
**Domain:** grupo_membership REMOVE path + FSM hardening + audit markers
**Confidence:** HIGH — all findings drawn from live codebase reads

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LEAVE-01 | Webhook `GROUP_PARTICIPANTS_UPDATE action="remove"` marca `grupo_membership.saiu_em = messageTimestamp` + insere marker `LEAD_SAIU_GRUPO:{grupo_jid}:{ts}` em conversas (idempotente) | webhook handler em `grupo_webhook.py:104` já filtra `action != "add"` e retorna ignorado — adicionar branch `action == "remove"` nesse ponto; SQL UPDATE `saiu_em`; marker via `_claim_marker` ou insert direto |
| LEAVE-02 | Notif pré-reunião e D-1 detectam `saiu_em != null` via `lead_in_group()` E redirecionam para DM | `_query_membership_row` atualmente filtra `saiu_em IS NULL` — Fase 13 muda a semântica para retornar a row mesmo com `saiu_em` preenchido, expondo-a ao caller via `source='left_group'`; callers em `warmup_grupo.py:817` e `confirmacao_agendamento.py:313` adicionam branch `source == 'left_group'` → força DM |
| LEAVE-03 | FSM do lead que saiu volta para `FALLBACK_1_1` com flag `LEFT_GROUP` no marker GRUPO_STATE_CHANGE | chamada `set_grupo_state()` com novo estado `LEFT_GROUP` ou transição forçada para `FALLBACK_1_1` com `reason='LEFT_GROUP'` — depende de como FSM-AUDIT-02 define o marcador; decisão: ver seção FSM monotônico |
| FSM-AUDIT-01 | `set_grupo_state()` valida transição estritamente monotônica: `ATIVO->AGUARDANDO` BLOQUEADA sem `force=True` | a função atual (linha 104-127) não tem nenhuma validação de transição — só checa se `state in VALID_STATES`; adicionar tabela de transições permitidas + flag `force` |
| FSM-AUDIT-02 | Toda transição grava marker `GRUPO_STATE_CHANGE:{ag_id}:{from}:{to}:{reason}:{caller}` em conversas; argumento `caller` obrigatório sem default | `set_grupo_state` atual grava `GRUPO_STATE:{agendamento_id}:{state}` — formato novo é diferente; `get_grupo_state` precisa continuar lendo o formato antigo OU ambos são escritos em paralelo durante migração |
| FSM-AUDIT-03 | CI grep check garante que nenhum caller chama `set_grupo_state` sem `reason` e `caller` | 9 callsites identificados abaixo — todos precisam ser migrados; grep CI pode ser teste pytest que faz ast.parse + verifica kwargs |
</phase_requirements>

---

## Summary

Phase 13 fecha o ciclo de vida de membership do grupo. Tem dois eixos independentes mas que devem ser implementados na mesma phase: (1) o **LEAVE handler** que registra a saída do lead da tabela `grupo_membership` e redireciona confirmações para DM; e (2) o **FSM audit monotônico** que endurece `set_grupo_state()` com validação de ordem + audit log de cada transição com `caller` obrigatório.

O codebase já tem toda a infraestrutura necessária. O webhook handler (`grupo_webhook.py`) tem o ponto exato de extensão na linha 104 (onde `action != "add"` retorna `ignorado`). A tabela `grupo_membership` já tem coluna `saiu_em TIMESTAMPTZ NULL` e a migration 004 está aplicada. O FSM (`grupo_state.py`) é um módulo pequeno (208 linhas) com 3 funções públicas e 9 callsites identificados no repositório — todos precisam receber os novos kwargs `reason` e `caller`.

A mudança mais delicada é na `_query_membership_row`: atualmente filtra `saiu_em IS NULL`, o que faz `lead_in_group()` retornar `None` para leads que saíram (caindo no probe fallback). Fase 13 precisa **remover esse filtro** e deixar o caller distinguir via `source` — o que muda a semântica de toda a decision tree. A abordagem correta é: `_query_membership_row` retorna a row com `saiu_em` preenchido; `lead_in_group()` detecta `saiu_em is not null` e retorna `{'in_group': False, 'source': 'left_group', ...}` antes de ir ao probe.

**Primary recommendation:** Implementar em 3 plans sequenciais — (A) SQL RPC `mark_grupo_membership_left` + webhook REMOVE branch + marker LEAD_SAIU_GRUPO + FSM LEFT_GROUP; (B) `_query_membership_row` / `lead_in_group` mudança de semântica + callers D-1/notif redirect; (C) `set_grupo_state` monotônico + `caller` obrigatório + migration de 9 callsites + grep CI test.

---

## Standard Stack

### Core (sem dependências novas)

| Component | Version/Location | Purpose |
|-----------|-----------------|---------|
| `grupo_webhook.py` | `app/routers/grupo_webhook.py:84` | Ponto de entrada do webhook — função `_processar_grupo_payload` |
| `grupo_membership.py` | `app/services/grupo_membership.py` | `upsert_grupo_membership`, `_query_membership_row`, `lead_in_group`, `parse_evolution_timestamp` |
| `grupo_state.py` | `app/services/grupo_state.py` | FSM: `set_grupo_state`, `get_grupo_state`, `transition_grupo_state` |
| Supabase RPC pattern | migration 004 — `upsert_grupo_membership` | SQL DEFINER function para contornar limitação PostgREST + partial unique index |
| `_claim_marker` helper | `grupo_fallback.py:158` | Insert atômico de marker em `conversas` com idempotência via unique constraint |
| `conversas_sistema_unique_idx` | unique constraint em `conversas` | Garante idempotência de markers `role=sistema` |

### Sem dependências novas a adicionar

Esta fase não requer nenhuma nova biblioteca Python. Toda a infraestrutura (APScheduler, cachetools, supabase-py, asyncio.Lock) já está presente e operando.

---

## Architecture Patterns

### Projeto estrutural de conversas (markers)

O padrão canônico de insert de marker no projeto é:

```python
# Fonte: grupo_fallback.py:158-174 (_claim_marker helper)
sb.table("conversas").insert({
    "empresa_id": empresa_id,
    "telefone":   telefone,
    "role":       "sistema",
    "conteudo":   conteudo,   # ex: "GRUPO_STATE_CHANGE:{ag_id}:{from}:{to}:{reason}:{caller}"
    "criado_em":  datetime.utcnow().isoformat(),
}).execute()
```

Idempotência é garantida pela `conversas_sistema_unique_idx` (unique constraint). Colisão de insert = `unique violation` = ignorado silenciosamente. Markers `role=sistema` nunca são exibidos ao lead.

### GRUPO_STATE marker format atual vs novo

**Formato atual (get_grupo_state lê):**
```
GRUPO_STATE:{agendamento_id}:{state}
```

**Formato proposto para audit log (FSM-AUDIT-02):**
```
GRUPO_STATE_CHANGE:{ag_id}:{from}:{to}:{reason}:{caller}
```

**Decisão crítica para o planner:** são dois markers diferentes com prefixos diferentes. `get_grupo_state` continua lendo `GRUPO_STATE:` (prefixo antigo, append-only, mais recente vence). O novo `GRUPO_STATE_CHANGE:` é apenas para audit — não é consumido por `get_grupo_state`. Isso significa que `set_grupo_state` precisa escrever AMBOS: o marker antigo (para compatibilidade) + o novo audit marker. Alternativamente, pode-se migrar `get_grupo_state` para ler `GRUPO_STATE_CHANGE:` e extrair o `to` — mas isso quebra os markers históricos já no banco. A abordagem de dois markers em paralelo é mais segura e consistente com o padrão "nao regredir".

### Estrutura do webhook REMOVE handler

```python
# Em _processar_grupo_payload, após linha 104 (onde action != "add" retorna ignorado):
# Adicionar branch ANTES do return ignorado:

if action == "remove":
    # Mirror do bloco MEMB-02 (add) mas chama mark_grupo_membership_left
    _evento_ts = parse_evolution_timestamp(data.get("messageTimestamp") or payload.get("date_time"))
    for _tel_memb in telefones_saiu:
        _mark_left(sb, empresa_id, grupo_jid, telefone=_tel_memb, lid=None,
                   saiu_em=_evento_ts, instance_key=_instance_key_evento)
        _insert_leave_marker(sb, empresa_id, _tel_memb, grupo_jid, _evento_ts)
        _trigger_fsm_left_group(sb, empresa_id, _tel_memb, grupo_jid)
    for _lid_memb in lids_saiu:
        _mark_left(sb, empresa_id, grupo_jid, telefone=None, lid=_lid_memb,
                   saiu_em=_evento_ts, instance_key=_instance_key_evento)
    return {"ok": True, "grupo_jid": grupo_jid, "saidas_processadas": len(telefones_saiu)}
```

### SQL para marcar saída (novo RPC ou UPDATE direto)

O projeto usa RPC para UPSERT por causa da limitação do PostgREST com partial unique index. Para UPDATE simples (setar `saiu_em`) não há essa limitação — pode-se usar supabase-py diretamente:

```python
# UPDATE direto (sem RPC necessária para este caso)
result = sb.table('grupo_membership') \
    .update({'saiu_em': saiu_em.isoformat(), 'atualizado_em': datetime.utcnow().isoformat()}) \
    .eq('empresa_id', empresa_id) \
    .eq('grupo_jid', grupo_jid) \
    .eq('telefone', telefone) \   # ou .eq('lid', lid)
    .is_('saiu_em', 'null') \
    .execute()
```

Se `telefone OR lid` for necessário em um único UPDATE, o supabase-py `.or_()` funciona em UPDATE (diferente do UPSERT com partial unique). Uma alternativa mais limpa é uma nova RPC `mark_grupo_membership_left(p_empresa_id, p_grupo_jid, p_telefone, p_lid, p_saiu_em)` — consistente com o padrão da fase 10.

### Decision tree de `lead_in_group` após Fase 13

```
1. CACHE fast-path → probe_cache.get()  [sem mudança]
2. MEMBERSHIP DB → _query_membership_row() [MUDANÇA: remove filtro saiu_em IS NULL]
   2a. row.saiu_em is not None → return {in_group: False, source: 'left_group', ...}
   2b. ORPHAN check (instance_key mismatch) → return {source: 'orphan'}  [sem mudança]
   2c. row viva → return {in_group: True, source: 'membership'}  [sem mudança]
3. Probe fallback  [sem mudança]
```

O novo `source='left_group'` é o sinal que callers de D-1 e notif verificam para forçar DM.

### Pontos de redirect D-1 e notif pré-reunião

**confirmacao_agendamento.py — linha 311-316 (decisão destino):**
```python
_enviar_no_grupo = bool(
    _in_group_real_cf and _state_cf == STATE_ATIVO and grupo_jid
)
```
Fase 13 adiciona: se `_result_cf.get('source') == 'left_group'` → `_in_group_real_cf = False` (já seria False pelo `in_group: False`) + log `[CONFIRMACAO] lead saiu do grupo → DM forçado`.

**warmup_grupo.py — linha 817 (decisão destino notif):**
```python
if _in_group_real_nf and _fsm_ativo_nf and grupo_jid:
    _destino_nf = grupo_jid
else:
    _destino_nf = telefone ...
```
Fase 13 adiciona: checar `source == 'left_group'` nos kwargs do `lead_in_group` call na notif (linha ~801-806 que chama `ativar_fallback_se_necessario` — esse helper precisa propagar o source ou o caller precisa chamar `lead_in_group` diretamente para inspecionar `source`).

**Atenção:** `warmup_grupo.py` atualmente não chama `lead_in_group` diretamente para a notif — chama `ativar_fallback_se_necessario` (linha ~803). Esse helper retorna bool `_fallback_nf`, não o dict completo. Para expor `source='left_group'`, ou (a) `ativar_fallback_se_necessario` retorna um tuple `(bool, str_source)`, ou (b) notif chama `lead_in_group` diretamente após o check de fallback. Opção (b) é mais simples e não altera a assinatura do helper existente.

---

## FSM caller migration

### Mapa exaustivo de callsites de `set_grupo_state` / `transition_grupo_state`

Todos os callsites identificados via grep do repositório. **Todos precisam receber `reason` e `caller` obrigatórios após FSM-AUDIT-01/02.**

| # | Arquivo | Linha aprox. | State setado | Contexto | Caller sugerido |
|---|---------|-------------|-------------|---------|----------------|
| C1 | `app/services/grupo_state.py` | 142 | (qualquer) | `transition_grupo_state` chama `set_grupo_state` internamente — assinatura de `transition_grupo_state` também precisa de `reason`/`caller` para repassar | `caller` = quem chama `transition_grupo_state` |
| C2 | `app/routers/admin.py` | 917 | `STATE_ATIVO` | Ação `"promover_ativo"` — operador confirmou visualmente | `caller='admin_promover_ativo'` |
| C3 | `app/routers/leads.py` | 137 | `STATE_ATIVO` | Reuso de grupo existente — lead confirmado dentro via probe | `caller='leads_reuso_grupo'` |
| C4 | `app/routers/leads.py` | 256 | `STATE_ATIVO` | `promote_admin` via `updateParticipants` | `caller='leads_promote_admin'` |
| C5 | `app/services/grupo_fallback.py` | 278 | `STATE_ATIVO` | Lead já no grupo atual (Evolution confirma + legacy) — setado retroativamente | `caller='fallback_retroativo_ativo'` |
| C6 | `app/services/grupo_fallback.py` | 415 | `STATE_AGUARDANDO` | Criação do grupo — lead ainda não entrou | `caller='fallback_criar_grupo'` |
| C7 | `app/services/grupo_fallback.py` | ~890 | `STATE_FALLBACK_1_1` | Timer 30min expirou — via `transition_grupo_state` | `caller='fallback_timeout_30min'` |
| C8 | `app/services/grupo_fallback.py` | ~994 | `STATE_ATIVO` | Lead entrou no grupo — via `transition_grupo_state` | `caller='fallback_lead_entrou'` |
| C9 | **novo — Fase 13** | `grupo_webhook.py` novo | `LEFT_GROUP` ou `FALLBACK_1_1` | Lead saiu do grupo (REMOVE webhook) | `caller='webhook_remove'` |

**Nota sobre C1:** `transition_grupo_state` (linha 130) internamente chama `set_grupo_state`. Quando `set_grupo_state` recebe `caller`, `transition_grupo_state` precisa aceitar `reason` e `caller` como kwargs e repassar. Isso cascateia os callsites de `transition_grupo_state` (C7 e C8) que também precisam ser atualizados.

### Callsites de `transition_grupo_state` (chamam C7 e C8):

| # | Arquivo | Linha aprox. | Transição | Context |
|---|---------|-------------|----------|---------|
| T1 | `app/services/grupo_fallback.py` | ~890 | `AGUARDANDO → FALLBACK_1_1` | Job APScheduler timeout 30min (`_executar_timeout_grupo_aguardando`) |
| T2 | `app/services/grupo_fallback.py` | ~994 | `AGUARDANDO/FALLBACK_1_1 → ATIVO` | `processar_entrada_lead_no_grupo` — lead entrou |

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Idempotência do marker LEAD_SAIU_GRUPO | Checar existência antes de inserir | `_claim_marker` / unique constraint `conversas_sistema_unique_idx` | Webhook pode disparar 2x; constraint garante atomicidade sem lock |
| SQL UPDATE de `saiu_em` com telefone OR lid | Query Python em loop | RPC SQL nova `mark_grupo_membership_left` (consistente com padrão da migration 004) OU `.or_()` em UPDATE supabase-py | `.or_()` em UPDATE funciona (diferente do UPSERT com partial unique que precisa de RPC) |
| Monotonia FSM | Mapa de transições hardcoded em `set_grupo_state` | Tabela `ALLOWED_TRANSITIONS` em `grupo_state.py` | Centraliza lógica; callers não sabem sobre monotonicidade |
| Grep CI check de `caller` | Script shell ad-hoc | Teste pytest com `ast.parse` no módulo (padrão estabelecido em `test_grupo_fallback_migration.py`) | Mesmo padrão dos testes de regressão de migration da Fase 11 |
| Dashboard timeline | Endpoint novo separado | Augmentar `/admin/grupo/status` (retorna `GRUPO_STATE:` markers) para também retornar `GRUPO_STATE_CHANGE:` markers ordenados por `criado_em` | Reutiliza auth + infra existente |

---

## Common Pitfalls

### Pitfall 1: Filtro `saiu_em IS NULL` em `_query_membership_row` — mudança de semântica
**What goes wrong:** Remover o filtro `saiu_em IS NULL` da query faz `_query_membership_row` retornar rows de leads que saíram. Callers que hoje assumem `row is not None → lead está no grupo` passam a ter comportamento errado.
**Why it happens:** Atualmente a ausência de row (`None`) e a presença de row são as únicas semânticas. Com a mudança, row presente mas `saiu_em not null` é um terceiro estado.
**How to avoid:** `lead_in_group` precisa checar `row.get('saiu_em')` ANTES do orphan check e retornar `{in_group: False, source: 'left_group'}` imediatamente. `_probe_retry_job` também chama `_query_membership_row` diretamente — precisa ser atualizado para não confundir "row com saiu_em" como "row viva".
**Warning signs:** Log `[MEMB-LOOKUP] source=membership in_group=True` para lead que saiu do grupo.

### Pitfall 2: `ATIVO -> AGUARDANDO` retroativo em callsite C5
**What goes wrong:** O callsite C5 (`grupo_fallback.py:278`) faz `set_grupo_state(..., STATE_ATIVO)` com guard `get_grupo_state() is None` (só seta se nunca foi setado). Após Fase 13, `ATIVO -> AGUARDANDO` será BLOQUEADO sem `force=True`. Mas C5 só seta ATIVO quando state é None — portanto não é uma regressão de monotonicidade. A atenção é em C3/C4 que setam ATIVO sem checar o estado atual — se por algum bug o lead já estiver em LEFT_GROUP e o sistema tentar setar ATIVO, o guard monotônico vai bloquear corretamente.
**How to avoid:** O guard monotônico precisa definir `LEFT_GROUP` como estado terminal — nenhuma transição a partir dele exceto via `force=True` admin.

### Pitfall 3: Dois formatos de marker (GRUPO_STATE vs GRUPO_STATE_CHANGE)
**What goes wrong:** `get_grupo_state` lê `GRUPO_STATE:{ag_id}:{state}` com `.like("conteudo", f"GRUPO_STATE:{agendamento_id}:%")`. Se `GRUPO_STATE_CHANGE:` markers forem escritos com prefixo diferente, o `like` vai incluí-los no resultado e o parser `parts = ct.split(":")` vai quebrar (parts terá 6 elementos em vez de 3).
**How to avoid:** O prefixo `GRUPO_STATE_CHANGE:` começa com `GRUPO_STATE_` que faz match no `.like("conteudo", "GRUPO_STATE:%")`. O parser em `get_grupo_state` (linha 96: `if len(parts) >= 3 and parts[2] in VALID_STATES`) vai **falhar silenciosamente** se `parts[2]` for o `from` do audit log em vez de um estado válido. **Solução: mudar o like query para `GRUPO_STATE:{agendamento_id}:%` (já é o que faz) — o problema é que o prefixo do audit log precisa ser distinto. Usar `GSC:` ou manter `GRUPO_STATE_CHANGE:` e corrigir o like em `get_grupo_state` para `.eq("conteudo", ...)` ou usar `.like("conteudo", f"GRUPO_STATE:{agendamento_id}:[A-Z]%")` — mas supabase-py não suporta regex no `.like`. A solução mais simples: mudar `get_grupo_state` para filtrar `like "GRUPO_STATE:{ag_id}:%" AND NOT like "GRUPO_STATE_CHANGE:%"` — mas `.not_.like()` aninhado é verboso. Alternativa limpa: o audit marker usa exatamente o prefixo `GSC:` em vez de `GRUPO_STATE_CHANGE:`.**
**Warning signs:** `get_grupo_state` retorna `None` mesmo após transição (parts[2] não está em VALID_STATES).

### Pitfall 4: `_probe_retry_job` usa `_query_membership_row` diretamente
**What goes wrong:** `_probe_retry_job` (grupo_membership.py:566) chama `_query_membership_row` e considera `row is not None` como "lead está no grupo" (short-circuit). Se a query passar a retornar rows com `saiu_em != null`, o job vai acreditar que o lead está no grupo e parar a chain prematuramente.
**How to avoid:** `_probe_retry_job` precisa checar `row.get('saiu_em')` antes de fazer short-circuit. Se `saiu_em is not None` → `in_group = False` (lead saiu), não cacheia como True, continua chain (ou encerra graciosamente).

### Pitfall 5: marker LEAD_SAIU_GRUPO não é idempotente pelo unique constraint
**What goes wrong:** O marker `LEAD_SAIU_GRUPO:{grupo_jid}:{ts}` inclui `{ts}` no conteúdo — dois webhooks REMOVE com timestamps diferentes geram dois markers diferentes (não colidem no unique constraint). O mesmo lead teria dois markers de saída.
**How to avoid:** O marker de saída **não deve incluir `{ts}` no conteúdo** se precisar ser idempotente via unique constraint. Use `LEAD_SAIU_GRUPO:{grupo_jid}` (sem ts) e deixe o `criado_em` da conversas registrar quando aconteceu. O timestamp da saída fica em `grupo_membership.saiu_em` (fonte de verdade). Alternativamente, aceite múltiplos markers de saída (semanticamente correto — idempotência está no UPDATE do `saiu_em` que é idempotente via `WHERE saiu_em IS NULL`).

### Pitfall 6: Monotonia FSM — o que é "BLOQUEADO" para o admin
**What goes wrong:** FSM-AUDIT-01 diz que `ATIVO -> AGUARDANDO` deve ser BLOQUEADA sem `force=True`. O único caller que pode fazer isso é o endpoint admin `promover_ativo` — mas ele vai de `None/AGUARDANDO → ATIVO`, não de `ATIVO → AGUARDANDO`. Na prática, nenhum código atual faz `ATIVO → AGUARDANDO` — é uma prevenção profilática. O risco é bloquear algo que não existe e quebrar um edge case não mapeado.
**How to avoid:** Auditar os 9 callsites e confirmar que nenhum faz `ATIVO → AGUARDANDO` intencionalmente antes de ligar o guard. Se o guard bloquear C5 (que checa `state is None` antes), não há problema. O único caso preocupante seria um bug futuro tentando "resetar" o FSM de um lead que entrou no grupo.

---

## REMOVE webhook — infrastructure map

### Ponto de extensão exato no webhook handler

`grupo_webhook.py` — função `_processar_grupo_payload`, linha **104**:
```python
if action != "add":
    return {"ok": True, "ignorado": True, "motivo": f"action={action}"}
```

Esta linha é o ponto de inserção. A estrutura atual **não processa `remove`** — apenas retorna ignorado. A Fase 13 insere um branch `if action == "remove": ...` ANTES desse return.

### Parsing de participantes (mirror do bloco add)

O bloco de parsing (linhas 116-132) coleta `telefones_entraram` e `lids_entraram`. Para o REMOVE handler, o mesmo bloco produz `telefones_saiu` e `lids_saiu` — usando o mesmo código de parsing (as strings `@s.whatsapp.net` e `@lid` são estruturalmente idênticas no payload).

### `parse_evolution_timestamp` — disponível e testado

A função `parse_evolution_timestamp` (grupo_membership.py:442) foi implementada na Fase 10 e cobre:
- int/float epoch segundos (Baileys padrão)
- int/float epoch ms (> 10^12)
- string ISO 8601 ou string epoch
- None/missing → fallback `datetime.utcnow()`

O webhook REMOVE usa o mesmo caminho: `data.get("messageTimestamp") or payload.get("date_time")`.

### `_instance_key_evento` — já resolvido

```python
_instance_key_evento = (payload.get("instance") or "").strip()
```

Mesmo padrão do ADD handler. Pitfall 3 da Fase 10 (usar `payload.instance` em vez de lookup `empresas.evolution_instancia`) já está documentado e aplicado.

---

## saiu_em consumer — mudanças em `_query_membership_row`

### Estado atual (Fase 11, linha 103)
```python
.is_('saiu_em', 'null')  # filtra APENAS rows vivas
```

### Estado pós-Fase 13
Remover o filtro `.is_('saiu_em', 'null')`. A query retorna a row mais recente (por `atualizado_em DESC LIMIT 1`) independente de `saiu_em`. O campo `saiu_em` é incluído no SELECT (já está: linha 100 seleciona `entrou_em, saiu_em, instance_key, atualizado_em, telefone, lid`).

### Mudança em `lead_in_group` — novo branch em STEP 2

```python
if row is not None:
    # FASE 13: lead saiu do grupo (saiu_em preenchido)
    if row.get('saiu_em') is not None:
        return _emit_log({
            'in_group': False,
            'source': 'left_group',
            'instance_key_match': None,
            'last_event_at': row.get('saiu_em'),
        })
    # STEP 3 — ORPHAN check (caso Fernanda) [sem mudança]
    ...
```

### Impacto no `_probe_retry_job`

`_probe_retry_job` (linha ~587) faz:
```python
row = _query_membership_row(sb, empresa_id, grupo_jid, telefone, lid)
if row is not None:
    probe_cache.set(empresa_id, grupo_jid, telefone, lid, True)
    return  # short-circuit
```

Após Fase 13, precisa ser:
```python
row = _query_membership_row(sb, empresa_id, grupo_jid, telefone, lid)
if row is not None:
    if row.get('saiu_em') is not None:
        # Lead saiu — não cacheia como True, encerra chain graciosamente
        print(f"[PROBE-RETRY] lead saiu do grupo (saiu_em={row['saiu_em']}) — chain encerrada")
        return
    probe_cache.set(empresa_id, grupo_jid, telefone, lid, True)
    return
```

---

## FSM monotônico — arquitetura detalhada

### Estado atual de `set_grupo_state` (grupo_state.py:104-127)

```python
def set_grupo_state(sb, empresa_id: str, telefone: str,
                    agendamento_id: str, state: str) -> bool:
    if state not in VALID_STATES:
        print(f"[GRUPO-STATE] estado invalido {state!r}")
        return False
    if not (empresa_id and telefone and agendamento_id):
        return False
    try:
        sb.table("conversas").insert({...
            "conteudo": f"GRUPO_STATE:{agendamento_id}:{state}",
        }).execute()
        return True
    except Exception as e:
        ...
```

**Problemas:** sem validação de transição, sem `caller`, sem `reason`, sem audit log.

### Proposta para Fase 13

```python
STATE_LEFT_GROUP = "LEFT_GROUP"  # novo estado terminal

VALID_STATES = {STATE_AGUARDANDO, STATE_FALLBACK_1_1, STATE_ATIVO, STATE_LEFT_GROUP}

# Transições monotônicas permitidas (sem force=True):
# None → qualquer estado (primeiro set)
# AGUARDANDO → FALLBACK_1_1
# AGUARDANDO → ATIVO
# FALLBACK_1_1 → ATIVO
# qualquer → LEFT_GROUP (lead saiu — sempre permitido)
#
# BLOQUEADAS sem force=True:
# ATIVO → AGUARDANDO (regressão — só admin)
# ATIVO → FALLBACK_1_1 (regressão — só admin)
# LEFT_GROUP → qualquer (terminal — só admin)

ALLOWED_TRANSITIONS: dict[str | None, set[str]] = {
    None:               {STATE_AGUARDANDO, STATE_FALLBACK_1_1, STATE_ATIVO, STATE_LEFT_GROUP},
    STATE_AGUARDANDO:   {STATE_FALLBACK_1_1, STATE_ATIVO, STATE_LEFT_GROUP},
    STATE_FALLBACK_1_1: {STATE_ATIVO, STATE_LEFT_GROUP},
    STATE_ATIVO:        {STATE_LEFT_GROUP},  # somente LEFT_GROUP sem force
    STATE_LEFT_GROUP:   set(),              # terminal — nada sem force
}

def set_grupo_state(
    sb,
    empresa_id: str,
    telefone: str,
    agendamento_id: str,
    state: str,
    *,
    reason: str,   # obrigatório, sem default
    caller: str,   # obrigatório, sem default
    force: bool = False,
) -> bool:
    ...
```

### `transition_grupo_state` — cascata de kwargs

`transition_grupo_state` (linha 130) chama `set_grupo_state` internamente. Precisa aceitar e repassar `reason` e `caller`:

```python
def transition_grupo_state(sb, empresa_id, telefone, agendamento_id,
                            from_states, to_state, *, reason, caller, force=False) -> bool:
    current = get_grupo_state(sb, empresa_id, agendamento_id)
    if current not in from_states:
        print(f"[GRUPO-STATE] {agendamento_id[:8]} BLOCKED: {current!r} not in {from_states}")
        # FSM-AUDIT-02: gravar marker BLOCKED mesmo em recusa
        _insert_audit_marker(sb, empresa_id, telefone, agendamento_id,
                             from_state=current, to_state=to_state,
                             reason=f"BLOCKED:{reason}", caller=caller)
        return False
    return set_grupo_state(sb, empresa_id, telefone, agendamento_id, to_state,
                           reason=reason, caller=caller, force=force)
```

### Audit marker format

O success criterion SC4 exige `GRUPO_STATE_CHANGE:{ag_id}:{from}:{to}:{reason}:{caller}`. Para evitar colisão com `get_grupo_state` (que faz `.like("GRUPO_STATE:{ag_id}:%")`), o prefixo do audit marker deve ser **diferente**. Duas opções:

**Opção A (recomendada):** `GSC:{ag_id}:{from}:{to}:{reason}:{caller}`
- `get_grupo_state` usa `.like("GRUPO_STATE:{ag_id}:%")` — não captura `GSC:` markers
- Zero risco de colisão
- `get_grupo_state` não precisa ser alterado

**Opção B:** `GRUPO_STATE_CHANGE:{ag_id}:{from}:{to}:{reason}:{caller}`
- `get_grupo_state` usa `.like("GRUPO_STATE:%")` — captura AMBOS os prefixos (pois `GRUPO_STATE_CHANGE:` começa com `GRUPO_STATE_`)
- Requer correção no `.like()` de `get_grupo_state`: trocar para `.like(f"GRUPO_STATE:{agendamento_id}:%").not_.like("GRUPO_STATE_CHANGE:%")` — supabase-py suporta `.not_.like()` em colunas mas a sintaxe é `q.neq` ou filter chain

O success criterion SC5 usa o formato `GRUPO_STATE_CHANGE:` no enunciado. O planner deve decidir entre Opção A (zero risco de colisão) vs Opção B (match exato com requirement text mas requer patch em `get_grupo_state`). **Research recomenda Opção A com log de alias** — `set_grupo_state` escreve marker com prefixo `GSC:` internamente; o requirement de leitura no dashboard apenas filtra por `GSC:`.

### CI grep check (FSM-AUDIT-03)

O projeto já tem precedente em `test_grupo_fallback_migration.py` (usa `ast.parse` + regex no source). Para o check de `caller`, a abordagem mais robusta é um teste pytest que:

1. Lê o source de `grupo_state.py`
2. Verifica que `caller` não tem valor default (usa `ast` para checar assinatura)
3. Lê todos os arquivos `.py` do projeto
4. Faz `ast.parse` + walk para achar calls a `set_grupo_state` e `transition_grupo_state`
5. Verifica que nenhuma call tem `caller="unknown"` ou omite `caller`

Alternativamente: teste de string simples que faz grep por `set_grupo_state(` sem `caller=` no mesmo bloco de texto. O ast.parse é mais robusto mas mais verboso. O padrão do projeto usa ambos (grep via regex + assert em source).

---

## `/admin/grupos` dashboard — audit timeline

### Estado atual (`/admin/grupo/status`)

O endpoint `/admin/grupo/status` (admin.py:784-874) lê markers `GRUPO_STATE:{ag_id}:{state}` de `conversas`, dedupa por `(telefone, ag_id)` mantendo o mais recente, e retorna lista de leads com estado atual.

**Para adicionar timeline auditável (FSM-AUDIT-02):** o mesmo endpoint pode retornar os audit markers `GSC:` por agendamento quando solicitado com query param `?timeline=true`. A query adicional:

```python
# Se timeline=true, busca todos GSC: markers para os agendamento_ids retornados
if timeline:
    gsc_q = sb.table("conversas").select("telefone,conteudo,criado_em") \
        .eq("empresa_id", empresa_id).eq("role", "sistema") \
        .like("conteudo", "GSC:%") \
        .order("criado_em", desc=False).limit(5000).execute()
    # Agrupa por agendamento_id e adiciona como lista `state_timeline` em cada item
```

Isso não requer novo endpoint — apenas query param adicional em endpoint existente.

### Frontend (escopo mínimo)

O success criterion SC5 menciona "query do dashboard `/admin/grupos` exibe timeline auditável". O frontend `/admin/grupos` (v2.1, commit 8d9fe5c) consome `/admin/grupo/status`. Para Fase 13, o planner deve verificar se o frontend precisa mudança ou se a timeline é suficiente como JSON no endpoint. O requirement não menciona novo componente UI — apenas "exibe timeline auditável". Backend-only é suficiente se o frontend já renderiza o JSON do endpoint.

---

## Validation Architecture

### Test framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `leadflow-backend/` (sem pytest.ini; usa `pyproject.toml` ou default) |
| Quick run command | `cd leadflow-backend && pytest tests/ -x -q` |
| Full suite command | `cd leadflow-backend && pytest tests/ -v` |
| Conftest | `tests/conftest.py` — stub de `app.services.evolution` para evitar httpx→idna circular import |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | File sugerido | Automated Command |
|--------|----------|-----------|--------------|-------------------|
| LEAVE-01 | Webhook REMOVE marca `saiu_em` + insere marker LEAD_SAIU_GRUPO (idempotente) | unit | `tests/test_leave_handler.py` | `pytest tests/test_leave_handler.py -x` |
| LEAVE-01 | Segunda chamada REMOVE com mesmo (empresa, grupo, tel) não duplica marker | unit (idempotency) | `tests/test_leave_handler.py` | idem |
| LEAVE-02 | `lead_in_group()` com row `saiu_em != null` retorna `{in_group: False, source: 'left_group'}` | unit | `tests/test_lead_in_group_decision.py` (ampliar existente) | `pytest tests/test_lead_in_group_decision.py -x` |
| LEAVE-02 | D-1 com `source='left_group'` escolhe DM em vez de grupo | unit | `tests/test_leave_handler.py` | `pytest tests/test_leave_handler.py -x` |
| LEAVE-03 | Webhook REMOVE aciona transição FSM para `FALLBACK_1_1` (com flag LEFT_GROUP em marker) | unit | `tests/test_leave_handler.py` | idem |
| FSM-AUDIT-01 | `ATIVO → AGUARDANDO` sem `force=True` é bloqueado e retorna False | unit | `tests/test_fsm_monotonic.py` | `pytest tests/test_fsm_monotonic.py -x` |
| FSM-AUDIT-01 | `ATIVO → AGUARDANDO` com `force=True` passa (admin path) | unit | `tests/test_fsm_monotonic.py` | idem |
| FSM-AUDIT-01 | `LEFT_GROUP → ATIVO` sem `force=True` é bloqueado | unit | `tests/test_fsm_monotonic.py` | idem |
| FSM-AUDIT-02 | Toda transição escreve marker `GSC:{ag_id}:{from}:{to}:{reason}:{caller}` em conversas | unit | `tests/test_fsm_monotonic.py` | idem |
| FSM-AUDIT-02 | Transição bloqueada escreve marker `GSC:...:BLOCKED:{reason}:{caller}` | unit | `tests/test_fsm_monotonic.py` | idem |
| FSM-AUDIT-03 | `set_grupo_state` não aceita `caller` com default via inspeção AST | static/grep | `tests/test_fsm_caller_ci.py` | `pytest tests/test_fsm_caller_ci.py -x` |
| FSM-AUDIT-03 | Nenhum callsite no repositório chama `set_grupo_state` sem `caller=` | static/grep | `tests/test_fsm_caller_ci.py` | idem |
| LEAVE-02 (probe_retry) | `_probe_retry_job` com row `saiu_em != null` encerra chain sem cachear True | unit | `tests/test_probe_retry.py` (ampliar existente) | `pytest tests/test_probe_retry.py -x` |

### Detalhes de implementação dos testes

**`tests/test_leave_handler.py` (novo — Wave 0):**
- Testar `_processar_grupo_payload` com `action="remove"` — verificar que `grupo_membership.saiu_em` é atualizado (mock supabase)
- Testar idempotência: segunda chamada com mesmo (empresa, grupo, tel) não falha (mock do UPDATE retorna 0 rows afetadas graciosamente)
- Testar marker `LEAD_SAIU_GRUPO:{grupo_jid}` em conversas via `_claim_marker`
- Testar que FSM transiciona para `FALLBACK_1_1` (ou `LEFT_GROUP`) via mock de `set_grupo_state`

**`tests/test_fsm_monotonic.py` (novo — Wave 0):**
- Testar todas as transições da `ALLOWED_TRANSITIONS` table: válidas passam, inválidas retornam False
- Testar que audit marker é escrito em conversas em todas as transições (mock supabase)
- Testar `force=True` desbloqueia transições bloqueadas
- Testar que `transition_grupo_state` repassa `reason` e `caller` para `set_grupo_state`

**`tests/test_fsm_caller_ci.py` (novo — Wave 0):**
```python
import ast, pathlib, re

def test_set_grupo_state_has_no_default_caller():
    """FSM-AUDIT-03: caller não tem default na assinatura."""
    src = pathlib.Path("app/services/grupo_state.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "set_grupo_state":
            # caller deve estar em args.args ou kwonlyargs sem default
            kwonly = [a.arg for a in node.args.kwonlyargs]
            assert "caller" in kwonly, "caller não é kwarg"
            # verificar sem default: kw_defaults para posição de caller
            idx = kwonly.index("caller")
            assert node.args.kw_defaults[idx] is None, "caller tem default!"

def test_no_callsite_omits_caller():
    """FSM-AUDIT-03: nenhum callsite omite caller."""
    py_files = list(pathlib.Path("app").rglob("*.py"))
    for f in py_files:
        src = f.read_text()
        # Heurística: linhas com set_grupo_state( mas sem caller=
        for i, line in enumerate(src.splitlines()):
            if "set_grupo_state(" in line and "caller=" not in line:
                # Pode ser a definição — pular
                if "def set_grupo_state" in line:
                    continue
                assert False, f"{f}:{i+1} — set_grupo_state sem caller="
```

**Ampliação de `tests/test_lead_in_group_decision.py`:**
- Adicionar test case: `_query_membership_row` retorna row com `saiu_em="2026-06-09T23:00:00"` → `lead_in_group` retorna `{in_group: False, source: 'left_group'}`
- Verificar que probe Evolution não é chamado quando `source='left_group'` (short-circuit antes do STEP 4)

### Sampling Rate
- **Per task commit:** `pytest tests/test_leave_handler.py tests/test_fsm_monotonic.py tests/test_fsm_caller_ci.py -x -q`
- **Per wave merge:** `pytest tests/ -q`
- **Phase gate:** Full suite green antes de `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_leave_handler.py` — novo, cobre LEAVE-01/02/03
- [ ] `tests/test_fsm_monotonic.py` — novo, cobre FSM-AUDIT-01/02
- [ ] `tests/test_fsm_caller_ci.py` — novo, cobre FSM-AUDIT-03
- [ ] Nova RPC SQL `mark_grupo_membership_left` em migration 005 (ou inline UPDATE em grupo_membership.py — decidir no plano)
- [ ] `STATE_LEFT_GROUP` constant + `ALLOWED_TRANSITIONS` dict em `grupo_state.py`

---

## Environment Availability

Esta fase é código/config-only com dependências existentes. Nenhuma nova dependência de runtime.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| supabase-py | `grupo_membership.py`, `grupo_state.py` | Sim | Existente | — |
| APScheduler | `grupo_membership.py` (probe retry) | Sim | 3.10.4 | — |
| pytest + pytest-asyncio | Testes | Sim | Existente | — |
| Migration 004 `grupo_membership` | tabela `saiu_em` column | Sim (aplicada) | — | — |

---

## Open Questions

1. **RPC vs UPDATE direto para marcar saída**
   - O que sabemos: UPDATE por `(empresa_id, grupo_jid, telefone) WHERE saiu_em IS NULL` é expressável diretamente em supabase-py com `.or_()` para cobrir `telefone OR lid`. Diferente do UPSERT com partial unique, o UPDATE não tem limitação PostgREST.
   - O que é incerto: se há edge case em que `telefone` é null e `lid` é o único identificador — o UPDATE `OR` em supabase-py precisa ser testado.
   - Recommendation: Usar UPDATE direto (sem nova RPC) para marcar saída. Mais simples, sem nova migration de função SQL. Se `telefone OR lid` precisar de `.or_()` em UPDATE, testar no Wave 0.

2. **`LEFT_GROUP` como estado FSM ou apenas flag no marker**
   - O que sabemos: LEAVE-03 diz "FSM volta pra `FALLBACK_1_1` (com flag `LEFT_GROUP` no marker GRUPO_STATE_CHANGE)". FSM-AUDIT-01 menciona transições `AGUARDANDO→FALLBACK_1_1→ATIVO` como monotônicas. SC6 diz "Lead que saiu volta pra FSM `LEFT_GROUP` (novo estado terminal)".
   - Contradição aparente: LEAVE-03 diz `FALLBACK_1_1`, SC6 diz `LEFT_GROUP`. O requirement LEAVE-03 no REQUIREMENTS.md diz `FALLBACK_1_1 com flag LEFT_GROUP no marker`. O SC6 no enunciado da fase diz `LEFT_GROUP` como estado terminal.
   - Recommendation: Implementar `LEFT_GROUP` como estado FSM real (adicionar à `VALID_STATES`). A transição é `ATIVO → LEFT_GROUP` (ou qualquer estado → LEFT_GROUP). O marker de transição `GSC:{ag_id}:ATIVO:LEFT_GROUP:webhook_remove:webhook_remove` já carrega a flag implicitamente. `FALLBACK_1_1` não é o destino certo pois o lead SAIU — não está em "fallback aguardando" mas em estado terminal.

3. **Callers de D-1 e notif: inspecionar `source` vs boolean flag**
   - O que sabemos: `warmup_grupo.py` não chama `lead_in_group` diretamente para notif — chama `ativar_fallback_se_necessario` que retorna bool.
   - O que é incerto: se `ativar_fallback_se_necessario` precisa ser alterado para retornar `source` ou se a notif deve chamar `lead_in_group` diretamente após o check de fallback.
   - Recommendation: A notif deve fazer dois checks em sequência: (1) `ativar_fallback_se_necessario` como hoje (para decidir ATIVO vs FALLBACK), (2) se `grupo_jid` existe, chamar `lead_in_group` para verificar `source == 'left_group'` — forçar DM sem chamar probe se já sabe que saiu. Alternativa mais limpa: `ativar_fallback_se_necessario` aceita kwarg `return_source=True` e retorna `(bool, str)`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | O filtro `.is_('saiu_em', 'null')` pode ser removido de `_query_membership_row` sem quebrar callers que assumem `row is not None → in_group=True` — desde que `lead_in_group` cheque `row.saiu_em` antes do orphan check | saiu_em consumer | Se algum caller interno de `_query_membership_row` (fora de `lead_in_group`) assume row não nula como in_group=True, esse caller vai ter falso positivo |
| A2 | `conversas_sistema_unique_idx` cobre o marker `LEAD_SAIU_GRUPO:{grupo_jid}` (sem timestamp) para idempotência de dois webhooks REMOVE | marker idempotency | Se o unique index não existir ou não cobrir todos os campos necessários, markers duplicados serão inseridos |
| A3 | supabase-py `.or_()` funciona em UPDATE (não apenas em SELECT) para cobrir `telefone OR lid` no UPDATE de saiu_em | SQL UPDATE | Se `.or_()` não funcionar em UPDATE, precisa de nova RPC SQL |
| A4 | O prefixo `GSC:` (short for `GRUPO_STATE_CHANGE:`) não colide com nenhum marker existente | FSM audit marker | Se houver markers `GSC:` preexistentes no banco, a query de dashboard vai misturar dados |

---

## Sources

### Primary (HIGH confidence — leitura direta do codebase)
- `leadflow-backend/app/services/grupo_state.py` — FSM completo: estados, assinatura `set_grupo_state`, callsites
- `leadflow-backend/app/services/grupo_membership.py` — `_query_membership_row`, `lead_in_group`, `upsert_grupo_membership`, `_probe_retry_job`
- `leadflow-backend/app/routers/grupo_webhook.py` — handler webhook, ponto de extensão REMOVE
- `leadflow-backend/app/routers/admin.py:784-874` — `/admin/grupo/status` endpoint
- `leadflow-backend/app/routers/confirmacao_agendamento.py:265-320` — decisão de destino D-1
- `leadflow-backend/app/routers/warmup_grupo.py:779-830` — decisão de destino notif pré-reunião
- `leadflow-backend/app/db/migrations/004_grupo_membership.sql` — schema `grupo_membership`, partial unique index, RPC
- `leadflow-backend/app/services/grupo_fallback.py:158-174` — `_claim_marker` helper (padrão canonical de marker insert)
- `.planning/REQUIREMENTS.md:95-105` — LEAVE-01/02/03, FSM-AUDIT-01/02/03 completos
- `.planning/STATE.md` — histórico de decisões v2.2

### Secondary (MEDIUM confidence — summaries de phases anteriores)
- `.planning/phases/10-*/10-01-SUMMARY.md` — confirma `parse_evolution_timestamp` e padrão de `instance_key = payload.instance`
- `.planning/phases/11-*/11-01-SUMMARY.md` — confirma `_query_membership_row` com `saiu_em IS NULL` e nota explícita "Fase 13 mexe aqui"

---

## Metadata

**Confidence breakdown:**
- Webhook REMOVE handler point: HIGH — leitura direta de `grupo_webhook.py:104`
- FSM callsite map: HIGH — grep exaustivo, 9 callsites enumerados com arquivo:linha
- `_query_membership_row` change: HIGH — comentário explícito no código "Fase 13 mexe aqui"
- `lead_in_group` source='left_group': HIGH — decision tree lida linha por linha
- D-1/notif redirect points: HIGH — código lido em `confirmacao_agendamento.py:311-316` e `warmup_grupo.py:817`
- SQL UPDATE para saiu_em: MEDIUM — supabase-py `.or_()` em UPDATE não testado neste repo (vs SELECT onde funciona)
- Dashboard timeline: MEDIUM — endpoint lido; formato do query param e frontend não verificados

**Research date:** 2026-06-09
**Valid until:** 2026-06-30 (codebase estável — sem dependências externas novas)
