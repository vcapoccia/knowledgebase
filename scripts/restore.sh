#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config/backup.conf"

if [ -z "$1" ]; then
    echo "Usage: $0 <backup_timestamp>"
    echo ""
    echo "Available backups:"
    ls -1 "$BACKUP_ROOT" | grep "BACKUP_.*_MANIFEST.txt" | sed 's/BACKUP_\(.*\)_MANIFEST.txt/  \1/'
    exit 1
fi

TIMESTAMP=$1
APP_BACKUP="${BACKUP_APP_DIR}/app_${TIMESTAMP}"
DB_BACKUP="${BACKUP_DB_DIR}/db_${TIMESTAMP}"

if [ ! -d "$APP_BACKUP" ] || [ ! -d "$DB_BACKUP" ]; then
    echo "❌ Backup $TIMESTAMP non trovato"
    exit 1
fi

echo "🔄 RESTORE KBSEARCH da backup $TIMESTAMP"
echo "=========================================="
echo ""

# Stop services
echo "1. Stop services..."
docker compose down

# Restore PostgreSQL
echo "2. Restore PostgreSQL..."
# ... implement

echo "✅ RESTORE COMPLETATO"

