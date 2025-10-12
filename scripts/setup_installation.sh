#!/usr/bin/env bash
set -euo pipefail

# Interactive helper to configure environment variables for docker compose
# and start the stack with custom parameters.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERRORE] Docker non è installato o non è nel PATH." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[ERRORE] La CLI 'docker compose' non è disponibile." >&2
  exit 1
fi

DEFAULT_APP_ROOT="${PROJECT_ROOT}"
DEFAULT_API_PORT="8000"
DEFAULT_POSTGRES_PORT="5432"
DEFAULT_MEILI_PORT="7700"
DEFAULT_QDRANT_PORT="6333"
DEFAULT_REDIS_PORT="6379"
DEFAULT_KB_HOST_DIR="/mnt/kb"
DEFAULT_KB_CONTAINER_DIR="/mnt/kb"
DEFAULT_POSTGRES_DB="kb"
DEFAULT_POSTGRES_USER="kbuser"
DEFAULT_POSTGRES_PASSWORD="kbpass"
DEFAULT_MEILI_MASTER_KEY="change_me_meili_key"

if [ -f "${ENV_FILE}" ]; then
  # shellcheck disable=SC1090
  set -a
  source "${ENV_FILE}"
  set +a
fi

prompt() {
  local question="$1"
  local default_value="$2"
  local response

  if [ -n "${default_value}" ]; then
    read -rp "${question} [${default_value}]: " response
  else
    read -rp "${question}: " response
  fi

  if [ -z "${response}" ]; then
    echo "${default_value}"
  else
    echo "${response}"
  fi
}

APP_ROOT="$(prompt "Percorso root dell'applicazione" "${APP_ROOT:-${DEFAULT_APP_ROOT}}")"
API_PORT="$(prompt "Porta esposta per il servizio API" "${API_PORT:-${DEFAULT_API_PORT}}")"
POSTGRES_PORT="$(prompt "Porta esposta per PostgreSQL" "${POSTGRES_PORT:-${DEFAULT_POSTGRES_PORT}}")"
MEILI_PORT="$(prompt "Porta esposta per Meilisearch" "${MEILI_PORT:-${DEFAULT_MEILI_PORT}}")"
QDRANT_PORT="$(prompt "Porta esposta per Qdrant" "${QDRANT_PORT:-${DEFAULT_QDRANT_PORT}}")"
REDIS_PORT="$(prompt "Porta esposta per Redis" "${REDIS_PORT:-${DEFAULT_REDIS_PORT}}")"
KB_HOST_DIR="$(prompt "Cartella locale contenente i file della knowledge base" "${KB_HOST_DIR:-${DEFAULT_KB_HOST_DIR}}")"
KB_CONTAINER_DIR="$(prompt "Percorso di montaggio all'interno dei container" "${KB_CONTAINER_DIR:-${DEFAULT_KB_CONTAINER_DIR}}")"
POSTGRES_DB="$(prompt "Nome del database PostgreSQL" "${POSTGRES_DB:-${DEFAULT_POSTGRES_DB}}")"
POSTGRES_USER="$(prompt "Utente PostgreSQL" "${POSTGRES_USER:-${DEFAULT_POSTGRES_USER}}")"
POSTGRES_PASSWORD="$(prompt "Password PostgreSQL" "${POSTGRES_PASSWORD:-${DEFAULT_POSTGRES_PASSWORD}}")"
MEILI_MASTER_KEY="$(prompt "Chiave master di Meilisearch" "${MEILI_MASTER_KEY:-${DEFAULT_MEILI_MASTER_KEY}}")"

mkdir -p "${KB_HOST_DIR}"

{
  echo "# Configurazione generata da scripts/setup_installation.sh"
  printf 'APP_ROOT=%q\n' "${APP_ROOT}"
  printf 'API_PORT=%q\n' "${API_PORT}"
  printf 'POSTGRES_PORT=%q\n' "${POSTGRES_PORT}"
  printf 'MEILI_PORT=%q\n' "${MEILI_PORT}"
  printf 'QDRANT_PORT=%q\n' "${QDRANT_PORT}"
  printf 'REDIS_PORT=%q\n' "${REDIS_PORT}"
  printf 'KB_HOST_DIR=%q\n' "${KB_HOST_DIR}"
  printf 'KB_CONTAINER_DIR=%q\n' "${KB_CONTAINER_DIR}"
  printf 'POSTGRES_DB=%q\n' "${POSTGRES_DB}"
  printf 'POSTGRES_USER=%q\n' "${POSTGRES_USER}"
  printf 'POSTGRES_PASSWORD=%q\n' "${POSTGRES_PASSWORD}"
  printf 'MEILI_MASTER_KEY=%q\n' "${MEILI_MASTER_KEY}"
} >"${ENV_FILE}"

cat <<EOF_SUMMARY

Configurazione salvata in ${ENV_FILE}:
  - APP_ROOT = ${APP_ROOT}
  - API_PORT = ${API_PORT}
  - POSTGRES_PORT = ${POSTGRES_PORT}
  - MEILI_PORT = ${MEILI_PORT}
  - QDRANT_PORT = ${QDRANT_PORT}
  - REDIS_PORT = ${REDIS_PORT}
  - KB_HOST_DIR = ${KB_HOST_DIR}
  - KB_CONTAINER_DIR = ${KB_CONTAINER_DIR}
  - POSTGRES_DB = ${POSTGRES_DB}
  - POSTGRES_USER = ${POSTGRES_USER}
  - MEILI_MASTER_KEY = ${MEILI_MASTER_KEY}
EOF_SUMMARY

read -rp $'Vuoi avviare ora lo stack con "docker compose up -d"? [Y/n]: ' START_STACK
START_STACK=${START_STACK:-Y}
if [[ "${START_STACK}" =~ ^[Yy]$ ]]; then
  if [ ! -d "${APP_ROOT}" ]; then
    echo "[ERRORE] La directory ${APP_ROOT} non esiste." >&2
    exit 1
  fi
  echo "Avvio dei servizi Docker Compose..."
  (cd "${APP_ROOT}" && docker compose up -d)
  echo "Stack avviato."
else
  echo "Puoi avviare manualmente i servizi con:"
  echo "  (cd \"${APP_ROOT}\" && docker compose up -d)"
fi
