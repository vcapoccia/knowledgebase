#!/bin/bash
set -e

MEILI_KEY="change_me_meili_key"
API_URL="http://127.0.0.1:8000"
MEILI_URL="http://127.0.0.1:7700"

echo ">>> 1) Aggiorno impostazioni MeiliSearch..."
curl -s -X PATCH "$MEILI_URL/indexes/kb_docs/settings" \
  -H "Authorization: Bearer $MEILI_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "filterableAttributes": [
      "year",
      "cliente",
      "project_type",
      "anno_cliente_tipo",
      "ext",
      "size_class",
      "area",
      "lotto"
    ],
    "sortableAttributes": ["year","size_class"]
  }' | jq .

echo
echo ">>> 2) Resetto stati su Postgres (tutti -> new)..."
docker exec -i kbsearch-postgres-1 psql -U kbuser -d kb <<'SQL'
UPDATE documents
SET status='new', started_at=NULL, finished_at=NULL, last_error=NULL;
SQL

echo
echo ">>> 3) Avvio ingestion full..."
curl -s -X POST "$API_URL/ingestion/start?mode=full" | jq .

echo
echo ">>> Fatto. Puoi controllare lo stato con:"
echo "    curl -s $API_URL/ingestion/progress | jq ."

