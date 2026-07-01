#!/usr/bin/env python3
"""
sincronizar_vivareal_xlsx.py
Sincroniza o VivaReal_Imoveis.xlsx já existente em disco pro imoveis.db, via
upsert por ID VivaReal (fonte='VivaReal').

Uso previsto: rodar UMA VEZ depois da migração pra fonte/ref_externa (ver
db.py), preenchendo link/nome/data_publicacao de imóveis que já estavam no
banco mas foram inseridos antes dessas colunas existirem. Também serve como
sincronização manual sempre que só houver a planilha (sem precisar rodar o
scraper de novo).

Uso:
    python3 sincronizar_vivareal_xlsx.py
"""

import sys
from pathlib import Path
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    print("Erro: pandas não instalado. Execute: pip install pandas openpyxl")
    sys.exit(1)

import db
from gerar_site import normalizar_tipo

VIVAREAL = Path(__file__).parent / "VivaReal_Imoveis.xlsx"
FONTE    = "VivaReal"


def ler_planilha():
    if not VIVAREAL.exists():
        print(f"❌ Arquivo não encontrado: {VIVAREAL}")
        return []
    try:
        df = pd.read_excel(VIVAREAL, sheet_name="VivaReal Maringá", dtype=str)
    except Exception as e:
        print(f"❌ Erro lendo {VIVAREAL.name}: {e}")
        return []
    df = df.where(pd.notnull(df), None)

    itens = []
    for _, r in df.iterrows():
        id_ = r.get("ID VivaReal", "") or ""
        if not id_:
            continue

        def tof(x):
            try:
                return float(x.replace(",", ".")) if x and str(x).strip() not in ("", "None") else None
            except Exception:
                return None

        def toi(x):
            try:
                return int(float(x)) if x and str(x).strip() not in ("", "None", "0") else None
            except Exception:
                return None

        link   = r.get("Link", "") or ""
        bairro = r.get("Bairro", "") or ""
        rua    = r.get("Endereço", "") or ""

        itens.append({
            "ref_externa":     str(id_).strip(),
            "data_captura":    r.get("Data Captura", "") or datetime.now().strftime("%Y-%m-%d"),
            "grupo":           FONTE,
            "corretor":        r.get("Corretor", "") or "VivaReal",
            "contato":         "",
            "tipo":            normalizar_tipo(r.get("Tipo", "") or "", r.get("Observações", "") or ""),
            "bairro":          f"{bairro} · {rua}".strip(" ·") if rua else bairro,
            "area":            tof(r.get("Área (m²)")),
            "quartos":         toi(r.get("Quartos")),
            "suites":          toi(r.get("Suítes")),
            "banheiros":       toi(r.get("Banheiros")),
            "vagas":           toi(r.get("Vagas")),
            "preco":           toi(r.get("Preço (R$)")),
            "observacoes":     f"id:{id_}",
            "status":          "Venda",
            "data_publicacao": r.get("Data Publicação", "") or "",
            "link":            link,
        })
    return itens


def main():
    db.init_db()
    itens = ler_planilha()
    print(f"📂 {len(itens)} imóveis lidos de {VIVAREAL.name}")
    if not itens:
        return

    novos = atualizados = precos_mudaram = 0
    refs_vistas = []
    with db.db_conn() as conn:
        for item in itens:
            refs_vistas.append(item["ref_externa"])
            acao, _ = db.upsert_imovel_externo(conn, item, FONTE)
            if acao == "novo":
                novos += 1
            elif acao == "preco_mudou":
                precos_mudaram += 1
            elif acao == "atualizado":
                atualizados += 1
        removidos = db.marcar_ausentes(conn, FONTE, refs_vistas)

    print(f"✅ {novos} novos · {atualizados} atualizados · {precos_mudaram} com preço alterado · {removidos} marcados como Removido")
    print("\nPronto! Rode python3 gerar_site.py para atualizar o site.")


if __name__ == "__main__":
    main()
