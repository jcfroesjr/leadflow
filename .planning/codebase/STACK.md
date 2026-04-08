# Technology Stack

## Summary

LeadFlow is a multi-tenant SaaS lead management platform. The backend is a Python/FastAPI async API deployed on Easypanel via Docker. The frontend is a React 18 SPA built with Vite, styled with Tailwind CSS, and served by Nginx. Supabase provides the database (PostgreSQL), authentication, and file storage. There is no separate ORM — the backend uses the official `supabase-py` client directly.

---

## Languages

**Primary:**
- Python 3.11 — backend API, services, schedulers (`leadflow-backend/`)
- JavaScript (ES Modules, JSX) — frontend React app (`leadflow-frontend/src/`)

**Secondary:**
- SQL — Supabase migrations (`leadflow-backend/migrations/conversas_migration.sql`, `leadflow-backend/supabase/`)

---

## Runtime

**Backend:**
- Python 3.11 (pinned in `leadflow-backend/Dockerfile`: `FROM python:3.11-slim`)
- Uvicorn ASGI server, 2 workers: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2`

**Frontend:**
- Node 20 Alpine (build stage in `leadflow-frontend/Dockerfile`)
- Nginx Alpine (runtime stage, serves static build on port 80)

**Package Managers:**
- Backend: pip with `leadflow-backend/requirements.txt` (no lockfile)
- Frontend: npm with `leadflow-frontend/package.json` + `package-lock.json`

---

## Frameworks

**Backend Core:**
- FastAPI 0.115.0 — REST API framework (`leadflow-backend/requirements.txt`)
- Pydantic 2.8.0 — request/response validation
- Uvicorn 0.30.0 with `[standard]` extras — ASGI server

**Frontend Core:**
- React 18.3.1 — UI framework (`leadflow-frontend/package.json`)
- React Router DOM 6.26.0 — client-side routing
- Vite 5.3.0 — build tool and dev server (`leadflow-frontend/vite.config.js`)

**CSS/Styling:**
- Tailwind CSS 3.4.0 — utility-first CSS (`leadflow-frontend/tailwind.config.js`)
- PostCSS + Autoprefixer — build pipeline (`leadflow-frontend/postcss.config.js`)
- Custom brand color: `#1D9E75` (green) defined in `tailwind.config.js`

**Async Task Processing:**
- APScheduler 3.10.4 — in-process async scheduler (`leadflow-backend/app/scheduler.py`)
  - Uses `AsyncIOScheduler` with `timezone=America/Sao_Paulo`
  - Runs no-show checks every 30 minutes, follow-up jobs on `date` triggers
- Celery 5.4.0 + Redis 5.0.8 — distributed task queue (`leadflow-backend/app/worker.py`)
  - Beat schedule: followup check every 15 min, cleanup job
  - Tasks in `leadflow-backend/app/tasks/followup_tasks.py` and `agendamento_tasks.py`

---

## Key Dependencies

**Backend Critical:**
- `supabase==2.7.0` — database client (supabase-py), auth verification (`leadflow-backend/app/db/client.py`)
- `anthropic==0.34.0` — Claude AI SDK (`leadflow-backend/app/services/llm.py`)
- `google-genai>=1.0.0` — Gemini AI SDK (`leadflow-backend/app/services/llm.py`)
- `openai>=1.0.0` — OpenAI GPT SDK + embeddings for RAG (`leadflow-backend/app/services/llm.py`, `rag.py`)
- `google-api-python-client>=2.0.0` — Google Calendar API (`leadflow-backend/app/services/google_calendar.py`)
- `google-auth>=2.0.0` + `google-auth-oauthlib>=1.0.0` — OAuth2 and service account auth
- `httpx==0.27.0` — async HTTP client for Evolution API, Zoom, Meta Graph API
- `apscheduler==3.10.4` — in-process job scheduling
- `celery==5.4.0` — distributed task queue
- `redis==5.0.8` — Celery broker and backend
- `python-jose[cryptography]==3.3.0` + `passlib[bcrypt]==1.7.4` — JWT handling
- `fpdf2==2.7.9` — PDF generation for lead documents (`leadflow-backend/app/services/pdf_generator.py`)
- `gtts==2.5.3` — text-to-speech (Google TTS)
- `pypdf==4.3.1` + `python-docx==1.1.2` — document parsing for RAG knowledge base
- `cryptography==43.0.0` — encryption utilities
- `aiofiles==24.1.0` — async file I/O
- `python-multipart==0.0.9` — file upload support

**Frontend Critical:**
- `@supabase/supabase-js ^2.45.0` — database queries and auth (`leadflow-frontend/src/services/supabase.js`)
- `axios ^1.7.0` — HTTP client for backend API calls (`leadflow-frontend/src/services/api.js`)
- `react-router-dom ^6.26.0` — routing (`leadflow-frontend/src/App.jsx`)
- `lucide-react ^0.383.0` — icon library
- `date-fns ^3.6.0` — date formatting utilities

---

## Configuration

**Backend Environment Variables (loaded via `python-dotenv`):**
- `SUPABASE_URL` — Supabase project URL
- `SUPABASE_SERVICE_KEY` — service role key for backend DB access
- `EVOLUTION_API_URL` — Evolution API base URL (fallback; primary config is per-company in DB)
- `EVOLUTION_API_KEY` — Evolution API key (fallback)
- `REDIS_URL` — Redis broker URL for Celery
- `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` — LLM API keys (fallback; primary is per-company in DB)
- Per-company API keys are stored in `empresas.config_apis` JSONB column in Supabase

**Frontend Configuration:**
- Supabase URL and public anon key are hardcoded in `leadflow-frontend/src/services/supabase.js`
- Backend base URL is hardcoded in `leadflow-frontend/src/services/api.js`: `https://leadflow-backend.bqvcbz.easypanel.host`
- No `.env` files used on the frontend

**Build:**
- Backend: `leadflow-backend/Dockerfile` — python:3.11-slim, installs requirements, exposes 8000
- Frontend: `leadflow-frontend/Dockerfile` — multi-stage: Node 20 build → Nginx Alpine serve, `leadflow-frontend/nginx.frontend.conf`

---

## Platform Requirements

**Development:**
- Python 3.11+
- Node 20+
- Redis instance for Celery
- Supabase project (URL + service key)

**Production:**
- Easypanel hosting platform (Docker-based)
- Backend URL: `https://leadflow-backend.bqvcbz.easypanel.host`
- Frontend URL: `https://leadflow-frontend.bqvcbz.easypanel.host`
- Redis service (configured via `REDIS_URL`)

---

## Dev Tooling

**Testing:**
- Backend: pytest-style tests in `leadflow-backend/tests/` (`test_agente_fixes.py`, `test_calendar_buffer.py`)
- Frontend: no test framework detected

**Linting/Formatting:**
- No ESLint, Prettier, or Biome config detected in frontend
- No flake8, black, or ruff config detected in backend

**Migrations:**
- Manual SQL files in `leadflow-backend/migrations/`
- Migration runner script: `leadflow-backend/supabase/rodar_migrations.py`

---

*Stack analysis: 2026-04-07*
