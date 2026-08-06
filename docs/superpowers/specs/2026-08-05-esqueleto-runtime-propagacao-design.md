# Esqueleto em runtime — propagação atômica da lógica de agendamento

**Data:** 2026-08-05
**Escopo:** `config_ia.prompt_sistema`, `app/services/wizard/{esqueleto,montador}.py` e as
frases de voz hardcoded em `app/routers/agente.py` (§3.6)
**Fora de escopo:** implantação das telas de conversação (Q1/Q2/Q3, empatia, marcadinho,
follow-ups, confirmação D-1, offline, nutrição). Outro projeto.

---

## 1. Problema

A lógica de agendamento do agente vive em dois lugares: o código determinístico de
`agente.py` e as regras do `prompt_sistema`. O código é único e propaga sozinho. O
prompt **não**: ele é uma string materializada em `config_ia` por empresa, com os
blocos de regra fisicamente copiados dentro.

Consequência: corrigir uma lição de agendamento exige editar N prompts, um por
empresa. Na prática ninguém edita todos, e as empresas divergem em silêncio.

**A divergência já existe.** O prompt da Rejane em produção não tem três dos dez
blocos fixos do esqueleto:

- `# QUANDO LEAD CONFIRMA AGENDAMENTO`
- `# PROIBIDO ABSOLUTO — ANUNCIAR SEM CHAMAR` (+ `REGRA ABSOLUTA DE HORÁRIOS`)
- `# REGRA CRÍTICA — PROIBIDO REPETIR Q1`

E a `REGRAS INEGOCIÁVEIS #1` dela é a versão anterior ao fix do caso Vanessa — falta
a cláusula *"Na PRIMEIRA oferta (PASSO 3) … chame com dias=7 sem pedir preferência"*.
A lição está no esqueleto e não está em produção.

### 1.1. Segundo defeito: os blocos "fixos" carregam a voz da Rejane

O esqueleto foi extraído verbatim do prompt dela, e junto das regras vieram **frases
de resposta literais**, com emoji e estilo:

| Bloco | Texto embutido |
|---|---|
| `PRINCÍPIOS` #2 | "Entendi, dia cheio! 💛 Algum outro dia funciona melhor?" |
| `PRINCÍPIOS` #2 | "Imagino! A call é rapidinha, só 30min. Prefere começo ou fim do dia?" |
| `TRATAMENTO` CAT 2 | "Beleza, vou ver na manhã de sexta pra você 😊" |
| `TRATAMENTO` CAT 3 | "Tranquilo! 💛 Tem algum dia…" · "Sem problema! Manhã, tarde ou noite…" · "Entendi 💛 Qual dia costuma ser…" |
| `TRATAMENTO` CAT 4 | "Claro, {{lead.nome}}! Fico no aguardo 💛 Qualquer coisa, é só me chamar." |
| `MEMÓRIA` | "Olha {{lead.nome}}, dessa vez não achei opções diferentes…" |
| `PROIBIDO ABSOLUTO` | "Poxa, as 10h ja esta reservado, mas tenho 11h ou 11h30…" |
| `REGRA CRÍTICA Q1` | "Tudo bem, qualquer coisa estou por aqui!" |
| `FORMATO DE RESPOSTA` | "MÁX 1 emoji por mensagem" |

São 💛 três vezes, 😊 uma, ✅ uma, dentro do que deveria ser regra universal.

Impacto medido contra as implantações existentes:

- **Liliane** — tom definido como *sem emojis, corporativo*. Recebe `Tranquilo! 💛`.
- **Jeenifer (NPA)** — público de terapeutas, *"emoji elegante, sem monte de coração"*.
  Mesmo problema.
- **Natália Titos** — reunião de **45min**. O bloco afirma *"a call é rapidinha, só
  30min"*. Isso não é tom, é **fato errado** dito ao lead.

### 1.2. Terceiro defeito: texto fixo fora do alcance do validador

`montador._identidade()` escreve *"qualificar leads do formulário e AGENDAR uma
conversa via WhatsApp"* dentro da função, não em `BLOCOS_FIXOS`. O `validar()` confere
byte a byte apenas o que está em `BLOCOS_FIXOS` — essa linha não é conferida. A Rejane
diz *"AGENDAR uma **sessão estratégica**"*; montar hoje trocaria o vocabulário do nicho
sem o validador reclamar.

