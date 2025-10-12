#!/usr/bin/env bash
set -e

REDIS_URL="${REDIS_URL:-redis://redis:6379/0}"
MEILI_URL="${MEILI_URL:-http://127.0.0.1:7700}"
MEILI_MASTER_KEY="${MEILI_MASTER_KEY:-}"
QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:6333}"
API_URL="${API_URL:-http://127.0.0.1:8000}"

hdr=()
if [ -n "$MEILI_MASTER_KEY" ]; then
  hdr=(-H "Authorization: Bearer $MEILI_MASTER_KEY")
fi

clear

echo "=== RQ (queue/worker) ==="
docker exec -it kbsearch-worker-1 rq info -u "$REDIS_URL"

echo
echo "=== Jobs in coda (prime 10) ==="
docker exec -i kbsearch-redis-1 redis-cli -n 0 lrange rq:queue:kb_ingestion 0 9

echo
echo "=== Job attualmente in esecuzione (Started registry) ==="
docker exec -i kbsearch-redis-1 redis-cli -n 0 zrevrange rq:registry:started:kb_ingestion 0 0 WITHSCORES

echo
echo "=== Registry varie ==="
echo -n "started: "; docker exec -i kbsearch-redis-1 redis-cli -n 0 zcard rq:registry:started:kb_ingestion
echo -n "failed : "; docker exec -i kbsearch-redis-1 redis-cli -n 0 zcard rq:registry:failed:kb_ingestion
echo -n "deferred: "; docker exec -i kbsearch-redis-1 redis-cli -n 0 zcard rq:registry:deferred:kb_ingestion

echo
echo "=== Qdrant: punti in kb_chunks ==="
curl -s "$QDRANT_URL/collections/kb_chunks/points/count" | jq

echo
echo "=== Meili: documenti indicizzati (kb_docs) ==="
curl -s "${hdr[@]}" "$MEILI_URL/indexes/kb_docs/stats" | jq

echo
echo "=== API progress (best effort) ==="
curl -s "$API_URL/ingestion/progress"
echo