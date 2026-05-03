---
phase: 02-dashboard-real
verified: 2026-04-09T00:00:00Z
status: human_needed
score: 8/8 must-haves verified
overrides_applied: 0
re_verification: null
gaps: []
deferred: []
human_verification:
  - test: "Open the dashboard in a browser while authenticated. Confirm all four KPI cards display numeric values (not 0) when leads exist in the database."
    expected: "Total de leads, Agendamentos, Conversas ativas, Taxa de conversão each show a real number from Supabase."
    why_human: "Cannot execute browser rendering or authenticate against Supabase in this environment."
  - test: "Confirm the AreaChart renders two area series (Leads, Agendamentos) with data points for the last 7 days shown on the X-axis as dd/mm labels."
    expected: "Chart is visible with the correct date labels and non-zero data when records exist."
    why_human: "Recharts rendering requires a live browser — not verifiable statically."
  - test: "Scroll to the Ultimos leads table. Verify each row shows nome, telefone, status badge, and a relative time string (e.g., 'há 2 horas')."
    expected: "Up to 5 rows displayed with all four fields populated from real Supabase data."
    why_human: "formatRelativeTime output and status badge rendering require live execution."
---

# Phase 2: Dashboard Real — Verification Report

**Phase Goal:** Dashboard exibe KPIs e gráfico com dados reais do Supabase.
**Verified:** 2026-04-09T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth                                                                           | Status     | Evidence                                                                                                                    |
|----|---------------------------------------------------------------------------------|------------|-----------------------------------------------------------------------------------------------------------------------------|
| 1  | KPI Total de leads exibe COUNT real de leads.empresa_id                         | VERIFIED   | dashboard.ts line 24: `supabase.from('leads').select('*', {count:'exact', head:true}).eq('empresa_id', empresaId)`         |
| 2  | KPI Agendamentos exibe COUNT de leads WHERE status = agendado                   | VERIFIED   | dashboard.ts line 25: `.eq('status', 'agendado')`                                                                          |
| 3  | KPI Conversas ativas exibe COUNT WHERE status IN (em_contato, qualificado)      | VERIFIED   | dashboard.ts line 26: `.in('status', ['em_contato', 'qualificado'])`                                                       |
| 4  | KPI Taxa de conversao exibe (COUNT qualificados / COUNT total) * 100 arredondado | VERIFIED   | dashboard.ts line 27: `.eq('status', 'qualificado')` as numerator; line 32: `Math.round((quali / total) * 100)`            |
| 5  | Grafico AreaChart exibe dados dos ultimos 7 dias para leads e agendamentos      | VERIFIED   | dashboard.ts lines 65-68 select/filter by `data_hora`; line 77 accumulates via `row.data_hora`; DashboardPage.tsx lines 91-113 bind chartData to AreaChart |
| 6  | Tabela de ultimos 5 leads exibe nome, telefone, status e tempo relativo         | VERIFIED   | dashboard.ts lines 89-95: select `id,nome,telefone,status,score,criado_em` limit 5; DashboardPage.tsx lines 166-179 render all four fields |
| 7  | Queries usam staleTime 30s (configurado globalmente em main.tsx)                | VERIFIED   | main.tsx line 10: `defaultOptions: { queries: { staleTime: 30000, retry: 1 } }`                                            |
| 8  | npm run build passa sem erros TypeScript                                        | VERIFIED   | SUMMARY documents `tsc -b → 0 errors, vite build → built in 6.20s`; code analysis confirms no type violations (Lead imported, map typed correctly, fetchRecentLeads returns Promise<Lead[]>) |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact                                                        | Expected                                        | Status   | Details                                                                                                        |
|-----------------------------------------------------------------|-------------------------------------------------|----------|----------------------------------------------------------------------------------------------------------------|
| `leadflow-frontend-v2/src/services/api/dashboard.ts`           | fetchDashboardMetrics, fetchChartData, fetchRecentLeads, DashboardMetrics, ChartPoint | VERIFIED | All three functions and both interfaces present; 97 lines of substantive implementation |
| `leadflow-frontend-v2/src/modules/dashboard/DashboardPage.tsx` | Dashboard with KPIs, AreaChart, recent leads table | VERIFIED | 185-line component with all three useQuery hooks, four KpiCards, AreaChart, and leads table rendered |

### Key Link Verification

| From              | To                        | Via                                   | Status  | Details                                                                               |
|-------------------|---------------------------|---------------------------------------|---------|---------------------------------------------------------------------------------------|
| DashboardPage.tsx | supabase (leads table)    | fetchDashboardMetrics(empresaId)      | WIRED   | useQuery calls fetchDashboardMetrics; function queries `leads` with empresa_id filter |
| DashboardPage.tsx | supabase (agendamentos)   | fetchChartData(empresaId)             | WIRED   | useQuery calls fetchChartData; function queries `agendamentos` using `data_hora`      |
| DashboardPage.tsx | useAuth()                 | tenant?.empresa?.id                   | WIRED   | Line 21: `const { tenant } = useAuth()`; line 22: `empresaId = tenant?.empresa?.id ?? ''`; all queries use `enabled: !!empresaId` guard |

