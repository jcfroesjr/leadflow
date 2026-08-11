# RAG da Clara — base de objeções e dúvidas (LeadCase / LeadFlow)

> Cada bloco abaixo é **uma mensagem `/ia` separada**. Não cole tudo de uma vez.

## Por que um bloco por mensagem

`rag._chunkar` corta em **400 palavras com 40 de overlap**. Um documentão vira chunks
cortados em lugar arbitrário — a resposta do preço pode terminar no meio e o pedaço que
volta pra Clara fica truncado. Mandando um `/ia` por assunto, **cada assunto vira um
chunk inteiro** e volta completo.

A busca é `text-embedding-3-small` com threshold **0.28** (piso 0.18, `top_k=5`). Ela
compara a **mensagem crua do lead** contra o chunk. Por isso cada bloco começa com as
**variações reais que o lead digita** — é o que faz o score subir. Sem essa linha, "e se
ela errar?" não encontra um texto que só fala em "confiabilidade do agente".

## Como enviar

Pelo seu número (já autorizado em `config_ia.numeros_ensino`) mande pro número da
LeadCase, um por vez, esperando o "Aprendi ✅":

```
/ia <cole um bloco inteiro aqui>
```

Use um self-chat ou uma nota — a confirmação volta no mesmo chat. Depois de indexar,
confira com `GET /admin/rag/testar` usando as perguntas de teste do fim do arquivo.

---

### 1. Preço

```
/ia PERGUNTAS: quanto custa, qual o valor, qual o preço, quanto é, quanto fica por mês, mensalidade, valor do investimento, tem taxa, é caro, cabe no meu bolso.

O preço depende de quantos leads o cliente recebe por mês. São tres planos: ate 350 leads por mes custa R$297 por mes; de 351 a 500 leads custa R$597 por mes; acima de 500 leads custa R$997 por mes. A maioria dos mentores fica no plano de R$297.

Em todos os planos ha R$997 de implantacao, cobrados uma unica vez no inicio. A implantação não é taxa de cadastro: é o trabalho de configurar o agente com o método e o jeito de falar do cliente, conectar o WhatsApp, conectar a agenda e testar com lead real antes de ligar. Quem faz é o time da LeadCase, não o cliente.

Se o cliente passar do limite do plano dele num mes, nao bloqueamos o atendimento de jeito nenhum — nenhum lead fica sem resposta. Cobramos R$0,40 por lead excedente naquele mes. So se ele ficar tres meses seguidos acima da faixa e que o plano sobe, porque ai virou o padrao dele e nao um pico de campanha.

Sem fidelidade e sem multa. A cobrança é mensal e o cliente cancela quando quiser.

Forma de ancorar o valor: um mentor que vende mentoria de alguns milhares de reais precisa recuperar UM lead perdido por mês para o sistema se pagar várias vezes. E o lead perdido é invisível — ninguém contabiliza quem mandou mensagem no sábado à noite e não teve resposta.

Comparação honesta: uma secretária ou SDR dedicada a responder e qualificar custa acima de R$3.000 por mês com encargos, trabalha 8 horas por dia e tira férias.
```

### 2. "É robô?"

```
/ia PERGUNTAS: isso é um robô, é um bot, é automático, é uma pessoa ou uma máquina, tô falando com IA, é atendimento automático, o cliente percebe que é robô, meu lead vai perceber, parece robô, odeio falar com robô.

Sim, a Clara é uma inteligência artificial — e a melhor prova do produto é a própria conversa: a pessoa está falando com o LeadFlow neste momento e a conversa flui como com uma pessoa.

Por que não parece robô: o agente não trabalha com menu de opções nem com "digite 1 para vendas". Ele lê o que a pessoa escreveu, responde no contexto, aceita mudança de ideia no meio do caminho, entende "não posso de manhã" e "sexta é melhor" sem precisar de comando.

Quando o lead pergunta diretamente se é uma IA, a resposta é sempre a verdade. Mentir queima a confiança e o objetivo do agente é justamente construir confiança até a reunião.

O dono pode entrar na conversa a qualquer momento — quando ele responde pelo WhatsApp, o agente cala automaticamente e devolve o comando pra ele.
```

### 3. "E se ela errar com meu lead?"

