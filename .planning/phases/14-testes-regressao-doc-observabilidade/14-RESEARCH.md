# Phase 14: Testes Regressao + Doc + Observabilidade — Research

**Researched:** 2026-06-10
**Domain:** pytest regression suite + healthcheck endpoint extension + structured log audit + documentation artifacts
**Confidence:** HIGH — all findings verified against actual source files in this session

---

## Summary

Phase 14 is the final phase of milestone v2.2. Its job is to lock the 5 motivating cases behind a regression suite, fill the observability gap in the existing healthcheck endpoint, and produce documentation artifacts. Phases 10-13 have already built all the production mechanisms; Phase 14 does not add new production logic — it only adds tests, extends one endpoint, and writes docs.

The key insight for the planner: **108 tests already pass** (excluding 2 known-broken env tests: `test_calendar_buffer.py` tzdata and `test_verificar_lead_no_grupo_phase3.py` httpx/idna). The new `test_v2_regression.py` will add 5 case-named tests (1 skipped) on top of the existing infrastructure. The healthcheck endpoint at `GET /admin/grupo-membership/health` already returns most of what OBS-V2-G1 asks for; the gap is `cache_hit_rate` (derivable from existing `cache_stats.hits/misses`) and explicit `total_rows_24h` windowing (currently returns all-time `total_rows` plus `writes_by_source_24h`). OBS-V2-G2 names the path `/health/grupo-membership` but the live endpoint is `/admin/grupo-membership/health` — the plan should extend the existing endpoint, not create a new path.

The OBS-V2-G1 log marker requirement uses `[GRUPO-STATE-CHANGE]` as the criterion label, but Phases 13 deliberately chose the prefix `GSC:` to avoid collision with `get_grupo_state`'s `.like("GRUPO_STATE:%")` parser. This is a resolved naming decision: the requirement criterion is satisfied by `GSC:` markers already present in `grupo_state.py`. No new marker needed — just document the mapping.

**Primary recommendation:** Write `test_v2_regression.py` with 4 passing + 1 `pytest.mark.skip` test, extend the healthcheck with `cache_hit_rate` computed field + rename of `total_rows` → `total_rows_24h` windowing, bump `BUILD_VERSION`, and write two memory docs (DOC-V2-G1 + DOC-V2-G2).

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEST-V2-G1 | Ana Carla (08/06) — Path 3 createGroup direct write, FSM=ATIVO <60s, no probe | `lead_in_group` source='membership' Path 3 verified in `leads.py`; `test_lead_in_group_decision.py::test_membership_hit_returns_without_probe` is the base pattern; new case-named test adds Path 3 createGroup stub |
| TEST-V2-G2 | Rosania (08/06) — webhook T+138s, retry max_age=600s waits instead of falling to DM | `test_probe_retry.py::test_rosania_sequence` + `test_table_hit_skips_probe` already cover core; new case-named test adds explicit T+138s narrative assertion |
| TEST-V2-G3 | Fernanda (07/06) — instance_key mismatch → source='orphan' | `test_lead_in_group_decision.py::test_orphan_instance_skips_probe` already covers; new case-named test is a labelled alias |
| TEST-V2-G4 | Valquiria (06/06) — job discarded by max_age_seconds=600 | `test_probe_retry.py::test_max_age_guard_expired` already covers; new case-named test is a labelled alias with 47h scenario |
| TEST-V2-G5 | 553891500357 (09/06) — stub test created but skipped in CI (blocked-pending-data) | pytest.mark.skip with reason message; no production assertions until user provides trace |
| DOC-V2-G1 | New memory `grupo_membership_arquitetura.md` + session memory in user's memory dir | Write memory file documenting webhook-first inversion, the 3 paths, retry chain, LEAVE handler |
| DOC-V2-G2 | Update `agente_referencia_compilada.md` with tabla + lead_in_group() + retry + FSM audit | Append new sections to existing reference doc |
| OBS-V2-G1 | Structured logs [MEMB-WRITE], [MEMB-LOOKUP], [PROBE-RETRY], [GRUPO-STATE-CHANGE] | All four families ALREADY PRESENT in source — verified by grep. [GRUPO-STATE-CHANGE] criterion satisfied by GSC: prefix (documented design decision). OBS-V2-G1 is DONE; task = verify + document |
| OBS-V2-G2 | Endpoint `/health/grupo-membership` returns {total_rows, last_write_at, cache_size, cache_hit_rate, writes_per_source} | PARTIAL — existing endpoint at `/admin/grupo-membership/health` returns total_rows + last_write_at + writes_by_source_24h + cache_stats (no hit_rate). Gap: add computed `cache_hit_rate` field + explicit 24h windowing for total_rows. Path discrepancy: criterion names `/health/...` but live endpoint is `/admin/...`; extend existing, document discrepancy |
</phase_requirements>

