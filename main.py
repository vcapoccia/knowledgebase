# api/main.py  — compat layer con fallback endpoints e static legacy
import os
import logging
from typing import Any, Dict
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.routing import APIRoute
from jinja2 import Environment, FileSystemLoader, select_autoescape

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kbsearch.main")

app = FastAPI(title="KBSearch API")

# --- STATIC & TEMPLATE autodetection ---
CANDIDATES = [
    ("frontend/static", "frontend/templates"),
    ("web/static", "web"),
    ("www/static", "www"),
    ("static", "."),
]

STATIC_DIR = None
TEMPLATE_DIR = None
for sdir, tdir in CANDIDATES:
    if os.path.isdir(sdir) and os.path.isdir(tdir):
        STATIC_DIR, TEMPLATE_DIR = sdir, tdir
        break
if STATIC_DIR is None:
    for sdir, _ in CANDIDATES:
        if os.path.isdir(sdir):
            STATIC_DIR = sdir
            break
if TEMPLATE_DIR is None:
    for _, tdir in CANDIDATES:
        if os.path.isdir(tdir):
            TEMPLATE_DIR = tdir
            break
if STATIC_DIR is None:
    STATIC_DIR = "frontend/static"
if TEMPLATE_DIR is None:
    TEMPLATE_DIR = "frontend/templates"

logger.info("Using STATIC_DIR=%s TEMPLATE_DIR=%s", STATIC_DIR, TEMPLATE_DIR)

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    logger.warning("STATIC_DIR '%s' non trovato; /static farà 404", STATIC_DIR)

# --- fun di util per rispondere anche a HEAD ---
def file_response_allow_head(path: str, media_type: str):
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=os.path.basename(path) + " not found")
    return FileResponse(path, media_type=media_type)

def add_get_head(path: str):
    def decorator(func):
        app.add_api_route(path, func, methods=["GET","HEAD"])
        return func
    return decorator

# legacy: /style.css
@add_get_head("/style.css")
def legacy_style():
    return file_response_allow_head(os.path.join(STATIC_DIR, "style.css"), "text/css")

# legacy: /app.js
@add_get_head("/app.js")
def legacy_app_js():
    return file_response_allow_head(os.path.join(STATIC_DIR, "app.js"), "application/javascript")

# legacy: /ENG24-LOGO-ICON-DARK.svg
@add_get_head("/ENG24-LOGO-ICON-DARK.svg")
def legacy_logo():
    p1 = os.path.join(STATIC_DIR, "ENG24-LOGO-ICON-DARK.svg")
    p2 = os.path.join(TEMPLATE_DIR, "ENG24-LOGO-ICON-DARK.svg")
    path = p1 if os.path.isfile(p1) else p2
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="ENG24-LOGO-ICON-DARK.svg not found")
    return FileResponse(path, media_type="image/svg+xml")

# --- Jinja env ---
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR if os.path.isdir(TEMPLATE_DIR) else "."),
    autoescape=select_autoescape(["html", "xml"])
)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    try:
        return HTMLResponse(env.get_template("home.html").render())
    except Exception:
        logger.exception("Errore nel render di home.html")
        return HTMLResponse("Internal Server Error (template home)", status_code=500)

@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin.html", response_class=HTMLResponse)
def admin(request: Request):
    try:
        return HTMLResponse(env.get_template("admin.html").render())
    except Exception:
        logger.exception("Errore nel render di admin.html")
        return HTMLResponse("Internal Server Error (template admin)", status_code=500)

@app.get("/health")
def health():
    return {"ok": True, "errors": []}

# --- Importa eventuali route reali (se esistono, registrano endpoints e sovrascrivono i fallback) ---
_imported = []
for mod in ("api.route_admin", "api.route_download", "route_admin", "route_download"):
    try:
        __import__(mod)
        _imported.append(mod)
    except Exception as e:
        logger.debug("Import opzionale %s fallito: %s", mod, e)
logger.info("Moduli route importati: %s", _imported)

# --- Fallback endpoints sicuri (shape atteso dal front-end) ---
@app.get("/failed_docs")
def failed_docs(limit: int = 20):
    return {"failed": []}

@app.get("/queue")
def queue_status():
    return {"queue": []}

@app.get("/progress")
def progress():
    return {"progress": {}}

@app.post("/ingestion/start")
def ingestion_start(mode: str = "full"):
    # se una route reale è presente, verrà usata quella (FastAPI sceglie l'ultima registrata)
    return {"ok": True, "enqueued": False, "reason": "fallback-not-configured"}

@app.post("/init_indexes")
def init_indexes():
    return {"ok": True, "init": "fallback-no-op"}

@app.get("/filters")
def filters():
    # usato dalla home con faccette/filtri: restituisce shape vuota compatibile
    return {
        "area": [],
        "tipo": [],
        "anno": [],
        "extra": {"clienti": [], "oggetti": [], "categorie": [], "extensions": []}
    }

@app.post("/search")
def search(body: Dict[str, Any]):
    # shape minima attesa dalla home
    return {"hits": [], "total": 0, "page": body.get("page", 1), "per_page": body.get("per_page", 10)}