```
/ia PERGUNTAS: e se errar, e se falar besteira, e se alucinar, e se inventar, tenho medo que fale errado com meu cliente, e se prometer o que não posso cumprir, e se marcar horário errado, e se atrapalhar minha venda, não confio em IA solta.

É a preocupação mais justa que existe e o sistema foi construído em cima dela.

O agente não improvisa o caminho: a sequência de perguntas até a reunião é travada em código, não fica a critério da IA. Ela escolhe as palavras; a ordem é fixa.

Horário o agente não inventa. Ele só oferece o que a agenda do cliente devolveu naquele instante — se um horário não está livre, ele não existe pra ele. Isso elimina o erro mais caro, que é marcar em cima de compromisso.

O que ele fala sobre o negócio vem do material que o próprio cliente entrega na implantação. Quando não tem base pra responder algo, ele leva pra reunião em vez de chutar.

E o dono tem o freio na mão: entrou na conversa pelo WhatsApp, o agente silencia sozinho. Existe também um botão de pausa. Toda conversa fica registrada no painel pra ler quando quiser.
```

### 4. Como funciona na prática

```
/ia PERGUNTAS: como funciona, como é que funciona, me explica como funciona, o que exatamente ele faz, como é o processo, como funciona na prática, o que acontece quando o lead chega, me explica antes da call, quero entender antes.

O caminho é este: o lead preenche o formulário do anúncio ou chama no WhatsApp. Em segundos o agente responde, confirma quem é a pessoa e qual é o problema dela, faz as perguntas de qualificação que o dono definiu, e — se a pessoa tem perfil — abre a agenda do dono, oferece horários que estão realmente livres e marca a reunião.

Depois de marcar, ele manda o link da reunião e lembra a pessoa antes da hora, que é o que derruba no-show.

Se o lead some no meio do caminho, o agente faz o follow-up sozinho, em intervalos configurados, até a pessoa responder ou dizer que não quer. Quem para de responder não fica esquecido.

Tudo isso acontece 24 horas por dia, inclusive sábado, domingo e madrugada. O dono acompanha por um painel onde vê cada conversa e o lead andando pelo funil.
```

### 5. Implantação — prazo e trabalho do cliente

```
/ia PERGUNTAS: quanto tempo demora pra implantar, demora pra ficar pronto, quando começa a funcionar, é difícil de configurar, eu vou ter que configurar, preciso mexer em alguma coisa, preciso entender de tecnologia, sou leigo, não sou técnico, o que eu preciso mandar.

O cliente não configura nada. Quem implanta é o time da LeadCase.

O cliente recebe um link e preenche um passo a passo pelo celular: dados do negócio, conexão do WhatsApp por QR Code, conexão da agenda com um clique, e o envio dos materiais que ele já tiver — apresentação, script de vendas, perguntas frequentes, áudio explicando o método, o que existir. Se ele não souber responder algo, marca "não sei" e o time resolve.

Não precisa saber nada de tecnologia. Não instala programa, não troca de celular, não mexe em código.

Com o material em mãos, o agente é configurado, testado com conversa real e só então entra no ar.
```

### 6. Número de WhatsApp e risco de banimento

```
/ia PERGUNTAS: usa meu número, preciso de outro número, posso usar meu whatsapp pessoal, meu número vai ser banido, whatsapp bloqueia, é seguro pro meu número, é whatsapp oficial, precisa de api oficial, vou perder meu whatsapp.

Funciona com um número de WhatsApp dedicado ao atendimento — o recomendado é não usar o número pessoal do dono, pela mesma razão que nenhuma empresa atende cliente no celular particular.

Sobre banimento: o risco existe para quem dispara mensagem em massa para quem não pediu. Não é o caso aqui. O agente responde quem chegou por vontade própria pelo formulário ou pelo anúncio, uma conversa por vez, com ritmo humano. É conversa iniciada pelo lead, que é exatamente o uso que o WhatsApp espera.

A conexão também roda com proteção de rede própria, o que evita os bloqueios por comportamento suspeito que acontecem quando várias contas saem do mesmo lugar.
```

### 7. "Já tenho equipe / secretária"

