# Onboarding de Novas Empresas + Conexão WhatsApp — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ao criar uma nova empresa, copiar automaticamente as configurações da empresa-modelo e guiar o usuário por um wizard de 3 etapas (template aplicado → API keys → QR code WhatsApp).

**Architecture:** Backend FastAPI com 5 novos endpoints (1 em configuracoes.py, 4 em whatsapp.py novo). Frontend com página `/onboarding` em stepper + componente `<WhatsAppConnect>` compartilhado com a aba WhatsApp nova em SettingsPage.

**Tech Stack:** Python/FastAPI + httpx (Evolution API calls), React/TypeScript + shadcn/ui, Supabase service key, Evolution API v2

---

## File Map

### Backend
| Arquivo | Ação | O que faz |
|---|---|---|
| `leadflow-backend/app/routers/configuracoes.py` | Modificar | Adicionar endpoint `POST /configuracoes/empresas/{id}/aplicar-template` |
| `leadflow-backend/app/routers/whatsapp.py` | Criar | 4 endpoints: criar instância, status, desconectar, get instância atual |
| `leadflow-backend/app/main.py` | Modificar | Registrar router whatsapp |
| `leadflow-backend/.env.example` | Criar | Documentar `TEMPLATE_EMPRESA_ID` |

### Frontend
| Arquivo | Ação | O que faz |
|---|---|---|
| `leadflow-frontend/src/components/WhatsAppConnect.tsx` | Criar | Componente QR code compartilhado (modo criar / gerenciar) |
| `leadflow-frontend/src/modules/onboarding/OnboardingPage.tsx` | Criar | Stepper 3 etapas pós-criação de empresa |
| `leadflow-frontend/src/modules/settings/SettingsPage.tsx` | Modificar | Adicionar aba "WhatsApp" com `<WhatsAppConnect mode="gerenciar">` (**nota:** a spec chama este arquivo de `ConfiguracoesPage.tsx`, mas o arquivo real verificado no repositório é `src/modules/settings/SettingsPage.tsx`) |
| `leadflow-frontend/src/modules/empresas/EmpresasPage.tsx` | Modificar | Redirecionar para `/onboarding` após criar empresa |
| `leadflow-frontend/src/app/router.tsx` | Modificar | Registrar rota `/onboarding` |
| `leadflow-frontend/src/components/ApiKeysForm.tsx` | **Não criar** — desvio intencional | A spec pede extração do form de API keys; o plano usa form inline simplificado em Etapa2 (YAGNI — ver Notas) |

---

## Task 1: Backend — endpoint aplicar-template

**Files:**
- Modify: `leadflow-backend/app/routers/configuracoes.py`

- [ ] **Step 1: Ler o arquivo antes de editar**

```bash
cat leadflow-backend/app/routers/configuracoes.py
```

- [ ] **Step 2: Adicionar endpoint ao final de configuracoes.py**

Adicionar após o último endpoint existente:

```python
import os

@router.post("/empresas/{empresa_id}/aplicar-template")
async def aplicar_template(
    empresa_id: str,
    authorization: str = Header(None),
):
    """Copia config_ia e config_agendamento da empresa-modelo para a nova empresa."""
    if not authorization:
        raise HTTPException(401, "Token não fornecido")
    token = authorization.replace("Bearer ", "")
    sb = get_supabase()
    user_res = sb.auth.get_user(token)
    if not user_res.user:
        raise HTTPException(401, "Token inválido")

    # Verifica que o usuário é membro da empresa alvo
    membro = sb.table("membros") \
        .select("empresa_id") \
        .eq("usuario_id", user_res.user.id) \
        .eq("empresa_id", empresa_id) \
        .eq("ativo", True) \
        .limit(1).execute()
    if not membro.data:
        raise HTTPException(403, "Acesso negado a esta empresa")

    template_id = os.environ.get("TEMPLATE_EMPRESA_ID", "")
    if not template_id:
        raise HTTPException(503, "Template não configurado (TEMPLATE_EMPRESA_ID ausente)")

    try:
        template = sb.table("empresas") \
            .select("config_ia, config_agendamento") \
            .eq("id", template_id) \
            .single().execute()
    except Exception:
        raise HTTPException(503, "Empresa-modelo não encontrada")

    if not template.data:
        raise HTTPException(503, "Empresa-modelo não encontrada")

    sb.table("empresas").update({
        "config_ia": template.data.get("config_ia"),
        "config_agendamento": template.data.get("config_agendamento"),
    }).eq("id", empresa_id).execute()

    return {"ok": True, "copiados": ["config_ia", "config_agendamento"]}
```

