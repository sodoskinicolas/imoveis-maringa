#!/bin/bash
# parar_baileys.sh — Para o bot Baileys

PW_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PID_FILE="$PW_DIR/baileys_bot/bot.pid"

if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    rm -f "$PID_FILE"
    echo "✅ Bot parado (PID $PID)"
  else
    echo "⚠️  Bot não estava rodando (PID $PID inativo)"
    rm -f "$PID_FILE"
  fi
else
  echo "⚠️  Nenhum bot registrado. Verifique manualmente:"
  echo "   ps aux | grep bot.js"
fi
