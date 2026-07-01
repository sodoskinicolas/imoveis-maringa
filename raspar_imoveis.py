#!/usr/bin/env python3
"""
raspar_imoveis.py
Raspa todos os sites de imobiliárias de Maringá, identifica imóveis novos
e insere no SQLite (imoveis.db) com Status="Novo".

Uso manual:
  python3 raspar_imoveis.py
  python3 raspar_imoveis.py --dry-run   # mostra o que faria, sem salvar

Agendado via LaunchAgent para rodar às 3h da manhã.
"""

import re
import sys
import json
import time
import logging
import argparse
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import db
from processar_mensagens import (
    validar_bairro, validar_campos_numericos, extrair_edificio,
    buscar_specs_condo, buscar_condo_completo, condo_incompleto,
    eh_provavel_edificio, pesquisar_condominio, atualizar_aba_condominios,
)

# ── Configuração ──────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
LOG_FILE  = BASE_DIR / "raspar_imoveis.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
})

# ── Helpers de parsing ────────────────────────────────────────────────────────

def fix_enc(s):
    """Corrige mojibake latin-1 em UTF-8 (Sub100 e outros CMSs)."""
    if not s:
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except Exception:
        return s

def parse_area(s):
    if not s:
        return None
    m = re.search(r"([\d.,]+)\s*m", s.replace(" ", ""))
    if not m:
        return None
    try:
        return float(m.group(1).replace(".", "").replace(",", "."))
    except ValueError:
        return None

def parse_preco(s):
    if not s or "Consulte" in s or "consulte" in s:
        return None
    m = re.search(r"[\d.,]+", s.replace(" ", "").replace("R$", ""))
    if not m:
        return None
    try:
        return int(float(m.group().replace(".", "").replace(",", ".")))
    except ValueError:
        return None

def parse_int(s):
    if not s or not str(s).strip():
        return None
    m = re.match(r"(\d+)", str(s).strip())
    if not m:
        return None
    v = int(m.group(1))
    # Evitar artefatos de número de apartamento (ex: 101, 1302)
    return v if 0 < v <= 20 else None

def infer_tipo(s):
    s = (s or "").lower()
    # Tipos mais específicos primeiro para evitar falsos positivos
    if "sobrado" in s:                                      return "Sobrado"
    if "kitnet" in s or "kit net" in s or "studio" in s or "flat" in s: return "Kitnet"
    if "cobertura" in s:                                    return "Apartamento"
    if "apart" in s or "apto" in s:                        return "Apartamento"
    if "edif" in s or "andar" in s:                        return "Apartamento"
    if "chácara" in s or "chacara" in s:                   return "Chácara"
    if "sítio" in s or "sitio" in s:                       return "Sítio"
    if "galpão" in s or "galpao" in s:                     return "Galpão"
    if "terreno" in s or "lote" in s:                      return "Terreno"
    if "sala" in s or "comercial" in s or "loja" in s:     return "Sala Comercial"
    if "casa" in s:                                         return "Casa"
    return "Imóvel"

def slug(url):
    """Extrai o identificador único da URL (último segmento não-vazio)."""
    parts = [p for p in url.rstrip("/").split("/") if p]
    return parts[-1] if parts else url

def get_page(url, ajax=False, retries=3, delay=2):
    headers = {}
    if ajax:
        headers["X-Requested-With"] = "XMLHttpRequest"
    for attempt in range(retries):
        try:
            r = SESSION.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            return r
        except Exception as e:
            log.warning(f"  Tentativa {attempt+1}/{retries} falhou: {url} → {e}")
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
    return None


# ── Sub100 CMS (Haraki, Massaru, Bellakaza, Silvio Iwata, Casa do Corretor) ──
#
# Todos os 5 sites são construídos na mesma plataforma Sub100 (confirmado pelo
# rodapé "Desenvolvedor: Sub100 Sistemas" em cada um). Cada tenant, porém, tem
# sua própria configuração de URLs — silvioiwata.com.br mudou de
# "/imoveis-a-venda" pra "/imoveis/venda/{categoria}/{cidade}-pr" em algum
# momento e quebrou o scraper (410 Gone); o mesmo aconteceu antes com
# Haraki/Massaru/Bellakaza. Por isso não fixamos mais slugs de categoria à mão
# — descobrir_categorias_venda() lê a home do site e extrai as URLs de
# categoria reais que estão publicadas ali, o que sobrevive a mudanças de
# slug sem precisar de manutenção manual.
SUB100_SITES = [
    {"domain": "harakiimoveis.com.br",    "grupo": "Haraki Imóveis"},
    {"domain": "massaruimoveis.com.br",   "grupo": "Massaru Imóveis"},
    {"domain": "bellakaza.com.br",        "grupo": "Bellakaza"},
    {"domain": "silvioiwata.com.br",      "grupo": "Silvio Iwata"},
    {"domain": "casadocorretormga.com.br","grupo": "Casa do Corretor"},
]

