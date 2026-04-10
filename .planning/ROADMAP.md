# Roadmap: Leadflow Frontend v2

**Created:** 2026-04-09
**Goal:** Frontend v2 totalmente funcional — auth real, dados reais, ações conectadas ao backend, build sem erros.

---

## Phase 1: Auth & Foundation
**Goal:** Usuário consegue entrar no sistema, sessão persiste, rotas protegidas funcionam, build sem erros TypeScript.

**Requirements:** AUTH-01 a AUTH-06, BILD-01 a BILD-04

**Deliverables:**
- LoginPage funcional com Supabase Auth
- AuthProvider + ProtectedRoute operacionais no main.tsx
- empresa_id resolvido e disponível via useAuth()
- `npm run build` sem erros
- Redeploy no Easypanel com build limpo

**Status:** 🔄 Em progresso (código criado, build não verificado)

---

## Phase 2: Dashboard Real
**Goal:** Dashboard exibe KPIs e gráfico com dados reais do Supabase.

**Requirements:** DASH-01 a DASH-07

**Deliverables:**
- fetchDashboardMetrics() retornando dados reais
- fetchChartData() com dados dos últimos 7 dias
- fetchRecentLeads() com 5 últimos leads
- KpiCards com loading skeleton
- Gráfico AreaChart com dados reais
- Tabela de leads recentes funcional

**Plans:** 1 plan

Plans:
- [ ] 02-01-PLAN.md — Corrigir dashboard.ts (data_hora, taxa de conversão) e tipos DashboardPage.tsx

**Status:** 📋 Planejado

---

## Phase 3: Leads & Actions
**Goal:** Tabela de leads com dados reais + todos os botões de ação chamando o backend.

**Requirements:** LEAD-01 a LEAD-11

**Deliverables:**
- fetchLeads() com dados reais filtrados por empresa_id
- Busca e filtro de status funcionais
- Modal agendar-manual chamando POST /leads/{id}/agendar-manual
- Modal vincular chamando POST /leads/{id}/vincular-agendamento
- Cancelar com confirmação chamando POST /leads/{id}/cancelar-manual
- Enviar Zoom chamando POST /leads/{id}/enviar-zoom
- Iniciar conversa chamando POST /leads/{id}/iniciar-conversa
- invalidateQueries após cada ação para refresh da tabela
- Exportar CSV funcional

**Status:** 🔄 Em progresso (services criados, integração com Auth/token pendente)

---

## Phase 4: Conversas
**Goal:** Inbox com threads reais do WhatsApp e histórico de mensagens com polling automático.

**Requirements:** CONV-01 a CONV-08

**Deliverables:**
- fetchThreads() agrupando conversas por telefone e enriquecendo com nome do lead
- fetchMensagens() carregando histórico da thread selecionada
- Polling a cada 10s na thread ativa (refetchInterval)
- Bubbles diferenciadas por role
- Mensagens sistema como chips

**Status:** 🔄 Em progresso (services criados, testagem pendente)

---

## Phase 5: Agente IA
**Goal:** Página de configuração do agente carrega e salva config_ia real.

**Requirements:** AGNT-01 a AGNT-07

**Deliverables:**
- fetchAgentConfig() carregando do Supabase
- saveAgentConfig() fazendo merge e salvando
- useEffect populando form quando config carrega
- Feedback de sucesso/erro após salvar
- Máquina de estados visual

**Status:** 🔄 Em progresso (services criados, integração com Auth pendente)

---

## Phase 6: Pipeline & Settings
**Goal:** Kanban com leads reais por status + Settings com info da empresa e status de integrações.

**Requirements:** PIPE-01 a PIPE-04, SETT-01 a SETT-03

**Deliverables:**
- Pipeline com leads agrupados por status do Supabase
- Settings exibindo nome/fuso da empresa
- Status de integrações (Evolution, Google Calendar) baseado em config_apis

**Status:** ⏳ Pendente

---

## Fase Atual

**Phase 1: Auth & Foundation** é a porta de entrada. Sem auth funcionando, nenhuma das outras páginas exibe dados reais.

### Próximo passo imediato:
1. Verificar se o build TypeScript passa (`npm run build`)
2. Corrigir erros de tipo se houver
3. Confirmar que LoginPage + AuthProvider funcionam no ambiente deployado
4. Redeploy no Easypanel

---
*Roadmap criado: 2026-04-09*
