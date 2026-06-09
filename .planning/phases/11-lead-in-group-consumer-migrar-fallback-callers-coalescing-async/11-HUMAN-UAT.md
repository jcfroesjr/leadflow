---
status: partial
phase: 11-lead-in-group-consumer-migrar-fallback-callers-coalescing-async
source: [11-VERIFICATION.md]
started: 2026-06-09
updated: 2026-06-09
---

## Current Test

[awaiting human testing under natural prod traffic]

## Tests

### 1. source=membership in live prod traffic
expected: After 5-10 min of natural group traffic, SSH logs show at least one `[MEMB-LOOKUP] ... source=membership` (or `source=cache`) hit — confirms the webhook-first inversion reads the grupo_membership table instead of falling through to a probe every call. Command: `docker logs <container> --tail 200 -f | grep "\[MEMB-LOOKUP\]"` (find container via `docker ps | grep leadflow`).
result: [pending]

### 2. Migration 005 grant persists after restart
expected: After the next Easypanel container restart, `curl /admin/grupo-membership/health` still returns a clean response with NO `*_erro` keys (`total_rows_erro`, `last_write_erro`, `writes_24h_erro` absent) — confirms the table GRANT to service_role persisted at the DB level (not just in-memory).
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
