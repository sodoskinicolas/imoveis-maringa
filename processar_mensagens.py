#!/usr/bin/env python3
"""
processar_mensagens.py
Lê mensagens capturadas pelo bot Baileys, agrupa fotos + texto do mesmo corretor
como um único imóvel, extrai dados e salva no SQLite (imoveis.db).

Uso:
    python3 processar_mensagens.py             # processa e atualiza planilha
    python3 processar_mensagens.py --dry-run   # mostra sem salvar
    python3 processar_mensagens.py --ver-fila  # lista mensagens pendentes
"""

import json, re, sys, os, base64, unicodedata
from pathlib import Path
import db

BASE_DIR     = Path(__file__).parent
FILA_FILE    = BASE_DIR / "mensagens_fila.json"
ABA_IMOVEIS      = "Imóveis"
ABA_DEMANDAS     = "Demandas"
ABA_CONDOMINIOS  = "Condomínios"

DRY_RUN  = "--dry-run"  in sys.argv
VER_FILA = "--ver-fila" in sys.argv

# Janela de tempo para agrupar fotos + texto do mesmo corretor (segundos)
JANELA_AGRUPAMENTO = 300  # 5 minutos

# ─── Colunas (igual ao existente na planilha) ────────────────────────────────
COLUNAS_IMOVEIS = [
    'Data Captura', 'Grupo', 'Corretor', 'Contato (WhatsApp)', 'Tipo',
    'Bairro / Endereço', 'Área (m²)', 'Quartos', 'Suítes', 'Banheiros',
    'Vagas', 'Preço (R$)', 'Observações', 'Status', 'Data Publicação'
]

COLUNAS_DEMANDAS = [
    'Data', 'Grupo', 'Corretor', 'Contato', 'Tipo Buscado', 'Bairro/Região',
    'Área Mín', 'Quartos', 'Suítes', 'Banheiros', 'Vagas', 'Orçamento Máx',
    'Observações', 'Status'
]

COLUNAS_CONDOMINIOS = [
    'Nome', 'Endereço', 'Bairro', 'CEP', 'Construtora / Incorporadora',
    'Ano Lançamento', 'Previsão Entrega', 'Padrão',
    'Torres', 'Andares', 'Total Aptos',
    'Área Mín (m²)', 'Área Máx (m²)', 'Quartos', 'Vagas',
    'Lazer', 'Faixa de Preço', 'Observações', 'Site / Link', 'Data Cadastro'
]

# Nomes de condomínios descobertos nesta execução (para pesquisar ao final)
_CONDOS_NOVOS: set = set()

# ─── Anthropic API ────────────────────────────────────────────────────────────

def _api_key():
    env = BASE_DIR / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("ANTHROPIC_API_KEY", "")

def analisar_imagem(img_path, caption="", autor=""):
    """Claude Haiku analisa uma imagem e extrai dados do imóvel."""
    api_key = _api_key()
    if not api_key or not Path(img_path).exists():
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        img_b64 = base64.standard_b64encode(Path(img_path).read_bytes()).decode()

        prompt = (
            "Você é especialista em imóveis de Maringá/PR. Analise esta imagem de grupo de corretores.\n"
            "Retorne SOMENTE um JSON válido:\n"
            '{"eh_imovel":true/false,"tipo":"Apartamento|Casa|Terreno|Sala Comercial|Outro",'
            '"bairro":"nome ou null","area":numero_m2_ou_null,"quartos":num_ou_null,'
            '"suites":num_ou_null,"banheiros":num_ou_null,"vagas":num_ou_null,'
            '"preco":inteiro_reais_ou_null,"obs":"info extra"}\n\n'
            f"Legenda: {caption or '(sem legenda)'}\nCorretor: {autor}"
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role":"user","content":[
                {"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":img_b64}},
                {"type":"text","text":prompt}
            ]}]
        )
        m = re.search(r'\{.*\}', resp.content[0].text, re.DOTALL)
        return json.loads(m.group()) if m else None
    except Exception as e:
        print(f"  ⚠️  Claude API: {e}")
        return None

# ─── Links de imóveis (sites de imobiliárias, portais) ───────────────────────

_HEADERS_LINK = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# Domínios que não são páginas de imóvel (não vale a pena buscar)
_LINKS_IGNORAR = re.compile(
    r'wa\.me|whatsapp\.com|chat\.whatsapp|instagram\.com|facebook\.com|fb\.com|'
    r'youtube\.com|youtu\.be|maps\.google|goo\.gl/maps|tiktok\.com',
    re.IGNORECASE
)

def extrair_links(texto):
    """Retorna lista de URLs http(s) encontradas no texto, ignorando redes sociais/mapas."""
    if not texto:
        return []
    urls = re.findall(r'https?://[^\s<>"\')\]]+', texto)
    limpos = []
    for u in urls:
        u = u.rstrip('.,;!?')
        if u and not _LINKS_IGNORAR.search(u) and u not in limpos:
            limpos.append(u)
    return limpos

