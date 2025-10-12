#!/usr/bin/env python3
"""
kb_diagnostics.py – health & progress checker per la KB

Controlla:
- Postgres: conteggi documents per stato, documento "stuck", ultimi falliti
- MeiliSearch: numero documenti, stato indexing, fieldDistribution, faccette
- Qdrant: presenza collezione e numero punti (vectors/points)

Config via env:
  POSTGRES_DSN           (default: postgresql://kbuser:kbpass@postgres:5432/kb)
  MEILI_URL              (default: http://meili:7700)
  MEILI_MASTER_KEY | MEILI_API_KEY (opzionali)
  MEILI_INDEX            (default: kb_docs)
  QDRANT_URL             (default: http://qdrant:6333)
  QDRANT_COLLECTION      (default: kb_chunks)

Esecuzione tipica dentro al container API:
  docker compose exec -T api python /app/kb_diagnostics.py
"""

import os
import sys
import json
import time
import datetime as dt
from typing import Optional, Dict, Any

# dipendenze (già presenti nelle tue immagini)
import requests
import psycopg
from psycopg.rows import dict_row

# ==========
# Config
# ==========
DSN = os.environ.get("POSTGRES_DSN", "postgresql://kbuser:kbpass@postgres:5432/kb")
MEILI_URL = os.environ.get("MEILI_URL", "http://meili:7700").rstrip("/")
MEILI_KEY = os.environ.get("MEILI_MASTER_KEY") or os.environ.get("MEILI_API_KEY") or ""
MEILI_IDX = os.environ.get("MEILI_INDEX", "kb_docs")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333").rstrip("/")
QDRANT_COLL = os.environ.get("QDRANT_COLLECTION", "kb_chunks")

S = requests.Session()
if MEILI_KEY:
    S.headers.update({"Authorization": f"Bearer {MEILI_KEY}"})


def h2(txt: str):
    print("\n" + "=" * 8, txt, "=" * 8)


def safe_get(url: str, **kw) -> Optional[Dict[str, Any]]:
    try:
        r = S.get(url, timeout=15, **kw)
        if r.status_code >= 400:
            print(f"[WARN] GET {url} -> {r.status_code}", file=sys.stderr)
            return None
        return r.json()
    except Exception as e:
        print(f"[WARN] GET {url} -> {e}", file=sys.stderr)
        return None


def postgres_diag():
    h2("POSTGRES")
    try:
        with psycopg.connect(DSN) as conn, conn.cursor(row_factory=dict_row) as cur:
            # Conteggio per stato
            cur.execute("SELECT status, COUNT(*) AS n FROM documents GROUP BY status ORDER BY status;")
            rows = cur.fetchall()
            total = 0
            for r in rows:
                total += r["n"]
                print(f"{r['status']:<11}: {r['n']}")
            print(f"{'total':<11}: {total}")

            # Documenti in processing potenzialmente "stuck"
            cur.execute("""
                SELECT id, path, started_at
                FROM documents
                WHERE status='processing'
                ORDER BY started_at NULLS LAST
                LIMIT 3;
            """)
            stucks = cur.fetchall()
            if stucks:
                now = dt.datetime.utcnow().replace(tzinfo=None)
                for s in stucks:
                    age = None
                    if s["started_at"]:
                        # s["started_at"] might be timezone-aware
                        try:
                            started = s["started_at"]
                            if getattr(started, "tzinfo", None) is not None:
                                started = started.astimezone(dt.timezone.utc).replace(tzinfo=None)
                            age = now - started
                        except Exception:
                            age = None
                    print(f"- processing id={s['id']} age={age} path={s['path']}")
            else:
                print("processing   : 0")

            # Ultimi 5 falliti (preview errore)
            cur.execute("""
                SELECT id, LEFT(COALESCE(last_error,''), 140) AS err, finished_at
                FROM documents
                WHERE status='failed'
                ORDER BY finished_at DESC NULLS LAST
                LIMIT 5;
            """)
            failed = cur.fetchall()
            if failed:
                print("failed last  :")
                for f in failed:
                    fa = f["finished_at"]
                    if getattr(fa, "tzinfo", None) is not None:
                        fa = fa.astimezone(dt.timezone.utc).replace(tzinfo=None)
                    print(f"  • id={f['id']} at={fa} err={f['err']}")
            else:
                print("failed last  : (none)")

            # Conta chunk se tabella esiste
            try:
                cur.execute("SELECT COUNT(*) AS chunks FROM chunks;")
                n = cur.fetchone()["chunks"]
                print(f"chunks       : {n}")
            except psycopg.errors.UndefinedTable:
                print("chunks       : (tabella 'chunks' assente)")
    except Exception as e:
        print(f"[ERROR] Postgres: {e}")


