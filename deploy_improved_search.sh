#!/bin/bash
# ================================================================
# KB Search - Deploy Improved Search Module v2.0
# ================================================================
# Migliora ricerca con:
# - Deduplicazione versioni (3,207 pattern analizzati)
# - Filtro temporale smart ("dal 2021 in poi")
# - Stopwords removal (40+ stopwords IT)
#
# Features:
# - Backup automatico pre-deploy
# - Rollback automatico se errori
# - Health check post-deploy
# - Backward compatible (no breaking changes)
# ================================================================

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Config
KBSEARCH_ROOT="/opt/kbsearch"
API_DIR="$KBSEARCH_ROOT/api"
BACKUP_DIR="$KBSEARCH_ROOT/backups/search_upgrade_$(date +%Y%m%d_%H%M%S)"
IMPROVE_SEARCH_PY="$KBSEARCH_ROOT/improve_search.py"
MAIN_PY="$API_DIR/main.py"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# === PREFLIGHT CHECKS ===
preflight_checks() {
    log_info "Eseguo preflight checks..."
    
    # Check se siamo in /opt/kbsearch
    if [[ ! -d "$KBSEARCH_ROOT" ]]; then
        log_error "Directory $KBSEARCH_ROOT non trovata!"
        log_info "Sei sicuro di essere nel server giusto?"
        exit 1
    fi
    
    # Check se improve_search.py esiste
    if [[ ! -f "$IMPROVE_SEARCH_PY" ]]; then
        log_error "File improve_search.py non trovato in $KBSEARCH_ROOT"
        log_info "Assicurati di aver copiato il file prima di eseguire il deploy!"
        exit 1
    fi
    
    # Check se main.py esiste
    if [[ ! -f "$MAIN_PY" ]]; then
        log_error "File main.py non trovato in $API_DIR"
        log_info "L'applicazione non sembra essere installata correttamente."
        exit 1
    fi
    
    # Check se Docker è running
    if ! docker compose ps | grep -q "api"; then
        log_error "Container API non in esecuzione!"
        log_info "Avvia l'applicazione con: docker compose up -d"
        exit 1
    fi
    
    log_success "Preflight checks OK"
}

# === BACKUP ===
backup_files() {
    log_info "Creo backup in $BACKUP_DIR..."
    
    mkdir -p "$BACKUP_DIR"
    
    # Backup main.py
    cp "$MAIN_PY" "$BACKUP_DIR/main.py.backup"
    
    # Backup improve_search.py se esiste già
    if [[ -f "$API_DIR/improve_search.py" ]]; then
        cp "$API_DIR/improve_search.py" "$BACKUP_DIR/improve_search.py.backup"
    fi
    
    # Backup docker compose logs
    docker compose logs api --tail=100 > "$BACKUP_DIR/api_logs_pre_deploy.txt" 2>&1 || true
    
    log_success "Backup creato: $BACKUP_DIR"
}

# === TEST MODULE ===
test_module() {
    log_info "Testo validità modulo improve_search.py..."
    
    # Test sintassi Python
    if ! python3 -m py_compile "$IMPROVE_SEARCH_PY"; then
        log_error "Errore sintassi Python in improve_search.py!"
        exit 1
    fi
    
    # Test import
    if ! python3 -c "import sys; sys.path.insert(0, '$(dirname $IMPROVE_SEARCH_PY)'); import improve_search" 2>&1; then
        log_error "Errore import modulo!"
        exit 1
    fi
    
    # Test funzioni base
    if ! python3 "$IMPROVE_SEARCH_PY" > /dev/null 2>&1; then
        log_error "Test modulo fallito! Esegui: python3 $IMPROVE_SEARCH_PY"
        exit 1
    fi
    
    log_success "Modulo valido"
}

