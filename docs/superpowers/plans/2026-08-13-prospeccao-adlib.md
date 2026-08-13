# Prospecção via Ad Library — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ligar a tela `/campaigns` (hoje um stub de 23 linhas) a campanhas de prospecção que se retroalimentam diariamente com anunciantes ativos da Biblioteca de Anúncios da Meta, com status de contato por prospect.

**Architecture:** Um 4º serviço `leadflow-scraper` (mesmo repo `leadflow-backend`, `Dockerfile.scraper` com Chromium) roda o scrape em subprocesso e grava em duas tabelas novas no Supabase. O `leadflow-backend` só lê e enfileira — não tem Chromium. O frontend consome pelo router `/prospeccao`.

**Tech Stack:** Python 3.11 (prod) / 3.14 (venv local), FastAPI, APScheduler, Playwright + Chromium, httpx, Supabase, React + TanStack Query v5, Tailwind.

**Spec:** [`docs/superpowers/specs/2026-08-13-prospeccao-adlib-design.md`](../specs/2026-08-13-prospeccao-adlib-design.md)

---

## Contexto que o executor precisa saber

**Dois repositórios.** `leadflow-backend` e `leadflow-frontend` são **submódulos git**. Commit dentro do submódulo primeiro, depois commit do ponteiro no repo raiz. `tools/` vive só na raiz e **não é visível** para o backend — por isso o parser é portado, não importado.

**Ambiente de teste.** `pytest 9.0.3`, rodar de dentro de `leadflow-backend/`. A suite atual passa. `python` resolve pro venv da raiz (`c:\Projetos\Leadflow\venv`), que já tem `playwright 1.62.0` e `httpx`.

**Regras do projeto (CLAUDE.md).**
- `git add <arquivo>` explícito, **nunca** `git add .`
- PowerShell encadeia com `;`, não `&&`
- Horário sempre em São Paulo (UTC-3) na tela, nunca UTC cru
- Toda resposta que gera commit termina dizendo qual serviço redeployar

**As duas armadilhas do parser que não podem regredir** (custaram uma sessão inteira):
1. A primeira linha do card é um zero-width space (`\u200b`). Não é string vazia e `_norm()` a reduz a `""` — passa por qualquer filtro de palavra-chave e vira o "nome do anunciante". O nome sai da âncora `"Patrocinado"`: é sempre a linha logo acima.
2. O Instagram vem em `l.facebook.com/l.php?u=<url-encoded>`. Um `.split("?")[0]` descarta o destino. Precisa desembrulhar `u=` **e** tratar o deeplink `instagram.com/_u/<handle>`, senão todo handle vira `_u`.

**Fixture golden já preservada** em `leadflow-backend/tests/fixtures/adlib_cards_2026-08-13.json` — 34 cards reais capturados de "mentoria para mulheres" em 13/08. É a linha de base: **0 sem nome, 0 com `l.php`, 17 com Instagram**.

---

## Estrutura de arquivos

### `leadflow-backend`
| Arquivo | Responsabilidade |
|---|---|
| `app/services/adlib.py` | **Parser puro.** Sem I/O, sem browser. Extrai prospects de cards já coletados. Testável offline |
| `app/services/adlib_enrich.py` | **Segundo hop.** Busca telefone nas landing pages. Só httpx |
| `app/services/adlib_store.py` | **Persistência.** Upsert que não pisa no status |
| `app/services/adlib_runner.py` | **Executável.** Orquestra browser → parser → enrich → store. Roda como subprocesso |
| `app/scraper_main.py` | **Entrypoint do 4º serviço.** APScheduler só com os jobs de prospecção |
| `app/routers/prospeccao.py` | **HTTP.** 8 endpoints, lê e enfileira |
| `Dockerfile.scraper` | Imagem com Chromium |
| `tests/fixtures/adlib_cards_2026-08-13.json` | ✅ já existe |
| `tests/test_adlib_extracao.py` | Golden do parser |
| `tests/test_adlib_enrich.py` | Teto de tempo do segundo hop |
| `tests/test_adlib_store.py` | Upsert não pisa no status |

A separação parser / enrich / store / runner existe para que **três dos quatro rodem sem browser e sem rede** — é o que torna a suite rápida e o bug reproduzível offline.

### `leadflow-frontend`
| Arquivo | Responsabilidade |
|---|---|
| `src/modules/campaigns/CampaignsPage.tsx` | Lista de campanhas + modal de criação (substitui o stub) |
| `src/modules/campaigns/ProspectsTable.tsx` | Lista de prospects, filtros, botões de ação |
| `src/modules/campaigns/api.ts` | Tipos + chamadas do módulo |

---

## Task 1: Migration das duas tabelas

**Files:**
- Create: `leadflow-backend/migrations/2026-08-13_prospeccao.sql`

- [ ] **Step 1: Escrever a migration**

```sql
-- Prospecção via Biblioteca de Anúncios da Meta.
-- Ver docs/superpowers/specs/2026-08-13-prospeccao-adlib-design.md

create table if not exists prospeccao_campanhas (
  id                  uuid primary key default gen_random_uuid(),
  empresa_id          uuid not null references empresas(id) on delete cascade,
  termo               text not null,
  min_dias            int  not null default 60,
  paginas             int  not null default 6,
  ativa               boolean not null default true,
  ultima_rodada       timestamptz,
  ultimo_erro         text,
  rodar_solicitado_em timestamptz,
  criada_em           timestamptz not null default now(),
  unique (empresa_id, termo)
);

create table if not exists prospeccao_prospects (
  id              uuid primary key default gen_random_uuid(),
  empresa_id      uuid not null references empresas(id) on delete cascade,
  campanha_id     uuid not null references prospeccao_campanhas(id) on delete cascade,
  chave           text not null,
  anunciante      text not null,
  instagram       text,
  page_url        text,
  whatsapp        text,
  lp_url          text,
  ad_id           text,
  inicio          date,
  dias_no_ar      int,
  anuncios_ativos int  not null default 1,
  status          text not null default 'novo',
  contatado_em    timestamptz,
  lead_id         uuid references leads(id) on delete set null,
  visto_em        timestamptz not null default now(),
  criado_em       timestamptz not null default now(),
  unique (empresa_id, campanha_id, chave),
  constraint prospeccao_status_valido
    check (status in ('novo','contatado','respondeu','descartado'))
);

create index if not exists idx_prospects_campanha_status
  on prospeccao_prospects (empresa_id, campanha_id, status);
create index if not exists idx_prospects_dias
  on prospeccao_prospects (empresa_id, dias_no_ar desc);
create index if not exists idx_campanhas_fila
  on prospeccao_campanhas (rodar_solicitado_em)
  where rodar_solicitado_em is not null;
```

