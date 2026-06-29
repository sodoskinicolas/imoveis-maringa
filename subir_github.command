#!/bin/bash
cd "$(dirname "$0")"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Subindo arquivos para o GitHub..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

rm -f .git/index.lock 2>/dev/null

git config user.email "sodoskinicolas@gmail.com"
git config user.name "Nicolas Sodoski"

git add -A -- ':!.DS_Store' ':!baileys_bot/auth/' ':!baileys_bot/imagens/' ':!baileys_bot/baileys.log' ':!mensagens_fila.json' ':!cache_locais.json' ':!*.app' ':!*.zip'

git commit -m "🔄 Atualização $(date '+%Y-%m-%d %H:%M')" 2>/dev/null || echo "Nada novo para commitar."

echo "📤 Enviando para GitHub..."
git push origin main

echo ""
echo "✅ Pronto! Acesse: https://sodoskinicolas.github.io/imoveis-maringa/"
echo ""
echo "⚠️  Se o site não aparecer ainda:"
echo "   1. Acesse github.com/sodoskinicolas/imoveis-maringa"
echo "   2. Settings → Pages → Source: GitHub Actions → Save"
echo ""
sleep 5