# Carregar sites descobertos automaticamente pelo descobrir_sites.py
_SITES_EXTRAS_FILE = Path(__file__).parent / "sites_extras.json"
try:
    if _SITES_EXTRAS_FILE.exists():
        _extras = json.loads(_SITES_EXTRAS_FILE.read_text('utf-8'))
        _sub100_extras = [s for s in _extras if s.get('_tipo') == 'sub100']
        if _sub100_extras:
            SUB100_SITES.extend(_sub100_extras)
            log.info(f"sites_extras.json: {len(_sub100_extras)} site(s) Sub100 adicionado(s)")
except Exception as _e:
    log.warning(f"Erro ao carregar sites_extras.json: {_e}")


def parse_sub100_block(html_block, base_domain):
    """
    Extrai dados de um bloco HTML de listagem Sub100 (resposta AJAX).

    Detecção de tipo — ordem de prioridade:
      1. URL slug do item: /venda/sobrado-em-maringa/ → tipo mais confiável
      2. og:title / <title> / <h1-4>  (só presentes na página individual)
    """
    # ── Ref / URL ─────────────────────────────────────────────────────────────
    # Tenants Sub100 diferentes usam estruturas de URL diferentes pro item:
    #   Haraki/Massaru/Bellakaza:  /imovel/8020000829/venda/sobrado-em-maringa/bairro
    #   Silvio Iwata/Casa do Corretor: /imovel/3620005920/apartamento-a-venda/bairro
    # Tentamos os dois formatos, mais dois fallbacks genéricos pra qualquer
    # variação futura: pegar só o ID de qualquer /imovel/{id}/, ou o número
    # (com zeros à esquerda) solto no texto do bloco.
    full_url_m  = re.search(r'/imovel/(\d{7,12})/venda/([^"\'>\s]+)', html_block)
    alt_url_m   = re.search(r'/imovel/(\d{7,12})/([a-z][a-z-]*?)-a-venda/', html_block, re.I)
    bare_url_m  = re.search(r'/imovel/(\d{7,12})/', html_block)
    short_url_m = re.search(r'/imovel/(0{3,}\d+)/', html_block)
    text_ref_m  = re.search(r'\b(0{3,}\d{2,})\b', html_block)

    if full_url_m:
        raw_ref   = full_url_m.group(1)   # ex: 8020000829
        url_slug  = full_url_m.group(2)   # ex: sobrado-em-maringa/jardim-everest
    elif alt_url_m:
        raw_ref   = alt_url_m.group(1)    # ex: 3620005920
        url_slug  = alt_url_m.group(2)    # ex: apartamento, casa-em-condominio
    elif bare_url_m:
        raw_ref  = bare_url_m.group(1)
        url_slug = ""
    elif short_url_m:
        raw_ref  = short_url_m.group(1)
        url_slug = ""
    elif text_ref_m:
        raw_ref  = text_ref_m.group(1)
        url_slug = ""
    else:
        return None

    # Normalizar ref para 8 dígitos (remover prefixo de cliente ex: 802)
    if len(raw_ref) > 8 and not raw_ref.startswith('0'):
        raw_ref = raw_ref[3:].zfill(8)
    ref  = raw_ref
    link = f"https://{base_domain}/imovel/{ref}/"

    # ── Tipo ──────────────────────────────────────────────────────────────────
    # 1ª opção: slug da URL do item (mais confiável — ex: "sobrado-em-maringa")
    tipo = None
    if url_slug:
        # slug começa com o tipo: "sobrado-em-", "casa-em-", "apartamento-em-", etc.
        slug_first = url_slug.split("/")[0]   # ex: "sobrado-em-maringa"
        tipo = infer_tipo(slug_first)

    # 2ª opção: og:title / <title> / <h1-4> (presentes quando bloco é página individual)
    if not tipo or tipo == "Imóvel":
        for pat in [
            r'og:title["\s]+content="([^"]+)"',
            r'<title>([^<]+)</title>',
            r'<h[1-4][^>]*>([^<]+)</h[1-4]>',
        ]:
            m = re.search(pat, html_block, re.I)
            if m:
                tipo = infer_tipo(fix_enc(m.group(1).strip()))
                if tipo and tipo != "Imóvel":
                    break

    tipo = tipo or "Imóvel"

    # ── Demais campos ─────────────────────────────────────────────────────────
    area_m  = re.search(r'([\d.,]+)\s*m[²2]', html_block)
    preco_m = re.search(r'R\$\s*[\d.,]+', html_block.replace("\xa0", " "))
    qtos_m  = re.search(r'(\d+)\s*(?:quarto|dorm)', html_block, re.I)
    ban_m   = re.search(r'(\d+)\s*(?:banheiro|ban\.)', html_block, re.I)
    vaga_m  = re.search(r'(\d+)\s*(?:vaga|garagem)', html_block, re.I)
    bairro_m = re.search(
        r'(?:localiza[çc][aã]o|bairro)[^<]*?([A-ZÀ-Ú][a-zà-ú\s]+(?:Zona\s+\d+)?)',
        html_block, re.I
    )
    bairro = fix_enc(bairro_m.group(1).strip()) if bairro_m else ""

    return {
        "ref":       ref,
        "link":      link,
        "tipo":      tipo,
        "bairro":    bairro,
        "area":      parse_area(fix_enc(area_m.group(0))) if area_m else None,
        "quartos":   parse_int(qtos_m.group(1))  if qtos_m  else None,
        # Sub100 só expõe contagem de banheiro no card, não suíte — antes isso
        # estava sendo gravado por engano na coluna "suites".
        "banheiros": parse_int(ban_m.group(1))   if ban_m   else None,
        "suites":    None,
        "vagas":     parse_int(vaga_m.group(1))  if vaga_m  else None,
        "preco":     parse_preco(preco_m.group(0)) if preco_m else None,
        "obs":       link,
    }

