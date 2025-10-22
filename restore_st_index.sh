#!/bin/bash
set -e

echo "🔄 RIPRISTINO INDICE SENTENCE-TRANSFORMER"
echo "=========================================="
echo ""

# 1. Fix version warning
echo "1. Fix docker-compose warning..."
sed -i '/^version:/d' docker-compose.override.yml
echo "   ✅ Version rimosso"
echo ""

# 2. Status attuale
echo "2. Collections attuali:"
curl -s http://localhost:6333/collections | jq '.result.collections'
echo ""

LLAMA_POINTS=$(curl -s http://localhost:6333/collections/kb_llama3_docs | jq -r '.result.points_count // 0')
echo "   kb_llama3_docs: $LLAMA_POINTS points (✅ mantieni, sta processando)"
echo ""

# 3. Crea kb_st_docs (se non esiste)
echo "3. Ricrea collection kb_st_docs..."

CREATE_RESULT=$(curl -s -X PUT http://localhost:6333/collections/kb_st_docs \
  -H 'Content-Type: application/json' \
  -d '{
    "vectors": {
      "size": 384,
      "distance": "Cosine"
    }
  }')

if echo "$CREATE_RESULT" | grep -q '"status":"ok"'; then
    echo "   ✅ kb_st_docs creata"
elif echo "$CREATE_RESULT" | grep -q "already exists"; then
    echo "   ✅ kb_st_docs già esiste"
else
    echo "   ❌ Errore creazione:"
    echo "$CREATE_RESULT" | jq
    exit 1
fi
echo ""

# 4. Verifica collections
echo "4. Collections dopo setup:"
curl -s http://localhost:6333/collections | jq -r '.result.collections[] | "   \(.name)"'
echo ""

# 5. Check documenti DB
DB_COUNT=$(docker compose exec -T postgres psql -U kbuser -d kb -c "SELECT COUNT(*) FROM documents;" | grep -o '[0-9]\+' | head -1)
echo "5. Documenti in PostgreSQL: $DB_COUNT"
echo ""

# 6. Avvia ingestion SOLO sentence-transformer
echo "6. Avvio ingestion sentence-transformer (incremental)..."
echo "   → Veloce! Docs già estratti, crea solo embeddings"
echo ""

INGEST_RESULT=$(curl -s -X POST "http://localhost:8000/ingestion/start?model=sentence-transformer&mode=incremental")

if echo "$INGEST_RESULT" | grep -q "started\|running"; then
    echo "   ✅ Ingestion avviata"
else
    echo "   Risultato:"
    echo "$INGEST_RESULT" | jq
fi

echo ""
echo "================================"
echo "✅ RIPRISTINO AVVIATO"
echo "================================"
echo ""
echo "STATO SISTEMA:"
echo "  ✅ kb_llama3_docs: $LLAMA_POINTS points (continua a processare)"
echo "  🔄 kb_st_docs: 0 points (sta creando...)"
echo ""
echo "TEMPO STIMATO:"
echo "  kb_st_docs: ~2-3 ore (GPU accelerato)"
echo "  kb_llama3_docs: continua in background"
echo ""
echo "MONITOR:"
echo "  Dashboard: http://localhost:8000/admin"
echo ""
echo "  CLI:"
echo "  watch -n 30 'echo \"ST: \$(curl -s http://localhost:6333/collections/kb_st_docs | jq -r .result.points_count)\" && echo \"Llama3: \$(curl -s http://localhost:6333/collections/kb_llama3_docs | jq -r .result.points_count)\"'"
echo ""

# 7. Wait e verifica
sleep 30

echo "Status dopo 30s:"
ST_POINTS=$(curl -s http://localhost:6333/collections/kb_st_docs | jq -r '.result.points_count // 0')
LLAMA_POINTS_NEW=$(curl -s http://localhost:6333/collections/kb_llama3_docs | jq -r '.result.points_count // 0')
PROGRESS=$(curl -s http://localhost:8000/progress | jq -r '.done // 0')

echo "  kb_st_docs: $ST_POINTS vectors"
echo "  kb_llama3_docs: $LLAMA_POINTS_NEW vectors"
echo "  Worker progress: $PROGRESS/$DB_COUNT"
echo ""

if [ "$ST_POINTS" -gt 0 ]; then
    echo "✅ kb_st_docs in creazione! Ricerca ST tornerà disponibile tra poco!"
else
    echo "⏳ kb_st_docs in setup... aspetta qualche minuto"
fi

