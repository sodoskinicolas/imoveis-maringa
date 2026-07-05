# -*- coding: utf-8 -*-
"""
Bateria de testes do scraper do portal sub100.com.br (raspar_imoveis.py),
com fixtures construídos a partir de respostas REAIS da API beta-api
capturadas via Chrome em 2026-07-01. Roda numa cópia isolada (/tmp/tp).
"""
import sys, json, sqlite3, copy, os, shutil, tempfile
BASE = os.path.dirname(os.path.abspath(__file__))
TMP  = tempfile.mkdtemp(prefix="teste_portal_sub100_")
for f in os.listdir(BASE):
    if f.endswith(".py") or f.endswith(".json") or f == "imoveis.db":
        shutil.copy(os.path.join(BASE, f), TMP)
sys.path.insert(0, TMP)
os.chdir(TMP)

import raspar_imoveis as ri

FALHAS = []
TOTAL = [0]
def check(nome, cond, extra=""):
    TOTAL[0] += 1
    print(("  OK  " if cond else "  FALHOU ") + nome + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        FALHAS.append(nome)

# ── Fixtures com valores reais observados na API ─────────────────────────────
ITEM_APTO = {  # real: Torre de Miami, Bellakaza (anunciante trocado p/ não-raspado no teste de aproveitamento)
    "id": "b6b668b5-f545-44bd-9054-843c46dca753",
    "address": {"complete": "Rua Tietê, 584, 107 - Zona 07, Maringá - PR",
                "street": "Rua Tietê", "number": "584", "neighborhood": "Zona 07",
                "city": "Maringá", "uf": "PR", "complement": "107"},
    "suites": 1, "rooms": None, "dorms": 2, "bwc": 1, "parking_spaces": "1",
    "private_area": "48,00", "total_area": "0,00", "land_area": "0,00",
    "business_type": "Venda", "total": "185.000,00", "variation": 0,
    "reference": "64320000097", "internal_code": "110",
    "subtype_name": "Apartamento", "tags": [],
    "advertiser": {"id": "x", "name": "Casa Dom Imóveis", "creci": "J00001"},
    "condo": {"id": "y", "name": "Torre de Miami"},
    "latitude": "-23.4062498", "longitude": "-51.9428531",
}
ITEM_SALA = {  # real: Sala sem dorms/vagas, sem rua
    "id": "b40b867b-d905-4250-9f6c-f2b48758ad80",
    "address": {"complete": ",  - Zona 01 Centro, Maringá - PR", "street": None,
                "number": None, "neighborhood": "Zona 01 Centro", "city": "Maringá", "uf": "PR"},
    "suites": 0, "dorms": 0, "bwc": 0, "parking_spaces": "0",
    "private_area": "41,00", "total_area": "0,00", "land_area": "0,00",
    "total": "197.000,00", "reference": "98920000211",
    "subtype_name": "Sala", "tags": [],
    "advertiser": {"id": "x", "name": "GR21 Empreendimentos Imobiliários"},
    "condo": None,
}
ITEM_TERRENO = {  # real: só land_area
    "id": "39e1b124-bf63-433b-a874-1b8682573b41",
    "address": {"complete": ",  - Jardim Oriental, Maringá - PR", "street": None,
                "number": None, "neighborhood": "Jardim Oriental", "city": "Maringá", "uf": "PR"},
    "suites": 0, "dorms": 0, "bwc": 0, "parking_spaces": "0",
    "private_area": "0,00", "total_area": "400,00", "land_area": "400,00",
    "total": "260.000,00", "reference": "11120000333",
    "subtype_name": "Terrenos", "tags": [], "advertiser": {"name": "Prado Imóveis"}, "condo": None,
}
ITEM_JA_RASPADO = {  # anunciante que já raspamos direto → deve ser pulado
    "id": "1e194c58-7814-4d30-98c7-a66368afc5c8",
    "address": {"complete": "Rua Vereador Basílio Sautchuk, 901", "street": "Rua Vereador Basílio Sautchuk",
                "number": "901", "neighborhood": "Zona 01 Centro", "city": "Maringá", "uf": "PR"},
    "suites": 1, "dorms": 2, "bwc": 2, "parking_spaces": "1",
    "private_area": "77,00", "total_area": "97,00", "land_area": "0,00",
    "total": "680.000,00", "reference": "20200073780",
    "subtype_name": "Apartamento", "tags": [],
    "advertiser": {"name": "Lélo Imóveis"}, "condo": {"name": "Diamante de Gould"},
}
DESC_REAL = ("APARTAMENTO À VENDA NO EDIFÍCIO TORRE DE MIAMI - 2 DORMITÓRIOS, SACADA E VAGA "
             "DE GARAGEM - MARINGÁ/PR\n\nApartamento à venda no Edifício Torre de Miami, localizado "
             "na Rua Tietê, 584, ideal para quem busca praticidade, conforto e excelente custo-benefício "
             "em Maringá.\n\nO imóvel conta com 48,755m² de área privativa, com planta funcional e "
             "ambientes bem distribuídos.")

# ── 1. Helpers ────────────────────────────────────────────────────────────────
print("\n== helpers ==")
check("_num_br preço", ri._num_br("185.000,00") == 185000.0)
check("_num_br área", ri._num_br("48,00") == 48.0)
check("_num_br zero → None", ri._num_br("0,00") is None)
check("_num_br None → None", ri._num_br(None) is None)
check("_slug_url acentos", ri._slug_url("Jardim Aclimação") == "jardim-aclimacao")
check("_slug_url composto", ri._slug_url("Kitnet e Studio") == "kitnet-e-studio")
for nome, esperado in [("Lélo Imóveis", True), ("Imobiliária Silvio Iwata", True),
                       ("Junior Joda Soluções Imobiliárias", True),
                       ("Bellakaza Negócios Imobiliários", True),
                       ("Opção Imóveis", True), ("Casa Dom Imóveis", False),
                       ("Benites & Gonzaga Imóveis", False), ("GR21 Empreendimentos Imobiliários", False),
                       ("", False)]:
    check(f"anunciante '{nome}' → {'pula' if esperado else 'aproveita'}",
          ri._anunciante_ja_raspado(nome) == esperado)

# ── 2. Parser de item da API ──────────────────────────────────────────────────
print("\n== parse_portal_sub100_item ==")
it = ri.parse_portal_sub100_item(copy.deepcopy(ITEM_APTO))
check("ref", it["ref"] == "64320000097")
check("tipo Apartamento", it["tipo"] == "Apartamento")
check("bairro", it["bairro"] == "Zona 07")
check("endereço rua+nº", it["endereco"] == "Rua Tietê 584")
check("edifício do condo", it["edificio"] == "Torre de Miami")
check("corretor = anunciante", it["corretor"] == "Casa Dom Imóveis")
check("área privativa", it["area"] == 48.0)
# Na API do portal, dorms EXCLUI suítes (verificado em 23 anúncios reais em
# 2026-07-02): total de quartos = dorms + suites. Este fixture: dorms=2 + suites=1 = 3.
check("quartos = dorms + suites", it["quartos"] == 3, str(it["quartos"]))
check("suítes (API dá direto!)", it["suites"] == 1)
check("banheiros", it["banheiros"] == 1)
check("vagas", it["vagas"] == 1)
check("preço int", it["preco"] == 185000)
check("link formato portal", it["link"] ==
      "https://sub100.com.br/imoveis/64320000097/venda/apartamento-em-maringa-pr/zona-07", it["link"])

it2 = ri.parse_portal_sub100_item(copy.deepcopy(ITEM_SALA))
check("sala: tipo", it2["tipo"] == "Sala Comercial")
check("sala: quartos 0 → None", it2["quartos"] is None)
check("sala: vagas 0 → None", it2["vagas"] is None)
check("sala: sem edifício", it2["edificio"] == "")
check("sala: sem rua → endereco vazio", it2["endereco"] == "")

it3 = ri.parse_portal_sub100_item(copy.deepcopy(ITEM_TERRENO))
check("terreno: tipo", it3["tipo"] == "Terreno")
check("terreno: área = total/land", it3["area"] == 400.0)

check("sem reference → None", ri.parse_portal_sub100_item({"address": {}}) is None)

# Casos reais de dorms/suites investigados no portal em 2026-07-02 (descrição
# do anúncio vs campos da API) — a regra quartos = dorms + suites deve bater
# com o texto de cada anúncio:
_CASOS_QUARTOS = [
    # (ref real,       dorms, suites, total no texto do anúncio)
    ("2020005967",     1,     2,      3),   # "três quartos, sendo duas suítes"
    ("21220000377",    1,     2,      3),   # "3 quartos ... 02 suítes + 01 quarto"
    ("2020006245",     0,     2,      2),   # "dois dormitórios, ambos suítes"
    ("55020000119",    0,     1,      1),   # "1 dormitório, sendo 1 suíte"
    ("21220000412",    1,     1,      2),   # "2 Dormitórios (1 Suíte, 1 Quarto)"
    ("420002040",      2,     1,      3),   # "3 Quartos sendo uma suíte"
    ("64320000097",    2,     0,      2),   # Torre de Miami: "2 dormitórios", sem suíte
]
for ref, d, s, esperado in _CASOS_QUARTOS:
    caso = dict(ITEM_SALA, reference=ref, dorms=d, suites=s, subtype_name="Apartamento")
    r = ri.parse_portal_sub100_item(caso)
    check(f"quartos real {ref}: {d}+{s} → {esperado}", r["quartos"] == esperado, str(r["quartos"]))
    ok_suites = (r["suites"] or 0) <= (r["quartos"] or 0)
    check(f"  suítes ≤ quartos ({ref})", ok_suites)

# ── 2b. Semântica quartos/suítes das OUTRAS fontes (auditoria 2026-07-02) ────
print("\n== quartos/suítes: tenants Sub100, Lélo, Patrimônio ==")

# Tenant Sub100 — markup real capturado do card da Haraki (ref 14420001641,
# ficha diz "Dormitórios 1 suíte + 2 quartos" = 3 no total):
CARD_TENANT_SQ = ('<a href="/imovel/14420001641/venda/casa-em-maringa/zona-05">'
    '<div class="row d-flex flex-nowrap align-items-center mt-4 mb-2 pt-2 me-3 fs-7">'
    '<div class="col-auto d-flex justify-content-between align-items-center gap-2">'
    '<span class="iconColor icon-dormitorios fs-4"></span> <span>1 + 2</span> </div>'
    '<div class="col-auto"><span class="iconColor icon-banheiros fs-4"></span> <span>3</span></div>'
    '<div class="col-auto"><span class="iconColor icon-garagem fs-4"></span> <span>2</span></div>'
    '<div class="col-auto"><span class="iconColor icon-area_total fs-4"></span> '
    '<span translate="no">205,21 m²</span></div></div> R$ 979.000,00')
t = ri.parse_sub100_block(CARD_TENANT_SQ, "harakiimoveis.com.br")
check("tenant '1 + 2' → quartos 3", t["quartos"] == 3, str(t["quartos"]))
check("tenant '1 + 2' → suites 1", t["suites"] == 1, str(t["suites"]))
check("tenant ícone banheiros → 3", t["banheiros"] == 3, str(t["banheiros"]))
check("tenant ícone garagem → vagas 2", t["vagas"] == 2, str(t["vagas"]))

# número único = só quartos comuns, sem suíte (Haraki ref 14420001806: card "3",
# ficha "3 quartos"):
CARD_TENANT_SIMPLES = CARD_TENANT_SQ.replace("1 + 2", "3").replace("14420001641", "14420001806")
t2 = ri.parse_sub100_block(CARD_TENANT_SIMPLES, "harakiimoveis.com.br")
check("tenant '3' → quartos 3, sem suíte", t2["quartos"] == 3 and t2["suites"] is None,
      f"q={t2['quartos']} s={t2['suites']}")

# texto "1 suíte + 2 quartos" (título/meta) como fallback sem o markup de ícone:
CARD_TENANT_TEXTO = ('<a href="/imovel/43820000173/venda/casa-em-maringa/lot-madrid">x</a> '
    'Casa à venda com 1 suíte + 2 quartos em Loteamento Madrid R$ 330.000,00')
t3 = ri.parse_sub100_block(CARD_TENANT_TEXTO, "juniorjoda.com.br")
check("tenant texto '1 suíte + 2 quartos' → 3/1", t3["quartos"] == 3 and t3["suites"] == 1,
      f"q={t3['quartos']} s={t3['suites']}")

# regressão: card antigo sem suíte nenhuma continua igual
t4 = ri.parse_sub100_block('<a href="/imovel/8020000829/venda/sobrado-em-maringa/jardim-everest">x</a> '
                           'R$ 500.000,00 3 quartos 120 m² 2 banheiros', "harakiimoveis.com.br")
check("tenant regressão '3 quartos' texto", t4["quartos"] == 3 and t4["suites"] is None)

# Patrimônio (Kurole) — ADITIVO: card real "3 Dormitórios"+"1 Suíte" = título
# "1 Suíte + 3 Quartos" (Residencial Granada, 2026-07-02):
CARD_KUROLE = ('<div class="imo-dad-compl"><div class="dorm-ico" title="3 Dormitórios">'
    '<span></span><span>3</span><div>Dorm.</div></div>'
    '<div class="suites-ico" title="1 Suíte"><span></span><span>1</span><div>Suite</div></div>'
    '<div class="banh-ico" title="3 Banheiros"><span></span><span>3</span><div>Banho</div></div>'
    '<div class="gar-ico" title="4 Garagens"><span></span><span>4</span><div>Garagens</div></div></div>'
    ' 250,00 m² R$ 890.000,00 V')
p = ri.parse_patrimonio_card(CARD_KUROLE, "https://www.patrimonioimoveisprontos.com.br/comprar/x/782")
check("kurole 3 Dorm + 1 Suíte → quartos 4", p["quartos"] == 4, str(p["quartos"]))
check("kurole suites 1", p["suites"] == 1, str(p["suites"]))
p2 = ri.parse_patrimonio_card(CARD_KUROLE.replace('title="3 Dormitórios"', 'title="x"')
                              .replace('<span>3</span><div>Dorm.</div>', ''),
                              "https://www.patrimonioimoveisprontos.com.br/comprar/x/783")
check("kurole só '1 Suíte' → quartos 1", p2["quartos"] == 1, str(p2["quartos"]))

# Lélo — SUBSET: "3 Dormitórios (1 Suíte)" = 3 total (comportamento mantido);
# caso só-suítes "3 Suítes" → quartos herda 3 (antes ficava None):
if hasattr(ri, 'parse_lelo_card') or True:
    fn = getattr(ri, 'parse_lelo_card', None) or getattr(ri, '_parse_lelo_card', None)
    if fn:
        l1 = fn('Apartamento 3 Dormitórios (1 Suíte) 2 vagas R$ 500.000',
                'https://www.leloimoveis.com.br/imovel/apartamento-3-quartos-zona-08-maringa/79900/1')
        check("lélo subset 3 Dorm (1 Suíte) → 3/1", l1["quartos"] == 3 and l1["suites"] == 1,
              f"q={l1['quartos']} s={l1['suites']}")
        l2 = fn('Apartamento 3 Suítes 2 vagas R$ 1.500.000',
                'https://www.leloimoveis.com.br/imovel/apartamento-3-quartos-zona-08-maringa/79900/2')
        check("lélo só-suítes '3 Suítes' → quartos 3", l2["quartos"] == 3, str(l2["quartos"]))
    else:
        print("  (parse da Lélo não exposto como função — pulado)")

# ── 3. scrape_portal_sub100 com API mockada (2 páginas reais de estrutura) ───
print("\n== scrape_portal_sub100 (rede mockada) ==")
PAG1 = {"meta": {"current_page": 1, "last_page": 2, "per_page": 20, "total": 4},
        "data": [ITEM_APTO, ITEM_JA_RASPADO]}
PAG2 = {"meta": {"current_page": 2, "last_page": 2, "per_page": 20, "total": 4},
        "data": [ITEM_SALA, ITEM_TERRENO]}
DETALHES = {ITEM_APTO["id"]: {"data": {**ITEM_APTO, "description": DESC_REAL}},
            ITEM_SALA["id"]: {"data": {**ITEM_SALA, "description": ""}},
            ITEM_TERRENO["id"]: {"data": {**ITEM_TERRENO, "description": "Ótimo terreno de esquina, 400m², "
                                          "pronto para construir.\nDocumentação em dia."}}}
chamadas = {"paginas": 0, "detalhes": 0}

def fake_get_json(url, params=None, retries=3):
    if params and "page" in params:
        chamadas["paginas"] += 1
        return PAG1 if params["page"] == 1 else (PAG2 if params["page"] == 2 else {"data": []})
    chamadas["detalhes"] += 1
    uid = url.rsplit("/", 1)[-1]
    return DETALHES.get(uid)

ri._get_json_portal = fake_get_json
ri.time.sleep = lambda s: None  # sem esperas no teste

items = ri.scrape_portal_sub100()
check("2 páginas percorridas", chamadas["paginas"] == 2, str(chamadas))
check("3 aproveitados (Lélo pulado)", len(items) == 3, str(len(items)))
check("Lélo não está no resultado", all(i["corretor"] != "Lélo Imóveis" for i in items))
check("3 detalhes buscados (todos sem desc no banco)", chamadas["detalhes"] == 3, str(chamadas))
apto = next(i for i in items if i["ref"] == "64320000097")
check("descrição completa no obs", apto["obs"] == DESC_REAL)
check("id_api removido do item final", "id_api" not in apto)
sala = next(i for i in items if i["ref"] == "98920000211")
check("desc vazia → fallback resumo", "Sala Comercial" in sala["obs"] and "GR21" in sala["obs"], sala["obs"])

# ── 4. Sincronização com banco (cópia real) ───────────────────────────────────
print("\n== atualizar_db na cópia do banco ==")
# não pesquisar condomínio na web durante teste
ri.pesquisar_condominio = lambda *a, **k: None
ri.atualizar_aba_condominios = lambda *a, **k: None

# em produção _raspar_uma_fonte seta o grupo; reproduzir aqui
def com_grupo(lst):
    lst = copy.deepcopy(lst)
    for i in lst:
        i["grupo"] = "sub100.com.br"
    return lst

ri.atualizar_db(com_grupo(items), dry_run=False)
con = sqlite3.connect(os.path.join(TMP, "imoveis.db")); con.row_factory = sqlite3.Row
rows = {r["ref_externa"]: r for r in con.execute(
    "SELECT * FROM imoveis WHERE fonte='sub100.com.br'")}
check("3 inseridos com fonte sub100.com.br", len(rows) == 3, str(len(rows)))
r = rows.get("64320000097")
check("corretor gravado", r and r["corretor"] == "Casa Dom Imóveis")
check("suítes gravadas", r and r["suites"] == 1)
check("preço gravado", r and r["preco"] == 185000)
check("descrição completa gravada", r and r["observacoes"] == DESC_REAL)
check("edifício no bairro_end", r and "Torre de Miami" in r["bairro"], r["bairro"] if r else "")
check("status Novo", r and r["status"] == "Novo")
ph = con.execute("SELECT COUNT(*) c FROM preco_historico ph JOIN imoveis i ON i.id=ph.imovel_id "
                 "WHERE i.fonte='sub100.com.br'").fetchone()["c"]
check("preco_historico criado", ph == 3, str(ph))

# ── 5. Segunda rodada: descrição preservada, preço mudou, imóvel sumiu ───────
print("\n== segunda rodada (incremental) ==")
chamadas["detalhes"] = 0
PAG1["data"] = [dict(ITEM_APTO, total="192.000,00")]   # preço subiu; terreno e sala sumiram
PAG1["meta"]["last_page"] = 1
items2 = ri.scrape_portal_sub100()
check("detalhe NÃO rebuscado (desc já no banco)", chamadas["detalhes"] == 0, str(chamadas))
apto2 = items2[0]
check("descrição reusada do banco", apto2["obs"] == DESC_REAL)
ri.atualizar_db(com_grupo(items2), dry_run=False)
con2 = sqlite3.connect(os.path.join(TMP, "imoveis.db")); con2.row_factory = sqlite3.Row
r2 = con2.execute("SELECT * FROM imoveis WHERE fonte='sub100.com.br' AND ref_externa='64320000097'").fetchone()
check("preço atualizado", r2["preco"] == 192000, str(r2["preco"]))
check("descrição continua completa após update", r2["observacoes"] == DESC_REAL)
ph2 = con2.execute("SELECT COUNT(*) c FROM preco_historico ph JOIN imoveis i ON i.id=ph.imovel_id "
                   "WHERE i.ref_externa='64320000097' AND i.fonte='sub100.com.br'").fetchone()["c"]
check("histórico de preço tem 2 entradas", ph2 == 2, str(ph2))
rem = con2.execute("SELECT COUNT(*) c FROM imoveis WHERE fonte='sub100.com.br' AND status='Removido'").fetchone()["c"]
check("sala+terreno marcados Removido", rem == 2, str(rem))

# ── 5b. Slug único: 2 imóveis do mesmo bairro (link termina igual) ───────────
print("\n== slug único (colisão que derrubou a rodada de 2026-07-03) ==")
import db as _db
try:
    with _db.db_conn() as c3:
        for _ref in ("77720000001", "77720000002"):
            _db.upsert_imovel_externo(c3, {
                "ref_externa": _ref, "data_captura": "2026-07-03",
                "grupo": "sub100.com.br", "tipo": "Apartamento",
                "bairro": "Zona 07", "preco": 500000,
                "link": f"https://sub100.com.br/imoveis/{_ref}/venda/apartamento-em-maringa-pr/zona-07",
            }, "sub100.com.br")
        n_slug = c3.execute("SELECT COUNT(*) FROM imoveis WHERE ref_externa IN "
                            "('77720000001','77720000002')").fetchone()[0]
    check("2 imóveis com link terminando igual → 2 inseridos (sem IntegrityError)",
          n_slug == 2, str(n_slug))
except Exception as e:
    check("slug único sem IntegrityError", False, str(e)[:80])

# ── 6. Regressão: fontes existentes intactas ─────────────────────────────────
print("\n== regressão fontes existentes ==")
antes = dict(con2.execute("SELECT fonte, COUNT(*) FROM imoveis WHERE fonte IS NOT NULL "
                          "AND fonte != 'sub100.com.br' GROUP BY fonte").fetchall())
orig = sqlite3.connect(os.path.join(BASE, "imoveis.db"))
orig_counts = dict(orig.execute("SELECT fonte, COUNT(*) FROM imoveis WHERE fonte IS NOT NULL "
                                "GROUP BY fonte").fetchall())
check("nenhuma linha de outras fontes alterada em contagem",
      all(antes.get(f) == c for f, c in orig_counts.items() if f != "sub100.com.br"), str(antes))
check("SUB100_SITES intacto (5 sites)", len([s for s in ri.SUB100_SITES if "domain" in s]) >= 5)
check("OUTRAS_FONTES tem o portal", any(f["grupo"] == "sub100.com.br" for f in ri.OUTRAS_FONTES))
check("parse_sub100_block (tenant) segue funcionando",
      ri.parse_sub100_block('<a href="/imovel/8020000829/venda/sobrado-em-maringa/jardim-everest">x</a> '
                            'R$ 500.000,00 3 quartos 120 m²', "harakiimoveis.com.br")["tipo"] == "Sobrado")

print("\n" + ("TODOS OS %d TESTES PASSARAM" % TOTAL[0] if not FALHAS else "FALHARAM: " + ", ".join(FALHAS)))
sys.exit(1 if FALHAS else 0)