- [ ] **Step 3: Verificar que `import os` já existe ou adicionar no topo do arquivo**

Se `import os` não estiver no topo, adicionar junto com os outros imports existentes.

- [ ] **Step 4: Testar o endpoint manualmente**

```bash
# Obter token do Supabase (use um token válido do frontend)
curl -X POST https://leadflow-backend.bqvcbz.easypanel.host/configuracoes/empresas/{EMPRESA_ID}/aplicar-template \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json"
# Esperado: {"ok": true, "copiados": ["config_ia", "config_agendamento"]}

# Sem TEMPLATE_EMPRESA_ID no .env → esperado: 503
# Com token inválido → esperado: 401
# Com empresa sem membro → esperado: 403
```

- [ ] **Step 5: Commit**

```bash
rtk git add leadflow-backend/app/routers/configuracoes.py
rtk git commit -m "feat(backend): add POST /configuracoes/empresas/{id}/aplicar-template"
```

---

## Task 2: Backend — router whatsapp.py

**Files:**
- Create: `leadflow-backend/app/routers/whatsapp.py`

- [ ] **Step 1: Criar o arquivo**

```python
# leadflow-backend/app/routers/whatsapp.py
import os
import re
import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from app.db.client import get_supabase

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

SLUG_RE = re.compile(r"^[a-z0-9-]{3,60}$")


def _evo_url() -> str:
    url = os.environ.get("EVOLUTION_API_URL", "").rstrip("/")
    if not url:
        raise HTTPException(503, "EVOLUTION_API_URL não configurada")
    return url


def _evo_key() -> str:
    return os.environ.get("EVOLUTION_API_KEY", "")


def _evo_headers() -> dict:
    return {"apikey": _evo_key(), "Content-Type": "application/json"}


async def _validar_acesso(authorization: str | None, empresa_id: str):
    if not authorization:
        raise HTTPException(401, "Token não fornecido")
    token = authorization.replace("Bearer ", "")
    sb = get_supabase()
    user_res = sb.auth.get_user(token)
    if not user_res.user:
        raise HTTPException(401, "Token inválido")
    membro = sb.table("membros") \
        .select("empresa_id") \
        .eq("usuario_id", user_res.user.id) \
        .eq("empresa_id", empresa_id) \
        .eq("ativo", True) \
        .limit(1).execute()
    if not membro.data:
        raise HTTPException(403, "Acesso negado")
    return sb


def _get_connection_state(instancia_nome: str) -> str | None:
    """Retorna estado da instância ou None se não existir."""
    try:
        r = httpx.get(
            f"{_evo_url()}/instance/connectionState/{instancia_nome}",
            headers=_evo_headers(),
            timeout=10,
        )
        if r.status_code == 404:
            return None
        data = r.json()
        # Evolution API v2: {"instance": {"state": "open"}}
        return data.get("instance", {}).get("state") or data.get("state")
    except Exception:
        return None


@router.post("/instancia/criar")
async def criar_instancia(
    body: dict,
    authorization: str = Header(None),
):
    empresa_id = body.get("empresa_id", "")
    instancia_nome = body.get("instancia_nome", "")

    sb = await _validar_acesso(authorization, empresa_id)

    if not SLUG_RE.match(instancia_nome):
        raise HTTPException(400, "instancia_nome inválido: use apenas letras minúsculas, números e hífens (3-60 caracteres)")

    # Verificar se instância já existe
    estado_atual = _get_connection_state(instancia_nome)
    if estado_atual == "open":
        return {"estado": "open", "instancia_nome": instancia_nome}

    if estado_atual is not None:
        # Instância existe mas não conectada — buscar QR da instância existente
        try:
            r = httpx.get(
                f"{_evo_url()}/instance/connect/{instancia_nome}",
                headers=_evo_headers(),
                timeout=10,
            )
            data = r.json()
            qrcode_base64 = data.get("base64") or data.get("qrcode", {}).get("base64", "")
            sb.table("empresas").update({"evolution_instancia": instancia_nome}).eq("id", empresa_id).execute()
            return {"qrcode_base64": qrcode_base64, "instancia_nome": instancia_nome}
        except Exception as e:
            raise HTTPException(500, f"Erro ao obter QR da instância existente: {e}")

    # Criar nova instância
    try:
        r = httpx.post(
            f"{_evo_url()}/instance/create",
            headers=_evo_headers(),
            json={"instanceName": instancia_nome, "qrcode": True, "integration": "WHATSAPP-BAILEYS"},
            timeout=15,
        )
        if r.status_code >= 400:
            raise HTTPException(500, f"Evolution API erro {r.status_code}: {r.text}")
        data = r.json()
        qrcode_base64 = (
            data.get("qrcode", {}).get("base64")
            or data.get("base64")
            or ""
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erro ao criar instância: {e}")

    sb.table("empresas").update({"evolution_instancia": instancia_nome}).eq("id", empresa_id).execute()
    return {"qrcode_base64": qrcode_base64, "instancia_nome": instancia_nome}


@router.get("/instancia/status")
async def status_instancia(
    instancia_nome: str = Query(...),
    empresa_id: str = Query(...),
    authorization: str = Header(None),
):
    if not SLUG_RE.match(instancia_nome):
        raise HTTPException(400, "instancia_nome inválido")

    await _validar_acesso(authorization, empresa_id)

    estado = _get_connection_state(instancia_nome)
    return {"estado": estado or "close", "instancia_nome": instancia_nome}


@router.get("/instancia")
async def get_instancia(
    empresa_id: str = Query(...),
    authorization: str = Header(None),
):
    sb = await _validar_acesso(authorization, empresa_id)

    res = sb.table("empresas").select("evolution_instancia").eq("id", empresa_id).single().execute()
    instancia_nome = (res.data or {}).get("evolution_instancia")

    if not instancia_nome:
        return {"instancia_nome": None, "estado": None}

    estado = _get_connection_state(instancia_nome)
    if estado is None:
        # Instância não existe mais na Evolution API — retorna null conforme spec
        return {"instancia_nome": None, "estado": None}

    return {"instancia_nome": instancia_nome, "estado": estado}


@router.delete("/instancia/{instancia_nome}")
async def desconectar_instancia(
    instancia_nome: str,
    empresa_id: str = Query(...),
    authorization: str = Header(None),
):
    if not SLUG_RE.match(instancia_nome):
        raise HTTPException(400, "instancia_nome inválido")

    sb = await _validar_acesso(authorization, empresa_id)

    # Tenta deletar na Evolution API — ignora 404
    try:
        httpx.delete(
            f"{_evo_url()}/instance/delete/{instancia_nome}",
            headers=_evo_headers(),
            timeout=10,
        )
    except Exception:
        pass  # Falha silenciosa — limpamos o DB de qualquer forma

    sb.table("empresas").update({"evolution_instancia": None}).eq("id", empresa_id).execute()
    return {"ok": True}
```

