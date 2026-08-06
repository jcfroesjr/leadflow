# Esqueleto em runtime — propagação atômica da lógica de agendamento

**Data:** 2026-08-05
**Escopo:** `config_ia.prompt_sistema` e `app/services/wizard/{esqueleto,montador}.py`
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

## 2. Objetivo

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

### 3.5. `validar()` passa a cobrir três coisas

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

## 5. Riscos

| Risco | Mitigação |
|---|---|
| Bug no esqueleto atinge todas as empresas de uma vez | `esqueleto_versao` pinável por empresa; rollback sem deploy |
| Montador perde texto de nicho na migração | Gate do diff; balde "perda" bloqueia a migração |
| Lacuna de voz não preenchida numa empresa nova | `validar()` recusa a montagem; sem fallback silencioso |
| Custo de montar o prompt a cada requisição | Concatenação de strings; desprezível frente à chamada do LLM |
| Empresa precisa sair do trilho | Decidir se existe escape hatch — **questão em aberto**, ver §6 |

---

## 6. Questões em aberto

1. **A tela "Prompt do sistema" no Agente IA.** Vira lacunas + preview read-only,
   ou mantém textarea editável com escape hatch (`esqueleto_versao: "manual"`, para de
   receber propagação)? Recomendação: read-only, que é a leitura literal de *"as regras
   fixas não podem mudar uma vírgula"*.
2. **Onde as lacunas de voz são preenchidas na implantação** — SQL da Fase 1, ou tela.
   Depende do projeto de implantação, que está fora deste escopo.

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
