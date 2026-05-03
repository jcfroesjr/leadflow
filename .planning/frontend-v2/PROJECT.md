# Leadflow Frontend v2

## What This Is

Interface SaaS moderna do Leadflow, construída com React 19 + TypeScript + Tailwind CSS + shadcn/ui. Substitui o frontend v1 (JSX puro) com design profissional, dark mode, componentes reutilizáveis e integração completa com Supabase Auth, Supabase Direct e backend FastAPI. Destinada a operadores comerciais que gerenciam leads, conversas WhatsApp e agendamentos.

## Core Value

O operador entra, vê seus leads e conversas em tempo real, toma ações (agendar, cancelar, iniciar conversa) sem precisar abrir outra ferramenta.

## Requirements

### Validated

- ✓ Estrutura de páginas criada (Dashboard, Leads, Conversas, Pipeline, Agente IA, Configurações) — fase inicial
- ✓ Design system com dark/light mode, CSS custom properties HSL, DM Sans — fase inicial
- ✓ Componentes UI base (button, card, badge, avatar, skeleton, input) — fase inicial
- ✓ Sidebar + Topbar + AppLayout com rotas — fase inicial
- ✓ Dockerfile multi-stage + nginx para deploy no Easypanel — fase inicial
- ✓ Instalação de @supabase/supabase-js + TanStack Query configurado — fase inicial

### Active

- [ ] Login funcional com Supabase Auth (email + senha) — ProtectedRoute operacional
- [ ] Dashboard com KPIs reais (total leads, agendados, conversas ativas, taxa de conversão)
- [ ] Dashboard com gráfico 7 dias (leads + agendamentos) via Supabase direto
- [ ] Leads — tabela com dados reais, busca, filtro por status
- [ ] Leads — ações funcionais: agendar-manual, vincular, cancelar, enviar-zoom, iniciar-conversa (POST backend)
- [ ] Conversas — inbox agrupado por telefone com histórico real do Supabase
- [ ] Conversas — polling a cada 10-15s para novas mensagens
- [ ] Agente IA — carregar config_ia do banco e salvar alterações
- [ ] Pipeline — kanban agrupado por fase_conversa/status real
- [ ] Configurações — exibir empresa e status de integrações reais
- [ ] Build sem erros TypeScript para deploy no Easypanel

### Out of Scope

- Editor de webhooks — existe no frontend v1, não replicar no v2 ainda
- Cadastro de nova empresa — fluxo de signup não é necessário neste ciclo
- Push notifications / websockets — polling é suficiente para v1
- Relatórios avançados / exportação além de CSV — deferred
- Mobile app — web-first

## Context

**Frontend v1** (leadflow-frontend) existe em produção em JSX puro com Tailwind básico. O v2 é um projeto paralelo em desenvolvimento, já deployado em https://leadflow-leadflow-frontend-v2.bqvcbz.easypanel.host.

**Estado atual do v2:** Todas as páginas existem com mock data. Services de API foram criados (`src/services/api/`), contexto de Auth (`src/contexts/AuthContext.tsx`), ProtectedRoute, LoginPage. O código está no GitHub mas o Easypanel ainda pode estar servindo versão anterior ao último deploy.

**Backend:** FastAPI em https://leadflow-backend.bqvcbz.easypanel.host — requer Bearer JWT (Supabase access token) nos headers. Auth: Supabase email+senha → JWT → `membros` table → `empresa_id`.

**Supabase:** `pllpwjuagqykxwyfpqrz.supabase.co` — tabelas: leads, conversas, agendamentos, empresas, membros, webhooks, calendario_tokens.

**Problemas conhecidos (CONCERNS.md):** Sem RLS no Supabase (isolamento só por app), CORS aberto (`*`), sem retry/circuit breaker, build TypeScript pode ter erros de tipo.

## Constraints

- **Stack**: React 19 + TypeScript + Tailwind v3 + shadcn/ui pattern — não mudar
- **Deploy**: Easypanel via Dockerfile — build deve passar sem erros
- **Auth**: Supabase Auth apenas — sem OAuth social neste ciclo
- **Backend**: Não alterar routers do backend para acomodar frontend — adaptar o frontend
- **Dados**: Supabase direto para reads de dashboard; backend para actions (agendar, cancelar, etc.)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| TanStack Query para fetching | Cache, refetch automático, loading/error states | — Pending |
| Supabase direto para reads | Evita round-trip desnecessário pelo backend | — Pending |
| Mock data substituído por services reais | Código de serviços já criado na sessão anterior | — Pending |
| ProtectedRoute + AuthProvider no main.tsx | Padrão React para auth global | — Pending |
| Polling (refetchInterval) ao invés de websockets | Simples, suficiente para v1 | — Pending |

---
*Last updated: 2026-04-09 — inicialização do projeto frontend-v2*
