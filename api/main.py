# api/main.py
import os
import logging
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from route_admin import router as admin_router  # <— importa e monta le API

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="kbsearch-api")

# === static dir detection (prefer frontend/static) ===
STATIC_DIR = "frontend/static"
if not os.path.isdir(STATIC_DIR):
    if os.path.isdir("web/static"):
        STATIC_DIR = "web/static"
    elif os.path.isdir("www/static"):
        STATIC_DIR = "www/static"
    elif os.path.isdir("static"):
        STATIC_DIR = "static"

logger.info("Using STATIC_DIR=%s", STATIC_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# legacy convenience routes (alcuni template usano /style.css /app.js /ENG24-LOGO-ICON-DARK.svg)
def _safe_file(path, media_type, not_found_msg):
    if os.path.isfile(path):
        return FileResponse(path, media_type=media_type)
    return JSONResponse(status_code=404, content={"error": not_found_msg})

@app.get("/style.css")
def style_css():
    return _safe_file(os.path.join(STATIC_DIR, "style.css"), "text/css", "style.css not found")

@app.get("/app.js")
def app_js():
    return _safe_file(os.path.join(STATIC_DIR, "app.js"), "application/javascript", "app.js not found")

@app.get("/ENG24-LOGO-ICON-DARK.svg")
def logo_svg():
    # prova nello static e poi in frontend/static root image
    p = os.path.join(STATIC_DIR, "ENG24-LOGO-ICON-DARK.svg")
    if not os.path.isfile(p):
        # fallback in web/ o www/ root
        for base in ("web", "www", "frontend/static"):
            alt = os.path.join(base, "ENG24-LOGO-ICON-DARK.svg")
            if os.path.isfile(alt):
                p = alt
                break
    return _safe_file(p, "image/svg+xml", "logo not found")

# === templates dir detection ===
if os.path.isdir("frontend/templates"):
    TEMPLATE_DIR = "frontend/templates"
elif os.path.isdir("web"):
    TEMPLATE_DIR = "web"
elif os.path.isdir("www"):
    TEMPLATE_DIR = "www"
else:
    TEMPLATE_DIR = "."

logger.info("Using TEMPLATE_DIR=%s", TEMPLATE_DIR)
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"])
)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    try:
        tpl = env.get_template("home.html")
        return HTMLResponse(tpl.render())
    except Exception:
        logger.exception("Error rendering home template")
        return HTMLResponse("Internal Server Error", status_code=500)

@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin.html", response_class=HTMLResponse)
def admin(request: Request):
    try:
        tpl = env.get_template("admin.html")
        return HTMLResponse(tpl.render())
    except Exception:
        logger.exception("Error rendering admin template")
        return HTMLResponse("Internal Server Error", status_code=500)

@app.get("/health")
def health():
    return {"ok": True, "errors": []}

# === monta le API necessarie all'admin/home ===
app.include_router(admin_router)