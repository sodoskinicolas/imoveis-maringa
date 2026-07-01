#!/usr/bin/env python3
"""
db.py — módulo central de banco de dados SQLite.
Todas as leituras/escritas de imoveis.db passam por aqui.
"""

import re
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import date

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
    slug            TEXT UNIQUE,  -- chave de deduplicação (último segmento da URL)
    fonte           TEXT,         -- 'Junior Joda', 'VivaReal', ou NULL/'' pra grupos de WhatsApp
    ref_externa     TEXT,         -- Ref./ID estável na fonte externa (pra upsert + histórico)
    nome            TEXT,         -- nome do empreendimento (quando houver, ex: JJ)
    link            TEXT,         -- URL do anúncio na fonte externa
    data_venda      TEXT          -- data em que foi marcado Vendido/Removido
);

CREATE TABLE IF NOT EXISTS preco_historico (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    imovel_id       INTEGER NOT NULL REFERENCES imoveis(id),
    preco           INTEGER,
    data            TEXT
);
CREATE INDEX IF NOT EXISTS idx_preco_hist_imovel ON preco_historico(imovel_id);

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

def _colunas_existentes(conn, tabela):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({tabela})").fetchall()}

def _migrar_schema(conn):
    """Adiciona colunas novas em bancos já existentes (idempotente — ALTER TABLE ADD COLUMN)."""
    cols_i = _colunas_existentes(conn, "imoveis")
    novas_i = {
        "fonte":       "TEXT",
        "ref_externa": "TEXT",
        "nome":        "TEXT",
        "link":        "TEXT",
        "data_venda":  "TEXT",
        "edificio":    "TEXT",   # nome do edifício/condomínio extraído do obs
    }
    for col, tipo in novas_i.items():
        if col not in cols_i:
            conn.execute(f"ALTER TABLE imoveis ADD COLUMN {col} {tipo}")

    cols_d = _colunas_existentes(conn, "demandas")
    if "edificio" not in cols_d:
        conn.execute("ALTER TABLE demandas ADD COLUMN edificio TEXT")

def _backfill_fonte_legado(conn):
    """
    Preenche fonte/ref_externa em linhas legadas que foram inseridas direto no
    banco (ex: migração antiga de Imoveis_Grupos.xlsx) antes de essas colunas
    existirem, mas que na verdade vêm de fonte externa — identificáveis pelo
    valor de 'grupo' e por um id/ref embutido em 'observacoes'. Sem isso, o
    próximo upsert dessas fontes criaria linhas duplicadas em vez de
    atualizar as existentes. Idempotente: só afeta linhas com fonte NULL.
    """
    rows = conn.execute(
        "SELECT id, observacoes FROM imoveis WHERE fonte IS NULL AND grupo='vivareal.com.br'"
    ).fetchall()
    for r in rows:
        m = re.search(r'id:(\d+)', r["observacoes"] or "")
        if m:
            conn.execute(
                "UPDATE imoveis SET fonte='VivaReal', ref_externa=? WHERE id=?",
                (m.group(1), r["id"]),
            )

    rows = conn.execute(
        "SELECT id, observacoes FROM imoveis WHERE fonte IS NULL AND grupo='juniorjoda.com.br'"
    ).fetchall()
    for r in rows:
        m = re.search(r'Ref\.?\s*(\d+)', r["observacoes"] or "")
        if m:
            conn.execute(
                "UPDATE imoveis SET fonte='Junior Joda', ref_externa=? WHERE id=?",
                (m.group(1), r["id"]),
            )

