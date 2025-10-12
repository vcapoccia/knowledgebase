#!/bin/bash
# debug-kb.sh - Script completo per debug KB Search

echo "=== KB Search Debug Report ==="
echo "Generated: $(date)"
echo ""

echo "1. Container Status"
docker ps -a --filter "name=kbsearch" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

echo "2. Database Stats"
docker exec kbsearch-postgres-1 psql -U kbuser -d kb -c "
SELECT 
  status, 
  COUNT(*) as count,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
FROM documents 
GROUP BY status 
ORDER BY count DESC;
" 2>/dev/null || echo "❌ DB not accessible"
echo ""

echo "3. Redis Queue"
docker exec kbsearch-redis-1 redis-cli LLEN rq:queue:kb_ingestion 2>/dev/null || echo "❌ Redis not accessible"
echo ""

echo "4. Meilisearch Docs"
curl -s -H "Authorization: Bearer change_me_meili_key" \
  http://localhost:7700/indexes/kb_docs/stats 2>/dev/null | \
  jq -r '"Documents: \(.numberOfDocuments // 0)"' || echo "❌ Meili not accessible"
echo ""

echo "5. Qdrant Points"
curl -s http://localhost:6333/collections/kb_chunks 2>/dev/null | \
  jq -r '"Points: \(.result.points_count // 0)"' || echo "❌ Qdrant not accessible"
echo ""

echo "6. Worker Alive"
docker exec kbsearch-worker-1 ps aux | grep -q "rq worker" && echo "✓ Worker running" || echo "❌ Worker not running"
echo ""

echo "7. API Health"
curl -s http://localhost:8000/health >/dev/null && echo "✓ API responding" || echo "❌ API not responding"
echo ""

echo "8. Recent Errors (last 20 lines)"
docker logs kbsearch-worker-1 --tail 20 2>&1 | grep -i error || echo "No recent errors"
echo ""

echo "=== End Report ==="