# === PATCH MAIN.PY ===
patch_main_py() {
    log_info "Patching main.py per integrare improve_search..."
    
    # Check se già integrato
    if grep -q "from improve_search import enhance_search_query" "$MAIN_PY"; then
        log_warn "main.py già patchato, skip"
        return 0
    fi
    
    # Backup
    cp "$MAIN_PY" "$MAIN_PY.pre_patch"
    
    # Aggiungi import dopo gli altri import
    sed -i '/^import /a\# Search improvement module\ntry:\n    from improve_search import enhance_search_query, extract_date_filter, clean_query\n    IMPROVE_SEARCH_AVAILABLE = True\nexcept ImportError:\n    IMPROVE_SEARCH_AVAILABLE = False\n    print("⚠️  improve_search module not available - using basic search")' "$MAIN_PY"
    
    # Trova /search endpoint e modifica
    # Cerca la riga con "def search(" e aggiungi parametri
    if grep -q '@app.get("/search")' "$MAIN_PY" || grep -q '@app.post("/search")' "$MAIN_PY"; then
        log_info "Modifico endpoint /search..."
        
        # Crea patch file temporaneo
        cat > /tmp/search_patch.py << 'PATCH_EOF'
# === SEARCH ENDPOINT IMPROVED ===
@app.get("/search")
@app.post("/search")
async def search(
    q_text: str = Query(None, description="Text search query"),
    q_semantic: str = Query(None, description="Semantic search query"),
    filters: str = Query(None, description="Filters (kb_area:X)"),
    top_k: int = Query(20, ge=1, le=100),
    deduplicate: bool = Query(False, description="Remove duplicate versions"),
    smart_filter: bool = Query(True, description="Apply smart date filtering"),
):
    """
    Search endpoint with improvements:
    - Automatic version deduplication
    - Smart date filtering from query
    - Stopwords removal for better BM25
    """
    try:
        # Original query (for metadata)
        original_query = q_text or q_semantic or ""
        
        # Enhancement pipeline
        enhancement_meta = {}
        clean_query_text = q_text
        
        if IMPROVE_SEARCH_AVAILABLE and (q_text or q_semantic):
            # Extract date filter from query
            date_filter = extract_date_filter(original_query)
            if date_filter:
                enhancement_meta['date_filter'] = date_filter
            
            # Clean query for BM25 (remove stopwords)
            if q_text:
                clean_query_text = clean_query(q_text, remove_dates=(date_filter is not None))
                enhancement_meta['original_query'] = q_text
                enhancement_meta['cleaned_query'] = clean_query_text
        
        # === ORIGINAL SEARCH LOGIC ===
        # (manteniamo tutto come prima)
        results = []
        
        # BM25 search (con query pulita se disponibile)
        if q_text or clean_query_text:
            query_for_bm25 = clean_query_text if IMPROVE_SEARCH_AVAILABLE and clean_query_text else q_text
            # ... codice originale BM25 ...
            pass
        
        # Vector search
        if q_semantic:
            # ... codice originale vector ...
            pass
        
        # === ENHANCEMENT APPLICATO QUI ===
        if IMPROVE_SEARCH_AVAILABLE and results:
            try:
                # Apply date filter
                if smart_filter and 'date_filter' in enhancement_meta:
                    from improve_search import apply_date_filter
                    original_count = len(results)
                    results = apply_date_filter(results, enhancement_meta['date_filter'])
                    enhancement_meta['filtered_by_date'] = original_count - len(results)
                
                # Apply deduplication
                if deduplicate:
                    from improve_search import deduplicate_results
                    original_count = len(results)
                    results = deduplicate_results(results)
                    enhancement_meta['removed_duplicates'] = original_count - len(results)
                
            except Exception as e:
                # Graceful degradation: se enhancement fallisce, usa risultati originali
                print(f"⚠️  Enhancement failed: {e} - using original results")
        
        # Response (backward compatible)
        response = {
            "total": len(results),
            "hits": results[:top_k],
            "query": {
                "text": q_text,
                "semantic": q_semantic,
                "filters": filters
            }
        }
        
        # Add enhancement metadata if available
        if enhancement_meta:
            response['enhancement'] = enhancement_meta
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
PATCH_EOF
        
        log_warn "ATTENZIONE: Patch automatica non implementata completamente"
        log_warn "Integrazione manuale consigliata - vedi DEPLOY_GUIDE.md"
    fi
    
    log_success "main.py patchato (import aggiunto)"
}

# === COPY FILES ===
copy_files() {
    log_info "Copio file nell'API container..."
    
    # Copia improve_search.py in api/
    cp "$IMPROVE_SEARCH_PY" "$API_DIR/improve_search.py"
    
    # Set permissions
    chmod 644 "$API_DIR/improve_search.py"
    
    log_success "File copiati"
}

# === REBUILD CONTAINER ===
rebuild_container() {
    log_info "Rebuild container API..."
    
    # Stop API
    docker compose stop api
    
    # Rebuild (no cache per essere sicuri)
    docker compose build --no-cache api
    
    # Start API
    docker compose up -d api
    
    # Wait for healthy
    log_info "Attendo che API sia healthy..."
    for i in {1..30}; do
        if docker compose ps api | grep -q "healthy"; then
            log_success "API healthy"
            return 0
        fi
        sleep 2
    done
    
    log_error "API non diventa healthy dopo 60s!"
    return 1
}

