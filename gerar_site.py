#!/usr/bin/env python3
"""
gerar_site.py
Lê imoveis.db (SQLite) e gera Imoveis.html.
Chamado automaticamente após cada inserção no banco de dados.

Fontes externas (VivaReal, Junior Joda) não são mais lidas de planilhas
separadas aqui — elas são sincronizadas pro imoveis.db por
importar_vivareal.py / scrape_vivareal.py / importar_juniorjoda.py, e este
script lê tudo direto do banco (colunas fonte/ref_externa/nome/link).

Uso manual:
  python gerar_site.py
"""

import json
import math
import re
from pathlib import Path
from datetime import datetime

import db
import processar_mensagens as pm

SITE  = Path(__file__).parent / "Imoveis.html"
WA_JJ = "5544988132965"   # WhatsApp Junior Joda Soluções Imobiliárias


def limpar(val):
    if val is None: return None
    if isinstance(val, float) and math.isnan(val): return None
    return val

_TIPO_MAP = [
    (["apartamento", "apto", "edifício", "edificio", "ed.", "andar", "cobertura"], "Apartamento"),
    (["casa"],                                                                       "Casa"),
    (["terreno", "lote"],                                                            "Terreno"),
    (["sobrado"],                                                                    "Sobrado"),
    (["sala comercial", "sala", "loja", "comercial"],                               "Sala Comercial"),
    (["galpão", "galpao"],                                                           "Galpão"),
    (["kitnet", "kit net"],                                                          "Kitnet"),
    (["chácara", "chacara"],                                                         "Chácara"),
    (["sítio", "sitio"],                                                             "Sítio"),
]

def normalizar_tipo(tipo, obs=""):
    """Garante que o tipo seja sempre um valor padronizado, inferindo do obs se necessário."""
    t = (tipo or "").strip()
    tl = t.lower()
    for palavras, valor in _TIPO_MAP:
        if any(p in tl for p in palavras):
            return valor
    # Se tipo está vazio ou genérico, tenta inferir do obs
    if t in ("", "Imóvel") and obs:
        ol = obs.lower()
        for palavras, valor in _TIPO_MAP:
            if any(p in ol for p in palavras):
                return valor
    return t or "Imóvel"




def _extrair_url(texto):
    """Extrai a primeira URL http/https de um texto."""
    if not texto: return ""
    m = re.search(r'https?://[^\s]+', texto)
    return m.group(0).rstrip('.,)') if m else ""

def carregar_imoveis():
    """
    Lê todos os imóveis do SQLite: mensagens de grupos de WhatsApp e também os
    imóveis de fontes externas (VivaReal, Junior Joda), sincronizados por
    upsert_imovel_externo() e já deduplicados no próprio banco por
    (fonte, ref_externa).
    """
    db.init_db()
    with db.db_conn() as conn:
        registros = db.listar_imoveis(conn)

    rows = []
    vistos = set()
    for r in registros:
        if not r.get("data_captura"):
            continue
        obs   = pm.limpar_obs(r.get("observacoes") or "")
        fonte = r.get("fonte") or ""
        link  = r.get("link") or _extrair_url(obs)

        corretor = r.get("corretor") or ""
        preco    = r.get("preco") or ""
        data     = r.get("data_captura") or ""
        area     = r.get("area") or ""

        # Deduplicação por conteúdo só se aplica a capturas de grupos de
        # WhatsApp — imóveis de fonte externa já são únicos no banco por
        # (fonte, ref_externa), então não precisam (e não devem) passar por
        # essa checagem de novo.
        if not fonte:
            chave_dup = f"{corretor}|{preco}|{area}|{str(data)[:16]}"
            if chave_dup in vistos:
                continue
            vistos.add(chave_dup)

        # Edifício e condomínio: usa valores salvos no banco (verificados pelo quality gate).
        # Fallback para extração do obs se coluna ainda estiver vazia.
        edificio = r.get("edificio") or None
        if not edificio and obs:
            try:
                edificio = pm.extrair_edificio(obs) or None
            except Exception:
                edificio = None
        condominio = r.get("condominio") or None
        if not condominio and obs:
            try:
                condominio = pm.extrair_condominio(obs) or None
            except Exception:
                condominio = None
        # Deduplicação: se ambos extraíram o mesmo nome, é condomínio
        if edificio and condominio and edificio.lower() == condominio.lower():
            edificio = None

        rows.append({
            "data":            data,
            "grupo":           r.get("grupo") or "",
            "corretor":        corretor,
            "contato":         r.get("contato") or "",
            "tipo":            normalizar_tipo(r.get("tipo") or "", obs),
            "nome":            r.get("nome") or "",
            "bairro":          r.get("bairro") or "",
            "area":            r.get("area"),
            "quartos":         r.get("quartos"),
            "suites":          r.get("suites"),
            "vagas":           r.get("vagas"),
            "preco":           r.get("preco"),
            "obs":             obs,
            "edificio":        edificio,
            "condominio":      condominio,
            "status":          r.get("status") or "Novo",
            "data_publicacao": r.get("data_publicacao") or "",
            "link":            link,
            "fonte":           fonte,
            "sem_excl":        False,  # preenchido abaixo
        })

    # ── Detectar imóveis sem exclusividade ───────────────────────────────────
    # Um imóvel é "sem exclusividade" quando o mesmo imóvel aparece em 2+
    # fontes distintas (ex: VivaReal + massaruimoveis.com.br).
    from collections import defaultdict

    def _ab(a):
        return round(a / 5) * 5 if a else None  # bucket de 5m²

    fontes_por_chave = defaultdict(set)
    idxs_por_chave   = defaultdict(list)

    for idx, im in enumerate(rows):
        fonte_im = im.get("fonte") or ""
        if not fonte_im:
            continue  # grupos WA não participam da detecção
        edif = (im.get("edificio") or im.get("condominio") or "").strip().lower()
        bairro_im = (im.get("bairro") or "").strip().lower()
        preco_im  = im.get("preco")
        ab        = _ab(im.get("area"))

        chaves = []
        if edif and len(edif) > 3:
            if ab:
                chaves.append(("E_A", edif, ab))
            if preco_im:
                chaves.append(("E_P", edif, preco_im))
        if bairro_im and preco_im:
            chaves.append(("B_P", bairro_im, preco_im))
        if bairro_im and im.get("quartos") and ab:
            chaves.append(("B_Q_A", bairro_im, im.get("quartos"), ab))

        for chave in chaves:
            fontes_por_chave[chave].add(fonte_im)
            idxs_por_chave[chave].append(idx)

    excl_idxs = set()
    for chave, fontes_set in fontes_por_chave.items():
        if len(fontes_set) >= 2:
            for idx in idxs_por_chave[chave]:
                excl_idxs.add(idx)

    for idx in excl_idxs:
        rows[idx]["sem_excl"] = True

    return rows


def carregar_demandas():
    """Lê demandas do SQLite."""
    db.init_db()
    with db.db_conn() as conn:
        registros = db.listar_demandas(conn)

    rows = []
    vistos = set()
    for r in registros:
        if not r.get("data"):
            continue
        corretor = r.get("corretor") or ""
        orc      = r.get("orcamento_max") or ""
        data     = r.get("data") or ""
        chave    = f"{corretor}|{orc}|{str(data)[:16]}"
        if chave in vistos:
            continue
        vistos.add(chave)
        obs_d = pm.limpar_obs(r.get("observacoes") or "")
        # Edifício/condomínio: usa valores salvos pelo quality gate; fallback para extração.
        edificio_d = r.get("edificio") or ""
        if not edificio_d and obs_d:
            try:
                edificio_d = pm.extrair_edificio(obs_d) or ""
            except Exception:
                edificio_d = ""
        condominio_d = r.get("condominio") or ""
        if not condominio_d and obs_d:
            try:
                condominio_d = pm.extrair_condominio(obs_d) or ""
            except Exception:
                condominio_d = ""
        # Deduplicação: se ambos extraíram o mesmo nome, é condomínio
        if edificio_d and condominio_d and edificio_d.lower() == condominio_d.lower():
            edificio_d = ""
        rows.append({
            "data":       data,
            "grupo":      r.get("grupo") or "",
            "corretor":   corretor,
            "contato":    r.get("contato") or "",
            "tipo":       r.get("tipo_buscado") or "Apartamento",
            "regiao":     r.get("bairro_regiao") or "",
            "edificio":   edificio_d,
            "condominio": condominio_d,
            "area_min":  r.get("area_min"),
            "quartos":   r.get("quartos"),
            "suites":    r.get("suites"),
            "banheiros": r.get("banheiros"),
            "vagas":     r.get("vagas"),
            "orcamento": r.get("orcamento_max"),
            "obs":       obs_d,
            "status":    r.get("status") or "Ativo",
        })
    return rows


