---
phase: 14-testes-regressao-doc-observabilidade
plan: "02"
subsystem: backend-observability
tags: [healthcheck, cache, observability, build-version]
dependency_graph:
  requires: []
  provides: [OBS-V2-G2]
  affects: [admin.py grupo_membership_health, main.py /version]
tech_stack:
  added: []
  patterns: [additive healthcheck extension, div0-guarded ratio, isolated try/except blocks]
key_files:
  created: []
  modified:
    - leadflow-backend/app/routers/admin.py
    - leadflow-backend/app/main.py
decisions:
  - "cache_hit_rate emite None (nao 0.0) quando hits+misses==0 — evita falso positivo 'tudo miss' em deploy fresco; 0.0 seria ambiguo"
  - "total_rows_24h usa bloco try/except proprio com cutoff_24h redefinido localmente — cada bloco isolado, falha nao derruba o resto do payload"
  - "Nao foi criada rota adicional /health/grupo-membership; discrepancia de path documentada em comentario no codigo (OBS-V2-G2 cita path diferente do real)"
metrics:
  duration_minutes: 5
  completed_date: "2026-06-10"
  tasks_completed: 2
  files_modified: 2
---

# Phase 14 Plan 02: Healthcheck cache_hit_rate + total_rows_24h + BUILD_VERSION bump Summary

Estendeu `GET /admin/grupo-membership/health` com `cache_hit_rate` (div0-guarded float|null) + `total_rows_24h` (count isolado em try/except) e atualizou `BUILD_VERSION` para `"2026-06-10-v2-2-completo"` fechando o gap de rastreabilidade das Fases 12+13.

## What Was Built

### Task 1 — Extend grupo-membership/health endpoint (commit f34db6f)

Editado `grupo_membership_health()` em `app/routers/admin.py` de forma aditiva:

1. **`cache_hit_rate`** — campo top-level float|null calculado de `probe_cache.stats()`:
   - `_total_lk = hits + misses`; se `_total_lk > 0` retorna `round(hits/_total_lk, 3)`, caso contrário `None`
   - Guard div0 obrigatório: `None` em deploy fresco (sem lookups ainda); `0.0` seria enganoso
2. **`total_rows_24h`** — bloco try/except isolado que conta rows `grupo_membership` criadas nas últimas 24h via `count="exact"` com `.gte("criado_em", cutoff_24h_cnt)`
3. **`phase`** — atualizado de `"11-consumer"` para `"14-observability"`
4. **Comentário** de discrepância de path: critério OBS-V2-G2 cita `/health/grupo-membership`; endpoint real é `/admin/grupo-membership/health`

Todos os campos existentes preservados: `total_rows`, `last_write_at`, `writes_by_source_24h`, `cache_stats`, `lookup_stats`.

### Task 2 — Bump BUILD_VERSION (commit 3b5721c)

`app/main.py` linha 248:
- DE: `BUILD_VERSION = "2026-06-09-lead-in-group-consumer"`
- PARA: `BUILD_VERSION = "2026-06-10-v2-2-completo"`

Fases 12 e 13 foram shippadas sem bump. Deploy v2.2 completo (Fases 10-14) agora rastreável via `GET /version` campo `"build"`.

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | f34db6f | feat(14-02): extend grupo-membership/health with cache_hit_rate + total_rows_24h |
| Task 2 | 3b5721c | chore(14-02): bump BUILD_VERSION to 2026-06-10-v2-2-completo |

## Known Stubs

None.

## Threat Flags

No new threat surface introduced. Fields added to existing unauthenticated endpoint expose only aggregate metrics (ratio float, count int) — zero PII. Inherits accepted risk AR-11-01 per threat register T-14-03/T-14-04.

## Self-Check: PASSED

- [x] `leadflow-backend/app/routers/admin.py` — modified, AST valid
- [x] `leadflow-backend/app/main.py` — modified, AST valid
- [x] Commit f34db6f exists in submodule
- [x] Commit 3b5721c exists in submodule
- [x] `cache_hit_rate` present with `_total_lk > 0` guard
- [x] `total_rows_24h` present in isolated try/except
- [x] `phase` = "14-observability"
- [x] `BUILD_VERSION` = "2026-06-10-v2-2-completo" (old value absent)
- [x] OBS-V2-G2 marked complete in REQUIREMENTS.md
