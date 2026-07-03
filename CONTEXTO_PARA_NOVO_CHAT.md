# Contexto do Projeto PW — Imóveis Maringá

Sou Nicolas Sodoski, corretor em Maringá-PR. Tenho um projeto em `~/Claude/Projects/PW` que é uma plataforma de imóveis com:
- **Bot WhatsApp** (Baileys/Node.js) capturando imóveis de grupos de corretores
- **Scrapers** de imobiliárias locais (Haraki, Massaru, Bellakaza, Silvio Iwata, Casa do Corretor, Lélo, Patrimônio, Opção, portal sub100.com.br com ~14k imóveis)
- **IA** (Claude Haiku) classifica venda vs demanda, extrai dados de imagens/links
- **Banco SQLite** (`imoveis.db`) — tabelas: `imoveis`, `demandas`, `condominios` (13.789 registros, coluna `plantas` para multi-planta)
- **Site estático** (`Imoveis.html` → GitHub Pages em sodoskinicolas.github.io/imoveis-maringa)
- **Automação** via LaunchAgents: processar+push a cada 30min, verificador de erros a cada 1h, scraping via GitHub Actions às 3h

## Estado atual do banco (2026-07-03)
- 3.674 imóveis (855 WhatsApp, 2.819 scraping), 2.733 com status "Novo"
- 29 demandas ativas
- 13.789 condomínios (91 com specs completos, 1 com multi-planta: NEST635)

## O que foi implementado recentemente (esta sessão)

### Multi-planta em edifícios (`condominios.plantas`)
Coluna `plantas` (JSON array) na tabela `condominios`. Cada objeto: `{area, quartos, suites, vagas, descricao, tipo}`.
`trim_specs_condo(row, area)` seleciona a planta mais próxima (±25%) em vez de specs genéricas.
**NEST635** cadastrado: Zona 08, PRC Empreendimentos, 25 andares, 2 plantas (119m²/2suítes e 105m²/1suíte).

### Normalização de nome em `buscar_specs_condo` (`db.py`)
`_norm_nome(s)` → strip tudo não-alfanumérico, lowercase.
"NEST635" agora casa com "NEST 635 VERTICAL HOUSES" no banco.

### Match de imóveis melhorado (`gerar_site.py`)
- Edifício é **critério de score**, não filtro rígido — imóveis de outros edifícios com config similar aparecem no "Near Match"
- Tipo 'Imóvel' nas demandas é wildcard (não filtra por tipo)
- Ordenação: mesmo edifício primeiro → score desc → menor preço
- `_normEdif(s)` em JS para comparação normalizada de nome de edifício

### Fix crítico JS (site estava completamente quebrado)
`\'` dentro de f-string Python gera `'` no output (não `\'`). Os onclick da Aba Bairros geravam JS inválido.
**Fix:** 3 ocorrências substituídas por `data-bairro`/`data-edif` + `this.dataset`.

### `verificar_corrigir.py` — check ⑦ melhorado
Passa `area=area_min` para `buscar_specs_condo` (seleciona planta certa).
Check ⑦b: corrige `tipo_buscado` de 'Imóvel' para tipo específico da planta.

### `gerar_fluxograma.py` atualizado
Todos os recursos atuais documentados, sem referências a "hoje". Novo nó `verificar_corrigir.py` na lane de manutenção.

## Pendências que o Nicolas ainda precisa rodar no Mac

```bash
cd ~/Claude/Projects/PW
rm -f .git/HEAD.lock .git/index.lock    # se houver lock travado
python3 verificar_corrigir.py           # preenche specs das demandas (incl. NEST635)
python3 gerar_site.py                   # regera site com fix JS + match melhorado
git add gerar_site.py Fluxograma_Sistema.html gerar_fluxograma.py db.py processar_mensagens.py verificar_corrigir.py
git commit -m "site: fix JS onclick + match config similar + multi-planta + fluxograma"
git push

# Instalar LaunchAgent do verificador (se ainda não feito):
cp ~/Claude/Projects/PW/com.imoveis.verificador-erros.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.imoveis.verificador-erros.plist

# Re-scrape Silvio Iwata (só 27 no banco vs 454 coletados):
python3 raspar_imoveis.py   # sem --dry-run
```

## Arquivos principais
- `db.py` — schema, helpers, `buscar_specs_condo`, `_norm_nome`, `trim_specs_condo`, cache de condominios
- `processar_mensagens.py` — pipeline WhatsApp (classifica, extrai, valida, grava)
- `raspar_imoveis.py` — scrapers de todos os sites + portal sub100
- `gerar_site.py` — gera `Imoveis.html` (site completo em JS puro)
- `verificar_corrigir.py` — quality gate automático horário (7+ checks)
- `gerar_fluxograma.py` — gera `Fluxograma_Sistema.html` (painel visual da arquitetura)
- `auditar_historico.py` — reprocessamento retroativo manual (`--dry-run`/`--apply`)
- `arquivar_demanda.py` — CLI pra arquivar/restaurar demandas

## Pegadinhas do ambiente
- Git lock: se `git commit` falhar, rodar `rm -f .git/HEAD.lock .git/index.lock` no Mac
- `.command` sem permissão: `chmod +x arquivo.command` antes de usar
- `gerar_site.py` é lento no sandbox (~40s) mas rápido no Mac (~5s)
- API key da app (em `.env`) está sem créditos — busca web de bairro via Claude está desabilitada temporariamente
- `ProcessPoolExecutor` (não Thread) para scraping paralelo — HTML parsing é CPU-bound, GIL bloqueia threads
