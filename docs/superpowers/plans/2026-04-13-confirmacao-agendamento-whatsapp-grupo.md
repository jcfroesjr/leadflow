# Confirmação de Agendamento via WhatsApp Grupo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enviar confirmação automática de presença no grupo WhatsApp do lead no dia da reunião, processar resposta no grupo e iniciar reagendamento 1-1 se necessário.

**Architecture:** Novo módulo `confirmacao_agendamento.py` (espelhando o padrão de `followup_agenda.py`) com jobs APScheduler, handler de webhook para grupos e recovery de startup. O agente.py recebe três pequenas extensões: branch para mensagens de grupo no webhook, captura do ID do novo agendamento e hook de reagendamento. O frontend recebe nova seção de configuração no card de Agenda/Configurações.

**Tech Stack:** FastAPI, APScheduler (AsyncIOScheduler), Supabase Python SDK, Evolution API (`enviar_mensagem`, `renomear_grupo` — já existem em `app/services/evolution.py`), React + TypeScript.

---

## File Structure

| Arquivo | Ação | Responsabilidade |
|---------|------|-----------------|
| `leadflow-backend/app/routers/confirmacao_agendamento.py` | Criar | Jobs, webhook handler, recovery |
| `leadflow-backend/app/routers/agente.py` | Modificar (3 pontos) | Branch @g.us, captura ID agendamento, hook reagendamento |
| `leadflow-backend/app/main.py` | Modificar | Import + startup hook |
| SQL (executar no Supabase) | Migração | 3 novas colunas em `agendamentos` |
| `leadflow-frontend/src/modules/agenda/AgendaPage.tsx` | Modificar | Nova seção UI Confirmação |

---

## Task 1: SQL Migration

**Files:**
- SQL: executar direto no editor SQL do Supabase

- [ ] **Step 1: Executar migration no Supabase SQL Editor**

```sql
ALTER TABLE agendamentos
  ADD COLUMN IF NOT EXISTS confirmacao_status TEXT DEFAULT 'pendente',
  ADD COLUMN IF NOT EXISTS confirmacao_enviada_em TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS grupo_jid TEXT;

COMMENT ON COLUMN agendamentos.confirmacao_status IS 'pendente | enviada | confirmada | negada | timeout';
COMMENT ON COLUMN agendamentos.grupo_jid IS 'JID do grupo WhatsApp @g.us associado ao lead';
```

- [ ] **Step 2: Verificar colunas criadas**

No Supabase, executar:
```sql
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'agendamentos'
  AND column_name IN ('confirmacao_status', 'confirmacao_enviada_em', 'grupo_jid');
```
Esperado: 3 linhas retornadas.

- [ ] **Step 3: Commit de documentação**

```bash
cd leadflow-backend
git add -A
git commit -m "chore(db): add confirmacao_status, confirmacao_enviada_em, grupo_jid to agendamentos"
```

---

## Task 2: Criar `confirmacao_agendamento.py`

**Files:**
- Create: `leadflow-backend/app/routers/confirmacao_agendamento.py`

Este módulo segue o mesmo padrão de `followup_agenda.py`. Leia `leadflow-backend/app/routers/followup_agenda.py` antes de começar para entender a estrutura.

- [ ] **Step 1: Criar o arquivo com o módulo completo**