def descobrir_categorias_venda(domain):
    """
    Descobre as URLs de categoria de venda publicadas na home do site Sub100,
    em vez de confiar em slugs fixos — eles já mudaram pelo menos duas vezes
    nesses sites (foi exatamente isso que quebrou o scraper: "/imoveis-a-venda"
    virou "/imoveis/venda/{categoria}/{cidade}-pr", com categorias que variam
    por tenant: "casas-ou-sobrados" num site, "casas"+"sobrados" separados em
    outro, etc). Ler direto da home sobrevive a essas mudanças sem manutenção.

    Exclui variantes por bairro (.../imoveis/venda/apartamentos/10-maringa-pr
    /143-bairros), que são subconjuntos redundantes da própria categoria.

    O sufixo de cidade (/10-maringa-pr) é OPCIONAL — a Casa do Corretor, por
    exemplo, publica as categorias sem ele (/imoveis/venda/casas-ou-sobrados,
    sem cidade), provavelmente por atuar numa cidade só.
    """
    base = f"https://{domain}"
    r = get_page(base)
    categorias = []
    if r:
        vistas = set()
        for m in re.finditer(
            r'href=["\'](?:https?://[^"\']*?)?(/imoveis/venda/[a-z0-9-]+(?:/\d+-[a-z-]+-pr)?)["\']',
            r.text,
        ):
            path = m.group(1)
            if path in vistas:
                continue
            vistas.add(path)
            categorias.append(f"{base}{path}")
    return categorias


# Delimitadores conhecidos de "fim de card" em páginas Sub100 — tentados em
# ordem até um deles produzir uma divisão real (mais de ~3 blocos). Tenants
# diferentes usam textos de botão diferentes: Haraki/Massaru/Bellakaza usam
# "Contate agora", Silvio Iwata usa "CONTATAR". Sem o delimitador certo, a
# página inteira vira 1 bloco só e só o primeiro imóvel é extraído — foi
# exatamente isso que fazia Silvio Iwata/Casa do Corretor renderem só 1
# imóvel por página em vez de ~10.
_DELIMITADORES_CARD = [
    r'Contate\s+agora',
    r'CONTATAR',
    r'(?=Ref\.:?\s*\d{4,})',   # fallback genérico: quebra antes de cada "Ref.: NNNN"
]

def _split_blocks_sub100(html):
    for pat in _DELIMITADORES_CARD:
        blocks = re.split(pat, html, flags=re.I)
        if len(blocks) >= 2:   # delimitador realmente bateu pelo menos 1 vez
            return blocks
    return [html]


