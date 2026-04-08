# Architecture

**Analysis Date:** 2026-04-07

## Summary

LeadFlow is a multi-tenant SaaS platform for automated lead qualification and scheduling via WhatsApp. The system receives leads from external form tools (Responde APP and others) via webhooks, scores them, initiates AI-driven WhatsApp conversations using configurable LLMs (Gemini, OpenAI, Anthropic), manages scheduling via Google Calendar, creates Zoom meetings, and orchestrates automated follow-up sequences. The backend is a FastAPI (Python) monolith deployed on Easypanel; the frontend is a React/Vite SPA. Supabase serves as both the relational database (PostgreSQL + pgvector) and the auth provider. All inter-service state is persisted in Supabase.

---

## High-Level Component Map

```
External form tools (Responde APP, etc.)
         │ POST /webhook/{empresa_id}/{token}
         ▼
[FastAPI Backend — leadflow-backend]
  ├── webhook.py        ← receives lead, calls LLM, sends first WhatsApp message
  ├── agente.py         ← receives WhatsApp replies from Evolution API, runs conversation
  ├── leads.py          ← manual scheduling, cancellation, Zoom link dispatch
  ├── followup_agenda.py← APScheduler date-trigger follow-up sequences
  ├── warmup_grupo.py   ← APScheduler group warmup messages
  ├── noshow_check.py   ← APScheduler interval job (every 30 min)
  └── (other routers)
         │
         ├── Supabase (PostgreSQL + pgvector + Auth)
         ├── Evolution API  ← WhatsApp messaging
         ├── Google Calendar API  ← scheduling
         ├── Zoom API  ← meeting links
         ├── Meta Marketing API  ← ad enrichment
         └── LLM APIs (Gemini / OpenAI / Anthropic)

[React Frontend — leadflow-frontend]
  └── axios → Backend REST API
  └── supabase-js → Supabase direct (auth + read queries for dashboard)
```

---

## Layers

**Routers (`leadflow-backend/app/routers/`):**
- Purpose: HTTP request handling, business orchestration
- Contains: FastAPI `APIRouter` instances, all business logic (no separate service layer for business rules)
- Depends on: `app/db/client.py`, `app/services/`, `app/auth.py`, `app/scheduler.py`
- Notable: Business logic is heavy in routers (not separated into a domain layer)

**Services (`leadflow-backend/app/services/`):**
- Purpose: Thin wrappers for external APIs
- Files: `evolution.py` (WhatsApp), `llm.py` (Gemini/OpenAI/Anthropic), `google_calendar.py` (Calendar), `zoom.py` (Zoom meetings), `meta.py` (Meta Ads), `rag.py` (embeddings + pgvector search), `pdf_generator.py` (PDF generation)
- Contains: HTTP clients, auth negotiation, no business logic

**DB Client (`leadflow-backend/app/db/client.py`):**
- Purpose: Single Supabase client factory — `get_supabase()` called inline on every request (no connection pooling abstraction)
- All SQL is written as Supabase PostgREST calls (`.table().select().eq()...execute()`)

**Auth (`leadflow-backend/app/auth.py`):**
- Purpose: FastAPI dependency `get_current_empresa_id`
- Flow: Extracts `Bearer` JWT from `Authorization` header → validates via `sb.auth.get_user(token)` → looks up `membros` table to resolve `empresa_id`
- Used as `Depends(get_current_empresa_id)` in protected routes
- Webhook endpoints (`/webhook/{empresa_id}/{token}`) use URL token auth, not JWT

**Scheduler (`leadflow-backend/app/scheduler.py`):**
- Purpose: Singleton `AsyncIOScheduler` instance (APScheduler), timezone `America/Sao_Paulo`
- Started in FastAPI `lifespan` context manager at app startup
- Shared across all router modules via import

**Frontend Services (`leadflow-frontend/src/services/`):**
- `api.js` — axios instance with base URL `https://leadflow-backend.bqvcbz.easypanel.host`, injects JWT from Supabase session on every request, handles 401 by signing out
- `supabase.js` — Supabase JS client for auth and direct table queries (dashboard metrics read directly from Supabase, bypassing backend)

