#!/usr/bin/env python3
"""
Monitor leggero per KB Search.
Espone snapshot real-time di: salute servizi, stato coda RQ, progress ingestion,
ultimi documenti falliti/processati, job correnti, ecc.

Dipendenze (pip): fastapi uvicorn redis rq psycopg[binary] requests meilisearch qdrant-client
"""

import os
import time
import json
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from redis import Redis
from rq import Queue
from rq.registry import StartedJobRegistry, FailedJobRegistry, FinishedJobRegistry

import psycopg
from psycopg.rows import dict_row

import meilisearch
from qdrant_client import QdrantClient

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
POSTGRES_DSN        = os.getenv("POSTGRES_DSN", "postgresql://kbuser:kbpass@postgres:5432/kb")
REDIS_URL           = os.getenv("REDIS_URL", "redis://redis:6379/0")

MEILI_URL           = os.getenv("MEILI_URL", "http://meili:7700")
MEILI_MASTER_KEY    = os.getenv("MEILI_MASTER_KEY") or os.getenv("MEILI_API_KEY") or ""
MEILI_INDEX         = os.getenv("MEILI_INDEX", "kb_docs")

QDRANT_URL          = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_HOST         = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT         = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION   = os.getenv("QDRANT_COLLECTION", "kb_chunks")

RQ_QUEUE_NAME       = os.getenv("RQ_QUEUE", "kb_ingestion")

# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
app = FastAPI(title="KB Monitor API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

def _pg():
    return psycopg.connect(POSTGRES_DSN)

def _redis() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)

def _rq() -> Queue:
    return Queue(RQ_QUEUE_NAME, connection=_redis())

def _meili():
    return meilisearch.Client(MEILI_URL, MEILI_MASTER_KEY or None)

def _qdrant():
    # QdrantClient usa HTTP di default; host/port sono preferibili a base_url
    return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=10)

# -----------------------------------------------------------------------------
# Utils
# -----------------------------------------------------------------------------
def _ok(val: Any, ms: Optional[int]=None, err: Optional[str]=None):
    return {"ok": err is None, "ms": ms, "value": val, "error": err}

def _timed(fn):
    t0 = time.time()
    try:
        v = fn()
        return _ok(v, int((time.time()-t0)*1000), None)
    except Exception as e:
        return _ok(None, int((time.time()-t0)*1000), str(e))

# -----------------------------------------------------------------------------
# /health
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    """Ping rapido di tutti i servizi. I check non bloccano il resto."""
    out: Dict[str, Any] = {}

    out["redis"] = _timed(lambda: _redis().ping())
    out["postgres"] = _timed(lambda: _pg().execute("SELECT 1").fetchone()[0])

    # Meili: usa endpoint /health, fallback al client
    def _h_meili():
        try:
            r = requests.get(f"{MEILI_URL}/health", headers={"Authorization": f"Bearer {MEILI_MASTER_KEY}"} if MEILI_MASTER_KEY else {}, timeout=5)
            r.raise_for_status()
            j = r.json()
            return j.get("status", "ok")
        except Exception:
            # fallback: version via client
            return _meili().version()
    out["meili"] = _timed(_h_meili)

    # Qdrant: usa client (get_collections) – robusto; il vecchio GET / può non essere JSON
    def _h_qdrant():
        cli = _qdrant()
        cols = cli.get_collections()
        return "available" if cols is not None else "unknown"
    out["qdrant"] = _timed(_h_qdrant)

    return {"health": out}

