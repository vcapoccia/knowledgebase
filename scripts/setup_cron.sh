#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Backup giornaliero alle 2:00 AM
CRON_JOB="0 2 * * * $SCRIPT_DIR/backup_full.sh >> /var/log/kbsearch_backup.log 2>&1"

# Aggiungi a crontab
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo "✅ Cron job configurato: backup giornaliero alle 2:00 AM"
echo "   Log: /var/log/kbsearch_backup.log"

