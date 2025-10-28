#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# DIAGNOSTICA BACKEND - Post-Reboot
# ═══════════════════════════════════════════════════════════════

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              DIAGNOSTICA BACKEND KB SEARCH                     ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# ═══════════════════════════════════════════════════════════════
# TEST 1: Docker
# ═══════════════════════════════════════════════════════════════
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 1: Docker Service"
echo "═══════════════════════════════════════════════════════════════"

systemctl is-active docker > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Docker service: RUNNING"
else
    echo "❌ Docker service: NOT RUNNING"
    echo "   FIX: systemctl start docker"
    exit 1
fi
echo ""

# ═══════════════════════════════════════════════════════════════
# TEST 2: Container Status
# ═══════════════════════════════════════════════════════════════
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 2: Container Status"
echo "═══════════════════════════════════════════════════════════════"

cd /opt/kbsearch 2>/dev/null || cd /home/vcapoccia/kbsearch 2>/dev/null

if [ ! -f "docker-compose.yml" ]; then
    echo "❌ docker-compose.yml non trovato!"
    echo "   Sei nella directory corretta?"
    exit 1
fi

echo "Container attivi:"
docker-compose ps

echo ""
echo "Verifica container critici..."

# Postgres
if docker-compose ps | grep -q "kbsearch-postgres.*Up"; then
    echo "✅ PostgreSQL: UP"
else
    echo "❌ PostgreSQL: DOWN"
    echo "   FIX: docker-compose up -d kbsearch-postgres"
fi

# Backend/API
if docker-compose ps | grep -q "kbsearch.*Up"; then
    echo "✅ Backend API: UP"
else
    echo "❌ Backend API: DOWN"
    echo "   FIX: docker-compose up -d kbsearch"
fi

# Qdrant (se presente)
if docker-compose ps | grep -q "qdrant.*Up"; then
    echo "✅ Qdrant: UP"
elif docker ps -a | grep -q qdrant; then
    echo "⚠️  Qdrant: EXISTS but not UP"
else
    echo "ℹ️  Qdrant: not configured (ok se usi Postgres per embeddings)"
fi

echo ""

# ═══════════════════════════════════════════════════════════════
# TEST 3: PostgreSQL Connectivity
# ═══════════════════════════════════════════════════════════════
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 3: PostgreSQL Connectivity"
echo "═══════════════════════════════════════════════════════════════"

docker exec kbsearch-postgres-1 pg_isready -U kbuser > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ PostgreSQL: ACCEPTING CONNECTIONS"
    
    # Test query
    ROWS=$(docker exec kbsearch-postgres-1 psql -U kbuser -d kb -t -c "SELECT COUNT(*) FROM documents;" 2>/dev/null | tr -d ' ')
    if [ ! -z "$ROWS" ]; then
        echo "✅ Database query: OK ($ROWS documenti)"
    else
        echo "❌ Database query: FAILED"
    fi
else
    echo "❌ PostgreSQL: NOT ACCEPTING CONNECTIONS"
    echo "   FIX: docker-compose restart kbsearch-postgres"
fi
echo ""

# ═══════════════════════════════════════════════════════════════
# TEST 4: Backend API Health
# ═══════════════════════════════════════════════════════════════
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 4: Backend API Health"
echo "═══════════════════════════════════════════════════════════════"

# Health check endpoint
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health 2>/dev/null)
if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ API Health endpoint: OK (200)"
elif [ "$HTTP_CODE" = "000" ]; then
    echo "❌ API: NOT RESPONDING (connection refused)"
    echo "   Backend non risponde - verifica logs"
else
    echo "⚠️  API Health: HTTP $HTTP_CODE"
fi

# Search endpoint (senza query)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/search?q_text=test 2>/dev/null)
if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Search endpoint: OK (200)"
elif [ "$HTTP_CODE" = "500" ]; then
    echo "❌ Search endpoint: ERROR 500 (backend crash)"
    echo "   ⚠️  QUESTO È IL PROBLEMA!"
