# Coding Conventions

## Summary

Leadflow is a bilingual codebase: a Python FastAPI backend using Brazilian Portuguese identifiers and print-based logging, and a React JSX frontend using camelCase JavaScript. The backend is organized into focused router modules with no framework-enforced structure beyond FastAPI routers. All data access is done through a freshly-instantiated Supabase client per call (`get_supabase()`). Multi-tenant isolation is enforced by appending `.eq("empresa_id", empresa_id)` on every query. Config is stored in a JSONB column (`config_apis`) on the `empresas` table rather than environment variables, except for bootstrap credentials. There are no linters or formatters configured in either project.

---

## Naming Patterns

**Backend (Python):**
- Files: `snake_case` module names matching the domain (`followup_agenda.py`, `noshow_check.py`, `warmup_grupo.py`)
- Functions: `snake_case` throughout — `get_supabase()`, `executar_noshow_check()`, `agendar_followups_para_lead()`
- Local variables: Portuguese `snake_case` — `empresa_id`, `config_apis`, `evo_instancia`, `nome_arquivo`
- Private/internal helpers: prefixed with underscore — `_get_nested()`, `_extrair()`, `_processar_noshow()`, `_gerar_resposta_openai_com_agenda()`
- Internal output parameters: double-underscore prefix by convention — `_slots_out`, `_evento_id_out` (passed as mutable lists)

**Frontend (JavaScript/JSX):**
- Files: `PascalCase` for page components (`Leads.jsx`, `Configuracoes.jsx`), `camelCase` for services (`api.js`, `supabase.js`)
- Component functions: `PascalCase` — `export default function Leads()`, `export function StatusBadge()`
- Local state and helper functions: `camelCase` — `const [filtroStatus, setFiltroStatus]`, `function exportarCSV()`
- Route paths: kebab-case — `/followup`, `/base-rag`, `/agente`

---

## Code Style

**Formatting:**
- No formatter is configured in either project (no `.prettierrc`, `biome.json`, or `pyproject.toml` with Black/Ruff)
- Backend indentation: 4 spaces (Python standard)
- Frontend indentation: 2 spaces (observed in JSX files)

**Linting:**
- No ESLint config detected in frontend
- No Ruff/Flake8/Pylint config detected in backend
- Code is not linted in CI

---

## Import Organization

**Backend:**
- Standard library first, then third-party, then `app.*` internal modules
- Heavy service imports (LLM clients, `requests_oauthlib`) are done inline inside functions to defer import cost and avoid circular dependencies — this is intentional and common:
  ```python
  # In webhook.py endpoint body:
  from app.services.llm import gerar_resposta
  from app.routers.agente import _gerar_resposta_openai_com_agenda
  ```
- Router imports are consolidated at the top of `app/main.py`

**Frontend:**
- React hooks first, then context, then services, then component library, then external libs:
  ```js
  import { useEffect, useState } from 'react'
  import { useAuth } from '../contexts/AuthContext'
  import { supabase } from '../services/supabase'
  import api from '../services/api'
  import { StatusBadge, Badge } from '../components/UI'
  import { format } from 'date-fns'
  import { Search, Download } from 'lucide-react'
  ```
- No path aliases — all imports use relative paths (`../contexts/`, `../services/`)

---

## Supabase Access Pattern

**Backend — always call `get_supabase()` at the top of each endpoint:**
```python
# app/db/client.py
def get_supabase():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    return create_client(url, key)

# In every router endpoint:
sb = get_supabase()
res = sb.table("leads").select("*").eq("empresa_id", empresa_id).execute()
```
- A new client is instantiated per request — there is no connection pooling or shared singleton
- Always chain `.eq("empresa_id", empresa_id)` immediately after `.table()` for tenant isolation
- Use `.limit(1).execute()` for single-row lookups, `.single().execute()` only when exactly one row is guaranteed
- Result data is accessed via `.data` list: `res.data[0]` or `res.data or []`
- Updates use `.update({...}).eq("id", row_id).execute()` — no return value is checked on updates

