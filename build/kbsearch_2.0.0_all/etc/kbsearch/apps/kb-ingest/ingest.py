#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import re
import sys
import json
import uuid
import sqlite3
import subprocess
from pathlib import Path
from typing import List, Dict, Iterable, Tuple

import torch
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# --- Estrazione testo ---
try:
    import docx  # python-docx
except Exception:
    docx = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None


# =========================
# Config da variabili env
# =========================
KB_ROOT = os.getenv("KB_ROOT", "/mnt/kb")
KB_GARE_DIR = os.getenv("KB_GARE_DIR", "") or None
KB_AQ_DIR = os.getenv("KB_AQ_DIR", "") or None

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "120"))
INGEST_BATCH = int(os.getenv("INGEST_BATCH", "128"))
INGEST_LOG_LEVEL = os.getenv("INGEST_LOG_LEVEL", "info")

EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-m3")

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "kb_chunks")

# escludi alcune sezioni dall’indicizzazione (es. "documentazione,accesso_atti")
EXCLUDE_SEZIONI = {s.strip().lower() for s in os.getenv("EXCLUDE_SEZIONI", "").split(",") if s.strip()}

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SQLITE_PATH = DATA_DIR / "ingest.db"

# device
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


# ===== Logging minimale =====
def log(msg: str, level: str = "info"):
    levels = ["debug", "info", "warn", "error"]
    if levels.index(level) >= levels.index(INGEST_LOG_LEVEL):
        print(f"[{level.upper()}] {msg}", flush=True)


# ===== Util =====
def have_cmd(name: str) -> bool:
    from shutil import which
    return which(name) is not None


def run_pdftotext(pdf_path: str) -> str:
    try:
        out = subprocess.run(
            ["pdftotext", "-q", "-layout", pdf_path, "-"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
        )
        return out.stdout.decode("utf-8", errors="ignore")
    except Exception as e:
        log(f"pdftotext fallito su {pdf_path}: {e}", "warn")
        return ""


def extract_text(path: str) -> str:
    p = Path(path)
    ext = p.suffix.lower()
    try:
        if ext == ".pdf":
            if have_cmd("pdftotext"):
                return run_pdftotext(str(p))
            else:
                log("pdftotext non trovato; installa poppler-utils nel container.", "warn")
                return ""
        elif ext == ".docx":
            if not docx:
                log("python-docx non installato", "warn")
                return ""
            d = docx.Document(str(p))
            return "\n".join([para.text for para in d.paragraphs])
        elif ext in (".txt", ".md"):
            return p.read_text(encoding="utf-8", errors="ignore")
        elif ext in (".html", ".htm"):
            if not BeautifulSoup:
                return p.read_text(encoding="utf-8", errors="ignore")
            html = p.read_text(encoding="utf-8", errors="ignore")
            return BeautifulSoup(html, "lxml").get_text(" ", strip=True)
        else:
            return ""  # ignora altri tipi
    except Exception as e:
        log(f"estrazione fallita {p}: {e}", "warn")
        return ""


def sliding_chunks(text: str, size: int, overlap: int) -> Iterable[str]:
    text = text.strip()
    if not text:
        return []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + size)
        yield text[start:end]
        if end == n:
            break
        start = end - overlap


