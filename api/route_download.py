import os
from fastapi import HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import text

KB_ROOT = os.getenv("KB_ROOT", "/mnt/kb")

def _safe_join(root, maybe_abs):
    # accetta path assoluti già sotto KB_ROOT o relativi
    full = maybe_abs if os.path.isabs(maybe_abs) else os.path.join(KB_ROOT, maybe_abs)
    full = os.path.realpath(full); root = os.path.realpath(KB_ROOT)
    if not full.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="Path fuori KB_ROOT")
    return full

def attach(app, engine):
    @app.get("/download")
    def download(doc_id: int = Query(..., ge=1)):
        # prendi il path dal DB
        with engine.begin() as cx:
            row = cx.execute(text("SELECT path FROM documents WHERE id = :i"), {"i": doc_id}).fetchone()
        if not row: raise HTTPException(status_code=404, detail="Documento non trovato")
        full = _safe_join(KB_ROOT, row.path)
        if not os.path.exists(full): raise HTTPException(status_code=404, detail=f"File assente: {full}")
        fn = os.path.basename(full)
        # forza il download
        return FileResponse(full, media_type="application/octet-stream", filename=fn)