---

## Existing Coverage Map

The key planning input: which existing tests already lock each case mechanism, so `test_v2_regression.py` adds case-named assertions without duplicating logic.

| Case | Person | Mechanism Locked | Existing Test File | Existing Test Name | New test in test_v2_regression.py |
|------|--------|-----------------|-------------------|-------------------|------------------------------------|
| TEST-V2-G1 | Ana Carla 08/06 | Path 3 `createGroup` direct write → `upsert_grupo_membership(fonte='create_group')` → `lead_in_group` returns `source='membership'` without probe | `test_lead_in_group_decision.py` | `test_membership_hit_returns_without_probe` | `test_v2_g1_ana_carla_path3_create_group` |
| TEST-V2-G1 (write path) | Ana Carla 08/06 | `upsert_grupo_membership` called from `leads.py` Path 3 on createGroup response | `test_grupo_membership_upsert.py` | `test_upsert_basico_insert` | (covered by above) |
| TEST-V2-G2 | Rosania 08/06 | Probe negative at T=0 → `schedule_probe_retry` enqueued → job at T+138s finds `_query_membership_row` returns row → TABLE_HIT → no DM fallback | `test_probe_retry.py` | `test_rosania_sequence`, `test_table_hit_skips_probe` | `test_v2_g2_rosania_table_hit_at_138s` |
| TEST-V2-G3 | Fernanda 07/06 | `_query_membership_row` returns row with old `instance_key` != current → `lead_in_group` returns `source='orphan', in_group=False` | `test_lead_in_group_decision.py` | `test_orphan_instance_skips_probe` | `test_v2_g3_fernanda_orphan_instance_key` |
| TEST-V2-G4 | Valquiria 06/06 | `_probe_retry_job` called with `enqueued_at` 47h ago → `age_sec > max_age_seconds=600` → job discarded, no probe call | `test_probe_retry.py` | `test_max_age_guard_expired` | `test_v2_g4_valquiria_max_age_discard` |
| TEST-V2-G5 | 553891500357 09/06 | Unknown — trace not yet available from user | None | — | `test_v2_g5_lead_553891500357` (skipped) |

**Planning implication:** `test_v2_regression.py` contains 5 case-named tests, each with a docstring explaining the real-world scenario. Tests G1-G4 are thin wrappers that call the same mock stubs already proven in the existing files (to avoid import duplication). They can import and call the existing mock factories OR copy the minimal setup inline. Inline is simpler since the test count is small.

---

## Standard Stack

### Core (already installed — no new dependencies for Phase 14)

| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| pytest | installed | Test runner | [VERIFIED: venv — 108 tests collected] |
| pytest-asyncio | installed | async test support | [VERIFIED: `@pytest.mark.asyncio` used throughout] |
| unittest.mock | stdlib | Mock/patch | [VERIFIED: used in all test files] |
| cachetools | >=5.5.0 | probe_cache TTLCache (already installed Phase 10) | [VERIFIED: probe_cache.py imports TTLCache] |

### No new dependencies

Phase 14 adds only test files and endpoint modifications. No new `pip install` required. The existing conftest.py stubs for `app.services.evolution` and the `sys.modules` injection patterns for `app.scheduler` / `app.db.client` from `test_probe_retry.py` are the patterns to reuse.

---

## Architecture Patterns

### Existing test infrastructure (reuse verbatim)

**conftest.py stub pattern** — evolution module injected before any test:

```python
# conftest.py already handles:
# sys.modules["app.services.evolution"] = stub
# stub.verificar_lead_no_grupo = async def returning {"ok": True, "in_group": False}
```

**Autouse reset fixture** (from `test_lead_in_group_decision.py` and `test_probe_retry.py`):

```python
@pytest.fixture(autouse=True)
def reset_state():
    from app.services import probe_cache
    from app.services import grupo_membership as gm
    probe_cache.clear_all()
    gm._reset_probe_locks_for_tests()
    yield
    probe_cache.clear_all()
    gm._reset_probe_locks_for_tests()
```

**APScheduler stub** (from `test_probe_retry.py` module-level):

```python
import sys
from types import ModuleType
from unittest.mock import MagicMock

# app.scheduler stub (APScheduler not installed in test venv)
_sched_stub = ModuleType("app.scheduler")
_sched_stub.scheduler = MagicMock()
sys.modules.setdefault("app.scheduler", _sched_stub)

# app.db.client stub (supabase-py API mismatch in test venv)
_db_stub = ModuleType("app.db.client")
_db_stub.get_supabase = MagicMock(return_value=MagicMock())
sys.modules.setdefault("app.db.client", _db_stub)
```

