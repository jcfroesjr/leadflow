# Codebase Structure

**Analysis Date:** 2026-04-07

## Summary

The project is a monorepo with two independent git sub-repos: `leadflow-backend` (FastAPI Python) and `leadflow-frontend` (React/Vite). A root-level `venv/` and `app.py`/`requirements.txt` appear to be scratch/test files unrelated to the main applications.

---

## Directory Layout

```
Leadflow/                          # Monorepo root
├── leadflow-backend/              # FastAPI backend (Python)
│   ├── app/                       # Application source
│   │   ├── main.py                # FastAPI app factory + lifespan + router mounts
│   │   ├── auth.py                # JWT + empresa_id resolution dependency
│   │   ├── scheduler.py           # APScheduler singleton
│   │   ├── worker.py              # (background worker utilities)
│   │   ├── core/                  # (shared core utilities — currently sparse)
│   │   ├── db/
│   │   │   └── client.py          # get_supabase() factory
│   │   ├── routers/               # FastAPI routers (all business logic here)
│   │   │   ├── webhook.py         # Lead ingestion from external forms
│   │   │   ├── agente.py          # AI agent — Evolution webhook, LLM dispatch
│   │   │   ├── leads.py           # Lead management, manual scheduling
│   │   │   ├── agenda.py          # Google Calendar mirror (read only)
│   │   │   ├── agendamentos.py    # Google OAuth flow + config
│   │   │   ├── configuracoes.py   # Company settings CRUD
│   │   │   ├── followup.py        # Manual follow-up blast by score tier
│   │   │   ├── followup_agenda.py # APScheduler follow-up sequences
│   │   │   ├── warmup_grupo.py    # APScheduler group warmup sequences
│   │   │   ├── noshow_check.py    # APScheduler no-show detector
│   │   │   └── documentos.py      # RAG document upload + indexing
│   │   ├── services/              # External API thin wrappers
│   │   │   ├── evolution.py       # WhatsApp via Evolution API (send/create group/media)
│   │   │   ├── llm.py             # Gemini + OpenAI + Anthropic unified interface
│   │   │   ├── google_calendar.py # Calendar CRUD + freebusy slots
│   │   │   ├── zoom.py            # Zoom meeting creation (S2S OAuth)
│   │   │   ├── meta.py            # Meta Marketing API ad enrichment
│   │   │   ├── rag.py             # OpenAI embeddings + pgvector similarity search
│   │   │   └── pdf_generator.py   # Lead notification PDF generation
│   │   └── tasks/                 # Standalone task modules
│   │       ├── agendamento_tasks.py  # Scheduling-related tasks
│   │       └── followup_tasks.py    # Follow-up task helpers
│   ├── migrations/                # SQL migration files
│   │   └── conversas_migration.sql
│   ├── supabase/                  # Supabase config
│   │   └── conversas_migration.sql
│   ├── tests/                     # Test files
│   ├── Dockerfile                 # Container build
│   └── requirements.txt           # Python dependencies
│
├── leadflow-frontend/             # React/Vite frontend
│   ├── src/
│   │   ├── App.jsx                # Route definitions + AuthProvider wrapper
│   │   ├── main.jsx               # Vite entry point
│   │   ├── index.css              # Global styles (Tailwind)
│   │   ├── pages/                 # Page components (one per route)
│   │   │   ├── Login.jsx          # /login — email/password auth
│   │   │   ├── Cadastro.jsx       # /cadastro — sign-up + empresa creation
│   │   │   ├── Dashboard.jsx      # /dashboard — metrics overview
│   │   │   ├── Leads.jsx          # /leads — lead list, status, manual scheduling
│   │   │   ├── Agente.jsx         # /agente — AI agent config (LLM model, prompt, score)
│   │   │   ├── AgentEditor.jsx    # Agent script editor (extended view)
│   │   │   ├── Agendamentos.jsx   # /agendamentos — calendar view + OAuth config
│   │   │   ├── Followup.jsx       # /followup — manual follow-up blast by tier
│   │   │   ├── Webhooks.jsx       # /webhooks — webhook config + field mapping
│   │   │   ├── Configuracoes.jsx  # /configuracoes — API keys + company settings
│   │   │   ├── BaseRAG.jsx        # /rag — document upload + RAG index management
│   │   │   ├── Empresas.jsx       # /empresas — company management (admin)
│   │   │   └── Usuarios.jsx       # /usuarios — user/member management
│   │   ├── components/
│   │   │   ├── AppLayout.jsx      # Authenticated shell with Sidebar
│   │   │   ├── Sidebar.jsx        # Navigation sidebar
│   │   │   ├── UI.jsx             # Shared UI primitives (MetricCard, Badge, Modal, etc.)
│   │   │   ├── AuthContext.jsx    # (duplicate — canonical is src/contexts/AuthContext.jsx)
│   │   │   └── ProtectedRoute.jsx # Auth guard wrapper
│   │   ├── contexts/
│   │   │   └── AuthContext.jsx    # Auth state: user, tenant (empresa_id + papel)
│   │   └── services/
│   │       ├── api.js             # Axios instance → backend (JWT auto-injected)
│   │       └── supabase.js        # Supabase JS client (auth + direct queries)
│   └── (config files: vite.config, tailwind.config, etc.)
│
├── .planning/codebase/            # GSD planning documents
├── docs/                          # Project documentation
└── venv/                          # Root Python venv (scratch/local use)
```

