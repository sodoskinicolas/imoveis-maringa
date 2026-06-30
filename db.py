#!/usr/bin/env python3
"""
db.py — módulo central de banco de dados SQLite.
Todas as leituras/escritas de imoveis.db passam por aqui.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager

BASE_DIR = Path(__file__).parent
DB_PATH  = BASE_DIR / "imoveis.db"

# ─── Schema ───────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS imoveis (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    data_captura    TEXT,
    grupo           TEXT,
    corretor        TEXT,
    contato         TEXT,
    tipo            TEXT,
    bairro          TEXT,
    area            REAL,
    quartos         INTEGER,
    suites          INTEGER,
    banheiros       INTEGER,
    vagas           INTEGER,
    preco           INTEGER,
    observacoes     TEXT,
    status          TEXT DEFAULT 'Novo',
    data_publicacao TEXT,
    slug            TEXT UNIQUE   -- chave de deduplicação (último segmento da URL)
);

CREATE TABLE IF NOT EXISTS demandas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    data            TEXT,
    grupo           TEXT,
    corretor        TEXT,
    contato         TEXT,
    tipo_buscado    TEXT,
    bairro_regiao   TEXT,
    area_min        REAL,
    quartos         INTEGER,
    suites          INTEGER,
    banheiros       INTEGER,
    vagas           INTEGER,
    orcamento_max   INTEGER,
    observacoes     TEXT,
    status          TEXT DEFAULT 'Ativo',
    fingerprint     TEXT UNIQUE   -- chave de deduplicação
);

CREATE TABLE IF NOT EXISTS condominios (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome                    TEXT,
    endereco                TEXT,
    bairro                  TEXT,
    cep                     TEXT,
    construtora             TEXT,
    ano_lancamento          TEXT,
    previsao_entrega        TEXT,
    padrao                  TEXT,
    torres                  INTEGER,
    andares                 INTEGER,
    total_aptos             INTEGER,
    area_min                REAL,
    area_max                REAL,
    quartos                 TEXT,
    vagas                   INTEGER,
    lazer                   TEXT,
    faixa_preco             TEXT,
    observacoes             TEXT,
    site_link               TEXT,
    data_cadastro           TEXT
);

CREATE INDEX IF NOT EXISTS idx_imoveis_grupo   ON imoveis(grupo);
CREATE INDEX IF NOT EXISTS idx_imoveis_tipo    ON imoveis(tipo);
CREATE INDEX IF NOT EXISTS idx_imoveis_preco   ON imoveis(preco);
CREATE INDEX IF NOT EXISTS idx_imoveis_status  ON imoveis(status);
CREATE INDEX IF NOT EXISTS idx_demandas_status ON demandas(status);
"""

# ─── Conexão ──────────────────────────────────────────────────────────────────

def get_conn(path=None):
    """Retorna conexão SQLite com row_factory=sqlite3.Row (acesso por nome de coluna)."""
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # múltiplos leitores simultâneos
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

