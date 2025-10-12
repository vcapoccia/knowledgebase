#!/bin/bash
#
# cleanup_repo.sh - Script di pulizia repository KnowledgeBase
# 
# ATTENZIONE: Questo script elimina file. Fai backup prima!
# 
# Uso: ./cleanup_repo.sh [--dry-run]
#

set -e

DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "🔍 MODALITÀ DRY-RUN: nessun file sarà eliminato"
    echo ""
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

echo "🧹 Pulizia Repository KnowledgeBase"
echo "📁 Directory: $REPO_ROOT"
echo ""

# Funzione per eliminare file/cartelle
remove_item() {
    local item="$1"
    if [[ ! -e "$item" ]]; then
        echo "  ⏭️  $item (già assente)"
        return
    fi
    
    if $DRY_RUN; then
        echo "  [DRY-RUN] Eliminerei: $item"
    else
        if [[ -d "$item" ]]; then
            rm -rf "$item"
            echo "  ✅ Eliminata cartella: $item"
        else
            rm -f "$item"
            echo "  ✅ Eliminato file: $item"
        fi
    fi
}

# Backup preventivo se non è dry-run
if ! $DRY_RUN; then
    BACKUP_DIR="${REPO_ROOT}.backup.$(date +%Y%m%d_%H%M%S)"
    echo "💾 Creazione backup in: $BACKUP_DIR"
    cp -r "$REPO_ROOT" "$BACKUP_DIR"
    echo "✅ Backup completato"
    echo ""
fi

echo "🗂️  FASE 1: Rimozione frontend duplicati"
remove_item "web"
remove_item "www"
remove_item "app"
echo ""

echo "🐍 FASE 2: Rimozione file Python duplicati"
remove_item "main.py"
remove_item "worker_tasks.py"
remove_item "api/worker_tasks.py"
echo ""

echo "⚙️  FASE 3: Rimozione configurazioni duplicate/inutilizzate"
remove_item "api/config"
remove_item "config"
echo ""

echo "🐛 FASE 4: Rimozione file debug/temporanei"
remove_item "patch_worker_tasks.diff"
remove_item "diagnostics.sh"
remove_item "struttura.txt"
remove_item "logs"
remove_item "frontend/templates/admin.bak"
echo ""

echo "📜 FASE 5: Rimozione script inutilizzati"
remove_item "scripts/cleanupTxt.sh"
remove_item "scripts/debugKB.sh"
remove_item "scripts/diag.sh"
remove_item "scripts/stopAllJobs.sh"
remove_item "scripts/watch_ingestion.sh"
remove_item "scripts/monitor_ingestion.sh"
remove_item "scripts/reindex.sh"
remove_item "scripts/init.d"
remove_item "scripts/kb_diagnostics.py"
echo ""

echo "🗑️  FASE 6: Rimozione file Python inutilizzati"
remove_item "api/appMonitor.py"
remove_item "api/kb_diagnostics.py"
remove_item "api/regex_rules.py"
remove_item "api/regex_rules_api.py"
echo ""

echo "🧼 FASE 7: Pulizia cache Python"
if $DRY_RUN; then
    echo "  [DRY-RUN] Eliminerei tutte le cartelle __pycache__"
    find . -type d -name "__pycache__" | head -10
    echo "  ..."
else
    PYCACHE_COUNT=$(find . -type d -name "__pycache__" | wc -l)
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    echo "  ✅ Eliminate $PYCACHE_COUNT cartelle __pycache__"
    
    PYC_COUNT=$(find . -name "*.pyc" | wc -l)
    find . -name "*.pyc" -delete
    echo "  ✅ Eliminati $PYC_COUNT file .pyc"
fi
echo ""

echo "📊 RIEPILOGO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if $DRY_RUN; then
    echo "⚠️  Modalità DRY-RUN: nessun file è stato eliminato"
    echo ""
    echo "Per eseguire la pulizia reale:"
    echo "  ./cleanup_repo.sh"
else
    echo "✅ Pulizia completata!"
    echo ""
    echo "📁 Backup salvato in:"
    echo "   $BACKUP_DIR"
    echo ""
    echo "🔄 Prossimi passi:"
    echo "   1. Verifica che tutto funzioni: docker compose build"
    echo "   2. Se tutto ok: docker compose up -d"
    echo "   3. Se ci sono problemi: cp -r $BACKUP_DIR/* ."
fi

echo ""
echo "📝 File/cartelle rimossi:"
echo "   - Frontend: web/, www/, app/"
echo "   - Python: main.py, worker_tasks.py (root), api/worker_tasks.py"
echo "   - Config: api/config/, config/"
echo "   - Debug: logs/, patch_worker_tasks.diff, ecc."
echo "   - Script: cleanupTxt.sh, debugKB.sh, monitor_ingestion.sh, ecc."
echo "   - Cache: __pycache__/, *.pyc"
echo ""

if ! $DRY_RUN; then
    echo "✨ Repository pulito! Dimensione ridotta significativamente."
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
