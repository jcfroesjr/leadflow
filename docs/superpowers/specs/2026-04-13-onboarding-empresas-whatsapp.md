# Spec: Onboarding de Novas Empresas + Conexão WhatsApp

**Data:** 2026-04-13
**Status:** Aprovado pelo usuário

---

## Contexto

O Leadflow está sendo preparado para comercialização. Ao criar uma nova empresa, o processo atual exige configuração manual de todos os parâmetros (agente IA, follow-ups, aquecimento de grupo). O objetivo é replicar automaticamente a estrutura da empresa-modelo (Rejane Leal) para que o novo cliente só precise preencher suas API keys e conectar o WhatsApp.

---

## Escopo

Dois subsistemas independentes, entregues juntos:

1. **Onboarding automático** — ao criar empresa, copia `config_ia` + `config_agendamento` da empresa-modelo
2. **Conexão WhatsApp via UI** — wizard pós-criação para configurar API keys e conectar instância Evolution API com QR code

---

## Decisões de design

| Decisão | Escolha | Motivo |
|---|---|---|
| Template de configuração | Empresa-modelo dinâmica | Admin pode atualizar o template pela UI sem deploy |
| Identificação da empresa-modelo | Variável de ambiente `TEMPLATE_EMPRESA_ID` | Simples, sem alterar schema do banco |
| `config_apis` na empresa nova | Começa vazio `{}` | Evita expor credenciais da empresa-modelo |
| Fluxo de setup | Rota dedicada `/onboarding` com stepper | URL clara, retomável, padrão SaaS |
| WhatsApp connect | Disponível no onboarding E em Configurações | Onboarding guiado + reconexão posterior |

---

## Arquitetura

### Fluxo completo

```
1. Usuário clica "Nova empresa" em EmpresasPage
2. POST /configuracoes/empresas/criar → { ok, empresa_id }
3. Frontend redireciona → /onboarding?empresa_id={id}
4. OnboardingPage — Etapa 1: aplica template
   POST /configuracoes/empresas/{id}/aplicar-template
5. OnboardingPage — Etapa 2: API Keys
   POST /configuracoes/api-keys (endpoint existente)
6. OnboardingPage — Etapa 3: Conectar WhatsApp
   POST /whatsapp/instancia/criar → QR code
   GET /whatsapp/instancia/status (polling 3s)
7. Ao conectar → redireciona /dashboard
```

### Diagrama de componentes

```
OnboardingPage (/onboarding?empresa_id=...)
  ├── StepIndicator (etapas 1/2/3)
  ├── Etapa1Confirmacao
  │     └── chama POST /configuracoes/empresas/{id}/aplicar-template
  ├── Etapa2ApiKeys
  │     └── <ApiKeysForm> (extraído de Configurações)
  └── Etapa3WhatsApp
        └── <WhatsAppConnect mode="criar">

ConfiguracoesPage (existente, expandida)
  └── nova aba "WhatsApp"
        └── <WhatsAppConnect mode="gerenciar">
```

---

## Backend

### Variável de ambiente nova

```bash
# .env
TEMPLATE_EMPRESA_ID=<uuid-da-empresa-modelo>
```

### Endpoint: aplicar template

```
POST /configuracoes/empresas/{empresa_id}/aplicar-template
Auth: Bearer token (membro da empresa)
```

**Lógica:**
1. Valida JWT e pertencimento do usuário à empresa
2. Lê `TEMPLATE_EMPRESA_ID` do env
3. Busca `config_ia` + `config_agendamento` da empresa-modelo
4. Faz UPDATE na empresa nova com esses valores
5. `config_apis` **não é copiado** — permanece `{}`
6. Idempotente — pode ser chamado múltiplas vezes

**Resposta:** `{ ok: true, copiados: ["config_ia", "config_agendamento"] }`

### Novo router: `/whatsapp`

**`POST /whatsapp/instancia/criar`**

Body: `{ instancia_nome: string, empresa_id: string }`

1. Valida JWT e pertencimento
2. Chama `POST {EVOLUTION_API_URL}/instance/create` com `{ instanceName, qrcode: true, token: EVOLUTION_API_KEY }`
3. Salva `evolution_instancia = instancia_nome` na empresa
4. Retorna `{ qrcode_base64: string, instancia_nome: string }`

**`GET /whatsapp/instancia/status`**

Query: `?instancia_nome=...&empresa_id=...`

