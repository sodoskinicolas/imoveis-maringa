#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
revisar_demandas.py — FALLBACK LLM (dormente) do modelo híbrido de demandas.

A ingestão automática (Baileys + processar_mensagens.py) usa SÓ regex — 100%
offline, custo zero. Quando o regex não consegue extrair nenhum alvo de busca
(preço/região/edifício/área/quartos), a demanda é gravada com status='Revisar'.

Este script pega essas demandas 'Revisar' e reprocessa o texto bruto (coluna
observacoes) com o Claude, preenchendo os campos que faltaram. NÃO roda sozinho
na ingestão — você chama quando quiser / quando a chave de API tiver créditos:

    python3 revisar_demandas.py --dry-run     # mostra o que faria, sem gravar
    python3 revisar_demandas.py               # aplica no banco
    python3 revisar_demandas.py --status Nova # reprocessa outro status
    python3 revisar_demandas.py --regenerar   # regenera o site ao final

Circuit-breaker: se a API responder "sem créditos", para na hora e avisa —
nenhuma demanda é perdida (continua 'Revisar' pra próxima tentativa).
"""
import argparse
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import db  # noqa: E402
import processar_mensagens as pm  # noqa: E402

MODELO = "claude-haiku-4-5-20251001"

PROMPT = """Você é especialista no mercado imobiliário de Maringá/PR. Abaixo está \
a mensagem BRUTA de um corretor num grupo de WhatsApp, que é uma DEMANDA (um \
corretor procurando imóvel para um cliente comprador).

Extraia os dados do que o cliente PROCURA. Retorne SOMENTE um JSON válido, sem \
texto fora dele:
{{
  "tipo_buscado": "Apartamento|Casa|Terreno|Sala Comercial|Imóvel",
  "bairro_regiao": "bairro(s)/região/zona(s)/avenida — se vários, separe por ' · '; senão null",
  "edificio": "nome(s) de edifício/condomínio citado(s), separados por ' · '; senão null",
  "area_min": numero_m2_ou_null,
  "quartos": numero_ou_null,
  "suites": numero_ou_null,
  "vagas": numero_ou_null,
  "orcamento_max": inteiro_em_reais_ou_null,
  "locacao": true_se_for_aluguel_senao_false,
  "requisitos": "preferências relevantes em texto curto (mobiliado, andar alto, sem MRV, planejados, etc.) ou null"
}}

Regras: orcamento_max é o TETO que o comprador aceita pagar (em reais, inteiro). \
Se disser "até 500 mil" → 500000. Se for aluguel, o valor pode ser baixo \
(centenas/poucos milhares). Não invente dados que não estão na mensagem.

Mensagem:
\"\"\"{texto}\"\"\""""


def _extrair_llm(client, texto):
    resp = client.messages.create(
        model=MODELO,
        max_tokens=600,
        messages=[{"role": "user", "content": PROMPT.format(texto=texto[:1500])}],
    )
    raw = resp.content[0].text
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    return json.loads(m.group())


