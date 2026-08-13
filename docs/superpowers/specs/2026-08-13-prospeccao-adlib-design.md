# Prospecção via Biblioteca de Anúncios — design

**Data**: 2026-08-13
**Estado**: aprovado, pronto pro plano de implementação
**Tela**: `/campaigns` (hoje um stub sem backend)

---

## 1. O problema

A tela de Campanhas existe no menu, tem rota e sidebar, e é uma casca: 23 linhas de
JSX, um `EmptyState` e um botão com `onClick: () => {}`. Não há router `campaigns`
no backend nem tabela no Supabase.

Ao mesmo tempo, `tools/adlib_prospect.py` já extrai anunciantes ativos da Biblioteca
de Anúncios da Meta e ranqueia por **dias no ar** — o sinal de que a campanha se
paga, e portanto de que o anunciante tem verba e tem o problema que o LeadFlow
resolve. Hoje esse resultado morre num CSV local.

O objetivo é ligar os dois: a tela passa a listar campanhas de prospecção salvas,
que se retroalimentam sozinhas todo dia com anunciantes novos, com botões pra
marcar quem já foi contatado.

## 2. O que os dados dizem (medido, não suposto)

A premissa inicial era que "geralmente o anúncio tem o link do respondi.app", o que
daria telefone. **Isso não se confirmou.** Medição em 4 termos, 205 anúncios:

| termo | anúncios | com CTA de WhatsApp |
|---|---|---|
| mentoria emagrecimento | 43 | 0 |
| mentoria de vendas | 57 | 0 |
| harmonização facial | 60 | 2 |
| consultoria financeira | 45 | 3 |

5 em 205 (2,4%) — e 4 desses são apenas a palavra "whatsapp" no texto do anúncio,
sem link. O único link real era `api.whatsapp.com/send` **sem o parâmetro `phone`**.

Isso não é limitação do scraper: anúncio Click-to-WhatsApp é roteado internamente
pela Meta e o número nunca fica exposto na Biblioteca.

O telefone aparece **um hop adiante**, na landing page. Medição no termo
"mentoria para mulheres" (34 anúncios):

| etapa | quantidade |
|---|---|
| anúncios capturados | 34 |
| **com Instagram** | **17 (50%)** |
| com landing page | 11 LPs únicas (32%) |
| LPs que expõem WhatsApp | 3 |
| **anunciantes únicos com telefone** | **2 (~6%)** |

Exemplos reais colhidos: `wa.me/5542988167565`,
`api.whatsapp.com/send?phone=55021975617771`.

**Conclusão que orienta o design**: o canal confiável é o Instagram (50%). O
telefone é bônus de ~6%, vale buscar porque é barato, mas nada pode depender dele.

## 3. Decisões e por quê

| Decisão | Escolha | Razão |
|---|---|---|
| Entidade | Tabela `prospects` própria, promoção manual pro funil | Lead raspado na mesma base do inbound contamina BI, taxa de conversão e o agente |
| Runtime | 4º serviço `leadflow-scraper` | Chromium travado ou IP bloqueado morre isolado, sem encostar em follow-up/auto-cura/confirmação |
| Telefone | Segundo hop na LP, com teto de tempo | ~1 em 4 LPs entrega número; é HTTP simples, sem browser |
| Disparo em massa | **Fora de escopo** | Dado raspado; abordagem é a dedo e em volume baixo (LGPD, e queima o número) |

## 4. Modelo de dados

Duas tabelas novas no Supabase. Escritas só pelo backend/scraper com service key;
o frontend nunca consulta direto (mesmo padrão do resto do sistema).

```sql
create table prospeccao_campanhas (
  id                  uuid primary key default gen_random_uuid(),
  empresa_id          uuid not null references empresas(id) on delete cascade,
  termo               text not null,
  min_dias            int  not null default 60,
  paginas             int  not null default 6,
  ativa               boolean not null default true,
  ultima_rodada       timestamptz,
  ultimo_erro         text,
  rodar_solicitado_em timestamptz,          -- fila do botão "Rodar agora"
  criada_em           timestamptz not null default now(),
  unique (empresa_id, termo)
);

create table prospeccao_prospects (
  id              uuid primary key default gen_random_uuid(),
  empresa_id      uuid not null references empresas(id) on delete cascade,
  campanha_id     uuid not null references prospeccao_campanhas(id) on delete cascade,
  chave           text not null,            -- page_url, ou nome normalizado se não houver
  anunciante      text not null,
  instagram       text,
  page_url        text,
  whatsapp        text,                     -- só quando a LP expõe
  lp_url          text,
  ad_id           text,
  inicio          date,
  dias_no_ar      int,
  anuncios_ativos int  not null default 1,
  status          text not null default 'novo',   -- novo|contatado|respondeu|descartado
  contatado_em    timestamptz,
  lead_id         uuid references leads(id) on delete set null,
  visto_em        timestamptz not null default now(),
  criado_em       timestamptz not null default now(),
  unique (empresa_id, campanha_id, chave)
);

create index on prospeccao_prospects (empresa_id, campanha_id, status);
create index on prospeccao_prospects (empresa_id, dias_no_ar desc);
```