```python
"""
Confirmação de agendamento via WhatsApp grupo.

Fluxo:
  1. Ao criar agendamento, agente.py chama agendar_job_confirmacao().
  2. No horário configurado (ex: 08:00 do dia da reunião), job_confirmacao envia
     mensagem de confirmação no grupo @g.us do lead.
  3. Lead responde no grupo → webhook do agente.py chama processar_confirmacao_grupo().
  4. Positivo → envia msg confirmada, cancela timeout job.
     Negativo → envia msg negada, inicia reagendamento 1-1.
  5. Se timeout (sem resposta em X min) → job_timeout inicia reagendamento 1-1.
  6. Ao reagendar via 1-1, agente.py chama on_reagendamento() para atualizar grupo.
  7. Startup: recuperar_confirmacoes_pendentes() recarrega jobs pendentes/enviados.
"""
import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.db.client import get_supabase
from app.services.evolution import enviar_mensagem, renomear_grupo

router = APIRouter(prefix="/confirmacao-agendamento", tags=["confirmacao-agendamento"])

_PALAVRAS_POSITIVO = {"sim", "confirmo", "pode", "estarei", "vou estar", "claro", "com certeza", "ok", "s"}
_EMOJIS_POSITIVO  = {"✅", "👍"}
_PALAVRAS_NEGATIVO = {"não", "nao", "cancelar", "impossível", "impossivel", "n"}
_FRASES_NEGATIVO  = {"não posso", "nao posso"}
_EMOJIS_NEGATIVO  = {"❌", "👎"}


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _limpar_numero(numero: str) -> str:
    """Remove tudo que não é dígito. Para comparação de telefone, não para envio."""
    import re
    return re.sub(r"\D", "", numero)


def _substituir(template: str, nome: str, hora: str, data: str) -> str:
    return (template
            .replace("{nome}", nome)
            .replace("{hora}", hora)
            .replace("{data}", data))


def _get_evo(empresa: dict) -> tuple[str, str, str]:
    """Retorna (url, key, instancia) da empresa."""
    cfg = empresa.get("config_apis") or {}
    url  = (cfg.get("evolution_url") or os.getenv("EVOLUTION_API_URL", "")).rstrip("/")
    key  = cfg.get("evolution_key") or os.getenv("EVOLUTION_API_KEY", "")
    inst = empresa.get("evolution_instancia") or cfg.get("evolution_instancia", "") or os.getenv("EVOLUTION_INSTANCIA", "")
    return url, key, inst


def _classificar_resposta(texto: str) -> str:
    """Retorna 'positivo', 'negativo' ou '' (ignorar)."""
    t = texto.strip().lower()
    # Emojis
    for e in _EMOJIS_POSITIVO:
        if e in texto: return "positivo"
    for e in _EMOJIS_NEGATIVO:
        if e in texto: return "negativo"
    # Frases (multi-palavra antes de palavras isoladas)
    for f in _FRASES_NEGATIVO:
        if f in t: return "negativo"
    # Palavras isoladas (match exato ou início da mensagem)
    palavras = set(t.split())
    if palavras & _PALAVRAS_POSITIVO: return "positivo"
    if palavras & _PALAVRAS_NEGATIVO: return "negativo"
    return ""


# ─── Agendamento de jobs ────────────────────────────────────────────────────────

def agendar_job_confirmacao(agendamento_id: str, inicio_iso: str, empresa_id: str) -> None:
    """
    Agenda job_confirmacao para o horário configurado no dia da reunião.
    Chamado pelo agente.py imediatamente após inserir o agendamento.

    inicio_iso: "YYYY-MM-DDTHH:MM:SS" (horário local da empresa, sem tz suffix).
    """
    from app.scheduler import scheduler
    try:
        sb = get_supabase()
        empresa_res = sb.table("empresas") \
            .select("config_agendamento, fuso") \
            .eq("id", empresa_id).limit(1).execute()
        if not empresa_res.data:
            return
        empresa_data = empresa_res.data[0]
        cfg = empresa_data.get("config_agendamento") or {}

        if not cfg.get("confirmacao_ativa"):
            return

        horario_str = cfg.get("confirmacao_horario", "08:00")  # "HH:MM"
        fuso_nome   = empresa_data.get("fuso") or "America/Sao_Paulo"

        import pytz
        fuso = pytz.timezone(fuso_nome)

        # Data da reunião (sem hora) + horário de confirmação
        data_reuniao = datetime.fromisoformat(inicio_iso).date()
        hora_h, hora_m = [int(x) for x in horario_str.split(":")]
        run_local = datetime(data_reuniao.year, data_reuniao.month, data_reuniao.day,
                             hora_h, hora_m, 0)
        run_local_aware = fuso.localize(run_local)
        run_utc = run_local_aware.astimezone(timezone.utc).replace(tzinfo=None)

        now_utc = datetime.utcnow()
        if run_utc <= now_utc:
            print(f"[CONFIRMACAO] horário de confirmação {horario_str} já passou para agendamento {agendamento_id} — pulando")
            return

        job_id = f"conf_{agendamento_id}"
        scheduler.add_job(
            _executar_confirmacao_job,
            "date",
            run_date=run_utc,
            args=[agendamento_id],
            id=job_id,
            replace_existing=True,
            timezone="UTC",
        )
        print(f"[CONFIRMACAO] job agendado para {run_utc.isoformat()} | agendamento={agendamento_id}")
    except Exception as e:
        print(f"[CONFIRMACAO] erro ao agendar job: {e}")


# ─── Jobs executados pelo APScheduler ──────────────────────────────────────────

async def _executar_confirmacao_job(agendamento_id: str) -> None:
    """Envia mensagem de confirmação no grupo e agenda o timeout job."""
    try:
        sb = get_supabase()

        # Busca agendamento + lead
        ag_res = sb.table("agendamentos") \
            .select("empresa_id, lead_id, grupo_jid, inicio, confirmacao_status") \
            .eq("id", agendamento_id).limit(1).execute()
        if not ag_res.data:
            print(f"[CONFIRMACAO] agendamento {agendamento_id} não encontrado")
            return
        ag = ag_res.data[0]

        if ag.get("confirmacao_status") != "pendente":
            print(f"[CONFIRMACAO] agendamento {agendamento_id} não está pendente — ignorando")
            return

        grupo_jid = ag.get("grupo_jid")
        if not grupo_jid:
            print(f"[CONFIRMACAO] agendamento {agendamento_id} sem grupo_jid — pulando")
            return

        empresa_id = ag["empresa_id"]

        # Lead: nome e telefone
        lead_res = sb.table("leads") \
            .select("nome, telefone") \
            .eq("id", ag["lead_id"]).limit(1).execute()
        if not lead_res.data:
            return
        lead = lead_res.data[0]
        nome      = (lead.get("nome") or "").split()[0]
        telefone  = lead.get("telefone", "")

        # Config empresa
        emp_res = sb.table("empresas") \
            .select("config_agendamento, config_apis, evolution_instancia") \
            .eq("id", empresa_id).limit(1).execute()
        if not emp_res.data:
            return
        empresa = emp_res.data[0]
        cfg = empresa.get("config_agendamento") or {}

        if not cfg.get("confirmacao_ativa"):
            return

        # Hora/data da reunião formatadas
        inicio_dt = datetime.fromisoformat(ag["inicio"].replace("Z", "").split("+")[0])
        hora_fmt = inicio_dt.strftime("%H:%M")
        data_fmt = inicio_dt.strftime("%d/%m/%Y")

        mensagem_conf = _substituir(
            cfg.get("confirmacao_mensagem",
                    "Olá {nome}! Confirmando sua reunião hoje às {hora}. Você confirma presença? ✅ Sim / ❌ Não"),
            nome, hora_fmt, data_fmt,
        )

        evo_url, evo_key, evo_inst = _get_evo(empresa)
        if not all([evo_url, evo_key, evo_inst]):
            print(f"[CONFIRMACAO] Evolution não configurada para empresa {empresa_id}")
            return

        await enviar_mensagem(evo_url, evo_key, evo_inst, grupo_jid, mensagem_conf)

        now_iso = datetime.utcnow().isoformat()
        sb.table("agendamentos").update({
            "confirmacao_status":    "enviada",
            "confirmacao_enviada_em": now_iso,
        }).eq("id", agendamento_id).execute()

        # Agenda timeout
        timeout_min = int(cfg.get("confirmacao_timeout_min", 120))
        run_timeout = datetime.utcnow() + timedelta(minutes=timeout_min)
        from app.scheduler import scheduler
        scheduler.add_job(
            _executar_timeout_job,
            "date",
            run_date=run_timeout,
            args=[agendamento_id],
            id=f"conf_timeout_{agendamento_id}",
            replace_existing=True,
            timezone="UTC",
        )
        print(f"[CONFIRMACAO] mensagem enviada ao grupo {grupo_jid}, timeout em {timeout_min}min")
    except Exception as e:
        print(f"[CONFIRMACAO] erro no job de confirmação {agendamento_id}: {e}")


async def _executar_timeout_job(agendamento_id: str) -> None:
    """Disparado quando lead não respondeu. Inicia reagendamento 1-1."""
    try:
        sb = get_supabase()
        ag_res = sb.table("agendamentos") \
            .select("empresa_id, lead_id, grupo_jid, inicio, confirmacao_status") \
            .eq("id", agendamento_id).limit(1).execute()
        if not ag_res.data:
            return
        ag = ag_res.data[0]

        if ag.get("confirmacao_status") != "enviada":
            # Lead já respondeu — não fazer nada
            return

        sb.table("agendamentos").update({"confirmacao_status": "timeout"}) \
            .eq("id", agendamento_id).execute()

        await _iniciar_reagendamento_1_1(ag, sb, motivo="timeout")
    except Exception as e:
        print(f"[CONFIRMACAO] erro no timeout job {agendamento_id}: {e}")


async def _iniciar_reagendamento_1_1(ag: dict, sb, motivo: str) -> None:
    """Envia msg negada no grupo + injeta contexto + abre conversa privada."""
    try:
        empresa_id = ag["empresa_id"]
        grupo_jid  = ag.get("grupo_jid")
        inicio_dt  = datetime.fromisoformat(ag["inicio"].replace("Z", "").split("+")[0])
        hora_fmt   = inicio_dt.strftime("%H:%M")
        data_fmt   = inicio_dt.strftime("%d/%m/%Y")

        lead_res = sb.table("leads") \
            .select("nome, telefone") \
            .eq("id", ag["lead_id"]).limit(1).execute()
        if not lead_res.data:
            return
        lead     = lead_res.data[0]
        nome     = (lead.get("nome") or "").split()[0]
        telefone = lead.get("telefone", "")

        emp_res = sb.table("empresas") \
            .select("config_agendamento, config_apis, evolution_instancia") \
            .eq("id", empresa_id).limit(1).execute()
        if not emp_res.data:
            return
        empresa = emp_res.data[0]
        cfg = empresa.get("config_agendamento") or {}

        evo_url, evo_key, evo_inst = _get_evo(empresa)

        # 1. Envia msg negada no grupo
        if grupo_jid and all([evo_url, evo_key, evo_inst]):
            msg_negada = _substituir(
                cfg.get("confirmacao_msg_negativa",
                        "Sem problemas! Iremos te enviar no privado novos horários de agendamento. "
                        "Caso queira marcar, é só escolher o horário 😉"),
                nome, hora_fmt, data_fmt,
            )
            await enviar_mensagem(evo_url, evo_key, evo_inst, grupo_jid, msg_negada)

        # 2. Injeta contexto de reagendamento em conversas do lead (1-1)
        sb.table("conversas").insert({
            "empresa_id": empresa_id,
            "telefone":   telefone,
            "role":       "sistema",
            "conteudo":   (f"[SISTEMA: Lead não confirmou presença na reunião de {data_fmt} às {hora_fmt}. "
                           "Inicie reagendamento: apresente-se cordialmente, explique a situação e ofereça novos slots.]"),
            "criado_em":  datetime.utcnow().isoformat(),
        }).execute()

        # 3. Abre conversa privada com o lead
        if all([evo_url, evo_key, evo_inst]):
            msg_privada = _substituir(
                cfg.get("confirmacao_msg_abertura_privado",
                        "Oi {nome}! Vi que não conseguimos confirmar sua reunião de {data} às {hora}. "
                        "Posso te oferecer novos horários?"),
                nome, hora_fmt, data_fmt,
            )
            destino_privado = f"{telefone}@s.whatsapp.net" if "@" not in telefone else telefone
            await enviar_mensagem(evo_url, evo_key, evo_inst, destino_privado, msg_privada)

        print(f"[CONFIRMACAO] reagendamento 1-1 iniciado para {telefone} ({motivo})")
    except Exception as e:
        print(f"[CONFIRMACAO] erro ao iniciar reagendamento 1-1: {e}")


# ─── Handler chamado pelo webhook do agente.py ─────────────────────────────────

async def processar_confirmacao_grupo(
    grupo_jid: str,
    key: dict,
    body: dict,
    empresa_id: str,
    sb,
) -> None:
    """
    Chamado pelo webhook de agente.py quando chega mensagem de grupo (@g.us).
    Verifica se é resposta de confirmação de agendamento e age conforme classificação.
    """
    try:
        # 1. Remetente real do grupo
        participant = key.get("participant", "")
        if not participant:
            return

        # 2. Extrai texto
        data = body.get("data", {})
        texto = (
            data.get("message", {}).get("conversation")
            or data.get("message", {}).get("extendedTextMessage", {}).get("text")
            or ""
        ).strip()
        if not texto:
            return  # sticker, imagem, reação — ignorar

        # 3. Busca agendamento ativo com confirmacao_status='enviada' para este grupo
        ag_res = sb.table("agendamentos") \
            .select("id, empresa_id, lead_id, inicio, grupo_jid") \
            .eq("empresa_id", empresa_id) \
            .eq("grupo_jid", grupo_jid) \
            .eq("confirmacao_status", "enviada") \
            .neq("status", "cancelado") \
            .limit(1).execute()
        if not ag_res.data:
            return
        ag = ag_res.data[0]

        # 4. Verifica se remetente é o lead (normaliza para dígitos)
        lead_res = sb.table("leads") \
            .select("telefone") \
            .eq("id", ag["lead_id"]).limit(1).execute()
        if not lead_res.data:
            return
        telefone_lead = lead_res.data[0].get("telefone", "")

        import re as _re
        p_digits = _re.sub(r"\D", "", participant)
        t_digits = _re.sub(r"\D", "", telefone_lead)

        # Aceita correspondência parcial: o número do lead pode ter 12 dígitos (com DDI)
        # e o participant pode ter 13 (com 9 extra) ou vice-versa.
        if not (p_digits.endswith(t_digits) or t_digits.endswith(p_digits)):
            return

        # 5. Classifica resposta
        classificacao = _classificar_resposta(texto)
        if not classificacao:
            return

        agendamento_id = ag["id"]
        from app.scheduler import scheduler

        if classificacao == "positivo":
            sb.table("agendamentos").update({"confirmacao_status": "confirmada"}) \
                .eq("id", agendamento_id).execute()

            # Cancela timeout job
            try: scheduler.remove_job(f"conf_timeout_{agendamento_id}")
            except Exception: pass

            # Busca config para mensagem positiva
            emp_res = sb.table("empresas") \
                .select("config_agendamento, config_apis, evolution_instancia") \
                .eq("id", empresa_id).limit(1).execute()
            if emp_res.data:
                empresa = emp_res.data[0]
                cfg = empresa.get("config_agendamento") or {}
                inicio_dt = datetime.fromisoformat(ag["inicio"].replace("Z", "").split("+")[0])
                lead2 = sb.table("leads").select("nome").eq("id", ag["lead_id"]).limit(1).execute()
                nome = ((lead2.data[0].get("nome") or "").split()[0]) if lead2.data else ""
                msg_pos = _substituir(
                    cfg.get("confirmacao_msg_positiva", "Perfeito! Te esperamos às {hora} 😊"),
                    nome, inicio_dt.strftime("%H:%M"), inicio_dt.strftime("%d/%m/%Y"),
                )
                evo_url, evo_key, evo_inst = _get_evo(empresa)
                if all([evo_url, evo_key, evo_inst]):
                    await enviar_mensagem(evo_url, evo_key, evo_inst, grupo_jid, msg_pos)
            print(f"[CONFIRMACAO] lead confirmou presença — agendamento {agendamento_id}")

        elif classificacao == "negativo":
            sb.table("agendamentos").update({"confirmacao_status": "negada"}) \
                .eq("id", agendamento_id).execute()

            try: scheduler.remove_job(f"conf_timeout_{agendamento_id}")
            except Exception: pass

            await _iniciar_reagendamento_1_1(ag, sb, motivo="negativo")
            print(f"[CONFIRMACAO] lead negou presença — agendamento {agendamento_id}")

    except Exception as e:
        print(f"[CONFIRMACAO] erro ao processar mensagem de grupo: {e}")


# ─── Recovery de startup ────────────────────────────────────────────────────────

async def recuperar_confirmacoes_pendentes() -> None:
    """
    Chamado no startup: recarrega jobs de confirmação que ainda precisam disparar.
    Cobre dois cenários:
      - status='pendente': confirmação ainda não enviada, mas reunião ainda no futuro
      - status='enviada': confirmação enviada, timeout job pode não ter sido agendado
    """
    try:
        from app.scheduler import scheduler
        sb = get_supabase()
        now_iso = datetime.utcnow().isoformat()

        # ── Pendentes: recriar job_confirmacao ──────────────────────────────────
        pend_res = sb.table("agendamentos") \
            .select("id, empresa_id, inicio, grupo_jid") \
            .eq("confirmacao_status", "pendente") \
            .gt("inicio", now_iso) \
            .neq("status", "cancelado") \
            .execute()

        for ag in (pend_res.data or []):
            if not ag.get("grupo_jid"):
                continue
            job_id = f"conf_{ag['id']}"
            if scheduler.get_job(job_id):
                continue  # já existe
            agendar_job_confirmacao(ag["id"], ag["inicio"], ag["empresa_id"])
            print(f"[CONFIRMACAO] recovery: reagendado conf job para agendamento {ag['id']}")

        # ── Enviadas: recriar timeout job se ainda no futuro ────────────────────
        env_res = sb.table("agendamentos") \
            .select("id, empresa_id, confirmacao_enviada_em") \
            .eq("confirmacao_status", "enviada") \
            .neq("status", "cancelado") \
            .execute()

        for ag in (env_res.data or []):
            empresa_id = ag["empresa_id"]
            enviada_em_str = ag.get("confirmacao_enviada_em")
            if not enviada_em_str:
                continue

            # Busca timeout_min da config da empresa
            emp_res = sb.table("empresas") \
                .select("config_agendamento") \
                .eq("id", empresa_id).limit(1).execute()
            if not emp_res.data:
                continue
            cfg = emp_res.data[0].get("config_agendamento") or {}
            timeout_min = int(cfg.get("confirmacao_timeout_min", 120))

            enviada_em = datetime.fromisoformat(enviada_em_str.replace("Z", "").split("+")[0])
            run_timeout = enviada_em + timedelta(minutes=timeout_min)

            if run_timeout <= datetime.utcnow():
                # Já passou — disparar imediatamente em background
                from asyncio import ensure_future
                ensure_future(_executar_timeout_job(ag["id"]))
                continue

            job_id = f"conf_timeout_{ag['id']}"
            if scheduler.get_job(job_id):
                continue
            scheduler.add_job(
                _executar_timeout_job,
                "date",
                run_date=run_timeout,
                args=[ag["id"]],
                id=job_id,
                replace_existing=True,
                timezone="UTC",
            )
            print(f"[CONFIRMACAO] recovery: timeout job reagendado para agendamento {ag['id']}")

    except Exception as e:
        print(f"[CONFIRMACAO] erro no recovery: {e}")


# ─── Hook chamado pelo agente.py ao criar novo agendamento via 1-1 ──────────────

async def on_reagendamento(
    novo_agendamento_id: str,
    novo_inicio_iso: str,
    empresa_id: str,
    lead_id_ag: str,
    numero: str,
    nome_lead: str,
    sb,
) -> None:
    """
    Chamado pelo agente.py após criar novo agendamento quando o lead tinha
    agendamento anterior com confirmacao_status 'negada' ou 'timeout'.

    - Cancela agendamentos anteriores problemáticos
    - Remove jobs antigos do scheduler
    - Renomeia grupo WhatsApp com nova data
    - Injeta mensagem de sistema de reagendamento concluído
    - Agenda novo job de confirmação
    """
    try:
        from app.scheduler import scheduler

        # Busca agendamentos anteriores do mesmo lead
        ant_res = sb.table("agendamentos") \
            .select("id, grupo_jid") \
            .eq("empresa_id", empresa_id) \
            .eq("lead_id", lead_id_ag) \
            .in_("confirmacao_status", ["negada", "timeout"]) \
            .neq("status", "cancelado") \
            .execute()

        if not ant_res.data:
            # Nenhum agendamento anterior — apenas agenda confirmação para o novo
            agendar_job_confirmacao(novo_agendamento_id, novo_inicio_iso, empresa_id)
            return

        novo_dt      = datetime.fromisoformat(novo_inicio_iso)
        nova_hora    = novo_dt.strftime("%H:%M")
        nova_data    = novo_dt.strftime("%d/%m/%Y")
        novo_nome_g  = f"Reunião - {nome_lead} - {nova_data}"

        # Config Evolution
        emp_res = sb.table("empresas") \
            .select("config_apis, evolution_instancia") \
            .eq("id", empresa_id).limit(1).execute()
        empresa = emp_res.data[0] if emp_res.data else {}
        evo_url, evo_key, evo_inst = _get_evo(empresa)

        for ag_ant in ant_res.data:
            ant_id    = ag_ant["id"]
            ant_grupo = ag_ant.get("grupo_jid")

            # Cancela agendamento antigo
            sb.table("agendamentos").update({"status": "cancelado"}) \
                .eq("id", ant_id).execute()

            # Remove jobs do scheduler
            for jid in [f"conf_{ant_id}", f"conf_timeout_{ant_id}"]:
                try: scheduler.remove_job(jid)
                except Exception: pass

            # Renomeia grupo com nova data
            if ant_grupo and all([evo_url, evo_key, evo_inst]):
                await renomear_grupo(evo_url, evo_key, evo_inst, ant_grupo, novo_nome_g)

        # Injeta contexto de reagendamento concluído (append-only em conversas)
        sb.table("conversas").insert({
            "empresa_id": empresa_id,
            "telefone":   numero,
            "role":       "sistema",
            "conteudo":   (f"[SISTEMA: Reagendamento concluído. Nova reunião em {nova_data} às {nova_hora}. "
                           "Fluxo de confirmação reiniciado.]"),
            "criado_em":  datetime.utcnow().isoformat(),
        }).execute()

        # Agenda confirmação para o novo agendamento
        agendar_job_confirmacao(novo_agendamento_id, novo_inicio_iso, empresa_id)
        print(f"[CONFIRMACAO] reagendamento concluído — novo agendamento {novo_agendamento_id}")

    except Exception as e:
        print(f"[CONFIRMACAO] erro em on_reagendamento: {e}")


# ─── Endpoint de debug ──────────────────────────────────────────────────────────

@router.post("/recovery")
async def forcar_recovery():
    """Força recarregamento dos jobs pendentes (debug/admin)."""
    try:
        await recuperar_confirmacoes_pendentes()
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"ok": False, "erro": str(e)}, status_code=500)
```