def _raspar_listagem_sub100(url_base, domain, seen_refs, nome_grupo, max_paginas=80):
    """
    Raspa uma URL de listagem Sub100 (categoria ou página combinada),
    paginando até não achar mais imóveis novos.

    Manda os dois nomes de parâmetro de paginação conhecidos (pagina= e
    page=) porque tenants Sub100 diferentes usam nomes diferentes — o
    framework ignora o que não reconhece, então não custa nada mandar os
    dois de uma vez em vez de adivinhar qual esse site em particular usa.
    """
    items = []
    page = 1
    while page <= max_paginas:
        if page == 1:
            url = url_base
        else:
            sep = "&" if "?" in url_base else "?"
            url = f"{url_base}{sep}pagina={page}&page={page}"
        r = get_page(url)
        if not r:
            break

        html = r.text
        if not re.search(r'/imovel/\d+', html):
            break

        blocks = _split_blocks_sub100(html)
        found = 0
        for block in blocks:
            item = parse_sub100_block(block, domain)
            if not item or item["ref"] in seen_refs:
                continue
            seen_refs.add(item["ref"])
            items.append(item)
            found += 1

        rotulo = url_base.rsplit("/imoveis/venda", 1)[-1] or "/imoveis/venda"
        log.info(f"[{nome_grupo}] {rotulo} — página {page}: {found} imóveis")
        if found == 0:
            break
        page += 1
        time.sleep(1.0)

    return items


def scrape_sub100(cfg):
    """
    Raspa um site Sub100 (config em SUB100_SITES: domain + grupo). Vale para
    os 5 sites — Haraki, Massaru, Bellakaza, Silvio Iwata e Casa do Corretor
    são todos construídos na mesma plataforma (rodapé "Sub100 Sistemas").

    Estratégia: descobre as URLs de categoria publicadas na própria home
    (descobrir_categorias_venda) e raspa cada uma com paginação, mais a
    página combinada /imoveis/venda como fonte extra — funciona em alguns
    tenants (ex. Silvio Iwata lista tudo ali junto) e é inofensiva nos que
    não suportam (só retorna vazio). Dedup por ref dentro do site inteiro via
    seen_refs, então rodar a combinada depois das categorias não duplica nada.

    O tipo de cada imóvel vem do slug da URL do PRÓPRIO item
    (parse_sub100_block), não da categoria — mais confiável, já que algumas
    categorias vêm combinadas (ex: "casas-ou-sobrados").
    """
    domain     = cfg["domain"]
    nome_grupo = cfg["grupo"]
    base       = f"https://{domain}"

    seen_refs = set()
    items     = []

    categorias = descobrir_categorias_venda(domain)
    if categorias:
        log.info(f"[{nome_grupo}] {len(categorias)} categoria(s) encontrada(s) na home")
    else:
        log.warning(f"[{nome_grupo}] Nenhuma categoria encontrada na home — só vou tentar a página combinada")

    for url_cat in categorias:
        items.extend(_raspar_listagem_sub100(url_cat, domain, seen_refs, nome_grupo))
        time.sleep(1.0)

    # Página combinada — cobertura extra, sem custo se o tenant não suportar
    items.extend(_raspar_listagem_sub100(f"{base}/imoveis/venda", domain, seen_refs, nome_grupo))

    from collections import Counter
    tipos = Counter(it["tipo"] for it in items)
    log.info(f"[{nome_grupo}] Total: {len(items)} imóveis | {dict(tipos)}")
    return items


# ── Lélo Imóveis (plataforma CasaSoft) ────────────────────────────────────────
#
# Site diferente do Sub100 — plataforma "CasaSoft" (rodapé "Sistema CasaSoft -
# Feito pela Paper"). Totalmente renderizado no servidor (HTML puro já traz
# tudo), sem AJAX/JS necessário. Paginação é por path, não por query string:
# /imoveis/venda-pagina-{N} (confirmado no link real "Próxima página" da
# página 1, via Chrome — não é um parâmetro adivinhado).
#
# Cada card é um <a href="https://www.leloimoveis.com.br/imovel/{slug}/{id-
# empresa}/{ref}">conteúdo do card inteiro</a> — usamos a própria tag como
# delimitador de card, o que é mais confiável que tentar adivinhar um texto
# de botão (como fizemos pro Sub100).
#
# O título de cada card segue um padrão bem consistente (é o alt-text das
# fotos, repetido 2-3x por card): "{Tipo} para venda no {Bairro} em {Cidade}
# com {area}m² por R$ {preco}" — dá pra extrair tipo/bairro/cidade/área/preço
# de uma vez só com uma regex, em vez de vários campos separados feito no
# Sub100. Cobre Maringá e cidades vizinhas (Sarandi, Mandaguaçu, Marialva) —
# filtramos só Maringá aqui pra manter o escopo do projeto.
LELO_BASE = "https://www.leloimoveis.com.br"

