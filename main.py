# api/main.py - KB Search API con Multi-Model Support v3.0
import os
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import redis
from redis import Redis

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, VectorParams, Distance

import meilisearch

import psycopg
from psycopg.rows import dict_row

from rq import Queue
from rq.job import Job

# ===== ENV =====
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
MEILI_URL = os.getenv("MEILI_URL", "http://meili:7700")
MEILI_MASTER_KEY = os.getenv("MEILI_MASTER_KEY", "change_me_meili_key")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "kb")
POSTGRES_USER = os.getenv("POSTGRES_USER", "kbuser")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "kbpass")

DOCS_BASE_PATH = os.getenv("DOCS_PATH", "/mnt/kb")

MEILI_INDEX = "kb_docs"
DEFAULT_MODEL = "sentence-transformer"

# Model configs
MODEL_CONFIGS = {
    "sentence-transformer": {
        "name": "all-MiniLM-L6-v2",
        "dimension": 384,
        "collection_prefix": "kb_st",
        "type": "transformers"
    },
    "llama3": {
        "name": "llama3",
        "dimension": 4096,
        "collection_prefix": "kb_llama3",
        "type": "ollama"
    },
    "mistral": {
        "name": "mistral",
        "dimension": 4096,
        "collection_prefix": "kb_mistral",
        "type": "ollama"
    }
}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

app = FastAPI(title="KB Search API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== Templates e Static Files =====
templates = Jinja2Templates(directory="frontend/templates")
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# ===== Clients =====
def rconn() -> Redis:
    return redis.from_url(REDIS_URL, decode_responses=True)

def qdrant_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)

def meili_client() -> meilisearch.Client:
    return meilisearch.Client(MEILI_URL, MEILI_MASTER_KEY)

def pg_conn():
    dsn = f"host={POSTGRES_HOST} dbname={POSTGRES_DB} user={POSTGRES_USER} password={POSTGRES_PASSWORD}"
    return psycopg.connect(dsn, autocommit=True, row_factory=dict_row)

def get_embedder(model_type: str):
    """Ottieni embedder per il modello specificato"""
    config = MODEL_CONFIGS.get(model_type, MODEL_CONFIGS[DEFAULT_MODEL])
    
    if config["type"] == "transformers":
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(config["name"])
        return lambda text: model.encode([text], convert_to_numpy=True).tolist()[0]
    
    elif config["type"] == "ollama":
        import requests
        
        def embed_ollama(text: str) -> List[float]:
            try:
                resp = requests.post(
                    "http://ollama:11434/api/embeddings",
                    json={"model": config["name"], "prompt": text},
                    timeout=30
                )
                if resp.status_code == 200:
                    return resp.json()["embedding"]
                else:
                    log.error(f"Ollama errore: {resp.status_code}")
                    return [0.0] * config["dimension"]
            except Exception as e:
                log.error(f"Ollama errore: {e}")
                return [0.0] * config["dimension"]
        
        return embed_ollama
    
    raise ValueError(f"Tipo modello non supportato: {config['type']}")

# ===== HTML Pages =====
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page - Ricerca"""
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request):
    """Admin page - Monitoring ingestion"""
    return templates.TemplateResponse("admin.html", {"request": request})

# ===== Health =====
@app.get("/health")
async def health():
    """Health check"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/api/health")
async def api_health():
    """Health check API"""
    checks = {}
    
    # Redis
    try:
        rc = rconn()
        rc.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"
    
    # Qdrant
    try:
        qd = qdrant_client()
        collections = qd.get_collections()
        checks["qdrant"] = f"ok ({len(collections.collections)} collections)"
    except Exception as e:
        checks["qdrant"] = f"error: {e}"
    
    # Meilisearch
    try:
        meili = meili_client()
        meili.health()
        checks["meilisearch"] = "ok"
    except Exception as e:
        checks["meilisearch"] = f"error: {e}"
    
    # PostgreSQL
    try:
        with pg_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM documents")
            cnt = cur.fetchone()["cnt"]
            checks["postgres"] = f"ok ({cnt} docs)"
    except Exception as e:
        checks["postgres"] = f"error: {e}"
    
    all_ok = all(v.startswith("ok") for v in checks.values())
    
    return {
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
        "timestamp": datetime.now().isoformat()
    }