- [ ] **Step 2: Testar endpoint de status manualmente**

```bash
# Após registrar o router (próximo task), testar:
curl "https://leadflow-backend.bqvcbz.easypanel.host/whatsapp/instancia/status?instancia_nome=teste-instancia&empresa_id={ID}" \
  -H "Authorization: Bearer {TOKEN}"
# Esperado: {"estado": "close", "instancia_nome": "teste-instancia"}
```

- [ ] **Step 3: Commit**

```bash
rtk git add leadflow-backend/app/routers/whatsapp.py
rtk git commit -m "feat(backend): add whatsapp router with Evolution API integration"
```

---

## Task 3: Backend — registrar router + .env.example

**Files:**
- Modify: `leadflow-backend/app/main.py`
- Create: `leadflow-backend/.env.example`

- [ ] **Step 1: Adicionar import e include_router em main.py**

Na linha dos imports de routers (linha 6), adicionar `whatsapp` ao final:

```python
from app.routers import webhook, leads, configuracoes, agente, agenda, agendamentos, followup, documentos, followup_agenda, noshow_check, warmup_grupo, conversas, whatsapp
```

Após `app.include_router(conversas.router)` (linha 59), adicionar:

```python
app.include_router(whatsapp.router)
```

- [ ] **Step 2: Criar .env.example**

```bash
# leadflow-backend/.env.example
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiJ9...
EVOLUTION_API_URL=https://sua-evolution-api.com
EVOLUTION_API_KEY=sua-global-api-key
TEMPLATE_EMPRESA_ID=uuid-da-empresa-modelo-aqui
```

- [ ] **Step 3: Adicionar TEMPLATE_EMPRESA_ID no .env real do servidor**

No painel do EasyPanel, adicionar a variável de ambiente:
```
TEMPLATE_EMPRESA_ID=<uuid da empresa da Rejane Leal>
```

Para obter o UUID: Supabase → Table Editor → empresas → filtrar pelo nome "Rejane Leal" → copiar o `id`.

- [ ] **Step 4: Commit**

```bash
rtk git add leadflow-backend/app/main.py leadflow-backend/.env.example
rtk git commit -m "feat(backend): register whatsapp router and document env vars"
```

