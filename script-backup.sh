#!/bin/bash
# =======================================================================
# KNOWLEDGEBASE BACKUP SCRIPT
# Script di backup completo per Knowledge Base System v2.0
# =======================================================================

set -euo pipefail

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[0;37m'
NC='\033[0m' # No Color

# Configurazioni
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_ROOT="$PROJECT_DIR/data/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="$BACKUP_ROOT/backup_$TIMESTAMP"
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-30}
COMPRESS_LEVEL=${BACKUP_COMPRESS_LEVEL:-6}
PARALLEL_JOBS=${BACKUP_PARALLEL_JOBS:-2}

# Flags
INCLUDE_DOCUMENTS=${BACKUP_INCLUDE_DOCUMENTS:-true}
INCLUDE_LOGS=${BACKUP_INCLUDE_LOGS:-false}
INCLUDE_CONFIG=${BACKUP_INCLUDE_CONFIG:-true}
INCLUDE_DATABASE=${BACKUP_INCLUDE_DATABASE:-true}
ENCRYPT_BACKUP=${ENCRYPT_BACKUP:-false}
REMOTE_BACKUP=${REMOTE_BACKUP:-false}

# =======================================================================
# UTILITY FUNCTIONS
# =======================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

log_success() {
    echo -e "${PURPLE}[SUCCESS]${NC} $1"
}

# Calcola dimensione directory
get_dir_size() {
    local dir="$1"
    if [[ -d "$dir" ]]; then
        du -sh "$dir" 2>/dev/null | cut -f1 || echo "N/A"
    else
        echo "N/A"
    fi
}

# Calcola spazio disponibile
get_available_space() {
    df -h "$BACKUP_ROOT" | awk 'NR==2 {print $4}'
}

# Controlla se comando esiste
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# =======================================================================
# PRE-BACKUP CHECKS
# =======================================================================

