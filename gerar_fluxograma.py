#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerar_fluxograma.py
Gera um arquivo HTML local, autocontido e interativo, com um fluxograma
resumido de todo o sistema (site + bots + banco). Clicar em qualquer etapa
mostra a lógica detalhada dela. Os números (imóveis, demandas, condomínios)
são lidos do imoveis.db no momento da geração.

Uso:
    python3 gerar_fluxograma.py

Rode de novo sempre que quiser atualizar os números e o conteúdo. O arquivo
gerado (Fluxograma_Sistema.html) pode ser aberto direto no navegador,
localmente, sem precisar de servidor nem internet.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
DB_PATH  = BASE_DIR / "imoveis.db"
OUT_PATH = BASE_DIR / "Fluxograma_Sistema.html"


def coletar_stats():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ni = conn.execute("SELECT COUNT(*) FROM imoveis").fetchone()[0]
    ni_wa = conn.execute(
        "SELECT COUNT(*) FROM imoveis WHERE corretor IS NOT NULL AND corretor != ''"
    ).fetchone()[0]
    ni_scrape = ni - ni_wa
    nd = conn.execute("SELECT COUNT(*) FROM demandas").fetchone()[0]
    nc = conn.execute("SELECT COUNT(*) FROM condominios").fetchone()[0]
    nc_completo = conn.execute(
        "SELECT COUNT(*) FROM condominios WHERE area_min IS NOT NULL OR construtora IS NOT NULL OR padrao IS NOT NULL"
    ).fetchone()[0]
    novos = conn.execute("SELECT COUNT(*) FROM imoveis WHERE status='Novo'").fetchone()[0]
    conn.close()
    return {
        "imoveis": ni, "imoveis_whatsapp": ni_wa, "imoveis_scraping": ni_scrape,
        "demandas": nd, "condominios": nc, "condominios_completos": nc_completo,
        "imoveis_novos": novos,
    }


# ─── Definição das etapas do fluxograma ──────────────────────────────────────
# Cada nó: id, título, subtítulo curto (aparece no card), categoria/lane,
# e o "detalhe" (HTML mostrado ao clicar).

