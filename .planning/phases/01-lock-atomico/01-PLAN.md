---
phase: 1
phase_name: lock-atomico-queue
wave: 1
depends_on: []
files_modified:
  - leadflow-backend/app/services/lock.py (NEW)
  - leadflow-backend/app/db/migrations/processing_locks.sql (NEW)
  - leadflow-backend/app/scheduler.py (registrar cleanup job)
  - leadflow-backend/app/main.py (BUILD_VERSION bump)
requirements:
  - LOCK-01
  - LOCK-02
  - LOCK-03
  - LOCK-07
  - LOCK-08
autonomous: true
---

# Phase 1, Plan 01 — Lock Service + Migration

## Objective

Criar o serviço de lock atômico em Postgres (Supabase) e o job APScheduler de cleanup. Sem isso, a integração no webhook (Plan 02) não tem como travar/destravar.

## Why

Causa raiz documentada em `ANALISE_DETALHADA_DEFEITOS.md`: webhooks paralelos do mesmo lead lendo `historico` defasado → estado divergente → Q2/empathy/slots duplicados → agendamento errado. Lock atômico resolve garantindo serialização por (empresa_id, telefone).

## Scope

1. Migration SQL pra tabela `processing_locks`
2. `app/services/lock.py` com 3 funções: `acquire_lock`, `release_lock`, `cleanup_expired_locks`
3. Job APScheduler de cleanup periódico (30s)
4. Logs `[LOCK]` estruturados
5. Testes unitários básicos (sem dependência de Postgres real — mock)

## Tasks

<task id="1.1" autonomous="true">
<title>Criar migration SQL pra tabela processing_locks</title>

<read_first>
- leadflow-backend/app/db/client.py (entender padrão de acesso ao Supabase)
- ANALISE_DETALHADA_DEFEITOS.md seção "SOLUÇÃO PROPOSTA — ARQUITETURA"
</read_first>

<action>
Criar arquivo `leadflow-backend/app/db/migrations/001_processing_locks.sql` com:

```sql
-- Migration: processing_locks
-- Purpose: Atomic lock per (empresa_id, telefone) for agent webhook serialization
-- Created: 2026-05-03

CREATE TABLE IF NOT EXISTS processing_locks (
    empresa_id UUID NOT NULL,
    telefone TEXT NOT NULL,
    msg_id TEXT NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (empresa_id, telefone)
);

CREATE INDEX IF NOT EXISTS idx_processing_locks_expires
    ON processing_locks (expires_at);
```

Aplicar manualmente no Supabase (Studio SQL Editor) ou via supabase-py com service_role key.

Adicionar comentário no topo do arquivo: "-- Aplicar via Supabase Studio ou via script init_db.py".
</action>

<acceptance_criteria>
- Arquivo `leadflow-backend/app/db/migrations/001_processing_locks.sql` existe
- Contém `CREATE TABLE IF NOT EXISTS processing_locks`
- Tem PK em (empresa_id, telefone)
- Tem coluna `expires_at TIMESTAMPTZ NOT NULL`
- Tem index em `expires_at`
- Comentário explicativo no topo
</acceptance_criteria>
</task>

<task id="1.2" autonomous="true">
<title>Aplicar migration no Supabase de produção</title>

<read_first>
- leadflow-backend/app/db/migrations/001_processing_locks.sql (criada na task 1.1)
- C:\Users\Caca Froes\.claude\projects\c--Projetos-Leadflow\memory\project_leadflow.md (credenciais Supabase service_role)
</read_first>

<action>
Aplicar a migration via curl + Supabase REST RPC ou diretamente via Supabase Studio.

Opção A (preferida — via curl com service_role key):
```bash
curl -X POST "https://pllpwjuagqykxwyfpqrz.supabase.co/rest/v1/rpc/exec_sql" \
  -H "apikey: $SUPABASE_SERVICE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"sql": "CREATE TABLE IF NOT EXISTS processing_locks (empresa_id UUID NOT NULL, telefone TEXT NOT NULL, msg_id TEXT NOT NULL, acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), expires_at TIMESTAMPTZ NOT NULL, PRIMARY KEY (empresa_id, telefone)); CREATE INDEX IF NOT EXISTS idx_processing_locks_expires ON processing_locks (expires_at);"}'
```

Opção B (fallback — via Supabase Studio SQL Editor):
- Abrir https://pllpwjuagqykxwyfpqrz.supabase.co
- SQL Editor → New Query → colar o conteúdo de 001_processing_locks.sql
- Run

