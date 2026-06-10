---
phase: 13-leave-handler-fsm-audit-monotonico
reviewed: 2026-06-10T03:30:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - app/services/grupo_state.py
  - app/services/grupo_membership.py
  - app/routers/grupo_webhook.py
  - app/routers/confirmacao_agendamento.py
  - app/routers/warmup_grupo.py
  - app/routers/admin.py
  - app/routers/leads.py
  - app/services/grupo_fallback.py
  - scripts/check_fsm_callers.py
  - tests/test_fsm_monotonic.py
  - tests/test_fsm_caller_ci.py
  - tests/test_leave_handler.py
  - tests/test_lead_in_group_decision.py
findings:
  critical: 0
  warning: 4
  high: 0
  medium: 3
  low: 3
  total: 7
status: resolved
resolved_at: 2026-06-10
resolution_commit: e34637f
---

# Phase 13: Code Review Report

> **Resolution (2026-06-10, submodule `e34637f`):** WR-01, WR-02, WR-03 FIXED.
> - WR-02 (notif left_group masked by probe cache): now derives `_left_group_nf` from the FSM state (`_state_nf == "LEFT_GROUP"`) instead of a second `lead_in_group` call — reliable + removes the double-call.
> - WR-01 (LEFT_GROUP wrong agendamento on grupo_jid reuse): added `.order("criado_em", desc=True)` to the lookup.
> - WR-03 (timeline cross-tenant): scoped the agendamentos enrichment query by `empresa_id`.
> - WR-04 (unquoted OR values) DEFERRED: matches the existing Phase-11 `_query_membership_row` pattern; phones are digits-only (nil injection risk) — fix both together later for consistency.
> - IN-01/02/03 DEFERRED: marker reason colon-escaping, sweep `**kwargs` doc note, NOOP_ vs BLOCKED audit noise — minor, tracked for Phase 14/follow-up.
> 57 phase-13 tests still green after fixes.

**Reviewed:** 2026-06-10T03:30:00Z
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Phase 13 delivers three interdependent concerns: (1) a monotonic FSM with mandatory audit trail (`GROUP_STATE` + `GSC:` markers), (2) a webhook REMOVE handler that marks `saiu_em`, writes a `LEAD_SAIU_GRUPO` marker, and transitions the FSM to `LEFT_GROUP`, and (3) plumbing in the D-1 and pre-meeting notification paths to detect `source='left_group'` and force DM. The FSM design is sound and the callsite migration is complete. The audit machinery (check_fsm_callers.py + test_fsm_caller_ci.py) provides strong structural guarantees.

Three issues require attention before or shortly after deploy:

**Most impactful:** The `agendamentos` enrichment query in `admin_grupo_status` (line 856) fetches rows **without** `empresa_id` scoping — if agendamento UUIDs from a different tenant are injected into the `ags` list (possible if the GRUPO_STATE conversas are ever cross-contaminated), appointment data from other companies leaks in the response. This is an existing pattern but newly reachable via the `?timeline=true` path and worth fixing.

**Correctness risk:** `_trigger_fsm_left_group` calls `set_grupo_state` using the `telefone` extracted from the `agendamentos` row — correct when available. However the `agendamentos` query uses only `grupo_jid` + non-cancelado to pick the appointment. For a `grupo_jid` that was **reused** across two leads (e.g. a recurring session), `.limit(1)` may target the wrong row and transition the wrong lead's FSM to `LEFT_GROUP`. The old group must be explicitly filtered (e.g. `status='agendado'` or a recency sort).

**Subtle correctness:** The warmup notif path calls `ativar_fallback_se_necessario` (which internally calls `lead_in_group` with full probe) and then calls `lead_in_group` a second time with `allow_probe_fallback=False` to detect `source='left_group'`. The second call is cache-aware and avoids a second HTTP probe, which is correct. However if the first call populates the probe cache with `True` (lead is in group), the second call returns `source='cache'` instead of `source='left_group'` — the `saiu_em` row would have been skipped entirely. This means a lead who left between the group-creation webhook and the notif job (and whose REMOVE webhook was already processed) may still get a grupo DM. The correct fix is to bypass the cache for the left_group check, or to check the FSM state instead of calling `lead_in_group` a second time.

---

## Warnings

### WR-01: `_trigger_fsm_left_group` — wrong agendamento picked when grupo_jid reused

**File:** `app/routers/grupo_webhook.py:324-348`
**Severity:** Warning

