---
phase: 12-retry-async-callers-com-margem
plan: 02
subsystem: api
tags: [apscheduler, retry, probe, confirmacao, warmup, recovery, async, caller-migration]

# Dependency graph
requires:
  - phase: 12-01
    provides: schedule_probe_retry() + lead_in_group(schedule_retry_on_negative=True)
provides:
  - Caller 1 (confirmacao D-1) migrated to lead_in_group with retry
  - Caller 2 (notif warmup) enqueues schedule_probe_retry best-effort
  - recuperar_probe_retries_pendentes() recovery startup
affects: [12-03 tests, 14 observability]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Caller migration: replace direct verificar_lead_no_grupo with lead_in_group(schedule_retry_on_negative=True)"
    - "Best-effort retry injection: insert schedule_probe_retry after fallback decision without altering _destino"
    - "Recovery startup: state-DB-based (no marker) — agendamentos status=agendado + grupo_jid in next 6h + no membership row"

key-files:
  created: []
  modified:
    - leadflow-backend/app/routers/confirmacao_agendamento.py
    - leadflow-backend/app/routers/warmup_grupo.py
    - leadflow-backend/app/services/grupo_membership.py
    - leadflow-backend/app/main.py

key-decisions:
  - "Recovery uses state-DB approach (no PROBE_RETRY_PENDING marker): queries agendamentos+grupo_membership; enqueued_at is fresh post-restart (max_age=600 still protects intra-restart zombie jobs)"
  - "Warmup notif retry injected AFTER ativar_fallback_se_necessario decision — does not change _destino_nf or ativar_fallback_se_necessario signature (preserves Phase 11 7 callsites)"
  - "Aquec (_executar_aquecimento_grupo_job) stays synchronous — AGORA decision confirmed, no schedule_probe_retry added"
  - "Caller 2 confirmed in warmup_grupo.py _executar_notificacao_grupo_job (not _executar_timeout_grupo_aguardando which has no probe)"

# Metrics
duration: ~10min
completed: 2026-06-09
tasks_completed: 3
files_modified: 4
---

# Phase 12 / Plan 02: Callers com Margem — Retry Activation Summary

**PROBE-RETRY-02 implementado: 2 callers com margem migrados para retry async; recovery startup adicionado; aquec permanece sincrono.**

## Performance

- **Duration:** ~10 min
- **Completed:** 2026-06-09
- **Tasks:** 3/3
- **Files modified:** 4

## Accomplishments

- **Task 1** (commit db89b28): `confirmacao_agendamento.py` linha 291 — bloco `verificar_lead_no_grupo` direto substituido por `lead_in_group(schedule_retry_on_negative=True)`. `_in_group_real_cf` continua bool; linhas 299-308 (decisao destino) e timeout job intactos. Log atualizado para incluir `source=`.
- **Task 2** (commit df57bbb): `warmup_grupo.py` notif job — apos `ativar_fallback_se_necessario`, se `_in_group_real_nf is False` e `grupo_jid` presente, enfileira `schedule_probe_retry(attempts_left=3)` best-effort. `ativar_fallback_se_necessario` sem mudanca de assinatura. Aquec confirmado sem `schedule_probe_retry`.
- **Task 3** (commit d6fb9ab): `grupo_membership.py` — `async recuperar_probe_retries_pendentes()` adicionada ao fim do arquivo (+67 linhas). Query `agendamentos status=agendado + grupo_jid != null + inicio <= now+6h`, skip se row ja existe em `grupo_membership`, creds Evolution via `empresas.config_apis + evolution_instancia` (mesmo padrao warmup_grupo.py:749-752). `main.py` — `_recov_probe_retries()` closure + `create_task` adicionados no lifespan ao lado dos outros `_recov_*`.

## Caller 2 Deviation Confirmation

O plano original mencionava `_executar_timeout_grupo_aguardando` como "Caller 2". Apos leitura direta (confirmado no RESEARCH.md §5b), essa funcao nao faz probe — apenas transiciona FSM. O callsite real com margem temporal e a notif pre-reuniao em `_executar_notificacao_grupo_job` (`warmup_grupo.py`). O plano final (12-02-PLAN.md) ja refletia esta correcao. Implementacao seguiu o plano correto.

