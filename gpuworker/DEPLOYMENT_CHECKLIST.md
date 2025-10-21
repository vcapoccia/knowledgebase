# 🚀 DEPLOYMENT CHECKLIST - KBSearch GPU

## 📋 STEP-BY-STEP DEPLOYMENT

### ✅ STEP 1: Verifica Prerequisiti
```bash
# Check GPU disponibile
nvidia-smi

# Check Docker ha accesso GPU
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi

# Se errore: installa nvidia-container-toolkit
# sudo apt install -y nvidia-container-toolkit
# sudo systemctl restart docker
```

---

### ✅ STEP 2: Backup Configurazione Attuale
```bash
cd /opt/kbsearch

# Backup files attuali
cp docker-compose.yml docker-compose.yml.backup
cp worker/worker_tasks.py worker/worker_tasks.py.backup
cp Dockerfile_worker Dockerfile_worker.backup
cp requirements_worker.txt requirements_worker.txt.backup
```

---

### ✅ STEP 3: Sostituisci File

#### 1. docker-compose.yml
```bash
# Scarica il nuovo docker-compose.yml da Claude
# Oppure copia da /mnt/user-data/outputs/docker-compose.yml

cp /mnt/user-data/outputs/docker-compose.yml /opt/kbsearch/docker-compose.yml
```

#### 2. Dockerfile_worker (con Tesseract)
```bash
cp /mnt/user-data/outputs/Dockerfile_worker /opt/kbsearch/Dockerfile_worker
```

#### 3. requirements_worker.txt (con PyTorch CUDA)
```bash
cp /mnt/user-data/outputs/requirements_worker.txt /opt/kbsearch/requirements_worker.txt
```

#### 4. worker_tasks.py
```bash
# IL TUO worker_tasks.py È GIÀ OK! 
# Ha già tutto il supporto GPU integrato.
# Non serve sostituirlo!

# (Opzionale) Se vuoi OCR per PDF scansionati:
# Copia funzioni da /mnt/user-data/outputs/OCR_OPTIONAL_FUNCTIONS.py
# e integrale nel worker_tasks.py
```

---

### ✅ STEP 4: Stop Servizi Attuali
```bash
cd /opt/kbsearch

docker compose down

# (Opzionale) Pulisci tutto per ripartire da zero
# docker compose down -v  # ⚠️ CANCELLA I DATI!
```

---

### ✅ STEP 5: Rebuild con GPU Support
```bash
# Rebuild tutto senza cache
docker compose build --no-cache

# Verifica che build sia andata OK
docker compose config
```

---

### ✅ STEP 6: Avvio Servizi con GPU
```bash
# Start tutti i servizi
docker compose up -d

# Aspetta che tutto sia healthy
sleep 30

# Check status
docker compose ps
```

---

### ✅ STEP 7: Verifica GPU Detection

#### Worker
```bash
# Log worker - dovresti vedere:
# 🎮 Worker GPU DETECTED: NVIDIA GeForce RTX 3080
# 🎮 CUDA Version: 12.0
# 📦 Worker batch size: 64 (GPU optimized)

docker compose logs worker | grep -i "gpu\|cuda"

# Se vedi "GPU non disponibile", c'è un problema
```

#### Ollama
```bash
# Verifica Ollama usa GPU
docker exec kbsearch-ollama nvidia-smi

# Test Ollama con modello
docker exec kbsearch-ollama ollama pull llama3
docker exec kbsearch-ollama ollama run llama3 "ciao"
```

#### API
```bash
# Verifica API è up
curl http://localhost:8000/health

# Check log API
docker compose logs api | grep -i "gpu\|cuda"
```

---

### ✅ STEP 8: Test Ingestion con GPU

#### 1. Init Collections
```bash
# Apri admin UI
http://localhost:8000/admin

# Clicca "Inizializza Indici"
# Seleziona modello: sentence-transformer
```

