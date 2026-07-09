#!/usr/bin/env python3
"""
analise_precos.py — Motor de análise de histórico de preços (projeto PW).

Lê imoveis + preco_historico + preco_historico_vertical + verticais_geo e calcula
métricas que respondem as 30 perguntas de corretores/imobiliárias sobre preço.

Gera (idempotente, reconstrói toda vez):
  metricas_precos_vertical  -> 1 linha por edifício vertical
  metricas_bairro           -> 1 linha por bairro
  RESUMO_precos.json        -> números de mercado (lazer x sem lazer, rankings, oportunidades)

Rodar:  python3 analise_precos.py
Depende de:  gerar_historico_vertical.py já ter rodado (tabela preco_historico_vertical).
"""
import sqlite3, re, unicodedata, statistics, json, os
from datetime import datetime, timedelta

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imoveis.db")
REMOVIDO = "Removido"

M2_MIN, M2_MAX = 800, 25000   # faixa sã de R$/m² (descarta outliers e terrenos mal rotulados)

def norm(s):
    if not s: return ""
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().upper()
    s = re.sub(r'\b(ED|EDIF|EDIFICIO|RES|RESID|RESIDENCIAL|COND|CONDOMINIO|CONJ|CONJUNTO)\b', '', s)
    return re.sub(r'[^A-Z0-9]', '', s)

def clean_bairro(b):
    """Remove sufixos poluídos do tipo 'Bairro · Rua X · Ed. Y'."""
    if not b: return None
    return b.split('·')[0].split(' - ')[0].strip() or None

def m2_ok(preco, area):
    if not (preco and area and area > 0): return None
    v = preco / area
    return v if M2_MIN <= v <= M2_MAX else None

def padrao_cadastro(txt):
    """Normaliza o texto de padrão do cadastro/condomínio para alto/medio/baixo."""
    if not txt: return None
    t = txt.lower()
    if 'luxo' in t or 'alto' in t: return 'alto'
    if 'medio' in t or 'médio' in t or 'normal' in t: return 'medio'
    if 'econ' in t or 'baixo' in t or 'popular' in t or 'simples' in t: return 'baixo'
    return None

def moda(xs):
    xs = [x for x in xs if x]
    if not xs: return None
    return statistics.mode(xs) if len(set(xs)) < len(xs) else xs[0]

def pct(new, old):
    if not old: return None
    return round(100 * (new - old) / old, 1)

def valor_em(serie, data_alvo, tol_dias=4, campo=2):
    """serie: lista de (data_str, preco_medio, preco_m2). Retorna valor no campo mais
    próximo de data_alvo dentro da tolerância."""
    best = None; bestdiff = None
    for row in serie:
        d = datetime.fromisoformat(row[0])
        diff = abs((d - data_alvo).days)
        if diff <= tol_dias and (bestdiff is None or diff < bestdiff):
            v = row[campo] if row[campo] else row[1]
            if v: best = v; bestdiff = diff
    return best

