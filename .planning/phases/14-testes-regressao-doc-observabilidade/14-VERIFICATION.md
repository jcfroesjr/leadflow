---
phase: 14-testes-regressao-doc-observabilidade
verified: 2026-06-10T04:45:00Z
status: human_needed
score: 5/6 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Apply memory checklist from leadflow-backend/docs/grupo_membership_v2.md Section 8"
    expected: "Two memory files exist in ~/.claude/projects/c--Projetos-Leadflow/memory/: (1) sessao_2026-06-10_grupo_membership_v2.md (new) documenting the webhook-first inversion; (2) agente_referencia_compilada.md updated (APPEND) with grupo_membership table, lead_in_group() decision tree, retry async, and FSM audit"
    why_human: "Memory files live outside the repo (user/orchestrator space). The in-repo doc (leadflow-backend/docs/grupo_membership_v2.md Section 8) has an explicit unchecked checklist for these two items. Cannot be verified or written by the implementation subagent — requires orchestrator or user action."
---

# Phase 14: Testes Regressao + Doc + Observabilidade — Verification Report

**Phase Goal:** Block regression of the 5 motivating cases via pytest; consolidate docs; healthcheck detects cache-masking-persistence; structured logs in all new flows.
**Verified:** 2026-06-10T04:45:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | 4/4 regression cases pass (Ana Carla/Rosania/Fernanda/Valquiria) | VERIFIED | `test_v2_regression.py` lines 69-256: 4 async tests with probe_called count==0 assertions; SUMMARY confirms `5 passed, 1 skipped in 0.09s`; correct patch target `app.services.evolution.verificar_lead_no_grupo` confirmed in source |
| 2 | TEST-V2-G5 (553891500357) is `pytest.mark.skip` with `blocked-pending-data` reason | VERIFIED | Lines 263-275: `@pytest.mark.skip(reason="blocked-pending-data: requires full webhook trace for lead 553891500357 (09/06 incident)...")` — no `assert True` placeholder |
| 3 | In-repo doc covers webhook-first inversion + memory checklist | VERIFIED | `leadflow-backend/docs/grupo_membership_v2.md` (295 lines): 8 sections confirmed: inversion, 3 write paths, decision tree, retry async, LEAVE+FSM audit, observability, 5-case table, memory checklist. Checklist items are `[ ]` (intentionally undone — external files, human action required) |
| 4 | Healthcheck returns `cache_hit_rate` + `total_rows_24h` (existing fields preserved) | VERIFIED | `admin.py` line 1212: `"cache_hit_rate": round(_cs["hits"] / _total_lk, 3) if _total_lk > 0 else None`; line 1280: `out["total_rows_24h"]`; div0 guard confirmed (`_total_lk > 0`); all legacy fields present: `total_rows`, `last_write_at`, `writes_by_source_24h`, `cache_stats`, `lookup_stats`; `phase: "14-observability"` |
| 5 | Structured log markers `[MEMB-WRITE]`, `[MEMB-LOOKUP]`, `[PROBE-RETRY]`, `GSC:` present in source | VERIFIED | `grupo_membership.py`: 10+ occurrences of `[MEMB-WRITE]`, 5+ of `[MEMB-LOOKUP]`, 8+ of `[PROBE-RETRY]`; `grupo_state.py` line 101: `f"GSC:{agendamento_id}:{from_state}:{to_state}:{reason}:{caller}"`. Locked by `test_v2_obs_g1_log_markers_present` which reads source via pathlib |
| 6 | v2.1 13-test baseline + Phases 10-13 + 5 new = full suite green | VERIFIED | Gate confirmed in `grupo_membership_v2.md` Section 9: `113 passed, 1 skipped, 0 failed in 6.55s` (2026-06-10). Skip = G5 intentional. Ignores: only 2 named ENV-failure files (`test_calendar_buffer.py` tzdata, `test_verificar_lead_no_grupo_phase3.py` httpx/idna) — not logic regressions |
| 7 | Memory files `sessao_2026-06-XX_grupo_membership_v2.md` and updated `agente_referencia_compilada.md` exist | NEEDS HUMAN | `sessao_2026-06-10_grupo_membership_v2.md` does NOT exist in memory dir. `agente_referencia_compilada.md` does NOT contain v2.2 content (last updated May 25 per observation). Plan 14-03 intentionally delegated these to user/orchestrator via checklist in `grupo_membership_v2.md` Section 8 |