_LELO_TITULO_RE = re.compile(
    r'([\wÀ-ÿ ]+?)\s+para venda no\s+([\wÀ-ÿ.\'° ]+?)\s+em\s+(\w+)\s+'
    r'com\s+([\d.,]+)\s*m[²2]\s+por\s+R\$\s*([\d.,]+)',
    re.I,
)

def parse_lelo_card(html_block, href):
    ref = href.rstrip("/").rsplit("/", 1)[-1]
    slug_path = href.split("/imovel/", 1)[-1].split("/")[0] if "/imovel/" in href else ""
    tipo = infer_tipo(slug_path)

    bairro = cidade = ""
    area = preco = None
    m_tit = _LELO_TITULO_RE.search(html_block)
    if m_tit:
        if tipo == "Imóvel":
            tipo = infer_tipo(m_tit.group(1))
        bairro = m_tit.group(2).strip()
        cidade = m_tit.group(3).strip()
        area = parse_area(m_tit.group(4) + "m2")
        preco = parse_preco("R$ " + m_tit.group(5))

    # Fallback caso o padrão do título não bata (ex: card sem foto/alt-text)
    if area is None:
        area_m = re.search(r'([\d.,]+)\s*m[²2]', html_block)
        area = parse_area(area_m.group(0)) if area_m else None
    if preco is None:
        preco_m = re.search(r'R\$\s*[\d.,]+', html_block)
        preco = parse_preco(preco_m.group(0)) if preco_m else None

    qtos_m = re.search(r'(\d+)\s*quartos?', html_block, re.I)
    suite_m = re.search(r'(\d+)\s*su[ií]tes?', html_block, re.I)
    vaga_m = re.search(r'(\d+)\s*vagas?', html_block, re.I)

    return {
        "ref": ref,
        "link": href,
        "tipo": tipo,
        "bairro": bairro,
        "cidade": cidade,
        "area": area,
        "quartos": parse_int(qtos_m.group(1)) if qtos_m else None,
        "suites": parse_int(suite_m.group(1)) if suite_m else None,
        "banheiros": None,
        "vagas": parse_int(vaga_m.group(1)) if vaga_m else None,
        "preco": preco,
        "obs": href,
    }


def scrape_lelo(max_paginas=60):
    items = []
    seen = set()
    page = 1
    while page <= max_paginas:
        url = f"{LELO_BASE}/imoveis/venda" if page == 1 else f"{LELO_BASE}/imoveis/venda-pagina-{page}"
        r = get_page(url)
        if not r:
            break
        html = r.text
        matches = list(re.finditer(
            r'<a\s+href="(https://www\.leloimoveis\.com\.br/imovel/[^"]+)"[^>]*>', html
        ))
        if not matches:
            break

        novos_pagina = 0
        for i, m in enumerate(matches):
            href = m.group(1)
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else start + 4000
            item = parse_lelo_card(html[start:end], href)
            if not item["ref"] or item["ref"] in seen:
                continue
            seen.add(item["ref"])
            novos_pagina += 1
            if item.get("cidade") and "maring" not in item["cidade"].lower():
                continue
            items.append(item)

        log.info(f"[Lélo Imóveis] página {page}: {novos_pagina} imóveis novos")
        if novos_pagina == 0:
            break
        page += 1
        time.sleep(1.0)

    log.info(f"[Lélo Imóveis] Total: {len(items)} imóveis (Maringá)")
    return items


# ── Opção Imóveis (plataforma Flip CRM / Next.js) ─────────────────────────────
#
# Site em Next.js — os cards são renderizados via JS (botões sem href, não dá
# pra raspar como HTML estático comum), MAS a página 1 vem com todos os dados
# já embutidos como JSON dentro de <script id="__NEXT_DATA__"> no HTML puro
# (confirmado via requests simples, sem precisar de navegador). Isso cobre 30
# dos ~349 imóveis à venda em Maringá.
#
# Páginas seguintes: o site pagina via um endpoint interno
# (imobiliariasiteapi.eurekalabs.com.br/search-imoveis) que exige um
# parâmetro de "tenant" que não é passado na URL nem em headers óbvios — é
# injetado pelo bundle JS do próprio site de um jeito que não consegui
# extrair de forma limpa (e não persegui isso mais a fundo: seria efetivamente
# extrair uma credencial/token embutido só pra contornar uma validação de
# acesso, o que preferi não fazer). Também tentei achar um endpoint
# "/_next/data/{buildId}/..." com parâmetros de página alternativos
# (pagina, offset, skip) sem sucesso. Por ora só cobrimos a página 1 — dá pra
# revisitar se aparecer uma forma legítima de paginar (ex: API pública
# documentada, ou mudança no site que exponha os links de paginação como
# href normal).
OPCAO_BASE = "https://www.opcaoimoveis.com.br"

