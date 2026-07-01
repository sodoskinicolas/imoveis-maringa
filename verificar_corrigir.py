#!/usr/bin/env python3
"""
verificar_corrigir.py
Quality gate automático — roda ANTES de gerar_site.py.
Garante que os dados no banco atendem ao padrão mínimo dos cards.

Correções automáticas:
  ① Limpa markdown do WhatsApp (*bold*, _italic_, ~riscado~) do campo obs
  ② Remove texto de resposta de IA salvo acidentalmente como dado
  ③ Normaliza tipo para valores padronizados (Apartamento, Casa, etc.)
  ④ Limpa bairro/bairro_regiao que contenha texto de IA ou seja inválido
  ⑤ Revalida bairro contra lista oficial de Maringá (326 bairros)

Uso:
    python3 verificar_corrigir.py           # corrige no banco
    python3 verificar_corrigir.py --dry-run # mostra sem alterar
    python3 verificar_corrigir.py --verbose # mostra todos os checks
"""

import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import db
import processar_mensagens as pm

DRY_RUN = "--dry-run" in sys.argv
VERBOSE  = "--verbose" in sys.argv

# ── Tipos válidos ──────────────────────────────────────────────────────────────
_TIPOS_VALIDOS = {
    'Apartamento', 'Casa', 'Terreno', 'Sobrado', 'Sala Comercial',
    'Galpão', 'Kitnet', 'Chácara', 'Sítio', 'Imóvel',
}

_TIPO_MAP = [
    (['apartamento', 'apto', 'cobertura', 'kitnet', 'andar'], 'Apartamento'),
    (['casa'],                                                  'Casa'),
    (['terreno', 'lote'],                                       'Terreno'),
    (['sobrado'],                                               'Sobrado'),
    (['sala comercial', 'sala', 'loja', 'comercial'],          'Sala Comercial'),
    (['galpão', 'galpao'],                                      'Galpão'),
    (['kitnet', 'kit net'],                                     'Kitnet'),
    (['chácara', 'chacara'],                                    'Chácara'),
    (['sítio', 'sitio'],                                        'Sítio'),
]

def _normalizar_tipo(tipo, obs=''):
    """Devolve tipo padronizado; infere do obs se tipo está errado/vazio."""
    t = (tipo or '').strip()
    if t in _TIPOS_VALIDOS:
        return t
    tl = t.lower()
    for palavras, valor in _TIPO_MAP:
        if any(p in tl for p in palavras):
            return valor
    if obs:
        ol = obs.lower()
        for palavras, valor in _TIPO_MAP:
            if any(p in ol for p in palavras):
                return valor
    return t or 'Imóvel'

# ── Detecção de texto de IA salvo acidentalmente ──────────────────────────────
# Quando o modelo Claude retorna uma resposta conversacional em vez de extrair
# um campo, esse texto pode ser salvo no banco. Detecta por prefixos típicos.
_PREFIXOS_IA = (
    'vou ', 'preciso de mais ', 'infelizmente', 'desculpe',
    'como ia', 'não tenho acesso', 'nao tenho acesso', 'para responder',
    'me forneça', 'poderia me ', 'pode me ', 'não consegui localizar',
    'nao consegui localizar', 'com base nas informações', 'lamento ',
    'sinto ', 'entendo ', 'não foi possível', 'nao foi possivel',
)

def _parece_ia(texto):
    """True se o texto parece resposta conversacional do modelo salva acidentalmente."""
    if not texto:
        return False
    tl = texto.strip().lower()
    return any(tl.startswith(p) for p in _PREFIXOS_IA)

# ── Verificação de preço ───────────────────────────────────────────────────────
def _preco_invalido(preco):
    """True se o campo preço contém texto em vez de número."""
    if not preco:
        return False
    limpo = re.sub(r'[r$\s.,]', '', str(preco).lower())
    return bool(limpo) and not limpo.isdigit()

# ── Verificação de edificio em demandas (somente log) ─────────────────────────
def _checar_edificio(obs):
    try:
        return pm.extrair_edificio(obs) if obs else None
    except Exception:
        return None

# ── Verificar e corrigir tabela imóveis ───────────────────────────────────────

def verificar_imoveis(conn):
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, tipo, bairro, preco, observacoes FROM imoveis"
    ).fetchall()

    corrigidos = 0
    alertas    = []

    for rid, tipo, bairro, preco, obs in rows:
        fixes = {}

        # ① Limpar markdown WhatsApp no obs
        obs_limpo = pm.limpar_obs(obs or '')
        if obs_limpo != (obs or ''):
            fixes['observacoes'] = obs_limpo
            if VERBOSE:
                print(f"    [#{rid}] obs: removeu markdown")

        # ② Bairro com texto de IA → apaga
        if _parece_ia(bairro or ''):
            fixes['bairro'] = ''
            alertas.append(f"  ⚠️  [imoveis #{rid}] bairro parecia IA → apagado: {(bairro or '')[:60]!r}")

        # ③ Normalizar tipo
        tipo_novo = _normalizar_tipo(tipo or '', obs_limpo)
        if tipo_novo != (tipo or ''):
            fixes['tipo'] = tipo_novo
            if VERBOSE:
                print(f"    [#{rid}] tipo: {tipo!r} → {tipo_novo!r}")

        # ④ Preço inválido → só alerta, não apaga (pode ser "consulte")
        if _preco_invalido(preco):
            alertas.append(f"  ⚠️  [imoveis #{rid}] preço suspeito: {preco!r}")

        if fixes:
            if VERBOSE:
                print(f"  [imoveis #{rid}] corrigindo: {list(fixes.keys())}")
            if not DRY_RUN:
                set_clause = ', '.join(f"{k}=?" for k in fixes)
                cur.execute(f"UPDATE imoveis SET {set_clause} WHERE id=?",
                            list(fixes.values()) + [rid])
            corrigidos += 1

    if not DRY_RUN:
        conn.commit()

    for a in alertas:
        print(a)
    print(f"  ✅ imoveis: {corrigidos} corrigido(s)"
          + (f", {len(alertas)} alerta(s)" if alertas else ""))
    return corrigidos, len(alertas)

