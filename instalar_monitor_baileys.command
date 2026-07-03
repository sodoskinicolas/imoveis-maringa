#!/bin/bash
# Instala o monitor do Baileys (pop-up se >2h sem mensagens). Duplo clique para rodar.
cd "$(dirname "$0")"
chmod +x monitor_baileys.sh
cp com.imoveis.monitor-baileys.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.imoveis.monitor-baileys.plist 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.imoveis.monitor-baileys.plist
echo ""
echo "✅ Monitor Baileys instalado — verifica a cada 15 minutos."
echo "   Pop-up aparece se o bot ficar mais de 2h sem captar mensagens."
echo ""
echo "   Teste agora: ./monitor_baileys.sh --test"
echo ""
read -p "Pressione Enter para fechar..."