- [ ] **Step 2: Aplicar no Supabase**

Rodar o SQL no editor do Supabase (projeto `pllpwjuagqykxwyfpqrz`).

Verificar:
```sql
select table_name from information_schema.tables
 where table_name like 'prospeccao_%';
```
Esperado: 2 linhas.

- [ ] **Step 3: Commit**

```bash
cd leadflow-backend
git add migrations/2026-08-13_prospeccao.sql
git commit -m "feat(prospeccao): tabelas de campanhas e prospects"
```

---

## Task 2: Parser portado + teste golden

O parser já existe e está provado em `tools/adlib_prospect.py`. Aqui ele é portado para o backend **com o teste escrito primeiro**, pra que a porta não introduza regressão silenciosa.

**Files:**
- Create: `leadflow-backend/tests/test_adlib_extracao.py`
- Create: `leadflow-backend/app/services/adlib.py`
- Reference: `tools/adlib_prospect.py` (origem)

- [ ] **Step 1: Escrever o teste golden (falha — o módulo não existe)**

```python
"""
Golden da extração da Biblioteca de Anúncios.

Trava o comportamento contra 34 cards REAIS capturados em 13/08/2026 do termo
"mentoria para mulheres". Quando a Meta trocar o HTML, este teste cai antes de
a tela mostrar lista vazia ou nome em branco.

Os dois bugs que este teste existe para impedir de voltar:
  1. anunciante vinha "\u200b" (zero-width space da 1a linha do card)
  2. instagram vinha "l.facebook.com/l.php" (destino mora na query, e o
     split("?")[0] jogava fora justamente ele)

Funcao pura -> roda offline, sem browser, sem rede, sem Supabase.
"""
import json
from datetime import date
from pathlib import Path

import pytest

from app.services.adlib import extrair, anunciante_do_texto, instagram_dos_links

FIXTURE = Path(__file__).parent / "fixtures" / "adlib_cards_2026-08-13.json"
HOJE = date(2026, 8, 13)


@pytest.fixture(scope="module")
def prospects():
    cards = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return extrair(cards, HOJE)


def test_fixture_intacta():
    cards = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(cards) == 34, "fixture mudou — o golden perde o sentido"


def test_todos_tem_nome(prospects):
    assert len(prospects) == 34
    sem_nome = [p for p in prospects if not p.anunciante.strip()]
    assert sem_nome == [], f"{len(sem_nome)} prospects sem nome"


def test_nenhum_nome_e_caractere_invisivel(prospects):
    """BUG 1: a 1a linha do card e \\u200b e virava o nome."""
    for p in prospects:
        assert p.anunciante != "\u200b"
        assert p.anunciante.strip("\u200b\ufeff\xa0 "), f"nome invisivel: {p.anunciante!r}"


def test_nenhum_link_e_redirecionador(prospects):
    """BUG 2: instagram vinha como l.facebook.com/l.php."""
    for p in prospects:
        assert "l.php" not in (p.instagram or "")
        assert "l.php" not in (p.page_url or "")


def test_instagram_resolvido_em_17(prospects):
    com_ig = [p for p in prospects if p.instagram]
    assert len(com_ig) == 17, f"esperado 17, veio {len(com_ig)}"


def test_deeplink_u_vira_handle_real(prospects):
    """instagram.com/_u/<handle> e deeplink de app; o handle NAO e '_u'."""
    for p in prospects:
        assert not (p.instagram or "").endswith("/_u")
    carol = [p for p in prospects if "planejecomacarol" in (p.instagram or "")]
    assert carol, "handle do deeplink _u nao foi resolvido"


def test_nomes_conhecidos_da_amostra(prospects):
    nomes = {p.anunciante for p in prospects}
    for esperado in ("Alta Performance", "George Soares", "Ana Kerkovsky"):
        assert esperado in nomes, f"{esperado!r} sumiu da extracao"


@pytest.mark.parametrize("texto,esperado", [
    ("\u200b\nAtivo\nPlataformas\nVer detalhes do anúncio\nFulana Silva\nPatrocinado\ncopy",
     "Fulana Silva"),
    ("\u200b\nAtivo\nBeltrano\nPatrocinado\n", "Beltrano"),
])
def test_ancora_patrocinado(texto, esperado):
    assert anunciante_do_texto(texto) == esperado


@pytest.mark.parametrize("links,esperado", [
    (["https://l.facebook.com/l.php?u=https%3A%2F%2Fwww.instagram.com%2Ffulana&h=AB"],
     "https://www.instagram.com/fulana"),
    (["https://l.facebook.com/l.php?u=https%3A%2F%2Fwww.instagram.com%2F_u%2Fbeltrana&h=AB"],
     "https://www.instagram.com/beltrana"),
    (["https://www.instagram.com/p/XYZ123"], ""),          # post nao e perfil
    (["https://www.facebook.com/pagina/"], ""),
])
def test_instagram_dos_links(links, esperado):
    assert instagram_dos_links(links) == esperado
```

- [ ] **Step 2: Rodar para ver falhar**

```bash
cd leadflow-backend
python -m pytest tests/test_adlib_extracao.py -q
```
Esperado: FAIL — `ModuleNotFoundError: No module named 'app.services.adlib'`

- [ ] **Step 3: Portar o parser**

Criar `app/services/adlib.py` copiando de `tools/adlib_prospect.py` as partes puras: `MESES`, `RE_ID`, `RE_INICIO`, `RE_USOS`, `RE_INVISIVEL`, `RE_IG`, `IG_RESERVADO`, `_norm`, `_limpa`, `_parse_data`, `_destino`, `_instagram`, `_anunciante`, `JS_COLETA`, e a dataclass `Prospect`.

Renomear para nomes públicos (o teste importa estes):
- `_anunciante` → `anunciante_do_texto`
- `_instagram` → `instagram_dos_links`
- `_extrair(cards, termo, hoje)` → `extrair(cards, hoje)`

Mudanças na dataclass `Prospect` — **as três importam**:

1. **Remover o campo `termo`.** O termo agora vive na campanha, não no prospect.
2. **`chave` vira CAMPO, não método.** Hoje é `def chave(self)`. Precisa ser
   `chave: str`, preenchido dentro de `extrair`. Motivo: a Task 5 persiste via
   `asdict(p)`, e `asdict()` **não inclui métodos** — a `salvar()` estouraria com
   `KeyError: 'chave'`. Mesma regra de antes: `page_url` quando houver, senão
   `_norm(anunciante)`.