# === HEALTH CHECK ===
health_check() {
    log_info "Health check post-deploy..."
    
    # Check 1: Container running
    if ! docker compose ps api | grep -q "Up"; then
        log_error "Container API non running!"
        return 1
    fi
    
    # Check 2: Health endpoint
    if ! curl -sf http://localhost:8000/health > /dev/null; then
        log_error "Health endpoint non risponde!"
        return 1
    fi
    
    # Check 3: Search endpoint (basic test)
    if ! curl -sf "http://localhost:8000/search?q_text=test&top_k=1" > /dev/null; then
        log_error "Search endpoint non risponde!"
        return 1
    fi
    
    # Check 4: Logs per errori
    if docker compose logs api --tail=50 | grep -i "error.*improve_search\|traceback.*improve_search"; then
        log_warn "Trovati errori nei log relativi a improve_search"
        return 1
    fi
    
    log_success "Health check OK"
    return 0
}

# === ROLLBACK ===
rollback() {
    log_warn "Eseguo ROLLBACK..."
    
    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_error "Backup directory non trovata: $BACKUP_DIR"
        return 1
    fi
    
    # Restore main.py
    if [[ -f "$BACKUP_DIR/main.py.backup" ]]; then
        cp "$BACKUP_DIR/main.py.backup" "$MAIN_PY"
        log_success "main.py ripristinato"
    fi
    
    # Remove improve_search.py
    if [[ -f "$API_DIR/improve_search.py" ]]; then
        rm "$API_DIR/improve_search.py"
        log_success "improve_search.py rimosso"
    fi
    
    # Rebuild
    docker compose stop api
    docker compose build --no-cache api
    docker compose up -d api
    
    # Wait
    sleep 10
    
    if curl -sf http://localhost:8000/health > /dev/null; then
        log_success "Rollback completato - API restored"
        return 0
    else
        log_error "CRITICO: Rollback fallito! Controlla manualmente"
        return 1
    fi
}

# === MAIN ===
main() {
    echo ""
    echo "================================================================"
    echo "  KB Search - Deploy Improved Search Module v2.0"
    echo "================================================================"
    echo ""
    
    # Handle rollback mode
    if [[ "$1" == "rollback" ]]; then
        LAST_BACKUP=$(ls -td $KBSEARCH_ROOT/backups/search_upgrade_* 2>/dev/null | head -1)
        if [[ -z "$LAST_BACKUP" ]]; then
            log_error "Nessun backup trovato!"
            exit 1
        fi
        BACKUP_DIR="$LAST_BACKUP"
        rollback
        exit $?
    fi
    
    # === DEPLOY PIPELINE ===
    
    # 1. Preflight
    preflight_checks || exit 1
    
    # 2. Backup
    backup_files || exit 1
    
    # 3. Test module
    test_module || exit 1
    
    # 4. Patch main.py
    log_info "Integrazione con main.py..."
    log_warn "⚠️  Integrazione MANUALE consigliata - vedere DEPLOY_GUIDE.md"
    log_info "Per ora copio solo il modulo, poi dovrai integrarlo manualmente"
    
    # 5. Copy files
    copy_files || exit 1
    
    # 6. Rebuild
    if ! rebuild_container; then
        log_error "Rebuild fallito!"
        rollback
        exit 1
    fi
    
    # 7. Health check
    if ! health_check; then
        log_error "Health check fallito!"
        log_warn "Eseguo rollback automatico..."
        rollback
        exit 1
    fi
    
    # === SUCCESS ===
    echo ""
    echo "================================================================"
    log_success "DEPLOY COMPLETATO CON SUCCESSO!"
    echo "================================================================"
    echo ""
    log_info "Backup salvato in: $BACKUP_DIR"
    log_info "Modulo copiato in: $API_DIR/improve_search.py"
    echo ""
    log_warn "⚠️  INTEGRAZIONE MANUALE NECESSARIA:"
    log_info "1. Modifica $MAIN_PY per usare il modulo"
    log_info "2. Segui le istruzioni in DEPLOY_GUIDE.md"
    log_info "3. Esegui: docker compose restart api"
    log_info "4. Test: ./test_improved_search.sh"
    echo ""
    log_info "Per rollback: $0 rollback"
    echo ""
}

# Run
main "$@"