**Issue:** The query selects the first non-cancelled appointment matching `grupo_jid`:

```python
sb.table("agendamentos")
  .select("id, telefone")
  .eq("empresa_id", empresa_id)
  .eq("grupo_jid", grupo_jid)
  .neq("status", "cancelado")
  .limit(1)
  .execute()
```

If a `grupo_jid` has been reused for a second appointment (the same WhatsApp group is reused on a later booking, which occurs in production when `_criar_grupo_agendamento` detects an existing live group), `.limit(1)` without an `order` clause returns a non-deterministic row. The FSM LEFT_GROUP transition gets applied to whichever agendamento Postgres returns first — potentially the *previous* one that has already completed. The CURRENT agendamento's FSM would remain `ATIVO`, causing the D-1 and notif paths to continue sending to the group even after the lead left.

**Fix:** Add `status='agendado'` filter or sort descending by `criado_em` to ensure the most-current booking is targeted:

```python
sb.table("agendamentos")
  .select("id, telefone")
  .eq("empresa_id", empresa_id)
  .eq("grupo_jid", grupo_jid)
  .eq("status", "agendado")          # only the active booking
  .order("criado_em", desc=True)     # most recent first
  .limit(1)
  .execute()
```

---

### WR-02: warmup_grupo left_group check bypassed by probe cache hit

**File:** `app/routers/warmup_grupo.py:811-826`
**Severity:** Warning

**Issue:** The flow is:

1. `ativar_fallback_se_necessario(...)` is called — this function internally calls `lead_in_group` with full probe enabled. If the probe returns `True`, it populates `probe_cache` for `(empresa_id, grupo_jid, telefone, lid)`.
2. Immediately after, `lead_in_group(..., allow_probe_fallback=False)` is called to detect `source='left_group'`.

Step 2 first checks `probe_cache.get(...)` (STEP 1 in `lead_in_group`). If the cache was populated in step 1 with `in_group=True`, step 2 returns `{'source': 'cache', 'in_group': True}` without ever reading `_query_membership_row`. The `saiu_em` check (STEP 2b) is never reached. `_left_group_nf` stays `False` and the message is sent to the group instead of DM.

This only fires in the specific window where the REMOVE webhook has already been processed (`saiu_em` set in the DB) **but** the probe cache still has a positive entry from an earlier check within the same cache TTL. The cache TTL is not shown in the reviewed files, but if it is longer than the time between `ativar_fallback_se_necessario` and the `lead_in_group` call (effectively zero — same request), the positive cache entry from step 1 will always mask the left_group detection in step 2.

**Fix:** The simplest correct approach is to invalidate the cache for this lead before the second `lead_in_group` call, or check `_query_membership_row` directly. Alternatively, read the FSM state instead (if FSM=LEFT_GROUP, route DM — no second `lead_in_group` call needed):

```python
# Instead of calling lead_in_group a second time, check FSM state
# (already read as _state_nf above)
_left_group_nf = (_state_nf == STATE_LEFT_GROUP)
```

This is cheaper, correct, and avoids the cache-bypass issue entirely.

---

### WR-03: `agendamentos` enrichment query in `admin_grupo_status` missing `empresa_id` scope

**File:** `app/routers/admin.py:855-863`
**Severity:** Warning

**Issue:** The `leads` enrichment query is correctly scoped with `.eq("empresa_id", empresa_id)`. The `agendamentos` enrichment query is not:

```python
ag = sb.table("agendamentos").select("id,inicio,status,grupo_jid") \
    .in_("id", ags).execute()   # no empresa_id filter
```

`ags` is derived exclusively from `GRUPO_STATE:{ag_id}:…` markers that were already filtered by `empresa_id` in the conversas query. So in normal operation there is no cross-tenant leakage. However:
- If the database does not enforce RLS on `agendamentos`, a crafted `empresa_id` UUID that is valid but belongs to another tenant could cause the `GRUPO_STATE` markers of that tenant to appear (via the conversas query which IS scoped), and the agendamento enrichment would correctly scope to those IDs — still limited to the target company.
- More concretely: without the `empresa_id` filter, any agendamento ID reachable via the `in_("id", ags)` list could return data from another tenant if RLS is not active. This is pre-existing but newly surfaced by the timeline query path.

**Fix:** Add empresa_id filter to match the leads query:

```python
ag = sb.table("agendamentos").select("id,inicio,status,grupo_jid") \
    .eq("empresa_id", empresa_id) \
    .in_("id", ags).execute()
```

