import os, yaml, re, sqlite3, threading
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Query, Header, HTTPException
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from sentence_transformers import SentenceTransformer
import torch
API_PORT = int(os.getenv("API_PORT", "8080"))
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "kb_chunks")
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "changeme-admin-token")
DATA_DIR = os.getenv("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "app.db")

os.makedirs(DATA_DIR, exist_ok=True)

with open("config.yaml") as f:
    CFG = yaml.safe_load(f)

app = FastAPI(title="KB Search API", version="1.1.0")
qc = QdrantClient(url=QDRANT_URL)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
embedder = SentenceTransformer(EMBED_MODEL, device=DEVICE)
_db_lock = threading.Lock()
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _db_lock:
        conn = get_db()
        cur = conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS metadata_vocab (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            label TEXT,
            type TEXT DEFAULT 'string',
            allowed_values TEXT,
            group_key TEXT,
            UNIQUE(key)
        );
        CREATE TABLE IF NOT EXISTS doc_user_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            user_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at INTEGER DEFAULT (strftime('%s','now')),
            updated_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE INDEX IF NOT EXISTS idx_doc_user_meta_doc ON doc_user_meta(doc_id);
        CREATE INDEX IF NOT EXISTS idx_doc_user_meta_status ON doc_user_meta(status);
        """)
        conn.commit()
        conn.close()

init_db()

class Hit(BaseModel):
    doc_id: str
    title: str
    path_rel: str
    score: float
    snippet: str
    chunk_index: int
    kb_area: Optional[str] = None
    livello: Optional[str] = None
    sd: Optional[str] = None
    sezione: Optional[str] = None
    anno: Optional[int] = None
    cliente: Optional[str] = None
    ambito: Optional[str] = None
    oda_code: Optional[str] = None
    as_code: Optional[str] = None
    as_rdo: Optional[str] = None
    as_cliente: Optional[str] = None

def parse_operators(q: str) -> (str, Dict[str, Any]):
    pattern = r'(?P<k>\w+):(?P<v>"[^"]+"|\S+)'
    filters = {}
    for key, val in re.findall(pattern, q):
        v = val.strip('"')
        key = key.lower()
        if key in ("kb", "livello", "sd", "sezione", "cliente", "ambito", "oda", "as", "rdo"):
            mapkey = {"kb":"kb_area","oda":"oda_code","as":"as_code","rdo":"as_rdo"}.get(key, key)
            filters[mapkey] = v
        elif key == "anno":
            if ".." in v:
                lo, hi = v.split("..", 1)
                filters["anno_range"] = (int(lo or 0), int(hi or 9999))
            else:
                filters["anno"] = int(v)
    q_clean = re.sub(pattern, "", q).strip()
    return q_clean, filters

def build_qdrant_filter(filters: Dict[str, Any]) -> Optional[qm.Filter]:
    must = []
    for k in ["kb_area","livello","sd","sezione","cliente","ambito","oda_code","as_code","as_rdo"]:
        if k in filters:
            must.append(qm.FieldCondition(key=k, match=qm.MatchValue(value=filters[k])))
    if "anno" in filters:
        must.append(qm.FieldCondition(key="anno", match=qm.MatchValue(value=filters["anno"])))
    if "anno_range" in filters:
        lo, hi = filters["anno_range"]
        must.append(qm.FieldCondition(key="anno", range=qm.Range(gte=lo, lte=hi)))
    return qm.Filter(must=must) if must else None

def admin_auth(authorization: Optional[str]):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ",1)[1]
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

@app.get("/health")
def health():
    pending = get_db().execute("select count(*) as c from doc_user_meta where status='pending'").fetchone()["c"]
    return {"status": "ok", "pending_meta": pending}

@app.get("/search")
def search(q: str = Query(..., min_length=1), k: int = 20):
    q_text, ops = parse_operators(q)
    vec = embedder.encode(q_text or q, normalize_embeddings=True).tolist()
    qfilt = build_qdrant_filter(ops)
    res = qc.search(collection_name=QDRANT_COLLECTION, query_vector=vec, with_payload=True, limit=k, query_filter=qfilt)
    hits: List[Hit] = []
    doc_ids: List[str] = []
    for p in res:
        pl = p.payload or {}
        doc_ids.append(pl.get("doc_id",""))
        hits.append(Hit(
            doc_id=pl.get("doc_id",""),
            title=pl.get("title",""),
            path_rel=pl.get("path_rel",""),
            score=float(p.score),
            snippet=(pl.get("chunk_text","")[:350] + "...") if pl.get("chunk_text") else "",
            chunk_index=pl.get("chunk_index",0),
            kb_area=pl.get("kb_area"),
            livello=pl.get("livello"),
            sd=pl.get("sd"),
            sezione=pl.get("sezione"),
            anno=pl.get("anno"),
            cliente=pl.get("cliente"),
            ambito=pl.get("ambito"),
            oda_code=pl.get("oda_code"),
            as_code=pl.get("as_code"),
            as_rdo=pl.get("as_rdo"),
            as_cliente=pl.get("as_cliente"),
        ))
    user_meta_map: Dict[str, Dict[str, List[str]]] = {}
    if doc_ids:
        ph = ",".join("?" for _ in doc_ids)
        rows = get_db().execute(
            f"select doc_id, key, value from doc_user_meta where status='approved' and doc_id in ({ph})",
            doc_ids
        ).fetchall()
        for r in rows:
            user_meta_map.setdefault(r["doc_id"], {}).setdefault(r["key"], []).append(r["value"])
    return {"query": q, "operators": ops, "hits": [h.model_dump() | {"user_meta": user_meta_map.get(h.doc_id, {})} for h in hits]}

@app.get("/facets")
def facets(q: str = Query("", description="optional query to scope facets"), k: int = 200):
    q_text, ops = parse_operators(q)
    vec = embedder.encode(q_text or " ", normalize_embeddings=True).tolist()
    qfilt = build_qdrant_filter(ops)
    res = qc.search(collection_name=QDRANT_COLLECTION, query_vector=vec, with_payload=True, limit=k, query_filter=qfilt)
    docs = [p.payload for p in res if p.payload]
    def count(field: str):
        agg: Dict[str,int] = {}
        for pl in docs:
            v = pl.get(field)
            if v is None: continue
            s = str(v)
            agg[s] = agg.get(s,0) + 1
        return agg
    strong_fields = ["kb_area","livello","sd","sezione","anno","cliente","ambito","oda_code","as_code","as_rdo"]
    strong = {f: count(f) for f in strong_fields}
    ids = [pl.get("doc_id","") for pl in docs]
    user_facets: Dict[str, Dict[str,int]] = {}
    if ids:
        ph = ",".join("?" for _ in ids)
        rows = get_db().execute(
            f"select key, value, count(*) as c from doc_user_meta where status='approved' and doc_id in ({ph}) group by key, value",
            ids
        ).fetchall()
        for r in rows:
            user_facets.setdefault(r["key"], {})[r["value"]] = r["c"]
    return {"strong": strong, "user": user_facets, "count": len(docs)}

class AddMetaPayload(BaseModel):
    doc_id: str
    key: str
    value: str
    user_id: Optional[str] = None

@app.post("/meta/doc")
def add_user_meta(payload: AddMetaPayload, x_user: Optional[str] = Header(default=None)):
    user = payload.user_id or x_user or "anon"
    with _db_lock:
        conn = get_db()
        conn.execute("insert into doc_user_meta(doc_id,key,value,user_id,status) values (?,?,?,?,?)",
                     (payload.doc_id, payload.key, payload.value, user, "pending"))
        conn.commit()
    return {"status": "queued", "moderation": "pending"}

@app.get("/admin/config")
def get_config(authorization: Optional[str] = Header(default=None)):
    admin_auth(authorization)
    rows = get_db().execute("select key, value from config").fetchall()
    return {r["key"]: r["value"] for r in rows}

class SetConfigPayload(BaseModel):
    root_kb_path: Optional[str] = None
    structure_doc: Optional[str] = None

@app.post("/admin/config")
def set_config(payload: SetConfigPayload, authorization: Optional[str] = Header(default=None)):
    admin_auth(authorization)
    with _db_lock:
        conn = get_db()
        if payload.root_kb_path is not None:
            conn.execute("insert into config(key,value) values('root_kb_path',?) on conflict(key) do update set value=excluded.value",
                         (payload.root_kb_path,))
        if payload.structure_doc is not None:
            conn.execute("insert into config(key,value) values('structure_doc',?) on conflict(key) do update set value=excluded.value",
                         (payload.structure_doc,))
        conn.commit()
    return {"status": "ok"}

class VocabItem(BaseModel):
    key: str
    label: Optional[str] = None
    type: Optional[str] = "string"
    allowed_values: Optional[List[str]] = None
    group_key: Optional[str] = None

@app.get("/admin/vocab")
def vocab_list(authorization: Optional[str] = Header(default=None)):
    admin_auth(authorization)
    rows = get_db().execute("select id,key,label,type,allowed_values,group_key from metadata_vocab order by key").fetchall()
    out = []
    for r in rows:
        av = r["allowed_values"]
        out.append({
            "id": r["id"], "key": r["key"], "label": r["label"],
            "type": r["type"], "allowed_values": [] if not av else yaml.safe_load(av),
            "group_key": r["group_key"]
        })
    return out

@app.post("/admin/vocab")
def vocab_add(item: VocabItem, authorization: Optional[str] = Header(default=None)):
    admin_auth(authorization)
    with _db_lock:
        conn = get_db()
        conn.execute(
            "insert into metadata_vocab(key,label,type,allowed_values,group_key) values (?,?,?,?,?)",
            (item.key, item.label, item.type, yaml.safe_dump(item.allowed_values) if item.allowed_values else None, item.group_key)
        )
        conn.commit()
    return {"status": "ok"}

@app.put("/admin/vocab/{key}")
def vocab_update(key: str, item: VocabItem, authorization: Optional[str] = Header(default=None)):
    admin_auth(authorization)
    with _db_lock:
        conn = get_db()
        conn.execute(
            "update metadata_vocab set label=?, type=?, allowed_values=?, group_key=? where key=?",
            (item.label, item.type, yaml.safe_dump(item.allowed_values) if item.allowed_values else None, item.group_key, key)
        )
        conn.commit()
    return {"status": "ok"}

@app.delete("/admin/vocab/{key}")
def vocab_delete(key: str, authorization: Optional[str] = Header(default=None)):
    admin_auth(authorization)
    with _db_lock:
        conn = get_db()
        conn.execute("delete from metadata_vocab where key=?", (key,))
        conn.commit()
    return {"status": "ok"}

@app.get("/admin/meta/pending")
def meta_pending(authorization: Optional[str] = Header(default=None)):
    admin_auth(authorization)
    rows = get_db().execute("select id,doc_id,key,value,user_id,created_at from doc_user_meta where status='pending' order by created_at asc").fetchall()
    return [dict(r) for r in rows]

class ModeratePayload(BaseModel):
    action: str
    key: Optional[str] = None
    value: Optional[str] = None

@app.post("/admin/meta/{meta_id}/moderate")
def meta_moderate(meta_id: int, payload: ModeratePayload, authorization: Optional[str] = Header(default=None)):
    admin_auth(authorization)
    with _db_lock:
        conn = get_db()
        if payload.action == "approve":
            conn.execute("update doc_user_meta set status='approved', updated_at=strftime('%s','now') where id=?", (meta_id,))
        elif payload.action == "reject":
            conn.execute("update doc_user_meta set status='rejected', updated_at=strftime('%s','now') where id=?", (meta_id,))
        elif payload.action == "edit":
            if payload.key is None or payload.value is None:
                raise HTTPException(status_code=400, detail="key and value required for edit")
            conn.execute("update doc_user_meta set key=?, value=?, status='approved', updated_at=strftime('%s','now') where id=?",
                         (payload.key, payload.value, meta_id))
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
        conn.commit()
    return {"status": "ok"}

# --- DOWNLOAD SICURO ---------------------------------------------------------
from fastapi import Query
from fastapi.responses import FileResponse, PlainTextResponse
import mimetypes, base64, os

ALLOWED_EXTS = {
    ".pdf",".txt",".md",".html",".htm",".doc",".docx",".ppt",".pptx",".xls",".xlsx",
    ".csv",".rtf",".odt",".ods",".png",".jpg",".jpeg",".gif",".webp",".svg"
}

def _b64url_decode(s: str) -> str:
    s = s.strip()
    padding = '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding).decode("utf-8")

@app.get("/file")
def download_file(b64: str = Query(..., description="path_rel base64url")):
    kb_root = os.environ.get("KB_ROOT") or "/mnt/kb"
    try:
        path_rel = _b64url_decode(b64)
    except Exception:
        return PlainTextResponse("Bad b64", status_code=400)

    if path_rel.startswith("/") or ".." in path_rel.replace("\\", "/"):
        return PlainTextResponse("Forbidden", status_code=403)

    abs_path = os.path.realpath(os.path.join(kb_root, path_rel))
    kb_root_real = os.path.realpath(kb_root)
    if not abs_path.startswith(kb_root_real + os.sep):
        return PlainTextResponse("Forbidden", status_code=403)

    if not os.path.isfile(abs_path):
        return PlainTextResponse("Not Found", status_code=404)

    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in ALLOWED_EXTS:
        return PlainTextResponse("Forbidden extension", status_code=403)

    ctype, _ = mimetypes.guess_type(abs_path)
    headers = {}
    if (ctype or "").lower() == "application/pdf":
        headers["Content-Disposition"] = f'inline; filename="{os.path.basename(abs_path)}"'
    else:
        headers["Content-Disposition"] = f'attachment; filename="{os.path.basename(abs_path)}"'

    return FileResponse(abs_path, media_type=ctype or "application/octet-stream", headers=headers)
