# worker/worker_tasks.py  (usa lo stesso contenuto anche in api/worker_tasks.py e ./worker_tasks.py)
import os
import json
import logging
from datetime import datetime
from meilisearch import Client as MeiliClient
from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# env defaults
MEILI_URL = os.environ.get("MEILI_URL", "http://meili:7700")
MEILI_KEY = os.environ.get("MEILI_KEY", "")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
POSTGRES_DSN = os.environ.get("POSTGRES_DSN", "postgresql://kbuser:kbpass@postgres:5432/kb")

# create Meili client with compatibility fallback
def create_meili_client():
    try:
        meili = MeiliClient(MEILI_URL, MEILI_KEY)
    except TypeError:
        # older/newer clients may have different signature
        meili = MeiliClient(MEILI_URL)
    return meili

# helper to sanitize documents for Meili
def sanitize_docs_for_meili(docs):
    """
    Accept many input shapes and return a list of dicts suitable for Meili.
    """
    if docs is None:
        return []

    # coerce generator/iterable to list
    if isinstance(docs, (str, bytes)):
        # single string -> create dict
        return [{"text": docs}]
    try:
        docs_list = list(docs)
    except Exception:
        docs_list = [docs]

    sanitized = []
    for d in docs_list:
        if d is None:
            continue
        if isinstance(d, dict):
            sanitized.append(d)
            continue
        # try to convert known types
        try:
            sanitized.append(dict(d))
            continue
        except Exception:
            # fallback generic representation
            sanitized.append({"text": str(d)})
    return sanitized

# example task that writes to Meili and Qdrant
def run_ingestion(mode="full"):
    logger.info("Starting ingestion mode=%s at %s", mode, datetime.utcnow().isoformat())
    meili = create_meili_client()

    # example: produce docs from your indexing pipeline
    # replace the following with your actual doc generator
    docs = [
        {"id": "doc1", "title": "Example", "text": "Test content"},
    ]

    sanitized = sanitize_docs_for_meili(docs)
    if not sanitized:
        logger.info("No docs to index for Meili")
    else:
        try:
            # ensure index exists
            idx = meili.index("kb_docs")
            # add documents
            add_result = idx.add_documents(sanitized)
            logger.info("Meili add_documents result: %s", add_result)
        except Exception as e:
            logger.exception("Failed to push docs to Meili: %s", e)
            # re-raise if needed or handle job failure accordingly
            raise

    # Qdrant: example connection (adapt to your schema)
    try:
        qdr = QdrantClient(url=QDRANT_URL)
        # implement qdrant indexing here (create collection, upsert vectors, etc.)
        logger.info("Connected to Qdrant at %s", QDRANT_URL)
    except Exception as e:
        logger.exception("Failed to connect to Qdrant: %s", e)

    logger.info("Ingestion finished")
    return {"ok": True}
