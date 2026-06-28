#!/bin/bash
# subir_para_github.sh
# Envia a pasta PW para o GitHub pela primeira vez.
#
# PRÉ-REQUISITOS (faça antes de rodar este script):
#   1. Crie uma conta em https://github.com (se não tiver)
#   2. Crie um repositório PÚBLICO em https://github.com/new
#      - Nome sugerido: imoveis-maringa
#      - Deixe vazio (sem README)
#   3. Instale o GitHub CLI: https://cli.github.com
#      No Mac: brew install gh
#   4. Faça login: gh auth login
#
# DEPOIS rode:
#   chmod +x subir_para_github.sh
#   ./subir_para_github.sh

set -e

PW_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PW_DIR"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Subir Imóveis Maringá para o GitHub"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Verificar se gh está instalado
if ! command -v gh &>/dev/null; then
  echo "❌ GitHub CLI (gh) não encontrado."
  echo "   Instale com: brew install gh"
  echo "   Depois faça login: gh auth login"
  exit 1
fi

# Verificar se está logado
if ! gh auth status &>/dev/null; then
  echo "❌ Não está logado no GitHub CLI."
  echo "   Rode: gh auth login"
  exit 1
fi

GH_USER=$(gh api user --jq .login)
echo "👤 Logado como: $GH_USER"

# Pedir nome do repositório
read -p "📦 Nome do repositório GitHub (ex: imoveis-maringa): " REPO_NAME
REPO_NAME="${REPO_NAME:-imoveis-maringa}"

# Criar .gitignore para não enviar arquivos desnecessários
cat > .gitignore << 'EOF'
*.log
*.pyc
__pycache__/
.DS_Store
*.swp
outputs/
raspar_imoveis.log
gerar_site.log
EOF

# Inicializar git se necessário
if [ ! -d ".git" ]; then
  git init
  echo "✅ Repositório git inicializado."
fi

# Criar repositório no GitHub
echo ""
echo "📡 Criando repositório $GH_USER/$REPO_NAME no GitHub..."
gh repo create "$REPO_NAME" --public --source=. --remote=origin 2>/dev/null || {
  # Repositório já existe — só adicionar o remote
  git remote remove origin 2>/dev/null || true
  git remote add origin "https://github.com/$GH_USER/$REPO_NAME.git"
  echo "   Repositório já existe, usando o existente."
}

# Primeiro commit
git add .
git status --short

echo ""
read -p "📤 Enviar esses arquivos para o GitHub? (s/n): " CONFIRM
if [[ "$CONFIRM" != "s" && "$CONFIRM" != "S" ]]; then
  echo "Cancelado."
  exit 0
fi

git commit -m "🚀 Setup inicial — imóveis Maringá" 2>/dev/null || \
  git commit --allow-empty -m "🚀 Setup inicial"

git branch -M main
git push -u origin main

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Arquivos enviados!"
echo ""
echo "🔗 Repositório: https://github.com/$GH_USER/$REPO_NAME"
echo ""
echo "PRÓXIMOS PASSOS:"
echo ""
echo "1. Ativar GitHub Pages:"
echo "   → Acesse: https://github.com/$GH_USER/$REPO_NAME/settings/pages"
echo "   → Em 'Source', selecione 'GitHub Actions'"
echo "   → Salve"
echo ""
echo "2. Rodar os workflows manualmente pela primeira vez:"
echo "   → Acesse: https://github.com/$GH_USER/$REPO_NAME/actions"
echo "   → Clique em '🌐 Gerar Site' → 'Run workflow'"
echo ""
echo "3. Seu site ficará disponível em:"
echo "   → https://$GH_USER.github.io/$REPO_NAME/"
echo ""
echo "A partir de amanhã, tudo roda automático:"
echo "   03:00 BRT → raspa os sites"
echo "   08:00 BRT → atualiza o site"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