- [ ] **Step 2: Verificar imports necessários (`pytz` já está no projeto)**

```bash
cd leadflow-backend
grep -r "pytz" requirements.txt
```

Se não estiver, adicionar ao `requirements.txt`:
```
pytz
```
E rodar `pip install pytz`.

- [ ] **Step 3: Commit**

```bash
cd leadflow-backend
git add app/routers/confirmacao_agendamento.py
git commit -m "feat(backend): add confirmacao_agendamento module with APScheduler jobs and group webhook handler"
```

---

## Task 3: Agente.py — Branch de Grupos no Webhook

**Files:**
- Modify: `leadflow-backend/app/routers/agente.py:1268-1271`

Inserir o branch `@g.us` **após** a linha 1268 (`return {"ok": True, "ignorado": True, "motivo": "fromMe"}`) e **antes** da linha 1271 (`numero_remoto = key.get("remoteJid", "")`).

- [ ] **Step 1: Localizar o ponto exato de inserção**

Abrir `agente.py` e confirmar que a linha 1268 termina com:
```python
        return {"ok": True, "ignorado": True, "motivo": "fromMe"}
```
E a linha 1271 começa com:
```python
    numero_remoto = key.get("remoteJid", "")
```

- [ ] **Step 2: Inserir o branch após a linha 1268**