## Verification

- AST parse OK para todos os 4 arquivos (todos os 3 commits)
- Import smoke OK: `recuperar_probe_retries_pendentes` e coroutine, `schedule_probe_retry` e sync
- No-regression: `grupo_fallback.py` nao tocado (diff vazio); `ativar_fallback_se_necessario` sem mudanca de assinatura
- Grep checks:
  - `schedule_retry_on_negative=True` em `confirmacao_agendamento.py` → linha 302 (1 ocorrencia)
  - `from app.services.grupo_membership import lead_in_group` em confirmacao → linha 295 (1 ocorrencia)
  - `_in_group_real_cf = (_result_cf.get("in_group") is True)` → 1 ocorrencia
  - `schedule_probe_retry` em `warmup_grupo.py` → linhas 831, 834 (notif job only)
  - `retry async enfileirado` em `warmup_grupo.py` → 1 ocorrencia
  - `def recuperar_probe_retries_pendentes` em `grupo_membership.py` → linha 631
  - `[PROBE-RETRY-RECOVERY]` em `grupo_membership.py` → varias ocorrencias
  - `_recov_probe_retries` em `main.py` → linhas 81 (def) + 93 (create_task) = 2 ocorrencias
  - `create_task(_recov_probe_retries())` em `main.py` → 1 ocorrencia
  - `_executar_aquecimento_grupo_job` nao contem `schedule_probe_retry` (aquec sincrono)

## Deviations from Plan

### Minor — Recovery uses `inicio` field (not `data_hora_utc`)

- **Found during:** Task 3 implementation
- **Issue:** Plan example used `data_hora_utc` as the field name for meeting datetime. The actual `agendamentos` schema uses `inicio` (confirmed via grep in warmup_grupo.py recovery at lines 266-279).
- **Fix:** Recovery query uses `.lte("inicio", janela_fim.isoformat())` instead of `data_hora_utc`.
- **Files modified:** `grupo_membership.py`
- **Impact:** None — functionally equivalent, schema-correct.

### Minor — Credential helper inlined (not imported)

- **Found during:** Task 3 implementation
- **Issue:** Plan suggested using `_get_evo_creds_for_empresa` helper. No such function exists in the codebase — grep in `grupo_fallback.py` and `grupo_membership.py` returned no matches. Pattern is always inlined (query `empresas` for `config_apis + evolution_instancia`).
- **Fix:** Inlined the same 4-line credential extraction from `warmup_grupo.py:749-752` directly inside the per-item loop in `recuperar_probe_retries_pendentes`. No new function introduced.
- **Files modified:** `grupo_membership.py`
- **Impact:** None — reuses validated credential-reading pattern.

## Known Stubs

None — all functionality is wired. Recovery uses real DB state. Callers use real `schedule_probe_retry` from Plan 12-01.

## Threat Flags

No new network endpoints, auth paths, or schema changes introduced. All trust boundaries covered by plan's threat model (T-12-05, T-12-06, T-12-07):
- T-12-05 (DoS recovery): `.limit(200)` + skip if row exists + skip without creds
- T-12-06 (cross-tenant creds): credentials fetched by `empresa_id` from the same row
- T-12-07 (caller tampers destination): `_in_group_real_cf/_nf` semantics preserved; retry is best-effort separate from sync decision

## Self-Check: PASSED

- `leadflow-backend/app/routers/confirmacao_agendamento.py` — EXISTS, modified
- `leadflow-backend/app/routers/warmup_grupo.py` — EXISTS, modified
- `leadflow-backend/app/services/grupo_membership.py` — EXISTS, modified
- `leadflow-backend/app/main.py` — EXISTS, modified
- Commit `db89b28` — EXISTS (confirmacao D-1 caller migrated)
- Commit `df57bbb` — EXISTS (warmup notif retry)
- Commit `d6fb9ab` — EXISTS (recovery + lifespan spawn)
- Import smoke test PASSED
- AST PASSED (all 4 files)
- Aquec no-migration PASSED
- No-regression grupo_fallback PASSED
