#!/bin/bash
# Adiciona "Ver Fluxograma.app" ao Dock.
cd "$(dirname "$0")"
APP_PATH="$(pwd)/Ver Fluxograma.app"

if [ ! -d "$APP_PATH" ]; then
  osascript -e 'display alert "Não encontrei o Ver Fluxograma.app nesta pasta." as critical'
  exit 1
fi

ENCODED_PATH=$(python3 -c "
import urllib.parse
print(urllib.parse.quote('$APP_PATH'))
" 2>/dev/null)

if [ -z "$ENCODED_PATH" ]; then
  ENCODED_PATH=$(echo "$APP_PATH" | sed 's/ /%20/g')
fi

defaults write com.apple.dock persistent-apps -array-add "<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>file://${ENCODED_PATH}/</string><key>_CFURLStringType</key><integer>15</integer></dict></dict></dict>"

killall Dock

echo ""
echo "Comando executado. Verificando se o ícone foi registrado..."
sleep 1
if defaults read com.apple.dock persistent-apps | grep -q "Ver Fluxograma"; then
  echo "✅ 'Ver Fluxograma' está na lista do Dock. Se não aparecer visualmente,"
  echo "   dê um Cmd+Espaço e digite 'Ver Fluxograma' pra confirmar que o app existe,"
  echo "   ou role o Dock — às vezes fica escondido se o Dock estiver cheio."
else
  echo "⚠️  Não encontrei 'Ver Fluxograma' na lista depois de tentar adicionar."
  echo "   Copie e cole esta linha inteira no Terminal e me mande o que aparecer:"
  echo "   defaults read com.apple.dock persistent-apps | tail -20"
fi
echo ""
sleep 5