```
/ia PERGUNTAS: já tenho equipe, tenho secretária, tenho uma pessoa que responde, meu time já faz isso, tenho SDR, já tenho quem atende, vou demitir alguém, vai substituir minha equipe.

Não substitui — abastece. A pessoa que hoje responde passa a receber o lead já qualificado e com reunião marcada, em vez de gastar o dia perguntando o básico e correndo atrás de quem não tem perfil.

Na prática o time deixa de fazer a parte repetitiva (responder, qualificar, oferecer horário, lembrar da reunião, insistir com quem sumiu) e fica com a parte que só gente faz: conduzir a conversa de venda e fechar.

E resolve o que nenhuma equipe cobre sem custo alto: o lead que chega às 23h, no domingo, no feriado. Esse hoje espera até segunda — e boa parte não espera, procura outro.
```

### 8. "Já tenho chatbot / ManyChat / Typebot / n8n"

```
/ia PERGUNTAS: já tenho chatbot, uso manychat, uso typebot, já tenho automação, tenho n8n, tenho fluxo pronto, qual a diferença pro chatbot, já uso chatgpt no whatsapp, qual a diferença do chatgpt.

A diferença é entre fluxo e conversa. Chatbot de fluxo trabalha com árvore de decisão: se o lead sai do caminho previsto, ele quebra ou repete a pergunta. Todo mundo já conversou com um.

Um GPT solto tem o problema oposto: conversa bem, mas não tem trilho. Ele inventa horário, pula etapa da qualificação, promete o que não pode e não marca nada na agenda de verdade.

O LeadFlow junta os dois: a conversa é livre e natural, mas a sequência até a reunião é travada em código, e o agendamento é integrado à agenda real. Ele não é um chat que fala bonito — é um que marca reunião e alimenta o funil.

Fora isso vem pronto de fábrica o que ninguém monta sozinho sem sofrer: follow-up de quem sumiu, lembrete de reunião, controle de no-show e painel de acompanhamento.
```

### 9. Agenda e reunião

```
/ia PERGUNTAS: usa minha agenda, integra com google agenda, agenda no meu calendário, e se eu já tiver compromisso, vai marcar em cima de outra coisa, marca no zoom, manda link do meet, como o lead recebe o link, posso escolher meus horários.

O agente lê a agenda do Google do dono em tempo real e só oferece horário que está realmente livre. Compromisso já marcado bloqueia o horário — ele não enxerga como disponível.

O dono define a janela de atendimento: dias da semana, horário de início e fim, duração da reunião e intervalo entre elas. O agente respeita isso.

Marcou, o evento entra na agenda e o link da reunião vai pro lead pelo WhatsApp, com Google Meet ou Zoom conforme a preferência do cliente.

Se o lead precisar remarcar, é só dizer no WhatsApp: o agente abre a agenda de novo, oferece outros horários e atualiza o compromisso.
```

### 10. Lembrete, no-show e follow-up

```
/ia PERGUNTAS: e o no show, o cliente marca e não aparece, como reduz falta, manda lembrete, e se o lead sumir, faz follow up, cobra o lead, quantas vezes insiste, e quem não responde.

São os dois vazamentos que ninguém tapa no braço.

No-show: o agente lembra o lead antes da reunião, com antecedência configurável. Lembrete perto da hora é o que mais recupera presença, porque a maioria não falta por desinteresse — falta porque esqueceu.

Sumiço: quando o lead para de responder no meio da conversa, o agente retoma sozinho depois de um tempo, com uma sequência de mensagens definida pelo dono. O tom é leve, sem cobrança, e cada tentativa traz um ângulo novo. Se a pessoa responde, a conversa continua de onde parou. Se diz que não quer, ele para e não incomoda mais.

Quem já marcou reunião não recebe follow-up de prospecção — o sistema separa as duas coisas.
```

### 11. Nicho e tipo de negócio

```
/ia PERGUNTAS: funciona no meu nicho, serve pro meu negócio, funciona pra clínica, pra imobiliária, pra advogado, pra estética, pra academia, pra infoproduto, pra mentoria, meu caso é diferente, funciona pra quem vende serviço.

Funciona para qualquer negócio em que o lead chega por formulário, anúncio ou indicação e o próximo passo é uma conversa marcada — mentoria, consultoria, clínica, estética, odontologia, imobiliária, advocacia, agência.

O que muda de um para outro é o texto: as perguntas de qualificação, o jeito de falar e as objeções do setor. Isso é configurado na implantação com o material do cliente. A mecânica de responder na hora, qualificar, marcar e lembrar é a mesma.

Onde encaixa pior: negócio sem volume de lead ou que vende por balcão, sem reunião no meio do caminho. Nesses casos é melhor dizer com honestidade que não é o momento do que empurrar.
```