def _extrair_texto_pagina(html, max_chars=3000):
    """Extrai título, meta tags e texto visível de uma página HTML."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")

    partes = []
    if soup.title and soup.title.string:
        partes.append(f"TÍTULO: {soup.title.string.strip()}")

    for prop in ("og:title", "og:description", "description", "og:price:amount", "product:price:amount"):
        tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            partes.append(f"{prop.upper()}: {tag['content'].strip()}")

    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    corpo = soup.get_text(separator=" ", strip=True)
    corpo = re.sub(r'\s{2,}', ' ', corpo)
    partes.append(f"TEXTO DA PÁGINA: {corpo[:max_chars]}")

    return "\n".join(partes)

def analisar_link(url, caption="", autor=""):
    """
    Baixa a página de um link de imóvel compartilhado e usa Claude Haiku
    para extrair os dados, no mesmo schema usado para imagens.
    Retorna dict ou None se a página não puder ser lida/não for imóvel.
    """
    api_key = _api_key()
    if not api_key:
        return None
    try:
        import requests
        resp = requests.get(url, headers=_HEADERS_LINK, timeout=12, allow_redirects=True)
        ctype = resp.headers.get("Content-Type", "")
        if resp.status_code != 200 or "html" not in ctype.lower():
            print(f"  ⚠️  Link {url} → status {resp.status_code} / {ctype or '?'}")
            return None
        texto_pagina = _extrair_texto_pagina(resp.text)
    except Exception as e:
        print(f"  ⚠️  Não consegui acessar o link ({url}): {e}")
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            "Você é especialista em imóveis de Maringá/PR. Abaixo está o conteúdo extraído "
            "da página de um anúncio de imóvel compartilhado num grupo de corretores.\n"
            "Retorne SOMENTE um JSON válido:\n"
            '{"eh_imovel":true/false,"tipo":"Apartamento|Casa|Terreno|Sala Comercial|Outro",'
            '"bairro":"nome ou null","edificio":"nome do condomínio/edifício ou null",'
            '"area":numero_m2_ou_null,"quartos":num_ou_null,"suites":num_ou_null,'
            '"banheiros":num_ou_null,"vagas":num_ou_null,"preco":inteiro_reais_ou_null,'
            '"obs":"resumo curto do anúncio"}\n\n'
            f"Legenda da mensagem: {caption or '(sem legenda)'}\nCorretor: {autor}\n\n"
            f"{texto_pagina}"
        )
        resp_ai = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        m = re.search(r'\{.*\}', resp_ai.content[0].text, re.DOTALL)
        resultado = json.loads(m.group()) if m else None
        if resultado and resultado.get("eh_imovel"):
            resultado["link"] = url
            print(f"  🔗 Link analisado: {resultado.get('tipo')} | {resultado.get('bairro') or '?'} | R${resultado.get('preco')}")
            return resultado
        return None
    except Exception as e:
        print(f"  ⚠️  Claude API (link): {e}")
        return None

# ─── Classificação: venda vs demanda ─────────────────────────────────────────

RE_DEMANDA = re.compile(
    r'cliente\s+(?:aprov|busc|quer|prec|comprad|procur)|'
    r'tenho\s+cliente|tenho\s+comprador|'
    r'\bpreciso\s+de\b|\bprocuro\b|\bestou\s+procurando\b|\bà\s+procura\b|'
    r'quero\s+(?:comprar|alugar)|'
    r'comprador\s+(?:busca|procura|quer|aprov)|'
    r'aprovado\s+em|aprovada\s+em|financiamento\s+aprovado|'
    r'busca(?:ndo)?\s+(?:casa|apartamento|apto|imovel|imóvel|terreno)|'
    r'algu[eé]m\s+(?:tem|com|que\s+tenha)\s+\w|'   # "alguém com um X pra venda"
    r'algu[eé]m\s+(?:tem|tem\s+um|sabe\s+de)|'
    r'\bpra\s+venda[,\s].{0,30}(?:precis|quer|busca|procu)',  # "pra venda... preciso"
    re.IGNORECASE)

# "Se vc procura... achou!" = anúncio de venda, não demanda
RE_VENDA = re.compile(
    r'\bvendo\b|\bvende\b|\bà\s+venda\b|\bdisponív|\banuncio\b|\bofereço\b|'
    r'\bchaves\s+na\s+mão\b|\bentrego\s+chaves\b|'
    r'achou[!🎉]|(?:se\s+vc|se\s+você)\s+procura',
    re.IGNORECASE)

def classificar(texto):
    d = bool(RE_DEMANDA.search(texto))
    v = bool(RE_VENDA.search(texto))
    if d and not v: return 'demanda'
    if v and not d: return 'venda'
    if d and v:
        return 'demanda' if RE_DEMANDA.search(texto).start() < RE_VENDA.search(texto).start() else 'venda'
    return 'indefinido'

# ─── Limpeza de texto WhatsApp ───────────────────────────────────────────────

def limpar_obs(texto):
    """Remove formatação WhatsApp do texto de observações."""
    if not texto:
        return texto
    # Remover negrito/itálico do WhatsApp: *texto* → texto, _texto_ → texto
    t = re.sub(r'\*([^*\n]+)\*', r'\1', texto)
    t = re.sub(r'_([^_\n]+)_', r'\1', t)
    # Remover tachado: ~texto~ → texto
    t = re.sub(r'~([^~\n]+)~', r'\1', t)
    # Remover caracteres invisíveis
    t = re.sub(r'[⁠​‌‍﻿]', '', t)
    # Limpar espaços múltiplos e linhas em branco excessivas
    t = re.sub(r' {2,}', ' ', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()

# ─── Extratores ───────────────────────────────────────────────────────────────

def extrair_preco(texto):
    # Remover caracteres invisíveis (ex: U+2060 WORD JOINER do WhatsApp)
    texto = re.sub(r'[⁠​‌‍﻿]', '', texto)

    # Preço atual quando houve redução: "de R$X para R$Y" → usa Y
    m_red = (
        re.search(r'reduz(?:iu|indo|ão).{0,60}?para\s*R?\$?\s*([\d.,]+)', texto, re.IGNORECASE) or
        re.search(r'de\s+R\$\s*[\d.,]+\s+para\s*R?\$?\s*([\d.,]+)', texto, re.IGNORECASE) or
        re.search(r'baixou.{0,40}?para\s*R?\$?\s*([\d.,]+)', texto, re.IGNORECASE) or
        re.search(r'por\s+apenas\s*R?\$?\s*([\d.,]+)', texto, re.IGNORECASE)
    )
    if m_red:
        raw = m_red.group(1).rstrip('.,')
        try:
            if re.match(r'^\d{1,3}(\.\d{3})+(,\d{2})?$', raw):
                num = float(raw.replace('.','').replace(',','.'))
            else:
                num = float(raw.replace(',',''))
            if 30_000 <= num <= 50_000_000:
                return int(num)
        except: pass

    padroes = [
        (r'R\$\s*([\d.,]+)\s*mi(?:lhão|lhões|l\b)?', 'mi'),
        (r'R\$\s*([\d.,]+)\s*mil\b', 'mil'),
        (r'R\$\s*([\d.,]+)', 'reais'),
        (r'\b(\d+(?:[.,]\d+)?)\s*mi(?:lhão|lhões)\b', 'mi'),   # "1 milhão" sem R$
        (r'\b(\d+(?:[.,]\d+)?)\s*mi\b', 'mi'),                 # "2mi" / "1.5 mi" abreviado, sem R$
        (r'\binvestimento[:\s]+(\d+(?:[.,]\d+)?)\s*mil\b', 'mil'),
        (r'\b([\d.,]+)\s*mil\b', 'mil'),
        (r'\b(\d+(?:[.,]\d+)?)\s*k\b', 'mil'),                 # "800k" abreviado
        # Número completo sem R$/mil/mi, mas só quando vem colado a uma palavra
        # de preço (evita confundir com CEP, telefone, código de imóvel etc.)
        (r'(?:at[ée]|por|valor|pre[çc]o|or[çc]amento|na\s+faixa\s+de|'
         r'cerca\s+de|em\s+torno\s+de)\s*(?:de\s+)?(\d{1,3}(?:\.\d{3}){1,3}(?:,\d{2})?)\b', 'reais'),
    ]
    for pat, tipo in padroes:
        m = re.search(pat, texto, re.IGNORECASE)
        if not m: continue
        raw = m.group(1).rstrip('.,')  # remove ponto/vírgula final (ex: "2.750.000,00.")
        if not raw: continue
        try:
            if re.match(r'^\d{1,3}(\.\d{3})+(,\d{2})?$', raw):
                num = float(raw.replace('.','').replace(',','.'))
            elif ',' in raw and '.' not in raw:
                num = float(raw.replace(',','.'))
            else:
                num = float(raw.replace(',',''))
            if tipo == 'mi':  num *= 1_000_000
            if tipo == 'mil' and num < 10_000: num *= 1_000
            if 30_000 <= num <= 50_000_000:
                return int(num)
        except: pass
    return None

def extrair_area(texto):
    """
    Prioridade: área privativa/construída > área total do imóvel > terreno (só obs).
    Retorna a área útil para match; área de terreno fica só nas observações.
    """
    t = texto

    # 1. Área privativa explícita: "192m² privativa", "área privativa 192m²"
    m = re.search(r'(?:área\s+)?privativ[ao]\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*m[²2]', t, re.IGNORECASE)
    if not m:
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*m[²2]\s*(?:de\s+)?privativ[ao]', t, re.IGNORECASE)
    if m:
        try: return float(m.group(1).replace(',','.'))
        except: pass

    # 2. Área construída/útil explícita: "192m² de construção", "construção 192m²"
    m = re.search(r'(?:área\s+)?constru[íi]d[ao]\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*m[²2]', t, re.IGNORECASE)
    if not m:
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*m[²2]\s*(?:de\s+)?constru[íi]d[ao]', t, re.IGNORECASE)
    if not m:
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*m[²2]\s*(?:de\s+)?constru[çc][aã]o', t, re.IGNORECASE)
    if not m:
        m = re.search(r'constru[çc][aã]o\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*m[²2]', t, re.IGNORECASE)
    if not m:
        m = re.search(r'(?:área\s+)?[uú]til\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*m[²2]', t, re.IGNORECASE)
    if m:
        try: return float(m.group(1).replace(',','.'))
        except: pass

    # 3. Nenhuma área específica — pegar primeiro número m² que NÃO seja terreno/lote
    # Se o contexto próximo contém "terreno" ou "lote", ignorar
    for m in re.finditer(r'(\d+(?:[.,]\d+)?)\s*m[²2]', t, re.IGNORECASE):
        # Verificar contexto (20 chars antes e depois)
        start = max(0, m.start() - 25)
        end   = min(len(t), m.end() + 25)
        ctx   = t[start:end].lower()
        if re.search(r'\bterreno\b|\blote\b|\bterr\b', ctx):
            continue  # pular área de terreno
        try: return float(m.group(1).replace(',','.'))
        except: pass

    return None

def extrair_num(texto, palavras):
    for p in palavras:
        m = re.search(r'(\d+)\s*' + p, texto, re.IGNORECASE)
        if m: return int(m.group(1))
    return None

def extrair_tipo(texto):
    t = texto.lower()
    primeira_linha = t.split('\n')[0].strip()

    # Prioridade 1: TÍTULO da primeira linha (ex: "Casa à Venda – ...")
    m_titulo = re.match(
        r'^(casa|sobrado|terreno|lote|apartamento|apto|sala|galpão|kitnet|studio|chácara|sítio)\b',
        primeira_linha)
    if m_titulo:
        p = m_titulo.group(1)
        if 'apart' in p or 'apto' in p:        return 'Apartamento'
        if 'casa'    in p:                      return 'Casa'
        if 'sobrado' in p:                      return 'Sobrado'
        if 'terreno' in p or 'lote' in p:       return 'Terreno'
        if 'sala'    in p:                      return 'Sala Comercial'
        if 'galpão'  in p:                      return 'Galpão'
        if 'kitnet'  in p or 'studio' in p:     return 'Kitnet'
        if 'chácara' in p or 'sítio' in p:      return 'Chácara'

    # Prioridade 2: padrão "proprietária de uma CASA", "vendo uma CASA", etc.
    m_oferta = re.search(
        r'(?:proprietári[ao]\s+de\s+um[a]?\s+|vendo\s+um[a]?\s+|tenho\s+um[a]?\s+|à\s+venda[:\s]+um[a]?\s+)'
        r'(apartamento|apto|casa|terreno|lote|sala|galpão|sobrado|kitnet)',
        t)
    if m_oferta:
        palavra = m_oferta.group(1)
        if 'apart' in palavra or 'apto' in palavra: return 'Apartamento'
        if 'casa'    in palavra: return 'Casa'
        if 'terreno' in palavra or 'lote' in palavra: return 'Terreno'
        if 'sala'    in palavra: return 'Sala Comercial'
        if 'galpão'  in palavra: return 'Galpão'
        if 'sobrado' in palavra: return 'Sobrado'
        if 'kitnet'  in palavra: return 'Kitnet'

    # Sinais de imóvel habitado (quartos, suíte, sala, cozinha) — se presentes,
    # "lote" e "terreno" são apenas medidas, não o tipo do imóvel
    tem_habitacao = bool(re.search(
        r'\bquartos?\b|\bdorm\b|\bsuítes?\b|\bsala\s+(?:de\s+)?(?:estar|jantar|pé\s+direito)\b'
        r'|\bcozinha\b|\bárea\s+privativa\b|\bárea\s+construída\b', t))

    # Prioridade 3: primeira menção no texto completo
    if re.search(r'\bkitnet\b|\bkit\s*net\b|\bstudio\b|\bflat\b', t): return 'Kitnet'
    if re.search(r'\bapartamento|\bapto\b|\bcobertura\b|\bárea\s+privativa\b', t): return 'Apartamento'
    if re.search(r'\bsobrado\b', t):                           return 'Sobrado'
    if re.search(r'\bcasa\b', t):                              return 'Casa'
    # "terreno" e "lote" só classificam como Terreno se não houver sinais de habitação
    if not tem_habitacao and re.search(r'\bterreno\b|\blote\b', t): return 'Terreno'
    if tem_habitacao and re.search(r'\blote\b|\bárea\s+do\s+lote\b', t): return 'Casa'
    if re.search(r'\bsala\s+comercial|\bloja\b|\bescritório\b', t): return 'Sala Comercial'
    if re.search(r'\bgalpão\b', t):                            return 'Galpão'
    if re.search(r'\bedifício|\bed\.\s*[a-zA-Z]|\bandar\b', t): return 'Apartamento'
    return 'Imóvel'

BAIRROS = [
    'Zona 01','Zona 02','Zona 03','Zona 04','Zona 05','Zona 06','Zona 07','Zona 08',
    'Zona 14','Zona 17','Zona 18','Jardim Alvorada','Jardim América','Jardim Astúrias',
    'Jardim Atalaia','Jardim Avenida','Jardim Bela Vista','Jardim Borba Gato',
    'Jardim Catuaí','Jardim Cidade Monções','Jardim Contorno','Jardim Dias',
    'Jardim Dubai','Jardim Europa','Jardim Farolândia','Jardim Finotti',
    'Jardim Florença','Jardim Imperial','Jardim Independência','Jardim Ipanema',
    'Jardim Itaipu','Jardim Liberdade','Jardim Malibu','Jardim Mandacaru',
    'Jardim Mônaco','Jardim Novo Horizonte','Jardim Olímpico','Jardim Panorama',
    'Jardim Paris','Jardim Paulista','Jardim Pinheiros','Jardim Primavera',
    'Jardim Santos Dumont','Jardim São Jorge','Jardim São Paulo','Jardim Sol Nascente',
    'Jardim Tamariz','Jardim Universo','Jardim Vera Cruz','Jardim Vitória','Jardim Yara',
    'Alto da Glória','Alto Alegre','Aeroporto','Centro','Centro Cívico','Floriano',
    'Gleba Palhano','Liberdade','Nova Esperança','Novo Aeroporto',
    'Parque das Laranjeiras','Parque Hortência','Parque Ideal','Santa Felicidade',
    'Santa Cruz','Santa Mônica','Santa Rosa','Santa Terezinha','Tuiuti','Ulyssea',
    'Vigilato Pereira','Palhano','Yara','Morumbi','Jardim Fregadoli',
    'Jardim Gastão Vidigal','Chácaras Aeroporto','Vila Operária','Vila Morangueira',
    # Loteamentos e bairros menos conhecidos
    'Jardim 3 Lagoas','Jardim Três Lagoas','Jardim Universitário','Jardim Altos do Mirante',
    'Jardim Colinas','Jardim Copacabana','Jardim Dinalva','Jardim Dom Bosco',
    'Jardim Flamingos','Jardim Francos','Jardim Ibiporã','Jardim Marcelo',
    'Jardim Monte Rei','Jardim Nobre','Jardim Olimpo','Jardim Ouro Branco',
    'Jardim Suíço','Jardim Tuiuti','Parque Alvorada','Parque Estação',
    'Residencial Cidade Universitária','Cidade Universitária',
    'Conjunto Residencial Requião','Jardim Requião',
]
BAIRROS_LOWER = {b.lower(): b for b in BAIRROS}

# ─── Lista oficial de bairros de Maringá (Prefeitura) ────────────────────────

BAIRROS_OFICIAIS_FILE = BASE_DIR / "bairros_maringa.json"
_BAIRROS_OFICIAIS_LOWER = None   # {normalizado: nome_oficial}

def _normalizar_bairro(s):
    """Remove acentos e coloca em minúsculas para comparação."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', (s or '').lower())
        if unicodedata.category(c) != 'Mn'
    ).strip()

