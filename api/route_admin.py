# api/route_admin.py
import os
import json
from functools import lru_cache
from typing import List, Dict, Any, Optional

import redis
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from redis import Redis
from rq import Queue

import psycopg
from psycopg.rows import dict_row
import meilisearch
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

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
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")

Q_REDIS_KEY_PROGRESS = "kb:progress"        # string JSON
Q_REDIS_KEY_FAILED   = "kb:failed_docs"     # list JSON lines
MEILI_INDEX          = "kb_docs"
QDRANT_COLLECTION    = os.getenv("QDRANT_COLLECTION", "kb_chunks")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

router = APIRouter()

# ===== Helpers =====
def rconn() -> Redis:
    return redis.from_url(REDIS_URL, decode_responses=True)

def meili_client() -> meilisearch.Client:
    return meilisearch.Client(MEILI_URL, MEILI_MASTER_KEY)

def pg_conn():
    dsn = f"host={POSTGRES_HOST} dbname={POSTGRES_DB} user={POSTGRES_USER} password={POSTGRES_PASSWORD}"
    return psycopg.connect(dsn, autocommit=True, row_factory=dict_row)

def qdrant_client() -> QdrantClient:
    return QdrantClient(QDRANT_URL, timeout=60)

@lru_cache(maxsize=1)
def embedding_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL_NAME)

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
    """
    Estrae valori unici per TUTTI i filtri disponibili.
    
    Returns:
        Dict con: areas, anni, clienti, oggetti, tipi_doc, categorie, extensions
    """
    try:
        with pg_conn() as conn, conn.cursor() as cur:
            # Aree
            cur.execute("SELECT DISTINCT area FROM documents WHERE area IS NOT NULL ORDER BY area")
            areas = [r['area'] for r in cur.fetchall()]
            
            # Anni
            cur.execute("SELECT DISTINCT anno FROM documents WHERE anno IS NOT NULL ORDER BY anno DESC")
            anni = [r['anno'] for r in cur.fetchall()]
            
            # Clienti (top 50 più frequenti)
            cur.execute("""
                SELECT cliente, COUNT(*) as cnt 
                FROM documents 
                WHERE cliente IS NOT NULL 
                GROUP BY cliente 
                ORDER BY cnt DESC, cliente 
                LIMIT 50
            """)
            clienti = [r['cliente'] for r in cur.fetchall()]
            
            # Oggetti/Temi
            cur.execute("SELECT DISTINCT oggetto FROM documents WHERE oggetto IS NOT NULL ORDER BY oggetto")
            oggetti = [r['oggetto'] for r in cur.fetchall()]
            
            # Tipi Documento
            cur.execute("SELECT DISTINCT tipo_doc FROM documents WHERE tipo_doc IS NOT NULL ORDER BY tipo_doc")
            tipi_doc = [r['tipo_doc'] for r in cur.fetchall()]
            
            # Categorie
            cur.execute("SELECT DISTINCT categoria FROM documents WHERE categoria IS NOT NULL ORDER BY categoria")
            categorie = [r['categoria'] for r in cur.fetchall()]
            
            # Estensioni
            cur.execute("SELECT DISTINCT ext FROM documents WHERE ext IS NOT NULL ORDER BY ext")
            extensions = [r['ext'] for r in cur.fetchall()]
            
            return {
                "areas": areas,
                "anni": anni,
                "clienti": clienti,
                "oggetti": oggetti,
                "tipi_doc": tipi_doc,
                "categorie": categorie,
                "extensions": extensions
            }
    except Exception as e:
        import logging
        logging.error(f"Errore in /filters: {e}")
        return {
            "area": [],
            "anno": [],
            "tipo": [],
            "extra": {
                "clienti": [],
                "oggetti": [],
                "categorie": [],
                "extensions": []
            },
            "error": str(e)
        }

def _filters_response(rows: Dict[str, List[Any]]) -> Dict[str, Any]:
    return {
        "area": rows.get("areas", []),
        "anno": rows.get("anni", []),
        "tipo": rows.get("tipi_doc", []),
        "extra": {
            "clienti": rows.get("clienti", []),
            "oggetti": rows.get("oggetti", []),
            "categorie": rows.get("categorie", []),
            "extensions": rows.get("extensions", []),
        }
    }


def _build_meili_filter(filters: Dict[str, Any]) -> Optional[List[str]]:
    clauses: List[str] = []
    if filters.get("area"):
        clauses.append(f"area = '{filters['area'].replace("'", "\\'")}'")
    if filters.get("tipo"):
        clauses.append(f"tipo_doc = '{filters['tipo'].replace("'", "\\'")}'")
    if filters.get("anno"):
        clauses.append(f"anno = {int(filters['anno'])}")
    return clauses or None


def _build_qdrant_filter(filters: Dict[str, Any]) -> Optional[qm.Filter]:
    must: List[qm.FieldCondition] = []
    if filters.get("area"):
        must.append(qm.FieldCondition(key="area", match=qm.MatchValue(value=filters["area"])))
    if filters.get("tipo"):
        must.append(qm.FieldCondition(key="tipo_doc", match=qm.MatchValue(value=filters["tipo"])))
    if filters.get("anno"):
        must.append(qm.FieldCondition(key="anno", match=qm.MatchValue(value=int(filters["anno"]))))
    return qm.Filter(must=must) if must else None


