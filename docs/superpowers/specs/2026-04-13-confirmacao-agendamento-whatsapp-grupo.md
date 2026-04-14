# Confirmação de Agendamento via WhatsApp Grupo — Design Spec

## Overview

Nova funcionalidade no módulo de Agendamento do Leadflow: após um agendamento ser criado, a Bia envia automaticamente uma mensagem de confirmação no WhatsApp grupo do lead no dia da reunião, em horário configurável. O lead responde no grupo. Com base na resposta (ou ausência dela), o sistema segue fluxos distintos.

---

## Contexto e Posição na UI

Nova seção na aba **Agenda → Configurações**, posicionada entre:
- "Aquecimento de grupo WhatsApp" (seção anterior)
- "Notificações pré-reunião" (seção seguinte)

O grupo de WhatsApp referenciado é o grupo criado pelo sistema para aquecimento de leads, identificado pelo marcador `GRUPO_WA_ID:` na tabela `conversas`.

---

## Fluxo Completo

```
Agendamento criado
      │
      ▼
job_confirmacao agendado para HH:MM do dia da reunião
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
           → Injeta contexto de reagendamento no conversas 1-1
           → Bia abre conversa privada com o lead

Bia agenda nova reunião via 1-1
      │
      ▼
Hook em criar_agendamento detecta agendamento anterior (negada/timeout)
      │
      ▼
Cancela agendamento antigo
Atualiza nome do grupo para nova data
Agenda novo job_confirmacao para nova data
```

---

## Banco de Dados

### Tabela `agendamentos` — novas colunas