def _carregar_bairros_oficiais():
    global _BAIRROS_OFICIAIS_LOWER
    if _BAIRROS_OFICIAIS_LOWER is not None:
        return
    try:
        with open(BAIRROS_OFICIAIS_FILE, encoding='utf-8') as f:
            lista = json.load(f)   # lista plana de strings
        _BAIRROS_OFICIAIS_LOWER = {_normalizar_bairro(b): b for b in lista}
    except Exception as e:
        print(f"  ⚠️  bairros_maringa.json: {e}")
        _BAIRROS_OFICIAIS_LOWER = {}

CACHE_VALIDACAO_BAIRRO_FILE = BASE_DIR / "cache_validacao_bairro.json"
_cache_val_bairro = None

def _cv_load():
    global _cache_val_bairro
    if _cache_val_bairro is not None:
        return _cache_val_bairro
    try:
        if CACHE_VALIDACAO_BAIRRO_FILE.exists():
            _cache_val_bairro = json.loads(CACHE_VALIDACAO_BAIRRO_FILE.read_text('utf-8'))
        else:
            _cache_val_bairro = {}
    except:
        _cache_val_bairro = {}
    return _cache_val_bairro

def _cv_save():
    if _cache_val_bairro is not None:
        CACHE_VALIDACAO_BAIRRO_FILE.write_text(
            json.dumps(_cache_val_bairro, ensure_ascii=False, indent=2), 'utf-8')

def _match_bairro_oficial(candidato):
    """Retorna (nome_oficial, score) ou (None, 0.0)."""
    _carregar_bairros_oficiais()
    if not candidato or not _BAIRROS_OFICIAIS_LOWER:
        return None, 0.0
    # Expandir abreviações antes de comparar (ex: "Jd" → "Jardim")
    candidato_exp = _expandir_abreviaturas(candidato)
    nc = _normalizar_bairro(candidato_exp)
    # 1. Exato
    if nc in _BAIRROS_OFICIAIS_LOWER:
        return _BAIRROS_OFICIAIS_LOWER[nc], 1.0
    # 2. Substring: a) oficial está contido no candidato ("Jardim Alvorada II" → nc contém nl)
    #              b) candidato está contido no oficial SÓ SE for >= 75% do comprimento
    #                 (evita "Tuiuti" → "Parque Residencial Tuiuti")
    for nl, oficial in _BAIRROS_OFICIAIS_LOWER.items():
        if not nc or not nl:
            continue
        if nl in nc:                              # oficial ⊆ candidato
            return oficial, 0.9
        if nc in nl and len(nc) >= 0.75 * len(nl):  # candidato ⊆ oficial (próximo em tamanho)
            return oficial, 0.9
    # 3. Fuzzy
    from difflib import SequenceMatcher
    melhor, best = None, 0.0
    for nl, oficial in _BAIRROS_OFICIAIS_LOWER.items():
        s = SequenceMatcher(None, nc, nl).ratio()
        if s > best:
            best, melhor = s, oficial
    if best >= 0.88:
        return melhor, best
    return None, best

def _buscar_bairro_web(referencia):
    """Claude Haiku + web_search para descobrir o bairro. Retorna string ou None."""
    api_key = _api_key()
    if not api_key:
        return None
    _carregar_bairros_oficiais()
    exemplos = ', '.join(list(_BAIRROS_OFICIAIS_LOWER.values())[:25])
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": (
                f'Qual é o BAIRRO deste imóvel em Maringá-PR?\n\n'
                f'REFERÊNCIA: {referencia[:400]}\n\n'
                f'Pesquise na internet o edifício/endereço e retorne SOMENTE o nome '
                f'do bairro oficial de Maringá (ex: {exemplos}...). '
                f'Se não encontrar, retorne NULO.'
            )}]
        )
        texto = ''.join(b.text for b in resp.content if hasattr(b, 'text')).strip()
        bairro = texto.split('\n')[0].strip().strip('"\'')
        # Rejeitar respostas conversacionais (modelo falou em vez de retornar bairro)
        _prefixos_invalidos = ('vou ', 'preciso ', 'não ', 'nao ', 'infelizmente',
                               'com base', 'para ', 'posso ', 'a referência',
                               'a localização', 'o imóvel', 'desculpe')
        if bairro and bairro.upper() != 'NULO' and 2 < len(bairro) < 50:
            if not bairro.lower().startswith(_prefixos_invalidos) and ',' not in bairro[:20]:
                return bairro
    except Exception as e:
        print(f"  ⚠️  Busca web bairro: {e}")
    return None

