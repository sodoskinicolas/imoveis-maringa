#!/bin/bash
# iniciar_baileys.sh — Instala dependências e inicia o bot em background

set -e

PW_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BOT_DIR="$PW_DIR/baileys_bot"
PID_FILE="$BOT_DIR/bot.pid"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Bot WhatsApp Baileys — Imóveis Maringá"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Verificar Node.js
if ! command -v node &>/dev/null; then
  echo "❌ Node.js não encontrado."
  echo "   Instale: https://nodejs.org  (LTS) ou via Homebrew:"
  echo "   brew install node"
  exit 1
fi

echo "✅ Node.js $(node --version)"

# Instalar dependências se necessário
if [ ! -d "$BOT_DIR/node_modules" ]; then
  echo ""
  echo "📦 Instalando dependências..."
  cd "$BOT_DIR" && npm install
  cd "$PW_DIR"
fi

# Matar TODOS os processos node bot.js (evita duplicatas)
PIDS=$(pgrep -f "node bot.js" 2>/dev/null || true)
if [ -n "$PIDS" ]; then
  echo "⚠️  Encerrando processos anteriores: $PIDS"
  echo "$PIDS" | xargs kill 2>/dev/null || true
  sleep 2
fi
rm -f "$PID_FILE"

# Criar pasta auth se não existir
mkdir -p "$BOT_DIR/auth"

echo ""
echo "🚀 Iniciando bot em background..."
echo "   Log: $BOT_DIR/baileys.log"
echo ""

cd "$BOT_DIR"
nohup node bot.js >> baileys.log 2>&1 &
BOT_PID=$!
echo $BOT_PID > "$PID_FILE"

echo "✅ Bot iniciado (PID $BOT_PID)"
echo ""

# Verificar se é primeira vez (sem sessão salva)
if [ ! -f "$BOT_DIR/auth/creds.json" ]; then
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "⚠️  PRIMEIRA EXECUÇÃO — ESCANEAR QR CODE"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "O QR Code vai aparecer no log. Para ver:"
  echo "   tail -f $BOT_DIR/baileys.log"
  echo ""
  echo "Escaneie com o WhatsApp do celular:"
  echo "   Configurações → Aparelhos Vinculados → Vincular Aparelho"
  echo ""
  echo "Após escanear, o bot conecta e começa a capturar mensagens."
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
else
  echo "ℹ️  Sessão existente — reconectando automaticamente."
  echo "    Para acompanhar: tail -f $BOT_DIR/baileys.log"
fi

echo ""
echo "Comandos úteis:"
echo "  Ver mensagens capturadas:  python3 processar_mensagens.py --ver-fila"
echo "  Processar mensagens:       python3 processar_mensagens.py"
echo "  Parar o bot:               bash parar_baileys.sh"
echo ""