3. **Adicionar `lp_url: str = ""` e `whatsapp: str = ""`** (preenchidos na Task 3).
   `lp_url` = primeiro destino que **não** é facebook.com nem instagram.com.

Cabeçalho obrigatório do módulo:
```python
"""
Parser da Biblioteca de Anúncios da Meta — funções puras, sem I/O.

CÓPIA DE PRODUÇÃO. Existe um gêmeo em tools/adlib_prospect.py no repo raiz,
usado para exploração local. leadflow-backend é submódulo e não enxerga
tools/, por isso a duplicação é consciente. Mudou aqui? Considere lá também.

Travado por tests/test_adlib_extracao.py contra 34 cards reais.
"""
```

- [ ] **Step 4: Rodar até passar**

```bash
python -m pytest tests/test_adlib_extracao.py -q
```
Esperado: `13 passed`

- [ ] **Step 5: Commit**

```bash
git add app/services/adlib.py tests/test_adlib_extracao.py tests/fixtures/adlib_cards_2026-08-13.json
git commit -m "feat(prospeccao): parser da Ad Library com golden de 34 cards reais"
```

---

## Task 3: Segundo hop — telefone na landing page

Rendimento medido: ~1 em 4 LPs. Nada pode depender dele.

**Files:**
- Create: `leadflow-backend/tests/test_adlib_enrich.py`
- Create: `leadflow-backend/app/services/adlib_enrich.py`

- [ ] **Step 1: Escrever o teste (falha)**

```python
"""
Segundo hop: a landing page do anúncio expõe telefone de WhatsApp?

Rendimento medido em 13/08: 3 de 11 LPs. O teto de tempo importa mais que a
cobertura — uma LP lenta não pode segurar a rodada inteira.
"""
import asyncio
import pytest

from app.services.adlib_enrich import extrair_whatsapp, enriquecer


@pytest.mark.parametrize("html,esperado", [
    ('<a href="https://wa.me/5542988167565">Fale comigo</a>', "5542988167565"),
    ('<a href="https://api.whatsapp.com/send?phone=55021975617771&text=oi">x</a>',
     "55021975617771"),
    ("<a href='https://api.whatsapp.com/send?text=oi&phone=5511999998888'>x</a>",
     "5511999998888"),
    ('<a href="https://respondi.app/abc123">x</a>', ""),      # slug, sem numero
    ("<p>me chama no whatsapp</p>", ""),                       # texto nao e link
    ("<a href='https://wa.me/'>x</a>", ""),                    # sem numero
])
def test_extrair_whatsapp(html, esperado):
    assert extrair_whatsapp(html) == esperado


def test_teto_de_tempo_respeitado(monkeypatch):
    """LP lenta nao segura a rodada. Devolve o que achou ate o teto."""
    async def _lenta(url, **kw):
        await asyncio.sleep(5)
        return '<a href="https://wa.me/5511111111111">x</a>'

    async def _rapida(url, **kw):
        return '<a href="https://wa.me/5522222222222">x</a>'

    async def fake_get(url, **kw):
        return await (_rapida(url) if "rapida" in url else _lenta(url))

    monkeypatch.setattr("app.services.adlib_enrich._baixar", fake_get)

    urls = ["http://rapida.com"] + [f"http://lenta{i}.com" for i in range(10)]
    achados = asyncio.run(enriquecer(urls, teto_seg=1.0))

    assert achados.get("http://rapida.com") == "5522222222222"
    assert len(achados) < len(urls), "deveria ter desistido das lentas"


def test_lp_quebrada_nao_derruba(monkeypatch):
    async def fake_get(url, **kw):
        if "ruim" in url:
            raise ConnectionError("boom")
        return '<a href="https://wa.me/5533333333333">x</a>'

    monkeypatch.setattr("app.services.adlib_enrich._baixar", fake_get)
    achados = asyncio.run(enriquecer(["http://ruim.com", "http://boa.com"], teto_seg=10))
    assert achados == {"http://boa.com": "5533333333333"}
```

- [ ] **Step 2: Rodar para ver falhar**

```bash
python -m pytest tests/test_adlib_enrich.py -q
```
Esperado: FAIL — módulo inexistente

- [ ] **Step 3: Implementar**

```python
"""
Segundo hop da prospecção: telefone de WhatsApp na landing page do anúncio.

POR QUE UM SEGUNDO HOP
----------------------
O anúncio em si NÃO expõe telefone. Medição de 13/08 em 4 termos, 205 anúncios:
5 tinham CTA de WhatsApp (2,4%), e o único link real vinha sem o parâmetro
`phone`. Não é falha do scraper — anúncio Click-to-WhatsApp é roteado por
dentro da Meta e o número nunca fica público.

O número aparece um hop adiante, na landing page: 3 de 11 LPs no teste.
É HTTP simples, sem browser, por isso vale o custo. Mas é BÔNUS — o canal
confiável continua sendo o Instagram (50% dos anúncios).
"""
import asyncio
import re

import httpx

# ordem importa: wa.me primeiro (o mais limpo), depois as variações com query
RE_WA = re.compile(
    r"wa\.me/(\d{10,15})"
    r"|(?:api\.)?whatsapp\.com/send\?[^\"'<>\s]*?phone=(\d{10,15})",
    re.I,
)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def extrair_whatsapp(html: str) -> str:
    """Primeiro telefone de WhatsApp no HTML. '' se não houver."""
    m = RE_WA.search(html or "")
    if not m:
        return ""
    return next((g for g in m.groups() if g), "")


async def _baixar(url: str, timeout: float = 15.0) -> str:
    """Isolado para o teste substituir sem tocar na rede."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as http:
        r = await http.get(url, headers={"User-Agent": UA})
        return r.text


async def _uma(url: str) -> tuple[str, str]:
    try:
        return url, extrair_whatsapp(await _baixar(url))
    except Exception:
        return url, ""          # LP fora do ar não derruba a rodada


async def enriquecer(urls: list[str], teto_seg: float = 90.0) -> dict[str, str]:
    """Telefone por landing page, dentro de um teto de tempo TOTAL.

    O teto vale mais que a cobertura: uma LP pendurada não pode segurar a
    rodada. Estourou, devolve o que já achou e o resto fica pra amanhã —
    a campanha roda todo dia de qualquer forma.
    """
    achados: dict[str, str] = {}
    tarefas = [asyncio.create_task(_uma(u)) for u in dict.fromkeys(urls)]
    try:
        for fut in asyncio.as_completed(tarefas, timeout=teto_seg):
            url, tel = await fut
            if tel:
                achados[url] = tel
    except (asyncio.TimeoutError, TimeoutError):
        pass
    finally:
        for t in tarefas:
            if not t.done():
                t.cancel()
    return achados
```