Adicionar imediatamente após `return {"ok": True, "ignorado": True, "motivo": "fromMe"}`:

```python
    # Mensagens de grupo (@g.us) — processa confirmação de agendamento
    # NOTA: empresa_id e sb NÃO estão em scope aqui (resolvidos mais adiante no webhook).
    # Fazemos lookup direto filtrando por evolution_instancia — mais eficiente que full scan.
    _remoto_raw = key.get("remoteJid", "")
    if _remoto_raw.endswith("@g.us"):
        try:
            from app.routers.confirmacao_agendamento import processar_confirmacao_grupo
            _inst_g = payload.get("instance", "")
            _sb_g   = get_supabase()
            # Busca empresa pelo instancia diretamente (evita full table scan)
            _emp_g_res = _sb_g.table("empresas") \
                .select("id") \
                .eq("evolution_instancia", _inst_g) \
                .limit(1).execute()
            if not _emp_g_res.data:
                # Fallback: instancia pode estar em config_apis
                _emp_g_all = _sb_g.table("empresas") \
                    .select("id, evolution_instancia, config_apis") \
                    .execute()
                _emp_g_id = next(
                    (e["id"] for e in (_emp_g_all.data or [])
                     if (e.get("evolution_instancia") or (e.get("config_apis") or {}).get("evolution_instancia", "")).lower() == _inst_g.lower()),
                    None,
                )
            else:
                _emp_g_id = _emp_g_res.data[0]["id"]
            if _emp_g_id:
                await processar_confirmacao_grupo(_remoto_raw, key, payload, _emp_g_id, _sb_g)
        except Exception as _e_grupo_conf:
            print(f"[CONFIRMACAO] erro ao processar mensagem de grupo: {_e_grupo_conf}")
        return {"status": "ok", "grupo": True}
```

