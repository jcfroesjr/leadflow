# Agendamento: Slots 3 Turnos + Deduplicação + Slots de Hoje — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir 3 bugs no agente IA: slots de hoje com buffer correto + hora atual no contexto do LLM, deduplicação de "Super te entendo", e busca de 3 slots por turno com extensão automática 5→15 dias.

**Architecture:** Dois arquivos modificados. `google_calendar.py` recebe ajuste de buffer. `agente.py` recebe: contexto de hora atual, fix de defaults, save pré-LLM no DB, post-processing de resposta, e nova função `_buscar_tres_slots` que substitui lógica duplicada em OpenAI e Gemini paths.

**Tech Stack:** Python 3.11, FastAPI, Supabase (PostgreSQL via `supabase-py`), Google Calendar API, OpenAI SDK, Google GenAI SDK, ZoneInfo.

---

## Mapa de arquivos

| Arquivo | Tipo | O que muda |
|---|---|---|
| `leadflow-backend/app/services/google_calendar.py` | Modify | Buffer de hoje: `15min → 60min` (linha ~113) |
| `leadflow-backend/app/routers/agente.py` | Modify | 5 mudanças descritas nas tasks abaixo |
| `leadflow-backend/tests/test_calendar_buffer.py` | Create | Testes unitários para buffer e filtro de turno |
| `leadflow-backend/tests/test_agente_fixes.py` | Create | Testes unitários para deduplicação e _data_ctx |

---

## Task 1: Buffer de hoje em google_calendar.py (15min → 60min)

**Files:**
- Modify: `leadflow-backend/app/services/google_calendar.py` linha ~113
- Create: `leadflow-backend/tests/test_calendar_buffer.py`

- [ ] **Step 1: Criar arquivo de testes**

```python
# leadflow-backend/tests/test_calendar_buffer.py
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock

TZ = ZoneInfo("America/Sao_Paulo")


def _make_hoje(hora: int, minuto: int):
    """Cria datetime 'agora' com hora/minuto específicos no fuso SP."""
    return datetime.now(TZ).replace(hour=hora, minute=minuto, second=0, microsecond=0)


def test_buffer_hoje_slot_dentro_60min_e_descartado():
    """Slot 45min à frente de agora deve ser descartado (< 60min buffer)."""
    agora = _make_hoje(14, 0)   # 14:00
    slot_candidato = agora + timedelta(minutes=45)  # 14:45 — menos de 60min

    # Simula time_min_candidato = max(hora_inicio_dia, agora + 60min)
    buffer = agora + timedelta(minutes=60)   # 15:00
    assert slot_candidato < buffer, "Slot dentro de 60min deve ser descartado"


def test_buffer_hoje_slot_apos_60min_e_aceito():
    """Slot 90min à frente de agora deve ser aceito."""
    agora = _make_hoje(14, 0)   # 14:00
    slot_candidato = agora + timedelta(minutes=90)  # 15:30 — mais de 60min

    buffer = agora + timedelta(minutes=60)   # 15:00
    assert slot_candidato >= buffer, "Slot após 60min deve ser aceito"


def test_buffer_hoje_sem_slots_cai_para_amanha():
    """Se time_min >= time_max, deve retornar lista vazia (cai para genérica)."""
    agora = _make_hoje(20, 0)   # 20:00 — expediente encerra 20:15
    time_min_candidato = agora + timedelta(minutes=60)  # 21:00
    time_max = agora.replace(hour=20, minute=15)  # 20:15

    assert time_min_candidato >= time_max, "Deve cair para próximo dia útil"
```

- [ ] **Step 2: Rodar testes para verificar que passam (são testes de lógica pura)**

```bash
cd leadflow-backend
python -m pytest tests/test_calendar_buffer.py -v
```
Esperado: 3 PASSED

- [ ] **Step 3: Alterar buffer em google_calendar.py**

No arquivo `leadflow-backend/app/services/google_calendar.py`, localizar linha ~113:

```python
# ANTES:
hoje + timedelta(minutes=15),

# DEPOIS:
hoje + timedelta(minutes=60),
```

A linha está dentro do bloco `if alvo.date() == hoje.date():`, no cálculo de `time_min_candidato`:
```python
time_min_candidato = max(
    alvo.replace(hour=hora_inicio_dia, minute=hora_inicio_minuto, second=0, microsecond=0),
    hoje + timedelta(minutes=60),   # ← era 15
)
```