---

## 2. Princípio

> *"Todas as regras do prompt têm que ser soberanas. As palavras vamos modificar."*
> — dono, 05/08

> *"Só não o esqueleto, que serve para todos."*

**Regra é soberana e universal. Palavra é da empresa.** Tudo neste documento é
consequência disso:

- A **estrutura** — regras, categorias, tabelas de decisão, ordem, proibições, e a
  lógica de gatilho no código — é uma só, vale para todas, e ninguém edita por empresa.
- A **palavra** — toda frase que o lead pode ler — é da empresa, sem exceção. Não existe
  frase compartilhada entre clientes, nem como default, nem como fallback.

O objetivo do arquivo de implantação é ter **a cara do cliente**: cada empresa que entra
no ar fala com a voz dela em 100% dos momentos, e recebe as regras de todo mundo.

## 2.1. Objetivo técnico

Uma correção na lógica de agendamento entra em **um** lugar e vale para **todas** as
empresas na mesma hora, existentes e novas — sem job de sincronização e sem UPDATE em
massa.

**Não-objetivo:** unificar tom, estilo ou vocabulário entre empresas. O oposto: a voz
tem que passar a ser realmente de cada uma.

---

## 3. Desenho

### 3.1. Estrutura fixa, voz variável

Cada bloco do esqueleto se divide em duas naturezas:

- **Estrutura** — a regra, as CATEGORIAS 1–4, a tabela de decisão, a ordem dos blocos,
  as proibições. Idêntica byte a byte em todas as empresas. É o que garante que, quando
  algo quebra, o mapa de depuração é sempre o mesmo.
- **Voz** — as frases modelo *dentro* da regra. Viram lacunas, preenchidas na migração
  com o tom e o estilo do cliente.

O bloco passa a ser um template com lacunas nomeadas:

```
## CATEGORIA 3 — Rejeição vaga (CHAVE)
Ex: "esse não dá", "tem outro?", "não consigo", "trabalho o dia todo"

NÃO chame função. Pergunta UMA coisa:
- {{resp.cat3_a}}
- {{resp.cat3_b}}
- {{resp.cat3_c}}

DEPOIS da resposta, volta na CATEGORIA 2 e busca certo.
```

São ~10 lacunas de voz no esqueleto inteiro:

| Lacuna | Bloco de origem |
|---|---|
| `resp.espelho_dia_cheio` | `PRINCÍPIOS` #2 |
| `resp.espelho_corrida` | `PRINCÍPIOS` #2 |
| `resp.cat2_validacao` | `TRATAMENTO` CAT 2 |
| `resp.cat3_a`, `resp.cat3_b`, `resp.cat3_c` | `TRATAMENTO` CAT 3 |
| `resp.cat4_aguardo` | `TRATAMENTO` CAT 4 |
| `resp.sem_opcoes_novas` | `MEMÓRIA` |
| `resp.horario_ocupado` | `PROIBIDO ABSOLUTO` |
| `resp.encerrar_cordial` | `REGRA CRÍTICA Q1` |

A duração da reunião **não** é lacuna de voz: sai de
`config_agendamento.duracao_reuniao_minutos`. É dado, e escrever à mão já produziu
erro factual em produção.

### 3.2. Montagem em runtime

`config_ia.prompt_sistema` deixa de guardar o prompt inteiro. Guarda só o que é da
empresa: identidade/nicho, personalidade, perguntas, objeções, e as lacunas de voz.

| | Onde vive | Quem edita | Propaga |
|---|---|---|---|
| Estrutura dos 10 blocos | `esqueleto.py` (código) | nós, 1 lugar | deploy → todas, na hora |
| Lacunas de voz | `config_ia` | implantação | não (é da empresa) |
| Identidade / nicho / tom / emojis | `config_ia` | implantação | não |
| Perguntas de qualificação | `config_ia` | implantação | não |
| Objeções | `config_ia` | implantação | não |