else
    echo "⚠️  Search endpoint: HTTP $HTTP_CODE"
fi
echo ""

# ═══════════════════════════════════════════════════════════════
# TEST 5: Ollama/LLM Service (se usato)
# ═══════════════════════════════════════════════════════════════
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 5: Ollama/LLM Service"
echo "═══════════════════════════════════════════════════════════════"

# Check se Ollama è configurato
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✅ Ollama: RUNNING"
    MODELS=$(curl -s http://localhost:11434/api/tags | grep -o '"name"' | wc -l)
    echo "   Modelli disponibili: $MODELS"
else
    echo "ℹ️  Ollama: NOT RUNNING (ok se non usi LLaMA/Mistral)"
fi
echo ""

# ═══════════════════════════════════════════════════════════════
# TEST 6: Backend Logs (ultimi errori)
# ═══════════════════════════════════════════════════════════════
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 6: Backend Logs (ultimi 20 righe)"
echo "═══════════════════════════════════════════════════════════════"

echo "Logs backend (cerca errori):"
docker-compose logs --tail=20 kbsearch 2>/dev/null

echo ""

# ═══════════════════════════════════════════════════════════════
# TEST 7: Network Connectivity
# ═══════════════════════════════════════════════════════════════
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 7: Network Connectivity"
echo "═══════════════════════════════════════════════════════════════"

# Ping tra container
docker exec kbsearch ping -c 1 kbsearch-postgres > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Network kbsearch → postgres: OK"
else
    echo "❌ Network kbsearch → postgres: FAILED"
    echo "   FIX: docker-compose down && docker-compose up -d"
fi
echo ""

# ═══════════════════════════════════════════════════════════════
# TEST 8: Disk Space
# ═══════════════════════════════════════════════════════════════
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 8: Disk Space"
echo "═══════════════════════════════════════════════════════════════"

DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 90 ]; then
    echo "✅ Disk space: OK ($DISK_USAGE% used)"
else
    echo "⚠️  Disk space: LOW ($DISK_USAGE% used)"
fi
echo ""

# ═══════════════════════════════════════════════════════════════
# TEST 9: Port Bindings
# ═══════════════════════════════════════════════════════════════
echo "═══════════════════════════════════════════════════════════════"
echo "TEST 9: Port Bindings"
echo "═══════════════════════════════════════════════════════════════"

# Check porta 8080 (backend)
if netstat -tuln | grep -q ":8080 "; then
    echo "✅ Port 8080 (backend): LISTENING"
else
    echo "❌ Port 8080 (backend): NOT LISTENING"
    echo "   Backend non ha fatto bind sulla porta"
fi

# Check porta 5432 (postgres)
if netstat -tuln | grep -q ":5432 "; then
    echo "✅ Port 5432 (postgres): LISTENING"
else
    echo "❌ Port 5432 (postgres): NOT LISTENING"
fi

# Check porta 80 (nginx/frontend)
if netstat -tuln | grep -q ":80 "; then
    echo "✅ Port 80 (frontend): LISTENING"
else
    echo "⚠️  Port 80 (frontend): NOT LISTENING"
fi
echo ""

# ═══════════════════════════════════════════════════════════════
# RIEPILOGO
# ═══════════════════════════════════════════════════════════════
echo "═══════════════════════════════════════════════════════════════"
echo "RIEPILOGO DIAGNOSTICA"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Se vedi ❌ in uno dei test critici (1-4), quello è il problema!"
echo ""
echo "AZIONI COMUNI:"
echo "  1. Restart tutti i container:"
echo "     docker-compose restart"
echo ""
echo "  2. Riavvio completo:"
echo "     docker-compose down"
echo "     docker-compose up -d"
echo ""
echo "  3. Verifica logs dettagliati:"
echo "     docker-compose logs -f kbsearch"
echo ""
echo "  4. Check memoria:"
echo "     free -h"
echo "     docker stats --no-stream"
echo ""
echo "═══════════════════════════════════════════════════════════════"
