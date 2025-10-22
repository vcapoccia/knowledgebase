#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config/backup.conf"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${BACKUP_ROOT}/backup_${TIMESTAMP}.log"

# Funzioni
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

error() {
    log "❌ ERROR: $1"
    exit 1
}

notify() {
    if [ -n "$NOTIFY_EMAIL" ]; then
        echo "$1" | mail -s "KBSearch Backup: $2" "$NOTIFY_EMAIL"
    fi
}

compress() {
    local file=$1
    case $COMPRESSION in
        gzip)
            gzip -9 "$file"
            echo "${file}.gz"
            ;;
        zstd)
            zstd -19 --rm "$file"
            echo "${file}.zst"
            ;;
        none)
            echo "$file"
            ;;
    esac
}

# ============================================
# MAIN BACKUP
# ============================================

log "🚀 BACKUP KBSEARCH STARTED"
log "============================================"

# Crea directory
mkdir -p "$BACKUP_APP_DIR" "$BACKUP_DB_DIR"

APP_BACKUP="${BACKUP_APP_DIR}/app_${TIMESTAMP}"
DB_BACKUP="${BACKUP_DB_DIR}/db_${TIMESTAMP}"
mkdir -p "$APP_BACKUP" "$DB_BACKUP"

# ============================================
# 1. APPLICATION FILES
# ============================================
log "📦 1. Backup Application Files..."

cd "$PROJECT_ROOT"

# Backup codice (escludi data/)
tar -czf "${APP_BACKUP}/code.tar.gz" \
    --exclude='data/*' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.git' \
    --exclude='backup_*' \
    .

SIZE_CODE=$(du -sh "${APP_BACKUP}/code.tar.gz" | cut -f1)
log "   ✅ Code backup: $SIZE_CODE"

# Backup docker-compose
cp docker-compose.yml "${APP_BACKUP}/"
cp docker-compose.override.yml "${APP_BACKUP}/" 2>/dev/null || true

# Backup scripts
cp -r scripts "${APP_BACKUP}/" 2>/dev/null || true

log "   ✅ Application files backed up"

# ============================================
# 2. POSTGRESQL
# ============================================
log "📊 2. Backup PostgreSQL..."

docker exec "$POSTGRES_CONTAINER" pg_dump -U kbuser kb > "${DB_BACKUP}/postgres_kb.sql"

COMPRESSED_PG=$(compress "${DB_BACKUP}/postgres_kb.sql")
SIZE_PG=$(du -sh "$COMPRESSED_PG" | cut -f1)
log "   ✅ PostgreSQL: $SIZE_PG"

# Schema only (veloce)
docker exec "$POSTGRES_CONTAINER" pg_dump -U kbuser kb --schema-only > "${DB_BACKUP}/postgres_schema.sql"

# Stats
DOC_COUNT=$(docker exec -T "$POSTGRES_CONTAINER" psql -U kbuser -d kb -t -c "SELECT COUNT(*) FROM documents;" | xargs)
log "   📈 Documents in DB: $DOC_COUNT"

# ============================================
# 3. REDIS
# ============================================
log "🔴 3. Backup Redis..."

docker exec "$REDIS_CONTAINER" redis-cli SAVE
docker cp "${REDIS_CONTAINER}:/data/dump.rdb" "${DB_BACKUP}/redis_dump.rdb"

SIZE_REDIS=$(du -sh "${DB_BACKUP}/redis_dump.rdb" | cut -f1)
log "   ✅ Redis: $SIZE_REDIS"

# ============================================
# 4. QDRANT (CRITICAL!)
# ============================================
log "🎨 4. Backup Qdrant..."

# Qdrant snapshots
COLLECTIONS=("kb_st_docs" "kb_llama3_docs" "kb_mistral_docs")
for collection in "${COLLECTIONS[@]}"; do
    SNAP_RESULT=$(curl -s -X POST "http://localhost:6333/collections/${collection}/snapshots" 2>/dev/null || echo "SKIP")
    
    if echo "$SNAP_RESULT" | grep -q '"result"'; then
        SNAP_NAME=$(echo "$SNAP_RESULT" | jq -r '.result.name')
        log "   → Snapshot $collection: $SNAP_NAME"
        
        # Download snapshot
        curl -s "http://localhost:6333/collections/${collection}/snapshots/${SNAP_NAME}" \
            -o "${DB_BACKUP}/qdrant_${collection}.snapshot"
    else
        log "   ⚠️  Collection $collection not found or empty"
    fi
done

# Full Qdrant data dir (fallback)
docker exec "$QDRANT_CONTAINER" tar -czf /tmp/qdrant_full.tar.gz /qdrant/storage 2>/dev/null || true
docker cp "${QDRANT_CONTAINER}:/tmp/qdrant_full.tar.gz" "${DB_BACKUP}/" 2>/dev/null || true

