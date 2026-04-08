# Concerns

## Summary
LeadsFlow tem falhas arquiteturais críticas concentradas no agente de IA: sem máquina de estados real, lógica de fluxo baseada em string matching frágil, sem concorrência, e jobs APScheduler perdidos a cada redeploy. Mais de 30 blocos `except: pass` silenciam falhas em caminhos críticos.

---

## AI Agent (Critical)

### Sem máquina de estados real
- **Severity**: Critical
- **File**: `leadflow-backend/app/routers/agente.py`
- **Description**: A posição no fluxo é detectada escaneando mensagens recentes por substrings em português (`"correto?"`, `"é isso mesmo?"`, `"marcadinho"`). Qualquer mudança de texto quebra o fluxo silenciosamente.
- **Impact**: Agente perde posição no fluxo após reordenação de mensagens ou mudança de wording.

### Persona hardcoded por cliente
- **Severity**: Critical
- **File**: `leadflow-backend/app/routers/agente.py` (linhas ~1775–1783)
- **Description**: Q1/Q2 messages têm copy hardcoded ("Sou a Bia do time da Rejane Leal"). Cada novo cliente requer mudança de código, não de configuração.
- **Impact**: Sistema não é multi-tenant para agente — impossível onboar outro cliente sem fork do código.

### Sem proteção a concorrência
- **Severity**: Critical
- **File**: `leadflow-backend/app/routers/agente.py`
- **Description**: Duas mensagens simultâneas do mesmo lead leem o mesmo histórico stale e podem ambas enviar Q1 ou criar eventos duplicados no Calendar.
- **Impact**: Race condition real em qualquer lead que responda rapidamente ou duplo-clique.

### Histórico limitado a 20 mensagens
- **Severity**: High
- **File**: `leadflow-backend/app/routers/agente.py` (linha ~1334)
- **Description**: Conversas com mais de 20 trocas reativam Q1, reiniciando o fluxo do zero.
- **Impact**: Leads mais engajados (justamente os melhores) têm pior experiência.

### Modo escuta sem expiração ou toggle
- **Severity**: High
- **File**: `leadflow-backend/app/routers/agente.py`
- **Description**: `HUMANO_ASSUMIU:` no banco bloqueia IA permanentemente. Sem UI para reverter, sem expiração automática.
- **Impact**: Lead fica preso fora do fluxo automatizado indefinidamente.

### Lógica OpenAI/Gemini duplicada
- **Severity**: Medium
- **File**: `leadflow-backend/app/routers/agente.py`
- **Description**: ~600 linhas de lógica de slot-building duplicadas para cada provider LLM.
- **Impact**: Bugs corrigidos em um provider não são corrigidos no outro.

---

## Reliability

### 30+ `except Exception: pass` em caminhos críticos
- **Severity**: Critical
- **File**: `webhook.py`, `leads.py`, `warmup_grupo.py`, `agendamento_tasks.py`
- **Description**: Falhas em atualização de status do lead, saves no Calendar, links Zoom e marcadores de conversa são silenciosamente engolidas.
- **Impact**: Leads ficam em estado inconsistente sem nenhum log de erro.

### APScheduler in-memory — jobs perdidos no redeploy
- **Severity**: Critical
- **File**: `leadflow-backend/app/main.py` e routers de scheduling
- **Description**: Todos os follow-ups e jobs de aquecimento existem apenas em memória. A cada redeploy, são perdidos. Heurística de recovery existe mas tem janela de 7 dias e pode perder leads.
- **Impact**: Leads agendados perdem notificações pré-reunião após qualquer redeploy.

### OAuth síncrono bloqueando event loop
- **Severity**: High
- **File**: `leadflow-backend/app/services/google_calendar.py`
- **Description**: Token refresh usa `httpx.post()` síncrono dentro de `async def`, bloqueando o event loop por até 10s por mensagem com Calendar integrado.
- **Impact**: Degrada toda a API durante uso do Google Calendar.

### Webhook sem idempotência
- **Severity**: High
- **File**: `leadflow-backend/app/routers/webhook.py`
- **Description**: POST duplicado da plataforma de formulário cria leads duplicados e envia mensagens duplicadas.
- **Impact**: Leads recebem dupla comunicação; stats de leads inflados.

### Supabase client sem pooling
- **Severity**: Medium
- **File**: `leadflow-backend/app/db/client.py`
- **Description**: `get_supabase()` cria novo cliente a cada request.
- **Impact**: Overhead de conexão em alta carga.

---

## Architecture

### Webhook sem verificação de assinatura
- **Severity**: Critical
- **File**: `leadflow-backend/app/routers/webhook.py`
- **Description**: Qualquer requisição POST com empresa_id e api_key na URL é aceita. Sem HMAC ou assinatura do payload.
- **Impact**: Endpoint pode ser abusado por qualquer pessoa que descubra a URL.

### Evolution webhook sem autenticação real
- **Severity**: High
- **File**: `leadflow-backend/app/routers/agente.py`
- **Description**: Webhook de entrada da Evolution resolve empresa escaneando todos os registros — sem token de verificação.
- **Impact**: Qualquer sistema pode injetar mensagens falsas no agente.

### Estado de máquina como strings no banco de conversas
- **Severity**: High
- **File**: Tabela `conversas`, todos os routers
- **Description**: Estado do sistema (`EVENTO_ID:`, `GRUPO_WA_ID:`, `FOLLOWUP_AGENDA_START:`, etc.) misturado com histórico real de conversa na mesma tabela.
- **Impact**: Queries de histórico precisam filtrar ruído; estado é difícil de auditar; sem schema enforcement.

### CORS wildcard em produção
- **Severity**: High
- **File**: `leadflow-backend/app/main.py`
- **Description**: `allow_origins=["*"]` expõe API para qualquer origem.
- **Impact**: Qualquer site pode fazer requests autenticadas se conseguir token.

### Credenciais em JSONB sem criptografia
- **Severity**: High
- **File**: Tabela `empresas`, coluna `config_apis`
- **Description**: API keys LLM, segredos OAuth e credenciais Zoom em texto plano em JSONB.
- **Impact**: Comprometimento do banco expõe todas as credenciais de todos os clientes.

### Service key para tudo (bypassa RLS)
- **Severity**: High
- **File**: `leadflow-backend/app/db/client.py`
- **Description**: Supabase service key usada em todos os acessos — RLS completamente ignorado.
- **Impact**: Bug de código pode acessar dados de outras empresas.

---

## Testing

### Cobertura zero nos fluxos críticos
- **Severity**: High
- **File**: `leadflow-backend/tests/`
- **Description**: Apenas 2 arquivos de teste (~76 linhas). Nenhum teste para: webhook ingestion, transições de estado do agente, scheduling de follow-ups, ou cenários multi-tenant.
- **Impact**: Regressões em qualquer mudança de agente são detectadas apenas em produção.

---

## Frontend

### Menos da metade das páginas tem error handling
- **Severity**: Medium
- **File**: `leadflow-frontend/src/pages/`
- **Description**: Apenas 8 de ~16 páginas com chamadas API têm `catch` com tratamento de erro.
- **Impact**: Falhas silenciosas — usuário vê tela em branco sem feedback.