**Frontend — import the singleton and query directly in component functions:**
```js
// src/services/supabase.js — singleton
export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)

// In page components — direct Supabase query
const { data, error } = await supabase
  .from('leads')
  .select('id,nome,...')
  .eq('empresa_id', tenant.empresa.id)
  .order('criado_em', { ascending: false })
```
- `tenant.empresa.id` from `useAuth()` context is the source of `empresa_id` in all frontend queries
- Frontend uses the Supabase anon key (publishable) — RLS on the database is the security layer for frontend queries
- Backend uses the Supabase service key — bypasses RLS and performs its own `empresa_id` scoping manually

---

## empresa_id Scoping

**Backend pattern — every route that accesses tenant data uses `Depends(get_current_empresa_id)`:**
```python
# app/auth.py
async def get_current_empresa_id(authorization: str = Header(None)) -> str:
    token = authorization.replace("Bearer ", "")
    sb = get_supabase()
    user = sb.auth.get_user(token)
    membro = sb.table("membros").select("empresa_id").eq("usuario_id", user.user.id).single().execute()
    return membro.data["empresa_id"]

# Usage:
@router.get("/leads")
async def listar_leads(empresa_id: str = Depends(get_current_empresa_id)):
    sb = get_supabase()
    res = sb.table("leads").select("*").eq("empresa_id", empresa_id)...
```

**Webhook and background jobs** receive `empresa_id` from the URL path (`/webhook/{empresa_id}/{token}`) or from database records — they do not use the auth dependency.

**Frontend** always passes `tenant.empresa.id` into every Supabase query:
```js
const { tenant } = useAuth()
supabase.from('leads').select('...').eq('empresa_id', tenant.empresa.id)
```

---

## Config Loading Pattern

All per-empresa runtime configuration lives in the `empresas` table in three JSONB columns:
- `config_apis` — external API credentials (Evolution, OpenAI, Gemini, Anthropic, Google Calendar OAuth, Zoom, Meta)
- `config_ia` — LLM agent settings (model, temperature, max_tokens, score_minimo, prompt_sistema, agente_pausado)
- `config_agendamento` — calendar/scheduling settings (followups_agenda list, grupo_aquecimento list, business hours)

**Backend access pattern:**
```python
empresa_res = sb.table("empresas").select("config_apis, config_ia").eq("id", empresa_id).limit(1).execute()
config_apis = empresa_res.data[0].get("config_apis") or {}
config_ia   = empresa_res.data[0].get("config_ia") or {}

evo_url = config_apis.get("evolution_url") or os.getenv("EVOLUTION_API_URL", "")
api_key = config_apis.get(f"{prov}_key", "")
```
- Always use `or {}` as fallback when extracting JSONB columns (they may be NULL)
- Environment variables serve as a system-wide fallback only; per-empresa `config_apis` takes precedence

---

## APScheduler Job Pattern

Jobs are always added to the global `scheduler` singleton from `app/scheduler.py`. Use `date` trigger for exact-time jobs and `interval` trigger for recurring checks.

```python
from app.scheduler import scheduler

# One-shot job at specific datetime:
scheduler.add_job(
    _executar_followup_job,
    "date",
    run_date=run_at,              # datetime object in UTC
    args=[empresa_id, telefone, i, marker_prefix, start_ts_iso],
    id=job_id,                    # deterministic string, e.g. f"fu_{empresa_id[:8]}_{telefone}_{type}_{i}"
    replace_existing=True,
    timezone="UTC",
)

# Recurring job (registered in lifespan):
scheduler.add_job(executar_noshow_check, "interval", minutes=30, id="noshow_check")
```

Job IDs are constructed to be globally unique and idempotent: `f"fu_{empresa_id[:8]}_{telefone}_{prefix_tag}_{index}"`. `replace_existing=True` is always set so recovery restarts do not fail.

Recovery at startup is handled by scanning the `conversas` table for `START` markers without a corresponding complete set of `SENT` markers. See `app/routers/followup_agenda.py` (`recuperar_followups_pendentes`) and `app/routers/warmup_grupo.py` (`recuperar_aquecimentos_pendentes`).

---

## Error Handling Pattern

