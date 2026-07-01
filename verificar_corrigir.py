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
  ⑥ Extrai/verifica edificio nos cards de imóveis e demandas:
       - Popula edificio vazio quando obs menciona um prédio
       - Limpa edificio com endereço embutido (Rua, Av., nº)
       - Limpa edificio que é palavra genérica ou texto de IA
       - Corrige capitalização contra banco de condomínios

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

# ── Validação de edificio ─────────────────────────────────────────────────────
_RE_ENDERECO = re.compile(
    r'\b(rua|av\.|avenida|travessa|alameda|estrada|rod\.|rodovia|n[oº°]\.?\s*\d)',
    re.IGNORECASE
)
# Palavras que aparecem em frases mas nunca em nomes de prédio
_PALAVRAS_FRASE = {
    'ou', 'ok', 'ser', 'não', 'nao', 'sim', 'mas', 'até', 'ate',
    'deixar', 'locado', 'locados', 'financiamento', 'documentação',
    'documentacao', 'mobiliado', 'mobiliada', 'semi', 'reformado',
    'aceita', 'aceito', 'pretende', 'térreo', 'terreo',
}

def _edificio_invalido(edificio):
    """
    Retorna motivo de invalidade (str) ou None se parece OK.
    Inválido quando:
    - Contém padrão de endereço (Rua X, Av. Y, nº 123)
    - Tem mais de 50 chars (frases longas, não nome de prédio)
    - Contém palavra típica de frase ("ou", "ok", "aceita", etc.)
    - Primeira palavra é genérica (blocklist de processar_mensagens)
    - Parece texto de IA
    """
    if not edificio:
        return None
    e = edificio.strip()
    if _RE_ENDERECO.search(e):
        return "contém endereço"
    if len(e) > 50:
        return "muito longo"
    if _parece_ia(e):
        return "parece texto de IA"
    palavras = e.lower().split()
    # Qualquer palavra de frase no meio do valor → é uma frase, não nome de prédio
    if any(p in _PALAVRAS_FRASE for p in palavras):
        return f"contém palavra de frase ({next(p for p in palavras if p in _PALAVRAS_FRASE)!r})"
    # Primeira palavra no blocklist genérico de processar_mensagens
    if palavras and palavras[0] in pm._EDIFICIO_GENERICO:
        return f"palavra genérica ({palavras[0]!r})"
    return None

def _extrair_edificio_seguro(obs):
    try:
        return pm.extrair_edificio(obs) if obs else None
    except Exception:
        return None

def _extrair_condominio_seguro(obs):
    try:
        return pm.extrair_condominio(obs) if obs else None
    except Exception:
        return None

# ── Verificar e corrigir tabela imóveis ───────────────────────────────────────

