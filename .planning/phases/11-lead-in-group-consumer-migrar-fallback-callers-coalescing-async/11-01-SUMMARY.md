---
phase: 11-lead-in-group-consumer-migrar-fallback-callers-coalescing-async
plan: 01
subsystem: api
tags: [asyncio, coalescing, grupo_membership, evolution, supabase, cache]

# Dependency graph
requires:
  - phase: 10-schema-3-paths-webhook-write-cache-standalone
    provides: grupo_membership table + write helpers + probe_cache singleton + get_instance_key
provides:
  - lead_in_group() async consumer (decision tree cache→membership→orphan→probe)
  - _query_membership_row() DB lookup helper (saiu_em IS NULL + OR telefone/lid)
  - probe coalescing primitives (_probe_locks dict + _probe_locks_dict_lock meta-lock + _get_probe_lock + _make_probe_lock_key)
  - _reset_probe_locks_for_tests() fixture hook
affects: [11-02 grupo_fallback migration, 11-03 pytest suite, 11-04 healthcheck stats]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Double-checked locking via asyncio.Lock per-chave para coalescing de probe HTTP"
    - "Decision tree invertida: grupo_membership como fonte primaria, probe Evolution como fallback"
    - "Imports locais dentro da funcao para permitir monkeypatch em testes"

key-files:
  created: []
  modified:
    - leadflow-backend/app/services/grupo_membership.py

key-decisions:
  - "source='orphan' (instance_key mismatch, caso Fernanda) NAO chama probe Evolution — economiza HTTP, caller decide recriar grupo"
  - "schedule_retry_on_negative e stub no-op nesta fase (assinatura preservada para Fase 12 PROBE-RETRY-01)"
  - "_query_membership_row RE-RAISE em erro DB para lead_in_group distinguir miss (None) vs erro (source='unknown')"
  - "Meta-lock protege criacao sob demanda do lock per-chave (defaultdict nao e thread-safe sob asyncio)"
  - "Cleanup de locks deferido: dict zera no restart diario do Easypanel; cap defensivo so se profiling mostrar leak"

patterns-established:
  - "Coalescing: N jobs concorrentes na mesma chave (empresa, grupo, tel, lid) disparam 1 unica chamada Evolution via double-checked cache pos-lock"
  - "Logs [MEMB-LOOKUP] key=value alinhados a [MEMB-WRITE] da Fase 10, com latency_ms em todas as branches"

requirements-completed: [MEMB-05, PROBE-COALESCE-01]

# Metrics
duration: ~20min
completed: 2026-06-09
---

# Phase 11 / Plan 01: lead_in_group() Consumer Summary

**Consumer webhook-first `lead_in_group()` adicionado a `grupo_membership.py` — consulta cache→tabela→orphan antes de cair para probe Evolution, com coalescing asyncio que colapsa N jobs concorrentes na mesma chave em 1 chamada HTTP.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-06-09
- **Tasks:** 4/4 (Task 4 e validacao-only)
- **Files modified:** 1 (`app/services/grupo_membership.py`, +208 linhas, additivo)

## Accomplishments

- **Task 1** (commit 1cfe4d1): imports + `_probe_locks` dict + `_probe_locks_dict_lock` meta-lock + `_get_probe_lock()` + `_make_probe_lock_key()` + `_reset_probe_locks_for_tests()` — primitivas de coalescing.
- **Task 2** (commit 5168c80): `_query_membership_row()` — DB lookup com `saiu_em IS NULL` + match OR telefone/lid + `ORDER BY atualizado_em DESC LIMIT 1`, re-raise em erro DB.
- **Task 3** (commit c5cb70f): `lead_in_group()` async — decision tree completa (cache fast-path → membership query → orphan check via instance_key → probe com coalescing double-checked). Retorna `{in_group, source, instance_key_match, last_event_at}`.
- **Task 4** (validacao-only): confirmado Fase 10 nao-regredida (upsert/get_instance_key/parse_evolution_timestamp intactos; probe_cache.py e evolution.py com git diff vazio).

## Verification

- AST parse OK + import smoke test OK (todos os 10 simbolos presentes e callable; `lead_in_group` e coroutine).
- Greds de aceitacao: `lead_in_group`=1, `_query_membership_row`=1, `_get_probe_lock`=1, `upsert_grupo_membership`=1, `get_instance_key`=1, `parse_evolution_timestamp`=1, `import asyncio`=1.
- source values: membership=1, orphan=1, probe=1, unknown>=3, cache=2; `[MEMB-LOOKUP]` >=3.
- No-regression: `git diff --stat` vazio para `probe_cache.py` e `evolution.py`.

## Notes / Deviations

- Execucao foi finalizada pelo orquestrador: o agente executor parou apos commitar Tasks 1-2 com o codigo da Task 3 ja escrito mas nao commitado (interrompido na verificacao por quoting de PowerShell nos greps). Orquestrador validou import + greps e commitou a Task 3 (c5cb70f). Nenhum desvio de conteudo do plano.

## Next

Plan 11-02 migra os 7 callsites de `verificar_lead_no_grupo` em `grupo_fallback.py` para consumir `lead_in_group()`, preservando PROBE-BYPASS-01.
