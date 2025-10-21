# ===== AGGIUNGERE AL MAIN.PY DOPO GLI ENDPOINT DI SEARCH =====
# (Circa riga 370, dopo /search_facets)

from fastapi.responses import FileResponse
import os
from pathlib import Path

# Path base documenti
DOCS_BASE_PATH = os.getenv("DOCS_PATH", "/mnt/kb-docs")

@app.get("/download")
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