**Backend — nested try/except with print-based logging:**
```python
try:
    # primary operation
    result = sb.table("leads").insert({...}).execute()
except Exception as _ins_exc:
    print(f"[WEBHOOK] INSERT com rastreamento falhou ({_ins_exc}), tentando sem canal/criativo/ad_id")
    try:
        result = sb.table("leads").insert(_lead_base).execute()
    except Exception as _ins_exc2:
        print(f"[WEBHOOK] INSERT base também falhou: {_ins_exc2}")
        return JSONResponse({"ok": False, "erro": f"Falha ao salvar lead: {_ins_exc2}"}, status_code=500)
```

- Background/non-critical operations are silently swallowed with bare `except Exception: pass`
- Logging is done exclusively with `print()` — format is `[MODULE-TAG] message`
- Global exception handler in `app/main.py` returns `{"ok": False, "erro": str(exc), "trace": traceback.format_exc()}` for any unhandled exception
- Success responses use `{"ok": True, ...}`, error responses use `{"ok": False, "erro": "..."}` — this is the standard envelope

**Frontend — minimal error handling, console.error for unexpected errors:**
```js
// Data load functions return early on error
if (error) console.error('[Leads] erro ao carregar:', error.message)
setLeads(data ?? [])

// Auth errors auto-redirect via axios interceptor:
if (err.response?.status === 401) {
    supabase.auth.signOut()
    window.location.href = '/login'
}
```

---

## Logging Pattern

**Backend:** All logging uses `print()` with bracketed module tags. No Python `logging` module is used anywhere in the main application code. The only exception is `app/tasks/followup_tasks.py` which uses Celery's `get_task_logger` (that module is a stub).

Format: `print(f"[TAG] descriptive message with {variables!r}")`

Common tags observed: `[SCHEDULER]`, `[WEBHOOK]`, `[AGENTE]`, `[AGENTE-TURNO]`, `[AGENTE-SLOTS]`, `[FOLLOWUP]`, `[NOSHOW]`, `[META]`, `[CANCEL]`, `[GRUPO]`, `[AGENDA]`, `[TRAVA Q1/Q2]`

Use `!r` (repr) for string variables in log lines to make empty strings and None visible.

---

## Frontend React Patterns

**Component structure:**
- All page components are default exports from `src/pages/`
- Shared UI primitives (`Badge`, `StatusBadge`, `Spinner`, `PageHeader`, `Modal`, `FormField`) live in `src/components/UI.jsx`
- Auth context is provided by `src/contexts/AuthContext.jsx` via `AuthProvider` wrapping the entire app in `src/App.jsx`
- `useAuth()` hook is the single access point for session state and `tenant.empresa.id`

**State management:**
- All state is local `useState` — no global state library
- Data is fetched in `useEffect` triggered by `tenant` becoming available
- Loading states use boolean `loading` and actions use strings or IDs for "in-progress" tracking (e.g., `const [zoomEnviando, setZoomEnviando] = useState(null)` stores the lead_id being processed)

**Supabase vs API calls:**
- Read operations (SELECT) go directly through the Supabase JS client
- Write/action operations go through the FastAPI backend via `api` (axios instance from `src/services/api.js`)

---

## Module Organization

**Backend:**
```
app/
  main.py           — FastAPI app, lifespan, middleware, router registration
  auth.py           — get_current_empresa_id dependency
  scheduler.py      — APScheduler singleton
  db/client.py      — get_supabase() factory
  routers/          — one file per domain (webhook, leads, agente, agenda, agendamentos,
                       configuracoes, followup, followup_agenda, noshow_check, warmup_grupo, documentos)
  services/         — external service wrappers (evolution, llm, google_calendar, zoom, meta, rag, pdf_generator)
  tasks/            — Celery stubs (largely unused; APScheduler is the active scheduler)
  core/             — lead_state.py (empty file, placeholder)
```

**Frontend:**
```
src/
  App.jsx           — router and AuthProvider wrapper
  main.jsx          — ReactDOM.createRoot entry point
  contexts/         — AuthContext.jsx (auth state, tenant)
  components/       — AppLayout.jsx, Sidebar.jsx, UI.jsx, ProtectedRoute.jsx
  pages/            — one file per route
  services/         — api.js (axios), supabase.js (client singleton)
```