check_prerequisites() {
    log_step "Controllo prerequisiti..."
    
    # Verifica comandi necessari
    local missing_commands=()
    
    if ! command_exists tar; then
        missing_commands+=("tar")
    fi
    
    if ! command_exists gzip; then
        missing_commands+=("gzip")
    fi
    
    if ! command_exists docker; then
        missing_commands+=("docker")
    fi
    
    if [[ $ENCRYPT_BACKUP == true ]] && ! command_exists gpg; then
        missing_commands+=("gpg")
    fi
    
    if [[ ${#missing_commands[@]} -gt 0 ]]; then
        log_error "Comandi mancanti: ${missing_commands[*]}"
        exit 1
    fi
    
    # Verifica spazio disco
    local available_space total_size
    available_space=$(df -BG "$BACKUP_ROOT" | tail -n1 | awk '{print $4}' | sed 's/G//')
    total_size=$(du -BG "$PROJECT_DIR" 2>/dev/null | tail -n1 | awk '{print $1}' | sed 's/G//')
    
    if [[ $available_space -lt $((total_size + 5)) ]]; then
        log_error "Spazio disco insufficiente. Disponibili: ${available_space}GB, Necessari: ~$((total_size + 5))GB"
        exit 1
    fi
    
    log_info "Spazio disponibile: ${available_space}GB"
    log_success "Prerequisiti soddisfatti"
}

check_services() {
    log_step "Controllo stato servizi..."
    
    cd "$PROJECT_DIR"
    
    # Lista servizi in esecuzione
    local running_services
    if running_services=$(docker-compose ps --services --filter "status=running" 2>/dev/null); then
        if [[ -n "$running_services" ]]; then
            log_info "Servizi in esecuzione:"
            echo "$running_services" | while read -r service; do
                log_info "  - $service"
            done
        else
            log_warn "Nessun servizio in esecuzione"
        fi
    else
        log_warn "Impossibile verificare stato servizi Docker Compose"
    fi
}

# =======================================================================
# BACKUP FUNCTIONS
# =======================================================================

backup_configuration() {
    log_step "Backup configurazioni..."
    
    local config_backup="$BACKUP_DIR/configuration"
    mkdir -p "$config_backup"
    
    # File di configurazione principali
    local config_files=(
        ".env"
        ".env.example"
        "docker-compose.yml"
        "docker-compose.override.yml"
        "Makefile"
        "README.md"
    )
    
    for file in "${config_files[@]}"; do
        if [[ -f "$PROJECT_DIR/$file" ]]; then
            cp "$PROJECT_DIR/$file" "$config_backup/"
            log_info "✓ Copiato: $file"
        fi
    done
    
    # Directory config
    if [[ -d "$PROJECT_DIR/config" ]]; then
        cp -r "$PROJECT_DIR/config" "$config_backup/"
        log_info "✓ Copiata directory config"
    fi
    
    # Scripts
    if [[ -d "$PROJECT_DIR/scripts" ]]; then
        cp -r "$PROJECT_DIR/scripts" "$config_backup/"
        log_info "✓ Copiata directory scripts"
    fi
    
    log_success "Backup configurazioni completato"
}

backup_documents() {
    if [[ $INCLUDE_DOCUMENTS != true ]]; then
        log_info "Backup documenti saltato (configurazione)"
        return 0
    fi
    
    log_step "Backup documenti..."
    
    local docs_dir="$PROJECT_DIR/docs"
    local docs_backup="$BACKUP_DIR/documents"
    
    if [[ ! -d "$docs_dir" ]]; then
        log_warn "Directory documenti non trovata: $docs_dir"
        return 0
    fi
    
    local docs_size
    docs_size=$(get_dir_size "$docs_dir")
    log_info "Dimensione documenti: $docs_size"
    
    # Backup incrementale se esiste backup precedente
    local latest_backup
    if latest_backup=$(find "$BACKUP_ROOT" -maxdepth 1 -type d -name "backup_*" | sort | tail -n2 | head -n1); then
        if [[ -d "$latest_backup/documents" ]]; then
            log_info "Backup incrementale basato su: $(basename "$latest_backup")"
            rsync -av --link-dest="$latest_backup/documents" "$docs_dir/" "$docs_backup/"
        else
            tar -czf "$docs_backup.tar.gz" -C "$PROJECT_DIR" docs/
        fi
    else
        tar -czf "$docs_backup.tar.gz" -C "$PROJECT_DIR" docs/
    fi
    
    log_success "Backup documenti completato"
}

backup_database() {
    if [[ $INCLUDE_DATABASE != true ]]; then
        log_info "Backup database saltato (configurazione)"
        return 0
    fi
    
    log_step "Backup database Qdrant..."
    
    local db_backup="$BACKUP_DIR/database"
    mkdir -p "$db_backup"
    
    # Controlla se Qdrant è in esecuzione
    if docker-compose ps qdrant | grep -q "Up"; then
        log_info "Qdrant in esecuzione, creazione snapshot..."
        
        # Crea snapshot via API
        local snapshot_name="backup_$TIMESTAMP"
        if curl -s -X POST "http://localhost:6333/collections/kb_chunks/snapshots" \
                -H "Content-Type: application/json" \
                -d "{\"snapshot_name\": \"$snapshot_name\"}" >/dev/null; then
            
            # Aspetta completamento snapshot
            sleep 5
            
            # Copia snapshot
            if docker cp kb-qdrant:/qdrant/storage/snapshots "$db_backup/snapshots"; then
                log_success "Snapshot Qdrant creato e copiato"
            else
                log_warn "Errore nella copia dello snapshot"
            fi
        else
            log_warn "Errore nella creazione dello snapshot via API"
        fi
    else
        log_info "Qdrant non in esecuzione, backup diretto volume..."
    fi
    
    # Backup volume Docker
    if docker volume ls | grep -q qdrant_storage; then
        log_info "Backup volume qdrant_storage..."
        docker run --rm \
            -v qdrant_storage:/data:ro \
            -v "$db_backup":/backup \
            alpine tar czf /backup/qdrant_volume.tar.gz -C /data .
        log_success "Backup volume completato"
    else
        log_warn "Volume qdrant_storage non trovato"
    fi
}

backup_logs() {
    if [[ $INCLUDE_LOGS != true ]]; then
        log_info "Backup logs saltato (configurazione)"
        return 0
    fi
    
    log_step "Backup logs..."
    
    local logs_backup="$BACKUP_DIR/logs"
    local logs_dir="$PROJECT_DIR/data/logs"
    
    if [[ -d "$logs_dir" ]]; then
        local logs_size
        logs_size=$(get_dir_size "$logs_dir")
        log_info "Dimensione logs: $logs_size"
        
        # Comprimi logs (escludendo file troppo vecchi)
        find "$logs_dir" -name "*.log" -mtime -7 | \
            tar -czf "$logs_backup.tar.gz" -T -
        
        log_success "Backup logs completato"
    else
        log_warn "Directory logs non trovata"
    fi
}

backup_application_data() {
    log_step "Backup dati applicazione..."
    
    local app_backup="$BACKUP_DIR/application"
    mkdir -p "$app_backup"
    
    # Cache e modelli
    if [[ -d "$PROJECT_DIR/temp" ]]; then
        # Solo file importanti, no upload temporanei
        find "$PROJECT_DIR/temp" -name "*.model" -o -name "*.cache" | \
            tar -czf "$app_backup/cache.tar.gz" -T -
        log_info "✓ Cache salvata"
    fi
    
    # Metrics e monitoring data
    if [[ -d "$PROJECT_DIR/monitoring" ]]; then
        cp -r "$PROJECT_DIR/monitoring" "$app_backup/"
        log_info "✓ Configurazione monitoring salvata"
    fi
    
    log_success "Backup dati applicazione completato"
}

# =======================================================================
# POST-BACKUP OPERATIONS
# =======================================================================

create_manifest() {
    log_step "Creazione manifest backup..."
    
    local manifest="$BACKUP_DIR/MANIFEST.json"
    
    cat > "$manifest" << EOF
{
    "backup_info": {
        "timestamp": "$TIMESTAMP",
        "version": "2.0.0",
        "type": "full",
        "hostname": "$(hostname)",
        "user": "$(whoami)",
        "path": "$BACKUP_DIR"
    },
    "system_info": {
        "os": "$(uname -s)",
        "kernel": "$(uname -r)",
        "arch": "$(uname -m)",
        "docker_version": "$(docker --version | cut -d' ' -f3 | cut -d',' -f1)",
        "compose_version": "$(docker-compose --version | cut -d' ' -f4 | cut -d',' -f1)"
    },
    "backup_contents": {
        "configuration": $([ -d "$BACKUP_DIR/configuration" ] && echo "true" || echo "false"),
        "documents": $([ -f "$BACKUP_DIR/documents.tar.gz" ] || [ -d "$BACKUP_DIR/documents" ] && echo "true" || echo "false"),
        "database": $([ -d "$BACKUP_DIR/database" ] && echo "true" || echo "false"),
        "logs": $([ -f "$BACKUP_DIR/logs.tar.gz" ] && echo "true" || echo "false"),
        "application": $([ -d "$BACKUP_DIR/application" ] && echo "true" || echo "false")
    },
    "sizes": {
        "configuration": "$(get_dir_size "$BACKUP_DIR/configuration")",
        "documents": "$(get_dir_size "$BACKUP_DIR/documents")",
        "database": "$(get_dir_size "$BACKUP_DIR/database")",
        "total": "$(get_dir_size "$BACKUP_DIR")"
    },
    "checksums": {
EOF

    # Genera checksums
    find "$BACKUP_DIR" -type f \( -name "*.tar.gz" -o -name "*.json" -o -name "*.sql" \) | \
    while read -r file; do
        local filename basename checksum
        filename=$(basename "$file")
        checksum=$(sha256sum "$file" | cut -d' ' -f1)
        echo "        \"$filename\": \"$checksum\"," >> "$manifest"
    done
    
    # Rimuovi ultima virgola e chiudi JSON
    sed -i '$ s/,$//' "$manifest"
    echo "    }" >> "$manifest"
    echo "}" >> "$manifest"
    
    log_success "Manifest creato: $(basename "$manifest")"
}

encrypt_backup() {
    if [[ $ENCRYPT_BACKUP != true ]]; then
        return 0
    fi
    
    log_step "Crittografia backup..."
    
    local encrypted_file="$BACKUP_DIR.tar.gz.gpg"
    
    # Comprimi e cripta in un solo passaggio
    tar -czf - -C "$BACKUP_ROOT" "$(basename "$BACKUP_DIR")" | \
    gpg --cipher-algo AES256 --compress-algo 1 --symmetric \
        --output "$encrypted_file"
    
    if [[ -f "$encrypted_file" ]]; then
        # Rimuovi directory non crittografata
        rm -rf "$BACKUP_DIR"
        log_success "Backup crittografato: $(basename "$encrypted_file")"
    else
        log_error "Errore nella crittografia"
        exit 1
    fi
}

cleanup_old_backups() {
    log_step "Pulizia backup obsoleti..."
    
    # Trova backup più vecchi di RETENTION_DAYS
    local old_backups
    old_backups=$(find "$BACKUP_ROOT" -maxdepth 1 -type d -name "backup_*" -mtime +$RETENTION_DAYS 2>/dev/null || true)
    
    if [[ -n "$old_backups" ]]; then
        echo "$old_backups" | while read -r old_backup; do
            if [[ -d "$old_backup" ]]; then
                local backup_age
                backup_age=$(( ($(date +%s) - $(stat -c %Y "$old_backup")) / 86400 ))
                log_info "Rimozione backup di $backup_age giorni: $(basename "$old_backup")"
                rm -rf "$old_backup"
            fi
        done
    else
        log_info "Nessun backup obsoleto da rimuovere"
    fi
    
    # Cleanup anche file crittografati
    find "$BACKUP_ROOT" -name "backup_*.tar.gz.gpg" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
    
    log_success "Pulizia completata"
}

# =======================================================================
# REMOTE BACKUP (opzionale)
# =======================================================================

sync_to_remote() {
    if [[ $REMOTE_BACKUP != true ]]; then
        return 0
    fi
    
    log_step "Sincronizzazione backup remoto..."
    
    # Configurazione remote (da variabili ambiente)
    local remote_host="${BACKUP_REMOTE_HOST:-}"
    local remote_path="${BACKUP_REMOTE_PATH:-}"
    local remote_user="${BACKUP_REMOTE_USER:-}"
    
    if [[ -z "$remote_host" || -z "$remote_path" ]]; then
        log_warn "Configurazione backup remoto incompleta"
        return 1
    fi
    
    local rsync_cmd="rsync -avz --progress"
    if [[ -n "$remote_user" ]]; then
        rsync_cmd="$rsync_cmd $BACKUP_DIR $remote_user@$remote_host:$remote_path"
    else
        rsync_cmd="$rsync_cmd $BACKUP_DIR $remote_host:$remote_path"
    fi
    
    if eval "$rsync_cmd"; then
        log_success "Backup sincronizzato con $remote_host"
    else
        log_error "Errore nella sincronizzazione remota"
        return 1
    fi
}

# =======================================================================
# MAIN BACKUP PROCESS
# =======================================================================

show_backup_summary() {
    log_step "Riepilogo backup completato"
    
    echo
    echo -e "${CYAN}=======================================================================${NC}"
    echo -e "${CYAN}                    BACKUP COMPLETATO SUCCESSFULLY${NC}"
    echo -e "${CYAN}=======================================================================${NC}"
    echo
    echo -e "${WHITE}📁 Directory backup:${NC} $BACKUP_DIR"
    echo -e "${WHITE}📅 Timestamp:${NC} $TIMESTAMP"
    echo -e "${WHITE}💾 Dimensione totale:${NC} $(get_dir_size "$BACKUP_DIR")"
    echo -e "${WHITE}🔄 Retention:${NC} $RETENTION_DAYS giorni"
    echo
    echo -e "${WHITE}📦 Contenuti inclusi:${NC}"
    
    if [[ $INCLUDE_CONFIG == true ]]; then
        echo -e "   ✅ Configurazioni ($(get_dir_size "$BACKUP_DIR/configuration"))"
    fi
    
    if [[ $INCLUDE_DOCUMENTS == true ]]; then
        if [[ -f "$BACKUP_DIR/documents.tar.gz" ]]; then
            echo -e "   ✅ Documenti ($(get_dir_size "$BACKUP_DIR/documents.tar.gz"))"
        elif [[ -d "$BACKUP_DIR/documents" ]]; then
            echo -e "   ✅ Documenti ($(get_dir_size "$BACKUP_DIR/documents"))"
        fi
    fi
    
    if [[ $INCLUDE_DATABASE == true ]]; then
        echo -e "   ✅ Database Qdrant ($(get_dir_size "$BACKUP_DIR/database"))"
    fi
    
    if [[ $INCLUDE_LOGS == true && -f "$BACKUP_DIR/logs.tar.gz" ]]; then
        echo -e "   ✅ Logs ($(get_dir_size "$BACKUP_DIR/logs.tar.gz"))"
    fi
    
    echo
    echo -e "${WHITE}🔧 Comandi di ripristino:${NC}"
    echo -e "   make restore"
    echo -e "   ./scripts/restore.sh $BACKUP_DIR"
    echo
    echo -e "${CYAN}=======================================================================${NC}"
}

# =======================================================================
# MAIN EXECUTION
# =======================================================================

main() {
    echo -e "${CYAN}=======================================================================${NC}"
    echo -e "${CYAN}           KNOWLEDGE BASE SYSTEM v2.0 - BACKUP SCRIPT${NC}"
    echo -e "${CYAN}=======================================================================${NC}"
    echo
    
    log_info "🔄 Avvio backup sistema..."
    log_info "📅 Timestamp: $TIMESTAMP"
    
    # Controlli preliminari
    check_prerequisites
    check_services
    
    # Crea directory backup
    mkdir -p "$BACKUP_DIR"
    log_info "📁 Directory backup: $BACKUP_DIR"
    
    # Esegui backup componenti
    backup_configuration
    backup_documents
    backup_database
    backup_logs
    backup_application_data
    
    # Post-processing
    create_manifest
    encrypt_backup
    
    # Cleanup
    cleanup_old_backups
    
    # Remote sync (se configurato)
    sync_to_remote
    
    # Summary
    show_backup_summary
    
    log_success "🎉 Backup completato con successo!"
}

# Controllo se lo script è eseguito direttamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi