#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# QUICK FIX - Problemi comuni post-reboot
# ═══════════════════════════════════════════════════════════════

cat << 'EOF'
╔════════════════════════════════════════════════════════════════╗
║           QUICK FIX - Backend Errore 500 Post-Reboot          ║
╚════════════════════════════════════════════════════════════════╝

❌ SINTOMO: Errore HTTP 500 su qualsiasi ricerca dopo reboot macchina

🔍 CAUSE COMUNI POST-REBOOT:
  1. Container Docker non riavviati automaticamente
  2. PostgreSQL non pronto prima del backend
  3. Ollama/LLM non avviato
  4. Problemi di network Docker
  5. Volume mounts non disponibili


═══════════════════════════════════════════════════════════════
FIX #1: RESTART COMPLETO (PROVA PRIMA QUESTO)
═══════════════════════════════════════════════════════════════

cd /opt/kbsearch  # o dove hai il docker-compose.yml

# Stop tutto
docker-compose down

# Aspetta 5 secondi
sleep 5

# Start tutto in ordine corretto
docker-compose up -d

# Aspetta che PostgreSQL sia pronto (30 sec)
sleep 30

# Verifica
docker-compose ps

# Test API
curl http://localhost:8080/search?q_text=test

# Se risponde con JSON → ✅ RISOLTO!
# Se risponde con 500 → vai a FIX #2


═══════════════════════════════════════════════════════════════
FIX #2: RESTART CON REBUILD (se FIX #1 non funziona)
═══════════════════════════════════════════════════════════════

cd /opt/kbsearch

# Down completo
docker-compose down

# Remove container (mantiene dati)
docker-compose rm -f

# Rebuild e restart
docker-compose up -d --build

# Aspetta startup
sleep 30

# Check logs
docker-compose logs --tail=50 kbsearch


═══════════════════════════════════════════════════════════════
FIX #3: VERIFICA POSTGRESQL
═══════════════════════════════════════════════════════════════

# PostgreSQL deve essere pronto PRIMA del backend

# Check se Postgres è pronto
docker exec kbsearch-postgres-1 pg_isready -U kbuser

# Se dice "accepting connections" → OK
# Se errore → restart Postgres

docker-compose restart kbsearch-postgres

# Aspetta 10 secondi
sleep 10

# Poi restart backend
docker-compose restart kbsearch


═══════════════════════════════════════════════════════════════
FIX #4: CHECK OLLAMA (se usi LLaMA/Mistral)
═══════════════════════════════════════════════════════════════

# Verifica se Ollama risponde
curl http://localhost:11434/api/tags

# Se non risponde:
systemctl restart ollama
# OPPURE
docker restart ollama  # se Ollama è in container

# Aspetta 10 secondi
sleep 10

# Poi restart backend
docker-compose restart kbsearch


═══════════════════════════════════════════════════════════════
FIX #5: LOGS DETTAGLIATI
═══════════════════════════════════════════════════════════════

# Vedi cosa sta crashando
docker-compose logs -f kbsearch

# Cerca questi errori:
#   "connection refused" → Postgres non pronto
#   "no module named" → dependency mancante
#   "permission denied" → problema volumi
#   "OOM" / "killed" → out of memory


═══════════════════════════════════════════════════════════════
FIX #6: VERIFICA MEMORIA
═══════════════════════════════════════════════════════════════

# Check memoria disponibile
free -h

# Check memoria container
docker stats --no-stream

# Se memoria bassa (<1GB libera):
#   1. Riavvia macchina
#   2. Aumenta swap
#   3. Riduci altri servizi


═══════════════════════════════════════════════════════════════
FIX #7: NETWORK RESET
═══════════════════════════════════════════════════════════════

cd /opt/kbsearch

# Down completo
docker-compose down

# Remove network
docker network rm kbsearch_default 2>/dev/null

# Recreate tutto
docker-compose up -d


═══════════════════════════════════════════════════════════════
FIX #8: AUTO-START AL BOOT (prevenire in futuro)
═══════════════════════════════════════════════════════════════

# Opzione A: Docker restart policy
# Modifica docker-compose.yml, aggiungi a ogni servizio:
    restart: unless-stopped

# Opzione B: Systemd service
# Crea /etc/systemd/system/kbsearch.service:

[Unit]
Description=KB Search
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/kbsearch
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target

# Enable:
systemctl enable kbsearch
systemctl start kbsearch


═══════════════════════════════════════════════════════════════
CHECKLIST VELOCE
═══════════════════════════════════════════════════════════════

[ ] Docker service running?
    systemctl status docker

[ ] Container up?
    docker-compose ps

[ ] Postgres accepting connections?
    docker exec kbsearch-postgres-1 pg_isready -U kbuser

[ ] Backend logs senza errori?
    docker-compose logs --tail=20 kbsearch

[ ] API risponde?
    curl http://localhost:8080/search?q_text=test

[ ] Frontend carica?
    curl http://localhost


═══════════════════════════════════════════════════════════════
COMANDO DIAGNOSTICA COMPLETA
═══════════════════════════════════════════════════════════════

# Esegui lo script diagnostico che ho creato:
bash /mnt/user-data/outputs/diagnostica_backend.sh

# Ti dirà esattamente qual è il problema!


═══════════════════════════════════════════════════════════════
ERRORI COMUNI E SOLUZIONI
═══════════════════════════════════════════════════════════════

ERRORE: "connection refused postgres"
FIX: docker-compose restart kbsearch-postgres && sleep 10 && docker-compose restart kbsearch

ERRORE: "no such container"
FIX: docker-compose up -d

ERRORE: "port already in use"
FIX: lsof -i :8080  # trova processo
     kill <PID>
     docker-compose up -d

ERRORE: "permission denied" su volumi
FIX: sudo chown -R 999:999 /opt/kbsearch/postgres_data

ERRORE: OOM / Out of memory
FIX: docker-compose down
     free -h  # check memoria
     docker-compose up -d


═══════════════════════════════════════════════════════════════
PRIORITY ORDER FIX
═══════════════════════════════════════════════════════════════

Prova in questo ordine:

1. FIX #1: docker-compose down && docker-compose up -d
   ↓ 80% dei casi si risolve qui

2. Se ancora 500 → FIX #3: Check Postgres
   ↓ 15% dei casi

3. Se ancora 500 → FIX #5: Leggi logs dettagliati
   ↓ Identifica problema specifico

4. Se ancora 500 → Manda logs e facciamo debug insieme


═══════════════════════════════════════════════════════════════
EOF
