#!/bin/bash
# desinstalar_autostart.sh — Remove o início automático do bot

PLIST_DST="$HOME/Library/LaunchAgents/com.imoveis.baileys.plist"

echo "⏹  Parando e removendo serviço..."
launchctl unload "$PLIST_DST" 2>/dev/null || true
rm -f "$PLIST_DST"
echo "✅ Serviço removido. O bot não iniciará mais automaticamente."
echo "   Para iniciar manualmente: ./iniciar_baileys.sh"