def validar_bairro(bairro_extraido, texto_completo='', edificio=''):
    """
    Valida/corrige o bairro extraído contra a lista oficial de Maringá.

    Fluxo:
      1. Match direto/fuzzy na lista oficial
      2. Se não encontrar, busca na web usando edifício + texto como referência
      3. Valida resultado da web também
      4. Cacheia pelo edifício (chave mais estável) para evitar buscas repetidas

    Retorna o nome oficial ou o candidato original se não confirmar.
    """
    _carregar_bairros_oficiais()
    cache = _cv_load()

    # Chave de cache: edifício tem precedência (mais estável)
    chave_cache = _normalizar_bairro(edificio or bairro_extraido or '')

    if chave_cache and chave_cache in cache:
        resultado = cache[chave_cache]
        if resultado and resultado != bairro_extraido:
            print(f"  📍 Bairro (cache): '{bairro_extraido}' → '{resultado}'")
        return resultado or bairro_extraido or ''

    # Passo 1: match contra lista oficial
    if bairro_extraido:
        oficial, score = _match_bairro_oficial(bairro_extraido)
        if oficial:
            if score < 1.0:
                print(f"  📍 Bairro corrigido: '{bairro_extraido}' → '{oficial}' ({score:.0%})")
            if chave_cache:
                cache[chave_cache] = oficial
            cache[_normalizar_bairro(bairro_extraido)] = oficial
            _cv_save()
            return oficial

    # Passo 2: busca web SOMENTE quando há nome de edifício/condomínio identificável
    # Não buscar com texto genérico (causa chamadas desnecessárias e respostas erradas)
    referencia = None
    if edificio and len(edificio.strip()) > 3:
        referencia = f"Edifício/condomínio: {edificio}. Cidade: Maringá-PR."
        if texto_completo:
            referencia += f"\nTexto: {texto_completo[:200]}"

    if referencia:
        print(f"  🔎 Bairro '{bairro_extraido or '?'}' não reconhecido — buscando via web...")
        bairro_web = _buscar_bairro_web(referencia)
        if bairro_web:
            oficial, score = _match_bairro_oficial(bairro_web)
            resultado = oficial if oficial else bairro_web
            print(f"  📍 Bairro via web: '{bairro_extraido}' → '{resultado}'")
            if chave_cache:
                cache[chave_cache] = resultado
            _cv_save()
            return resultado

    # Não confirmado — manter original e cachear para não buscar de novo
    if chave_cache:
        cache[chave_cache] = bairro_extraido or ''
        _cv_save()
    return bairro_extraido or ''

# ─── Cache de locais (bairro vs condomínio) ──────────────────────────────────
CACHE_LOCAIS_FILE = BASE_DIR / "cache_locais.json"

def _carregar_cache_locais():
    if CACHE_LOCAIS_FILE.exists():
        try: return json.load(open(CACHE_LOCAIS_FILE, encoding='utf-8'))
        except: pass
    return {}

def _salvar_cache_locais(cache):
    with open(CACHE_LOCAIS_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def classificar_local(nome):
    """
    Usa Claude Haiku para descobrir se um nome é bairro ou condomínio/edifício.
    Resultado armazenado em cache_locais.json para não repetir a consulta.
    Retorna dict: {'tipo': 'bairro'|'condominio'|'outro', 'nome': str, 'bairro_real': str|None}
    Efeito colateral: se for condomínio novo, adiciona a _CONDOS_NOVOS para pesquisa posterior.
    """
    if not nome or len(nome.strip()) < 3:
        return {'tipo': 'outro', 'nome': nome, 'bairro_real': None}

    cache = _carregar_cache_locais()
    chave = nome.strip().lower()
    if chave in cache:
        resultado = cache[chave]
        # Mesmo em cache: se é condomínio, verificar se ainda não foi pesquisado
        if resultado.get('tipo') == 'condominio' and f"_pesq_{chave}" not in cache:
            _CONDOS_NOVOS.add(resultado.get('nome', nome))
        return resultado

    api_key = _api_key()
    if not api_key:
        return {'tipo': 'outro', 'nome': nome, 'bairro_real': None}

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            f'Em Maringá-PR, o nome "{nome}" se refere a:\n'
            f'1) Um bairro ou zona oficial da cidade\n'
            f'2) Um condomínio, edifício ou empreendimento imobiliário\n'
            f'3) Outro (cidade, rua, etc)\n\n'
            f'Se for condomínio/edifício, em qual bairro de Maringá fica?\n\n'
            f'Responda SOMENTE JSON válido:\n'
            f'{{"tipo":"bairro"|"condominio"|"outro",'
            f'"nome":"nome mais completo/oficial se souber",'
            f'"bairro_real":"bairro onde fica (se condomínio) ou null"}}'
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        m = re.search(r'\{.*\}', resp.content[0].text, re.DOTALL)
        if m:
            resultado = json.loads(m.group())
            cache[chave] = resultado
            _salvar_cache_locais(cache)
            tipo = resultado.get('tipo', 'outro')
            nome_resultado = resultado.get('nome', nome)
            print(f"  🗺️  '{nome}' → {tipo.upper()}: {nome_resultado}"
                  + (f" (bairro: {resultado['bairro_real']})" if resultado.get('bairro_real') else ""))
            # Se for condomínio novo → agendar pesquisa detalhada
            if tipo == 'condominio':
                _CONDOS_NOVOS.add(nome_resultado)
            return resultado
    except Exception as e:
        print(f"  ⚠️  classificar_local: {e}")

    resultado = {'tipo': 'outro', 'nome': nome, 'bairro_real': None}
    cache[chave] = resultado
    _salvar_cache_locais(cache)
    return resultado


# ─── Pesquisa de condomínios (web search via Claude) ─────────────────────────

def _condos_ja_no_db():
    """Retorna set com nomes (lowercase) dos condomínios já cadastrados no SQLite."""
    try:
        with db.db_conn() as conn:
            nomes = db.listar_condominios_nomes(conn)
        return {n.lower().strip() for n in nomes}
    except:
        return set()


def pesquisar_condominio(nome, cidade="Maringá-PR"):
    """
    Pesquisa dados completos de um condomínio via Claude Sonnet + web_search.
    Retorna dict com informações ou None se já pesquisado/erro.
    """
    api_key = _api_key()
    if not api_key:
        return None

    cache = _carregar_cache_locais()
    chave_pesq = f"_pesq_{nome.strip().lower()}"
    if chave_pesq in cache:
        print(f"  🏗️  '{nome}' já pesquisado anteriormente (cache)")
        return None

    print(f"  🔎 Pesquisando condomínio '{nome}' em {cidade}...")

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        prompt = (
            f'Pesquise o empreendimento/condomínio "{nome}" em {cidade}.\n'
            f'Quero informações completas para cadastro imobiliário.\n\n'
            f'Retorne SOMENTE JSON válido (sem markdown, sem texto extra):\n'
            f'{{\n'
            f'  "nome": "nome completo oficial",\n'
            f'  "endereco": "rua e número",\n'
            f'  "bairro": "bairro em Maringá",\n'
            f'  "cep": "00000-000 ou null",\n'
            f'  "construtora": "nome da construtora/incorporadora",\n'
            f'  "ano_lancamento": "YYYY ou null",\n'
            f'  "previsao_entrega": "YYYY ou null",\n'
            f'  "padrao": "Econômico|Médio Padrão|Alto Padrão|Luxo",\n'
            f'  "torres": "número de torres ou null",\n'
            f'  "andares": "número de andares ou null",\n'
            f'  "total_aptos": "total de apartamentos ou null",\n'
            f'  "area_min": número_em_m2_ou_null,\n'
            f'  "area_max": número_em_m2_ou_null,\n'
            f'  "quartos": "ex: 2 e 3 quartos",\n'
            f'  "vagas": "ex: 1 a 2 vagas",\n'
            f'  "lazer": "lista separada por vírgula: piscina, academia, salão...",\n'
            f'  "faixa_preco": "ex: R$350.000 a R$550.000",\n'
            f'  "observacoes": "informações adicionais relevantes",\n'
            f'  "link": "URL principal do empreendimento"\n'
            f'}}'
        )

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
            messages=[{"role": "user", "content": prompt}]
        )

        # Extrair texto (ignorar tool_use blocks)
        text = ""
        for block in resp.content:
            if hasattr(block, 'text'):
                text += block.text

        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            info = json.loads(m.group())
            # Marcar como pesquisado no cache
            cache[chave_pesq] = True
            _salvar_cache_locais(cache)
            print(f"  ✅ Dados obtidos para '{info.get('nome', nome)}'")
            return info

    except Exception as e:
        print(f"  ⚠️  pesquisar_condominio('{nome}'): {e}")

    return None


def trim_specs_condo(row):
    """Reduz a linha COMPLETA da tabela condominios às specs usadas pra preencher imóveis."""
    if not row:
        return None
    quartos_raw = str(row.get('quartos') or '')
    nums_q = re.findall(r'\d+', quartos_raw)
    quartos = int(nums_q[0]) if nums_q else None
    def toint(v):
        try: return int(float(v)) if v else None
        except: return None
    return {
        'nome':     row.get('nome'),
        'bairro':   row.get('bairro') or None,
        'area_min': toint(row.get('area_min')),
        'quartos':  quartos,
        'vagas':    toint(row.get('vagas')),
        'padrao':   row.get('padrao') or None,
    }

def buscar_condo_completo(nome):
    """Busca a linha INTEIRA de condominios (todas as colunas) pelo nome. Retorna dict ou None."""
    if not nome:
        return None
    try:
        with db.db_conn() as conn:
            return db.buscar_specs_condo(conn, nome)
    except Exception as e:
        print(f"  ⚠️  buscar_condo_completo: {e}")
        return None

def condo_incompleto(row):
    """
    True se o registro só tem o nome (ex: os ~13.700 importados em bloco do
    GeoMaringá, que vieram sem construtora/área/padrão/andares) — candidato a
    ser completado via pesquisa web.
    """
    if not row:
        return True
    return not (row.get('area_min') or row.get('construtora') or row.get('padrao') or row.get('andares'))

def buscar_specs_condo(nome):
    """Busca specs resumidas (area_min, quartos, vagas, bairro, padrao) de um condomínio. Ou None."""
    return trim_specs_condo(buscar_condo_completo(nome))