def montar_nos(stats):
    return [
        # ---- LANE 1: pipeline automático de imóveis ----
        dict(id="whatsapp", lane="pipeline", titulo="WhatsApp Grupos", sub="Baileys · bot.js · 24/7", detalhe="""
            <p><strong>O que é:</strong> um serviço Node.js (<code>baileys_bot/bot.js</code>) conectado direto ao WhatsApp
            via biblioteca Baileys — sem navegador, sem QR toda hora. Fica sempre rodando (LaunchAgent com
            <code>KeepAlive=true</code>, reinicia sozinho se cair).</p>
            <p><strong>O que faz:</strong> monitora os grupos de corretores configurados em <code>config.json</code>,
            captura toda mensagem de texto e imagem (ignorando grupos bloqueados por regex: moradores, família,
            assembleia, síndico), e grava cada uma crua em <code>mensagens_fila.json</code>.</p>
            <p><strong>Status hoje:</strong> teve algumas quedas de conexão normais (timeouts do WhatsApp Web),
            sempre reconectando sozinho em segundos.</p>
        """),
        dict(id="scraping", lane="pipeline", titulo="Scraping Imobiliárias", sub="raspar_imoveis.py · diário 3h", detalhe="""
            <p><strong>O que é:</strong> script Python que raspa 6 sites de imobiliárias de Maringá: Haraki, Massaru,
            Bellakaza (via CMS Sub100), Silvio Iwata e Casa do Corretor.</p>
            <p><strong>O que faz:</strong> baixa as páginas de listagem, extrai tipo/bairro/área/quartos/preço via
            regex, e grava direto no <code>imoveis.db</code> (sem passar pela IA — dado já vem estruturado do HTML).</p>
            <p><strong>Corrigido hoje:</strong> um bug antigo trocava banheiros por suítes nos sites Sub100
            (97 registros históricos já corrigidos). Agora também cruza com a tabela <code>condominios</code> igual
            ao pipeline do WhatsApp.</p>
            <p><strong>Disparado por:</strong> GitHub Actions (cron diário 03h) — roda na nuvem, não depende do seu Mac ligado.</p>
        """),
        dict(id="processar", lane="pipeline", titulo="processar_mensagens.py", sub="IA classifica e extrai", detalhe="""
            <p><strong>O que faz:</strong> lê <code>mensagens_fila.json</code>, agrupa fotos + texto do mesmo
            corretor numa janela de 5 minutos (1 pacote = 1 imóvel), e decide:</p>
            <p>1) Classifica <strong>venda</strong> vs <strong>demanda</strong> por regex de expressões
            ("vendo", "à venda" vs "preciso de", "tenho cliente"...).<br>
            2) Extrai tipo, bairro, área, quartos, suítes, banheiros, vagas, preço do texto.<br>
            3) Se o texto tiver um <strong>link</strong> do anúncio, baixa a página e manda pro Claude Haiku
            extrair os dados de lá também (adicionado hoje).<br>
            4) Se só tiver <strong>imagem</strong> (sem texto suficiente), o Claude Haiku analisa a foto.</p>
            <p><strong>Reconhece preço em:</strong> "R$800mil", "2 milhões", "2mi", "1.5mi", "800k",
            "até 650.000" — ampliado hoje pra pegar as abreviações mais comuns do WhatsApp.</p>
            <p><strong>Disparado por:</strong> <code>processar_e_push.sh</code> a cada 30 min.</p>
        """),
        dict(id="validacao", lane="pipeline", titulo="Validação &amp; Cruzamento", sub="bairro + condomínios + faixas", detalhe="""
            <p><strong>Antes de gravar, todo imóvel/demanda passa por:</strong></p>
            <p>1) <strong>Bairro</strong> validado contra a lista oficial da Prefeitura de Maringá (match exato →
            fuzzy → busca web como último recurso).<br>
            2) Se o texto cita um <strong>edifício/condomínio</strong>, cruza com a tabela <code>condominios</code>
            (13.787 registros). Se achar, completa bairro/área/quartos/vagas que estiverem vazios no imóvel.<br>
            3) Se o condomínio <strong>não existir ou estiver incompleto</strong> (só nome, sem construtora/área/padrão)
            — e for um <strong>prédio de verdade</strong> (não um condomínio de casas) — pesquisa na web
            (Claude + web_search) e completa o cadastro do condomínio, não só do imóvel.<br>
            4) <strong>Faixas numéricas plausíveis:</strong> quartos 1–10, suítes ≤ quartos, banheiros 0–15,
            área 10–3.000m² pra prédio/casa ou até 500.000m² pra terreno/chácara/sítio (a faixa muda pelo tipo,
            corrigido hoje depois de descobrir que estava descartando terrenos legítimos).</p>
            <p><strong>Como diferencia prédio de condomínio de casas:</strong> nomes com "CONDOMÍNIO RESIDENCIAL",
            "COND.RES.", "CONJ.RES." (padrão típico do import do GeoMaringá) são tratados como casas — cada casa
            tem um tamanho diferente, não faz sentido pesquisar "a specs padrão". Nomes limpos ou com "Edifício"
            explícito são tratados como prédio.</p>
            <p><strong>Bug corrigido hoje:</strong> existia um condomínio cadastrado literalmente chamado
            "MARINGÁ" — toda mensagem que citava a cidade estava "casando" com ele. Corrigido.</p>
        """),
        dict(id="db", lane="pipeline", titulo="imoveis.db", sub="SQLite · banco central", destaque=True, detalhe=f"""
            <p><strong>Tabelas:</strong> <code>imoveis</code>, <code>demandas</code>, <code>condominios</code>.</p>
            <p><strong>Números atuais:</strong></p>
            <ul>
                <li>{stats['imoveis']} imóveis ({stats['imoveis_whatsapp']} via WhatsApp, {stats['imoveis_scraping']} via scraping) —
                {stats['imoveis_novos']} com status "Novo"</li>
                <li>{stats['demandas']} demandas ativas</li>
                <li>{stats['condominios']} condomínios cadastrados ({stats['condominios_completos']} com specs completos:
                construtora/área/padrão — o resto veio em bloco do cadastro oficial do GeoMaringá, só com o nome)</li>
            </ul>
            <p>Todo processo (WhatsApp, scraping, auditoria) escreve aqui. É a fonte única de verdade pro site.</p>
        """),
        dict(id="orquestracao", lane="pipeline", titulo="Orquestração", sub="a cada 30 min + cron diário", detalhe="""
            <p><strong>processar_e_push.sh</strong> (LaunchAgent local, a cada 30 min): roda
            <code>processar_mensagens.py</code> se tiver mensagem pendente, depois <code>gerar_site.py</code>,
            e faz <code>git push</code> do banco + site atualizados.</p>
            <p><strong>GitHub Actions</strong> (na nuvem, independente do seu Mac): roda <code>raspar_imoveis.py</code>
            todo dia às 3h, e <code>gerar_site.py</code> todo dia às 8h (ou a cada push no banco).</p>
        """),
        dict(id="site", lane="pipeline", titulo="Site Público", sub="gerar_site.py → GitHub Pages", detalhe="""
            <p><strong>gerar_site.py</strong> lê só o <code>imoveis.db</code> (fonte única de dados) e monta um único
            arquivo HTML estático (<code>Imoveis.html</code>) com abas de Imóveis e Demandas, busca e filtros — tudo
            em JavaScript puro, sem servidor.</p>
            <p><strong>VivaReal e Junior Joda</strong> não são mais lidos de planilha na hora de gerar o site: são
            sincronizados pro banco via upsert (<code>scrape_vivareal.py</code> / <code>importar_vivareal.py</code> /
            <code>importar_juniorjoda.py</code>), identificados por <code>fonte</code> + <code>ref_externa</code>.
            Isso permite rastrear <strong>histórico de preço</strong> por imóvel/edifício em <code>preco_historico</code>
            e marcar automaticamente como <code>Removido</code> quem sai do catálogo de uma fonte.</p>
            <p><strong>Publicação:</strong> o GitHub Actions copia esse HTML pro GitHub Pages. Site final:
            <a href="https://sodoskinicolas.github.io/imoveis-maringa/" target="_blank">sodoskinicolas.github.io/imoveis-maringa</a></p>
        """),
        # ---- LANE 2: prospecção ----
        dict(id="geomaringa", lane="prospeccao", titulo="GeoMaringá + eEmovel", sub="skill · acha proprietários", detalhe="""
            <p><strong>O que faz:</strong> dado um endereço ou nome de prédio, consulta a API pública do GeoMaringá
            (cadastro imobiliário oficial da Prefeitura) pra achar o lote e todos os endereços dele, depois
            automatiza o site <code>brokers.eemovel.com.br</code> via Chrome pra extrair nome + WhatsApp de cada
            proprietário.</p>
            <p><strong>Também foi usado hoje</strong> pra importar os 13.787 nomes de condomínios de Maringá pra
            tabela <code>condominios</code> (achei uma camada "Area Condominio" na API do GeoMaringá com o cadastro
            completo do município).</p>
            <p><strong>Saída:</strong> planilha Excel + lista formatada pra WhatsApp.</p>
        """),
        dict(id="kurole", lane="prospeccao", titulo="Kurole CRM", sub="skill · leads compradores", detalhe="""
            <p><strong>O que faz:</strong> extrai nome + telefone dos cards do CRM Kurole (usado pela imobiliária
            Patrimônio Imóveis Prontos), das colunas de Suspecção/Prospecção/Diagnóstico/Proposta.</p>
            <p><strong>Saída:</strong> alimenta a skill <code>envio-leads-whatsapp</code>.</p>
        """),
        dict(id="envio", lane="prospeccao", titulo="Envio WhatsApp", sub="skills · corretores e leads", detalhe="""
            <p><strong>envio-leads-whatsapp:</strong> manda mensagem (com 5 variações sorteadas) pra uma lista de
            leads/clientes, intervalo aleatório de 30–60s.</p>
            <p><strong>envio-massa-whatsapp:</strong> manda 2 mensagens sequenciais fixas pra corretores/contatos,
            com regras de exclusão (já salvo na agenda, já tem conversa aberta).</p>
            <p>Ambas rodam via WhatsApp Web + Chrome, sem precisar de API paga.</p>
        """),
        # ---- LANE 3: manutenção ----
        dict(id="auditoria", lane="manutencao", titulo="auditar_historico.py", sub="correção retroativa", detalhe="""
            <p><strong>Ferramenta nova (criada hoje).</strong> Reprocessa as mensagens ainda disponíveis na fila com
            a lógica de extração/validação atual, e reconcilia com o banco: corrige registros que tinham dado errado
            e insere o que tinha sido descartado antes de alguma correção.</p>
            <p>Também audita a tabela <code>imoveis</code> inteira (mesmo os registros mais antigos, sem o texto
            original disponível) validando bairro e faixas numéricas com o que já está salvo.</p>
            <p><strong>Uso:</strong> <code>python3 auditar_historico.py --dry-run</code> pra ver o que mudaria,
            <code>--apply</code> pra gravar de verdade.</p>
        """),
        # ---- LANE 4: legado / status incerto ----
        dict(id="legado", lane="legado", titulo="Fluxos paralelos / legado", sub="status incerto — revisar", detalhe="""
            <p>Scripts que existem no repositório mas não parecem mais conectados ao fluxo automático principal:</p>
            <ul>
                <li><strong>bot_grupos_wa.py / bot_demandas_wa.py</strong> — CLIs standalone, nenhum outro arquivo os chama hoje.</li>
                <li><strong>leitor-grupos-wa (skill)</strong> — lê grupos via Chrome, grava em Imoveis_Grupos.xlsx,
                em paralelo ao bot.js (Baileys). Não fica claro qual dos dois é o ativo.</li>
                <li><strong>scrape_vivareal.py vs importar_vivareal.py</strong> — dois caminhos pro mesmo dado.</li>
                <li><strong>docker-compose (Evolution API)</strong> + extrair/enviar contatos — prospecção antiga,
                parece substituída pelas skills de envio.</li>
            </ul>
            <p>Vale uma limpeza quando quiser — não é urgente, só ocupa espaço.</p>
        """),
    ]


