#!/usr/bin/env bash
set -euo pipefail

# Coda target (puoi passare un nome diverso come 1° argomento)
QUEUE="${1:-kb_ingestion}"

echo "==> Sospendo i worker (blocca nuovi job)…"
docker compose exec -T worker rq suspend || true

echo "==> Svuoto la coda '${QUEUE}'…"
# Nota: rq empty accetta i nomi coda come argomenti, NON --queue
docker compose exec -T worker rq empty "${QUEUE}" || true

echo "==> Ripulisco registri RQ (scheduled/deferred/started/failed/canceled/finished)…"
docker compose exec -T worker python - <<'PY'
import os
from redis import Redis
from rq import Queue
from rq.job import Job
from rq.registry import ScheduledJobRegistry, DeferredJobRegistry, StartedJobRegistry, FailedJobRegistry, FinishedJobRegistry
try:
    from rq.registry import CanceledJobRegistry
except Exception:
    CanceledJobRegistry = None

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
QUEUE_NAME = os.environ.get("TARGET_QUEUE", "kb_ingestion")

r = Redis.from_url(REDIS_URL)
q = Queue(QUEUE_NAME, connection=r)

def purge_registry(reg):
    ids = list(reg.get_job_ids())
    for jid in ids:
        try:
            j = Job.fetch(jid, connection=r)
            try:
                j.cancel()
            except Exception:
                pass
            reg.remove(jid, delete_job=True)
        except Exception as e:
            print("WARN", type(reg).__name__, jid, e)
    print(f"cleared {type(reg).__name__}: {len(ids)}")

purge_registry(ScheduledJobRegistry(queue=q))
purge_registry(DeferredJobRegistry(queue=q))

# I "Started" in pratica sono job in esecuzione: li rimuoviamo dal registro.
# Se vuoi forzare, riavvia anche il container del worker dopo questo passo.
sr = StartedJobRegistry(queue=q)
for jid in list(sr.get_job_ids()):
    try:
        sr.remove(jid, delete_job=True)
    except Exception as e:
        print("WARN StartedJobRegistry", jid, e)
print("cleared StartedJobRegistry")

purge_registry(FailedJobRegistry(queue=q))

if CanceledJobRegistry:
    purge_registry(CanceledJobRegistry(queue=q))

# Anche i "Finished" (opzionale)
fn = FinishedJobRegistry(queue=q)
for jid in list(fn.get_job_ids()):
    try:
        fn.remove(jid, delete_job=True)
    except Exception:
        pass
print("cleared FinishedJobRegistry")
PY

echo "==> (Opzionale) Riattivo i worker (consigliato dopo pulizia)…"
docker compose exec -T worker rq resume || true

echo "==> (Opzionale) Riavvio container worker per essere sicuri che non resti niente appeso…"
docker compose restart worker

echo "==> Fatto."