**Frontend Contexts (`leadflow-frontend/src/contexts/`):**
- `AuthContext.jsx` — provides `user`, `tenant` (empresa + papel), `signIn`, `signUp`, `signOut`, `resetPassword`; resolves `empresa_id` by joining `membros` → `empresas` on login

---

## Auth Model

**User auth:** Supabase Auth (email + password). JWT is a Supabase-issued access token.

**Tenant resolution:** Every authenticated user maps to exactly one `empresa_id` via the `membros` table (`usuario_id` → `empresa_id` + `papel`). The backend dependency `get_current_empresa_id` (`app/auth.py`) performs this lookup on every protected request.

**Webhook auth:** `POST /webhook/{empresa_id}/{token}` — validated by querying `webhooks` table for matching `empresa_id` + `token` + `ativo=True`. No JWT involved.

**API key storage:** Third-party credentials (Evolution API key, LLM keys, Zoom credentials, Google OAuth) are stored as JSON in `empresas.config_apis` JSONB column, scoped per empresa.

**Data isolation:** All queries include `.eq("empresa_id", empresa_id)`, enforced at the application layer (not RLS).

---

## Data Flow: Lead Creation → Qualification → Scheduling

1. External form tool POSTs to `POST /webhook/{empresa_id}/{token}` (`webhook.py:receber_webhook`)
2. Webhook token validated against `webhooks` table
3. Payload fields extracted via configurable field mapping (`mapeamento_campos` in webhook record)
4. Lead inserted into `leads` table with `status="pendente"`
5. If `ad_id` present and `meta_access_token` configured → `meta.py:buscar_info_anuncio` enriches `canal`/`criativo`
6. If `score >= score_minimo` (from `empresas.config_ia`) and Evolution configured:
   - LLM generates opening message via `agente.py:_gerar_resposta_{provider}_com_agenda` (with Calendar function calling) or `llm.py:gerar_resposta`
   - Message sent via `evolution.py:enviar_mensagem` → lead `status="enviado"`
   - Opening message saved to `conversas` table (`role="assistant"`)
   - `FOLLOWUP_AGENDA_START:{timestamp}` marker saved to `conversas` → triggers `followup_agenda.py:agendar_followups_para_lead`
7. If score below minimum → lead `status="nao_enviado"`
8. Notification team members receive WhatsApp text + PDF via dedicated Evolution instance

**Scheduling (agent-driven):**
1. Lead replies → `POST /agente/evolution/webhook` receives event from Evolution API
2. Agent looks up empresa by `evolution_instancia` field, loads lead, loads `conversas` history (last 20 messages)
3. LLM called with function tools `buscar_horarios_livres` + `criar_agendamento` (Google Calendar)
4. On slot confirmed: Calendar event created, `agendamentos` row inserted, lead `status="agendado"`
5. WhatsApp group optionally created (`leads.py:_criar_grupo_agendamento`), warmup messages scheduled (`warmup_grupo.py:agendar_aquecimento_grupo`)
6. Zoom link generated if `zoom_*` credentials configured

**Manual scheduling (frontend-triggered):**
- `POST /leads/{lead_id}/agendar-manual` — creates Calendar event + Zoom meeting + group + follow-up sequences

---

## AI Agent Conversation Flow

Entry point: `POST /agente/evolution/webhook` (`agente.py:receber_mensagem_evolution`)