### 12. Cancelamento, contrato e suporte

```
/ia PERGUNTAS: tem fidelidade, tem contrato, tem multa, posso cancelar, e se eu não gostar, tem garantia, e se não funcionar pra mim, quem me atende depois, tem suporte, e se der problema.

Sem fidelidade e sem multa. A assinatura é mensal e o cliente cancela quando quiser.

Depois de no ar, o cliente fala direto com o time da LeadCase pelo WhatsApp. Ajuste de texto, mudança de horário de atendimento, troca das perguntas de qualificação: é pedir e ser feito.

O agente também aprende depois de ligado. Quando aparece uma pergunta nova que ele não sabia responder, o dono manda a informação e ela passa a fazer parte do repertório dele — sem precisar refazer nada.
```

### 13. Dados e LGPD

```
/ia PERGUNTAS: e a lgpd, meus dados estão seguros, os dados dos meus leads, quem tem acesso, vocês vendem meus dados, onde ficam as conversas, é seguro.

Os dados dos leads são do cliente. Cada empresa fica isolada no sistema — uma nunca enxerga a base da outra.

As conversas ficam registradas para o dono ler no painel e acompanhar o atendimento. Nada é vendido, compartilhado ou usado para outro fim.

Quem opera é o próprio dono e quem ele autorizar. O acesso do time da LeadCase existe para dar suporte e é ele quem pede.
```

### 14. Volume e limites

```
/ia PERGUNTAS: quantos leads aguenta, tem limite de mensagem, tem limite de conversa, e se vier muito lead, aguenta pico, quantas conversas ao mesmo tempo, e se meu anúncio estourar.

O agente atende todas as conversas ao mesmo tempo — ele não tem fila. Se cem leads chegam no mesmo minuto porque um anúncio estourou, os cem são respondidos em segundos. É a diferença mais concreta em relação a atendimento humano, que atende um por vez.

Não há limite de mensagens no plano.

O gargalo passa a ser a agenda do dono, não o atendimento. Que é exatamente o problema que se quer ter.
```

### 15. "Preciso pensar / falar com meu sócio"

```
/ia PERGUNTAS: preciso pensar, vou pensar, deixa eu ver, preciso falar com meu sócio, com minha esposa, com meu marido, com minha equipe, depois te falo, vou analisar, me manda material.

Pensar faz todo sentido e não é hora de empurrar.

A conversa de 30 minutos é sem compromisso e serve justamente pra isso: em vez de decidir com base em texto de WhatsApp, a pessoa vê o sistema rodando, faz as perguntas dela e sai com o que precisa pra decidir — sozinha ou com o sócio. O sócio pode inclusive participar da conversa.

Material solto por WhatsApp costuma virar mensagem não lida. Trinta minutos vendo funcionando resolve mais.
```

---

## Perguntas de teste — rode depois de indexar

Use `GET /admin/rag/testar` (ou mande pelo WhatsApp de um número de teste) e confirme
que **volta o chunk certo**, não um vizinho:

| Pergunta do lead | Deve puxar |
|---|---|
| "quanto é?" | 1 — Preço |
| "isso aí é um robô né" | 2 — É robô |
| "e se ela falar besteira com meu cliente?" | 3 — E se errar |
| "me explica antes da call como funciona" | 4 — Como funciona |
| "demora pra ficar pronto?" | 5 — Implantação |
| "meu número pode ser banido?" | 6 — Número/banimento |
| "já tenho uma menina que responde" | 7 — Já tenho equipe |
| "qual a diferença pro chatgpt?" | 8 — Chatbot/GPT |
| "marca no meu google agenda?" | 9 — Agenda |
| "tem fidelidade?" | 12 — Cancelamento |

Qualquer uma que voltar `SEM MATCH` ou o chunk errado: reescreva a linha `PERGUNTAS:`
daquele bloco com as palavras que o lead realmente usou e reindexe.

> Regra ao alimentar isto no futuro: **nada de número inventado.** Sem "aumenta 300% as
> reuniões" e sem "mais de X clientes". Quando tiver o número real da Rejane, entra aqui
> como bloco novo com a fonte — aí vira a peça mais forte da base.
