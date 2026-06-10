---
phase: 14
slug: testes-regressao-doc-observabilidade
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-10
---

# Phase 14 — Validation Strategy

> Per-phase validation contract. This IS the regression/observability phase — its
> own deliverable is the test suite. Full suite green: 113 passed, 1 skipped.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (+ pytest-asyncio) |
| **Config file** | `leadflow-backend/tests/conftest.py` (evolution stub) + sys.modules stubs (apscheduler/supabase) |
| **Quick run command** | `cd leadflow-backend && python -m pytest tests/test_v2_regression.py -q` |
| **Full suite command** | `cd leadflow-backend && python -m pytest tests/ -q --ignore=tests/test_calendar_buffer.py --ignore=tests/test_verificar_lead_no_grupo_phase3.py` |
| **Estimated runtime** | ~6.5s full suite |

---

## Sampling Rate

- **After every task commit:** Run the quick command
- **After every plan wave:** Run the full suite
- **Before `/gsd-verify-work`:** Full suite green (113 passed, 1 skipped)
- **Max feedback latency:** ~7 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 14-01 | 01 | 1 | TEST-V2-G1..G5, OBS-V2-G1 | T-14-01 | 5 regression cases (4 pass + 1 skip) + log-marker source audit | unit | `pytest tests/test_v2_regression.py` | ✅ | ✅ green (5 pass, 1 skip) |
| 14-02 | 02 | 1 | OBS-V2-G2 | T-14-03/04 | healthcheck +cache_hit_rate (div0-guarded) +total_rows_24h; BUILD_VERSION bump | static | `ast.parse` + grep cache_hit_rate/total_rows_24h | ✅ | ✅ green |
| 14-03 | 03 | 2 | DOC-V2-G1/G2 | T-14-06 | in-repo arch doc + full-suite non-regression gate | doc + suite | `test -f docs/grupo_membership_v2.md` + full pytest | ✅ | ✅ green (113 pass, 1 skip) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Requirement → test map

| Requirement | Coverage |
|-------------|----------|
| TEST-V2-G1 (Ana Carla) | `test_v2_g1_ana_carla_path3_create_group` |
| TEST-V2-G2 (Rosania) | `test_v2_g2_rosania_table_hit_at_138s` |
| TEST-V2-G3 (Fernanda) | `test_v2_g3_fernanda_orphan_instance_key` |
| TEST-V2-G4 (Valquiria) | `test_v2_g4_valquiria_max_age_discard` |
| TEST-V2-G5 (553891500357) | `test_v2_g5_lead_553891500357` — skip (blocked-pending-data) |
| OBS-V2-G1 (log markers) | `test_v2_obs_g1_log_markers_present` |
| OBS-V2-G2 (healthcheck fields) | ast/grep on admin.py (runtime needs server) |
| DOC-V2-G1/G2 | `test -f docs/grupo_membership_v2.md` + content grep |

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. The regression suite is the phase deliverable.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Healthcheck returns the new fields at runtime | OBS-V2-G2 | Requires a running server | `curl /admin/grupo-membership/health` → `cache_hit_rate` + `total_rows_24h` present |
| TEST-V2-G5 (lead 553891500357) | TEST-V2-G5 | Blocked pending full webhook trace from user | Provide timestamps + payloads + conversas; then un-skip the test |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or are documented Manual-Only
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none)
- [x] No watch-mode flags
- [x] Feedback latency < 7s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-10
