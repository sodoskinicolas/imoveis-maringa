# 30 perguntas de histórico de preços — e como a base responde

Projeto PW (imóveis de Maringá-PR). Cada pergunta abaixo é do dia a dia de corretor/imobiliária. Ao lado, a tabela/coluna que responde e, quando os dados já permitem, um número real (base de 08/07/2026: 733 edifícios verticais com métricas, 403 bairros, ~19 mil anúncios, histórico começando em 30/06/2026).

> **Tabelas criadas para isso:** `preco_historico` (série por anúncio) · `preco_historico_vertical` (série agregada por edifício) · `metricas_precos_vertical` (foto atual + variações + padrão por edifício) · `metricas_bairro` (por bairro) · `RESUMO_precos.json` (mercado).

## Bloco 1 — Preço atual e de referência

1. **Qual o preço médio e mediano deste edifício hoje?** → `metricas_precos_vertical.preco_medio / preco_mediano`. A mediana é a referência boa (ignora outliers). Ex.: Edifício Central (Centro) mediana R$ 895 mil.
2. **Qual o preço do m² deste edifício?** → `preco_m2_medio`. Ex.: prédios de alto padrão ~R$ 10.533/m², médio ~R$ 6.444, baixo ~R$ 4.132.
3. **Qual a faixa de preço praticada (mín–máx)?** → `preco_min / preco_max`.
4. **Este apartamento está caro ou barato para o prédio?** → compara o preço do anúncio com `preco_mediano` do edifício. Acima da mediana = pedindo mais que o padrão do prédio.
5. **Este apartamento está caro ou barato para o bairro?** → `preco_m2` do anúncio vs `metricas_bairro.preco_m2_medio`. Ex.: Centro R$ 9.997/m², Zona 03 R$ 10.082, Jd. Aclimação R$ 9.968.
6. **Um preço pedido está dentro do mercado?** (validador de precificação) → cruza m² do imóvel com a faixa `preco_m2_min–max` do bairro + mediana do edifício. Fora da faixa = revisar.

## Bloco 2 — Evolução no tempo (o "histórico" de fato)

7. **Como evoluiu o preço médio do m² deste edifício?** → série em `preco_historico_vertical` (uma linha por edifício por data).
8. **Quanto o prédio variou em 7 / 30 / 90 dias?** → `var_7d_pct / var_30d_pct / var_90d_pct`. *(hoje só 7 dias têm série; 30/90 preenchem conforme a coleta diária roda.)*
9. **O prédio está subindo, estável ou caindo?** → `tendencia` (subindo/estavel/caindo).
10. **Qual o histórico completo de um anúncio específico?** → `preco_historico WHERE imovel_id = ?` (toda mudança de preço, com data).
11. **Quanto (%) um imóvel baixou desde que foi anunciado?** → primeiro vs último preço em `preco_historico` do anúncio. Ex. real: um imóvel caiu de R$ 280 mil (30/06) para R$ 268 mil (02/07).
12. **Que % dos imóveis do edifício já baixaram de preço?** → `pct_baixaram`. Alto = mais poder de negociação para o comprador.
13. **Qual a maior queda registrada (R$ e %) e onde?** → ordenar variações de `preco_historico` / `metricas_precos_vertical.var_30d_pct`.
14. **Há variação sazonal ao longo do ano?** → agregação mensal de `preco_historico_vertical` (disponível após ~12 meses de coleta).

## Bloco 3 — Estoque, liquidez e giro

15. **Quantos imóveis estão à venda hoje neste edifício?** → `n_ativos`. Ex.: Edifício Central 150 anúncios ativos.
16. **O estoque está subindo ou caindo?** (mais oferta pressiona preço p/ baixo) → contagem de ativos por data.
17. **Quais imóveis saíram do mercado (venderam/retiraram)?** → `imoveis.status = 'Removido'` e `n_removidos` por edifício.
18. **Quais edifícios têm maior giro?** → ranking por `n_removidos` (proxy de liquidez). Hoje 6 prédios já registram saídas — cresce com a coleta.
19. **Qual o tempo médio de mercado (dias anunciado)?** → `data_captura` vs data de remoção/venda. *(depende de acumular datas de saída.)*

