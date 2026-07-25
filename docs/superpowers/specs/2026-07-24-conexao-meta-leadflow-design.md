# Conexão Meta no Leadflow — Design

**Data:** 2026-07-24
**Origem:** port do AvalancheVendas (quicks `260723-izi` + `260723-p2b`, shippados 23/07)
**Status:** design aprovado, aguardando plano de implementação

---

## 1. Objetivo

Trazer pro Leadflow as duas conexões Meta que já existem (ou estão quase) no AvalancheVendas:

1. **WhatsApp Cloud API via Embedded Signup** — botão de 1 clique que conecta o número oficial da empresa. Destrava operar sem a Evolution (não-oficial), eliminando a classe inteira de incidentes de ban, socket zumbi e troca de proxy.
2. **Meta Ads via OAuth** — substitui o access token colado à mão em Configurações → Meta Ads por um botão de conexão.

As duas são o **mesmo mecanismo** (Facebook Login for Business com `response_type: 'code'`), variando só o `config_id` e os escopos. Um App Meta, dois `config_id`, dois botões.

## 2. Decisões tomadas

| # | Decisão | Alternativa descartada |
|---|---|---|
| D1 | **Canal por empresa**: empresa opera Evolution **ou** Cloud API, nunca as duas | "Mesmo número nos 2 canais" (desenho do Avalanche) — complexidade alta pra ganho baixo no Leadflow |
| D2 | **Dispatch multi-tenant por `phone_number_id`** — Callback URL única | Roteamento por slug na URL (Avalanche) — trava em 1 empresa recebendo inbound |
| D3 | **Adapter Meta→Evolution**: traduz o payload e reusa `receber_mensagem_evolution` | Pipeline inbound próprio — duplicaria ~10k linhas de lógica de agente |
| D4 | **Fernet no Python** pro access token (revisado — ver abaixo) | pgcrypto + GUC; plaintext em `config_apis` |
| D5 | **Template Q1 criado automaticamente** a partir do `config_ia.q1_template` | Dono cadastra à mão no WhatsApp Manager e informa o nome |
| D6 | **WhatsApp primeiro, Ads depois** | Fazer os dois juntos — dobraria o risco da fase 1 sem entregar nada novo |

### Por que D1 (canal por empresa)

O Leadflow é **outbound-first**: o lead preenche formulário, o webhook chega e a Bia **dispara** a Q1 na hora. A Cloud API não deixa iniciar conversa com texto livre — fora da janela de 24h só sai template aprovado. Além disso a Cloud API **não tem grupo**, e o fluxo de grupo do Leadflow (probe @lid, FSM, convite, aquecimento) é grande e só existe na Evolution.

Misturar os dois canais numa mesma empresa significaria manter as duas árvores de decisão vivas em paralelo. Canal por empresa mantém cada empresa num caminho só: as que rodam hoje ficam intactas na Evolution, e a Cloud API é o caminho das novas.

**Consequência aceita:** empresa em Cloud API não usa grupo. O fluxo de grupo fica desligado pra ela.

### Por que D3 (adapter)

O `POST /agente/evolution/webhook` ([`app/routers/agente.py:3594`](../../../leadflow-backend/app/routers/agente.py)) carrega o cérebro inteiro: lock atômico por `(empresa_id, telefone)`, dedup, FSM de agendamento, qualificação Q1/Q2/Q3, slots, safety-net, markers de diagnóstico. Reimplementar isso pro Cloud API criaria um segundo cérebro divergente — e a história do projeto mostra que bugs de agente aparecem justamente nas divergências entre caminhos (ver os fixes de "canal unificado nos 3 senders").

O adapter converte o payload da Meta no formato que o handler já espera e chama o mesmo handler. **O `agente.py` não é tocado.**

### Por que D4 (cifrar o token) — e por que Fernet e não pgcrypto

O access token do Embedded Signup é **permanente** e dá poder de enviar mensagem em nome do número da empresa. Hoje o Leadflow guarda credenciais em `empresas.config_apis` em texto puro. Pra esse token específico isso é risco desproporcional — um dump da tabela vira capacidade de mandar WhatsApp como qualquer cliente.

