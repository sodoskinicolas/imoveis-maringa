#!/bin/bash
cd "$(dirname "$0")"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Atualizar site e publicar na nuvem"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Processar mensagens do WhatsApp
echo "📩 Processando mensagens dos grupos..."
python3 processar_mensagens.py
echo ""

# 2. Gerar site
echo "🌐 Gerando site..."
python3 gerar_site.py
echo ""

# 3. Subir para GitHub
echo "📤 Subindo para GitHub..."
rm -f .git/index.lock 2>/dev/null
git config user.email "sodoskinicolas@gmail.com"
git config user.name "Nicolas Sodoski"
git add -A -- ':!.DS_Store' ':!baileys_bot/auth/' ':!baileys_bot/imagens/' ':!baileys_bot/baileys.log' ':!mensagens_fila.json' ':!cache_locais.json' ':!*.app' ':!*.zip'
git commit -m "🔄 Atualização $(date '+%d/%m/%Y %H:%M')" 2>/dev/null || echo "  (sem mudanças novas)"
git push origin main

echo ""
echo "✅ Site publicado!"
echo "   👉 https://sodoskinicolas.github.io/imoveis-maringa/"
echo ""
echo "   O site atualiza em ~2 minutos no GitHub."
echo ""
sleep 5
