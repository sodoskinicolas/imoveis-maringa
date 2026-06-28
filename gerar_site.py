#!/usr/bin/env python3
"""
gerar_site.py
Lê Imoveis_Grupos.xlsx + Demandas_Grupos.xlsx + JuniorJoda_Imoveis.xlsx e gera Imoveis.html.
Chamado automaticamente pelo bot_grupos_wa.py e bot_demandas_wa.py após cada inserção.

Uso manual:
  python gerar_site.py
"""

import json
import math
from pathlib import Path
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    print("Erro: pandas não instalado. Execute: pip install pandas openpyxl")
    raise

PLANILHA   = Path(__file__).parent / "Imoveis_Grupos.xlsx"
DEMANDAS   = Path(__file__).parent / "Demandas_Grupos.xlsx"
JUNIORJODA = Path(__file__).parent / "JuniorJoda_Imoveis.xlsx"
VIVAREAL   = Path(__file__).parent / "VivaReal_Imoveis.xlsx"
SITE       = Path(__file__).parent / "Imoveis.html"
WA_JJ      = "5544988132965"   # WhatsApp Junior Joda Soluções Imobiliárias


def limpar(val):
    if val is None: return None
    if isinstance(val, float) and math.isnan(val): return None
    return val




def carregar_imoveis():
    df = pd.read_excel(PLANILHA, sheet_name="Imóveis", dtype=str)
    df = df.where(pd.notnull(df), None)
    rows = []
    for _, r in df.iterrows():
        if not r.get("Data Captura"): continue
        # JJ and VR entries are loaded separately — skip to avoid duplicates
        grupo = (r.get("Grupo", "") or "").strip()
        if grupo == "juniorjoda.com.br": continue
        if grupo == "vivareal.com.br": continue
        def toint(x):
            try: return int(float(x)) if x else None
            except: return None
        def tofloat(x):
            try: return float(x) if x else None
            except: return None
        rows.append({
            "data":     r.get("Data Captura", "") or "",
            "grupo":    r.get("Grupo", "") or "",
            "corretor": r.get("Corretor", "") or "",
            "contato":  r.get("Contato (WhatsApp)", "") or "",
            "tipo":     r.get("Tipo", "") or "Apartamento",
            "bairro":   r.get("Bairro / Endereço", "") or "",
            "area":     tofloat(r.get("Área (m²)")),
            "quartos":  toint(r.get("Quartos")),
            "suites":   toint(r.get("Suítes")),
            "vagas":    toint(r.get("Vagas")),
            "preco":    toint(r.get("Preço (R$)")),
            "obs":              r.get("Observações", "") or "",
            "status":           r.get("Status", "Novo") or "Novo",
            "data_publicacao":  r.get("Data Publicação", "") or "",
            "link":     "",
            "fonte":    "",
        })
    return rows


def carregar_juniorjoda():
    """Lê JuniorJoda_Imoveis.xlsx (abas Venda e Locação) e retorna no mesmo formato de carregar_imoveis()."""
    if not JUNIORJODA.exists(): return []
    rows = []
    for sheet_name, modalidade in [("📋 Venda", "Venda"), ("🔑 Locação", "Locação")]:
        try:
            df = pd.read_excel(JUNIORJODA, sheet_name=sheet_name, dtype=str, header=1)
        except Exception:
            continue
        df = df.where(pd.notnull(df), None)
        for _, r in df.iterrows():
            ref = r.get("Ref.", "") or ""
            if not ref: continue
            def tof(x):
                try: return float(x) if x and str(x).strip() not in ("", "None") else None
                except: return None
            def toi(x):
                try: return int(float(x)) if x and str(x).strip() not in ("", "0", "None") else None
                except: return None
            preco_raw = r.get("Preço (R$)", "") or ""
            try:
                preco_num = int(float(preco_raw)) if preco_raw and str(preco_raw).strip() not in ("", "None", "Consulte") else None
            except:
                preco_num = None
            nome  = r.get("Empreendimento", "") or ""
            tipo  = r.get("Tipo", "") or ""
            bairro = r.get("Bairro / Localização", "") or ""
            cidade = r.get("Cidade", "") or ""
            area_priv = tof(r.get("Área Priv. (m²)"))
            area_tot  = tof(r.get("Área Total (m²)"))
            area = area_priv or area_tot
            label_mod = "Aluguel" if modalidade == "Locação" else "Venda"
            obs_final = f"Ref. {ref}"
            rows.append({
                "data":     datetime.now().strftime("%Y-%m-%d"),
                "grupo":    "juniorjoda.com.br",
                "corretor": "Junior Joda Soluções Imobiliárias",
                "contato":  WA_JJ,
                "tipo":     tipo,
                "nome":     nome,   # empreendimento — used directly for card title
                "bairro":   f"{bairro} · {cidade}".strip(" ·") if cidade else bairro,
                "area":     area,
                "quartos":  toi(r.get("Quartos")),
                "suites":   toi(r.get("Suítes")),
                "vagas":    toi(r.get("Vagas")),
                "preco":    preco_num,
                "obs":      obs_final,
                "status":   label_mod,
                "link":     f"https://juniorjoda.com.br/imovel/{ref}/",
                "fonte":    "Junior Joda",
            })
    return rows


