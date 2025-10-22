#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ============================================
# CONFIGURAZIONE
# ============================================

# Leggi da file config se esiste
CONFIG_FILE="$SCRIPT_DIR/config/github.conf"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
else
    # Default
    GITHUB_REMOTE="${GITHUB_REMOTE:-origin}"
    GITHUB_BRANCH="${GITHUB_BRANCH:-main}"
    AUTO_COMMIT="${AUTO_COMMIT:-true}"
    AUTO_PUSH="${AUTO_PUSH:-true}"
    COMMIT_PREFIX="${COMMIT_PREFIX:-[AUTO]}"
    DRY_RUN="${DRY_RUN:-false}"
fi

LOG_FILE="${PROJECT_ROOT}/scripts/logs/github_sync_$(date +%Y%m%d).log"
mkdir -p "$(dirname "$LOG_FILE")"

# ============================================
# FUNZIONI
# ============================================

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

error() {
    log "❌ ERROR: $1"
    exit 1
}

check_git() {
    cd "$PROJECT_ROOT"
    
    if [ ! -d .git ]; then
        error "Not a git repository. Run: git init"
    fi
    
    # Verifica remote
    if ! git remote | grep -q "^${GITHUB_REMOTE}$"; then
        error "Remote '${GITHUB_REMOTE}' not found. Configure it first."
    fi
}

detect_changes() {
    cd "$PROJECT_ROOT"
    
    # Files modificati
    MODIFIED=$(git status --porcelain | grep -E "^ M|^M " | wc -l)
    # Files non tracciati
    UNTRACKED=$(git status --porcelain | grep "^??" | wc -l)
    # Files cancellati
    DELETED=$(git status --porcelain | grep "^ D|^D " | wc -l)
    # Files staged
    STAGED=$(git status --porcelain | grep -E "^A |^M |^D " | wc -l)
    
    TOTAL=$((MODIFIED + UNTRACKED + DELETED))
    
    echo "$TOTAL"
}

