#!/usr/bin/env bash
# KB Search - Debian Package Builder
# Crea un pacchetto .deb completo e funzionante

set -euo pipefail

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${BLUE}[BUILD]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Package info
PACKAGE_NAME="kbsearch"
PACKAGE_VERSION="2.0.0"
PACKAGE_ARCH="all"
PACKAGE_MAINTAINER="KB Search Team <admin@kbsearch.local>"
PACKAGE_DESCRIPTION="Knowledge Base Search with Vector Database"

# Build directory
BUILD_DIR="build"
PACKAGE_DIR="$BUILD_DIR/${PACKAGE_NAME}_${PACKAGE_VERSION}_${PACKAGE_ARCH}"

cleanup_build() {
    if [[ -d "$BUILD_DIR" ]]; then
        rm -rf "$BUILD_DIR"
    fi
    mkdir -p "$BUILD_DIR"
}

create_package_structure() {
    log "Creazione struttura pacchetto..."
    mkdir -p "$PACKAGE_DIR"/{DEBIAN,etc/kbsearch,usr/{bin,share/doc/kbsearch},lib/systemd/system,var/{lib,log}/kbsearch}
    success "Struttura pacchetto creata"
}

create_control_files() {
    log "Creazione file controllo DEBIAN..."
    
    # Main control file
    cat > "$PACKAGE_DIR/DEBIAN/control" << EOF
Package: $PACKAGE_NAME
Version: $PACKAGE_VERSION
Section: utils
Priority: optional
Architecture: $PACKAGE_ARCH
Depends: docker.io (>= 24.0), docker-compose-plugin (>= 2.20), curl, jq, bc
Maintainer: $PACKAGE_MAINTAINER
Description: $PACKAGE_DESCRIPTION
 KB Search is a modern knowledge base search system with vector database
 capabilities. It provides intelligent document indexing and search with
 faceted navigation, real-time monitoring, and automated backup systems.
Homepage: https://github.com/kbsearch/kbsearch
EOF

    # Post-installation script
    cat > "$PACKAGE_DIR/DEBIAN/postinst" << 'POSTINST_EOF'
#!/bin/bash
set -e

case "$1" in
    configure)
        # Create system user
        if ! id kbsearch >/dev/null 2>&1; then
            useradd -r -s /bin/false -d /var/lib/kbsearch -c "KB Search Service" kbsearch
        fi
        
        # Create directories
        mkdir -p /etc/kbsearch/{run,logs} /var/{lib,log}/kbsearch /var/backups/kbsearch /mnt/kb/{_Gare,_AQ}
        chown -R kbsearch:kbsearch /var/lib/kbsearch /var/log/kbsearch /var/backups/kbsearch /etc/kbsearch/{run,logs}
        
        # Set permissions
        chmod 755 /usr/bin/kb-*
        
        # Generate config if needed
        if [[ ! -f /etc/kbsearch/.env ]]; then
            cp /etc/kbsearch/.env.example /etc/kbsearch/.env
            ADMIN_TOKEN=$(openssl rand -hex 32)
            sed -i "s/ADMIN_TOKEN=.*/ADMIN_TOKEN=$ADMIN_TOKEN/" /etc/kbsearch/.env
            chown kbsearch:kbsearch /etc/kbsearch/.env
            chmod 600 /etc/kbsearch/.env
            echo "Admin token: $ADMIN_TOKEN" > /var/log/kbsearch/install.log
            chmod 600 /var/log/kbsearch/install.log
        fi
        
        systemctl daemon-reload
        systemctl enable kbsearch.service
        
        echo ""
        echo "🎉 KB Search installed successfully!"
        echo "Next steps:"
        echo "  1. Configure: /etc/kbsearch/.env"
        echo "  2. Start: systemctl start kbsearch"
        echo "  3. Status: kb-setup status"
        ;;
esac
exit 0
POSTINST_EOF

    # Pre-removal script
    cat > "$PACKAGE_DIR/DEBIAN/prerm" << 'PRERM_EOF'
#!/bin/bash
set -e
case "$1" in
    remove|upgrade|deconfigure)
        if systemctl is-active --quiet kbsearch; then
            systemctl stop kbsearch || true
        fi
        ;;
esac
exit 0
PRERM_EOF

    chmod +x "$PACKAGE_DIR/DEBIAN"/{postinst,prerm}
    success "File controllo DEBIAN creati"
}