---

## Key File Locations

**Entry Points:**
- `leadflow-backend/app/main.py` — FastAPI app, router mounting, lifespan (APScheduler start)
- `leadflow-frontend/src/main.jsx` — Vite/React entry
- `leadflow-frontend/src/App.jsx` — Route tree

**Auth:**
- `leadflow-backend/app/auth.py` — `get_current_empresa_id` dependency
- `leadflow-frontend/src/contexts/AuthContext.jsx` — Frontend auth provider + tenant resolution

**Database:**
- `leadflow-backend/app/db/client.py` — `get_supabase()` — called per-request everywhere

**Core Business Logic:**
- `leadflow-backend/app/routers/webhook.py` — lead ingestion pipeline
- `leadflow-backend/app/routers/agente.py` — AI conversation engine (3200+ lines)
- `leadflow-backend/app/routers/leads.py` — manual scheduling, Zoom dispatch
- `leadflow-backend/app/routers/followup_agenda.py` — time-based follow-up sequences

**Scheduler:**
- `leadflow-backend/app/scheduler.py` — APScheduler singleton import

**External API Wrappers:**
- `leadflow-backend/app/services/evolution.py` — WhatsApp messaging
- `leadflow-backend/app/services/llm.py` — Gemini/OpenAI/Anthropic unified
- `leadflow-backend/app/services/google_calendar.py` — Calendar + freebusy

---

## Router Map

All routes are relative to the backend base URL `https://leadflow-backend.bqvcbz.easypanel.host`.

### webhook.py (no prefix)
```
POST /webhook/{empresa_id}/{token}     → webhook.py:receber_webhook         → receive lead from external form, run LLM, send first WhatsApp message
POST /teste/notificacao                → webhook.py:testar_notificacao       → test team notification (text + PDF) for an existing lead
POST /teste/whatsapp                   → webhook.py:testar_whatsapp          → test raw WhatsApp message send
```

### agente.py (no prefix)
```
POST /agente/evolution/webhook         → agente.py:receber_mensagem_evolution → receive WhatsApp reply from Evolution API, run AI conversation
POST /agente/testar                    → agente.py:(test endpoint)            → test LLM response for a lead
POST /agente/debug-rag                 → agente.py:(debug endpoint)           → debug RAG retrieval
POST /agente/debug-calendar            → agente.py:(debug endpoint)           → debug Google Calendar availability
POST /agente/debug-zoom                → agente.py:(debug endpoint)           → debug Zoom meeting creation
```

### leads.py (prefix: /leads)
```
GET  /leads/                           → leads.py:listar_leads                → list leads for empresa (last 50, requires JWT)
POST /leads/{lead_id}/agendar-manual   → leads.py:agendar_manual              → manual schedule: Calendar event + Zoom + group + follow-up
POST /leads/{lead_id}/vincular-agendamento → leads.py:vincular_agendamento    → link existing Calendar event to lead
POST /leads/{lead_id}/cancelar-manual  → leads.py:cancelar_manual             → cancel scheduling, delete Calendar event
POST /leads/{lead_id}/iniciar-conversa → leads.py:iniciar_conversa            → resend initial AI message to lead
POST /leads/{lead_id}/enviar-zoom      → leads.py:enviar_zoom                 → send Zoom link to lead via WhatsApp
POST /leads/reprocessar-pendentes      → leads.py:reprocessar_pendentes       → reprocess leads stuck in "pendente" status
```

