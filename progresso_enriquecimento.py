#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mini-painel flutuante do progresso de enriquecimento das plantas dos edifícios
verticais (tabela verticais_geo do imoveis.db). Fica sempre no topo, atualiza
sozinho a cada 20s e se fecha quando não sobrar nenhum edifício pra processar.

Rode: python3 progresso_enriquecimento.py   (ou dê 2 cliques no .command)
"""
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).resolve().parent / "imoveis.db"
INTERVALO_MS = 20_000  # 20s

# Mesmos filtros da tarefa agendada (só verticais residenciais)
FILTRO_COMERCIAL = (
    "nome_cadastral IS NOT NULL "
    "AND nome_cadastral NOT LIKE '%EMPRESARIAL%' AND nome_cadastral NOT LIKE '%SHOPPING%' "
    "AND nome_cadastral NOT LIKE '%COMERCIAL%' AND nome_cadastral NOT LIKE '%CENTER%' "
    "AND nome_cadastral NOT LIKE '%GALERIA%' AND nome_cadastral NOT LIKE '%CLÍNICA%' "
    "AND nome_cadastral NOT LIKE '%MÉDICO%' AND nome_cadastral NOT LIKE '% SALA%' "
    "AND nome_cadastral NOT LIKE '%CONJ%' AND nome_cadastral NOT LIKE '%SUBDIVISAO%'"
)


def ler():
    """Retorna (com_planta, total_geral, processados, total_processavel, faltam)."""
    try:
        conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
        cur = conn.cursor()
        total_geral = cur.execute("SELECT COUNT(*) FROM verticais_geo").fetchone()[0]
        com_planta = cur.execute(
            "SELECT COUNT(*) FROM verticais_geo WHERE plantas IS NOT NULL AND plantas != '[]'"
        ).fetchone()[0]
        total_proc = cur.execute(
            f"SELECT COUNT(*) FROM verticais_geo WHERE classe='vertical' AND {FILTRO_COMERCIAL}"
        ).fetchone()[0]
        faltam = cur.execute(
            f"SELECT COUNT(*) FROM verticais_geo WHERE classe='vertical' "
            f"AND (plantas IS NULL OR plantas_confianca='revisar') AND {FILTRO_COMERCIAL}"
        ).fetchone()[0]
        conn.close()
        processados = total_proc - faltam
        return com_planta, total_geral, processados, total_proc, faltam
    except Exception as e:
        return None, None, None, None, str(e)


# Plano B: se não houver tkinter (janela gráfica), mostra no Terminal e sai.
try:
    import tkinter as tk
except Exception:
    print("🏢  Enriquecimento de edifícios — progresso ao vivo (Ctrl+C para sair)\n")
    while True:
        com_planta, total_geral, processados, total_proc, faltam = ler()
        if com_planta is None:
            print(f"\r  erro ao ler banco: {faltam}", end="", flush=True)
            time.sleep(20); continue
        pct = round((processados / total_proc) * 100) if total_proc else 100
        if faltam <= 0:
            print(f"\r  ✅ {com_planta}/{total_geral} — Concluído!            ")
            break
        print(f"\r  🏢 {com_planta}/{total_geral}  ·  faltam {faltam}  ·  {pct}%   ",
              end="", flush=True)
        time.sleep(20)
    raise SystemExit

root = tk.Tk()
root.title("Enriquecimento")
root.attributes("-topmost", True)
root.resizable(False, False)
root.configure(bg="#1e1e1e")

# Posiciona no canto superior direito
W, H = 320, 130
root.update_idletasks()
sw = root.winfo_screenwidth()
root.geometry(f"{W}x{H}+{sw - W - 24}+48")

titulo = tk.Label(root, text="🏢  Enriquecimento de edifícios",
                  bg="#1e1e1e", fg="#eaeaea", font=("Helvetica", 13, "bold"))
titulo.pack(pady=(12, 2))

numero = tk.Label(root, text="—", bg="#1e1e1e", fg="#4caf50",
                  font=("Helvetica", 20, "bold"))
numero.pack()

# Barra de progresso (canvas simples, sem depender de ttk)
BARRA_W = 280
cv = tk.Canvas(root, width=BARRA_W, height=10, bg="#333", highlightthickness=0)
cv.pack(pady=(6, 2))
fill = cv.create_rectangle(0, 0, 0, 10, fill="#4caf50", width=0)

status = tk.Label(root, text="", bg="#1e1e1e", fg="#9a9a9a",
                  font=("Helvetica", 11))
status.pack()


def atualizar():
    com_planta, total_geral, processados, total_proc, faltam = ler()
    if com_planta is None:  # erro
        numero.config(text="erro", fg="#e57373")
        status.config(text=str(faltam)[:38])
        root.after(INTERVALO_MS, atualizar)
        return

    numero.config(text=f"{com_planta}/{total_geral}")
    pct = (processados / total_proc) if total_proc else 1
    cv.coords(fill, 0, 0, int(BARRA_W * pct), 10)

    if faltam <= 0:
        numero.config(text=f"✅ {com_planta}/{total_geral}")
        status.config(text="Concluído! Fechando…", fg="#4caf50")
        cv.coords(fill, 0, 0, BARRA_W, 10)
        root.after(6000, root.destroy)  # fecha sozinho após 6s
        return

    status.config(text=f"faltam {faltam} edifícios  ·  {round(pct*100)}% dos residenciais")
    root.after(INTERVALO_MS, atualizar)


atualizar()
root.mainloop()