---

### WR-04: `_mark_membership_left` OR filter syntax: unquoted values may break PostgREST

**File:** `app/services/grupo_membership.py:466-468`
**Severity:** Warning

**Issue:** The OR filter in `_mark_membership_left`:

```python
q = q.or_(f'telefone.eq.{telefone},lid.eq.{lid}')
```

The identical pattern is used in `_query_membership_row` (line 115) and in `grupo_fallback.py:242`. This is an established pattern in the codebase and works for normal E.164 phone numbers (digits only) and `@lid` values (alphanumeric). However, if `telefone` or `lid` contains a comma, colon, or closing parenthesis, PostgREST will parse the filter incorrectly, potentially matching unintended rows or silently dropping the filter clause. `telefone` values in production are cleaned to digits-only before reaching this code, so the risk is low for phone numbers. `lid` values are `@lid` JIDs from WhatsApp — they can contain hyphens and alphanumerics but not commas or colons in practice.

**Fix:** Follow the PostgREST quoting standard for safety, matching the existing or_() usage in `admin.py:149` which uses the `.like.` operator variant. For equality, quote the value:

```python
q = q.or_(f'telefone.eq."{telefone}",lid.eq."{lid}"')
```

Apply the same fix to `_query_membership_row` line 115 for consistency.

---

## Info

### IN-01: GSC audit marker contains unescaped user-controlled data in `reason` field

**File:** `app/services/grupo_state.py:101`
**Severity:** Info

**Issue:** The GSC marker is written as:

```python
f"GSC:{agendamento_id}:{from_state}:{to_state}:{reason}:{caller}"
```

`reason` is supplied by callsites as a free-form string (e.g. `"lead_saiu_grupo"`, `"timeout_30min"`). In `set_grupo_state`, when a transition is BLOCKED, the reason is prefixed: `f"BLOCKED:{reason}"`. If any callsite passes a `reason` containing a colon (e.g. `"admin:reset"`), the `admin_grupo_status` timeline parser splits with `maxsplit=5` — this is safe for the split itself, but the `caller_t` field would absorb the extra content. In practice, all current callsite `reason` strings are underscore-delimited identifiers, so there is no current exposure. Worth documenting as a constraint.

**Fix:** Validate or strip colons from `reason` and `caller` in `set_grupo_state`, or document the no-colon constraint in the docstring:

```python
# Validation guard (optional, defensive):
reason = reason.replace(":", "_")
caller = caller.replace(":", "_")
```

---

### IN-02: `check_fsm_callers.py` does not detect `**kwargs` forwarding of caller

**File:** `scripts/check_fsm_callers.py:57-59`
**Severity:** Info

**Issue:** The AST check verifies that `caller=` appears as an explicit keyword argument in every `set_grupo_state` / `transition_grupo_state` call. It correctly skips function definitions. However, if a future developer wraps an FSM call via `**kwargs` forwarding (e.g. `set_grupo_state(sb, eid, tel, ag_id, state, **options)` where `options` contains `caller`), the check would flag it as a violation. This is a false-positive risk, not a false-negative. All current callsites use explicit kwargs — no current issue.

**Fix:** No action needed now. Add a comment to the script noting that `**kwargs` forwarding is not detected and is therefore not permitted as a pattern for passing `caller`.

---

### IN-03: `transition_grupo_state` writes a BLOCKED marker on `from_states` mismatch even when the mismatch is intentional / benign

**File:** `app/services/grupo_state.py:207-211`
**Severity:** Info

**Issue:** `transition_grupo_state` calls `_insert_audit_marker` with `BLOCKED:{reason}` whenever `current not in from_states`. This is by design for detecting race conditions. However, several legitimate call paths use `from_states=(STATE_AGUARDANDO, STATE_FALLBACK_1_1)` and arrive when the state is already `ATIVO` (e.g. `processar_entrada_lead_no_grupo` called twice in quick succession). These produce `BLOCKED` markers in the audit log that are semantically "no-op" rather than "blocked transition". Over time the audit timeline will contain BLOCKED noise that makes true blocking events harder to distinguish.

**Fix:** Consider a separate `reason` prefix for from_states mismatches (e.g. `NOOP_ALREADY_TRANSITIONED`) vs. true monotonic guard blocks (`BLOCKED`). No functional impact.

---

_Reviewed: 2026-06-10T03:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