# -----------------------------------------------------------------------------
# /queue  (job correnti / registri RQ)
# -----------------------------------------------------------------------------
@app.get("/queue")
def queue_state():
    q = _rq()
    started = StartedJobRegistry(queue=q)
    failed = FailedJobRegistry(queue=q)
    finished = FinishedJobRegistry(queue=q)

    active_ids = started.get_job_ids()
    res_active = []
    for jid in active_ids:
        try:
            j = q.job_class.fetch(jid, connection=q.connection)
            res_active.append({
                "id": j.id,
                "func": j.func_name,
                "args": j.args,
                "kwargs": j.kwargs,
                "meta": j.meta,
                "enqueued_at": j.enqueued_at.isoformat() if j.enqueued_at else None,
                "started_at": j.started_at.isoformat() if j.started_at else None,
            })
        except Exception as e:
            res_active.append({"id": jid, "err": str(e)})

    failed_ids = failed.get_job_ids()[-50:]
    res_failed = []
    for jid in failed_ids:
        try:
            j = q.job_class.fetch(jid, connection=q.connection)
            res_failed.append({
                "id": j.id,
                "func": j.func_name,
                "exc_preview": (j.exc_info or "").splitlines()[-1] if j.exc_info else None,
                "enqueued_at": j.enqueued_at.isoformat() if j.enqueued_at else None,
                "ended_at": j.ended_at.isoformat() if j.ended_at else None,
            })
        except Exception as e:
            res_failed.append({"id": jid, "err": str(e)})

    return {
        "counts": {
            "queued": q.count,
            "active": len(active_ids),
            "failed": len(failed.get_job_ids()),
            "finished": len(finished.get_job_ids()),
        },
        "active": res_active,
        "failed_recent": res_failed,
    }

# -----------------------------------------------------------------------------
# /progress  (contatori documenti nel DB)
# -----------------------------------------------------------------------------
@app.get("/progress")
def progress():
    with _pg() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
          SELECT
            COUNT(*) FILTER (WHERE status IS NOT NULL)                    AS total,
            COUNT(*) FILTER (WHERE status='done')                         AS done,
            COUNT(*) FILTER (WHERE status='failed')                       AS failed,
            COUNT(*) FILTER (WHERE status='processing')                   AS processing
          FROM documents
        """)
        row = cur.fetchone() or {}
        total       = int(row.get("total") or 0)
        done        = int(row.get("done") or 0)
        failed      = int(row.get("failed") or 0)
        processing  = int(row.get("processing") or 0)
        remaining   = max(total - done - failed - processing, 0)
        percent     = round(done * 100.0 / total, 2) if total else 0.0

        # ultimo documento "in lavorazione"
        cur.execute("""
          SELECT id, path, status, started_at, finished_at, last_error
          FROM documents
          WHERE status='processing'
          ORDER BY started_at DESC NULLS LAST
          LIMIT 1
        """)
        current = cur.fetchone()

        # ultimi falliti
        cur.execute("""
          SELECT id, path, last_error, finished_at
          FROM documents
          WHERE status='failed'
          ORDER BY finished_at DESC NULLS LAST
          LIMIT 50
        """)
        last_failed = cur.fetchall()

    return {
        "total": total, "done": done, "failed": failed,
        "processing": processing, "remaining": remaining,
        "percent": percent, "current": current, "failed_list": last_failed,
    }

# -----------------------------------------------------------------------------
# /meili/stats  /qdrant/stats
# -----------------------------------------------------------------------------
@app.get("/meili/stats")
def meili_stats():
    try:
        idx = _meili().index(MEILI_INDEX)
        st = idx.get_stats()
        return {"ok": True, "index": MEILI_INDEX, "stats": st}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/qdrant/stats")
def qdrant_stats():
    try:
        cli = _qdrant()
        info = cli.get_collection(QDRANT_COLLECTION)
        # points_count è in info.vectors_count / points_count a seconda delle versioni
        pts = getattr(info, "points_count", None)
        if pts is None and hasattr(info, "vectors_count"):
            pts = info.vectors_count
        return {"ok": True, "collection": QDRANT_COLLECTION, "points": int(pts or 0)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# -----------------------------------------------------------------------------
# /documents/{kind}
# -----------------------------------------------------------------------------
@app.get("/documents/failed")
def docs_failed(limit: int = 200):
    with _pg() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
          SELECT id, path, last_error, finished_at
          FROM documents
          WHERE status='failed'
          ORDER BY finished_at DESC NULLS LAST
          LIMIT %s
        """, (limit,))
        return {"rows": cur.fetchall()}

@app.get("/documents/done")
def docs_done(limit: int = 200):
    with _pg() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
          SELECT id, path, finished_at
          FROM documents
          WHERE status='done'
          ORDER BY finished_at DESC NULLS LAST
          LIMIT %s
        """, (limit,))
        return {"rows": cur.fetchall()}