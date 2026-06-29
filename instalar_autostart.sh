#!/bin/bash
# instalar_autostart.sh — Instala o bot para iniciar automaticamente no login

PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/com.imoveis.baileys.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.imoveis.baileys.plist"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Bot WhatsApp — Instalar Início Automático"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Parar versão anterior se existir
if launchctl list | grep -q "com.imoveis.baileys" 2>/dev/null; then
    echo "⏹  Parando serviço anterior..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

# Copiar plist
mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"
echo "✅ Arquivo instalado em: $PLIST_DST"

# Carregar e iniciar
launchctl load "$PLIST_DST"
echo "✅ Serviço registrado e iniciado"

echo ""
echo "O bot agora inicia automaticamente ao fazer login no Mac."
echo ""
echo "Comandos úteis:"
echo "  Ver log:      tail -f ~/Claude/Projects/PW/baileys_bot/baileys.log"
echo "  Parar:        launchctl unload ~/Library/LaunchAgents/com.imoveis.baileys.plist"
echo "  Reiniciar:    launchctl kickstart -k gui/\$(id -u)/com.imoveis.baileys"
echo "  Desinstalar:  bash desinstalar_autostart.sh"
echo ""
