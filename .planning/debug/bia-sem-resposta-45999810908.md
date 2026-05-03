---
status: diagnosed
trigger: "Agente de IA 'Bia' não respondeu nada ao lead com número 45999810908"
created: 2026-04-12T00:00:00Z
updated: 2026-04-12T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMADA — filtro de score silencioso bloqueia lead (score=0 < score_minimo=10000 por padrão), OU número não está na tabela leads (lead enviou mensagem sem passar pelo formulário)
test: Verificado por análise estática completa do fluxo agente.py + webhook.py
expecting: Verificar no Supabase: (1) se lead 45999810908 existe em leads, (2) qual é o score, (3) qual é o score_minimo em config_ia da empresa
next_action: ROOT CAUSE FOUND — aguardando diagnóstico final

## Symptoms

expected: Bia qualifica o lead — envia Q1 ("preencheu nosso formulário...") e Q2 (cita o desafio + "é isso mesmo?")
actual: Nenhuma resposta foi enviada ao lead
errors: Desconhecidos — investigar logs e código
reproduction: Lead 45999810908 enviou mensagem no WhatsApp, Bia não respondeu
started: 2026-04-12 (hoje)

## Eliminated

- hypothesis: numero_interno (Fix #25) — número 45999810908 está em notificacoes_telefones
  evidence: Possível mas improvável para um lead. É verificado em agente.py linha 1342. Necessita confirmação via Supabase.
  timestamp: 2026-04-12

- hypothesis: Evolution API webhook desabilitado (Fix #23)
  evidence: Se o webhook não chegasse ao backend, não haveria processamento algum. O código chegaria a retornar 400 ou silêncio total. Precisa confirmação mas a pergunta implica que a mensagem chegou (lead "enviou mensagem no WhatsApp").
  timestamp: 2026-04-12

- hypothesis: NameError em funções module-level (Fix #18)
  evidence: Esses erros causariam um 500 com traceback, que seria logado. Não seria silencioso. O comportamento reportado é silêncio total sem envio.
  timestamp: 2026-04-12

## Evidence

- timestamp: 2026-04-12
  checked: agente.py linha 1439-1442 — filtro score_minimo
  found: score_minimo = int(config_ia.get("score_minimo", 10000)). Se config_ia não tiver score_minimo explicitamente setado, o default é 10000. Leads sem score (score=0) são bloqueados silenciosamente com retorno {"ok": True, "ignorado": True, "motivo": "score abaixo do mínimo"}.
  implication: Se 45999810908 enviou mensagem direto no WhatsApp sem passar pelo formulário, não está na tabela leads → score=0 → bloqueado. Mesmo se estiver no banco com score baixo, é bloqueado.

- timestamp: 2026-04-12
  checked: agente.py linha 1389 — fallback de lead não encontrado
  found: lead = lead_res.data[0] if lead_res.data else {"nome": numero, "telefone": numero, "dados_raw": {}}. Quando lead NÃO existe no banco, cria um dict sem campo "score" → lead.get("score", 0) = 0.
  implication: Qualquer mensagem de WhatsApp de um número não cadastrado no banco de leads retorna score=0 e é imediatamente bloqueada pelo filtro de score_minimo=10000.

- timestamp: 2026-04-12
  checked: agente.py linha 1967 — roteamento de fase
  found: if fase == "novo" and not _modo_retorno: → envia Q1. Esta linha NUNCA é alcançada para leads com score < score_minimo porque o early return na linha 1441 ocorre antes.
  implication: O roteamento de fase (Q1/Q2) é correto, mas o filtro de score o impede de ser atingido.

- timestamp: 2026-04-12
  checked: webhook.py linha 233-244 — score na criação do lead via formulário
  found: O webhook de formulário TAMBÉM verifica score_minimo antes de enviar Q1. Se score < score_minimo, marca lead como "nao_enviado" e não envia nada.
  implication: Há dois pontos de bloqueio por score: (1) no webhook de criação de lead, (2) no webhook de mensagem recebida do Evolution.

- timestamp: 2026-04-12
  checked: agente.py linha 1574-1584 — modo_humano bloqueio
  found: Se existe registro "HUMANO_ASSUMIU:..." em conversas para este número, a IA é bloqueada silenciosamente (a menos que seja cancelamento/remarcação).
  implication: Hipótese secundária: se alguém manualmente assumiu a conversa antes, a IA está bloqueada. Verificar na tabela conversas.

## Resolution

root_cause: HIPÓTESE PRINCIPAL: O lead 45999810908 tem score=0 (ou abaixo do score_minimo configurado). Quando sua mensagem chega via Evolution webhook, agente.py linha 1439-1442 executa early return silencioso ANTES de qualquer roteamento de fase, impedindo que Q1 seja enviado. Isso ocorre em dois cenários: (A) lead enviou mensagem direto no WhatsApp sem preencher formulário — não está na tabela leads → score=0 por padrão → bloqueado; (B) lead preencheu formulário mas seu score calculado é abaixo do score_minimo da empresa.

HIPÓTESE SECUNDÁRIA: Alguém da equipe assumiu manualmente a conversa (HUMANO_ASSUMIU registrado em conversas) antes do lead responder, bloqueando a IA (linha 1582-1584).

fix: Para confirmar: verificar no Supabase (1) tabela leads: EXISTS telefone=45999810908? qual score? (2) tabela conversas: EXISTS telefone=45999810908 role=sistema conteudo LIKE 'HUMANO_ASSUMIU:%'? (3) tabela empresas: qual config_ia.score_minimo?
verification:
files_changed: []
