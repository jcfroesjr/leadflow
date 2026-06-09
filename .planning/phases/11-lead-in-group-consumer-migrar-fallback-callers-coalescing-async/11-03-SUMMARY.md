---
phase: 11-lead-in-group-consumer-migrar-fallback-callers-coalescing-async
plan: 03
subsystem: tests
tags: [pytest, asyncio, coalescing, grupo_membership, grupo_fallback, regression]

# Dependency graph
requires:
  - phase: 11-lead-in-group-consumer-migrar-fallback-callers-coalescing-async
    plan: 01
    provides: lead_in_group() async consumer + _reset_probe_locks_for_tests hook
  - phase: 11-lead-in-group-consumer-migrar-fallback-callers-coalescing-async
    plan: 02
    provides: grupo_fallback.py with 7 mechanical substitutions
provides:
  - 7 unit tests covering lead_in_group() decision tree (MEMB-05)
  - 3 integration tests covering probe coalescing (PROBE-COALESCE-01)
  - 9 CI grep tests validating Plan 11-02 migration regression-free
  - conftest.py with evolution stub (env workaround for Python 3.14 + broken idna)
affects: [CI, regression safety for Plans 11-01 and 11-02]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "conftest.py sys.modules stub para modules com import-time side effects (httpx->idna broken)"
    - "monkeypatch target deve ser o modulo FONTE quando import e local dentro da funcao"
    - "autouse fixture _reset_probe_locks_for_tests() para isolamento entre testes async"

key-files:
  created:
    - leadflow-backend/tests/test_lead_in_group_decision.py
    - leadflow-backend/tests/test_lead_in_group_coalesce.py
    - leadflow-backend/tests/test_grupo_fallback_migration.py
    - leadflow-backend/tests/conftest.py
  modified: []

key-decisions:
  - "monkeypatch target = app.services.evolution.verificar_lead_no_grupo (NAO grupo_membership) — funcao e importada localmente dentro de lead_in_group()"
  - "conftest.py injeta stub evolution em sys.modules + setattr em app.services para satisfazer resolucao de path do monkeypatch do pytest"
  - "test_calendar_buffer.py exclui da suite por falta de tzdata (Python 3.14 Windows, pre-existente)"
  - "test_verificar_lead_no_grupo_phase3.py falha por httpx->idna circular import (pre-existente, nao causado por Plan 11-03)"

requirements-completed: [MEMB-05, PROBE-COALESCE-01]

# Metrics
duration: ~45min
completed: 2026-06-09
---

# Phase 11 / Plan 03: Pytest Suite — Decision Tree + Coalescing + Migration Regression Summary

**Suite pytest de 19 testes cobrindo Plans 11-01 e 11-02: decision tree de `lead_in_group()` (7 unit), probe coalescing asyncio (3 integration), e guardrail CI grep para as 7 substituicoes mecanicas de `grupo_fallback.py` (9 testes) — mais `conftest.py` com stub de `evolution` para contornar broken httpx/idna no venv Python 3.14.**

## Performance

- **Duration:** ~45 min
- **Completed:** 2026-06-09
- **Tasks:** 4/4
- **Files created:** 4 (`test_lead_in_group_decision.py`, `test_lead_in_group_coalesce.py`, `test_grupo_fallback_migration.py`, `conftest.py`)

## Accomplishments

- **Task 1** (commit 810bd9a): `test_lead_in_group_decision.py` — 7 testes unit cobrindo cada branch da decision tree de `lead_in_group()`: cache fast-path, membership hit (instance match), orphan/Fernanda (mismatch sem probe), no-row probe fallback + cache set, DB error → unknown, sem creds → unknown, flag `allow_probe_fallback=False` → unknown. Autouse fixture reseta `probe_cache` + `_probe_locks` entre testes.

- **Task 2** (commit e72a4ec): `test_lead_in_group_coalesce.py` — 3 testes integration cobrindo PROBE-COALESCE-01: 3 jobs concorrentes mesma chave disparam 1 probe (double-checked locking; sources = `['cache', 'cache', 'probe']`), chaves diferentes rodam em paralelo (elapsed < 180ms para 2x100ms), mesma chave reusa mesmo objeto `asyncio.Lock`.

- **Task 3** (commit 5bd396c): `test_grupo_fallback_migration.py` — 9 CI grep tests validando Plan 11-02: exatamente 7 `await lead_in_group`, 0 `await verificar_lead_no_grupo`, import top-level presente, evolution import multi-line preservado, PROBE-BYPASS-01 preservado (marker + log), ALERTA-GRUPO-01 preservado, orphan handling >= 5 callsites, markers v2.1 intactos, kwargs explícitos `sb=sb` em 7 chamadas.