- [ ] **Step 3: Verificar que `get_supabase` já está importado no topo de `agente.py`**

```bash
grep -n "from app.db.client import\|get_supabase" leadflow-backend/app/routers/agente.py | head -5
```

Esperado: linha com `get_supabase` no topo do arquivo.

- [ ] **Step 4: Commit**

```bash
cd leadflow-backend
git add app/routers/agente.py
git commit -m "feat(agente): add @g.us webhook branch for group confirmation processing"
```

---

## Task 4: Agente.py — Captura ID do Agendamento e Agenda Confirmação

**Files:**
- Modify: `leadflow-backend/app/routers/agente.py:2471-2486`

O insert em `agendamentos` está em torno das linhas 2475-2484. Precisa de 3 mudanças:
1. Buscar `grupo_jid` antes do insert
2. Adicionar `grupo_jid` no dict do insert
3. Capturar o ID retornado e chamar `agendar_job_confirmacao`

- [ ] **Step 1: Localizar o bloco do insert em `agendamentos`**

```bash
grep -n "agendamentos.*insert\|\"grupo_jid\"\|_ag_result\|_novo_agendamento" leadflow-backend/app/routers/agente.py | head -10
```

Confirmar que o insert está em `if lead_id_ag and _inicio_iso:` (linha ~2471).