**Source-code inspection pattern** (from `test_probe_retry.py` PROBE-RETRY-02 tests):

```python
import pathlib
src = pathlib.Path(__file__).resolve().parent.parent / "app" / "routers" / "confirmacao_agendamento.py"
content = src.read_text(encoding="utf-8")
assert "schedule_retry_on_negative=True" in content
```

This pattern is the preferred approach when testing "does this caller activate retry" — avoids importing heavy transitive deps.

### Pattern for test_v2_regression.py

Each regression test follows the same 4-step pattern:

1. **Setup** — mock supabase row (or no row) + mock probe result
2. **Exercise** — call `lead_in_group()` or `_probe_retry_job()` (the async function under test)
3. **Assert** — assert `result['source']` and `result['in_group']` match the case's expected behavior
4. **Case comment** — docstring names the real person + date + scenario

For TEST-V2-G5: use `@pytest.mark.skip(reason="blocked-pending-data: requires full webhook trace for lead 553891500357 — provide incident timestamps + payloads to unlock")`.

### Project structure for Phase 14 artifacts

```
leadflow-backend/
  tests/
    test_v2_regression.py    # new: 5 case-named tests (4 pass, 1 skip)

app/routers/
  admin.py                   # extend grupo_membership_health() with cache_hit_rate

app/main.py                  # BUILD_VERSION bump

~/.claude/projects/.../memory/
  grupo_membership_arquitetura.md   # new: DOC-V2-G1
  agente_referencia_compilada.md    # update: DOC-V2-G2 (append sections)
```

---

## Healthcheck Endpoint: Gap Analysis (OBS-V2-G2)

### Current endpoint state (verified in session)

**Path:** `GET /admin/grupo-membership/health` (NOT `/health/grupo-membership`)
**Auth:** No gate (same as other `/admin/grupo/*` endpoints)
**Location:** `app/routers/admin.py` line 1180

**Current response shape (Phase 11 state):**

```json
{
  "total_rows": 0,
  "last_write_at": null,
  "writes_by_source_24h": {"webhook_add": 3, "create_group": 1},
  "cache_stats": {
    "hits": 0, "misses": 0, "writes": 0, "invalidations": 0,
    "size": 0, "maxsize": 512, "ttl_seconds": 300
  },
  "lookup_stats": {
    "lock_dict_size": 0
  },
  "phase": "11-consumer"
}
```

### OBS-V2-G2 required fields

| Field in requirement | Current state | Action |
|---------------------|---------------|--------|
| `total_rows` (all-time) | `total_rows` — all-time count | EXISTS — rename to `total_rows_all_time` OR keep as is and add `total_rows_24h` |
| `last_write_at` | `last_write_at` — ISO string of most recent `atualizado_em` | EXISTS |
| `cache_size` | `cache_stats.size` | EXISTS under `cache_stats` |
| `cache_hit_rate` | MISSING — derivable from `cache_stats.hits / (hits + misses)` | ADD as top-level computed field |
| `writes_per_source` | `writes_by_source_24h` — map of fonte → count last 24h | EXISTS, rename to `writes_per_source` OR alias |

**Minimum changes to close OBS-V2-G2:**

1. Add `cache_hit_rate: float` computed as `hits / (hits + misses)` if `(hits + misses) > 0` else `null`
2. Add `total_rows_24h: int` counting rows where `criado_em >= NOW()-24h` (separate query from all-time `total_rows`)
3. Update `phase` field to `"14-observability"`

**Path discrepancy resolution:** The requirement criterion says `/health/grupo-membership` but the live endpoint is `/admin/grupo-membership/health`. Recommendation: extend the existing `/admin/grupo-membership/health` endpoint (do not create a new route). Add a comment in the code documenting the path discrepancy. The planner should note this in the PLAN.md so the verifier tests the correct path.

---

## Structured Logs: OBS-V2-G1 Audit

All four log marker families required by OBS-V2-G1 are already present in production code. Verified by grep in this session:

| Criterion Marker | Actual Prefix Used | Location | Lines (examples) |
|-----------------|--------------------|----------|-----------------|
| `[MEMB-WRITE]` | `[MEMB-WRITE]` | `grupo_membership.py` | 397, 413, 424, 430, 478, 482 |
| `[MEMB-LOOKUP]` | `[MEMB-LOOKUP]` | `grupo_membership.py` | 129, 198, 264, 311, 341 |
| `[PROBE-RETRY]` | `[PROBE-RETRY]` | `grupo_membership.py` | 584, 618, 621, 650, 674, 690, 695, 703, 714 |
| `[GRUPO-STATE-CHANGE]` | `GSC:` (audit marker in `conversas`) | `grupo_state.py` | 94-101 |