---

## Task 4: Frontend — componente WhatsAppConnect

**Files:**
- Create: `leadflow-frontend/src/components/WhatsAppConnect.tsx`

- [ ] **Step 1: Criar o componente**

```tsx
// leadflow-frontend/src/components/WhatsAppConnect.tsx
import { useState, useEffect, useRef } from 'react'
import { Wifi, WifiOff, QrCode, RefreshCw, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { api } from '@/lib/api'

interface Props {
  mode: 'criar' | 'gerenciar'
  empresaId: string
  /** Chamado ao conectar com sucesso (modo criar) */
  onConectado?: () => void
}

interface StatusResp { estado: string | null; instancia_nome: string | null }
interface CriarResp { qrcode_base64?: string; instancia_nome: string; estado?: string }

function toSlug(name: string): string {
  return name
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60)
}

const SLUG_RE = /^[a-z0-9-]{3,60}$/

export function WhatsAppConnect({ mode, empresaId, onConectado }: Props) {
  const [instanciaNome, setInstanciaNome] = useState('')
  const [qrcode, setQrcode] = useState('')
  const [estado, setEstado] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [erro, setErro] = useState('')
  const [qrExpirado, setQrExpirado] = useState(false)
  const [reconectando, setReconectando] = useState(false)
  const [confirmDesconect, setConfirmDesconect] = useState(false)

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const qrTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Modo gerenciar: carregar estado atual ao montar
  useEffect(() => {
    if (mode !== 'gerenciar') return
    api.get<StatusResp>(`/whatsapp/instancia?empresa_id=${empresaId}`)
      .then(r => {
        setInstanciaNome(r.instancia_nome ?? '')
        setEstado(r.estado)
      })
      .catch(() => {})
  }, [mode, empresaId])

  function iniciarPolling(nome: string) {
    pararPolling()
    pollingRef.current = setInterval(async () => {
      try {
        const r = await api.get<StatusResp>(
          `/whatsapp/instancia/status?instancia_nome=${nome}&empresa_id=${empresaId}`
        )
        setEstado(r.estado)
        if (r.estado === 'open') {
          pararPolling()
          pararQrTimer()
          setQrcode('')
          onConectado?.()
        } else if (r.estado === 'close') {
          pararPolling()
          setErro('Conexão perdida. Tente reconectar.')
        }
      } catch {}
    }, 3000)
  }

  function iniciarQrTimer(nome: string) {
    pararQrTimer()
    qrTimerRef.current = setTimeout(() => {
      setQrExpirado(true)
    }, 60000)
  }

  function pararPolling() {
    if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null }
  }

  function pararQrTimer() {
    if (qrTimerRef.current) { clearTimeout(qrTimerRef.current); qrTimerRef.current = null }
    setQrExpirado(false)
  }

  useEffect(() => () => { pararPolling(); pararQrTimer() }, [])

  async function criarOuConectar(nome: string) {
    if (!SLUG_RE.test(nome)) {
      setErro('Nome inválido: use apenas letras minúsculas, números e hífens (3-60 caracteres)')
      return
    }
    setLoading(true)
    setErro('')
    setQrcode('')
    pararQrTimer()
    try {
      const r = await api.post<CriarResp>('/whatsapp/instancia/criar', {
        instancia_nome: nome,
        empresa_id: empresaId,
      })
      if (r.estado === 'open') {
        setEstado('open')
        onConectado?.()
        return
      }
      setQrcode(r.qrcode_base64 ?? '')
      setEstado('qr')
      iniciarPolling(nome)
      iniciarQrTimer(nome)
    } catch (e: any) {
      setErro(e.message ?? 'Erro ao criar instância')
    } finally {
      setLoading(false)
    }
  }

  async function desconectar() {
    setLoading(true)
    try {
      await api.delete(`/whatsapp/instancia/${instanciaNome}?empresa_id=${empresaId}`)
      setEstado(null)
      setQrcode('')
      setReconectando(false)
      setConfirmDesconect(false)
    } catch (e: any) {
      setErro(e.message ?? 'Erro ao desconectar')
    } finally {
      setLoading(false)
    }
  }

  async function reconectar() {
    if (estado === 'open') {
      // Desconectar primeiro, depois mostrar QR
      await desconectar()
    }
    setReconectando(true)
  }

  // ─── Modo CRIAR ───────────────────────────────────────────────────────────
  if (mode === 'criar') {
    if (estado === 'open') {
      return (
        <div className="flex flex-col items-center gap-3 py-6">
          <Wifi size={40} className="text-green-500" />
          <p className="font-semibold text-green-600">WhatsApp conectado!</p>
          <Badge variant="success">Conectado</Badge>
        </div>
      )
    }

    return (
      <div className="space-y-4">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">Nome da instância</label>
          <Input
            value={instanciaNome}
            onChange={e => setInstanciaNome(toSlug(e.target.value))}
            placeholder="minha-empresa"
            className="font-mono text-xs"
            disabled={!!qrcode}
          />
          <p className="text-[11px] text-muted-foreground">Apenas letras minúsculas, números e hífens</p>
        </div>

        {!qrcode && (
          <Button
            className="w-full"
            disabled={loading || !instanciaNome}
            onClick={() => criarOuConectar(instanciaNome)}
          >
            <QrCode size={14} className="mr-2" />
            {loading ? 'Aguarde…' : 'Criar e conectar'}
          </Button>
        )}

        {qrcode && (
          <div className="flex flex-col items-center gap-3">
            <p className="text-xs text-muted-foreground text-center">
              Abra o WhatsApp → Dispositivos Vinculados → Vincular Dispositivo e escaneie:
            </p>
            <img
              src={`data:image/png;base64,${qrcode}`}
              alt="QR Code WhatsApp"
              className="w-52 h-52 rounded-lg border"
            />
            {qrExpirado && (
              <Button variant="outline" size="sm" onClick={() => criarOuConectar(instanciaNome)}>
                <RefreshCw size={13} className="mr-1.5" /> Atualizar QR code
              </Button>
            )}
            <p className="text-[11px] text-muted-foreground animate-pulse">Aguardando scan…</p>
          </div>
        )}

        {erro && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{erro}</p>}
      </div>
    )
  }

  // ─── Modo GERENCIAR ───────────────────────────────────────────────────────
  const conectado = estado === 'open'

  if (!reconectando) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between p-4 rounded-lg border bg-muted/30">
          <div className="flex items-center gap-3">
            {conectado ? <Wifi size={20} className="text-green-500" /> : <WifiOff size={20} className="text-muted-foreground" />}
            <div>
              <p className="text-sm font-medium">{instanciaNome || '—'}</p>
              <Badge
                variant={conectado ? 'success' : estado === 'qr' ? 'outline' : 'secondary'}
                className="text-[10px] mt-0.5"
              >
                {conectado ? 'Conectado' : estado === 'qr' ? 'Aguardando scan' : 'Desconectado'}
              </Badge>
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={reconectar} disabled={loading}>
              <RefreshCw size={13} className="mr-1.5" /> Reconectar
            </Button>
            {conectado && !confirmDesconect && (
              <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setConfirmDesconect(true)}>
                <Trash2 size={13} />
              </Button>
            )}
            {confirmDesconect && (
              <div className="flex gap-1">
                <Button variant="destructive" size="sm" onClick={desconectar} disabled={loading}>
                  Confirmar
                </Button>
                <Button variant="outline" size="sm" onClick={() => setConfirmDesconect(false)}>
                  Cancelar
                </Button>
              </div>
            )}
          </div>
        </div>
        {erro && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{erro}</p>}
      </div>
    )
  }

  // Modo reconectar — exibe fluxo QR com o instanciaNome já salvo
  return (
    <div className="space-y-4">
      <p className="text-sm font-medium">Reconectar instância <span className="font-mono">{instanciaNome}</span></p>
      {!qrcode && (
        <Button className="w-full" disabled={loading} onClick={() => criarOuConectar(instanciaNome)}>
          <QrCode size={14} className="mr-2" />
          {loading ? 'Aguarde…' : 'Gerar QR code'}
        </Button>
      )}
      {qrcode && (
        <div className="flex flex-col items-center gap-3">
          <img src={`data:image/png;base64,${qrcode}`} alt="QR Code" className="w-52 h-52 rounded-lg border" />
          {qrExpirado && (
            <Button variant="outline" size="sm" onClick={() => criarOuConectar(instanciaNome)}>
              <RefreshCw size={13} className="mr-1.5" /> Atualizar QR code
            </Button>
          )}
          <p className="text-[11px] text-muted-foreground animate-pulse">Aguardando scan…</p>
        </div>
      )}
      {estado === 'open' && (
        <div className="flex flex-col items-center gap-2 py-4">
          <Wifi size={32} className="text-green-500" />
          <p className="text-sm font-semibold text-green-600">Reconectado com sucesso!</p>
        </div>
      )}
      <Button variant="ghost" size="sm" className="w-full" onClick={() => { setReconectando(false); pararPolling(); pararQrTimer() }}>
        Cancelar
      </Button>
      {erro && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{erro}</p>}
    </div>
  )
}
```

