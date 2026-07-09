#!/usr/bin/env python3
"""
Gera/atualiza a tabela preco_historico_vertical: histórico de preço POR EDIFÍCIO
vertical ao longo do tempo, agregando os anúncios individuais.

Fonte:
  preco_historico(imovel_id, preco, data)  -> série temporal por anúncio
  imoveis(id, edificio, area)              -> nome do edifício e m² do anúncio
  verticais_geo(cadastro_es, nome_*)       -> chave do edifício (por nome normalizado)

Saída (idempotente - reconstrói a tabela toda vez):
  preco_historico_vertical(
    cadastro_es, data, n_anuncios,
    preco_medio, preco_mediano, preco_min, preco_max, preco_m2_medio
  )
"""
import sqlite3, re, unicodedata, statistics, os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imoveis.db")

def norm(s):
    if not s:
        return ""
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = s.upper()
    s = re.sub(r'\b(ED|EDIF|EDIFICIO|RES|RESID|RESIDENCIAL|COND|CONDOMINIO|CONJ|CONJUNTO)\b', '', s)
    s = re.sub(r'[^A-Z0-9]', '', s)
    return s

def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    # 1) mapa nome-normalizado -> cadastro_es (só verticais)
    vg = {}
    for cad, nc, nw in cur.execute(
        "SELECT cadastro_es, nome_cadastral, nome_web FROM verticais_geo WHERE classe='vertical'"):
        for nm in (nc, nw):
            k = norm(nm)
            if len(k) >= 4 and k not in vg:  # nomes <4 chars = matching frágil
                vg[k] = cad

    # incorpora o índice de sinônimos (mapear_edificios.py), incl. matches fuzzy
    try:
        for k, cad in cur.execute("SELECT edificio_norm, cadastro_es FROM edificio_alias"):
            vg.setdefault(k, cad)
    except sqlite3.OperationalError:
        pass

    # 2) mapa imovel_id -> (cadastro_es, area) via nome do edifício
    im = {}
    for iid, edi, area in cur.execute("SELECT id, edificio, area FROM imoveis"):
        cad = vg.get(norm(edi))
        if cad:
            im[iid] = (cad, area if (area and area > 0) else None)

    # 3) agrega preco_historico por (cadastro_es, data)
    #    buckets[(cad,data)] = {'precos':[...], 'm2':[...]}
    buckets = {}
    for iid, preco, data in cur.execute(
        "SELECT imovel_id, preco, data FROM preco_historico WHERE preco IS NOT NULL AND preco>0"):
        info = im.get(iid)
        if not info:
            continue
        cad, area = info
        b = buckets.setdefault((cad, data), {'precos': [], 'm2': []})
        b['precos'].append(preco)
        if area:
            v = preco / area
            if 800 <= v <= 25000:   # descarta outliers / terrenos mal rotulados
                b['m2'].append(v)

    # 4) reconstrói a tabela
    cur.execute("DROP TABLE IF EXISTS preco_historico_vertical")
    cur.execute("""
        CREATE TABLE preco_historico_vertical (
            cadastro_es    INTEGER,
            data           TEXT,
            n_anuncios     INTEGER,
            preco_medio    INTEGER,
            preco_mediano  INTEGER,
            preco_min      INTEGER,
            preco_max      INTEGER,
            preco_m2_medio INTEGER,
            PRIMARY KEY (cadastro_es, data)
        )
    """)
    rows = []
    for (cad, data), b in buckets.items():
        p = b['precos']
        m2 = b['m2']
        rows.append((
            cad, data, len(p),
            int(round(statistics.mean(p))),
            int(round(statistics.median(p))),
            min(p), max(p),
            int(round(statistics.mean(m2))) if m2 else None,
        ))
    cur.executemany(
        "INSERT INTO preco_historico_vertical VALUES (?,?,?,?,?,?,?,?)", rows)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_phv_cad ON preco_historico_vertical(cadastro_es)")
    con.commit()

    # 5) resumo
    ne = cur.execute("SELECT COUNT(DISTINCT cadastro_es) FROM preco_historico_vertical").fetchone()[0]
    nd = cur.execute("SELECT COUNT(DISTINCT data) FROM preco_historico_vertical").fetchone()[0]
    nr = cur.execute("SELECT COUNT(*) FROM preco_historico_vertical").fetchone()[0]
    print(f"OK: {nr} linhas | {ne} edificios | {nd} datas distintas")
    con.close()

if __name__ == "__main__":
    main()
