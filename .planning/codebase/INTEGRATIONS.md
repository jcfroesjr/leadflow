# External Integrations

## Summary

LeadFlow integrates with seven external services: Evolution API (WhatsApp messaging), Supabase (database + auth), Google Calendar (scheduling), Zoom (video meetings), Meta Graph API (ad attribution), a multi-provider LLM gateway (Anthropic Claude / Google Gemini / OpenAI GPT), and OpenAI Embeddings for RAG. All integration credentials are stored per-company in the `empresas.config_apis` JSONB column in Supabase, with environment variable fallbacks for global defaults.

---

## Evolution API (WhatsApp)

**Purpose:** Send and receive WhatsApp messages, create groups, send media/documents/contacts. Core delivery channel for the AI sales agent.

**Implementation file:** `leadflow-backend/app/services/evolution.py`

**Called from:**
- `leadflow-backend/app/routers/webhook.py` — sends initial contact message and team notifications on new lead
- `leadflow-backend/app/routers/agente.py` — sends AI agent replies to leads
- `leadflow-backend/app/routers/followup_agenda.py` — sends follow-up messages
- `leadflow-backend/app/routers/warmup_grupo.py` — sends group warm-up messages

**Auth pattern:** `apikey` header (`"apikey": api_key`). Credentials resolved per-company:
1. `empresas.config_apis.evolution_url` and `empresas.config_apis.evolution_key`
2. Falls back to `EVOLUTION_API_URL` / `EVOLUTION_API_KEY` env vars

**Instance model:** Each company configures a named WhatsApp instance stored in `empresas.evolution_instancia` or `config_apis.evolution_instancia`. A separate `notificacoes_instancia` can be configured for team notification messages.

**Key functions in `evolution.py`:**
- `enviar_mensagem(base_url, api_key, instancia, numero, texto)` — POST `/message/sendText/{instancia}`
- `enviar_documento(base_url, api_key, instancia, numero, base64_data, nome_arquivo)` — POST `/message/sendMedia/{instancia}` with `mediatype: document`
- `enviar_midia_grupo(base_url, api_key, instancia, grupo_jid, tipo, media)` — POST `/message/sendMedia/{instancia}`
- `enviar_contato(base_url, api_key, instancia, numero_destino, nome_contato, numero_contato)` — POST `/message/sendContact/{instancia}`
- `criar_grupo(base_url, api_key, instancia, subject, participants)` — POST `/group/create/{instancia}`

**Incoming webhook endpoint:** `POST /webhook/{empresa_id}/{token}` in `leadflow-backend/app/routers/webhook.py` — receives lead data from form platforms (Typeform, RD Station, etc.) and triggers the AI agent.

---

## Supabase

**Purpose:** PostgreSQL database (primary data store), authentication (JWT-based), and pgvector for RAG similarity search.

**Implementation files:**
- `leadflow-backend/app/db/client.py` — backend client factory (`create_client` with service key)
- `leadflow-frontend/src/services/supabase.js` — frontend client (public anon key)
- `leadflow-frontend/src/contexts/AuthContext.jsx` — auth state management
- `leadflow-backend/app/auth.py` — JWT verification middleware

**Auth pattern:**
- Backend: service role key via `SUPABASE_SERVICE_KEY` env var — bypasses RLS for server operations
- Frontend: public anon key hardcoded in `supabase.js` — subject to RLS policies
- User auth: `supabase.auth.signInWithPassword()` (email/password) in `AuthContext.jsx`
- Backend verifies frontend tokens via `sb.auth.get_user(token)` in `auth.py`

**Tables accessed (identified from router queries):**
- `empresas` — company config: `nome`, `evolution_instancia`, `config_apis` (JSONB), `config_ia` (JSONB), `config_agendamento` (JSONB), `fuso`
- `leads` — lead records: `nome`, `telefone`, `email`, `score`, `origem`, `status`, `dados_raw`, `canal`, `criativo`, `ad_id`, `empresa_id`
- `webhooks` — webhook configs: `empresa_id`, `token`, `ativo`, `mapeamento_campos`, `plataforma`
- `membros` — user-company membership: `usuario_id`, `empresa_id`, `papel`
- `conversas` — chat history: `empresa_id`, `telefone`, `role`, `conteudo`, `criado_em`
- `agendamentos` — scheduled meetings: `empresa_id`, `lead_id`, `inicio`, `status`
- `calendario_tokens` — OAuth2 tokens for Google Calendar: `empresa_id`, `plataforma`, `access_token`, `refresh_token`

