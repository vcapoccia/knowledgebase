#!/bin/bash
set -e

# =============================================================================
# KBSearch GPU Deployment Script
# =============================================================================
# Questo script automatizza il deployment del supporto GPU per kbsearch.
# 
# PREREQUISITI:
# - GPU NVIDIA con driver installati (nvidia-smi funzionante)
# - nvidia-container-toolkit installato
# - Docker Compose
# 
# USAGE:
#   cd /opt/kbsearch
#   bash deploy_gpu.sh
# 
# Lo script:
# 1. Verifica prerequisiti (GPU, Docker)
# 2. Fa backup della configurazione attuale
# 3. Copia nuovi file da gpuworker/
# 4. Rebuild containers con supporto GPU
# 5. Restart servizi
# 6. Verifica GPU detection
# =============================================================================

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Funzioni di utilità
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

# Directory
KBSEARCH_DIR="/opt/kbsearch"
GPU_FILES_DIR="$KBSEARCH_DIR/gpuworker"
BACKUP_DIR="$KBSEARCH_DIR/backup_$(date +%Y%m%d_%H%M%S)"

# =============================================================================
# STEP 0: Verifica che script sia lanciato da /opt/kbsearch
# =============================================================================
print_header "VERIFICA DIRECTORY"

if [ "$(pwd)" != "$KBSEARCH_DIR" ]; then
    print_error "Lo script deve essere eseguito da $KBSEARCH_DIR"
    print_step "Esegui: cd $KBSEARCH_DIR && bash deploy_gpu.sh"
    exit 1
fi
print_success "Directory corretta: $(pwd)"

# =============================================================================
# STEP 1: Verifica prerequisiti
# =============================================================================
print_header "STEP 1: VERIFICA PREREQUISITI"

# Check nvidia-smi
print_step "Verifico GPU NVIDIA..."
if ! command -v nvidia-smi &> /dev/null; then
    print_error "nvidia-smi non trovato. Driver NVIDIA non installati?"
    exit 1
fi

if ! nvidia-smi &> /dev/null; then
    print_error "nvidia-smi fallito. Problemi con driver NVIDIA?"
    exit 1
fi

GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
print_success "GPU rilevata: $GPU_NAME"

# Check Docker
print_step "Verifico Docker..."
if ! command -v docker &> /dev/null; then
    print_error "Docker non trovato. Installalo prima."
    exit 1
fi
print_success "Docker: $(docker --version)"

# Check Docker Compose
print_step "Verifico Docker Compose..."
if ! command -v docker compose &> /dev/null; then
    print_error "Docker Compose non trovato. Installalo prima."
    exit 1
fi
print_success "Docker Compose: $(docker compose version)"

# Check Docker accesso GPU
print_step "Verifico Docker accesso GPU..."
if ! docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
    print_error "Docker non ha accesso alla GPU"
    print_warning "Installa nvidia-container-toolkit:"
    echo "  sudo apt install -y nvidia-container-toolkit"
    echo "  sudo systemctl restart docker"
    exit 1
fi
print_success "Docker ha accesso GPU"

# Check directory gpuworker esiste
print_step "Verifico directory gpuworker..."
if [ ! -d "$GPU_FILES_DIR" ]; then
    print_error "Directory $GPU_FILES_DIR non trovata"
    print_warning "Crea la directory e copia i file dentro:"
    echo "  mkdir -p $GPU_FILES_DIR"
    echo "  cp docker-compose.yml Dockerfile_worker requirements_worker.txt $GPU_FILES_DIR/"
    exit 1
fi
print_success "Directory gpuworker trovata"

