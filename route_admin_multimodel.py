# api/route_admin.py - Con monitoraggio dettagliato ingestion
import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

import redis
from fastapi import APIRouter, Query, Body
from fastapi.responses import JSONResponse
from redis import Redis
from rq import Queue
from rq.job import Job

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
MEILI_MASTER_KEY = os.getenv("MEILI_MASTER_KEY", os.getenv("MEILI_KEY", "change_me_meili_key"))

# Redis keys per tracking dettagliato
Q_REDIS_KEY_PROGRESS = "kb:progress"
Q_REDIS_KEY_FAILED = "kb:failed_docs"
Q_REDIS_KEY_CURRENT_DOC = "kb:current_doc"
Q_REDIS_KEY_PROCESSING_LOG = "kb:processing_log"  # Lista ultimi 100 documenti
Q_REDIS_KEY_STATS = "kb:stats"

MEILI_INDEX = "kb_docs"

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
            area TEXT,
            anno INTEGER,
            cliente TEXT,
            oggetto TEXT,
            tipo_doc TEXT,
            categoria TEXT,
            ext TEXT,
            mtime TIMESTAMP DEFAULT NOW()
        );
        """)
        # Aggiungi colonne se non esistono (per migrazione)
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS area TEXT;")
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS anno INTEGER;")
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS cliente TEXT;")
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS oggetto TEXT;")
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS tipo_doc TEXT;")
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS categoria TEXT;")
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS ext TEXT;")
        
        # Indici
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_title ON documents (title);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_path ON documents (path);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_area ON documents (area);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_anno ON documents (anno);")

# ===== Admin endpoints =====
@router.get("/queue")
def get_queue():
    q = Queue(RQ_QUEUE, connection=rconn())
    
    # Get workers info
    workers = []
    for worker in q.connection.smembers('rq:workers'):
        workers.append(worker.decode() if isinstance(worker, bytes) else str(worker))
    
    return {
        "queue": q.name,
        "count": len(q.jobs),
        "scheduled": len(q.scheduled_job_registry),
        "started_jobs": len(q.started_job_registry),
        "deferred": len(q.deferred_job_registry),
        "failed": len(q.failed_job_registry),
        "workers": workers
    }

@router.get("/progress")
def get_progress():
    """Progress globale + documento corrente"""
    rc = rconn()
    
    # Progress generale
    raw = rc.get(Q_REDIS_KEY_PROGRESS)
    if not raw:
        progress = {"running": False, "done": 0, "total": 0, "stage": "idle"}
    else:
        try:
            progress = json.loads(raw)
        except Exception:
            progress = {"running": False, "done": 0, "total": 0, "stage": "idle"}
    
    # Documento corrente
    current_doc_raw = rc.get(Q_REDIS_KEY_CURRENT_DOC)
    if current_doc_raw:
        try:
            progress["current_doc"] = json.loads(current_doc_raw)
        except Exception:
            progress["current_doc"] = None
    else:
        progress["current_doc"] = None
    
    # Stats aggregate
    stats_raw = rc.get(Q_REDIS_KEY_STATS)
    if stats_raw:
        try:
            progress["stats"] = json.loads(stats_raw)
        except Exception:
            progress["stats"] = {}
    else:
        progress["stats"] = {}
    
    return progress

@router.get("/processing_log")
def get_processing_log(limit: int = Query(50, ge=1, le=200)):
    """Log dettagliato ultimi N documenti processati"""
    rc = rconn()
    items = rc.lrange(Q_REDIS_KEY_PROCESSING_LOG, 0, limit - 1) or []
    
    log_entries = []
    for item in items:
        try:
            log_entries.append(json.loads(item))
        except Exception:
            log_entries.append({"error": item})
    
    return {
        "total": len(log_entries),
        "entries": log_entries
    }

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

@router.delete("/failed_docs")
def clear_failed_docs():
    """Pulisci lista documenti falliti"""
    rc = rconn()
    rc.delete(Q_REDIS_KEY_FAILED)
    return {"ok": True, "message": "Failed docs cleared"}

@router.post("/init_indexes")
def init_indexes():
    # Meili
    client = meili_client()
    try:
        try:
            client.get_index(MEILI_INDEX)
        except meilisearch.errors.MeilisearchApiError:
            client.create_index(MEILI_INDEX, {"primaryKey": "id"})
        
        # Configurazione filtri
        client.index(MEILI_INDEX).update_filterable_attributes([
            "area", "anno", "cliente", "oggetto", "tipo_doc", "categoria", "ext"
        ])
        client.index(MEILI_INDEX).update_sortable_attributes(["anno", "mtime"])
        client.index(MEILI_INDEX).update_searchable_attributes([
            "title", "content", "path"
        ])
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"meili: {e}"}, status_code=500)

    # Postgres
    try:
        ensure_pg_schema()
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"postgres: {e}"}, status_code=500)

    # Reset tracking
    rc = rconn()
    rc.delete(Q_REDIS_KEY_FAILED)
    rc.delete(Q_REDIS_KEY_CURRENT_DOC)
    rc.delete(Q_REDIS_KEY_PROCESSING_LOG)
    rc.set(Q_REDIS_KEY_PROGRESS, json.dumps({
        "running": False, "done": 0, "total": 0, "stage": "initialized"
    }))
    rc.set(Q_REDIS_KEY_STATS, json.dumps({
        "success": 0,
        "failed": 0,
        "chunked": 0,
        "meili_indexed": 0,
        "qdrant_vectorized": 0
    }))

    return {"ok": True, "message": "Indexes initialized"}

@router.post("/ingestion/start")
def ingestion_start(
    mode: str = Query("full", description="full | incremental"),
    model: str = Query("sentence-transformer", description="sentence-transformer | llama3 | mistral")
):
    """Avvia ingestion con modello selezionato"""
    try:
        from worker_tasks import run_ingestion
    except Exception:
        run_ingestion = None

    # Valida modello
    VALID_MODELS = ["sentence-transformer", "llama3", "mistral"]
    if model not in VALID_MODELS:
        return JSONResponse(
            {"ok": False, "error": f"Modello non valido. Usa uno tra: {', '.join(VALID_MODELS)}"},
            status_code=400
        )

    rc = rconn()
    rc.delete(Q_REDIS_KEY_FAILED)
    rc.delete(Q_REDIS_KEY_CURRENT_DOC)
    rc.set(Q_REDIS_KEY_PROGRESS, json.dumps({
        "running": True, "done": 0, "total": 0, "stage": f"queued-{model}"
    }))

    q = Queue(RQ_QUEUE, connection=rc)
    if run_ingestion:
        job = q.enqueue(run_ingestion, {"mode": mode, "model": model}, job_timeout=60*60*6)
    else:
        job = q.enqueue("worker_tasks.run_ingestion", {"mode": mode, "model": model}, job_timeout=60*60*6)

    # Determina collection name
    collection_map = {
        "sentence-transformer": "kb_st_docs",
        "llama3": "kb_llama3_docs",
        "mistral": "kb_mistral_docs"
    }

    return {
        "ok": True,
        "enqueued": True,
        "job_id": job.get_id(),
        "mode": mode,
        "model": model,
        "collection": collection_map.get(model, "kb_st_docs")
    }

@router.post("/ingestion/pause")
def ingestion_pause():
    """Pause ingestion (set flag)"""
    rc = rconn()
    rc.set("kb:ingestion_pause", "1")
    return {"ok": True, "message": "Pause flag set"}

@router.post("/ingestion/resume")
def ingestion_resume():
    """Resume ingestion (clear flag)"""
    rc = rconn()
    rc.delete("kb:ingestion_pause")
    return {"ok": True, "message": "Pause flag cleared"}

@router.get("/ingestion/status")
def ingestion_status():
    """Status dettagliato ingestion"""
    rc = rconn()
    q = Queue(RQ_QUEUE, connection=rc)
    
    # Job attivo
    started_jobs = q.started_job_registry.get_job_ids()
    current_job = None
    if started_jobs:
        try:
            job = Job.fetch(started_jobs[0], connection=rc)
            current_job = {
                "id": job.id,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "status": job.get_status()
            }
        except Exception:
            pass
    
    # Progress
    progress = get_progress()
    
    # Pause flag
    paused = rc.exists("kb:ingestion_pause")
    
    return {
        "job": current_job,
        "progress": progress,
        "paused": bool(paused),
        "queue_length": len(q.jobs),
        "failed_count": len(q.failed_job_registry)
    }

# ===== Filters endpoint =====
@router.get("/filters")
def filters():
    """Estrae valori unici per tutti i filtri disponibili"""
    try:
        with pg_conn() as conn, conn.cursor() as cur:
            # Aree
            cur.execute("SELECT DISTINCT area FROM documents WHERE area IS NOT NULL AND area != '' ORDER BY area")
            areas = [r['area'] for r in cur.fetchall()]
            
            # Anni
            cur.execute("SELECT DISTINCT anno FROM documents WHERE anno IS NOT NULL ORDER BY anno DESC")
            anni = [r['anno'] for r in cur.fetchall()]
            
            # Clienti
            cur.execute("""
                SELECT cliente, COUNT(*) as cnt 
                FROM documents 
                WHERE cliente IS NOT NULL AND cliente != ''
                GROUP BY cliente 
                ORDER BY cnt DESC, cliente 
                LIMIT 50
            """)
            clienti = [r['cliente'] for r in cur.fetchall()]
            
            # Oggetti
            cur.execute("SELECT DISTINCT oggetto FROM documents WHERE oggetto IS NOT NULL AND oggetto != '' ORDER BY oggetto")
            oggetti = [r['oggetto'] for r in cur.fetchall()]
            
            # Tipi Documento
            cur.execute("SELECT DISTINCT tipo_doc FROM documents WHERE tipo_doc IS NOT NULL AND tipo_doc != '' ORDER BY tipo_doc")
            tipi_doc = [r['tipo_doc'] for r in cur.fetchall()]
            
            # Categorie
            cur.execute("SELECT DISTINCT categoria FROM documents WHERE categoria IS NOT NULL AND categoria != '' ORDER BY categoria")
            categorie = [r['categoria'] for r in cur.fetchall()]
            
            # Estensioni
            cur.execute("SELECT DISTINCT ext FROM documents WHERE ext IS NOT NULL AND ext != '' ORDER BY ext")
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
            "areas": [], "anni": [], "clienti": [], "oggetti": [],
            "tipi_doc": [], "categorie": [], "extensions": [],
            "error": str(e)
        }

# ===== Search endpoint =====
@router.get("/search")
def search_get(
    q_text: str = Query("", description="Testo di ricerca"),
    top_k: int = Query(10, ge=1, le=100),
    area: Optional[str] = Query(None),
    anno: Optional[int] = Query(None),
    cliente: Optional[str] = Query(None),
    oggetto: Optional[str] = Query(None),
    tipo_doc: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None),
    ext: Optional[str] = Query(None)
):
    return _do_search(q_text, top_k, area, anno, cliente, oggetto, tipo_doc, categoria, ext)

@router.post("/search")
def search_post(payload: Dict[str, Any] = Body(...)):
    q_text = payload.get("query", payload.get("q_text", ""))
    top_k = int(payload.get("limit", payload.get("top_k", 10)))
    area = payload.get("area")
    anno = payload.get("anno")
    cliente = payload.get("cliente")
    oggetto = payload.get("oggetto")
    tipo_doc = payload.get("tipo_doc")
    categoria = payload.get("categoria")
    ext = payload.get("ext")
    
    return _do_search(q_text, top_k, area, anno, cliente, oggetto, tipo_doc, categoria, ext)

def _do_search(
    q_text: str,
    top_k: int,
    area: Optional[str] = None,
    anno: Optional[int] = None,
    cliente: Optional[str] = None,
    oggetto: Optional[str] = None,
    tipo_doc: Optional[str] = None,
    categoria: Optional[str] = None,
    ext: Optional[str] = None
):
    try:
        client = meili_client()
        idx = client.index(MEILI_INDEX)
        
        # Costruisci filtri
        filters = []
        if area:
            filters.append(f'area = "{area}"')
        if anno:
            filters.append(f'anno = {anno}')
        if cliente:
            filters.append(f'cliente = "{cliente}"')
        if oggetto:
            filters.append(f'oggetto = "{oggetto}"')
        if tipo_doc:
            filters.append(f'tipo_doc = "{tipo_doc}"')
        if categoria:
            filters.append(f'categoria = "{categoria}"')
        if ext:
            filters.append(f'ext = "{ext}"')
        
        filter_string = " AND ".join(filters) if filters else None
        
        search_params = {
            "limit": top_k,
            "attributesToRetrieve": [
                "id", "doc_id", "title", "path", "content", 
                "area", "anno", "cliente", "oggetto", "tipo_doc", 
                "categoria", "ext", "url"
            ],
            "attributesToHighlight": ["title", "content"],
            "highlightPreTag": "<mark>",
            "highlightPostTag": "</mark>",
        }
        
        if filter_string:
            search_params["filter"] = filter_string
        
        result = idx.search(q_text, search_params)
        
        hits = []
        for hit in result.get("hits", []):
            formatted = hit.get("_formatted", {})
            content_snippet = formatted.get("content", hit.get("content", ""))
            if content_snippet:
                content_snippet = content_snippet[:300] + ("..." if len(content_snippet) > 300 else "")
            
            hits.append({
                "doc_id": hit.get("id", hit.get("doc_id")),
                "title": hit.get("title", "Senza titolo"),
                "content_snippet": content_snippet,
                "score": None,
                "area": hit.get("area"),
                "anno": hit.get("anno"),
                "cliente": hit.get("cliente"),
                "oggetto": hit.get("oggetto"),
                "tipo": hit.get("tipo_doc"),
                "categoria": hit.get("categoria"),
                "ext": hit.get("ext"),
                "url": hit.get("url"),
                "path": hit.get("path")
            })
        
        return {
            "total": result.get("estimatedTotalHits", len(hits)),
            "hits": hits,
            "processing_time_ms": result.get("processingTimeMs", 0)
        }
        
    except meilisearch.errors.MeilisearchApiError as e:
        import logging
        logging.error(f"Errore Meilisearch: {e}")
        return JSONResponse(
            {"ok": False, "error": str(e), "hits": []}, 
            status_code=500
        )
    except Exception as e:
        import logging
        logging.error(f"Errore ricerca: {e}")
        return JSONResponse(
            {"ok": False, "error": str(e), "hits": []}, 
            status_code=500
        )
