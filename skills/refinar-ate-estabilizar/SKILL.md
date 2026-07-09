---
name: refinar-ate-estabilizar
description: Loop de autoavaliação e reescrita. Use quando o usuário pedir para "refinar até parar de melhorar", "avalie seu próprio trabalho", "dá uma nota de 0 a 100", "reescreve até ficar bom", "itera até estabilizar", ou executar /refinar. Aplica-se a textos, mensagens, documentos, código, planilhas e qualquer entrega — Claude cria uma rubrica, se pontua de 0 a 100, lista os pontos fracos, reescreve corrigindo-os e repete até a nota parar de subir, apresentando no fim a melhor versão e a trajetória da pontuação.
---

# Refinar até estabilizar

Depois de produzir a entrega, não pare na primeira versão. Rode um ciclo de autoavaliação honesta e reescrita, repetindo até a qualidade parar de melhorar de forma significativa.

## Passo 0 — Definir a rubrica ANTES de avaliar

Antes de dar qualquer nota, escreva uma **rubrica clara** adequada ao tipo de entrega. Use de 4 a 6 critérios, cada um com um peso, somando 100. A rubrica deve ser específica ao pedido — não genérica.

Exemplos de critérios (adapte ao caso):
- Texto/mensagem: clareza, concisão, tom adequado ao público, correção factual, força do gancho/chamada.
- Código: corretude, legibilidade, tratamento de erros, desempenho, testes/verificação.
- Documento/relatório: precisão dos dados, estrutura, completude, objetividade, formatação.

Mostre a rubrica (critérios + pesos) logo no começo, para a avaliação ser auditável.

## Passo 1 — Autoavaliar de 0 a 100

Pontue a versão atual em cada critério da rubrica e some a nota total (0–100). Seja rigoroso e honesto: a nota serve para expor fraquezas, não para se elogiar. Evite inflar.

## Passo 2 — Listar os pontos mais fracos

Liste os critérios com menor pontuação e **explique por que cada um perdeu pontos** — de forma concreta, apontando o trecho/aspecto específico que falhou. Priorize os 2–4 problemas que mais derrubam a nota.

## Passo 3 — Reescrever corrigindo os pontos fracos

Reescreva a entrega corrigindo os principais pontos fracos identificados, **mantendo intactos os aspectos que já pontuaram bem** (não regrida no que estava funcionando). A reescrita deve mirar diretamente nos itens do Passo 2.

## Passo 4 — Repetir até estabilizar

Volte ao Passo 1 com a nova versão. Repita o ciclo (avaliar → apontar fraquezas → reescrever) **até a nota parar de melhorar de forma significativa** — como regra prática, pare quando o ganho de uma iteração for menor que ~2 pontos, ou após no máximo 5 iterações (o que vier primeiro). Não fique em loop infinito nem reescreva por reescrever.

## Passo 5 — Apresentar o resultado

No fim, entregue:
1. **A melhor versão** (a de maior nota), destacada e pronta para uso.
2. **A trajetória da pontuação** — a nota de cada iteração, ex.: `v1: 72 → v2: 85 → v3: 91 → v4: 92 (estabilizou)`.
3. Uma linha curta sobre o que mudou entre as versões e por que a nota subiu.

## Regras

- A rubrica vem antes da primeira nota — nunca pontue sem critérios explícitos.
- Notas honestas: se está mediano, dê nota de mediano. A utilidade do loop depende disso.
- Nunca descarte o que já estava bom ao reescrever.
- Pare quando estabilizar; relate a trajetória mesmo que tenha bastado uma iteração.
- Mostre o raciocínio de forma enxuta — o valor está na melhor versão final, não em textão de processo.