- [ ] **Step 2: Substituir o bloco do insert**

Encontrar:
```python
            if lead_id_ag and _inicio_iso:
                _duracao_ag = int(config_apis.get("duracao_reuniao_minutos", 60))
                from datetime import timedelta as _td_ag
                _fim_iso_ag = (datetime.strptime(_inicio_iso, "%Y-%m-%dT%H:%M:%S") + _td_ag(minutes=_duracao_ag)).isoformat()
                sb.table("agendamentos").insert({
                    "empresa_id":   empresa_id,
                    "lead_id":      lead_id_ag,
                    "plataforma":   "google",
                    "status":       "confirmado",
                    "inicio":       _inicio_iso,
                    "fim":          _fim_iso_ag,
                    "evento_id":    _evento_criado[0],
                    "link_reuniao": "",
                }).execute()
```

Substituir por:
```python
            if lead_id_ag and _inicio_iso:
                _duracao_ag = int(config_apis.get("duracao_reuniao_minutos", 60))
                from datetime import timedelta as _td_ag
                _fim_iso_ag = (datetime.strptime(_inicio_iso, "%Y-%m-%dT%H:%M:%S") + _td_ag(minutes=_duracao_ag)).isoformat()

                # Busca JID do grupo do lead (GRUPO_WA_ID no conversas)
                _grupo_row_ag = sb.table("conversas") \
                    .select("conteudo") \
                    .eq("empresa_id", empresa_id) \
                    .eq("telefone", numero) \
                    .eq("role", "sistema") \
                    .like("conteudo", "GRUPO_WA_ID:%") \
                    .limit(1).execute()
                _grupo_jid_ag = None
                if _grupo_row_ag.data:
                    _grupo_jid_ag = _grupo_row_ag.data[0]["conteudo"].split("GRUPO_WA_ID:")[1].strip()

                _ag_insert_res = sb.table("agendamentos").insert({
                    "empresa_id":   empresa_id,
                    "lead_id":      lead_id_ag,
                    "plataforma":   "google",
                    "status":       "confirmado",
                    "inicio":       _inicio_iso,
                    "fim":          _fim_iso_ag,
                    "evento_id":    _evento_criado[0],
                    "link_reuniao": "",
                    "grupo_jid":    _grupo_jid_ag,
                }).execute()

                _novo_agendamento_id = (_ag_insert_res.data[0]["id"]
                                        if _ag_insert_res.data else None)

                # Agenda confirmação se ativada
                # on_reagendamento também cancela agendamentos anteriores (negada/timeout)
                # independente de haver grupo no novo agendamento.
                if _novo_agendamento_id and config_agendamento.get("confirmacao_ativa", False):
                    try:
                        from app.routers.confirmacao_agendamento import on_reagendamento
                        await on_reagendamento(
                            _novo_agendamento_id,
                            _inicio_iso,
                            empresa_id,
                            lead_id_ag,
                            numero,
                            lead.get("nome", ""),
                            sb,
                        )
                    except Exception as _e_conf_ag:
                        print(f"[CONFIRMACAO] erro ao processar confirmação pós-agendamento: {_e_conf_ag}")
```

**Observação:** `on_reagendamento` já chama `agendar_job_confirmacao` internamente para o novo agendamento. Não chamar `agendar_job_confirmacao` separadamente.

- [ ] **Step 3: Verificar que `config_agendamento` está acessível neste escopo**

```bash
grep -n "config_agendamento" leadflow-backend/app/routers/agente.py | grep -v "#" | head -5
```

Confirmar que `config_agendamento = empresa.get("config_agendamento") or {}` aparece antes da linha 2471.

- [ ] **Step 4: Verificar que `lead` (dict) está acessível neste escopo**

```bash
grep -n "^    lead = \|^        lead = " leadflow-backend/app/routers/agente.py | head -5
```

`lead` é o dict do lead atual. Se não estiver disponível neste escopo (bloco aninhado), usar `lead_atual.data[0]` que já é buscado na linha 2447.

