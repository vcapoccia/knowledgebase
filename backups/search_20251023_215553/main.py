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
        collection_name = f"{config['collection_prefix']}_docs"
        
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
        
        # AGGREGAZIONE: Raggruppa chunk per documento, tieni il migliore per ogni doc
        docs_map = {}
        for hit in results:
            doc_id = hit.payload.get("doc_id") or hit.payload.get("path")
            
            if not doc_id:
                continue
            
            # Se documento non ancora visto, o questo chunk ha score migliore
            if doc_id not in docs_map or hit.score > docs_map[doc_id]["score"]:
                docs_map[doc_id] = {
                    "id": doc_id,
                    "score": hit.score,
                    "title": hit.payload.get("title"),
                    "text": hit.payload.get("text", "")[:500],  # Preview
                    "path": hit.payload.get("path"),
                    "area": hit.payload.get("area"),
                    "anno": hit.payload.get("anno"),
                    "cliente": hit.payload.get("cliente"),
                    "oggetto": hit.payload.get("oggetto"),
                    "tipo_doc": hit.payload.get("tipo_doc"),
                    "categoria": hit.payload.get("categoria"),
                    "ext": hit.payload.get("ext"),
                    "chunk_id": hit.payload.get("chunk_id"),
                    "page_number": hit.payload.get("page_number"),
                    "versione": hit.payload.get("versione")
                }
        
        # Converti map in lista e ordina per score
        unique_docs = sorted(docs_map.values(), key=lambda x: x["score"], reverse=True)
        
        # Prendi solo top_k documenti
        hits = unique_docs[:top_k]
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return {
            "total": len(hits),
            "total_unique_docs": len(unique_docs),  # Quanti documenti unici trovati
            "total_chunks_searched": len(results),   # Quanti chunk esaminati
            "hits": hits,
            "processing_time_ms": round(processing_time, 2),
            "model": model,
            "collection": collection_name,
            "search_method": "semantic"  # Aggiungo campo mancante
        }
    
    except Exception as e:
        log.error(f"Errore ricerca: {e}")
        import traceback
        log.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search/keyword")