**Important design note on `[GRUPO-STATE-CHANGE]`:** The requirement criterion uses `[GRUPO-STATE-CHANGE]` as the label, but Phase 13 deliberately used the prefix `GSC:` in the `conversas` table content to avoid collision with `get_grupo_state`'s `.like("GRUPO_STATE:%")` parser. The intent is satisfied: every FSM transition writes a structured `GSC:{ag_id}:{from}:{to}:{reason}:{caller}` marker to `conversas`. This is the audit trail for "grupo state change" events. **OBS-V2-G1 is DONE as implemented.** The planner task for this requirement is: verify markers exist in source + add one sentence to the Phase 14 summary documenting the naming resolution.

Additional log prefixes present (not in criteria, bonus observability):
- `[PROBE-RETRY-RECOVERY]` — startup recovery logs
- `[MEMB-WRITE-PATH2-LID]`, `[MEMB-WRITE-PATH2-TEL]`, `[MEMB-WRITE-PATH3]` — per-path write logs in `agente.py` and `leads.py`
- `[GRUPO-STATE]` — invalid state guard in `grupo_state.py`
- `[MEMB-INSTANCE-KEY]` — instance key lookup error

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| cache_hit_rate calculation | Custom stats tracking | Derive from existing `probe_cache.stats()` dict: `hits / (hits + misses)` |
| Test isolation between test runs | Module-level singleton state bugs | Reuse existing `reset_state` autouse fixture from `test_lead_in_group_decision.py` |
| Mocking APScheduler | pip-installing apscheduler in test venv | Reuse `sys.modules` stub injection from `test_probe_retry.py` (already working) |
| test_v2_g5 stubbed behavior | Writing fake assertions for unknown behavior | `pytest.mark.skip(reason="blocked-pending-data: ...")` with descriptive reason |

---

## Common Pitfalls

### Pitfall 1: Duplicating test logic instead of referencing it

**What goes wrong:** Writing `test_v2_regression.py` that re-implements the full mock setup already in `test_probe_retry.py` or `test_lead_in_group_decision.py`, making maintenance burden x2.
**How to avoid:** Each regression test should be a thin case-narrative wrapper. The mock setup is minimal inline (3-4 lines of `MagicMock()` setup). The heavy APScheduler + supabase stub injection is needed because `schedule_probe_retry` is called transitively — copy the module-level stub pattern from `test_probe_retry.py` at the top of `test_v2_regression.py`.
**Warning signs:** If `test_v2_regression.py` grows beyond ~150 lines, it's duplicating logic.

### Pitfall 2: Wrong import path for verificar_lead_no_grupo

**What goes wrong:** Patching `'app.services.grupo_membership.verificar_lead_no_grupo'` instead of `'app.services.evolution.verificar_lead_no_grupo'`.
**Why it happens:** `lead_in_group()` uses a LOCAL import (`from app.services.evolution import ...`), so the patch target is the evolution module, not grupo_membership. This is documented in `test_lead_in_group_decision.py` line 13-16.
**How to avoid:** Always patch `'app.services.evolution.verificar_lead_no_grupo'` (or use `monkeypatch.setattr` on the evolution stub already injected by conftest).

### Pitfall 3: Testing /health/... path that doesn't exist

**What goes wrong:** The success criterion says `/health/grupo-membership` but the endpoint is `/admin/grupo-membership/health`. A smoke test or verification step that hits `/health/grupo-membership` will get 404.
**How to avoid:** All tests and verification steps use `/admin/grupo-membership/health`. Document the path discrepancy in a comment in admin.py.

### Pitfall 4: cache_hit_rate division by zero

**What goes wrong:** `hits / (hits + misses)` raises `ZeroDivisionError` on fresh deploy when no lookups have occurred.
**How to avoid:** Guard: `rate = round(hits / (hits + misses), 3) if (hits + misses) > 0 else None`. Emit `null` when no data, not 0.0 (0.0 would be misleading — it suggests all misses, not "no data yet").

### Pitfall 5: BUILD_VERSION not bumped after Phase 13

