"""
PASSO 3 — Envia mensagem personalizada para cada corretor da planilha
Lê o arquivo contatos_corretores.xlsx e envia via Evolution API
com intervalo aleatório para evitar bloqueio do WhatsApp.
"""

import requests
import pandas as pd
import time
import random
import os
from datetime import datetime

# ─── CONFIGURAÇÕES — edite aqui ───────────────────────────────────────────────
API_URL        = "http://localhost:8080"
API_KEY        = "minha-chave-secreta-123"   # mesma chave do docker-compose.yml
INSTANCE       = "corretor-maringa"
ARQUIVO        = "contatos_corretores.xlsx"  # planilha gerada no passo 2

# Intervalo entre mensagens (segundos) — aleatório para parecer humano
DELAY_MIN      = 8    # mínimo de segundos entre mensagens
DELAY_MAX      = 20   # máximo de segundos entre mensagens

# Mensagem — use {primeiro_nome} onde quiser o nome da pessoa
MENSAGEM = """Opa! Tudo bem {primeiro_nome}? 😊

Vi que você trabalha com corretagem aqui em Maringá, me conte — tem mais grupos de corretores como esse aqui em Maringá?

Estou mapeando o mercado da região e seria ótimo trocar uma ideia contigo!"""
# ──────────────────────────────────────────────────────────────────────────────

headers = {
    "apikey": API_KEY,
    "Content-Type": "application/json"
}


def enviar_mensagem(numero, texto):
    """Envia uma mensagem de texto para um número via Evolution API."""
    url = f"{API_URL}/message/sendText/{INSTANCE}"
    payload = {
        "number": numero,
        "text": texto
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def main():
    # 1. Carregar planilha
    if not os.path.exists(ARQUIVO):
        print(f"Arquivo '{ARQUIVO}' não encontrado. Execute primeiro o extrair_contatos_grupo.py")
        return

    df = pd.read_excel(ARQUIVO) if ARQUIVO.endswith(".xlsx") else pd.read_csv(ARQUIVO)

    # Filtrar apenas quem ainda não recebeu mensagem
    pendentes = df[df["Mensagem Enviada"] != "Sim"].copy()
    total = len(pendentes)

    print(f"Total de contatos na planilha: {len(df)}")
    print(f"Pendentes para envio: {total}")

    if total == 0:
        print("Todas as mensagens já foram enviadas!")
        return

    confirma = input(f"\nEnviar mensagem para {total} corretores? (s/n): ")
    if confirma.lower() != "s":
        print("Cancelado.")
        return

    print("\nIniciando envios...\n")

    enviados = 0
    erros    = 0

    for idx, row in pendentes.iterrows():
        numero      = str(row["Número"]).strip()
        pnome       = str(row["Primeiro Nome"]).strip() if row["Primeiro Nome"] else "Corretor"
        nome_completo = str(row["Nome Completo"]).strip()

        # Monta a mensagem personalizada
        texto = MENSAGEM.format(primeiro_nome=pnome)

        hora = datetime.now().strftime("%H:%M:%S")
        print(f"[{hora}] Enviando para {nome_completo} ({numero})...", end=" ")

        try:
            enviar_mensagem(numero, texto)
            df.at[idx, "Mensagem Enviada"] = "Sim"
            df.at[idx, "Data Envio"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            enviados += 1
            print("✓")
        except Exception as e:
            df.at[idx, "Mensagem Enviada"] = "Erro"
            df.at[idx, "Resposta"] = str(e)
            erros += 1
            print(f"✗ Erro: {e}")

        # Salva progresso após cada envio
        if ARQUIVO.endswith(".xlsx"):
            df.to_excel(ARQUIVO, index=False)
        else:
            df.to_csv(ARQUIVO, index=False, encoding="utf-8-sig")

        # Aguarda intervalo aleatório (exceto após o último)
        if enviados + erros < total:
            espera = random.randint(DELAY_MIN, DELAY_MAX)
            print(f"    Aguardando {espera}s antes do próximo envio...")
            time.sleep(espera)

    print(f"\n=== RESUMO ===")
    print(f"Enviados com sucesso: {enviados}")
    print(f"Erros:               {erros}")
    print(f"Planilha atualizada: {ARQUIVO}")


if __name__ == "__main__":
    main()
