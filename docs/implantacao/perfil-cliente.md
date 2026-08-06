# Perfil do cliente — layout do arquivo de implantação

**Uma empresa = um perfil.** Este arquivo é a cara do cliente. Toda frase que o lead
pode ler sai daqui; nada é herdado de outra empresa, nem como default, nem como
fallback.

O que **não** está aqui: as regras. Elas vivem no `esqueleto.py` e no código, são
iguais para todas, e não se editam por empresa. *"As regras do prompt têm que ser
soberanas. As palavras vamos modificar."*

Status dos campos:

| | |
|---|---|
| ✅ | já existe e é lido pelo código hoje |
| 🆕 | campo novo — precisa ser criado |
| ⚠️ | hoje o código **adivinha** isso; passa a ler daqui |

---

## 1. Identidade

```json
"identidade": {
  "nome_agente":       "Bia",
  "nome_responsavel":  "Rejane",
  "empresa_nome":      "Rejane Leal Mentora",
  "papel":             "SDR humana e experiente",
  "sessao_label":      "sessão estratégica"
}
```

| Campo | | Onde é lido |
|---|---|---|
| `nome_agente` | ✅ | `config_ia.nome_agente` |
| `nome_responsavel` | ✅ | `config_ia.nome_responsavel` |
| `empresa_nome` | ✅ | variável `{{empresa_nome}}` |
| `papel` | ✅ | slot do `montador._identidade()` |
| `sessao_label` | 🆕 | **hoje é hardcoded** dentro de `_identidade()` como *"uma conversa"*. A Rejane diz *"uma sessão estratégica"*. Como está dentro da função e não em `BLOCOS_FIXOS`, o `validar()` byte a byte **não confere essa linha** |

---

## 2. Voz — o que dá a cara do cliente

### 2.1. Paleta de emoji

```json
"voz": {
  "tom": "acolhedor e próximo, como amiga que trabalha com vendas",
  "emojis": ["💛", "😊", "💘", "✅"],
  "emoji_max_por_msg": 1
}
```

| Campo | | Observação |
|---|---|---|
| `tom` | ✅ | slot do `montador._personalidade()` |
| `emojis` | ⚠️🆕 | **É o ponto crítico.** Hoje não existe campo: `agente.py:5949` decide farejando a substring `"não use cora"` dentro do `prompt_sistema`. Prompt sem essa frase exata → a empresa leva 💛. E `agente.py:8262/8402/8460` **instruem o modelo**: *"Use emojis com moderação: 💛 😊"* — para todas, inclusive a Jeenifer, que atende terapeutas e pede *"sem monte de coração"* |
| `emoji_max_por_msg` | 🆕 | hoje é a linha fixa *"MÁX 1 emoji por mensagem"* dentro do bloco `FORMATO DE RESPOSTA` |

Lista vazia = **empresa não usa emoji**. O `validar()` já recusa frase com emoji
quando `emojis: []`.

### 2.2. Frases dentro das regras — 12 lacunas

Preenchem os `{{resp.<chave>}}` do esqueleto. **Todas obrigatórias** —
`montar()` levanta `ValueError` com qualquer uma vazia, de propósito.

```json
"voz": {
  "frases": {
    "espelho_dia_cheio":  "",
    "espelho_corrida":    "",
    "exemplo_negrito":    "",
    "regra_emoji":        "",
    "cat2_validacao":     "",
    "cat3_a":             "",
    "cat3_b":             "",
    "cat3_c":             "",
    "cat4_aguardo":       "",
    "sem_opcoes_novas":   "",
    "horario_ocupado":    "",
    "encerrar_cordial":   ""
  }
}
```

| Chave | O que a frase precisa fazer |
|---|---|
| `espelho_dia_cheio` | Lead diz que o dia está cheio. Acolhe e pergunta outro dia |
| `espelho_corrida` | Lead diz que está corrida. Acolhe, lembra que é curta (**usar a duração real**) e pergunta o turno |
| `exemplo_negrito` | Exemplo de como escreve data/hora final em negrito |
| `regra_emoji` | Limite de emoji por mensagem, na política da empresa |
| `cat2_validacao` | Validação breve antes de buscar, quando a lead deu contexto claro |
| `cat3_a/b/c` | Rejeição vaga — três variações: qual **dia**, qual **turno**, qual dia mais tranquilo |
| `cat4_aguardo` | Lead pediu tempo. Acolhe e encerra sem insistir e sem oferecer horário |
| `sem_opcoes_novas` | A busca só devolveu horários já oferecidos |
| `horario_ocupado` | Lead pediu horário fora da lista (= ocupado). **Nunca "problema técnico"** |
| `encerrar_cordial` | Lead nega ter preenchido o formulário. Encerra sem insistir |

### 2.3. Fallbacks — quando o sistema falha

Hoje **hardcoded no `agente.py`**, todos com 💛, todos iguais para todas as empresas.

```json
"voz": {
  "fallbacks": {
    "safety_net":      "",
    "llm_vazio":       "",
    "audio_ilegivel":  "",
    "optout_despedida":"",
    "verificando":     ""
  }
}
```