def scrape_opcao():
    items = []
    url = f"{OPCAO_BASE}/buscar/maringa-pr-brasil/venda"
    r = get_page(url)
    if not r:
        return items

    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if not m:
        log.warning("[Opção Imóveis] __NEXT_DATA__ não encontrado na página")
        return items
    try:
        data = json.loads(m.group(1))
        imoveis = data["props"]["pageProps"]["initialBuscarData"]["imoveis"]
    except Exception as e:
        log.warning(f"[Opção Imóveis] Erro ao ler __NEXT_DATA__: {e}")
        return items

    for it in imoveis:
        ref = it.get("codigo") or ""
        if not ref:
            continue
        det = it.get("detalhes") or {}
        preco = it.get("precoVenda")
        imovel_url = it.get("imovelUrl") or ""
        items.append({
            "ref": ref,
            "link": urljoin(OPCAO_BASE + "/imovel/", imovel_url) if imovel_url else url,
            "tipo": infer_tipo(it.get("tipoImovel", "")),
            "bairro": it.get("bairro", ""),
            "cidade": it.get("cidade", ""),
            "area": det.get("areaConstruida"),
            "quartos": det.get("dormitorios"),
            "suites": det.get("suites"),
            "banheiros": None,
            "vagas": det.get("vagas"),
            "preco": int(preco) if preco else None,
            "obs": it.get("titulo", ""),
        })

    log.info(
        f"[Opção Imóveis] {len(items)} imóveis coletados (só página 1 de ~12 — "
        f"ver nota no código sobre a limitação de paginação)"
    )
    return items


# ── Patrimônio Imóveis Prontos (plataforma Kurole) ────────────────────────────
#
# Mesma plataforma do CRM que o Nicolas já usa internamente (Kurole), mas
# esta é a instalação pública de um concorrente — raspamos como fonte externa
# normal. Cobre Maringá E Londrina misturados na mesma listagem; filtramos só
# Maringá. Paginação confirmada via clique real no link "2" da página (não
# adivinhada): query string "&pag={N}" — outros nomes de parâmetro tentados
# antes ("pagina", "page") não tinham efeito nenhum.
PATRIMONIO_BASE = "https://www.patrimonioimoveisprontos.com.br"
PATRIMONIO_SEARCH = (
    f"{PATRIMONIO_BASE}/pesquisa-de-imoveis/"
    "?locacao_venda=V&finalidade=&dormitorio=&garagem=&vmi=&vma=&ordem=3"
)

def parse_patrimonio_card(html_block, href):
    ref_m = re.search(r'/(\d+)$', href)
    ref = ref_m.group(1) if ref_m else ""

    # URL: comprar/{Cidade}/{Tipo}/{SubTipo}/{Bairro}/{codigo}
    partes = [p for p in href.split("/") if p]
    tipo_raw = ""
    for i, p in enumerate(partes):
        if p.lower() == "comprar" and i + 2 < len(partes):
            tipo_raw = partes[i + 2]
            break
    tipo = infer_tipo(tipo_raw)

    loc_m = re.search(r'([A-ZÀ-Ú][^\n\-]{1,45}?)\s*-\s*([A-ZÀ-Ú][a-zà-ÿ]+)/PR', html_block)
    bairro = loc_m.group(1).strip() if loc_m else ""
    cidade = loc_m.group(2).strip() if loc_m else ""

    preco_m = re.search(r'R\$\s*[\d.,]+', html_block)
    quartos_m = re.search(r'(\d+)\s*Dorm', html_block, re.I)
    suites_m = re.search(r'(\d+)\s*Su[ií]te', html_block, re.I)
    banho_m = re.search(r'(\d+)\s*Banho', html_block, re.I)
    vaga_m = re.search(r'(\d+)\s*Garage', html_block, re.I)
    area_m = re.search(r'([\d.,]+)\s*m[²2]', html_block)

    return {
        "ref": ref,
        "link": href,
        "tipo": tipo,
        "bairro": bairro,
        "cidade": cidade,
        "area": parse_area(area_m.group(0)) if area_m else None,
        "quartos": parse_int(quartos_m.group(1)) if quartos_m else None,
        "suites": parse_int(suites_m.group(1)) if suites_m else None,
        "banheiros": parse_int(banho_m.group(1)) if banho_m else None,
        "vagas": parse_int(vaga_m.group(1)) if vaga_m else None,
        "preco": parse_preco(preco_m.group(0)) if preco_m else None,
        "obs": href,
    }