copy_application_files() {
    log "Copia file applicazione..."
    
    cp -r apps "$PACKAGE_DIR/etc/kbsearch/"
    cp compose.yml "$PACKAGE_DIR/etc/kbsearch/" 2>/dev/null || echo "compose.yml not found, will create default"
    cp .env.example "$PACKAGE_DIR/etc/kbsearch/" 2>/dev/null || echo ".env.example not found, will create default"
    
    # Create basic compose.yml if missing
    if [[ ! -f "$PACKAGE_DIR/etc/kbsearch/compose.yml" ]]; then
        cat > "$PACKAGE_DIR/etc/kbsearch/compose.yml" << 'COMPOSE_EOF'
name: kbsearch
networks:
  kbnet: {}
volumes:
  kb_api_data: {}
  qdrant_storage: {}

services:
  qdrant:
    image: qdrant/qdrant:latest
    networks: [kbnet]
    volumes:
      - qdrant_storage:/qdrant/storage
    ports:
      - "6333:6333"
    restart: unless-stopped

  kb-api:
    build:
      context: ./apps/kb-api
      dockerfile: Dockerfile
    networks: [kbnet]
    environment:
      ADMIN_TOKEN: ${ADMIN_TOKEN:-change-me}
      QDRANT_URL: http://qdrant:6333
      KB_ROOT: /mnt/kb
    depends_on:
      - qdrant
    volumes:
      - kb_api_data:/data
      - /mnt/kb:/mnt/kb:ro
    ports:
      - "8080:8080"
    restart: unless-stopped

  kb-ui:
    image: nginx:alpine
    networks: [kbnet]
    volumes:
      - ./apps/kb-ui:/usr/share/nginx/html:ro
    restart: unless-stopped

  caddy:
    image: caddy:2
    networks: [kbnet]
    depends_on:
      - kb-api
      - kb-ui
    ports:
      - "80:80"
    volumes:
      - ./caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      - /mnt/kb:/srv/files:ro
    restart: unless-stopped
COMPOSE_EOF
    fi
    
    # Create basic .env.example if missing
    if [[ ! -f "$PACKAGE_DIR/etc/kbsearch/.env.example" ]]; then
        cat > "$PACKAGE_DIR/etc/kbsearch/.env.example" << 'ENV_EOF'
# KB Search Configuration
PUBLIC_HOST=kb.local
KB_ROOT=/mnt/kb
KB_GARE_DIR=/mnt/kb/_Gare
KB_AQ_DIR=/mnt/kb/_AQ
ADMIN_TOKEN=change-me-please
EMBED_MODEL=BAAI/bge-m3
QDRANT_COLLECTION=kb_chunks
CHUNK_SIZE=800
CHUNK_OVERLAP=120
INGEST_BATCH=128
EXCLUDE_SEZIONI=documentazione,accesso_atti
LOG_LEVEL=info
ENV_EOF
    fi
    
    # Create Caddy config
    mkdir -p "$PACKAGE_DIR/etc/kbsearch/caddy"
    cat > "$PACKAGE_DIR/etc/kbsearch/caddy/Caddyfile" << 'CADDY_EOF'
:80 {
    encode zstd gzip
    handle_path /api/* {
        reverse_proxy kb-api:8080
    }
    handle_path /files/* {
        root * /srv
        file_server browse
    }
    handle {
        reverse_proxy kb-ui:80
    }
}
CADDY_EOF
    
    success "File applicazione copiati"
}

create_system_executables() {
    log "Creazione eseguibili sistema..."
    
    # Main setup script
    cat > "$PACKAGE_DIR/usr/bin/kb-setup" << 'SETUP_EOF'
#!/usr/bin/env bash
# KB Search System Management
set -euo pipefail

INSTALL_DIR="/etc/kbsearch"
cd "$INSTALL_DIR" 2>/dev/null || { echo "KB Search not installed"; exit 1; }

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

show_status() {
    echo -e "\n${BLUE}=== KB SEARCH STATUS ===${NC}"
    
    if systemctl is-active --quiet kbsearch; then
        echo -e "${GREEN}✓${NC} Service: ACTIVE"
    else
        echo -e "${RED}✗${NC} Service: INACTIVE"
    fi
    
    local containers
    containers=$(docker compose ps --format "table {{.Service}}\t{{.Status}}" 2>/dev/null || echo "")
    if [[ -n "$containers" ]]; then
        echo -e "\n${BLUE}Containers:${NC}"
        echo "$containers"
    fi
    
    echo -e "\n${BLUE}Endpoints:${NC}"
    local host_ip=$(hostname -I | awk '{print $1}' || echo "localhost")
    if curl -sf "http://localhost/api/health" >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Web UI: http://$host_ip/"
        echo -e "${GREEN}✓${NC} API: http://$host_ip/api/"
    else
        echo -e "${RED}✗${NC} Services not responding"
    fi
}

case "${1:-help}" in
    status|st) show_status ;;
    start) systemctl start kbsearch; sleep 3; show_status ;;
    stop) systemctl stop kbsearch ;;
    restart) systemctl restart kbsearch; sleep 3; show_status ;;
    logs) journalctl -u kbsearch -f ;;
    *) echo "Usage: $0 {status|start|stop|restart|logs}" ;;
esac
SETUP_EOF

    # Copy ingest monitor if exists
    if [[ -f "bin/kb-ingest-monitor.sh" ]]; then
        cp "bin/kb-ingest-monitor.sh" "$PACKAGE_DIR/usr/bin/kb-ingest-monitor"
    else
        # Create basic version
        cat > "$PACKAGE_DIR/usr/bin/kb-ingest-monitor" << 'INGEST_EOF'
#!/usr/bin/env bash
# KB Search Ingest Monitor
set -euo pipefail

COMPOSE_FILE="/etc/kbsearch/compose.yml"

show_status() {
    echo "=== INGEST STATUS ==="
    if docker compose -f "$COMPOSE_FILE" ps | grep -q kb-ingest; then
        echo "✓ Ingest container found"
    else
        echo "✗ Ingest container not running"
    fi
}

case "${1:-help}" in
    status) show_status ;;
    start) cd /etc/kbsearch && docker compose run --rm kb-ingest ;;
    *) echo "Usage: $0 {status|start}" ;;
esac
INGEST_EOF
    fi
    
    chmod +x "$PACKAGE_DIR/usr/bin"/kb-*
    success "Eseguibili sistema creati"
}

create_systemd_services() {
    log "Creazione servizi systemd..."
    
    cat > "$PACKAGE_DIR/lib/systemd/system/kbsearch.service" << 'SERVICE_EOF'
[Unit]
Description=KB Search Knowledge Base System
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=root
WorkingDirectory=/etc/kbsearch
ExecStart=/usr/bin/docker compose up -d qdrant kb-api kb-ui caddy
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300
TimeoutStopSec=120
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
SERVICE_EOF
    
    success "Servizi systemd creati"
}

create_documentation() {
    log "Creazione documentazione..."
    
    local doc_dir="$PACKAGE_DIR/usr/share/doc/kbsearch"
    
    cat > "$doc_dir/README.Debian" << 'README_EOF'
KB Search for Debian
====================

Quick Start:
1. Configure: sudo nano /etc/kbsearch/.env
2. Start: sudo systemctl start kbsearch
3. Access: http://your-server-ip/

Commands:
- kb-setup: Main system management
- kb-ingest-monitor: Document ingestion control

Configuration: /etc/kbsearch/.env
Data: /var/lib/kbsearch/
Logs: /var/log/kbsearch/
README_EOF
    
    cat > "$doc_dir/copyright" << 'COPYRIGHT_EOF'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: kbsearch
Source: https://github.com/kbsearch/kbsearch

Files: *
Copyright: 2024 KB Search Team
License: GPL-3+
COPYRIGHT_EOF
    
    success "Documentazione creata"
}

build_package() {
    log "Build del pacchetto .deb..."
    
    local installed_size
    installed_size=$(du -sk "$PACKAGE_DIR" | cut -f1)
    echo "Installed-Size: $installed_size" >> "$PACKAGE_DIR/DEBIAN/control"
    
    dpkg-deb --build --root-owner-group "$PACKAGE_DIR"
    
    local package_file="${PACKAGE_NAME}_${PACKAGE_VERSION}_${PACKAGE_ARCH}.deb"
    mv "${PACKAGE_DIR}.deb" "$package_file"
    
    success "Pacchetto creato: $package_file"
    
    echo
    echo -e "${GREEN}🎉 DEBIAN PACKAGE BUILD COMPLETE! 🎉${NC}"
    echo
    echo -e "${BLUE}Installation:${NC}"
    echo "  sudo dpkg -i $package_file"
    echo "  sudo apt-get install -f"
    echo
    ls -lh "$package_file"
}

main() {
    echo -e "${BLUE}🏗️  KB Search Debian Package Builder${NC}"
    echo
    
    if [[ ! -f "apps/kb-ui/assets/app.js" ]]; then
        error "Run from KB Search project root directory"
        exit 1
    fi
    
    cleanup_build
    create_package_structure
    create_control_files
    copy_application_files
    create_system_executables
    create_systemd_services
    create_documentation
    build_package
}

main "$@"
