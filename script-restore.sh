#!/bin/bash
# =======================================================================
# KNOWLEDGEBASE RESTORE SCRIPT
# Script di ripristino completo per Knowledge Base System v2.0
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
BACKUP_DIR=""
FORCE_RESTORE=false
DRY_RUN=false
RESTORE_COMPONENTS=()

# =======================================================================
# UTILITY FUNCTIONS
# =======================================================================

usage() {
    cat << EOF
Usage: $0 [OPTIONS] [BACKUP_PATH]

Ripristina il Knowledge Base System da un backup

OPTIONS:
    -f, --force              Forza il ripristino senza conferma
    -n, --dry-run           Simula il ripristino senza eseguirlo
    -c, --component COMP     Ripristina solo il componente specificato
                            (config, documents, database, logs, all)
    -l, --list              Lista tutti i backup disponibili
    -i, --info BACKUP_PATH  Mostra informazioni su un backup
    -h, --help              Mostra questo messaggio di aiuto

ESEMPI:
    $0                      # Ripristina dal backup più recente
    $0 backup_20241125_143000  # Ripristina da backup specifico
    $0 -c database          # Ripristina solo il database
    $0 -l                   # Lista backup disponibili
    $0 -n backup_latest     # Simula ripristino

COMPONENTI:
    config      - Configurazioni (.env, docker-compose.yml, ecc.)
    documents   - Documenti della knowledge base
    database    - Database Qdrant con vettori
    logs        - Log di sistema
    all         - Tutti i componenti (default)

EXIT CODES:
    0 - Ripristino completato con successo
    1 - Errore durante il ripristino
    2 - Errore parametri o file non trovato
EOF
}

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

log_debug() {
    [[ ${DEBUG:-false} == true ]] && echo -e "${CYAN}[DEBUG]${NC} $1" >&2
}

