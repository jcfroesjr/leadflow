---
phase: 1
phase_name: lock-atomico-queue
wave: 2
depends_on: [1.01]
files_modified:
  - leadflow-backend/app/routers/agente.py (envolver _processar_webhook_evolution_inner com try/finally)
  - leadflow-backend/app/main.py (BUILD_VERSION bump)
requirements:
  - LOCK-04
  - LOCK-05
  - LOCK-06
autonomous: true
---

# Phase 1, Plan 02 — Integração no Webhook Handler + Queue

## Objective

Envolver `_processar_webhook_evolution_inner` com lock atômico (try/finally) e implementar queue pra mensagens enfileiradas quando lock está ocupado.

## Why

Sem essa integração, o lock criado no Plan 01 não serve pra nada. Esta task conecta o lock ao fluxo real do webhook, garantindo que múltiplas mensagens do mesmo lead sejam processadas em ordem cronológica.

## Scope

1. Adquirir lock no início do handler (após resolver empresa_id e telefone)
2. Liberar lock no `finally` (mesmo se processamento falhar)
3. Quando lock ocupado, enfileirar via marker `QUEUED:{msg_id}:{ts}` e retornar 200 imediato
4. Após release, processar próximo da queue se houver

## Tasks

<task id="2.1" autonomous="true">
<title>Importar lock service no agente.py</title>

<read_first>
- leadflow-backend/app/routers/agente.py (top imports, linhas 1-20)
- leadflow-backend/app/services/lock.py (do Plan 01)
</read_first>

<action>
Em `leadflow-backend/app/routers/agente.py`, no bloco de imports do topo (logo após `from app.services.evolution import enviar_mensagem`), adicionar:

```python
from app.services.lock import acquire_lock, release_lock
```
</action>

<acceptance_criteria>
- `app/routers/agente.py` contém `from app.services.lock import acquire_lock, release_lock`
- Não quebra outros imports
- Sintaxe Python válida
</acceptance_criteria>
</task>

<task id="2.2" autonomous="true">
<title>Envolver _processar_webhook_evolution_inner com lock atômico</title>

<read_first>
- leadflow-backend/app/routers/agente.py linhas 2779-2920 (entry point do webhook handler)
- ANALISE_DETALHADA_DEFEITOS.md seção "SOLUÇÃO PROPOSTA — ARQUITETURA" (componente 1)
</read_first>

<action>
Localizar a função `_processar_webhook_evolution_inner` em `leadflow-backend/app/routers/agente.py` (linha ~2779).

Após o bloco que resolve `numero` (telefone) e `empresa_id` (linha ~2940-2950), adicionar guard de lock. Estrutura:

```python
# ── LOCK ATÔMICO (LOCK-04) ───────────────────────────────────────────────
# Sem esse lock, múltiplas mensagens do mesmo lead em <10s causam:
# Q2/empathy/slots duplicados, agendamento errado. Race observada em
# produção (Caca 03/05: 13 msgs do bot em 7s). Lock atômico em Postgres
# garante 1 mensagem por vez por (empresa, telefone). TTL 60s + cleanup
# job (scheduler.py) prevenem deadlock de processo morto.

_lock_acquired = False
_lock_msg_id = _msg_id  # capturado antes da idempotência

try:
    if empresa_id and numero and _lock_msg_id:
        _lock_acquired = acquire_lock(empresa_id, numero, _lock_msg_id)
        if not _lock_acquired:
            # LOCK-05: Lock ocupado — enfileira marker QUEUED e retorna
            # 200 imediato. Próximo processamento (após release) consultará
            # markers QUEUED em ordem cronológica.
            try:
                sb.table("conversas").insert({
                    "empresa_id": empresa_id,
                    "telefone": numero,
                    "role": "sistema",
                    "conteudo": f"QUEUED:{_lock_msg_id}:{datetime.utcnow().isoformat()}",
                    "criado_em": datetime.utcnow().isoformat(),
                }).execute()
                print(f"[QUEUE] enqueued empresa={empresa_id[:8]} tel={numero} msg={_lock_msg_id[:8]}")
            except Exception as _e_q:
                print(f"[QUEUE] erro enqueue: {_e_q}")
            return {"ok": True, "queued": True, "motivo": "lock_busy"}

    # === processamento normal continua aqui ===
    # ... (todo o código existente do handler) ...

finally:
    # LOCK-04: libera lock SEMPRE, mesmo se processamento falhou.
    if _lock_acquired and empresa_id and numero:
        release_lock(empresa_id, numero, _lock_msg_id)
        # LOCK-06: processa próximo da queue se houver
        try:
            _next_queued = sb.table("conversas") \
                .select("id, conteudo, criado_em") \
                .eq("empresa_id", empresa_id) \
                .eq("telefone", numero) \
                .eq("role", "sistema") \
                .like("conteudo", "QUEUED:%") \
                .order("criado_em", desc=False) \
                .limit(1).execute()
            if _next_queued.data:
                _qrow = _next_queued.data[0]
                _qmsg_id = (_qrow["conteudo"] or "").split(":")[1] if ":" in (_qrow["conteudo"] or "") else ""
                # Remove o marker QUEUED (consumido)
                sb.table("conversas").delete().eq("id", _qrow["id"]).execute()
                print(f"[QUEUE] dequeued empresa={empresa_id[:8]} tel={numero} msg={_qmsg_id[:8]}")
                # NOTA: re-disparar o processamento desta msg requer payload
                # original. Como Evolution já mandou, o ideal é que SYNC
                # ou retry da Evolution traga novamente. Por enquanto,
                # apenas marca como dequeued e confia em retry/sync.
                # Próxima task (2.3) implementa re-disparo via webhook
                # interno se necessário.
        except Exception as _e_dq:
            print(f"[QUEUE] erro dequeue: {_e_dq}")
```

**IMPORTANTE — sobre a estrutura try/finally:**
- O `try` deve englobar TODO o corpo atual da função após a aquisição de lock
- O `finally` deve ser o último bloco da função
- Dada a complexidade da função existente (centenas de linhas), use a abordagem cirúrgica:
  1. Após resolver `empresa_id`/`numero`/`_msg_id`, inserir o bloco `try:`
  2. Indentar TODO o código subsequente em +4 espaços (função inteira)
  3. Adicionar `finally:` block ao final, antes do return final

Use Edit tool com replace_all=false e contexto único pra fazer a transformação em chunks.
</action>

<acceptance_criteria>
- `_processar_webhook_evolution_inner` tem `acquire_lock(...)` no início
- Tem `try:` envolvendo o processamento
- Tem `finally:` com `release_lock(...)`
- Tem retorno antecipado `{"ok": True, "queued": True}` quando lock ocupado
- Insere marker `QUEUED:{msg_id}:{ts}` em conversas quando enfileirado
- Logs `[QUEUE] enqueued/dequeued` aparecem
- Sintaxe Python válida (`python -c "import ast; ast.parse(open(...).read()); print('OK')"`)
- Backend importa sem erro
</acceptance_criteria>
</task>

<task id="2.3" autonomous="true">
<title>Bump BUILD_VERSION pra phase 1 plan 02</title>

<read_first>
- leadflow-backend/app/main.py (linha do BUILD_VERSION)
</read_first>

<action>
Atualizar `BUILD_VERSION` em `leadflow-backend/app/main.py`:

```python
BUILD_VERSION = "2026-05-03-phase1-lock-webhook-integrado"
```
</action>

<acceptance_criteria>
- `app/main.py` contém `BUILD_VERSION = "2026-05-03-phase1-lock-webhook-integrado"`
- Endpoint `/version` retorna esse build após redeploy
</acceptance_criteria>
</task>

## Verification (após todas tasks)

1. Backend importa sem erro: `python -c "from app.routers.agente import _processar_webhook_evolution_inner; print('OK')"`
2. Build version endpoint retorna `2026-05-03-phase1-lock-webhook-integrado`
3. Webhook test single message: continua funcionando normalmente (smoke test)
4. Webhook test 2 mensagens simultâneas do mesmo lead: 2ª retorna `{"queued": true}` no log
5. Logs `[LOCK] acquired/released` aparecem para cada webhook processado

## must_haves

- Lock acquire+release no caminho normal (happy path)
- Lock release no caminho de erro (exception)
- Marker QUEUED inserido quando lock ocupado
- Próximo da queue removido após release (não vira lixo eterno)