- [ ] **Step 2: Verificar que Badge tem variant="success"**

Verificar em `leadflow-frontend/src/components/ui/badge.tsx` se existe `variant: "success"`. Se não existir, substituir `variant="success"` por `className="bg-green-500/10 text-green-700 border-green-500/30"` nas ocorrências.

- [ ] **Step 3: Commit**

```bash
rtk git add leadflow-frontend/src/components/WhatsAppConnect.tsx
rtk git commit -m "feat(frontend): add WhatsAppConnect shared component with QR code flow"
```

---

## Task 5: Frontend — OnboardingPage

**Files:**
- Create: `leadflow-frontend/src/modules/onboarding/OnboardingPage.tsx`

- [ ] **Step 1: Criar o componente**

```tsx
// leadflow-frontend/src/modules/onboarding/OnboardingPage.tsx
import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { CheckCircle2, AlertTriangle, ChevronRight } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { WhatsAppConnect } from '@/components/WhatsAppConnect'
import { api } from '@/lib/api'
import { supabase } from '@/lib/supabase'
import { cn } from '@/lib/utils'

const STEPS = ['Configuração inicial', 'API Keys', 'Conectar WhatsApp']

// ─── Etapa 1 ──────────────────────────────────────────────────────────────────
function Etapa1({ empresaId, onNext }: { empresaId: string; onNext: () => void }) {
  const [status, setStatus] = useState<'loading' | 'ok' | 'erro'>('loading')
  const [erro, setErro] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    api.post<{ ok: boolean; erro?: string }>(`/configuracoes/empresas/${empresaId}/aplicar-template`, {})
      .then(() => setStatus('ok'))
      .catch(e => {
        const msg: string = e.message ?? ''
        // 403 = usuário não é membro desta empresa → redirecionar
        if (msg.includes('Acesso negado') || msg.includes('403')) {
          navigate('/dashboard')
          return
        }
        setErro(msg || 'Erro ao aplicar template')
        setStatus('erro')
      })
  }, [empresaId])

  return (
    <div className="space-y-5">
      {status === 'loading' && (
        <p className="text-sm text-muted-foreground animate-pulse">Configurando sua conta…</p>
      )}

      {status === 'ok' && (
        <div className="space-y-2">
          {['Agente IA configurado', 'Follow-ups configurados', 'Aquecimento de grupo configurado'].map(item => (
            <div key={item} className="flex items-center gap-2.5 text-sm">
              <CheckCircle2 size={16} className="text-green-500 flex-shrink-0" />
              <span>{item}</span>
            </div>
          ))}
        </div>
      )}

      {status === 'erro' && (
        <div className="flex items-start gap-2.5 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30">
          <AlertTriangle size={16} className="text-yellow-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-yellow-700">Template não disponível</p>
            <p className="text-xs text-yellow-600 mt-0.5">Você pode configurar manualmente depois em Configurações.</p>
          </div>
        </div>
      )}

      {status !== 'loading' && (
        <Button className="w-full" onClick={onNext}>
          Próximo <ChevronRight size={14} className="ml-1" />
        </Button>
      )}
    </div>
  )
}

// ─── Etapa 2 ──────────────────────────────────────────────────────────────────
function Etapa2({ empresaId, onNext }: { empresaId: string; onNext: () => void }) {
  const [form, setForm] = useState({ evolution_url: '', evolution_key: '', openai_key: '' })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  async function salvar(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      // Busca config_apis atual para não sobrescrever outros campos
      const { data } = await supabase.from('empresas')
        .select('config_apis, evolution_instancia')
        .eq('id', empresaId).single()
      const atual = data?.config_apis ?? {}
      await supabase.from('empresas').update({
        config_apis: { ...atual, ...form },
        evolution_instancia: data?.evolution_instancia ?? '',
      }).eq('id', empresaId)
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={salvar} className="space-y-4">
      <p className="text-xs text-muted-foreground">Configure as integrações essenciais. Você pode completar as demais em Configurações depois.</p>
      {[
        { key: 'evolution_url', label: 'Evolution API — URL base', placeholder: 'https://sua-evolution.com', type: 'text' },
        { key: 'evolution_key', label: 'Evolution API — Global API Key', placeholder: 'Chave da API', type: 'password' },
        { key: 'openai_key', label: 'OpenAI — API Key', placeholder: 'sk-...', type: 'password' },
      ].map(({ key, label, placeholder, type }) => (
        <div key={key} className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">{label}</label>
          <Input
            type={type}
            placeholder={placeholder}
            value={(form as any)[key]}
            onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
            className="font-mono text-xs"
          />
        </div>
      ))}
      <div className="flex gap-2 pt-1">
        <Button type="submit" className="flex-1" disabled={saving}>
          {saved ? '✓ Salvo' : saving ? 'Salvando…' : 'Salvar'}
        </Button>
        {saved && (
          <Button type="button" className="flex-1" onClick={onNext}>
            Próximo <ChevronRight size={14} className="ml-1" />
          </Button>
        )}
      </div>
      {!saved && (
        <button type="button" className="text-xs text-muted-foreground underline w-full text-center" onClick={onNext}>
          Pular por agora
        </button>
      )}
    </form>
  )
}

// ─── Etapa 3 ──────────────────────────────────────────────────────────────────
function Etapa3({ empresaId }: { empresaId: string }) {
  const navigate = useNavigate()
  const [conectado, setConectado] = useState(false)

  return (
    <div className="space-y-4">
      <WhatsAppConnect
        mode="criar"
        empresaId={empresaId}
        onConectado={() => setConectado(true)}
      />
      {conectado && (
        <Button className="w-full" onClick={() => navigate('/dashboard')}>
          Ir para o painel →
        </Button>
      )}
      {!conectado && (
        <button
          className="text-xs text-muted-foreground underline w-full text-center"
          onClick={() => navigate('/dashboard')}
        >
          Pular por agora
        </button>
      )}
    </div>
  )
}

// ─── OnboardingPage ────────────────────────────────────────────────────────────
export function OnboardingPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const empresaId = params.get('empresa_id') ?? ''
  const [etapa, setEtapa] = useState(0)

  useEffect(() => {
    if (!empresaId) navigate('/dashboard')
  }, [empresaId])

  if (!empresaId) return null

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <h1 className="text-xl font-semibold">Configurar nova empresa</h1>
          <p className="text-sm text-muted-foreground mt-1">Siga os passos para começar a usar o Leadflow</p>
        </div>

        {/* Stepper */}
        <div className="flex items-center gap-0">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center flex-1 last:flex-none">
              <div className={cn(
                'flex items-center justify-center w-7 h-7 rounded-full text-xs font-semibold border-2 flex-shrink-0',
                i < etapa ? 'bg-primary border-primary text-primary-foreground' :
                i === etapa ? 'border-primary text-primary' : 'border-muted text-muted-foreground'
              )}>
                {i < etapa ? <CheckCircle2 size={14} /> : i + 1}
              </div>
              {i < STEPS.length - 1 && (
                <div className={cn('h-0.5 flex-1 mx-1', i < etapa ? 'bg-primary' : 'bg-muted')} />
              )}
            </div>
          ))}
        </div>

        <p className="text-xs text-muted-foreground text-center">Etapa {etapa + 1} de {STEPS.length}: {STEPS[etapa]}</p>

        <Card>
          <CardContent className="pt-5">
            {etapa === 0 && <Etapa1 empresaId={empresaId} onNext={() => setEtapa(1)} />}
            {etapa === 1 && <Etapa2 empresaId={empresaId} onNext={() => setEtapa(2)} />}
            {etapa === 2 && <Etapa3 empresaId={empresaId} />}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
rtk git add leadflow-frontend/src/modules/onboarding/OnboardingPage.tsx
rtk git commit -m "feat(frontend): add OnboardingPage with 3-step wizard"
```