- [ ] **Step 5: Commit**

```bash
cd leadflow-backend
git add app/routers/agente.py
git commit -m "feat(agente): capture agendamento ID, lookup grupo_jid, schedule confirmation on booking"
```

---

## Task 5: Main.py — Registrar Router e Startup Hook

**Files:**
- Modify: `leadflow-backend/app/main.py`

- [ ] **Step 1: Adicionar import do router e do recovery no topo de `main.py`**

Localizar a linha:
```python
from app.routers import webhook, leads, configuracoes, agente, agenda, agendamentos, followup, documentos, followup_agenda, noshow_check, warmup_grupo, conversas, whatsapp
```

Substituir por:
```python
from app.routers import webhook, leads, configuracoes, agente, agenda, agendamentos, followup, documentos, followup_agenda, noshow_check, warmup_grupo, conversas, whatsapp, confirmacao_agendamento
```

- [ ] **Step 2: Adicionar chamada de recovery no startup**

Localizar o bloco de startup (após `scheduler.start()` e após os outros `await recuperar_*`):
```python
    await recuperar_notificacoes_pendentes()
```

Adicionar após essa linha:
```python
    from app.routers.confirmacao_agendamento import recuperar_confirmacoes_pendentes
    await recuperar_confirmacoes_pendentes()
```

- [ ] **Step 3: Registrar o router**

Após as outras linhas `app.include_router(...)`, adicionar:
```python
app.include_router(confirmacao_agendamento.router)
```

- [ ] **Step 4: Verificar que não há erro de import**

```bash
cd leadflow-backend
python -c "from app.main import app; print('OK')"
```

Esperado: `OK` sem erros.

- [ ] **Step 5: Commit**

```bash
cd leadflow-backend
git add app/main.py
git commit -m "feat(backend): register confirmacao_agendamento router and startup recovery"
```

---

## Task 6: Frontend — Nova Seção de Configuração

**Files:**
- Modify: `leadflow-frontend/src/modules/agenda/AgendaPage.tsx`

A seção vai entre o card "Aquecimento de grupo WhatsApp" (linha ~622) e o card "Notificações pré-reunião (grupo)" (linha ~632 após o reorder buttons já inseridos).

- [ ] **Step 1: Atualizar o tipo do estado `config` para incluir os campos novos**

Localizar o `useState` de `config` no componente `AbaConfig` (em torno da linha 372):

```typescript
const [config, setConfig] = useState<{
  followups_agenda: { delay_minutos: number; mensagem: string }[]
  grupo_aquecimento: { delay_minutos: number; tipo: string; conteudo: string; imagem_url?: string; legenda?: string }[]
  grupo_notificacoes: { delay_minutos: number; mensagem: string; tipo?: string; imagem_url?: string; legenda?: string }[]
}>({
  followups_agenda: [],
  grupo_aquecimento: [],
  grupo_notificacoes: [],
})
```

Adicionar os novos campos ao tipo e ao valor inicial:

```typescript
const [config, setConfig] = useState<{
  followups_agenda: { delay_minutos: number; mensagem: string }[]
  grupo_aquecimento: { delay_minutos: number; tipo: string; conteudo: string; imagem_url?: string; legenda?: string }[]
  grupo_notificacoes: { delay_minutos: number; mensagem: string; tipo?: string; imagem_url?: string; legenda?: string }[]
  confirmacao_ativa: boolean
  confirmacao_horario: string
  confirmacao_timeout_min: number
  confirmacao_mensagem: string
  confirmacao_msg_positiva: string
  confirmacao_msg_negativa: string
  confirmacao_msg_abertura_privado: string
}>({
  followups_agenda: [],
  grupo_aquecimento: [],
  grupo_notificacoes: [],
  confirmacao_ativa: false,
  confirmacao_horario: '08:00',
  confirmacao_timeout_min: 120,
  confirmacao_mensagem: 'Olá {nome}! Confirmando sua reunião hoje às {hora}. Você confirma presença? ✅ Sim / ❌ Não',
  confirmacao_msg_positiva: 'Perfeito! Te esperamos às {hora} 😊',
  confirmacao_msg_negativa: 'Sem problemas! Iremos te enviar no privado novos horários de agendamento. Caso queira marcar, é só escolher o horário 😉',
  confirmacao_msg_abertura_privado: 'Oi {nome}! Vi que não conseguimos confirmar sua reunião de {data} às {hora}. Posso te oferecer novos horários?',
})
```

- [ ] **Step 2: Atualizar `fetchConfig` para popular os novos campos**

Localizar o bloco onde `config_agendamento` é lido (em torno da linha 428-445):

```typescript
if (data?.config_agendamento) {
  const raw = data.config_agendamento
  setConfig(c => ({
    ...c,
    grupo_aquecimento:  normalizeAquecimento(raw.grupo_aquecimento),
    ...
  }))
}
```

Adicionar dentro do `setConfig`:
```typescript
    confirmacao_ativa:                raw.confirmacao_ativa ?? false,
    confirmacao_horario:              raw.confirmacao_horario ?? '08:00',
    confirmacao_timeout_min:          raw.confirmacao_timeout_min ?? 120,
    confirmacao_mensagem:             raw.confirmacao_mensagem ?? 'Olá {nome}! Confirmando sua reunião hoje às {hora}. Você confirma presença? ✅ Sim / ❌ Não',
    confirmacao_msg_positiva:         raw.confirmacao_msg_positiva ?? 'Perfeito! Te esperamos às {hora} 😊',
    confirmacao_msg_negativa:         raw.confirmacao_msg_negativa ?? 'Sem problemas! Iremos te enviar no privado novos horários de agendamento. Caso queira marcar, é só escolher o horário 😉',
    confirmacao_msg_abertura_privado: raw.confirmacao_msg_abertura_privado ?? 'Oi {nome}! Vi que não conseguimos confirmar sua reunião de {data} às {hora}. Posso te oferecer novos horários?',
```

