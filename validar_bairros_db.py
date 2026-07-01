#!/usr/bin/env python3
"""
validar_bairros_db.py
Percorre todos os registros de imóveis e demandas no SQLite e valida/corrige
o campo bairro contra a lista oficial de Maringá (bairros_maringa.json).

Uso:
    python3 validar_bairros_db.py           # corrige no banco
    python3 validar_bairros_db.py --dry-run # só mostra, não salva
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from processar_mensagens import validar_bairro, _carregar_bairros_oficiais
import db

DRY_RUN = "--dry-run" in sys.argv

def validar_tabela(conn, tabela, col_bairro="bairro", col_edificio="edificio"):
    cur = conn.cursor()

    # Verificar se coluna edificio existe
    cols = [row[1] for row in cur.execute(f"PRAGMA table_info({tabela})").fetchall()]
    tem_edificio = col_edificio in cols

    if tem_edificio:
        rows = cur.execute(f"SELECT id, {col_bairro}, {col_edificio} FROM {tabela}").fetchall()
    else:
        rows = cur.execute(f"SELECT id, {col_bairro} FROM {tabela}").fetchall()

    corrigidos = 0
    sem_bairro_resolvido = 0

    for row in rows:
        rid = row[0]
        bairro_atual = (row[1] or '').strip()
        edificio = ((row[2] or '') if tem_edificio else '').strip() if tem_edificio else ''

        # Pular registros onde bairro já está vazio e não há edifício — nada a fazer
        if not bairro_atual and not edificio:
            continue

        bairro_novo = validar_bairro(
            bairro_atual,
            texto_completo='',   # não temos o texto original aqui
            edificio=edificio
        )

        if not bairro_novo and bairro_atual:
            sem_bairro_resolvido += 1
            continue

        if bairro_novo != bairro_atual:
            print(f"  [{tabela}] id={rid}  '{bairro_atual}' → '{bairro_novo}'"
                  + (f"  (edif: {edificio})" if edificio else ""))
            if not DRY_RUN:
                cur.execute(
                    f"UPDATE {tabela} SET {col_bairro}=? WHERE id=?",
                    (bairro_novo, rid)
                )
            corrigidos += 1

    if not DRY_RUN:
        conn.commit()

    print(f"\n  ✅ {tabela}: {corrigidos} bairros corrigidos"
          + (f", {sem_bairro_resolvido} sem resolução" if sem_bairro_resolvido else ""))
    return corrigidos

def main():
    print("🗺️  Validando bairros no banco de dados...")
    _carregar_bairros_oficiais()

    if DRY_RUN:
        print("  (modo dry-run — nenhuma alteração será salva)\n")

    with db.db_conn() as conn:
        # Tabela imoveis
        print("\n── Imóveis ──────────────────────────────────────────────────────")
        validar_tabela(conn, "imoveis", col_bairro="bairro", col_edificio="edificio")

        # Tabela demandas (bairro pode ter múltiplos separados por ' · ')
        print("\n── Demandas ─────────────────────────────────────────────────────")
        cur = conn.cursor()
        rows = cur.execute("SELECT id, bairro_regiao FROM demandas").fetchall()
        corrigidos = 0
        for rid, bairro_atual in rows:
            bairro_atual = (bairro_atual or '').strip()
            if not bairro_atual:
                continue
            # Demandas podem ter múltiplos bairros separados por ' · '
            if ' · ' in bairro_atual:
                partes = [p.strip() for p in bairro_atual.split(' · ') if p.strip()]
                validados = []
                for p in partes:
                    v = validar_bairro(p, texto_completo='', edificio='')
                    validados.append(v)
                bairro_novo = ' · '.join(dict.fromkeys(validados))
            else:
                bairro_novo = validar_bairro(bairro_atual, texto_completo='', edificio='')

            if bairro_novo != bairro_atual:
                print(f"  [demandas] id={rid}  '{bairro_atual}' → '{bairro_novo}'")
                if not DRY_RUN:
                    cur.execute("UPDATE demandas SET bairro_regiao=? WHERE id=?", (bairro_novo, rid))
                corrigidos += 1

        if not DRY_RUN:
            conn.commit()
        print(f"\n  ✅ demandas: {corrigidos} bairros corrigidos")

    print("\n✅ Validação concluída!\n")

if __name__ == "__main__":
    main()