`agente.py` chama `montador.montar(config_ia)` no momento da requisição, no lugar do
`config_ia.get("prompt_sistema", …)`. Como não existe cópia dos blocos no banco, não
existe dessincronização possível.

**Pontos de integração** (verificados no código):

- [`agente.py:6293`](../../../leadflow-backend/app/routers/agente.py#L6293) — fluxo principal do webhook
- [`agente.py:11654`](../../../leadflow-backend/app/routers/agente.py#L11654) — segundo ponto de entrada

A montagem entra **antes** das ~12 mutações de runtime já existentes (RAG, contexto de
slots, branches de objeção, restauração do `_prompt_sistema_base` em `agente.py:9038`).
Essas continuam operando sobre o resultado, sem alteração.

### 3.3. Política de emoji vira campo

[`agente.py:5949`](../../../leadflow-backend/app/routers/agente.py#L5949) decide se a
empresa aceita coração procurando a substring `"não use cora"` **dentro do texto do
prompt**. Com o prompt montado, política inferida de substring é frágil por construção.
Passa a ser campo explícito em `config_ia` (a lista `emojis` que o montador já usa em
`_personalidade()`), e o esqueleto lê o campo.

### 3.4. Pin de versão por empresa

`config_ia.esqueleto_versao`, default `"latest"`. Empresa nova nasce em `latest`.

Se um bloco novo causar problema numa empresa, ela é pinada na versão anterior sem
travar as outras e sem deploy para reverter. Sem isso, um bug no esqueleto atinge todas
as empresas instantaneamente — mesmo raio de dano do incidente de 31/07 (UPDATE sem
WHERE), só que por design.

### 3.5. A tela do Agente IA vira read-only

**Decisão do dono (05/08):** o textarea do prompt do sistema deixa de existir.
*"Não pode mexer, senão perde nossas melhorias fixas ao longo do tempo."*

A tela passa a ter:

- **Campos editáveis** — só as lacunas: identidade/nicho, tom, emojis, perguntas,
  objeções, e as ~10 frases de voz.
- **Preview read-only** — o prompt montado, exibido para conferência, sem edição.

**Não existe escape hatch.** Nada de `esqueleto_versao: "manual"`, nada de textarea
liberado sob aviso. A razão é a que motivou o projeto inteiro: qualquer caminho que
permita escrever texto livre por cima de um bloco reintroduz a divergência silenciosa
— só que agora com a aparência de estar sob controle.

**Consequência, e é a parte que importa:** quando uma empresa precisar de algo que o
esqueleto não expressa, a saída **não** é liberar a edição dela. É **criar uma lacuna
nova no esqueleto**. Isso é código, é revisado, e passa a existir para todas as
empresas. O desvio de uma vira capacidade do sistema, em vez de dívida escondida no
`config_ia` de uma linha do banco.

O gate do diff (§4) é quem detecta isso: todo texto que cai no balde **perda** é uma
lacuna faltando, e bloqueia a migração até ela existir.

### 3.6. As frases embutidas no `agente.py` também viram lacunas

**Pedido do dono (05/08):** *"quando o LLM não entende, salta essa frase embutida no
código. Não quero isso mais — quero por empresa."*

O esqueleto não é a única fonte de voz da Rejane, e o problema não está só no
`agente.py`. Varredura do backend inteiro (`app/**/*.py`, literais em português
voltados ao lead, descartando log, SQL e instrução ao LLM):

| | Total |
|---|---|
| Candidatos a voz no backend | **258**, em 38 arquivos |
| …só em `app/routers/agente.py` | **153** |
| …em `app/routers/confirmacao_agendamento.py` | 15 |
| …em `app/routers/leads.py` | 13 |
| …em `app/services/wizard/esqueleto.py` | 10 |
| …em `app/services/qualificacao_lock.py` | 8 |
| Literais **com emoji** no `agente.py` | 46 |

O número exato de chaves finais sai da triagem (parte é log residual, parte é uma
mesma frase repetida em ramos diferentes). Mas a ordem de grandeza é essa: **centenas
de frases**, não dezenas. Todas hoje compartilhadas entre todos os clientes.

Os dois que o dono apontou são os fallbacks de falha do LLM:

| Local | Gatilho | Texto |
|---|---|---|
| `agente.py:3919` | SAFETY-NET: handler ficou silencioso | "Anotei aqui! Só um momento que vou conferir pra te responder direitinho 💛" |
| `agente.py:9249-9257` | LLM retornou vazio (loop de tool_calls ou falha silenciosa) | "Deixa eu verificar aqui e já te retorno, {nome}! 💛" |

Outros que vão para o lead:

| Local | Texto |
|---|---|
| `agente.py:3164` | "Que bom falar com você 😊" |
| `agente.py:5207` | "Oi! 🙈 Não consegui ouvir bem seu áudio… 💛" |
| `agente.py:6062` | "Tudo bem, fico à disposição… é só me chamar 💛" |
| `agente.py:6168` | "Tudo certo! Agradeço o retorno 💛" |
| `agente.py:9580` | "horário certinho 😊 Só um instante!" |
| `agente.py:10024`, `10276`, `10606` | "Conferi aqui na agenda 😊" / "consegui aqui pra você 😊" |
| `agente.py:10027`, `10436`, `10682` | "Qual funciona melhor pra você? 😊" |
| `agente.py:8577`, `8765`, `8817`, `8820` | âncoras pós-LLM, anexadas à resposta |

E o caso mais direto de contradição — o código **instruindo** o modelo:

| Local | Texto |
|---|---|
| `agente.py:8262`, `8402`, `8460` | "Use emojis com moderação: 💛 😊" |

A Liliane está configurada como *sem emojis, corporativo*. O sistema manda o modelo
dela usar coração, em três lugares.

**Desenho:** mesmo princípio do §3.1, aplicado ao código. O `agente.py` mantém a
**lógica do gatilho** (quando o safety-net dispara, quando o LLM voltou vazio) e perde
o **texto**. O texto vem de `config_ia`, por chave nomeada, resolvido por uma função
única:

```python
voz(config_ia, "falha_llm_vazio", nome=_nome_curto)
```

Isso é o que satisfaz *"se for no código tem que funcionar pra ambos também"*: a
correção do gatilho continua sendo uma só e propaga por deploy; a frase passa a ser da
empresa.

Exemplo do próprio dono para a chave `falha_llm_vazio`: *"vou chamar um atendente pra
te auxiliar"* — que para um público de terapeutas ou um cliente corporativo é resposta
melhor do que *"Anotei aqui! … 💛"*.

#### Fallback quando a chave não existe — decisão pendente

O §3.7 proíbe fallback silencioso, e a razão é o incidente do `marcadinho_template`
(05/08): o default hardcoded era persona de outra empresa. Mas suprimir a mensagem do
SAFETY-NET seria pior que mandá-la — o safety-net existe justamente para o lead não
ficar sem resposta.

Regra proposta: **fallback nunca carrega persona**. Se a chave faltar, o sistema envia
um texto neutro — sem emoji, sem nome de agente, sem tom — e loga em nível de erro.
Ex.: *"Só um momento, já te respondo."* Não é a voz de ninguém, e por isso não vaza
identidade de empresa nenhuma.

A `validar()` continua exigindo todas as chaves preenchidas na implantação, então o
neutro é rede de segurança, não caminho normal.

**A decidir:** o dono aprova o texto neutro como último recurso, ou prefere que a
ausência de chave bloqueie a empresa de entrar no ar?

### 3.7. `validar()` passa a cobrir três coisas

1. Estrutura byte a byte (já faz) — **e agora incluindo o texto hoje preso em
   `_identidade()`**, que precisa migrar para `BLOCOS_FIXOS` ou ganhar cobertura
   equivalente.
2. Toda lacuna `{{resp.*}}` preenchida. Lacuna vazia recusa a montagem — não existe
   fallback silencioso para o texto da Rejane. Esse é exatamente o modo de falha do
   `marcadinho_template` (05/08): o default hardcoded era persona de outra empresa.
3. As frases de voz respeitam a política de emoji da empresa.

---

## 4. Migração

Nenhuma empresa migra sem diff aprovado. Para cada uma:

1. Ler o `prompt_sistema` atual e guardar cópia em `config_ia.prompt_sistema_backup`.
2. Extrair as lacunas (identidade, tom, emojis, perguntas, objeções, frases de voz).
3. Montar com o esqueleto.
4. Diff contra o prompt atual, classificado em três baldes:
   - **igual** — tem que ser a maioria esmagadora. Se não for, o desenho está errado.
   - **perda** — texto do nicho que sumiu. Nunca aceitável: é lacuna faltando no
     montador. Adicionar a lacuna e repetir.
   - **ganho** — bloco de agendamento que a empresa não tinha. Aprovado **um por um**
     pelo dono, nunca em lote.
5. Só grava depois da aprovação. Reverter é escrever `prompt_sistema_backup` de volta —
   um campo, sem deploy.

### 4.1. Ordem: Rejane primeiro

Contra-intuitivo, e é de propósito. O esqueleto foi extraído do prompt dela, então as
frases embutidas **são as dela**. Preencher as lacunas da Rejane com os valores atuais
tem que produzir um prompt **byte a byte idêntico ao de hoje**.

O diff da Rejane é o teste do montador: **tem que dar zero**. Diff vazio prova que a
montagem em runtime reproduz produção. Qualquer coisa diferente de zero é bug no
montador, encontrado antes de tocar em qualquer empresa.

Os três blocos que faltam nela entram **depois**, ligados um a um, com conversa real
sendo acompanhada — não como efeito colateral da migração.

Depois da Rejane: Liliane, Jeenifer, Natália. Nessas o diff vai expor onde a voz da
Rejane estava sobrescrevendo a delas — bug que já está no ar hoje, apenas invisível.

---

## 4.2. Portão de entrada no ar — regressão contra incidentes conhecidos

**Exigência do dono (05/08):** *"não posso aceitar implantar uma empresa nova e o
sistema pular as Q, mandar informação de agendamento errado — sendo que já foi
corrigido em outra empresa."*

**Propagar o esqueleto não entrega isso sozinho.** As duas falhas citadas nascem de
três origens distintas, e só duas propagam:

| Origem da falha | Propaga sozinho? |
|---|---|
| Regra do prompt (`esqueleto.py`) | sim, depois deste projeto |
| Código determinístico (FSM das Q, slot-pick, failsafe, guards) | sim, já hoje, por deploy |
| **Config por empresa** (`campo_desafio`, `duracao_reuniao_minutos`, `score_minimo`, mapeamento do webhook, `grupo_ativo`) | **não, nunca** |

A terceira é a que causa exatamente os sintomas citados:

- **Q2 sai aberta** porque `campo_desafio` não foi mapeado contra o payload real do
  formulário — a regra está certa, falta o dado. (Playbook, item 3.)
- **Duração errada no convite** porque `duracao_reuniao_minutos` não bate com a sessão
  real da empresa. (Playbook, item 6 — caso Natália, 45min.)
- **Lead nunca abordado** porque `score_minimo` não bate com o score real do formulário
  daquele cliente. (Playbook, item 4.)

Empresa nova com esqueleto perfeito e código atualizado **ainda pula Q** se a config
estiver incompleta. Logo, a garantia pedida exige uma terceira perna.

### 4.2.1. A bateria

O índice de memória documenta ~90 sessões de fix já shippados. Cada uma é um modo de
falha conhecido — e portanto um caso de teste. A implantação passa a ter um portão:
**empresa nova não vai ao ar sem passar.**

Cada caso é um par (entrada, comportamento proibido), rodado contra a empresa recém
implantada com lead de teste:

| Caso | Origem | Falha proibida |
|---|---|---|
| Lead responde só "Boa noite!" | 31/07 saudação | Confirmar Q2/Q3 e forçar slots |
| Q1 vem do painel, não do LLM | 28/07 q1 determinística | Q1 improvisada |
| Lead confirma Q2 | 29/07 cascata Q3 | Promover a qualificado antes da Q3 |
| Lead diz "trabalho às 8:30" | 05/08 restrição de horário | Re-ofertar 08:00 |
| Lead pede dia da semana | 01/08 rebusca | Frase pronta de "não tem" |
| Lead faz pergunta antes de escolher | 02/08 pergunta não agenda | Chutar o primeiro slot e criar evento |
| Lead pede valor após slots | 01/08 pergunta valor | Bypass dos forçadores |
| Empresa com `ativa=false` | 01/08 empresa inativa | Lead órfão sem follow-up |
| …demais incidentes do índice | | |

A lista completa sai da triagem do índice de memória. O critério não é "todos os ~90",
é **todos os que são reproduzíveis com lead de teste** — os demais viram checklist
manual no playbook.

### 4.2.2. Validação de config, não só de comportamento

Parte dos casos é verificável sem conversar, e essa parte roda primeiro por ser barata:

- `campo_desafio` resolve contra o `ultimo_payload` real do webhook — não deduzido
- `duracao_reuniao_minutos` preenchido e conferido com o cliente
- `score_minimo` conferido contra o score real dos leads do CSV
- `grupo_ativo` coerente com o que a voz de confirmação promete
- toda chave de voz (§3.6) preenchida
- linha ativa em `membros` para o acesso da dona

Isso é o "checklist de ouro" do playbook virando código executável em vez de item de
leitura que alguém pode pular.

## 5. Riscos

| Risco | Mitigação |
|---|---|
| Bug no esqueleto atinge todas as empresas de uma vez | `esqueleto_versao` pinável por empresa; rollback sem deploy |
| Montador perde texto de nicho na migração | Gate do diff; balde "perda" bloqueia a migração |
| Lacuna de voz não preenchida numa empresa nova | `validar()` recusa a montagem; sem fallback silencioso |
| Custo de montar o prompt a cada requisição | Concatenação de strings; desprezível frente à chamada do LLM |
| Empresa precisa de algo que o esqueleto não expressa | Vira lacuna nova no esqueleto (código, revisado, vale pra todas) — nunca texto livre no banco. Ver §3.5 |
| Alguém edita o prompt à mão e desfaz a propagação | Impossível por construção: não há textarea. Ver §3.5 |

---

## 6. Questões em aberto

1. **Onde as lacunas de voz são preenchidas na implantação** — SQL da Fase 1, ou tela.
   Depende do projeto de implantação, que está fora deste escopo.

*(A tela do Agente IA foi decidida em 05/08 — read-only, sem escape hatch. Ver §3.5.)*

---

## 7. Critério de pronto

- [ ] Diff da Rejane = zero, com montagem em runtime ligada
- [ ] `validar()` recusa montagem com lacuna de voz vazia
- [ ] `validar()` cobre o texto hoje preso em `_identidade()`
- [ ] Liliane e Jeenifer sem 💛 em nenhuma frase modelo
- [ ] Natália com a duração real (45min) vinda de `config_agendamento`
- [ ] Alterar um bloco em `esqueleto.py` + deploy muda as 5 empresas, verificado em
      prompt montado
- [ ] Pin de versão segura uma empresa sem afetar as outras
- [ ] Tela do Agente IA sem textarea de prompt: lacunas editáveis + preview read-only
- [ ] Não existe caminho no sistema que grave texto livre por cima de um bloco fixo
- [ ] Nenhum literal com emoji em `agente.py` sai para o lead: os 46 triados, os de voz
      movidos para `config_ia`, os de instrução ao LLM lendo a política da empresa
- [ ] `agente.py:8262/8402/8460` param de mandar o modelo usar 💛😊 — a instrução passa a
      refletir a lista `emojis` da empresa (Liliane sem nenhum)
- [ ] SAFETY-NET e fallback de LLM vazio falam na voz da empresa
- [ ] Nenhum fallback de última instância carrega persona (sem emoji, sem nome de agente)

**Portão de implantação (§4.2) — é isto que responde à exigência do dono:**

- [ ] Empresa nova não vai ao ar sem passar na bateria de regressão
- [ ] Bateria cobre os incidentes reproduzíveis com lead de teste, derivados do índice
- [ ] Validação de config roda antes da de comportamento (barata primeiro)
- [ ] Reprodução de "pular Q" e "agendamento errado" **falha o portão**, não passa
      despercebida
- [ ] Checklist de ouro do playbook virou verificação executável, não item de leitura