## Bloco 4 — Segmentação e comparáveis

20. **Qual o preço médio por nº de quartos (1/2/3/4)?** → agrupar `imoveis` por `quartos`.
21. **Qual o preço por tipo (apartamento, cobertura, studio)?** → agrupar por `tipo`.
22. **Quanto vale um apê de X m² e Y quartos neste prédio?** (avaliação por comparáveis) → mediana dos anúncios do edifício com mesmo perfil × área.
23. **Qual o preço/m² por zona/região (ranking)?** → `metricas_bairro` ordenado por `preco_m2_medio`.
24. **Qual o ticket médio de venda no bairro?** → `metricas_bairro.preco_medio`.
25. **Prédio com lazer completo vale mais por m²?** → sim: com lazer completo (≥4 itens) ~R$ 8.619/m² vs ~R$ 6.427/m² sem lazer. Fonte: `lazer_completo` × `preco_m2_medio`.

## Bloco 5 — Padrão construtivo (alto / médio / baixo)

26. **A base classifica alto/médio/baixo padrão?** → sim: `metricas_precos_vertical.padrao` + `padrao_fonte`. Distribuição atual: 237 alto, 241 médio, 237 baixo. Ver seção "Padrão" abaixo.
27. **Essa classificação vem do cadastro ou do preço?** → `padrao_fonte`: `cadastro` quando o padrão está declarado na tabela `condominios` (29 prédios hoje, ex.: Atmosphere, Vision = "Alto Padrão"); senão `preco_m2` (tercis de mercado).
28. **Qual a diferença de preço/m² entre padrões?** → alto ~R$ 10.533, médio ~R$ 6.444, baixo ~R$ 4.132 por m².

## Bloco 6 — Oportunidades e riscos

29. **Onde estão as melhores oportunidades hoje?** → anúncios com m² abaixo da mediana do edifício **e** que baixaram recentemente (`pct_baixaram` alto + `var` negativa). Reunido no `RESUMO_precos.json` (`edificios_mais_baixaram`, `edificios_maior_queda_30d`).
30. **Como não ser enganado por lançamento/"direitos" com preço baixo?** → esses anúncios (cessão de direitos, entrada de lançamento na planta) não são o valor da unidade pronta e derrubam a média. O motor **descarta automaticamente** anúncios com m² abaixo de 50% da mediana do próprio edifício (`n_suspeitos_direitos`; 642 anúncios filtrados até agora) antes de calcular qualquer estatística.

---

## Sobre padrão construtivo — o que a documentação já tem

A pergunta "a documentação tem algo sobre padrão?" tem **duas fontes**:

1. **Cadastro da prefeitura (GeoMaringá / espelho do IPTU):** cada lote traz o campo **"Padrão"** dentro de `InformacoesTerreno` (junto de Situação, Topográfica, Ocupação, Ano). É o padrão construtivo oficial usado na avaliação venal — a skill `busca-completa-imovel` já lê esse campo. Ainda não está extraído em massa para todos os edifícios; quando estiver, vira a fonte mais confiável de `padrao`.
2. **Tabela `condominios` (coluna `padrao`):** já preenchida para ~78 empreendimentos (ex.: "Alto Padrão", "Médio Padrão", "Luxo"), vindos da coleta de lançamentos/construtoras.

Enquanto o padrão de cadastro não é extraído para todos, o motor usa a regra: **`cadastro` (quando declarado) → senão tercis de R$/m² do mercado**. Isso dá uma classificação para os 733 edifícios hoje e melhora sozinha à medida que o padrão oficial for coletado.

## Limitações honestas (por que alguns números ainda são parciais)

- **Histórico curto:** a coleta começou em 30/06/2026, então variações de 30/90 dias e sazonalidade ainda estão se formando. A infraestrutura já grava tudo — é questão de deixar rodar.
- **Casamento anúncio↔edifício por nome:** ~52% dos anúncios com edifício preenchido casam com um vertical do cadastro. O resto fica de fora das métricas por prédio (mas entra nas de bairro). Dá para subir isso com um índice de sinônimos.
- **Locação/yield:** só 20 anúncios de locação hoje — análise de rentabilidade fica pendente de mais dados.
