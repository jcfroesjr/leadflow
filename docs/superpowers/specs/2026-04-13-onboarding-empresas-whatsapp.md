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
2. POST /configuracoes/empresas/criar
   → insere empresa + insere membro como admin (ambos na mesma chamada)
   → retorna { ok: true, empresa_id: string, nome: string }
3. Frontend redireciona → /onboarding?empresa_id={id}
4. OnboardingPage — Etapa 1: aplica template
   POST /configuracoes/empresas/{id}/aplicar-template
   (usuário já é membro — inserido no passo 2)
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

### Endpoint existente: criar empresa

```
POST /configuracoes/empresas/criar
```

Já implementado. Insere empresa + membro (papel=admin) na mesma chamada usando service key (ignora RLS). Retorna `{ ok: true, empresa_id: string, nome: string }`. Nenhuma alteração necessária neste endpoint.

### Endpoint novo: aplicar template

```
POST /configuracoes/empresas/{empresa_id}/aplicar-template
Auth: Bearer token (JWT válido + usuário é membro da empresa)
```

**Pré-condição:** o usuário já é membro da empresa (inserido em `/empresas/criar` no passo 2). A verificação de pertencimento via tabela `membros` funciona normalmente.

**Lógica:**
1. Valida JWT e pertencimento do usuário à empresa
2. Lê `TEMPLATE_EMPRESA_ID` do env — se não definido ou empresa não encontrada, retorna `{ ok: false, erro: "Template não configurado" }` com HTTP 503; o onboarding pode continuar (etapa 1 exibe aviso e permite avançar)
3. Busca `config_ia` + `config_agendamento` da empresa-modelo
4. Faz UPDATE na empresa nova com esses valores
5. `config_apis` **não é copiado** — permanece `{}`
6. Idempotente — pode ser chamado múltiplas vezes sem efeito colateral

**Resposta sucesso:** `{ ok: true, copiados: ["config_ia", "config_agendamento"] }`
**Resposta erro template:** `{ ok: false, erro: "Template não configurado" }` (HTTP 503)

### Novo router: `/whatsapp`

**`POST /whatsapp/instancia/criar`**

Body: `{ instancia_nome: string, empresa_id: string }`

Validação de `instancia_nome` (backend e frontend): apenas letras minúsculas, números e hífens (`^[a-z0-9-]{3,60}$`).

1. Valida JWT e pertencimento (403 se não autorizado)
2. Verifica se já existe instância com esse nome via `GET /instance/connectionState/{instanceName}`:
   - Se `estado === "open"`: retorna `{ estado: "open", instancia_nome }` sem QR — frontend trata como já conectado
   - Se existir mas não conectada: retorna QR da instância existente (idempotente)
3. Chama `POST {EVOLUTION_API_URL}/instance/create` com `{ instanceName, qrcode: true, token: EVOLUTION_API_KEY }`
4. Salva `evolution_instancia = instancia_nome` na empresa
5. Retorna `{ qrcode_base64: string, instancia_nome: string }` ou `{ estado: "open", instancia_nome: string }`

**`GET /whatsapp/instancia/status`**

Query: `?instancia_nome=...&empresa_id=...`

1. Valida JWT e pertencimento
2. Chama `GET {EVOLUTION_API_URL}/instance/connectionState/{instanceName}`
3. Retorna `{ estado: "qr" | "connecting" | "open" | "close", instancia_nome: string }`
4. Se instância não existir na Evolution API: retorna `{ estado: "close" }`

**`DELETE /whatsapp/instancia/{instancia_nome}`**

Path: `instancia_nome` (validado: `^[a-z0-9-]{3,60}$`); Query: `?empresa_id=...`

1. Valida JWT e pertencimento (403 se não autorizado)
2. Chama `DELETE {EVOLUTION_API_URL}/instance/delete/{instanceName}`; se Evolution retornar 404 (instância não existe), ignora o erro
3. Limpa `evolution_instancia = null` na empresa independentemente do resultado da Evolution API
4. Retorna `{ ok: true }`

**`GET /whatsapp/instancia`**

Query: `?empresa_id=...`

1. Valida JWT e pertencimento (403 se não autorizado)
2. Lê `evolution_instancia` da tabela `empresas`
3. Se instância definida: chama `GET /instance/connectionState/{instanceName}` para obter estado atual
   - Se Evolution retornar 404: retorna `{ instancia_nome: null, estado: null }` (instância foi deletada externamente — não limpa o DB, deixa para o usuário reconectar)
4. Retorna `{ instancia_nome: string | null, estado: "qr" | "open" | "close" | "connecting" | null }`

Usado pelo componente `<WhatsAppConnect mode="gerenciar">` para exibir o estado atual. O estado `"qr"` indica que a instância existe mas aguarda scan — o componente exibe o botão "Reconectar" nesse caso.

### Variáveis de ambiente utilizadas (já existem)

- `EVOLUTION_API_URL` — URL base da Evolution API
- `EVOLUTION_API_KEY` — global API key

---

## Frontend

### Nova rota

