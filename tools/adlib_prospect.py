#!/usr/bin/env python
"""
adlib_prospect — extrai anunciantes ativos da Biblioteca de Anúncios da Meta (BR)
e devolve um CSV de prospects pro LeadFlow.

POR QUE NAVEGADOR E NÃO API
---------------------------
A Ad Library API (`graph.facebook.com/.../ads_archive`) só devolve anúncios de
POLÍTICA e temas sociais. Anúncio comercial — que é o que interessa aqui — existe
só na interface pública. Por isso Playwright.

O SINAL QUE IMPORTA
-------------------
Não é "quem anuncia". É **há quanto tempo o mesmo anúncio está no ar**. Criativo
rodando há 60+ dias não é teimosia: é campanha que se paga. Quem sustenta campanha
paga há meses tem verba, tem lead entrando e tem o problema que o LeadFlow resolve.
Por isso o padrão de `--min-dias` é 60.

USO
---
    pip install playwright pandas && playwright install chromium

    python tools/adlib_prospect.py --termo "mentoria para mulheres" --min-dias 60
    python tools/adlib_prospect.py --termos termos.txt --paginas 8 --out prospects.csv
    python tools/adlib_prospect.py --termo "harmonização facial" --headful   # se pedir login

LIMITES — leia antes de usar
----------------------------
* A Meta às vezes exige login pra navegar a biblioteca. Rode com `--headful`, logue
  na janela que abrir e deixe rodar. Use uma conta que você não se importe de perder.
* Isto é coleta de dado PÚBLICO pra pesquisa comercial. Não é lista de disparo.
  Mandar mensagem em massa pra número raspado queima o número, viola o WhatsApp e
  te expõe na LGPD. O uso certo é: ranquear, escolher a dedo e abordar no canal
  público (DM do Instagram, formulário do site) em volume baixo.
* Os seletores da Ad Library mudam sem aviso. O parser aqui é por TEXTO
  ("Identificação da biblioteca"), justamente pra sobreviver a troca de classe CSS.
  Se um dia voltar zero, rode `--headful --debug` e olhe a tela.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote_plus

BASE = (
    "https://www.facebook.com/ads/library/"
    "?active_status=active&ad_type=all&country=BR"
    "&q={termo}&search_type=keyword_unordered&media_type=all"
)

MESES = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}

RE_ID = re.compile(r"Identifica[çc][ãa]o da biblioteca[:\s]+(\d+)", re.I)
RE_INICIO = re.compile(
    r"Veicula[çc][ãa]o iniciada em\s+(\d{1,2})\s+de\s+([a-zç]+)\.?\s+de\s+(\d{4})", re.I
)
RE_USOS = re.compile(r"(\d+)\s+an[úu]ncios?\s+us", re.I)


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _parse_data(txt: str) -> date | None:
    m = RE_INICIO.search(txt)
    if not m:
        return None
    dia, mes_txt, ano = m.groups()
    mes = MESES.get(_norm(mes_txt)[:3])
    if not mes:
        return None
    try:
        return date(int(ano), mes, int(dia))
    except ValueError:
        return None


@dataclass
class Prospect:
    anunciante: str
    page_url: str
    instagram: str
    ad_id: str
    inicio: str
    dias_no_ar: int
    anuncios_ativos: int
    termo: str

    def chave(self) -> str:
        return self.page_url or _norm(self.anunciante)


# JS roda no contexto da página: acha cada card pelo TEXTO e sobe até o container.
JS_COLETA = """
() => {
  const marcador = 'dentificação da biblioteca';
  const saida = [];
  const vistos = new Set();
  for (const el of document.querySelectorAll('div,span')) {
    if (!el.textContent || !el.textContent.includes(marcador)) continue;
    if (el.querySelector('div,span')) {
      // só o nó mais interno que contém o marcador — evita pegar a página toda
      const filhos = Array.from(el.querySelectorAll('div,span'));
      if (filhos.some(f => f.textContent && f.textContent.includes(marcador))) continue;
    }
    let card = el;
    for (let i = 0; i < 8 && card.parentElement; i++) {
      card = card.parentElement;
      if ((card.innerText || '').length > 220) break;
    }
    const texto = card.innerText || '';
    const id = (texto.match(/[Ii]dentifica\\S* da biblioteca[:\\s]+(\\d+)/) || [])[1];
    if (!id || vistos.has(id)) continue;
    vistos.add(id);
    const links = Array.from(card.querySelectorAll('a[href]')).map(a => a.href);
    saida.push({ texto, links });
  }
  return saida;
}
"""


def _extrair(cards: list[dict], termo: str, hoje: date) -> list[Prospect]:
    out: list[Prospect] = []
    for card in cards:
        texto = card.get("texto") or ""
        links = card.get("links") or []

        ad_id = (RE_ID.search(texto) or [None, ""])[1] if RE_ID.search(texto) else ""
        inicio = _parse_data(texto)
        if not inicio:
            continue

        page_url = next(
            (l.split("?")[0] for l in links
             if "facebook.com" in l and "/ads/" not in l and "l.php" not in l),
            "",
        )
        instagram = next((l.split("?")[0] for l in links if "instagram.com" in l), "")

        # nome do anunciante: linha logo após os metadados, a mais "nome-like"
        nome = ""
        for linha in (l.strip() for l in texto.splitlines()):
            if not linha or len(linha) > 60:
                continue
            n = _norm(linha)
            if any(p in n for p in (
                "identificacao", "veiculacao", "plataforma", "ativo", "patrocinado",
                "categoria", "ver detalhes", "ver resumo", "abrir", "este anuncio",
            )):
                continue
            nome = linha
            break

        usos = RE_USOS.search(texto)
        out.append(Prospect(
            anunciante=nome or "(sem nome)",
            page_url=page_url,
            instagram=instagram,
            ad_id=ad_id,
            inicio=inicio.isoformat(),
            dias_no_ar=(hoje - inicio).days,
            anuncios_ativos=int(usos.group(1)) if usos else 1,
            termo=termo,
        ))
    return out


def coletar(termo: str, paginas: int, headful: bool, debug: bool) -> list[Prospect]:
    from playwright.sync_api import sync_playwright

    hoje = date.today()
    url = BASE.format(termo=quote_plus(termo))
    achados: list[Prospect] = []

    with sync_playwright() as p:
        nav = p.chromium.launch(headless=not headful)
        ctx = nav.new_context(
            locale="pt-BR",
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
        )
        pg = ctx.new_page()
        print(f"[adlib] {termo!r} → {url}", file=sys.stderr)
        pg.goto(url, wait_until="domcontentloaded", timeout=60_000)
        pg.wait_for_timeout(4_000)

        if "login" in pg.url or _norm(pg.title()).startswith("entrar"):
            print("[adlib] a Meta pediu login. Rode com --headful e logue na janela.",
                  file=sys.stderr)
            if not headful:
                nav.close()
                return []
            pg.wait_for_timeout(45_000)  # janela pra você logar à mão

        for i in range(paginas):
            pg.mouse.wheel(0, 4_000)
            pg.wait_for_timeout(2_500)
            if debug:
                print(f"[adlib]   scroll {i + 1}/{paginas}", file=sys.stderr)

        cards = pg.evaluate(JS_COLETA)
        if debug:
            print(f"[adlib]   {len(cards)} cards brutos", file=sys.stderr)
            Path("adlib_debug.png").write_bytes(pg.screenshot(full_page=False))
        achados = _extrair(cards, termo, hoje)
        nav.close()

    return achados


def main() -> int:
    ap = argparse.ArgumentParser(description="Prospects da Biblioteca de Anúncios Meta (BR)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--termo", help="termo de busca (nicho)")
    g.add_argument("--termos", help="arquivo com um termo por linha")
    ap.add_argument("--min-dias", type=int, default=60,
                    help="descarta anúncio no ar há menos que isso (padrão 60)")
    ap.add_argument("--paginas", type=int, default=6, help="quantidade de scrolls")
    ap.add_argument("--out", default="prospects.csv")
    ap.add_argument("--headful", action="store_true", help="abre o navegador visível")
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    if a.termo:
        termos = [a.termo]
    else:
        termos = [
            l.strip() for l in Path(a.termos).read_text("utf-8").splitlines()
            if l.strip() and not l.lstrip().startswith("#")
        ]

    todos: dict[str, Prospect] = {}
    for termo in termos:
        try:
            for p in coletar(termo, a.paginas, a.headful, a.debug):
                if p.dias_no_ar < a.min_dias:
                    continue
                # mantém o registro mais antigo — mede há quanto tempo o anunciante insiste
                atual = todos.get(p.chave())
                if not atual or p.dias_no_ar > atual.dias_no_ar:
                    todos[p.chave()] = p
        except Exception as e:  # um termo quebrado não derruba a rodada
            print(f"[adlib] ERRO em {termo!r}: {type(e).__name__}: {e}", file=sys.stderr)

    linhas = sorted(todos.values(), key=lambda x: (-x.dias_no_ar, x.anunciante))
    if not linhas:
        print("[adlib] nada encontrado. Tente --headful --debug e confira adlib_debug.png.",
              file=sys.stderr)
        return 1

    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(linhas[0]).keys()))
        w.writeheader()
        for p in linhas:
            w.writerow(asdict(p))

    print(f"[adlib] {len(linhas)} anunciantes com anúncio no ar há {a.min_dias}+ dias → {a.out}")
    print(f"[adlib] top 5 por tempo de veiculação:")
    for p in linhas[:5]:
        print(f"   {p.dias_no_ar:>4}d  {p.anunciante[:44]:<44} {p.instagram or p.page_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