### A regra que faz a retroalimentação funcionar

O upsert diário casa por `(empresa_id, campanha_id, chave)` e atualiza **apenas**:

```
dias_no_ar, anuncios_ativos, visto_em, e os campos de contato quando vierem
preenchidos e a coluna estiver vazia
```

**Nunca** toca em `status`, `contatado_em` nem `lead_id`. Sem essa regra, a rodada
de amanhã zera todo "contatado" marcado hoje.

O `UPDATE` é escrito com colunas explícitas e `WHERE id =`, nunca em massa — é
exatamente o formato do incidente de 31/07, em que um `UPDATE` sem `WHERE`
sobrescreveu follow-ups de todas as empresas.

Prospect que sumiu da Biblioteca **não é apagado**: fica com `visto_em` velho. A
tela mostra "sumiu há N dias" — deixar de anunciar também é sinal.

## 5. Componentes

### 5.1 `app/services/adlib.py` — o parser (backend)

Porte das funções puras hoje em `tools/adlib_prospect.py`: `_limpa`, `_destino`,
`_instagram`, `_anunciante`, `_parse_data`, `_extrair`, mais o `JS_COLETA`.

Duas armadilhas que o parser resolve e que **não podem regredir**:

1. A primeira linha do card é um zero-width space (`​`). Não é string vazia, e
   `_norm()` a reduz a `""` — passava por todo filtro e virava o "nome do
   anunciante". O nome sai da âncora `"Patrocinado"`: é sempre a linha logo acima.
2. O link do Instagram vem embrulhado em `l.facebook.com/l.php?u=<url-encoded>`. Um
   `.split("?")[0]` descarta justamente o destino. Precisa desembrulhar o `u=`, e
   tratar o deeplink `instagram.com/_u/<handle>`, senão todo handle vira `_u`.

`leadflow-backend` é submódulo e não enxerga `tools/`, então o parser existe nos
dois repositórios. É duplicação consciente: prefiro admitir e testar dos dois lados
a criar um pacote compartilhado só por isso.

### 5.2 `app/services/adlib_runner.py` — o executor

Módulo executável (`python -m app.services.adlib_runner <campanha_id>`). Roda como
**subprocesso**, nunca dentro do event loop — Playwright síncrono no loop do
APScheduler travaria o processo inteiro.

Sequência por campanha:

1. Abre a Biblioteca com o termo, dá `paginas` scrolls, coleta os cards.
2. Extrai os prospects e descarta quem tem `dias_no_ar < min_dias`.
3. **Segundo hop**: `httpx` GET nas LPs únicas, timeout 15s cada, **teto de 90s no
   total**. Regex em `wa.me/<num>`, `api.whatsapp.com/send?phone=`,
   `respondi.app/<slug>`. Estourou o teto: grava o que achou e segue.
4. Upsert conforme a regra da seção 4.
5. Grava `ultima_rodada`; em falha, grava `ultimo_erro` e sai com código ≠ 0.

### 5.3 `leadflow-scraper` — o 4º serviço

Mesmo repositório `leadflow-backend`, `Dockerfile.scraper` (slim + Chromium),
entrypoint `app/scraper_main.py` com APScheduler carregando **só** o job de
prospecção. Mesmo padrão já usado entre web e scheduler: processos separados
saindo da mesma imagem.

| serviço | imagem | roda |
|---|---|---|
| leadflow-backend | slim | uvicorn — inalterado |
| leadflow-scheduler | slim | APScheduler — inalterado |
| leadflow-frontend | node | Vite — inalterado |
| **leadflow-scraper** | **+Chromium** | **cron 04:00 + fila 2min** |

Dois jobs:

- `prospeccao_diaria` — cron 04:00 BR, campanhas ativas **em série**, nunca paralelo.
- `prospeccao_fila` — a cada 2 min, pega campanhas com `rodar_solicitado_em` não
  nulo, roda e limpa a flag.

