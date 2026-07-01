#!/bin/bash
# Adiciona "Subir GitHub.app" ao Dock automaticamente.
# Rode este arquivo UMA VEZ (duplo clique). Depois disso pode apagá-lo se quiser.

cd "$(dirname "$0")"
APP_PATH="$(pwd)/Subir GitHub.app"

if [ ! -d "$APP_PATH" ]; then
  osascript -e 'display alert "Não encontrei o Subir GitHub.app nesta pasta." as critical'
  exit 1
fi

# Monta a URL file:// com espaços codificados como %20
ENCODED_PATH=$(python3 -c "
import urllib.parse
print(urllib.parse.quote('$APP_PATH'))
" 2>/dev/null || echo "$APP_PATH" | sed 's/ /%20/g')

defaults write com.apple.dock persistent-apps -array-add "<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>file://${ENCODED_PATH}/</string><key>_CFURLStringType</key><integer>15</integer></dict></dict></dict>"

killall Dock

osascript -e 'display notification "Já pode clicar nele pra subir tudo pro GitHub." with title "✅ Subir GitHub adicionado ao Dock" sound name "Glass"'

echo ""
echo "Pronto! O Dock vai reiniciar (é normal piscar por um segundo) e o ícone"
echo "'Subir GitHub' vai aparecer lá. Clique nele sempre que quiser subir as"
echo "atualizações pro GitHub."
echo ""
sleep 4
