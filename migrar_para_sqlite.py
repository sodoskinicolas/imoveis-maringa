#!/usr/bin/env python3
"""
migrar_para_sqlite.py
Migração única: lê Imoveis_Grupos.xlsx e popula imoveis.db.
Execute uma vez. Após a migração, o xlsx não é mais usado.

Uso:
    python3 migrar_para_sqlite.py
"""

from pathlib import Path
import pandas as pd
import db

BASE_DIR = Path(__file__).parent
PLANILHA = BASE_DIR / "Imoveis_Grupos.xlsx"


def _str(v):
    if v is None:
        return None
    s = str(v).strip()
    return None if s in ("", "nan", "None", "NaT") else s

def _int(v):
    try:
        f = float(v)
        return int(f) if f == f else None   # NaN check
    except (TypeError, ValueError):
        return None

def _float(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def migrar_imoveis(conn):
    print("📋 Migrando aba Imóveis...")
    df = pd.read_excel(PLANILHA, sheet_name="Imóveis", dtype=str)
    df = df.where(pd.notnull(df), None)
    inseridos = ignorados = 0

    for _, r in df.iterrows():
        obs = _str(r.get("Observações"))
        sl  = db.slug_from_obs(obs)
        cur = conn.execute("""
            INSERT OR IGNORE INTO imoveis
                (data_captura, grupo, corretor, contato, tipo, bairro, area,
                 quartos, suites, banheiros, vagas, preco, observacoes,
                 status, data_publicacao, slug)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            _str(r.get("Data Captura")),
            _str(r.get("Grupo")),
            _str(r.get("Corretor")),
            _str(r.get("Contato (WhatsApp)")),
            _str(r.get("Tipo")),
            _str(r.get("Bairro / Endereço")),
            _float(r.get("Área (m²)")),
            _int(r.get("Quartos")),
            _int(r.get("Suítes")),
            _int(r.get("Banheiros")),
            _int(r.get("Vagas")),
            _int(r.get("Preço (R$)")),
            obs,
            _str(r.get("Status")) or "Novo",
            _str(r.get("Data Publicação")),
            sl,
        ))
        if cur.rowcount:
            inseridos += 1
        else:
            ignorados += 1

    print(f"   ✅ {inseridos} inseridos | {ignorados} duplicatas ignoradas")


def migrar_demandas(conn):
    print("📋 Migrando aba Demandas...")
    df = pd.read_excel(PLANILHA, sheet_name="Demandas", dtype=str)
    df = df.where(pd.notnull(df), None)
    inseridos = ignorados = 0

    for _, r in df.iterrows():
        corretor = _str(r.get("Corretor"))
        preco    = _int(r.get("Orçamento Máx"))
        bairro   = _str(r.get("Bairro/Região"))
        area     = _float(r.get("Área Mín"))
        obs      = _str(r.get("Observações"))

        # Fingerprint igual ao de processar_mensagens.py
        try:
            fp_preco = int(float(preco)) if preco else 0
        except:
            fp_preco = 0
        try:
            fp_area = int(float(area)) if area else 0
        except:
            fp_area = 0
        autor_low = (corretor or "").lower().strip()
        bairro_low = (bairro or "").lower().strip()
        texto_curto = (obs or "")[:80].lower().strip()

        if bairro_low and fp_preco:
            fp = f"{autor_low}|{bairro_low}|{fp_preco}"
        elif fp_preco and fp_area:
            fp = f"{autor_low}|{fp_preco}|{fp_area}"
        elif fp_preco:
            fp = f"{autor_low}|{fp_preco}"
        elif texto_curto:
            fp = f"{autor_low}|txt:{texto_curto}"
        else:
            fp = None

        cur = conn.execute("""
            INSERT OR IGNORE INTO demandas
                (data, grupo, corretor, contato, tipo_buscado, bairro_regiao,
                 area_min, quartos, suites, banheiros, vagas, orcamento_max,
                 observacoes, status, fingerprint)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            _str(r.get("Data")),
            _str(r.get("Grupo")),
            corretor,
            _str(r.get("Contato")),
            _str(r.get("Tipo Buscado")),
            bairro,
            area,
            _int(r.get("Quartos")),
            _int(r.get("Suítes")),
            _int(r.get("Banheiros")),
            _int(r.get("Vagas")),
            preco,
            obs,
            _str(r.get("Status")) or "Ativo",
            fp,
        ))
        if cur.rowcount:
            inseridos += 1
        else:
            ignorados += 1

    print(f"   ✅ {inseridos} inseridos | {ignorados} duplicatas ignoradas")


def migrar_condominios(conn):
    print("📋 Migrando aba Condomínios...")
    df = pd.read_excel(PLANILHA, sheet_name="Condomínios", dtype=str)
    df = df.where(pd.notnull(df), None)
    inseridos = 0

    for _, r in df.iterrows():
        nome = _str(r.get("Nome"))
        if not nome:
            continue
        conn.execute("""
            INSERT OR REPLACE INTO condominios
                (nome, endereco, bairro, cep, construtora, ano_lancamento,
                 previsao_entrega, padrao, torres, andares, total_aptos,
                 area_min, area_max, quartos, vagas, lazer, faixa_preco,
                 observacoes, site_link, data_cadastro)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            nome,
            _str(r.get("Endereço")),
            _str(r.get("Bairro")),
            _str(r.get("CEP")),
            _str(r.get("Construtora / Incorporadora")),
            _str(r.get("Ano Lançamento")),
            _str(r.get("Previsão Entrega")),
            _str(r.get("Padrão")),
            _int(r.get("Torres")),
            _int(r.get("Andares")),
            _int(r.get("Total Aptos")),
            _float(r.get("Área Mín (m²)")),
            _float(r.get("Área Máx (m²)")),
            _str(r.get("Quartos")),
            _int(r.get("Vagas")),
            _str(r.get("Lazer")),
            _str(r.get("Faixa de Preço")),
            _str(r.get("Observações")),
            _str(r.get("Site / Link")),
            _str(r.get("Data Cadastro")),
        ))
        inseridos += 1

    print(f"   ✅ {inseridos} condomínios inseridos")


def main():
    if not PLANILHA.exists():
        print(f"❌ Planilha não encontrada: {PLANILHA}")
        return

    print(f"🚀 Iniciando migração: {PLANILHA} → {db.DB_PATH}")
    db.init_db()

    with db.db_conn() as conn:
        migrar_imoveis(conn)
        migrar_demandas(conn)
        migrar_condominios(conn)

        ni = conn.execute("SELECT COUNT(*) FROM imoveis").fetchone()[0]
        nd = conn.execute("SELECT COUNT(*) FROM demandas").fetchone()[0]
        nc = conn.execute("SELECT COUNT(*) FROM condominios").fetchone()[0]

    print(f"\n✅ Migração concluída → {db.DB_PATH}")
    print(f"   {ni} imóveis | {nd} demandas | {nc} condomínios")


if __name__ == "__main__":
    main()
