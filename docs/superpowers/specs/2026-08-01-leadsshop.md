# LeadsShop — Spec Inicial

**Data:** 01/08/2026
**Ecossistema:** LeadCase (hub) → LeadFlow (SDR/agente) · **LeadsShop (novo)**
**Status:** requisitos em coleta — nada implementado

## Objetivo

Ferramenta que transforma **um link de produto de marketplace** em **criativo pronto pra postar** (vídeo vertical 15s + copy + hashtags), no formato que comprovadamente viraliza em conta de afiliado/dropship.

Meta de operação declarada pelo usuário: **4 vídeos/dia** (~120/mês), sem estoque e sem fotografar produto.

## De onde veio

Sessão de 01/08/2026 fez o processo inteiro **na mão**, 2 produtos ponta a ponta. Tudo abaixo foi medido, não estimado. Esta spec é a automação daquele fluxo.

Referência de formato: perfil `@looksdalicia` (TikTok) — 3 vídeos com 383K/232K/204K views contra mediana de ~2K no resto.

---

## Validado nesta sessão

### A fórmula do criativo

| Elemento | Regra |
|---|---|
| Enquadramento | Flat lay top-down, 9:16, sem rosto, sem modelo, sem locação |
| Superfície | Colcha branca texturizada (matelassê), luz natural difusa |
| Composição | 3 cores da mesma peça em leque diagonal (clara / escura / terrosa). Peça única quando o produto só tem 1 cor |
| Movimento | Mãos entrando por baixo **esticando** o tecido pra mostrar elasticidade, depois soltando |
| Texto | `Sem ACREDITAR que {esse/essa} {peça} {lindo/linda} tá quase de graça` — "ACREDITAR" sempre caixa alta, 2 linhas no topo, branco com contorno preto |
| Legenda | **Só hashtag**, 3 delas: `#modafeminina` + 2 específicas da peça. Zero texto corrido |
| Duração | 15s, em loop perfeito (faixa validada pro formato: 7–18s) |

**Anti-padrão obrigatório:** nunca postar em lote. Os 10 vídeos fracos do perfil de referência têm IDs sequenciais — subiram juntos e canibalizaram o alcance uns dos outros. Um por vez, espaçado.

### O pipeline técnico

```
link curto (vt.tiktok.com/XXX)
  └─> resolve redirect  ──> og_info: { product_id, title, image_url }
        └─> gera flat lay   (nano-banana-2, reference_image_urls = foto do anúncio)
              └─> anima      (veo3-1-lite, extra_params.image, aspect_ratio 9:16, 4s)
                    └─> ffmpeg: boomerang -> 15s + drawtext + 1080x1920@30
                          └─> MP4 pronto
```

### Custos medidos (Kairogen)

| Etapa | Modelo | Créditos |
|---|---|---|
| Imagem flat lay | `nano-banana-2` | **3** |
| Imagem (alta) | `nano-banana-pro` | 6 |
| Imagem (mínima) | `z-image-turbo` | 1 |
| Vídeo 4s | `veo3-1-lite` | **8** |
| Vídeo 6s / 8s | `veo3-1-lite` | 12 / 16 |
| Pós-produção | ffmpeg local | **0** |

**Receita econômica validada: 11 créditos/vídeo** (nano-banana-2 + veo 4s). Qualidade não caiu em relação à receita de 22 créditos — comparado lado a lado no produto "body de renda".

Planos: ESSENTIAL R$49/280cr · PRO R$149/930cr · **PRECISION R$249/1.720cr** (melhor taxa, R$0,145/cr) · CREATOR R$1.199/8.000cr. 120 vídeos/mês × 11 cr = 1.320 cr → **PRECISION cobre com ~30% de folga pra retrabalho**.

---

## Requisitos funcionais

### RF0 — Autenticação (TikTok Shop Open API)

O "login" do sistema é **OAuth por empresa**. A empresa autoriza a LeadsShop uma vez; o sistema guarda token, **nunca senha**.

**Fluxo:** `POST` no token endpoint com `App Key` + `App Secret` + `authorization_code` → retorna `access_token`, `refresh_token` e **`shop_cipher`**.

O `shop_cipher` é **por loja** — é ele que dá o isolamento multi-tenant. Guardar junto do `empresa_id`, como já é feito com as credenciais de Evolution/Meta no LeadFlow.

