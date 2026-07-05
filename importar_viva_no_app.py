#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Importa os 402 lotes do Vivá Home Resort (Loteamento Paysage Trebbiano, Marialva)
para o banco do app 'Cadastro Imobiliário Nativo' / 'Busca de Proprietário'.

Roda no Mac do Nicolas. Lê viva_para_app.csv (mesma pasta) e grava em:
  ~/Library/Application Support/CadastroImobiliarioNativo/cache.db  (tabela imovel)

É seguro rodar várias vezes (INSERT OR REPLACE por cadastro). Não apaga nada.
"""
import os, sqlite3, csv, json, datetime, sys

CACHE_VERSION = 3
CONDOMINIO = "Vivá Home Resort (Loteamento Paysage Trebbiano)"
BAIRRO = "Jardim Paraíso"
CIDADE = "Marialva/PR"

DB = os.path.expanduser("~/Library/Application Support/CadastroImobiliarioNativo/cache.db")
CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viva_para_app.csv")

def main():
    if not os.path.exists(DB):
        print("ERRO: não achei o banco do app em:\n ", DB)
        print("Abra o app 'Cadastro Imobiliário Nativo' uma vez e rode de novo.")
        sys.exit(1)
    if not os.path.exists(CSV):
        print("ERRO: não achei viva_para_app.csv na mesma pasta deste script.")
        sys.exit(1)

    con = sqlite3.connect(DB, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    # garante a tabela (mesmo schema do app)
    con.execute("""CREATE TABLE IF NOT EXISTS imovel(
        cadastro INTEGER PRIMARY KEY,
        nome TEXT, complemento TEXT, complemento_full TEXT, area TEXT,
        tipo TEXT, cpf_cnpj TEXT, endereco TEXT, bairro TEXT, condominio TEXT,
        dados_json TEXT, atualizado TEXT)""")

    agora = datetime.datetime.now().isoformat(timespec="seconds")
    n = 0
    with open(CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cad = int(row["cadastro"])
            nome = row["nome"].strip()
            end = row["endereco"].strip()
            venal = row.get("venal", "").strip()
            info = {
                "cadastro": cad, "nome": nome,
                "complemento": end, "complemento_full": end,
                "lote": "", "quadra": "",
                "area": "", "area_terreno": "",
                "tipo": "terreno", "cpf_cnpj": "",
                "endereco": end, "bairro": BAIRRO,
                "condominio": CONDOMINIO, "cidade": CIDADE,
                "valor_venal_territorial": venal,
                "fonte": "Elotech Marialva - Cadastro Imobiliário",
                "_v": CACHE_VERSION,
            }
            con.execute(
                "INSERT OR REPLACE INTO imovel(cadastro,nome,complemento,"
                "complemento_full,area,tipo,cpf_cnpj,endereco,bairro,condominio,"
                "dados_json,atualizado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (cad, nome, end, end, "", "terreno", "", end, BAIRRO, CONDOMINIO,
                 json.dumps(info, ensure_ascii=False), agora))
            n += 1
    con.commit()
    tot = con.execute("SELECT COUNT(*) FROM imovel WHERE condominio=?", (CONDOMINIO,)).fetchone()[0]
    con.close()
    print(f"OK! {n} lotes importados. No app o condomínio '{CONDOMINIO}' agora tem {tot} imóveis.")
    print("Abra o app, digite 'Vivá' e clique Buscar.")

if __name__ == "__main__":
    main()
