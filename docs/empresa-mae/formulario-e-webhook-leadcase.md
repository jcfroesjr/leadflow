# Formulário de captação da LeadCase + mapeamento + payloads de teste

> IMPL-05. O formulário alimenta a Clara: a pergunta de desafio vira a **Q2** e o
> volume de leads vira a **Q3** (que é o que ela usa pra cotar a faixa certa).

---

## 1. Perguntas do formulário

Ordem pensada pra atrito crescente: identificação primeiro, qualificação depois.

| # | Pergunta | Tipo | Vai pra |
|---|---|---|---|
| 1 | Qual o seu nome completo? | texto | `leads.nome` |
| 2 | Qual o seu WhatsApp (com DDD)? | telefone | `leads.telefone` — **com +55** |
| 3 | Qual o seu melhor e-mail? | e-mail | `leads.email` |
| 4 | O que você vende hoje? | escolha | `dados_raw` |
| 5 | **Qual o seu maior desafio hoje no atendimento dos seus leads?** | escolha | **Q2 da Clara** |
| 6 | **Quantos leads novos você recebe por mês?** | escolha | **confirma a Q3** |
| 7 | Quanto custa o que você vende? | escolha | `dados_raw` |
| 8 | Hoje quem responde os seus leads? | escolha | `dados_raw` |

### Opções sugeridas

**4. O que você vende hoje?**
Mentoria / consultoria · Curso ou infoproduto · Serviço (clínica, estética, odonto) ·
Imóveis · Advocacia · Agência · Outro

**5. Maior desafio** — é o texto que a Clara devolve na Q2, então precisa soar como
frase do lead, não como rótulo:
- Lead chega e demoro pra responder
- Perco lead à noite, fim de semana e feriado
- Gasto muito tempo qualificando quem não tem perfil
- Marco reunião e a pessoa não aparece
- Meu anúncio traz lead mas pouca gente fecha
- Não consigo fazer follow-up de quem some

**6. Volume/mês** — as faixas espelham os planos de propósito. A resposta já diz em
qual plano ele cai antes da conversa:
- Até 50
- De 51 a 150
- De 151 a 350  ← ainda Essencial
- De 351 a 500  ← Pro
- De 501 a 850  ← Escala
- Mais de 850   ← Personalizado

**7. Ticket** — Até R$500 · R$500 a R$2 mil · R$2 mil a R$10 mil · Acima de R$10 mil

**8. Quem responde hoje?** — Eu mesmo · Secretária/assistente · Time de vendas ·
Um chatbot · Ninguém, os leads ficam esperando

### Score (Responde APP)

Dê peso maior a **volume** e **ticket** — são os dois que dizem se o LeadFlow paga a
conta pra pessoa. `score_minimo` da LeadCase está em **0**, ou seja, todo lead é
atendido; o score serve pra priorizar na tela, não pra barrar.

---

## 2. Mapeamento (`mapeamento_campos` do webhook)

O Responde APP entrega as respostas em `respondent.answers.<texto exato da pergunta>`.
O texto tem que bater **caractere por caractere** com o do formulário, interrogação
inclusive.

```json
{
  "nome":          "respondent.answers.Qual o seu nome completo?",
  "telefone":      "respondent.answers.Qual o seu WhatsApp (com DDD)?",
  "email":         "respondent.answers.Qual o seu melhor e-mail?",
  "interesse":     "respondent.answers.Qual o seu maior desafio hoje no atendimento dos seus leads?",
  "volume":        "respondent.answers.Quantos leads novos você recebe por mês?",
  "ticket":        "respondent.answers.Quanto custa o que você vende?",
  "vende":         "respondent.answers.O que você vende hoje?",
  "quem_responde": "respondent.answers.Hoje quem responde os seus leads?",
  "score":         "respondent.score",
  "canal":         "respondent.respondent_utms.utm_source",
  "criativo":      "respondent.respondent_utms.utm_content",
  "ad_id":         "respondent.respondent_utms.utm_term"
}
```

### As chaves EXTRAS viram variáveis (14/08)

`volume`, `ticket`, `vende` e `quem_responde` não são chaves conhecidas do
código — e é justamente esse o ponto. **Toda chave do mapeamento que não seja
reservada** (`nome`, `telefone`, `email`, `score`, `canal`, `criativo`, `ad_id`,
`empresa`, `interesse`/`desafio`) vira `{{lead.<chave>}}`, utilizável no
`prompt_sistema` e nos templates de Q1/Q2/Q3. O nome da chave é seu: mapeou
`"volume"`, escreve `{{lead.volume}}`.