**Revisão durante a implementação:** o plano original era portar `encrypt_api_key`/`decrypt_api_key` do AvalancheVendas (pgcrypto + `SECURITY DEFINER`). Ao implementar, dois fatos mudaram a escolha:

1. Aquelas funções dependem de um GUC `app.encryption_key` configurado no Postgres (Supabase Studio → Custom Postgres Config). Se ele não estiver setado, `pgp_sym_encrypt(texto, NULL)` **falha em runtime** — ou seja, um passo manual esquecido quebra a conexão em produção com erro obscuro.
2. `cryptography==43.0.0` já é dependência do Leadflow, e **todo** segredo do projeto vive em env.

Então a cifra acontece no Python (Fernet, chave em `META_TOKEN_ENC_KEY`) — [`app/services/cloud_api_crypto.py`](../../../leadflow-backend/app/services/cloud_api_crypto.py). Mesma ameaça mitigada, um passo operacional a menos, e coerente com onde o resto dos segredos já mora.

**Perda da chave:** os tokens ficam ilegíveis e cada empresa reconecta em 1 clique. Nenhum dado de lead se perde. Não há rotação com re-cifragem nesta versão — trocar a chave equivale a pedir reconexão.

## 3. Arquitetura

### 3.1 Outbound — switch no `evolution_router`

O Leadflow já tem um gargalo único de envio:

```
evo_router.send_text(empresa_id, numero, texto)     app/services/evolution_router.py:480
```

**Os 33 call sites já passam `empresa_id`** — exatamente o que decide o canal. O switch mora no topo de `send_text` / `send_media` / `send_audio_voice`:

```
send_text(empresa_id, numero, texto)
   ├─ canal(empresa) == 'cloud_api'  → cloud_api_sender.send_text()
   └─ senão                          → fluxo Evolution atual (intacto)
```

Nenhum call site muda. Throttle, dedup anti-loop, retry e limite por lead continuam valendo — a Cloud API não precisa de anti-ban, mas o dedup e o limite por lead sim (são proteções contra bug de loop, não contra a Meta).

**Descoberta na implementação — o gargalo não era único.** O webhook de formulário chama o primitivo `evolution.enviar_mensagem` **direto**, sem passar pelo `evolution_router`. Ou seja, o envio mais importante do Leadflow (a Q1, que é justamente a abertura de conversa) ficava fora do switch.

Isso ganhou um caminho próprio em [`app/services/canal_abertura.py`](../../../leadflow-backend/app/services/canal_abertura.py), e não foi absorvido pelo `evolution_router` de propósito: passar a Q1 do formulário pelo router adicionaria throttle e dedup a um envio que hoje não os tem, mudando o comportamento da Evolution de tabela. O caminho Evolution segue byte a byte igual; só a Cloud API desvia.

### 3.2 Inbound — Callback URL única + dispatch por `phone_number_id`

```
POST /webhook/cloud-api                      ← uma URL pro App inteiro
   ↓ raw body ANTES de qualquer parse
   ↓ HMAC-SHA256 vs X-Hub-Signature-256      (App Secret GLOBAL)
   ↓ parse JSON
   ↓ extrai entry[0].changes[0].value.metadata.phone_number_id
   ↓ lookup cloud_api_config por phone_number_id → empresa_id
   ↓ replay window 5min
   ↓ traduz payload Meta → formato Evolution
   ↓ receber_mensagem_evolution()             ← MESMO cérebro
```

**Simplificação sobre o Avalanche:** com App Meta compartilhado entre as empresas, o `verify_token` e o `app_secret` pertencem ao **App**, não à empresa. Isso elimina:

- o `verify_token` gerado e exibido uma única vez na tela
- o passo manual "cole a Callback URL e o Verify Token no painel da Meta" por empresa
- as colunas `verify_token_encrypted`, `app_secret_encrypted` e `webhook_url_complete` da tabela

A empresa guarda só `phone_number_id`, `waba_id` e `access_token`.

**Ordem de validação é contratual:** ler o corpo cru **antes** de `request.json()`. Re-serializar muda o espaçamento e quebra a assinatura.

### 3.3 O adapter

O handler espera o formato da Evolution:

