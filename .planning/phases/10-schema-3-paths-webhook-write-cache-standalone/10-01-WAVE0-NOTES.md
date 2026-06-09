# Wave 0 Notes — Phase 10 Plan 01

**Date:** 2026-06-09
**Purpose:** Resolver ASSUMPTIONs A1, A2, A4 do 10-RESEARCH.md antes de tocar em código de produção.

---

### A1: cachetools version

- **Comando:** `curl -s "https://pypi.org/pypi/cachetools/json" | python -c "..."` (pip local quebrado — venv pip com ImportError em idna)
- **Output (5.x disponíveis no PyPI):**
  ```
  5.x versions: ['5.0.0', '5.1.0', '5.2.0', '5.2.1', '5.3.0', '5.3.1', '5.3.2', '5.3.3', '5.4.0', '5.5.0', '5.5.1', '5.5.2']
  Latest overall: 7.1.4
  ```
- **Versão escolhida:** `cachetools>=5.5.0,<6.0.0`
- **Decisão:** Primeira escolha — `5.5.0` está disponível no PyPI. Range `<6.0.0` evita quebra por major bump (7.x já existe mas está fora do range — Easypanel instalará `5.5.2` que é a mais recente da série 5.x). O venv local tem pip corrompido (`pip._vendor.idna` circular import) mas PyPI JSON API confirma versão via `curl`.
- **Adicionado em:** `leadflow-backend/requirements.txt` linha 26, entre `apscheduler==3.10.4` (L25) e `pytz>=2024.1` (L27).
- **Verificação:** `grep -n "^cachetools" leadflow-backend/requirements.txt` → `26:cachetools>=5.5.0,<6.0.0`

---

### A2: messageTimestamp shape

- **Tentativa:** SSH Easypanel não disponível no momento da execução — sem acesso ao container `3e74f7da5a68` para `docker logs`.
- **Shape observado:** Pending — logs indisponíveis no momento.
- **Contexto do código (agente.py L3730):** `data = payload.get("data", {})` — o campo `messageTimestamp` viria de `data.get("messageTimestamp")`.
- **Evidência indireta no RESEARCH.md (Path 1, linha 611):** `_evento_ts_raw = (payload.get('data') or {}).get('messageTimestamp') or payload.get('date_time')` — research já documentou que Baileys envia em segundos epoch, com fallback para string ISO.
- **Decisão:** Usar parser defensivo cobrindo 3 shapes (já documentado em 10-RESEARCH.md §Code Examples Path 1):
  ```python
  try:
      if isinstance(_evento_ts_raw, (int, float)):
          # Epoch segundos (padrão Baileys)
          # Guard: se > 10^12, assume ms — divide por 1000
          ts_int = int(_evento_ts_raw)
          evento_ts = datetime.fromtimestamp(ts_int / 1000 if ts_int > 10**12 else ts_int)
      elif isinstance(_evento_ts_raw, str):
          try:
              evento_ts = datetime.fromisoformat(_evento_ts_raw.replace('Z', '+00:00'))
          except ValueError:
              evento_ts = datetime.fromtimestamp(int(_evento_ts_raw))
      else:
          evento_ts = datetime.utcnow()
  except Exception:
      evento_ts = datetime.utcnow()
  ```
- **Confirmar em Wave 2** ao implementar `parse_evolution_timestamp` em Plan 03 Task 1 — logar shape real no primeiro webhook que chegar após deploy.

---

### A4: Path 2 callsite — CONFIRMADO

**Localização:** `leadflow-backend/app/routers/agente.py:3822-3867`

**Bloco:** `[LID-CAPTURE-MSG]` dentro do `try/except` em `if _emp_g_id:` (linha 3821), que por sua vez está dentro de `if _remoto_raw.endswith("@g.us"):` (linha 3799).

**Handler pai:** Função MESSAGES_UPSERT — event check em linha 3727:
```python
if event not in ("messages.upsert", "MESSAGES_UPSERT", "message.upsert"):
    return {"ok": True, "ignorado": True, "event": event}
```

**Variáveis no scope (verificadas via leitura direta linhas 3727-3867):**

