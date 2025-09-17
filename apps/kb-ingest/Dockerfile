FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/
# NON installare torch qui: è già nella base CUDA
RUN pip install --no-cache-dir -r requirements.txt

COPY ingest.py /app/

ENV KB_ROOT=/mnt/kb \
    QDRANT_URL=http://qdrant:6333 \
    QDRANT_COLLECTION=kb_chunks \
    CHUNK_SIZE=800 CHUNK_OVERLAP=120 \
    INGEST_BATCH=128 INGEST_LOG_LEVEL=info \
    EMBED_MODEL=BAAI/bge-m3

CMD ["python", "ingest.py"]