# ── Prédio/edifício vertical vs condomínio residencial horizontal (casas) ────
#
# Só vale a pena pesquisar/padronizar specs (torres, andares, área, lazer...)
# pra PRÉDIOS — cada casa de um condomínio residencial tem um tamanho/planta
# diferente, não existe "a specs do condomínio X" nesse caso.
_RE_EDIFICIO_EXPLICITO = re.compile(r'\bedif[íi]cio\b|^ed\.?\s', re.IGNORECASE)
_RE_CONDO_HORIZONTAL = re.compile(
    r'condom[íi]nio\s*resid|cond\.?\s*resid|\bcond\.?\s*res\.?\b|'
    r'conjunto\s*resid|conj\.?\s*resid|\bconj\.?\s*res\.?\b|'
    r'loteamento|\bsobrados?\b|\bch[áa]caras?\b|residencial\s+e\s+comercial',
    re.IGNORECASE
)

def eh_provavel_edificio(nome):
    """
    Heurística: 'Edifício X' ou nome limpo (ex: Atmosphere, Vision) → prédio.
    'X, CONDOMÍNIO RESIDENCIAL' / 'COND.RES.' / 'CONJ.RES.' → casas, não prédio.
    """
    if not nome:
        return False
    n = nome.strip()
    if _RE_EDIFICIO_EXPLICITO.search(n):
        return True
    if _RE_CONDO_HORIZONTAL.search(n):
        return False
    return True

