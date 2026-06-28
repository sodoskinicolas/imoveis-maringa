#!/bin/bash
# instalar_agendamento.sh
# Instala dois LaunchAgents no macOS:
#   - 03:00  →  raspar_imoveis.py  (raspagem de todos os sites)
#   - 08:00  →  gerar_site.py      (regera o HTML do site)
#
# Uso:
#   chmod +x instalar_agendamento.sh
#   ./instalar_agendamento.sh

set -e

PW_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PYTHON=$(which python3)
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS"

echo "📂 Pasta do projeto: $PW_DIR"
echo "🐍 Python: $PYTHON"

# ── 1. Raspar imóveis às 03:00 ────────────────────────────────────────────────
PLIST_RASPAR="$LAUNCH_AGENTS/com.nicolassodoski.raspar_imoveis.plist"

cat > "$PLIST_RASPAR" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nicolassodoski.raspar_imoveis</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$PW_DIR/raspar_imoveis.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$PW_DIR</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>   <integer>3</integer>
        <key>Minute</key> <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>$PW_DIR/raspar_imoveis.log</string>

    <key>StandardErrorPath</key>
    <string>$PW_DIR/raspar_imoveis.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLIST

# ── 2. Gerar site às 08:00 ────────────────────────────────────────────────────
PLIST_SITE="$LAUNCH_AGENTS/com.nicolassodoski.gerar_site.plist"

cat > "$PLIST_SITE" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nicolassodoski.gerar_site</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$PW_DIR/gerar_site.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$PW_DIR</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>   <integer>8</integer>
        <key>Minute</key> <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>$PW_DIR/gerar_site.log</string>

    <key>StandardErrorPath</key>
    <string>$PW_DIR/gerar_site.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
PLIST

# ── Registrar no launchd ──────────────────────────────────────────────────────
launchctl unload "$PLIST_RASPAR" 2>/dev/null || true
launchctl load   "$PLIST_RASPAR"
echo "✅ Agendado: raspar_imoveis.py às 03:00"

launchctl unload "$PLIST_SITE" 2>/dev/null || true
launchctl load   "$PLIST_SITE"
echo "✅ Agendado: gerar_site.py às 08:00"

echo ""
echo "Para verificar:"
echo "  launchctl list | grep nicolassodoski"
echo ""
echo "Para rodar manualmente agora (teste):"
echo "  python3 $PW_DIR/raspar_imoveis.py --dry-run"
echo "  python3 $PW_DIR/gerar_site.py"
echo ""
echo "Logs em:"
echo "  $PW_DIR/raspar_imoveis.log"
echo "  $PW_DIR/gerar_site.log"