if [ -f "${DB_BACKUP}/qdrant_full.tar.gz" ]; then
    SIZE_QDRANT=$(du -sh "${DB_BACKUP}/qdrant_full.tar.gz" | cut -f1)
    log "   ✅ Qdrant full: $SIZE_QDRANT"
fi

# Qdrant stats
for collection in "${COLLECTIONS[@]}"; do
    COUNT=$(curl -s "http://localhost:6333/collections/${collection}" 2>/dev/null | jq -r '.result.points_count // 0')
    if [ "$COUNT" != "0" ]; then
        log "   📊 $collection: $COUNT vectors"
    fi
done

# ============================================
# 5. MEILISEARCH
# ============================================
log "🔍 5. Backup Meilisearch..."

# Meilisearch dump
MEILI_DUMP=$(curl -s -X POST "http://localhost:7700/dumps" \
    -H "Authorization: Bearer ${MEILI_MASTER_KEY:-masterKey}" | jq -r '.uid')

if [ "$MEILI_DUMP" != "null" ]; then
    # Wait for dump
    sleep 10
    
    # Download dump
    MEILI_FILE=$(curl -s "http://localhost:7700/dumps/${MEILI_DUMP}/status" \
        -H "Authorization: Bearer ${MEILI_MASTER_KEY:-masterKey}" | jq -r '.status')
    
    log "   → Meilisearch dump: $MEILI_DUMP ($MEILI_FILE)"
fi

# ============================================
# 6. BACKUP MANIFEST
# ============================================
log "📋 6. Creating Manifest..."

cat > "${BACKUP_ROOT}/BACKUP_${TIMESTAMP}_MANIFEST.txt" << MANIFEST
KBSEARCH BACKUP MANIFEST
========================
Timestamp: $TIMESTAMP
Date: $(date)
Hostname: $(hostname)

APPLICATION:
- Code: ${APP_BACKUP}/code.tar.gz ($SIZE_CODE)
- Docker Compose: ${APP_BACKUP}/docker-compose*.yml

DATABASES:
- PostgreSQL: ${DB_BACKUP}/postgres_kb.sql* ($SIZE_PG)
  Documents: $DOC_COUNT
- Redis: ${DB_BACKUP}/redis_dump.rdb ($SIZE_REDIS)
- Qdrant: ${DB_BACKUP}/qdrant_* ($SIZE_QDRANT)
- Meilisearch: dump_${MEILI_DUMP}

RESTORE COMMAND:
  $SCRIPT_DIR/restore.sh ${TIMESTAMP}

MANIFEST

log "   ✅ Manifest created"

# ============================================
# 7. CLEANUP OLD BACKUPS
# ============================================
log "🗑️  7. Cleanup old backups (>${RETENTION_DAYS} days)..."

find "$BACKUP_APP_DIR" -type d -mtime +$RETENTION_DAYS -exec rm -rf {} + 2>/dev/null || true
find "$BACKUP_DB_DIR" -type d -mtime +$RETENTION_DAYS -exec rm -rf {} + 2>/dev/null || true

OLD_COUNT=$(find "$BACKUP_ROOT" -name "BACKUP_*_MANIFEST.txt" -mtime +$RETENTION_DAYS | wc -l)
find "$BACKUP_ROOT" -name "BACKUP_*_MANIFEST.txt" -mtime +$RETENTION_DAYS -delete

log "   ✅ Removed $OLD_COUNT old backups"

# ============================================
# 8. FINAL STATS
# ============================================
TOTAL_SIZE=$(du -sh "$BACKUP_ROOT" | cut -f1)

log "============================================"
log "✅ BACKUP COMPLETED SUCCESSFULLY"
log "============================================"
log "Total backup size: $TOTAL_SIZE"
log "Location: $BACKUP_ROOT"
log "Manifest: ${BACKUP_ROOT}/BACKUP_${TIMESTAMP}_MANIFEST.txt"
log ""
log "To restore: $SCRIPT_DIR/restore.sh $TIMESTAMP"

notify "Backup completed: $TOTAL_SIZE" "SUCCESS"


# ============================================
# SYNC TO GITHUB (opzionale)
# ============================================

if [ -f "$SCRIPT_DIR/config/github.conf" ]; then
    source "$SCRIPT_DIR/config/github.conf"
    
    if [ "$AUTO_COMMIT" = "true" ]; then
        log "🔄 Syncing backup scripts to GitHub..."
        
        bash "$SCRIPT_DIR/sync_github.sh" -m "Backup completed: $TIMESTAMP" 2>&1 | tee -a "$LOG_FILE"
    fi
fi

