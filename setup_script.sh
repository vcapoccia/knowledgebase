#!/usr/bin/env bash
# KB Search - Automated Setup and Deployment Script
# Usage: ./setup.sh [install|update|backup|restore|status|logs]

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="kbsearch"
INSTALL_DIR="/etc/${APP_NAME}"
SERVICE_USER="kbsearch"
DATA_DIR="/var/lib/${APP_NAME}"
BACKUP_DIR="/var/backups/${APP_NAME}"
LOG_DIR="/var/log/${APP_NAME}"

# Functions
log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1" >&2
}

fatal() {
    error "$1"
    exit 1
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        fatal "Non eseguire questo script come root. Usa sudo quando richiesto."
    fi
}

# Check system requirements
check_requirements() {
    log "Controllo requisiti sistema..."
    
    # Check OS
    if ! grep -q "Ubuntu\|Debian" /etc/os-release; then
        warn "OS non testato. Supporto garantito per Ubuntu/Debian"
    fi
    
    # Check Docker
    if ! command -v docker >/dev/null 2>&1; then
        fatal "Docker non installato. Installa Docker prima di continuare."
    fi
    
    # Check Docker Compose
    if ! docker compose version >/dev/null 2>&1; then
        fatal "Docker Compose v2 non disponibile. Aggiorna Docker."
    fi
    
    # Check available disk space (need at least 10GB)
    local available_kb=$(df / | awk 'NR==2 {print $4}')
    local available_gb=$((available_kb / 1024 / 1024))
    if (( available_gb < 10 )); then
        fatal "Spazio disco insufficiente. Richiesti almeno 10GB, disponibili ${available_gb}GB"
    fi
    
    # Check memory (recommend at least 8GB)
    local total_mem_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    local total_mem_gb=$((total_mem_kb / 1024 / 1024))
    if (( total_mem_gb < 8 )); then
        warn "RAM limitata (${total_mem_gb}GB). Raccomandati almeno 8GB per performance ottimali."
    fi
    
    # Check GPU (optional)
    if command -v nvidia-smi >/dev/null 2>&1; then
        success "GPU NVIDIA rilevata - embedding accelerati disponibili"
    else
        log "GPU non rilevata - verrà usata CPU per embedding"
    fi
    
    success "Requisiti sistema verificati"
}

# Create system user and directories
setup_system() {
    log "Setup sistema..."
    
    # Create system user
    if ! id "$SERVICE_USER" >/dev/null 2>&1; then
        sudo useradd -r -s /bin/false -d "$DATA_DIR" -c "KB Search Service" "$SERVICE_USER"
        success "Utente sistema '$SERVICE_USER' creato"
    fi
    
    # Create directories
    local dirs=("$INSTALL_DIR" "$DATA_DIR" "$BACKUP_DIR" "$LOG_DIR")
    for dir in "${dirs[@]}"; do
        sudo mkdir -p "$dir"
        sudo chown "$SERVICE_USER:$SERVICE_USER" "$dir"
    done
    
    # Add current user to docker group
    if ! groups | grep -q docker; then
        sudo usermod -aG docker "$USER"
        warn "Aggiunto $USER al gruppo docker. LOGOUT/LOGIN richiesto!"
    fi
    
    success "Sistema configurato"
}

# Install application files
install_app() {
    log "Installazione applicazione..."
    
    # Copy application files
    sudo cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/"
    
    # Set permissions
    sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
    sudo chmod +x "$INSTALL_DIR/bin/"*.sh
    
    # Create .env if it doesn't exist
    if [[ ! -f "$INSTALL_DIR/.env" ]]; then
        sudo cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
        
        # Generate secure tokens
        local admin_token=$(openssl rand -hex 32)
        local grafana_pass=$(openssl rand -base64 16)
        
        sudo sed -i "s/ADMIN_TOKEN=.*/ADMIN_TOKEN=$admin_token/" "$INSTALL_DIR/.env"
        sudo sed -i "s/GRAFANA_PASSWORD=.*/GRAFANA_PASSWORD=$grafana_pass/" "$INSTALL_DIR/.env"
        
        success "File .env creato con token sicuri"
    fi
    
    # Create systemd service
    create_systemd_service
    
    success "Applicazione installata in $INSTALL_DIR"
}

# Create systemd service for management
create_systemd_service() {
    local service_file="/etc/systemd/system/${APP_NAME}.service"
    
    sudo tee "$service_file" >/dev/null <<EOF
[Unit]
Description=KB Search Knowledge Base
Documentation=https://github.com/yourorg/kbsearch
Requires=docker.service
After=docker.service
StartLimitIntervalSec=0

[Service]
Type=oneshot
RemainAfterExit=yes
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/docker compose up -d qdrant kb-api kb-ui caddy
ExecStop=/usr/bin/docker compose down
ExecReload=/usr/bin/docker compose restart
TimeoutStartSec=300
TimeoutStopSec=120
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    sudo systemctl enable "$APP_NAME"
    
    success "Servizio systemd creato: $service_file"
}