**Score:** 6/7 truths verified (1 needs human action)

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `leadflow-backend/tests/test_v2_regression.py` | 5 case-named tests (4 pass + 1 skip) + 1 log-marker source-audit | VERIFIED | 317 lines, 6 test functions confirmed; correct imports and patch targets |
| `leadflow-backend/app/routers/admin.py` | Healthcheck extended with `cache_hit_rate` + `total_rows_24h` + `phase="14-observability"` | VERIFIED | All 3 new fields present; div0 guard on `cache_hit_rate`; isolated try/except for `total_rows_24h`; legacy fields intact |
| `leadflow-backend/app/main.py` | `BUILD_VERSION = "2026-06-10-v2-2-completo"` | VERIFIED | Line 248 confirmed; old value `"2026-06-09-lead-in-group-consumer"` absent; consumed at line 283 in `/version` response |
| `leadflow-backend/docs/grupo_membership_v2.md` | Architecture doc ≥60 lines covering 8 sections + 5-case table + memory checklist | VERIFIED | 295 lines; all 8 sections present; grep matches: `lead_in_group` ×7, `GSC:` ×7, `max_age` ×7, all 5 cases ×9, `agente_referencia_compilada` ×1 |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `test_v2_regression.py` | `app.services.grupo_membership.lead_in_group` | `from app.services.grupo_membership import lead_in_group` | WIRED | Import confirmed at line 80 (G1), 203 (G3) |
| `test_v2_regression.py` | `app.services.evolution.verificar_lead_no_grupo` | `monkeypatch.setattr('app.services.evolution.verificar_lead_no_grupo', fake_probe)` | WIRED | Correct patch target (local import in `lead_in_group`) confirmed lines 88, 139, 188, 242 |
| `test_v2_regression.py` | `app.services.grupo_membership._probe_retry_job` | `from app.services.grupo_membership import _probe_retry_job` | WIRED | Import confirmed lines 131 (G2), 232 (G4) |
| `admin.py grupo_membership_health()` | `probe_cache.stats()` | `_cs = probe_cache.stats()` → `cache_hit_rate` calc | WIRED | `_total_lk = _cs.get("hits", 0) + _cs.get("misses", 0)` at line 1206; div0 guard at line 1212 |
| `/version endpoint` | `BUILD_VERSION` constant | `"build": BUILD_VERSION` in response | WIRED | Line 283 confirmed |

---

### Data-Flow Trace (Level 4)

Not applicable — phase produces tests, docs, and healthcheck extension. No dynamic data-rendering components.

---

### Behavioral Spot-Checks

