#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🔄 SETUP AUTO-SYNC GITHUB"
echo "========================="
echo ""
echo "Scegli frequenza sync:"
echo "  1) Ogni ora"
echo "  2) Ogni 6 ore"
echo "  3) Una volta al giorno (2:30 AM)"
echo "  4) Manuale (no cron)"
echo ""

read -p "Scelta [1-4]: " choice

case $choice in
    1)
        CRON_SCHEDULE="0 * * * *"
        FREQ="ogni ora"
        ;;
    2)
        CRON_SCHEDULE="0 */6 * * *"
        FREQ="ogni 6 ore"
        ;;
    3)
        CRON_SCHEDULE="30 2 * * *"
        FREQ="giornaliero (2:30 AM)"
        ;;
    4)
        echo "✅ Sync manuale - usa: ./scripts/sync_github.sh"
        exit 0
        ;;
    *)
        echo "❌ Scelta non valida"
        exit 1
        ;;
esac

# Setup cron
CRON_JOB="$CRON_SCHEDULE $SCRIPT_DIR/sync_github.sh >> $SCRIPT_DIR/logs/autosync.log 2>&1"

# Aggiungi
(crontab -l 2>/dev/null | grep -v "sync_github.sh"; echo "$CRON_JOB") | crontab -

echo ""
echo "✅ Auto-sync configurato: $FREQ"
echo "   Log: $SCRIPT_DIR/logs/autosync.log"
echo ""
echo "Per disabilitare:"
echo "  crontab -e"
echo "  # Rimuovi riga con sync_github.sh"

