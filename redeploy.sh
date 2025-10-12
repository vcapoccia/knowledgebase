#!/usr/bin/env bash
# scripts/redeploy.sh
# Riavvia l'ambiente docker del progetto con cleanup di cache/orfani.
# Opzioni:
#   --rebuild        : ricostruisce le immagini (docker compose build)
#   --no-cache       : build senza cache
#   --deep           : pulizia profonda (include volumi **non usati**)
#   --services "a b" : limita up/build ai servizi indicati (es. "api worker")
#   --no-up          : non fare 'up -d' alla fine (solo cleanup)
#   --prune-builders : esegue anche 'docker builder prune'
#   --keep-images    : NON rimuove immagini dangling/unreferenced
#   --keep-containers: NON rimuove container fermati
#   --keep-networks  : NON rimuove reti non usate

set -euo pipefail

# ---- Config base ----
PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"

# ---- Parse args ----
REBUILD=false
NO_CACHE=false
DO_UP=true
DEEP=false
PRUNE_BUILDERS=false
SERVICES=()
KEEP_IMAGES=false
KEEP_CONTAINERS=false
KEEP_NETWORKS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rebuild) REBUILD=true; shift ;;
    --no-cache) NO_CACHE=true; shift ;;
    --deep) DEEP=true; shift ;;
    --prune-builders) PRUNE_BUILDERS=true; shift ;;
    --services) shift; IFS=' ' read -r -a SERVICES <<< "${1:-}"; shift || true ;;
    --no-up) DO_UP=false; shift ;;
    --keep-images) KEEP_IMAGES=true; shift ;;
    --keep-containers) KEEP_CONTAINERS=true; shift ;;
    --keep-networks) KEEP_NETWORKS=true; shift ;;
    -h|--help)
      cat <<EOF
Uso: $(basename "$0") [opzioni]
  --rebuild         Ricostruisce le immagini
  --no-cache        Build senza cache
  --deep            Pulizia profonda (include volumi non usati)
  --prune-builders  Pulisce anche cache dei builder
  --services "a b"  Limita a specifici servizi (es: "api worker")
  --no-up           Non esegue 'up -d' finale
  --keep-images     NON rimuove immagini inutilizzate
  --keep-containers NON rimuove container fermati
  --keep-networks   NON rimuove reti non usate
EOF
      exit 0
      ;;
    *) echo "Argomento sconosciuto: $1"; exit 1 ;;
  esac
done

cd "$PROJECT_DIR"

echo "==> Progetto: $PROJECT_DIR"
echo "==> Commander: $COMPOSE_CMD"
echo "==> Opzioni: rebuild=$REBUILD no_cache=$NO_CACHE deep=$DEEP up=$DO_UP services=${SERVICES[*]:-<tutti>}"

# ---- Sanity checks ----
if ! command -v docker &>/dev/null; then
  echo "ERRORE: docker non trovato nel PATH"; exit 1
fi
if ! $COMPOSE_CMD version &>/dev/null; then
  echo "ERRORE: 'docker compose' non disponibile."; exit 1
fi
if [[ ! -f docker-compose.yml && ! -f compose.yml ]]; then
  echo "ERRORE: file docker-compose.yml/compose.yml non trovato in $PROJECT_DIR"; exit 1
fi

# ---- Mostra uso disco prima ----
echo "==> Spazio Docker prima della pulizia:"
docker system df || true
echo

# ---- Giù tutto ----
echo "==> Stop & down (keeping volumes di dati)..."
$COMPOSE_CMD down --remove-orphans || true
echo

# ---- Prune mirato ----
echo "==> Pulizia risorse inutilizzate..."
$KEEP_CONTAINERS || docker container prune -f || true
$KEEP_NETWORKS   || docker network prune -f || true
$KEEP_IMAGES     || docker image prune -af || true

# Builder cache (opzionale)
if $PRUNE_BUILDERS; then
  echo "==> Pulizia cache builder..."
  docker builder prune -af || true
fi

# Deep prune (ATTENZIONE: rimuove volumi NON usati da nessun container)
if $DEEP; then
  echo "==> Deep prune: volumi non usati (N.B.: NON tocca i volumi in uso) ..."
  docker volume prune -f || true
fi
echo

# ---- (Ri)build immagini se richiesto ----
if $REBUILD; then
  echo "==> Build immagini..."
  BUILD_ARGS=()
  $NO_CACHE && BUILD_ARGS+=(--no-cache)
  if ((${#SERVICES[@]})); then
    $COMPOSE_CMD build "${BUILD_ARGS[@]}" "${SERVICES[@]}"
  else
    $COMPOSE_CMD build "${BUILD_ARGS[@]}"
  fi
  echo
fi

# ---- Up ----
if $DO_UP; then
  echo "==> Up -d ..."
  if ((${#SERVICES[@]})); then
    $COMPOSE_CMD up -d "${SERVICES[@]}"
  else
    $COMPOSE_CMD up -d
  fi
  echo
fi

# ---- Mostra stato & spazio dopo ----
echo "==> Stato servizi:"
$COMPOSE_CMD ps
echo

echo "==> Spazio Docker dopo la pulizia:"
docker system df || true
echo

echo "✔ Fatto."

