#!/usr/bin/env python3
"""
bot_grupos_wa.py
Recebe dados extraídos pelo bot WhatsApp (JSON) e insere no SQLite (imoveis.db)
sem duplicar registros.

Uso:
  python bot_grupos_wa.py --dados '{"grupo":"Maringá APTs","corretor":"João","contato":"554499...",
                                    "tipo":"Apartamento","bairro":"Zona 7","area":"80",
                                    "quartos":"3","suites":"1","vagas":"2","preco":"420000",
                                    "obs":"Sacada gourmet"}'

  python bot_grupos_wa.py --arquivo dados_capturados.json
"""

import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

import db

COL_ORDER = [
    "data_captura", "grupo", "corretor", "contato",
    "tipo", "bairro", "area", "quartos",
    "suites", "vagas", "preco", "obs", "status"
]


def normalizar(item: dict) -> dict:
    """Garante campos padrão e formata valores."""
    out = {k: None for k in COL_ORDER}
    out.update({
        "data_captura": datetime.now().strftime("%Y-%m-%d"),
        "status":       "Novo",
    })
    mapa = {
        "grupo":    ["grupo", "group", "nome_grupo"],
        "corretor": ["corretor", "broker", "nome"],
        "contato":  ["contato", "telefone", "phone", "whatsapp", "numero"],
        "tipo":     ["tipo", "type", "tipo_imovel"],
        "bairro":   ["bairro", "endereco", "address", "localizacao", "location"],
        "area":     ["area", "m2", "metragem", "tamanho"],
        "quartos":  ["quartos", "bedrooms", "dorms", "dormitorios"],
        "suites":   ["suites", "suite", "suítes"],
        "vagas":    ["vagas", "garagem", "garage"],
        "preco":    ["preco", "preco_venda", "valor", "price"],
        "obs":      ["obs", "observacoes", "observações", "descricao", "descricao_completa", "description"],
    }
    for campo, chaves in mapa.items():
        for chave in chaves:
            if chave in item and item[chave]:
                out[campo] = str(item[chave]).strip()
                break
    return out


def _to_num(v, cast=float):
    try:
        return cast(str(v).replace(".", "").replace(",", ".")) if v else None
    except:
        return None


def inserir(item: dict):
    db.init_db()
    item = normalizar(item)

    ok = db.inserir_imovel(db.get_conn(), {
        "data_captura":    item["data_captura"],
        "grupo":           item["grupo"],
        "corretor":        item["corretor"],
        "contato":         item["contato"],
        "tipo":            item["tipo"] or "Imóvel",
        "bairro":          item["bairro"],
        "area":            _to_num(item["area"], float),
        "quartos":         _to_num(item["quartos"], int),
        "suites":          _to_num(item["suites"], int),
        "banheiros":       None,
        "vagas":           _to_num(item["vagas"], int),
        "preco":           _to_num(item["preco"], int),
        "observacoes":     item["obs"],
        "status":          item["status"] or "Novo",
        "data_publicacao": item["data_captura"],
    })

    if ok:
        print(f"✅ Inserido: {item['corretor']} | {item['bairro']} | R$ {item['preco']}")
        _regenerar_site()
    else:
        print(f"⚠️  Duplicata ignorada: {item['corretor']} / {item['bairro']} / R${item['preco']}")


def processar_arquivo(path: str):
    with open(path, "r", encoding="utf-8") as f:
        dados = json.load(f)
    if isinstance(dados, list):
        for i in dados:
            inserir(i)
    else:
        inserir(dados)


def _regenerar_site():
    import subprocess
    site_script = Path(__file__).parent / "gerar_site.py"
    if site_script.exists():
        subprocess.run([sys.executable, str(site_script)], check=False)


def main():
    parser = argparse.ArgumentParser(description="Insere imóveis no SQLite a partir do bot WA")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dados",   help="JSON do imóvel como string")
    group.add_argument("--arquivo", help="Arquivo JSON com um ou vários imóveis")
    args = parser.parse_args()

    if args.dados:
        inserir(json.loads(args.dados))
    else:
        processar_arquivo(args.arquivo)


if __name__ == "__main__":
    main()