def scrape_patrimonio(max_paginas=15):
    items = []
    seen = set()
    page = 1
    while page <= max_paginas:
        url = PATRIMONIO_SEARCH + (f"&pag={page}" if page > 1 else "")
        r = get_page(url)
        if not r:
            break
        html = r.text
        matches = list(re.finditer(r'href="(/?comprar/[^"]+/\d+)"', html))
        if not matches:
            break

        novos_pagina = 0
        for i, m in enumerate(matches):
            href = urljoin(r.url, m.group(1))
            ref_probe = href.rstrip("/").rsplit("/", 1)[-1]
            if ref_probe in seen:
                continue
            seen.add(ref_probe)
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else start + 3000
            item = parse_patrimonio_card(html[start:end], href)
            novos_pagina += 1
            if item.get("cidade") and "maring" not in item["cidade"].lower():
                continue
            items.append(item)

        log.info(f"[Patrimônio Imóveis Prontos] página {page}: {novos_pagina} imóveis novos")
        if novos_pagina == 0:
            break
        page += 1
        time.sleep(1.0)

    log.info(f"[Patrimônio Imóveis Prontos] Total: {len(items)} imóveis (Maringá)")
    return items


# ── Coletar todos ─────────────────────────────────────────────────────────────

# Sites com scraper próprio (fora do padrão Sub100) — cada um com plataforma
# e estrutura de URL completamente diferentes entre si (CasaSoft, Next.js/
# Flip CRM, Kurole). "grupo" aqui é o mesmo domínio usado como `fonte` no
# banco, seguindo a convenção já usada pros 5 sites Sub100.
OUTRAS_FONTES = [
    {"grupo": "leloimoveis.com.br",              "func": scrape_lelo},
    {"grupo": "opcaoimoveis.com.br",              "func": scrape_opcao},
    {"grupo": "patrimonioimoveisprontos.com.br",  "func": scrape_patrimonio},
]


def coletar_todos():
    todos = []

    for cfg in SUB100_SITES:
        try:
            items = scrape_sub100(cfg)
            for it in items:
                it["grupo"] = cfg["domain"]
            todos.extend(items)
        except Exception as e:
            log.error(f"[{cfg['grupo']}] Erro na raspagem: {e}", exc_info=True)
        time.sleep(2)

    for cfg in OUTRAS_FONTES:
        try:
            items = cfg["func"]()
            for it in items:
                it["grupo"] = cfg["grupo"]
            todos.extend(items)
        except Exception as e:
            log.error(f"[{cfg['grupo']}] Erro na raspagem: {e}", exc_info=True)
        time.sleep(2)

    log.info(f"Total coletado (todos os sites): {len(todos)}")
    return todos


# ── Validação e cruzamento com a base (bairros + condominios) ────────────────

def validar_e_completar_item(item, permitir_pesquisa_web=True):
    """
    Cruza o item raspado com nossa base (bairros oficiais + tabela condominios)
    e completa o que estiver faltando:
      1. Tenta identificar o edifício/condomínio citado no bairro/endereço/link.
      2. Se achar um já cadastrado → preenche bairro/área/quartos/vagas vazios.
      3. Se achar um nome de edifício mas ele NÃO estiver cadastrado → pesquisa
         na web (Claude + web_search) e cadastra antes de completar o item.
      4. Valida o bairro contra a lista oficial de Maringá.
      5. Valida as faixas numéricas (quartos/suítes/banheiros/vagas/área).
    Modifica `item` in-place e também retorna.
    """
    texto_ref = " ".join(str(item.get(k) or "") for k in ("bairro", "endereco", "tipo", "obs"))

    edificio = extrair_edificio(texto_ref)
    if edificio:
        condo_row = buscar_condo_completo(edificio)
        # Só pesquisa/completa specs padronizados pra prédios verticais — um
        # condomínio residencial de casas não tem "specs padrão" pra buscar.
        if permitir_pesquisa_web and eh_provavel_edificio(edificio) and (
            condo_row is None or condo_incompleto(condo_row)
        ):
            nome_pesq = (condo_row or {}).get('nome') or edificio
            info = pesquisar_condominio(nome_pesq)
            if info:
                atualizar_aba_condominios(info, atualizar_se_existir=bool(condo_row))
        specs = buscar_specs_condo(edificio)
        if specs:
            if not item.get("bairro") and specs.get("bairro"):
                item["bairro"] = specs["bairro"]
            if not item.get("area") and specs.get("area_min"):
                item["area"] = specs["area_min"]
            if not item.get("quartos") and specs.get("quartos"):
                item["quartos"] = specs["quartos"]
            if not item.get("vagas") and specs.get("vagas"):
                item["vagas"] = specs["vagas"]
        item["edificio"] = edificio

    item["bairro"] = validar_bairro(
        item.get("bairro", ""), texto_completo=texto_ref, edificio=edificio or ""
    )
    validar_campos_numericos(item)
    return item