- [ ] **Step 4: Rodar testes novamente para confirmar**

```bash
python -m pytest tests/test_calendar_buffer.py -v
```
Esperado: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add leadflow-backend/app/services/google_calendar.py leadflow-backend/tests/test_calendar_buffer.py
git commit -m "fix: aumentar buffer de slots de hoje de 15min para 60min"
```

---

## Task 2: Injetar hora atual no contexto do LLM (agente.py)

**Files:**
- Modify: `leadflow-backend/app/routers/agente.py` — função `_gerar_resposta_openai_com_agenda` (~linha 85) e `_gerar_resposta_gemini_com_agenda` (~linha 523)

- [ ] **Step 1: Localizar os dois _data_ctx no arquivo**

```bash
grep -n "_data_ctx" leadflow-backend/app/routers/agente.py
```
Esperado: 2 ocorrências — uma em cada função.

- [ ] **Step 2: Alterar _data_ctx na função OpenAI (~linha 85)**

`datetime` já está importado no topo do arquivo (`from datetime import datetime`). Usar diretamente.

```python
# ANTES:
from datetime import date as _dt_today
_hoje = _dt_today.today()
_data_ctx = (
    f"\n\nDATA DE HOJE: {_hoje.strftime('%d/%m/%Y')}. Ano atual: {_hoje.year}."
    f" Ao chamar criar_agendamento, sempre use o ano {_hoje.year} para datas no formato DD/MM. Exemplo: '23/03' → data='2026-03-23'."
    "\n\nIMPORTANTE: Nunca reproduza '[SLOTS_TOKENS: ...]' nas suas respostas ao lead."
    " Essa marcação é interna do sistema e serve apenas para que você saiba qual slot_token usar ao chamar criar_agendamento."
)

# DEPOIS:
from datetime import date as _dt_today
from zoneinfo import ZoneInfo as _ZI_ctx
_hoje = _dt_today.today()
_agora_local_ctx = datetime.now(_ZI_ctx(fuso))   # datetime já importado no topo do arquivo
_agora_fmt_ctx = _agora_local_ctx.strftime('%d/%m/%Y %H:%M')
_data_ctx = (
    f"\n\nDATA E HORA ATUAL: {_agora_fmt_ctx}. Ano atual: {_hoje.year}."
    f" Ao chamar criar_agendamento, sempre use o ano {_hoje.year} para datas no formato DD/MM. Exemplo: '23/03' → data='2026-03-23'."
    f" IMPORTANTE: Só sugira horários de hoje ({_agora_local_ctx.strftime('%d/%m/%Y')}) se forem APÓS {_agora_fmt_ctx}. Horários anteriores a este não existem mais."
    "\n\nIMPORTANTE: Nunca reproduza '[SLOTS_TOKENS: ...]' nas suas respostas ao lead."
    " Essa marcação é interna do sistema e serve apenas para que você saiba qual slot_token usar ao chamar criar_agendamento."
)
```

- [ ] **Step 3: Alterar _data_ctx_g na função Gemini (~linha 523)**

```python
# ANTES:
from datetime import date as _dt_today_g
_hoje_g = _dt_today_g.today()
_data_ctx_g = f"\n\nDATA DE HOJE: {_hoje_g.strftime('%d/%m/%Y')}. Ano atual: {_hoje_g.year}. Ao chamar criar_agendamento, sempre use o ano {_hoje_g.year} para datas no formato DD/MM. Exemplo: '23/03' → data='2026-03-23'."

