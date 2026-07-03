---
name: review
description: Compara a build atual com a especificação em specs/nome.md, requisito por requisito, e lista todas as lacunas, bugs e itens faltantes — apontando o item exato da spec em que cada um falha. Escreve as correções específicas para /build implementar. Só aprova a build quando TODOS os requisitos da spec forem totalmente atendidos. Use quando o usuário executar /review ou pedir para "revisar contra a spec", "verificar a build", "conferir a especificação".
---

# review — Verifica a build contra a especificação, requisito por requisito

Seu papel aqui é ser um **revisor rigoroso e imparcial**. A spec é o critério de verdade. Não corrija o código você mesmo — sua saída é um **veredito e uma lista de correções** para o `/build` implementar.

## Fase 1 — Carregar a especificação e a build

1. Localize a spec em `specs/`. Se o usuário indicou um nome (`/review upload-comprovantes`), use `specs/<nome>.md`. Se não indicou:
   - Se houver **uma** spec, use ela.
   - Se houver **várias**, liste-as e pergunte qual revisar. **Não escolha por conta própria.**
   - Se não existir spec, avise que não há critério de revisão e pare.
2. Leia a spec inteira, focando em **Requisitos**, **Casos extremos a tratar** e **Definição de "concluído"**.
3. Inspecione a build real — o código e os arquivos que a implementam. Se existir um relatório de build (saída do `/build`), use-o como ponto de partida, mas **verifique você mesmo**: não confie na afirmação de conformidade sem conferir no código. Um requisito marcado como atendido no relatório mas ausente no código é uma **lacuna**.

## Fase 2 — Análise requisito por requisito

Percorra **cada requisito numerado da spec, um a um** (R1, R2, ...). Para cada um, determine o status verificando o código de verdade:

- **PASSA** — totalmente atendido, com evidência no código.
- **FALHA** — não atendido, atendido parcialmente, ou com bug. Toda falha deve apontar **o item exato da spec** (o número/texto do requisito, caso extremo ou item da definição de concluído) onde ocorre.

Depois dos requisitos, faça o mesmo com:

- Cada **caso extremo** listado na spec — foi tratado com o comportamento definido?
- Cada item da **Definição de "concluído"** — é verificável e está satisfeito?

Também sinalize **bugs** que quebram um requisito mesmo que o requisito pareça "implementado" (ex.: existe mas falha com entrada válida). E sinalize **escopo extra**: funcionalidade construída que a spec não pediu — reporte como observação (não é motivo isolado para reprovar, mas o usuário deve saber).

Não invente requisitos que não estão na spec. Revise **apenas** contra o que a spec define.

## Fase 3 — Veredito e correções

Produza o relatório neste formato:

```markdown
## Revisão — <nome da spec>

### Veredito: APROVADA ✅  /  REPROVADA ❌

### Requisitos
- **R1** — <texto>: PASSA — evidência: `arquivo:linha` ...
- **R2** — <texto>: FALHA — <o que está errado> (falha no item **R2** da spec). Local: `arquivo:linha`.
- ...

### Casos extremos
- <caso da spec>: PASSA / FALHA — ...

### Definição de "concluído"
- [x] <item> — verificado
- [ ] <item> — não atendido: ...

### Lacunas, bugs e itens faltantes
Lista de tudo que reprovou, cada um amarrado ao item exato da spec:
1. [R2] <descrição precisa da lacuna/bug/faltante> — em `arquivo:linha`.
2. [Caso extremo: rede offline] <...>.

### Correções necessárias (para o /build implementar)
Instruções específicas e acionáveis, uma por lacuna, referenciando o item da spec:
1. **[R2]** <o que exatamente mudar>, em `arquivo`. Comportamento esperado: <...>. Como verificar depois: <...>.
2. **[Caso extremo: rede offline]** <...>.

### Escopo extra (observação)
- <funcionalidade não pedida pela spec, se houver>
```

## Regras de aprovação (rígidas)

- A build **só é APROVADA quando TODOS os requisitos, TODOS os casos extremos e TODA a definição de "concluído" passarem**. Uma única falha ⇒ **REPROVADA**.
- Não aprove com ressalvas, não aprove "quase lá", não aprove com pendências. Se falta algo, é REPROVADA e a lista de correções tem que estar completa.
- **Seja específico:** cada lacuna aponta o item exato da spec e o local no código; cada correção é acionável o suficiente para o `/build` implementar sem adivinhar.
- Não conserte o código nesta skill — sua entrega é o veredito + as correções. O ciclo é: `/build` implementa as correções → `/review` roda de novo → repete até APROVADA.