# ── Sincronização com o banco ─────────────────────────────────────────────────

def atualizar_db(novos_raw, dry_run=False):
    """
    Sincroniza os imóveis raspados no SQLite via upsert por (fonte, ref) —
    mesmo padrão usado pra VivaReal/Junior Joda (ver db.upsert_imovel_externo).

    Cada rodada de scrape é uma fotografia do catálogo atual de cada site:
    imóveis novos são inseridos, os que já existiam são atualizados (com o
    preço antigo preservado em preco_historico se mudou), e os que sumiram
    do site nesta rodada são marcados status='Removido' — em vez do
    comportamento antigo, que só inseria e nunca detectava o que saiu de
    venda/foi vendido.
    """
    db.init_db()
    hoje = date.today().isoformat()

    log.info(f"Itens coletados (todos os sites): {len(novos_raw)}")
    if not novos_raw:
        return 0

    # Validar/cruzar com bairros oficiais + tabela condominios, e completar o
    # que faltar. Em --dry-run não pesquisa na web (evita custo de API só pra
    # testar), mas ainda valida e cruza com o que já está cadastrado.
    log.info("Validando e cruzando com a base (bairros + condominios)...")
    for item in novos_raw:
        validar_e_completar_item(item, permitir_pesquisa_web=not dry_run)

    if dry_run:
        log.info("[DRY-RUN] Nenhuma alteração salva.")
        for it in novos_raw[:10]:
            log.info(f"  {it.get('grupo','')} | {it.get('tipo','')} | {it.get('bairro','')} | {it.get('edificio','') or ''} | {it.get('preco','')} | {it.get('obs','')}")
        return len(novos_raw)

    novos = atualizados = precos_mudaram = 0
    refs_por_fonte = {}

    with db.db_conn() as conn:
        for item in novos_raw:
            fonte = item.get("grupo") or ""
            ref   = item.get("ref") or ""
            if not fonte or not ref:
                continue
            refs_por_fonte.setdefault(fonte, []).append(ref)

            bairro_end = item.get("bairro") or ""
            end = item.get("endereco", "")
            if end:
                bairro_end = f"{bairro_end} · {end}".strip(" ·")
            edificio = item.get("edificio") or ""
            if edificio and edificio.lower() not in bairro_end.lower():
                bairro_end = f"{bairro_end} · Ed. {edificio}".strip(" ·")

            db_item = {
                "ref_externa":     ref,
                "data_captura":    hoje,
                "grupo":           fonte,
                "corretor":        "",
                "contato":         "",
                "tipo":            item.get("tipo", "Imóvel"),
                "bairro":          bairro_end,
                "area":            item.get("area"),
                "quartos":         item.get("quartos"),
                "suites":          item.get("suites"),
                "banheiros":       item.get("banheiros"),
                "vagas":           item.get("vagas"),
                "preco":           item.get("preco"),
                "observacoes":     item.get("obs", ""),
                "status":          "Novo",
                "data_publicacao": hoje,
                "link":            item.get("link", ""),
            }
            acao, _ = db.upsert_imovel_externo(conn, db_item, fonte)
            if acao == "novo":
                novos += 1
            elif acao == "preco_mudou":
                precos_mudaram += 1
            elif acao == "atualizado":
                atualizados += 1

        # Só marca como Removido dentro das fontes que de fato coletamos algo
        # nesta rodada — se um site falhou por completo (0 itens), não
        # queremos apagar o status de tudo que já estava lá por causa disso.
        removidos_total = 0
        for fonte, refs in refs_por_fonte.items():
            removidos_total += db.marcar_ausentes(conn, fonte, refs)

    log.info(
        f"✅ {novos} novos · {atualizados} atualizados · "
        f"{precos_mudaram} com preço alterado · {removidos_total} marcados como Removido"
    )
    return novos


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Raspar imóveis de Maringá")
    parser.add_argument("--dry-run", action="store_true",
                        help="Mostra o que seria sincronizado sem alterar o banco")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info(f"Iniciando raspagem — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.dry_run:
        log.info("** MODO DRY-RUN — nenhuma alteração será salva **")

    todos = coletar_todos()
    novos = atualizar_db(todos, dry_run=args.dry_run)

    log.info(f"Raspagem concluída. Novos: {novos}")
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