```sql
ALTER TABLE agendamentos
  ADD COLUMN confirmacao_status TEXT DEFAULT 'pendente',
  -- valores: 'pendente' | 'enviada' | 'confirmada' | 'negada' | 'timeout' | 'reagendando'
  ADD COLUMN confirmacao_enviada_em TIMESTAMPTZ;
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

Variáveis suportadas: `{nome}`, `{hora}`, `{data}`

---

## Backend

### Novos Jobs APScheduler

#### `job_confirmacao_{agendamento_id}`

Agendado no momento da criação do agendamento, para `confirmacao_horario` no dia da reunião.

Responsabilidades:
1. Verifica se `confirmacao_ativa` é `true` na config da empresa
2. Busca grupo do lead via `conversas` (marcador `GRUPO_WA_ID:`)
3. Substitui variáveis na `confirmacao_mensagem`
4. Envia mensagem via Evolution API para o JID do grupo (`@g.us`)
5. Atualiza `confirmacao_status = 'enviada'` e `confirmacao_enviada_em = now()`
6. Agenda `job_confirmacao_timeout_{agendamento_id}` para `now() + confirmacao_timeout_min`

#### `job_confirmacao_timeout_{agendamento_id}`

Responsabilidades:
1. Verifica se `confirmacao_status` ainda é `'enviada'` — se não, cancela (lead já respondeu)
2. Atualiza `confirmacao_status = 'timeout'`
3. Envia `confirmacao_msg_negativa` no grupo
4. Injeta mensagem de sistema no `conversas` 1-1 do lead:
   ```
   [SISTEMA: Lead não confirmou presença na reunião agendada para {data} às {hora}.
   Inicie reagendamento: apresente-se cordialmente, explique a situação e ofereça novos slots.]
   ```
5. Envia `confirmacao_msg_abertura_privado` via Evolution API no chat 1-1 do lead

### Extensão do Webhook em `agente.py`

Quando chega mensagem com JID `@g.us`:

1. Ignora se mensagem é do próprio bot (botMessageContextInfo)
2. Busca agendamento ativo da empresa cujo grupo corresponde ao JID
3. Se `confirmacao_status != 'enviada'`: ignora (não está esperando confirmação)
4. Classifica a mensagem:
   - **Positivo**: `sim`, `confirmo`, `pode`, `estarei`, `vou estar`, `✅`, `👍`, `s`, `ok`
   - **Negativo**: `não`, `nao`, `não posso`, `nao posso`, `cancelar`, `❌`, `👎`, `n`
   - **Outros**: ignora (não aciona Bia)
5. **Fluxo positivo**:
   - Atualiza `confirmacao_status = 'confirmada'`
   - Cancela `job_confirmacao_timeout_{agendamento_id}`
   - Substitui variáveis em `confirmacao_msg_positiva`
   - Envia mensagem no grupo via Evolution API
6. **Fluxo negativo**:
   - Atualiza `confirmacao_status = 'negada'`
   - Cancela `job_confirmacao_timeout_{agendamento_id}`
   - Envia `confirmacao_msg_negativa` no grupo
   - Injeta contexto de reagendamento no `conversas` 1-1
   - Envia `confirmacao_msg_abertura_privado` no chat 1-1

### Hook em `criar_agendamento`

Ao criar novo agendamento via fluxo 1-1, antes de salvar:

1. Busca agendamentos anteriores do mesmo lead com `confirmacao_status IN ('negada', 'timeout')`
2. Se encontrar:
   - Cancela o agendamento anterior (status `cancelado`)
   - Cancela jobs APScheduler relacionados ao agendamento anterior
   - Atualiza nome do grupo WhatsApp via Evolution API para refletir nova data
   - Remove a mensagem de sistema de reagendamento do `conversas` (ou adiciona nova com nova data)
3. Prossegue com criação normal do novo agendamento
4. Agenda `job_confirmacao` para o novo agendamento (se `confirmacao_ativa`)

---

## Frontend

### Nova Seção: "Confirmação de Agendamento"

Localização: `leadflow-frontend/src/pages/AgendaConfigPage.tsx` (ou equivalente), entre os cards de Aquecimento e Notificações pré-reunião.

**Campos:**

| Campo | Tipo | Descrição |
|-------|------|-----------|
| Ativar confirmação | Toggle | Liga/desliga toda a funcionalidade |
| Horário de envio | `<input type="time">` | Horário que a mensagem vai para o grupo |
| Timeout sem resposta | `<input type="number">` + label "minutos" | Quanto aguardar antes de acionar 1-1 |
| Mensagem de confirmação | `<textarea>` | Pergunta enviada no grupo. Variáveis: `{nome}`, `{hora}`, `{data}` |
| Mensagem quando confirmado | `<textarea>` | Resposta no grupo quando lead confirma. Variáveis: `{nome}`, `{hora}` |
| Mensagem quando negado/timeout | `<textarea>` | Resposta no grupo quando lead nega ou não responde. Variáveis: `{nome}` |
| Mensagem de abertura 1-1 | `<textarea>` | Primeira mensagem da Bia no privado. Variáveis: `{nome}`, `{hora}`, `{data}` |

Cada textarea exibe um preview abaixo com as variáveis substituídas por dados de exemplo.

Segue o padrão visual dos demais cards da página (sem componentes novos). Salva via `PUT /configuracoes/agendamento` já existente (ou endpoint equivalente), atualizando o campo `config_agendamento` da empresa.

---

## Identificação do Grupo do Lead

O grupo é identificado via tabela `conversas`, buscando registros com:
- `lead_id = {lead_id}`
- `canal = 'whatsapp'`
- `conteudo LIKE 'GRUPO_WA_ID:%'`

O JID do grupo é extraído do marcador `GRUPO_WA_ID:{jid}`.

---

## Limites e Regras de Negócio

- Se o lead não tiver grupo criado, a confirmação é silenciosamente pulada (log de warning)
- Se a empresa não tiver Evolution instância configurada, confirmação é pulada
- Apenas a **primeira** resposta no grupo é considerada (subsequentes ignoradas)
- O webhook de grupos só processa mensagens de grupos com marcador `GRUPO_WA_ID` no `conversas` — outras mensagens de grupos são ignoradas
- Jobs são cancelados/reagendados atomicamente ao reagendar via 1-1
- Confirmação só é agendada se `confirmacao_ativa = true` na config da empresa

---

## Arquivos Afetados

**Backend:**
- `leadflow-backend/app/routers/agendamento.py` — hook em criar_agendamento, novo endpoint config
- `leadflow-backend/app/routers/agente.py` — extensão do webhook para grupos
- `leadflow-backend/app/scheduler.py` (ou equivalente) — novos jobs APScheduler
- Migração SQL: nova colunas em `agendamentos`

**Frontend:**
- `leadflow-frontend/src/pages/AgendaConfigPage.tsx` (ou equivalente) — nova seção UI
- Tipos TypeScript: atualizar `config_agendamento` type

---

## Fora de Escopo

- Reagendamento via grupo (lead escolhe novo slot dentro do grupo) — não implementado
- Confirmação via canal que não seja WhatsApp
- Múltiplas tentativas de confirmação no mesmo dia
