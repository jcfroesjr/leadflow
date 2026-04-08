# Testing Patterns

## Summary

Leadflow has minimal automated test coverage. The backend has two pytest test files covering two specific utility functions isolated from the router layer. There is no test framework configured for the frontend — no Jest, Vitest, or Playwright setup exists. The majority of quality assurance happens through manual testing via dedicated test endpoints built into the API itself (`/teste/whatsapp`, `/teste/notificacao`) and through print-statement logging observed in production. This document describes what exists, what is observable in the code, and the recommended approach for expanding coverage.

---

## Test Framework

**Runner:**
- `pytest` (version inferred from compiled `.pyc` filenames: `pytest-9.0.2`)
- Config: none — no `pytest.ini`, `pyproject.toml`, or `setup.cfg` detected
- Location: `leadflow-backend/tests/`

**Run Command:**
```bash
cd leadflow-backend
pytest tests/
```

No coverage report, no watch mode, no CI integration configured.

**Frontend:**
- No test runner configured. `package.json` has no `test` script.
- No Jest, Vitest, or Playwright config files detected.

---

## Existing Test Files

**`leadflow-backend/tests/test_agente_fixes.py`**

Tests two pure utility functions that are replicated inside the test file itself (the functions are not imported from production code):

1. `_strip_super_te_entendo(resposta)` — regex post-processing that removes a fixed greeting phrase from LLM output
2. `_filtrar_turno(slots, turno)` — filters time slot strings by morning/afternoon/evening

Tests are plain functions, no fixtures, no mocking, no Supabase calls:
```python
def test_strip_super_te_entendo_no_inicio():
    resposta = "Super te entendo 💛\n\nAqui estão os horários:\n- 26/03 às 09:00"
    resultado = _strip_super_te_entendo(resposta)
    assert "Super te entendo" not in resultado
    assert "Aqui estão os horários" in resultado
```

8 test functions total. All test string manipulation logic only.

**`leadflow-backend/tests/test_calendar_buffer.py`**

Tests calendar slot buffer logic — whether a slot within 60 minutes of now should be discarded. Uses `zoneinfo` for timezone-aware datetime construction but does not import any production code:

```python
def test_buffer_hoje_slot_dentro_60min_e_descartado():
    agora = _make_hoje(14, 0)
    slot_candidato = agora + timedelta(minutes=45)
    buffer = agora + timedelta(minutes=60)
    assert slot_candidato < buffer, "Slot dentro de 60min deve ser descartado"
```

3 test functions. All test datetime arithmetic only.

**Critical gap:** Both test files replicate the logic they are testing — neither imports from `app.routers.agente` or `app.services.google_calendar`. If the production implementation drifts from the copy in the test file, the tests will not catch it.

---

## Built-in Manual Test Endpoints

The API exposes three dedicated test endpoints in `leadflow-backend/app/routers/webhook.py`:

**`POST /teste/whatsapp`**
Tests Evolution API message delivery directly. Accepts `{ "numero", "mensagem", "instancia", "evo_url", "evo_key" }`. Falls back to environment variables for missing fields.

**`POST /teste/notificacao`**
Replays the full notification flow (text + PDF) for an existing lead. Accepts `{ "empresa_id", "lead_id" }`. Validates that Evolution is configured and telefones_notif list is populated.

**`GET /health`**
Returns `{"status": "ok", "version": "1.0.0", "build": "..."}`. Useful for confirming deployment.

These endpoints are the primary manual testing surface for the webhook and Evolution integration.

---

## Manual Testing via Print Logging

All router and service code uses `print()` for operational observability. Log lines follow the pattern `[MODULE-TAG] message`. To manually test the webhook flow end-to-end:

1. Send a POST to `/webhook/{empresa_id}/{token}` with a JSON payload
2. Observe stdout for the sequence:
   - `[WEBHOOK] lead criado id=... nome=... score=...`
   - `[WEBHOOK] notif: ativas=True telefones=N ...`
   - `[WEBHOOK] lead=... score=... score_minimo=... agente_ativo=True/False`
   - `[AGENTE-TURNO] msg_pura=...`
   - `[FOLLOWUP] job #0 ... agendado para ...`