| Variável | Origem | Valor/Shape |
|----------|--------|-------------|
| `payload` | parâmetro do handler (escopo global da função) | dict completo do webhook Evolution |
| `data` | `payload.get("data", {})` — linha 3730 | dict com `key`, `message`, `messageTimestamp` |
| `key` | `data.get("key", {})` — linha 3733 | dict com `remoteJid`, `fromMe`, `participant`, `id` |
| `_remoto_raw` | `key.get("remoteJid", "")` — linha 3798 | grupo_jid (formato `120363xxx@g.us`) |
| `_inst_g` | `payload.get("instance", "")` — linha 3802 | nome da instância Evolution (ex: `rejane-leal-mentora`) |
| `_sb_g` | `get_supabase()` — linha 3803 | cliente supabase service_role |
| `_emp_g_id` | lookup por `evolution_instancia == _inst_g` — linha 3820 | UUID empresa |
| `_participant` | `(key or {}).get("participant", "")` — linha 3827 | `@lid` ou telefone limpo (`5511xxx@s.whatsapp.net`) |
| `_tel_lead` | `_tels_aguard[0]` — linha 3845 (path @lid único) | telefone do lead aguardando |
| `_tel_match` | `_aguard_q.data[0].get("telefone")` — linha 3863 (path telefone) | telefone matched por sufixo |

**Dois paths dentro do bloco:**

1. **Path @lid** (linha 3831-3850): `"@lid" in _participant.lower()` → unique-aguardando → `_salvar_lead_lid` + `processar_entrada_lead_no_grupo` na linha 3848
2. **Path telefone limpo** (linha 3852-3865): participant é telefone → normalize + busca por sufixo → `processar_entrada_lead_no_grupo` na linha 3865

**Plan 04 patch strategy (Task 2 — Path 2):**

Inserir UPSERT em `grupo_membership` nos dois sub-paths:

**Sub-path @lid (após linha 3846, antes da linha 3848):**
```python
from app.services.grupo_membership import upsert_grupo_membership
from datetime import datetime as _dt_memb
_ts_raw_memb = (data or {}).get("messageTimestamp")
_entrou_em_memb = _parse_ts(_ts_raw_memb) if _ts_raw_memb else _dt_memb.utcnow()
upsert_grupo_membership(
    _sb_g,
    empresa_id=_emp_g_id,
    grupo_jid=_remoto_raw,
    telefone=_tel_lead,
    lid=_participant.strip(),
    instance_key=_inst_g,   # payload.get("instance") — Pitfall 3
    entrou_em=_entrou_em_memb,
    fonte='messages_upsert',
    last_event_id=(key or {}).get("id", ""),
)
```

**Sub-path telefone (após linha 3863, antes da linha 3865):**
```python
upsert_grupo_membership(
    _sb_g,
    empresa_id=_emp_g_id,
    grupo_jid=_remoto_raw,
    telefone=_tel_match,
    lid=None,
    instance_key=_inst_g,
    entrou_em=_entrou_em_memb,
    fonte='messages_upsert',
    last_event_id=(key or {}).get("id", ""),
)
```

**Campos mínimos do UPSERT (4 campos plan-required):**
- `instance_key` = `_inst_g` = `payload.get("instance", "")` — instância que originou o evento (Pitfall 3 — NÃO fazer lookup)
- `lid` = `_participant.strip()` (path @lid) ou `None` (path telefone)
- `telefone` = `_tel_lead` (path @lid) ou `_tel_match` (path telefone)
- `entrou_em` = derivado de `data.get("messageTimestamp")` com fallback `datetime.utcnow()`

**Linha exata de inserção confirmada:**
- Path @lid: INSERIR entre linha 3846 (`_salvar_lead_lid(...)`) e linha 3847 (`print("[LID-CAPTURE-MSG]...")`)
- Path telefone: INSERIR entre linha 3863 (`_tel_match = ...`) e linha 3864 (`print("[LID-CAPTURE-MSG]...")`)

**Sanity check:** `grep -c "LID-CAPTURE-MSG" leadflow-backend/app/routers/agente.py` → `5` (callsite preexistente confirmado, não modificado nesta wave)
