#!/usr/bin/env python3
"""
arquivar_demanda.py
Arquiva ou restaura demandas de clientes compradores no imoveis.db.
Uma demanda arquivada some da aba "Demandas" do site e passa a aparecer
na aba "Arquivadas" — nada é apagado, o status anterior fica salvo pra
poder restaurar depois.

Uso:
  python3 arquivar_demanda.py --listar                # lista demandas ativas (com id)
  python3 arquivar_demanda.py --listar-arquivadas      # lista demandas já arquivadas
  python3 arquivar_demanda.py --arquivar 12            # arquiva a demanda id=12
  python3 arquivar_demanda.py --restaurar 12           # restaura a demanda id=12
"""

import argparse
import subprocess
import sys
from pathlib import Path

import db


def _orc(v):
    return f"R$ {v:,.0f}".replace(",", ".") if v else "—"


def listar(conn):
    rows = db.listar_demandas(conn)
    if not rows:
        print("Nenhuma demanda ativa.")
        return
    print(f"{'ID':<6}{'CORRETOR':<26}{'REGIÃO':<32}{'ORÇAMENTO':<15}STATUS")
    for r in rows:
        print(f"#{r['id']:<5}{(r.get('corretor') or '—')[:24]:<26}"
              f"{(r.get('bairro_regiao') or '—')[:30]:<32}{_orc(r.get('orcamento_max')):<15}"
              f"{r.get('status')}")


def listar_arquivadas(conn):
    rows = db.listar_demandas_arquivadas(conn)
    if not rows:
        print("Nenhuma demanda arquivada.")
        return
    print(f"{'ID':<6}{'CORRETOR':<26}{'REGIÃO':<32}{'ORÇAMENTO':<15}STATUS ANTERIOR")
    for r in rows:
        print(f"#{r['id']:<5}{(r.get('corretor') or '—')[:24]:<26}"
              f"{(r.get('bairro_regiao') or '—')[:30]:<32}{_orc(r.get('orcamento_max')):<15}"
              f"{r.get('status_anterior') or '—'}")


def _regenerar_site():
    s = Path(__file__).parent / "gerar_site.py"
    if s.exists():
        subprocess.run([sys.executable, str(s)], check=False)


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--listar", action="store_true",
                    help="lista demandas ativas com seus ids")
    g.add_argument("--listar-arquivadas", action="store_true",
                    help="lista demandas já arquivadas")
    g.add_argument("--arquivar", type=int, metavar="ID",
                    help="arquiva a demanda com esse id")
    g.add_argument("--restaurar", type=int, metavar="ID",
                    help="restaura (desarquiva) a demanda com esse id")
    args = p.parse_args()

    db.init_db()
    with db.db_conn() as conn:
        if args.listar:
            listar(conn)
        elif args.listar_arquivadas:
            listar_arquivadas(conn)
        elif args.arquivar is not None:
            if db.arquivar_demanda(conn, args.arquivar):
                print(f"✅ Demanda #{args.arquivar} arquivada.")
                _regenerar_site()
            else:
                print(f"⚠️  Demanda #{args.arquivar} não encontrada ou já estava arquivada.")
        elif args.restaurar is not None:
            if db.desarquivar_demanda(conn, args.restaurar):
                print(f"✅ Demanda #{args.restaurar} restaurada.")
                _regenerar_site()
            else:
                print(f"⚠️  Demanda #{args.restaurar} não encontrada ou não estava arquivada.")


if __name__ == "__main__":
    main()