def atualizar_aba_condominios(info, atualizar_se_existir=False):
    """
    Insere condomínio novo no SQLite, ou — se atualizar_se_existir=True e o
    nome já existe — completa a linha existente (usado quando o cadastro
    estava incompleto, ex: import bruto do GeoMaringá) sem criar duplicata.
    """
    from datetime import datetime

    nome = str(info.get('nome', '') or '').strip()
    if not nome:
        return

    linha_existente = buscar_condo_completo(nome)

    def _toint(v):
        try: return int(float(v)) if v else None
        except: return None
    def _tofloat(v):
        try: return float(v) if v else None
        except: return None

    valores = (
        info.get('endereco') or None,
        info.get('bairro') or None,
        info.get('cep') or None,
        info.get('construtora') or None,
        info.get('ano_lancamento') or None,
        info.get('previsao_entrega') or None,
        info.get('padrao') or None,
        _toint(info.get('torres')),
        _toint(info.get('andares')),
        _toint(info.get('total_aptos')),
        _tofloat(info.get('area_min')),
        _tofloat(info.get('area_max')),
        str(info.get('quartos') or '') or None,
        _toint(info.get('vagas')),
        info.get('lazer') or None,
        info.get('faixa_preco') or None,
        info.get('observacoes') or None,
        info.get('link') or None,
        datetime.now().strftime('%d/%m/%Y %H:%M'),
    )

    with db.db_conn() as conn:
        if linha_existente:
            if not atualizar_se_existir:
                print(f"  ⏭️  '{nome}' já está em condominios")
                return
            # Mantém o nome original (chave de match) e completa o resto
            conn.execute("""
                UPDATE condominios SET
                    endereco=?, bairro=?, cep=?, construtora=?, ano_lancamento=?,
                    previsao_entrega=?, padrao=?, torres=?, andares=?, total_aptos=?,
                    area_min=?, area_max=?, quartos=?, vagas=?, lazer=?, faixa_preco=?,
                    observacoes=?, site_link=?, data_cadastro=?
                WHERE id=?
            """, valores + (linha_existente['id'],))
            print(f"  🏗️  Condomínio '{nome}' completado no SQLite (estava incompleto)")
        else:
            conn.execute("""
                INSERT INTO condominios
                    (nome, endereco, bairro, cep, construtora, ano_lancamento,
                     previsao_entrega, padrao, torres, andares, total_aptos,
                     area_min, area_max, quartos, vagas, lazer, faixa_preco,
                     observacoes, site_link, data_cadastro)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (nome,) + valores)
            print(f"  🏗️  Condomínio '{nome}' cadastrado no SQLite")

# Nomes geográficos que NÃO são bairros (cidade, estado, país)
_NAO_BAIRRO = {
    'maringá', 'maringa', 'londrina', 'curitiba', 'são paulo', 'sao paulo',
    'brasil', 'brazil', 'paraná', 'parana', 'pr',
}

def _expandir_abreviaturas(texto):
    """Expande abreviações comuns de bairros para facilitar a busca."""
    t = texto
    t = re.sub(r'\bJD\.\s*', 'Jardim ', t, flags=re.IGNORECASE)
    t = re.sub(r'\bRES\.\s*', 'Residencial ', t, flags=re.IGNORECASE)
    t = re.sub(r'\bCOND\.\s*', 'Condomínio ', t, flags=re.IGNORECASE)
    t = re.sub(r'\bPQ\.\s*', 'Parque ', t, flags=re.IGNORECASE)
    t = re.sub(r'\bAV\.\s*', 'Avenida ', t, flags=re.IGNORECASE)
    return t

def extrair_bairro(texto, todos=False):
    """
    todos=False → retorna o bairro mais relevante (para imóveis).
    todos=True  → retorna TODOS os bairros/regiões encontrados, separados por ' · ' (para demandas).
    """
    # Expandir abreviações e normalizar plural "Zonas" → "Zona"
    texto_exp = _expandir_abreviaturas(texto)
    texto_exp = re.sub(r'\bZonas\b', 'Zona', texto_exp, flags=re.IGNORECASE)
    tl = texto_exp.lower()

    # 0. Padrão do título: "Tipo à Venda – Bairro | Cidade"
    m_titulo = re.search(
        r'(?:venda|aluguel|locação)\s*[–\-—]+\s*([A-ZÀ-Ú][A-Za-zÀ-ú\s]{2,40}?)\s*\|',
        texto_exp, re.IGNORECASE)
    if m_titulo:
        candidato = m_titulo.group(1).strip()
        if candidato.lower() not in _NAO_BAIRRO and 2 < len(candidato) < 45:
            if not todos:
                return BAIRROS_LOWER.get(candidato.lower(), candidato)
            # em modo todos: registra mas continua buscando mais

    if todos:
        # ── Modo demanda: encontrar TODOS os bairros/regiões no texto ──────────
        encontrados = []
        vistos = set()

        # Passo 1: "Zona(s) 01, 03, 07 e 08" → cada número vira "Zona XX"
        for m_z in re.finditer(r'\bZona(?:s)?\s+(\d+(?:\s*[,e]\s*\d+)*)', texto_exp, re.IGNORECASE):
            for num in re.findall(r'\d+', m_z.group(1)):
                bl = f"zona {int(num):02d}"
                if bl in BAIRROS_LOWER and BAIRROS_LOWER[bl] not in vistos:
                    encontrados.append(BAIRROS_LOWER[bl])
                    vistos.add(BAIRROS_LOWER[bl])

        # Passo 2: varredura direta por bairros conhecidos (mais longo primeiro)
        for bl, b in sorted(BAIRROS_LOWER.items(), key=lambda x: -len(x[0])):
            if bl in tl and b not in vistos:
                encontrados.append(b)
                vistos.add(b)

        if encontrados:
            return ' · '.join(encontrados)

        # Passo 3: padrão contextual "região/bairro do/da NOME"
        # Captura apenas palavras que começam com maiúscula (para não engolir o resto da frase)
        for m_ctx in re.finditer(
            r'(?:região|regiao|bairro)\s+(?:do|da|de|dos|das)\s+'
            r'([A-ZÀ-Ú][a-zA-ZÀ-ú]+(?:\s+[A-ZÀ-Ú][a-zA-ZÀ-ú]+)*)',
            texto_exp
        ):
            c = m_ctx.group(1).strip()
            if 2 < len(c) < 40 and c.lower() not in _NAO_BAIRRO:
                if c.lower() in BAIRROS_LOWER:
                    return BAIRROS_LOWER[c.lower()]
                # Tentar prefixo "Jardim X" (ex: "regiao do Dias" → "Jardim Dias")
                jardim = f"jardim {c.lower()}"
                if jardim in BAIRROS_LOWER:
                    return BAIRROS_LOWER[jardim]
        return ''

    # ── Modo imóvel: retornar primeiro/mais relevante ───────────────────────────
    # 1. Verificar lista de bairros conhecidos
    for bl, b in BAIRROS_LOWER.items():
        if bl in tl:
            return b
    # 2. Padrão contextual
    m = re.search(
        r'(?:no|na|em|bairro|condomínio|cond\.?|edifício|ed\.?|residencial|região)\s+'
        r'([A-ZÀ-Ú0-9][a-zA-ZÀ-ú0-9\s]{2,35}?)(?:\s*[-–,.]|\s*$|\s*\n)',
        texto_exp)
    if m:
        c = m.group(1).strip()
        if c.lower() in _NAO_BAIRRO:
            return ''
        if 2 < len(c) < 40:
            if c.lower() in BAIRROS_LOWER:
                return BAIRROS_LOWER[c.lower()]
            info = classificar_local(c)
            if info['tipo'] == 'bairro':
                return info.get('nome', c)
            elif info['tipo'] == 'condominio':
                bairro_real = info.get('bairro_real')
                if bairro_real:
                    return f"Cond. {info.get('nome', c)} · {bairro_real}"
                return f"Cond. {info.get('nome', c)}"
    return ''

def extrair_edificio(texto):
    """Extrai nome de edifício/condomínio mencionado explicitamente no texto."""
    # 1. Padrão com prefixo: "edifício X", "condomínio X", "residencial X"
    m = re.search(
        r'(?:edifício|ed\.|condomínio|cond\.|residencial)\s+([A-ZÀ-Ú][A-Za-zÀ-ú\s]{2,35}?)(?:\s*[·\-,\.]|\s*\d+[oOºª]|\s*$|\n)',
        texto, re.IGNORECASE
    )
    if m:
        nome = m.group(1).strip().rstrip('·-.,')
        if 2 < len(nome) < 40:
            return nome

    # 2. Nome de edifício no início do texto sem prefixo (ex: "Urban Yticon, 23º andar...")
    #    Captura 1-4 palavras capitalizadas antes de vírgula, traço ou número de andar
    m2 = re.match(
        r'^([A-ZÀ-Ú][A-Za-zÀ-ú]+(?:\s+[A-ZÀ-Ú][A-Za-zÀ-ú]+){0,3})\s*(?:,|\.|[–\-]|\d+[oOºª])',
        texto.strip()
    )
    if m2:
        nome = m2.group(1).strip()
        _nao_edificio = {'apartamento', 'apto', 'casa', 'terreno', 'venda', 'aluguel',
                         'ótima', 'lindo', 'excelente', 'bom', 'boa', 'oportunidade',
                         'imóvel', 'imovel', 'sobrado', 'cobertura', 'studio'}
        if nome.lower() not in _nao_edificio and 3 < len(nome) < 45:
            return nome

    # 2b. Código de empreendimento: 3+ letras maiúsculas + dígitos (ex: NEST635, PARK900, MRV123)
    m3 = re.search(r'\b([A-Z]{3,}\d+[A-Z0-9]*)\b', texto)
    if m3:
        nome = m3.group(1)
        if 4 <= len(nome) <= 20:
            return nome

    # 2c. Nome próprio após "com", "busco", "busca" em contexto de demanda
    #     Ex: "alguém com Vista Bela", "busco Residencial das Flores"
    m4 = re.search(
        r'(?:\bcom\b|\bbusco\b|\bbusca\b|\bquero\b|\bdo\b|\bda\b)\s+'
        r'([A-ZÀ-Ú][A-Za-zÀ-ú0-9]+(?:\s+[A-ZÀ-Ú][A-Za-zÀ-ú0-9]+){0,3})'
        r'(?:\s+de\s|\s+com\s|\s*[,\.\n]|$)',
        texto
    )
    if m4:
        candidato = m4.group(1).strip()
        _nao_edificio_ctx = {
            'apartamento', 'apto', 'casa', 'imóvel', 'imovel', 'terreno',
            'cliente', 'comprador', 'área', 'quartos', 'suítes', 'vaga',
            'preferência', 'piscina', 'lazer',
        }
        if candidato.lower() not in _nao_edificio_ctx and 3 < len(candidato) < 40:
            return candidato

    # 3. Fallback: verificar se algum condomínio cadastrado no DB aparece no texto.
    #    Exclui nomes curtos demais e nomes iguais a cidade/estado (ex: existe um
    #    condomínio chamado literalmente "MARINGÁ" no import do GeoMaringá — sem
    #    esse filtro, toda mensagem que menciona a cidade "casava" com ele).
    try:
        with db.db_conn() as conn:
            nomes_condos = db.listar_condominios_nomes(conn)
        tl = texto.lower()
        for n in nomes_condos:
            n = str(n or '').strip()
            nl = n.lower()
            if not n or len(n) <= 5 or nl in _NAO_BAIRRO:
                continue
            if nl in tl:
                return n
    except:
        pass

    return None

def extrair_campos(texto, pesquisar_condo_imediato=False, eh_demanda=False):
    """
    Extrai campos do texto da mensagem.
    pesquisar_condo_imediato=True: se o condomínio não estiver no DB,
    pesquisa na web na hora (usado para demandas, para preencher specs antes de salvar).
    eh_demanda=True: extrai todos os bairros/regiões mencionados (não só o primeiro).
    """
    edificio = extrair_edificio(texto)
    condo_specs = None

    # Se achou nome de edifício → buscar specs direto no DB (rápido)
    if edificio:
        condo_row = buscar_condo_completo(edificio)
        condo_specs = trim_specs_condo(condo_row)
        precisa_completar = condo_row is None or condo_incompleto(condo_row)

        if precisa_completar:
            # Tentar classificação via IA pra confirmar que é mesmo um condomínio
            # e pegar o nome mais "oficial" possível
            info_local = classificar_local(edificio)
            nome_condo = info_local.get('nome', edificio)

            # Código de empreendimento (ex: NEST635, PARK900) — forçar como condomínio
            # mesmo que a IA não reconheça, pois esses padrões são sempre empreendimentos
            eh_codigo = bool(re.match(r'^[A-Z]{3,}\d+', edificio))
            parece_condo = info_local.get('tipo') == 'condominio' or eh_codigo

            if parece_condo and not condo_row:
                # Pode estar cadastrado sob o nome "oficial" devolvido pela IA
                condo_row = buscar_condo_completo(nome_condo)
                condo_specs = trim_specs_condo(condo_row)
                precisa_completar = condo_row is None or condo_incompleto(condo_row)

            # Só vale pesquisar/completar specs padronizados pra PRÉDIOS — um
            # condomínio residencial de casas não tem "specs padrão" pra buscar.
            if parece_condo and precisa_completar and eh_provavel_edificio(nome_condo):
                if pesquisar_condo_imediato:
                    motivo = "incompleto" if condo_row else "não cadastrado"
                    print(f"  🔎 '{nome_condo}' {motivo} — pesquisando na web...")
                    info_pesq = pesquisar_condominio(nome_condo)
                    if info_pesq:
                        atualizar_aba_condominios(info_pesq, atualizar_se_existir=bool(condo_row))
                        condo_specs = buscar_specs_condo(nome_condo)
                elif not condo_row:
                    # Defer para o final (fluxo normal de venda)
                    _CONDOS_NOVOS.add(nome_condo)

    # Extração direta da mensagem
    campos = {
        'tipo':      extrair_tipo(texto),
        'bairro':    extrair_bairro(texto, todos=eh_demanda),
        'edificio':  edificio,
        'area':      extrair_area(texto),
        'quartos':   extrair_num(texto, [r'quartos?', r'dormit[oó]rios?', r'dorm\.?']),
        'suites':    extrair_num(texto, [r'su[íi]tes?']),
        'banheiros': extrair_num(texto, [r'banheiros?', r'\bwc\b', r'lavabo']),
        'vagas':     extrair_num(texto, [r'vagas?', r'garagens?']),
        'preco':     extrair_preco(texto),
    }

    # Completar campos faltantes com specs do condomínio (mensagem tem prioridade)
    if condo_specs:
        if not campos['tipo'] or campos['tipo'] == 'Imóvel':
            campos['tipo'] = 'Apartamento'  # edifícios são sempre apartamentos
        if not campos['bairro'] and condo_specs.get('bairro'):
            campos['bairro'] = condo_specs['bairro']
            print(f"  🏗️  Bairro do condo '{edificio}': {condo_specs['bairro']}")
        if not campos['area'] and condo_specs.get('area_min'):
            campos['area'] = condo_specs['area_min']
            print(f"  🏗️  Área do condo '{edificio}': {condo_specs['area_min']}m²")
        if not campos['quartos'] and condo_specs.get('quartos'):
            campos['quartos'] = condo_specs['quartos']
            print(f"  🏗️  Quartos do condo '{edificio}': {condo_specs['quartos']}")
        if not campos['vagas'] and condo_specs.get('vagas'):
            campos['vagas'] = condo_specs['vagas']
            print(f"  🏗️  Vagas do condo '{edificio}': {condo_specs['vagas']}")

    # ── Validar / corrigir bairro contra lista oficial de Maringá ──────────────
    # Para demandas com múltiplos bairros (separados por ' · '), valida cada um
    if campos.get('bairro') and ' · ' in str(campos['bairro']):
        partes = [p.strip() for p in campos['bairro'].split(' · ') if p.strip()]
        validados = []
        for p in partes:
            v = validar_bairro(p, texto_completo=texto, edificio='')
            validados.append(v)
        campos['bairro'] = ' · '.join(dict.fromkeys(validados))  # deduplica mantendo ordem
    else:
        campos['bairro'] = validar_bairro(
            campos.get('bairro', ''),
            texto_completo=texto,
            edificio=campos.get('edificio', '') or ''
        )

    validar_campos_numericos(campos)
    return campos

# Faixas aceitáveis pra cada campo numérico — fora disso, foi erro de extração
_FAIXAS_NUMERICAS = {
    'quartos':   (1, 10),
    'suites':    (0, 10),
    'banheiros': (0, 15),
    'vagas':     (0, 10),
}
# Área tem faixa própria por tipo. Só usa a faixa apertada (prédio) quando o
# tipo é CONFIRMADAMENTE residencial compacto — terreno/chácara/sítio/galpão/
# sala comercial variam demais, e "Imóvel" (fallback genérico, tipo não
# identificado com certeza) também fica na faixa larga por segurança: é
# melhor deixar passar um exagero raro do que apagar um terreno de verdade.
_TIPOS_RESIDENCIAL_COMPACTO = {
    'apartamento', 'casa', 'sobrado', 'kitnet', 'studio', 'cobertura', 'flat',
}
_FAIXA_AREA_PREDIO   = (10, 3_000)
_FAIXA_AREA_TERRENO  = (10, 500_000)

def validar_campos_numericos(campos):
    """
    Anula (vira None) qualquer campo numérico fora da faixa plausível pra um
    imóvel residencial/comercial em Maringá, e corrige inconsistências simples
    entre quartos/suítes. Modifica `campos` in-place.
    """
    for campo, (minimo, maximo) in _FAIXAS_NUMERICAS.items():
        valor = campos.get(campo)
        if valor is None:
            continue
        try:
            valor_num = float(valor)
        except (TypeError, ValueError):
            campos[campo] = None
            continue
        if not (minimo <= valor_num <= maximo):
            print(f"  ⚠️  {campo}={valor} fora da faixa plausível ({minimo}-{maximo}) — descartado")
            campos[campo] = None

    area = campos.get('area')
    if area is not None:
        try:
            area_num = float(area)
        except (TypeError, ValueError):
            campos['area'] = None
            area_num = None
        if area_num is not None:
            tipo_norm = str(campos.get('tipo') or '').strip().lower()
            minimo, maximo = _FAIXA_AREA_PREDIO if tipo_norm in _TIPOS_RESIDENCIAL_COMPACTO else _FAIXA_AREA_TERRENO
            if not (minimo <= area_num <= maximo):
                print(f"  ⚠️  area={area} fora da faixa plausível pra {campos.get('tipo') or '?'} ({minimo}-{maximo}) — descartado")
                campos['area'] = None

    # Suítes não podem passar do total de quartos (sinal de extração errada)
    quartos, suites = campos.get('quartos'), campos.get('suites')
    if quartos is not None and suites is not None and suites > quartos:
        print(f"  ⚠️  suítes ({suites}) > quartos ({quartos}) — suítes descartadas")
        campos['suites'] = None

    return campos

def tem_dados(c):
    return any([c.get('preco'), c.get('area'), c.get('quartos'), c.get('suites'), c.get('vagas')])

# ─── Agrupamento: fotos + texto do mesmo corretor = 1 imóvel ─────────────────

def agrupar_mensagens(pendentes):
    """
    Agrupa mensagens próximas no tempo do mesmo autor no mesmo grupo.
    Retorna lista de pacotes — cada pacote = 1 imóvel.
    """
    if not pendentes:
        return []

    ordenadas = sorted(enumerate(pendentes), key=lambda x: x[1].get('timestamp', 0))
    usadas = set()
    pacotes = []

    for idx_orig, msg in ordenadas:
        if idx_orig in usadas:
            continue

        ts = msg.get('timestamp', 0)
        pacote_idxs = [idx_orig]
        usadas.add(idx_orig)

        for idx2, outro in ordenadas:
            if idx2 in usadas:
                continue
            if (outro['autor'] == msg['autor'] and
                outro['grupo'] == msg['grupo'] and
                abs(outro.get('timestamp', 0) - ts) <= JANELA_AGRUPAMENTO):
                pacote_idxs.append(idx2)
                usadas.add(idx2)

        msgs_pacote = [pendentes[i] for i in pacote_idxs]
        # Melhor contato: primeiro não-vazio de todo o pacote
        melhor_contato = next(
            (m.get('contato', '') for m in msgs_pacote if m.get('contato')),
            ''
        )
        pacotes.append({
            'idxs': pacote_idxs,
            'msgs': msgs_pacote,
            'autor': msg['autor'],
            'grupo': msg['grupo'],
            'data':  msg.get('data', ''),
            'contato': melhor_contato,
        })

    return pacotes

def resolver_pacote(pacote):
    """
    De um pacote de mensagens (texto + fotos), extrai os dados do imóvel.
    Regra: se o texto tem dados → usa o texto, ignora imagens.
           se só tem imagens → analisa UMA imagem com Claude.
    Retorna (campos, obs, classe) ou None se não for imóvel.
    """
    msgs = pacote['msgs']

    # Juntar todo o texto do pacote
    textos = [m.get('texto', '') for m in msgs if m.get('texto')]
    texto_completo = '\n'.join(textos).strip()

    # Classificar pelo texto
    classe = classificar(texto_completo) if texto_completo else 'indefinido'

    # Extrair campos do texto
    # Pesquisa o edifício/condomínio na hora sempre que ele aparecer e não estiver
    # cadastrado, pra já vir com bairro/specs corretos antes de gravar.
    eh_demanda = (classe == 'demanda')
    campos = extrair_campos(texto_completo, pesquisar_condo_imediato=True, eh_demanda=eh_demanda) if texto_completo else None

    link_usado = None

    # ── Corretor mandou o link do anúncio? Buscar a página e completar os dados ──
    campos_incompletos = (not campos) or (not tem_dados(campos)) or not campos.get('bairro') or not campos.get('preco')
    if campos_incompletos:
        links = extrair_links(texto_completo)
        if links:
            print(f"  🔗 Link encontrado na mensagem — buscando dados em {links[0]}")
            info_link = analisar_link(links[0], texto_completo, pacote['autor'])
            if info_link:
                if campos is None:
                    campos = {
                        'tipo': info_link.get('tipo', 'Imóvel'), 'bairro': info_link.get('bairro') or '',
                        'edificio': info_link.get('edificio'), 'area': None, 'quartos': None,
                        'suites': None, 'banheiros': None, 'vagas': None, 'preco': None,
                    }
                # Texto digitado pelo corretor tem prioridade; o link só preenche o que faltou
                for campo_k in ('tipo', 'bairro', 'edificio', 'area', 'quartos', 'suites', 'banheiros', 'vagas', 'preco'):
                    if not campos.get(campo_k) and info_link.get(campo_k):
                        campos[campo_k] = info_link[campo_k]
                if campos.get('bairro'):
                    campos['bairro'] = validar_bairro(campos['bairro'], texto_completo=texto_completo, edificio=campos.get('edificio') or '')
                validar_campos_numericos(campos)
                link_usado = links[0]
                campos['link'] = link_usado

    # Demanda citando um edifício/condomínio específico é válida mesmo sem
    # conseguir extrair preço/área — "preciso de algo no Evidence" já diz o
    # suficiente pra virar lead; não descartar só por falta de número.
    dados_suficientes = campos and (
        tem_dados(campos) or (classe == 'demanda' and campos.get('edificio'))
    )
    if dados_suficientes:
        # Dados suficientes (texto e/ou link) → não precisa analisar imagem
        obs = limpar_obs(texto_completo[:300])
        if link_usado and link_usado not in obs:
            # Link primeiro: db.slug_from_obs() usa a 1ª palavra pra deduplicar por URL
            obs = f"{link_usado} {obs}".strip()
        return campos, obs, classe

    # Texto/link insuficientes → tentar UMA imagem (a primeira com arquivo salvo)
    img_msgs = [m for m in msgs if m.get('imagemPath') and Path(m['imagemPath']).exists()]
    if img_msgs:
        img_msg = img_msgs[0]  # só analisar a primeira
        n_imgs = len(img_msgs)
        print(f"  🔍 Claude analisa 1 imagem de {n_imgs} [{pacote['autor']}]")
        resultado = analisar_imagem(img_msg['imagemPath'], texto_completo, pacote['autor'])
        if resultado and resultado.get('eh_imovel'):
            campos = {
                'tipo':      resultado.get('tipo', 'Imóvel'),
                'bairro':    resultado.get('bairro') or '',
                'area':      resultado.get('area'),
                'quartos':   resultado.get('quartos'),
                'suites':    resultado.get('suites'),
                'banheiros': resultado.get('banheiros'),
                'vagas':     resultado.get('vagas'),
                'preco':     resultado.get('preco'),
            }
            validar_campos_numericos(campos)
            # Só inserir se tiver pelo menos 1 dado concreto (preço, área, quartos...)
            if not tem_dados(campos):
                print(f"     ⏭️  Imagem de imóvel sem dados concretos — ignorando")
                return None
            obs = limpar_obs(resultado.get('obs', '') or texto_completo[:300])
            if classe == 'indefinido':
                classe = 'venda'
            print(f"     ✅ {campos['tipo']} | {campos.get('bairro') or '?'} | R${campos.get('preco')}")
            return campos, obs, classe
        # Claude confirmou que não é imóvel, ou não conseguiu analisar → pular
        return None

    # Imagem sem arquivo local (download falhou ou não suportado) → pular sem criar placeholder
    return None  # sem dados suficientes

# ─── Deduplicação ─────────────────────────────────────────────────────────────

def fazer_fp(autor, bairro, preco, area, texto, timestamp=None):
    autor = str(autor or '').lower().strip()
    bairro = str(bairro or '').lower().strip()
    # Normalizar para int para evitar "480000" vs "480000.0" do Excel vs do Claude
    try:   preco = int(float(preco)) if preco else 0
    except: preco = 0
    try:   area = int(float(area)) if area else 0
    except: area = 0
    texto_curto = str(texto or '')[:80].lower().strip()

    if bairro and preco:       return f"{autor}|{bairro}|{preco}"
    elif preco and area:       return f"{autor}|{preco}|{area}"
    elif preco:                return f"{autor}|{preco}"
    elif texto_curto:          return f"{autor}|txt:{texto_curto}"
    elif timestamp:            return f"{autor}|ts:{int(timestamp)}"  # fallback: autor+timestamp
    return None  # último recurso: não deduplica

# ─── Fingerprints a partir do SQLite ────────────────────────────────────────

def fp_imoveis():
    """Carrega fingerprints de imóveis do SQLite para deduplicação."""
    try:
        with db.db_conn() as conn:
            rows = conn.execute(
                "SELECT corretor, bairro, preco, area, observacoes FROM imoveis"
            ).fetchall()
        fps = set()
        for r in rows:
            autor  = r["corretor"] or ''
            bairro = r["bairro"] or ''
            preco  = r["preco"]
            area   = r["area"]
            obs    = r["observacoes"] or ''
            fp_com = fazer_fp(autor, bairro, preco, area, obs)
            fp_sem = fazer_fp(autor, '',     preco, area, obs)
            if fp_com: fps.add(fp_com)
            if fp_sem: fps.add(fp_sem)
        return fps
    except: return set()

def fp_demandas():
    """Carrega fingerprints de demandas do SQLite para deduplicação."""
    try:
        with db.db_conn() as conn:
            rows = conn.execute(
                "SELECT corretor, bairro_regiao, orcamento_max, area_min, observacoes FROM demandas"
            ).fetchall()
        fps = set()
        for r in rows:
            autor  = r["corretor"] or ''
            bairro = r["bairro_regiao"] or ''
            preco  = r["orcamento_max"]
            area   = r["area_min"]
            obs    = r["observacoes"] or ''
            fp_com = fazer_fp(autor, bairro, preco, area, obs)
            fp_sem = fazer_fp(autor, '',     preco, area, obs)
            if fp_com: fps.add(fp_com)
            if fp_sem: fps.add(fp_sem)
        return fps
    except: return set()

# ─── Inserção no SQLite ──────────────────────────────────────────────────────

def inserir_linhas_imoveis(linhas):
    """Insere lista de linhas (ordem: COLUNAS_IMOVEIS) no SQLite."""
    db.init_db()
    with db.db_conn() as conn:
        for ln in linhas:
            # ln: data_captura, grupo, corretor, contato, tipo, bairro, area,
            #     quartos, suites, banheiros, vagas, preco, obs, status, data_pub
            db.inserir_imovel(conn, {
                "data_captura":    ln[0],
                "grupo":           ln[1],
                "corretor":        ln[2],
                "contato":         ln[3],
                "tipo":            ln[4],
                "bairro":          ln[5],
                "area":            ln[6],
                "quartos":         ln[7],
                "suites":          ln[8],
                "banheiros":       ln[9],
                "vagas":           ln[10],
                "preco":           ln[11],
                "observacoes":     ln[12],
                "status":          ln[13] if len(ln) > 13 else "Novo",
                "data_publicacao": ln[14] if len(ln) > 14 else None,
            })

def inserir_linhas_demandas(linhas):
    """Insere lista de linhas (ordem: COLUNAS_DEMANDAS) no SQLite."""
    db.init_db()
    with db.db_conn() as conn:
        fps_existentes = db.carregar_fps_demandas(conn)
        for ln in linhas:
            # ln: data, grupo, corretor, contato, tipo_buscado, bairro, area_min,
            #     quartos, suites, banheiros, vagas, orcamento_max, obs, status
            item = {
                "data":           ln[0],
                "grupo":          ln[1],
                "corretor":       ln[2],
                "contato":        ln[3],
                "tipo_buscado":   ln[4],
                "bairro_regiao":  ln[5],
                "area_min":       ln[6],
                "quartos":        ln[7],
                "suites":         ln[8],
                "banheiros":      ln[9],
                "vagas":          ln[10],
                "orcamento_max":  ln[11],
                "observacoes":    ln[12],
                "status":         ln[13] if len(ln) > 13 else "Ativo",
            }
            fp = fazer_fp(ln[2], ln[5], ln[11], ln[6], ln[12])
            if fp and fp in fps_existentes:
                continue
            db.inserir_demanda(conn, item, fp)
            if fp:
                fps_existentes.add(fp)

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not FILA_FILE.exists():
        print("Fila vazia — bot Baileys ainda não capturou mensagens.")
        return

    with open(FILA_FILE, 'r', encoding='utf-8') as f:
        fila = json.load(f)

    pendentes = [m for m in fila if not m.get('processado')]
    print(f"📬 {len(pendentes)} mensagens pendentes (total: {len(fila)})\n")

    if VER_FILA:
        for i, m in enumerate(pendentes, 1):
            cls = classificar(m.get('texto',''))
            ic = '🏠' if cls=='venda' else '🔍' if cls=='demanda' else '❓'
            print(f"── {i}. {ic} [{m['grupo']}] {m['autor']} ({m.get('data','')})")
            img = f" + 🖼️" if m.get('temImagem') else ""
            print(f"   {m.get('texto','(imagem)')[:150]}{img}\n")
        return

    # Agrupar por autor + grupo + tempo
    pacotes = agrupar_mensagens(pendentes)
    print(f"📦 {len(pacotes)} pacotes agrupados (era {len(pendentes)} msgs individuais)\n")

    fps_v = fp_imoveis()
    fps_d = fp_demandas()
    novas_vendas, novas_demandas = [], []
    sem_dados = duplicatas = 0

    for pacote in pacotes:
        resultado = resolver_pacote(pacote)

        # Marcar todas as mensagens do pacote como processadas
        for idx in pacote['idxs']:
            fila[idx]['processado'] = True

        if resultado is None:
            sem_dados += 1
            continue

        campos, obs, classe = resultado

        ts0 = pacote['msgs'][0].get('timestamp') if pacote['msgs'] else None

        if classe == 'demanda':
            fp = fazer_fp(pacote['autor'], campos.get('bairro',''), campos.get('preco'), campos.get('area'), obs, ts0)
            if fp and fp in fps_d:
                duplicatas += 1
                continue
            # Validar contato: LIDs (>13 dígitos) não são telefones reais
            contato_raw = str(pacote.get('contato') or '').replace('.', '').replace(' ', '')
            contato_ok = contato_raw if (contato_raw.isdigit() and 10 <= len(contato_raw) <= 13) else ''
            if not contato_ok and campos.get('link'):
                # Sem WhatsApp válido — usa o link do anúncio como contato/fonte
                contato_ok = campos['link']
            linha = [
                pacote['data'], pacote['grupo'], pacote['autor'], contato_ok,
                campos['tipo'], campos.get('bairro',''), campos.get('area'),
                campos.get('quartos'), campos.get('suites'), campos.get('banheiros'),
                campos.get('vagas'), campos.get('preco'), obs, 'Nova'
            ]
            novas_demandas.append(linha)
            fps_d.add(fp or f"{pacote['autor']}|ts:{ts0}")

            if DRY_RUN:
                n = len(pacote['msgs'])
                print(f"🔍 DEMANDA ({n} msgs) | {campos['tipo']} | {campos.get('bairro') or '?'} | orç. R${campos.get('preco')}")
                print(f"   [{pacote['grupo']}] {pacote['autor']}\n")

        else:  # venda ou indefinido
            fp = fazer_fp(pacote['autor'], campos.get('bairro',''), campos.get('preco'), campos.get('area'), obs, ts0)
            if fp and fp in fps_v:
                duplicatas += 1
                continue
            contato_raw = str(pacote.get('contato') or '').replace('.', '').replace(' ', '')
            contato_ok = contato_raw if (contato_raw.isdigit() and 10 <= len(contato_raw) <= 13) else ''
            if not contato_ok and campos.get('link'):
                # Sem WhatsApp válido — usa o link do anúncio como contato/fonte
                contato_ok = campos['link']
            linha = [
                pacote['data'], pacote['grupo'], pacote['autor'], contato_ok,
                campos['tipo'], campos.get('bairro',''), campos.get('area'),
                campos.get('quartos'), campos.get('suites'), campos.get('banheiros'),
                campos.get('vagas'), campos.get('preco'), obs, 'Novo', ''
            ]
            novas_vendas.append(linha)
            fps_v.add(fp or f"{pacote['autor']}|ts:{ts0}")

            if DRY_RUN:
                n = len(pacote['msgs'])
                print(f"🏠 VENDA ({n} msgs→1) | {campos['tipo']} | {campos.get('bairro') or '?'} | "
                      f"{campos.get('area')}m² | R${campos.get('preco')}")
                print(f"   [{pacote['grupo']}] {pacote['autor']}\n")

    if not DRY_RUN:
        if novas_vendas:
            inserir_linhas_imoveis(novas_vendas)
        if novas_demandas:
            inserir_linhas_demandas(novas_demandas)

        with open(FILA_FILE, 'w', encoding='utf-8') as f:
            json.dump(fila, f, ensure_ascii=False, indent=2)

    print(f"\n{'[DRY-RUN] ' if DRY_RUN else ''}✅ {len(novas_vendas)} imóveis inseridos → SQLite imoveis")
    print(f"{'[DRY-RUN] ' if DRY_RUN else ''}🔍 {len(novas_demandas)} demandas inseridas → SQLite demandas")
    print(f"   ↳ {duplicatas} duplicatas ignoradas")
    print(f"   ↳ {sem_dados} pacotes sem dados de imóvel")

    # ── Pesquisar e cadastrar condomínios novos encontrados nesta execução ──────
    if not DRY_RUN and _CONDOS_NOVOS:
        ja_na_planilha = _condos_ja_no_db()
        novos_para_pesquisar = [n for n in _CONDOS_NOVOS if n.lower() not in ja_na_planilha]
        if novos_para_pesquisar:
            print(f"\n🏗️  Pesquisando {len(novos_para_pesquisar)} condomínio(s) novo(s)...")
            for nome_condo in novos_para_pesquisar:
                info = pesquisar_condominio(nome_condo)
                if info:
                    atualizar_aba_condominios(info)

if __name__ == '__main__':
    main()