Log lines using `!r` formatting (e.g., `{evo_instancia!r}`) make it easy to identify empty strings vs. None.

---

## Test Coverage Gaps

**Critical — untested production code paths:**

1. **Webhook flow** (`leadflow-backend/app/routers/webhook.py`) — the entire `receber_webhook` function is untested. This is the most critical path in the system: it receives leads, routes to the AI agent, triggers notifications, and starts the follow-up scheduler.

2. **AI agent router** (`leadflow-backend/app/routers/agente.py`) — the Q1/Q2 conversation flow trava (guard logic), LLM provider selection, and function-calling for calendar are all untested. This file is ~2200 lines and contains the most complex business logic.

3. **Follow-up scheduler** (`leadflow-backend/app/routers/followup_agenda.py`) — the recovery logic (`recuperar_followups_pendentes`) and anti-duplicate markers are untested.

4. **No-show detection** (`leadflow-backend/app/routers/noshow_check.py`) — the `executar_noshow_check` function runs every 30 minutes in production and is entirely untested.

5. **Frontend** — zero test coverage. All pages, context, and service logic are untested.

6. **Supabase query construction** — because `get_supabase()` creates a real client with live credentials, there is no mock for database calls. Any test that touches a router must either use real Supabase or mock the client.

---

## Recommended Testing Approach

**Phase 1 — Unit tests for pure logic (no mocking needed)**

Expand the existing pattern: extract pure utility functions from large router files and test them in isolation. Priority targets:

- `_substituir_variaveis()` in `agente.py` — variable substitution in LLM prompts
- `_get_nested()` and `_extrair()` in `webhook.py` — field mapping from webhook payloads
- Slot filtering and buffer logic (already tested but against duplicated code — refactor to import from production)
- `_get_provider()` in `services/llm.py` — model name to provider mapping

**Phase 2 — Integration tests with Supabase mocking**

Use `unittest.mock.patch` to mock `get_supabase()` and return a `MagicMock` that simulates table query chains:

```python
from unittest.mock import MagicMock, patch

def make_sb_mock(data):
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = data
    return sb

@patch("app.db.client.get_supabase")
async def test_webhook_lead_sem_telefone(mock_sb):
    mock_sb.return_value = make_sb_mock([{"token": "abc", "ativo": True, "mapeamento_campos": {}}])
    # POST to /webhook/empresa/token with payload missing telefone
    # Assert response: {"ok": False, "erro": "Telefone não encontrado..."}
```

**Phase 3 — Webhook smoke test**

Use FastAPI's `TestClient` from `httpx` for end-to-end route testing without a live server:

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
```

**Phase 4 — Frontend component tests**

If frontend testing is added, use Vitest + React Testing Library. Priority targets: `AuthContext` (session flow), `Leads` (filter logic), `UI.jsx` (StatusBadge mapping).

---

## What Makes Testing Hard in This Codebase

1. **`get_supabase()` creates a new client per call** — must be mocked at import level in each module under test
2. **Inline imports inside endpoints** — e.g., `from app.services.llm import gerar_resposta` inside the endpoint body — require mocking at the specific import site
3. **APScheduler side effects** — `agendar_followups_para_lead()` schedules real jobs; tests must either mock the scheduler or use `misfire_grace_time` carefully
4. **No dependency injection** — Supabase client and scheduler are not injected, making substitution for testing require monkey-patching
5. **Long monolithic functions** — `receber_webhook` is ~400 lines; testing all branches requires many fixtures

---

## Test File Locations

```
leadflow-backend/
  tests/
    __init__.py
    test_agente_fixes.py      # 76 lines — string manipulation tests
    test_calendar_buffer.py   # 34 lines — datetime arithmetic tests
```

New test files should follow the `test_{module_name}.py` naming convention and be placed in `leadflow-backend/tests/`.
