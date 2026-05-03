# Requirements: Leadflow Frontend v2

**Defined:** 2026-04-09
**Core Value:** Operador entra, vê leads e conversas em tempo real e toma ações sem abrir outra ferramenta.

## v1 Requirements

### Autenticação

- [ ] **AUTH-01**: Usuário acessa tela de login com email e senha
- [ ] **AUTH-02**: Login autentica via Supabase Auth e redireciona para Dashboard
- [ ] **AUTH-03**: Sessão persiste após refresh (Supabase session storage)
- [ ] **AUTH-04**: Rotas protegidas redirecionam para /login se não autenticado
- [ ] **AUTH-05**: Logout limpa sessão e redireciona para /login
- [ ] **AUTH-06**: empresa_id resolvido via tabela `membros` após login

### Dashboard

- [ ] **DASH-01**: KPI "Total de leads" exibe contagem real do Supabase
- [ ] **DASH-02**: KPI "Agendamentos" exibe leads com status=agendado
- [ ] **DASH-03**: KPI "Conversas ativas" exibe leads em_contato + qualificado
- [ ] **DASH-04**: KPI "Taxa de conversão" calculada como qualificados/total
- [ ] **DASH-05**: Gráfico de área exibe leads e agendamentos dos últimos 7 dias
- [ ] **DASH-06**: Tabela de últimos 5 leads com nome, telefone, status e tempo relativo
- [ ] **DASH-07**: Dados recarregam automaticamente (staleTime 30s)

### Leads

- [ ] **LEAD-01**: Tabela exibe todos os leads da empresa ordenados por data
- [ ] **LEAD-02**: Busca filtra por nome ou telefone em tempo real
- [ ] **LEAD-03**: Filtro por status (todos, novo, em_contato, qualificado, agendado, convertido, perdido)
- [ ] **LEAD-04**: Botão "Agendar manualmente" abre modal com data+hora e chama POST /leads/{id}/agendar-manual
- [ ] **LEAD-05**: Modal de agendamento exibe zoom_link em estado de sucesso
- [ ] **LEAD-06**: Botão "Enviar Zoom" chama POST /leads/{id}/enviar-zoom
- [ ] **LEAD-07**: Botão "Cancelar agendamento" chama POST /leads/{id}/cancelar-manual (com confirmação)
- [ ] **LEAD-08**: Botão "Vincular agendamento" abre modal e chama POST /leads/{id}/vincular-agendamento
- [ ] **LEAD-09**: Botão "Iniciar conversa Bia" chama POST /leads/{id}/iniciar-conversa (com confirmação)
- [ ] **LEAD-10**: Exportar CSV baixa todos os leads da empresa
- [ ] **LEAD-11**: Ações desabilitadas durante loading (feedback visual)

### Conversas

- [ ] **CONV-01**: Lista de threads agrupada por telefone, ordenada por última atividade
- [ ] **CONV-02**: Thread exibe nome do lead (buscado da tabela leads), última mensagem e tempo relativo
- [ ] **CONV-03**: Busca filtra threads por nome ou telefone
- [ ] **CONV-04**: Seleção de thread carrega histórico completo de mensagens
- [ ] **CONV-05**: Mensagens exibidas com bubble diferenciado por role (user/assistant/system)
- [ ] **CONV-06**: Mensagens do tipo sistema exibidas como chips centralizados
- [ ] **CONV-07**: Polling automático a cada 10-15s para novas mensagens na thread ativa
- [ ] **CONV-08**: Painel lateral direito exibe telefone do lead selecionado

### Agente IA

- [ ] **AGNT-01**: Página carrega config_ia atual do Supabase (modelo, nome_agente, nome_responsavel, templates)
- [ ] **AGNT-02**: Seleção de modelo atualiza estado local
- [ ] **AGNT-03**: Campos de persona (nome_agente, nome_responsavel) editáveis
- [ ] **AGNT-04**: Textareas Q1, Q2, empatia editáveis com variáveis documentadas
- [ ] **AGNT-05**: Botão Salvar faz PATCH em empresas.config_ia via Supabase
- [ ] **AGNT-06**: Feedback visual de sucesso/erro após salvar
- [ ] **AGNT-07**: Máquina de estados exibe as 6 fases com status visual

### Pipeline

- [ ] **PIPE-01**: Kanban com 5 colunas: novo, em_contato, qualificado, agendado, convertido
- [ ] **PIPE-02**: Cards exibem nome do lead, score e tempo relativo
- [ ] **PIPE-03**: Contagem de leads por coluna exibida no header
- [ ] **PIPE-04**: Dados carregados do Supabase filtrando por empresa_id

### Configurações

- [ ] **SETT-01**: Exibe nome da empresa e fuso horário da tabela empresas
- [ ] **SETT-02**: Status de integração Evolution API (conectado/não configurado)
- [ ] **SETT-03**: Status de integração Google Calendar (conectado/não configurado)

### Build e Deploy

- [ ] **BILD-01**: `npm run build` completa sem erros TypeScript
- [ ] **BILD-02**: Dockerfile multi-stage produz imagem funcional
- [ ] **BILD-03**: nginx serve SPA com fallback para index.html
- [ ] **BILD-04**: Variáveis Supabase hardcoded (sem necessidade de env vars no container)

## v2 Requirements

### Notificações

- **NOTF-01**: Badge de notificações no topbar com contagem real
- **NOTF-02**: Lista de alertas (leads sem resposta, agendamentos do dia)

### Configurações Avançadas

- **SETT-04**: Formulário para salvar nome/fuso da empresa
- **SETT-05**: Gerenciamento de API keys (Evolution, OpenAI, Zoom, Google)
- **SETT-06**: OAuth Google Calendar inline

### Campanhas

- **CAMP-01**: Listagem de campanhas de follow-up
- **CAMP-02**: Criação de campanha com sequência de mensagens

## Out of Scope

| Feature | Reason |
|---------|--------|
| Cadastro de nova empresa | Fluxo de onboarding via backend diretamente |
| Websockets / real-time | Polling suficiente para v1 |
| Editor de webhooks | Complexo, existe no v1 |
| Relatórios exportação além de CSV | Deferred v2 |
| Mobile app | Web-first |
| Multi-idioma | PT-BR only |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01 a AUTH-06 | Phase 1 — Auth & Foundation | Pending |
| BILD-01 a BILD-04 | Phase 1 — Auth & Foundation | Pending |
| DASH-01 a DASH-07 | Phase 2 — Dashboard Real | Pending |
| LEAD-01 a LEAD-11 | Phase 3 — Leads & Actions | Pending |
| CONV-01 a CONV-08 | Phase 4 — Conversas | Pending |
| AGNT-01 a AGNT-07 | Phase 5 — Agente IA | Pending |
| PIPE-01 a PIPE-04 | Phase 6 — Pipeline & Settings | Pending |
| SETT-01 a SETT-03 | Phase 6 — Pipeline & Settings | Pending |

**Coverage:**
- v1 requirements: 43 total
- Mapped to phases: 43
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-09*
*Last updated: 2026-04-09 após inicialização*