# Setup KB data directories
setup_kb_directories() {
    log "Setup directory Knowledge Base..."
    
    local kb_root="/mnt/kb"
    
    # Prompt for KB location
    echo
    read -p "Percorso della Knowledge Base [$kb_root]: " user_kb_root
    kb_root="${user_kb_root:-$kb_root}"
    
    # Create KB directories if they don't exist
    if [[ ! -d "$kb_root" ]]; then
        read -p "Directory $kb_root non esiste. Crearla? [y/N]: " create_kb
        if [[ "$create_kb" =~ ^[Yy]$ ]]; then
            sudo mkdir -p "$kb_root"/{_Gare,_AQ}
            sudo chown -R "$USER:$USER" "$kb_root"
            success "Directory KB create: $kb_root"
        else
            warn "Directory KB non creata. Configurale manualmente prima dell'avvio."
        fi
    fi
    
    # Update .env with correct paths
    sudo sed -i "s|KB_ROOT=.*|KB_ROOT=$kb_root|" "$INSTALL_DIR/.env"
    sudo sed -i "s|KB_GARE_DIR=.*|KB_GARE_DIR=$kb_root/_Gare|" "$INSTALL_DIR/.env"
    sudo sed -i "s|KB_AQ_DIR=.*|KB_AQ_DIR=$kb_root/_AQ|" "$INSTALL_DIR/.env"
    
    success "Directory KB configurate"
}

# Configure firewall
setup_firewall() {
    if command -v ufw >/dev/null 2>&1; then
        log "Configurazione firewall..."
        
        # Allow SSH
        sudo ufw allow ssh >/dev/null 2>&1
        
        # Allow HTTP/HTTPS
        sudo ufw allow 80/tcp >/dev/null 2>&1
        sudo ufw allow 443/tcp >/dev/null 2>&1
        
        # Allow API port (optional, if exposed)
        read -p "Esporre porta API 8080 esternamente? [y/N]: " expose_api
        if [[ "$expose_api" =~ ^[Yy]$ ]]; then
            sudo ufw allow 8080/tcp >/dev/null 2>&1
            success "Porta API 8080 esposta"
        fi
        
        # Enable UFW if not active
        if ! sudo ufw status | grep -q "Status: active"; then
            sudo ufw --force enable >/dev/null 2>&1
            success "Firewall attivato"
        fi
    fi
}

# Start services
start_services() {
    log "Avvio servizi..."
    
    cd "$INSTALL_DIR"
    
    # Start core services
    sudo systemctl start "$APP_NAME"
    
    # Wait for services to be ready
    log "Attendo che i servizi siano pronti..."
    local max_attempts=30
    local attempt=0
    
    while (( attempt < max_attempts )); do
        if curl -sf http://localhost/api/health >/dev/null 2>&1; then
            success "Servizi avviati e raggiungibili"
            return 0
        fi
        
        ((attempt++))
        sleep 2
        echo -n "."
    done
    
    error "Timeout avvio servizi. Controlla i logs."
    return 1
}

# Install function
install() {
    echo -e "${PURPLE}"
    echo "╔══════════════════════════════════════════╗"
    echo "║        KB Search - Installation          ║"
    echo "╚══════════════════════════════════════════╝"
    echo -e "${NC}"
    
    check_requirements
    setup_system
    install_app
    setup_kb_directories
    setup_firewall
    
    # Ask to start services
    echo
    read -p "Avviare i servizi ora? [Y/n]: " start_now
    if [[ ! "$start_now" =~ ^[Nn]$ ]]; then
        start_services
        show_status
        
        echo
        success "✨ Installazione completata!"
        echo
        echo -e "${GREEN}Accedi alla Knowledge Base:${NC}"
        echo -e "  🌐 Web UI: ${BLUE}http://$(hostname -I | awk '{print $1}')/${NC}"
        echo -e "  🔧 API:    ${BLUE}http://$(hostname -I | awk '{print $1}')/api/${NC}"
        echo
        echo -e "${YELLOW}Prossimi passi:${NC}"
        echo "  1. Aggiungi documenti nelle directory KB"
        echo "  2. Esegui il primo ingest: sudo $INSTALL_DIR/bin/kb-ingest-monitor.sh start"
        echo "  3. Configura DNS: kb.local -> $(hostname -I | awk '{print $1}')"
        echo
        echo -e "${BLUE}Gestione servizio:${NC}"
        echo "  systemctl status $APP_NAME"
        echo "  systemctl restart $APP_NAME"
        echo "  $INSTALL_DIR/bin/kb-ingest-monitor.sh status"
    fi
}

