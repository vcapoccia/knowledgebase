#!/usr/bin/env bash
set -euo pipefail

echo "===> worker-entrypoint.sh avviato"

# -----------------------------
# Env di default (override via docker-compose/.env)
# -----------------------------
: "${QUEUE_NAME:=kb_ingestion}"
: "${REDIS_URL:=redis://redis:6379/0}"
: "${RQ_JOB_TIMEOUT:=21600}"          # 6h
: "${RQ_RESULT_TTL:=500}"             # TTL risultati
: "${PYTHONUNBUFFERED:=1}"
: "${LANG:=C.UTF-8}"
: "${LC_ALL:=C.UTF-8}"
export PYTHONUNBUFFERED LANG LC_ALL

# -----------------------------
# Sanitize env che possono iniettare opzioni RQ duplicate
# -----------------------------
# Alcuni ambienti impostano queste variabili causando la duplicazione di --serializer / -S.
unset RQ_CLI_OPTIONS || true
unset RQ_SERIALIZER || true
unset RQ_WORKER_OPTS || true
unset RQ_WORKER_ARGS || true

# -----------------------------
# Info OCR / Parser (facoltative)
# -----------------------------
if command -v tesseract >/dev/null 2>&1; then
  echo "Tesseract: $(tesseract --version | head -n1 || true)"
else
  echo "Tesseract non installato (ok se OCR disattivato)"
fi

if command -v pdftotext >/dev/null 2>&1; then
  echo "Poppler/pdftotext OK"
else
  echo "pdftotext non trovato"
fi

if command -v soffice >/dev/null 2>&1; then
  echo "LibreOffice: $(soffice --version || true)"
else
  echo "LibreOffice non trovato (conversione doc/xls via unoconv potrebbe non funzionare)"
fi

python - <<'PY'
import rq, sys
print("RQ version:", rq.__version__)
PY

# -----------------------------
# Verifiche minime file applicativi
# -----------------------------
if [[ ! -f /app/worker_tasks.py ]]; then
  echo "ERRORE: /app/worker_tasks.py non trovato. Controlla il bind mount / build."
  ls -la /app || true
  exit 1
fi

# -----------------------------
# Attendi Redis pronto (senza redis-cli)
# -----------------------------
echo "===> Attendo Redis su: ${REDIS_URL}"
python - <<'PY'
import os, sys, time
import redis
url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
for i in range(60):
    try:
        r = redis.from_url(url)
        r.ping()
        print("Redis OK")
        sys.exit(0)
    except Exception as e:
        print(f"Redis non pronto, retry {i+1}/60: {e}")
        time.sleep(1)
print("Redis non raggiungibile, esco con errore.")
sys.exit(1)
PY

# -----------------------------
# Avvio RQ worker
# NOTE:
# - niente flag non supportati
# - nessun flag/var che imposti serializer (evita i warning click)
# -----------------------------
echo "===> Avvio RQ worker sulla coda '${QUEUE_NAME}' con REDIS_URL='${REDIS_URL}'"
echo "     JOB_TIMEOUT=${RQ_JOB_TIMEOUT}s, RESULT_TTL=${RQ_RESULT_TTL}s"

exec rq worker \
  --url "${REDIS_URL}" \
  --job-monitoring-interval 5 \
  --results-ttl "${RQ_RESULT_TTL}" \
  --worker-ttl 420 \
  "${QUEUE_NAME}"