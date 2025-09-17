#!/usr/bin/env bash
set -euo pipefail

COMPOSE_DIR="/etc/kbsearch"
SERVICE_INGEST="kb-ingest"

case "${1:-}" in
  logs)
    sudo docker compose -f $COMPOSE_DIR/compose.yml logs -f $SERVICE_INGEST;;
  ps)
    sudo docker compose -f $COMPOSE_DIR/compose.yml ps;;
  *)
    echo "Uso: $0 {logs|ps}";;
esac