Contenção, dado que é um browser em produção:

- Subprocesso com `asyncio.wait_for(..., timeout=300)` e `kill()` no estouro.
- `max_instances=1` nos dois jobs.
- `PROSPECCAO_ENABLED` (default `false`) — desliga sem redeploy se der ruim às 4h.

### 5.4 `app/routers/prospeccao.py`

Todos os endpoints com `get_current_empresa_id`, como o resto do sistema.

```
GET    /prospeccao/campanhas
POST   /prospeccao/campanhas              {termo, min_dias, paginas}
PATCH  /prospeccao/campanhas/{id}         pausar / reativar / editar
DELETE /prospeccao/campanhas/{id}
POST   /prospeccao/campanhas/{id}/rodar   → grava rodar_solicitado_em
GET    /prospeccao/prospects?campanha_id=&status=
PATCH  /prospeccao/prospects/{id}         {status}
POST   /prospeccao/prospects/{id}/virar-lead
```

`POST /rodar` **enfileira, não executa** — o backend não tem Chromium. Escolhi fila
em vez de o backend chamar o scraper por HTTP interno porque: não há segredo
compartilhado pra vazar, nenhum request fica pendurado esperando um scrape de 90s,
e o pedido sobrevive a restart do scraper. Custo: até 2 min de latência no botão.

`virar-lead` cria em `leads` com `origem='adlib'`, grava o `lead_id` de volta no
prospect e marca `status='contatado'`. É a única ponte entre as duas bases, e é
sempre manual.

### 5.5 Frontend — `src/modules/campaigns/`

TanStack Query v5, mesmo padrão do `LeadsPage`.

```
Campanhas                                    [+ Nova campanha]
├─ mentoria para mulheres    13 prospects   4 novos   ha 6h  [▸]
├─ harmonizacao facial        7 prospects   0 novos   ha 6h  [▸]

  386d  Alta Performance    @jessicameurerferreira  📞 5542988167565
        [Contatado] [Descartar] [Virar lead →]
  340d  George Soares       @georgesoares_
        [Contatado] [Descartar] [Virar lead →]
```

- `CampaignsPage.tsx` — lista de campanhas, modal de criação, "Rodar agora"
- `ProspectsTable.tsx` — lista, filtros e botões de ação
- Filtros: status, tem Instagram, tem telefone, mínimo de dias
- Após "Rodar agora", a linha mostra **"na fila…"** até `ultima_rodada` mudar
- Horários sempre em São Paulo (UTC-3), nunca UTC cru

## 6. Falhas e degradação

| Falha | Comportamento |
|---|---|
| Meta pede login | Rodada devolve 0, grava `ultimo_erro`, tela mostra o aviso. Não derruba as outras campanhas |
| Chromium trava | `wait_for` 300s mata o subprocesso; job segue pra próxima campanha |
| LP fora do ar / lenta | Aquela LP é pulada; teto de 90s protege a rodada |
| Meta troca o HTML | Teste golden quebra no CI antes de a tela mentir |
| Um termo estoura | `try/except` por campanha — um termo quebrado não derruba a rodada |

## 7. Testes

- **Golden de extração** (`test_adlib_extracao.py`): fixture com os 34 cards reais
  já capturados de "mentoria para mulheres". Trava **0 sem nome, 0 com `l.php`,
  17 com Instagram**. É a rede que pega troca de HTML da Meta.
- **Upsert não pisa no status**: insere prospect, marca `contatado`, roda o upsert
  de novo com `dias_no_ar` maior, afirma que `status` continua `contatado` e que
  `dias_no_ar` atualizou.
- **Segundo hop respeita o teto**: LPs simuladas lentas, afirma que retorna dentro
  da janela e grava o que achou até ali.
- **Isolamento por empresa**: prospect de uma empresa nunca aparece pra outra.

## 8. Deploy

- **leadflow-scraper** — serviço NOVO, `Dockerfile.scraper`. Env: `PROSPECCAO_ENABLED=true`
- **leadflow-backend** — router novo
- **leadflow-frontend** — tela nova
- **leadflow-scheduler** — nada
- Migration das duas tabelas antes de tudo

## 9. Fora de escopo (consciente)

- **Disparo em massa a partir dos prospects.** Dado raspado; a abordagem certa é a
  dedo, no canal público, em volume baixo.
- **Agente IA tocando prospect sozinho.** Mesma razão.
- **Descoberta automática de termos.** Os termos são escolhidos por você.

Os três cabem depois sem refazer nada — o primeiro exige uma decisão de LGPD que
não é técnica.
