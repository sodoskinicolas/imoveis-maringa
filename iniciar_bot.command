#!/bin/bash
# iniciar_bot.command — Duplo clique para iniciar o bot e fechar o terminal

cd "$(dirname "$0")"
./iniciar_baileys.sh

# Fecha a janela do Terminal automaticamente após 2s
sleep 2
osascript -e 'tell application "Terminal" to close front window' &