generate_commit_message() {
    cd "$PROJECT_ROOT"
    
    local custom_msg="$1"
    
    if [ -n "$custom_msg" ]; then
        echo "${COMMIT_PREFIX} $custom_msg"
        return
    fi
    
    # Auto-generate message
    local msg="${COMMIT_PREFIX} Auto-sync: "
    local changes=()
    
    # Analizza modifiche
    if git diff --name-only --cached | grep -q "^main.py$"; then
        changes+=("API updates")
    fi
    
    if git diff --name-only --cached | grep -q "worker/"; then
        changes+=("worker changes")
    fi
    
    if git diff --name-only --cached | grep -q "scripts/"; then
        changes+=("scripts updates")
    fi
    
    if git diff --name-only --cached | grep -q "docker-compose"; then
        changes+=("docker config")
    fi
    
    if git diff --name-only --cached | grep -q "requirements"; then
        changes+=("dependencies")
    fi
    
    if git diff --name-only --cached | grep -q "frontend/"; then
        changes+=("frontend updates")
    fi
    
    if [ ${#changes[@]} -eq 0 ]; then
        changes+=("misc changes")
    fi
    
    # Join array
    local IFS=", "
    msg="${msg}${changes[*]}"
    
    echo "$msg"
}

show_status() {
    cd "$PROJECT_ROOT"
    
    log "📊 Git Status:"
    log "=============="
    
    # Modified files
    MODIFIED_FILES=$(git status --porcelain | grep -E "^ M|^M " | sed 's/^ M /  [M] /' | sed 's/^M  /  [M] /')
    if [ -n "$MODIFIED_FILES" ]; then
        log "Modified:"
        echo "$MODIFIED_FILES" | tee -a "$LOG_FILE"
    fi
    
    # Untracked files
    UNTRACKED_FILES=$(git status --porcelain | grep "^??" | sed 's/^?? /  [+] /')
    if [ -n "$UNTRACKED_FILES" ]; then
        log "New files:"
        echo "$UNTRACKED_FILES" | tee -a "$LOG_FILE"
    fi
    
    # Deleted files
    DELETED_FILES=$(git status --porcelain | grep -E "^ D|^D " | sed 's/^ D /  [-] /' | sed 's/^D  /  [-] /')
    if [ -n "$DELETED_FILES" ]; then
        log "Deleted:"
        echo "$DELETED_FILES" | tee -a "$LOG_FILE"
    fi
}

# ============================================
# MAIN
# ============================================

main() {
    local COMMIT_MSG="$1"
    local FORCE_PUSH="${2:-false}"
    
    log "🔄 GITHUB SYNC STARTED"
    log "======================"
    log "Remote: $GITHUB_REMOTE"
    log "Branch: $GITHUB_BRANCH"
    log "Dry-run: $DRY_RUN"
    log ""
    
    # Check git
    check_git
    
    # Detect changes
    CHANGES=$(detect_changes)
    
    if [ "$CHANGES" -eq 0 ]; then
        log "✅ No changes to sync"
        exit 0
    fi
    
    log "📝 Detected $CHANGES file(s) with changes"
    log ""
    
    # Show status
    show_status
    log ""
    
    # Git add
    if [ "$AUTO_COMMIT" = "true" ]; then
        log "📦 Staging changes..."
        
        if [ "$DRY_RUN" = "true" ]; then
            log "[DRY-RUN] Would stage all changes"
        else
            git add -A
            log "   ✅ Changes staged"
        fi
    else
        log "⏭️  Auto-commit disabled, skipping"
        exit 0
    fi
    
    # Git commit
    log ""
    log "💾 Creating commit..."
    
    FULL_COMMIT_MSG=$(generate_commit_message "$COMMIT_MSG")
    log "   Message: $FULL_COMMIT_MSG"
    
    if [ "$DRY_RUN" = "true" ]; then
        log "[DRY-RUN] Would commit with message: $FULL_COMMIT_MSG"
    else
        if git commit -m "$FULL_COMMIT_MSG"; then
            COMMIT_HASH=$(git rev-parse --short HEAD)
            log "   ✅ Commit created: $COMMIT_HASH"
        else
            error "Commit failed"
        fi
    fi
    
    # Git push
    if [ "$AUTO_PUSH" = "true" ]; then
        log ""
        log "🚀 Pushing to GitHub..."
        
        if [ "$DRY_RUN" = "true" ]; then
            log "[DRY-RUN] Would push to $GITHUB_REMOTE/$GITHUB_BRANCH"
        else
            # Pull first to avoid conflicts
            log "   → Pulling latest changes..."
            if git pull "$GITHUB_REMOTE" "$GITHUB_BRANCH" --rebase; then
                log "   ✅ Pulled successfully"
            else
                log "   ⚠️  Pull had conflicts, attempting to resolve..."
                # Try to continue rebase
                git rebase --continue 2>/dev/null || true
            fi
            
            # Push
            log "   → Pushing..."
            if [ "$FORCE_PUSH" = "true" ]; then
                git push "$GITHUB_REMOTE" "$GITHUB_BRANCH" --force
            else
                git push "$GITHUB_REMOTE" "$GITHUB_BRANCH"
            fi
            
            log "   ✅ Pushed to GitHub"
        fi
    else
        log ""
        log "⏭️  Auto-push disabled, commit local only"
    fi
    
    # Summary
    log ""
    log "============================================"
    log "✅ SYNC COMPLETED"
    log "============================================"
    log "Repo: https://github.com/vcapoccia/knowledgebase"
    log "Branch: $GITHUB_BRANCH"
    log "Commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'N/A')"
    log "Files synced: $CHANGES"
}

# ============================================
# PARSE ARGUMENTS
# ============================================

COMMIT_MSG=""
FORCE_PUSH=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--message)
            COMMIT_MSG="$2"
            shift 2
            ;;
        -f|--force)
            FORCE_PUSH=true
            shift
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -m, --message MSG    Custom commit message"
            echo "  -f, --force          Force push"
            echo "  -d, --dry-run        Show what would be done"
            echo "  -h, --help           Show this help"
            echo ""
            echo "Examples:"
            echo "  $0                           # Auto-sync with generated message"
            echo "  $0 -m 'Fixed bug in API'     # Custom message"
            echo "  $0 -d                        # Dry-run mode"
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

# Run main
main "$COMMIT_MSG" "$FORCE_PUSH"

