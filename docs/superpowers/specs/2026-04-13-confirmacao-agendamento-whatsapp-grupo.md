# Confirmação de Agendamento via WhatsApp Grupo — Design Spec

## Overview

Nova funcionalidade no módulo de Agendamento do Leadflow: após um agendamento ser criado, a Bia envia automaticamente uma mensagem de confirmação no WhatsApp grupo do lead no dia da reunião, em horário configurável. O lead responde no grupo. Com base na resposta (ou ausência dela), o sistema segue fluxos distintos.

---

## Contexto e Posição na UI

Nova seção na aba **Agenda → Configurações**, posicionada entre:
- "Aquecimento de grupo WhatsApp" (seção anterior — linha 546 de `AgendaPage.tsx`)
- "Notificações pré-reunião" (seção seguinte — linha 623 de `AgendaPage.tsx`)

O grupo de WhatsApp referenciado é o grupo criado pelo sistema para aquecimento de leads, identificado pelo marcador `GRUPO_WA_ID:` na tabela `conversas`.

---

## Fluxo Completo

```
Agendamento criado (inline em agente.py ~linha 2461)
      │
      ▼
Captura ID do novo agendamento (result.data[0]["id"])
Agenda job_confirmacao para HH:MM do dia da reunião
      │
      ▼
[HH:MM do dia] Mensagem de confirmação enviada no grupo
      │
      ├─── Lead responde POSITIVO no grupo
      │         │
      │         ▼
      │    "Perfeito! Te esperamos às HH:MM 😊" enviado no grupo
      │    confirmacao_status = 'confirmada'
      │    → Segue para notificações pré-reunião
      │
      ├─── Lead responde NEGATIVO no grupo
      │         │
      │         ▼
      │    "Sem problemas! Iremos te enviar no privado novos horários..." enviado no grupo
      │    confirmacao_status = 'negada'
      │    → Injeta contexto de reagendamento no conversas 1-1
      │    → Bia abre conversa privada com o lead
      │
      └─── Timeout (sem resposta após X minutos)
                │
                ▼
           confirmacao_status = 'timeout'
           → Envia confirmacao_msg_negativa no grupo
           → Injeta contexto de reagendamento no conversas 1-1
           → Bia abre conversa privada com o lead

Bia agenda nova reunião via 1-1 (inline em agente.py ~linha 2461)
      │
      ▼
Detecta agendamento anterior (negada/timeout, status != 'cancelado') do mesmo lead
      │
      ▼
Cancela agendamento antigo
Atualiza nome do grupo para nova data
Agenda novo job_confirmacao para a nova data
```

---

## Banco de Dados

### Tabela `agendamentos` — novas colunas

```sql
ALTER TABLE agendamentos
  ADD COLUMN confirmacao_status TEXT DEFAULT 'pendente',
  -- valores: 'pendente' | 'enviada' | 'confirmada' | 'negada' | 'timeout'
  ADD COLUMN confirmacao_enviada_em TIMESTAMPTZ,
  ADD COLUMN grupo_jid TEXT;
  -- JID do grupo WhatsApp (@g.us) associado ao lead no momento do agendamento
  -- Populado ao criar o agendamento, buscando GRUPO_WA_ID no conversas do lead
```

### `config_agendamento` JSONB na tabela `empresas` — novos campos

```json
{
  "confirmacao_ativa": true,
  "confirmacao_horario": "08:00",
  "confirmacao_timeout_min": 120,
  "confirmacao_mensagem": "Olá {nome}! Confirmando sua reunião hoje às {hora}. Você confirma presença? ✅ Sim / ❌ Não",
  "confirmacao_msg_positiva": "Perfeito! Te esperamos às {hora} 😊",
  "confirmacao_msg_negativa": "Sem problemas! Iremos te enviar no privado novos horários de agendamento. Caso queira marcar, é só escolher o horário 😉",
  "confirmacao_msg_abertura_privado": "Oi {nome}! Vi que não conseguimos confirmar sua reunião de {data} às {hora}. Posso te oferecer novos horários?"
}
```