# DEPOIS:
from datetime import date as _dt_today_g
from zoneinfo import ZoneInfo as _ZI_ctx_g
_hoje_g = _dt_today_g.today()
_agora_local_ctx_g = datetime.now(_ZI_ctx_g(fuso))   # datetime já importado no topo do arquivo
_agora_fmt_ctx_g = _agora_local_ctx_g.strftime('%d/%m/%Y %H:%M')
_data_ctx_g = (
    f"\n\nDATA E HORA ATUAL: {_agora_fmt_ctx_g}. Ano atual: {_hoje_g.year}."
    f" Ao chamar criar_agendamento, sempre use o ano {_hoje_g.year} para datas no formato DD/MM. Exemplo: '23/03' → data='2026-03-23'."
    f" IMPORTANTE: Só sugira horários de hoje ({_agora_local_ctx_g.strftime('%d/%m/%Y')}) se forem APÓS {_agora_fmt_ctx_g}."
)
```

- [ ] **Step 4: Verificar que o arquivo ainda é válido Python**

```bash
cd leadflow-backend
python -c "import app.routers.agente; print('OK')"
```
Esperado: `OK` (sem erros de sintaxe)

- [ ] **Step 5: Commit**

```bash
git add leadflow-backend/app/routers/agente.py
git commit -m "fix: injetar hora atual no contexto do LLM para evitar sugestão de horários passados"
```

---

## Task 3: Corrigir defaults de _expediente_encerrado (agente.py)

**Files:**
- Modify: `leadflow-backend/app/routers/agente.py` — linhas ~341-342 (OpenAI) e ~602-603 (Gemini)

- [ ] **Step 1: Localizar os dois callsites com grep**

```bash
grep -n "fim_h.*18\|fim_m.*30" leadflow-backend/app/routers/agente.py
```
Esperado: 4 linhas (2 callsites × 2 condições cada)

- [ ] **Step 2: Corrigir OpenAI path (~linha 341)**

Localizar o bloco:
```python
_expediente_encerrado = _pediu_hoje and (
    _agora_local.hour > _hcfg.get("fim_h", 18) or
    (_agora_local.hour == _hcfg.get("fim_h", 18) and _agora_local.minute >= _hcfg.get("fim_m", 30))
)
```

Alterar para:
```python
_expediente_encerrado = _pediu_hoje and (
    _agora_local.hour > _hcfg.get("fim_h", 20) or
    (_agora_local.hour == _hcfg.get("fim_h", 20) and _agora_local.minute >= _hcfg.get("fim_m", 15))
)
```

- [ ] **Step 3: Corrigir Gemini path (~linha 602)**

Localizar o bloco idêntico no Gemini path:
```python
_expediente_encerrado_g = _pediu_hoje_g and (
    _agora_local_g.hour > _hcfg_g.get("fim_h", 18) or
    (_agora_local_g.hour == _hcfg_g.get("fim_h", 18) and _agora_local_g.minute >= _hcfg_g.get("fim_m", 30))
)
```

Alterar para:
```python
_expediente_encerrado_g = _pediu_hoje_g and (
    _agora_local_g.hour > _hcfg_g.get("fim_h", 20) or
    (_agora_local_g.hour == _hcfg_g.get("fim_h", 20) and _agora_local_g.minute >= _hcfg_g.get("fim_m", 15))
)
```

- [ ] **Step 4: Verificar com grep que não sobrou nenhum default 18/30**

```bash
grep -n "fim_h.*18\|fim_m.*30" leadflow-backend/app/routers/agente.py
```
Esperado: 0 linhas

- [ ] **Step 5: Verificar sintaxe**

```bash
python -c "import app.routers.agente; print('OK')"
```
Esperado: `OK`

- [ ] **Step 6: Commit**

```bash
git add leadflow-backend/app/routers/agente.py
git commit -m "fix: corrigir defaults _expediente_encerrado para 20:15 em OpenAI e Gemini paths"
```

---

## Task 4: Salvar mensagens pré-LLM no DB + post-processing "Super te entendo" (agente.py)

**Files:**
- Modify: `leadflow-backend/app/routers/agente.py` — bloco `_eh_passo3` (~linha 1115) e bloco de save (~linha 1212)
- Create: `leadflow-backend/tests/test_agente_fixes.py`

- [ ] **Step 1: Criar testes de deduplicação**

```python
# leadflow-backend/tests/test_agente_fixes.py
import re


def _strip_super_te_entendo(resposta: str) -> str:
    """Replica a lógica de post-processing do agente."""
    return re.sub(
        r'(?i)super te entendo\s*💛?\s*[\n\r]*', '', resposta, count=1
    ).strip()


def test_strip_super_te_entendo_no_inicio():
    resposta = "Super te entendo 💛\n\nAqui estão os horários:\n- 26/03 às 09:00"
    resultado = _strip_super_te_entendo(resposta)
    assert "Super te entendo" not in resultado
    assert "Aqui estão os horários" in resultado


