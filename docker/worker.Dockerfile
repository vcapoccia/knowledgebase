# docker/worker.Dockerfile
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# OS deps (OCR + parsers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg locales tini \
    tesseract-ocr tesseract-ocr-ita tesseract-ocr-eng \
    poppler-utils poppler-data \
    libreoffice-core libreoffice-writer libreoffice-calc libreoffice-impress \
    libreoffice-java-common default-jre-headless \
    unoconv \
    antiword catdoc \
    ghostscript qpdf file \
    fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

# locale
RUN sed -i 's/# it_IT.UTF-8 UTF-8/it_IT.UTF-8 UTF-8/' /etc/locale.gen \
 && locale-gen it_IT.UTF-8 && update-locale LANG=it_IT.UTF-8
ENV LANG=it_IT.UTF-8 LC_ALL=it_IT.UTF-8

WORKDIR /app

# i sorgenti stanno sotto api/
COPY api/worker_tasks.py /app/worker_tasks.py
COPY api/requirements.txt /app/requirements.txt

# venv + deps Python
RUN python -m venv $VIRTUAL_ENV \
 && pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cu118 -r /app/requirements.txt

COPY docker/worker-entrypoint.sh /usr/local/bin/worker-entrypoint.sh
RUN chmod +x /usr/local/bin/worker-entrypoint.sh

HEALTHCHECK --interval=30s --timeout=5s --retries=5 CMD \
  python -c "import os, redis; r=redis.Redis(host=os.environ.get('REDIS_HOST','redis'), port=int(os.environ.get('REDIS_PORT','6379'))); r.ping()"

ENTRYPOINT ["/usr/bin/tini","--","/usr/local/bin/worker-entrypoint.sh"]