### Data-Flow Trace (Level 4)

| Artifact            | Data Variable | Source                                      | Produces Real Data | Status    |
|---------------------|---------------|---------------------------------------------|--------------------|-----------|
| DashboardPage.tsx   | metrics       | fetchDashboardMetrics → 4 Supabase COUNT queries | Yes            | FLOWING   |
| DashboardPage.tsx   | chartData     | fetchChartData → 2 Supabase select queries  | Yes                | FLOWING   |
| DashboardPage.tsx   | recentLeads   | fetchRecentLeads → Supabase select with order/limit | Yes          | FLOWING   |

### Behavioral Spot-Checks

Step 7b: SKIPPED — no runnable entry point available without a live browser and authenticated Supabase session. Visual rendering checks routed to human verification.

### Requirements Coverage

| Requirement | Source Plan | Description                                      | Status        | Evidence                                                             |
|-------------|-------------|--------------------------------------------------|---------------|----------------------------------------------------------------------|
| DASH-01     | 02-01-PLAN  | KPI Total de leads — COUNT WHERE empresa_id      | SATISFIED     | dashboard.ts line 24: COUNT query on leads filtered by empresa_id    |
| DASH-02     | 02-01-PLAN  | KPI Agendamentos — COUNT WHERE status='agendado' | SATISFIED     | dashboard.ts line 25: .eq('status', 'agendado')                      |
| DASH-03     | 02-01-PLAN  | KPI Conversas ativas — status IN (em_contato, qualificado) | SATISFIED | dashboard.ts line 26: .in('status', ['em_contato', 'qualificado']) |
| DASH-04     | 02-01-PLAN  | Taxa de conversao = qualificados/total           | SATISFIED     | dashboard.ts line 27: .eq('status', 'qualificado') as sole numerator |
| DASH-05     | 02-01-PLAN  | Grafico area 7 dias — data_hora fix applied      | SATISFIED     | dashboard.ts uses data_hora throughout agendamentos branch           |
| DASH-06     | 02-01-PLAN  | Tabela 5 leads — nome, telefone, status, tempo   | SATISFIED     | All four fields selected and rendered; formatRelativeTime called     |
| DASH-07     | 02-01-PLAN  | staleTime 30s via global TanStack Query config   | SATISFIED     | main.tsx: defaultOptions.queries.staleTime = 30000                   |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None found | — | No placeholder returns, no empty handlers, no TODO comments, no hardcoded empty arrays passed to rendering |

### Human Verification Required

**1. KPI Cards display real Supabase data**

**Test:** Log in as an authenticated operator, navigate to the Dashboard. Observe all four KPI cards.
**Expected:** "Total de leads", "Agendamentos", "Conversas ativas", and "Taxa de conversao" each display a number from the database (not perpetual loading skeletons and not zero when records exist).
**Why human:** Supabase authentication and live query execution cannot be simulated in static analysis.

**2. AreaChart renders 7-day series with correct labels**

**Test:** On the Dashboard, locate the "Leads e agendamentos — ultimos 7 dias" card. Inspect the chart area.
**Expected:** Two colored area series (Leads and Agendamentos) plotted against X-axis labels formatted as dd/mm for each of the last 7 days.
**Why human:** Recharts rendering output requires a live browser environment.

**3. Ultimos leads table shows all required fields**

**Test:** Scroll to the "Ultimos leads" card. With at least one lead in the database, verify the displayed rows.
**Expected:** Each row shows nome (truncated if long), telefone, a colored status badge, and a relative time string (e.g., "ha 2 horas") in the rightmost column.
**Why human:** formatRelativeTime behavior and StatusBadge rendering require live execution.

### Gaps Summary

No gaps found. All 8 must-have truths are implemented correctly:

- The critical `data_hora` fix for agendamentos is in place (was the primary bug this phase addressed).
- The DASH-04 taxa de conversao formula uses only `status='qualificado'` as the numerator, not a funnel sum.
- The `fetchRecentLeads` function has an explicit `Promise<Lead[]>` return type with a safe cast.
- DashboardPage.tsx imports `Lead` from `@/types` and uses it in the map, eliminating the verbose inline type.
- staleTime 30s is set globally in main.tsx — no per-query configuration needed or present.
- Commit `dd99a69` in the frontend submodule confirms changes were applied and pushed.

Three human verification items remain because the phase goal ("Dashboard exibe KPIs e grafico com dados reais") is ultimately a visual/runtime assertion that requires a browser with a live Supabase connection.

---

_Verified: 2026-04-09T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