Variáveis suportadas por campo:
- `confirmacao_mensagem`: `{nome}`, `{hora}`, `{data}`
- `confirmacao_msg_positiva`: `{nome}`, `{hora}`
- `confirmacao_msg_negativa`: `{nome}` — variáveis `{hora}` e `{data}` **não** incluídas por design; a mensagem é genérica de redirecionamento
- `confirmacao_msg_abertura_privado`: `{nome}`, `{hora}`, `{data}`

---

## Backend

### Captura de ID e Grupo ao Criar Agendamento (inline `agente.py` ~linha 2461)

O insert atual em `agendamentos` não armazena o resultado. Mudar para capturar o ID e o JID do grupo:

```python
# Busca JID do grupo do lead antes do insert (usa telefone — coluna existente em conversas)
_grupo_row = sb.table("conversas") \
    .select("conteudo") \
    .eq("empresa_id", empresa_id) \
    .eq("telefone", numero) \
    .like("conteudo", "GRUPO_WA_ID:%") \
    .limit(1).execute()
_grupo_jid = None
if _grupo_row.data:
    _grupo_jid = _grupo_row.data[0]["conteudo"].split("GRUPO_WA_ID:")[1].strip()

# Insert com select para capturar ID retornado
_ag_result = sb.table("agendamentos").insert({
    ...campos existentes...,
    "grupo_jid": _grupo_jid,
}).execute()
_novo_agendamento_id = _ag_result.data[0]["id"]

# Agenda job de confirmação se ativado e grupo disponível
_conf_ativa = (config_empresa or {}).get("confirmacao_ativa", False)
if _conf_ativa and _grupo_jid:
    agendar_job_confirmacao(_novo_agendamento_id, data_hora_reuniao, empresa_id)
elif _conf_ativa and not _grupo_jid:
    print(f"[CONFIRMACAO] lead {lead_id_ag} sem grupo — confirmação não agendada")
```

A variável do lead neste bloco é `lead_id_ag` (linha 2439), não `lead_id` (linha 1467).

A função `agendar_job_confirmacao` fica em `scheduler.py`.

**Same-day booking:** Se `confirmacao_horario` já passou no dia do agendamento (ex: reunião marcada às 15h, horário de confirmação é 08h), o job **não é agendado** — loga warning e segue sem confirmação. Não tentar compensar com horário imediato.

---

### Novos Jobs APScheduler (`scheduler.py`)

#### `job_confirmacao_{agendamento_id}`

Agendado para `confirmacao_horario` no dia da reunião (fuso da empresa).

Responsabilidades:
1. Busca agendamento: `id = agendamento_id` — join com `leads` para obter `nome` e `telefone`
2. Busca config da empresa via `empresa_id` do agendamento: `config_agendamento`
3. Verifica `confirmacao_ativa = true` — se não, encerra
4. Usa `grupo_jid` já armazenado na linha do agendamento (sem re-query em `conversas`)
5. Se `grupo_jid` é null: loga warning e encerra
6. Substitui variáveis na `confirmacao_mensagem` com `nome`, `hora`, `data` do lead/reunião
7. Envia mensagem via Evolution API para `grupo_jid`
8. Atualiza `confirmacao_status = 'enviada'` e `confirmacao_enviada_em = now()`
9. Agenda `job_confirmacao_timeout_{agendamento_id}` para `now() + confirmacao_timeout_min minutos`

#### `job_confirmacao_timeout_{agendamento_id}`

Responsabilidades:
1. Busca agendamento — join `leads` para `nome`, `telefone`, `hora`, `data`
2. Busca config da empresa via `empresa_id` do agendamento para obter `confirmacao_timeout_min` e mensagens
3. Verifica `confirmacao_status == 'enviada'` — se não, encerra (lead já respondeu)
4. Atualiza `confirmacao_status = 'timeout'`
5. Envia `confirmacao_msg_negativa` (variável `{nome}` substituída) no `grupo_jid`
6. Insere nova linha em `conversas` (padrão existente: `telefone`, `role`, sem `lead_id`/`canal`):
   ```python
   sb.table("conversas").insert({
       "empresa_id": empresa_id,
       "telefone": telefone_lead,
       "role": "sistema",
       "conteudo": f"[SISTEMA: Lead não confirmou presença na reunião de {data} às {hora}. "
                   "Inicie reagendamento: apresente-se cordialmente, explique a situação e ofereça novos slots.]"
   }).execute()
   ```
