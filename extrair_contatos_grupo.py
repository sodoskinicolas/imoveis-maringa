"""
PASSO 2 — Extrai participantes de um grupo do WhatsApp e salva em Excel/CSV
Requisito: Evolution API rodando em http://localhost:8080
"""

import requests
import pandas as pd
import json
import re

# ─── CONFIGURAÇÕES — edite aqui ───────────────────────────────────────────────
API_URL      = "http://localhost:8080"
API_KEY      = "minha-chave-secreta-123"   # mesma chave do docker-compose.yml
INSTANCE     = "corretor-maringa"           # nome da instância que você criou
ARQUIVO_SAIDA = "contatos_corretores.xlsx"  # ou troque por "contatos_corretores.csv"
# ──────────────────────────────────────────────────────────────────────────────

headers = {
    "apikey": API_KEY,
    "Content-Type": "application/json"
}


def listar_grupos():
    """Lista todos os grupos disponíveis na instância."""
    url = f"{API_URL}/group/fetchAllGroups/{INSTANCE}?getParticipants=false"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    grupos = resp.json()
    return grupos


def escolher_grupo(grupos):
    """Mostra os grupos e pede para o usuário escolher um."""
    print("\n=== GRUPOS DISPONÍVEIS ===")
    for i, g in enumerate(grupos):
        nome = g.get("subject", "Sem nome")
        gid  = g.get("id", "")
        print(f"[{i}] {nome}  ({gid})")

    print()
    idx = int(input("Digite o número do grupo que deseja usar: "))
    return grupos[idx]


def obter_participantes(group_id):
    """Busca todos os participantes do grupo."""
    url = f"{API_URL}/group/participants/{INSTANCE}?groupJid={group_id}"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data.get("participants", [])


def extrair_nome(contato):
    """Tenta obter o nome do contato. Fallback para número."""
    nome = contato.get("name") or contato.get("pushName") or ""
    return nome.strip()


def primeiro_nome(nome_completo):
    """Retorna só o primeiro nome, capitalizado."""
    if not nome_completo:
        return ""
    return nome_completo.strip().split()[0].capitalize()


def limpar_numero(jid):
    """Extrai o número puro do JID do WhatsApp (ex: 5544999991234@s.whatsapp.net → 5544999991234)."""
    return re.sub(r"@.*", "", jid)


def main():
    print("Conectando à Evolution API...")

    # 1. Listar grupos
    try:
        grupos = listar_grupos()
    except Exception as e:
        print(f"\nErro ao conectar: {e}")
        print("Verifique se a Evolution API está rodando e o WhatsApp conectado.")
        return

    if not grupos:
        print("Nenhum grupo encontrado. Verifique se o WhatsApp está conectado.")
        return

    # 2. Escolher grupo
    grupo = escolher_grupo(grupos)
    group_id = grupo["id"]
    group_nome = grupo.get("subject", group_id)
    print(f"\nBuscando participantes de: {group_nome} ...")

    # 3. Obter participantes
    participantes = obter_participantes(group_id)
    print(f"Total encontrado: {len(participantes)} participantes")

    # 4. Montar DataFrame
    registros = []
    for p in participantes:
        jid    = p.get("id", "")
        numero = limpar_numero(jid)

        # Pular números de grupo e status
        if "@g.us" in jid or "status" in jid:
            continue

        nome   = extrair_nome(p)
        pnome  = primeiro_nome(nome)

        registros.append({
            "Número":        numero,
            "Nome Completo": nome,
            "Primeiro Nome": pnome,
            "JID":           jid,
            "Admin":         "Sim" if p.get("admin") else "Não",
            "Mensagem Enviada": "Não",
            "Resposta":        ""
        })

    df = pd.DataFrame(registros)
    df = df.drop_duplicates(subset="Número")

    print(f"Contatos únicos: {len(df)}")

    # 5. Salvar
    if ARQUIVO_SAIDA.endswith(".csv"):
        df.to_csv(ARQUIVO_SAIDA, index=False, encoding="utf-8-sig")
    else:
        df.to_excel(ARQUIVO_SAIDA, index=False)

    print(f"\nSalvo em: {ARQUIVO_SAIDA}")
    print(df[["Número", "Nome Completo", "Primeiro Nome", "Admin"]].to_string(index=False))


if __name__ == "__main__":
    main()