Verificar que tabela existe via curl GET:
```bash
curl -s "https://pllpwjuagqykxwyfpqrz.supabase.co/rest/v1/processing_locks?limit=0" \
  -H "apikey: $SUPABASE_SERVICE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
  -I
```

Deve retornar HTTP 200.
</action>

<acceptance_criteria>
- Tabela `processing_locks` existe no Supabase de produção
- Curl GET na tabela retorna HTTP 200 com Content-Range header
- Inserir uma linha de teste manualmente via curl POST funciona
- Conflito (segunda inserção com mesma PK) retorna HTTP 409
</acceptance_criteria>
</task>

<task id="1.3" autonomous="true">
<title>Criar app/services/lock.py com acquire/release/cleanup</title>

<read_first>
- leadflow-backend/app/db/client.py (padrão get_supabase)
- leadflow-backend/app/scheduler.py (entender APScheduler setup)
- leadflow-backend/app/services/evolution.py (padrão de logging existente)
</read_first>

<action>
Criar `leadflow-backend/app/services/lock.py` com o seguinte conteúdo:

```python
"""
Lock atômico por (empresa_id, telefone) pra serializar processamento de
webhooks do agente IA. Sem isso, múltiplas mensagens em paralelo do mesmo
lead causam race conditions: Q2/empathy/slots duplicados, agendamento errado.

Estratégia: tabela `processing_locks` com PK em (empresa_id, telefone).
INSERT atômico = lock adquirido. UNIQUE_VIOLATION = outro detentor ativo.
TTL de 60s + cleanup job protegem contra deadlocks de processo morto.
"""
from datetime import datetime, timedelta
from typing import Optional
from app.db.client import get_supabase

LOCK_TTL_SECONDS = 60


def acquire_lock(empresa_id: str, telefone: str, msg_id: str) -> bool:
    """
    Tenta adquirir lock atômico para (empresa_id, telefone).

    Returns:
        True se lock adquirido, False se outro detentor ativo.
    """
    sb = get_supabase()
    now = datetime.utcnow()
    expires = now + timedelta(seconds=LOCK_TTL_SECONDS)
    try:
        sb.table("processing_locks").insert({
            "empresa_id": empresa_id,
            "telefone": telefone,
            "msg_id": msg_id,
            "acquired_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }).execute()
        print(f"[LOCK] acquired empresa={empresa_id[:8]} tel={telefone} msg={msg_id[:8]}")
        return True
    except Exception as e:
        # PostgreSQL unique_violation = código 23505. supabase-py
        # encapsula em APIError ou similar. Conservador: qualquer falha
        # de insert = lock ocupado. Cleanup job limpa expired_at < now.
        msg = str(e).lower()
        if "23505" in msg or "duplicate" in msg or "already exists" in msg:
            print(f"[LOCK] busy empresa={empresa_id[:8]} tel={telefone} (msg={msg_id[:8]})")
            return False
        # Erro inesperado — log e considera "não adquirido" pra ser seguro
        print(f"[LOCK] erro acquire empresa={empresa_id[:8]} tel={telefone}: {e}")
        return False


def release_lock(empresa_id: str, telefone: str, msg_id: Optional[str] = None) -> bool:
    """
    Libera o lock. Se msg_id fornecido, só libera se for o detentor atual
    (evita race onde lock expirou e foi readquirido por outro msg_id).

    Returns:
        True se removeu uma linha, False se nada removido.
    """
    sb = get_supabase()
    try:
        q = sb.table("processing_locks") \
            .delete() \
            .eq("empresa_id", empresa_id) \
            .eq("telefone", telefone)
        if msg_id:
            q = q.eq("msg_id", msg_id)
        res = q.execute()
        removed = len(res.data or [])
        print(f"[LOCK] released empresa={empresa_id[:8]} tel={telefone} msg={(msg_id or '?')[:8]} removed={removed}")
        return removed > 0
    except Exception as e:
        print(f"[LOCK] erro release empresa={empresa_id[:8]} tel={telefone}: {e}")
        return False


def cleanup_expired_locks() -> int:
    """
    Remove locks com expires_at < NOW(). Chamado periodicamente (30s) pelo
    APScheduler pra prevenir deadlock de processo morto no meio.

    Returns:
        Número de locks removidos.
    """
    sb = get_supabase()
    try:
        now = datetime.utcnow().isoformat()
        res = sb.table("processing_locks") \
            .delete() \
            .lt("expires_at", now) \
            .execute()
        removed = len(res.data or [])
        if removed > 0:
            print(f"[LOCK] cleanup removed {removed} expired lock(s)")
        return removed
    except Exception as e:
        print(f"[LOCK] erro cleanup: {e}")
        return 0


def lock_status(empresa_id: str, telefone: str) -> Optional[dict]:
    """
    Retorna info do lock ativo se houver. Útil pra observabilidade
    (endpoint /admin/queue-stats no Plan 03).
    """
    sb = get_supabase()
    try:
        res = sb.table("processing_locks") \
            .select("msg_id, acquired_at, expires_at") \
            .eq("empresa_id", empresa_id) \
            .eq("telefone", telefone) \
            .limit(1).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None
```
</action>