**pgvector / RAG:**
- Supabase RPC function `buscar_chunks_rag` called in `leadflow-backend/app/services/rag.py`
- Parameters: `query_embedding`, `empresa_id_param`, `match_count`, `match_threshold`
- Embeddings generated via OpenAI `text-embedding-3-small` (1536 dimensions)

**Real-time usage:** Not detected in backend. Frontend uses standard `supabase-js` query methods only.

---

## Google Calendar

**Purpose:** Check free/busy slots, create meeting events, delete events, rename events. Used by the AI agent to propose and confirm appointment times during conversations.

**Implementation file:** `leadflow-backend/app/services/google_calendar.py`

**Called from:** `leadflow-backend/app/routers/agente.py` (via function calling tools for OpenAI/Gemini)

**Auth pattern — dual mode:**
1. **OAuth2 (preferred):** Tokens stored in `calendario_tokens` Supabase table per company. Resolved in `leadflow-backend/app/routers/webhook.py` and `agente.py`. `client_id`/`client_secret` come from `config_apis.google_oauth_client_id` / `config_apis.google_oauth_client_secret`.
2. **Service Account (fallback):** Full credentials JSON stored in `config_apis.google_calendar_credentials`. Loaded via `google.oauth2.service_account.Credentials.from_service_account_info()`.

**Config keys in `empresas.config_apis`:**
- `google_calendar_credentials` — service account JSON dict
- `google_calendar_id` — primary calendar ID (default: `"primary"`)
- `google_calendars_verificar` — list of additional calendar IDs to check for conflicts
- `google_oauth_client_id` / `google_oauth_client_secret` — OAuth2 app credentials

**Key functions in `google_calendar.py`:**
- `buscar_horarios_livres(...)` — returns list of available slot strings (`DD/MM/YYYY HH:MM`). Supports `nome_dia`, `data_especifica`, `proxima_semana` filtering. Uses `freebusy().query()`.
- `verificar_slot_livre(...)` — bool check for a specific slot
- `criar_evento_calendar(...)` — creates event via `events().insert()`, returns `evento_id` and `link`
- `deletar_evento_calendar(...)` — deletes event by ID
- `buscar_e_deletar_eventos_lead(...)` — finds and deletes future events matching a query string
- `buscar_evento_no_horario(...)` — finds event near a given datetime (±window)
- `renomear_evento_calendar(...)` — patches event title

---

## Zoom

**Purpose:** Create scheduled Zoom meetings when an appointment is confirmed. Returns `join_url` to be sent to the lead.

**Implementation file:** `leadflow-backend/app/services/zoom.py`

**Called from:** `leadflow-backend/app/routers/agendamentos.py` (when creating/confirming appointments)

**Auth pattern:** Server-to-Server OAuth. Credentials per-company in `config_apis`:
- `zoom_account_id`
- `zoom_client_id`
- `zoom_client_secret`

Token obtained on each call: POST `https://zoom.us/oauth/token?grant_type=account_credentials&account_id={account_id}` with HTTP Basic auth (client_id:client_secret). No token caching — token fetched fresh per meeting creation.

**Key function:**
- `criar_reuniao_zoom(account_id, client_id, client_secret, titulo, data, hora_inicio, duracao_minutos, fuso)` — async, returns `join_url` string or `None`
- Meeting settings: `join_before_host=True`, `waiting_room=False`, type 2 (scheduled)

---

## Meta Graph API (Meta Ads)

**Purpose:** Enrich incoming leads with ad attribution data — resolve `ad_id` to campaign name, ad set name, and ad name for analytics/CRM tagging.

**Implementation file:** `leadflow-backend/app/services/meta.py`

**Called from:** `leadflow-backend/app/routers/webhook.py` — triggered after lead insert when `ad_id` is present in the webhook payload and `meta_access_token` is configured.

**Auth pattern:** Long-lived access token stored per-company in `config_apis.meta_access_token`. Passed as `access_token` query parameter.

**API version:** Meta Graph API v21.0 (`https://graph.facebook.com/v21.0`)

**Key function:**
- `buscar_info_anuncio(access_token, ad_id)` — async GET `/{ad_id}?fields=name,campaign{name},adset{name}`
- Returns: `{ ad_name, campaign_name, adset_name }` dict
- Result written to `leads.canal` (campaign name) and `leads.criativo` (ad name) columns

---

## LLM Gateway (Multi-Provider AI)

