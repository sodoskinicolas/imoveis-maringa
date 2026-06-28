#!/bin/bash
cd "/Users/nicolassodoski/Claude/Projects/PW/chatbot-corretores"
echo "=== Instalando dependências (sem scripts nativos) ==="
npm install --ignore-scripts @whiskeysockets/baileys @hapi/boom pino qrcode-terminal xlsx
if [ $? -eq 0 ]; then
  echo ""
  echo "✓ Instalação concluída!"
  echo ""
  echo "Agora rode o arquivo: 2_extrair_contatos.command"
else
  echo ""
  echo "✗ Erro na instalação. Tentando método alternativo..."
  npm install --ignore-scripts --legacy-peer-deps @whiskeysockets/baileys @hapi/boom pino qrcode-terminal xlsx
fi
echo ""
read -p "Pressione Enter para fechar..."