**What goes wrong:** Phase 13 shipped (commits e449d9d, f02b72d, 6b814a9) without bumping BUILD_VERSION. Current value is still `"2026-06-09-lead-in-group-consumer"` (Phase 11 value). Phases 12 and 13 are deployed but not verifiable via `/version`.
**How to avoid:** Phase 14 MUST include a BUILD_VERSION bump as an early task. Recommended value: `"2026-06-10-v2-2-completo"` or `"2026-06-10-webhook-first-completo"`.

### Pitfall 6: test_v2_g5 actually asserting behavior

**What goes wrong:** Writing `test_v2_g5` with placeholder assertions (`assert True`) instead of a proper skip, which makes it pass without actually validating anything and silently drops the tracking signal.
**How to avoid:** Use `@pytest.mark.skip` with an explicit reason string. The skip is intentional and visible in CI output. The stub test exists to be found and un-skipped when the user provides the trace.

### Pitfall 7: DOC artifacts in wrong location

**What goes wrong:** Writing memory files to the project directory instead of the user's memory directory (`~/.claude/projects/c--Projetos-Leadflow/memory/`).
**How to avoid:** The memory skill or equivalent Write tool call should target the absolute path of the memory directory, not `.planning/`. Confirm the path before writing.

---

## Code Examples

### test_v2_regression.py skeleton

