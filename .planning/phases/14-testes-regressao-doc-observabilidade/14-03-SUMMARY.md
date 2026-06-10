---
phase: 14-testes-regressao-doc-observabilidade
plan: "03"
subsystem: backend-docs
tags: [documentation, regression-gate, v2.2, webhook-first, milestone-close]
dependency_graph:
  requires:
    - "14-01 (test_v2_regression.py — 5 case-named tests)"
    - "14-02 (healthcheck cache_hit_rate + BUILD_VERSION)"
    - "13-04 (GSC: audit marker in grupo_state.py)"
    - "10-01..12-01 (grupo_membership table, lead_in_group, probe retry)"
  provides:
    - "DOC-V2-G1: in-repo architecture doc leadflow-backend/docs/grupo_membership_v2.md"
    - "DOC-V2-G2: memory checklist (external files referenced, not written)"
    - "Non-regression gate: 113 passed, 1 skipped, 0 failed — milestone v2.2 locked"
  affects:
    - "leadflow-backend/docs/grupo_membership_v2.md (new)"
tech_stack:
  added: []
  patterns:
    - "Architecture doc in-repo (docs/ directory, markdown)"
    - "pytest full-suite gate with --ignore for known env failures"
key_files:
  created:
    - "leadflow-backend/docs/grupo_membership_v2.md"
  modified: []
decisions:
  - "Doc created in submodule docs/ (not .planning/) — lives with the code it documents"
  - "Non-regression gate ignores only 2 named files (tzdata/httpx-idna env failures, not logic) — documented in doc section 9"
  - "Memory checklist items reference external ~/.claude/.../memory/ files — not written here, checklist is the DOC-V2-G2 deliverable"
  - "Gate ran in 6.55s (<60s target) — all 113 passed on first attempt"
metrics:
  duration: "~5 minutes"
  completed: "2026-06-10T04:37:26Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 1
  files_modified: 0
  commits:
    - hash: "bea7aa8"
      repo: "leadflow-backend"
      message: "docs(14-03): add grupo_membership_v2.md — webhook-first architecture doc"
    - hash: "0b5c1df"
      repo: "leadflow-backend"
      message: "docs(14-03): record non-regression gate result — 113 passed, 1 skipped, 6.55s"
requirements: [DOC-V2-G1, DOC-V2-G2]
---

# Phase 14 Plan 03: Architecture Doc + Non-Regression Gate Summary

**One-liner:** In-repo architecture doc for webhook-first grupo membership v2.2 (8 sections, 291 lines, 5-case table) + full pytest suite gate confirming 113 passed / 1 skipped / 0 failed in 6.55s.

## What Was Built

### Task 1 — `leadflow-backend/docs/grupo_membership_v2.md` (commit bea7aa8)

Documento de arquitetura consolidada v2.2 com 8 seções:

| Seção | Conteúdo |
|-------|----------|
| 1. Inversão webhook-first | Antes (probe primário) vs depois (tabela primária); por que mudou (4+ casos 08/06) |
| 2. Tabela + 3 write paths | Schema `grupo_membership`, `instance_key`, UPSERT idempotente; Path 1/2/3 com fontes |
| 3. `lead_in_group()` decision tree | Fluxo cache→tabela→probe; todos os `source` values (membership/cache/probe/orphan/left_group/stale) |
| 4. Retry async | `schedule_probe_retry` 30s/2min/5min, `max_age_seconds=600`, TABLE_HIT short-circuit |
| 5. LEAVE handler + FSM audit | `saiu_em`, `LEAD_SAIU_GRUPO`, FSM monôtônico, `GSC:` vs `GRUPO_STATE:` distinção |
| 6. Observabilidade | 4 log markers, healthcheck `/admin/grupo-membership/health` response shape v2.2 |
| 7. Tabela 5 casos | Ana Carla/Rosania/Fernanda/Valquiria/553891500357 → mecanismo → teste regressão |
| 8. Checklist memórias | DOC-V2-G2: 2 itens externos em `~/.claude/.../memory/` (append `agente_referencia_compilada.md` + nova sessão) |

**Métricas:** 291 linhas; `grep lead_in_group` = 7 matches; `grep GSC:` = 7; `grep max_age` = 7; 9 matches dos 5 casos.

### Task 2 — Gate de não-regressão (commit 0b5c1df)

Comando executado:
```
cd leadflow-backend && python -m pytest tests/ -q \
  --ignore=tests/test_calendar_buffer.py \
  --ignore=tests/test_verificar_lead_no_grupo_phase3.py
```

**Resultado:** `113 passed, 1 skipped, 0 failed in 6.55s` (2026-06-10)

| Categoria | Contagem |
|-----------|----------|
| Baseline pré-Fase 14 | 108 |
| Novos passing (14-01: G1..G4 + OBS-V2-G1) | 5 |
| Novo skipped (14-01: G5 blocked-pending-data) | 1 |
| **Total** | **113 passed + 1 skipped** |
| Failures | 0 |
| Tempo | 6.55s |

Ignores justificados (falhas de ENV, não de lógica):
- `test_calendar_buffer.py` — `tzdata` ausente no venv de teste
- `test_verificar_lead_no_grupo_phase3.py` — `httpx`/`idna` version mismatch no venv

Os 13 testes v2.1 + toda a infraestrutura das Fases 10-13 seguem verdes.

## Deviations from Plan

None — plano executado exatamente como escrito.

O gate passou na primeira execução com contagem exata esperada (113 passed, 1 skipped).
O doc foi criado em uma passagem com todos os acceptance criteria atendidos na primeira verificação.

## Known Stubs

- `test_v2_g5_lead_553891500357` — stub `pytest.mark.skip` intencional, rastreado. Ver 14-01-SUMMARY.md.

## Threat Flags

Nenhum. Plano cria apenas doc markdown e roda suite de testes. Sem código de runtime, sem endpoints novos, sem rede, sem auth.

T-14-05 (telefones reais no doc) — aceito conforme threat model do plano (repo privado, mesmos números já em STATE.md/REQUIREMENTS.md).
T-14-06 (--ignore scope) — mitigado: apenas 2 ignores específicos e nomeados, justificados no doc seção 9 e no research.

## Self-Check: PASSED

- [x] `leadflow-backend/docs/grupo_membership_v2.md` — FOUND (291 linhas)
- [x] `grep lead_in_group` >= 1 — FOUND (7)
- [x] `grep GSC:` >= 1 — FOUND (7)
- [x] `grep max_age` >= 1 — FOUND (7)
- [x] `grep -E "Ana Carla|Rosania|Fernanda|Valquiria|553891500357"` >= 4 — FOUND (9)
- [x] `grep -E "agente_referencia_compilada|sessao_2026-06"` >= 1 — FOUND (3)
- [x] Submodule commit `bea7aa8` — FOUND
- [x] Submodule commit `0b5c1df` — FOUND
- [x] Gate: 113 passed, 1 skipped, 0 failed — VERIFIED
- [x] Secão "Non-regression gate" no doc com contagem final — PRESENT