def test_strip_super_te_entendo_case_insensitive():
    resposta = "SUPER TE ENTENDO 💛\n\nTenho disponível:"
    resultado = _strip_super_te_entendo(resposta)
    assert "SUPER TE ENTENDO" not in resultado


def test_strip_nao_remove_se_nao_presente():
    resposta = "Tenho disponível 26/03 às 09:00"
    resultado = _strip_super_te_entendo(resposta)
    assert resultado == resposta


def test_strip_apenas_no_inicio_da_mensagem():
    """Remove apenas quando 'Super te entendo 💛' é seguido de nova linha (início de bloco)."""
    # Com emoji + newline — deve remover
    resposta_com_newline = "Super te entendo 💛\nAqui estão os horários."
    assert "Super te entendo" not in _strip_super_te_entendo(resposta_com_newline)

    # Sem emoji, no meio de uma frase — NÃO deve remover (regex exige \n ou fim de string após)
    resposta_meio = "Olá! Super te entendo como é difícil escolher um horário."
    resultado_meio = _strip_super_te_entendo(resposta_meio)
    assert "Super te entendo como é difícil" in resultado_meio
```

- [ ] **Step 2: Rodar testes**

```bash
cd leadflow-backend
python -m pytest tests/test_agente_fixes.py -v
```
Esperado: 4 PASSED

- [ ] **Step 3: Adicionar save das mensagens pré-LLM no DB**

Localizar o bloco que envia as mensagens pré-LLM (~linha 1115):

```python
# ANTES (apenas envia, não salva):
if _eh_passo3:
    try:
        import asyncio as _aio_pre
        import os as _os_pre
        _evo_url_pre   = config_apis.get("evolution_url", "") or _os_pre.getenv("EVOLUTION_API_URL", "").rstrip("/")
        _evo_key_pre   = config_apis.get("evolution_key", "") or _os_pre.getenv("EVOLUTION_API_KEY", "")
        _evo_inst_pre  = (empresa.get("evolution_instancia") or config_apis.get("evolution_instancia", "")) or _os_pre.getenv("EVOLUTION_INSTANCIA", "")
        if _evo_url_pre and _evo_key_pre and _evo_inst_pre:
            await enviar_mensagem(_evo_url_pre, _evo_key_pre, _evo_inst_pre, numero, "Super te entendo 💛")
            await _aio_pre.sleep(2)
            await enviar_mensagem(_evo_url_pre, _evo_key_pre, _evo_inst_pre, numero,
                "Baseado nisso tudo que você me contou e preencheu no seu formulário, já vejo que faria total sentido você conversar mais de perto com a Rejane. Com certeza ela vai conseguir te ajudar bastante!")
            await _aio_pre.sleep(2)
    except Exception:
        pass
```

Substituir por:

```python
# DEPOIS (envia E salva no DB):
_texto_empatia_pre = "Baseado nisso tudo que você me contou e preencheu no seu formulário, já vejo que faria total sentido você conversar mais de perto com a Rejane. Com certeza ela vai conseguir te ajudar bastante!"
if _eh_passo3:
    try:
        import asyncio as _aio_pre
        import os as _os_pre
        _evo_url_pre   = config_apis.get("evolution_url", "") or _os_pre.getenv("EVOLUTION_API_URL", "").rstrip("/")
        _evo_key_pre   = config_apis.get("evolution_key", "") or _os_pre.getenv("EVOLUTION_API_KEY", "")
        _evo_inst_pre  = (empresa.get("evolution_instancia") or config_apis.get("evolution_instancia", "")) or _os_pre.getenv("EVOLUTION_INSTANCIA", "")
        if _evo_url_pre and _evo_key_pre and _evo_inst_pre:
            await enviar_mensagem(_evo_url_pre, _evo_key_pre, _evo_inst_pre, numero, "Super te entendo 💛")
            await _aio_pre.sleep(2)
            await enviar_mensagem(_evo_url_pre, _evo_key_pre, _evo_inst_pre, numero, _texto_empatia_pre)
            await _aio_pre.sleep(2)
    except Exception:
        pass
    # Salva mensagens pré-LLM no DB para que _super_te_entendo_ja_enviado detecte em turnos futuros.
    # Nota: o save ocorre mesmo se a Evolution API não estava disponível (evo_url/key vazios) —
    # isso é intencional: garante deduplicação independente do estado do WhatsApp.
    try:
        from datetime import timedelta as _td_pre
        _agora_pre_ref = datetime.utcnow()
        sb.table("conversas").insert([
            {
                "empresa_id": empresa_id,
                "telefone":   numero,
                "role":       "assistant",
                "conteudo":   "Super te entendo 💛",
                "criado_em":  (_agora_pre_ref - _td_pre(seconds=4)).isoformat(),
            },
            {
                "empresa_id": empresa_id,
                "telefone":   numero,
                "role":       "assistant",
                "conteudo":   _texto_empatia_pre,
                "criado_em":  (_agora_pre_ref - _td_pre(seconds=3)).isoformat(),
            },
        ]).execute()
    except Exception:
        pass