# ===== Search =====
@app.get("/search")
@app.get("/api/search")
async def search(
    q_text: str = Query(..., description="Query di ricerca"),
    model: str = Query(DEFAULT_MODEL, description="Modello embedding da usare"),
    top_k: int = Query(20, ge=1, le=100, description="Numero risultati"),
    filters: Optional[str] = Query(None, description="Filtri (es: area:AQ,anno:2023)")
):
    """
    Ricerca semantica vettoriale su Qdrant con aggregazione per documento
    """
    if not q_text or not q_text.strip():
        return {"total": 0, "hits": [], "processing_time_ms": 0}
    
    start_time = datetime.now()
    
    try:
        # Config modello
        if model not in MODEL_CONFIGS:
            model = DEFAULT_MODEL
        
        config = MODEL_CONFIGS[model]
        collection_name = f"{config['collection_prefix']}_chunks"
        
        # Genera embedding query
        embedder = get_embedder(model)
        query_vector = embedder(q_text.strip())
        
        # Prepara filtri Qdrant
        qdrant_filter = None
        if filters:
            conditions = []
            for f in filters.split(','):
                if ':' in f:
                    key, value = f.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    if key and value:
                        conditions.append(
                            FieldCondition(key=key, match=MatchValue(value=value))
                        )
            
            if conditions:
                qdrant_filter = Filter(must=conditions)
        
        # Ricerca vettoriale - CERCA PIÙ CHUNK per avere buon campione
        # Con ~35 chunks/doc, top_k * 3 dovrebbe dare abbastanza documenti unici
        search_limit = min(top_k * 3, 200)
        
        qd = qdrant_client()
        results = qd.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=search_limit,
            query_filter=qdrant_filter,
            with_payload=True
        )
        
        # Aggrega per documento e calcola score massimo
        docs_map = {}
        for hit in results:
            doc_id = hit.payload.get("doc_id")
            if not doc_id:
                continue
            
            if doc_id not in docs_map:
                docs_map[doc_id] = {
                    "doc_id": doc_id,
                    "path": hit.payload.get("path", ""),
                    "title": hit.payload.get("title", ""),
                    "score": hit.score,
                    "metadata": {k: v for k, v in hit.payload.items() if k not in ["doc_id", "path", "title", "text", "chunk_index"]},
                    "chunks": []
                }
            
            # Mantieni score massimo e aggiungi chunk
            docs_map[doc_id]["score"] = max(docs_map[doc_id]["score"], hit.score)
            docs_map[doc_id]["chunks"].append({
                "chunk_index": hit.payload.get("chunk_index", 0),
                "text": hit.payload.get("text", ""),
                "score": hit.score
            })
        
        # Ordina documenti per score e limita a top_k
        docs_list = sorted(docs_map.values(), key=lambda d: d["score"], reverse=True)[:top_k]
        
        # Per ogni documento, mantieni solo i top 3 chunk migliori
        for doc in docs_list:
            doc["chunks"] = sorted(doc["chunks"], key=lambda c: c["score"], reverse=True)[:3]
        
        elapsed = (datetime.now() - start_time).total_seconds() * 1000
        
        return {
            "total": len(docs_list),
            "hits": docs_list,
            "processing_time_ms": round(elapsed, 2),
            "model": model,
            "collection": collection_name
        }
    
    except Exception as e:
        log.error(f"Errore ricerca: {e}")
        import traceback
        log.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