```python
# Source: derived from test_lead_in_group_decision.py + test_probe_retry.py patterns [VERIFIED this session]
import sys
from types import ModuleType
from unittest.mock import MagicMock
from datetime import datetime, timedelta
import pytest

# ── Module-level stubs (APScheduler + supabase absent in test venv) ──
_sched_stub = ModuleType("app.scheduler")
_sched_stub.scheduler = MagicMock()
sys.modules.setdefault("app.scheduler", _sched_stub)

_db_stub = ModuleType("app.db.client")
_db_stub.get_supabase = MagicMock(return_value=MagicMock())
sys.modules.setdefault("app.db.client", _db_stub)

@pytest.fixture(autouse=True)
def reset_state():
    from app.services import probe_cache
    from app.services import grupo_membership as gm
    probe_cache.clear_all()
    gm._reset_probe_locks_for_tests()
    yield
    probe_cache.clear_all()
    gm._reset_probe_locks_for_tests()


@pytest.mark.asyncio
async def test_v2_g1_ana_carla_path3_create_group(monkeypatch):
    """TEST-V2-G1: Ana Carla 08/06 — createGroup direct write (Path 3).

    When _criar_grupo_agendamento calls upsert_grupo_membership(fonte='create_group'),
    subsequent lead_in_group() returns source='membership' WITHOUT calling probe.
    FSM can advance to ATIVO in <60s.
    """
    from app.services.grupo_membership import lead_in_group
    from app.services import probe_cache

    probe_called = {'count': 0}
    async def fake_probe(*args, **kwargs):
        probe_called['count'] += 1
        return {'ok': True, 'in_group': False, 'erro': ''}

    monkeypatch.setattr('app.services.evolution.verificar_lead_no_grupo', fake_probe)

    # Simulate: Path 3 already wrote a row (entrou_em = now, instance match)
    row = {
        'entrou_em': datetime.utcnow().isoformat(),
        'saiu_em': None,
        'instance_key': 'test-instance',
        'atualizado_em': datetime.utcnow().isoformat(),
        'telefone': '5514998151089',
        'lid': None,
    }
    monkeypatch.setattr('app.services.grupo_membership._query_membership_row',
                        lambda *a, **kw: row)
    monkeypatch.setattr('app.services.grupo_membership.get_instance_key',
                        lambda sb, eid: 'test-instance')

    result = await lead_in_group(
        sb=MagicMock(), empresa_id='emp-test',
        telefone='5514998151089', grupo_jid='120363test@g.us',
        evo_url='http://evo', evo_key='key', evo_inst='inst',
    )

    assert result['in_group'] is True
    assert result['source'] == 'membership'
    assert probe_called['count'] == 0, "Path 3 row present — probe must NOT be called"


@pytest.mark.asyncio
async def test_v2_g2_rosania_table_hit_at_138s(monkeypatch):
    """TEST-V2-G2: Rosania 08/06 — webhook ADD chegou T+138s.

    Probe at T=0 returns False → schedule_probe_retry enqueued (max_age=600s).
    At T+138s, _probe_retry_job finds row in table (webhook already wrote it)
    → TABLE_HIT → probe NOT called → lead considered in group.
    """
    from app.services.grupo_membership import _probe_retry_job

    probe_called = {'count': 0}
    async def fake_probe(*args, **kwargs):
        probe_called['count'] += 1
        return {'ok': True, 'in_group': True, 'erro': ''}

    monkeypatch.setattr('app.services.evolution.verificar_lead_no_grupo', fake_probe)

    # Table already has row at T+138s (webhook wrote it)
    row = {
        'entrou_em': datetime.utcnow().isoformat(),
        'saiu_em': None,
        'instance_key': 'inst',
        'atualizado_em': datetime.utcnow().isoformat(),
    }
    monkeypatch.setattr('app.services.grupo_membership._query_membership_row',
                        lambda *a, **kw: row)

    await _probe_retry_job(
        empresa_id='emp-test', grupo_jid='120363test@g.us',
        telefone='5562984551622', lid='',
        attempts_left=2, max_age_seconds=600,
        enqueued_at=datetime.utcnow() - timedelta(seconds=138),  # T+138s
        evo_url='http://evo', evo_key='key', evo_inst='inst',
    )

    assert probe_called['count'] == 0, "TABLE_HIT: probe must not be called (Rosania case)"


@pytest.mark.asyncio
async def test_v2_g3_fernanda_orphan_instance_key(monkeypatch):
    """TEST-V2-G3: Fernanda 07/06 — grupo orfao de instancia antiga (bia-rejane).

    Row in grupo_membership has instance_key='bia-rejane' (old).
    Current empresa instance is 'rejane-leal-mentora' (new).
    lead_in_group returns source='orphan', in_group=False, probe NOT called.
    Caller creates a new group.
    """
    from app.services.grupo_membership import lead_in_group

    probe_called = {'count': 0}
    async def fake_probe(*args, **kwargs):
        probe_called['count'] += 1
        return {'ok': True, 'in_group': True, 'erro': ''}

    monkeypatch.setattr('app.services.evolution.verificar_lead_no_grupo', fake_probe)

    old_row = {
        'entrou_em': (datetime.utcnow() - timedelta(days=5)).isoformat(),
        'saiu_em': None,
        'instance_key': 'bia-rejane',      # OLD instance
        'atualizado_em': (datetime.utcnow() - timedelta(days=5)).isoformat(),
        'telefone': '5551999532715',
        'lid': None,
    }
    monkeypatch.setattr('app.services.grupo_membership._query_membership_row',
                        lambda *a, **kw: old_row)
    monkeypatch.setattr('app.services.grupo_membership.get_instance_key',
                        lambda sb, eid: 'rejane-leal-mentora')  # NEW instance

    result = await lead_in_group(
        sb=MagicMock(), empresa_id='emp-test',
        telefone='5551999532715', grupo_jid='120363test@g.us',
        evo_url='http://evo', evo_key='key', evo_inst='inst',
    )

    assert result['in_group'] is False
    assert result['source'] == 'orphan'
    assert result['instance_key_match'] is False
    assert probe_called['count'] == 0, "Orphan instance: probe must NOT be called"


def test_v2_g4_valquiria_max_age_discard(monkeypatch):
    """TEST-V2-G4: Valquiria 06/06 — aquec recovery job 47h after enqueue.

    _probe_retry_job called with enqueued_at = 47h ago, max_age_seconds=600.
    Job must be discarded immediately (no probe, no reschedule).
    """
    # Covered by test_probe_retry.py::test_max_age_guard_expired.
    # This test is the case-named alias with explicit 47h scenario.
    from app.services.grupo_membership import _probe_retry_job
    import asyncio

    probe_called = {'count': 0}

    async def run():
        monkeypatch.setattr('app.services.grupo_membership._query_membership_row',
                            lambda *a, **kw: None)
        async def fake_probe(*args, **kwargs):
            probe_called['count'] += 1
            return {'ok': True, 'in_group': True}
        monkeypatch.setattr('app.services.evolution.verificar_lead_no_grupo', fake_probe)

        await _probe_retry_job(
            empresa_id='emp-test', grupo_jid='120363test@g.us',
            telefone='5582981291203', lid='',
            attempts_left=2, max_age_seconds=600,
            enqueued_at=datetime.utcnow() - timedelta(hours=47),  # Valquiria: 47h late
            evo_url='http://evo', evo_key='key', evo_inst='inst',
        )

    asyncio.get_event_loop().run_until_complete(run())
    assert probe_called['count'] == 0, "Max age expired: probe must NOT be called (Valquiria case)"


@pytest.mark.skip(reason=(
    "blocked-pending-data: requires full webhook trace for lead 553891500357 "
    "(09/06 incident). Provide timestamps + webhook payloads + conversas log "
    "to unlock this test. See REQUIREMENTS.md TEST-V2-G5."
))
def test_v2_g5_lead_553891500357():
    """TEST-V2-G5: Lead 553891500357 09/06 — persists after 6 palliative fixes.

    Stub test. Will be implemented once user provides full incident trace.
    Expected mechanism: TBD after trace analysis.
    """
    pass
```

