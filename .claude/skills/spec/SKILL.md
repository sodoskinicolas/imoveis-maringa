---
name: spec
description: Entrevista o usuário sobre um recurso ou aplicativo que ele quer construir, uma pergunta específica por vez, até entender completamente objetivo, requisitos, restrições e definição de "concluído". Só então escreve uma especificação detalhada em specs/nome.md. NÃO começa a construir. Use quando o usuário executar /spec ou pedir para "especificar", "escrever uma spec", "planejar um recurso antes de construir".
---

# spec — Entrevista e escreve a especificação de um recurso

Seu papel aqui é **descobrir e documentar**, não construir. Não escreva código, não crie arquivos além da spec final, não proponha implementação até a especificação estar pronta e o usuário concordar.

## Fase 1 — Entrevista (uma pergunta por vez)

Conduza uma entrevista para entender completamente o que o usuário quer. Regras:

1. **Faça UMA pergunta específica por vez.** Nunca despeje uma lista de perguntas. Espere a resposta antes da próxima.
2. **Cada pergunta deve ser concreta**, baseada no que o usuário já disse. Nada de perguntas genéricas ("quais são seus requisitos?"). Prefira perguntas fechadas ou com exemplos ("O upload aceita só PDF, ou também imagens? E qual o tamanho máximo por arquivo?").
3. **Vá do amplo para o detalhe.** Comece pelo objetivo e pelo problema real que ele resolve; depois entre em requisitos, fluxos, dados, integrações e restrições.
4. **Não comece a construir.** Se o usuário pedir para já implementar, lembre gentilmente que primeiro você fecha a spec — leva poucos minutos e evita retrabalho.

Continue perguntando até ter clareza sobre **todos** estes pontos:

- **Objetivo**: qual problema isto resolve, para quem, e por que agora.
- **Requisitos indispensáveis** (must-have) vs. o que fica de fora (out of scope).
- **Fluxo principal**: passo a passo do caminho feliz, do início ao resultado.
- **Dados e integrações**: o que entra, o que sai, onde é armazenado, quais sistemas/APIs externos.
- **Restrições**: tecnologia obrigatória ou proibida, prazo, orçamento, ambiente, limitações de plataforma.
- **Casos extremos e erros**: entradas inválidas, estados vazios, falhas de rede, concorrência, permissões, limites.
- **Definição de "concluído"**: como alguém verifica objetivamente que ficou pronto e correto.

Quando achar que já tem o suficiente, **faça um resumo curto do que entendeu e pergunte se está completo ou se falta algo** antes de escrever a spec.

## Fase 2 — Escrever a especificação

Depois que o usuário confirmar, escreva uma especificação clara e detalhada e salve em `specs/<nome>.md` (use um slug curto em kebab-case para `<nome>`, derivado do recurso — ex.: `specs/upload-comprovantes.md`). Crie a pasta `specs/` se não existir.

A spec deve ter esta estrutura:

```markdown
# <Nome do recurso>

## Objetivo
Qual problema resolve, para quem, e o resultado esperado. 2–4 frases.

## Escopo
### Incluído
- ...
### Fora do escopo
- ...

## Requisitos
Requisitos exatos e numerados (R1, R2, ...), cada um verificável e sem ambiguidade.

## Fluxo principal
Passo a passo do caminho feliz.

## Dados e integrações
Entradas, saídas, armazenamento, APIs/sistemas externos, formatos.

## Restrições
Tecnológicas, de prazo, de ambiente, de plataforma.

## Casos extremos a tratar
Lista concreta de cada caso e o comportamento esperado (entrada inválida, estado vazio, falha de rede, permissão negada, limites, concorrência).

## Definição de "concluído"
Checklist concreto e verificável. Cada item deve ser algo que outra pessoa consiga testar e marcar como feito. Inclua critérios de aceitação por requisito quando fizer sentido.

## Perguntas em aberto
Qualquer coisa ainda não decidida (deixe vazio se não houver).
```

Regras de qualidade da spec:

- **Seja específico e testável.** Troque "deve ser rápido" por "carrega em até 2s com 1.000 registros". Troque "tratar erros" por o comportamento exato de cada erro.
- **Não invente requisitos** que o usuário não confirmou. Se algo ficou incerto, coloque em "Perguntas em aberto" em vez de assumir.
- **A definição de concluído tem que permitir verificação objetiva** — alguém que não participou da conversa deve conseguir olhar a construção e dizer "sim, atende" ou "não atende".

Ao terminar, informe o caminho do arquivo salvo e pergunte se quer ajustar algo. **Ainda não construa** — a menos que o usuário peça explicitamente na sequência.
