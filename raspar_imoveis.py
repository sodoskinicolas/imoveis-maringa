#!/usr/bin/env python3
"""
raspar_imoveis.py
Raspa todos os sites de imobiliárias de Maringá, identifica imóveis novos
e atualiza Imoveis_Grupos.xlsx com Status="Novo".

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
import pandas as pd
import openpyxl

# ── Configuração ──────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
PLANILHA  = BASE_DIR / "Imoveis_Grupos.xlsx"
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

def parse_sub100_block(html_block, base_domain):
    """
    Extrai dados de um bloco HTML de listagem Sub100.
    O bloco é o trecho antes de 'Contate agora!' para cada imóvel.
    """
    # Ref / URL
    ref_m = re.search(r'/imovel/(0{3,}\d+)/', html_block)
    if not ref_m:
        return None
    ref = ref_m.group(1)
    link = f"https://{base_domain}/imovel/{ref}/"

    # Área
    area_m = re.search(r'([\d.,]+)\s*m[²2]', html_block)
    area_str = area_m.group(0) if area_m else ""

    # Preço
    preco_m = re.search(r'R\$\s*[\d.,]+', html_block.replace("\xa0", " "))
    preco_str = preco_m.group(0) if preco_m else ""

    # Quartos / Banheiros / Vagas — ícones com números próximos
    qtos_m  = re.search(r'(\d+)\s*(?:quarto|dorm)', html_block, re.I)
    ban_m   = re.search(r'(\d+)\s*(?:banheiro|ban\.)', html_block, re.I)
    vaga_m  = re.search(r'(\d+)\s*(?:vaga|garagem)', html_block, re.I)

    # Bairro — geralmente aparece depois do endereço numa tag de localização
    bairro_m = re.search(
        r'(?:localiza[çc][aã]o|bairro)[^<]*?([A-ZÀ-Ú][a-zà-ú\s]+(?:Zona\s+\d+)?)',
        html_block, re.I
    )
    bairro = fix_enc(bairro_m.group(1).strip()) if bairro_m else ""

    # Tipo — prioridade: og:title > <title> > h1-4 > bairro
    tipo_str = ""
    for pat in [
        r'og:title["\s]+content="([^"]+)"',     # <meta property="og:title" content="Sobrado à venda...">
        r'<title>([^<]+)</title>',               # <title>Sobrado à venda...</title>
        r'<h[1-4][^>]*>([^<]+)</h[1-4]>',       # <h1>Sobrado ...</h1>
    ]:
        m = re.search(pat, html_block, re.I)
        if m:
            tipo_str = fix_enc(m.group(1).strip())
            break
    tipo = infer_tipo(tipo_str or bairro)

    return {
        "ref":     ref,
        "link":    link,
        "tipo":    tipo,
        "bairro":  bairro,
        "area":    parse_area(fix_enc(area_str)),
        "quartos": parse_int(qtos_m.group(1)) if qtos_m else None,
        "suites":  parse_int(ban_m.group(1))  if ban_m  else None,
        "vagas":   parse_int(vaga_m.group(1)) if vaga_m else None,
        "preco":   parse_preco(preco_str),
        "obs":     link,
    }

def scrape_sub100(base_url, domain, nome_grupo):
    """
    Raspa site Sub100 por categoria de tipo, para o tipo vir da URL e nunca
    ser inferido errado a partir do texto do bloco.
    Fallback: página geral /imoveis-a-venda para tipos não cobertos pelas categorias.
    """
    # Categorias com tipo explícito — URL padrão Sub100
    base = f"https://{domain}"
    cidade_slug = "10-maringa-pr"  # slug padrão Maringá no Sub100
    CATEGORIAS = [
        (f"{base}/imoveis/venda/apartamentos/{cidade_slug}", "Apartamento"),
        (f"{base}/imoveis/venda/casas/{cidade_slug}",         "Casa"),
        (f"{base}/imoveis/venda/sobrados/{cidade_slug}",      "Sobrado"),
        (f"{base}/imoveis/venda/terrenos/{cidade_slug}",      "Terreno"),
        (f"{base}/imoveis/venda/coberturas/{cidade_slug}",    "Apartamento"),
        (f"{base}/imoveis/venda/salas-comerciais/{cidade_slug}", "Sala Comercial"),
        (f"{base}/imoveis/venda/galpoes/{cidade_slug}",       "Galpão"),
        (f"{base}/imoveis/venda/chacaras/{cidade_slug}",      "Chácara"),
        (f"{base}/imoveis/venda/studios/{cidade_slug}",       "Kitnet"),
        (f"{base}/imoveis/venda/kitnets/{cidade_slug}",       "Kitnet"),
    ]

    items = []
    seen_refs = set()

    def _raspar_categoria(cat_url, tipo_fixo):
        page = 1
        while True:
            url = f"{cat_url}?page={page}" if page > 1 else cat_url
            r = get_page(url, ajax=True)
            if not r:
                break

            html = r.text
            if page > 1 and not re.search(r'/imovel/0{3,}\d+/', html):
                break

            blocks = re.split(r'Contate\s+agora', html, flags=re.I)
            found = 0
            for block in blocks:
                item = parse_sub100_block(block, domain)
                if not item or item["ref"] in seen_refs:
                    continue
                item["tipo"] = tipo_fixo   # ← tipo vem da categoria, não inferido
                seen_refs.add(item["ref"])
                items.append(item)
                found += 1

            if found == 0:
                break

            soup = BeautifulSoup(html, "html.parser")
            next_btn = soup.find("a", string=re.compile(r"próxima|next|›|»", re.I))
            if not next_btn and not re.search(rf'page={page+1}', html):
                break
            page += 1
            time.sleep(1.0)

    log.info(f"[{nome_grupo}] Raspando por categoria...")
    for cat_url, tipo_fixo in CATEGORIAS:
        before = len(items)
        _raspar_categoria(cat_url, tipo_fixo)
        log.info(f"[{nome_grupo}] {tipo_fixo}: {len(items)-before} imóveis")
        time.sleep(1.0)

    # Fallback: página geral para pegar tipos não cobertos pelas categorias acima
    log.info(f"[{nome_grupo}] Iniciando raspagem → {base_url}")
    page = 1
    while True:
        url = f"{base_url}?page={page}" if page > 1 else base_url
        r = get_page(url, ajax=True)
        if not r:
            log.warning(f"[{nome_grupo}] Falha ao carregar página {page}")
            break

        html = r.text
        if page > 1 and not re.search(r'/imovel/0{3,}\d+/', html):
            break

        blocks = re.split(r'Contate\s+agora', html, flags=re.I)
        found_this_page = 0
        for block in blocks:
            item = parse_sub100_block(block, domain)
            if not item or item["ref"] in seen_refs:
                continue   # já coletado pela categoria
            seen_refs.add(item["ref"])
            items.append(item)
            found_this_page += 1

        log.info(f"[{nome_grupo}] Fallback página {page}: {found_this_page} novos")
        if found_this_page == 0:
            break

        soup = BeautifulSoup(html, "html.parser")
        next_btn = soup.find("a", string=re.compile(r"próxima|next|\bnext\b|›|»", re.I))
        if not next_btn:
            if not re.search(rf'page={page+1}', html):
                break
        page += 1
        time.sleep(1.5)

    log.info(f"[{nome_grupo}] Total coletado: {len(items)} imóveis")
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

    # Sub100
    for url, domain, grupo in [
        ("https://harakiimoveis.com.br/imoveis-a-venda",  "harakiimoveis.com.br",   "Haraki Imóveis"),
        ("https://massaruimoveis.com.br/imoveis-a-venda", "massaruimoveis.com.br",  "Massaru Imóveis"),
        ("https://bellakaza.com.br/imoveis-a-venda",      "bellakaza.com.br",       "Bellakaza"),
    ]:
        try:
            items = scrape_sub100(url, domain, grupo)
            for it in items:
                it["grupo"] = domain
            todos.extend(items)
        except Exception as e:
            log.error(f"[{grupo}] Erro na raspagem: {e}", exc_info=True)
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


# ── Deduplicação e import ─────────────────────────────────────────────────────

def fingerprint(item):
    """Chave para deduplicar: bairro (20 chars) + área arredondada + preço."""
    bairro = (item.get("bairro") or "").lower().strip()[:20]
    area   = round(item.get("area") or 0, 0)
    preco  = item.get("preco") or 0
    return (bairro, area, preco)

def atualizar_planilha(novos_raw, dry_run=False):
    if not PLANILHA.exists():
        log.error(f"Planilha não encontrada: {PLANILHA}")
        return 0

    # Carregar planilha existente
    df = pd.read_excel(PLANILHA, sheet_name="Imóveis", dtype=str)
    df = df.where(pd.notnull(df), None)

    # Construir conjuntos de dedup a partir dos existentes
    slugs_existentes = set()
    fps_existentes   = set()
    for _, row in df.iterrows():
        obs = (row.get("Observações") or "").strip()
        if obs:
            slugs_existentes.add(slug(obs))
        area_v = row.get("Área (m²)")
        try:
            area_f = round(float(area_v), 0) if area_v else 0
        except (ValueError, TypeError):
            area_f = 0
        preco_v = row.get("Preço (R$)")
        try:
            preco_i = int(float(preco_v)) if preco_v else 0
        except (ValueError, TypeError):
            preco_i = 0
        bairro_b = (row.get("Bairro / Endereço") or "").lower().strip()[:20]
        fps_existentes.add((bairro_b, area_f, preco_i))

    # Filtrar novos
    novos = []
    slugs_novos = set()
    fps_novos   = set()

    for item in novos_raw:
        sl = slug(item.get("link", ""))
        fp = fingerprint(item)
        if sl in slugs_existentes or sl in slugs_novos:
            continue
        if fp[0] and fp in fps_existentes or fp in fps_novos:
            continue
        novos.append(item)
        slugs_novos.add(sl)
        if fp[0]:
            fps_novos.add(fp)

    log.info(f"Imóveis novos encontrados: {len(novos)} (de {len(novos_raw)} coletados)")

    if not novos:
        return 0

    if dry_run:
        log.info("[DRY-RUN] Nenhuma alteração salva.")
        for it in novos[:10]:
            log.info(f"  Novo: {it.get('tipo','')} | {it.get('bairro','')} | {it.get('preco','')} | {it.get('link','')}")
        return len(novos)

    # Inserir novos na planilha
    wb = openpyxl.load_workbook(PLANILHA)
    ws = wb["Imóveis"]

    hoje = date.today().isoformat()
    inseridos = 0

    for item in novos:
        bairro_end = item.get("bairro") or ""
        end = item.get("endereco", "")
        if end:
            bairro_end = f"{bairro_end} · {end}".strip(" ·")

        area = item.get("area")
        preco = item.get("preco")

        ws.append([
            hoje,                          # Data Captura
            item.get("grupo", ""),         # Grupo
            "",                            # Corretor
            "",                            # Contato (WhatsApp)
            item.get("tipo", "Imóvel"),    # Tipo
            bairro_end,                    # Bairro / Endereço
            area if area else None,        # Área (m²)
            item.get("quartos"),           # Quartos
            item.get("suites"),            # Suítes
            item.get("vagas"),             # Vagas
            preco if preco else None,      # Preço (R$)
            item.get("obs", ""),           # Observações (link)
            "Novo",                        # Status  ← ETIQUETA NOVO
            hoje,                          # Data Publicação
        ])
        inseridos += 1

    wb.save(PLANILHA)
    log.info(f"✅ {inseridos} imóveis novos adicionados com Status='Novo' em {PLANILHA.name}")
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
    inseridos = atualizar_planilha(todos, dry_run=args.dry_run)

    log.info(f"Raspagem concluída. Novos inseridos: {inseridos}")
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