| Chave | | Hoje |
|---|---|---|
| `safety_net` | ⚠️🆕 | `agente.py:3919` — *"Anotei aqui! Só um momento que vou conferir pra te responder direitinho 💛"* |
| `llm_vazio` | ⚠️🆕 | `agente.py:9249-9257` — *"Deixa eu verificar aqui e já te retorno, {nome}! 💛"* |
| `audio_ilegivel` | ⚠️🆕 | `agente.py:5207` — *"Oi! 🙈 Não consegui ouvir bem seu áudio… 💛"* |
| `optout_despedida` | ⚠️🆕 | `agente.py:6062` — *"Tudo bem, fico à disposição… é só me chamar 💛"* |
| `verificando` | ⚠️🆕 | `agente.py:9580` — *"horário certinho 😊 Só um instante!"* |

Exemplo do dono para `llm_vazio`: *"vou chamar um atendente pra te auxiliar"* — para
público de terapeutas ou cliente corporativo, é melhor que *"Anotei aqui… 💛"*.

**A decidir:** chave faltando → texto neutro sem persona (*"Só um momento, já te
respondo."*) e log de erro, ou **bloqueia a empresa de entrar no ar**?

### 2.4. Momentos da conversa

Também hardcoded hoje.

```json
"voz": {
  "momentos": {
    "saudacao_retorno":   "",
    "slots_encontrados":  "",
    "escolha_slot":       ""
  }
}
```

| Chave | | Hoje |
|---|---|---|
| `saudacao_retorno` | ⚠️🆕 | `agente.py:3164` — *"Que bom falar com você 😊"* |
| `slots_encontrados` | ⚠️🆕 | `agente.py:10024/10276/10606` — *"Conferi aqui na agenda 😊"* / *"consegui aqui pra você 😊"* |
| `escolha_slot` | ⚠️🆕 | `agente.py:10027/10436/10682` — *"Qual funciona melhor pra você? 😊"* |

---

## 3. Qualificação

```json
"qualificacao": {
  "perguntas": ["Q1…", "Q2…"],
  "empatia":   "",
  "campo_desafio": "respondent.answers.<pergunta EXATA do form>",
  "score_minimo": 10000
}
```

| Campo | | |
|---|---|---|
| `perguntas` | ✅ | `q1_template`, `q2_template`, `q3_template`, `perguntas_extras` |
| `empatia` | ✅ | `empatia_template` — enviada **pré-LLM**. Nunca colar no `prompt_sistema` (duplica) |
| `campo_desafio` | ✅ | Fonte canônica é o **mapeamento do webhook**, chave `desafio`/`interesse`. Tem cascata de 4 níveis (`agente.py:5294-5333`) com auto-detecção — é o **modelo do padrão certo** |
| `score_minimo` | ✅ | Conferir contra o score real do CSV do cliente |

---

## 4. Agendamento

```json
"agendamento": {
  "duracao_reuniao_minutos": 60,
  "plataforma": "zoom",
  "grupo_ativo": true,
  "confirmacao": ""
}
```

| Campo | | |
|---|---|---|
| `duracao_reuniao_minutos` | ✅ | **Sem cascata e sem default derivado.** Natália = 45min, código assume 60/30. É dado, não tom: a frase `espelho_corrida` deve interpolar daqui |
| `plataforma` | ✅ | Zoom / Meet / Teams. Se Meet, a confirmação **não** pode perguntar de Zoom |
| `grupo_ativo` | ✅ | Se `false`, a confirmação não pode prometer grupo |
| `confirmacao` | ✅ | `config_ia.marcadinho_template`. **Sobrescreve a resposta do LLM** quando o evento é criado. Vazio → cai no default, que é a persona da Rejane |

---

## 5. Objeções

```json
"objecoes": [
  { "objecao": "preço", "resposta": "" }
]
```

✅ slot do `montador._objecoes()`. Acolhe primeiro, nunca fala preço.

---

## 6. O que este arquivo **não** controla

Regras, e é de propósito:

- Os 11 blocos do `esqueleto.py` — categorias 1-4, tabelas de decisão, proibições, ordem
- FSM das Q, slot-pick, failsafe, guards
- A tela do Agente IA é **read-only** no prompt: quem precisa de algo que o esqueleto
  não expressa ganha **lacuna nova no esqueleto** (código, revisado, vale pra todas),
  nunca texto livre no banco

---

## 7. Estado real

**Nada disso está ligado ainda.** O que existe hoje:

- ✅ As 12 lacunas de voz existem no `esqueleto.py`, com `montar()` recusando vazio
- ✅ `resolver_prompt()` garante que empresa não migrada não regride
- ❌ `agente.py` **não** chama o montador — lê `prompt_sistema` cru
- ❌ Nenhum dos ⚠️🆕 foi implementado
- ❌ `config_ia.emojis` não existe

Spec: `docs/superpowers/specs/2026-08-05-esqueleto-runtime-propagacao-design.md`