| Behavior | Check | Result | Status |
|----------|-------|--------|--------|
| Test file has 6 test functions | `grep -c "def test_" test_v2_regression.py` | 6 | PASS |
| G5 is skip not assert-True | Source inspection lines 263-275 | `pytest.mark.skip(reason="blocked-pending-data...")`, no `assert True` | PASS |
| `cache_hit_rate` has div0 guard | `admin.py` grep | `_total_lk > 0` guard → `None` when no lookups | PASS |
| `BUILD_VERSION` is exact target string | `main.py` line 248 | `"2026-06-10-v2-2-completo"` | PASS |
| All 4 log markers present in source | `grupo_membership.py` + `grupo_state.py` grep | `[MEMB-WRITE]` ×10+, `[MEMB-LOOKUP]` ×5+, `[PROBE-RETRY]` ×8+, `GSC:` ×4+ | PASS |
| Full suite gate | SUMMARY 14-03 (run confirmed in submodule) | 113 passed, 1 skipped, 0 failed in 6.55s | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TEST-V2-G1 | 14-01 | Ana Carla Path 3 createGroup → source='membership', probe=0 | SATISFIED | `test_v2_g1_ana_carla_path3_create_group` lines 69-112: row present, instance_key match, probe count assertion |
| TEST-V2-G2 | 14-01 | Rosania T+138s TABLE_HIT in retry job, probe=0 | SATISFIED | `test_v2_g2_rosania_table_hit_at_138s` lines 120-160: enqueued_at=now-138s, row present, probe count assertion |
| TEST-V2-G3 | 14-01 | Fernanda instance_key mismatch → source='orphan', in_group=False | SATISFIED | `test_v2_g3_fernanda_orphan_instance_key` lines 168-213: old_row instance_key='bia-rejane', current='rejane-leal-mentora' |
| TEST-V2-G4 | 14-01 | Valquiria max_age discard (47h > 600s), probe=0 | SATISFIED | `test_v2_g4_valquiria_max_age_discard` lines 221-256: enqueued_at=now-47h |
| TEST-V2-G5 | 14-01 | 553891500357 stub skip with blocked-pending-data | SATISFIED | `test_v2_g5_lead_553891500357` lines 263-275: `pytest.mark.skip` with correct reason |
| DOC-V2-G1 | 14-03 | Architecture doc + session memory for webhook-first inversion | PARTIAL | In-repo doc `grupo_membership_v2.md` (295 lines, 8 sections) VERIFIED. Session memory `sessao_2026-06-10_grupo_membership_v2.md` NOT found in memory dir — human action required per Section 8 checklist |
| DOC-V2-G2 | 14-03 | `agente_referencia_compilada.md` updated with v2.2 content | PARTIAL | Not updated — last modified May 25. In-repo doc includes checklist item `[ ]` delegating this to user/orchestrator |
| OBS-V2-G1 | 14-01 | Structured logs `[MEMB-WRITE]`, `[MEMB-LOOKUP]`, `[PROBE-RETRY]`, `[GRUPO-STATE-CHANGE]/GSC:` | SATISFIED | All 4 confirmed in source; `test_v2_obs_g1_log_markers_present` locks against regression |
| OBS-V2-G2 | 14-02 | `/health/grupo-membership` returns `cache_hit_rate` + `total_rows_24h` | SATISFIED | Both fields in `admin.py` healthcheck; div0 guard; legacy fields preserved; path discrepancy (`/health/grupo-membership` vs `/admin/grupo-membership/health`) documented in code comment — intentional, no new route created |

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `test_v2_regression.py` | `datetime.utcnow()` DeprecationWarning | Info | Pre-existing pattern throughout codebase; documented in SUMMARY as accepted; no functional impact |

No blockers or structural stubs found.

---

### Human Verification Required

#### 1. Apply Memory Checklist (DOC-V2-G1 + DOC-V2-G2)

**Test:** Open `leadflow-backend/docs/grupo_membership_v2.md` Section 8 and complete the two `[ ]` checklist items:

1. Append to `~/.claude/projects/c--Projetos-Leadflow/memory/agente_referencia_compilada.md`: add section covering `grupo_membership` table, `lead_in_group()` decision tree, retry async `schedule_probe_retry`/`_probe_retry_job` (max_age=600), FSM monotonic + `GSC:` audit marker. APPEND only — do not rewrite.

2. Create `~/.claude/projects/c--Projetos-Leadflow/memory/sessao_2026-06-10_grupo_membership_v2.md` documenting the webhook-first inversion (context 08/06, 5 cases, architectural decisions Phases 10-14, reference to in-repo doc as definitive source).

**Expected:** Both files exist and contain v2.2 content. `agente_referencia_compilada.md` has a section mentioning `grupo_membership`, `lead_in_group()`, `schedule_probe_retry`, `max_age_seconds`, and `GSC:`. New session memory file exists.

**Why human:** Memory files live in `~/.claude/projects/c--Projetos-Leadflow/memory/` which is outside the `leadflow-backend` submodule. Plan 14-03 explicitly designed this as user/orchestrator action. The implementation subagent correctly created the in-repo doc with the checklist rather than writing to the memory directory itself.

---

### Gaps Summary

No blocking code gaps. All 6 code success criteria are satisfied:

- 4/4 regression tests pass with correct probe-count-zero assertions
- G5 is properly stubbed as `pytest.mark.skip`
- Healthcheck has `cache_hit_rate` (div0-guarded) + `total_rows_24h` + all legacy fields
- All 4 log marker families confirmed in source and locked by source-audit test
- Full suite: 113 passed, 1 skipped, 0 failed in 6.55s
- `BUILD_VERSION = "2026-06-10-v2-2-completo"` deployed

The only open item is **DOC-V2-G1/DOC-V2-G2** memory files (external to repo). The plan explicitly delegated these to the user/orchestrator via a checklist in `grupo_membership_v2.md` Section 8. This is not a code failure — it is an orchestrator handoff.

**SC6 count note:** Roadmap SC6 says "18 testes" (13 v2.1 + 5 new). Actual suite is 113 passed — a superset that includes all 18. The 18 are not regressed.

---

_Verified: 2026-06-10T04:45:00Z_
_Verifier: Claude (gsd-verifier)_