def _num(v):
    try:
        if v in (None, "", "null"):
            return None
        return int(float(v))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="não grava, só mostra")
    ap.add_argument("--status", default="Revisar", help="status alvo (padrão: Revisar)")
    ap.add_argument("--regenerar", action="store_true", help="regenera o site ao final")
    ap.add_argument("--limite", type=int, default=0, help="máx. de demandas (0 = todas)")
    args = ap.parse_args()

    # 1) Primeiro vê se há trabalho — assim o caso comum (nada a revisar) não
    #    depende nem da chave nem do pacote anthropic instalado.
    db.init_db()
    with db.db_conn() as conn:
        conn.row_factory = __import__("sqlite3").Row
        rows = conn.execute(
            "SELECT * FROM demandas WHERE status = ? ORDER BY id", (args.status,)
        ).fetchall()

    if not rows:
        print(f"Nenhuma demanda com status='{args.status}'. Nada a revisar. ✅")
        return 0

    if args.limite:
        rows = rows[: args.limite]

    # 2) Só agora exige a chave e o SDK.
    api_key = pm._api_key()
    if not api_key:
        print(f"⚠️  {len(rows)} demanda(s) '{args.status}' aguardando, mas não há "
              f"ANTHROPIC_API_KEY (.env ou env). Recarregue a chave e rode de novo.")
        return 1
    try:
        import anthropic
    except ImportError:
        print("⚠️  Pacote 'anthropic' não instalado. Rode: pip3 install anthropic")
        return 1
    client = anthropic.Anthropic(api_key=api_key)

    print(f"🔁 {len(rows)} demanda(s) '{args.status}' para reprocessar com LLM"
          f"{' [DRY-RUN]' if args.dry_run else ''}\n")

    atualizadas = 0
    for r in rows:
        texto = r["observacoes"] or ""
        if not texto.strip():
            print(f"  ⏭️  #{r['id']} sem texto — pulando")
            continue
        try:
            dados = _extrair_llm(client, texto)
        except Exception as e:
            msg = str(e).lower()
            if "credit" in msg or "billing" in msg or "quota" in msg or "insufficient" in msg:
                print(f"\n🛑 API sem créditos — parando. As demandas seguem 'Revisar' "
                      f"pra próxima tentativa.\n   ({e})")
                break
            print(f"  ⚠️  #{r['id']} falhou: {e}")
            continue
        if not dados:
            print(f"  ⚠️  #{r['id']} — LLM não devolveu JSON")
            continue

        # Só preenche o que estava vazio (mensagem/regex têm prioridade).
        novos = {
            "tipo_buscado":  r["tipo_buscado"] or dados.get("tipo_buscado") or "Imóvel",
            "bairro_regiao": r["bairro_regiao"] or (dados.get("bairro_regiao") or ""),
            "edificio":      r["edificio"] or (dados.get("edificio") or None),
            "area_min":      r["area_min"] if r["area_min"] is not None else _num(dados.get("area_min")),
            "quartos":       r["quartos"] if r["quartos"] is not None else _num(dados.get("quartos")),
            "suites":        r["suites"] if r["suites"] is not None else _num(dados.get("suites")),
            "vagas":         r["vagas"] if r["vagas"] is not None else _num(dados.get("vagas")),
            "orcamento_max": r["orcamento_max"] if r["orcamento_max"] is not None else _num(dados.get("orcamento_max")),
        }
        req = dados.get("requisitos")
        obs = r["observacoes"] or ""
        if req and req not in (None, "null") and str(req) not in obs:
            obs = f"{obs}\n[requisitos] {req}".strip()

        tem_alvo = any([novos["orcamento_max"], novos["bairro_regiao"],
                        novos["edificio"], novos["area_min"], novos["quartos"]])
        novo_status = "Nova" if tem_alvo else "Revisar"

        print(f"  ✅ #{r['id']}: {novos['tipo_buscado']} | "
              f"{novos['bairro_regiao'] or novos['edificio'] or '?'} | "
              f"R${novos['orcamento_max']} | q{novos['quartos']} s{novos['suites']} "
              f"→ {novo_status}")

        if not args.dry_run:
            with db.db_conn() as conn:
                conn.execute(
                    "UPDATE demandas SET tipo_buscado=?, bairro_regiao=?, edificio=?, "
                    "area_min=?, quartos=?, suites=?, vagas=?, orcamento_max=?, "
                    "observacoes=?, status=? WHERE id=?",
                    (novos["tipo_buscado"], novos["bairro_regiao"], novos["edificio"],
                     novos["area_min"], novos["quartos"], novos["suites"], novos["vagas"],
                     novos["orcamento_max"], obs, novo_status, r["id"]),
                )
                conn.commit()
            atualizadas += 1

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}✅ {atualizadas} demanda(s) atualizada(s)")

    if args.regenerar and not args.dry_run and atualizadas:
        print("🔧 Regenerando site...")
        import subprocess
        subprocess.run([sys.executable, str(BASE_DIR / "gerar_site.py")], cwd=str(BASE_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