```json
{ "instance": "<slug>",
  "data": { "key": { "id": "...", "remoteJid": "5511...@s.whatsapp.net", "fromMe": false },
            "message": { "conversation": "texto" },
            "pushName": "Nome" } }
```

O adapter monta isso a partir do payload da Meta:

| Evolution | Meta |
|---|---|
| `instance` | `empresas.evolution_instancia` da empresa resolvida |
| `data.key.id` | `messages[0].id` (wamid) — serve de chave de dedup e de lock |
| `data.key.remoteJid` | `messages[0].from` + `@s.whatsapp.net` |
| `data.key.fromMe` | sempre `false` (a Meta não entrega echo de outbound aqui) |
| `data.message.conversation` | `messages[0].text.body` |
| `data.pushName` | `contacts[0].profile.name` |

Empresa em Cloud API recebe um `evolution_instancia` sintético (ex: `cloudapi-<slug>`) só pra o lookup por essa coluna funcionar sem alterar o handler. Nada tenta alcançar a Evolution, porque o outbound já foi desviado no `evolution_router`.

**Áudio:** a Meta entrega um `media id`, não uma URL. O adapter baixa a mídia (`GET /{media_id}` → `url` → `GET` com Bearer) antes de entregar, porque o Leadflow transcreve áudio com Whisper e um áudio ilegível já causou incidente de silêncio do bot.

**Status de entrega:** `value.statuses[]` (delivered / read / failed) não é mensagem — trata em ramo separado, sem passar pelo adapter.

### 3.4 Template Q1

O `config_ia.q1_template` já é um template com placeholders ([`agente.py:4588`](../../../leadflow-backend/app/routers/agente.py)):

```
"Oie {{lead.nome}}, tudo bem? 😊
Sou a {{nome_agente}} do time da {{nome_responsavel}} e estou entrando em contato
porque você preencheu nosso formulário. Correto?"
```

Conversão pra Meta: `{{lead.nome}}` → `{{1}}`, `{{nome_agente}}` → `{{2}}`, `{{nome_responsavel}}` → `{{3}}`, preservando a ordem de aparição. Submete via `POST /{waba_id}/message_templates` (categoria `UTILITY`, idioma `pt_BR`) e acompanha o status por dois caminhos: o webhook `message_template_status_update` e um polling de fallback.

No envio, empresa em Cloud API manda a Q1 como `type: "template"` com os `components`. **A resposta do lead abre a janela de 24h e todo o resto da conversa é texto livre normal** — Q2, empatia, slots, confirmação, follow-up, tudo pelo caminho de texto.

**Se o template não estiver aprovado:** o envio falha com mensagem explícita e o lead fica em `pendente` — o status que o webhook já usa pra permitir retry. O lead não é perdido; ele espera a aprovação da Meta.

#### Consequência que o dono precisa saber

Na Evolution a Q1 é **gerada pelo LLM** a cada lead (o webhook monta o `prompt_sistema` e pede a abordagem). Na Cloud API a abertura é o **template aprovado** — texto fixo com variáveis. Não é escolha nossa: a Meta revisa e aprova um texto específico, e enviar outro dá erro 132005.

Efeito prático: empresa em canal oficial perde a personalização por LLM **na primeira mensagem**, e só nela. Da resposta do lead em diante o LLM comanda tudo como sempre.

Por isso `abrir_conversa` devolve `texto_enviado`: o histórico em `conversas` grava o que o lead **realmente recebeu**. Gravar a saída do LLM enquanto o lead viu o template faria o agente ler um histórico que não existe no WhatsApp dele — exatamente a divergência que deixou o agente mudo no inbound Cloud API do AvalancheVendas.

#### Mensagem de fora-do-horário

O Leadflow manda um texto próprio quando o lead chega fora do horário de atendimento. Esse texto **não é** o template aprovado, então na Cloud API ele não tem como sair. O lead fica em `pendente` e é abordado quando o atendimento volta — deliberadamente **não** marcado como `enviado_offline`, porque marcar envio que não aconteceu é a "conversa fantasma" do caso Liliane. Resolver isso de verdade pede um segundo template (fora do escopo desta rodada).

### 3.5 Meta Ads OAuth