def gerar_html(imoveis, demandas):
    imoveis_venda = [i for i in imoveis if i.get("status") != "Aluguel"]
    imoveis_loc   = [i for i in imoveis if i.get("status") == "Aluguel"]
    total_i   = len(imoveis_venda)
    total_l   = len(imoveis_loc)
    total_d   = len(demandas)
    agora     = datetime.now().strftime("%d/%m/%Y %H:%M")
    dados_i   = json.dumps(imoveis_venda, ensure_ascii=False)
    dados_l   = json.dumps(imoveis_loc,   ensure_ascii=False)
    dados_d   = json.dumps(demandas,      ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Imóveis Maringá</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f7f7f5;color:#111;min-height:100vh}}

/* Top bar */
.topbar{{background:#fff;border-bottom:1px solid #e8e8e4;padding:0 28px;height:56px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:50}}
.logo{{font-size:16px;font-weight:700;color:#111;letter-spacing:-0.3px}}
.topbar-meta{{font-size:12px;color:#999}}

/* Tab nav */
.tabnav{{background:#fff;border-bottom:1px solid #e8e8e4;padding:0 28px;display:flex;gap:0}}
.tab{{padding:14px 20px;font-size:14px;font-weight:500;color:#888;cursor:pointer;border-bottom:2.5px solid transparent;transition:color .15s,border-color .15s;user-select:none}}
.tab:hover{{color:#111}}
.tab.active{{color:#111;border-bottom-color:#111;font-weight:600}}
.tab-badge{{display:inline-block;margin-left:6px;background:#f0f0ec;color:#888;font-size:11px;font-weight:600;padding:2px 7px;border-radius:99px}}
.tab.active .tab-badge{{background:#111;color:#fff}}

/* Panels */
.panel{{display:none}}.panel.active{{display:block}}

/* Hero search */
.hero{{background:#fff;border-bottom:1px solid #e8e8e4;padding:20px 28px}}
.search-wrap{{position:relative;max-width:560px}}
.search-wrap svg{{position:absolute;left:14px;top:50%;transform:translateY(-50%);color:#aaa;pointer-events:none}}
.search-input{{width:100%;padding:12px 14px 12px 42px;border:1.5px solid #e0e0db;border-radius:10px;font-size:15px;color:#111;background:#f7f7f5;outline:none;transition:border-color .15s}}
.search-input:focus{{border-color:#111;background:#fff}}
.search-input::placeholder{{color:#bbb}}

/* Filter bar */
.filterbar{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;align-items:center}}
.fsel{{padding:7px 12px;border:1.5px solid #e0e0db;border-radius:8px;font-size:13px;color:#444;background:#fff;outline:none;cursor:pointer;appearance:none;-webkit-appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23999' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 8px center;padding-right:26px;transition:border-color .15s}}
.fsel:focus,.fsel:hover{{border-color:#111}}
.fsel.active{{border-color:#111;background:#111;color:#fff;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23fff' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")}}
.filter-sep{{width:1px;height:20px;background:#e0e0db;margin:0 2px}}
.btn-clear{{padding:7px 12px;border:1.5px solid transparent;border-radius:8px;font-size:13px;color:#999;background:none;cursor:pointer}}
.btn-clear:hover{{color:#111}}

/* Stats */
.statsbar{{display:flex;gap:24px;padding:16px 28px 0}}
.stat{{font-size:13px;color:#888}}
.stat strong{{color:#111;font-weight:600;font-size:15px;margin-right:4px}}

/* Content */
.content{{padding:20px 28px 40px}}
.results-row{{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}}
.results-txt{{font-size:13px;color:#888}}
.sort-sel{{padding:6px 28px 6px 10px;border:1.5px solid #e0e0db;border-radius:8px;font-size:13px;color:#444;background:#fff url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23999' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E") no-repeat right 8px center;appearance:none;-webkit-appearance:none;outline:none;cursor:pointer}}

/* Grid */
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:12px}}

/* Card — imóveis */
.card{{background:#fff;border:1.5px solid #e8e8e4;border-radius:12px;padding:18px;display:flex;flex-direction:column;gap:12px;transition:box-shadow .15s,border-color .15s;cursor:pointer}}
.card:hover{{box-shadow:0 4px 18px rgba(0,0,0,.10);border-color:#c5c5bf}}
.card:hover{{box-shadow:0 4px 20px rgba(0,0,0,.07);border-color:#d0d0cc}}
.card-header{{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}}
.card-name{{font-size:15px;font-weight:600;color:#111;line-height:1.3}}
.card-loc{{font-size:12px;color:#999;margin-top:3px}}
.card-price{{font-size:18px;font-weight:700;color:#111;white-space:nowrap;letter-spacing:-0.5px}}
.card-price-na{{font-size:13px;color:#bbb;white-space:nowrap}}
.chips{{display:flex;flex-wrap:wrap;gap:6px}}
.chip{{font-size:12px;padding:4px 10px;border-radius:99px;background:#f2f2ef;color:#555;font-weight:500}}
.chip-urgente{{background:#fff0f0;color:#c0392b;font-weight:700}}
.chip-dem{{background:#f0eafb;color:#6b21a8}}
.chip-jj{{background:#e8f4fd;color:#1a5f9a;font-weight:600}}
.chip-vr{{background:#fff3e0;color:#a06000;font-weight:600}}
.chip-aluguel{{background:#e8f5e9;color:#1b6b2a;font-weight:600}}
.chip-novo{{background:#dbeafe;color:#1a6fb5;font-weight:700}}
.card-novo{{border-left:3px solid #1a6fb5}}
.card-desc{{font-size:13px;color:#777;line-height:1.6;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.card-foot{{display:flex;justify-content:space-between;align-items:center;padding-top:12px;border-top:1px solid #f0f0ec;margin-top:auto}}
.card-who{{font-size:11px;color:#bbb;line-height:1.6}}
.foot-right{{display:flex;gap:6px;align-items:center}}

/* Card Junior Joda — borda azul */
.card-jj{{border-color:#cce0f5}}
.card-jj:hover{{border-color:#85bff5}}

/* Card VivaReal — borda laranja */
.card-vr{{border-color:#fde8c0}}
.card-vr:hover{{border-color:#f5c166}}
.chip-vr{{background:#fff3e0;color:#a06000;font-weight:600}}

/* Sem exclusividade */
.chip-sem-excl{{background:#fff0e8;color:#c05c00;font-weight:700;border:1px solid #f7c89a}}
.card-sem-excl{{border-left:3px solid #e07020}}

/* Agrupamento por edifício */
.grupo-header{{grid-column:1/-1;margin:20px 0 4px;padding:10px 14px;background:#f7f6f3;border-radius:8px;font-size:13px;font-weight:700;color:#444;display:flex;align-items:center;justify-content:space-between}}
.grupo-header-cnt{{font-size:12px;font-weight:500;color:#999;margin-left:8px}}

/* Bairros panel */
.bairros-search{{max-width:400px;width:100%;padding:12px 14px 12px 42px;border:1.5px solid #e0e0db;border-radius:10px;font-size:15px;background:#f7f7f5;outline:none;transition:border-color .15s}}
.bairros-search:focus{{border-color:#111;background:#fff}}
.bairros-list{{display:flex;flex-direction:column;gap:6px;max-width:800px}}
.bairro-row{{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;background:#fff;border:1.5px solid #e8e8e4;border-radius:10px;cursor:pointer;transition:box-shadow .15s,border-color .15s}}
.bairro-row:hover{{box-shadow:0 2px 12px rgba(0,0,0,.07);border-color:#c5c5bf}}
.bairro-name{{font-size:15px;font-weight:600;color:#111}}
.bairro-badges{{display:flex;gap:6px;align-items:center}}
.bairro-badge-i{{background:#e8f4fd;color:#1a6fb5;font-size:12px;font-weight:600;padding:3px 9px;border-radius:99px}}
.bairro-badge-d{{background:#f0eafb;color:#6b21a8;font-size:12px;font-weight:600;padding:3px 9px;border-radius:99px}}
.bairros-breadcrumb{{font-size:13px;color:#888;margin-bottom:16px;display:flex;align-items:center;gap:6px}}
.bairros-breadcrumb a{{color:#111;font-weight:600;cursor:pointer;text-decoration:none}}
.bairros-breadcrumb a:hover{{text-decoration:underline}}
.edif-row{{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:#faf9f7;border:1.5px solid #e8e8e4;border-radius:9px;cursor:pointer;transition:background .15s,border-color .15s}}
.edif-row:hover{{background:#f0eeeb;border-color:#c5c5bf}}
.edif-name{{font-size:14px;font-weight:600;color:#333}}
.bairros-imoveis-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:10px;margin-top:12px}}

/* Card — demandas (borda roxa) */
.card-dem{{border-color:#e4d8f5}}
.card-dem:hover{{border-color:#c4a9e8}}
.card-dem .card-name{{color:#6b21a8}}
.card-dem .card-price{{color:#6b21a8}}
.dem-orcamento-label{{font-size:11px;color:#9c72c8;font-weight:500;text-align:right;margin-top:2px}}

.btn-wa{{display:inline-flex;align-items:center;gap:5px;padding:6px 12px;background:#25d366;color:#fff;border-radius:8px;font-size:12px;font-weight:600;text-decoration:none;transition:opacity .15s}}
.btn-wa:hover{{opacity:.85}}
.btn-wa svg{{width:14px;height:14px}}
.btn-sem-contato{{display:inline-flex;align-items:center;gap:4px;padding:5px 10px;background:#f3f0fa;color:#a78bca;border-radius:8px;font-size:11px;font-weight:500;border:1px solid #e4d8f5;cursor:default}}
.btn-link{{display:inline-flex;align-items:center;gap:4px;padding:6px 10px;background:#1a4f8a;color:#fff;border-radius:8px;font-size:12px;font-weight:600;text-decoration:none;transition:opacity .15s}}
.btn-link:hover{{opacity:.85}}

/* pills */
.pill{{font-size:11px;font-weight:600;padding:3px 9px;border-radius:99px}}
.pill-novo{{background:#e8f4fd;color:#1a6fb5}}
.pill-verificado{{background:#eaf5e2;color:#2d7a1a}}
.pill-contato{{background:#fff3e0;color:#a06000}}
.pill-encaminhado{{background:#f0eafb;color:#6b21a8}}
.pill-fechado{{background:#eaf5e2;color:#2d7a1a}}
.pill-vendido{{background:#eaf5e2;color:#2d7a1a}}
.pill-cancelado{{background:#fce8e8;color:#b52020}}
.pill-descartado{{background:#fce8e8;color:#b52020}}
.pill-venda{{background:#e8f4fd;color:#1a5f9a}}
.pill-aluguel{{background:#e8f5e9;color:#1b6b2a}}

/* Empty */
.empty{{grid-column:1/-1;text-align:center;padding:80px 20px;color:#ccc}}
.empty p{{font-size:15px;margin-top:12px;color:#aaa}}

/* ── Match panel ── */
/* ── Match acordeão ── */
.match-list{{display:flex;flex-direction:column;gap:8px}}
.match-item{{border:1.5px solid #e4d8f5;border-radius:12px;overflow:hidden;background:#fff;transition:box-shadow .15s}}
.match-item.open{{box-shadow:0 4px 20px rgba(107,33,168,.10);border-color:#c4a9e8}}
.match-item-header{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:15px 18px;cursor:pointer;user-select:none}}
.match-item-header:hover{{background:#faf7fe}}
.match-item-left{{flex:1;min-width:0}}
.match-dem-title{{font-size:15px;font-weight:700;color:#6b21a8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.match-dem-sub{{font-size:12px;color:#999;margin-top:2px;line-height:1.5}}
.match-item-right{{display:flex;align-items:center;gap:8px;flex-shrink:0}}
.match-count-badge{{background:#f0eafb;color:#6b21a8;font-size:12px;font-weight:700;padding:5px 12px;border-radius:99px;white-space:nowrap}}
.match-chevron{{font-size:16px;color:#a78bca;transition:transform .2s;flex-shrink:0}}
.match-item.open .match-chevron{{transform:rotate(180deg)}}
.match-body{{display:none;border-top:1px solid #f0eafb;padding:16px}}
.match-item.open .match-body{{display:block}}
.match-grid{{display:flex;flex-direction:column;gap:6px}}
.match-row-item{{display:flex;align-items:center;gap:12px;background:#faf8fe;border:1px solid #ede8f7;border-radius:9px;padding:11px 14px;transition:background .15s}}
.match-row-item:hover{{background:#f3eefb;border-color:#c9b8e8}}
.match-row-jj{{background:#f5f9fe;border-color:#d0e6f7}}.match-row-jj:hover{{background:#eaf3fd;border-color:#9dc8ee}}
.match-row-near{{border-color:#fde8c0}}.match-row-near:hover{{border-color:#f5c166}}
.mri-main{{flex:1;min-width:0}}
.mri-title{{font-size:13px;font-weight:600;color:#111;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.mri-info{{font-size:11.5px;color:#888;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.mri-right{{display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0}}
.mri-price{{font-size:14px;font-weight:700;color:#111;letter-spacing:-.3px;white-space:nowrap}}
.mri-actions{{display:flex;align-items:center;gap:5px}}
.match-score{{display:inline-block;padding:2px 7px;border-radius:99px;font-size:10.5px;font-weight:700}}
.mscore-high{{background:#eaf5e2;color:#2d7a1a}}
.mscore-mid{{background:#fff3e0;color:#a06000}}
.mscore-low{{background:#f0f0ec;color:#777}}
.match-none{{color:#bbb;font-size:13px;padding:8px 0;text-align:center}}
.match-near-label{{font-size:12px;font-weight:600;color:#a06000;margin:12px 0 5px;letter-spacing:.2px}}
.match-row-item{{cursor:pointer}}
/* ── Modal detalhes do imóvel ── */
#im-modal-overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9999;align-items:center;justify-content:center}}
#im-modal-overlay.active{{display:flex}}
#im-modal{{background:#fff;border-radius:18px;width:min(560px,95vw);max-height:88vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.25);padding:28px 28px 24px;position:relative}}
.im-modal-close{{position:absolute;top:14px;right:16px;background:none;border:none;font-size:22px;cursor:pointer;color:#aaa;line-height:1}}
.im-modal-close:hover{{color:#333}}
.im-modal-tipo{{font-size:11px;font-weight:700;color:#9c72c8;letter-spacing:.8px;text-transform:uppercase;margin-bottom:4px}}
.im-modal-titulo{{font-size:20px;font-weight:800;color:#111;margin-bottom:2px}}
.im-modal-bairro{{font-size:13px;color:#888;margin-bottom:16px}}
.im-modal-specs{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px}}
.im-spec{{background:#f5f2fc;border-radius:8px;padding:7px 13px;font-size:12.5px;font-weight:600;color:#5a35a0}}
.im-modal-preco{{font-size:26px;font-weight:900;color:#111;letter-spacing:-.5px;margin-bottom:16px}}
.im-modal-obs{{font-size:13px;color:#555;line-height:1.65;background:#faf8fe;border-radius:10px;padding:12px 14px;margin-bottom:18px;white-space:pre-wrap;word-break:break-word;max-height:180px;overflow-y:auto}}
.im-modal-corretor{{font-size:12px;color:#888;margin-bottom:16px}}
.im-modal-btns{{display:flex;gap:10px;flex-wrap:wrap}}
.im-modal-btns a{{flex:1;min-width:130px;text-align:center;padding:11px 16px;border-radius:10px;font-size:14px;font-weight:700;text-decoration:none;transition:opacity .15s}}
.im-modal-btns a:hover{{opacity:.85}}
.im-btn-wa{{background:#25d366;color:#fff}}
.im-btn-link{{background:#1a4f8a;color:#fff}}
/* ── Toggle vista ── */
.view-toggle{{display:flex;gap:4px}}
.btn-view{{padding:5px 12px;border:1.5px solid #e0e0db;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;background:#fff;color:#666;transition:all .15s;line-height:1.4}}
.btn-view.active{{background:#6b21a8;color:#fff;border-color:#6b21a8}}
/* ── Vista lista ── */
.grid.list-view{{display:flex;flex-direction:column;gap:5px}}
.grid.list-view .card{{flex-direction:row;align-items:center;padding:10px 14px;gap:14px;border-radius:9px}}
.grid.list-view .card-header{{flex:1;min-width:0;margin:0}}
.grid.list-view .card-name{{font-size:13.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px}}
.grid.list-view .card-loc{{display:none}}
.grid.list-view .chips{{flex:0 0 auto;flex-wrap:nowrap}}
.grid.list-view .card-desc{{display:none}}
.grid.list-view .card-foot{{border-top:none;padding-top:0;margin-top:0;flex-shrink:0}}
.grid.list-view .card-who{{display:none}}
.grid.list-view .card-expand{{display:none!important}}
/* ── Expandir card inline ── */
.card-expand{{display:none;padding-top:12px;border-top:1px solid #f0f0ec;margin-top:8px}}
.card.expanded .card-expand{{display:block}}
.card.expanded{{box-shadow:0 4px 22px rgba(107,33,168,.13)!important;border-color:#c4a9e8!important}}
.ce-specs{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}}
.ce-spec{{background:#f5f2fc;border-radius:7px;padding:5px 11px;font-size:12px;font-weight:600;color:#5a35a0}}
.ce-obs{{font-size:13px;color:#555;line-height:1.65;background:#faf8fe;border-radius:8px;padding:10px 12px;margin-bottom:10px;white-space:pre-wrap;word-break:break-word;max-height:200px;overflow-y:auto}}
.ce-origem{{font-size:11.5px;color:#aaa;margin-bottom:10px}}
.ce-btns{{display:flex;gap:8px;flex-wrap:wrap}}
.ce-btns a{{flex:1;min-width:110px;text-align:center;padding:9px 14px;border-radius:9px;font-size:13px;font-weight:700;text-decoration:none;transition:opacity .15s}}
.ce-btns a:hover{{opacity:.85}}
.ce-btn-wa{{background:#25d366;color:#fff}}
.ce-btn-link{{background:#1a4f8a;color:#fff}}
.card-expand-arrow{{font-size:11px;color:#9c72c8;margin-left:4px;transition:transform .2s;display:inline-block;opacity:.5}}
.card.expanded .card-expand-arrow{{transform:rotate(180deg);opacity:1}}

@media(max-width:640px){{
  .topbar,.hero,.statsbar,.content{{padding-left:16px;padding-right:16px}}
  .tabnav{{padding-left:16px}}
  .card-price{{font-size:16px}}
}}
</style>
</head>
<body>

<div class="topbar">
  <span class="logo">Imóveis Maringá</span>
  <span class="topbar-meta">Atualizado {agora}</span>
</div>

<!-- Tab nav -->
<nav class="tabnav">
  <div class="tab active" onclick="mudarAba('imoveis',this)">
    🏠 Venda <span class="tab-badge" id="badge-i">{total_i}</span>
  </div>
  <div class="tab" onclick="mudarAba('locacao',this)">
    🔑 Locação <span class="tab-badge" id="badge-l">{total_l}</span>
  </div>
  <div class="tab" onclick="mudarAba('demandas',this)">
    🔍 Demandas <span class="tab-badge" id="badge-d">{total_d}</span>
  </div>
  <div class="tab" onclick="mudarAba('match',this);renderMatch()">
    🎯 Match <span class="tab-badge" id="badge-match">—</span>
  </div>
  <div class="tab" onclick="mudarAba('bairros',this);initBairros()">
    🏘️ Bairros
  </div>
</nav>

<!-- ═══ PAINEL IMÓVEIS ═══ -->
<div class="panel active" id="panel-imoveis">
  <div class="hero">
    <div class="search-wrap">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input type="text" id="busca-i" class="search-input" placeholder="Buscar por nome, bairro, corretor…" autocomplete="off">
    </div>
    <div class="filterbar">
      <select class="fsel" id="bairro-i">
        <option value="">Bairro</option>
      </select>
      <select class="fsel" id="quartos-i">
        <option value="">Quartos</option>
        <option value="1">1+</option><option value="2">2+</option>
        <option value="3">3+</option><option value="4">4+</option>
      </select>
      <select class="fsel" id="banheiros-i">
        <option value="">Banheiros</option>
        <option value="1">1+</option><option value="2">2+</option>
        <option value="3">3+</option><option value="4">4+</option>
      </select>
      <select class="fsel" id="vagas-i">
        <option value="">Vagas</option>
        <option value="1">1+</option><option value="2">2+</option><option value="3">3+</option>
      </select>
      <select class="fsel" id="preco-min-i">
        <option value="">Preço de</option>
        <option value="100000">R$ 100 mil</option><option value="200000">R$ 200 mil</option>
        <option value="300000">R$ 300 mil</option><option value="400000">R$ 400 mil</option>
        <option value="500000">R$ 500 mil</option><option value="600000">R$ 600 mil</option>
        <option value="700000">R$ 700 mil</option><option value="800000">R$ 800 mil</option>
        <option value="900000">R$ 900 mil</option><option value="1000000">R$ 1 milhão</option>
        <option value="1250000">R$ 1,25 milhão</option><option value="1500000">R$ 1,5 milhão</option>
        <option value="1750000">R$ 1,75 milhão</option><option value="2000000">R$ 2 milhões</option>
        <option value="2500000">R$ 2,5 milhões</option><option value="3000000">R$ 3 milhões</option>
        <option value="3500000">R$ 3,5 milhões</option><option value="4000000">R$ 4 milhões</option>
        <option value="4500000">R$ 4,5 milhões</option><option value="5000000">R$ 5 milhões</option>
      </select>
      <select class="fsel" id="preco-max-i">
        <option value="">até</option>
        <option value="100000">R$ 100 mil</option><option value="200000">R$ 200 mil</option>
        <option value="300000">R$ 300 mil</option><option value="400000">R$ 400 mil</option>
        <option value="500000">R$ 500 mil</option><option value="600000">R$ 600 mil</option>
        <option value="700000">R$ 700 mil</option><option value="800000">R$ 800 mil</option>
        <option value="900000">R$ 900 mil</option><option value="1000000">R$ 1 milhão</option>
        <option value="1250000">R$ 1,25 milhão</option><option value="1500000">R$ 1,5 milhão</option>
        <option value="1750000">R$ 1,75 milhão</option><option value="2000000">R$ 2 milhões</option>
        <option value="2500000">R$ 2,5 milhões</option><option value="3000000">R$ 3 milhões</option>
        <option value="3500000">R$ 3,5 milhões</option><option value="4000000">R$ 4 milhões</option>
        <option value="4500000">R$ 4,5 milhões</option><option value="5000000">R$ 5 milhões</option>
      </select>
      <select class="fsel" id="fonte-i">
        <option value="">Todas as fontes</option>
        <option value="grupos">Grupos WhatsApp</option>
        <option value="Junior Joda">Junior Joda</option>
        <option value="VivaReal">VivaReal</option>
      </select>
      <select class="fsel" id="status-i">
        <option value="">Status</option>
        <option>Novo</option><option>Verificado</option>
        <option>Em Contato</option><option>Vendido</option><option>Removido</option>
        <option>Venda</option><option>Aluguel</option><option>Descartado</option>
      </select>
      <select class="fsel" id="datapub-i">
        <option value="">Data publicação</option>
        <option value="30">Últimos 30 dias</option>
        <option value="90">Últimos 90 dias</option>
        <option value="180">Últimos 6 meses</option>
        <option value="365">Último ano</option>
      </select>
      <select class="fsel" id="excl-i">
        <option value="">Exclusividade</option>
        <option value="sem">Sem exclusividade</option>
        <option value="com">Com exclusividade</option>
      </select>
      <div class="filter-sep"></div>
      <button class="btn-clear" onclick="resetarI()">Limpar</button>
    </div>
  </div>
  <div class="statsbar" id="stats-i"></div>
  <div class="content">
    <div class="results-row">
      <span class="results-txt" id="rtxt-i"></span>
      <div style="display:flex;align-items:center;gap:10px">
        <div class="view-toggle">
          <button class="btn-view active" id="btn-cards-i" onclick="setViewI('cards')">⊞ Cards</button>
          <button class="btn-view" id="btn-lista-i" onclick="setViewI('lista')">☰ Lista</button>
          <button class="btn-view" id="btn-edif-i" onclick="setViewI('edificio')">🏢 Edifício</button>
        </div>
        <select class="sort-sel" id="ord-i" onchange="aplicarI()">
          <option value="data_desc">Mais recentes</option>
          <option value="preco_asc">Menor preço</option>
          <option value="preco_desc">Maior preço</option>
          <option value="area_desc">Maior área</option>
        </select>
      </div>
    </div>
    <div class="grid" id="grid-i"></div>
  </div>
</div>

<!-- ═══ PAINEL LOCAÇÃO ═══ -->
<div class="panel" id="panel-locacao">
  <div class="hero">
    <div class="search-wrap">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input type="text" id="busca-l" class="search-input" placeholder="Buscar por nome, bairro, corretor…" autocomplete="off">
    </div>
    <div class="filterbar">
      <select class="fsel" id="quartos-l">
        <option value="">Quartos</option>
        <option value="1">1 quarto</option><option value="2">2 quartos</option>
        <option value="3">3 quartos</option><option value="4">4+</option>
      </select>
      <select class="fsel" id="vagas-l">
        <option value="">Vagas</option>
        <option value="1">1 vaga</option><option value="2">2 vagas</option><option value="3">3+</option>
      </select>
      <select class="fsel" id="preco-l">
        <option value="">Aluguel até</option>
        <option value="1500">R$ 1.500</option><option value="2500">R$ 2.500</option>
        <option value="4000">R$ 4.000</option><option value="7000">R$ 7.000</option>
        <option value="12000">R$ 12.000</option>
      </select>
      <select class="fsel" id="fonte-l">
        <option value="">Todas as fontes</option>
        <option value="Junior Joda">Junior Joda</option>
      </select>
      <div class="filter-sep"></div>
      <button class="btn-clear" onclick="resetarL()">Limpar</button>
    </div>
  </div>
  <div class="statsbar" id="stats-l"></div>
  <div class="content">
    <div class="results-row">
      <span class="results-txt" id="rtxt-l"></span>
      <select class="sort-sel" id="ord-l" onchange="aplicarL()">
        <option value="data_desc">Mais recentes</option>
        <option value="preco_asc">Menor aluguel</option>
        <option value="preco_desc">Maior aluguel</option>
        <option value="area_desc">Maior área</option>
      </select>
    </div>
    <div class="grid" id="grid-l"></div>
  </div>
</div>


<!-- ═══ PAINEL MATCH ═══ -->
<div class="panel" id="panel-match">
  <div class="content" id="content-match" style="padding-top:24px">
    <div class="empty"><p>Clique na aba para carregar os matches.</p></div>
  </div>
</div>

<!-- ═══ PAINEL BAIRROS ═══ -->
<div class="panel" id="panel-bairros">
  <div class="hero">
    <div class="search-wrap">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input type="text" id="busca-bairros" class="search-input" placeholder="Filtrar bairros…" autocomplete="off" oninput="filtrarBairros()">
    </div>
  </div>
  <div class="content" id="content-bairros">
    <div class="empty"><p>Carregando…</p></div>
  </div>
</div>

<!-- ═══ PAINEL DEMANDAS ═══ -->
<div class="panel" id="panel-demandas">
  <div class="hero">
    <div class="search-wrap">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input type="text" id="busca-d" class="search-input" placeholder="Buscar por corretor, região, observações…" autocomplete="off">
    </div>
    <div class="filterbar">
      <select class="fsel" id="tipo-d">
        <option value="">Tipo</option>
        <option value="Apartamento">Apartamento</option>
        <option value="Casa">Casa</option>
        <option value="Terreno">Terreno</option>
        <option value="Imóvel">Imóvel</option>
      </select>
      <select class="fsel" id="regiao-d">
        <option value="">Região</option>
      </select>
      <select class="fsel" id="quartos-d">
        <option value="">Quartos</option>
        <option value="1">1+</option><option value="2">2+</option>
        <option value="3">3+</option><option value="4">4+</option>
      </select>
      <select class="fsel" id="vagas-d">
        <option value="">Vagas</option>
        <option value="1">1+</option><option value="2">2+</option><option value="3">3+</option>
      </select>
      <select class="fsel" id="area-d">
        <option value="">Área mín.</option>
        <option value="50">50 m²</option><option value="80">80 m²</option>
        <option value="100">100 m²</option><option value="120">120 m²</option>
        <option value="150">150 m²</option><option value="200">200 m²</option>
      </select>
      <select class="fsel" id="orc-d">
        <option value="">Orçamento até</option>
        <option value="300000">R$ 300 mil</option><option value="400000">R$ 400 mil</option>
        <option value="500000">R$ 500 mil</option><option value="700000">R$ 700 mil</option>
        <option value="1000000">R$ 1 milhão</option><option value="1500000">R$ 1,5 milhão</option>
        <option value="2000000">R$ 2 milhões</option><option value="3000000">R$ 3 milhões</option>
      </select>
      <select class="fsel" id="status-d">
        <option value="">Status</option>
        <option>Novo</option><option>Em Contato</option>
        <option>Encaminhado</option><option>Fechado</option><option>Cancelado</option>
      </select>
      <div class="filter-sep"></div>
      <button class="btn-clear" onclick="resetarD()">Limpar</button>
    </div>
  </div>
  <div class="statsbar" id="stats-d"></div>
  <div class="content">
    <div class="results-row">
      <span class="results-txt" id="rtxt-d"></span>
      <div style="display:flex;align-items:center;gap:10px">
        <div class="view-toggle">
          <button class="btn-view active" id="btn-cards-d" onclick="setViewD('cards')">⊞ Cards</button>
          <button class="btn-view" id="btn-edif-d" onclick="setViewD('edificio')">🏢 Edifício</button>
        </div>
        <select class="sort-sel" id="ord-d" onchange="aplicarD()">
          <option value="data_desc">Mais recentes</option>
          <option value="orc_desc">Maior orçamento</option>
          <option value="orc_asc">Menor orçamento</option>
        </select>
      </div>
    </div>
    <div class="grid" id="grid-d"></div>
  </div>
</div>

<script>
var IMOVEIS  = {dados_i};
var LOCACAO  = {dados_l};
var DEMANDAS = {dados_d};

/* ── helpers ── */
function fmtP(v){{ return v ? 'R$ ' + v.toLocaleString('pt-BR') : null; }}
function fmtA(v){{ if(!v) return null; return (v%1===0?v:v.toFixed(1))+' m²'; }}
function selActive(id){{ var e=document.getElementById(id); if(e)e.classList.toggle('active',!!e.value); }}

function pillCls(s){{
  var m={{
    'Novo':'novo','Verificado':'verificado','Em Contato':'contato',
    'Encaminhado':'encaminhado','Fechado':'fechado',
    'Vendido':'vendido','Cancelado':'cancelado','Descartado':'descartado',
    'Removido':'cancelado',
    'Venda':'venda','Aluguel':'aluguel'
  }};
  return 'pill pill-'+(m[s]||'novo');
}}

function btnWa(num){{
  if(!num) return '';
  var n=num.replace(/\\D/g,'');
  // Rejeitar LIDs (>13 dígitos) e strings muito curtas
  if(n.length<8||n.length>13) return '';
  return '<a class="btn-wa" href="https://wa.me/'+n+'" target="_blank">'+
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.125.555 4.122 1.524 5.855L0 24l6.334-1.524A11.94 11.94 0 0 0 12 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.818a9.818 9.818 0 0 1-5.006-1.374l-.36-.214-3.727.977.994-3.634-.235-.374A9.818 9.818 0 1 1 12 21.818z"/></svg>'+
    'Chamar</a>';
}}

/* ── tab nav ── */
function mudarAba(aba,el){{
  document.querySelectorAll('.tab').forEach(function(t){{t.classList.remove('active');}});
  document.querySelectorAll('.panel').forEach(function(p){{p.classList.remove('active');}});
  el.classList.add('active');
  document.getElementById('panel-'+aba).classList.add('active');
}}

/* ════ IMÓVEIS ════ */
function extrairEdificio(obs) {{
  // Extrai nome do edifício/condomínio do texto da obs
  if (!obs) return null;
  var m = obs.match(/(?:edif[íi]cio|ed\\.|condom[íi]nio|cond\\.|residencial)\\s+([A-Za-zÀ-ú][A-Za-zÀ-ú\\s]{{2,30}}?)(?:\\s*[·\\-,\\.\\d]|$)/i);
  if (m) return m[1].trim().replace(/\\s+/g, ' ');
  return null;
}}

function cardNome(im){{
  var tipo = im.tipo || 'Imóvel';
  if (im.fonte === 'Junior Joda') {{
    var nomeJJ = im.nome || '';
    var bairroJJ = im.bairro || '';
    // Se tem empreendimento, usar no título
    if (nomeJJ) return tipo + ' · ' + nomeJJ;
    // Se não tem empreendimento mas tem bairro, usar bairro no título
    if (bairroJJ) return tipo + ' · ' + bairroJJ;
    return tipo;
  }}
  if (im.fonte === 'VivaReal') {{
    var bairroPrincipal = im.bairro ? im.bairro.split(' · ')[0].trim() : '';
    return bairroPrincipal ? tipo + ' · ' + bairroPrincipal : tipo;
  }}
  // WhatsApp: Tipo · Edifício · Condomínio · Bairro
  var bairro     = im.bairro     ? im.bairro.split(',')[0].trim() : '';
  var edificio   = im.edificio   || null;
  var condominio = im.condominio || null;
  // Fallback legado: bairro começava com "Cond. X" → extrai como condomínio
  if (!edificio && !condominio && im.bairro && im.bairro.startsWith('Cond. ')) {{
    condominio = im.bairro.replace(/^Cond\\.\\s*/, '').split('·')[0].trim();
    bairro = im.bairro.split('·')[1] ? im.bairro.split('·')[1].trim() : '';
  }}
  // Deduplicação: não repetir edificio/condomínio se já estiver no bairro
  var bl = bairro.toLowerCase();
  if (edificio && bl.includes(edificio.toLowerCase())) edificio = null;
  if (condominio && bl.includes(condominio.toLowerCase())) condominio = null;
  var localParts = [edificio, condominio].filter(Boolean);
  if (localParts.length && bairro) return tipo + ' · ' + localParts.join(' · ') + ' · ' + bairro;
  if (localParts.length)           return tipo + ' · ' + localParts.join(' · ');
  return bairro ? tipo + ' · ' + bairro : tipo;
}}

function cardI(im){{
  var isJJ = im.fonte === 'Junior Joda';
  var isVR  = im.fonte === 'VivaReal';
  var isNovo = im.status === 'Novo';
  var chips=[fmtA(im.area),
    im.quartos?(im.quartos+(im.quartos===1?' quarto':' quartos')):null,
    im.suites?(im.suites+(im.suites===1?' suíte':' suítes')):null,
    im.vagas?(im.vagas+(im.vagas===1?' vaga':' vagas')):null
  ].filter(Boolean).map(function(c){{return'<span class="chip">'+c+'</span>';}}).join('');
  if(isNovo) chips='<span class="chip chip-novo">🆕 Novo</span>'+chips;
  if(isVR)   chips='<span class="chip chip-vr">VivaReal</span>'+chips;
  if(isJJ)   chips='<span class="chip chip-jj">JJ</span>'+chips;
  if(im.sem_excl) chips+='<span class="chip chip-sem-excl">⚡ Sem excl.</span>';
  var linkBtn = im.link ? '<a class="btn-link" href="'+im.link+'" target="_blank">Ver ↗</a>' : '';
  // Para JJ: obs já contém apenas "Ref. XXXXX" — exibe direto no corpo
  // Para VR: mostra data de publicação
  var obsDisplay = isVR
    ? (im.data_publicacao ? 'Publicado em '+im.data_publicacao : '')
    : (im.obs || '');
  var imIdx = IMOVEIS.indexOf(im);
  var cardCls = (im.sem_excl ? ' card-sem-excl' : '') + (isJJ ? ' card-jj' : isVR ? ' card-vr' : isNovo ? ' card-novo' : '');
  // Seção expandida com specs completos e botões
  var ceSpecs=[];
  if(im.area)      ceSpecs.push(im.area+' m²');
  if(im.quartos)   ceSpecs.push(im.quartos+(im.quartos===1?' quarto':' quartos'));
  if(im.suites)    ceSpecs.push(im.suites+(im.suites===1?' suíte':' suítes'));
  if(im.banheiros) ceSpecs.push(im.banheiros+(im.banheiros===1?' banheiro':' banheiros'));
  if(im.vagas)     ceSpecs.push(im.vagas+(im.vagas===1?' vaga':' vagas'));
  var ceBtns='';
  if(im.contato){{var nc=String(im.contato).replace(/\\D/g,'');if(nc.length>=8&&nc.length<=13)ceBtns+='<a class="ce-btn-wa" href="https://wa.me/'+nc+'" target="_blank">💬 WhatsApp</a>';}}
  if(im.link) ceBtns+='<a class="ce-btn-link" href="'+im.link+'" target="_blank">🔗 Ver anúncio</a>';
  var ceOrigem=(im.corretor||'')+(im.grupo?' · '+im.grupo:'')+(im.data?' · '+im.data:'');
  var expandHtml='<div class="card-expand">'+
    (ceSpecs.length?'<div class="ce-specs">'+ceSpecs.map(function(s){{return'<span class="ce-spec">'+s+'</span>';}}).join('')+'</div>':'')+
    (im.obs?'<div class="ce-obs">'+im.obs.replace(/</g,'&lt;')+'</div>':'')+
    (ceOrigem?'<div class="ce-origem">'+ceOrigem+'</div>':'')+
    (ceBtns?'<div class="ce-btns">'+ceBtns+'</div>':'<div style="color:#bbb;font-size:12px">Sem contato disponível</div>')+
  '</div>';
  return '<div class="card'+cardCls+'" onclick="toggleExpand(this)">'+
    '<div class="card-header">'+
      '<div><div class="card-name">'+cardNome(im)+' <span class="card-expand-arrow">▾</span></div>'+(im.bairro?'<div class="card-loc">'+im.bairro+'</div>':'')+' </div>'+
      (im.preco?'<div class="card-price">'+fmtP(im.preco)+'</div>':'<div class="card-price-na">Consultar</div>')+
    '</div>'+
    (chips?'<div class="chips">'+chips+'</div>':'')+
    (obsDisplay?'<div class="card-desc">'+obsDisplay+'</div>':'')+
    '<div class="card-foot">'+
      '<div class="card-who">'+(im.corretor||'—')+'<br>'+(im.grupo||'')+(im.data?' · '+im.data:'')+' </div>'+
      '<div class="foot-right" onclick="event.stopPropagation()">'+btnWa(im.contato)+linkBtn+'<span class="'+pillCls(im.status||'Novo')+'">'+(im.status||'Novo')+'</span></div>'+
    '</div>'+
    expandHtml+
  '</div>';
}}

function baseBairro(b){{return(b||'').split('·')[0].split(',')[0].trim();}}
function totalBanheiros(im){{return(im.banheiros||0)+(im.suites||0);}}

function filtrarI(){{
  var b   = document.getElementById('busca-i').value.toLowerCase();
  var br  = document.getElementById('bairro-i').value;
  var q   = document.getElementById('quartos-i').value;
  var bnh = document.getElementById('banheiros-i').value;
  var vg  = document.getElementById('vagas-i').value;
  var pmn = parseFloat(document.getElementById('preco-min-i').value)||0;
  var pmx = parseFloat(document.getElementById('preco-max-i').value)||Infinity;
  var fn  = document.getElementById('fonte-i').value;
  var st  = document.getElementById('status-i').value;
  var dp  = parseInt(document.getElementById('datapub-i').value)||0;
  var ex  = document.getElementById('excl-i').value;
  var hoje = new Date(); hoje.setHours(0,0,0,0);
  return IMOVEIS.filter(function(im){{
    var hay=[im.obs,im.bairro,im.corretor,im.grupo,im.tipo].join(' ').toLowerCase();
    if(b&&hay.indexOf(b)===-1) return false;
    if(br&&baseBairro(im.bairro)!==br) return false;
    if(q){{var n=parseInt(q);if(!im.quartos||im.quartos<n)return false;}}
    if(bnh){{var nb=parseInt(bnh);if(totalBanheiros(im)<nb)return false;}}
    if(vg){{var n2=parseInt(vg);if(!im.vagas||im.vagas<n2)return false;}}
    if(pmn&&im.preco&&im.preco<pmn) return false;
    if(im.preco&&im.preco>pmx) return false;
    if(fn==='grupos'){{if(im.fonte&&im.fonte!=='')return false;}}
    else if(fn&&im.fonte!==fn) return false;
    if(st&&im.status!==st) return false;
    if(ex==='sem'&&!im.sem_excl) return false;
    if(ex==='com'&&im.sem_excl) return false;
    if(dp&&im.data_publicacao){{
      var pub=new Date(im.data_publicacao); pub.setHours(0,0,0,0);
      var diff=Math.round((hoje-pub)/(1000*60*60*24));
      if(diff>dp) return false;
    }}
    return true;
  }});
}}

function ordenarI(l){{
  var o=document.getElementById('ord-i').value; l=l.slice();
  if(o==='preco_asc') l.sort(function(a,b){{return(a.preco||9e9)-(b.preco||9e9);}});
  else if(o==='preco_desc') l.sort(function(a,b){{return(b.preco||0)-(a.preco||0);}});
  else if(o==='area_desc') l.sort(function(a,b){{return(b.area||0)-(a.area||0);}});
  else l.sort(function(a,b){{return(b.data||'').localeCompare(a.data||'');}});
  return l;
}}

function _renderEdificioGrupos(lista, gridEl, cardFn){{
  // Agrupa lista por edificio/condominio, renderiza com cabeçalhos
  var grupos={{}};
  lista.forEach(function(im){{
    var g = im.edificio || im.condominio || im.regiao || '—';
    if(!grupos[g]) grupos[g]=[];
    grupos[g].push(im);
  }});
  var keys = Object.keys(grupos).sort(function(a,b){{
    if(a==='—') return 1; if(b==='—') return -1;
    return a.localeCompare(b,'pt-BR');
  }});
  var html='';
  keys.forEach(function(g){{
    var items=grupos[g];
    html+='<div class="grupo-header">'+g+'<span class="grupo-header-cnt">'+items.length+(items.length===1?' imóvel':' imóveis')+'</span></div>';
    html+=items.map(cardFn).join('');
  }});
  gridEl.className='grid';
  gridEl.innerHTML=html||'<div class="empty"><p>Nenhum resultado.</p></div>';
}}

function aplicarI(){{
  var lista=ordenarI(filtrarI());
  ['bairro-i','quartos-i','banheiros-i','vagas-i','preco-min-i','preco-max-i','fonte-i','status-i','datapub-i','excl-i'].forEach(selActive);
  var cp=lista.filter(function(i){{return i.preco;}});
  var med=cp.length?Math.round(cp.reduce(function(s,i){{return s+i.preco;}},0)/cp.length):0;
  var novos=lista.filter(function(i){{return i.status==='Novo';}}).length;
  var semExcl=lista.filter(function(i){{return i.sem_excl;}}).length;
  document.getElementById('stats-i').innerHTML=
    '<div class="stat"><strong>'+lista.length+'</strong> imóveis</div>'+
    '<div class="stat"><strong>'+novos+'</strong> novos</div>'+
    (semExcl?'<div class="stat"><strong>'+semExcl+'</strong> ⚡ sem excl.</div>':'')+
    (med?'<div class="stat"><strong>'+fmtP(med)+'</strong> preço médio</div>':'');
  document.getElementById('rtxt-i').textContent=lista.length+' de '+IMOVEIS.length;
  var grid=document.getElementById('grid-i');
  if(_viewI==='edificio'){{
    _renderEdificioGrupos(lista, grid, cardI);
  }} else {{
    grid.className=(_viewI==='lista')?'grid list-view':'grid';
    grid.innerHTML=lista.length?lista.map(cardI).join(''):
      '<div class="empty"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg><p>Nenhum imóvel encontrado.</p></div>';
  }}
}}

var _viewI='cards';
function setViewI(v){{
  _viewI=v;
  document.getElementById('btn-cards-i').className='btn-view'+(v==='cards'?' active':'');
  document.getElementById('btn-lista-i').className='btn-view'+(v==='lista'?' active':'');
  document.getElementById('btn-edif-i').className='btn-view'+(v==='edificio'?' active':'');
  aplicarI();
}}
function toggleExpand(el){{
  el.classList.toggle('expanded');
}}

function resetarI(){{
  document.getElementById('busca-i').value='';
  ['bairro-i','quartos-i','banheiros-i','vagas-i','preco-min-i','preco-max-i','fonte-i','status-i','datapub-i','excl-i'].forEach(function(id){{document.getElementById(id).value='';}});
  aplicarI();
}}

// Popular dropdown de bairros dinamicamente
(function(){{
  var bairros={{}};
  IMOVEIS.forEach(function(im){{var b=baseBairro(im.bairro);if(b)bairros[b]=(bairros[b]||0)+1;}});
  var sel=document.getElementById('bairro-i');
  Object.keys(bairros).sort().forEach(function(b){{
    var o=document.createElement('option');o.value=b;o.textContent=b+' ('+bairros[b]+')';sel.appendChild(o);
  }});
}})();

['busca-i','bairro-i','quartos-i','banheiros-i','vagas-i','preco-min-i','preco-max-i','fonte-i','status-i','datapub-i','excl-i'].forEach(function(id){{
  document.getElementById(id).addEventListener('input',aplicarI);
}});

/* ════ LOCAÇÃO ════ */
function filtrarL(){{
  var b  = document.getElementById('busca-l').value.toLowerCase();
  var q  = document.getElementById('quartos-l').value;
  var vg = document.getElementById('vagas-l').value;
  var pm = parseFloat(document.getElementById('preco-l').value)||Infinity;
  var fn = document.getElementById('fonte-l').value;
  return LOCACAO.filter(function(im){{
    var hay=[im.obs,im.bairro,im.corretor,im.grupo,im.tipo,im.nome].join(' ').toLowerCase();
    if(b&&hay.indexOf(b)===-1) return false;
    if(q){{var n=parseInt(q);if(q==='4'){{if(!im.quartos||im.quartos<4)return false;}}else{{if(!im.quartos||im.quartos<n)return false;}}}}
    if(vg){{var n2=parseInt(vg);if(vg==='3'){{if(!im.vagas||im.vagas<3)return false;}}else{{if(!im.vagas||im.vagas<n2)return false;}}}}
    if(im.preco&&im.preco>pm) return false;
    if(fn&&im.fonte!==fn) return false;
    return true;
  }});
}}

function ordenarL(l){{
  var o=document.getElementById('ord-l').value; l=l.slice();
  if(o==='preco_asc') l.sort(function(a,b){{return(a.preco||9e9)-(b.preco||9e9);}});
  else if(o==='preco_desc') l.sort(function(a,b){{return(b.preco||0)-(a.preco||0);}});
  else if(o==='area_desc') l.sort(function(a,b){{return(b.area||0)-(a.area||0);}});
  else l.sort(function(a,b){{return(b.data||'').localeCompare(a.data||'');}});
  return l;
}}

function aplicarL(){{
  var lista=ordenarL(filtrarL());
  ['quartos-l','vagas-l','preco-l','fonte-l'].forEach(selActive);
  var cp=lista.filter(function(i){{return i.preco;}});
  var med=cp.length?Math.round(cp.reduce(function(s,i){{return s+i.preco;}},0)/cp.length):0;
  document.getElementById('stats-l').innerHTML=
    '<div class="stat"><strong>'+lista.length+'</strong> imóveis</div>'+
    (med?'<div class="stat"><strong>'+fmtP(med)+'</strong> aluguel médio</div>':'');
  document.getElementById('rtxt-l').textContent=lista.length+' de '+LOCACAO.length;
  document.getElementById('grid-l').innerHTML=lista.length?lista.map(cardI).join(''):
    '<div class="empty"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg><p>Nenhum imóvel para locação encontrado.</p></div>';
}}

function resetarL(){{
  document.getElementById('busca-l').value='';
  ['quartos-l','vagas-l','preco-l','fonte-l'].forEach(function(id){{document.getElementById(id).value='';}});
  aplicarL();
}}

['busca-l','quartos-l','vagas-l','preco-l','fonte-l'].forEach(function(id){{
  document.getElementById(id).addEventListener('input',aplicarL);
}});

/* ════ DEMANDAS ════ */
function cardD(dm){{
  var urgente = dm.obs && dm.obs.toUpperCase().indexOf('URGENTE')!==-1;
  var chips=[
    dm.tipo?('<span class="chip chip-dem">'+dm.tipo+'</span>'):null,
    urgente?'<span class="chip chip-urgente">🔥 URGENTE</span>':null,
    dm.area_min?('<span class="chip">Mín '+dm.area_min+' m²</span>'):null,
    dm.quartos?(dm.quartos+(dm.quartos===1?' quarto':' quartos')):null,
    dm.suites?(dm.suites+(dm.suites===1?' suíte':' suítes')):null,
    dm.banheiros?(dm.banheiros+(dm.banheiros===1?' banheiro':' banheiros')):null,
    dm.vagas?(dm.vagas+(dm.vagas===1?' vaga':' vagas')):null
  ].filter(Boolean).map(function(c){{return typeof c==='string'&&c.indexOf('class="chip')===-1?'<span class="chip">'+c+'</span>':c;}}).join('');
  // Título descreve O QUE É BUSCADO, não quem busca
  var tipo       = dm.tipo       || '';
  var edificio   = dm.edificio   || '';
  var condominio = dm.condominio || '';
  var regiao     = dm.regiao     || '';
  var tituloParts = [];
  if (tipo)       tituloParts.push(tipo);
  if (edificio)   tituloParts.push(edificio);
  if (condominio) tituloParts.push(condominio);
  if (regiao)     tituloParts.push(regiao);
  var titulo = tituloParts.length ? 'Busca ' + tituloParts.join(' · ') : 'Demanda';
  // Seção expandida
  var ceSpecs=[];
  if(dm.area_min)  ceSpecs.push('Mín '+dm.area_min+' m²');
  if(dm.quartos)   ceSpecs.push(dm.quartos+(dm.quartos===1?' quarto':' quartos'));
  if(dm.suites)    ceSpecs.push(dm.suites+(dm.suites===1?' suíte':' suítes'));
  if(dm.banheiros) ceSpecs.push(dm.banheiros+(dm.banheiros===1?' banheiro':' banheiros'));
  if(dm.vagas)     ceSpecs.push(dm.vagas+(dm.vagas===1?' vaga':' vagas'));
  if(dm.orcamento) ceSpecs.push('Orç. até '+fmtP(dm.orcamento));
  var ceOrigem=(dm.corretor||'')+(dm.grupo?' · '+dm.grupo:'')+(dm.data?' · '+dm.data:'');
  var ceBtns='';
  if(dm.contato){{var nc=String(dm.contato).replace(/\D/g,'');if(nc.length>=8&&nc.length<=13)ceBtns+='<a class="ce-btn-wa" href="https://wa.me/'+nc+'" target="_blank">💬 WhatsApp</a>';}}
  var expandHtml='<div class="card-expand">'+
    (ceSpecs.length?'<div class="ce-specs">'+ceSpecs.map(function(s){{return'<span class="ce-spec">'+s+'</span>';}}).join('')+'</div>':'')+
    (dm.obs?'<div class="ce-obs">'+dm.obs.replace(/</g,'&lt;')+'</div>':'')+
    (ceOrigem?'<div class="ce-origem">'+ceOrigem+'</div>':'')+
    (ceBtns?'<div class="ce-btns">'+ceBtns+'</div>':'<div style="color:#bbb;font-size:12px">Sem contato disponível</div>')+
  '</div>';
  return '<div class="card card-dem" onclick="toggleExpand(this)">'+
    '<div class="card-header">'+
      '<div><div class="card-name">'+titulo+' <span class="card-expand-arrow">▾</span></div><div class="card-loc">'+(dm.corretor||'—')+'</div></div>'+
      '<div style="text-align:right">'+
        (dm.orcamento?'<div class="card-price">'+fmtP(dm.orcamento)+'</div><div class="dem-orcamento-label">orçamento máx</div>':'<div class="card-price-na">Consultar</div>')+
      '</div>'+
    '</div>'+
    (chips?'<div class="chips">'+chips+'</div>':'')+
    (dm.obs?'<div class="card-desc">'+dm.obs+'</div>':'')+
    '<div class="card-foot">'+
      '<div class="card-who">'+(dm.grupo||'—')+(dm.data?' · '+dm.data:'')+' </div>'+
      '<div class="foot-right" onclick="event.stopPropagation()">'+btnWa(dm.contato)+'<span class="'+pillCls(dm.status||'Novo')+'">'+(dm.status||'Novo')+'</span></div>'+
    '</div>'+
    expandHtml+
  '</div>';
}}

function filtrarD(){{
  var b   = document.getElementById('busca-d').value.toLowerCase();
  var tp  = document.getElementById('tipo-d').value;
  var rg  = document.getElementById('regiao-d').value.toLowerCase();
  var q   = document.getElementById('quartos-d').value;
  var vg  = document.getElementById('vagas-d').value;
  var am  = parseFloat(document.getElementById('area-d').value)||0;
  var om  = parseFloat(document.getElementById('orc-d').value)||Infinity;
  var st  = document.getElementById('status-d').value;
  return DEMANDAS.filter(function(dm){{
    var hay=[dm.obs,dm.regiao,dm.corretor,dm.grupo,dm.tipo,dm.edificio,dm.condominio].join(' ').toLowerCase();
    if(b&&hay.indexOf(b)===-1) return false;
    if(tp&&(dm.tipo||'').toLowerCase().indexOf(tp.toLowerCase())===-1) return false;
    if(rg){{var drg=(dm.regiao||'').toLowerCase();if(drg.indexOf(rg)===-1) return false;}}
    if(q){{var n=parseInt(q);if(!dm.quartos||dm.quartos<n)return false;}}
    if(vg){{var n2=parseInt(vg);if(!dm.vagas||dm.vagas<n2)return false;}}
    if(am&&(!dm.area_min||dm.area_min<am)) return false;
    if(dm.orcamento&&dm.orcamento>om) return false;
    if(st&&dm.status!==st) return false;
    return true;
  }});
}}

function ordenarD(l){{
  var o=document.getElementById('ord-d').value; l=l.slice();
  if(o==='orc_desc') l.sort(function(a,b){{return(b.orcamento||0)-(a.orcamento||0);}});
  else if(o==='orc_asc') l.sort(function(a,b){{return(a.orcamento||9e9)-(b.orcamento||9e9);}});
  else l.sort(function(a,b){{return(b.data||'').localeCompare(a.data||'');}});
  return l;
}}

var _viewD='cards';
function setViewD(v){{
  _viewD=v;
  document.getElementById('btn-cards-d').className='btn-view'+(v==='cards'?' active':'');
  document.getElementById('btn-edif-d').className='btn-view'+(v==='edificio'?' active':'');
  aplicarD();
}}

function aplicarD(){{
  var lista=ordenarD(filtrarD());
  ['tipo-d','regiao-d','quartos-d','vagas-d','area-d','orc-d','status-d'].forEach(selActive);
  var urgentes=lista.filter(function(d){{return d.obs&&d.obs.toUpperCase().indexOf('URGENTE')!==-1;}}).length;
  var novos=lista.filter(function(d){{return d.status==='Novo';}}).length;
  var co=lista.filter(function(d){{return d.orcamento;}});
  var med=co.length?Math.round(co.reduce(function(s,d){{return s+d.orcamento;}},0)/co.length):0;
  document.getElementById('stats-d').innerHTML=
    '<div class="stat"><strong>'+lista.length+'</strong> demandas</div>'+
    '<div class="stat"><strong>'+novos+'</strong> novas</div>'+
    (urgentes?'<div class="stat"><strong>'+urgentes+'</strong> 🔥 urgentes</div>':'')+
    (med?'<div class="stat"><strong>'+fmtP(med)+'</strong> orçamento médio</div>':'');
  document.getElementById('rtxt-d').textContent=lista.length+' de '+DEMANDAS.length;
  var gridD=document.getElementById('grid-d');
  if(_viewD==='edificio'){{
    _renderEdificioGrupos(lista, gridD, cardD);
  }} else {{
    gridD.className='grid';
    gridD.innerHTML=lista.length?lista.map(cardD).join(''):
      '<div class="empty"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg><p>Nenhuma demanda encontrada.</p></div>';
  }}
}}

function resetarD(){{
  document.getElementById('busca-d').value='';
  ['tipo-d','regiao-d','quartos-d','vagas-d','area-d','orc-d','status-d'].forEach(function(id){{document.getElementById(id).value='';}});
  aplicarD();
}}

// Popular dropdown de regiões dinamicamente
(function(){{
  var regioes={{}};
  DEMANDAS.forEach(function(dm){{
    if(!dm.regiao) return;
    // Se tem ' · ', pegar cada parte
    dm.regiao.split(' · ').forEach(function(r){{
      r=r.trim();
      if(r) regioes[r]=(regioes[r]||0)+1;
    }});
  }});
  var sel=document.getElementById('regiao-d');
  Object.keys(regioes).sort().forEach(function(r){{
    var o=document.createElement('option');o.value=r;o.textContent=r+' ('+regioes[r]+')';sel.appendChild(o);
  }});
}})();

['busca-d','tipo-d','regiao-d','quartos-d','vagas-d','area-d','orc-d','status-d'].forEach(function(id){{
  document.getElementById(id).addEventListener('input',aplicarD);
}});

/* ════ BAIRROS ════ */
var _bairrosInited=false;
var _bairroAtual=null;
var _edificioAtual=null;

function initBairros(){{
  if(_bairrosInited) return;
  _bairrosInited=true;
  renderBairrosList();
}}

function filtrarBairros(){{
  renderBairrosList();
}}

function _buildIndex(){{
  // bairros → edificios → {{imoveis:[], demandas:[]}}
  var idx={{}};
  function addIm(bairro, edif, im){{
    if(!bairro) bairro='Sem bairro';
    if(!edif) edif='—';
    if(!idx[bairro]) idx[bairro]={{}};
    if(!idx[bairro][edif]) idx[bairro][edif]={{imoveis:[],demandas:[]}};
    idx[bairro][edif].imoveis.push(im);
  }}
  function addDm(regiao, edif, dm){{
    var bairros=(regiao||'Sem bairro').split(' · ');
    bairros.forEach(function(b){{
      b=b.trim()||'Sem bairro';
      if(!edif) edif='—';
      if(!idx[b]) idx[b]={{}};
      if(!idx[b][edif]) idx[b][edif]={{imoveis:[],demandas:[]}};
      idx[b][edif].demandas.push(dm);
    }});
  }}
  var excl=['Vendido','Removido','Cancelado','Descartado'];
  IMOVEIS.forEach(function(im){{
    if(excl.indexOf(im.status)!==-1) return;
    addIm(baseBairro(im.bairro), im.edificio||im.condominio||null, im);
  }});
  DEMANDAS.forEach(function(dm){{
    if(['Fechado','Cancelado'].indexOf(dm.status)!==-1) return;
    addDm(dm.regiao, dm.edificio||dm.condominio||null, dm);
  }});
  return idx;
}}

var _bairrosIdx=null;
function getBairrosIdx(){{
  if(!_bairrosIdx) _bairrosIdx=_buildIndex();
  return _bairrosIdx;
}}

function renderBairrosList(){{
  var idx=getBairrosIdx();
  var busca=(document.getElementById('busca-bairros').value||'').toLowerCase();
  var keys=Object.keys(idx).sort(function(a,b){{return a.localeCompare(b,'pt-BR');}});
  if(busca) keys=keys.filter(function(b){{return b.toLowerCase().indexOf(busca)!==-1;}});
  var html='<div class="bairros-list">';
  keys.forEach(function(b){{
    var edifs=idx[b];
    var totalI=0,totalD=0;
    Object.values(edifs).forEach(function(e){{totalI+=e.imoveis.length;totalD+=e.demandas.length;}});
    html+='<div class="bairro-row" onclick="renderEdificiosDoBairro(\''+b.replace(/'/g,"\\'")+'\')">';
    html+='<div class="bairro-name">'+b+'</div>';
    html+='<div class="bairro-badges">';
    if(totalI) html+='<span class="bairro-badge-i">'+totalI+' imóveis</span>';
    if(totalD) html+='<span class="bairro-badge-d">'+totalD+' dem.</span>';
    html+='</div></div>';
  }});
  html+='</div>';
  document.getElementById('content-bairros').innerHTML=html;
}}

function renderEdificiosDoBairro(bairro){{
  _bairroAtual=bairro;
  var idx=getBairrosIdx();
  var edifs=idx[bairro]||{{}};
  var keys=Object.keys(edifs).sort(function(a,b){{
    if(a==='—') return 1; if(b==='—') return -1;
    return a.localeCompare(b,'pt-BR');
  }});
  var html='<div class="bairros-breadcrumb"><a onclick="renderBairrosList()">🏘️ Bairros</a> › <strong>'+bairro+'</strong></div>';
  html+='<div class="bairros-list">';
  keys.forEach(function(e){{
    var data=edifs[e];
    var ni=data.imoveis.length, nd=data.demandas.length;
    html+='<div class="edif-row" onclick="renderImoveisDoEdificio(\''+bairro.replace(/'/g,"\\'")+'\',' + '\''+e.replace(/'/g,"\\'")+'\')">';
    html+='<div class="edif-name">'+(e==='—'?'<span style="color:#bbb">Sem edifício específico</span>':e)+'</div>';
    html+='<div class="bairro-badges">';
    if(ni) html+='<span class="bairro-badge-i">'+ni+'</span>';
    if(nd) html+='<span class="bairro-badge-d">'+nd+' dem.</span>';
    html+='</div></div>';
  }});
  html+='</div>';
  document.getElementById('content-bairros').innerHTML=html;
}}

function renderImoveisDoEdificio(bairro, edif){{
  var idx=getBairrosIdx();
  var data=(idx[bairro]||{{}})[edif]||{{imoveis:[],demandas:[]}};
  var html='<div class="bairros-breadcrumb">'
    +'<a onclick="renderBairrosList()">🏘️ Bairros</a> › '
    +'<a onclick="renderEdificiosDoBairro(\''+bairro.replace(/'/g,"\\'")+'\'">'+bairro+'</a> › '
    +'<strong>'+(edif==='—'?'Sem edifício específico':edif)+'</strong>'
    +'</div>';
  if(data.imoveis.length){{
    html+='<div style="font-size:13px;font-weight:700;color:#888;margin:16px 0 8px;letter-spacing:.5px">IMÓVEIS À VENDA ('+data.imoveis.length+')</div>';
    html+='<div class="bairros-imoveis-grid">'+data.imoveis.map(cardI).join('')+'</div>';
  }}
  if(data.demandas.length){{
    html+='<div style="font-size:13px;font-weight:700;color:#9c72c8;margin:24px 0 8px;letter-spacing:.5px">DEMANDAS ('+data.demandas.length+')</div>';
    html+='<div class="bairros-imoveis-grid">'+data.demandas.map(cardD).join('')+'</div>';
  }}
  if(!data.imoveis.length&&!data.demandas.length){{
    html+='<div class="empty"><p>Nenhum resultado.</p></div>';
  }}
  document.getElementById('content-bairros').innerHTML=html;
}}

/* ════ MATCH ════ */
var VIZINHOS={{"Zona 01":["Zona 07"],"Zona 07":["Jardim Alvorada","Vila Morangueira","Zona 01"],"Zona 08":["Jardim Aclimação","Vila Marumby","Vila Morangueira"],"Parque das Bandeiras":["Jardim Alvorada","Jardim Copacabana","Jardim Diamante","Jardim Dias I","Jardim Paris","Parque Palmeiras","Parque das Laranjeiras"],"Parque das Laranjeiras":["Jardim Copacabana","Jardim Diamante","Jardim Dias I","Parque Palmeiras","Parque das Bandeiras"],"Parque Palmeiras":["Jardim Copacabana","Jardim Diamante","Jardim Dias I","Jardim Monte Rei","Jardim Paris","Parque das Bandeiras","Parque das Laranjeiras"],"Jardim Copacabana":["Jardim Diamante","Jardim Dias I","Jardim Monte Rei","Jardim Paris","Parque Palmeiras","Parque das Bandeiras","Parque das Laranjeiras"],"Jardim Diamante":["Jardim Copacabana","Jardim Dias I","Jardim Monte Rei","Jardim Paris","Jardim Rebouças","Parque Palmeiras","Parque das Bandeiras","Parque das Laranjeiras"],"Jardim Dias I":["Jardim Copacabana","Jardim Diamante","Parque Palmeiras","Parque das Bandeiras","Parque das Laranjeiras"],"Jardim Paris":["Jardim Copacabana","Jardim Diamante","Jardim Guairacá","Jardim Monte Rei","Jardim Rebouças","Jardim Tropical","Parque Palmeiras","Parque das Bandeiras","Parque das Laranjeiras"],"Jardim Monte Rei":["Jardim Copacabana","Jardim Diamante","Jardim Guairacá","Jardim Paris","Jardim Rebouças","Parque Palmeiras"],"Jardim Rebouças":["Jardim Diamante","Jardim Guairacá","Jardim Monte Rei","Jardim Paris","Jardim Tropical"],"Jardim Guairacá":["Jardim Monte Rei","Jardim Paris","Jardim Rebouças","Jardim Tropical","Parque Hortência"],"Cidade Universitária":["Jardim Aurora","Jardim Olímpico","Jardim Tropical","Jardim do Carmo","Parque Hortência"],"Parque Hortência":["Cidade Universitária","Jardim Aurora","Jardim Guairacá","Jardim Olímpico","Jardim Tropical","Jardim do Carmo"],"Jardim do Carmo":["Cidade Universitária","Jardim Aurora","Jardim Olímpico","Jardim Tropical","Parque Hortência"],"Jardim Olímpico":["Cidade Universitária","Jardim Aurora","Jardim Tropical","Jardim do Carmo","Parque Hortência"],"Jardim Aurora":["Cidade Universitária","Jardim Olímpico","Jardim do Carmo","Parque Hortência"],"Jardim Tropical":["Cidade Universitária","Jardim Guairacá","Jardim Olímpico","Jardim Paris","Jardim Rebouças","Jardim do Carmo","Parque Hortência"],"Jardim Alvorada":["Jardim Oásis","Parque das Bandeiras","Vila Morangueira","Zona 07"],"Vila Morangueira":["Jardim Alvorada","Jardim Oásis","Jardim Pinheiros","Jardim da Glória","Zona 07","Zona 08"],"Jardim Oásis":["Jardim Alvorada","Jardim Pinheiros","Jardim da Glória","Vila Morangueira"],"Jardim Pinheiros":["Jardim Oásis","Jardim da Glória","Vila Morangueira"],"Jardim da Glória":["Jardim Oásis","Jardim Pinheiros","Vila Morangueira"],"Vila Marumby":["Jardim Aclimação","Jardim Catedral","Jardim Higienópolis","Jardim Ipanema","Jardim Leblon","Jardim Universo","Parque Tarumã","Zona 08"],"Jardim Aclimação":["Jardim Catedral","Jardim Ipanema","Jardim Leblon","Vila Marumby","Zona 08"],"Jardim Catedral":["Jardim Aclimação","Jardim Ipanema","Jardim Leblon","Parque Tarumã","Vila Marumby"],"Jardim Leblon":["Jardim Aclimação","Jardim Catedral","Jardim Ipanema","Parque Tarumã","Vila Marumby"],"Jardim Ipanema":["Jardim Aclimação","Jardim Catedral","Jardim Higienópolis","Jardim Leblon","Jardim Universo","Parque Tarumã","Vila Marumby"],"Parque Tarumã":["Jardim Catedral","Jardim Ipanema","Jardim Leblon","Jardim Universo","Vila Marumby"],"Jardim Higienópolis":["Jardim Espanha","Jardim Iguaçu","Jardim Ipanema","Jardim Universo","Vila Marumby"],"Jardim Universo":["Jardim Espanha","Jardim Higienópolis","Jardim Iguaçu","Jardim Ipanema","Parque Tarumã","Vila Marumby"],"Jardim Iguaçu":["Jardim Espanha","Jardim Europa","Jardim Higienópolis","Jardim Universo"],"Jardim Espanha":["Jardim Barcelona","Jardim Europa","Jardim Higienópolis","Jardim Iguaçu","Jardim Universo"],"Jardim Europa":["Jardim Barcelona","Jardim Espanha","Jardim Iguaçu","Parque Industrial"],"Jardim Barcelona":["Jardim Espanha","Jardim Europa","Parque Industrial"],"Parque Industrial":["Jardim Barcelona","Jardim Europa"]}};
var BAIRRO_ALIAS={{"Jardim Paris III":"Jardim Paris","Jardim Paris VI":"Jardim Paris","Jardim Pinheiros III":"Jardim Pinheiros","Jardim Paulista III":"Jardim Paulista","Jardim Paulista IV":"Jardim Paulista","Jardim Dias II":"Jardim Dias I","Parque Industrial 200":"Parque Industrial","Jardim Novo Oásis":"Jardim Oásis","Jardim Imperial II":"Jardim Imperial"}};

function canonicBairro(str){{
  if(!str) return '';
  // Pegar parte antes de " · " (bairro principal)
  var b = str.split(' · ')[0].split(',')[0].trim();
  return BAIRRO_ALIAS[b] || b;
}}

function ehVizinho(demRegiao, imBairro){{
  if(!demRegiao||!imBairro) return false;
  var imB = canonicBairro(imBairro);
  var demWords = demRegiao.toLowerCase().split(/\\W+/).filter(function(w){{return w.length>3;}});
  // Encontrar qual bairro do mapa corresponde à região da demanda
  var demBairro = null;
  Object.keys(VIZINHOS).forEach(function(b){{
    if(demWords.some(function(w){{return b.toLowerCase().indexOf(w)!==-1 || w.indexOf(b.toLowerCase().split(' ')[1]||'x')!==-1;}}))
      demBairro = b;
  }});
  if(!demBairro) return false;
  var vizList = VIZINHOS[demBairro] || [];
  return vizList.some(function(v){{
    return imB.toLowerCase().indexOf(v.toLowerCase())!==-1 || v.toLowerCase().indexOf(imB.toLowerCase())!==-1;
  }});
}}

function _normEdif(s){{
  // Normaliza nome de edifício para comparação: lowercase, sem espaços/pontuação
  return (s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
}}

function matchImoveis(dm){{
  var excl=['Vendido','Removido','Cancelado','Descartado'];
  var demBairroCanon=dm.regiao?canonicBairro(dm.regiao):null;
  // Normaliza edifício da demanda para match fuzzy (NEST635 == NEST 635)
  var demEdifNorm=_normEdif(dm.edificio||dm.condominio||'');
  var scored=[];
  IMOVEIS.forEach(function(im){{
    if(excl.indexOf(im.status)!==-1) return;
    // Filtro hard: quando há região, só mostrar imóveis do mesmo bairro ou vizinhos próximos
    if(demBairroCanon){{
      var imBC=canonicBairro(im.bairro||'');
      var mesmoBairro=!!(imBC&&(imBC.toLowerCase().indexOf(demBairroCanon.toLowerCase())!==-1||demBairroCanon.toLowerCase().indexOf(imBC.toLowerCase())!==-1));
      if(!mesmoBairro&&!ehVizinho(dm.regiao,im.bairro||'')) return;
    }}
    var score=0,total=0;
    var tipoOk=true,edificioOk=false;
    // edificio — critério de pontuação (NÃO hard filter).
    // Imóveis do mesmo edifício pontuam mais → exact.
    // Imóveis de outros prédios com config similar → near.
    if(demEdifNorm){{
      total++;
      var imEdifNorm=_normEdif(im.edificio||im.condominio||im.nome||'');
      edificioOk=!!(imEdifNorm&&(imEdifNorm.indexOf(demEdifNorm)!==-1||demEdifNorm.indexOf(imEdifNorm)!==-1));
      if(edificioOk) score++;
    }}
    // tipo — 'Imóvel' é wildcard (aceita qualquer tipo sem penalizar)
    if(dm.tipo){{
      var dt=dm.tipo.toLowerCase();
      if(dt!=='imóvel'&&dt!=='imovel'){{
        total++;
        var it=(im.tipo||'').toLowerCase();
        if(it&&(it.indexOf(dt)!==-1||dt.indexOf(it)!==-1)){{score++;}}else{{tipoOk=false;}}
      }}
    }}
    // quartos
    if(dm.quartos){{total++;if(im.quartos&&im.quartos>=dm.quartos)score++;}}
    // suites
    if(dm.suites)    {{total++;if(im.suites&&im.suites>=dm.suites)score++;}}
    // banheiros
    if(dm.banheiros) {{total++;if(im.suites&&im.suites>=dm.banheiros)score++;}}
    // vagas
    if(dm.vagas)  {{total++;if(im.vagas&&im.vagas>=dm.vagas)score++;}}
    // area: acima de 80% da área mínima (sem teto — quanto maior melhor)
    if(dm.area_min){{
      total++;
      if(im.area && im.area>=dm.area_min*0.8) score++;
    }}
    // orcamento: ±20% (não mostrar imóveis muito baratos nem muito caros)
    var precoOk=false,precoDentro20=false;
    if(dm.orcamento){{
      total++;
      precoOk=!!(im.preco&&im.preco>=dm.orcamento*0.8&&im.preco<=dm.orcamento*1.2);
      precoDentro20=precoOk;
      if(precoOk) score++;
    }}
    // regiao — comparação canônica (não word overlap solto)
    var regiaoOk=false,regiaoVizinha=false;
    if(dm.regiao){{
      total++;
      var imBC2=canonicBairro(im.bairro||'');
      regiaoOk=!!(demBairroCanon&&imBC2&&(imBC2.toLowerCase().indexOf(demBairroCanon.toLowerCase())!==-1||demBairroCanon.toLowerCase().indexOf(imBC2.toLowerCase())!==-1));
      if(regiaoOk){{score++;}}else{{regiaoVizinha=ehVizinho(dm.regiao,im.bairro||'');}}
    }}
    if(total>0) scored.push({{im:im,score:score,total:total,tipoOk:tipoOk,edificioOk:edificioOk,precoOk:precoOk,precoDentro20:precoDentro20,regiaoOk:regiaoOk,regiaoVizinha:regiaoVizinha}});
  }});
  // Prioridade: 1º mesmo edifício, 2º score decrescente, 3º preço crescente
  scored.sort(function(a,b){{
    if(a.edificioOk!==b.edificioOk) return a.edificioOk?-1:1;
    if(b.score!==a.score) return b.score-a.score;
    return(a.im.preco||9e9)-(b.im.preco||9e9);
  }});
  var exact=scored.filter(function(e){{return e.score===e.total;}});
  var exactSet={{}};exact.forEach(function(e){{exactSet[e.im.obs||e.im.id]=1;}});
  var near=scored.filter(function(e){{
    if(e.score!==e.total-1||e.total<=1) return false;
    if(exactSet[e.im.obs||e.im.id]) return false;
    // tipo deve sempre coincidir no "quase lá" (exceto wildcard 'Imóvel')
    if(dm.tipo&&dm.tipo.toLowerCase()!=='imóvel'&&dm.tipo.toLowerCase()!=='imovel'&&!e.tipoOk) return false;
    // preço deve estar dentro de ±20% do orçamento
    if(dm.orcamento&&!e.precoOk&&!e.precoDentro20) return false;
    // região: se o critério falhou, só aceitar bairro vizinho (não qualquer lugar)
    if(dm.regiao&&!e.regiaoOk&&!e.regiaoVizinha) return false;
    return true;
  }});
  return {{exact:exact, near:near}};
}}

function mscoreCls(score,total){{
  if(total===0) return 'mscore-low';
  var p=score/total;
  return p>=0.7?'mscore-high':p>=0.4?'mscore-mid':'mscore-low';
}}

function missedCriteria(dm, im){{
  var missed=[];
  // edificio — aponta quando o imóvel é de outro prédio (config similar)
  if(dm.edificio||dm.condominio){{
    var demE=_normEdif(dm.edificio||dm.condominio||'');
    var imE=_normEdif(im.edificio||im.condominio||im.nome||'');
    if(demE&&!(imE&&(imE.indexOf(demE)!==-1||demE.indexOf(imE)!==-1))){{
      missed.push('edifício '+(dm.edificio||dm.condominio));
    }}
  }}
  if(dm.tipo){{var dt=dm.tipo.toLowerCase(),it=(im.tipo||'').toLowerCase();if(dt!=='imóvel'&&dt!=='imovel'&&!(it&&(it.indexOf(dt)!==-1||dt.indexOf(it)!==-1)))missed.push('tipo');}}
  if(dm.quartos&&!(im.quartos&&im.quartos>=dm.quartos)) missed.push(dm.quartos+' quartos');
  if(dm.suites&&!(im.suites&&im.suites>=dm.suites))         missed.push(dm.suites+' suítes');
  if(dm.banheiros&&!(im.suites&&im.suites>=dm.banheiros)) missed.push(dm.banheiros+' banheiros');
  if(dm.vagas&&!(im.vagas&&im.vagas>=dm.vagas))           missed.push(dm.vagas+' vagas');
  if(dm.area_min&&!(im.area&&im.area>=dm.area_min*0.8)) missed.push('área < '+Math.round(dm.area_min*0.8)+' m²');
  if(dm.orcamento&&!(im.preco&&im.preco>=dm.orcamento*0.8&&im.preco<=dm.orcamento*1.2)){{var pct=im.preco?Math.round((im.preco/dm.orcamento-1)*100):null;missed.push(pct!==null?(pct>20?'+'+pct+'% do orçamento':pct<-20?pct+'% abaixo do orçamento':'fora ±20%'):'sem preço');}}
  if(dm.regiao){{var words=dm.regiao.toLowerCase().split(/\\W+/).filter(function(w){{return w.length>3;}});var bl=(im.bairro||'').toLowerCase();if(!(words.length&&words.some(function(w){{return bl.indexOf(w)!==-1;}}))){{var viz=ehVizinho(dm.regiao,im.bairro||'');missed.push(viz?'bairro vizinho':'região');}}}}
  return missed;
}}

function cardMatchIm(entry, dm, isNear){{
  var im=entry.im,isJJ=im.fonte==='Junior Joda';
  var imIdx=IMOVEIS.indexOf(im);
  var nome=cardNome(im);
  var infoParts=[
    fmtA(im.area),
    im.quartos?(im.quartos+(im.quartos===1?' qt':' qts')):null,
    im.suites?(im.suites+(im.suites===1?' suíte':' suítes')):null,
    im.vagas?(im.vagas+(im.vagas===1?' vaga':' vagas')):null,
    im.bairro||null
  ].filter(Boolean).join(' · ');
  var badge=isNear
    ? '<span class="match-score mscore-mid">Falta: '+missedCriteria(dm,im).join(', ')+'</span>'
    : '<span class="match-score mscore-high">✓ todos critérios</span>';
  var onclick=imIdx>=0?' onclick="abrirModalPorIdx('+imIdx+');event.stopPropagation()"':'';
  return '<div class="match-row-item'+(isJJ?' match-row-jj':'')+(isNear?' match-row-near':'')+'"'+onclick+'>'+
    '<div class="mri-main">'+
      '<div class="mri-title">'+nome+'</div>'+
      '<div class="mri-info">'+infoParts+'</div>'+
    '</div>'+
    '<div class="mri-right">'+
      '<div class="mri-price">'+(im.preco?fmtP(im.preco):'Consultar')+'</div>'+
      '<div class="mri-actions">'+badge+'<span style="font-size:10px;color:#b09ad8">▶ detalhes</span>'+'</div>'+
    '</div>'+
  '</div>';
}}

function renderMatch(){{
  var totalExact=0;
  var items=[];
  DEMANDAS.forEach(function(dm,idx){{
    var res=matchImoveis(dm);
    totalExact+=res.exact.length;
    var demTitle=(dm.regiao&&dm.tipo)?dm.tipo+' · '+dm.regiao:(dm.regiao||dm.tipo||dm.corretor||'Demanda');
    var subParts=[];
    if(dm.corretor) subParts.push(dm.corretor);
    if(dm.orcamento) subParts.push('Orçamento: '+fmtP(dm.orcamento));
    if(dm.quartos)   subParts.push(dm.quartos+' quartos');
    if(dm.suites)    subParts.push(dm.suites+' suítes');
    if(dm.vagas)     subParts.push(dm.vagas+' vagas');
    if(dm.area_min)  subParts.push('Mín '+dm.area_min+' m²');
    if(dm.regiao)    subParts.push('Região: '+dm.regiao);
    var bodyHtml=
      (res.exact.length?
        '<div class="match-grid">'+res.exact.map(function(e){{return cardMatchIm(e,dm,false);}}).join('')+'</div>':
        '<div class="match-none">Nenhum imóvel atende a todos os critérios.</div>')+
      (res.near.length?
        '<div class="match-near-label">Quase lá — falta apenas 1 critério</div>'+
        '<div class="match-grid">'+res.near.map(function(e){{return cardMatchIm(e,dm,true);}}).join('')+'</div>':
        '');
    items.push(
      '<div class="match-item" id="mi-'+idx+'">'+
        '<div class="match-item-header" onclick="toggleMatch('+idx+')">'+
          '<div class="match-item-left">'+
            '<div class="match-dem-title">'+demTitle+'</div>'+
            '<div class="match-dem-sub">'+subParts.join(' · ')+'</div>'+
          '</div>'+
          '<div class="match-item-right">'+
            (dm.contato
              ? btnWa(dm.contato)
              : '<span class="btn-sem-contato" title="Número não capturado — LID WhatsApp">📵 Sem contato</span>')+
            '<span class="match-count-badge">'+res.exact.length+' exatos · '+res.near.length+' quase</span>'+
            '<span class="match-chevron">&#9662;</span>'+
          '</div>'+
        '</div>'+
        '<div class="match-body">'+bodyHtml+'</div>'+
      '</div>'
    );
  }});
  document.getElementById('badge-match').textContent=totalExact;
  document.getElementById('content-match').innerHTML=
    items.length?'<div class="match-list">'+items.join('')+'</div>':
    '<div class="empty"><p>Nenhuma demanda cadastrada.</p></div>';
  if(items.length) toggleMatch(0);
}}
function toggleMatch(idx){{
  var el=document.getElementById('mi-'+idx);
  if(el) el.classList.toggle('open');
}}


/* init */
aplicarI();
aplicarL();
aplicarD();

/* ── Modal de detalhes do imóvel ── */
(function(){{
  var overlay=document.createElement('div');
  overlay.id='im-modal-overlay';
  overlay.innerHTML=
    '<div id="im-modal">'+
      '<button class="im-modal-close" onclick="fecharModalIm()">✕</button>'+
      '<div id="im-modal-body"></div>'+
    '</div>';
  document.body.appendChild(overlay);
  overlay.addEventListener('click',function(e){{if(e.target===overlay)fecharModalIm();}});
}})();

function abrirModalPorIdx(idx){{
  abrirModalIm(idx);
}}
function abrirModalIm(idx){{
  var im=IMOVEIS[idx];
  if(!im) return;
  var specs=[];
  if(im.area)    specs.push(im.area+' m²');
  if(im.quartos) specs.push(im.quartos+(im.quartos===1?' quarto':' quartos'));
  if(im.suites)  specs.push(im.suites+(im.suites===1?' suíte':' suítes'));
  if(im.banheiros) specs.push(im.banheiros+(im.banheiros===1?' banheiro':' banheiros'));
  if(im.vagas)   specs.push(im.vagas+(im.vagas===1?' vaga':' vagas'));
  var nome=cardNome(im);
  var precoHtml=im.preco
    ? '<div class="im-modal-preco">'+fmtP(im.preco)+'</div>'
    : '<div class="im-modal-preco" style="color:#aaa">Consultar</div>';
  var obsHtml=im.obs
    ? '<div class="im-modal-obs">'+im.obs.replace(/</g,'&lt;')+'</div>'
    : '';
  var origem=(im.corretor?im.corretor:'')+(im.grupo?' · '+im.grupo:'')+(im.data?' · '+im.data:'');
  var btns='';
  if(im.contato){{var n=String(im.contato).replace(/\\D/g,'');if(n.length>=8&&n.length<=13) btns+='<a class="im-btn-wa" href="https://wa.me/'+n+'" target="_blank">💬 WhatsApp</a>';}}
  if(im.link) btns+='<a class="im-btn-link" href="'+im.link+'" target="_blank">🔗 Ver anúncio</a>';
  document.getElementById('im-modal-body').innerHTML=
    '<div class="im-modal-tipo">'+(im.tipo||'Imóvel')+'</div>'+
    '<div class="im-modal-titulo">'+nome+'</div>'+
    '<div class="im-modal-bairro">'+(im.bairro||'')+'</div>'+
    '<div class="im-modal-specs">'+specs.map(function(s){{return '<span class="im-spec">'+s+'</span>';}}).join('')+'</div>'+
    precoHtml+
    obsHtml+
    '<div class="im-modal-corretor">'+origem+'</div>'+
    (btns?'<div class="im-modal-btns">'+btns+'</div>':'<div style="color:#aaa;font-size:13px">Sem contato disponível</div>');
  document.getElementById('im-modal-overlay').classList.add('active');
  document.body.style.overflow='hidden';
}}
function fecharModalIm(){{
  document.getElementById('im-modal-overlay').classList.remove('active');
  document.body.style.overflow='';
}}
document.addEventListener('keydown',function(e){{if(e.key==='Escape')fecharModalIm();}});
</script>
</body>
</html>"""
    return html


def main():
    db.init_db()
    imoveis  = carregar_imoveis()
    demandas = carregar_demandas()
    n_jj = sum(1 for i in imoveis if i.get("fonte") == "Junior Joda")
    n_vr = sum(1 for i in imoveis if i.get("fonte") == "VivaReal")
    html = gerar_html(imoveis, demandas)
    SITE.write_text(html, encoding="utf-8")
    print(f"✅ Site gerado: {SITE} ({len(imoveis)} imóveis [{n_jj} JJ · {n_vr} VR] · {len(demandas)} demandas)")


if __name__ == "__main__":
    main()
