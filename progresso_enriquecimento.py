#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mini-painel flutuante do progresso de enriquecimento das plantas dos edifícios
verticais (tabela verticais_geo do imoveis.db). Fica sempre no topo e atualiza
sozinho a cada 20s.

Agora mostra a porcentagem de edifícios em cada faixa de confiança da planta:
  ✅ Completos (alta) · 🟡 Média · 🟠 Baixa · 🔴 Revisar

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

# Faixas exibidas: rótulo, chave interna, cor
FAIXAS = [
    ("✅ Completos", "alta",    "#4caf50"),
    ("🟡 Média",     "media",   "#e6b800"),
    ("🟠 Baixa",     "baixa",   "#e6832b"),
    ("🔴 Revisar",   "revisar", "#e57373"),
]


def ler():
    """Retorna (total_proc, {alta,media,baixa,revisar}) ou (None, msg_erro)."""
    try:
        conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
        cur = conn.cursor()
        total_proc = cur.execute(
            f"SELECT COUNT(*) FROM verticais_geo WHERE classe='vertical' AND {FILTRO_COMERCIAL}"
        ).fetchone()[0]
        def cont(cond):
            return cur.execute(
                f"SELECT COUNT(*) FROM verticais_geo WHERE classe='vertical' "
                f"AND {FILTRO_COMERCIAL} AND {cond}"
            ).fetchone()[0]
        alta  = cont("plantas_confianca='alta'")
        media = cont("plantas_confianca='media'")
        baixa = cont("plantas_confianca='baixa'")
        # Revisar = tudo que ainda não virou uma planta confiável (revisar,
        # revisar_final, nulos e demais casos pendentes).
        revisar = total_proc - alta - media - baixa
        conn.close()
        return total_proc, {"alta": alta, "media": media, "baixa": baixa, "revisar": revisar}
    except Exception as e:
        return None, str(e)


def _pct(n, tot):
    return round(n / tot * 100) if tot else 0


# Plano B: se não houver tkinter (janela gráfica), mostra no Terminal e sai.
try:
    import tkinter as tk
except Exception:
    print("🏢  Enriquecimento de edifícios — progresso por faixa (Ctrl+C para sair)\n")
    while True:
        total_proc, dados = ler()
        if total_proc is None:
            print(f"\r  erro ao ler banco: {dados}", end="", flush=True)
            time.sleep(20); continue
        partes = "  ·  ".join(
            f"{rot} {_pct(dados[key], total_proc)}% ({dados[key]})"
            for rot, key, _ in FAIXAS
        )
        print(f"\r  {partes}   ", end="", flush=True)
        time.sleep(20)
    raise SystemExit

root = tk.Tk()
root.title("Enriquecimento")
root.attributes("-topmost", True)
root.resizable(False, False)
root.configure(bg="#1e1e1e")

# Posiciona no canto superior direito
W, H = 340, 210
root.update_idletasks()
sw = root.winfo_screenwidth()
root.geometry(f"{W}x{H}+{sw - W - 24}+48")

titulo = tk.Label(root, text="🏢  Enriquecimento de edifícios",
                  bg="#1e1e1e", fg="#eaeaea", font=("Helvetica", 13, "bold"))
titulo.pack(pady=(12, 2))

subtitulo = tk.Label(root, text="—", bg="#1e1e1e", fg="#9a9a9a",
                     font=("Helvetica", 10))
subtitulo.pack(pady=(0, 6))

BARRA_W = 300
linhas = {}  # key -> (label, canvas, fill_rect)
corpo = tk.Frame(root, bg="#1e1e1e")
corpo.pack()
for rot, key, cor in FAIXAS:
    lbl = tk.Label(corpo, text=f"{rot}: —", bg="#1e1e1e", fg=cor,
                   font=("Helvetica", 11, "bold"), anchor="w", width=30)
    lbl.pack(anchor="w")
    cv = tk.Canvas(corpo, width=BARRA_W, height=8, bg="#333", highlightthickness=0)
    cv.pack(pady=(0, 4))
    fill = cv.create_rectangle(0, 0, 0, 8, fill=cor, width=0)
    linhas[key] = (lbl, cv, fill)


def atualizar():
    total_proc, dados = ler()
    if total_proc is None:  # erro
        subtitulo.config(text=str(dados)[:44], fg="#e57373")
        root.after(INTERVALO_MS, atualizar)
        return

    subtitulo.config(text=f"{total_proc} edifícios residenciais mapeados", fg="#9a9a9a")
    for rot, key, _cor in FAIXAS:
        n = dados[key]
        pct = _pct(n, total_proc)
        lbl, cv, fill = linhas[key]
        lbl.config(text=f"{rot}: {pct}%  ({n})")
        cv.coords(fill, 0, 0, int(BARRA_W * pct / 100), 8)

    root.after(INTERVALO_MS, atualizar)


atualizar()
root.mainloop()