def _sanitize_preview(text: str) -> str:
    return (text or "").replace("\n", " ")


@router.get("/filters")
def filters():
    try:
        with pg_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT DISTINCT area FROM documents WHERE area IS NOT NULL ORDER BY area")
            areas = [r["area"] for r in cur.fetchall()]

            cur.execute("SELECT DISTINCT anno FROM documents WHERE anno IS NOT NULL ORDER BY anno DESC")
            anni = [r["anno"] for r in cur.fetchall()]

            cur.execute("SELECT DISTINCT tipo_doc FROM documents WHERE tipo_doc IS NOT NULL ORDER BY tipo_doc")
            tipi_doc = [r["tipo_doc"] for r in cur.fetchall()]

            # Extra facets for potential advanced UIs
            cur.execute("""
                SELECT cliente
                FROM documents
                WHERE cliente IS NOT NULL
                GROUP BY cliente
                ORDER BY COUNT(*) DESC, cliente
                LIMIT 50
            """)
            clienti = [r["cliente"] for r in cur.fetchall()]

            cur.execute("SELECT DISTINCT oggetto FROM documents WHERE oggetto IS NOT NULL ORDER BY oggetto")
            oggetti = [r["oggetto"] for r in cur.fetchall()]

            cur.execute("SELECT DISTINCT categoria FROM documents WHERE categoria IS NOT NULL ORDER BY categoria")
            categorie = [r["categoria"] for r in cur.fetchall()]

            cur.execute("SELECT DISTINCT ext FROM documents WHERE ext IS NOT NULL ORDER BY ext")
            extensions = [r["ext"] for r in cur.fetchall()]

            return _filters_response({
                "areas": areas,
                "anni": anni,
                "tipi_doc": tipi_doc,
                "clienti": clienti,
                "oggetti": oggetti,
                "categorie": categorie,
                "extensions": extensions,
            })
    except Exception as e:
        import logging
        logging.error(f"Errore in /filters: {e}")
        return {
            "area": [],
            "anno": [],
            "tipo": [],
            "extra": {
                "clienti": [],
                "oggetti": [],
                "categorie": [],
                "extensions": []
            },
            "error": str(e)
        }


@router.post("/search")
def search(payload: Dict[str, Any]):
    mode = (payload or {}).get("mode", "kw")
    q = (payload or {}).get("q", "").strip()
    page = max(1, int((payload or {}).get("page") or 1))
    per_page = max(1, min(100, int((payload or {}).get("per_page") or 10)))
    offset = (page - 1) * per_page
    filters = (payload or {}).get("filters") or {}
    reduce_server = bool((payload or {}).get("reduce_server", True))

    if mode == "sem":
        if not q:
            return {"hits": [], "total": 0, "page": page, "per_page": per_page, "mode": mode}
        model = embedding_model()
        query_vec = model.encode(q).tolist()
        cli = qdrant_client()
        q_filter = _build_qdrant_filter(filters) if reduce_server else None
        try:
            results = cli.search(
                collection_name=QDRANT_COLLECTION,
                query_vector=query_vec,
                limit=per_page,
                offset=offset,
                with_payload=True,
                filter=q_filter,
            )
            hits = [
                {
                    "id": point.payload.get("doc_id"),
                    "chunk_id": point.payload.get("chunk_id"),
                    "title": point.payload.get("title"),
                    "path": point.payload.get("path"),
                    "preview": _sanitize_preview(point.payload.get("text", "")),
                    "score": round(point.score, 4) if point.score is not None else None,
                    "area": point.payload.get("area"),
                    "anno": point.payload.get("anno"),
                    "tipo": point.payload.get("tipo_doc"),
                }
                for point in results
            ]
            total = cli.count(collection_name=QDRANT_COLLECTION, count_filter=q_filter, exact=False).count
            return {"hits": hits, "total": total, "page": page, "per_page": per_page, "mode": mode}
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"qdrant: {e}"}, status_code=500)

    client = meili_client()
    idx = client.index(MEILI_INDEX)
    params: Dict[str, Any] = {"limit": per_page, "offset": offset}
    if reduce_server:
        flt = _build_meili_filter(filters)
        if flt:
            params["filter"] = flt
    try:
        res = idx.search(q or "", params)
        hits = []
        for doc in res.get("hits", []):
            preview_source = doc.get("preview") or doc.get("content", "")
            hits.append({
                "id": doc.get("id"),
                "title": doc.get("title"),
                "path": doc.get("path"),
                "preview": _sanitize_preview(preview_source)[:500],
                "score": doc.get("_rankingScore"),
                "area": doc.get("area"),
                "anno": doc.get("anno"),
                "tipo": doc.get("tipo_doc"),
            })
        return {
            "hits": hits,
            "total": res.get("estimatedTotalHits", len(hits)),
            "page": page,
            "per_page": per_page,
            "mode": mode,
        }
    except meilisearch.errors.MeilisearchApiError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