#### 2. Start Ingestion
```bash
# Via UI: clicca "Avvia Ingestion"
# Via API:
curl -X POST "http://localhost:8000/ingestion/start?model=sentence-transformer"
```

#### 3. Monitor Progress
```bash
# Progress real-time
watch -n 2 "curl -s http://localhost:8000/progress | jq"

# Log worker real-time
docker compose logs worker -f

# GPU usage real-time
watch -n 1 nvidia-smi
```

#### 4. Verifica Risultati
Dovresti vedere:
- ✅ GPU usage ~60-80% durante embedding
- ✅ Batch size 64 nei log
- ✅ ~0.5-1 sec per documento (vs 2-3 sec CPU)
- ✅ Worker log mostra "device cuda"

---

### ✅ STEP 9: Test Ricerca

```bash
# Test ricerca full-text
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "test query",
    "mode": "fulltext"
  }'

# Test ricerca semantica (usa GPU)
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "test query", 
    "mode": "semantic",
    "model": "sentence-transformer"
  }'
```

---

## 🐛 TROUBLESHOOTING RAPIDO

### Problema: "GPU non disponibile"
```bash
# 1. Verifica driver
nvidia-smi

# 2. Verifica Docker vede GPU
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi

# 3. Verifica docker-compose ha deploy GPU
docker compose config | grep -A 5 "deploy:"

# 4. Rebuild worker
docker compose stop worker
docker compose build --no-cache worker
docker compose up -d worker
docker compose logs worker
```

### Problema: "CUDA out of memory"
```bash
# Riduci batch size in worker_tasks.py linea 33:
# BATCH_SIZE = 32 if GPU_AVAILABLE else 16

# Oppure libera memoria:
docker compose restart worker
```

### Problema: "PyTorch not compiled with CUDA"
```bash
# Verifica versione PyTorch
docker exec kbsearch-worker-1 python -c "import torch; print(torch.__version__)"

# Dovrebbe essere: 2.1.0+cu121
# Se è 2.1.0 (senza +cu121), reinstalla:

docker exec kbsearch-worker-1 pip uninstall -y torch
docker exec kbsearch-worker-1 pip install torch==2.1.0+cu121 \
  --extra-index-url https://download.pytorch.org/whl/cu121

docker compose restart worker
```

### Problema: Worker crash o errori strani
```bash
# Log completo
docker compose logs worker --tail=100

# Rebuilld da zero
docker compose stop worker
docker compose rm -f worker
docker compose build --no-cache worker
docker compose up -d worker
```

---

## 📊 METRICHE SUCCESSO

### Con GPU (RTX 3080/4090)
- ✅ Ingestion: 0.5-1 sec/documento
- ✅ GPU usage: 60-80%
- ✅ Batch size: 64
- ✅ VRAM: ~2GB (Sentence Transformer)

### Senza GPU (Fallback CPU)
- ⚠️ Ingestion: 2-3 sec/documento
- ⚠️ CPU usage: 80-100%
- ⚠️ Batch size: 16

**Speed-up atteso: 3-5x con GPU!**

---

## ✅ CHECKLIST FINALE

- [ ] `nvidia-smi` mostra GPU
- [ ] `docker compose config` mostra `deploy:` per worker/ollama/api
- [ ] Worker log mostra "🎮 Worker GPU DETECTED"
- [ ] Worker log mostra "batch size: 64"
- [ ] Ingestion parte senza errori
- [ ] GPU usage sale durante ingestion
- [ ] Ricerca semantica funziona
- [ ] Performance ~3x più veloci che CPU

---

## 🎉 FATTO!

Se tutto OK, hai:
- ✅ Worker con GPU acceleration
- ✅ Ollama con GPU per LLM
- ✅ API con GPU per ricerca
- ✅ Tesseract per OCR (opzionale)
- ✅ Speed-up 3-5x vs CPU

Buon lavoro! 🚀