# ====== Metadati robusti dal path ======
def path_meta(root: str, f: str) -> Dict:
    p = Path(f)
    # relativo rispetto a KB_ROOT per costruire l'URL
    if str(p).startswith(KB_ROOT.rstrip("/") + "/"):
        rel = str(p)[len(KB_ROOT.rstrip("/")) + 1 :]
    else:
        # fallback
        rel = str(p.relative_to("/")) if p.is_absolute() else str(p)

    parts = rel.split("/")
    meta = {
        "path_rel": rel,
        "file_name": p.name,
        "ext": (p.suffix[1:].lower() if p.suffix else ""),
        "kb_area": None,      # aq|gare
        "livello": None,      # gara|aq|oda|as
        "sd": None,
        "sezione": None,
        "anno": None,
        "cliente": None,
        "ambito": None,
        "oda_code": None,
        "as_code": None,
        "as_rdo": None,
    }

    def norm_sezione(seg: str) -> str:
        s = seg.lower()
        if s.startswith("01_documentazione"): return "documentazione"
        if s.startswith("02_chiarimenti"):     return "chiarimenti"
        if s.startswith("04_offertatecnica"):  return "offerta"
        if s.startswith("08_accessoagliatti"): return "accesso_atti"
        if s.startswith("09_oda"):             return "oda"
        return "unknown"

    if len(parts) >= 1:
        top = parts[0]
        if top == "_Gare":
            meta["kb_area"] = "gare"
            meta["livello"] = "gara"
            if len(parts) >= 2:
                gara_dir = parts[1]
                m = re.match(r"^(20\d{2})_(.+?)\-([A-Za-z0-9]+)$", gara_dir)
                if m:
                    meta["anno"], meta["cliente"], meta["ambito"] = m.group(1), m.group(2), m.group(3)
                if len(parts) >= 3:
                    meta["sezione"] = norm_sezione(parts[2])

        elif top == "_AQ":
            meta["kb_area"] = "aq"
            if len(parts) >= 2 and re.match(r"^SD\d+$", parts[1]):
                meta["sd"] = parts[1]
                meta["livello"] = "aq"
                # ODA
                if len(parts) >= 3 and parts[2].lower().startswith("09_oda"):
                    meta["livello"] = "oda"
                    if len(parts) >= 4:
                        m = re.match(r"^(ODA\d+)_([^/]+)$", parts[3])
                        if m:
                            meta["oda_code"], meta["cliente"] = m.group(1), m.group(2)
                    if len(parts) >= 5:
                        meta["sezione"] = norm_sezione(parts[4])
                # AS
                if len(parts) >= 3 and parts[2].lower().startswith("99_as"):
                    meta["livello"] = "as"
                    if len(parts) >= 4:
                        as_folder = parts[3]
                        m = re.match(r"^(AS\d+)_([0-9]+)_RDO_(.+)$", as_folder)
                        if m:
                            meta["as_code"], meta["as_rdo"], meta["cliente"] = m.group(1), m.group(2), m.group(3)
                        else:
                            m2 = re.match(r"^(AS\d+)_.*?_(.+)$", as_folder)
                            if m2:
                                meta["as_code"], meta["cliente"] = m2.group(1), m2.group(2)
                    if len(parts) >= 5:
                        meta["sezione"] = norm_sezione(parts[4])

    # generici
    if not meta["anno"]:
        m = re.search(r"\b(20\d{2})\b", rel)
        if m:
            meta["anno"] = m.group(1)
    if not meta["ambito"] and meta["kb_area"] == "gare" and len(parts) > 1:
        m = re.search(r"-(\w+)$", parts[1])
        if m:
            meta["ambito"] = m.group(1)
    if not meta["sezione"] and len(parts) >= 2:
        meta["sezione"] = norm_sezione(parts[-2])

    # titolo parlante
    stem = p.stem
    title = None
    if meta.get("cliente") and meta.get("ambito") and meta.get("anno"):
        title = f"{meta['cliente']} - {meta['ambito']} ({meta['anno']})"
    if not title:
        title = stem.replace("_", " ").replace("-", " ").strip() or "(senza titolo)"
    meta["title"] = title

    # breadcrumb + url per UI
    bc = []
    if meta["kb_area"]: bc.append(meta["kb_area"])
    if meta["sd"]: bc.append(meta["sd"])
    if meta["livello"] and meta["livello"] not in ("aq",): bc.append(meta["livello"])
    if meta["sezione"]: bc.append(meta["sezione"])
    meta["breadcrumb"] = " / ".join(bc)

    meta["url"] = "/files/" + rel
    return meta


