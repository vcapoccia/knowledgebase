# Knowledge Base — Guida Operativa

Ultimo aggiornamento: 2025-09-17T09:18:50Z

## 1) Architettura (overview)
- **Caddy**: reverse proxy e static file server (`/` ⇒ UI, `/api` ⇒ API, `/files` ⇒ documenti KB in sola lettura).
- **KB UI (nginx)**: interfaccia web statica (HTML+JS).
- **KB API (FastAPI)**: ricerca, facets, download URL building.
- **Qdrant**: vettori e payload indicizzati.
- **KB Ingest**: parser + embedding GPU-ready, ingest incrementale.

## 2) Requisiti
- Debian/Ubuntu con **Docker** e **Docker Compose** installati.
- Cartella dei documenti KB montata in host, es: `/mnt/kb/_Gare`, `/mnt/kb/_AQ`.
- DNS/hosts: opzionale `kb.local` → IP della VM.

## 3) Layout cartelle
```
/etc/kbsearch/
  compose.yml
  .env
  caddy/
    Caddyfile
  apps/
    kb-ui/
      index.html
      assets/ (se usati)
    kb-api/
      Dockerfile, main.py, requirements.txt, config.yaml
    kb-ingest/
      Dockerfile, ingest.py, requirements.txt
  run/           (socket/lock)
/mnt/kb/         (documenti reali, bind mount read-only in Caddy)
```

## 4) Variabili importanti (.env)
```
PUBLIC_BASE_URL=http://kb.local
KB_ROOT=/mnt/kb
KB_GARE_DIR=/mnt/kb/_Gare
KB_AQ_DIR=/mnt/kb/_AQ
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=kb_chunks
```

## 5) Avvio (senza interrompere ingest)
```bash
cd /etc/kbsearch
docker compose up -d qdrant kb-api kb-ui caddy    # servizi principali
# ingest one-shot:
docker compose run --rm kb-ingest
```

## 6) Health check rapidi
```bash
curl -s http://127.0.0.1/api/health
curl -s http://127.0.0.1:6333/collections
curl -sI http://127.0.0.1/             # UI via Caddy
curl -sI http://127.0.0.1/files/       # static files via Caddy
```

## 7) UI — uso
- Barra superiore: campo ricerca + tasto “Escludi Documentazione”.
- Colonna sinistra: **faccette** (clic per filtrare, clic di nuovo per rimuovere).
- Risultati: titolo, score, badge metadati, pulsante **Apri** → `/files/<path_rel>`.

## 8) Manutenzione
- **Pulizia spazio**:
  ```bash
  docker system prune -af
  docker volume prune -f
  docker builder prune -af
  docker image prune -af
  ```
- **Backup**: salvare `/etc/kbsearch` e il volume `qdrant_storage`.
- **Aggiornamento**: rebuild dei servizi `kb-api`/`kb-ingest` se cambiano dipendenze.

## 9) Troubleshooting
- **404 su `/` ma `/api/health` ok** → problema Host header / Caddyfile. Provare con IP diretto o correggere Caddyfile.
- **Download non parte** → verificare mount `/mnt/kb` in Caddy e route `/files/*` con `file_server`.
- **Facets vuote** → controllare risposta `/api/facets` e che la UI costruisca `filters[]` correttamente.
- **Ingest lento** → GPU attiva? `torch.cuda.is_available()` dentro `kb-ingest`.
- **Qdrant Unhealthy** → rimuovere healthcheck rigido o aumentare timeout, verificare porta 6333.

## 10) Stop / Restart
```bash
docker compose stop
docker compose start
docker compose down   # ferma e rimuove (mantenendo volumi)
```
