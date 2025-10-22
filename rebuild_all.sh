#!/bin/bash
set -e

echo "🔄 REBUILD COMPLETO SISTEMA"
echo "==========================="
echo ""

# Timer
START_TIME=$(date +%s)

# ============================================
# 1. STOP TUTTO
# ============================================
echo "1. ⏹️  STOP containers..."
docker compose down
echo "   ✅ Containers fermati"
echo ""

# ============================================
# 2. BACKUP DATABASE (Opzionale)
# ============================================
echo "2. 💾 BACKUP database (opzionale)..."
read -p "   Vuoi fare backup di data/ prima del prune? (s/N): " backup_choice

if [ "$backup_choice" = "s" ]; then
    BACKUP_DIR="../kbsearch_data_backup_$(date +%Y%m%d_%H%M%S)"
    echo "   → Backup in $BACKUP_DIR..."
    mkdir -p "$BACKUP_DIR"
    cp -r data/ "$BACKUP_DIR/" 2>/dev/null || true
    echo "   ✅ Backup creato: $(realpath $BACKUP_DIR)"
else
    echo "   ⏭️  Backup saltato"
fi
echo ""

# ============================================
# 3. PULIZIA DOCKER
# ============================================
echo "3. 🧹 PULIZIA Docker..."
echo ""

# Volumi (ATTENZIONE!)
read -p "   ⚠️  Eliminare VOLUMI Docker (cancella DB!)? (s/N): " prune_volumes
echo ""

if [ "$prune_volumes" = "s" ]; then
    echo "   → Prune COMPLETO (containers, images, volumes, networks, cache)"
    docker system prune -af --volumes
    echo "   ⚠️  Database cancellati! Serve re-ingestion"
else
    echo "   → Prune PARZIALE (containers, images, networks, cache)"
    docker system prune -af
    echo "   ✅ Database preservati"
fi

# Pulizia aggiuntiva
echo ""
echo "   → Pulizia build cache..."
docker builder prune -af

# Pulizia immagini dangling
echo "   → Pulizia immagini dangling..."
docker image prune -af

echo ""
echo "   ✅ Docker pulito"
echo ""

# ============================================
# 4. VERIFICA SPAZIO
# ============================================
echo "4. 💽 VERIFICA spazio disco..."
df -h . | tail -1
echo ""

# ============================================
# 5. BUILD IMAGES
# ============================================
echo "5. 🏗️  BUILD nuove images..."
echo ""

# API
echo "   → Building API..."
docker compose build --no-cache api

# Worker
echo "   → Building Worker..."
docker compose build --no-cache worker

echo ""
echo "   ✅ Build completato"
echo ""

# ============================================
# 6. START CONTAINERS
# ============================================
echo "6. 🚀 START containers..."
docker compose up -d

echo ""
echo "   ⏳ Attendo 20s per startup..."
sleep 20
echo ""

# ============================================
# 7. VERIFICA SALUTE
# ============================================
echo "7. 🏥 VERIFICA salute servizi..."
echo ""

# Container status
echo "   Container status:"
docker compose ps

echo ""

# Health checks
echo "   Health checks:"

# API
API_HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null || echo "FAIL")
if [[ "$API_HEALTH" == *"ok"* ]] || [[ "$API_HEALTH" == *"healthy"* ]]; then
    echo "   ✅ API: OK"
else
    echo "   ❌ API: FAIL"
fi

# PostgreSQL
PG_HEALTH=$(docker compose exec -T postgres pg_isready -U kbuser 2>/dev/null || echo "FAIL")
if [[ "$PG_HEALTH" == *"accepting"* ]]; then
    echo "   ✅ PostgreSQL: OK"
else
    echo "   ❌ PostgreSQL: FAIL"
fi

# Redis
REDIS_HEALTH=$(docker compose exec -T redis redis-cli ping 2>/dev/null || echo "FAIL")
if [[ "$REDIS_HEALTH" == "PONG" ]]; then
    echo "   ✅ Redis: OK"
else
    echo "   ❌ Redis: FAIL"
fi

# Qdrant
QDRANT_HEALTH=$(curl -s http://localhost:6333/healthz 2>/dev/null || echo "FAIL")
if [[ "$QDRANT_HEALTH" == *"ok"* ]] || [[ "$QDRANT_HEALTH" =~ ^[[:space:]]*$ ]]; then
    echo "   ✅ Qdrant: OK"
else
    echo "   ❌ Qdrant: FAIL"
fi

# Meilisearch
MEILI_HEALTH=$(curl -s http://localhost:7700/health 2>/dev/null || echo "FAIL")
if [[ "$MEILI_HEALTH" == *"available"* ]]; then
    echo "   ✅ Meilisearch: OK"
else
    echo "   ❌ Meilisearch: FAIL"
fi

# Worker
WORKER_STATUS=$(docker compose ps worker --format json 2>/dev/null | grep -q "running" && echo "OK" || echo "FAIL")
if [ "$WORKER_STATUS" = "OK" ]; then
    echo "   ✅ Worker: OK"
else
    echo "   ❌ Worker: FAIL"
fi

echo ""

# ============================================
# 8. GPU CHECK
# ============================================
echo "8. 🎮 VERIFICA GPU..."
GPU_CHECK=$(docker compose exec worker nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo "N/A")
if [ "$GPU_CHECK" != "N/A" ]; then
    echo "   ✅ GPU: $GPU_CHECK"
else
    echo "   ⚠️  GPU: Non disponibile"
fi
echo ""

# ============================================
# 9. DATABASE CHECK
# ============================================
echo "9. 🗄️  VERIFICA database..."

# Count documenti
DOC_COUNT=$(docker compose exec -T postgres psql -U kbuser -d kb -c "SELECT COUNT(*) FROM documents;" 2>/dev/null | grep -o '[0-9]\+' | head -1 || echo "0")
echo "   Documenti nel DB: $DOC_COUNT"

# Qdrant points
QDRANT_COUNT=$(curl -s http://localhost:6333/collections/kb_st_docs 2>/dev/null | grep -o '"points_count":[0-9]*' | grep -o '[0-9]*' || echo "0")
echo "   Qdrant vectors: $QDRANT_COUNT"

echo ""

if [ "$DOC_COUNT" -eq 0 ]; then
    echo "   ⚠️  Database vuoto! Serve ingestion:"
    echo "      curl -X POST 'http://localhost:8000/ingestion/start?model=sentence-transformer&mode=incremental'"
fi
echo ""

# ============================================
# SUMMARY
# ============================================
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo "================================"
echo "✅ REBUILD COMPLETATO!"
echo "================================"
echo ""
echo "Tempo impiegato: ${DURATION}s"
echo ""
echo "📊 RIEPILOGO:"
echo "   - Containers: $(docker compose ps --format json | grep -c running || echo 0) running"
echo "   - Documenti DB: $DOC_COUNT"
echo "   - Vectors: $QDRANT_COUNT"
echo ""
echo "🌐 ACCESSO:"
echo "   - Dashboard: http://localhost:8000"
echo "   - Admin: http://localhost:8000/admin"
echo "   - API Health: http://localhost:8000/health"
echo ""
echo "📝 LOG:"
echo "   docker compose logs -f api"
echo "   docker compose logs -f worker"
echo ""

# Se DB vuoto, reminder ingestion
if [ "$DOC_COUNT" -eq 0 ]; then
    echo "⚠️  AZIONE RICHIESTA:"
    echo "   Avvia ingestion con:"
    echo "   curl -X POST 'http://localhost:8000/ingestion/start?model=sentence-transformer&mode=incremental'"
    echo ""
fi