def verificar_imoveis(conn):
    cur = conn.cursor()
    # Inclui edificio na query (coluna pode não existir em bancos antigos — já migrado acima)
    rows = cur.execute(
        "SELECT id, tipo, bairro, preco, observacoes, edificio, condominio FROM imoveis"
    ).fetchall()

    corrigidos = 0
    alertas    = []

    for rid, tipo, bairro, preco, obs, edificio_atual, condominio_atual in rows:
        fixes = {}

        # ① Limpar markdown WhatsApp no obs
        obs_limpo = pm.limpar_obs(obs or '')
        if obs_limpo != (obs or ''):
            fixes['observacoes'] = obs_limpo

        # ② Bairro com texto de IA → apaga
        if _parece_ia(bairro or ''):
            fixes['bairro'] = ''
            alertas.append(f"  ⚠️  [imoveis #{rid}] bairro parecia IA → apagado")

        # ③ Normalizar tipo
        tipo_novo = _normalizar_tipo(tipo or '', obs_limpo)
        if tipo_novo != (tipo or ''):
            fixes['tipo'] = tipo_novo

        # ④ Preço inválido → só alerta
        if _preco_invalido(preco):
            alertas.append(f"  ⚠️  [imoveis #{rid}] preço suspeito: {preco!r}")

        # ⑥a Verificar/popular edificio
        motivo = _edificio_invalido(edificio_atual)
        if motivo:
            novo = _extrair_edificio_seguro(obs_limpo)
            if novo and not _edificio_invalido(novo):
                fixes['edificio'] = novo
                if VERBOSE:
                    print(f"    [imoveis #{rid}] edificio: {edificio_atual!r} ({motivo}) → {novo!r}")
            else:
                fixes['edificio'] = None
                if VERBOSE:
                    print(f"    [imoveis #{rid}] edificio: {edificio_atual!r} ({motivo}) → limpo")
        elif not edificio_atual:
            novo = _extrair_edificio_seguro(obs_limpo)
            if novo and not _edificio_invalido(novo):
                fixes['edificio'] = novo
                if VERBOSE:
                    print(f"    [imoveis #{rid}] edificio: (vazio) → {novo!r}")

        # ⑥b Verificar/popular condominio
        motivo_c = _edificio_invalido(condominio_atual)
        if motivo_c:
            novo_c = _extrair_condominio_seguro(obs_limpo)
            if novo_c and not _edificio_invalido(novo_c):
                fixes['condominio'] = novo_c
                if VERBOSE:
                    print(f"    [imoveis #{rid}] condominio: {condominio_atual!r} ({motivo_c}) → {novo_c!r}")
            else:
                fixes['condominio'] = None
                if VERBOSE:
                    print(f"    [imoveis #{rid}] condominio: {condominio_atual!r} ({motivo_c}) → limpo")
        elif not condominio_atual:
            novo_c = _extrair_condominio_seguro(obs_limpo)
            if novo_c and not _edificio_invalido(novo_c):
                fixes['condominio'] = novo_c
                if VERBOSE:
                    print(f"    [imoveis #{rid}] condominio: (vazio) → {novo_c!r}")

        # Deduplicação: se edificio e condominio ficaram iguais → limpar edificio
        e_final = fixes.get('edificio', edificio_atual)
        c_final = fixes.get('condominio', condominio_atual)
        if e_final and c_final and str(e_final).lower() == str(c_final).lower():
            fixes['edificio'] = None
            if VERBOSE:
                print(f"    [imoveis #{rid}] edificio dedup com condominio → limpo")

        if fixes:
            if VERBOSE:
                print(f"  [imoveis #{rid}] fixes: {list(fixes.keys())}")
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
        "SELECT id, tipo_buscado, bairro_regiao, orcamento_max, observacoes, edificio, condominio, contato, "
        "area_min, quartos, vagas FROM demandas"
    ).fetchall()

    corrigidos = 0
    alertas    = []

    for rid, tipo, bairro, orc, obs, edificio_atual, condominio_atual, contato, area_min, quartos, vagas in rows:
        fixes = {}

        # ① Limpar markdown WhatsApp no obs
        obs_limpo = pm.limpar_obs(obs or '')
        if obs_limpo != (obs or ''):
            fixes['observacoes'] = obs_limpo

        # ② Bairro com texto de IA → apaga
        if _parece_ia(bairro or ''):
            fixes['bairro_regiao'] = ''
            alertas.append(f"  ⚠️  [demandas #{rid}] bairro parecia IA → apagado")

        # ⓪ Alerta: sem contato (LID do WhatsApp — número real indisponível)
        if not (contato or '').strip():
            alertas.append(f"  📵 [demandas #{rid}] sem contato WhatsApp — grupo pode usar LID")

        # ③ Normalizar tipo
        tipo_novo = _normalizar_tipo(tipo or '', obs_limpo)
        if tipo_novo != (tipo or ''):
            fixes['tipo_buscado'] = tipo_novo

        # ⑥a Verificar/popular edificio
        motivo = _edificio_invalido(edificio_atual)
        if motivo:
            novo = _extrair_edificio_seguro(obs_limpo)
            if novo and not _edificio_invalido(novo):
                fixes['edificio'] = novo
                if VERBOSE:
                    print(f"    [demandas #{rid}] edificio: {edificio_atual!r} ({motivo}) → {novo!r}")
            else:
                fixes['edificio'] = None
        elif not edificio_atual:
            novo = _extrair_edificio_seguro(obs_limpo)
            if novo and not _edificio_invalido(novo):
                fixes['edificio'] = novo
                if VERBOSE:
                    print(f"    [demandas #{rid}] edificio: (vazio) → {novo!r}")

        # ⑥b Verificar/popular condominio
        motivo_c = _edificio_invalido(condominio_atual)
        if motivo_c:
            novo_c = _extrair_condominio_seguro(obs_limpo)
            if novo_c and not _edificio_invalido(novo_c):
                fixes['condominio'] = novo_c
                if VERBOSE:
                    print(f"    [demandas #{rid}] condominio: {condominio_atual!r} ({motivo_c}) → {novo_c!r}")
            else:
                fixes['condominio'] = None
        elif not condominio_atual:
            novo_c = _extrair_condominio_seguro(obs_limpo)
            if novo_c and not _edificio_invalido(novo_c):
                fixes['condominio'] = novo_c
                if VERBOSE:
                    print(f"    [demandas #{rid}] condominio: (vazio) → {novo_c!r}")

        # Deduplicação: se edificio e condominio ficaram iguais → limpar edificio
        e_final = fixes.get('edificio', edificio_atual)
        c_final = fixes.get('condominio', condominio_atual)
        if e_final and c_final and str(e_final).lower() == str(c_final).lower():
            fixes['edificio'] = None
            e_final = None
            if VERBOSE:
                print(f"    [demandas #{rid}] edificio dedup com condominio → limpo")

        # ⑦ Completar specs da demanda a partir do banco de condomínios
        #    Quando edificio ou condomínio é conhecido mas campos-chave estão vazios.
        #    Passa area_min para selecionar a planta correta em edifícios multi-planta.
        local_nome = e_final or c_final
        if local_nome and (not area_min or not bairro or not quartos):
            try:
                specs = pm.buscar_specs_condo(local_nome, area=area_min)
                if specs:
                    if not bairro and specs.get('bairro'):
                        fixes['bairro_regiao'] = specs['bairro']
                        if VERBOSE:
                            print(f"    [demandas #{rid}] bairro de '{local_nome}': {specs['bairro']!r}")
                    if not area_min and specs.get('area_min'):
                        fixes['area_min'] = specs['area_min']
                        if VERBOSE:
                            print(f"    [demandas #{rid}] area_min de '{local_nome}': {specs['area_min']}")
                    if not quartos and specs.get('quartos'):
                        fixes['quartos'] = specs['quartos']
                        if VERBOSE:
                            print(f"    [demandas #{rid}] quartos de '{local_nome}': {specs['quartos']}")
                    if not vagas and specs.get('vagas'):
                        fixes['vagas'] = specs['vagas']
                        if VERBOSE:
                            print(f"    [demandas #{rid}] vagas de '{local_nome}': {specs['vagas']}")
                    # ⑦b Se tipo_buscado é genérico ('Imóvel') e a planta tem tipo, corrigir
                    tipo_atual = fixes.get('tipo_buscado', tipo)
                    if (not tipo_atual or tipo_atual == 'Imóvel') and specs.get('tipo'):
                        fixes['tipo_buscado'] = specs['tipo']
                        if VERBOSE:
                            print(f"    [demandas #{rid}] tipo de '{local_nome}': {specs['tipo']!r}")
            except Exception as ex:
                if VERBOSE:
                    print(f"    [demandas #{rid}] ⚠️  buscar specs '{local_nome}': {ex}")

        if fixes:
            if VERBOSE:
                print(f"  [demandas #{rid}] fixes: {list(fixes.keys())}")
            if not DRY_RUN:
                set_clause = ', '.join(f"{k}=?" for k in fixes)
                cur.execute(f"UPDATE demandas SET {set_clause} WHERE id=?",
                            list(fixes.values()) + [rid])
            corrigidos += 1

    if not DRY_RUN:
        conn.commit()

    for a in alertas:
        print(a)
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