```

- [ ] **Step 4: Adicionar post-processing da resposta do LLM**

Localizar o bloco de remoção de SLOTS_TOKENS (~linha 1207):

```python
# Localizar esta linha:
_idx_tok = resposta.find("[SLOTS_TOKENS:")
if _idx_tok != -1:
    resposta = resposta[:_idx_tok].strip()
```

Adicionar LOGO APÓS esse bloco:

```python
# Remove "Super te entendo" da resposta do LLM se já foi enviado pré-LLM
if _eh_passo3:
    import re as _re_ste
    resposta = _re_ste.sub(
        r'(?i)super te entendo\s*💛?\s*(\n|$)', '', resposta, count=1
    ).strip()
```

- [ ] **Step 5: Verificar sintaxe**

```bash
python -c "import app.routers.agente; print('OK')"
```
Esperado: `OK`

- [ ] **Step 6: Rodar testes novamente**

```bash
python -m pytest tests/test_agente_fixes.py -v
```
Esperado: 4 PASSED

- [ ] **Step 7: Commit**

```bash
git add leadflow-backend/app/routers/agente.py leadflow-backend/tests/test_agente_fixes.py
git commit -m "fix: salvar mensagens pre-LLM no DB e remover Super te entendo duplicado da resposta"
```

---

## Task 5: Busca de 3 slots por turno com extensão 5→15 dias (agente.py)

**Files:**
- Modify: `leadflow-backend/app/routers/agente.py` — função `_gerar_resposta_openai_com_agenda` (~linhas 321-365) e `_gerar_resposta_gemini_com_agenda` (~linhas 582-638)

- [ ] **Step 1: Adicionar testes de filtro por turno**

Abrir `leadflow-backend/tests/test_agente_fixes.py` e adicionar:

```python
def _filtrar_turno(slots: list[str], turno: str) -> list[str]:
    """Replica a lógica de filtro por turno do agente."""
    resultado = []
    for s in slots:
        try:
            hora = int(s.split(" ")[1].split(":")[0])
        except (IndexError, ValueError):
            continue
        if turno == "manha" and hora < 12:
            resultado.append(s)
        elif turno == "tarde" and 12 <= hora < 17:
            resultado.append(s)
        elif turno == "noite" and hora >= 17:
            resultado.append(s)
    return resultado


def test_filtrar_manha():
    slots = ["26/03/2026 08:00", "26/03/2026 11:00", "26/03/2026 14:00", "26/03/2026 18:00"]
    assert _filtrar_turno(slots, "manha") == ["26/03/2026 08:00", "26/03/2026 11:00"]


def test_filtrar_tarde():
    slots = ["26/03/2026 08:00", "26/03/2026 14:00", "26/03/2026 16:00", "26/03/2026 18:00"]
    assert _filtrar_turno(slots, "tarde") == ["26/03/2026 14:00", "26/03/2026 16:00"]


def test_filtrar_noite():
    slots = ["26/03/2026 08:00", "26/03/2026 14:00", "26/03/2026 17:00", "26/03/2026 19:00"]
    assert _filtrar_turno(slots, "noite") == ["26/03/2026 17:00", "26/03/2026 19:00"]


def test_filtrar_turno_vazio():
    slots = ["26/03/2026 14:00", "26/03/2026 15:00"]
    assert _filtrar_turno(slots, "manha") == []
    assert _filtrar_turno(slots, "noite") == []