---

## Task 6: Frontend — aba WhatsApp em SettingsPage

**Files:**
- Modify: `leadflow-frontend/src/modules/settings/SettingsPage.tsx`

- [ ] **Step 1: Ler o arquivo**

```bash
cat leadflow-frontend/src/modules/settings/SettingsPage.tsx
```

- [ ] **Step 2: Adicionar import do WhatsAppConnect no topo**

```tsx
import { WhatsAppConnect } from '@/components/WhatsAppConnect'
```

- [ ] **Step 3: Adicionar 'whatsapp' ao tipo Aba e array de abas**

Alterar o tipo `Aba`:
```tsx
type Aba = 'apis' | 'notificacoes' | 'empresa' | 'whatsapp'
```

Alterar o array `abas`:
```tsx
const abas: { id: Aba; label: string }[] = [
  { id: 'apis', label: 'Integrações de API' },
  { id: 'notificacoes', label: 'Notificações' },
  { id: 'empresa', label: 'Dados da empresa' },
  { id: 'whatsapp', label: 'WhatsApp' },
]
```

- [ ] **Step 4: Adicionar bloco da aba WhatsApp após a aba Empresa**

Após o bloco `{aba === 'empresa' && ...}`, adicionar:

```tsx
{/* ── ABA: WhatsApp ── */}
{aba === 'whatsapp' && (
  <Card>
    <CardHeader>
      <CardTitle className="text-sm">Conexão WhatsApp</CardTitle>
      <CardDescription className="text-xs">
        Gerencie a instância Evolution API da sua empresa.
      </CardDescription>
    </CardHeader>
    <CardContent>
      <WhatsAppConnect mode="gerenciar" empresaId={empresaId} />
    </CardContent>
  </Card>
)}
```