- [ ] **Step 4: Rodar até passar**

```bash
python -m pytest tests/test_adlib_enrich.py -q
```
Esperado: `8 passed` (6 do parametrize + teto + LP quebrada)

- [ ] **Step 5: Commit**

```bash
git add app/services/adlib_enrich.py tests/test_adlib_enrich.py
git commit -m "feat(prospeccao): segundo hop busca telefone na landing page"
```

---

## Task 4: Upsert que não pisa no status

**A task mais importante do plano.** Se o upsert errar, a rodada das 4h apaga todo "contatado" marcado no dia anterior — e o usuário só descobre semanas depois.

**Files:**
- Create: `leadflow-backend/tests/test_adlib_store.py`
- Create: `leadflow-backend/app/services/adlib_store.py`

- [ ] **Step 1: Escrever o teste (falha)**

```python
"""
Persistência da prospecção — a regra que faz a retroalimentação funcionar.

A rodada diária ATUALIZA dias_no_ar/anuncios_ativos/visto_em e NUNCA toca em
status/contatado_em/lead_id. Sem isso, a rodada de amanhã zera o "contatado"
marcado hoje.

Incidente de referência (31/07): um UPDATE sem WHERE sobrescreveu followups de
TODAS as empresas. Por isso o teste também trava que o update é por id.
"""
import pytest

from app.services.adlib_store import montar_upsert, campos_de_atualizacao


def test_campos_de_atualizacao_nao_incluem_status():
    campos = campos_de_atualizacao()
    for proibido in ("status", "contatado_em", "lead_id", "criado_em"):
        assert proibido not in campos, f"{proibido} NAO pode ser sobrescrito pela rodada"


def test_campos_de_atualizacao_incluem_os_moveis():
    campos = campos_de_atualizacao()
    for esperado in ("dias_no_ar", "anuncios_ativos", "visto_em"):
        assert esperado in campos


def test_prospect_novo_nasce_como_novo():
    novo, update = montar_upsert(
        existente=None,
        prospect={"chave": "k1", "anunciante": "A", "dias_no_ar": 100},
        empresa_id="e1", campanha_id="c1",
    )
    assert novo is not None
    assert novo["status"] == "novo"
    assert novo["empresa_id"] == "e1" and novo["campanha_id"] == "c1"
    assert update is None


def test_prospect_existente_preserva_status():
    existente = {"id": "p1", "status": "contatado", "contatado_em": "2026-08-01T10:00:00Z",
                 "dias_no_ar": 90, "instagram": "https://www.instagram.com/x"}
    novo, update = montar_upsert(
        existente=existente,
        prospect={"chave": "k1", "anunciante": "A", "dias_no_ar": 100, "anuncios_ativos": 2},
        empresa_id="e1", campanha_id="c1",
    )
    assert novo is None
    assert update["_id"] == "p1", "update DEVE ser por id — nunca em massa"
    assert "status" not in update and "contatado_em" not in update
    assert update["dias_no_ar"] == 100
    assert update["anuncios_ativos"] == 2
    assert "visto_em" in update


def test_contato_so_preenche_quando_vazio():
    """Não sobrescreve telefone bom com vazio, nem apaga o que já tinha."""
    existente = {"id": "p1", "status": "novo", "whatsapp": "5511999998888", "instagram": ""}
    _, update = montar_upsert(
        existente=existente,
        prospect={"chave": "k1", "anunciante": "A", "dias_no_ar": 10,
                  "whatsapp": "", "instagram": "https://www.instagram.com/novo"},
        empresa_id="e1", campanha_id="c1",
    )
    assert "whatsapp" not in update, "nao pode apagar telefone ja conhecido"
    assert update["instagram"] == "https://www.instagram.com/novo", "vazio deve ser preenchido"
```

- [ ] **Step 2: Rodar para ver falhar**

```bash
python -m pytest tests/test_adlib_store.py -q
```

- [ ] **Step 3: Implementar**

```python
"""
Persistência dos prospects — decide o que a rodada diária pode e não pode tocar.

Funções puras (montar_upsert/campos_de_atualizacao) separadas do I/O de propósito:
a regra crítica fica testável sem Supabase.
"""
from datetime import datetime, timezone

# Campos que a rodada diária pode atualizar num prospect que já existe.
# status/contatado_em/lead_id ficam DE FORA: são do usuário, não do robô.
_MOVEIS = ("dias_no_ar", "anuncios_ativos", "visto_em")
# Campos de contato: só preenchem quando a coluna está vazia (nunca apagam).
_CONTATO = ("instagram", "page_url", "whatsapp", "lp_url", "ad_id", "inicio")


def campos_de_atualizacao() -> tuple[str, ...]:
    return _MOVEIS


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def montar_upsert(existente: dict | None, prospect: dict,
                  empresa_id: str, campanha_id: str) -> tuple[dict | None, dict | None]:
    """Devolve (linha_para_insert, dict_para_update). Exatamente um é None.

    O update carrega `_id` — quem persiste DEVE usar `.eq("id", _id)`. Update
    em massa aqui repetiria o incidente de 31/07.
    """
    if existente is None:
        linha = {
            "empresa_id": empresa_id,
            "campanha_id": campanha_id,
            "status": "novo",
            "visto_em": _agora(),
            **{k: v for k, v in prospect.items() if v not in (None, "")},
        }
        linha.setdefault("anuncios_ativos", 1)
        return linha, None

    update: dict = {"_id": existente["id"], "visto_em": _agora()}
    for campo in _MOVEIS:
        if campo == "visto_em":
            continue
        if prospect.get(campo) is not None:
            update[campo] = prospect[campo]
    for campo in _CONTATO:
        novo = prospect.get(campo)
        if novo and not existente.get(campo):
            update[campo] = novo
    return None, update
```

Adicionar depois, no mesmo módulo, a função de I/O:

```python
def salvar(sb, empresa_id: str, campanha_id: str, prospects: list[dict]) -> dict:
    """Aplica os upserts. Devolve {'novos': n, 'atualizados': n}."""
    chaves = [p["chave"] for p in prospects]
    if not chaves:
        return {"novos": 0, "atualizados": 0}
    existentes = {
        r["chave"]: r
        for r in (sb.table("prospeccao_prospects")
                    .select("*")
                    .eq("empresa_id", empresa_id)
                    .eq("campanha_id", campanha_id)
                    .in_("chave", chaves)
                    .execute().data or [])
    }
    novos, atualizados = [], 0
    for p in prospects:
        linha, update = montar_upsert(existentes.get(p["chave"]), p, empresa_id, campanha_id)
        if linha:
            novos.append(linha)
        elif update:
            pid = update.pop("_id")
            sb.table("prospeccao_prospects").update(update).eq("id", pid).execute()
            atualizados += 1
    if novos:
        sb.table("prospeccao_prospects").insert(novos).execute()
    return {"novos": len(novos), "atualizados": atualizados}
```