async def search_keyword(
    q: str = Query(..., description="Query keyword"),
    limit: int = Query(20, ge=1, le=100),
    filters: Optional[str] = Query(None)
):
    """
    Ricerca keyword su Meilisearch (fallback)
    """
    if not q or not q.strip():
        return {"total": 0, "hits": [], "processing_time_ms": 0}
    
    start_time = datetime.now()
    
    try:
        meili = meili_client()
        idx = meili.index(MEILI_INDEX)
        
        # Prepara filtri Meilisearch
        meili_filters = []
        if filters:
            for f in filters.split(','):
                if ':' in f:
                    key, value = f.split(':', 1)
                    meili_filters.append(f"{key.strip()} = '{value.strip()}'")
        
        filter_str = " AND ".join(meili_filters) if meili_filters else None
        
        results = idx.search(
            q.strip(),
            {
                "limit": limit,
                "filter": filter_str,
                "attributesToRetrieve": ["id", "title", "content", "path", "area", "anno", "cliente", "oggetto"]
            }
        )
        
        hits = []
        for hit in results.get("hits", []):
            hits.append({
                "id": hit.get("id"),
                "title": hit.get("title"),
                "text": hit.get("content", "")[:500],
                "path": hit.get("path"),
                "area": hit.get("area"),
                "anno": hit.get("anno"),
                "cliente": hit.get("cliente"),
                "oggetto": hit.get("oggetto")
            })
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return {
            "total": results.get("estimatedTotalHits", 0),
            "hits": hits,
            "processing_time_ms": round(processing_time, 2)
        }
    
    except Exception as e:
        log.error(f"Errore ricerca keyword: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== Facets =====
@app.get("/facets")
@app.get("/api/facets")
async def get_facets():
    """
    Ritorna faccette aggregate da PostgreSQL (GLOBALI - tutti i documenti)
    """
    try:
        with pg_conn() as conn, conn.cursor() as cur:
            facets = {}
            
            # Area
            cur.execute("SELECT area, COUNT(*) as cnt FROM documents WHERE area IS NOT NULL GROUP BY area ORDER BY cnt DESC")
            facets["area"] = {row["area"]: row["cnt"] for row in cur.fetchall()}
            
            # Anno
            cur.execute("SELECT anno, COUNT(*) as cnt FROM documents WHERE anno IS NOT NULL GROUP BY anno ORDER BY anno DESC")
            facets["anno"] = {row["anno"]: row["cnt"] for row in cur.fetchall()}
            
            # Cliente
            cur.execute("SELECT cliente, COUNT(*) as cnt FROM documents WHERE cliente IS NOT NULL GROUP BY cliente ORDER BY cnt DESC LIMIT 50")
            facets["cliente"] = {row["cliente"]: row["cnt"] for row in cur.fetchall()}
            
            # Oggetto
            cur.execute("SELECT oggetto, COUNT(*) as cnt FROM documents WHERE oggetto IS NOT NULL GROUP BY oggetto ORDER BY cnt DESC LIMIT 50")
            facets["oggetto"] = {row["oggetto"]: row["cnt"] for row in cur.fetchall()}
            
            # Tipo Doc
            cur.execute("SELECT tipo_doc, COUNT(*) as cnt FROM documents WHERE tipo_doc IS NOT NULL GROUP BY tipo_doc ORDER BY cnt DESC")
            facets["tipo_doc"] = {row["tipo_doc"]: row["cnt"] for row in cur.fetchall()}
            
            # Categoria
            cur.execute("SELECT categoria, COUNT(*) as cnt FROM documents WHERE categoria IS NOT NULL GROUP BY categoria ORDER BY cnt DESC")
            facets["categoria"] = {row["categoria"]: row["cnt"] for row in cur.fetchall()}
            
            # Estensione
            cur.execute("SELECT ext, COUNT(*) as cnt FROM documents WHERE ext IS NOT NULL GROUP BY ext ORDER BY cnt DESC")
            facets["ext"] = {row["ext"]: row["cnt"] for row in cur.fetchall()}
            
            return {"facets": facets}
    
    except Exception as e:
        log.error(f"Errore facets: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search_facets")
@app.get("/api/search_facets")
async def get_search_facets(
    q_text: str = Query(..., description="Query di ricerca"),
    model: str = Query(DEFAULT_MODEL, description="Modello embedding"),
    filters: Optional[str] = Query(None, description="Filtri applicati")
):
    """
    Faccette DINAMICHE basate sui risultati della ricerca corrente
    """
    try:
        # 1. Esegui ricerca per ottenere doc_ids risultanti
        if model not in MODEL_CONFIGS:
            model = DEFAULT_MODEL
        
        config = MODEL_CONFIGS[model]
        collection_name = f"{config['collection_prefix']}_docs"
        
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
        
        # Ricerca vettoriale (top 100 per avere buon campione)
        qd = qdrant_client()
        results = qd.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=100,
            query_filter=qdrant_filter,
            with_payload=True
        )
        
        # 2. Estrai doc_ids dai risultati
        doc_ids = [hit.payload.get("doc_id") for hit in results if hit.payload.get("doc_id")]
        
        if not doc_ids:
            return {"facets": {}, "total_results": 0}
        
        # 3. Aggrega faccette SOLO su questi doc_ids
        with pg_conn() as conn, conn.cursor() as cur:
            facets = {}
            
            # Area
            cur.execute("""
                SELECT area, COUNT(*) as cnt 
                FROM documents 
                WHERE id = ANY(%s) AND area IS NOT NULL 
                GROUP BY area 
                ORDER BY cnt DESC
            """, (doc_ids,))
            facets["area"] = {row["area"]: row["cnt"] for row in cur.fetchall()}
            
            # Anno
            cur.execute("""
                SELECT anno, COUNT(*) as cnt 
                FROM documents 
                WHERE id = ANY(%s) AND anno IS NOT NULL 
                GROUP BY anno 
                ORDER BY anno DESC
            """, (doc_ids,))
            facets["anno"] = {row["anno"]: row["cnt"] for row in cur.fetchall()}
            
            # Cliente
            cur.execute("""
                SELECT cliente, COUNT(*) as cnt 
                FROM documents 
                WHERE id = ANY(%s) AND cliente IS NOT NULL 
                GROUP BY cliente 
                ORDER BY cnt DESC 
                LIMIT 20
            """, (doc_ids,))
            facets["cliente"] = {row["cliente"]: row["cnt"] for row in cur.fetchall()}
            
            # Oggetto
            cur.execute("""
                SELECT oggetto, COUNT(*) as cnt 
                FROM documents 
                WHERE id = ANY(%s) AND oggetto IS NOT NULL 
                GROUP BY oggetto 
                ORDER BY cnt DESC 
                LIMIT 20
            """, (doc_ids,))
            facets["oggetto"] = {row["oggetto"]: row["cnt"] for row in cur.fetchall()}
            
            # Tipo Doc
            cur.execute("""
                SELECT tipo_doc, COUNT(*) as cnt 
                FROM documents 
                WHERE id = ANY(%s) AND tipo_doc IS NOT NULL 
                GROUP BY tipo_doc 
                ORDER BY cnt DESC
            """, (doc_ids,))
            facets["tipo_doc"] = {row["tipo_doc"]: row["cnt"] for row in cur.fetchall()}
            
            # Categoria
            cur.execute("""
                SELECT categoria, COUNT(*) as cnt 
                FROM documents 
                WHERE id = ANY(%s) AND categoria IS NOT NULL 
                GROUP BY categoria 
                ORDER BY cnt DESC
            """, (doc_ids,))
            facets["categoria"] = {row["categoria"]: row["cnt"] for row in cur.fetchall()}
            
            # Estensione
            cur.execute("""
                SELECT ext, COUNT(*) as cnt 
                FROM documents 
                WHERE id = ANY(%s) AND ext IS NOT NULL 
                GROUP BY ext 
                ORDER BY cnt DESC
            """, (doc_ids,))
            facets["ext"] = {row["ext"]: row["cnt"] for row in cur.fetchall()}
            
            return {"facets": facets, "total_results": len(doc_ids)}
    
    except Exception as e:
        log.error(f"Errore search_facets: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== Download & Thumbnail =====
@app.get("/download_file")
async def download_file(path: str = Query(..., description="Path del file da scaricare")):
    """
    Download di un documento dalla knowledge base
    """
    try:
        # Costruisci path completo
        full_path = Path(DOCS_BASE_PATH) / path
        
        # Verifica che il file esista
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="File non trovato")
        
        # Verifica che sia un file (non directory)
        if not full_path.is_file():
            raise HTTPException(status_code=400, detail="Il path specificato non è un file")
        
        # Verifica che il path sia dentro DOCS_BASE_PATH (security)
        if not str(full_path.resolve()).startswith(str(Path(DOCS_BASE_PATH).resolve())):
            raise HTTPException(status_code=403, detail="Accesso negato")
        
        # Ottieni nome file per download
        filename = full_path.name
        
        # Ritorna file
        return FileResponse(
            path=str(full_path),
            filename=filename,
            media_type='application/octet-stream'
        )
    
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Errore download file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/thumbnail")
async def get_thumbnail(
    path: str = Query(..., description="Path del file"),
    page: int = Query(1, ge=1, description="Numero pagina"),
    width: int = Query(200, ge=50, le=500, description="Larghezza thumbnail")
):
    """
    Genera thumbnail di una pagina PDF/DOCX
    """
    try:
        from PIL import Image
        import io
        
        # Costruisci path completo
        full_path = Path(DOCS_BASE_PATH) / path
        
        # Verifica sicurezza
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="File non trovato")
        
        if not str(full_path.resolve()).startswith(str(Path(DOCS_BASE_PATH).resolve())):
            raise HTTPException(status_code=403, detail="Accesso negato")
        
        ext = full_path.suffix.lower()
        
        # PDF
        if ext == '.pdf':
            try:
                import fitz  # PyMuPDF
                
                doc = fitz.open(str(full_path))
                
                if page > len(doc):
                    raise HTTPException(status_code=404, detail=f"Pagina {page} non esiste (totale: {len(doc)})")
                
                # Estrai pagina (0-indexed)
                pdf_page = doc[page - 1]
                
                # Render come immagine
                pix = pdf_page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom per qualità
                img_data = pix.tobytes("png")
                
                # Ridimensiona
                img = Image.open(io.BytesIO(img_data))
                aspect_ratio = img.height / img.width
                new_height = int(width * aspect_ratio)
                img = img.resize((width, new_height), Image.Resampling.LANCZOS)
                
                # Ritorna PNG
                buf = io.BytesIO()
                img.save(buf, format='PNG')
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
        
        # Importa il task
        
        job = q.enqueue(
            'worker_tasks.run_ingestion',
            {"mode": mode, "model": model},
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
        collection_name = f"{config['collection_prefix']}_docs"
        
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