Antes disso só o desafio chegava na conversa; o resto morria em `dados_raw` e só
aparecia no PDF. Consequência que se pagava toda conversa: a **Q3 re-perguntava o
volume** que o campo 6 já tinha perguntado — o mesmo loop de confirmação que o
prompt proíbe, atravessando a fronteira página→WhatsApp, onde nenhuma regra
pegava.

Duas travas, com teste em `tests/test_vars_formulario.py`:

- chave reservada **nunca** é sobrescrita por mapeamento (`"nome": "INVASOR"` não
  troca o nome do lead);
- variável escrita no template **sem** a chave correspondente no mapeamento não
  vaza `{{...}}` pro lead — some do texto e sai `[TEMPLATE-BELT]` no log. Foi
  assim que 57 leads da Jeenifer leram `[desafio informado no formulário]`.

O mapeamento é lido com cache de 60s: editou, testa na hora, sem redeploy.

Notas que evitam retrabalho:

- **`interesse` é a chave do desafio.** Sem ela, `{{lead.desafio}}` sai vazio e a Q2
  fica sem sentido — foi o caso Moema, 20/07.
- **UTMs são opcionais**: o código já cai em `utm_source`/`utm_content`/`utm_term`
  sozinho quando `canal`/`criativo`/`ad_id` não estão mapeados. Mapear explicitamente
  não atrapalha.
- **O telefone TEM que sair com o 55.** O webhook usa os dígitos crus e não
  acrescenta DDI em lugar nenhum: `(21) 99508-5057` vira `21995085057` e a Evolution
  não entrega, porque o JID brasileiro é `5521...@s.whatsapp.net`. Os leads da Rejane
  funcionam porque o formulário dela já manda `55...` (13 dígitos). No Responde APP:
  campo do tipo telefone com país Brasil, ou máscara que inclua `+55`. **Confira isso
  antes de publicar o formulário** — errado aqui, nenhum lead recebe a Q1 e o sintoma
  parece "o agente não respondeu".
- **Perguntas 4, 6, 7 e 8** continuam saindo no PDF que vai pro seu WhatsApp, e
  agora também chegam na conversa como `{{lead.vende}}`, `{{lead.volume}}`,
  `{{lead.ticket}}` e `{{lead.quem_responde}}` — desde que mapeadas acima.

---

## 3. Payload de teste — plano (não precisa de mapeamento)

`_extrair` cai em `payload.get(<campo>)` quando não há caminho mapeado. Serve pra
provar o caminho ponta a ponta antes de configurar o formulário.

Arquivo: `teste-lead-leadcase.json`

```json
{
  "nome": "Caca Teste",
  "telefone": "5521995085057",
  "email": "teste@leadcase.com.br",
  "interesse": "perco lead porque ninguém responde no WhatsApp fora do horário",
  "score": 100,
  "canal": "teste-manual",
  "criativo": "payload-teste",
  "empresa": "Mentoria Teste"
}
```

## 4. Payload de teste — formato Responde APP (valida o mapeamento)

Arquivo: `teste-lead-leadcase-respondeapp.json`. Use este **depois** de configurar o
mapeamento — ele prova que os caminhos aninhados estão certos.

---

## 5. Como disparar

**Passo 1 — pegar a URL do webhook.** Logado como LeadCase: Configurações → Webhooks.
Se não existir, crie um; a URL sai no formato
`/webhook/3f400111-3354-4552-b5b7-43e15a75b19d/<token>`.

**Passo 2 — disparar** (troque `<TOKEN>`):

```powershell
curl.exe -s -X POST -H "Content-Type: application/json" --data-binary "@c:/Projetos/Leadflow/docs/empresa-mae/teste-lead-leadcase.json" "https://leadflow-backend.bqvcbz.easypanel.host/webhook/3f400111-3354-4552-b5b7-43e15a75b19d/<TOKEN>"
```

Resposta esperada: `{"ok":true,"recebido":true}` — **na hora**. O processamento é em
background de propósito (21/07): o Responde APP tem timeout curto, e webhook lento
contava como falha; 15 falhas desativam o webhook e você fica sem lead, como no
apagão de 06/08.

**Passo 3 — acompanhar:**

```powershell
curl.exe -s -H "Authorization: Bearer 6213bf16-fad3-47ff-84b7-d18e6ac03154-intcaca01" "https://leadflow-backend.bqvcbz.easypanel.host/admin/logs?since_min=10&limit=80"
```

O que tem que acontecer, em ordem: lead salvo → Q1 enviada pro **21 99508-5057** →
você responde → Q2 com o desafio do payload → Q3 → empatia → horários.

⚠ O 21 99508-5057 vai **receber mensagem de verdade**. Use um número seu.