- [ ] **Step 4: Rodar até passar**

```bash
python -m pytest tests/test_adlib_store.py -q
```
Esperado: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add app/services/adlib_store.py tests/test_adlib_store.py
git commit -m "feat(prospeccao): upsert diario nunca sobrescreve status do usuario"
```

---

## Task 5: Runner — browser, bloqueio de CDN, orquestração

**Files:**
- Create: `leadflow-backend/app/services/adlib_runner.py`

- [ ] **Step 1: Implementar o runner**

Pontos que **não** podem ser simplificados:

**Bloqueio de CDN por URL, nunca por `resource_type`.** Medido em 13/08: sem bloqueio 23,5 MB por termo; bloqueando `image`/`media`/`font` por tipo **piora para 77 MB**, porque o Facebook re-busca a imagem via `fetch` e o filtro por tipo não pega o retry; bloqueando `scontent*.fbcdn.net` por URL cai para 10,8 MB — e ainda rende mais cards (65 contra 59), porque a página renderiza mais rápido no mesmo tempo de scroll.

**Detecção de bloqueio.** Se a Meta pedir login, gravar `ultimo_erro='meta_pediu_login'`. Bloqueio silencioso que parece "0 prospects" é o pior modo de falha: o usuário acha que o nicho secou quando o IP caiu.

**Proxy.** Só quando `SCRAPER_PROXY_URL` existir. Nunca o proxy do Evolution — requisitos opostos (Evolution precisa de IP sticky, scraper quer rotativo).

```python
"""
Executor de uma campanha de prospecção. Roda como SUBPROCESSO:

    python -m app.services.adlib_runner <campanha_id>

Por que subprocesso: Playwright síncrono dentro do event loop do APScheduler
travaria o processo inteiro. Isolado, um Chromium pendurado morre sozinho
(o chamador usa asyncio.wait_for + kill) sem levar o serviço junto.
"""
import os
import re
import sys
from datetime import date, datetime, timezone
from urllib.parse import quote_plus

from app.db.client import get_supabase
from app.services.adlib import JS_COLETA, extrair
from app.services.adlib_enrich import enriquecer
from app.services.adlib_store import salvar

BASE = (
    "https://www.facebook.com/ads/library/"
    "?active_status=active&ad_type=all&country=BR"
    "&q={termo}&search_type=keyword_unordered&media_type=all"
)

# Bloqueio POR URL do CDN. Ver docstring da Task 5 no plano: bloquear por
# resource_type piora 3x porque o Facebook re-busca a imagem via fetch.
RE_CDN = re.compile(r"(scontent|video)[\w.-]*\.(xx\.)?fbcdn\.net", re.I)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _coletar_cards(termo: str, paginas: int) -> tuple[list[dict], str]:
    """Devolve (cards, erro). erro='' quando deu certo."""
    from playwright.sync_api import sync_playwright

    proxy = os.getenv("SCRAPER_PROXY_URL", "").strip()
    with sync_playwright() as p:
        nav = p.chromium.launch(
            headless=True,
            proxy={"server": proxy} if proxy else None,
        )
        ctx = nav.new_context(locale="pt-BR", viewport={"width": 1400, "height": 900},
                              user_agent=UA)
        ctx.route("**/*", lambda r: r.abort() if RE_CDN.search(r.request.url)
                  else r.continue_())
        pg = ctx.new_page()
        try:
            pg.goto(BASE.format(termo=quote_plus(termo)),
                    wait_until="domcontentloaded", timeout=60_000)
            pg.wait_for_timeout(4_000)
            if "login" in pg.url or (pg.title() or "").lower().startswith("entrar"):
                return [], "meta_pediu_login"
            for _ in range(paginas):
                pg.mouse.wheel(0, 4_000)
                pg.wait_for_timeout(2_500)
            return pg.evaluate(JS_COLETA), ""
        finally:
            nav.close()


def rodar(campanha_id: str) -> int:
    sb = get_supabase()
    camp = (sb.table("prospeccao_campanhas").select("*")
              .eq("id", campanha_id).limit(1).execute().data or [None])[0]
    if not camp:
        print(f"[PROSPECCAO] campanha {campanha_id} não existe")
        return 1

    termo = camp["termo"]
    print(f"[PROSPECCAO] {termo!r} iniciando")
    cards, erro = _coletar_cards(termo, camp.get("paginas") or 6)

    if erro:
        sb.table("prospeccao_campanhas").update(
            {"ultimo_erro": erro, "ultima_rodada": datetime.now(timezone.utc).isoformat(),
             "rodar_solicitado_em": None}
        ).eq("id", campanha_id).execute()
        print(f"[PROSPECCAO] {termo!r} bloqueado: {erro}")
        return 2

    min_dias = camp.get("min_dias") or 60
    achados = [p for p in extrair(cards, date.today()) if p.dias_no_ar >= min_dias]

    lps = [p.lp_url for p in achados if p.lp_url]
    if lps:
        import asyncio
        telefones = asyncio.run(enriquecer(lps, teto_seg=90.0))
        for p in achados:
            if p.lp_url in telefones:
                p.whatsapp = telefones[p.lp_url]

    from dataclasses import asdict
    res = salvar(sb, camp["empresa_id"], campanha_id, [asdict(p) for p in achados])

    sb.table("prospeccao_campanhas").update(
        {"ultima_rodada": datetime.now(timezone.utc).isoformat(),
         "ultimo_erro": None, "rodar_solicitado_em": None}
    ).eq("id", campanha_id).execute()

    print(f"[PROSPECCAO] {termo!r}: {len(cards)} cards, {len(achados)} com {min_dias}+ dias, "
          f"{res['novos']} novos, {res['atualizados']} atualizados")
    return 0


if __name__ == "__main__":
    sys.exit(rodar(sys.argv[1]))
