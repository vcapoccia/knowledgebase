#!/usr/bin/env python3
"""
KNOWLEDGEBASE API - Main Application
=====================================

Sistema di Knowledge Base Semantico con ricerca vettoriale
FastAPI backend per gestione documenti e ricerca semantica

Autore: vcapoccia
Versione: 2.0.0
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseSettings

# Importa i moduli applicazione
from app.api import router as api_router
from app.models import SearchRequest, SearchResponse, HealthResponse
from app.services import QdrantService, DocumentService
from app.utils import setup_logging, get_system_info
from config import settings

# =======================================================================
# CONFIGURAZIONI E LOGGING
# =======================================================================

# Setup logging
logger = setup_logging(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format_type=settings.LOG_FORMAT
)

# =======================================================================
# LIFECYCLE MANAGEMENT
# =======================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestisce il ciclo di vita dell'applicazione"""
    
    logger.info("🚀 Avvio Knowledge Base API...")
    
    try:
        # Inizializza servizi
        logger.info("Inizializzazione servizi...")
        
        # Controlla connessione Qdrant
        qdrant_service = QdrantService()
        await qdrant_service.health_check()
        logger.info("✅ Qdrant connesso e funzionante")
        
        # Inizializza servizio documenti
        doc_service = DocumentService()
        await doc_service.initialize()
        logger.info("✅ Servizio documenti inizializzato")
        
        # Controlla directory documenti
        if not Path(settings.KB_ROOT).exists():
            logger.warning(f"⚠️  Directory documenti non trovata: {settings.KB_ROOT}")
        else:
            doc_count = len(list(Path(settings.KB_ROOT).rglob("*.pdf"))) + \
                       len(list(Path(settings.KB_ROOT).rglob("*.docx"))) + \
                       len(list(Path(settings.KB_ROOT).rglob("*.txt")))
            logger.info(f"📚 Trovati {doc_count} documenti nella knowledge base")
        
        logger.info("✅ Knowledge Base API avviato con successo!")
        
        yield
        
    except Exception as e:
        logger.error(f"❌ Errore durante l'avvio: {str(e)}")
        sys.exit(1)
    
    finally:
        # Cleanup
        logger.info("🛑 Spegnimento Knowledge Base API...")
        try:
            await qdrant_service.close()
            await doc_service.close()
            logger.info("✅ Servizi chiusi correttamente")
        except Exception as e:
            logger.error(f"❌ Errore durante lo spegnimento: {str(e)}")

# =======================================================================
# APPLICAZIONE FASTAPI
# =======================================================================

app = FastAPI(
    title="Knowledge Base API",
    description="""
    🧠 **Knowledge Base API v2.0**
    
    Sistema avanzato di ricerca semantica per knowledge base aziendali.
    
    **Caratteristiche:**
    - 🔍 Ricerca semantica con embeddings
    - 📊 Faceted search e filtri avanzati
    - 📄 Supporto PDF, DOCX, TXT, HTML
    - 🚀 API REST ad alte performance
    - 💾 Storage vettoriale con Qdrant
    
    **Endpoints principali:**
    - `/api/search` - Ricerca semantica
    - `/api/facets` - Filtri disponibili
    - `/api/health` - Status sistema
    """,
    version="2.0.0",
    docs_url="/api/docs" if settings.ENV != "production" else None,
    redoc_url="/api/redoc" if settings.ENV != "production" else None,
    lifespan=lifespan
)

# =======================================================================
# MIDDLEWARE
# =======================================================================

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# =======================================================================
# EXCEPTION HANDLERS
# =======================================================================

@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    logger.error(f"ValueError: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Invalid request", "detail": str(exc)}
    )

@app.exception_handler(ConnectionError)
async def connection_error_handler(request, exc):
    logger.error(f"Connection Error: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error": "Service unavailable", "detail": "Database connection failed"}
    )

# =======================================================================
# ROUTE PRINCIPALI
# =======================================================================

@app.get("/", response_model=dict)
async def root():
    """Homepage API con informazioni sistema"""
    return {
        "name": "Knowledge Base API",
        "version": "2.0.0",
        "status": "online",
        "environment": settings.ENV,
        "docs_url": "/api/docs" if settings.ENV != "production" else None,
        "endpoints": {
            "search": "/api/search",
            "facets": "/api/facets", 
            "health": "/api/health",
            "docs": "/api/docs"
        }
    }

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """
    Health check completo del sistema
    
    Controlla:
    - Stato API
    - Connessione Qdrant
    - Disponibilità documenti
    - Utilizzo memoria
    """
    try:
        # Informazioni sistema
        system_info = get_system_info()
        
        # Controlla Qdrant
        qdrant_service = QdrantService()
        qdrant_status = await qdrant_service.health_check()
        
        # Controlla documenti
        kb_root_exists = Path(settings.KB_ROOT).exists()
        doc_count = 0
        if kb_root_exists:
            doc_count = len(list(Path(settings.KB_ROOT).rglob("*")))
        
        # Status generale
        overall_status = "healthy" if qdrant_status and kb_root_exists else "degraded"
        
        return HealthResponse(
            status=overall_status,
            version="2.0.0",
            timestamp=system_info["timestamp"],
            services={
                "api": "healthy",
                "qdrant": "healthy" if qdrant_status else "unhealthy",
                "documents": "healthy" if kb_root_exists else "unhealthy"
            },
            metrics={
                "documents_available": doc_count,
                "memory_usage_mb": system_info["memory_usage_mb"],
                "cpu_usage_percent": system_info["cpu_usage_percent"],
                "disk_usage_percent": system_info["disk_usage_percent"]
            },
            configuration={
                "kb_root": settings.KB_ROOT,
                "qdrant_url": settings.QDRANT_URL,
                "qdrant_collection": settings.QDRANT_COLLECTION,
                "environment": settings.ENV
            }
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Health check failed: {str(e)}"
        )

# =======================================================================
# INCLUDE ROUTES
# =======================================================================

# Include API routes
app.include_router(
    api_router,
    prefix="/api",
    tags=["search"]
)

# =======================================================================
# STATIC FILES (per sviluppo)
# =======================================================================

if settings.ENV == "development":
    # Serve file statici solo in sviluppo
    if Path("static").exists():
        app.mount("/static", StaticFiles(directory="static"), name="static")

# =======================================================================
# MAIN ENTRY POINT
# =======================================================================

if __name__ == "__main__":
    # Configurazione server
    server_config = {
        "host": "0.0.0.0",
        "port": 8000,
        "log_level": settings.LOG_LEVEL.lower(),
        "access_log": True,
        "server_header": False,  # Security: hide server header
        "date_header": False,    # Security: hide date header
    }
    
    if settings.ENV == "development":
        # Configurazione sviluppo
        server_config.update({
            "reload": True,
            "reload_dirs": ["app"],
            "reload_excludes": ["*.log", "*.pyc", "__pycache__"],
        })
    else:
        # Configurazione produzione
        server_config.update({
            "workers": settings.KB_API_WORKERS or 4,
            "loop": "uvloop",  # Faster event loop
            "http": "httptools",  # Faster HTTP parser
        })
    
    logger.info(f"🚀 Avvio server {settings.ENV}...")
    logger.info(f"📊 Configurazione: {server_config}")
    
    try:
        uvicorn.run("main:app", **server_config)
    except KeyboardInterrupt:
        logger.info("👋 Server fermato dall'utente")
    except Exception as e:
        logger.error(f"❌ Errore server: {str(e)}")
        sys.exit(1)