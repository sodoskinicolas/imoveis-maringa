#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera Lazer_Edificios.html — lista os edifícios verticais de Maringá com a
estrutura de lazer catalogada (coluna `lazer` de verticais_geo) e um filtro de
botões multi-seleção (piscina, academia, salão de festas, ...). A lógica do
filtro é E (AND): mostra só os edifícios que têm TODOS os itens marcados.
Roda sozinho a partir do imoveis.db; é chamado pela tarefa 'enriquecer-lazer-verticais'."""
import sqlite3, json, os, unicodedata
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(BASE, "imoveis.db")
OUT  = os.path.join(BASE, "Lazer_Edificios.html")


def _norm(s):
    s = (s or "").strip().lower()
    s = "".join(ch for ch in unicodedata.normalize("NFD", s)
                if unicodedata.category(ch) != "Mn")
    return s


def _endereco(r):
    tl = (r["tipo_logradouro"] or "").strip()
    lg = (r["logradouro"] or "").split(",")[0].strip()
    num = ""
    try:
        arr = json.loads(r["numeros"]) if r["numeros"] else []
        if arr:
            num = str(arr[0])
    except Exception:
        pass
    partes = " ".join(p for p in [tl, lg] if p)
    if num:
        partes += f", {num}"
    return partes.strip(", ").strip()


def coletar():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    total_vert = c.execute("SELECT COUNT(*) FROM verticais_geo WHERE classe='vertical'").fetchone()[0]
    rows = c.execute(
        "SELECT cadastro_es, nome_web, nome_cadastral, bairro, tipo_logradouro, "
        "logradouro, numeros, n_unidades, preco, lazer, lazer_confianca "
        "FROM verticais_geo "
        "WHERE classe='vertical' AND lazer IS NOT NULL AND lazer!='' AND lazer!='[]' "
        "ORDER BY n_unidades DESC"
    ).fetchall()
    edificios = []
    for r in rows:
        try:
            itens = [str(x).strip() for x in json.loads(r["lazer"]) if str(x).strip()]
        except Exception:
            itens = []
        if not itens:
            continue
        nome = (r["nome_web"] or r["nome_cadastral"] or "").strip()
        edificios.append({
            "id": r["cadastro_es"],
            "nome": nome.title() if nome.isupper() else nome,
            "bairro": (r["bairro"] or "").strip().title(),
            "endereco": _endereco(r),
            "unidades": r["n_unidades"] or 0,
            "preco": (r["preco"] or "").strip(),
            "conf": r["lazer_confianca"] or "",
            "lazer": sorted(set(itens), key=_norm),
        })
    conn.close()
    return edificios, total_vert


def render(edificios, total_vert):
    # universo de itens de lazer (para os botões), por frequência desc
    freq = {}
    for e in edificios:
        for it in e["lazer"]:
            freq[it] = freq.get(it, 0) + 1
    itens_ordenados = sorted(freq, key=lambda k: (-freq[k], _norm(k)))
    com = len(edificios)
    pct = round(100 * com / total_vert) if total_vert else 0
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    dados = json.dumps(edificios, ensure_ascii=False)
    chips = "".join(
        f'<button class="lchip" data-k="{_norm(it)}" onclick="toggle(this)">'
        f'{it} <span class="n">{freq[it]}</span></button>'
        for it in itens_ordenados
    )
    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Edifícios · Lazer — Maringá</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f7f7f5;color:#111}}
.wrap{{max-width:1100px;margin:0 auto;padding:24px 16px 60px}}
h1{{font-size:22px;font-weight:700}}
.sub{{color:#666;font-size:13px;margin-top:4px}}
.bar{{position:sticky;top:0;background:#f7f7f5;padding:14px 0 10px;z-index:5;border-bottom:1px solid #ececec;margin-top:14px}}
.searchrow{{display:flex;gap:8px;align-items:center;margin-bottom:10px}}
#q{{flex:1;padding:9px 12px;border:1px solid #ddd;border-radius:8px;font-size:14px}}
.chips{{display:flex;flex-wrap:wrap;gap:7px}}
.lchip{{cursor:pointer;border:1px solid #d9d9d4;background:#fff;border-radius:20px;
  padding:6px 12px;font-size:13px;color:#333;display:inline-flex;align-items:center;gap:6px;transition:.12s}}
.lchip:hover{{border-color:#b8b8b2}}
.lchip .n{{background:#eee;border-radius:10px;padding:0 6px;font-size:11px;color:#777}}
.lchip.on{{background:#111;color:#fff;border-color:#111}}
.lchip.on .n{{background:#444;color:#eee}}
.tools{{display:flex;gap:12px;align-items:center;margin-top:10px;font-size:13px;color:#555}}
.tools a{{color:#0a7;cursor:pointer;text-decoration:none}}
.mode{{display:inline-flex;gap:4px;align-items:center}}
.count{{font-weight:600;color:#111}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px;margin-top:16px}}
.card{{background:#fff;border:1px solid #eee;border-radius:12px;padding:16px;box-shadow:0 1px 2px rgba(0,0,0,.03)}}
.card h3{{font-size:16px;font-weight:700}}
.card .addr{{color:#666;font-size:13px;margin-top:2px}}
.meta{{display:flex;gap:10px;flex-wrap:wrap;font-size:12px;color:#888;margin:8px 0}}
.meta b{{color:#333}}
.itens{{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}}
.tag{{background:#f0f4f0;color:#256;border-radius:6px;padding:3px 8px;font-size:12px}}
.tag.hit{{background:#111;color:#fff}}
.empty{{text-align:center;color:#999;padding:60px 0}}
.badge{{font-size:10px;padding:1px 6px;border-radius:5px;background:#eee;color:#888;margin-left:6px}}
</style></head><body>
<div class="wrap">
  <h1>Edifícios de Maringá · Lazer</h1>
  <div class="sub">{com} de {total_vert} edifícios verticais com estrutura de lazer catalogada ({pct}%) · atualizado {agora}</div>
  <div class="bar">
    <div class="searchrow">
      <input id="q" placeholder="Buscar por nome, bairro ou endereço…" oninput="render()">
    </div>
    <div class="chips">{chips}</div>
    <div class="tools">
      <span class="mode">Modo:
        <a id="modebtn" onclick="toggleMode()">TEM TODOS os marcados</a></span>
      <a onclick="limpar()">limpar filtros</a>
      <span style="margin-left:auto">Mostrando <span class="count" id="cnt">0</span></span>
    </div>
  </div>
  <div class="grid" id="grid"></div>
</div>
<script>
var EDIF = {dados};
var sel = new Set();
var modeAll = true; // true = E (tem todos), false = OU (tem algum)

function toggle(btn){{
  var k = btn.getAttribute('data-k');
  if(sel.has(k)){{ sel.delete(k); btn.classList.remove('on'); }}
  else {{ sel.add(k); btn.classList.add('on'); }}
  render();
}}
function toggleMode(){{
  modeAll = !modeAll;
  document.getElementById('modebtn').textContent = modeAll ? 'TEM TODOS os marcados' : 'TEM QUALQUER um marcado';
  render();
}}
function limpar(){{
  sel.clear();
  document.querySelectorAll('.lchip.on').forEach(function(b){{b.classList.remove('on');}});
  document.getElementById('q').value='';
  render();
}}
function norm(s){{ return (s||'').toString().toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,''); }}

function render(){{
  var q = norm(document.getElementById('q').value);
  var grid = document.getElementById('grid');
  var out = EDIF.filter(function(e){{
    var keys = e.lazer.map(norm);
    var okSel;
    if(sel.size===0) okSel = true;
    else if(modeAll) okSel = Array.from(sel).every(function(k){{return keys.indexOf(k)!==-1;}});
    else okSel = Array.from(sel).some(function(k){{return keys.indexOf(k)!==-1;}});
    if(!okSel) return false;
    if(q){{
      var hay = norm(e.nome+' '+e.bairro+' '+e.endereco);
      if(hay.indexOf(q)===-1) return false;
    }}
    return true;
  }});
  document.getElementById('cnt').textContent = out.length;
  if(out.length===0){{ grid.innerHTML='<div class="empty">Nenhum edifício com essa combinação de lazer.</div>'; return; }}
  grid.innerHTML = out.map(function(e){{
    var tags = e.lazer.map(function(it){{
      var hit = sel.has(norm(it));
      return '<span class="tag'+(hit?' hit':'')+'">'+it+'</span>';
    }}).join('');
    var conf = e.conf ? '<span class="badge">'+e.conf+'</span>' : '';
    var preco = e.preco ? '<b>R$ '+Number(e.preco).toLocaleString('pt-BR')+'</b>' : '';
    return '<div class="card"><h3>'+(e.nome||'—')+conf+'</h3>'+
      '<div class="addr">'+e.endereco+(e.bairro?' · '+e.bairro:'')+'</div>'+
      '<div class="meta"><span>'+(e.unidades?('<b>'+e.unidades+'</b> unid.'):'')+'</span>'+
      (preco?'<span>'+preco+'</span>':'')+'</div>'+
      '<div class="itens">'+tags+'</div></div>';
  }}).join('');
}}
render();
</script>
</body></html>"""
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    return com, total_vert, pct


if __name__ == "__main__":
    edificios, total_vert = coletar()
    com, tot, pct = render(edificios, total_vert)
    print(f"✅ Lazer_Edificios.html gerado: {com}/{tot} edifícios com lazer ({pct}%)")
