#!/bin/bash
# instalar_autostart.command — Duplo clique para instalar início automático do bot

PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/com.imoveis.baileys.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.imoveis.baileys.plist"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Bot WhatsApp — Instalar Início Automático"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Parar versão anterior se existir
if launchctl list 2>/dev/null | grep -q "com.imoveis.baileys"; then
    echo "⏹  Parando serviço anterior..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    sleep 1
fi

# Garantir que o node_modules está instalado
BOT_DIR="$(cd "$(dirname "$0")" && pwd)/baileys_bot"
if [ ! -d "$BOT_DIR/node_modules" ]; then
    echo "📦 Instalando dependências do bot..."
    cd "$BOT_DIR" && npm install
fi

# Copiar plist para LaunchAgents
mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"
echo "✅ Plist instalado"

# Carregar serviço
launchctl load "$PLIST_DST"
sleep 2

# Verificar se está rodando
if launchctl list 2>/dev/null | grep -q "com.imoveis.baileys"; then
    echo "✅ Bot iniciado e configurado para iniciar automaticamente no login!"
else
    echo "⚠️  Serviço registrado. Será iniciado no próximo login."
fi

echo ""
echo "📋 Para ver o log do bot:"
echo "   tail -f '$BOT_DIR/baileys.log'"
echo ""
echo "Esta janela pode ser fechada."
sleep 3
