# =======================================================================
# KNOWLEDGEBASE API DOCKERFILE (Multi-stage)
# FastAPI backend per ricerca semantica e gestione knowledge base
# =======================================================================

# -----------------------------------------------------------------------
# STAGE 1: Base Python con dipendenze di sistema
# -----------------------------------------------------------------------
FROM python:3.11-slim as base

LABEL maintainer="vcapoccia@example.com"
LABEL version="2.0.0"
LABEL description="Knowledge Base API - FastAPI Backend"

# Variabili di ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Installa dipendenze di sistema
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Crea utente non-root
RUN useradd --create-home --shell /bin/bash kbuser
WORKDIR /app

# -----------------------------------------------------------------------
# STAGE 2: Dipendenze Python
# -----------------------------------------------------------------------
FROM base as dependencies

# Copia e installa requirements
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------
# STAGE 3: Sviluppo (con hot reload e dev tools)
# -----------------------------------------------------------------------
FROM dependencies as development

# Installa dipendenze sviluppo
COPY requirements.dev.txt .
RUN pip install --no-cache-dir -r requirements.dev.txt

# Installa tools sviluppo
RUN pip install \
    black \
    flake8 \
    pytest \
    pytest-asyncio \
    pytest-cov \
    mypy

# Copia codice applicazione
COPY --chown=kbuser:kbuser . /app/

# Crea directory necessarie
RUN mkdir -p /app/logs /app/temp /app/config && \
    chown -R kbuser:kbuser /app

USER kbuser

# Porta esposta
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando sviluppo con hot reload
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--log-level", "debug"]

# -----------------------------------------------------------------------
# STAGE 4: Produzione (ottimizzata)
# -----------------------------------------------------------------------
FROM dependencies as production

# Copia solo il codice necessario
COPY --chown=kbuser:kbuser app/ /app/app/
COPY --chown=kbuser:kbuser main.py /app/
COPY --chown=kbuser:kbuser config.py /app/
COPY --chown=kbuser:kbuser health_check.py /app/

# Crea directory necessarie
RUN mkdir -p /app/logs /app/temp && \
    chown -R kbuser:kbuser /app

USER kbuser

# Porta esposta
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando produzione
CMD ["gunicorn", "main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-", "--log-level", "info"]