```

- [ ] **Step 2: Rodar contra uma campanha real**

Inserir uma campanha à mão no Supabase e:
```bash
cd leadflow-backend
python -m app.services.adlib_runner <campanha_id>
```
Esperado: `[PROSPECCAO] 'mentoria para mulheres': 5x cards, 13 com 60+ dias, 13 novos, 0 atualizados`

- [ ] **Step 3: Rodar de novo — prova a idempotência**

```bash
python -m app.services.adlib_runner <mesmo_id>
```
Esperado: `0 novos, 13 atualizados`

- [ ] **Step 4: Commit**

```bash
git add app/services/adlib_runner.py
git commit -m "feat(prospeccao): runner com bloqueio de CDN e deteccao de login"
```

---

## Task 6: O 4º serviço — `leadflow-scraper`

**Files:**
- Create: `leadflow-backend/Dockerfile.scraper`
- Create: `leadflow-backend/app/scraper_main.py`
- Modify: `leadflow-backend/requirements.txt`

- [ ] **Step 1: Adicionar playwright ao requirements**

```
playwright==1.62.0
```

- [ ] **Step 2: Criar `Dockerfile.scraper`**

```dockerfile
# Imagem do leadflow-scraper — o ÚNICO serviço com Chromium.
# backend e scheduler continuam em python:3.11-slim sem browser: Chromium
# travado ou IP bloqueado morre isolado, sem encostar em follow-up,
# auto-cura ou confirmação.
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential curl libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

COPY . .

CMD ["python", "-m", "app.scraper_main"]
```

- [ ] **Step 3: Criar `app/scraper_main.py`**

```python
"""
Entrypoint do serviço leadflow-scraper.

APScheduler PRÓPRIO, carregando SÓ os jobs de prospecção — de propósito. Este
processo tem Chromium; nada de follow-up, auto-cura ou confirmação roda aqui.

Dois jobs:
  prospeccao_diaria  cron 04:00 BR — campanhas ativas, EM SÉRIE
  prospeccao_fila    a cada 2 min  — pega quem tem rodar_solicitado_em

Desligar sem redeploy: PROSPECCAO_ENABLED=false no serviço.
"""
import asyncio
import os
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.client import get_supabase

TIMEOUT_SEG = 300


async def _rodar_uma(campanha_id: str) -> None:
    """Subprocesso com timeout duro. Chromium pendurado morre sozinho."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "app.services.adlib_runner", campanha_id,
    )
    try:
        await asyncio.wait_for(proc.wait(), timeout=TIMEOUT_SEG)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        print(f"[SCRAPER] campanha {campanha_id} estourou {TIMEOUT_SEG}s — morta")


async def rodada_diaria() -> None:
    sb = get_supabase()
    campanhas = (sb.table("prospeccao_campanhas").select("id,termo")
                   .eq("ativa", True).execute().data or [])
    print(f"[SCRAPER] rodada diária: {len(campanhas)} campanhas")
    for c in campanhas:                      # EM SÉRIE — nunca paralelo
        await _rodar_uma(c["id"])


async def rodada_fila() -> None:
    sb = get_supabase()
    pedidas = (sb.table("prospeccao_campanhas").select("id,termo")
                 .not_.is_("rodar_solicitado_em", "null").execute().data or [])
    for c in pedidas:
        print(f"[SCRAPER] fila: {c['termo']!r}")
        await _rodar_uma(c["id"])


def main() -> None:
    if os.getenv("PROSPECCAO_ENABLED", "false").lower() != "true":
        print("[SCRAPER] PROSPECCAO_ENABLED != true — ocioso")
    sched = AsyncIOScheduler(timezone="America/Sao_Paulo",
                             job_defaults={"misfire_grace_time": None})
    if os.getenv("PROSPECCAO_ENABLED", "false").lower() == "true":
        sched.add_job(rodada_diaria, "cron", hour=4, minute=0,
                      id="prospeccao_diaria", replace_existing=True, max_instances=1)
        sched.add_job(rodada_fila, "interval", minutes=2,
                      id="prospeccao_fila", replace_existing=True, max_instances=1)
        print("[SCRAPER] jobs registrados (diária 04:00 BR, fila 2min)")
    sched.start()
    asyncio.get_event_loop().run_forever()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Build local para provar que a imagem sobe**

```bash
cd leadflow-backend
docker build -f Dockerfile.scraper -t leadflow-scraper-test .
```
Esperado: build completo. A imagem fica em torno de 900 MB–1 GB (base + Chromium).

- [ ] **Step 5: Commit**

```bash
git add Dockerfile.scraper app/scraper_main.py requirements.txt
git commit -m "feat(prospeccao): servico leadflow-scraper isolado com Chromium"
```

---

## Task 7: Router `/prospeccao`

**Files:**
- Create: `leadflow-backend/app/routers/prospeccao.py`
- Modify: `leadflow-backend/app/main.py` (perto da linha 347, junto dos outros `include_router`)

- [ ] **Step 1: Implementar o router**

Todos os endpoints com `Depends(get_current_empresa_id)` e **todo** query filtrando por `empresa_id` — é o isolamento multi-tenant do sistema inteiro.

```python
"""
Router da prospecção via Biblioteca de Anúncios.

Este serviço NÃO tem Chromium. "Rodar agora" ENFILEIRA (grava
rodar_solicitado_em); quem executa é o leadflow-scraper, que varre a fila a
cada 2 min. Escolhido em vez de HTTP interno: sem segredo compartilhado, sem
request pendurado esperando um scrape de 90s, e o pedido sobrevive a restart.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import get_current_empresa_id
from app.db.client import get_supabase

router = APIRouter(prefix="/prospeccao", tags=["prospeccao"])

STATUS_VALIDOS = {"novo", "contatado", "respondeu", "descartado"}


class CampanhaIn(BaseModel):
    termo: str = Field(min_length=2, max_length=120)
    min_dias: int = Field(default=60, ge=0, le=3650)
    paginas: int = Field(default=6, ge=1, le=30)


class CampanhaPatch(BaseModel):
    ativa: bool | None = None
    min_dias: int | None = Field(default=None, ge=0, le=3650)
    paginas: int | None = Field(default=None, ge=1, le=30)


class ProspectPatch(BaseModel):
    status: str


@router.get("/campanhas")
async def listar_campanhas(empresa_id: str = Depends(get_current_empresa_id)):
    sb = get_supabase()
    camps = (sb.table("prospeccao_campanhas").select("*")
               .eq("empresa_id", empresa_id).order("criada_em", desc=True)
               .execute().data or [])
    for c in camps:
        stats = (sb.table("prospeccao_prospects").select("status")
                   .eq("empresa_id", empresa_id).eq("campanha_id", c["id"])
                   .execute().data or [])
        c["total"] = len(stats)
        c["novos"] = sum(1 for s in stats if s["status"] == "novo")
        c["na_fila"] = c.get("rodar_solicitado_em") is not None
    return camps


