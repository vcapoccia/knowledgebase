# worker/worker_tasks.py
import os
import time
import uuid
import logging
from typing import Dict, Any, List, Tuple
import subprocess
import pathlib

import meilisearch
import psycopg
from psycopg.rows import dict_row

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

log = logging.getLogger("kbsearch.worker")

# === CONFIG ===
KB_ROOT = os.getenv("KB_ROOT", "/kbroot")  # monta questo host path nel compose
MEILI_URL = os.getenv("MEILI_URL", "http://meili:7700")
MEILI_MASTER_KEY = os.getenv("MEILI_MASTER_KEY")
MEILI_INDEX = os.getenv("MEILI_INDEX", "kb_docs")

PG_HOST = os.getenv("PGHOST", os.getenv("POSTGRES_HOST", "postgres"))
PG_DB = os.getenv("PGDATABASE", os.getenv("POSTGRES_DB", "kb"))
PG_USER = os.getenv("PGUSER", os.getenv("POSTGRES_USER", "kbuser"))
PG_PASS = os.getenv("PGPASSWORD", os.getenv("POSTGRES_PASSWORD", "kbpass"))
PG_PORT = int(os.getenv("PGPORT", "5432"))

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "kb_docs")

# vettore dummy (1D) giusto per popolare Qdrant; potrai sostituire con embeddings reali
QDRANT_VECTOR_SIZE = int(os.getenv("QDRANT_VECTOR_SIZE", "1"))

def meili_client() -> meilisearch.Client:
    if MEILI_MASTER_KEY:
        return meilisearch.Client(MEILI_URL, MEILI_MASTER_KEY)
    return meilisearch.Client(MEILI_URL)

def pg_conn():
    return psycopg.connect(
        host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASS, port=PG_PORT, row_factory=dict_row
    )

def qdrant_client():
    # disattivo il check compat così non ci blocchiamo per mismatch minori
    return QdrantClient(url=QDRANT_URL, prefer_grpc=False, timeout=120, api_key=None, client_checks=False)

# === UTILS ===
def ensure_tables():
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                path TEXT,
                title TEXT,
                ext TEXT,
                mtime BIGINT,
                content TEXT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS failed_documents (
                id TEXT PRIMARY KEY,
                path TEXT,
                error TEXT,
                ts BIGINT
            );
        """)

def ensure_meili():
    c = meili_client()
    try:
        c.get_raw_index(MEILI_INDEX)
    except Exception:
        c.create_index(MEILI_INDEX, {"primaryKey": "id"})
    idx = c.index(MEILI_INDEX)
    idx.update_settings({
        "searchableAttributes": ["title", "content", "path"],
        "filterableAttributes": ["ext"],
    })
    return idx

def ensure_qdrant():
    qc = qdrant_client()
    try:
        qc.get_collection(QDRANT_COLLECTION)
    except Exception:
        qc.recreate_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=qm.VectorParams(size=QDRANT_VECTOR_SIZE, distance=qm.Distance.COSINE)
        )
    return qc

def extract_text(path: pathlib.Path) -> Tuple[str, str]:
    """
    Ritorna (content, ext). Supporto semplice: .txt, .md, .pdf
    """
    ext = path.suffix.lower().lstrip(".")
    try:
        if ext in ("txt", "md", "csv", "log"):
            return (path.read_text(errors="ignore"), ext)
        if ext == "pdf":
            # richiede poppler-utils nel worker
            out = subprocess.check_output(["pdftotext", "-layout", "-nopgbrk", "-q", str(path), "-"], stderr=subprocess.DEVNULL)
            return (out.decode(errors="ignore"), ext)
        # altri formati: per ora skip o prova "file" semplice
        return ("", ext)
    except Exception as e:
        log.warning("estrazione fallita %s: %s", path, e)
        raise

def list_files(root: str) -> List[pathlib.Path]:
    p = pathlib.Path(root)
    if not p.exists():
        return []
    files = []
    for f in p.rglob("*"):
        if f.is_file():
            files.append(f)
    return files

# === JOB PRINCIPALE ===
def run_ingestion(params: Dict[str, Any]):
    mode = (params or {}).get("mode", "full")
    log.info("Ingestion avviata: mode=%s KB_ROOT=%s", mode, KB_ROOT)

    ensure_tables()
    idx = ensure_meili()
    qc = ensure_qdrant()

    docs_batch: List[Dict[str, Any]] = []
    qdrant_points: List[qm.PointStruct] = []
    failed: List[Dict[str, Any]] = []

    files = list_files(KB_ROOT)
    total = len(files)
    log.info("Trovati %d file", total)

    with pg_conn() as conn, conn.cursor() as cur:
        for i, path in enumerate(files, start=1):
            try:
                content, ext = extract_text(path)
                if not content.strip():
                    raise RuntimeError("contenuto vuoto o non supportato")

                doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(path)))
                title = path.stem
                mtime = int(path.stat().st_mtime)

                # Postgres UPSERT
                cur.execute("""
                    INSERT INTO documents (id, path, title, ext, mtime, content)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        path=EXCLUDED.path, title=EXCLUDED.title, ext=EXCLUDED.ext,
                        mtime=EXCLUDED.mtime, content=EXCLUDED.content;
                """, (doc_id, str(path), title, ext, mtime, content))

                # Meili
                docs_batch.append({
                    "id": doc_id,
                    "path": str(path),
                    "title": title,
                    "ext": ext,
                    "mtime": mtime,
                    "content": content,
                })

                # Qdrant: vettore dummy 1D (sostituibile con embeddings reali)
                qdrant_points.append(
                    qm.PointStruct(
                        id=doc_id,
                        vector=[0.0],
                        payload={"path": str(path), "title": title, "ext": ext, "mtime": mtime}
                    )
                )

                # flush batch periodico
                if len(docs_batch) >= 100:
                    idx.add_documents(docs_batch)
                    docs_batch.clear()
                if len(qdrant_points) >= 256:
                    qc.upsert(collection_name=QDRANT_COLLECTION, points=qdrant_points)
                    qdrant_points.clear()

            except Exception as e:
                log.warning("Fail su %s: %s", path, e)
                failed.append({"id": str(uuid.uuid4()), "path": str(path), "error": str(e), "ts": int(time.time()*1000)})

        # flush finali
        if docs_batch:
            idx.add_documents(docs_batch)
        if qdrant_points:
            qc.upsert(collection_name=QDRANT_COLLECTION, points=qdrant_points)

        # salva failed
        for f in failed:
            cur.execute("""
                INSERT INTO failed_documents (id, path, error, ts)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING;
            """, (f["id"], f["path"], f["error"], f["ts"]))

    log.info("Ingestion terminata: ok=%d, failed=%d", total - len(failed), len(failed))
    return {"ok": True, "processed": total - len(failed), "failed": len(failed)}