def carregar_vivareal():
    """Lê VivaReal_Imoveis.xlsx e retorna no mesmo formato de carregar_imoveis()."""
    if not VIVAREAL.exists(): return []
    rows = []
    try:
        df = pd.read_excel(VIVAREAL, sheet_name="VivaReal Maringá", dtype=str)
    except Exception:
        return []
    df = df.where(pd.notnull(df), None)
    for _, r in df.iterrows():
        id_ = r.get("ID VivaReal", "") or ""
        if not id_: continue
        def tof(x):
            try: return float(x.replace(",",".")) if x and str(x).strip() not in ("","None") else None
            except: return None
        def toi(x):
            try: return int(float(x)) if x and str(x).strip() not in ("","None","0") else None
            except: return None
        link = r.get("Link", "") or ""
        bairro = r.get("Bairro", "") or ""
        rua    = r.get("Endereço", "") or ""
        rows.append({
            "data":             r.get("Data Captura", "") or "",
            "grupo":            "vivareal.com.br",
            "corretor":         r.get("Corretor", "") or "VivaReal",
            "contato":          "",
            "tipo":             r.get("Tipo", "") or "Imóvel",
            "bairro":           f"{bairro} · {rua}".strip(" ·") if rua else bairro,
            "area":             tof(r.get("Área (m²)")),
            "quartos":          toi(r.get("Quartos")),
            "suites":           toi(r.get("Suítes")),
            "vagas":            toi(r.get("Vagas")),
            "preco":            toi(r.get("Preço (R$)")),
            "obs":              f"id:{id_}",
            "status":           "Venda",
            "data_publicacao":  r.get("Data Publicação", "") or "",
            "link":             link,
            "fonte":            "VivaReal",
        })
    return rows


