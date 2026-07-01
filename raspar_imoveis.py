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
import time
import logging
import argparse
from datetime import datetime, date
from pathlib import Path

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


# ── Sub100 CMS (Haraki, Massaru, Bellakaza) ──────────────────────────────────
#
# Config por site Sub100.
# pagina_param → parâmetro de paginação (padrão Sub100: "pagina")
# Para adicionar um novo site Sub100, basta incluir uma entrada aqui.
SUB100_SITES = [
    {
        "url":          "https://harakiimoveis.com.br/imoveis-a-venda",
        "domain":       "harakiimoveis.com.br",
        "grupo":        "Haraki Imóveis",
        "pagina_param": "pagina",
    },
    {
        "url":          "https://massaruimoveis.com.br/imoveis-a-venda",
        "domain":       "massaruimoveis.com.br",
        "grupo":        "Massaru Imóveis",
        "pagina_param": "pagina",
    },
    {
        "url":          "https://bellakaza.com.br/imoveis-a-venda",
        "domain":       "bellakaza.com.br",
        "grupo":        "Bellakaza",
        "pagina_param": "pagina",
    },
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
    # AJAX retorna URLs longas: /imovel/8020000829/venda/sobrado-em-maringa/bairro
    # Página individual usa:    /imovel/00000829/
    # Texto do bloco contém:    00000829 (antes de "Contate agora")
    full_url_m = re.search(r'/imovel/(\d{7,12})/venda/([^"\'>\s]+)', html_block)
    short_url_m = re.search(r'/imovel/(0{3,}\d+)/', html_block)
    text_ref_m  = re.search(r'\b(0{3,}\d{2,})\b', html_block)

    if full_url_m:
        raw_ref   = full_url_m.group(1)   # ex: 8020000829
        url_slug  = full_url_m.group(2)   # ex: sobrado-em-maringa/jardim-everest
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

def scrape_sub100(cfg):
    """
    Raspa um site Sub100 usando a config do dicionário `cfg` (ver SUB100_SITES).

    Estratégia definitiva:
      • Usa AJAX (X-Requested-With: XMLHttpRequest) na página geral de listagem.
        Sem AJAX o Sub100 entrega shell HTML vazio (conteúdo é JS-renderizado).
      • O tipo é extraído da URL slug de cada item no bloco AJAX:
          /venda/sobrado-em-maringa/... → Sobrado
          /venda/casa-em-maringa/...   → Casa
        Isso substitui a abordagem de categorias, que era necessária antes mas
        dependia de requests sem AJAX (que não traziam itens).
    """
    domain     = cfg["domain"]
    nome_grupo = cfg["grupo"]
    base_url   = cfg["url"]
    pag_param  = cfg.get("pagina_param", "pagina")

    items     = []
    seen_refs = set()

    log.info(f"[{nome_grupo}] Iniciando raspagem AJAX → {base_url}")
    page = 1
    while True:
        url = f"{base_url}?{pag_param}={page}" if page > 1 else base_url
        r = get_page(url, ajax=True)   # AJAX necessário — sem ele a página é JS-rendered
        if not r:
            log.warning(f"[{nome_grupo}] Falha ao carregar página {page}")
            break

        html = r.text
        if not re.search(r'/imovel/\d+', html):
            break

        blocks = re.split(r'Contate\s+agora', html, flags=re.I)
        found = 0
        for block in blocks:
            item = parse_sub100_block(block, domain)
            if not item or item["ref"] in seen_refs:
                continue
            seen_refs.add(item["ref"])
            items.append(item)
            found += 1

        log.info(f"[{nome_grupo}] Página {page}: {found} imóveis")
        if found == 0:
            break

        soup = BeautifulSoup(html, "html.parser")
        next_btn = (
            soup.find("a", href=re.compile(rf'{pag_param}={page+1}'))
            or soup.find("a", string=re.compile(r"próxima|next|›|»", re.I))
        )
        if not next_btn:
            break
        page += 1
        time.sleep(1.5)

    # Resumo por tipo
    from collections import Counter
    tipos = Counter(it["tipo"] for it in items)
    log.info(f"[{nome_grupo}] Total: {len(items)} imóveis | {dict(tipos)}")
    return items


# ── Silvio Iwata ──────────────────────────────────────────────────────────────

def scrape_silvio():
    log.info("[Silvio Iwata] Iniciando raspagem")
    base = "https://silvioiwata.com.br"
    items = []
    seen = set()
    page = 1

    while True:
        url = f"{base}/imoveis-a-venda?pagina={page}" if page > 1 else f"{base}/imoveis-a-venda"
        r = get_page(url)
        if not r:
            break

        soup = BeautifulSoup(r.text, "html.parser")

        # Procura cards de imóveis — padrão comum em sites imobiliários
        cards = (
            soup.find_all("div", class_=re.compile(r"imovel|property|listing|card", re.I))
            or soup.find_all("article")
        )

        found = 0
        for card in cards:
            link_tag = card.find("a", href=re.compile(r"/imovel/"))
            if not link_tag:
                continue
            link = base + link_tag["href"] if link_tag["href"].startswith("/") else link_tag["href"]
            s = slug(link)
            if s in seen:
                continue
            seen.add(s)

            text = card.get_text(" ", strip=True)
            tipo_tag = card.find(class_=re.compile(r"tipo|categoria|tag", re.I))
            bairro_tag = card.find(class_=re.compile(r"bairro|local|cidade|regi", re.I))

            items.append({
                "ref":     s,
                "link":    link,
                "tipo":    infer_tipo(tipo_tag.get_text() if tipo_tag else text),
                "bairro":  bairro_tag.get_text(strip=True) if bairro_tag else "",
                "area":    parse_area(text),
                "quartos": parse_int(re.search(r"(\d+)\s*quarto", text, re.I) and
                                     re.search(r"(\d+)\s*quarto", text, re.I).group(1)),
                "suites":  parse_int(re.search(r"(\d+)\s*su[íi]te", text, re.I) and
                                     re.search(r"(\d+)\s*su[íi]te", text, re.I).group(1)),
                "vagas":   parse_int(re.search(r"(\d+)\s*vaga", text, re.I) and
                                     re.search(r"(\d+)\s*vaga", text, re.I).group(1)),
                "preco":   parse_preco(re.search(r"R\$\s*[\d.,]+", text.replace("\xa0", " ")) and
                                       re.search(r"R\$\s*[\d.,]+", text.replace("\xa0", " ")).group(0)),
                "obs":     link,
            })
            found += 1

        log.info(f"[Silvio Iwata] Página {page}: {found} imóveis")
        if found == 0:
            break

        next_btn = soup.find("a", string=re.compile(r"próxima|next|»|›", re.I))
        if not next_btn:
            break
        page += 1
        time.sleep(1.5)

    log.info(f"[Silvio Iwata] Total: {len(items)}")
    return items, "silvioiwata.com.br"


# ── Casa do Corretor ──────────────────────────────────────────────────────────

def scrape_casa_corretor():
    log.info("[Casa do Corretor] Iniciando raspagem")
    base = "https://casadocorretormga.com.br"
    items = []
    seen = set()
    page = 1

    while True:
        url = f"{base}/imoveis-a-venda?pagina={page}" if page > 1 else f"{base}/imoveis-a-venda"
        r = get_page(url)
        if not r:
            break

        soup = BeautifulSoup(r.text, "html.parser")
        cards = (
            soup.find_all("div", class_=re.compile(r"imovel|property|listing|card", re.I))
            or soup.find_all("article")
        )

        found = 0
        for card in cards:
            link_tag = card.find("a", href=re.compile(r"/imovel/|/imoveis/"))
            if not link_tag:
                continue
            link = base + link_tag["href"] if link_tag["href"].startswith("/") else link_tag["href"]
            s = slug(link)
            if s in seen:
                continue
            seen.add(s)

            text = card.get_text(" ", strip=True)
            tipo_tag  = card.find(class_=re.compile(r"tipo|categoria|tag", re.I))
            bairro_tag = card.find(class_=re.compile(r"bairro|local|regi", re.I))
            addr_tag   = card.find(class_=re.compile(r"endereco|address|rua", re.I))

            items.append({
                "ref":     s,
                "link":    link,
                "tipo":    infer_tipo(tipo_tag.get_text() if tipo_tag else text),
                "bairro":  fix_enc(bairro_tag.get_text(strip=True) if bairro_tag else ""),
                "endereco": fix_enc(addr_tag.get_text(strip=True) if addr_tag else ""),
                "area":    parse_area(text),
                "quartos": parse_int(re.search(r"(\d+)\s*quarto", text, re.I) and
                                     re.search(r"(\d+)\s*quarto", text, re.I).group(1)),
                "suites":  None,
                "vagas":   parse_int(re.search(r"(\d+)\s*vaga", text, re.I) and
                                     re.search(r"(\d+)\s*vaga", text, re.I).group(1)),
                "preco":   parse_preco(re.search(r"R\$\s*[\d.,]+", text.replace("\xa0", " ")) and
                                       re.search(r"R\$\s*[\d.,]+", text.replace("\xa0", " ")).group(0)),
                "obs":     link,
            })
            found += 1

        log.info(f"[Casa do Corretor] Página {page}: {found} imóveis")
        if found == 0:
            break

        next_btn = soup.find("a", string=re.compile(r"próxima|next|»|›", re.I))
        if not next_btn:
            break
        page += 1
        time.sleep(1.5)

    log.info(f"[Casa do Corretor] Total: {len(items)}")
    return items, "casadocorretormga.com.br"


# ── Coletar todos ─────────────────────────────────────────────────────────────

def coletar_todos():
    todos = []

    # Sub100 (Haraki, Massaru, Bellakaza)
    for cfg in SUB100_SITES:
        try:
            items = scrape_sub100(cfg)
            for it in items:
                it["grupo"] = cfg["domain"]
            todos.extend(items)
        except Exception as e:
            log.error(f"[{cfg['grupo']}] Erro na raspagem: {e}", exc_info=True)
        time.sleep(2)

    # Silvio
    try:
        items, grupo = scrape_silvio()
        for it in items:
            it["grupo"] = grupo
        todos.extend(items)
    except Exception as e:
        log.error(f"[Silvio] Erro: {e}", exc_info=True)

    time.sleep(2)

    # Casa do Corretor
    try:
        items, grupo = scrape_casa_corretor()
        for it in items:
            it["grupo"] = grupo
        todos.extend(items)
    except Exception as e:
        log.error(f"[Casa do Corretor] Erro: {e}", exc_info=True)

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


# ── Deduplicação e import ─────────────────────────────────────────────────────

def atualizar_db(novos_raw, dry_run=False):
    """Deduplica e insere imóveis raspados no SQLite."""
    db.init_db()

    hoje = date.today().isoformat()

    # Carregar slugs e fingerprints existentes para deduplicação em memória
    with db.db_conn() as conn:
        slugs_existentes = db.carregar_slugs(conn)
        fps_existentes   = db.carregar_fps_imoveis(conn)

    novos      = []
    slugs_vis  = set()
    fps_vis    = set()

    for item in novos_raw:
        obs = item.get("obs") or item.get("link", "")
        sl  = db.slug_from_obs(obs)
        bairro = (item.get("bairro") or "").lower().strip()[:20]
        area   = round(item.get("area") or 0, 0)
        preco  = int(item.get("preco") or 0)
        fp = (bairro, area, preco)
        fp_sem = ("", area, preco)

        if sl and (sl in slugs_existentes or sl in slugs_vis):
            continue
        if (fp[0] and fp in fps_existentes) or fp_sem in fps_existentes:
            continue
        if fp in fps_vis or fp_sem in fps_vis:
            continue

        novos.append(item)
        if sl:
            slugs_vis.add(sl)
        fps_vis.add(fp)
        fps_vis.add(fp_sem)

    log.info(f"Imóveis novos: {len(novos)} (de {len(novos_raw)} coletados)")

    if not novos:
        return 0

    # Validar/cruzar com bairros oficiais + tabela condominios, e completar o
    # que faltar. Em --dry-run não pesquisa na web (evita custo de API só pra
    # testar), mas ainda valida e cruza com o que já está cadastrado.
    log.info("Validando e cruzando com a base (bairros + condominios)...")
    for item in novos:
        validar_e_completar_item(item, permitir_pesquisa_web=not dry_run)

    if dry_run:
        log.info("[DRY-RUN] Nenhuma alteração salva.")
        for it in novos[:10]:
            log.info(f"  Novo: {it.get('tipo','')} | {it.get('bairro','')} | {it.get('edificio','') or ''} | {it.get('preco','')} | {it.get('obs','')}")
        return len(novos)

    inseridos = 0
    with db.db_conn() as conn:
        for item in novos:
            bairro_end = item.get("bairro") or ""
            end = item.get("endereco", "")
            if end:
                bairro_end = f"{bairro_end} · {end}".strip(" ·")
            edificio = item.get("edificio") or ""
            if edificio and edificio.lower() not in bairro_end.lower():
                bairro_end = f"{bairro_end} · Ed. {edificio}".strip(" ·")

            ok = db.inserir_imovel(conn, {
                "data_captura":    hoje,
                "grupo":           item.get("grupo", ""),
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
            })
            if ok:
                inseridos += 1

    log.info(f"✅ {inseridos} imóveis novos adicionados no SQLite")
    return inseridos


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Raspar imóveis de Maringá")
    parser.add_argument("--dry-run", action="store_true",
                        help="Mostra o que seria inserido sem alterar a planilha")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info(f"Iniciando raspagem — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.dry_run:
        log.info("** MODO DRY-RUN — nenhuma alteração será salva **")

    todos = coletar_todos()
    inseridos = atualizar_db(todos, dry_run=args.dry_run)

    log.info(f"Raspagem concluída. Novos inseridos: {inseridos}")
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