**Purpose:** Generate AI sales agent responses. Supports three providers: Google Gemini, Anthropic Claude, OpenAI GPT. Provider selected per-company via `config_ia.modelo` / `config_ia.provider`.

**Implementation file:** `leadflow-backend/app/services/llm.py`

**Called from:**
- `leadflow-backend/app/routers/agente.py` — processes incoming WhatsApp messages, generates replies
- `leadflow-backend/app/routers/webhook.py` — generates initial contact message on new lead

**Provider detection in `llm.py`:**
- Model name starts with `"gemini"` → Google Gemini (`google-genai` SDK, `genai.Client`)
- Model name starts with `"claude"` → Anthropic (`anthropic.AsyncAnthropic`)
- All others → OpenAI (`openai.AsyncOpenAI`)

**Auth pattern:** API key resolved per-company from `config_apis.{provider}_key` (e.g. `gemini_key`, `openai_key`, `anthropic_key`). Falls back to env vars `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.

**Key function:**
- `gerar_resposta(modelo, system_prompt, mensagem, api_key, temperatura, max_tokens, provider, historico)` — async, returns text string

**Function calling (for calendar scheduling):**
- OpenAI: `_gerar_resposta_openai_com_agenda()` in `agente.py` — tools: `buscar_horarios_livres`, `criar_agendamento`
- Gemini: `_gerar_resposta_gemini_com_agenda()` in `agente.py` — equivalent tool definitions
- Anthropic (Claude): no function calling for calendar — uses plain `gerar_resposta()`

---

## OpenAI Embeddings (RAG)

**Purpose:** Vector similarity search over company knowledge base documents (PDFs, DOCX). Provides contextual answers for the AI agent.

**Implementation file:** `leadflow-backend/app/services/rag.py`

**Called from:** `leadflow-backend/app/routers/documentos.py` (indexing), `leadflow-backend/app/routers/agente.py` (retrieval during conversations)

**Model:** `text-embedding-3-small` (1536 dimensions)

**Storage:** Embeddings stored in Supabase with pgvector extension. Retrieved via RPC `buscar_chunks_rag`.

**Auth:** OpenAI key from `config_apis.openai_key` (per-company).

**Key functions in `rag.py`:**
- `gerar_embedding(texto, api_key)` — single embedding
- `gerar_embeddings_batch(textos, api_key)` — batch embeddings (100 per request)
- `buscar_contexto_rag(mensagem, empresa_id, api_key, top_k, threshold)` — full retrieval pipeline

---

## APScheduler (In-Process Job Scheduler)

**Purpose:** Schedule time-exact jobs within the FastAPI process: follow-up messages, no-show detection, group warm-up sequences.

**Implementation file:** `leadflow-backend/app/scheduler.py`

**Scheduler instance:** `AsyncIOScheduler` with `timezone=America/Sao_Paulo`, `misfire_grace_time=None` (jobs always fire even if delayed).

**Jobs registered:**
- `executar_noshow_check` — interval trigger, every 30 minutes. Registered in `app.main:lifespan`.
- Follow-up jobs — `date` trigger (exact timestamp). Registered by `agendar_followups_para_lead()` in `followup_agenda.py`.
- Group warm-up jobs — `date` trigger. Registered by `agendar_aquecimento_grupo()` in `warmup_grupo.py`.
- Group notification jobs — `date` trigger. Registered by `agendar_notificacoes_grupo()` in `warmup_grupo.py`.

**Persistence:** No persistent job store — in-memory only. On restart, `recuperar_followups_pendentes()`, `recuperar_aquecimentos_pendentes()`, and `recuperar_notificacoes_pendentes()` query the `conversas` table for unprocessed `START` markers and re-schedule outstanding jobs.

---

## Celery + Redis (Distributed Task Queue)

**Purpose:** Background task processing for follow-up checks and agendamento cleanup. Secondary to APScheduler.

**Implementation files:**
- `leadflow-backend/app/worker.py` — Celery app config and beat schedule
- `leadflow-backend/app/tasks/followup_tasks.py` — follow-up verification task
- `leadflow-backend/app/tasks/agendamento_tasks.py` — agendamento cleanup task

**Broker/Backend:** Redis (`REDIS_URL` env var, default `redis://localhost:6379`)

**Beat schedule:**
- `verificar_followups_pendentes` — every 15 minutes (`crontab(minute="*/15")`)
- `limpar-agendamentos-antigos` — defined in `worker.py`

**Config:** `task_acks_late=True`, `worker_prefetch_multiplier=1` (safe for long-running tasks)

---

*Integration audit: 2026-04-07*
