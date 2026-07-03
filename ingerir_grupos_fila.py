#!/usr/bin/env python3
"""
ingerir_grupos_fila.py
Ponte de ingestão: recebe mensagens BRUTAS lidas dos grupos do WhatsApp Web
(recuperação de histórico ou releitura) e as injeta na `mensagens_fila.json`
no MESMO formato que o bot Baileys (bot.js) grava.

Assim o `processar_mensagens.py` faz TODO o trabalho de verificação — validação
de bairro, extração/match de edifício e condomínio, semântica quartos/suítes,
classificação venda-vs-demanda, agrupamento e deduplicação por fingerprint —
antes de gravar no `imoveis.db`. NÃO reimplementa extração aqui (era esse o
problema do bot_grupos_wa.py, que inseria dado cru pulando as verificações).

Entrada: arquivo JSON com uma lista de objetos:
  [
    {"grupo":"BUSCA DE IMÓVEIS 🏡", "autor":"Alison Telles",
     "contato":"554499981418", "texto":"...", "timestamp":1782823628},
    ...
  ]
Campos: grupo (obrigatório), texto (obrigatório), autor, contato, timestamp.
Se `timestamp` faltar, usa o momento atual.

Uso:
  python3 ingerir_grupos_fila.py --arquivo msgs_recuperadas.json            # só injeta na fila
  python3 ingerir_grupos_fila.py --arquivo msgs_recuperadas.json --processar # injeta e processa
  python3 ingerir_grupos_fila.py --arquivo msgs.json --fila /tmp/fila_teste.json  # fila alternativa (teste)
"""
import sys, json, argparse, hashlib, subprocess, re
from datetime import datetime
from pathlib import Path

BASE_DIR  = Path(__file__).parent
FILA_PADRAO = BASE_DIR / "mensagens_fila.json"

# Mesmo prefiltro do bot.js (PALAVRAS_IMOVEL) — descarta ruído antes de gravar.
PALAVRAS_IMOVEL = re.compile(
    r"vend[ao]|alug[ao]|apartamento|apto|casa\b|terreno|sala comercial|loja|m[²2]\b|"
    r"quarto|dormit|suíte|suite|vaga|garagem|\br\$|condomín|bairro|imóvel|imovel|"
    r"\d+\s*m\s*[²2]|cliente\s+(?:procura|busca|quer|precisa|aprovad)|procuro\b|busco\b|"
    r"preciso\s+de\s+(?:apto|apartamento|casa)|financiamento\s+aprovado",
    re.IGNORECASE,
)

def pode_ser_imovel(texto: str) -> bool:
    return bool(texto and PALAVRAS_IMOVEL.search(texto))

def gerar_msgid(grupo: str, autor: str, texto: str, ts) -> str:
    """ID estável e determinístico — reprocessar o mesmo histórico não duplica."""
    base = f"{grupo}|{autor}|{ts}|{texto}".encode("utf-8")
    return "REC" + hashlib.sha1(base).hexdigest()[:29].upper()

def carregar_fila(fila_file: Path):
    if fila_file.exists():
        try:
            return json.loads(fila_file.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def main():
    ap = argparse.ArgumentParser(description="Injeta mensagens brutas de grupos na fila do pipeline")
    ap.add_argument("--arquivo", required=True, help="JSON com lista de mensagens brutas")
    ap.add_argument("--fila", default=str(FILA_PADRAO), help="Caminho da mensagens_fila.json (default: a real)")
    ap.add_argument("--processar", action="store_true", help="Roda processar_mensagens.py ao final")
    ap.add_argument("--dry-run", action="store_true", help="Mostra o que faria sem gravar")
    args = ap.parse_args()

    msgs = json.loads(Path(args.arquivo).read_text(encoding="utf-8"))
    if isinstance(msgs, dict):
        msgs = [msgs]

    fila_file = Path(args.fila)
    fila = carregar_fila(fila_file)
    ids_existentes = {m.get("msgId") for m in fila if m.get("msgId")}

    novas = 0
    puladas_dup = 0
    puladas_filtro = 0
    for m in msgs:
        texto = (m.get("texto") or "").strip()
        grupo = (m.get("grupo") or "").strip()
        autor = (m.get("autor") or "Desconhecido").strip()
        if not grupo or not texto:
            continue
        if not pode_ser_imovel(texto):
            puladas_filtro += 1
            continue

        ts = m.get("timestamp")
        try:
            ts = int(ts)
        except (TypeError, ValueError):
            ts = int(datetime.now().timestamp())

        msgid = m.get("msgId") or gerar_msgid(grupo, autor, texto, ts)
        if msgid in ids_existentes:
            puladas_dup += 1
            continue

        contato = str(m.get("contato") or "").replace(".", "").replace(" ", "")
        entrada = {
            "msgId": msgid,
            "grupo": grupo,
            "autor": autor,
            "contato": contato,
            "_lidJid": m.get("_lidJid"),
            "texto": texto,
            "temImagem": False,
            "imagemPath": None,
            "timestamp": ts,
            "data": datetime.fromtimestamp(ts).strftime("%d/%m/%Y, %H:%M:%S"),
            "processado": False,
            "_origem": "recuperacao_historico",
        }
        fila.append(entrada)
        ids_existentes.add(msgid)
        novas += 1

    print(f"📥 Recebidas: {len(msgs)} | ✅ novas p/ fila: {novas} | "
          f"⏭️ duplicatas: {puladas_dup} | 🚫 fora do filtro imóvel: {puladas_filtro}")

    if args.dry_run:
        print("(dry-run — fila NÃO gravada)")
        return

    fila_file.write_text(json.dumps(fila, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"💾 Fila atualizada: {fila_file}  (total agora: {len(fila)})")

    if args.processar:
        print("\n▶️  Rodando processar_mensagens.py (todas as verificações)...\n")
        proc_script = BASE_DIR / "processar_mensagens.py"
        subprocess.run([sys.executable, str(proc_script)], check=False)

if __name__ == "__main__":
    main()