- [ ] **Step 5: Verificar que CardDescription está importado**

A linha de imports já tem `CardHeader, CardTitle` — verificar se `CardDescription` também está. Se não, adicionar ao import de `@/components/ui/card`.

- [ ] **Step 6: Commit**

```bash
rtk git add leadflow-frontend/src/modules/settings/SettingsPage.tsx
rtk git commit -m "feat(frontend): add WhatsApp tab to SettingsPage"
```

---

## Task 7: Frontend — rota /onboarding + redirect EmpresasPage

**Files:**
- Modify: `leadflow-frontend/src/app/router.tsx`
- Modify: `leadflow-frontend/src/modules/empresas/EmpresasPage.tsx`

- [ ] **Step 1: Ler router.tsx**

```bash
cat leadflow-frontend/src/app/router.tsx
```

- [ ] **Step 2: Adicionar import de OnboardingPage em router.tsx**

```tsx
import { OnboardingPage } from '@/modules/onboarding/OnboardingPage'
```

- [ ] **Step 3: Adicionar rota /onboarding**

Adicionar após a rota `/workspace` existente (linha ~26):

```tsx
{
  path: '/onboarding',
  element: <ProtectedRoute><OnboardingPage /></ProtectedRoute>,
},
```

A rota usa `ProtectedRoute` (requer JWT) mas fica fora do `AppLayout` (sem sidebar), idêntico ao padrão de `/workspace`.