def meili_diag():
    h2("MEILISEARCH")
    idx_stats = safe_get(f"{MEILI_URL}/indexes/{MEILI_IDX}/stats")
    if not idx_stats:
        print(f"[ERROR] indice '{MEILI_IDX}' non trovato o Meili non raggiungibile.")
        # elenco indici disponibili per aiutare il debug
        all_idx = safe_get(f"{MEILI_URL}/indexes")
        if all_idx and "results" in all_idx:
            print("Indici disponibili:", ", ".join(i.get("uid", "?") for i in all_idx["results"]))
        return

    print(f"index        : {MEILI_IDX}")
    print(f"documents    : {idx_stats.get('numberOfDocuments')}")
    print(f"isIndexing   : {idx_stats.get('isIndexing')}")
    fd = idx_stats.get("fieldDistribution") or {}
    if fd:
        interesting = ["path", "preview", "chunks", "facets", "area", "tipo", "sottotipo", "year", "ext"]
        show = {k: fd.get(k) for k in interesting if k in fd}
        print("fields       :", json.dumps(show, ensure_ascii=False))

    # task in corso
    tasks = safe_get(f"{MEILI_URL}/tasks?limit=5&statuses=enqueued,processing")
    if tasks and "results" in tasks:
        print("tasks        :", len(tasks["results"]))
        for t in tasks["results"]:
            print("  •", t.get("uid"), t.get("type"), t.get("status"))
    else:
        print("tasks        : 0")

    # snapshot faccette (se configurate come filterable)
    try:
        payload = {
            "q": "",
            "limit": 0,
            "facets": ["sd", "oda_id", "oda_cliente", "as_id", "sottotipo", "area", "year", "cliente", "tipo", "ext"],
        }
        r = S.post(f"{MEILI_URL}/indexes/{MEILI_IDX}/search", json=payload, timeout=20)
        if r.ok:
            fd = r.json().get("facetDistribution") or {}
            # stampa contatori non vuoti
            non_empty = {k: v for k, v in fd.items() if isinstance(v, dict) and len(v) > 0}
            print("facets(non-empty):", ", ".join(f"{k}({len(v)})" for k, v in non_empty.items()) or "(none)")
        else:
            print(f"[WARN] search facets -> HTTP {r.status_code}")
    except Exception as e:
        print(f"[WARN] facets: {e}")


def qdrant_diag():
    h2("QDRANT")
    # Prova endpoint dettaglio della collezione
    detail = safe_get(f"{QDRANT_URL}/collections/{QDRANT_COLL}")
    listed = safe_get(f"{QDRANT_URL}/collections")
    if not listed:
        print("[ERROR] Qdrant non raggiungibile.")
        return

    have = [c.get("name") for c in listed.get("result", {}).get("collections", [])]
    print("collections  :", ", ".join(have) or "(none)")
    if QDRANT_COLL not in have:
        print(f"[WARN] collezione '{QDRANT_COLL}' non presente.")
        return

    points = None
    status = None
    if detail:
        res = detail.get("result") or {}
        # punti/vektors potrebbero non essere esposti su tutte le versioni via questo endpoint
        points = res.get("points_count")
        status = res.get("status") or res.get("state")

    # fallback: conta approssimata
    if points is None:
        cnt = safe_get(f"{QDRANT_URL}/collections/{QDRANT_COLL}/points/count")
        if cnt and "result" in cnt:
            points = cnt["result"].get("count")

    print(f"collection   : {QDRANT_COLL}")
    if status:
        print(f"status       : {status}")
    print(f"points_count : {points if points is not None else '(n/d)'}")


def main():
    print("KB Diagnostics\n"
          f"- DSN={DSN}\n"
          f"- MEILI_INDEX={MEILI_IDX} @ {MEILI_URL}\n"
          f"- QDRANT_COLLECTION={QDRANT_COLL} @ {QDRANT_URL}\n")

    postgres_diag()
    meili_diag()
    qdrant_diag()
    print("\nDone.")


if __name__ == "__main__":
    main()