**Registro no [Partner Center](https://partner.tiktokshop.com/):** dois tipos de app.

| Tipo | Quando | Aprovação |
|---|---|---|
| **Custom app** | Loja própria ou distribuição direta a sellers específicos | Rápida — marcar **"Seller in-house developer"** e validar pelo e-mail admin do Shop |
| **Public app** | Publicar na TikTok Shop App Store pra qualquer empresa do LeadCase usar | Review completo da TikTok |

**Caminho recomendado:** começar **Custom app** (destrava o desenvolvimento em dias, não semanas), migrar pra Public quando a LeadsShop for vendida a terceiros.

⚠️ **A região de negócio é escolhida no registro e NÃO pode ser alterada depois.** Selecionar **BR**.

Outros pontos: existem **Development Shops** pra testar sem loja real; desde 2026 o gateway aceita **só HTTPS**; e a API separa **Affiliate Seller** (seller buscando criador) de **Affiliate Creator** (criador gerenciando vitrine) — a LeadsShop usa a segunda.

### RF1 — Ingestão do produto
- Aceitar link curto (`vt.tiktok.com`) e link direto de PDP
- Resolver redirect e extrair `product_id`, título e imagem de capa do parâmetro `og_info`
- **Buscar TODAS as fotos do anúncio** — hoje é o gargalo (ver Riscos)
- Persistir catálogo: produto, fotos, cores disponíveis, preço

### RF2 — Geração do criativo
- Montar prompt de flat lay a partir do título + foto de referência do anúncio
- Detectar nº de cores do produto e escolher composição (leque de 3 vs peça única)
- Gerar N variações e deixar o usuário escolher
- Animar a variação escolhida

### RF3 — Pós-produção (ffmpeg, sem custo)
- Boomerang: ida + volta espelhada, comprimido pra duração alvo → **loop perfeito** (último frame = primeiro)
- Overlay de texto: Segoe UI Black, `borderw=6`, contorno preto, topo centralizado
- Saída 1080×1920 @30fps, `yuv420p`, `+faststart`
- **Montagem multi-ângulo:** cortes entre fotos reais do anúncio com zoom lento, intercalados com o clipe animado. Custo zero e aumenta fidelidade

### RF4 — Copy
- Gerar texto de tela pelo template, flexionando gênero/artigo conforme a peça
- Gerar as 3 hashtags: `#modafeminina` + 2 derivadas do título
- **Nunca afirmar atributo não verificável** (material, durabilidade, "não desbota") — só preço e aparência

### RF5 — Música
- Conta comercial/Shop **só pode** usar a Commercial Music Library — som normal pode ser mutado ou virar strike
- Sugerir faixa por perfil da peça (90–110 BPM, sem vocal forte competindo com o texto)
- Áudio externo/gerado por IA **mata o alcance** — o TikTok distribui por página de som. Não gerar música

### RF6 — Publicação
- Agendar 1 post por vez, espaçado (nunca lote)
- Vincular produto do Shop ao vídeo
- Registrar o que foi postado pra não repetir criativo

### RF7 — Métricas
- Views/likes/comentários por criativo, e conversão por produto
- Fechar o loop: qual gancho de texto performa melhor

---

## Decisões técnicas travadas

1. **Kairogen `generate_video` exige `extra_params: { "image": url }`** — não `first_frame_url`. A função `animate_from_generation` manda pela chave errada e a imagem **não chega no modelo**, que vira text-to-video e regenera o produto errado. Custou 32 créditos descobrir.
2. **Sempre passar `aspect_ratio` explícito.** Omitir não preserva o formato da origem — cai no default 16:9.
3. **Sempre conferir `param_schema` do modelo antes de chamar.** As chaves genéricas nem sempre batem.
4. `nano-banana-pro`/`nano-banana-2` **não aceitam `negative_prompt`** (erro 400) — dobrar as negativas dentro do prompt.
5. **HTTP 403 não gasta crédito** — dá pra sondar quais modelos o plano libera de graça.
6. `veo3-1-lite` aceita **apenas 4, 6 ou 8s**. É o único modelo de vídeo no ESSENTIAL.
7. Texto com acento no ffmpeg: usar `textfile=` apontando pra arquivo UTF-8. Inline quebra no Windows (cp1252).

---

## Riscos e travas obrigatórias

### R1 — PDP exige login → resolvido pela Open API (ver RF0)
`shop.tiktok.com/br/pdp/{id}` responde **"Entrar | TikTok"** mesmo com User-Agent de browser. Só a foto de capa vem no `og_info` do link de compartilhamento.

**Trava:** nunca usar credencial pessoal do usuário nem automação de browser logada — é a conta que gera a receita dele, e login automatizado é detectado e punido. O "login" do sistema é **OAuth por empresa**, guardando token — nunca senha. Até a app sair, upload manual das fotos.

### R2 — Dropship + imagem gerada por IA
Anunciar com imagem que a IA criou de um produto nunca manuseado gera devolução, avaliação ruim e strike por conteúdo enganoso.

**Travas:**
- Gerar **sempre a partir da foto do anúncio do fornecedor**, nunca do zero
- Priorizar montagem com fotos reais; IA só no plano de gancho
- Copy nunca afirma o que não é verificável

### R3 — Volume vira repetição
120 vídeos/mês exige ~120 produtos ou variação real de gancho. Mesmo formato + mesmo produto = conteúdo duplicado, que o TikTok penaliza.

**Trava:** biblioteca de ganchos alternativos, e limite de criativos por produto.

---

## Decisões de produto (01/08/2026)

### D1 — Conta central de IA com rateio

Uma única conta Kairogen da LeadsShop. Cada empresa consome de uma **cota mensal** definida pelo plano que assina.

**Modelo de cobrança:** mensalidade × N vídeos/mês. Custo base medido: **11 créditos/vídeo = R$1,60** no PRECISION (R$0,145/crédito).

**Implica:**
- Ledger de créditos por `empresa_id` — débito no momento da geração, não no fim
- Bloqueio ao estourar a cota (com upsell, não erro seco)
- **FILA OBRIGATÓRIA.** O limite de gerações simultâneas é da **conta**, não da empresa: PRECISION = 4 vídeos em paralelo. Com 10 empresas gerando ao mesmo tempo, sem fila com escalonamento justo, uma empresa trava as outras. Isso não existe no modelo de conta-por-empresa — é o custo de escolher central.
- Reconciliação: créditos consumidos vs faturado, por empresa

### D2 — Sistema publica sozinho

⚠️ **Depende de auditoria da TikTok. Sem ela, o recurso é inútil.** Regras da [Content Posting API](https://developers.tiktok.com/doc/content-posting-api-get-started) pra client **não auditado**:

- Todo conteúdo postado fica em **`SELF_ONLY`** (privado) — alcance zero
- A conta do usuário precisa estar **privada no momento do post**
- Máximo de **5 usuários postando por janela de 24h** — mata multi-tenant

**Consequência:** a publicação automática é feature **pós-auditoria**. Planejar em duas fases:
1. **v1:** gera o MP4 + copy + hashtags, notifica a empresa, ela posta. Funciona no dia 1.
2. **v2:** publicação direta, depois de passar a auditoria do client.

Não prometer publicação automática em contrato antes da auditoria sair.

### D3 — Multi-plataforma: fontes ≠ destinos

Distinção que a arquitetura precisa refletir:

- **Fonte (catálogo):** de onde vem o produto — TikTok Shop, Shopee, Shein, Amazon
- **Destino (publicação):** onde o vídeo é postado — TikTok (e, depois, Reels/Shorts)

Shopee/Shein/Amazon são **só fonte**. Um modelo interno único de `Produto` + **um adapter por fonte**.

| Fonte | Situação | Custo/atrito |
|---|---|---|
| **TikTok Shop** | ✅ Open API oficial (ver RF0) | Registro no Partner Center |
| **Shopee** | ✅ API oficial de afiliado: `open-api.affiliate.shopee.com.br/graphql` — REST/GraphQL assinado, sem browser. Campos: `itemId`, `name`, `offerLink`, `commissionRate`, `sales`, `rating`, imagens | Conta no [affiliate.shopee.com.br](https://affiliate.shopee.com.br) → **review manual de 5-15 dias** |
| **Amazon** | ⚠️ **A verificar** — PA-API exige conta Associates ativa e, salvo engano, vendas qualificadas antes de liberar a API. **Confirmar antes de prometer** | — |
| **Shein** | 🔴 **Não tem API pública de afiliado.** O `open.sheincorp.com` é pra seller/supply chain, não pra catálogo de afiliado. As opções são scrapers de terceiros pagos (SearchAPI, Oxylabs, ScrapingBee) ou cadastro manual | Custo recorrente de terceiro **ou** entrada manual |

**Recomendação de ordem:** TikTok Shop → Shopee (as duas com API oficial) → Amazon (verificar) → Shein por último (é a mais cara e frágil).

### D4 — Provider de IA abstraído

Interface interna única (`gerar_imagem`, `gerar_video`) com **um adapter por provider**. Implementar **só o Kairogen** agora.

**Por quê:** com conta central e rateio, a margem é literalmente `preço cobrado − custo do crédito`. Se o Kairogen reajustar, cair, ou surgir modelo melhor/mais barato, sem abstração você reescreve o núcleo do produto. Com abstração, troca um arquivo. Custo: ~1 dia a mais agora.

Alternativa já avaliada: Higgsfield (MCP oficial em `mcp.higgsfield.ai/mcp`, Kling ~6 cr/vídeo). Mais barato em alguns modelos, mas cobra em USD com IOF/spread.

### D5 — App público + auditoria (decidido 01/08/2026)

Rota: **Custom app + Development Shop** pra desenvolver → **Public app + auditoria da Content Posting API** pra lançar.

**Timeline realista da auditoria: 6-7 semanas.** Verificação de domínio e OAuth (~1 sem) → construção da superfície e review do app base (~1 sem) → revisões e reenvio (~1 sem) → submissão da auditoria de posting (~1 sem) → resposta e pedidos de revisão de UX (~3 sem). Entrar na fila cedo.

#### 🔴 A auditoria PROÍBE publicação 100% autônoma

Este é o achado mais importante da spec. As exigências de UX da [Content Posting API](https://developers.tiktok.com/doc/content-sharing-guidelines) são incompatíveis com "o sistema posta sozinho 4x/dia sem ninguém tocar":

- **Privacidade não pode ter valor padrão** — o usuário tem que escolher manualmente, a cada post, num dropdown
- **Comentário/Duet/Stitch começam todos desmarcados** — o usuário marca manualmente
- **Consentimento expresso do usuário antes de cada upload**
- **Preview do conteúdo obrigatório antes de postar**
- **Título e hashtags têm que ser editáveis**, nada travado

A API foi desenhada pro fluxo "o usuário aperta postar dentro do seu app", não pra agendador autônomo. Tentar burlar = rejeição na auditoria ou ban do client depois.

**O que continua viável — publicação assistida:** a LeadsShop gera vídeo, copy e hashtags, e enfileira. A pessoa abre o app e passa por uma tela de post conforme (escolhe privacidade + consente) em ~15 segundos por vídeo. Continua economizando ~95% do trabalho — só não é zero-touch.

**Reflexo comercial:** vender como *"seus criativos prontos, você aprova e publica em segundos"*, nunca como *"posta sozinho"*.

#### Checklist de conformidade (construir no v1, senão refaz tela)

| # | Exigência |
|---|---|
| 1 | Buscar `/v2/post/publish/creator_info/query/` **antes** de renderizar a tela de post |
| 2 | Exibir **nickname e avatar** do criador — a TikTok verifica isso |
| 3 | Renderizar o dropdown de privacidade a partir de `privacy_level_options` da resposta. **Não hardcodar os 4 níveis** — conta privada não tem `PUBLIC_TO_EVERYONE`, e hardcodar reprova |
| 4 | Sem valor padrão de privacidade; publicar bloqueado até escolher |
| 5 | Comentário/Duet/Stitch desmarcados por padrão; **cinza e desabilitados** se o criador desativou nas configurações |
| 6 | Toggle de conteúdo comercial **desligado por padrão**, com duas opções: *Sua marca* → rótulo "Conteúdo promocional"; *Conteúdo de marca* → rótulo "Parceria paga" |
| 7 | Conteúdo de marca **não pode ser privado** — desabilitar a opção ou trocar pra público avisando |
| 8 | Se o toggle comercial está ligado e nenhuma opção marcada → botão de publicar desabilitado |
| 9 | Declaração antes do botão: *"Ao publicar, você concorda com a Confirmação de Uso de Música do TikTok"* (+ Política de Conteúdo de Marca quando aplicável) |
| 10 | Preview do conteúdo antes de publicar |
| 11 | **Proibido** sobrepor marca, logo, watermark ou link promocional da LeadsShop no vídeo |
| 12 | Título/hashtags gerados têm que ser **editáveis** |
| 13 | Validar duração contra `max_video_post_duration_sec` retornado pela API |
| 14 | Avisar que o processamento leva alguns minutos; acompanhar via polling ou webhook |

## Perguntas em aberto

1. **Onde roda o ffmpeg?** O backend Python já existe — vira worker? Jobs de vídeo levam minutos, então precisa de fila de qualquer forma (ver D1).
2. **Preço de venda e tamanho das cotas** — quantos vídeos/mês em cada plano da LeadsShop?
3. **Amazon PA-API** libera sem histórico de vendas? (ver D3)

---

## Fora de escopo (v1)

- Rotação 360° do produto por IA — a IA reinventa o que não está visível e troca o produto. Usar corte entre fotos reais.
- Geração de música.
- Edição manual de vídeo na interface.
- Locução / avatar falando.
