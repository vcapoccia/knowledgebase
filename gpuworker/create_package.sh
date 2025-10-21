#!/bin/bash
# =============================================================================
# Create KBSearch GPU Package Tarball
# =============================================================================
# Questo script crea un archivio .tar.gz con tutti i file necessari
# per il deployment GPU di kbsearch.
#
# USAGE:
#   bash create_package.sh
#
# OUTPUT:
#   kbsearch_gpu_package_YYYYMMDD_HHMMSS.tar.gz
# =============================================================================

set -e

# Colori
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}=============================================================================${NC}"
echo -e "${CYAN}KBSearch GPU Package Creator${NC}"
echo -e "${CYAN}=============================================================================${NC}"
echo ""

# Timestamp per nome file
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PACKAGE_NAME="kbsearch_gpu_package_${TIMESTAMP}"
PACKAGE_FILE="${PACKAGE_NAME}.tar.gz"

# Directory temporanea per il package
TMP_DIR="/tmp/${PACKAGE_NAME}"

echo -e "${BLUE}▶ Creo directory temporanea: $TMP_DIR${NC}"
mkdir -p "$TMP_DIR"

# File da includere nel package
FILES=(
    "docker-compose.yml"
    "Dockerfile_worker"
    "requirements_worker.txt"
    "deploy_gpu.sh"
    "setup_gpuworker.sh"
    "rollback_gpu.sh"
    "ONE_LINER_COMMANDS.sh"
    "README_INDICE.md"
    "README_SCRIPTS.md"
    "GPU_DEPLOYMENT_GUIDE.md"
    "DEPLOYMENT_CHECKLIST.md"
    "OCR_OPTIONAL_FUNCTIONS.py"
)

echo -e "${BLUE}▶ Copio file nel package...${NC}"

# Controlla se siamo in /mnt/user-data/outputs
if [ -d "/mnt/user-data/outputs" ]; then
    SOURCE_DIR="/mnt/user-data/outputs"
else
    SOURCE_DIR="."
fi

COPIED=0
for file in "${FILES[@]}"; do
    if [ -f "$SOURCE_DIR/$file" ]; then
        cp "$SOURCE_DIR/$file" "$TMP_DIR/"
        echo -e "  ${GREEN}✓${NC} $file"
        COPIED=$((COPIED + 1))
    else
        echo -e "  ⚠️  $file (non trovato, skip)"
    fi
done

echo ""
echo -e "${BLUE}▶ Rendo eseguibili gli script...${NC}"
chmod +x "$TMP_DIR"/*.sh 2>/dev/null || true

echo -e "${BLUE}▶ Creo archivio tar.gz...${NC}"
tar -czf "$PACKAGE_FILE" -C /tmp "$PACKAGE_NAME"

echo -e "${BLUE}▶ Pulizia...${NC}"
rm -rf "$TMP_DIR"

echo ""
echo -e "${GREEN}=============================================================================${NC}"
echo -e "${GREEN}✅ PACKAGE CREATO CON SUCCESSO!${NC}"
echo -e "${GREEN}=============================================================================${NC}"
echo ""
echo "📦 File: ${CYAN}$PACKAGE_FILE${NC}"
echo "📂 Dimensione: $(du -h "$PACKAGE_FILE" | cut -f1)"
echo "📋 File inclusi: $COPIED"
echo ""
echo -e "${BLUE}Prossimi step:${NC}"
echo ""
echo "1. Copia il package sul server kbsearch:"
echo "   ${CYAN}scp $PACKAGE_FILE user@server:/tmp/${NC}"
echo ""
echo "2. Sul server, estrai il package:"
echo "   ${CYAN}cd /opt/kbsearch${NC}"
echo "   ${CYAN}tar -xzf /tmp/$PACKAGE_FILE${NC}"
echo "   ${CYAN}mv ${PACKAGE_NAME} gpuworker${NC}"
echo ""
echo "3. Esegui deployment:"
echo "   ${CYAN}bash gpuworker/deploy_gpu.sh${NC}"
echo ""
echo -e "${GREEN}✅ Fatto!${NC}"
echo ""