### cache_hit_rate extension for admin.py

```python
# Source: probe_cache.stats() returns hits + misses [VERIFIED this session]
# Add after: out["cache_stats"] = probe_cache.stats()

cs = probe_cache.stats()
total_lookups = cs.get('hits', 0) + cs.get('misses', 0)
out["cache_hit_rate"] = (
    round(cs['hits'] / total_lookups, 3) if total_lookups > 0 else None
)
```

### total_rows_24h addition for admin.py

```python
# Add a second count query scoped to last 24h
try:
    cutoff_24h = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    cnt_24h = (
        sb.table("grupo_membership")
        .select("id", count="exact")
        .gte("criado_em", cutoff_24h)
        .limit(1)
        .execute()
    )
    out["total_rows_24h"] = getattr(cnt_24h, "count", None) or 0
except Exception as e:
    out["total_rows_24h_erro"] = str(e)
```

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (installed in venv) + pytest-asyncio |
| Config file | none (auto-discovery) |
| Quick run command | `pytest tests/test_v2_regression.py -v` |
| Full suite command | `pytest tests/ -q --ignore=tests/test_calendar_buffer.py --ignore=tests/test_verificar_lead_no_grupo_phase3.py` |
| Current baseline | 108 passed (verified this session) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | Status |
|--------|----------|-----------|-------------------|--------|
| TEST-V2-G1 | Path 3 row → source=membership, no probe | async unit | `pytest tests/test_v2_regression.py::test_v2_g1_ana_carla_path3_create_group -x` | Wave 0 (new file) |
| TEST-V2-G2 | TABLE_HIT at T+138s skips probe | async unit | `pytest tests/test_v2_regression.py::test_v2_g2_rosania_table_hit_at_138s -x` | Wave 0 (new file) |
| TEST-V2-G3 | instance_key mismatch → orphan | async unit | `pytest tests/test_v2_regression.py::test_v2_g3_fernanda_orphan_instance_key -x` | Wave 0 (new file) |
| TEST-V2-G4 | max_age 47h → discard | sync unit | `pytest tests/test_v2_regression.py::test_v2_g4_valquiria_max_age_discard -x` | Wave 0 (new file) |
| TEST-V2-G5 | blocked-pending-data stub | pytest.mark.skip | `pytest tests/test_v2_regression.py::test_v2_g5_lead_553891500357 -v` | Wave 0 (new file, skipped) |
| OBS-V2-G1 | Verify log markers present in source | static grep | `grep -r "\[MEMB-WRITE\]\|\[PROBE-RETRY\]" app/` | DONE — no new code |
| OBS-V2-G2 | cache_hit_rate field returned | endpoint extension | `pytest` source-inspection of admin.py | Wave 1 (admin.py edit) |

### Sampling Rate

- **Per task commit:** `pytest tests/test_v2_regression.py -v`
- **Per wave merge:** `pytest tests/ -q --ignore=tests/test_calendar_buffer.py --ignore=tests/test_verificar_lead_no_grupo_phase3.py`
- **Phase gate:** Full suite green (target: 113 passed = 108 + 4 new passing + 1 skipped, 0 failures)

### Wave 0 Gaps

- [ ] `tests/test_v2_regression.py` — covers TEST-V2-G1..G5 (4 pass + 1 skip)

*(All other test infrastructure already exists. conftest.py stubs, autouse reset fixture, APScheduler/supabase stubs — all in place. No new conftest changes needed.)*

---

## Runtime State Inventory

Phase 14 is purely additive (tests + endpoint extension + docs). No renames, migrations, or runtime state changes.

- Stored data: None — no schema changes
- Live service config: None
- OS-registered state: None
- Secrets/env vars: None
- Build artifacts: None — verified by scope

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pytest | test runner | Yes | confirmed (108 tests run) | — |
| pytest-asyncio | async tests | Yes | confirmed (existing async tests pass) | — |
| cachetools | probe_cache | Yes | installed Phase 10 | — |
| app.scheduler (APScheduler) | test stub | Not in venv | — | sys.modules stub (already working in test_probe_retry.py) |
| supabase-py | test stub | Mismatched API in venv | — | sys.modules stub + MagicMock (already working) |

**No blocking missing dependencies.** The two absent libs (APScheduler, supabase-py) are already handled by the existing stub injection pattern.

---

## Security Domain

