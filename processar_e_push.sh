#!/bin/bash
# processar_e_push.sh
# Roda processar_mensagens.py e faz push do imoveis.db ao GitHub se houver mudanças.
# Executado automaticamente a cada 30 minutos pelo LaunchAgent.

set -euo pipefail

PROJECT_DIR="$HOME/Claude/Projects/PW"
LOG="$PROJECT_DIR/processar_auto.log"
PYTHON="$(which python3)"

# Garante que o git usa as credenciais armazenadas no keychain
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"
}

log "=== Início do ciclo automático ==="

cd "$PROJECT_DIR"

# 1. Processar mensagens da fila
if [ -f "mensagens_fila.json" ]; then
    PENDENTES=$(python3 -c "
import json
fila = json.load(open('mensagens_fila.json'))
print(sum(1 for m in fila if not m.get('processado')))
" 2>/dev/null || echo "0")

    if [ "$PENDENTES" -gt "0" ]; then
        log "Processando $PENDENTES mensagens pendentes..."
        $PYTHON processar_mensagens.py >> "$LOG" 2>&1
        log "Processamento concluído."
    else
        log "Nenhuma mensagem pendente. Pulando."
        exit 0
    fi
else
    log "mensagens_fila.json não encontrado. Pulando."
    exit 0
fi

# 2. Analisar domínios novos descobertos nos links das mensagens
if [ -f "novos_dominios.json" ]; then
    PENDENTES_DOM=$(python3 -c "
import json
d = json.load(open('novos_dominios.json'))
print(sum(1 for v in d.values() if not v.get('analisado')))
" 2>/dev/null || echo "0")
    if [ "$PENDENTES_DOM" -gt "0" ]; then
        log "Analisando $PENDENTES_DOM domínio(s) novo(s)..."
        $PYTHON descobrir_sites.py >> "$LOG" 2>&1
    fi
fi

# 3. Gerar site atualizado
log "Gerando site..."
$PYTHON gerar_site.py >> "$LOG" 2>&1

# 4. Fazer push para GitHub se imoveis.db mudou
git add imoveis.db mensagens_fila.json Imoveis.html novos_dominios.json sites_extras.json 2>/dev/null || true

if git diff --staged --quiet; then
    log "Sem mudanças para enviar ao GitHub."
else
    git commit -m "🤖 Auto: $(date '+%Y-%m-%d %H:%M') — mensagens + sites descobertos" >> "$LOG" 2>&1
    git push >> "$LOG" 2>&1
    log "✅ Push feito ao GitHub. Site será atualizado em instantes."
fi

log "=== Ciclo concluído ==="
