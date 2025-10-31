#!/bin/bash
# 
# Deploy Automatico - Metadata Enrichment
# ========================================
#
# Questo script automatizza l'intero processo di enrichment metadati:
# 1. Verifica dipendenze
# 2. Backup database (opzionale)
# 3. Test parser su sample
# 4. Update schema PostgreSQL
# 5. Enrichment metadati
# 6. Reindex Meilisearch
# 7. Verifica risultati
#
# Usage:
#   ./deploy_enrichment.sh              # Interattivo con conferme
#   ./deploy_enrichment.sh --auto       # Automatico senza conferme
#   ./deploy_enrichment.sh --test-only  # Solo test, no modifiche
#

set -e  # Exit on error

# ========================
# COLORI
# ========================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ========================
# CONFIGURAZIONE
# ========================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_DIR="/opt/kbsearch"
BACKUP_DIR="/opt/kbsearch/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

AUTO_MODE=false
TEST_ONLY=false

# Parse arguments
for arg in "$@"; do
    case $arg in
        --auto)
            AUTO_MODE=true
            ;;
        --test-only)
            TEST_ONLY=true
            ;;
        --help)
            echo "Usage: $0 [--auto] [--test-only] [--help]"
            echo ""
            echo "Options:"
            echo "  --auto       Esegui senza conferme interattive"
            echo "  --test-only  Esegui solo test, senza modifiche al DB"
            echo "  --help       Mostra questo messaggio"
            exit 0
            ;;
    esac
done

# ========================
# UTILITY FUNCTIONS
# ========================

print_header() {
    echo ""
    echo -e "${BLUE}===============================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}===============================================================================${NC}"
    echo ""
}