# Check file necessari esistono
print_step "Verifico file necessari in gpuworker/..."
REQUIRED_FILES=(
    "docker-compose.yml"
    "Dockerfile_worker"
    "requirements_worker.txt"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$GPU_FILES_DIR/$file" ]; then
        print_error "File mancante: $GPU_FILES_DIR/$file"
        exit 1
    fi
done
print_success "Tutti i file necessari presenti"

# =============================================================================
# STEP 2: Backup configurazione attuale
# =============================================================================
print_header "STEP 2: BACKUP CONFIGURAZIONE ATTUALE"

print_step "Creo directory backup: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

# Backup files
FILES_TO_BACKUP=(
    "docker-compose.yml"
    "Dockerfile_worker"
    "requirements_worker.txt"
    "worker/worker_tasks.py"
)

for file in "${FILES_TO_BACKUP[@]}"; do
    if [ -f "$file" ]; then
        cp "$file" "$BACKUP_DIR/"
        print_success "Backup: $file → $BACKUP_DIR/"
    else
        print_warning "File non trovato (skip): $file"
    fi
done

print_success "Backup completato in: $BACKUP_DIR"

# =============================================================================
# STEP 3: Stop servizi attuali
# =============================================================================
print_header "STEP 3: STOP SERVIZI ATTUALI"

print_step "Fermo servizi Docker Compose..."
if docker compose ps --quiet | grep -q .; then
    docker compose down
    print_success "Servizi fermati"
else
    print_warning "Nessun servizio in esecuzione"
fi

# =============================================================================
# STEP 4: Copia nuovi file
# =============================================================================
print_header "STEP 4: COPIA NUOVI FILE"

print_step "Copio docker-compose.yml..."
cp "$GPU_FILES_DIR/docker-compose.yml" ./
print_success "docker-compose.yml aggiornato"

print_step "Copio Dockerfile_worker..."
cp "$GPU_FILES_DIR/Dockerfile_worker" ./
print_success "Dockerfile_worker aggiornato"

print_step "Copio requirements_worker.txt..."
cp "$GPU_FILES_DIR/requirements_worker.txt" ./
print_success "requirements_worker.txt aggiornato"

print_warning "worker_tasks.py NON sovrascritto (è già OK con GPU support)"

# =============================================================================
# STEP 5: Verifica configurazione Docker Compose
# =============================================================================
print_header "STEP 5: VERIFICA CONFIGURAZIONE"

print_step "Verifico docker-compose.yml..."
if ! docker compose config &> /dev/null; then
    print_error "docker-compose.yml non valido!"
    exit 1
fi
print_success "docker-compose.yml valido"

print_step "Verifico sezioni deploy GPU..."
GPU_SERVICES=("worker" "ollama" "api")
for service in "${GPU_SERVICES[@]}"; do
    if docker compose config | grep -A 10 "^  $service:" | grep -q "capabilities.*gpu"; then
        print_success "GPU configurata per: $service"
    else
        print_warning "GPU non configurata per: $service"
    fi
done

# =============================================================================
# STEP 6: Rebuild containers
# =============================================================================
print_header "STEP 6: REBUILD CONTAINERS"

print_step "Rebuild worker con supporto GPU..."
echo "Questo può richiedere diversi minuti (download PyTorch con CUDA)..."
docker compose build --no-cache worker

print_success "Worker rebuild completato"

print_step "Rebuild API..."
docker compose build --no-cache api
print_success "API rebuild completato"

# =============================================================================
# STEP 7: Avvio servizi
# =============================================================================
print_header "STEP 7: AVVIO SERVIZI"

print_step "Avvio tutti i servizi..."
docker compose up -d

print_step "Attendo stabilizzazione servizi (30 secondi)..."
sleep 30

# =============================================================================
# STEP 8: Verifica servizi
# =============================================================================
print_header "STEP 8: VERIFICA SERVIZI"

print_step "Verifico stato containers..."
docker compose ps

# Verifica servizi healthy
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

# =============================================================================
# STEP 9: Verifica GPU Detection
# =============================================================================
print_header "STEP 9: VERIFICA GPU DETECTION"

print_step "Attendo inizializzazione worker (10 secondi)..."
sleep 10

print_step "Verifico GPU detection nel worker..."
if docker compose logs worker | grep -q "Worker GPU DETECTED"; then
    print_success "GPU rilevata dal worker!"
    
    # Mostra dettagli GPU
    echo ""
    docker compose logs worker | grep -E "(GPU DETECTED|CUDA Version|batch size)" | head -5
    echo ""
else
    print_warning "GPU NON rilevata dal worker"
    print_warning "Il worker userà CPU (più lento ma funzionante)"
    echo ""
    print_step "Log worker (ultime 20 righe):"
    docker compose logs worker --tail=20
    echo ""
fi

# =============================================================================
# STEP 10: Test Health Endpoints
# =============================================================================
print_header "STEP 10: TEST HEALTH ENDPOINTS"

print_step "Test API health endpoint..."
sleep 5
if curl -f -s http://localhost:8000/health > /dev/null; then
    print_success "API health: OK"
else
    print_error "API health: FAIL"
fi

print_step "Test Qdrant..."
if curl -f -s http://localhost:6333/collections > /dev/null; then
    print_success "Qdrant: OK"
else
    print_error "Qdrant: FAIL"
fi

print_step "Test Meilisearch..."
if curl -f -s http://localhost:7700/health > /dev/null; then
    print_success "Meilisearch: OK"
else
    print_error "Meilisearch: FAIL"
fi

print_step "Test Ollama..."
if curl -f -s http://localhost:11434/ > /dev/null; then
    print_success "Ollama: OK"
else
    print_error "Ollama: FAIL"
fi

# =============================================================================
# COMPLETAMENTO
# =============================================================================
print_header "✅ DEPLOYMENT COMPLETATO!"

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                   DEPLOYMENT COMPLETATO!                       ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${CYAN}📊 INFORMAZIONI:${NC}"
echo "  • GPU: $GPU_NAME"
echo "  • Admin UI: http://localhost:8000/admin"
echo "  • Backup: $BACKUP_DIR"
echo ""

echo -e "${CYAN}📝 PROSSIMI PASSI:${NC}"
echo ""
echo "1. Verifica GPU detection completa:"
echo "   ${YELLOW}docker compose logs worker | grep -i gpu${NC}"
echo ""
echo "2. Monitora GPU usage durante ingestion:"
echo "   ${YELLOW}watch -n 1 nvidia-smi${NC}"
echo ""
echo "3. Inizializza indici (via UI o API):"
echo "   ${YELLOW}curl -X POST http://localhost:8000/init_collections${NC}"
echo ""
echo "4. Avvia ingestion:"
echo "   ${YELLOW}curl -X POST 'http://localhost:8000/ingestion/start?model=sentence-transformer'${NC}"
echo ""
echo "5. Monitora progress:"
echo "   ${YELLOW}watch -n 2 'curl -s http://localhost:8000/progress | jq'${NC}"
echo ""

echo -e "${CYAN}🔧 COMANDI UTILI:${NC}"
echo "  • Log worker:      ${YELLOW}docker compose logs worker -f${NC}"
echo "  • Log API:         ${YELLOW}docker compose logs api -f${NC}"
echo "  • GPU usage:       ${YELLOW}nvidia-smi${NC}"
echo "  • Restart worker:  ${YELLOW}docker compose restart worker${NC}"
echo "  • Stop tutto:      ${YELLOW}docker compose down${NC}"
echo ""

echo -e "${CYAN}📚 DOCUMENTAZIONE:${NC}"
echo "  • GPU Guide:       gpuworker/GPU_DEPLOYMENT_GUIDE.md"
echo "  • Checklist:       gpuworker/DEPLOYMENT_CHECKLIST.md"
echo "  • Backup config:   $BACKUP_DIR"
echo ""

if docker compose logs worker | grep -q "Worker GPU DETECTED"; then
    echo -e "${GREEN}🎉 GPU ACCELERAZIONE ATTIVA! Speed-up atteso: 3-5x${NC}"
else
    echo -e "${YELLOW}⚠️  GPU non rilevata, worker usa CPU (funziona ma più lento)${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Verifica: ${YELLOW}docker exec kbsearch-worker-1 python -c 'import torch; print(torch.cuda.is_available())'${NC}"
    echo "  2. Rebuild:  ${YELLOW}docker compose build --no-cache worker && docker compose up -d${NC}"
    echo "  3. Log:      ${YELLOW}docker compose logs worker | grep -i 'gpu\|cuda\|torch'${NC}"
fi

echo ""
print_success "Deployment terminato con successo!"
echo ""