Segue o padrão que o Leadflow já usa em [`app/routers/oauth_zoom.py`](../../../leadflow-backend/app/routers/oauth_zoom.py): `GET /start` devolve a URL de autorização (com `state` persistido em `oauth_states`), `GET /callback` troca o code por token. Depois do callback, lista as ad accounts do usuário pra ele escolher qual vincular.

Substitui os campos `meta_access_token` e `meta_ad_account_id` de Configurações → Meta Ads. O [`app/services/meta.py`](../../../leadflow-backend/app/services/meta.py) passa a ler o token salvo em vez do valor colado. **Grandfather:** empresa que já tem token manual continua funcionando — o resolvedor tenta o token OAuth e cai no manual se não houver.

## 4. Schema

**Migration 011** — [`migrations/011_cloud_api_meta.sql`](../../../leadflow-backend/migrations/011_cloud_api_meta.sql). Duas tabelas, sem pgcrypto (ver D4):

`cloud_api_config` — uma por empresa. `phone_number_id` é **unique global**, não por empresa: um número pertence a uma empresa só, e o dispatch inbound depende disso pra não entregar mensagem no tenant errado. Guarda também o estado do template (`template_nome`, `template_status`, `template_variaveis`), porque a ordem das variáveis precisa sobreviver entre a submissão e o envio.

`meta_ads_tokens` — uma por empresa, com `ad_account_id` escolhido. Tabela própria em vez de reusar `calendario_tokens`: aquela tem semântica de OAuth de calendário (plataforma, refresh, expiração de 90 dias) e misturar Ads ali confundiria os dois ciclos de vida.

RLS habilitada nas duas, **sem policy** pra `anon`/`authenticated`: o frontend lê pelo backend com service role, e o token não sai nem cifrado.

## 5. Ameaças e mitigações

| Ameaça | Mitigação |
|---|---|
| Payload forjado se passando pela Meta | HMAC-SHA256 do corpo cru vs `X-Hub-Signature-256`, comparação em tempo constante |
| Replay de webhook antigo | Janela de 5min sobre `messages[0].timestamp` |
| Mensagem cair no tenant errado | `phone_number_id` unique global + lookup obrigatório; sem match → 404, não processa |
| Dump da tabela virar poder de enviar WhatsApp | `access_token_encrypted` via pgcrypto; nunca retornado pela API de leitura |
| Token/code/secret vazando em log | Log só de ids e flags booleanas — nunca o valor |
| Webhook duplicado gerando resposta dobrada | Dedup por wamid, que entra como `data.key.id` no dedup que já existe |
| Meta desativar webhook por timeout | ACK 200 imediato, processamento em background (padrão que o webhook de formulário já usa) |

## 6. Fases

| # | Entrega | Código | Verificação |
|---|---|---|---|
| 0 | App Meta (painel do dono) + migration 011 | `migrations/011_cloud_api_meta.sql` | ⏳ migration aplicada; envs presentes |
| 1 | Botão "Conectar WhatsApp" + troca do code + persistência | `routers/cloud_api.py`, `lib/facebook.ts`, `ConexaoWhatsAppOficial.tsx` | ⏳ conectar número de teste |
| 2 | Webhook inbound multi-tenant + adapter | `routers/webhook_cloud_api.py`, `services/cloud_api_adapter.py` | ⏳ msg do celular → Bia responde |
| 3 | Outbound + switch de canal | `services/cloud_api_sender.py`, `evolution_router.py` | ⏳ resposta sai com wamid |
| 4 | Template Q1 (criar, acompanhar, enviar) | `services/cloud_api_template.py`, `services/canal_abertura.py` | ⏳ formulário → Q1 como template |
| 5 | Meta Ads OAuth | `routers/meta_ads.py`, `ConexaoMetaAds.tsx` | ⏳ conectar e listar ad accounts |

Fase 5 é independente — reusa a canalização OAuth da fase 1.

**Estado:** código das fases 1-5 escrito e com 56 testes passando ([`tests/test_cloud_api_meta.py`](../../../leadflow-backend/tests/test_cloud_api_meta.py)). Nenhuma verificação ponta a ponta feita ainda — todas dependem da fase 0, que é o App Meta no painel. As colunas de verificação viram ✅ conforme cada uma for validada com número real.