- [ ] **Step 4: Atualizar redirect em EmpresasPage.tsx**

Localizar a linha:
```tsx
window.location.href = '/workspace'
```

Substituir por:
```tsx
window.location.href = `/onboarding?empresa_id=${res.empresa_id}`
```

- [ ] **Step 5: Commit**

```bash
rtk git add leadflow-frontend/src/app/router.tsx leadflow-frontend/src/modules/empresas/EmpresasPage.tsx
rtk git commit -m "feat(frontend): add /onboarding route and redirect from EmpresasPage"
```

---

## Task 8: Push e deploy

- [ ] **Step 1: Push para GitHub**

```bash
rtk git push origin main
```

- [ ] **Step 2: Adicionar TEMPLATE_EMPRESA_ID no EasyPanel**

1. Acesse o painel do EasyPanel → serviço `leadflow-backend`
2. Environment Variables → adicionar:
   ```
   TEMPLATE_EMPRESA_ID=<uuid-da-empresa-modelo>
   ```
3. Redeploy o serviço

- [ ] **Step 3: Smoke test completo**

1. Acesse o frontend → Configurações → Empresa → "Nova empresa"
2. Preencha o nome e clique "Criar empresa"
3. Verifique redirecionamento para `/onboarding?empresa_id=...`
4. Etapa 1: verifique checklist verde (config_ia e config_agendamento copiados)
5. Etapa 2: preencha Evolution URL + key + OpenAI key → Salvar
6. Etapa 3: digite nome da instância → "Criar e conectar" → QR code aparece
7. Escaneie com WhatsApp → badge "Conectado ✓" aparece
8. Clique "Ir para o painel"
9. Acesse Configurações → aba WhatsApp → verifique status e botão Reconectar

---

## Notas de implementação

- **Evolution API v2:** o formato do QR code retornado varia — o código já trata `data.qrcode.base64` e `data.base64`
- **Badge variant="success":** verificar se existe em `src/components/ui/badge.tsx`; se não, usar className diretamente
- **TEMPLATE_EMPRESA_ID:** obter o UUID da empresa da Rejane Leal em Supabase → Table Editor → empresas
- **Sem test suite:** o projeto não tem pytest configurado; os testes são manuais via curl e UI
- **Desvio intencional da spec — ApiKeysForm:** a spec pede extração de `<ApiKeysForm>` do SettingsPage. O plano inlina um form simplificado (3 campos) direto em Etapa2 por YAGNI — o SettingsPage existente já cobre o resto. A extração completa adicionaria ~150 linhas de complexidade sem benefício real para o onboarding.