# ── Verificar e corrigir tabela demandas ──────────────────────────────────────

def verificar_demandas(conn):
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, tipo_buscado, bairro_regiao, orcamento_max, observacoes FROM demandas"
    ).fetchall()

    corrigidos   = 0
    alertas      = []
    sem_edificio = []

    for rid, tipo, bairro, orc, obs in rows:
        fixes = {}

        # ① Limpar markdown WhatsApp no obs
        obs_limpo = pm.limpar_obs(obs or '')
        if obs_limpo != (obs or ''):
            fixes['observacoes'] = obs_limpo
            if VERBOSE:
                print(f"    [#{rid}] obs: removeu markdown")

        # ② Bairro com texto de IA → apaga
        if _parece_ia(bairro or ''):
            fixes['bairro_regiao'] = ''
            alertas.append(f"  ⚠️  [demandas #{rid}] bairro parecia IA → apagado: {(bairro or '')[:60]!r}")

        # ③ Normalizar tipo
        tipo_novo = _normalizar_tipo(tipo or '', obs_limpo)
        if tipo_novo != (tipo or ''):
            fixes['tipo_buscado'] = tipo_novo
            if VERBOSE:
                print(f"    [#{rid}] tipo: {tipo!r} → {tipo_novo!r}")

        # ④ Verificar se edificio seria extraído (confirma que vai aparecer no card)
        edificio = _checar_edificio(obs_limpo)
        if not edificio and obs_limpo and VERBOSE:
            sem_edificio.append(f"    [demandas #{rid}] sem edificio extraído do obs")

        if fixes:
            if VERBOSE:
                print(f"  [demandas #{rid}] corrigindo: {list(fixes.keys())}")
            if not DRY_RUN:
                set_clause = ', '.join(f"{k}=?" for k in fixes)
                cur.execute(f"UPDATE demandas SET {set_clause} WHERE id=?",
                            list(fixes.values()) + [rid])
            corrigidos += 1

    if not DRY_RUN:
        conn.commit()

    for a in alertas:
        print(a)
    if VERBOSE:
        for s in sem_edificio:
            print(s)
    print(f"  ✅ demandas: {corrigidos} corrigido(s)"
          + (f", {len(alertas)} alerta(s)" if alertas else ""))
    return corrigidos, len(alertas)

# ── Revalidar bairros (delega ao validar_bairros_db) ─────────────────────────

def revalidar_bairros(conn):
    """Re-roda a validação de bairros contra os 326 oficiais de Maringá."""
    try:
        from validar_bairros_db import validar_tabela
        c1 = validar_tabela(conn, "imoveis",  col_bairro="bairro",      col_edificio="edificio")
        # demandas: bairro_regiao pode ter múltiplos separados por " · "
        cur = conn.cursor()
        rows = cur.execute("SELECT id, bairro_regiao FROM demandas").fetchall()
        c2 = 0
        for rid, bairro_atual in rows:
            bairro_atual = (bairro_atual or '').strip()
            if not bairro_atual:
                continue
            partes = [p.strip() for p in bairro_atual.split(' · ') if p.strip()]
            validados = [pm.validar_bairro(p) for p in partes]
            bairro_novo = ' · '.join(dict.fromkeys(v for v in validados if v))
            if bairro_novo != bairro_atual:
                print(f"  [demandas #{rid}] bairro: {bairro_atual!r} → {bairro_novo!r}")
                if not DRY_RUN:
                    cur.execute("UPDATE demandas SET bairro_regiao=? WHERE id=?",
                                (bairro_novo, rid))
                c2 += 1
        if not DRY_RUN:
            conn.commit()
        print(f"  ✅ bairros: {c1 + c2} corrigido(s)")
        return c1 + c2
    except Exception as e:
        print(f"  ⚠️  Revalidação de bairros ignorada: {e}")
        return 0

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    print("🔍 Quality gate — verificando dados antes de publicar...")
    if DRY_RUN:
        print("  (dry-run: nenhuma alteração salva)\n")

    db.init_db()
    pm._carregar_bairros_oficiais()

    total_fixes  = 0
    total_alerts = 0

    with db.db_conn() as conn:
        print("\n── Imóveis ──────────────────────────────────────────────────────")
        c1, a1 = verificar_imoveis(conn)

        print("\n── Demandas ─────────────────────────────────────────────────────")
        c2, a2 = verificar_demandas(conn)

        print("\n── Bairros ──────────────────────────────────────────────────────")
        c3 = revalidar_bairros(conn)

        total_fixes  = c1 + c2 + c3
        total_alerts = a1 + a2

    print()
    if total_fixes or total_alerts:
        print(f"✅ {total_fixes} correção(ões) automática(s)"
              + (f" · {total_alerts} alerta(s) para revisão manual" if total_alerts else ""))
    else:
        print("✅ Dados OK — nenhuma correção necessária.")

if __name__ == "__main__":
    main()