print_step() {
    echo -e "${GREEN}➜ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

ask_confirmation() {
    if [ "$AUTO_MODE" = true ]; then
        return 0
    fi
    
    local prompt="$1"
    echo -e "${YELLOW}${prompt} (y/n): ${NC}"
    read -r response
    case "$response" in
        [yY][eE][sS]|[yY]) 
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# ========================
# VERIFICHE INIZIALI
# ========================

print_header "METADATA ENRICHMENT - DEPLOY AUTOMATICO"

print_step "Verifica ambiente..."

# Verifica Docker containers
if ! docker compose ps | grep -q "kbsearch-postgres-1.*Up"; then
    print_error "Container PostgreSQL non attivo!"
    echo "Avvia i servizi: cd /opt/kbsearch && docker compose up -d"
    exit 1
fi

if ! docker compose ps | grep -q "kbsearch-meili-1.*Up"; then
    print_warning "Container Meilisearch non attivo"
    echo "Alcune funzionalità potrebbero non essere disponibili"
fi

print_success "Containers OK"

# Verifica Python dependencies
print_step "Verifica dipendenze Python..."

if ! python3 -c "import psycopg" 2>/dev/null; then
    print_warning "Modulo psycopg mancante"
    if ask_confirmation "Installare dipendenze Python?"; then
        pip3 install psycopg[binary] meilisearch
    else
        print_error "Dipendenze mancanti. Esegui: pip3 install psycopg[binary] meilisearch"
        exit 1
    fi
fi

print_success "Dipendenze OK"

# ========================
# BACKUP (OPZIONALE)
# ========================

if [ "$TEST_ONLY" = false ]; then
    print_header "BACKUP DATABASE"
    
    if ask_confirmation "Vuoi fare un backup del database prima di procedere?"; then
        print_step "Creazione backup..."
        
        mkdir -p "$BACKUP_DIR"
        
        BACKUP_FILE="$BACKUP_DIR/documents_backup_${TIMESTAMP}.sql"
        
        docker exec kbsearch-postgres-1 pg_dump -U kbuser -d kb -t documents > "$BACKUP_FILE"
        
        if [ -f "$BACKUP_FILE" ]; then
            BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
            print_success "Backup creato: $BACKUP_FILE ($BACKUP_SIZE)"
        else
            print_error "Errore nella creazione del backup"
            exit 1
        fi
    else
        print_warning "Backup saltato (a tuo rischio!)"
    fi
fi

# ========================
# TEST PARSER
# ========================

print_header "TEST PARSER SU PATH REALI"

print_step "Esecuzione test su 100 path casuali..."

if [ -f "$SCRIPT_DIR/test_parser.py" ]; then
    python3 "$SCRIPT_DIR/test_parser.py" --samples 100
else
    print_warning "test_parser.py non trovato, salto test"
fi

if [ "$TEST_ONLY" = true ]; then
    print_success "Modalità TEST-ONLY completata"
    exit 0
fi

echo ""
if ! ask_confirmation "Risultati OK? Vuoi procedere con l'enrichment?"; then
    print_warning "Operazione annullata dall'utente"
    exit 0
fi

# ========================
# ANALISI PRELIMINARE
# ========================

print_header "ANALISI PRELIMINARE"

print_step "Analisi metadati estraibili (sola lettura)..."

if [ -f "$SCRIPT_DIR/enrich_metadata.py" ]; then
    python3 "$SCRIPT_DIR/enrich_metadata.py" --analyze
else
    print_error "enrich_metadata.py non trovato!"
    exit 1
fi

echo ""
if ! ask_confirmation "Vuoi procedere con l'update dello schema e l'enrichment?"; then
    print_warning "Operazione annullata dall'utente"
    exit 0
fi

# ========================
# UPDATE SCHEMA
# ========================

print_header "UPDATE SCHEMA POSTGRESQL"

print_step "Aggiunta colonne metadati al database..."

python3 "$SCRIPT_DIR/enrich_metadata.py" --update-schema

print_success "Schema aggiornato"

# ========================
# ENRICHMENT
# ========================

print_header "ENRICHMENT METADATI"

print_step "Arricchimento documenti con nuovi metadati..."
print_step "Questo potrebbe richiedere 3-5 minuti per 14K documenti..."

python3 "$SCRIPT_DIR/enrich_metadata.py" --enrich

print_success "Enrichment completato"

# ========================
# REINDEX MEILISEARCH
# ========================

if docker compose ps | grep -q "kbsearch-meili-1.*Up"; then
    print_header "REINDEX MEILISEARCH"
    
    print_step "Reindexing con nuovi metadati..."
    
    python3 "$SCRIPT_DIR/enrich_metadata.py" --reindex
    
    print_success "Reindex completato"
else
    print_warning "Meilisearch non disponibile, reindex saltato"
fi

# ========================
# VERIFICA RISULTATI
# ========================

print_header "VERIFICA RISULTATI"

print_step "Verifica schema PostgreSQL..."
docker exec kbsearch-postgres-1 psql -U kbuser -d kb -c "\d documents" | grep -E "(sd_numero|lotto|progressivo_oda|progressivo_as|numero_rdo|fase)"

echo ""
print_step "Statistiche metadati popolati..."
docker exec kbsearch-postgres-1 psql -U kbuser -d kb -c "
SELECT 
  COUNT(*) as totali,
  COUNT(sd_numero) as con_sd_numero,
  COUNT(lotto) as con_lotto,
  COUNT(progressivo_oda) as con_oda,
  COUNT(progressivo_as) as con_as,
  COUNT(numero_rdo) as con_rdo,
  COUNT(fase) as con_fase
FROM documents;
"

echo ""
print_step "Esempi di documenti arricchiti..."
docker exec kbsearch-postgres-1 psql -U kbuser -d kb -c "
SELECT 
  title, 
  sd_numero, 
  lotto, 
  progressivo_oda, 
  cliente, 
  fase
FROM documents
WHERE sd_numero IS NOT NULL
LIMIT 5;
"

# ========================
# SUMMARY
# ========================

print_header "✓ DEPLOY COMPLETATO CON SUCCESSO!"

echo ""
echo "📋 Riepilogo operazioni:"
echo "   ✓ Schema database aggiornato"
echo "   ✓ Metadati arricchiti"
echo "   ✓ Meilisearch reindexato"
echo ""
echo "🔍 Test ricerca con nuovi filtri:"
echo ""
echo "   # API"
echo "   curl -s 'http://localhost:8000/filters' | jq"
echo ""
echo "   # UI"
echo "   http://localhost:8000"
echo ""

if [ -f "$BACKUP_FILE" ]; then
    echo "💾 Backup salvato in: $BACKUP_FILE"
    echo ""
fi

echo "📚 Per maggiori dettagli, consulta:"
echo "   • GUIDA_ENRICHMENT.md"
echo "   • Test parser: python3 test_parser.py --help"
echo ""

print_success "Tutto pronto! 🚀"