# ====== DB incrementale (mtime) ======
def db_init():
    con = sqlite3.connect(SQLITE_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            path_rel TEXT PRIMARY KEY,
            mtime INTEGER NOT NULL,
            doc_uuid TEXT NOT NULL
        )
    """)
    con.commit()
    return con


def db_get(con, path_rel: str) -> Tuple[int, str] | None:
    cur = con.cursor()
    cur.execute("SELECT mtime, doc_uuid FROM files WHERE path_rel=?", (path_rel,))
    row = cur.fetchone()
    return (row[0], row[1]) if row else None


def db_upsert(con, path_rel: str, mtime: int, doc_uuid: str):
    cur = con.cursor()
    cur.execute("INSERT OR REPLACE INTO files(path_rel, mtime, doc_uuid) VALUES(?,?,?)",
                (path_rel, mtime, doc_uuid))
    con.commit()


# ====== Qdrant ======
def ensure_collection(client: QdrantClient, size: int = 1024):
    try:
        if not client.collection_exists(QDRANT_COLLECTION):
            log(f"Creo collection '{QDRANT_COLLECTION}' (dim={size})", "info")
            client.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=size, distance=Distance.COSINE),
                on_disk_payload=True
            )
        else:
            log(f"Collection '{QDRANT_COLLECTION}' pronta", "info")
    except Exception as e:
        log(f"Errore ensure_collection: {e}", "error")
        raise


# ====== Walk dei file ======
ALLOW_EXT = {".pdf", ".docx", ".txt", ".md", ".html", ".htm"}

def iter_files() -> Iterable[str]:
    roots = []
    if KB_GARE_DIR:
        roots.append(Path(KB_GARE_DIR))
    if KB_AQ_DIR:
        roots.append(Path(KB_AQ_DIR))
    if not roots:
        roots = [Path(KB_ROOT)]

    for r in roots:
        if not r.exists():
            continue
        for p in r.rglob("*"):
            if p.is_file() and p.suffix.lower() in ALLOW_EXT:
                yield str(p)


# ====== Main ======
def main():
    print(json.dumps({
        "KB_ROOT": KB_ROOT,
        "DEVICE": DEVICE,
        "MODEL": EMBED_MODEL,
        "BATCH": INGEST_BATCH,
        "CHUNK": f"{CHUNK_SIZE}/{CHUNK_OVERLAP}",
        "EXCLUDE_SEZIONI": sorted(list(EXCLUDE_SEZIONI)),
    }, indent=2))

    embedder = SentenceTransformer(EMBED_MODEL, device=DEVICE)

    client = QdrantClient(url=QDRANT_URL)
    ensure_collection(client, size=1024)

    con = db_init()

    points: List[PointStruct] = []
    batch_cnt = 0

    def flush():
        nonlocal points, batch_cnt
        if not points:
            return
        try:
            client.upsert(
                collection_name=QDRANT_COLLECTION,
                points=points
            )
            log(f"Upsert {len(points)} punti", "info")
            points = []
            batch_cnt += 1
        except Exception as e:
            log(f"Upsert fallito: {e}", "error")
            points = []

    for f in iter_files():
        raw = extract_text(f)
        if not raw.strip():
            log(f"Testo vuoto: {f}", "warn")
            # aggiorno comunque mtime per evitare ripetizioni inutili
            meta = path_meta(KB_ROOT, f)
            st = Path(f).stat()
            doc_uuid = str(uuid.uuid4())
            db_upsert(con, meta["path_rel"], int(st.st_mtime), doc_uuid)
            continue

        meta = path_meta(KB_ROOT, f)

        # filtro sezioni escluse
        if meta.get("sezione", "").lower() in EXCLUDE_SEZIONI:
            log(f"Escludo per sezione: {meta['sezione']} -> {meta['path_rel']}", "debug")
            continue

        st = Path(f).stat()
        rec = db_get(con, meta["path_rel"])
        if rec and rec[0] == int(st.st_mtime):
            # già indicizzato e non cambiato
            continue
        # nuovo doc_uuid a ogni mtime differente
        doc_uuid = str(uuid.uuid4())

        # chunking
        chs = list(sliding_chunks(raw, CHUNK_SIZE, CHUNK_OVERLAP))
        if not chs:
            continue

        # embed in mini-batch per non esplodere la memoria
        start = 0
        while start < len(chs):
            sub = chs[start : start + INGEST_BATCH]
            vecs = embedder.encode(sub, normalize_embeddings=True, convert_to_numpy=True)
            for i, (text, vec) in enumerate(zip(sub, vecs)):
                # id UUID v4 (stringa con trattini)
                pid = str(uuid.uuid4())
                payload = dict(meta)
                payload.update({
                    "doc_uuid": doc_uuid,
                    "chunk_idx": start + i,
                    "text": text,
                    "updated_at": int(st.st_mtime)
                })
                points.append(PointStruct(
                    id=pid,
                    vector=vec.tolist(),
                    payload=payload
                ))
                if len(points) >= INGEST_BATCH:
                    flush()
            start += INGEST_BATCH

        # salva stato incrementale
        db_upsert(con, meta["path_rel"], int(st.st_mtime), doc_uuid)

    flush()
    log("Ingestion completata.", "info")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)

