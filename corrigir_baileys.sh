#!/bin/bash
# corrigir_baileys.sh — Recuperação completa do bot Baileys após corrupção de sessão.
# Causa tratada: duas instâncias rodando ao mesmo tempo (Bad MAC + código 440) e
# creds.json zerado. Para tudo, apaga a sessão corrompida (com backup), zera o log
# gigante e sobe UMA única instância via LaunchAgent, mostrando o QR pra re-parear.
#
# Uso:  bash ~/Claude/Projects/PW/corrigir_baileys.sh

PW="/Users/nicolassodoski/Claude/Projects/PW"
BOT="$PW/baileys_bot"
PLIST_SRC="$PW/com.imoveis.baileys.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.imoveis.baileys.plist"
STAMP="$(date +%Y%m%d_%H%M%S)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Recuperação do Bot Baileys — Imóveis Maringá"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "[1/5] Parando TODAS as instâncias..."
# Descarrega o LaunchAgent (impede o KeepAlive de ressuscitar o bot)
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl bootout "gui/$(id -u)/com.imoveis.baileys" 2>/dev/null || true
# Mata qualquer node do bot que tenha sobrado (script + launchd)
pkill -f "baileys_bot/bot.js" 2>/dev/null || true
pkill -f "node bot.js" 2>/dev/null || true
sleep 2
rm -f "$BOT/bot.pid" "$BOT/bot.lock"
echo "      OK — nenhum node bot.js deve estar rodando agora."

echo ""
echo "[2/5] Fazendo backup e limpando a sessão corrompida (auth/)..."
if [ -d "$BOT/auth" ]; then
  mv "$BOT/auth" "$BOT/auth.corrompida.$STAMP"
  echo "      Sessão antiga guardada em: auth.corrompida.$STAMP"
fi
mkdir -p "$BOT/auth"

echo ""
echo "[3/5] Arquivando o log de 90 MB..."
if [ -f "$BOT/baileys.log" ]; then
  gzip -c "$BOT/baileys.log" > "$BOT/baileys.log.$STAMP.gz" 2>/dev/null || true
  : > "$BOT/baileys.log"
  echo "      Log antigo compactado em: baileys.log.$STAMP.gz (e log zerado)"
fi

echo ""
echo "[4/5] Subindo UMA única instância via LaunchAgent..."
# Garante que o plist está instalado
if [ ! -f "$PLIST_DST" ] && [ -f "$PLIST_SRC" ]; then
  cp "$PLIST_SRC" "$PLIST_DST"
  echo "      LaunchAgent instalado em ~/Library/LaunchAgents/"
fi
if launchctl load "$PLIST_DST" 2>/dev/null; then
  echo "      Bot iniciado pelo launchd (KeepAlive ativo)."
else
  echo "      launchctl falhou — subindo direto com node como fallback."
  cd "$BOT" && nohup node bot.js >> baileys.log 2>&1 &
  echo $! > "$BOT/bot.pid"
fi

echo ""
echo "[5/5] Aguardando o QR Code aparecer no log..."
sleep 7
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ESCANEIE O QR ABAIXO com o WhatsApp do celular:"
echo "  Configurações → Aparelhos Vinculados → Vincular Aparelho"
echo ""
echo "  (Ctrl+C encerra só a visualização — o bot continua rodando)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
tail -f "$BOT/baileys.log"
