#!/bin/bash
set -e

# =============================================================================
# Setup GPUWorker Directory
# =============================================================================
# Questo script prepara la directory gpuworker/ con tutti i file necessari
# per il deployment GPU.
#
# USAGE:
#   cd /opt/kbsearch
#   bash setup_gpuworker.sh
#
# Lo script:
# 1. Crea directory gpuworker/ se non esiste
# 2. Copia i file di configurazione GPU
# 3. Rende eseguibili gli script
# 4. Verifica che tutto sia pronto
# =============================================================================

# Colori
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
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

# =============================================================================
# SETUP
# =============================================================================
print_header "SETUP GPUWORKER DIRECTORY"

KBSEARCH_DIR="/opt/kbsearch"
GPU_DIR="$KBSEARCH_DIR/gpuworker"

# Verifica di essere in /opt/kbsearch
if [ "$(pwd)" != "$KBSEARCH_DIR" ]; then
    echo "Esegui questo script da $KBSEARCH_DIR"
    echo "cd $KBSEARCH_DIR && bash setup_gpuworker.sh"
    exit 1
fi

print_step "Creo directory gpuworker..."
mkdir -p "$GPU_DIR"
print_success "Directory creata: $GPU_DIR"

# Se i file sono stati scaricati da Claude in una directory temporanea,
# l'utente deve copiarli qui. Questo script assume che siano disponibili.
print_header "ISTRUZIONI"

echo ""
echo "Hai scaricato i file da Claude in una directory?"
echo ""
echo "Opzione 1 - Hai i file localmente:"
echo "  Copia i file nella directory gpuworker:"
echo "  ${YELLOW}cp /percorso/download/docker-compose.yml $GPU_DIR/${NC}"
echo "  ${YELLOW}cp /percorso/download/Dockerfile_worker $GPU_DIR/${NC}"
echo "  ${YELLOW}cp /percorso/download/requirements_worker.txt $GPU_DIR/${NC}"
echo "  ${YELLOW}cp /percorso/download/*.md $GPU_DIR/${NC}"
echo ""

echo "Opzione 2 - I file sono in /mnt/user-data/outputs (se Claude li ha creati):"
read -p "Vuoi copiare i file da /mnt/user-data/outputs? [y/N] " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    SOURCE_DIR="/mnt/user-data/outputs"
    
    if [ -d "$SOURCE_DIR" ]; then
        print_step "Copio file da $SOURCE_DIR..."
        
        FILES=(
            "docker-compose.yml"
            "Dockerfile_worker"
            "requirements_worker.txt"
            "deploy_gpu.sh"
            "GPU_DEPLOYMENT_GUIDE.md"
            "DEPLOYMENT_CHECKLIST.md"
            "OCR_OPTIONAL_FUNCTIONS.py"
        )
        
        for file in "${FILES[@]}"; do
            if [ -f "$SOURCE_DIR/$file" ]; then
                cp "$SOURCE_DIR/$file" "$GPU_DIR/"
                print_success "Copiato: $file"
            else
                print_warning "File non trovato: $file (skip)"
            fi
        done
        
        # Rendi eseguibile deploy_gpu.sh
        if [ -f "$GPU_DIR/deploy_gpu.sh" ]; then
            chmod +x "$GPU_DIR/deploy_gpu.sh"
            print_success "deploy_gpu.sh reso eseguibile"
        fi
    else
        print_warning "Directory $SOURCE_DIR non trovata"
        echo "Copia manualmente i file in $GPU_DIR/"
        exit 1
    fi
else
    echo ""
    print_warning "Copia manualmente i file in $GPU_DIR/ prima di procedere"
    echo ""
    echo "File necessari:"
    echo "  • docker-compose.yml"
    echo "  • Dockerfile_worker"
    echo "  • requirements_worker.txt"
    echo "  • deploy_gpu.sh"
    echo ""
    exit 0
fi

# =============================================================================
# VERIFICA
# =============================================================================
print_header "VERIFICA FILE"

REQUIRED=(
    "docker-compose.yml"
    "Dockerfile_worker"
    "requirements_worker.txt"
    "deploy_gpu.sh"
)

ALL_OK=true
for file in "${REQUIRED[@]}"; do
    if [ -f "$GPU_DIR/$file" ]; then
        print_success "$file presente"
    else
        print_warning "$file MANCANTE"
        ALL_OK=false
    fi
done

if [ "$ALL_OK" = false ]; then
    echo ""
    print_warning "Alcuni file mancano. Copiali in $GPU_DIR/ prima di eseguire deploy_gpu.sh"
    exit 1
fi

# =============================================================================
# COMPLETAMENTO
# =============================================================================
print_header "✅ SETUP COMPLETATO"

echo ""
echo -e "${GREEN}Directory gpuworker pronta!${NC}"
echo ""
echo "File disponibili in: ${YELLOW}$GPU_DIR/${NC}"
ls -lh "$GPU_DIR/"
echo ""

echo -e "${CYAN}Prossimo step:${NC}"
echo "  Esegui il deployment GPU con:"
echo ""
echo "  ${YELLOW}cd $KBSEARCH_DIR${NC}"
echo "  ${YELLOW}bash gpuworker/deploy_gpu.sh${NC}"
echo ""
echo "  Oppure copia lo script nella directory corrente:"
echo "  ${YELLOW}cp gpuworker/deploy_gpu.sh . && bash deploy_gpu.sh${NC}"
echo ""

print_success "Setup completato!"
