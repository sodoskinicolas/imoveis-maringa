#!/bin/bash
# Script de instalação e inicialização
# Execute com: bash instalar_e_rodar.sh

PASTA=$(cd "$(dirname "$0")" && pwd)
cd "$PASTA"

echo ""
echo "========================================"
echo "  Chatbot Corretores Maringá — Setup   "
echo "========================================"
echo ""

# Verificar Node.js
if ! command -v node &> /dev/null; then
    echo "✗ Node.js não encontrado."
    echo "  Instale em: https://nodejs.org"
    exit 1
fi
echo "✓ Node.js $(node --version)"

# Instalar dependências
echo ""
echo "Instalando pacotes (pode demorar 1-2 min na primeira vez)..."
npm install --silent

if [ $? -ne 0 ]; then
    echo "✗ Erro na instalação. Tente: npm install"
    exit 1
fi

echo "✓ Pacotes instalados!"
echo ""
echo "========================================"
echo "  O que deseja fazer?                  "
echo "  [1] Extrair contatos do grupo        "
echo "  [2] Enviar mensagens para corretores "
echo "========================================"
echo ""
read -p "Digite 1 ou 2: " opcao

if [ "$opcao" = "1" ]; then
    node extrair_contatos.js
elif [ "$opcao" = "2" ]; then
    node enviar_mensagens.js
else
    echo "Opção inválida."
fi
