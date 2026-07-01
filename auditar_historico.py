#!/usr/bin/env python3
"""
auditar_historico.py
Reprocessa TODAS as mensagens em mensagens_fila.json (processadas e pendentes)
com a lógica atual de extração/validação, reconcilia com as tabelas imoveis e
demandas (corrige registros existentes errados, insere o que tinha sido
descartado antes das correções), e faz uma segunda passada de validação em
toda a tabela imoveis/demandas usando só os dados já salvos (para os
registros mais antigos cujo texto original não está mais na fila).

IMPORTANTE: mensagens_fila.json só cobre a janela recente (verificar com
--stats). Registros de imoveis mais antigos que essa janela não têm o texto
original disponível — para esses, a auditoria valida os campos já salvos
(bairro, faixas numéricas, cruzamento com condominios) mas não reextrai do
zero.

Uso:
    python3 auditar_historico.py --stats     # só mostra números, não mexe em nada
    python3 auditar_historico.py --dry-run   # mostra tudo que mudaria, sem salvar
    python3 auditar_historico.py --apply     # aplica de verdade
"""

import json, sys, argparse
from pathlib import Path
from datetime import datetime

import db
import processar_mensagens as pm

BASE_DIR  = Path(__file__).parent
FILA_FILE = BASE_DIR / "mensagens_fila.json"

CAMPOS_IMOVEL_COMPARAR = ["tipo", "bairro", "area", "quartos", "suites", "banheiros", "vagas", "preco"]
CAMPOS_DEMANDA_COMPARAR = ["tipo", "bairro", "area", "quartos", "suites", "banheiros", "vagas", "preco"]