```typescript
// router.tsx — dentro do layout autenticado (requer JWT)
{ path: 'onboarding', element: <OnboardingPage /> }
```

A rota requer autenticação (JWT válido) como todas as demais rotas do app. Não requer empresa ativa no contexto do AuthContext — lê `empresa_id` diretamente da query string.

**Erro de empresa_id inválido:** se `empresa_id` estiver ausente ou o usuário não for membro da empresa (retorno 403 do endpoint `aplicar-template`), a página redireciona para `/dashboard` com toast de erro.

### `OnboardingPage.tsx`

- Lê `?empresa_id` da query string; se ausente, redireciona imediatamente para `/dashboard`
- Stepper linear (forward-only)
- **Retomável:** ao re-entrar na URL, etapa 1 chama `aplicar-template` normalmente (idempotente). O resultado é exibido (checklist ou aviso) e o usuário avança clicando "Próximo →" — não há avanço automático silencioso

**Etapa 1 — Configuração inicial**
- Ao montar: chama `POST /configuracoes/empresas/{id}/aplicar-template`
- Sucesso: exibe checklist "✓ Agente IA configurado", "✓ Follow-ups configurados", "✓ Aquecimento de grupo configurado" + botão "Próximo →"
- Erro (template não configurado, HTTP 503): exibe aviso amarelo "Template não disponível — você pode configurar manualmente depois" + botão "Próximo →" (fluxo não bloqueado)
- Erro (não autorizado, HTTP 403): redireciona para `/dashboard`

**Etapa 2 — API Keys**
- Renderiza `<ApiKeysForm empresaId={empresaId} />`
- Componente extraído do form inline atual em ConfiguracoesPage
- Botão "Salvar e Próximo →"

**Etapa 3 — Conectar WhatsApp**
- Renderiza `<WhatsAppConnect mode="criar" empresaId={empresaId} />`
- Link "Pular por agora" → `/dashboard` (empresa funciona sem WhatsApp conectado — agente IA não envia mensagens até instância configurada, ver nota abaixo)

### Componente `<WhatsAppConnect>`

Props: `mode: "criar" | "gerenciar"`, `empresaId: string`

**Modo "criar":**
- Input: nome da instância (pré-preenchido com slug do nome da empresa, ex: `"Rejane Leal"` → `"rejane-leal"`); aceita apenas `^[a-z0-9-]{3,60}$`, validado no cliente antes de enviar
- Botão "Criar e conectar"
- Ao clicar: `POST /whatsapp/instancia/criar`
- Exibe QR code como `<img src={`data:image/png;base64,${qrcode}`} />`
- Polling a cada 3s em `GET /whatsapp/instancia/status` (abortado via `AbortController` ao desmontar componente)
- QR code expira em ~60s: o polling continua durante esse período. Após 60s sem `estado === "open"`, exibe botão "Atualizar QR code" que chama `POST /whatsapp/instancia/criar` novamente (idempotente — retorna novo QR da mesma instância). O polling não é interrompido enquanto aguarda o clique
- Ao `estado === "open"`: para o polling, exibe badge verde "Conectado ✓" + botão "Ir para o painel →"
- Ao `estado === "close"` durante polling: exibe aviso "Conexão perdida" + botão para reiniciar

**Modo "gerenciar":**
- Ao montar: chama `GET /whatsapp/instancia?empresa_id=...` para obter instância atual e estado
- Exibe nome da instância e badge de estado (Conectado / Desconectado / Aguardando scan)
- **Botão "Reconectar":** reutiliza o `instancia_nome` já salvo na empresa (não exibe input). Se `estado === "open"`, exibe confirmação "Isso irá desconectar a instância atual. Continuar?" e chama `DELETE` antes de prosseguir; caso contrário, chama `POST /whatsapp/instancia/criar` diretamente (idempotente) e exibe o QR
- **Botão "Desconectar":** chama `DELETE /whatsapp/instancia/{nome}`, disponível apenas quando `estado === "open"`

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
- Extrai `<ApiKeysForm>` do form inline atual (sem mudar comportamento)

### "Pular por agora" — comportamento downstream

Se o usuário pular a etapa 3, `evolution_instancia` fica null na empresa. O agente IA (verificado em `app/routers/agente.py`) lê `evolution_instancia` da config antes de enviar mensagens via Evolution API — sem instância configurada, nenhuma mensagem é despachada. A tela de Configurações → aba WhatsApp exibe o componente de conexão, servindo como ponto de retorno para completar a configuração.

---

## Arquivos novos

| Arquivo | Descrição |
|---|---|
| `leadflow-backend/app/routers/whatsapp.py` | Router com 4 endpoints Evolution API |
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
| `leadflow-backend/.env.example` | Documentar nova var `TEMPLATE_EMPRESA_ID` (`.env` real não é commitado) |

---

## Fora do escopo

- Cobrança/planos de novas empresas (sem stripe ou similar)
- Convite de usuários por email
- Múltiplas empresas-modelo
- Migração de dados de empresa existente
- Banner/aviso persistente no app quando WhatsApp não está conectado