# ─── Template HTML ───────────────────────────────────────────────────────────

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
    background: #f4f5f7; color: #1a1d23; padding: 32px 24px 80px;
}
h1 { font-size: 22px; font-weight: 700; margin-bottom: 4px; }
.subtitulo { color: #6b7280; font-size: 13px; margin-bottom: 28px; }
.lane { margin-bottom: 34px; }
.lane-titulo {
    font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
    color: #6b46c1; margin-bottom: 12px;
}
.lane[data-lane="legado"] .lane-titulo { color: #9ca3af; }
.rio { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.card {
    background: #fff; border: 1.5px solid #e2e4e9; border-radius: 10px;
    padding: 12px 16px; min-width: 190px; max-width: 230px; cursor: pointer;
    transition: box-shadow .15s, border-color .15s, transform .1s;
}
.card:hover { box-shadow: 0 4px 14px rgba(0,0,0,.08); border-color: #6b46c1; transform: translateY(-1px); }
.card.ativo { border-color: #6b46c1; box-shadow: 0 0 0 3px rgba(107,70,193,.15); }
.card.destaque { border-color: #2563eb; border-width: 2px; background: #f5f8ff; }
.card-titulo { font-size: 13.5px; font-weight: 700; margin-bottom: 2px; }
.card-sub { font-size: 11px; color: #6b7280; }
.lane[data-lane="legado"] .card { border-style: dashed; background: #fafafa; }
.seta { color: #9ca3af; font-size: 18px; padding: 0 2px; }
.painel {
    position: fixed; top: 0; right: 0; height: 100%; width: 420px; max-width: 92vw;
    background: #fff; box-shadow: -6px 0 24px rgba(0,0,0,.12);
    transform: translateX(100%); transition: transform .2s ease;
    padding: 28px 26px; overflow-y: auto; z-index: 20;
}
.painel.aberto { transform: translateX(0); }
.painel-fechar {
    position: absolute; top: 18px; right: 18px; width: 30px; height: 30px; border-radius: 50%;
    border: none; background: #f0f0f2; font-size: 16px; cursor: pointer; color: #444;
}
.painel h2 { font-size: 18px; margin-bottom: 14px; padding-right: 30px; }
.painel p { font-size: 13.5px; line-height: 1.6; margin-bottom: 12px; color: #2c2f36; }
.painel code {
    background: #f0f0f5; padding: 1px 5px; border-radius: 4px; font-size: 12.5px; color: #6b46c1;
}
.painel ul { margin: 0 0 12px 20px; }
.painel li { font-size: 13.5px; line-height: 1.6; margin-bottom: 4px; }
.overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,.15); opacity: 0; pointer-events: none;
    transition: opacity .2s; z-index: 15;
}
.overlay.aberto { opacity: 1; pointer-events: auto; }
.rodape { margin-top: 40px; font-size: 11.5px; color: #9ca3af; }
.rodape code { background: #eceef2; padding: 1px 5px; border-radius: 4px; }
"""

JS = """
function abrirPainel(id) {
    const node = DADOS.find(n => n.id === id);
    if (!node) return;
    document.getElementById('painel-titulo').textContent = node.titulo;
    document.getElementById('painel-corpo').innerHTML = node.detalhe;
    document.getElementById('painel').classList.add('aberto');
    document.getElementById('overlay').classList.add('aberto');
    document.querySelectorAll('.card').forEach(c => c.classList.remove('ativo'));
    document.getElementById('card-' + id).classList.add('ativo');
}
function fecharPainel() {
    document.getElementById('painel').classList.remove('aberto');
    document.getElementById('overlay').classList.remove('aberto');
    document.querySelectorAll('.card').forEach(c => c.classList.remove('ativo'));
}
"""

LANES = [
    ("pipeline", "Pipeline de imóveis · automático"),
    ("prospeccao", "Prospecção de corretores &amp; leads · manual"),
    ("manutencao", "Manutenção &amp; qualidade de dados"),
    ("legado", "Fluxos paralelos / legado"),
]


def gerar_html(stats):
    nos = montar_nos(stats)
    por_lane = {lane_id: [] for lane_id, _ in LANES}
    for n in nos:
        por_lane[n["lane"]].append(n)

    lanes_html = []
    for lane_id, lane_titulo in LANES:
        cards = []
        itens = por_lane[lane_id]
        for i, n in enumerate(itens):
            classe = "card destaque" if n.get("destaque") else "card"
            cards.append(
                f'<div class="{classe}" id="card-{n["id"]}" onclick="abrirPainel(\'{n["id"]}\')">'
                f'<div class="card-titulo">{n["titulo"]}</div>'
                f'<div class="card-sub">{n["sub"]}</div></div>'
            )
            if i < len(itens) - 1:
                cards.append('<span class="seta">→</span>')
        lanes_html.append(f'''
        <div class="lane" data-lane="{lane_id}">
            <div class="lane-titulo">{lane_titulo}</div>
            <div class="rio">{"".join(cards)}</div>
        </div>''')

    dados_js = json.dumps([{"id": n["id"], "titulo": n["titulo"], "detalhe": n["detalhe"]} for n in nos], ensure_ascii=False)
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fluxograma do Sistema — Imóveis Maringá</title>
<style>{CSS}</style>
</head>
<body>
<h1>🗺️ Fluxograma do sistema — Imóveis Maringá</h1>
<div class="subtitulo">Clique em qualquer etapa pra ver a lógica dela. Gerado em {agora} · {stats['imoveis']} imóveis · {stats['demandas']} demandas · {stats['condominios']} condomínios no banco agora.</div>

{"".join(lanes_html)}

<div class="rodape">
Pra atualizar com os números e o conteúdo mais recentes, rode <code>python3 gerar_fluxograma.py</code> de novo
e recarregue esta página no navegador.
</div>

<div class="overlay" id="overlay" onclick="fecharPainel()"></div>
<div class="painel" id="painel">
    <button class="painel-fechar" onclick="fecharPainel()">✕</button>
    <h2 id="painel-titulo"></h2>
    <div id="painel-corpo"></div>
</div>

<script>
const DADOS = {dados_js};
{JS}
</script>
</body>
</html>"""


def main():
    stats = coletar_stats()
    html = gerar_html(stats)
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"✅ Fluxograma gerado: {OUT_PATH}")
    print(f"   {stats['imoveis']} imóveis | {stats['demandas']} demandas | {stats['condominios']} condomínios")


if __name__ == "__main__":
    main()