def carregar_demandas():
    if not DEMANDAS.exists(): return []
    df = pd.read_excel(DEMANDAS, sheet_name="Demandas", dtype=str)
    df = df.where(pd.notnull(df), None)
    rows = []
    for _, r in df.iterrows():
        if not r.get("Data"): continue
        def toint(x):
            try: return int(float(x)) if x else None
            except: return None
        rows.append({
            "data":      r.get("Data", "") or "",
            "grupo":     r.get("Grupo", "") or "",
            "corretor":  r.get("Corretor", "") or "",
            "contato":   r.get("Contato (WhatsApp)", "") or "",
            "tipo":      r.get("Tipo Buscado", "") or "Apartamento",
            "regiao":    r.get("Bairro / Região", "") or "",
            "area_min":  toint(r.get("Área Mín (m²)")),
            "quartos":   toint(r.get("Quartos")),
            "suites":    toint(r.get("Suítes")),
            "banheiros": toint(r.get("Banheiros")),
            "vagas":     toint(r.get("Vagas")),
            "orcamento": toint(r.get("Orçamento Máx (R$)")),
            "obs":       r.get("Observações", "") or "",
            "status":    r.get("Status", "Novo") or "Novo",
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
.card{{background:#fff;border:1.5px solid #e8e8e4;border-radius:12px;padding:18px;display:flex;flex-direction:column;gap:12px;transition:box-shadow .15s,border-color .15s}}
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

/* Card — demandas (borda roxa) */
.card-dem{{border-color:#e4d8f5}}
.card-dem:hover{{border-color:#c4a9e8}}
.card-dem .card-name{{color:#6b21a8}}
.card-dem .card-price{{color:#6b21a8}}
.dem-orcamento-label{{font-size:11px;color:#9c72c8;font-weight:500;text-align:right;margin-top:2px}}

.btn-wa{{display:inline-flex;align-items:center;gap:5px;padding:6px 12px;background:#25d366;color:#fff;border-radius:8px;font-size:12px;font-weight:600;text-decoration:none;transition:opacity .15s}}
.btn-wa:hover{{opacity:.85}}
.btn-wa svg{{width:14px;height:14px}}
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
.match-block{{margin-bottom:28px}}
.match-dem-header{{background:#fff;border:1.5px solid #e4d8f5;border-radius:12px;padding:16px 18px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}}
.match-dem-info{{flex:1;min-width:200px}}
.match-dem-title{{font-size:15px;font-weight:700;color:#6b21a8}}
.match-dem-sub{{font-size:12px;color:#999;margin-top:3px;line-height:1.6}}
.match-count-badge{{background:#f0eafb;color:#6b21a8;font-size:12px;font-weight:700;padding:5px 12px;border-radius:99px;white-space:nowrap}}
.match-row{{display:flex;gap:10px;overflow-x:auto;padding-bottom:8px}}
.match-row::-webkit-scrollbar{{height:4px}}.match-row::-webkit-scrollbar-thumb{{background:#ddd;border-radius:99px}}
.match-card{{background:#fff;border:1.5px solid #e8e8e4;border-radius:10px;padding:14px;min-width:230px;max-width:260px;flex-shrink:0;display:flex;flex-direction:column;gap:8px;transition:box-shadow .15s}}
.match-card:hover{{box-shadow:0 4px 16px rgba(0,0,0,.08);border-color:#ccc}}
.match-card-jj{{border-color:#cce0f5}}.match-card-jj:hover{{border-color:#85bff5}}
.match-card-name{{font-size:13px;font-weight:600;color:#111;line-height:1.3}}
.match-card-loc{{font-size:11px;color:#999;margin-top:2px}}
.match-card-price{{font-size:15px;font-weight:700;color:#111;letter-spacing:-.3px}}
.match-score{{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:700}}
.mscore-high{{background:#eaf5e2;color:#2d7a1a}}
.mscore-mid{{background:#fff3e0;color:#a06000}}
.mscore-low{{background:#f0f0ec;color:#777}}
.match-none{{color:#bbb;font-size:13px;padding:16px 0;text-align:center}}
.match-near-label{{font-size:12px;font-weight:600;color:#a06000;margin:14px 0 8px;padding-left:2px;letter-spacing:.2px}}
.match-card-near{{border-color:#fde8c0;opacity:.9}}
.match-card-near:hover{{border-color:#f5c166;opacity:1}}


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
</nav>

<!-- ═══ PAINEL IMÓVEIS ═══ -->
<div class="panel active" id="panel-imoveis">
  <div class="hero">
    <div class="search-wrap">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input type="text" id="busca-i" class="search-input" placeholder="Buscar por nome, bairro, corretor…" autocomplete="off">
    </div>
    <div class="filterbar">
      <select class="fsel" id="quartos-i">
        <option value="">Quartos</option>
        <option value="1">1 quarto</option><option value="2">2 quartos</option>
        <option value="3">3 quartos</option><option value="4">4+</option>
      </select>
      <select class="fsel" id="vagas-i">
        <option value="">Vagas</option>
        <option value="1">1 vaga</option><option value="2">2 vagas</option><option value="3">3+</option>
      </select>
      <select class="fsel" id="preco-i">
        <option value="">Preço até</option>
        <option value="300000">R$ 300 mil</option><option value="400000">R$ 400 mil</option>
        <option value="500000">R$ 500 mil</option><option value="700000">R$ 700 mil</option>
        <option value="1000000">R$ 1 milhão</option><option value="2000000">R$ 2 milhões</option>
      </select>
      <select class="fsel" id="fonte-i">
        <option value="">Todas as fontes</option>
        <option value="Junior Joda">Junior Joda</option>
        <option value="VivaReal">VivaReal</option>
      </select>
      <select class="fsel" id="status-i">
        <option value="">Status</option>
        <option>Novo</option><option>Verificado</option>
        <option>Em Contato</option><option>Vendido</option><option>Venda</option>
        <option>Aluguel</option><option>Descartado</option>
      </select>
      <select class="fsel" id="datapub-i">
        <option value="">Data publicação</option>
        <option value="30">Últimos 30 dias</option>
        <option value="90">Últimos 90 dias</option>
        <option value="180">Últimos 6 meses</option>
        <option value="365">Último ano</option>
      </select>
      <div class="filter-sep"></div>
      <button class="btn-clear" onclick="resetarI()">Limpar</button>
    </div>
  </div>
  <div class="statsbar" id="stats-i"></div>
  <div class="content">
    <div class="results-row">
      <span class="results-txt" id="rtxt-i"></span>
      <select class="sort-sel" id="ord-i" onchange="aplicarI()">
        <option value="data_desc">Mais recentes</option>
        <option value="preco_asc">Menor preço</option>
        <option value="preco_desc">Maior preço</option>
        <option value="area_desc">Maior área</option>
      </select>
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

<!-- ═══ PAINEL DEMANDAS ═══ -->
<div class="panel" id="panel-demandas">
  <div class="hero">
    <div class="search-wrap">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input type="text" id="busca-d" class="search-input" placeholder="Buscar por corretor, região, observações…" autocomplete="off">
    </div>
    <div class="filterbar">
      <select class="fsel" id="quartos-d">
        <option value="">Quartos</option>
        <option value="1">1 quarto</option><option value="2">2 quartos</option>
        <option value="3">3 quartos</option><option value="4">4+</option>
      </select>
      <select class="fsel" id="vagas-d">
        <option value="">Vagas</option>
        <option value="1">1 vaga</option><option value="2">2 vagas</option><option value="3">3+</option>
      </select>
      <select class="fsel" id="orc-d">
        <option value="">Orçamento até</option>
        <option value="300000">R$ 300 mil</option><option value="400000">R$ 400 mil</option>
        <option value="500000">R$ 500 mil</option><option value="700000">R$ 700 mil</option>
        <option value="1000000">R$ 1 milhão</option><option value="2000000">R$ 2 milhões</option>
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
      <select class="sort-sel" id="ord-d" onchange="aplicarD()">
        <option value="data_desc">Mais recentes</option>
        <option value="orc_desc">Maior orçamento</option>
        <option value="orc_asc">Menor orçamento</option>
      </select>
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
    'Venda':'venda','Aluguel':'aluguel'
  }};
  return 'pill pill-'+(m[s]||'novo');
}}

function btnWa(num){{
  if(!num) return '';
  return '<a class="btn-wa" href="https://wa.me/'+num.replace(/\\D/g,'')+'" target="_blank">'+
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
function cardNome(im){{
  if (im.fonte === 'Junior Joda') {{
    var tipo = im.tipo || 'Imóvel';
    return im.nome ? tipo + ' · ' + im.nome : tipo;
  }}
  if (im.fonte === 'VivaReal') {{
    var tipo = im.tipo || 'Imóvel';
    var bairroPrincipal = im.bairro ? im.bairro.split(' · ')[0].trim() : '';
    return bairroPrincipal ? tipo + ' · ' + bairroPrincipal : tipo;
  }}
  if(!im.obs) return im.tipo||'Imóvel';
  var p=im.obs.split('|')[0].trim();
  return p.length>2?p:(im.tipo||'Imóvel');
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
  var linkBtn = im.link ? '<a class="btn-link" href="'+im.link+'" target="_blank">Ver ↗</a>' : '';
  // Para JJ: obs já contém apenas "Ref. XXXXX" — exibe direto no corpo
  // Para VR: mostra data de publicação
  var obsDisplay = isVR
    ? (im.data_publicacao ? 'Publicado em '+im.data_publicacao : '')
    : (im.obs || '');
  var cardCls = isJJ ? ' card-jj' : isVR ? ' card-vr' : isNovo ? ' card-novo' : '';
  return '<div class="card'+cardCls+'">'+
    '<div class="card-header">'+
      '<div><div class="card-name">'+cardNome(im)+'</div>'+(im.bairro?'<div class="card-loc">'+im.bairro+'</div>':'')+' </div>'+
      (im.preco?'<div class="card-price">'+fmtP(im.preco)+'</div>':'<div class="card-price-na">Consultar</div>')+
    '</div>'+
    (chips?'<div class="chips">'+chips+'</div>':'')+
    (obsDisplay?'<div class="card-desc">'+obsDisplay+'</div>':'')+
    '<div class="card-foot">'+
      '<div class="card-who">'+(im.corretor||'—')+'<br>'+(im.grupo||'')+(im.data?' · '+im.data:'')+' </div>'+
      '<div class="foot-right">'+btnWa(im.contato)+linkBtn+'<span class="'+pillCls(im.status||'Novo')+'">'+(im.status||'Novo')+'</span></div>'+
    '</div>'+
  '</div>';
}}

function filtrarI(){{
  var b  = document.getElementById('busca-i').value.toLowerCase();
  var q  = document.getElementById('quartos-i').value;
  var vg = document.getElementById('vagas-i').value;
  var pm = parseFloat(document.getElementById('preco-i').value)||Infinity;
  var fn = document.getElementById('fonte-i').value;
  var st = document.getElementById('status-i').value;
  var dp = parseInt(document.getElementById('datapub-i').value)||0;
  var hoje = new Date(); hoje.setHours(0,0,0,0);
  return IMOVEIS.filter(function(im){{
    var hay=[im.obs,im.bairro,im.corretor,im.grupo,im.tipo].join(' ').toLowerCase();
    if(b&&hay.indexOf(b)===-1) return false;
    if(q){{var n=parseInt(q);if(q==='4'){{if(!im.quartos||im.quartos<4)return false;}}else{{if(!im.quartos||im.quartos<n)return false;}}}}
    if(vg){{var n2=parseInt(vg);if(vg==='3'){{if(!im.vagas||im.vagas<3)return false;}}else{{if(!im.vagas||im.vagas<n2)return false;}}}}
    if(im.preco&&im.preco>pm) return false;
    if(fn&&im.fonte!==fn) return false;
    if(st&&im.status!==st) return false;
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

function aplicarI(){{
  var lista=ordenarI(filtrarI());
  ['quartos-i','vagas-i','preco-i','fonte-i','status-i','datapub-i'].forEach(selActive);
  var cp=lista.filter(function(i){{return i.preco;}});
  var med=cp.length?Math.round(cp.reduce(function(s,i){{return s+i.preco;}},0)/cp.length):0;
  var novos=lista.filter(function(i){{return i.status==='Novo';}}).length;
  document.getElementById('stats-i').innerHTML=
    '<div class="stat"><strong>'+lista.length+'</strong> imóveis</div>'+
    '<div class="stat"><strong>'+novos+'</strong> novos</div>'+
    (med?'<div class="stat"><strong>'+fmtP(med)+'</strong> preço médio</div>':'');
  document.getElementById('rtxt-i').textContent=lista.length+' de '+IMOVEIS.length;
  document.getElementById('grid-i').innerHTML=lista.length?lista.map(cardI).join(''):
    '<div class="empty"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg><p>Nenhum imóvel encontrado.</p></div>';
}}

function resetarI(){{
  document.getElementById('busca-i').value='';
  ['quartos-i','vagas-i','preco-i','fonte-i','status-i','datapub-i'].forEach(function(id){{document.getElementById(id).value='';}});
  aplicarI();
}}

['busca-i','quartos-i','vagas-i','preco-i','fonte-i','status-i','datapub-i'].forEach(function(id){{
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
    dm.vagas?(dm.vagas+(dm.vagas===1?' vaga':' vagas')):null
  ].filter(Boolean).map(function(c){{return typeof c==='string'&&c.indexOf('class="chip')===-1?'<span class="chip">'+c+'</span>':c;}}).join('');
  return '<div class="card card-dem">'+
    '<div class="card-header">'+
      '<div><div class="card-name">'+(dm.regiao||dm.corretor||'Demanda')+'</div><div class="card-loc">'+(dm.corretor||'—')+'</div></div>'+
      '<div style="text-align:right">'+
        (dm.orcamento?'<div class="card-price">'+fmtP(dm.orcamento)+'</div><div class="dem-orcamento-label">orçamento máx</div>':'<div class="card-price-na">Consultar</div>')+
      '</div>'+
    '</div>'+
    (chips?'<div class="chips">'+chips+'</div>':'')+
    (dm.obs?'<div class="card-desc">'+dm.obs+'</div>':'')+
    '<div class="card-foot">'+
      '<div class="card-who">'+(dm.grupo||'—')+(dm.data?' · '+dm.data:'')+' </div>'+
      '<div class="foot-right">'+btnWa(dm.contato)+'<span class="'+pillCls(dm.status||'Novo')+'">'+(dm.status||'Novo')+'</span></div>'+
    '</div>'+
  '</div>';
}}

function filtrarD(){{
  var b  = document.getElementById('busca-d').value.toLowerCase();
  var q  = document.getElementById('quartos-d').value;
  var vg = document.getElementById('vagas-d').value;
  var om = parseFloat(document.getElementById('orc-d').value)||Infinity;
  var st = document.getElementById('status-d').value;
  return DEMANDAS.filter(function(dm){{
    var hay=[dm.obs,dm.regiao,dm.corretor,dm.grupo,dm.tipo].join(' ').toLowerCase();
    if(b&&hay.indexOf(b)===-1) return false;
    if(q){{var n=parseInt(q);if(q==='4'){{if(!dm.quartos||dm.quartos<4)return false;}}else{{if(dm.quartos&&dm.quartos<n)return false;}}}}
    if(vg){{var n2=parseInt(vg);if(vg==='3'){{if(!dm.vagas||dm.vagas<3)return false;}}else{{if(dm.vagas&&dm.vagas<n2)return false;}}}}
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

function aplicarD(){{
  var lista=ordenarD(filtrarD());
  ['quartos-d','vagas-d','orc-d','status-d'].forEach(selActive);
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
  document.getElementById('grid-d').innerHTML=lista.length?lista.map(cardD).join(''):
    '<div class="empty"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg><p>Nenhuma demanda encontrada.</p></div>';
}}

function resetarD(){{
  document.getElementById('busca-d').value='';
  ['quartos-d','vagas-d','orc-d','status-d'].forEach(function(id){{document.getElementById(id).value='';}});
  aplicarD();
}}

['busca-d','quartos-d','vagas-d','orc-d','status-d'].forEach(function(id){{
  document.getElementById(id).addEventListener('input',aplicarD);
}});

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
  var demWords = demRegiao.toLowerCase().split(/\W+/).filter(function(w){{return w.length>3;}});
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

function matchImoveis(dm){{
  var excl=['Vendido','Cancelado','Descartado'];
  var demBairroCanon=dm.regiao?canonicBairro(dm.regiao):null;
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
    var tipoOk=true;
    // tipo
    if(dm.tipo){{
      total++;
      var dt=dm.tipo.toLowerCase(),it=(im.tipo||'').toLowerCase();
      if(it&&(it.indexOf(dt)!==-1||dt.indexOf(it)!==-1)){{score++;}}else{{tipoOk=false;}}
    }}
    // quartos
    if(dm.quartos){{total++;if(im.quartos&&im.quartos>=dm.quartos)score++;}}
    // suites
    if(dm.suites)    {{total++;if(im.suites&&im.suites>=dm.suites)score++;}}
    // banheiros
    if(dm.banheiros) {{total++;if(im.suites&&im.suites>=dm.banheiros)score++;}}
    // vagas
    if(dm.vagas)  {{total++;if(im.vagas&&im.vagas>=dm.vagas)score++;}}
    // area
    if(dm.area_min){{total++;if(im.area&&im.area>=dm.area_min)score++;}}
    // orcamento
    var precoOk=false,precoDentro20=false;
    if(dm.orcamento){{
      total++;
      precoOk=!!(im.preco&&im.preco<=dm.orcamento);
      precoDentro20=!!(im.preco&&im.preco<=dm.orcamento*1.2&&im.preco>=dm.orcamento*0.8);
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
    if(total>0) scored.push({{im:im,score:score,total:total,tipoOk:tipoOk,precoOk:precoOk,precoDentro20:precoDentro20,regiaoOk:regiaoOk,regiaoVizinha:regiaoVizinha}});
  }});
  scored.sort(function(a,b){{return(a.im.preco||9e9)-(b.im.preco||9e9);}});
  var exact=scored.filter(function(e){{return e.score===e.total;}});
  var exactSet={{}};exact.forEach(function(e){{exactSet[e.im.obs||e.im.id]=1;}});
  var near=scored.filter(function(e){{
    if(e.score!==e.total-1||e.total<=1) return false;
    if(exactSet[e.im.obs||e.im.id]) return false;
    // tipo deve sempre coincidir no "quase lá"
    if(dm.tipo&&!e.tipoOk) return false;
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
  if(dm.tipo){{var dt=dm.tipo.toLowerCase(),it=(im.tipo||'').toLowerCase();if(!(it&&(it.indexOf(dt)!==-1||dt.indexOf(it)!==-1)))missed.push('tipo');}}
  if(dm.quartos&&!(im.quartos&&im.quartos>=dm.quartos)) missed.push(dm.quartos+' quartos');
  if(dm.suites&&!(im.suites&&im.suites>=dm.suites))         missed.push(dm.suites+' suítes');
  if(dm.banheiros&&!(im.suites&&im.suites>=dm.banheiros)) missed.push(dm.banheiros+' banheiros');
  if(dm.vagas&&!(im.vagas&&im.vagas>=dm.vagas))           missed.push(dm.vagas+' vagas');
  if(dm.area_min&&!(im.area&&im.area>=dm.area_min))     missed.push('≥'+dm.area_min+' m²');
  if(dm.orcamento&&!(im.preco&&im.preco<=dm.orcamento)){{var pct=im.preco?Math.round((im.preco/dm.orcamento-1)*100):0;missed.push(pct>0?'+'+pct+'% do orçamento':'orçamento');}}
  if(dm.regiao){{var words=dm.regiao.toLowerCase().split(/\W+/).filter(function(w){{return w.length>3;}});var bl=(im.bairro||'').toLowerCase();if(!(words.length&&words.some(function(w){{return bl.indexOf(w)!==-1;}}))){{var viz=ehVizinho(dm.regiao,im.bairro||'');missed.push(viz?'bairro vizinho':'região');}}}}
  return missed;
}}

function cardMatchIm(entry, dm, isNear){{
  var im=entry.im,isJJ=im.fonte==='Junior Joda';
  var nome=cardNome(im);
  var chips=[fmtA(im.area),
    im.quartos?(im.quartos+(im.quartos===1?' qt':' qts')):null,
    im.suites?(im.suites+(im.suites===1?' suíte':' suítes')):null,
    im.vagas?(im.vagas+(im.vagas===1?' vaga':' vagas')):null
  ].filter(Boolean).map(function(c){{return'<span class="chip" style="font-size:11px;padding:3px 8px">'+c+'</span>';}}).join('');
  var linkBtn=im.link?'<a class="btn-link" href="'+im.link+'" target="_blank" style="font-size:11px;padding:4px 8px">Ver ↗</a>':'';
  var badge=isNear
    ? '<span class="match-score mscore-mid">Falta: '+missedCriteria(dm,im).join(', ')+'</span>'
    : '<span class="match-score mscore-high">✓ todos os critérios</span>';
  return '<div class="match-card'+(isJJ?' match-card-jj':'')+(isNear?' match-card-near':'')+'">'+
    '<div>'+
      '<div class="match-card-name">'+nome+'</div>'+
      (im.bairro?'<div class="match-card-loc">'+im.bairro+'</div>':'')+
    '</div>'+
    (im.preco?'<div class="match-card-price">'+fmtP(im.preco)+'</div>':'<div style="font-size:12px;color:#bbb">Consultar</div>')+
    (chips?'<div class="chips" style="gap:4px">'+chips+'</div>':'')+
    '<div style="display:flex;align-items:center;justify-content:space-between;margin-top:2px">'+
      badge+
      '<div style="display:flex;gap:4px">'+btnWa(im.contato)+linkBtn+'</div>'+
    '</div>'+
  '</div>';
}}

function renderMatch(){{
  var html='';
  var totalExact=0;
  DEMANDAS.forEach(function(dm){{
    var res=matchImoveis(dm);
    totalExact+=res.exact.length;
    var demTitle=(dm.regiao&&dm.tipo)?dm.tipo+' · '+dm.regiao:(dm.regiao||dm.tipo||dm.corretor||'Demanda');
    html+='<div class="match-block">'+
      '<div class="match-dem-header">'+
        '<div class="match-dem-info">'+
          '<div class="match-dem-title">'+demTitle+'</div>'+
          '<div class="match-dem-sub">'+
            (dm.corretor||'—')+
            (dm.orcamento?' · Orçamento: '+fmtP(dm.orcamento):'')+
            (dm.quartos?' · '+dm.quartos+' quartos':'')+
            (dm.suites?' · '+dm.suites+' suítes':'')+
            (dm.banheiros?' · '+dm.banheiros+' banheiros':'')+
            (dm.vagas?' · '+dm.vagas+' vagas':'')+
            (dm.area_min?' · Mín '+dm.area_min+' m²':'')+
            (dm.regiao?' · Região: '+dm.regiao:'')+
          '</div>'+
        '</div>'+
        '<div style="display:flex;gap:8px;align-items:center;flex-shrink:0">'+
          (dm.contato?btnWa(dm.contato):'')+
          '<span class="match-count-badge">'+res.exact.length+' exatos · '+res.near.length+' quase</span>'+
        '</div>'+
      '</div>'+
      // — Exatos
      (res.exact.length?
        '<div class="match-row">'+res.exact.map(function(e){{return cardMatchIm(e,dm,false);}}).join('')+'</div>':
        '<div class="match-none">Nenhum imóvel atende a todos os critérios.</div>')+
      // — Quase (falta 1 critério)
      (res.near.length?
        '<div class="match-near-label">Quase lá — falta apenas 1 critério</div>'+
        '<div class="match-row">'+res.near.map(function(e){{return cardMatchIm(e,dm,true);}}).join('')+'</div>':
        '')+
    '</div>';
  }});
  document.getElementById('badge-match').textContent=totalExact;
  document.getElementById('content-match').innerHTML=html||
    '<div class="empty"><p>Nenhuma demanda cadastrada.</p></div>';
}}


/* init */
aplicarI();
aplicarL();
aplicarD();
</script>
</body>
</html>"""
    return html


def main():
    if not PLANILHA.exists():
        print(f"Planilha não encontrada: {PLANILHA}"); return
    imoveis  = carregar_imoveis()
    jj       = carregar_juniorjoda()
    vr       = carregar_vivareal()
    imoveis  = imoveis + jj + vr
    demandas = carregar_demandas()
    html = gerar_html(imoveis, demandas)
    SITE.write_text(html, encoding="utf-8")
    print(f"✅ Site gerado: {SITE} ({len(imoveis)} imóveis [{len(jj)} JJ · {len(vr)} VR] · {len(demandas)} demandas)")


if __name__ == "__main__":
    main()
