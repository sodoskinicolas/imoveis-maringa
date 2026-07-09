#!/usr/bin/env python3
"""
atualizar_precos_diario.py — Orquestra a atualização diária do histórico de preços.

Ordem:
  1) (opcional) coleta nova do VivaReal -> alimenta imoveis + preco_historico
     (só roda se --scrape for passado; a coleta pesada fica na tarefa de scraping)
  2) reconstrói preco_historico_vertical (série por edifício)
  3) roda analise_precos (métricas por edifício/bairro + RESUMO + padrão + filtro direitos)
  4) escreve PROGRESS_precos.json com o resumo do dia

Rodar:  python3 atualizar_precos_diario.py
        python3 atualizar_precos_diario.py --scrape   # inclui coleta VivaReal
"""
import subprocess, sys, os, json, sqlite3
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "imoveis.db")

def run(cmd, timeout=1800):
    print(f"→ {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd, cwd=BASE, timeout=timeout,
                           capture_output=True, text=True)
        print((r.stdout or "").strip()[-500:])
        if r.returncode != 0:
            print("  ! stderr:", (r.stderr or "").strip()[-300:])
        return r.returncode == 0
    except Exception as e:
        print("  ! falhou:", e)
        return False

def main():
    scrape = "--scrape" in sys.argv
    steps = {}

    if scrape:
        # coleta best-effort; se falhar, segue com o que já está no banco
        steps["scrape"] = run([sys.executable, "scrape_vivareal.py", "--paginas", "40"], timeout=2400)

    steps["mapear_edificios"] = run([sys.executable, "mapear_edificios.py"], timeout=600)
    steps["historico_vertical"] = run([sys.executable, "gerar_historico_vertical.py"], timeout=600)
    steps["analise"] = run([sys.executable, "analise_precos.py"], timeout=600)

    # progresso
    con = sqlite3.connect(DB); cur = con.cursor()
    def one(q):
        try: return cur.execute(q).fetchone()[0]
        except Exception: return None
    prog = {
        "atualizado_em": datetime.now().isoformat(),
        "passos_ok": steps,
        "datas_no_historico": one("SELECT COUNT(DISTINCT data) FROM preco_historico"),
        "edificios_com_serie": one("SELECT COUNT(DISTINCT cadastro_es) FROM preco_historico_vertical"),
        "edificios_com_metricas": one("SELECT COUNT(*) FROM metricas_precos_vertical"),
        "bairros_com_metricas": one("SELECT COUNT(*) FROM metricas_bairro"),
        "suspeitos_direitos_filtrados": one("SELECT COALESCE(SUM(n_suspeitos_direitos),0) FROM metricas_precos_vertical"),
    }
    con.close()
    with open(os.path.join(BASE, "PROGRESS_precos.json"), "w") as f:
        json.dump(prog, f, ensure_ascii=False, indent=2)
    print("\nPROGRESS_precos.json:", json.dumps(prog, ensure_ascii=False))

if __name__ == "__main__":
    main()
