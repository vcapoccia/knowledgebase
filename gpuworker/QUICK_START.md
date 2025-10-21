# 🚀 QUICK START - 3 Metodi per Deploy GPU

Scegli il tuo metodo preferito e vai!

---

## ⚡ METODO 1: Automatico Script (Consigliato)

**Tempo: 5 minuti** | **Difficoltà: 🟢 Facile**

```bash
cd /opt/kbsearch

# Crea directory
mkdir -p gpuworker

# Copia TUTTI i file scaricati da Claude in gpuworker/
cp /percorso/download/* gpuworker/

# Deploy automatico
bash gpuworker/deploy_gpu.sh
```

**Fatto!** Lo script fa tutto: backup, copy, rebuild, verify.

---

## 📋 METODO 2: Step-by-Step Manuale

**Tempo: 10 minuti** | **Difficoltà: 🟡 Medio**

```bash
cd /opt/kbsearch

# 1. Backup
cp docker-compose.yml docker-compose.yml.backup
cp Dockerfile_worker Dockerfile_worker.backup

# 2. Copia file GPU
cp gpuworker/docker-compose.yml ./
cp gpuworker/Dockerfile_worker ./
cp gpuworker/requirements_worker.txt ./

# 3. Rebuild
docker compose down
docker compose build --no-cache
docker compose up -d

# 4. Verifica GPU
sleep 30
docker compose logs worker | grep GPU
```

---

## 💨 METODO 3: One-Liner Ultra-Veloce

**Tempo: 3 minuti** | **Difficoltà: 🔴 Avanzato** | **⚠️ Nessun backup!**

```bash
cd /opt/kbsearch && \
  cp gpuworker/{docker-compose.yml,Dockerfile_worker,requirements_worker.txt} ./ && \
  docker compose down && \
  docker compose build --no-cache && \
  docker compose up -d && \
  sleep 30 && \
  docker compose logs worker | grep "GPU"
```

---

## ✅ Verifica Successo

Dopo il deploy, verifica che funzioni:

```bash
# 1. GPU rilevata?
docker compose logs worker | grep "GPU DETECTED"
# Vedi: "🎮 Worker GPU DETECTED: NVIDIA GeForce RTX..."

# 2. Servizi OK?
docker compose ps
# Tutti "Up"

# 3. API funziona?
curl http://localhost:8000/health
# {"status":"healthy"}

# 4. GPU in uso durante ingestion?
nvidia-smi
# Vedi GPU usage ~60-80% durante ingestion
```

---

## 🐛 Problema?

```bash
# Rollback veloce
bash gpuworker/rollback_gpu.sh

# Rebuild worker solo
docker compose restart worker
```

---

## 📖 Documentazione Completa

- **Guida Script**: `README_SCRIPTS.md`
- **Guida GPU**: `GPU_DEPLOYMENT_GUIDE.md`
- **Checklist**: `DEPLOYMENT_CHECKLIST.md`
- **Comandi Utili**: `ONE_LINER_COMMANDS.sh`

---

## 🎯 TL;DR

```bash
cd /opt/kbsearch
mkdir -p gpuworker
cp /download/* gpuworker/
bash gpuworker/deploy_gpu.sh
```

**Speed-up: 3-10x più veloce!** 🚀
