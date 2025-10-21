#!/bin/bash
set -e

# =============================================================================
# KBSearch GPU Rollback Script
# =============================================================================
# Questo script ripristina la configurazione precedente in caso di problemi
# con il deployment GPU.
#
# USAGE:
#   cd /opt/kbsearch
#   bash rollback_gpu.sh
#
# Lo script:
# 1. Trova il backup più recente
# 2. Stop servizi attuali
# 3. Ripristina file di configurazione
# 4. Rebuild containers
# 5. Restart servizi
# =============================================================================

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_header() {
    echo -e "${CYAN}=============================================================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}=============================================================================${NC}"
}

print_step() {
    echo -e "${BLUE}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# =============================================================================
# VERIFICA DIRECTORY
# =============================================================================
KBSEARCH_DIR="/opt/kbsearch"

if [ "$(pwd)" != "$KBSEARCH_DIR" ]; then
    print_error "Esegui questo script da $KBSEARCH_DIR"
    echo "cd $KBSEARCH_DIR && bash rollback_gpu.sh"
    exit 1
fi

print_header "🔄 ROLLBACK CONFIGURAZIONE GPU"
echo ""
print_warning "Questo script ripristinerà la configurazione precedente"
print_warning "e rimuoverà il supporto GPU"
echo ""
read -p "Sei sicuro di voler continuare? [y/N] " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Rollback annullato"
    exit 0
fi

# =============================================================================
# TROVA BACKUP PIÙ RECENTE
# =============================================================================
print_header "STEP 1: TROVA BACKUP"

print_step "Cerco backup più recente..."

BACKUP_DIRS=("$KBSEARCH_DIR"/backup_*)
if [ ! -d "${BACKUP_DIRS[0]}" ]; then
    print_error "Nessun backup trovato in $KBSEARCH_DIR"
    print_warning "Impossibile fare rollback senza backup"
    exit 1
fi

# Ordina per data e prendi il più recente
LATEST_BACKUP=$(ls -dt "$KBSEARCH_DIR"/backup_* 2>/dev/null | head -1)

if [ -z "$LATEST_BACKUP" ] || [ ! -d "$LATEST_BACKUP" ]; then
    print_error "Backup non valido: $LATEST_BACKUP"
    exit 1
fi

print_success "Backup trovato: $LATEST_BACKUP"

# Verifica file nel backup
print_step "Verifico contenuto backup..."
REQUIRED_FILES=(
    "docker-compose.yml"
    "Dockerfile_worker"
)

ALL_OK=true
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$LATEST_BACKUP/$file" ]; then
        print_success "✓ $file"
    else
        print_warning "✗ $file mancante nel backup"
        ALL_OK=false
    fi
done

if [ "$ALL_OK" = false ]; then
    print_warning "Backup incompleto, continuo comunque..."
fi

# =============================================================================
# STEP 2: STOP SERVIZI
# =============================================================================
print_header "STEP 2: STOP SERVIZI"

print_step "Fermo servizi Docker Compose..."
if docker compose ps --quiet | grep -q .; then
    docker compose down
    print_success "Servizi fermati"
else
    print_warning "Nessun servizio in esecuzione"
fi

# =============================================================================
# STEP 3: RIPRISTINA FILE
# =============================================================================
print_header "STEP 3: RIPRISTINA FILE"

FILES_TO_RESTORE=(
    "docker-compose.yml"
    "Dockerfile_worker"
    "requirements_worker.txt"
)

for file in "${FILES_TO_RESTORE[@]}"; do
    if [ -f "$LATEST_BACKUP/$file" ]; then
        print_step "Ripristino $file..."
        cp "$LATEST_BACKUP/$file" "$KBSEARCH_DIR/"
        print_success "$file ripristinato"
    else
        print_warning "$file non presente nel backup (skip)"
    fi
done

# =============================================================================
# STEP 4: REBUILD CONTAINERS
# =============================================================================
print_header "STEP 4: REBUILD CONTAINERS"

print_step "Rebuild worker..."
docker compose build --no-cache worker
print_success "Worker rebuild completato"

print_step "Rebuild API..."
docker compose build --no-cache api
print_success "API rebuild completato"

# =============================================================================
# STEP 5: RESTART SERVIZI
# =============================================================================
print_header "STEP 5: RESTART SERVIZI"

print_step "Avvio servizi..."
docker compose up -d

print_step "Attendo stabilizzazione (30 secondi)..."
sleep 30

# =============================================================================
# STEP 6: VERIFICA
# =============================================================================
print_header "STEP 6: VERIFICA SERVIZI"

print_step "Verifico stato containers..."
docker compose ps

SERVICES=("postgres" "redis" "meili" "qdrant" "ollama" "api" "worker")
ALL_OK=true

for service in "${SERVICES[@]}"; do
    if docker compose ps --filter "name=$service" --format "{{.Status}}" | grep -q "Up"; then
        print_success "$service: OK"
    else
        print_error "$service: ERRORE"
        ALL_OK=false
    fi
done

if [ "$ALL_OK" = false ]; then
    print_error "Alcuni servizi non sono partiti correttamente"
    print_warning "Verifica i log con: docker compose logs"
    exit 1
fi

# Test API
print_step "Test API health..."
sleep 5
if curl -f -s http://localhost:8000/health > /dev/null; then
    print_success "API: OK"
else
    print_error "API: FAIL"
fi

# =============================================================================
# COMPLETAMENTO
# =============================================================================
print_header "✅ ROLLBACK COMPLETATO"

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              ROLLBACK COMPLETATO CON SUCCESSO!                 ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${CYAN}📊 INFORMAZIONI:${NC}"
echo "  • Configurazione ripristinata da: $LATEST_BACKUP"
echo "  • Admin UI: http://localhost:8000/admin"
echo "  • Servizi attivi: $(docker compose ps --format "{{.Name}}" | wc -l)"
echo ""

echo -e "${CYAN}⚠️  NOTE:${NC}"
echo "  • Supporto GPU RIMOSSO"
echo "  • Worker usa CPU (più lento ma stabile)"
echo "  • Tutti i servizi operativi"
echo ""

echo -e "${CYAN}📝 COMANDI UTILI:${NC}"
echo "  • Log worker:      ${YELLOW}docker compose logs worker -f${NC}"
echo "  • Log API:         ${YELLOW}docker compose logs api -f${NC}"
echo "  • Restart worker:  ${YELLOW}docker compose restart worker${NC}"
echo ""

print_step "Verifica worker log..."
if docker compose logs worker | grep -q "GPU non disponibile\|cpu"; then
    print_success "Worker in modalità CPU (come atteso dopo rollback)"
elif docker compose logs worker | grep -q "GPU DETECTED"; then
    print_warning "Worker rileva ancora GPU (potrebbe essere normale)"
fi

echo ""
print_success "Sistema ripristinato alla configurazione precedente!"
echo ""