def carregar_fila():
    if not FILA_FILE.exists():
        return []
    with open(FILA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def indexar_imoveis_por_chave(conn):
    """(corretor, grupo, data_captura) -> lista de ids (normalmente 1)."""
    rows = conn.execute(
        "SELECT id, corretor, grupo, data_captura FROM imoveis WHERE corretor IS NOT NULL AND corretor != ''"
    ).fetchall()
    idx = {}
    for r in rows:
        chave = (r["corretor"] or "", r["grupo"] or "", r["data_captura"] or "")
        idx.setdefault(chave, []).append(r["id"])
    return idx


def indexar_demandas_por_chave(conn):
    rows = conn.execute("SELECT id, corretor, grupo, data FROM demandas").fetchall()
    idx = {}
    for r in rows:
        chave = (r["corretor"] or "", r["grupo"] or "", r["data"] or "")
        idx.setdefault(chave, []).append(r["id"])
    return idx


def diff_campos(row, campos, mapa_colunas):
    """
    Compara valores atuais da linha do banco com os recém-extraídos. Retorna
    dict {coluna: novo_valor}.

    Bairro é tratado à parte: sem acesso à API aqui, a reextração pode
    perder a validação por busca web que o processamento original teve —
    então só PREENCHE bairro vazio, nunca troca um valor já existente
    (evita regressão silenciosa de um bairro bom pra um pior).
    """
    mudancas = {}
    for campo, coluna in mapa_colunas.items():
        novo = campos.get(campo)
        if novo in (None, ""):
            continue  # não sobrescreve com vazio — só completa o que faltar ou corrige valor concreto
        atual = row[coluna]
        if coluna in ("bairro", "bairro_regiao") and atual:
            continue  # já tem bairro — não mexe (evita perder validação web feita antes)
        # normalizar pra comparação (numérico vs string, float vs int)
        try:
            if atual is not None and novo is not None:
                if float(atual) == float(novo):
                    continue
        except (TypeError, ValueError):
            if str(atual or "").strip() == str(novo or "").strip():
                continue
        mudancas[coluna] = novo
    return mudancas


def reprocessar_fila(conn, aplicar=False):
    """Reextrai todas as mensagens da fila e reconcilia com imoveis/demandas."""
    fila = carregar_fila()
    print(f"📨 {len(fila)} mensagens na fila (histórico disponível)")
    if not fila:
        return {"corrigidos": 0, "novos": 0, "sem_mudanca": 0, "ainda_sem_dados": 0}

    pacotes = pm.agrupar_mensagens(fila)
    print(f"📦 {len(pacotes)} pacotes agrupados\n")

    idx_imoveis  = indexar_imoveis_por_chave(conn)
    idx_demandas = indexar_demandas_por_chave(conn)

    mapa_imovel = {
        "tipo": "tipo", "bairro": "bairro", "area": "area", "quartos": "quartos",
        "suites": "suites", "banheiros": "banheiros", "vagas": "vagas", "preco": "preco",
    }
    mapa_demanda = {
        "tipo": "tipo_buscado", "bairro": "bairro_regiao", "area": "area_min", "quartos": "quartos",
        "suites": "suites", "banheiros": "banheiros", "vagas": "vagas", "preco": "orcamento_max",
    }

    stats = {"corrigidos": 0, "novos": 0, "sem_mudanca": 0, "ainda_sem_dados": 0}

    for pacote in pacotes:
        resultado = pm.resolver_pacote(pacote)
        chave = (pacote["autor"], pacote["grupo"], pacote["data"])

        if resultado is None:
            stats["ainda_sem_dados"] += 1
            continue

        campos, obs, classe = resultado
        tabela = "demandas" if classe == "demanda" else "imoveis"
        idx = idx_demandas if classe == "demanda" else idx_imoveis
        mapa = mapa_demanda if classe == "demanda" else mapa_imovel

        ids = idx.get(chave, [])
        if len(ids) > 1:
            print(f"  ⚠️  {len(ids)} registros ambíguos pra chave {chave} em {tabela} — pulando (revisar manualmente)")
            continue

        if ids:
            row = conn.execute(f"SELECT * FROM {tabela} WHERE id=?", (ids[0],)).fetchone()
            mudancas = diff_campos(row, campos, mapa)
            if mudancas:
                stats["corrigidos"] += 1
                resumo = ", ".join(f"{k}: {row[k]!r} → {v!r}" for k, v in mudancas.items())
                print(f"  🔧 [{tabela} #{ids[0]}] {pacote['autor']} ({pacote['grupo']}): {resumo}")
                if aplicar:
                    sets = ", ".join(f"{k}=?" for k in mudancas)
                    conn.execute(f"UPDATE {tabela} SET {sets} WHERE id=?", (*mudancas.values(), ids[0]))
            else:
                stats["sem_mudanca"] += 1
        else:
            # Não existe registro pra essa mensagem — provavelmente foi descartada
            # antes das correções de hoje (preço "2mi", demanda sem dado numérico, etc.)
            stats["novos"] += 1
            print(f"  ➕ [NOVO {classe}] {pacote['autor']} ({pacote['grupo']}): "
                  f"{campos.get('tipo')} | {campos.get('bairro') or '?'} | R${campos.get('preco')}")
            if aplicar:
                contato_raw = str(pacote.get("contato") or "").replace(".", "").replace(" ", "")
                contato_ok = contato_raw if (contato_raw.isdigit() and 10 <= len(contato_raw) <= 13) else ""
                if not contato_ok and campos.get("link"):
                    contato_ok = campos["link"]
                if classe == "demanda":
                    item = {
                        "data": pacote["data"], "grupo": pacote["grupo"], "corretor": pacote["autor"],
                        "contato": contato_ok, "tipo_buscado": campos.get("tipo"),
                        "bairro_regiao": campos.get("bairro", ""), "area_min": campos.get("area"),
                        "quartos": campos.get("quartos"), "suites": campos.get("suites"),
                        "banheiros": campos.get("banheiros"), "vagas": campos.get("vagas"),
                        "orcamento_max": campos.get("preco"), "observacoes": obs, "status": "Nova",
                    }
                    fp = pm.fazer_fp(pacote["autor"], campos.get("bairro", ""), campos.get("preco"), campos.get("area"), obs)
                    db.inserir_demanda(conn, item, fp)
                else:
                    db.inserir_imovel(conn, {
                        "data_captura": pacote["data"], "grupo": pacote["grupo"], "corretor": pacote["autor"],
                        "contato": contato_ok, "tipo": campos.get("tipo", "Imóvel"),
                        "bairro": campos.get("bairro", ""), "area": campos.get("area"),
                        "quartos": campos.get("quartos"), "suites": campos.get("suites"),
                        "banheiros": campos.get("banheiros"), "vagas": campos.get("vagas"),
                        "preco": campos.get("preco"), "observacoes": obs, "status": "Novo",
                        "data_publicacao": pacote["data"],
                    })

    return stats


# Sites Sub100 (raspar_imoveis.py) tinham um bug corrigido hoje: o card só
# expõe contagem de banheiro, e isso ia parar por engano na coluna "suites".
# Registros antigos raspados antes da correção ainda estão errados.
_DOMINIOS_SUB100 = ("harakiimoveis.com.br", "massaruimoveis.com.br", "bellakaza.com.br")

def remapear_sub100_suites_banheiros(conn, aplicar=False):
    """Corrige retroativamente: suites (na verdade é contagem de banheiro) → banheiros."""
    placeholders = ",".join("?" * len(_DOMINIOS_SUB100))
    rows = conn.execute(
        f"SELECT id, suites, banheiros FROM imoveis "
        f"WHERE grupo IN ({placeholders}) AND suites IS NOT NULL AND banheiros IS NULL",
        _DOMINIOS_SUB100
    ).fetchall()
    for row in rows:
        print(f"  🔧 [imoveis #{row['id']}] (Sub100) suites={row['suites']!r} → banheiros={row['suites']!r}, suites=None")
        if aplicar:
            conn.execute("UPDATE imoveis SET banheiros=?, suites=NULL WHERE id=?", (row["suites"], row["id"]))
    return len(rows)


def auditar_tabela_existente(conn, tabela, aplicar=False):
    """
    Segunda passada: valida bairro (só match local, sem busca web) e faixas
    numéricas de TODOS os registros da tabela, usando os dados já salvos.
    Cobre também os registros mais antigos que não estão mais na fila.
    """
    campo_bairro = "bairro" if tabela == "imoveis" else "bairro_regiao"
    campo_tipo   = "tipo" if tabela == "imoveis" else "tipo_buscado"
    rows = conn.execute(f"SELECT * FROM {tabela}").fetchall()
    corrigidos = 0

    for row in rows:
        campos = {
            "tipo":      row[campo_tipo],
            "quartos":   row["quartos"],
            "suites":    row["suites"],
            "banheiros": row["banheiros"],
            "vagas":     row["vagas"],
            "area":      row["area"] if tabela == "imoveis" else row["area_min"],
        }
        antes = dict(campos)
        pm.validar_campos_numericos(campos)

        mudancas = {}
        for k, v in campos.items():
            if k == "tipo" or v == antes[k]:
                continue
            coluna = "area" if (tabela == "imoveis" and k == "area") else ("area_min" if k == "area" else k)
            mudancas[coluna] = v

        # Bairro: só corrige se bate com match LOCAL (lista oficial), sem gastar API
        bairro_atual = row[campo_bairro]
        if bairro_atual and " · " not in str(bairro_atual):
            oficial, score = pm._match_bairro_oficial(bairro_atual)
            if oficial and oficial != bairro_atual:
                mudancas[campo_bairro] = oficial

        if mudancas:
            corrigidos += 1
            resumo = ", ".join(f"{k}: {row[k]!r} → {v!r}" for k, v in mudancas.items())
            print(f"  🔧 [{tabela} #{row['id']}] {resumo}")
            if aplicar:
                sets = ", ".join(f"{k}=?" for k in mudancas)
                conn.execute(f"UPDATE {tabela} SET {sets} WHERE id=?", (*mudancas.values(), row["id"]))

    return corrigidos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()
    aplicar = args.apply

    if args.stats:
        fila = carregar_fila()
        datas = sorted(set(m.get("data", "")[:10] for m in fila if m.get("data")))
        print(f"Mensagens na fila: {len(fila)} | processadas: {sum(1 for m in fila if m.get('processado'))} "
              f"| pendentes: {sum(1 for m in fila if not m.get('processado'))}")
        print(f"Intervalo coberto pela fila: {datas[0] if datas else '?'} a {datas[-1] if datas else '?'}")
        with db.db_conn() as conn:
            ni = conn.execute("SELECT COUNT(*) FROM imoveis").fetchone()[0]
            nd = conn.execute("SELECT COUNT(*) FROM demandas").fetchone()[0]
        print(f"imoveis.db: {ni} imóveis | {nd} demandas")
        return

    print("=" * 60)
    print(f"AUDITORIA DE HISTÓRICO — {'APLICANDO' if aplicar else 'DRY-RUN (nada será salvo)'}")
    print("=" * 60)

    with db.db_conn() as conn:
        print("\n--- 1) Reprocessando mensagens da fila (texto original disponível) ---\n")
        stats = reprocessar_fila(conn, aplicar=aplicar)

        print("\n--- 2) Remapeando suítes→banheiros dos sites Sub100 (bug antigo) ---\n")
        remapeados_sub100 = remapear_sub100_suites_banheiros(conn, aplicar=aplicar)

        print("\n--- 3) Auditando tabela imoveis inteira (bairro local + faixas numéricas por tipo) ---\n")
        corrigidos_imoveis = auditar_tabela_existente(conn, "imoveis", aplicar=aplicar)

        print("\n--- 4) Auditando tabela demandas inteira ---\n")
        corrigidos_demandas = auditar_tabela_existente(conn, "demandas", aplicar=aplicar)

        if aplicar:
            conn.commit()

    print("\n" + "=" * 60)
    print("RESUMO")
    print("=" * 60)
    print(f"Da fila ({len(carregar_fila())} msgs): {stats['corrigidos']} corrigidos | {stats['novos']} novos "
          f"| {stats['sem_mudanca']} sem mudança | {stats['ainda_sem_dados']} ainda sem dados suficientes")
    print(f"Remapeamento Sub100 (suítes→banheiros): {remapeados_sub100} registros")
    print(f"Auditoria tabela imoveis (faixas numéricas + bairro): {corrigidos_imoveis} corrigidos")
    print(f"Auditoria tabela demandas: {corrigidos_demandas} corrigidos")
    if not aplicar:
        print("\n⚠️  Modo dry-run — nada foi salvo. Rode com --apply pra gravar de verdade.")


if __name__ == "__main__":
    sys.exit(main())