@router.post("/campanhas")
async def criar_campanha(body: CampanhaIn,
                         empresa_id: str = Depends(get_current_empresa_id)):
    sb = get_supabase()
    termo = body.termo.strip()
    ja = (sb.table("prospeccao_campanhas").select("id")
            .eq("empresa_id", empresa_id).eq("termo", termo).execute().data or [])
    if ja:
        raise HTTPException(409, "Já existe campanha com esse termo")
    r = sb.table("prospeccao_campanhas").insert({
        "empresa_id": empresa_id, "termo": termo,
        "min_dias": body.min_dias, "paginas": body.paginas,
        "rodar_solicitado_em": datetime.now(timezone.utc).isoformat(),  # roda já
    }).execute()
    return r.data[0]


@router.patch("/campanhas/{campanha_id}")
async def editar_campanha(campanha_id: str, body: CampanhaPatch,
                          empresa_id: str = Depends(get_current_empresa_id)):
    campos = {k: v for k, v in body.model_dump().items() if v is not None}
    if not campos:
        raise HTTPException(400, "Nada para atualizar")
    sb = get_supabase()
    r = (sb.table("prospeccao_campanhas").update(campos)
           .eq("id", campanha_id).eq("empresa_id", empresa_id).execute())
    if not r.data:
        raise HTTPException(404, "Campanha não encontrada")
    return r.data[0]


@router.delete("/campanhas/{campanha_id}")
async def remover_campanha(campanha_id: str,
                           empresa_id: str = Depends(get_current_empresa_id)):
    sb = get_supabase()
    (sb.table("prospeccao_campanhas").delete()
       .eq("id", campanha_id).eq("empresa_id", empresa_id).execute())
    return {"ok": True}


@router.post("/campanhas/{campanha_id}/rodar")
async def rodar_agora(campanha_id: str,
                      empresa_id: str = Depends(get_current_empresa_id)):
    """ENFILEIRA. O leadflow-scraper pega em até 2 min."""
    sb = get_supabase()
    r = (sb.table("prospeccao_campanhas")
           .update({"rodar_solicitado_em": datetime.now(timezone.utc).isoformat()})
           .eq("id", campanha_id).eq("empresa_id", empresa_id).execute())
    if not r.data:
        raise HTTPException(404, "Campanha não encontrada")
    return {"enfileirada": True}


@router.get("/prospects")
async def listar_prospects(campanha_id: str = Query(...),
                           status: str | None = Query(None),
                           empresa_id: str = Depends(get_current_empresa_id)):
    sb = get_supabase()
    q = (sb.table("prospeccao_prospects").select("*")
           .eq("empresa_id", empresa_id).eq("campanha_id", campanha_id))
    if status:
        q = q.eq("status", status)
    return q.order("dias_no_ar", desc=True).execute().data or []


@router.patch("/prospects/{prospect_id}")
async def mudar_status(prospect_id: str, body: ProspectPatch,
                       empresa_id: str = Depends(get_current_empresa_id)):
    if body.status not in STATUS_VALIDOS:
        raise HTTPException(400, f"status inválido: {body.status}")
    campos = {"status": body.status}
    if body.status == "contatado":
        campos["contatado_em"] = datetime.now(timezone.utc).isoformat()
    sb = get_supabase()
    r = (sb.table("prospeccao_prospects").update(campos)
           .eq("id", prospect_id).eq("empresa_id", empresa_id).execute())
    if not r.data:
        raise HTTPException(404, "Prospect não encontrado")
    return r.data[0]


@router.post("/prospects/{prospect_id}/virar-lead")
async def virar_lead(prospect_id: str,
                     empresa_id: str = Depends(get_current_empresa_id)):
    """Única ponte entre prospect e o funil — e é sempre manual."""
    sb = get_supabase()
    p = (sb.table("prospeccao_prospects").select("*")
           .eq("id", prospect_id).eq("empresa_id", empresa_id)
           .limit(1).execute().data or [None])[0]
    if not p:
        raise HTTPException(404, "Prospect não encontrado")
    if p.get("lead_id"):
        return {"lead_id": p["lead_id"], "ja_existia": True}

    # pipeline_status="novo" é OBRIGATÓRIO: o Kanban filtra por ele
    # (whitelist em leads.py:2051). Lead sem pipeline_status nasce invisível
    # na tela de Pipeline — o usuário promove e nada aparece.
    lead = sb.table("leads").insert({
        "empresa_id": empresa_id,
        "nome": p["anunciante"],
        "telefone": p.get("whatsapp") or None,
        "origem": "adlib",
        "pipeline_status": "novo",
    }).execute().data[0]

    sb.table("prospeccao_prospects").update({
        "lead_id": lead["id"], "status": "contatado",
        "contatado_em": datetime.now(timezone.utc).isoformat(),
    }).eq("id", prospect_id).execute()
    return {"lead_id": lead["id"], "ja_existia": False}
```

- [x] **Step 1b: `leads.telefone` aceita nulo — VERIFICADO em 13/08 ✅**

Consultado no Supabase: `nome`, `telefone` e `pipeline_status` são todos
`is_nullable = YES`. O `virar-lead` funciona para prospect que só tem Instagram
(50% da amostra) sem precisar recusar ninguém. **Nenhuma mudança necessária.**

Fica registrado o que **não** se deve fazer se um dia isso mudar: nunca preencher
`telefone` com o @ do Instagram ou um placeholder. Telefone inválido em `leads` é
o que o agente usa pra disparar — viraria mensagem pra número inexistente ou, pior,
pra número de terceiro. A saída correta seria recusar a promoção, não inventar dado.

- [ ] **Step 2: Registrar em `app/main.py`**

Adicionar no import e depois da linha 347 (`app.include_router(meta_ads.router)`):
```python
app.include_router(prospeccao.router)
```

- [ ] **Step 3: Verificar que o backend sobe e a rota existe**

```bash
cd leadflow-backend
python -c "from app.main import app; print([r.path for r in app.routes if 'prospeccao' in r.path])"
```
Esperado: as 8 rotas listadas.

- [ ] **Step 4: Commit**

```bash
git add app/routers/prospeccao.py app/main.py
git commit -m "feat(prospeccao): router com fila para rodar agora"
```

---

## Task 8: Frontend — a tela

**Files:**
- Create: `leadflow-frontend/src/modules/campaigns/api.ts`
- Create: `leadflow-frontend/src/modules/campaigns/ProspectsTable.tsx`
- Modify: `leadflow-frontend/src/modules/campaigns/CampaignsPage.tsx` (substitui o stub inteiro)

- [ ] **Step 1: Tipos e chamadas (`api.ts`)**

```ts
import { api } from '@/lib/api'

