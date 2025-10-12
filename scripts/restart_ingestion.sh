#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-incremental}"   # incremental | full
API="http://127.0.0.1:8000"
QUEUE="kb_ingestion"
REDIS_URL="redis://redis:6379/0"

say(){ printf "\n==> %s\n" "$*"; }

# 0) sanity: docker compose up i servizi base (opzionale ma comodo)
if ! docker compose ps >/dev/null 2>&1; then
  say "Avvio dei servizi base…"
  docker compose up -d redis postgres qdrant meili >/dev/null
fi

# 1) (ri)avvia il worker
say "Riavvio worker…"
docker compose restart worker >/dev/null

# 2) attendi che Redis risponda dal container redis
say "Attendo Redis (redis-cli ping)…"
for i in {1..90}; do
  if docker compose exec -T redis redis-cli -p 6379 ping 2>/dev/null | grep -q PONG; then
    echo "Redis OK"
    break
  fi
  sleep 1
  if [[ $i -eq 90 ]]; then
    echo "Redis non raggiungibile" >&2
    exit 1
  fi
done

# 3) attendi che il worker sia in ascolto sulla coda
say "Attendo che il worker sia in ascolto sulla coda '${QUEUE}'…"
for i in {1..120}; do
  if docker compose logs --since=30s worker 2>/dev/null | grep -qE "\*\*\* Listening on ${QUEUE}"; then
    echo "Worker in ascolto"
    break
  fi
  sleep 1
  if [[ $i -eq 120 ]]; then
    echo "Worker non ancora in ascolto (timeout)" >&2
    docker compose logs --tail=80 worker || true
    exit 1
  fi
done

# 4) sblocco registries e requeue dei failed (via Python = più affidabile del CLI)
say "Sblocco registries e requeue dei failed…"
docker compose exec -T worker python - <<PY
from redis import Redis
from rq import Queue
from rq.registry import FailedJobRegistry, StartedJobRegistry
from rq.job import Job

r = Redis(host="redis", port=6379, db=0)
q = Queue("${QUEUE}", connection=r)

# ripulisci gli stuck in Started (rimetti in coda)
started = StartedJobRegistry(queue=q)
for jid in list(started.get_job_ids()):
    try:
        job = Job.fetch(jid, connection=r)
        started.remove(jid, delete_job=False)
        q.enqueue_job(job)
    except Exception as e:
        print("WARN started:", jid, e)

# requeue di tutti i failed
failed = FailedJobRegistry(queue=q)
for jid in list(failed.get_job_ids()):
    try:
        failed.requeue(jid)
    except Exception as e:
        print("WARN failed:", jid, e)

print("Done requeue/started-clean")
PY

# 5) stato RQ via API
say "Stato RQ (active/failed)…"
curl -sf "${API}/rq/active"  | jq || true
curl -sf "${API}/rq/failed"  | jq || true

# 6) avvio ingestion
say "Avvio ingestion: ${MODE}"
if [[ "$MODE" == "full" ]]; then
  curl -sf -X POST "${API}/ingestion/start?mode=full"         | jq
else
  curl -sf -X POST "${API}/ingestion/start?mode=incremental"  | jq
fi

# 7) progress iniziale
say "Progress iniziale"
curl -sf "${API}/ingestion/progress" | jq

# 8) ultimi log worker (per conferma)
say "Log worker (ultime 80 righe)"
docker compose logs --tail=80 worker
