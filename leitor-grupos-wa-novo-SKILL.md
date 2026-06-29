---
name: leitor-grupos-wa
description: >
  Bot que processa mensagens dos grupos do WhatsApp (capturadas pelo bot Baileys em background),
  extrai dados de imóveis e atualiza Imoveis_Grupos.xlsx. Use quando o usuário disser
  "lê os grupos", "captura imóveis", "atualiza a planilha", "roda o bot", "processa as mensagens",
  "lê o WhatsApp", "verifica os grupos", "quantas mensagens tem na fila",
  ou qualquer variação de leitura/captura de imóveis dos grupos de corretores.
compatibility: Requer que o bot Baileys esteja rodando em background (iniciar_baileys.sh).
---

# Bot Leitor de Grupos WhatsApp → Planilha de Imóveis

Usuário: Nicolas Sodoski, corretor imobiliário em Maringá.
Objetivo: Processar mensagens capturadas pelo bot Baileys dos grupos de corretores e inserir
os imóveis na planilha `/Users/nicolassodoski/Claude/Projects/PW/Imoveis_Grupos.xlsx`.

> ℹ️ O bot Baileys captura mensagens 24h/dia em background sem usar o Chrome.
> Esta skill apenas processa as mensagens já capturadas na fila.

---

## Passo 0 — Verificar status do bot

```python
import os, json
from pathlib import Path

BASE = Path('/Users/nicolassodoski/Claude/Projects/PW')
FILA = BASE / 'mensagens_fila.json'
PID_FILE = BASE / 'baileys_bot/bot.pid'

# Verificar se bot está rodando
bot_ativo = False
if PID_FILE.exists():
    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, 0)  # sinal 0 = verifica se processo existe
        bot_ativo = True
    except:
        bot_ativo = False

print(f"Bot Baileys: {'✅ Rodando' if bot_ativo else '⚠️  Parado'}")

# Contar mensagens na fila
if FILA.exists():
    fila = json.loads(FILA.read_text())
    pendentes = [m for m in fila if not m.get('processado')]
    print(f"Mensagens na fila: {len(fila)} total, {len(pendentes)} pendentes")
else:
    print("Fila vazia — o bot ainda não capturou mensagens.")
```

Se o bot estiver parado, avisar o usuário para rodar:
```
bash /Users/nicolassodoski/Claude/Projects/PW/iniciar_baileys.sh
```

---

## Passo 1 — Verificar mensagens pendentes na fila

```bash
cd /Users/nicolassodoski/Claude/Projects/PW
python3 processar_mensagens.py --ver-fila
```

Isso mostra todas as mensagens capturadas ainda não processadas, com grupo, autor e texto.

---

## Passo 2 — Processar mensagens e atualizar planilha

```bash
cd /Users/nicolassodoski/Claude/Projects/PW
python3 processar_mensagens.py
```

O script:
1. Lê `mensagens_fila.json`
2. Extrai dados (tipo, bairro, área, quartos, suítes, vagas, preço) via regex
3. Deduplica por `corretor + bairro + preço`
4. Insere novas linhas em `Imoveis_Grupos.xlsx` com Status="Novo" e fundo amarelo
5. Marca mensagens como `processado: true` na fila

---

## Passo 2b — Revisar imóveis de imagens (opcional)

Mensagens com imagens mas sem texto ficam marcadas como "📸 Imagem recebida — verificar manualmente".
Para listá-las:

```python
import json
from pathlib import Path

fila = json.loads(Path('/Users/nicolassodoski/Claude/Projects/PW/mensagens_fila.json').read_text())
imgs = [m for m in fila if m.get('temImagem') and not m.get('processado')]
for m in imgs:
    print(f"[{m['grupo']}] {m['autor']}: {m.get('texto','(sem texto)')[:100]}")
print(f"\nTotal com imagem: {len(imgs)}")
```

Se houver imagens importantes, o usuário pode abrir o WhatsApp manualmente para ver e informar os dados.

---

## Passo 3 — Conferir resultado

```python
import pandas as pd
df = pd.read_excel(
    '/Users/nicolassodoski/Claude/Projects/PW/Imoveis_Grupos.xlsx',
    sheet_name='Imóveis'
)
novos = df[df['Status'] == 'Novo']
print(f"✅ {len(novos)} imóveis com status 'Novo' na planilha")
print(novos[['Grupo','Corretor','Tipo','Bairro','Quartos','Preço (R$)']].tail(10).to_string())
```

---

## Passo 4 — Relatório final

Reportar:
- ✅ Grupos monitorados pelo bot: X
- 📬 Mensagens processadas: X
- 🏠 Imóveis novos inseridos: X
- 🔁 Duplicatas ignoradas: X
- 📸 Imagens para revisão manual: X
- 📊 Planilha: `/Users/nicolassodoski/Claude/Projects/PW/Imoveis_Grupos.xlsx`

---

## Configuração inicial (apenas uma vez)

Se o bot ainda não foi instalado:

```bash
# 1. Instalar Node.js (se não tiver)
brew install node

# 2. Iniciar o bot
bash /Users/nicolassodoski/Claude/Projects/PW/iniciar_baileys.sh

# 3. Escanear o QR Code que aparece no terminal
tail -f /Users/nicolassodoski/Claude/Projects/PW/baileys_bot/baileys.log
```

---

## Configurar grupos monitorados

Para monitorar apenas grupos específicos (padrão: todos os grupos):

```python
import json
from pathlib import Path

config_file = Path('/Users/nicolassodoski/Claude/Projects/PW/baileys_bot/config.json')
config = {"grupos": ["Maringá Imóveis", "Corretores MGA", "AP Maringá"]}
config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2))
print("Grupos configurados:", config['grupos'])
```

Lista vazia `[]` = monitorar todos os grupos.

---

## Regras importantes

- **Nunca deletar dados** da planilha — apenas adicionar linhas novas
- **Deduplicação**: por `corretor + bairro + preço`
- **Bot reinicia sozinho** se cair (reconexão automática com backoff de 5s)
- **Sessão WhatsApp persistente**: após o QR inicial, o bot reconecta sem escanear novamente
- **Fila cresce infinita**: mensagens com `processado: true` ficam registradas para histórico
