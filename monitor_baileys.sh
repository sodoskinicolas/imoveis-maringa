#!/bin/bash
# monitor_baileys.sh — mostra pop-up no Mac se o bot Baileys passar >2h sem captar mensagens.
# Instalado como LaunchAgent (com.imoveis.monitor-baileys.plist), roda a cada 15 min.
# Teste manual: ./monitor_baileys.sh --test  (força o pop-up)

PW="/Users/nicolassodoski/Claude/Projects/PW"
FILA="$PW/mensagens_fila.json"
STATE="$PW/.monitor_baileys_state"
LIMITE=7200     # 2h sem mensagem nova → alerta
REALERTA=7200   # re-alerta no máximo a cada 2h enquanto o problema persistir

# Timestamp (epoch) da mensagem mais recente na fila
NEWEST=$(python3 - "$FILA" <<'EOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    ts = [m.get("timestamp", 0) for m in d if isinstance(m, dict)]
    print(int(max(ts)) if ts else 0)
except Exception:
    print(0)
EOF
)

NOW=$(date +%s)

if [ "$NEWEST" -eq 0 ]; then
    DETALHE="Não consegui ler $FILA (arquivo ausente ou corrompido)."
    AGE=$((LIMITE + 1))
else
    AGE=$((NOW - NEWEST))
    ULTIMA=$(date -r "$NEWEST" '+%d/%m às %H:%M' 2>/dev/null || echo '?')
    HORAS=$((AGE / 3600))
    DETALHE="Última mensagem captada: ${ULTIMA} (${HORAS}h atrás)."
fi

# Modo teste: força o alerta
[ "$1" = "--test" ] && AGE=$((LIMITE + 1)) && DETALHE="[TESTE] $DETALHE"

if [ "$AGE" -gt "$LIMITE" ]; then
    LAST_ALERT=$(cat "$STATE" 2>/dev/null || echo 0)
    if [ $((NOW - LAST_ALERT)) -gt "$REALERTA" ] || [ "$1" = "--test" ]; then
        osascript <<EOF
display dialog "⚠️ O bot Baileys está há mais de 2h sem captar mensagens dos grupos.

${DETALHE}

Verifique se o bot está rodando e se há erros 'Bad MAC' no log:
tail -100 ~/Claude/Projects/PW/baileys_bot/baileys.log

Correção comum: parar_baileys.sh → limpar session-*.json em auth/ → iniciar_baileys.sh" with title "Monitor Baileys — Imóveis Maringá" buttons {"OK"} default button 1 with icon caution
EOF
        echo "$NOW" > "$STATE"
    fi
else
    # Voltou ao normal — zera o estado para alertar de novo num próximo episódio
    rm -f "$STATE"
fi
