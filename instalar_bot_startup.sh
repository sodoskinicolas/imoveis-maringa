#!/bin/bash
# instalar_bot_startup.sh
# Configura o bot Baileys para iniciar automaticamente quando o Mac ligar.

PLIST_FILE="$HOME/Library/LaunchAgents/com.nicolassodoski.baileys-bot.plist"
BOT_DIR="/Users/nicolassodoski/Claude/Projects/PW/baileys_bot"
LOG_FILE="$BOT_DIR/baileys.log"
NODE_PATH=$(which node)

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Configurar bot para iniciar no startup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ -z "$NODE_PATH" ]; then
  echo "❌ Node.js não encontrado. Instale com: brew install node"
  exit 1
fi

echo "✅ Node.js em: $NODE_PATH"

# Criar o arquivo plist do LaunchAgent
cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.nicolassodoski.baileys-bot</string>

  <key>ProgramArguments</key>
  <array>
    <string>$NODE_PATH</string>
    <string>$BOT_DIR/bot.js</string>
  </array>

  <key>WorkingDirectory</key>
  <string>$BOT_DIR</string>

  <!-- Iniciar automaticamente ao fazer login -->
  <key>RunAtLoad</key>
  <true/>

  <!-- Reiniciar automaticamente se cair -->
  <key>KeepAlive</key>
  <true/>

  <!-- Aguardar 10s antes de reiniciar após crash -->
  <key>ThrottleInterval</key>
  <integer>10</integer>

  <!-- Log de saída -->
  <key>StandardOutPath</key>
  <string>$LOG_FILE</string>

  <key>StandardErrorPath</key>
  <string>$LOG_FILE</string>

  <!-- Variáveis de ambiente -->
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
  </dict>
</dict>
</plist>
EOF

echo "✅ Arquivo criado: $PLIST_FILE"

# Parar versão anterior se existir
launchctl unload "$PLIST_FILE" 2>/dev/null || true

# Ativar o LaunchAgent
launchctl load "$PLIST_FILE"

echo "✅ LaunchAgent ativado!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "O bot agora:"
echo "  • Inicia automaticamente quando o Mac ligar"
echo "  • Reinicia sozinho se cair"
echo "  • Log em: $LOG_FILE"
echo ""
echo "Para desativar o startup automático:"
echo "  launchctl unload $PLIST_FILE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
