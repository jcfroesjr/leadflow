---
phase: 11-lead-in-group-consumer-migrar-fallback-callers-coalescing-async
plan: 02
subsystem: api
tags: [grupo_membership, grupo_fallback, lead_in_group, migration, webhook-first]

# Dependency graph
requires:
  - phase: 11-lead-in-group-consumer-migrar-fallback-callers-coalescing-async
    plan: 01
    provides: lead_in_group() async consumer (decision tree cache->membership->orphan->probe)
provides:
  - grupo_fallback.py with 7 mechanical substitutions (verificar_lead_no_grupo -> lead_in_group)
  - orphan/Fernanda case handled in all 6 logical blocks
  - PROBE-BYPASS-01 (GRUPO_LEAD_ENTROU_CRIACAO marker) preserved literally
affects: [11-03 pytest suite, prod grupo fallback behavior]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Explicit kwargs (sb=, empresa_id=, telefone=, grupo_jid=, lid=, evo_url=, evo_key=, evo_inst=) on all lead_in_group calls — Pitfall 2 avoidance"
    - "source='orphan' sentinel treated as not-in-group-current in all 6 blocks (caso Fernanda)"
    - "Polling preserves local variable convention (emp_id/tel vs empresa_id/telefone)"

key-files:
  created: []
  modified:
    - leadflow-backend/app/services/grupo_fallback.py

key-decisions:
  - "Local imports of verificar_lead_no_grupo inside functions REMOVED (Tasks 2+3) — lead_in_group already imported at module top"
  - "Polling callsites use cfg dict keys as evo_url=/evo_key=/evo_inst= kwargs — no rename of cfg variable itself"
  - "Orphan in polling branches: does NOT promote ATIVO — leaves state for Phase 13 LEAVE handler to clean"
  - "Block 2 (informativo) remains purely informative — ALWAYS activates Phase 7, lead_in_group result only logged"
  - "PROBE-BYPASS-01 unchanged literally — lead_in_group called only if bypass did not fire return False"

requirements-completed: [MEMB-05]

# Metrics
duration: ~25min
completed: 2026-06-09
---

# Phase 11 / Plan 02: Migrate grupo_fallback.py Callers to lead_in_group() Summary

**7 mechanical substitutions of `verificar_lead_no_grupo` -> `lead_in_group()` across 6 logical blocks in `grupo_fallback.py`. PROBE-BYPASS-01 marker bypass preserved literally. `source='orphan'` (caso Fernanda, instance_key mismatch) handled in all blocks. Zero HTTP Evolution calls when grupo_membership row exists.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-06-09
- **Tasks:** 4/4 (Task 4 is validation-only)
- **Files modified:** 1 (`app/services/grupo_fallback.py`, +107 lines, 3 commits)

## Accomplishments

- **Task 1** (commit 80e37a5): Import `from app.services.grupo_membership import lead_in_group` added after evolution import block. Blocks 1b/1c/2 in `ativar_fallback_se_necessario` migrated. PROBE-BYPASS-01 (GRUPO_LEAD_ENTROU_CRIACAO marker < 5min) preserved literally — bypass fires BEFORE `lead_in_group` call. Orphan sentinel added in blocks 1b and 1c.
- **Task 2** (commit 135e825): Callsites in `_disparar_convite_lead_se_aguardando` (line ~477) and `_disparar_alerta_grupo_se_aguardando` (line ~624) migrated. Local `from app.services.evolution import verificar_lead_no_grupo` imports removed from both functions. ALERTA-GRUPO-01 skip print preserved at line ~697.
- **Task 3** (commit 65b9538): Polling callsites in `polling_grupos_aguardando` migrated — branch GRUPO_AGUARDANDO_ENTRADA (line ~1173) and branch FALLBACK_1_1 FIX 26/05 (line ~1256). Variable names `emp_id`/`tel` preserved per local loop convention. Orphan in polling = does NOT promote ATIVO.
- **Task 4** (validation-only): All acceptance criteria verified via Grep tool + AST parse + smoke import.

## Verification

- `await lead_in_group` = 7 (all 7 callsites migrated)
- `await verificar_lead_no_grupo` = 0 (all removed from grupo_fallback.py)
- Import at line 40: `from app.services.grupo_membership import lead_in_group` — match
- `verificar_lead_no_grupo,` at line 35 (preserved in evolution import block for other callers)
- PROBE-BYPASS-01: `GRUPO_LEAD_ENTROU_CRIACAO` = 3 matches; `bypass probe (NAO ativa)` = 1 match
- ALERTA-GRUPO-01: `skip envio alerta grupo (config 08/06` = 1 match at line ~697
- Markers preserved: `GRUPO_AGUARDANDO_ENTRADA` = 15, `CONVITE_1_1_ENVIADO` = 2, `LEAD_LID` >= 1
- `caso Fernanda` = 7 matches; `ORPHAN` = 6 matches; `instance_key_match` = 5 matches
- `FASE 11` comments = 7 (one per callsite)
- `_get_lead_lid_for_group` = 8 (every callsite has it)
- AST parse: OK
- `lead_in_group` smoke import: OK, is coroutinefunction=True
- No-regression: `git diff --stat` empty for evolution.py, grupo_state.py, admin.py, leads.py, confirmacao_agendamento.py

## Deviations from Plan

None — plan executed exactly as written. All 7 substitutions were mechanical as specified. The `warmup_grupo.py` diff check returned a `no such path` git error (file may not exist at the submodule's current tracked commit), but confirmed the file was not modified by this plan.

## Known Stubs

None — this plan contains no placeholder values or stubs. All `lead_in_group` calls are wired to the real consumer from Plan 11-01.

## Self-Check: PASSED

- File `leadflow-backend/app/services/grupo_fallback.py` exists and modified
- Commits 80e37a5, 135e825, 65b9538 exist in submodule git log
- `await lead_in_group` count == 7 (verified)
- `await verificar_lead_no_grupo` count == 0 (verified)
- PROBE-BYPASS-01 preserved (verified via grep)
- AST parse OK
