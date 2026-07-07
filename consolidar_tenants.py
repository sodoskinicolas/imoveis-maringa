#!/usr/bin/env python3
"""
Consolidação Sub100 — passo único, rode DEPOIS da primeira raspagem nova.

Contexto: os 5 sites-tenant (Silvio Iwata, Massaru, Haraki, Bellakaza, Casa do
Corretor) eram raspados direto e NÃO traziam o nome do edifício. Agora o Portal
Sub100 (fonte 'sub100.com.br') ingere os mesmos imóveis JÁ COM edifício
(condo.name). Para não ficar com o imóvel duplicado (uma vez pelo tenant antigo,
outra pelo portal), este script marca os registros antigos dos tenants como
'Removido'. Não apaga nada — só muda o status, então é reversível e o histórico
de preços (preco_historico) continua intacto.

Segurança: só marca um registro do tenant como 'Removido' se o Portal já tiver
o MESMO imóvel (mesma ref) na base. Assim, se por algum motivo o portal ainda
não cobriu aquele imóvel, ele NÃO some da base.

Uso:
    cd ~/Claude/Projects/PW
    python3 raspar_imoveis.py          # 1) roda a raspagem (portal entra c/ edifício)
    python3 consolidar_tenants.py      # 2) marca os antigos dos tenants como Removido
    python3 consolidar_tenants.py --dry # (opcional) só mostra o que faria
"""
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).parent / "imoveis.db"

# domínios usados como `fonte` no scrape direto antigo dos 5 tenants
TENANTS = [
    "silvioiwata.com.br",
    "massaruimoveis.com.br",
    "harakiimoveis.com.br",
    "bellakaza.com.br",
    "casadocorretormga.com.br",
]
PORTAL = "sub100.com.br"


def main():
    dry = "--dry" in sys.argv
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row

    # refs que o portal já tem (pra só remover duplicata comprovada)
    refs_portal = {str(r["ref_externa"])
                   for r in con.execute(
                       "SELECT ref_externa FROM imoveis WHERE fonte=?", (PORTAL,))}
    print(f"Portal '{PORTAL}': {len(refs_portal)} imóveis na base.")
    if not refs_portal:
        print("⚠  O portal ainda não tem imóveis na base. Rode a raspagem "
              "(python3 raspar_imoveis.py) ANTES de consolidar. Nada foi alterado.")
        return

    total_marcados = 0
    for fonte in TENANTS:
        rows = con.execute(
            "SELECT id, ref_externa FROM imoveis "
            "WHERE fonte=? AND COALESCE(status,'') <> 'Removido'", (fonte,)).fetchall()
        # marca só os que o portal já cobre (mesma ref) — resto fica intacto
        alvo = [r["id"] for r in rows if str(r["ref_externa"]) in refs_portal]
        orfaos = len(rows) - len(alvo)
        print(f"  {fonte}: {len(rows)} ativos | {len(alvo)} já no portal → Removido"
              + (f" | {orfaos} sem par no portal (mantidos)" if orfaos else ""))
        if alvo and not dry:
            con.executemany("UPDATE imoveis SET status='Removido' WHERE id=?",
                            [(i,) for i in alvo])
            total_marcados += len(alvo)

    if dry:
        print("\n(dry-run) Nada foi alterado.")
    else:
        con.commit()
        print(f"\n✓ {total_marcados} registro(s) antigo(s) de tenant marcados como "
              f"'Removido' (duplicatas do portal). Reversível pelo status.")
    con.close()


if __name__ == "__main__":
    main()