7. Envia `confirmacao_msg_abertura_privado` (variáveis substituídas) via Evolution API para `{telefone}@s.whatsapp.net`

#### `recuperar_confirmacoes_pendentes()` (chamada no startup em `scheduler.py`)

Padrão existente para recovery após restart do servidor:

1. Busca `agendamentos` com `confirmacao_status = 'pendente'` e `data_hora > now()` — join `leads` para `nome` e `telefone`; por agendamento, busca config da empresa via `empresa_id`
2. Para cada um: chama `agendar_job_confirmacao(id, data_hora, empresa_id)` se job ainda não existe no scheduler
3. Busca `agendamentos` com `confirmacao_status = 'enviada'` — join `leads` para `telefone`; por agendamento, lê `timeout_min` do `config_agendamento` da empresa correspondente
4. Para cada um: calcula `run_date = confirmacao_enviada_em + timeout_min`. Se `run_date > now()`: agenda `job_confirmacao_timeout_{id}`

**Nota multi-tenant:** `timeout_min` é lido da config da empresa de cada agendamento individualmente — não existe valor global.

---

### Extensão do Webhook em `agente.py`

**Posição no código:** inserir o branch `@g.us` **após** o bloco `fromMe` que retorna na linha 1268, e **antes** da extração de `numero_remoto` na linha 1271:

```python
# linha 1268: return {"ok": True, "ignorado": True, "motivo": "fromMe"}

# INSERIR AQUI — após o fromMe return, antes do numero_remoto
numero_remoto_raw = key.get("remoteJid", "")
if numero_remoto_raw.endswith("@g.us"):
    await _processar_confirmacao_grupo(numero_remoto_raw, key, body, empresa_id, sb)
    return {"status": "ok"}

# linha 1271: numero_remoto = key.get("remoteJid", "")  ← já existente
```

Dessa forma, mensagens de bot (`fromMe=True`) em grupos já são descartadas pelo guard existente antes de chegar no branch `@g.us`.

**Função `_processar_confirmacao_grupo(grupo_jid, key, body, empresa_id, sb)`:**

1. Extrai `participant = key.get("participant", "")` — remetente real em grupos
2. Extrai texto da mensagem do payload (mesmo helper usado no fluxo 1-1). Se vazio (sticker, imagem, reação): retorna silenciosamente
3. Busca agendamento: `empresa_id = X AND grupo_jid = grupo_jid AND status != 'cancelado' AND confirmacao_status = 'enviada'` — join `leads` para `telefone`
4. Se nenhum: retorna silenciosamente
5. Normaliza `participant` para somente dígitos (remove `@s.whatsapp.net`, `+`, espaços). Normaliza `telefone` do lead da mesma forma. Se não baterem: retorna silenciosamente (outro participante)
6. Classifica o texto (strip, lower):
   - **Positivo**: `sim`, `confirmo`, `pode`, `estarei`, `vou estar`, `✅`, `👍`, `s`, `ok`, `claro`, `com certeza`
   - **Negativo**: `não`, `nao`, `não posso`, `nao posso`, `cancelar`, `❌`, `👎`, `n`, `impossível`, `impossivel`
   - **Outros**: retorna silenciosamente
7. **Fluxo positivo**:
   - Atualiza `confirmacao_status = 'confirmada'`
   - Tenta cancelar `job_confirmacao_timeout_{agendamento_id}` no scheduler (ignorar `JobLookupError`)
   - Substitui variáveis em `confirmacao_msg_positiva`, envia no grupo
8. **Fluxo negativo**:
   - Atualiza `confirmacao_status = 'negada'`
   - Tenta cancelar `job_confirmacao_timeout_{agendamento_id}` no scheduler
   - Envia `confirmacao_msg_negativa` no grupo
   - Insere linha em `conversas` com instrução de reagendamento (mesmo formato do timeout)
   - Envia `confirmacao_msg_abertura_privado` no chat 1-1 do lead