### configuracoes.py (prefix: /configuracoes)
```
GET  /configuracoes/                   → configuracoes.py:get_config          → get empresa config (APIs, agendamento, IA)
POST /configuracoes/api-keys           → configuracoes.py:salvar_api_keys     → save Evolution/LLM/Google/Zoom API keys
POST /configuracoes/empresa            → configuracoes.py:salvar_empresa      → save company name/CNPJ/timezone
```

### agenda.py (prefix: /agenda)
```
GET  /agenda/google/eventos            → agenda.py:listar_eventos             → list Google Calendar events (all calendars, date range)
GET  /agenda/google/calendarios        → agenda.py:listar_calendarios_disponiveis → list available Google calendars
```

### agendamentos.py (prefix: /agendamentos)
```
GET    /agendamentos/oauth/google/url       → agendamentos.py:oauth_google_url        → generate Google OAuth2 authorization URL
GET    /agendamentos/oauth/google/callback  → agendamentos.py:oauth_google_callback   → handle OAuth2 callback, save tokens
GET    /agendamentos/oauth/google/status    → agendamentos.py:oauth_google_status     → check OAuth connection status
DELETE /agendamentos/oauth/google/desconectar → agendamentos.py:oauth_google_desconectar → revoke OAuth tokens
POST   /agendamentos/config                 → agendamentos.py:(config endpoint)        → save agendamento config (slots, group, follow-ups)
```

### followup.py (prefix: /followup)
```
GET  /followup/stats                   → followup.py:followup_stats           → count pending leads by score
GET  /followup/tiers                   → followup.py:get_tiers                → get score tier configuration
POST /followup/tiers                   → followup.py:save_tiers               → save score tier configuration
POST /followup/disparar                → followup.py:disparar_followup        → blast follow-up messages to leads in score range
```

### followup_agenda.py (prefix: /followup-agenda)
```
POST /followup-agenda/check            → followup_agenda.py:(check endpoint)  → manually trigger follow-up check
```

### noshow_check.py (prefix: /noshow-check)
```
POST /noshow-check/check               → noshow_check.py:check_noshow_endpoint → manually trigger no-show check
```

### warmup_grupo.py (prefix: /warmup-grupo)
```
POST /warmup-grupo/forcar-notificacoes → warmup_grupo.py:forcar_notificacoes  → force schedule pre-meeting notifications for a group
```

### documentos.py (no prefix)
```
POST   /documentos/upload              → documentos.py:upload_documento       → upload and index PDF/DOCX/TXT for RAG
POST   /documentos/instrucao           → documentos.py:(instrucao endpoint)   → add text instruction directly to RAG index
DELETE /documentos/{doc_id}            → documentos.py:(delete endpoint)      → delete document and its chunks from RAG index
```

### main.py (no router prefix)
```
GET  /health                           → main.py:health                       → health check
GET  /                                 → main.py:root                         → API status
```

---

## Database Tables

Inferred from Supabase query patterns across all router files:

| Table | Key Columns (inferred) | Purpose |
|---|---|---|
| `empresas` | `id`, `nome`, `cnpj`, `plano`, `fuso`, `evolution_instancia`, `config_apis` (JSONB), `config_ia` (JSONB), `config_agendamento` (JSONB) | One row per tenant; all config stored as JSONB |
| `membros` | `usuario_id`, `empresa_id`, `papel` | User-to-empresa mapping; basis for auth tenant resolution |
| `leads` | `id`, `empresa_id`, `nome`, `telefone`, `email`, `score`, `status`, `origem`, `canal`, `criativo`, `ad_id`, `dados_raw` (JSONB), `agendamentos` (count), `criado_em` | Core lead records |
| `webhooks` | `id`, `empresa_id`, `token`, `ativo`, `plataforma`, `nome`, `mapeamento_campos` (JSONB) | Webhook definitions with field mapping config |
| `conversas` | `id`, `empresa_id`, `telefone`, `role` (`user`/`assistant`/`sistema`), `conteudo`, `criado_em` | Full conversation history; also used as event log via `role="sistema"` markers |
| `agendamentos` | `id`, `empresa_id`, `lead_id`, `inicio`, `status` (`confirmado`/`cancelado`/`noshow`), `lembretes_enviados`, `evento_id` (Google Calendar) | Appointment records |
| `calendario_tokens` | `empresa_id`, `plataforma`, `access_token`, `refresh_token`, `email`, `expiry` | Google OAuth2 tokens per empresa |
| `documentos` | `id`, `empresa_id`, `nome`, `status_indexacao`, `chunks_count` | RAG document metadata |
| `chunks_rag` | `id`, `documento_id`, `empresa_id`, `conteudo`, `embedding` (pgvector) | RAG text chunks with vector embeddings |
| `mensagens` | `id`, `empresa_id` | WhatsApp sent message log (referenced in Dashboard count query) |

