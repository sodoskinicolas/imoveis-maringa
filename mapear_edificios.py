#!/usr/bin/env python3
"""
mapear_edificios.py — Índice de sinônimos edifício(anúncio) -> cadastro_es(vertical).

Casa imoveis.edificio com verticais_geo por:
  1) match EXATO do nome normalizado (>=4 chars)
  2) match FUZZY conservador (SequenceMatcher >= 0.92 + pelo menos 1 token >=4 em comum)

Grava a tabela auditável `edificio_alias(edificio_norm PK, cadastro_es, metodo, score)`
que analise_precos.py e gerar_historico_vertical.py consomem (com fallback pro match
exato inline se a tabela não existir).

Rodar:  python3 mapear_edificios.py
"""
import sqlite3, re, unicodedata, os
from difflib import SequenceMatcher

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imoveis.db")
# norm() IDÊNTICO ao de analise_precos/gerar_historico (mantém DO/DA/DE) p/ as chaves casarem
STOP = r'\b(ED|EDIF|EDIFICIO|RES|RESID|RESIDENCIAL|COND|CONDOMINIO|CONJ|CONJUNTO)\b'
# artigos só saem na tokenização (qualidade do fuzzy), não na chave
STOP_TOK = r'\b(ED|EDIF|EDIFICIO|RES|RESID|RESIDENCIAL|COND|CONDOMINIO|CONJ|CONJUNTO|DO|DA|DE|DOS|DAS)\b'

def norm(s):
    if not s: return ""
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().upper()
    s = re.sub(STOP, '', s)
    return re.sub(r'[^A-Z0-9]', '', s)

def toks(s):
    if not s: return set()
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().upper()
    s = re.sub(STOP_TOK, ' ', s)
    return {t for t in re.split(r'[^A-Z0-9]+', s) if len(t) >= 4}

def main():
    con = sqlite3.connect(DB); cur = con.cursor()
    vg = {}; vtok = {}
    for cad, nc, nw in cur.execute(
        "SELECT cadastro_es, nome_cadastral, nome_web FROM verticais_geo WHERE classe='vertical'"):
        for nm in (nc, nw):
            k = norm(nm)
            if len(k) >= 4 and k not in vg: vg[k] = cad
            if nm: vtok.setdefault(cad, set()).update(toks(nm))
    vkeys = list(vg.keys())

    eds = set()
    for (edi,) in cur.execute("SELECT DISTINCT edificio FROM imoveis WHERE edificio IS NOT NULL AND edificio!=''"):
        eds.add(edi)

    aliases = {}   # edificio_norm -> (cad, metodo, score)
    for edi in eds:
        k = norm(edi)
        if len(k) < 4: continue
        if k in vg:
            aliases[k] = (vg[k], 'exato', 1.0); continue
        et = toks(edi)
        best = None; bestr = 0.0
        for vk in vkeys:
            if abs(len(vk) - len(k)) > 4: continue
            r = SequenceMatcher(None, k, vk).ratio()
            if r > bestr: bestr = r; best = vk
        if best and bestr >= 0.92:
            cad = vg[best]
            if et & vtok.get(cad, set()):   # exige token forte em comum (anti-falso-positivo)
                aliases.setdefault(k, (cad, 'fuzzy', round(bestr, 3)))

    cur.execute("DROP TABLE IF EXISTS edificio_alias")
    cur.execute("""CREATE TABLE edificio_alias(
        edificio_norm TEXT PRIMARY KEY, cadastro_es INTEGER, metodo TEXT, score REAL)""")
    cur.executemany("INSERT INTO edificio_alias VALUES (?,?,?,?)",
                    [(k, c, m, s) for k, (c, m, s) in aliases.items()])
    con.commit()

    ex = cur.execute("SELECT COUNT(*) FROM edificio_alias WHERE metodo='exato'").fetchone()[0]
    fz = cur.execute("SELECT COUNT(*) FROM edificio_alias WHERE metodo='fuzzy'").fetchone()[0]
    print(f"OK: {ex} exatos + {fz} fuzzy = {ex+fz} nomes de edifício mapeados")
    con.close()

if __name__ == "__main__":
    main()