1. Valida JWT e pertencimento
2. Chama `GET {EVOLUTION_API_URL}/instance/connectionState/{instanceName}`
3. Retorna `{ estado: "qr" | "connecting" | "open" | "close" }`

**`DELETE /whatsapp/instancia/desconectar`**

Body: `{ instancia_nome: string, empresa_id: string }`

1. Valida JWT e pertencimento
2. Chama `DELETE {EVOLUTION_API_URL}/instance/delete/{instanceName}`
3. Limpa `evolution_instancia = null` na empresa
4. Retorna `{ ok: true }`

### Variáveis de ambiente utilizadas (já existem)

- `EVOLUTION_API_URL` — URL base da Evolution API
- `EVOLUTION_API_KEY` — global API key

---

## Frontend

### Nova rota

```typescript
// router.tsx
{ path: 'onboarding', element: <OnboardingPage /> }
// rota pública — não requer empresa ativa no contexto
```

### `OnboardingPage.tsx`

- Lê `?empresa_id` da query string
- Stepper linear (forward-only)
- Retomável: ao re-entrar na URL, etapa 1 tenta aplicar template (idempotente) e avança

**Etapa 1 — Configuração inicial**
- Ao montar: chama `POST /configuracoes/empresas/{id}/aplicar-template`
- Exibe checklist: "✓ Agente IA configurado", "✓ Follow-ups configurados", "✓ Aquecimento de grupo configurado"
- Botão "Próximo →"

**Etapa 2 — API Keys**
- Renderiza `<ApiKeysForm empresaId={empresaId} />`
- Componente extraído do form inline atual em ConfiguracoesPage
- Botão "Salvar e Próximo →"

**Etapa 3 — Conectar WhatsApp**
- Renderiza `<WhatsAppConnect mode="criar" empresaId={empresaId} />`
- Link "Pular por agora" → `/dashboard`

### Componente `<WhatsAppConnect>`

Props: `mode: "criar" | "gerenciar"`, `empresaId: string`

**Modo "criar":**
- Input: nome da instância (pré-preenchido com slug do nome da empresa)
- Botão "Criar e conectar"
- Ao clicar: `POST /whatsapp/instancia/criar`
- Exibe QR code como `<img src={`data:image/png;base64,${qrcode}`} />`
- Polling a cada 3s em `GET /whatsapp/instancia/status`
- Ao `estado === "open"`: badge verde "Conectado ✓" + botão "Ir para o painel →"

**Modo "gerenciar":**
- Exibe instância atual e estado de conexão
- Botão "Reconectar" (recria QR code)
- Botão "Desconectar" (chama DELETE)

### Alterações em arquivos existentes

**`EmpresasPage.tsx`** — troca destino do redirect após criação:
```typescript
// antes
window.location.href = '/workspace'
// depois
window.location.href = `/onboarding?empresa_id=${res.empresa_id}`
```

**`ConfiguracoesPage.tsx`** — adiciona aba "WhatsApp":
- Nova aba com `<WhatsAppConnect mode="gerenciar" empresaId={empresaAtiva.id} />`
- Extrai `<ApiKeysForm>` do form inline atual

---

## Arquivos novos

| Arquivo | Descrição |
|---|---|
| `leadflow-backend/app/routers/whatsapp.py` | Router com 3 endpoints Evolution API |
| `leadflow-frontend/src/modules/onboarding/OnboardingPage.tsx` | Stepper de 3 etapas |
| `leadflow-frontend/src/components/WhatsAppConnect.tsx` | Componente compartilhado QR code |
| `leadflow-frontend/src/components/ApiKeysForm.tsx` | Extraído de ConfiguracoesPage |

## Arquivos modificados

| Arquivo | Mudança |
|---|---|
| `leadflow-backend/app/routers/configuracoes.py` | Novo endpoint `POST /empresas/{id}/aplicar-template` |
| `leadflow-backend/app/main.py` | Registrar router whatsapp |
| `leadflow-frontend/src/app/router.tsx` | Rota `/onboarding` |
| `leadflow-frontend/src/modules/empresas/EmpresasPage.tsx` | Redirect para `/onboarding` |
| `leadflow-frontend/src/modules/configuracoes/ConfiguracoesPage.tsx` | Aba WhatsApp + extrair ApiKeysForm |
| `leadflow-backend/.env` | Nova var `TEMPLATE_EMPRESA_ID` |

---

## Fora do escopo

- Cobrança/planos de novas empresas (sem stripe ou similar)
- Convite de usuários por email
- Múltiplas empresas-modelo
- Migração de dados de empresa existente