# ===== Keyword Search (Meilisearch) =====
@app.get("/keyword_search")
@app.get("/api/keyword_search")
async def keyword_search(
    q: str = Query(..., description="Query di ricerca"),
    limit: int = Query(20, ge=1, le=100),
    filters: Optional[str] = Query(None, description="Filtri (es: area=AQ AND anno=2023)")
):
    """
    Ricerca full-text su Meilisearch
    """
    if not q or not q.strip():
        return {"total": 0, "hits": [], "processing_time_ms": 0}
    
    start_time = datetime.now()
    
    try:
        meili = meili_client()
        idx = meili.index(MEILI_INDEX)
        
        search_params = {
            "limit": limit,
            "attributesToRetrieve": ["*"]
        }
        
        if filters:
            search_params["filter"] = filters
        
        results = idx.search(q.strip(), search_params)
        
        elapsed = (datetime.now() - start_time).total_seconds() * 1000
        
        return {
            "total": results.get("estimatedTotalHits", 0),
            "hits": results.get("hits", []),
            "processing_time_ms": round(elapsed, 2)
        }
    
    except Exception as e:
        log.error(f"Errore keyword search: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== Facets =====
@app.get("/facets")
@app.get("/api/facets")
async def get_facets(
    model: str = Query(DEFAULT_MODEL, description="Modello per collection")
):
    """
    Ottieni faccette disponibili da Qdrant
    """
    try:
        if model not in MODEL_CONFIGS:
            model = DEFAULT_MODEL
        
        config = MODEL_CONFIGS[model]
        collection_name = f"{config['collection_prefix']}_chunks"
        
        qd = qdrant_client()
        
        # Verifica collection esiste
        try:
            qd.get_collection(collection_name)
        except:
            return {"facets": {}}
        
        # Lista campi comuni per faccette
        facet_fields = ["area", "anno", "cliente", "categoria", "tipo_doc", "ext"]
        
        facets = {}
        
        # Per ogni campo, ottieni valori unici con conteggio
        # Usa scroll per campionare punti (più veloce di aggregazione completa)
        sample_size = 10000
        scroll_result = qd.scroll(
            collection_name=collection_name,
            limit=sample_size,
            with_payload=True,
            with_vectors=False
        )
        
        points = scroll_result[0]
        
        for field in facet_fields:
            values_count = {}
            
            for point in points:
                if field in point.payload:
                    value = str(point.payload[field])
                    values_count[value] = values_count.get(value, 0) + 1
            
            if values_count:
                # Ordina per conteggio decrescente
                sorted_values = sorted(values_count.items(), key=lambda x: x[1], reverse=True)
                facets[field] = [{"value": v, "count": c} for v, c in sorted_values[:50]]  # Top 50
        
        return {"facets": facets, "collection": collection_name}
    
    except Exception as e:
        log.error(f"Errore facets: {e}")
        return {"facets": {}, "error": str(e)}

# ===== Document Management =====
@app.get("/documents")
async def list_documents(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """Lista documenti da PostgreSQL"""
    try:
        with pg_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT id, path, title, mtime, ctime
                FROM documents
                ORDER BY mtime DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            
            docs = cur.fetchall()
            
            cur.execute("SELECT COUNT(*) as cnt FROM documents")
            total = cur.fetchone()["cnt"]
            
            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "documents": docs
            }
    
    except Exception as e:
        log.error(f"Errore list_documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/document/{doc_id:path}")
async def get_document(doc_id: str):
    """Ottieni dettagli documento"""
    try:
        with pg_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT id, path, title, content, mtime, ctime
                FROM documents
                WHERE id = %s
            """, (doc_id,))
            
            doc = cur.fetchone()
            
            if not doc:
                raise HTTPException(status_code=404, detail="Documento non trovato")
            
            return doc
    
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Errore get_document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== File Download =====
@app.get("/download/{file_path:path}")
async def download_file(file_path: str):
    """Download file da /mnt/kb"""
    try:
        full_path = Path(DOCS_BASE_PATH) / file_path
        
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="File non trovato")
        
        if not full_path.is_file():
            raise HTTPException(status_code=400, detail="Non è un file")
        
        # Verifica che il path sia dentro DOCS_BASE_PATH (security)
        if not str(full_path.resolve()).startswith(str(Path(DOCS_BASE_PATH).resolve())):
            raise HTTPException(status_code=403, detail="Accesso negato")
        
        return FileResponse(
            path=str(full_path),
            filename=full_path.name,
            media_type="application/octet-stream"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Errore download: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== Preview/Thumbnail =====
@app.get("/preview/{file_path:path}")
async def preview_file(file_path: str, page: int = Query(0, ge=0)):
    """
    Anteprima file (solo PDF per ora)
    Ritorna immagine PNG della pagina richiesta
    """
    try:
        full_path = Path(DOCS_BASE_PATH) / file_path
        
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="File non trovato")
        
        # Security check
        if not str(full_path.resolve()).startswith(str(Path(DOCS_BASE_PATH).resolve())):
            raise HTTPException(status_code=403, detail="Accesso negato")
        
        ext = full_path.suffix.lower()
        
        # PDF
        if ext == '.pdf':
            try:
                import fitz  # PyMuPDF
                from io import BytesIO
                
                doc = fitz.open(str(full_path))
                
                if page >= len(doc):
                    raise HTTPException(status_code=400, detail=f"Pagina {page} non esiste (max {len(doc)-1})")
                
                page_obj = doc[page]
                pix = page_obj.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom
                
                img_bytes = pix.tobytes("png")
                
                buf = BytesIO(img_bytes)
                buf.seek(0)
                
                return Response(content=buf.getvalue(), media_type="image/png")
            
            except ImportError:
                raise HTTPException(status_code=500, detail="PyMuPDF non installato (pip install pymupdf)")
        
        # DOCX (convert to PDF first, then thumbnail)
        elif ext == '.docx':
            # Richiede LibreOffice o docx2pdf
            raise HTTPException(status_code=501, detail="Thumbnail DOCX non ancora implementato")
        
        else:
            raise HTTPException(status_code=400, detail=f"Formato {ext} non supportato per thumbnail")
    
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Errore thumbnail: {e}")
        import traceback
        log.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

# ===== Ingestion Management =====
@app.post("/ingestion/start")
async def start_ingestion(
    model: str = Query(DEFAULT_MODEL, description="Modello da usare"),
    mode: str = Query("full", description="full o incremental")
):
    """Avvia ingestion"""
    if model not in MODEL_CONFIGS:
        raise HTTPException(status_code=400, detail=f"Modello non supportato: {model}")
    
    try:
        rc = rconn()
        q = Queue("kb_ingestion", connection=rc)
        
        # ✅ USA STRING REFERENCE - worker_tasks.py è nel worker container, NON nell'API
        job = q.enqueue(
            'worker_tasks.run_ingestion',
            mode=mode,
            model_type=model,
            job_timeout="24h",
            result_ttl=86400
        )
        
        return {
            "ok": True,
            "job_id": job.id,
            "model": model,
            "mode": mode,
            "message": f"Ingestion avviata con modello {model}"
        }
    
    except Exception as e:
        log.error(f"Errore avvio ingestion: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ingestion/stop")
async def stop_ingestion():
    """Ferma ingestion (graceful)"""
    try:
        rc = rconn()
        rc.set("kb:ingestion_stop", "1")
        return {"ok": True, "message": "Stop richiesto"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ingestion/pause")
async def pause_ingestion():
    """Pausa ingestion"""
    try:
        rc = rconn()
        rc.set("kb:ingestion_pause", "1")
        return {"ok": True, "message": "Ingestion in pausa"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ingestion/resume")
async def resume_ingestion():
    """Riprendi ingestion"""
    try:
        rc = rconn()
        rc.delete("kb:ingestion_pause")
        return {"ok": True, "message": "Ingestion ripresa"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/progress")
async def get_progress():
    """Ottieni progresso ingestion"""
    try:
        rc = rconn()
        
        progress_raw = rc.get("kb:progress")
        progress = json.loads(progress_raw) if progress_raw else {
            "running": False, "done": 0, "total": 0, "stage": "idle"
        }
        
        current_doc_raw = rc.get("kb:current_doc")
        current_doc = json.loads(current_doc_raw) if current_doc_raw else None
        
        stats_raw = rc.get("kb:stats")
        stats = json.loads(stats_raw) if stats_raw else {
            "success": 0, "failed": 0, "chunked": 0, "meili_indexed": 0, "qdrant_vectorized": 0
        }
        
        return {
            **progress,
            "current_doc": current_doc,
            "stats": stats
        }
    
    except Exception as e:
        log.error(f"Errore progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
async def get_stats():
    """Statistiche aggregate"""
    try:
        rc = rconn()
        stats_raw = rc.get("kb:stats")
        stats = json.loads(stats_raw) if stats_raw else {}
        
        # Aggiungi stats da servizi
        try:
            with pg_conn() as conn, conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as cnt FROM documents")
                stats["postgres_docs"] = cur.fetchone()["cnt"]
        except:
            stats["postgres_docs"] = 0
        
        try:
            qd = qdrant_client()
            collections = qd.get_collections().collections
            stats["qdrant_collections"] = {c.name: qd.get_collection(c.name).points_count for c in collections}
        except:
            stats["qdrant_collections"] = {}
        
        try:
            meili = meili_client()
            idx = meili.index(MEILI_INDEX)
            meili_stats = idx.get_stats()
            stats["meilisearch_docs"] = meili_stats.get("numberOfDocuments", 0)
        except:
            stats["meilisearch_docs"] = 0
        
        return stats
    
    except Exception as e:
        log.error(f"Errore stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/failed_docs")
async def get_failed_docs(limit: int = Query(100, ge=1, le=1000)):
    """Lista documenti falliti"""
    try:
        rc = rconn()
        failed = rc.lrange("kb:failed_docs", 0, limit - 1)
        return [json.loads(f) for f in failed]
    except Exception as e:
        log.error(f"Errore failed_docs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/processing_log")
async def get_processing_log(limit: int = Query(50, ge=1, le=500)):
    """Log processing"""
    try:
        rc = rconn()
        log_entries = rc.lrange("kb:processing_log", 0, limit - 1)
        return [json.loads(entry) for entry in log_entries]
    except Exception as e:
        log.error(f"Errore processing_log: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/queue")
async def get_queue_info():
    """Info queue RQ"""
    try:
        rc = redis.from_url(REDIS_URL, decode_responses=False)
        q = Queue("kb_ingestion", connection=rc)
        
        jobs = []
        for job_id in q.job_ids:
            try:
                job = Job.fetch(job_id, connection=rc)
                jobs.append({
                    "id": job.id,
                    "status": job.get_status(),
                    "created_at": job.created_at.isoformat() if job.created_at else None
                })
            except:
                pass
        
        return {
            "name": q.name,
            "count": len(q),
            "jobs": jobs
        }
    except Exception as e:
        log.error(f"Errore queue: {e}")
        return {"name": "kb_ingestion", "count": 0, "jobs": [], "error": str(e)}

@app.delete("/admin/failed")
async def clear_failed():
    """Pulisci lista failed"""
    try:
        rc = rconn()
        rc.delete("kb:failed_docs")
        return {"ok": True, "message": "Failed docs cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===== Models Management =====
@app.get("/models")
async def list_models():
    """Lista modelli disponibili"""
    models = []
    qd = qdrant_client()
    collections = qd.get_collections().collections
    
    for model_type, config in MODEL_CONFIGS.items():
        collection_name = f"{config['collection_prefix']}_chunks"
        
        # Verifica se collection esiste
        exists = any(c.name == collection_name for c in collections)
        points_count = 0
        
        if exists:
            try:
                coll_info = qd.get_collection(collection_name)
                points_count = coll_info.points_count
            except:
                pass
        
        models.append({
            "type": model_type,
            "name": config["name"],
            "dimension": config["dimension"],
            "collection": collection_name,
            "available": exists,
            "points_count": points_count
        })
    
    return {"models": models}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
