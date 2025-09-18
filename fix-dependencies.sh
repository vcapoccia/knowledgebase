#!/usr/bin/env bash
# KB Search - Fix Dependencies Script
# Risolve problemi di dipendenze del pacchetto .deb

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${BLUE}[FIX]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check current status
check_dependencies() {
    log "Controllo dipendenze correnti..."
    
    # Check Docker
    if command -v docker >/dev/null 2>&1; then
        local docker_version
        docker_version=$(docker --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
        log "Docker versione: $docker_version"
        
        # Extract major version
        local major_version
        major_version=$(echo "$docker_version" | cut -d. -f1)
        
        if (( major_version >= 20 )); then
            success "Docker versione accettabile per KB Search"
            echo "export DOCKER_OK=true"
        else
            warn "Docker versione troppo vecchia: $docker_version"
            echo "export DOCKER_OK=false"
        fi
    else
        error "Docker non installato"
        echo "export DOCKER_OK=false"
    fi
    
    # Check jq
    if command -v jq >/dev/null 2>&1; then
        success "jq già installato"
        echo "export JQ_OK=true"
    else
        warn "jq non installato"
        echo "export JQ_OK=false"
    fi
    
    # Check bc
    if command -v bc >/dev/null 2>&1; then
        success "bc già installato"
        echo "export BC_OK=true"
    else
        warn "bc non installato"
        echo "export BC_OK=false"
    fi
    
    # Check docker-compose
    if docker compose version >/dev/null 2>&1; then
        success "Docker Compose v2 disponibile"
        echo "export COMPOSE_OK=true"
    else
        warn "Docker Compose v2 non disponibile"
        echo "export COMPOSE_OK=false"
    fi
}

# Install missing basic dependencies
install_basic_deps() {
    log "Installazione dipendenze base..."
    
    local to_install=()
    
    if ! command -v jq >/dev/null 2>&1; then
        to_install+=("jq")
    fi
    
    if ! command -v bc >/dev/null 2>&1; then
        to_install+=("bc")
    fi
    
    if ! command -v curl >/dev/null 2>&1; then
        to_install+=("curl")
    fi
    
    if [[ ${#to_install[@]} -gt 0 ]]; then
        log "Installando: ${to_install[*]}"
        sudo apt-get update
        sudo apt-get install -y "${to_install[@]}"
        success "Dipendenze base installate"
    else
        success "Dipendenze base già presenti"
    fi
}

# Create relaxed package with looser dependencies
create_relaxed_package() {
    local original_package="$1"
    
    log "Creazione pacchetto con dipendenze meno stringenti..."
    
    # Create temp directory
    local temp_dir
    temp_dir=$(mktemp -d)
    
    # Extract original package
    dpkg-deb --extract "$original_package" "$temp_dir"
    dpkg-deb --control "$original_package" "$temp_dir/DEBIAN"
    
    # Modify control file
    sed -i 's/docker\.io (>= 24\.0)/docker.io (>= 20.0)/' "$temp_dir/DEBIAN/control"
    
    # Create new package
    local new_package
    new_package=$(basename "$original_package" .deb)-relaxed.deb
    
    dpkg-deb --build "$temp_dir" "$new_package"
    
    # Cleanup
    rm -rf "$temp_dir"
    
    success "Pacchetto modificato: $new_package"
    echo "$new_package"
}

# Test Docker functionality
test_docker() {
    log "Test funzionalità Docker..."
    
    # Test docker command
    if docker --version >/dev/null 2>&1; then
        success "Docker command funziona"
    else
        error "Docker command non funziona"
        return 1
    fi
    
    # Test docker service
    if sudo systemctl is-active --quiet docker; then
        success "Servizio Docker attivo"
    else
        warn "Servizio Docker non attivo, avvio..."
        sudo systemctl start docker
        sudo systemctl enable docker
    fi
    
    # Test docker compose
    if docker compose version >/dev/null 2>&1; then
        success "Docker Compose v2 funziona"
    else
        warn "Docker Compose v2 non disponibile"
        
        # Try to install compose plugin
        if command -v docker >/dev/null 2>&1; then
            log "Tentativo installazione compose plugin..."
            sudo apt-get update
            sudo apt-get install -y docker-compose-plugin 2>/dev/null || {
                warn "Impossibile installare compose plugin via apt"
                warn "Usa docker-compose legacy se disponibile"
            }
        fi
    fi
    
    # Test docker permissions
    if docker ps >/dev/null 2>&1; then
        success "Permessi Docker OK"
    else
        warn "Problemi permessi Docker"
        log "Aggiunta utente al gruppo docker..."
        sudo usermod -aG docker "$USER"
        warn "RIAVVIA la sessione per applicare i permessi!"
    fi
}

# Main installation with dependency fixes
install_with_fixes() {
    local package_file="$1"
    
    log "Installazione KB Search con fix dipendenze..."
    
    # Install basic dependencies first
    install_basic_deps
    
    # Try normal installation first
    log "Tentativo installazione normale..."
    if sudo dpkg -i "$package_file" 2>/dev/null; then
        success "Installazione completata senza problemi"
        return 0
    fi
    
    log "Installazione normale fallita, applicando fix..."
    
    # Create relaxed package
    local relaxed_package
    relaxed_package=$(create_relaxed_package "$package_file")
    
    # Install relaxed package
    log "Installazione pacchetto modificato..."
    sudo dpkg -i "$relaxed_package"
    
    # Fix any remaining issues
    log "Fix problemi rimanenti..."
    sudo apt-get install -f -y
    
    # Test functionality
    test_docker
    
    success "Installazione completata con fix"
}

# Show post-install status
show_status() {
    log "Stato post-installazione..."
    
    # Package status
    if dpkg -l | grep -q kbsearch; then
        success "Pacchetto KB Search installato"
    else
        error "Pacchetto KB Search non installato"
        return 1
    fi
    
    # Service status
    if systemctl is-enabled --quiet kbsearch 2>/dev/null; then
        success "Servizio KB Search abilitato"
    else
        warn "Servizio KB Search non abilitato"
    fi
    
    # Command availability
    local commands=("kb-setup" "kb-ingest-monitor")
    for cmd in "${commands[@]}"; do
        if command -v "$cmd" >/dev/null 2>&1; then
            success "Comando $cmd disponibile"
        else
            warn "Comando $cmd non trovato"
        fi
    done
    
    # Docker status
    if docker --version >/dev/null 2>&1; then
        local docker_version
        docker_version=$(docker --version)
        success "Docker: $docker_version"
    else
        error "Docker non funzionante"
    fi
    
    echo
    echo -e "${GREEN}🎉 KB Search ready!${NC}"
    echo
    echo -e "${BLUE}Prossimi passi:${NC}"
    echo "  1. Configura: sudo nano /etc/kbsearch/.env"
    echo "  2. Avvia: sudo systemctl start kbsearch"
    echo "  3. Status: kb-setup status"
    echo "  4. Accesso web: http://$(hostname -I | awk '{print $1}')"
}

# Main function
main() {
    local command="${1:-auto}"
    
    echo -e "${BLUE}🔧 KB Search Dependency Fixer${NC}"
    echo -e "${BLUE}==============================${NC}"
    echo
    
    case "$command" in
        check)
            eval "$(check_dependencies)"
            ;;
        install-deps)
            install_basic_deps
            ;;
        test-docker)
            test_docker
            ;;
        auto)
            # Find .deb package
            local package_file
            package_file=$(find . -name "kbsearch_*.deb" | head -1)
            
            if [[ -z "$package_file" ]]; then
                # No package found, assume already installed
                log "Nessun pacchetto .deb trovato, assumo già installato"
                install_basic_deps
                test_docker
                show_status
            else
                # Install with fixes
                install_with_fixes "$package_file"
                show_status
            fi
            ;;
        status)
            show_status
            ;;
        help)
            echo "KB Search Dependency Fixer"
            echo ""
            echo "USAGE: $0 [command]"
            echo ""
            echo "COMMANDS:"
            echo "  auto         Fix automatico completo (default)"
            echo "  check        Controlla dipendenze"
            echo "  install-deps Installa dipendenze base"
            echo "  test-docker  Testa funzionalità Docker"
            echo "  status       Mostra stato installazione"
            ;;
        *)
            error "Comando sconosciuto: $command"
            echo "Usa '$0 help' per l'aiuto"
            exit 1
            ;;
    esac
}

main "$@"