1. **Event filtering:** Ignores non-`MESSAGES_UPSERT` events, `fromMe=True` messages (except saves `HUMANO_ASSUMIU` marker if operator typed), messages from internal team numbers, group messages
2. **Empresa resolution:** Loops all empresas to match `evolution_instancia` to incoming payload's `instance` field
3. **Lead lookup:** Queries `leads` by `telefone` + `empresa_id`
4. **History load:** Last 20 messages from `conversas` ordered ascending
5. **Guard checks:** `agente_pausado`, `score_minimo`, `HUMANO_ASSUMIU` marker (suppresses bot if human took over)
6. **LLM dispatch:** Chooses between `_gerar_resposta_openai_com_agenda`, `_gerar_resposta_gemini_com_agenda` (with function calling for Calendar), or plain `llm.py:gerar_resposta`
7. **Function calling loop:** LLM may call `buscar_horarios_livres` (queries Google Calendar freebusy) and `criar_agendamento` (creates Calendar event); slots returned as `SLOT_YYYYMMDD_HHMM` tokens, never shown raw to lead
8. **Cancellation detection:** Regex on message for cancellation intent → deletes Calendar event, updates `agendamentos.status="cancelado"`, saves `FOLLOWUP_CANCEL_START` marker
9. **Response sent** via `evolution.py:enviar_mensagem`
10. **Conversation saved:** `role="user"` and `role="assistant"` records inserted into `conversas`
11. **Follow-up timer reset:** Saves new `FOLLOWUP_AGENDA_START` marker if lead sent a message (resets follow-up timer)

---

## Scheduling Architecture (APScheduler)

APScheduler runs inside the FastAPI process as `AsyncIOScheduler` (`app/scheduler.py`).

**Jobs registered at startup (`app/main.py:lifespan`):**
- `noshow_check` — `interval` trigger, every 30 minutes → `noshow_check.py:executar_noshow_check`
- Recovery jobs — `recuperar_followups_pendentes()` re-registers pending follow-up jobs from DB markers
- Recovery jobs — `recuperar_aquecimentos_pendentes()` + `recuperar_notificacoes_pendentes()` re-register group warmup/notification jobs

**Follow-up sequences (`followup_agenda.py`):**
- Triggered when `FOLLOWUP_AGENDA_START`, `FOLLOWUP_CANCEL_START`, or `FOLLOWUP_NOSHOW_START` markers are written to `conversas`
- Each entry in `config_agendamento.followups_agenda` (list of `{delay_minutos, mensagem}`) creates one APScheduler `date` trigger job
- Job ID: `fu_{empresa_id[:8]}_{telefone}_{prefix_tag}_{index}` — `replace_existing=True` prevents duplicates
- Anti-duplicate guard: checks `FOLLOWUP_AGENDA_SENT:{i}` marker before sending each message
- Cancels if user replied after the START timestamp

**Group warmup (`warmup_grupo.py`):**
- Triggered after group creation in `leads.py:_criar_grupo_agendamento`
- Each item in `config_agendamento.grupo_aquecimento` creates one `date` trigger job
- Sends text or image/video to group JID
- Pre-meeting notification jobs also scheduled for configured time windows before meeting

**No-show check (`noshow_check.py`):**
- Runs every 30 minutes
- Queries `agendamentos` with `status="confirmado"` and `inicio < (now - 90 min)`
- Marks as `noshow`, updates lead `status="noshow_agendamento"`, writes `FOLLOWUP_NOSHOW_START` marker

---

## Error Handling

**Strategy:** Try/except everywhere. Failures in non-critical paths (notifications, PDF generation, LLM enrichment) are caught, logged to stdout, and silently skipped. Critical path failures (lead insert, evolution send) return `JSONResponse(status_code=500)`.

**Global handler:** `app/main.py` registers a global exception handler returning `{"ok": False, "erro": ..., "trace": ...}` with HTTP 500.

**LLM fallback:** If LLM call fails in webhook, falls back to `config_ia.mensagem_inicial` static message.

**Calendar fallback:** OAuth2 tried first (from `calendario_tokens` table), then service account credentials from `config_apis.google_calendar_credentials`.

---

## Cross-Cutting Concerns

**Logging:** `print()` statements throughout with prefixes like `[WEBHOOK]`, `[AGENTE]`, `[FOLLOWUP]`, `[NOSHOW]`, `[GRUPO]`. No structured logging framework.

**Validation:** Minimal. Pydantic models used only in `followup.py` request bodies. Most endpoints accept raw `dict` bodies.

**Multi-tenancy:** Enforced at application layer via `empresa_id` filter on every query. No Supabase RLS observed in codebase.

**CORS:** `allow_origins=["*"]` — open to all origins.

**Encoding:** Webhook endpoint handles both UTF-8 and Latin-1 payloads (try/except on decode).
