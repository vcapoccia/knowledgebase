#!/usr/bin/env bash
set -euo pipefail

API="http://127.0.0.1:8000"

echo "==> Stato RQ (active jobs)"
curl -sf "${API}/rq/active" | jq || echo "Errore rq/active"

echo
echo "==> Stato RQ (failed jobs)"
curl -sf "${API}/rq/failed" | jq || echo "Errore rq/failed"

echo
echo "==> Stato ingestion (progress)"
curl -sf "${API}/ingestion/progress" | jq || echo "Errore ingestion/progress"

echo
echo "==> Stato ingestion (failed docs)"
curl -sf "${API}/ingestion/failed?limit=20" | jq || echo "Errore ingestion/failed"

echo
echo "==> Stato Qdrant (collections)"
curl -sf http://127.0.0.1:6333/collections | jq || echo "Errore Qdrant collections"

echo
echo "==> Conteggio punti in kb_chunks"
curl -sf -H "Content-Type: application/json" \
  -d '{"exact":true}' \
  "http://127.0.0.1:6333/collections/kb_chunks/points/count" | jq || echo "Errore Qdrant count"

echo
echo "==> Ultimi log worker (50 righe)"
docker compose logs --tail=50 worker || echo "Errore docker logs worker"