Phase 14 adds no new endpoints, auth paths, or network surface. The only endpoint change is extending an existing internal admin endpoint with a computed field. The existing auth-less pattern (`/admin/grupo-membership/health` has no `X-Admin-Key` gate — noted in the Phase 10 comment as intentional, same as other `/admin/grupo/*` endpoints) is unchanged.

No ASVS categories applicable beyond what Phases 10-13 already addressed.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| probe Evolution as fonte primaria (v2.1) | Webhook-first: tabela `grupo_membership` primaria, probe = fallback | Phase 10-11 (09/06) | Fases 14 regression tests validate the new primary path |
| No audit trail for FSM transitions | GSC: markers in conversas (monotonic guard + audit) | Phase 13 (10/06) | Timeline endpoint exposes them; regression tests can check markers |
| BUILD_VERSION at "2026-06-09-lead-in-group-consumer" (Phase 11) | Phases 12+13 deployed without bump | Phases 12-13 did not bump | Phase 14 MUST bump to make v2.2 verifiable via /version |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | test_v2_g4 using `asyncio.get_event_loop().run_until_complete()` works in pytest env | Code Examples | May need `@pytest.mark.asyncio` + `async def`; adjust if event loop policy differs |
| A2 | DOC memory files live at `~/.claude/projects/c--Projetos-Leadflow/memory/` | Architecture Patterns | Planner should confirm path before writing |

**All other claims in this research were verified against actual source files in this session.**

---

## Open Questions

1. **OBS-V2-G2 path discrepancy resolution**
   - What we know: Endpoint is `/admin/grupo-membership/health`; criterion says `/health/grupo-membership`
   - What's unclear: Whether the verifier (`/gsd-verify-work`) will check the criterion literally or accept the existing path
   - Recommendation: Extend existing endpoint + add a redirect or alias `/health/grupo-membership` → `/admin/grupo-membership/health` if the verifier checks the criterion path literally. Alternatively, document in PLAN.md that the criterion path is satisfied by the existing endpoint.

2. **DOC-V2-G2 scope: full rewrite vs append**
   - What we know: `agente_referencia_compilada.md` is an existing memory file that serves as the agent technical manual
   - What's unclear: Whether appending new sections (tabela grupo_membership, lead_in_group(), retry async, FSM audit) is sufficient or if the whole file needs restructuring
   - Recommendation: Append new sections only. The existing file is described as the "consultar ANTES de mexer" reference — avoid breaking existing content.

---

## Sources

### Primary (HIGH confidence)
- `leadflow-backend/app/services/grupo_membership.py` — log markers, lead_in_group() decision tree, upsert_grupo_membership, schedule_probe_retry [VERIFIED this session]
- `leadflow-backend/app/routers/admin.py` lines 1171-1262 — existing healthcheck endpoint shape [VERIFIED this session]
- `leadflow-backend/app/services/probe_cache.py` — stats() return shape [VERIFIED this session]
- `leadflow-backend/tests/` directory listing — 13 test files, 108 collectible tests [VERIFIED this session]
- `leadflow-backend/app/main.py` line 248 — current BUILD_VERSION [VERIFIED this session]
- `leadflow-backend/app/services/grupo_state.py` lines 94-101 — GSC: prefix [VERIFIED this session]

### Secondary (MEDIUM confidence)
- `.planning/phases/10-*/10-05-SUMMARY.md` — Phase 10 endpoint shape, what was built
- `.planning/phases/11-*/11-04-SUMMARY.md` — Phase 11 healthcheck extension (lookup_stats added)
- `.planning/phases/12-*/12-03-SUMMARY.md` — Phase 12 test suite details (57 tests passing post-Phase 12)
- `.planning/phases/13-*/13-04-SUMMARY.md` — Phase 13 test suite details (108 tests passing post-Phase 13)
- `.planning/REQUIREMENTS.md` — OBS-V2-G1/G2 requirement text [VERIFIED this session]

---

## Metadata

**Confidence breakdown:**

- Regression tests (TEST-V2-G1..G4): HIGH — existing test files verified; stubs confirmed working; decision tree in source confirmed
- TEST-V2-G5 stub: HIGH — `pytest.mark.skip` pattern is standard; content TBD by design
- Healthcheck gap analysis (OBS-V2-G2): HIGH — response shape read directly from admin.py source
- Log markers (OBS-V2-G1): HIGH — grep across entire app/ directory in this session
- DOC artifacts (DOC-V2-G1/G2): MEDIUM — location and format are conventional; specific content derived from knowledge of what was built in Phases 10-13

**Research date:** 2026-06-10
**Valid until:** 2026-07-10 (30 days — stable codebase, no fast-moving external deps)