export interface Campanha {
  id: string
  termo: string
  min_dias: number
  paginas: number
  ativa: boolean
  ultima_rodada: string | null
  ultimo_erro: string | null
  na_fila: boolean
  total: number
  novos: number
}

export interface Prospect {
  id: string
  anunciante: string
  instagram: string | null
  page_url: string | null
  whatsapp: string | null
  lp_url: string | null
  dias_no_ar: number
  anuncios_ativos: number
  status: 'novo' | 'contatado' | 'respondeu' | 'descartado'
  lead_id: string | null
  visto_em: string
}

export const prospeccao = {
  campanhas: () => api.get<Campanha[]>('/prospeccao/campanhas'),
  criar: (termo: string, min_dias: number, paginas: number) =>
    api.post<Campanha>('/prospeccao/campanhas', { termo, min_dias, paginas }),
  editar: (id: string, campos: Partial<Pick<Campanha, 'ativa' | 'min_dias' | 'paginas'>>) =>
    api.patch<Campanha>(`/prospeccao/campanhas/${id}`, campos),
  remover: (id: string) => api.delete<{ ok: boolean }>(`/prospeccao/campanhas/${id}`),
  rodar: (id: string) =>
    api.post<{ enfileirada: boolean }>(`/prospeccao/campanhas/${id}/rodar`, {}),
  prospects: (campanhaId: string, status?: string) =>
    api.get<Prospect[]>(
      `/prospeccao/prospects?campanha_id=${campanhaId}${status ? `&status=${status}` : ''}`),
  status: (id: string, status: Prospect['status']) =>
    api.patch<Prospect>(`/prospeccao/prospects/${id}`, { status }),
  virarLead: (id: string) =>
    api.post<{ lead_id: string }>(`/prospeccao/prospects/${id}/virar-lead`, {}),
}
```

- [ ] **Step 2: `ProspectsTable.tsx`**

Requisitos:
- Colunas: dias no ar (destaque — é o sinal que importa), anunciante, Instagram (link), WhatsApp (link `wa.me`), anúncios ativos, status
- Ações por linha: `Contatado`, `Descartar`, `Virar lead →`
- Filtro por status e por "tem contato"
- Linha `descartado` fica esmaecida
- Mutations invalidam `['prospects', campanhaId]`
- **Horário em São Paulo** — formatar `visto_em` com `timeZone: 'America/Sao_Paulo'`, nunca UTC cru

- [ ] **Step 3: `CampaignsPage.tsx`**

Substitui o stub. Requisitos:
- `useQuery(['campanhas'])` → `prospeccao.campanhas()`
- Sem campanhas: mantém o `EmptyState` existente, mas o botão abre o modal de criação (hoje é `onClick: () => {}`)
- Cada campanha vira card clicável: termo, `total` prospects, `novos` em destaque, "há Xh" da última rodada
- `ultimo_erro === 'meta_pediu_login'` → aviso visível: *"A Meta pediu login — o IP pode ter sido bloqueado"*. **Nunca** mostrar "0 prospects" nesse caso
- `na_fila` → badge "na fila…", com `refetchInterval: 15000` enquanto houver alguma na fila
- Campanha selecionada renderiza `<ProspectsTable campanhaId={...} />`
- Modal de criação: termo (obrigatório), min_dias (default 60), páginas (default 6)

- [ ] **Step 4: Verificar build**

```bash
cd leadflow-frontend
npm run build
```
Esperado: build sem erro de TypeScript.

- [ ] **Step 5: Commit**

```bash
git add src/modules/campaigns/api.ts src/modules/campaigns/ProspectsTable.tsx src/modules/campaigns/CampaignsPage.tsx
git commit -m "feat(campanhas): tela de prospeccao com acoes de contato"
```

---

## Task 9: Ponteiros dos submódulos e deploy

- [ ] **Step 1: Commitar os ponteiros no repo raiz**

```bash
cd c:/Projetos/Leadflow
git add leadflow-backend leadflow-frontend
git commit -m "chore: aponta submodulos pra prospeccao via Ad Library"
git push
```

- [ ] **Step 2: Criar o serviço no Easypanel**

- Nome: **leadflow-scraper**
- Repo: o mesmo do `leadflow-backend`
- Dockerfile: `Dockerfile.scraper`
- Env: todas as do backend (Supabase etc.) **mais** `PROSPECCAO_ENABLED=true`
- **Não** setar `SCRAPER_PROXY_URL` — só se a Meta bloquear

- [ ] **Step 3: Redeploy e verificação**

```
leadflow-backend  → /version deve mudar; conferir com
                    curl -s https://leadflow-backend.bqvcbz.easypanel.host/version
leadflow-frontend → sem /version; confirmar visualmente em /campaigns
leadflow-scraper  → docker logs deve mostrar
                    "[SCRAPER] jobs registrados (diária 04:00 BR, fila 2min)"
leadflow-scheduler→ NÃO precisa
```

- [ ] **Step 4: Teste de ponta a ponta**

1. Abrir `/campaigns`, criar campanha "mentoria para mulheres"
2. Em até 2 min o badge "na fila…" some e aparecem prospects
3. Marcar um como `Contatado`
4. Clicar "Rodar agora"; após a rodada, o prospect **continua** `contatado` — é a prova da regra do upsert em produção

---

## Riscos conhecidos

| Risco | Mitigação | Onde |
|---|---|---|
| RAM do VPS insuficiente para Chromium (300–500 MB de pico) | **Não verificado.** Checar RAM livre às 4h antes de habilitar | Task 9 |
| Meta bloqueia o IP do VPS | `SCRAPER_PROXY_URL` (residencial, rotativo, conta separada); detecção grava `meta_pediu_login` | Tasks 5, 8 |
| Meta troca o HTML | Golden de 34 cards quebra no CI | Task 2 |
| Parser divergir entre os dois repos | Cabeçalho em ambos apontando um pro outro | Task 2 |
| Rodada apagar "contatado" | `montar_upsert` testado; update sempre por `id` | Task 4 |
| ~~`leads.telefone` ser `NOT NULL`~~ | **RESOLVIDO 13/08** — é nullable; promoção funciona só com Instagram | Task 7 |
| Lead promovido invisível no Kanban | `pipeline_status="novo"` (whitelist em `leads.py:2051`) | Task 7 |
| `asdict()` perder a `chave` (é método hoje) | `chave` vira campo na dataclass | Task 2 |

## Fora de escopo

Disparo em massa a partir dos prospects, agente IA tocando prospect sozinho, descoberta automática de termos. Os três cabem depois sem refazer nada — o primeiro exige uma decisão de LGPD que não é técnica.
