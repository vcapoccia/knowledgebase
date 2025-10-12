# api/route_admin.py
import os
import json
from typing import List, Dict, Any

import redis
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from redis import Redis
from rq import Queue

import psycopg
from psycopg.rows import dict_row
import meilisearch

# ===== ENV =====
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
RQ_QUEUE = os.getenv("RQ_QUEUE", "kb_ingestion")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "kb")
POSTGRES_USER = os.getenv("POSTGRES_USER", "kbuser")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "kbpass")

MEILI_URL = os.getenv("MEILI_URL", "http://meili:7700")
# accetta sia MEILI_MASTER_KEY sia MEILI_KEY
MEILI_MASTER_KEY = os.getenv("MEILI_MASTER_KEY", os.getenv("MEILI_KEY", "change_me_meili_key"))

Q_REDIS_KEY_PROGRESS = "kb:progress"        # string JSON
Q_REDIS_KEY_FAILED   = "kb:failed_docs"     # list JSON lines
MEILI_INDEX          = "kb_docs"

router = APIRouter()

# ===== Helpers =====
def rconn() -> Redis:
    return redis.from_url(REDIS_URL, decode_responses=True)

def meili_client() -> meilisearch.Client:
    return meilisearch.Client(MEILI_URL, MEILI_MASTER_KEY)

def pg_conn():
    dsn = f"host={POSTGRES_HOST} dbname={POSTGRES_DB} user={POSTGRES_USER} password={POSTGRES_PASSWORD}"
    return psycopg.connect(dsn, autocommit=True, row_factory=dict_row)

def ensure_pg_schema():
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            title TEXT,
            content TEXT,
            mtime TIMESTAMP DEFAULT NOW()
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_title ON documents USING btree (title);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_path  ON documents USING btree (path);")

# ===== Admin endpoints attesi dalla UI =====
@router.get("/queue")
def get_queue():
    q = Queue(RQ_QUEUE, connection=rconn())
    return {
        "name": q.name,
        "count": len(q.jobs),
        "scheduled": len(q.scheduled_job_registry),
        "started": len(q.started_job_registry),
        "deferred": len(q.deferred_job_registry),
        "failed": len(q.failed_job_registry),
    }

@router.get("/progress")
def get_progress():
    rc = rconn()
    raw = rc.get(Q_REDIS_KEY_PROGRESS)
    if not raw:
        return {"running": False, "done": 0, "total": 0, "stage": "idle"}
    try:
        return json.loads(raw)
    except Exception:
        return {"running": False, "done": 0, "total": 0, "stage": "idle"}

@router.get("/failed_docs")
def get_failed_docs(limit: int = Query(20, ge=1, le=200)):
    rc = rconn()
    items = rc.lrange(Q_REDIS_KEY_FAILED, 0, limit - 1) or []
    out: List[Dict[str, Any]] = []
    for it in items:
        try:
            out.append(json.loads(it))
        except Exception:
            out.append({"error": it})
    return out

@router.post("/init_indexes")
def init_indexes():
    # Meili: crea indice se non esiste e assesta chiave primaria
    client = meili_client()
    try:
        try:
            client.get_index(MEILI_INDEX)  # fa HTTP GET e fallisce se non esiste
        except meilisearch.errors.MeilisearchApiError:
            client.create_index(MEILI_INDEX, {"primaryKey": "id"})
        # opzionale: settaggi base
        client.index(MEILI_INDEX).update_settings({
            "rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"]
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"meili: {e}"}, status_code=500)

    # Postgres: crea schema
    try:
        ensure_pg_schema()
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"postgres: {e}"}, status_code=500)

    # progress/failed reset
    rc = rconn()
    rc.delete(Q_REDIS_KEY_FAILED)
    rc.set(Q_REDIS_KEY_PROGRESS, json.dumps({"running": False, "done": 0, "total": 0, "stage": "initialized"}))

    return {"ok": True}

@router.post("/ingestion/start")
def ingestion_start(mode: str = Query("full")):
    try:
        from worker_tasks import run_ingestion  # se presente nell'immagine api
    except Exception:
        run_ingestion = None

    rc = rconn()
    rc.delete(Q_REDIS_KEY_FAILED)
    rc.set(Q_REDIS_KEY_PROGRESS, json.dumps({"running": True, "done": 0, "total": 0, "stage": "queued"}))

    q = Queue(RQ_QUEUE, connection=rc)
    if run_ingestion:
        job = q.enqueue(run_ingestion, {"mode": mode}, job_timeout=60*60*6)
    else:
        job = q.enqueue("worker_tasks.run_ingestion", {"mode": mode}, job_timeout=60*60*6)

    return {"ok": True, "enqueued": True, "job_id": job.get_id(), "mode": mode}

# ===== Endpoints per la home =====
@router.get("/filters")
def filters():
    return {"sources": [], "types": [], "years": []}

@router.post("/search")
def search(payload: Dict[str, Any]):
    client = meili_client()
    idx = client.index(MEILI_INDEX)
    q = payload.get("query") or ""
    limit = int(payload.get("limit") or 10)
    offset = int(payload.get("offset") or 0)
    try:
        res = idx.search(q, {"limit": limit, "offset": offset})
        hits = res.get("hits", [])
        return {"total": res.get("estimatedTotalHits", len(hits)), "items": hits}
    except meilisearch.errors.MeilisearchApiError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