---

### Hook de Reagendamento (inline em `agente.py` após insert do novo agendamento)

Quando Bia cria novo agendamento via 1-1, após capturar `_novo_agendamento_id`. A variável do lead neste bloco é `lead_id_ag` (linha 2439):

```python
# Detecta agendamento anterior para reagendamento
_ag_anteriores = sb.table("agendamentos") \
    .select("id, grupo_jid") \
    .eq("empresa_id", empresa_id) \
    .eq("lead_id", lead_id_ag) \
    .in_("confirmacao_status", ["negada", "timeout"]) \
    .neq("status", "cancelado") \
    .execute()

for _ag_ant in (_ag_anteriores.data or []):
    # Cancela agendamento antigo
    sb.table("agendamentos").update({"status": "cancelado"}) \
        .eq("id", _ag_ant["id"]).execute()
    # Remove jobs do scheduler
    for _jname in [f"job_confirmacao_{_ag_ant['id']}",
                   f"job_confirmacao_timeout_{_ag_ant['id']}"]:
        try: scheduler.remove_job(_jname)
        except: pass
    # Atualiza nome do grupo WhatsApp
    if _ag_ant.get("grupo_jid"):
        _novo_nome_grupo = f"Reunião - {nome_lead} - {nova_data_formatada}"
        # nova_data_formatada: DD/MM/YYYY extraído do novo agendamento
        requests.put(
            f"{EVOLUTION_URL}/group/updateGroupSubject/{instancia}",
            json={"groupJid": _ag_ant["grupo_jid"], "subject": _novo_nome_grupo},
            headers={"apikey": EVOLUTION_KEY}
        )
    # Injeta contexto de reagendamento (append-only)
    sb.table("conversas").insert({
        "empresa_id": empresa_id,
        "telefone": numero,
        "role": "sistema",
        "conteudo": f"[SISTEMA: Reagendamento concluído. Nova reunião em {nova_data_formatada} às {nova_hora}. Fluxo de confirmação reiniciado.]"
    }).execute()
```

Após o loop: agenda `job_confirmacao_{_novo_agendamento_id}` para o novo agendamento (se `confirmacao_ativa = true` e `_grupo_jid` disponível).

**Nome do grupo no reagendamento:** formato `"Reunião - {nome_lead} - {DD/MM/YYYY}"`. `nome_lead` vem do objeto `lead_atual.data[0]` já disponível neste bloco. A data é formatada em `DD/MM/YYYY` a partir de `data_hora_reuniao`.

---

## Frontend

### Nova Seção: "Confirmação de Agendamento"

**Localização exata:** `leadflow-frontend/src/modules/agenda/AgendaPage.tsx`, componente `AbaConfig`, inserir entre a linha 622 (fim do card "Aquecimento de grupo WhatsApp") e a linha 623 (início do card "Notificações pré-reunião (grupo)").

A seção usa o mesmo estado `config` já existente no componente, adicionando os campos `confirmacao_*` no `useState`.

**Campos:**

| Campo | Tipo | Variáveis disponíveis |
|-------|------|-----------------------|
| Ativar confirmação | Toggle | — |
| Horário de envio | `<input type="time">` | — |
| Timeout sem resposta | `<input type="number">` + "minutos" | — |
| Mensagem de confirmação | `<textarea>` | `{nome}`, `{hora}`, `{data}` |
| Mensagem quando confirmado | `<textarea>` | `{nome}`, `{hora}` |
| Mensagem quando negado/timeout | `<textarea>` | `{nome}` |
| Mensagem de abertura 1-1 | `<textarea>` | `{nome}`, `{hora}`, `{data}` |

Cada textarea exibe preview imediatamente abaixo com variáveis substituídas por dados de exemplo ("Maria", "14:00", "13/04/2026").

Segue o padrão visual dos demais cards da página (`<Card>`, `<CardHeader>`, `<CardContent>`) sem componentes novos. Persiste via `POST /agendamentos/config` já existente.

