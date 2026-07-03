---
name: build
description: Lê uma especificação em specs/nome.md e constrói exatamente o que ela descreve — nada além disso. Não adiciona funcionalidades, não refatora código irrelevante e não inventa requisitos. Ao terminar, lista quais requisitos da spec foram atendidos para a etapa de revisão verificar. Use quando o usuário executar /build ou pedir para "construir a spec", "implementar a especificação".
---

# build — Constrói exatamente o que a especificação descreve

Seu papel aqui é **implementar fielmente uma especificação existente**. A spec é o contrato: não faça mais, não faça menos, não faça diferente.

## Fase 1 — Carregar a especificação

1. Procure a spec em `specs/`. Se o usuário indicou um nome (`/build upload-comprovantes`), use `specs/<nome>.md`. Se não indicou:
   - Se houver **uma** spec em `specs/`, use ela.
   - Se houver **várias**, liste-as e pergunte qual construir. **Não escolha por conta própria.**
   - Se `specs/` não existir ou estiver vazia, avise que não há especificação e sugira rodar `/spec` primeiro. **Não invente uma spec.**
2. Leia a spec inteira antes de escrever qualquer código. Preste atenção especial às seções **Requisitos**, **Casos extremos a tratar** e **Definição de "concluído"**.
3. Se algum requisito estiver ambíguo ou contraditório, ou se houver itens em **Perguntas em aberto** que bloqueiam a construção, **pergunte ao usuário antes de implementar** — não preencha a lacuna com suposições.

## Fase 2 — Construir (com disciplina de escopo)

Implemente exatamente o que a spec descreve. Regras rígidas:

1. **Não adicione funcionalidades** que não estão na spec — nem "melhorias óbvias", nem extras "que seriam legais", nem tratamento de casos não listados.
2. **Não refatore código irrelevante.** Toque apenas no que é necessário para atender aos requisitos. Não reformate, não renomeie e não reorganize arquivos que não fazem parte do escopo.
3. **Não invente requisitos.** Se não está na spec, não é para construir. Se você acha que algo importante está faltando, **anote e pergunte** em vez de implementar por conta própria.
4. **Respeite as restrições da spec** — tecnologias obrigatórias/proibidas, ambiente, limites. Não troque de biblioteca ou abordagem por preferência pessoal.
5. **Trate exatamente os casos extremos listados** na spec, com o comportamento que ela define — nem mais, nem menos.
6. Siga as convenções já existentes no código (estilo, estrutura de pastas, padrões). Construa como se fosse parte natural do projeto.

Se durante a construção você perceber que um requisito é inviável como escrito, **pare e avise o usuário** com o motivo, em vez de improvisar uma solução alternativa fora da spec.

## Fase 3 — Relatório de conformidade para a revisão

Ao concluir, produza um relatório mapeando cada requisito da spec ao que foi feito, para que a etapa de revisão (`/review`, se existir) possa verificar. Use este formato:

```markdown
## Relatório de build — <nome da spec>

### Requisitos atendidos
- **R1** — <texto do requisito>: atendido em `caminho/arquivo.ext` (função/trecho). Como verificar: ...
- **R2** — ...: atendido em ...

### Casos extremos tratados
- <caso da spec>: comportamento implementado em `arquivo` — ...

### Definição de "concluído"
- [x] <item do checklist da spec> — evidência: ...
- [ ] <item não concluído, se houver> — motivo: ...

### Fora do escopo (intencionalmente NÃO feito)
- <qualquer coisa que a spec não pediu e que você deliberadamente não fez, se relevante>

### Desvios ou pendências
- <qualquer requisito que não deu para atender exatamente como escrito, com o motivo — ou "nenhum">
```

Regras do relatório:

- **Liste todos os requisitos numerados da spec**, um a um. Não agrupe nem pule nenhum.
- Para cada um, aponte **onde** foi atendido (arquivo e trecho) e **como verificar**.
- Seja honesto: se um item não foi concluído, marque como não concluído e explique. Não afirme conformidade que não existe.
- Não marque a "Definição de concluído" como completa se algum item do checklist não passou.