def init_db(path=None):
    """Cria tabelas e índices se não existirem."""
    with db_conn(path) as conn:
        conn.executescript(SCHEMA)
        _migrar_schema(conn)
        _backfill_fonte_legado(conn)
        # Índice único parcial: garante 1 linha por (fonte, ref_externa) pra permitir upsert.
        # Só pode ser criado depois da migração/backfill, já que as colunas podem ser novas.
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_imoveis_fonte_ref
            ON imoveis(fonte, ref_externa)
            WHERE fonte IS NOT NULL AND ref_externa IS NOT NULL
        """)

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

# ─── Upsert de fontes externas (VivaReal, Junior Joda, etc.) ─────────────────
#
# Diferente de inserir_imovel() (usado nas mensagens de grupo, que são
# eventos imutáveis), aqui cada rodada de scrape/import é uma FOTOGRAFIA do
# catálogo atual de uma fonte. Por isso usamos upsert por (fonte, ref_externa)
# em vez de sempre inserir: se o imóvel já existe, atualizamos os dados e, se
# o preço mudou, registramos em preco_historico. Isso permite reconstruir a
# evolução de preço de cada imóvel — e, agrupando por 'nome'/'bairro', de
# cada edifício — ao longo do tempo.

def upsert_imovel_externo(conn, item, fonte):
    """
    Insere ou atualiza um imóvel de fonte externa, identificado por
    (fonte, ref_externa). Se o preço mudou desde a última captura, grava o
    novo preço em preco_historico (histórico por imóvel/edifício).

    item deve conter pelo menos: ref_externa, preco. Demais campos são os
    mesmos usados em inserir_imovel().

    Retorna tupla (acao, imovel_id) onde acao é 'novo', 'atualizado',
    'preco_mudou' ou 'sem_mudanca'. Retorna ('erro', None) se ref_externa
    estiver vazio.
    """
    ref = str(item.get("ref_externa") or "").strip()
    if not ref:
        return ("erro", None)

    hoje = item.get("data_captura") or date.today().isoformat()
    row = conn.execute(
        "SELECT id, preco, status FROM imoveis WHERE fonte=? AND ref_externa=?",
        (fonte, ref),
    ).fetchone()

    if row is None:
        sl = slug_from_obs(item.get("link") or "")
        cur = conn.execute("""
            INSERT INTO imoveis
                (data_captura, grupo, corretor, contato, tipo, bairro, area,
                 quartos, suites, banheiros, vagas, preco, observacoes,
                 status, data_publicacao, slug, fonte, ref_externa, nome, link)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            hoje, item.get("grupo") or fonte, item.get("corretor"), item.get("contato"),
            item.get("tipo"), item.get("bairro"), item.get("area"),
            item.get("quartos"), item.get("suites"), item.get("banheiros"), item.get("vagas"),
            item.get("preco"), item.get("observacoes"),
            item.get("status", "Novo"), item.get("data_publicacao"), sl,
            fonte, ref, item.get("nome"), item.get("link"),
        ))
        novo_id = cur.lastrowid
        if item.get("preco") is not None:
            conn.execute(
                "INSERT INTO preco_historico (imovel_id, preco, data) VALUES (?,?,?)",
                (novo_id, item.get("preco"), hoje),
            )
        return ("novo", novo_id)

    imovel_id, preco_antigo, status_antigo = row["id"], row["preco"], row["status"]
    preco_novo = item.get("preco")

    # Se estava Vendido/Removido e reapareceu nesta captura, reativa o status.
    status_novo = status_antigo
    if status_antigo in ("Vendido", "Removido") and item.get("status"):
        status_novo = item.get("status")

    campos = {
        "corretor":        item.get("corretor"),
        "tipo":            item.get("tipo"),
        "bairro":          item.get("bairro"),
        "area":            item.get("area"),
        "quartos":         item.get("quartos"),
        "suites":          item.get("suites"),
        "banheiros":       item.get("banheiros"),
        "vagas":           item.get("vagas"),
        "observacoes":     item.get("observacoes"),
        "data_publicacao": item.get("data_publicacao"),
        "nome":            item.get("nome"),
        "link":            item.get("link"),
        "preco":           preco_novo,
        "status":          status_novo,
    }
    sets = ", ".join(f"{c}=?" for c in campos)
    conn.execute(f"UPDATE imoveis SET {sets} WHERE id=?", (*campos.values(), imovel_id))

    mudou_preco = (
        preco_novo is not None and preco_antigo is not None
        and int(preco_novo) != int(preco_antigo)
    )
    if mudou_preco:
        conn.execute(
            "INSERT INTO preco_historico (imovel_id, preco, data) VALUES (?,?,?)",
            (imovel_id, preco_novo, hoje),
        )
        return ("preco_mudou", imovel_id)
    return ("atualizado", imovel_id)


def marcar_ausentes(conn, fonte, refs_presentes, status_marca="Removido"):
    """
    Marca como Removido (por padrão) tudo que é dessa fonte, ainda não está
    Vendido/Removido, e não apareceu na captura mais recente (refs_presentes).
    Retorna quantas linhas foram marcadas.
    """
    refs = [str(r) for r in refs_presentes]
    hoje = date.today().isoformat()
    if refs:
        placeholders = ",".join("?" * len(refs))
        sql = f"""
            UPDATE imoveis
            SET status=?, data_venda=?
            WHERE fonte=? AND status NOT IN ('Vendido','Removido')
              AND (ref_externa IS NULL OR ref_externa NOT IN ({placeholders}))
        """
        params = (status_marca, hoje, fonte, *refs)
    else:
        sql = """
            UPDATE imoveis
            SET status=?, data_venda=?
            WHERE fonte=? AND status NOT IN ('Vendido','Removido')
        """
        params = (status_marca, hoje, fonte)
    cur = conn.execute(sql, params)
    return cur.rowcount


def historico_preco(conn, imovel_id):
    """Retorna o histórico de preços de um imóvel específico, em ordem cronológica."""
    rows = conn.execute(
        "SELECT preco, data FROM preco_historico WHERE imovel_id=? ORDER BY data",
        (imovel_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def historico_edificio(termo, conn=None):
    """
    Retorna o histórico de preços de todos os imóveis cujo nome/bairro batem
    com `termo` (match parcial, case-insensitive) — útil pra acompanhar a
    evolução de preços de um edifício/empreendimento ao longo do tempo.
    """
    fechar = conn is None
    conn = conn or get_conn()
    try:
        like = f"%{termo.strip().lower()}%"
        rows = conn.execute("""
            SELECT i.id AS imovel_id, i.nome, i.bairro, i.tipo, i.fonte,
                   ph.preco, ph.data
            FROM imoveis i
            JOIN preco_historico ph ON ph.imovel_id = i.id
            WHERE lower(COALESCE(i.nome,'')) LIKE ? OR lower(COALESCE(i.bairro,'')) LIKE ?
            ORDER BY i.id, ph.data
        """, (like, like)).fetchall()
        return [dict(r) for r in rows]
    finally:
        if fechar:
            conn.close()


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
             status, data_publicacao, slug, edificio)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
        item.get("edificio"),
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
             observacoes, status, fingerprint, edificio)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
        item.get("edificio"),
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