def main():
    con = sqlite3.connect(DB); cur = con.cursor()

    # padrão construtivo declarado (tabela condominios) -> por nome normalizado
    cond_padrao = {}
    for nome, padrao in cur.execute("SELECT nome, padrao FROM condominios WHERE padrao IS NOT NULL AND padrao!=''"):
        p = padrao_cadastro(padrao); k = norm(nome)
        if k and p and k not in cond_padrao: cond_padrao[k] = p

    # mapa nome-normalizado -> cadastro_es (verticais) e metadados do edifício
    vg = {}; meta = {}
    for cad, nc, nw, lazer, bairro in cur.execute(
        "SELECT cadastro_es, nome_cadastral, nome_web, lazer, bairro FROM verticais_geo WHERE classe='vertical'"):
        n_lazer = 0
        if lazer:
            try: n_lazer = len(json.loads(lazer))
            except Exception: pass
        padrao_cad = cond_padrao.get(norm(nc)) or cond_padrao.get(norm(nw))
        meta[cad] = {"bairro_cad": bairro, "n_lazer": n_lazer, "padrao_cad": padrao_cad}
        for nm in (nc, nw):
            k = norm(nm)
            if len(k) >= 4 and k not in vg: vg[k] = cad  # nomes <4 chars = matching frágil

    # incorpora o índice de sinônimos (mapear_edificios.py), incl. matches fuzzy
    try:
        for k, cad in cur.execute("SELECT edificio_norm, cadastro_es FROM edificio_alias"):
            vg.setdefault(k, cad)
    except sqlite3.OperationalError:
        pass  # tabela ainda não gerada -> segue só com match exato

    # anúncios por edifício (só ativos = status != Removido)
    ed = {}  # cad -> list de dicts
    for iid, edi, area, preco, quartos, tipo, bairro, status in cur.execute(
        "SELECT id, edificio, area, preco, quartos, tipo, bairro, status FROM imoveis"):
        cad = vg.get(norm(edi))
        if not cad: continue
        ed.setdefault(cad, []).append(dict(
            id=iid, area=area, preco=preco, quartos=quartos, tipo=tipo,
            bairro=clean_bairro(bairro), ativo=(status != REMOVIDO), removido=(status == REMOVIDO)))

    # histórico por anúncio (para % que baixaram) -> imovel_id -> [(data,preco)]
    hist = {}
    for iid, preco, data in cur.execute(
        "SELECT imovel_id, preco, data FROM preco_historico WHERE preco>0 ORDER BY data"):
        hist.setdefault(iid, []).append((data, preco))

    # série por edifício (preco_historico_vertical)
    serie = {}
    for cad, data, pm, pm2 in cur.execute(
        "SELECT cadastro_es, data, preco_medio, preco_m2_medio FROM preco_historico_vertical ORDER BY data"):
        serie.setdefault(cad, []).append((data, pm, pm2))

    hoje = datetime.now()

    # ---------- métricas por edifício ----------
    cur.execute("DROP TABLE IF EXISTS metricas_precos_vertical")
    cur.execute("""CREATE TABLE metricas_precos_vertical(
        cadastro_es INTEGER PRIMARY KEY, bairro TEXT, n_ativos INTEGER, n_removidos INTEGER,
        n_suspeitos_direitos INTEGER,
        preco_medio INTEGER, preco_mediano INTEGER, preco_min INTEGER, preco_max INTEGER,
        preco_m2_medio INTEGER, var_7d_pct REAL, var_30d_pct REAL, var_90d_pct REAL,
        tendencia TEXT, pct_baixaram REAL, n_lazer INTEGER, lazer_completo INTEGER,
        padrao TEXT, padrao_fonte TEXT,
        primeira_data TEXT, ultima_data TEXT, atualizado TEXT)""")

    linhas = []
    for cad, anuncios in ed.items():
        ativos = [a for a in anuncios if a['ativo']]

        # --- filtro de "direitos"/lançamento subprecificado ---
        # dentro do prédio, descarta anúncios com m² < 50% da mediana (cessão de direitos,
        # entrada de lançamento etc. não representam o valor real da unidade pronta).
        m2_prelim = [(a, v) for a in ativos if (v := m2_ok(a['preco'], a['area']))]
        n_susp = 0
        if len(m2_prelim) >= 3:
            med = statistics.median([v for _, v in m2_prelim])
            corte = 0.5 * med
            ids_susp = {id(a) for a, v in m2_prelim if v < corte}
            n_susp = len(ids_susp)
            ativos_val = [a for a in ativos if id(a) not in ids_susp]
        else:
            ativos_val = ativos

        precos = [a['preco'] for a in ativos_val if a['preco'] and a['preco'] > 0]
        m2 = [v for a in ativos_val if (v := m2_ok(a['preco'], a['area']))]
        n_rem = sum(1 for a in anuncios if a['removido'])
        bairro = moda([a['bairro'] for a in anuncios]) or meta.get(cad, {}).get('bairro_cad')

        s = serie.get(cad, [])
        v7 = v30 = v90 = None
        if s:
            atual = s[-1][2] or s[-1][1]
            if atual:
                v7  = pct(atual, valor_em(s, hoje - timedelta(days=7)))
                v30 = pct(atual, valor_em(s, hoje - timedelta(days=30), tol_dias=10))
                v90 = pct(atual, valor_em(s, hoje - timedelta(days=90), tol_dias=20))
        base = next((v for v in (v30, v7, v90) if v is not None), None)
        tend = None
        if base is not None:
            tend = 'subindo' if base > 1 else ('caindo' if base < -1 else 'estavel')

        # % de anúncios do edifício que baixaram de preço
        baix = tot2 = 0
        for a in anuncios:
            h = hist.get(a['id'])
            if h and len(h) >= 2:
                tot2 += 1
                if h[-1][1] < h[0][1]: baix += 1
        pct_baix = round(100*baix/tot2, 1) if tot2 else None

        nl = meta.get(cad, {}).get('n_lazer', 0)
        linhas.append(dict(
            cad=cad, bairro=bairro, n_ativos=len(ativos), n_rem=n_rem, n_susp=n_susp,
            preco_medio=int(round(statistics.mean(precos))) if precos else None,
            preco_mediano=int(round(statistics.median(precos))) if precos else None,
            preco_min=min(precos) if precos else None, preco_max=max(precos) if precos else None,
            preco_m2_medio=int(round(statistics.mean(m2))) if m2 else None,
            v7=v7, v30=v30, v90=v90, tend=tend, pct_baix=pct_baix, nl=nl,
            padrao_cad=meta.get(cad, {}).get('padrao_cad'),
            prim=(s[0][0] if s else None), ult=(s[-1][0] if s else None)))

    # --- classificação de padrão (2º passo): cadastro > tercis de R$/m² do mercado ---
    m2_vals = sorted(r['preco_m2_medio'] for r in linhas if r['preco_m2_medio'])
    if len(m2_vals) >= 3:
        t1 = m2_vals[len(m2_vals)//3]; t2 = m2_vals[2*len(m2_vals)//3]
    else:
        t1 = t2 = None
    def classifica(r):
        if r['padrao_cad']:
            return r['padrao_cad'], 'cadastro'
        v = r['preco_m2_medio']
        if v is None or t1 is None: return None, None
        return ('alto' if v >= t2 else 'baixo' if v < t1 else 'medio'), 'preco_m2'

    rows_ins = []
    for r in linhas:
        padrao, fonte = classifica(r)
        rows_ins.append((
            r['cad'], r['bairro'], r['n_ativos'], r['n_rem'], r['n_susp'],
            r['preco_medio'], r['preco_mediano'], r['preco_min'], r['preco_max'],
            r['preco_m2_medio'], r['v7'], r['v30'], r['v90'], r['tend'], r['pct_baix'],
            r['nl'], 1 if r['nl'] >= 4 else 0, padrao, fonte,
            r['prim'], r['ult'], hoje.isoformat()))
    cur.executemany("INSERT INTO metricas_precos_vertical VALUES (%s)" % ",".join("?"*22), rows_ins)

    # ---------- métricas por bairro ----------
    cur.execute("DROP TABLE IF EXISTS metricas_bairro")
    cur.execute("""CREATE TABLE metricas_bairro(
        bairro TEXT PRIMARY KEY, n_ativos INTEGER, preco_medio INTEGER, preco_mediano INTEGER,
        preco_m2_medio INTEGER, preco_m2_min INTEGER, preco_m2_max INTEGER, atualizado TEXT)""")
    bstats = {}
    for iid, area, preco, bairro, status in cur.execute(
        "SELECT id, area, preco, bairro, status FROM imoveis WHERE status!=? ", (REMOVIDO,)):
        bairro = clean_bairro(bairro)
        if not bairro: continue
        b = bstats.setdefault(bairro, {"p": [], "m2": []})
        if preco and preco > 0: b["p"].append(preco)
        v = m2_ok(preco, area)
        if v: b["m2"].append(v)
    brows = []
    for bairro, d in bstats.items():
        if not d["p"]: continue
        m2 = d["m2"]
        brows.append((bairro, len(d["p"]),
            int(round(statistics.mean(d["p"]))), int(round(statistics.median(d["p"]))),
            int(round(statistics.mean(m2))) if m2 else None,
            int(round(min(m2))) if m2 else None, int(round(max(m2))) if m2 else None,
            hoje.isoformat()))
    cur.executemany("INSERT INTO metricas_bairro VALUES (?,?,?,?,?,?,?,?)", brows)

    con.commit()

    # ---------- resumo de mercado (JSON) ----------
    def m2_medio_por(cond):
        vals = [r[0] for r in cur.execute(
            f"SELECT preco_m2_medio FROM metricas_precos_vertical WHERE preco_m2_medio IS NOT NULL AND {cond}")]
        return int(round(statistics.mean(vals))) if vals else None

    resumo = {
        "atualizado_em": hoje.isoformat(),
        "edificios_analisados": len(linhas),
        "bairros_analisados": len(brows),
        "m2_medio_com_lazer_completo": m2_medio_por("lazer_completo=1"),
        "m2_medio_sem_lazer": m2_medio_por("lazer_completo=0"),
        "por_padrao": {r[0] or "sem_classe": {"n": r[1], "m2_medio": r[2]} for r in cur.execute(
            "SELECT padrao, COUNT(*), CAST(AVG(preco_m2_medio) AS INT) FROM metricas_precos_vertical GROUP BY padrao")},
        "padrao_de_cadastro": cur.execute("SELECT COUNT(*) FROM metricas_precos_vertical WHERE padrao_fonte='cadastro'").fetchone()[0],
        "total_suspeitos_direitos": cur.execute("SELECT COALESCE(SUM(n_suspeitos_direitos),0) FROM metricas_precos_vertical").fetchone()[0],
        "top_bairros_m2": [dict(bairro=r[0], m2=r[1], n=r[2]) for r in cur.execute(
            "SELECT bairro, preco_m2_medio, n_ativos FROM metricas_bairro WHERE preco_m2_medio IS NOT NULL ORDER BY preco_m2_medio DESC LIMIT 10")],
        "edificios_maior_valorizacao_30d": [dict(cad=r[0], bairro=r[1], var30=r[2]) for r in cur.execute(
            "SELECT cadastro_es, bairro, var_30d_pct FROM metricas_precos_vertical WHERE var_30d_pct IS NOT NULL ORDER BY var_30d_pct DESC LIMIT 10")],
        "edificios_maior_queda_30d": [dict(cad=r[0], bairro=r[1], var30=r[2]) for r in cur.execute(
            "SELECT cadastro_es, bairro, var_30d_pct FROM metricas_precos_vertical WHERE var_30d_pct IS NOT NULL ORDER BY var_30d_pct ASC LIMIT 10")],
        "edificios_mais_baixaram": [dict(cad=r[0], bairro=r[1], pct=r[2], n_ativos=r[3]) for r in cur.execute(
            "SELECT cadastro_es, bairro, pct_baixaram, n_ativos FROM metricas_precos_vertical WHERE pct_baixaram IS NOT NULL AND pct_baixaram>0 ORDER BY pct_baixaram DESC LIMIT 10")],
    }
    with open(os.path.join(os.path.dirname(DB), "RESUMO_precos.json"), "w") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2)

    print(f"OK: {len(linhas)} edificios | {len(brows)} bairros")
    print(f"   m2 com lazer completo: {resumo['m2_medio_com_lazer_completo']} | sem lazer: {resumo['m2_medio_sem_lazer']}")
    con.close()

if __name__ == "__main__":
    main()