**System markers in `conversas` (`role="sistema"`):**
- `FOLLOWUP_AGENDA_START:{timestamp}` — triggers follow-up sequence after first contact
- `FOLLOWUP_CANCEL_START:{timestamp}` — triggers follow-up sequence after cancellation
- `FOLLOWUP_NOSHOW_START:{timestamp}` — triggers follow-up sequence after no-show
- `FOLLOWUP_AGENDA_SENT:{i}` — deduplication guard for follow-up send
- `HUMANO_ASSUMIU:{timestamp}` — suppresses bot when human operator intervenes
- `GRUPO_WA_ID:{grupo_jid}` — stores WhatsApp group JID for warmup
- `GRUPO_AQUEC_START:{timestamp}` — triggers group warmup sequence
- `GRUPO_AQUEC_SENT:{i}` — deduplication guard for warmup send
- `GRUPO_NOTIF_START:{timestamp}` — triggers pre-meeting notification sequence

---

## Frontend Pages

| Route | Component | Purpose |
|---|---|---|
| `/login` | `Login.jsx` | Email/password login |
| `/cadastro` | `Cadastro.jsx` | Self-service signup + empresa creation |
| `/dashboard` | `Dashboard.jsx` | Metrics: total leads, qualified, messages sent, active webhooks |
| `/leads` | `Leads.jsx` | Lead table with status, manual scheduling modal, conversation history |
| `/agente` | `Agente.jsx` | AI agent config: LLM model, system prompt, score minimum, temperature |
| `/agendamentos` | `Agendamentos.jsx` | Calendar view, Google OAuth connect/disconnect, slot config |
| `/followup` | `Followup.jsx` | Score tier config, manual blast by tier |
| `/webhooks` | `Webhooks.jsx` | Webhook CRUD, field mapping editor |
| `/configuracoes` | `Configuracoes.jsx` | API keys (Evolution, Gemini, OpenAI, Anthropic, Zoom, Meta, Google), company name/CNPJ/timezone |
| `/rag` | `BaseRAG.jsx` | Upload documents (PDF/DOCX/TXT), add text instructions, manage indexed chunks |
| `/empresas` | `Empresas.jsx` | Admin: list/manage all empresas |
| `/usuarios` | `Usuarios.jsx` | Manage team members (invite, role, delete) |

**Authentication pattern:** All authenticated pages use `useAuth()` hook to get `tenant.empresa.id`. The `AppLayout` component wraps all authenticated routes. Unauthenticated routes (`/login`, `/cadastro`) are standalone.

---

## Where to Add New Code

**New backend route:**
1. Create or extend a file in `leadflow-backend/app/routers/`
2. Add `router = APIRouter(prefix="/your-prefix", tags=["your-tag"])`
3. Mount in `leadflow-backend/app/main.py` with `app.include_router(your_router.router)`
4. Protect with `Depends(get_current_empresa_id)` from `app.auth`

**New external API service:**
- Add file to `leadflow-backend/app/services/`
- Follow pattern: thin wrapper returning dicts, async functions, httpx client

**New scheduled job:**
- Add job registration inside `lifespan` in `app/main.py`, or
- Call `scheduler.add_job(func, "date", run_date=..., ...)` from within a router after a triggering action
- Always use `replace_existing=True` and a deterministic `id` to prevent duplicates on recovery

**New frontend page:**
1. Create component in `leadflow-frontend/src/pages/`
2. Add `<Route path="/your-path" element={<YourPage />} />` inside the `<AppLayout>` block in `src/App.jsx`
3. Add navigation entry in `src/components/Sidebar.jsx`
4. Use `useAuth()` for empresa_id, `api` (axios) for backend calls, `supabase` for direct DB reads

**New Supabase table:**
- Add SQL to `leadflow-backend/migrations/`
- Update relevant routers to scope all queries with `.eq("empresa_id", empresa_id)`

---

## Special Directories

**`.planning/codebase/`:**
- Purpose: GSD architecture and planning documents
- Generated: By GSD mapping commands
- Committed: Yes

**`leadflow-backend/migrations/`:**
- Purpose: Raw SQL migration files for Supabase
- Applied manually via `rodar_migrations.py` script
- Committed: Yes

**`venv/` (root):**
- Purpose: Local Python virtual environment for root-level scratch scripts (`app.py`)
- Committed: No (should be in .gitignore)