# Update function
update() {
    log "Aggiornamento applicazione..."
    
    # Backup current version
    backup_config
    
    # Stop services
    sudo systemctl stop "$APP_NAME"
    
    # Update files (preserve .env)
    local temp_env="/tmp/.env.backup"
    sudo cp "$INSTALL_DIR/.env" "$temp_env"
    
    sudo rsync -av --exclude='.env' --exclude='run/*' "$SCRIPT_DIR/" "$INSTALL_DIR/"
    
    sudo cp "$temp_env" "$INSTALL_DIR/.env"
    sudo rm "$temp_env"
    
    # Set permissions
    sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
    sudo chmod +x "$INSTALL_DIR/bin/"*.sh
    
    # Restart services
    sudo systemctl start "$APP_NAME"
    
    success "Aggiornamento completato"
}

# Backup configuration and data
backup_config() {
    log "Backup configurazione..."
    
    local backup_file="$BACKUP_DIR/config-$(date +%Y%m%d-%H%M%S).tar.gz"
    sudo mkdir -p "$BACKUP_DIR"
    
    sudo tar -czf "$backup_file" \
        -C "$(dirname "$INSTALL_DIR")" "$(basename "$INSTALL_DIR")" \
        --exclude="$(basename "$INSTALL_DIR")/run" 2>/dev/null || true
    
    success "Backup salvato: $backup_file"
}

# Show status
show_status() {
    echo -e "\n${BLUE}=== STATO KB SEARCH ===${NC}"
    
    # System service
    if sudo systemctl is-active --quiet "$APP_NAME"; then
        success "Servizio sistema: ATTIVO"
    else
        error "Servizio sistema: INATTIVO"
    fi
    
    # Docker containers
    cd "$INSTALL_DIR" 2>/dev/null || fatal "Directory installazione non trovata"
    
    local containers
    containers=$(sudo docker compose ps --format "table {{.Service}}\t{{.Status}}" 2>/dev/null || echo "")
    
    if [[ -n "$containers" ]]; then
        echo -e "\n${BLUE}Container Docker:${NC}"
        echo "$containers"
    fi
    
    # Service endpoints
    echo -e "\n${BLUE}Endpoints:${NC}"
    
    local host_ip=$(hostname -I | awk '{print $1}')
    
    if curl -sf "http://localhost/api/health" >/dev/null 2>&1; then
        success "API: http://$host_ip/api/ ✓"
    else
        error "API: http://$host_ip/api/ ✗"
    fi
    
    if curl -sf "http://localhost/" >/dev/null 2>&1; then
        success "Web UI: http://$host_ip/ ✓"
    else
        error "Web UI: http://$host_ip/ ✗"
    fi
    
    # Disk usage
    echo -e "\n${BLUE}Utilizzo Disco:${NC}"
    sudo du -sh "$INSTALL_DIR" "$DATA_DIR" 2>/dev/null | while read size dir; do
        echo "  $(basename "$dir"): $size"
    done
}

# Show logs
show_logs() {
    local service="${1:-all}"
    cd "$INSTALL_DIR" 2>/dev/null || fatal "Directory installazione non trovata"
    
    case "$service" in
        "all")
            sudo docker compose logs --tail=50 -f
            ;;
        *)
            if sudo docker compose ps | grep -q "$service"; then
                sudo docker compose logs --tail=50 -f "$service"
            else
                error "Servizio '$service' non trovato"
                echo "Servizi disponibili:"
                sudo docker compose ps --format "table {{.Service}}"
            fi
            ;;
    esac
}

# Main function
main() {
    check_root
    
    case "${1:-}" in
        "install")
            install
            ;;
        "update")
            update
            ;;
        "backup")
            backup_config
            ;;
        "status"|"st")
            show_status
            ;;
        "logs")
            show_logs "${2:-all}"
            ;;
        "start")
            sudo systemctl start "$APP_NAME"
            success "Servizi avviati"
            ;;
        "stop")
            sudo systemctl stop "$APP_NAME"
            success "Servizi fermati"
            ;;
        "restart")
            sudo systemctl restart "$APP_NAME"
            success "Servizi riavviati"
            ;;
        "help"|"-h"|"--help"|"")
            cat << EOF
KB Search - Setup e gestione

UTILIZZO:
    $0 <comando> [opzioni]

COMANDI:
    install     Installazione completa del sistema
    update      Aggiorna applicazione (preserva configurazione)
    backup      Backup configurazione
    status      Mostra stato servizi
    logs [srv]  Mostra logs (opzionale: servizio specifico)
    start       Avvia servizi
    stop        Ferma servizi
    restart     Riavvia servizi

ESEMPI:
    $0 install              # Prima installazione
    $0 status               # Controllo stato
    $0 logs kb-api          # Logs API
    $0 update               # Aggiornamento

DIRECTORY:
    Config:     $INSTALL_DIR
    Data:       $DATA_DIR
    Backup:     $BACKUP_DIR
    Logs:       $LOG_DIR

SERVIZI:
    systemctl status $APP_NAME
    systemctl restart $APP_NAME
    
EOF
            ;;
        *)
            error "Comando sconosciuto: $1"
            echo "Usa '$0 help' per vedere i comandi disponibili"
            exit 1
            ;;
    esac
}

main "$@"