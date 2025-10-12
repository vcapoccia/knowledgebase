#!/usr/bin/env bash
API="http://127.0.0.1:8000"
QDRANT="http://127.0.0.1:6333"
WORKER=$(docker ps --filter "name=kbsearch-worker" --format "{{.Names}}" | head -n1)
OLLAMA=$(docker ps --filter "name=kbsearch-ollama" --format "{{.Names}}" | head -n1)

interval=${1:-5}

if ! command -v jq >/dev/null 2>&1; then
  echo "Installare jq per una stampa più pulita (apt-get install -y jq). Continuo comunque..."
  jq(){ cat; }
fi

clear
echo "Monitor Ingestion (refresh ogni ${interval}s) — Ctrl+C per uscire"
echo

while :; do
  NOW=$(date +"%F %T")
  echo "=== ${NOW} ============================================================="

  echo "-- Stato API /health"
  curl -s "$API/health" | jq .

  echo
  echo "-- Coda RQ / Ingestion"
  curl -s "$API/ingestion/status" | jq .

  echo
  echo "-- Progresso /ingestion/progress"
  curl -s "$API/ingestion/progress" | jq .

  echo
  echo "-- Qdrant: kb_chunks -> count punti"
  curl -s "$QDRANT/collections/kb_chunks/points/count" \
    -H 'Content-Type: application/json' \
    -d '{"exact":true}' | jq .

  echo
  echo "-- Docker stats (worker / ollama)"
  if [ -n "$WORKER" ] || [ -n "$OLLAMA" ]; then
    docker stats --no-stream $WORKER $OLLAMA 2>/dev/null
  else
    echo "N/D"
  fi

  echo
  echo "-- GPU (nvidia-smi, se presente)"
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,utilization.gpu,utilization.memory,memory.total,memory.used --format=csv,noheader,nounits
    echo
    echo "Processi GPU (pmon):"
    nvidia-smi pmon -s um -c 1 2>/dev/null || true
  else
    echo "nvidia-smi non trovato su host."
  fi

  echo
  echo "----------------------------------------------------------------------"
  sleep "$interval"
done
