#!/usr/bin/env python3
"""
verificador_erros.py
Detecta erros em imóveis e demandas: sem contato, duplicatas, specs faltando.
Roda a cada 1h via LaunchAgent. Salva relatório em verificador_erros_log.txt.
"""

import sys
import json
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import db

LOG_FILE = Path(__file__).parent / "verificador_erros_log.txt"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def verificar():
    erros = []
    avisos = []

    with db.db_conn() as conn:
        # ── 1. IMÓVEIS sem contato (ativo) ────────────────────────────────
        rows = conn.execute("""
            SELECT id, tipo, bairro, edificio, corretor, status
            FROM imoveis
            WHERE (contato IS NULL OR contato = '')
              AND status NOT IN ('Vendido','Removido','Cancelado','Descartado')
        """).fetchall()
        sem_contato_i = len(rows)
        if rows:
            avisos.append(f"📵 {sem_contato_i} imóveis ativos sem contato: ids={[r['id'] for r in rows[:10]]}")

        # ── 2. DEMANDAS sem contato ────────────────────────────────────────
        rows = conn.execute("""
            SELECT id, tipo_buscado, bairro_regiao, corretor, status
            FROM demandas
            WHERE (contato IS NULL OR contato = '')
              AND status NOT IN ('Fechado','Cancelado')
        """).fetchall()
        sem_contato_d = len(rows)
        if rows:
            avisos.append(f"📵 {sem_contato_d} demandas sem contato: ids={[r['id'] for r in rows]}")

        # ── 3. IMÓVEIS ativos com specs críticos faltando ──────────────────
        rows = conn.execute("""
            SELECT id, tipo, bairro, preco, area, quartos, corretor
            FROM imoveis
            WHERE status NOT IN ('Vendido','Removido','Cancelado','Descartado')
              AND (area IS NULL OR quartos IS NULL OR preco IS NULL)
        """).fetchall()
        if rows:
            avisos.append(f"⚠️ {len(rows)} imóveis ativos com area/quartos/preco faltando: ids={[r['id'] for r in rows[:10]]}")

        # ── 4. DEMANDAS com edificio/condominio mas quartos/bairro faltando ─
        rows = conn.execute("""
            SELECT id, corretor, edificio, condominio, quartos, bairro_regiao
            FROM demandas
            WHERE (edificio IS NOT NULL OR condominio IS NOT NULL)
              AND (quartos IS NULL OR bairro_regiao IS NULL OR bairro_regiao = '')
              AND status NOT IN ('Fechado','Cancelado')
        """).fetchall()
        if rows:
            avisos.append(f"⚠️ {len(rows)} demandas com edifício mas specs incompletos: ids={[r['id'] for r in rows]}")

        # ── 5. DUPLICATAS em imóveis (mesmo fingerprint) ───────────────────
        # imoveis não tem fingerprint explícito; checar por (corretor+bairro+preco+area)
        rows = conn.execute("""
            SELECT corretor, bairro, preco, area, COUNT(*) as cnt, GROUP_CONCAT(id) as ids
            FROM imoveis
            WHERE status NOT IN ('Vendido','Removido','Cancelado','Descartado')
              AND preco IS NOT NULL
            GROUP BY corretor, bairro, preco, area
            HAVING cnt > 1
        """).fetchall()
        if rows:
            erros.append(f"🔴 {len(rows)} grupos de imóveis duplicados: " +
                         "; ".join(f"ids=[{r['ids']}] ({r['corretor']},{r['bairro']},R${r['preco']},{'área'+str(r['area'])+'m²' if r['area'] else 'sem área'})" for r in rows[:5]))

        # ── 6. DUPLICATAS em demandas (mesmo corretor+edificio, status ativo) ─
        rows = conn.execute("""
            SELECT corretor, edificio, COUNT(*) as cnt, GROUP_CONCAT(id) as ids
            FROM demandas
            WHERE edificio IS NOT NULL AND edificio != ''
              AND status NOT IN ('Fechado','Cancelado')
            GROUP BY corretor, edificio
            HAVING cnt > 1
        """).fetchall()
        if rows:
            erros.append(f"🔴 {len(rows)} demandas duplicadas por corretor+edificio: " +
                         "; ".join(f"{r['corretor']} / {r['edificio']} → ids=[{r['ids']}]" for r in rows))

    # ── Resumo ──────────────────────────────────────────────────────────────
    total_erros  = len(erros)
    total_avisos = len(avisos)

    if not erros and not avisos:
        log(f"✅ Sem erros detectados (imóveis e demandas OK)")
        return

    log(f"── Relatório verificador ──────────────────────────────────────")
    for e in erros:
        log(f"  {e}")
    for a in avisos:
        log(f"  {a}")
    log(f"  Total: {total_erros} erros, {total_avisos} avisos")
    log(f"──────────────────────────────────────────────────────────────")

    # Salvar JSON para uso futuro (ex: badge no site)
    report = {
        "ts": datetime.now().isoformat(),
        "erros": erros,
        "avisos": avisos,
    }
    (Path(__file__).parent / "verificador_erros_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )

if __name__ == "__main__":
    verificar()