# Conferma interattiva
confirm() {
    if [[ $FORCE_RESTORE == true ]]; then
        return 0
    fi
    
    local message="$1"
    read -p "$(echo -e "${YELLOW}$message [y/N]: ${NC}")" -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

# Controlla se comando esiste
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# =======================================================================
# BACKUP MANAGEMENT
# =======================================================================

list_available_backups() {
    log_step "Backup disponibili:"
    echo
    
    local backup_found=false
    
    # Lista backup directory
    if [[ -d "$BACKUP_ROOT" ]]; then
        while IFS= read -r -d '' backup_dir; do
            backup_found=true
            local backup_name timestamp size
            backup_name=$(basename "$backup_dir")
            timestamp=$(echo "$backup_name" | sed 's/backup_//' | sed 's/_/ /')
            size=$(du -sh "$backup_dir" 2>/dev/null | cut -f1 || echo "N/A")
            
            echo -e "${WHITE}📦 $backup_name${NC}"
            echo -e "   📅 Data: $timestamp"
            echo -e "   💾 Dimensione: $size"
            
            # Leggi manifest se disponibile
            if [[ -f "$backup_dir/MANIFEST.json" ]]; then
                local backup_type contents
                backup_type=$(jq -r '.backup_info.type // "unknown"' "$backup_dir/MANIFEST.json" 2>/dev/null || echo "unknown")
                echo -e "   🏷️  Tipo: $backup_type"
                
                # Mostra contenuti
                local config_included docs_included db_included
                config_included=$(jq -r '.backup_contents.configuration // false' "$backup_dir/MANIFEST.json" 2>/dev/null || echo "false")
                docs_included=$(jq -r '.backup_contents.documents // false' "$backup_dir/MANIFEST.json" 2>/dev/null || echo "false")
                db_included=$(jq -r '.backup_contents.database // false' "$backup_dir/MANIFEST.json" 2>/dev/null || echo "false")
                
                echo -n "   📋 Contenuti: "
                [[ $config_included == "true" ]] && echo -n "Config "
                [[ $docs_included == "true" ]] && echo -n "Docs "
                [[ $db_included == "true" ]] && echo -n "DB "
                echo
            fi
            echo
        done < <(find "$BACKUP_ROOT" -maxdepth 1 -type d -name "backup_*" -print0 | sort -z)
    fi
    
    # Lista backup crittografati
    if find "$BACKUP_ROOT" -name "backup_*.tar.gz.gpg" -print -quit | grep -q .; then
        echo -e "${WHITE}🔐 Backup crittografati:${NC}"
        find "$BACKUP_ROOT" -name "backup_*.tar.gz.gpg" | sort | while read -r encrypted_backup; do
            local backup_name size
            backup_name=$(basename "$encrypted_backup" .tar.gz.gpg)
            size=$(du -sh "$encrypted_backup" 2>/dev/null | cut -f1 || echo "N/A")
            echo -e "   🔒 $backup_name ($size) - Richiede decrittografia"
        done
        echo
        backup_found=true
    fi
    
    if [[ $backup_found == false ]]; then
        log_warn "Nessun backup trovato in $BACKUP_ROOT"
        return 1
    fi
}

find_latest_backup() {
    find "$BACKUP_ROOT" -maxdepth 1 -type d -name "backup_*" | sort | tail -n1
}

show_backup_info() {
    local backup_path="$1"
    
    if [[ ! -d "$backup_path" ]]; then
        log_error "Backup non trovato: $backup_path"
        return 1
    fi
    
    log_step "Informazioni backup: $(basename "$backup_path")"
    echo
    
    # Informazioni base
    local size timestamp
    size=$(du -sh "$backup_path" | cut -f1)
    timestamp=$(stat -c %y "$backup_path" | cut -d' ' -f1,2)
    
    echo -e "${WHITE}📁 Percorso:${NC} $backup_path"
    echo -e "${WHITE}💾 Dimensione:${NC} $size"
    echo -e "${WHITE}📅 Creato:${NC} $timestamp"
    echo
    
    # Leggi manifest se disponibile
    if [[ -f "$backup_path/MANIFEST.json" ]]; then
        echo -e "${WHITE}📋 Dettagli dal manifest:${NC}"
        
        # Info generali
        local version backup_type hostname user
        version=$(jq -r '.backup_info.version // "unknown"' "$backup_path/MANIFEST.json")
        backup_type=$(jq -r '.backup_info.type // "unknown"' "$backup_path/MANIFEST.json")
        hostname=$(jq -r '.backup_info.hostname // "unknown"' "$backup_path/MANIFEST.json")
        user=$(jq -r '.backup_info.user // "unknown"' "$backup_path/MANIFEST.json")
        
        echo -e "   Versione: $version"
        echo -e "   Tipo: $backup_type"
        echo -e "   Host: $hostname"
        echo -e "   Utente: $user"
        echo
        
        # Contenuti
        echo -e "${WHITE}📦 Contenuti:${NC}"
        jq -r '.backup_contents | to_entries[] | select(.value == true) | "   ✅ " + .key' "$backup_path/MANIFEST.json"
        jq -r '.backup_contents | to_entries[] | select(.value == false) | "   ❌ " + .key' "$backup_path/MANIFEST.json"
        echo
        
        # Dimensioni
        echo -e "${WHITE}📏 Dimensioni componenti:${NC}"
        jq -r '.sizes | to_entries[] | "   " + .key + ": " + .value' "$backup_path/MANIFEST.json"
    else
        log_warn "Manifest non trovato, informazioni limitate"
        
        # Mostra contenuti directory
        echo -e "${WHITE}📁 Contenuti directory:${NC}"
        find "$backup_path" -maxdepth 2 -type d | sed 's|'$backup_path'||' | sed 's|^/||' | sort | while read -r item; do
            [[ -n "$item" ]] && echo "   📁 $item"
        done
        
        find "$backup_path" -maxdepth 1 -type f -name "*.tar.gz" | while read -r item; do
            local name size
            name=$(basename "$item")
            size=$(du -sh "$item" | cut -f1)
            echo "   📄 $name ($size)"
        done
    fi
}

# =======================================================================
# RESTORE FUNCTIONS
# =======================================================================

validate_backup() {
    local backup_path="$1"
    
    log_step "Validazione backup..."
    
    # Controlla se è directory o file crittografato
    if [[ -f "$backup_path.tar.gz.gpg" ]]; then
        log_info "Backup crittografato trovato: $backup_path.tar.gz.gpg"
        return 0
    elif [[ ! -d "$backup_path" ]]; then
        log_error "Backup non trovato: $backup_path"
        return 1
    fi
    
    # Verifica manifest
    if [[ -f "$backup_path/MANIFEST.json" ]]; then
        if ! jq empty "$backup_path/MANIFEST.json" 2>/dev/null; then
            log_error "Manifest corrotto: $backup_path/MANIFEST.json"
            return 1
        fi
        log_info "✅ Manifest valido"
    else
        log_warn "⚠️  Manifest mancante, controlli limitati"
    fi
    
    # Verifica checksums se disponibili
    if [[ -f "$backup_path/MANIFEST.json" ]]; then
        local checksums_available
        checksums_available=$(jq -r '.checksums // {}' "$backup_path/MANIFEST.json" | jq 'length')
        
        if [[ $checksums_available -gt 0 ]]; then
            log_info "Verifica checksums..."
            local checksum_errors=0
            
            jq -r '.checksums | to_entries[] | "\(.key) \(.value)"' "$backup_path/MANIFEST.json" | \
            while read -r filename expected_checksum; do
                local file_path="$backup_path/$filename"
                if [[ -f "$file_path" ]]; then
                    local actual_checksum
                    actual_checksum=$(sha256sum "$file_path" | cut -d' ' -f1)
                    if [[ "$actual_checksum" != "$expected_checksum" ]]; then
                        log_error "❌ Checksum errato per $filename"
                        ((checksum_errors++))
                    else
                        log_debug "✅ Checksum OK per $filename"
                    fi
                else
                    log_warn "⚠️  File mancante: $filename"
                fi
            done
            
            if [[ $checksum_errors -gt 0 ]]; then
                log_error "Errori di checksum rilevati"
                return 1
            fi
        fi
    fi
    
    log_success "Backup validato con successo"
    return 0
}

decrypt_backup() {
    local encrypted_file="$1"
    local output_dir="$2"
    
    log_step "Decrittografia backup..."
    
    if ! command_exists gpg; then
        log_error "GPG non disponibile per decrittografia"
        return 1
    fi
    
    # Decrittografa e estrai
    if gpg --decrypt "$encrypted_file" | tar -xzf - -C "$output_dir"; then
        log_success "Backup decrittografato e estratto"
        return 0
    else
        log_error "Errore nella decrittografia"
        return 1
    fi
}

pre_restore_checks() {
    log_step "Controlli pre-ripristino..."
    
    # Verifica Docker
    if ! command_exists docker; then
        log_error "Docker non disponibile"
        return 1
    fi
    
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker daemon non in esecuzione"
        return 1
    fi
    
    # Verifica spazio disco
    local backup_size available_space
    backup_size=$(du -s "$BACKUP_DIR" | cut -f1)
    available_space=$(df "$PROJECT_DIR" | tail -n1 | awk '{print $4}')
    
    if [[ $backup_size -gt $available_space ]]; then
        log_error "Spazio disco insufficiente per il ripristino"
        return 1
    fi
    
    log_success "Controlli pre-ripristino completati"
}

stop_services() {
    log_step "Arresto servizi..."
    
    cd "$PROJECT_DIR"
    
    if [[ -f docker-compose.yml ]]; then
        # Ferma servizi
        if docker-compose ps | grep -q "Up"; then
            log_info "Fermando servizi Docker Compose..."
            docker-compose down
            log_success "Servizi fermati"
        else
            log_info "Nessun servizio in esecuzione"
        fi
    else
        log_warn "File docker-compose.yml non trovato"
    fi
}

restore_configuration() {
    if [[ ${#RESTORE_COMPONENTS[@]} -gt 0 ]] && [[ ! " ${RESTORE_COMPONENTS[*]} " =~ " config " ]] && [[ ! " ${RESTORE_COMPONENTS[*]} " =~ " all " ]]; then
        log_info "Ripristino configurazione saltato (non richiesto)"
        return 0
    fi
    
    log_step "Ripristino configurazione..."
    
    local config_backup="$BACKUP_DIR/configuration"
    if [[ ! -d "$config_backup" ]]; then
        log_warn "Backup configurazione non trovato"
        return 0
    fi
    
    # Backup configurazione attuale
    if [[ -f "$PROJECT_DIR/.env" ]]; then
        cp "$PROJECT_DIR/.env" "$PROJECT_DIR/.env.backup.$(date +%Y%m%d_%H%M%S)"
        log_info "Backup configurazione attuale creato"
    fi
    
    # Ripristina file configurazione
    local config_files=(
        ".env"
        "docker-compose.yml"
        "docker-compose.override.yml"
        "Makefile"
    )
    
    for file in "${config_files[@]}"; do
        if [[ -f "$config_backup/$file" ]]; then
            if [[ $DRY_RUN == true ]]; then
                log_info "[DRY RUN] Ripristinerei: $file"
            else
                cp "$config_backup/$file" "$PROJECT_DIR/"
                log_info "✅ Ripristinato: $file"
            fi
        fi
    done
    
    # Ripristina directory config
    if [[ -d "$config_backup/config" ]]; then
        if [[ $DRY_RUN == true ]]; then
            log_info "[DRY RUN] Ripristinerei directory config"
        else
            rm -rf "$PROJECT_DIR/config"
            cp -r "$config_backup/config" "$PROJECT_DIR/"
            log_info "✅ Ripristinata directory config"
        fi
    fi
    
    # Ripristina script
    if [[ -d "$config_backup/scripts" ]]; then
        if [[ $DRY_RUN == true ]]; then
            log_info "[DRY RUN] Ripristinerei directory scripts"
        else
            rm -rf "$PROJECT_DIR/scripts"
            cp -r "$config_backup/scripts" "$PROJECT_DIR/"
            chmod +x "$PROJECT_DIR/scripts"/*.sh
            log_info "✅ Ripristinata directory scripts"
        fi
    fi
    
    log_success "Ripristino configurazione completato"
}

restore_documents() {
    if [[ ${#RESTORE_COMPONENTS[@]} -gt 0 ]] && [[ ! " ${RESTORE_COMPONENTS[*]} " =~ " documents " ]] && [[ ! " ${RESTORE_COMPONENTS[*]} " =~ " all " ]]; then
        log_info "Ripristino documenti saltato (non richiesto)"
        return 0
    fi
    
    log_step "Ripristino documenti..."
    
    # Controlla formato backup documenti
    if [[ -f "$BACKUP_DIR/documents.tar.gz" ]]; then
        log_info "Ripristino da archivio compresso..."
        if [[ $DRY_RUN == true ]]; then
            log_info "[DRY RUN] Estraerei documenti.tar.gz"
        else
            # Backup documenti attuali
            if [[ -d "$PROJECT_DIR/docs" ]]; then
                mv "$PROJECT_DIR/docs" "$PROJECT_DIR/docs.backup.$(date +%Y%m%d_%H%M%S)"
                log_info "Backup documenti attuali creato"
            fi
            
            # Estrai backup
            tar -xzf "$BACKUP_DIR/documents.tar.gz" -C "$PROJECT_DIR/"
            log_success "Documenti estratti da archivio"
        fi
    elif [[ -d "$BACKUP_DIR/documents" ]]; then
        log_info "Ripristino da directory..."
        if [[ $DRY_RUN == true ]]; then
            log_info "[DRY RUN] Copierei directory documents"
        else
            # Backup documenti attuali
            if [[ -d "$PROJECT_DIR/docs" ]]; then
                mv "$PROJECT_DIR/docs" "$PROJECT_DIR/docs.backup.$(date +%Y%m%d_%H%M%S)"
            fi
            
            # Copia documenti
            cp -r "$BACKUP_DIR/documents" "$PROJECT_DIR/docs"
            log_success "Documenti ripristinati da directory"
        fi
    else
        log_warn "Backup documenti non trovato"
        return 0
    fi
    
    # Verifica permessi
    if [[ $DRY_RUN == false && -d "$PROJECT_DIR/docs" ]]; then
        chown -R "$(whoami):$(whoami)" "$PROJECT_DIR/docs" 2>/dev/null || true
        find "$PROJECT_DIR/docs" -type d -exec chmod 755 {} \; 2>/dev/null || true
        find "$PROJECT_DIR/docs" -type f -exec chmod 644 {} \; 2>/dev/null || true
        log_info "Permessi documenti sistemati"
    fi
}

restore_database() {
    if [[ ${#RESTORE_COMPONENTS[@]} -gt 0 ]] && [[ ! " ${RESTORE_COMPONENTS[*]} " =~ " database " ]] && [[ ! " ${RESTORE_COMPONENTS[*]} " =~ " all " ]]; then
        log_info "Ripristino database saltato (non richiesto)"
        return 0
    fi
    
    log_step "Ripristino database Qdrant..."
    
    local db_backup="$BACKUP_DIR/database"
    if [[ ! -d "$db_backup" ]]; then
        log_warn "Backup database non trovato"
        return 0
    fi
    
    # Rimuovi volume esistente
    if docker volume ls | grep -q qdrant_storage; then
        if [[ $DRY_RUN == true ]]; then
            log_info "[DRY RUN] Rimuoverei volume qdrant_storage"
        else
            log_info "Rimozione volume Qdrant esistente..."
            docker volume rm qdrant_storage 2>/dev/null || true
        fi
    fi
    
    # Ripristina da volume backup
    if [[ -f "$db_backup/qdrant_volume.tar.gz" ]]; then
        if [[ $DRY_RUN == true ]]; then
            log_info "[DRY RUN] Ripristinerei volume da archivio"
        else
            log_info "Ripristino volume da archivio..."
            # Crea nuovo volume
            docker volume create qdrant_storage
            # Ripristina dati
            docker run --rm \
                -v qdrant_storage:/data \
                -v "$db_backup":/backup \
                alpine tar xzf /backup/qdrant_volume.tar.gz -C /data
            log_success "Volume Qdrant ripristinato da archivio"
        fi
    elif [[ -d "$db_backup/snapshots" ]]; then
        if [[ $DRY_RUN == true ]]; then
            log_info "[DRY RUN] Ripristinerei da snapshot"
        else
            log_info "Ripristino da snapshot..."
            # Crea nuovo volume e copia snapshot
            docker volume create qdrant_storage
            docker run --rm \
                -v qdrant_storage:/data \
                -v "$db_backup":/backup \
                alpine cp -r /backup/snapshots /data/
            log_success "Snapshot Qdrant ripristinati"
        fi
    else
        log_warn "Nessun backup database compatibile trovato"
    fi
}

start_services() {
    if [[ $DRY_RUN == true ]]; then
        log_info "[DRY RUN] Avvierei servizi Docker Compose"
        return 0
    fi
    
    log_step "Avvio servizi ripristinati..."
    
    cd "$PROJECT_DIR"
    
    if [[ -f docker-compose.yml ]]; then
        # Avvia servizi
        docker-compose up -d
        
        # Aspetta che i servizi siano pronti
        log_info "Attesa avvio servizi..."
        sleep 30
        
        # Verifica salute servizi
        if command_exists ./scripts/health-check.sh; then
            ./scripts/health-check.sh
        else
            log_info "Health check non disponibile"
        fi
        
        log_success "Servizi avviati"
    else
        log_error "File docker-compose.yml non trovato dopo ripristino"
        return 1
    fi
}

# =======================================================================
# MAIN RESTORE PROCESS
# =======================================================================

show_restore_summary() {
    log_step "Riepilogo ripristino completato"
    
    echo
    echo -e "${CYAN}=======================================================================${NC}"
    echo -e "${CYAN}                  RIPRISTINO COMPLETATO SUCCESSFULLY${NC}"
    echo -e "${CYAN}=======================================================================${NC}"
    echo
    echo -e "${WHITE}📁 Backup utilizzato:${NC} $(basename "$BACKUP_DIR")"
    echo -e "${WHITE}🔄 Componenti ripristinati:${NC}"
    
    if [[ ${#RESTORE_COMPONENTS[@]} -eq 0 ]] || [[ " ${RESTORE_COMPONENTS[*]} " =~ " all " ]]; then
        echo -e "   ✅ Tutti i componenti"
    else
        for component in "${RESTORE_COMPONENTS[@]}"; do
            echo -e "   ✅ $component"
        done
    fi
    
    echo
    echo -e "${WHITE}🌐 URL di accesso:${NC}"
    echo -e "   Web UI:        http://localhost"
    echo -e "   API Docs:      http://localhost/api/docs"
    echo -e "   Qdrant UI:     http://localhost:6333/dashboard"
    echo -e "   Health Check:  http://localhost/api/health"
    echo
    echo -e "${WHITE}🔧 Comandi utili:${NC}"
    echo -e "   make status     - Verifica stato servizi"
    echo -e "   make health     - Controllo salute dettagliato"
    echo -e "   make logs       - Visualizza logs"
    echo
    echo -e "${CYAN}=======================================================================${NC}"
}

main() {
    echo -e "${CYAN}=======================================================================${NC}"
    echo -e "${CYAN}          KNOWLEDGE BASE SYSTEM v2.0 - RESTORE SCRIPT${NC}"
    echo -e "${CYAN}=======================================================================${NC}"
    echo
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -f|--force)
                FORCE_RESTORE=true
                shift
                ;;
            -n|--dry-run)
                DRY_RUN=true
                shift
                ;;
            -c|--component)
                RESTORE_COMPONENTS+=("$2")
                shift 2
                ;;
            -l|--list)
                list_available_backups
                exit 0
                ;;
            -i|--info)
                show_backup_info "$2"
                exit 0
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            -*)
                log_error "Opzione sconosciuta: $1"
                usage
                exit 2
                ;;
            *)
                BACKUP_DIR="$BACKUP_ROOT/$1"
                shift
                ;;
        esac
    done
    
    # Se nessun backup specificato, usa il più recente
    if [[ -z "$BACKUP_DIR" ]]; then
        BACKUP_DIR=$(find_latest_backup)
        if [[ -z "$BACKUP_DIR" ]]; then
            log_error "Nessun backup trovato in $BACKUP_ROOT"
            log_info "Usa -l per vedere i backup disponibili"
            exit 2
        fi
        log_info "Usando backup più recente: $(basename "$BACKUP_DIR")"
    fi
    
    # Se componenti vuoti, ripristina tutto
    if [[ ${#RESTORE_COMPONENTS[@]} -eq 0 ]]; then
        RESTORE_COMPONENTS=("all")
    fi
    
    log_info "🔄 Avvio ripristino sistema..."
    log_info "📁 Backup: $(basename "$BACKUP_DIR")"
    log_info "🔧 Componenti: ${RESTORE_COMPONENTS[*]}"
    [[ $DRY_RUN == true ]] && log_info "🧪 Modalità DRY RUN attiva"
    
    # Validazione
    if ! validate_backup "$BACKUP_DIR"; then
        exit 1
    fi
    
    # Mostra informazioni backup
    show_backup_info "$BACKUP_DIR"
    
    # Conferma
    if ! confirm "Procedere con il ripristino?"; then
        log_info "Ripristino annullato dall'utente"
        exit 0
    fi
    
    # Pre-restore checks
    pre_restore_checks
    
    # Stop services
    stop_services
    
    # Restore components
    restore_configuration
    restore_documents
    restore_database
    
    # Start services
    start_services
    
    # Summary
    if [[ $DRY_RUN == true ]]; then
        log_info "🧪 DRY RUN completato - nessuna modifica effettuata"
    else
        show_restore_summary
        log_success "🎉 Ripristino completato con successo!"
    fi
}

# Controllo se lo script è eseguito direttamente
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi