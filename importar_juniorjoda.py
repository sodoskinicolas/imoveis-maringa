#!/usr/bin/env python3
"""
importar_juniorjoda.py
Lê JuniorJoda_Imoveis.xlsx (abas "📋 Venda" e "🔑 Locação") e sincroniza os
imóveis pro imoveis.db, via upsert por Ref. (fonte='Junior Joda').

Não existe scraper da Junior Joda neste projeto — a planilha é mantida/
atualizada externamente. Este script trata ela como um snapshot de entrada:
toda vez que rodar, imóveis novos são inseridos, imóveis existentes têm seus
dados atualizados (e o preço antigo é preservado em preco_historico se
mudou), e imóveis que desapareceram da planilha (venderam ou saíram do
catálogo) são marcados status='Removido'.

Uso:
    python3 importar_juniorjoda.py
"""

import re
import sys
from pathlib import Path
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    print("Erro: pandas não instalado. Execute: pip install pandas openpyxl")
    sys.exit(1)

import db

JUNIORJODA = Path(__file__).parent / "JuniorJoda_Imoveis.xlsx"
WA_JJ      = "5544988132965"   # WhatsApp Junior Joda Soluções Imobiliárias
FONTE      = "Junior Joda"

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
    t = (tipo or "").strip()
    tl = t.lower()
    for palavras, valor in _TIPO_MAP:
        if any(p in tl for p in palavras):
            return valor
    if t in ("", "Imóvel") and obs:
        ol = obs.lower()
        for palavras, valor in _TIPO_MAP:
            if any(p in ol for p in palavras):
                return valor
    return t or "Imóvel"


def ler_planilha():
    """Lê as duas abas da planilha JJ e retorna lista de itens no formato de upsert_imovel_externo()."""
    if not JUNIORJODA.exists():
        print(f"❌ Arquivo não encontrado: {JUNIORJODA}")
        return []

    hoje = datetime.now().strftime("%Y-%m-%d")
    itens = []
    vistos_jj = set()  # deduplicação por tipo+bairro+preço+área dentro da própria planilha

    for sheet_name, modalidade in [("📋 Venda", "Venda"), ("🔑 Locação", "Locação")]:
        try:
            df = pd.read_excel(JUNIORJODA, sheet_name=sheet_name, dtype=str, header=1)
        except Exception as e:
            print(f"⚠ Não consegui ler aba '{sheet_name}': {e}")
            continue
        df = df.where(pd.notnull(df), None)

        for _, r in df.iterrows():
            ref = r.get("Ref.", "") or ""
            if not ref:
                continue

            def tof(x):
                try:
                    return float(x) if x and str(x).strip() not in ("", "None") else None
                except Exception:
                    return None

            def toi(x):
                try:
                    return int(float(x)) if x and str(x).strip() not in ("", "0", "None") else None
                except Exception:
                    return None

            preco_raw = r.get("Preço (R$)", "") or ""
            try:
                preco_num = (
                    int(float(preco_raw))
                    if preco_raw and str(preco_raw).strip() not in ("", "None", "Consulte")
                    else None
                )
            except Exception:
                preco_num = None

            nome   = str(r.get("Empreendimento", "") or "")
            tipo   = r.get("Tipo", "") or ""
            bairro = str(r.get("Bairro / Localização", "") or "")
            cidade = r.get("Cidade", "") or ""

            cidade_clean = re.sub(r'\s*[-–]\s*[A-Z]{2}$', '', cidade).strip()
            cidade_display = cidade_clean if cidade_clean.lower() not in ('maringá', 'maringa', '') else ''

            bairro_final = bairro
            if nome and bairro and bairro.lower() in nome.lower():
                bairro_final = cidade_display
            elif cidade_display:
                bairro_final = f"{bairro} · {cidade_display}".strip(" ·") if bairro else cidade_display

            area_priv = tof(r.get("Área Priv. (m²)"))
            area_tot  = tof(r.get("Área Total (m²)"))
            area = area_priv or area_tot

            label_mod = "Aluguel" if modalidade == "Locação" else "Venda"

            chave_jj = f"{tipo}|{bairro}|{preco_num}|{area}"
            if chave_jj in vistos_jj:
                continue
            vistos_jj.add(chave_jj)

            itens.append({
                "ref_externa":     str(ref).strip(),
                "data_captura":    hoje,
                "grupo":           FONTE,
                "corretor":        "Junior Joda Soluções Imobiliárias",
                "contato":         WA_JJ,
                "tipo":            normalizar_tipo(tipo, nome),
                "nome":            nome,
                "bairro":          bairro_final,
                "area":            area,
                "quartos":         toi(r.get("Quartos")),
                "suites":          toi(r.get("Suítes")),
                "vagas":           toi(r.get("Vagas")),
                "preco":           preco_num,
                "observacoes":     f"Ref. {ref}",
                "status":          label_mod,
                "link":            f"https://juniorjoda.com.br/imovel/{ref}/",
            })

    return itens


def main():
    db.init_db()
    itens = ler_planilha()
    print(f"📂 {len(itens)} imóveis lidos de {JUNIORJODA.name}")
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
