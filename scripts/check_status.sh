#!/usr/bin/env bash
set -euo pipefail

ROOT="/opt/kbsearch"
ENV_FILE="$ROOT/.env"

# --- Helpers ---
have() { command -v "$1" >/dev/null 2>&1; }
hr() { printf '\n——— %s ———\n' "$1"; }

# --- Load .env safely ---
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC2046
  export $(grep -E '^(MEILI_MASTER_KEY|EMBED_MODEL|VECTOR_SIZE|QDRANT_COLLECTION|OLLAMA_PORT|OLLAMA_HOST|KB_ROOT)=' "$ENV_FILE" | xargs)
fi

# Defaults if missing
: "${MEILI_MASTER_KEY:=change_me_meili_key}"
: "${EMBED_MODEL:=nomic-embed-text}"
: "${VECTOR_SIZE:=768}"
: "${QDRANT_COLLECTION:=kb_chunks}"
: "${OLLAMA_HOST:=127.0.0.1}"
: "${OLLAMA_PORT:=11434}"

API_URL="http://127.0.0.1:8000"
MEILI_URL="http://127.0.0.1:7700"
QDRANT_URL="http://127.0.0.1:6333"
OLLAMA_URL="http://${OLLAMA_HOST}:${OLLAMA_PORT}"

WORKER_CONT=$(docker ps --filter "name=kbsearch-worker" --format "{{.Names}}" | head -n1 || true)

hr "STACK"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | sed 's/^/  /'

hr "API /health"
curl -fsS "${API_URL}/health" | (have jq && jq || cat)

hr "RQ / Worker"
if [[ -n "$WORKER_CONT" ]]; then
  docker exec "$WORKER_CONT" rq info -u redis://redis:6379/0 || true
else
  echo "  Nessun container worker trovato."
fi

hr "Ingestion queue (API)"
hr "Ingestion progress (API)"; 
curl -fsS "http://127.0.0.1:8000/ingestion/progress" | (command -v jq >/dev/null && jq || cat)
curl -fsS "${API_URL}/ingestion/status" | (have jq && jq || cat)

hr "Qdrant: collection config"
curl -fsS "${QDRANT_URL}/collections/${QDRANT_COLLECTION}" \
| (have jq && jq '{vectors:.result.config.params.vectors, status:.result.status}' || cat)

hr "Qdrant: points count"
curl -fsS -X POST "${QDRANT_URL}/collections/${QDRANT_COLLECTION}/points/count" \
  -H "Content-Type: application/json" -d '{"exact":true}' \
| (have jq && jq '.result' || cat)

hr "Meili: indexes"

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

curl -fsS "${MEILI_URL}/indexes" \

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

  -H "Authorization: Bearer ${MEILI_MASTER_KEY}" \

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

| (have jq && jq 'if type=="array" then map({uid, nbDocuments}) else . end' || cat)

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)



echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

hr "Ollama: embeddings smoke test"

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

EMBED_JSON=$(curl -fsS --max-time 5 "${OLLAMA_URL}/api/embeddings" \

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

  -d "{\"model\":\"${EMBED_MODEL}\",\"prompt\":\"prova di embedding\"}" 2>/dev/null || echo '{}')

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)



echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

# fallback se non risponde

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

if [[ "$EMBED_JSON" == '{}' ]]; then

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

  OLLAMA_URL="http://127.0.0.1:11434"

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

  EMBED_JSON=$(curl -fsS --max-time 5 "${OLLAMA_URL}/api/embeddings" \

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

    -d "{\"model\":\"${EMBED_MODEL}\",\"prompt\":\"prova di embedding\"}" 2>/dev/null || echo '{}')

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

fi

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)



echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

if have jq; then

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

  LEN=$(printf '%s' "$EMBED_JSON" | jq 'if .embedding then (.embedding|length) else (.embeddings[0]|length) end // 0')

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

  echo "  Model: ${EMBED_MODEL}"

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

  echo "  Embedding length: ${LEN}"

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

else

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

  echo "  (jq non disponibile) risposta grezza:"

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

  echo "  $EMBED_JSON"

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

fi

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)



echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

hr "Search test (API)"

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

curl -fsS -X POST "${API_URL}/search" \

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

  -H 'Content-Type: application/json' \

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

  -d '{"q":"offerta tecnica","limit":3}' \

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

| (have jq && jq '{results_count:(.results|length), results:.results}' || cat)

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)



echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

hr "KB mount visibility (inside worker)"

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

if [[ -n "$WORKER_CONT" ]]; then

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

  docker exec "$WORKER_CONT" bash -lc 'ls -lah ${KB_ROOT:-/mnt/kb} | head -n 20' || true

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

else

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

  echo "  Worker non trovato."

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

fi

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)



echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

echo

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

echo "Done."

echo "——— Meili: kb_docs stats ———"
MEILI_KEY=$(grep ^MEILI_MASTER_KEY= /opt/kbsearch/.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:7700/indexes/kb_docs/stats" -H "Authorization: Bearer ${MEILI_KEY}" | (have jq  jq || cat)