## 7. Pré-requisitos do dono (fase 0)

Não repete (é por Business): **verificação do Meta Business** — se o App do Leadflow ficar no mesmo Business do AvalancheVendas, já está feito.

Repete (por App):

1. Create App tipo **Business** em `developers.facebook.com`
2. Adicionar produto **WhatsApp**
3. Criar configuração de **Cadastro incorporado** → gera `META_CONFIG_ID_WHATSAPP`
4. Callback URL `https://api.leadcase.com.br/webhook/cloud-api` + Verify Token
5. Subscrever `messages` e `message_template_status_update`
6. Configuração de Facebook Login for Business com `ads_read` + `business_management` → gera `META_CONFIG_ID_ADS`
7. Envs no backend (Easypanel → `leadflow-backend` **e** o serviço do scheduler):

| Env | De onde vem |
|---|---|
| `META_APP_ID` | App Dashboard → Configurações → Básico |
| `META_APP_SECRET` | idem, "Chave secreta do app" |
| `META_VERIFY_TOKEN` | string que você inventa e cola na Callback URL |
| `META_CONFIG_ID_WHATSAPP` | id da configuração de Cadastro incorporado |
| `META_CONFIG_ID_ADS` | id da configuração de Login for Business (Ads) |
| `META_TOKEN_ENC_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

`META_TOKEN_ENC_KEY` precisa ser **a mesma** nos dois serviços — o web cifra ao conectar e o scheduler decifra pra enviar follow-up. Chaves diferentes fazem o follow-up falhar com "precisa reconectar".

**App Review não bloqueia o desenvolvimento.** Em modo de desenvolvimento o App funciona com WABAs e ad accounts onde o dono é admin, o que cobre as fases 1-4 ponta a ponta. A revisão de `whatsapp_business_management` + `whatsapp_business_messaging` é requisito pra onboarding de empresas de terceiros — ou seja, pra vender.

O checklist da Meta muda com frequência; o quadro de requisitos do próprio App Dashboard é a fonte da verdade.

## 8. O que fica de fora

- **Grupo na Cloud API** — a plataforma não suporta. `criar_grupo` recusa explicitamente pra empresa em canal oficial, barrando a porta de entrada do fluxo.
- **Follow-up fora da janela de 24h** — se o lead não responder a Q1, o follow-up (24h/48h) cai fora da janela e a Meta recusa com 131047. Precisa de um segundo template aprovado. **É a pendência mais relevante que sobra**: hoje o follow-up simplesmente falha e o motivo aparece no log.
- **Mensagem de fora-do-horário** — mesmo motivo (texto próprio, sem template). Lead fica `pendente`.
- **Botões interativos** — a Meta tem, com contrato próprio e limite de 3×20 chars. Degrada pra texto; o lead sempre pode responder escrevendo.
- **Migração de empresa que já roda na Evolution** — o número precisa sair da sessão do WhatsApp Web antes da Meta liberar. Procedimento operacional, não código.
- **Disparo em massa** — é pago na Cloud API e não é caso de uso do Leadflow.
- **Rotação da chave de cifra** — trocar `META_TOKEN_ENC_KEY` exige reconexão de todas as empresas.

## 9. Referências no AvalancheVendas

| Peça | Arquivo |
|---|---|
| SDK + `launchEmbeddedSignup()` | `avalanche-frontend/src/lib/facebook.ts` |
| UI 3 estados | `avalanche-frontend/src/components/cloud-api/CloudApiProvisioningForm.tsx` |
| Troca de code + subscribe WABA | `app/services/cloud_api_provisioning.py:357` |
| Rotas config / embedded-signup / test | `app/routers/cloud_api.py` |
| Receiver (HMAC + challenge + replay) | `app/routers/webhook_cloud_api.py` |
| Processador inbound | `app/services/cloud_api_webhook_processor.py` |
| Sender outbound | `app/services/cloud_api_sender.py` |
| Códigos de erro da Meta traduzidos | `app/services/cloud_api_webhook_processor.py:141` |
| Schema + pgcrypto | `supabase/migrations/20260525000001_cloud_api_config.sql` |