- **Task 4** (commit 5524636): Smoke run full suite. Diagnóstico: `verificar_lead_no_grupo` é importada LOCALMENTE dentro de `lead_in_group()`, logo monkeypatch precisa de `app.services.evolution` (módulo fonte), não `app.services.grupo_membership`. `httpx` falha por `idna` circular import no venv Python 3.14. Fix: `conftest.py` injeta stub de `evolution` em `sys.modules` + `setattr` no pacote `app.services` antes de qualquer test run. 46/52 pass (excluindo `test_calendar_buffer.py` e `test_verificar_lead_no_grupo_phase3.py` — ambos pre-existentes).

## Verification

- `test_lead_in_group_decision.py`: 7/7 PASS
- `test_lead_in_group_coalesce.py`: 3/3 PASS
- `test_grupo_fallback_migration.py`: 9/9 PASS
- Pre-existing suites: `test_probe_cache.py` 6/6 PASS, `test_grupo_membership_upsert.py` 6/6 PASS, `test_agente_fixes.py` 8/8 PASS, `test_qualificacao_lock_phase7.py` 7/7 PASS
- Total passing (excl. pre-existing env failures): **46/52**
- Suite runs in ~3s

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] monkeypatch target incorreto para local import**
- **Found during:** Task 4 (smoke run)
- **Issue:** `verificar_lead_no_grupo` é importada com `from app.services.evolution import verificar_lead_no_grupo` DENTRO do corpo de `lead_in_group()` (local import, não module-level). `monkeypatch.setattr('app.services.grupo_membership.verificar_lead_no_grupo', ...)` falha com `AttributeError` — o nome não existe no namespace do módulo.
- **Fix:** Target alterado para `app.services.evolution.verificar_lead_no_grupo` (o módulo onde o símbolo é definido).
- **Files modified:** `tests/test_lead_in_group_decision.py`, `tests/test_lead_in_group_coalesce.py`
- **Commit:** 5524636

**2. [Rule 3 - Blocking] httpx→idna circular import impedia import de app.services.evolution**
- **Found during:** Task 4 (smoke run)
- **Issue:** `httpx` (importado no topo de `evolution.py`) falha por bug circular import em `idna` no venv Python 3.14 deste projeto. Qualquer tentativa de `monkeypatch.setattr('app.services.evolution.*')` dispara o import e crasha.
- **Fix:** Adicionado `tests/conftest.py` que injeta stub leve de `app.services.evolution` em `sys.modules` + como atributo em `app.services` antes de qualquer test — previne o import real de `evolution.py`. Stub expõe `verificar_lead_no_grupo` como coroutine padrão; cada teste sobrescreve com `monkeypatch` conforme necessário.
- **Files created:** `tests/conftest.py`
- **Commit:** 5524636

## Pre-existing Environmental Failures (NOT caused by Plan 11-03)

| File | Failure | Cause |
|------|---------|-------|
| `test_calendar_buffer.py` | `ZoneInfoNotFoundError: America/Sao_Paulo` | `tzdata` não instalado no Python 3.14 venv Windows |
| `test_verificar_lead_no_grupo_phase3.py` | `ImportError: idna circular import` | Tentativa de `patch("httpx.AsyncClient")` — mesmo bug broken `idna`; não usa conftest stub pois patcha diretamente em `httpx` |

Ambas as falhas estavam presentes antes do Plan 11-03 — confirmado via `git log` (nenhum dos arquivos afetados foi modificado por este plan).

## Known Stubs

None — os testes não têm stubs que bloqueiem seus objetivos. O `conftest.py` stub de `evolution` é intencional e explícito; cada teste que precisa de comportamento específico sobrescreve via `monkeypatch`.

## Threat Flags

None — este plan cria apenas arquivos de teste. Não introduz novos endpoints, paths de auth, acesso a arquivos ou mudanças de schema.

## Self-Check: PASSED

- File `leadflow-backend/tests/test_lead_in_group_decision.py` exists — FOUND
- File `leadflow-backend/tests/test_lead_in_group_coalesce.py` exists — FOUND
- File `leadflow-backend/tests/test_grupo_fallback_migration.py` exists — FOUND
- File `leadflow-backend/tests/conftest.py` exists — FOUND
- Commits 810bd9a, e72a4ec, 5bd396c, 5524636 exist in submodule git log — FOUND
- 7 decision tests PASS — VERIFIED
- 3 coalesce tests PASS — VERIFIED
- 9 migration grep tests PASS — VERIFIED
- Pre-existing tests not regressed — VERIFIED (46 pass, 6 pre-existing failures unchanged)