<acceptance_criteria>
- Arquivo `leadflow-backend/app/services/lock.py` existe
- Contém função `acquire_lock(empresa_id, telefone, msg_id) -> bool`
- Contém função `release_lock(empresa_id, telefone, msg_id) -> bool`
- Contém função `cleanup_expired_locks() -> int`
- Contém função `lock_status(empresa_id, telefone) -> Optional[dict]`
- Constante `LOCK_TTL_SECONDS = 60`
- Logs `[LOCK]` em acquire/release/cleanup
- Sintaxe válida: `python -c "import ast; ast.parse(open('leadflow-backend/app/services/lock.py').read()); print('OK')"` retorna `OK`
</acceptance_criteria>
</task>

<task id="1.4" autonomous="true">
<title>Registrar cleanup job no APScheduler</title>

<read_first>
- leadflow-backend/app/scheduler.py (configuração atual do APScheduler)
- leadflow-backend/app/main.py (entender startup hooks)
</read_first>

<action>
Em `leadflow-backend/app/scheduler.py`, adicionar registro do job de cleanup logo após `scheduler = AsyncIOScheduler(...)`:

```python
# Job de cleanup de locks expirados (LOCK-07)
# Roda a cada 30s pra prevenir deadlock se processo morrer com lock ativo.
# Lock tem TTL de 60s; cleanup intervalo 30s = no máximo 1.5x TTL antes de ser removido.
from app.services.lock import cleanup_expired_locks

scheduler.add_job(
    cleanup_expired_locks,
    "interval",
    seconds=30,
    id="cleanup_expired_locks",
    replace_existing=True,
    max_instances=1,
)
print("[SCHEDULER] registered cleanup_expired_locks (interval=30s)")
```

Posicionar antes do `scheduler.start()` ou no equivalente do startup hook.
</action>

<acceptance_criteria>
- `app/scheduler.py` contém `from app.services.lock import cleanup_expired_locks`
- `app/scheduler.py` contém `scheduler.add_job(cleanup_expired_locks, "interval", seconds=30, id="cleanup_expired_locks", ...)`
- `print("[SCHEDULER] registered cleanup_expired_locks` aparece nos logs após restart
- Sintaxe Python válida
</acceptance_criteria>
</task>

<task id="1.5" autonomous="true">
<title>Bump BUILD_VERSION pra phase 1 plan 01</title>

<read_first>
- leadflow-backend/app/main.py (linha do BUILD_VERSION)
</read_first>

<action>
Em `leadflow-backend/app/main.py`, atualizar `BUILD_VERSION` pra:

```python
BUILD_VERSION = "2026-05-03-phase1-lock-atomico-base"
```
</action>

<acceptance_criteria>
- `app/main.py` contém `BUILD_VERSION = "2026-05-03-phase1-lock-atomico-base"`
- Endpoint `/version` retorna esse build após redeploy
</acceptance_criteria>
</task>

## Verification (após todas tasks)

1. Migration aplicada: `curl -s {supa}/rest/v1/processing_locks?limit=0 -I` retorna 200
2. `app/services/lock.py` syntax OK
3. `app/scheduler.py` syntax OK + contém registro do job
4. Backend restart: logs mostram `[SCHEDULER] registered cleanup_expired_locks`
5. Após 30s: logs podem mostrar `[LOCK] cleanup removed N expired lock(s)` (0 se não há nenhum)

## must_haves

- Tabela processing_locks existe e funcional no Supabase prod
- Service lock.py importável sem erro
- Cleanup job registrado e logando
- Backend redeployável sem regressão