@contextmanager
def db_conn(path=None):
    """Context manager: abre conexão, commit no sucesso, rollback no erro."""
    conn = get_conn(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db(path=None):
    """Cria tabelas e índices se não existirem."""
    with db_conn(path) as conn:
        conn.executescript(SCHEMA)

# ─── Helpers de imóveis ───────────────────────────────────────────────────────

def slug_from_obs(obs):
    """
    Extrai slug único de uma URL em 'observacoes'.
    Formato: dominio/ultimo-segmento  ex: 'harakiimoveis.com.br/00000123'
    Isso evita colisão entre sites que usam o mesmo CMS (Sub100).
    """
    if not obs:
        return None
    # Pega a primeira palavra que pareça URL
    url = str(obs).strip().split()[0]
    if not url.startswith("http"):
        return None
    # Extrair domínio + último segmento do path
    try:
        # Remove scheme (https://)
        sem_scheme = url.split("://", 1)[1] if "://" in url else url
        partes = [p for p in sem_scheme.rstrip("/").split("/") if p]
        if not partes:
            return None
        dominio = partes[0].lower()
        ultimo  = partes[-1] if len(partes) > 1 else None
        if not ultimo:
            return None
        return f"{dominio}/{ultimo}"
    except Exception:
        return None

def carregar_slugs(conn):
    """Retorna set de slugs já presentes na tabela imoveis (para deduplicação)."""
    rows = conn.execute("SELECT slug FROM imoveis WHERE slug IS NOT NULL").fetchall()
    return {r["slug"] for r in rows}

def carregar_fps_imoveis(conn):
    """
    Retorna set de fingerprints (bairro, area_arred, preco) para deduplicação
    por conteúdo (quando slug não está disponível).
    """
    rows = conn.execute(
        "SELECT bairro, area, preco FROM imoveis"
    ).fetchall()
    fps = set()
    for r in rows:
        bairro = (r["bairro"] or "").lower().strip()[:20]
        area   = round(r["area"] or 0, 0)
        preco  = int(r["preco"] or 0)
        fps.add((bairro, area, preco))
        fps.add(("", area, preco))    # variante sem bairro
    return fps

def inserir_imovel(conn, item):
    """
    Insere um imóvel. Ignora se o slug já existe (INSERT OR IGNORE).
    Retorna True se inserido, False se era duplicata.
    """
    sl = slug_from_obs(item.get("observacoes") or item.get("link", ""))
    cur = conn.execute("""
        INSERT OR IGNORE INTO imoveis
            (data_captura, grupo, corretor, contato, tipo, bairro, area,
             quartos, suites, banheiros, vagas, preco, observacoes,
             status, data_publicacao, slug)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        item.get("data_captura"),
        item.get("grupo"),
        item.get("corretor"),
        item.get("contato"),
        item.get("tipo"),
        item.get("bairro"),
        item.get("area"),
        item.get("quartos"),
        item.get("suites"),
        item.get("banheiros"),
        item.get("vagas"),
        item.get("preco"),
        item.get("observacoes"),
        item.get("status", "Novo"),
        item.get("data_publicacao"),
        sl,
    ))
    return cur.rowcount > 0

# ─── Helpers de demandas ──────────────────────────────────────────────────────

def carregar_fps_demandas(conn):
    """Retorna set de fingerprints de demandas existentes."""
    rows = conn.execute(
        "SELECT fingerprint FROM demandas WHERE fingerprint IS NOT NULL"
    ).fetchall()
    return {r["fingerprint"] for r in rows}

def inserir_demanda(conn, item, fp):
    """
    Insere uma demanda. Ignora se fingerprint já existe.
    Retorna True se inserido.
    """
    cur = conn.execute("""
        INSERT OR IGNORE INTO demandas
            (data, grupo, corretor, contato, tipo_buscado, bairro_regiao,
             area_min, quartos, suites, banheiros, vagas, orcamento_max,
             observacoes, status, fingerprint)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        item.get("data"),
        item.get("grupo"),
        item.get("corretor"),
        item.get("contato"),
        item.get("tipo_buscado"),
        item.get("bairro_regiao"),
        item.get("area_min"),
        item.get("quartos"),
        item.get("suites"),
        item.get("banheiros"),
        item.get("vagas"),
        item.get("orcamento_max"),
        item.get("observacoes"),
        item.get("status", "Ativo"),
        fp,
    ))
    return cur.rowcount > 0

# ─── Leitura para site ────────────────────────────────────────────────────────

def listar_imoveis(conn, excluir_grupos=None):
    """Retorna todos os imóveis como lista de dicts, excluindo grupos especificados."""
    excluir = excluir_grupos or []
    if excluir:
        placeholders = ",".join("?" * len(excluir))
        sql = f"SELECT * FROM imoveis WHERE grupo NOT IN ({placeholders}) ORDER BY id DESC"
        rows = conn.execute(sql, excluir).fetchall()
    else:
        rows = conn.execute("SELECT * FROM imoveis ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]

def listar_demandas(conn):
    """Retorna todas as demandas ativas como lista de dicts."""
    rows = conn.execute(
        "SELECT * FROM demandas WHERE status != 'Inativo' ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]

def buscar_specs_condo(conn, nome):
    """Busca specs de condomínio pelo nome (match parcial)."""
    if not nome:
        return None
    nome_low = nome.strip().lower()
    rows = conn.execute("SELECT * FROM condominios").fetchall()
    for r in rows:
        n = (r["nome"] or "").strip().lower()
        if not n:
            continue
        if nome_low in n or n in nome_low:
            return dict(r)
    return None

def listar_condominios_nomes(conn):
    """Retorna lista de nomes de condomínios cadastrados."""
    rows = conn.execute("SELECT nome FROM condominios WHERE nome IS NOT NULL").fetchall()
    return [r["nome"] for r in rows if r["nome"]]


if __name__ == "__main__":
    init_db()
    with db_conn() as conn:
        ni = conn.execute("SELECT COUNT(*) FROM imoveis").fetchone()[0]
        nd = conn.execute("SELECT COUNT(*) FROM demandas").fetchone()[0]
        nc = conn.execute("SELECT COUNT(*) FROM condominios").fetchone()[0]
    print(f"✅ imoveis.db OK — {ni} imóveis | {nd} demandas | {nc} condomínios")
# 2026-06-30