```

- [ ] **Step 2: Rodar testes novos**

```bash
python -m pytest tests/test_agente_fixes.py -v
```
Esperado: todos PASSED

- [ ] **Step 3: Implementar _buscar_tres_slots() no agente.py**

Localizar a linha onde começa a chamada a `buscar_horarios_livres` dentro de `_gerar_resposta_openai_com_agenda` (dentro do handler `if tc.function.name == "buscar_horarios_livres":`), aproximadamente linha 344.

Adicionar a função helper **antes** do loop `for _round in range(6):`, logo após as definições de `_passou_fase_inicial`, `_passo3`, etc. (~linha 273):

```python
    async def _buscar_tres_slots_openai() -> list[str]:
        """Busca 1 slot por turno (manhã/tarde/noite) com extensão automática 5→15 dias.
        Retorna lista de até 3 strings no formato 'DD/MM/YYYY HH:MM'."""
        import asyncio as _aio_3s
        _hcfg3 = _horario_cfg or {}
        _slots_tres = []
        for _turno in ("manha", "tarde", "noite"):
            _slot_turno = None
            for _dias_janela in (5, 15):
                _candidatos = await _aio_3s.to_thread(
                    buscar_horarios_livres,
                    credentials_dict=calendar_creds,
                    calendar_id=calendar_id,
                    calendars_verificar=calendars_verificar or [],
                    fuso=fuso,
                    dias=_dias_janela,
                    oauth_creds=oauth_creds,
                    hora_inicio_dia=_hcfg3.get("ini_h", 8),
                    hora_inicio_minuto=_hcfg3.get("ini_m", 0),
                    hora_fim_dia=_hcfg3.get("fim_h", 20),
                    hora_fim_minuto=_hcfg3.get("fim_m", 15),
                )
                for _s in _candidatos:
                    try:
                        _h = int(_s.split(" ")[1].split(":")[0])
                    except (IndexError, ValueError):
                        continue
                    if _turno == "manha" and _h < 12:
                        _slot_turno = _s
                        break
                    elif _turno == "tarde" and 12 <= _h < 17:
                        _slot_turno = _s
                        break
                    elif _turno == "noite" and _h >= 17:
                        _slot_turno = _s
                        break
                if _slot_turno:
                    break  # encontrou nessa janela, não precisa de 15 dias
            if _slot_turno:
                _slots_tres.append(_slot_turno)
        return _slots_tres
```

- [ ] **Step 4: Substituir seleção de slots no handler OpenAI**

Localizar o bloco atual de seleção (~linha 361):

```python
if slots:
    # Seleciona 1 manhã (< 12h) + 1 tarde (12h-17h) + 1 noite (>= 17h)
    _manha = next((s for s in slots if int(s.split(" ")[1].split(":")[0]) < 12), None)
    _tarde = next((s for s in slots if 12 <= int(s.split(" ")[1].split(":")[0]) < 17), None)
    _noite = next((s for s in slots if int(s.split(" ")[1].split(":")[0]) >= 17), None)
    tres = [s for s in [_manha, _tarde, _noite] if s]
```

Substituir **apenas** as 4 linhas internas (mantendo `if slots:` e o código de `linhas` abaixo):

```python
if slots:
    # Busca 1 slot por turno com extensão automática 5→15 dias.
    # Invariante: o guard `if slots:` garante que há pelo menos 1 slot disponível,
    # então o fallback `slots[:3]` nunca será uma lista vazia.
    tres = await _buscar_tres_slots_openai()
    if not tres:
        tres = [s for s in slots[:3]]  # fallback: usa os primeiros slots retornados