**Inicialização do estado** — em `fetchConfig()` (existente em `AbaConfig`), ao ler `data.config_agendamento`, popular os novos campos com defaults se ausentes:

```typescript
confirmacao_ativa: raw.confirmacao_ativa ?? false,
confirmacao_horario: raw.confirmacao_horario ?? '08:00',
confirmacao_timeout_min: raw.confirmacao_timeout_min ?? 120,
confirmacao_mensagem: raw.confirmacao_mensagem ?? 'Olá {nome}! Confirmando sua reunião hoje às {hora}. Você confirma presença? ✅ Sim / ❌ Não',
confirmacao_msg_positiva: raw.confirmacao_msg_positiva ?? 'Perfeito! Te esperamos às {hora} 😊',
confirmacao_msg_negativa: raw.confirmacao_msg_negativa ?? 'Sem problemas! Iremos te enviar no privado novos horários de agendamento. Caso queira marcar, é só escolher o horário 😉',
confirmacao_msg_abertura_privado: raw.confirmacao_msg_abertura_privado ?? 'Oi {nome}! Vi que não conseguimos confirmar sua reunião de {data} às {hora}. Posso te oferecer novos horários?',
```

---

## Limites e Regras de Negócio

- Se `grupo_jid` for null ao criar agendamento → confirmação não agendada (log warning)
- Se a empresa não tiver Evolution instância configurada → confirmação pulada
- Apenas a **primeira** resposta válida (positivo ou negativo) do lead no grupo é processada — subsequentes ignoradas
- Mensagens de outros participantes do grupo são ignoradas (filtro por `participant == telefone_lead` normalizado)
- Branch `@g.us` inserido após o `fromMe` return (linha 1268), antes de `numero_remoto` (linha 1271) — mensagens do bot em grupos já descartadas pelo guard existente
- Same-day booking com `confirmacao_horario` já passado: job não agendado, sem tentativa de reagendar imediatamente
- `confirmacao_msg_negativa` suporta apenas `{nome}` por design — mensagem genérica de redirecionamento
- `timeout_min` lido por agendamento da config da empresa correspondente (multi-tenant)
- `conversas` é append-only — nenhuma linha deletada, nova linha de sistema substitui o contexto para a Bia
- Nome do grupo no reagendamento: `"Reunião - {nome_lead} - {DD/MM/YYYY}"`

---

## Arquivos Afetados

**Backend:**
- `leadflow-backend/app/routers/agente.py`:
  - Insert em `agendamentos` (~linha 2461): capturar ID retornado, buscar e salvar `grupo_jid`, chamar `agendar_job_confirmacao`
  - Hook de reagendamento: após o insert do novo agendamento, cancelar agendamento anterior se `confirmacao_status IN ('negada', 'timeout')` e `status != 'cancelado'`; usar variável `lead_id_ag`
  - Webhook: inserir branch `@g.us` entre linhas 1268–1271; implementar `_processar_confirmacao_grupo`
- `leadflow-backend/app/scheduler.py`:
  - Função `agendar_job_confirmacao(agendamento_id, data_hora, empresa_id)`
  - Job `job_confirmacao_{id}`
  - Job `job_confirmacao_timeout_{id}`
  - Função `recuperar_confirmacoes_pendentes()` — chamada no startup
- `leadflow-backend/app/routers/agendamentos.py`: verificar se `POST /agendamentos/config` serializa JSONB sem mudanças (apenas validar)
- Migração SQL: colunas `confirmacao_status`, `confirmacao_enviada_em`, `grupo_jid` em `agendamentos`

**Frontend:**
- `leadflow-frontend/src/modules/agenda/AgendaPage.tsx` — nova seção em `AbaConfig`, entre linhas 622–623; atualizar `useState` e `fetchConfig`

---

## Fora de Escopo

- Reagendamento via grupo (lead escolhe novo slot dentro do grupo) — não implementado
- Confirmação via canal que não seja WhatsApp
- Múltiplas tentativas de confirmação no mesmo dia