- [ ] **Step 3: Adicionar o Switch component nos imports (se não existir)**

```bash
grep -n "Switch\|toggle\|Toggle" leadflow-frontend/src/modules/agenda/AgendaPage.tsx
```

Se não existir, adicionar ao import dos componentes:
```typescript
import { Switch } from '@/components/ui/switch'
```

Se `Switch` não existir em `@/components/ui/switch`, usar uma alternativa: `<input type="checkbox">` estilizado como toggle, ou verificar quais componentes UI existem:
```bash
ls leadflow-frontend/src/components/ui/
```

- [ ] **Step 4: Inserir o card "Confirmação de Agendamento" entre Aquecimento e Notificações**

Localizar o comentário `{/* Notificações pré-reunião do grupo */}` e inserir o card antes dele:

```tsx
      {/* Confirmação de Agendamento */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-sm">Confirmação de Agendamento</CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Envia mensagem de confirmação no grupo WhatsApp no dia da reunião
              </CardDescription>
            </div>
            <Switch
              checked={config.confirmacao_ativa}
              onCheckedChange={v => setConfig(c => ({ ...c, confirmacao_ativa: v }))}
            />
          </div>
        </CardHeader>
        {config.confirmacao_ativa && (
          <CardContent className="space-y-4">
            <div className="flex gap-3">
              <div className="space-y-1">
                <label className="text-[10px] text-muted-foreground">Horário de envio</label>
                <Input type="time" value={config.confirmacao_horario} className="h-7 text-xs w-28"
                  onChange={e => setConfig(c => ({ ...c, confirmacao_horario: e.target.value }))} />
              </div>
              <div className="space-y-1">
                <label className="text-[10px] text-muted-foreground">Timeout sem resposta (min)</label>
                <Input type="number" value={config.confirmacao_timeout_min} className="h-7 text-xs w-24"
                  onChange={e => setConfig(c => ({ ...c, confirmacao_timeout_min: Number(e.target.value) }))} />
              </div>
            </div>

            {(
              [
                { key: 'confirmacao_mensagem',             label: 'Mensagem de confirmação',      vars: '{nome}, {hora}, {data}' },
                { key: 'confirmacao_msg_positiva',         label: 'Mensagem quando confirmado',   vars: '{nome}, {hora}' },
                { key: 'confirmacao_msg_negativa',         label: 'Mensagem quando negado/timeout', vars: '{nome}' },
                { key: 'confirmacao_msg_abertura_privado', label: 'Mensagem de abertura 1-1',     vars: '{nome}, {hora}, {data}' },
              ] as const
            ).map(({ key, label, vars }) => {
              const valor = config[key] as string
              const preview = valor
                .replace(/{nome}/g, 'Maria')
                .replace(/{hora}/g, '14:00')
                .replace(/{data}/g, '13/04/2026')
              return (
                <div key={key} className="space-y-1">
                  <label className="text-[10px] text-muted-foreground">{label}</label>
                  <p className="text-[9px] text-muted-foreground/60">Variáveis: {vars}</p>
                  <textarea
                    value={valor}
                    rows={2}
                    onChange={e => setConfig(c => ({ ...c, [key]: e.target.value }))}
                    className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-xs resize-none focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                  {preview !== valor && (
                    <p className="text-[10px] text-muted-foreground italic bg-muted/40 rounded px-2 py-1">
                      Preview: {preview}
                    </p>
                  )}
                </div>
              )
            })}
          </CardContent>
        )}
      </Card>
```

**Observação:** Se `Switch` não existir em `@/components/ui/switch`, substituir por:
```tsx
<input
  type="checkbox"
  checked={config.confirmacao_ativa}
  onChange={e => setConfig(c => ({ ...c, confirmacao_ativa: e.target.checked }))}
  className="h-4 w-4 cursor-pointer"
/>
```

- [ ] **Step 5: Build para verificar erros TypeScript**

```bash
cd leadflow-frontend
npm run build 2>&1 | tail -20
```

Esperado: `✓ built in X.XXs` sem erros TypeScript.

- [ ] **Step 6: Commit**

```bash
cd leadflow-frontend
git add src/modules/agenda/AgendaPage.tsx
git commit -m "feat(frontend): add confirmacao agendamento config section to AgendaPage"
git push
```

```bash
cd ..
git add leadflow-frontend
git commit -m "chore: update leadflow-frontend submodule"
```

---

## Task 7: Push Backend e Verificação Final

**Files:**
- Backend submodule

- [ ] **Step 1: Push backend**

```bash
cd leadflow-backend
git push
```

- [ ] **Step 2: Verificar que `pytz` está em `requirements.txt`**

```bash
grep pytz leadflow-backend/requirements.txt
```

Se ausente, adicionar e fazer commit:
```bash
echo "pytz" >> leadflow-backend/requirements.txt
git add requirements.txt
git commit -m "chore(deps): add pytz for timezone handling in confirmacao_agendamento"
git push
```

- [ ] **Step 3: Atualizar submodule no repo raiz**

```bash
cd ..  # volta para c:/Projetos/Leadflow
git add leadflow-backend leadflow-frontend
git commit -m "chore: update submodules — confirmacao agendamento feature"
git push
```

- [ ] **Step 4: Fazer deploy no EasyPanel**

Acessar EasyPanel e fazer rebuild/redeploy de:
- `leadflow-backend` (novos arquivos Python + migration SQL)
- `leadflow-frontend` (nova seção UI)

- [ ] **Step 5: Teste de smoke — verificar webhook de grupo**

Enviar uma mensagem de teste para um grupo existente via WhatsApp e verificar nos logs do backend:
```
[CONFIRMACAO] ...
```
ou ausência de erros 500.

- [ ] **Step 6: Commit final de documentação**

```bash
cd c:/Projetos/Leadflow
git add docs/
git commit -m "docs: add confirmacao agendamento implementation plan"
git push
```