```

**Atenção:** o restante do bloco (criação de `linhas`, `token`, `display`, `_var_mapa`) permanece **inalterado**.

- [ ] **Step 5: Adicionar função equivalente para Gemini**

Após `_buscar_tres_slots_openai`, ou diretamente dentro de `_gerar_resposta_gemini_com_agenda` (~após linha 537), adicionar:

```python
    async def _buscar_tres_slots_gemini() -> list[str]:
        """Idêntica à versão OpenAI — busca 1 slot por turno com extensão 5→15 dias."""
        import asyncio as _aio_3sg
        _hcfg3g = _horario_cfg or {}
        _slots_tres_g = []
        for _turno_g in ("manha", "tarde", "noite"):
            _slot_turno_g = None
            for _dias_janela_g in (5, 15):
                _candidatos_g = await _aio_3sg.to_thread(
                    buscar_horarios_livres,
                    credentials_dict=calendar_creds,
                    calendar_id=calendar_id,
                    calendars_verificar=calendars_verificar or [],
                    fuso=fuso,
                    dias=_dias_janela_g,
                    oauth_creds=oauth_creds,
                    hora_inicio_dia=_hcfg3g.get("ini_h", 8),
                    hora_inicio_minuto=_hcfg3g.get("ini_m", 0),
                    hora_fim_dia=_hcfg3g.get("fim_h", 20),
                    hora_fim_minuto=_hcfg3g.get("fim_m", 15),
                )
                for _s_g in _candidatos_g:
                    try:
                        _h_g = int(_s_g.split(" ")[1].split(":")[0])
                    except (IndexError, ValueError):
                        continue
                    if _turno_g == "manha" and _h_g < 12:
                        _slot_turno_g = _s_g
                        break
                    elif _turno_g == "tarde" and 12 <= _h_g < 17:
                        _slot_turno_g = _s_g
                        break
                    elif _turno_g == "noite" and _h_g >= 17:
                        _slot_turno_g = _s_g
                        break
                if _slot_turno_g:
                    break
            if _slot_turno_g:
                _slots_tres_g.append(_slot_turno_g)
        return _slots_tres_g
```

- [ ] **Step 6: Substituir seleção de slots no handler Gemini (~linha 622)**

Localizar:
```python
if slots:
    # Seleciona 1 manhã (< 12h) + 1 tarde (12h-17h) + 1 noite (>= 17h)
    _manha_g = next((s for s in slots if int(s.split(" ")[1].split(":")[0]) < 12), None)
    _tarde_g = next((s for s in slots if 12 <= int(s.split(" ")[1].split(":")[0]) < 17), None)
    _noite_g = next((s for s in slots if int(s.split(" ")[1].split(":")[0]) >= 17), None)
    tres_g = [s for s in [_manha_g, _tarde_g, _noite_g] if s]
```

Substituir pelas 3 primeiras linhas (manter o resto inalterado):
```python
if slots:
    # Busca 1 slot por turno com extensão automática 5→15 dias.
    # Invariante: guard `if slots:` garante fallback sempre não-vazio.
    tres_g = await _buscar_tres_slots_gemini()
    if not tres_g:
        tres_g = [s for s in slots[:3]]  # fallback
```

- [ ] **Step 7: Verificar sintaxe**

```bash
python -c "import app.routers.agente; print('OK')"
```
Esperado: `OK`

- [ ] **Step 8: Rodar todos os testes**

```bash
python -m pytest tests/ -v
```
Esperado: todos PASSED

- [ ] **Step 9: Commit**

```bash
git add leadflow-backend/app/routers/agente.py leadflow-backend/tests/test_agente_fixes.py
git commit -m "feat: buscar 3 slots por turno com extensao automatica 5-15 dias"
```

---

## Task 6: Push para GitHub e redeploy

- [ ] **Step 1: Push backend**

```bash
cd leadflow-backend
git push origin main
```

- [ ] **Step 2: Push frontend (se necessário)**

```bash
cd leadflow-frontend
git push origin main
```

- [ ] **Step 3: Redeploy no Easypanel**
  - Acessar painel Easypanel
  - Redeploy manual do serviço `leadflow-backend`

- [ ] **Step 4: Verificação manual em produção**
  - Testar conversa completa: passo 1 → passo 2 → confirmar desafio → verificar:
    - "Super te entendo" aparece 1x
    - 3 horários exibidos (manhã/tarde/noite) com datas
    - LLM não sugere horários passados de hoje

---

## Resumo das mudanças

| Task | Arquivo | Linhas aproximadas |
|---|---|---|
| 1 | `google_calendar.py` | ~113 (buffer 15→60min) |
| 2 | `agente.py` | ~85 e ~523 (hora atual no contexto) |
| 3 | `agente.py` | ~341 e ~602 (defaults _expediente_encerrado) |
| 4 | `agente.py` | ~1115 (save pré-LLM) + ~1207 (post-process) |
| 5 | `agente.py` | ~273 e ~537 (novas funções) + ~361 e ~622 (substituição) |
