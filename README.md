# KB Search Starter v1.1.0
Stack: Qdrant + API (FastAPI) + Ingestion + UI. Backend metadati (SQLite), facets, moderazione admin.

Quick start:
1) Monta la KB su /mnt/kb
2) Copia in /etc/kbsearch
3) systemctl daemon-reload && systemctl enable --now kbsearch
4) kbsearchctl ingest
5) http://<IP-VM>/
