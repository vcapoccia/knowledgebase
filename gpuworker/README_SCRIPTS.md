# 🚀 KBSearch GPU Deployment - Guida Completa

Questa cartella contiene tutto il necessario per abilitare il supporto GPU su kbsearch.

## 📦 Contenuto

```
gpuworker/
├── docker-compose.yml          # Config con GPU support
├── Dockerfile_worker           # Worker con Tesseract OCR
├── requirements_worker.txt     # Dipendenze con PyTorch CUDA
├── deploy_gpu.sh              # Script deployment automatico ⭐
├── setup_gpuworker.sh         # Script preparazione directory
├── rollback_gpu.sh            # Script rollback configurazione
├── GPU_DEPLOYMENT_GUIDE.md    # Guida dettagliata
├── DEPLOYMENT_CHECKLIST.md    # Checklist step-by-step
└── OCR_OPTIONAL_FUNCTIONS.py  # Funzioni OCR (opzionali)
```

---

## 🎯 Quick Start (3 passi)

### **STEP 1: Prepara la directory gpuworker**

```bash
cd /opt/kbsearch

# Opzione A: Scarica i file da Claude e copiaci manualmente
mkdir -p gpuworker
cp /percorso/download/* gpuworker/

# Opzione B: Usa lo script setup (se file in /mnt/user-data/outputs)
bash setup_gpuworker.sh
```

### **STEP 2: Esegui deployment GPU**

```bash
cd /opt/kbsearch
bash gpuworker/deploy_gpu.sh
```

Lo script fa **TUTTO automaticamente**:
- ✅ Verifica prerequisiti (GPU, Docker, nvidia-smi)
- ✅ Backup configurazione attuale
- ✅ Copia nuovi file con supporto GPU
- ✅ Rebuild containers
- ✅ Restart servizi
- ✅ Verifica GPU detection
- ✅ Test health endpoints

### **STEP 3: Verifica GPU attiva**

```bash
# Verifica log worker
docker compose logs worker | grep GPU

# Dovresti vedere:
# 🎮 Worker GPU DETECTED: NVIDIA GeForce RTX 3080
# 📦 Worker batch size: 64 (GPU optimized)

# Monitora GPU durante ingestion
watch -n 1 nvidia-smi
```

---

## 📋 Prerequisiti

Prima di eseguire lo script, verifica:

### 1. **GPU NVIDIA con driver**
```bash
nvidia-smi
# Deve mostrare la tua GPU
```

### 2. **nvidia-container-toolkit**
```bash
# Se non installato:
sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker

# Test Docker + GPU:
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
```

### 3. **Docker Compose**
```bash
docker compose version
# Deve essere v2.x
```

---

## 🔧 Dettaglio Script

### **deploy_gpu.sh** ⭐ (PRINCIPALE)

Script completo che automatizza tutto il deployment.

**Cosa fa:**
1. ✅ Verifica prerequisiti (GPU, Docker, file necessari)
2. ✅ Crea backup automatico in `backup_YYYYMMDD_HHMMSS/`
3. ✅ Stop servizi attuali
4. ✅ Copia configurazione GPU da `gpuworker/`
5. ✅ Rebuild worker, API, Ollama con GPU support
6. ✅ Restart tutti i servizi
7. ✅ Verifica GPU detection
8. ✅ Test health endpoints
9. ✅ Mostra comandi utili e prossimi passi

**Usage:**
```bash
cd /opt/kbsearch
bash gpuworker/deploy_gpu.sh
```

**Output atteso:**
```
============================================================================
✅ DEPLOYMENT COMPLETATO!
============================================================================

📊 INFORMAZIONI:
  • GPU: NVIDIA GeForce RTX 3080
  • Admin UI: http://localhost:8000/admin
  • Backup: /opt/kbsearch/backup_20250115_143022

🎉 GPU ACCELERAZIONE ATTIVA! Speed-up atteso: 3-5x
```

---

### **setup_gpuworker.sh**

Script helper per preparare la directory `gpuworker/` con i file necessari.

**Cosa fa:**
1. Crea directory `gpuworker/` se non esiste
2. Copia file da `/mnt/user-data/outputs` (se disponibili)
3. Rende eseguibile `deploy_gpu.sh`
4. Verifica che tutti i file siano presenti

**Usage:**
```bash
cd /opt/kbsearch
bash setup_gpuworker.sh
```

---

### **rollback_gpu.sh**

Script di emergenza per tornare alla configurazione precedente.

**Cosa fa:**
1. Trova backup più recente in `backup_*/`
2. Stop servizi
3. Ripristina file originali
4. Rebuild containers
5. Restart servizi
6. Verifica funzionamento

**Usage:**
```bash
cd /opt/kbsearch
bash gpuworker/rollback_gpu.sh
```

**Quando usarlo:**
- ❌ GPU non rilevata e vuoi tornare indietro
- ❌ Problemi con il worker dopo deployment
- ❌ Performance peggiorate
- ❌ Errori strani nei log

---

## 🎮 Performance Attese

### **Con GPU (RTX 3080/4090)**

| Modello | Tempo/doc | Batch Size | VRAM |
|---------|-----------|------------|------|
| Sentence Transformer | 0.5-1 sec | 64 | ~2GB |
| Llama3 | 3-5 sec | N/A | ~8GB |
| Mistral | 2-4 sec | N/A | ~6GB |

**Speed-up:** **3-10x più veloce** rispetto a CPU!

### **Senza GPU (Fallback CPU)**

| Modello | Tempo/doc | Batch Size | RAM |
|---------|-----------|------------|-----|
| Sentence Transformer | 2-3 sec | 16 | 500MB |
| Llama3 | 30-60 sec | N/A | 8GB |
| Mistral | 20-40 sec | N/A | 6GB |

---

## 🐛 Troubleshooting

### **Problema: "GPU non rilevata dal worker"**

```bash
# 1. Verifica PyTorch vede GPU
docker exec kbsearch-worker-1 python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"

# 2. Se False, verifica driver
nvidia-smi

# 3. Rebuild worker
docker compose stop worker
docker compose build --no-cache worker
docker compose up -d worker

# 4. Check log
docker compose logs worker | grep -i "gpu\|cuda"
```

### **Problema: "Script non eseguibile"**

```bash
chmod +x gpuworker/deploy_gpu.sh
chmod +x gpuworker/setup_gpuworker.sh
chmod +x gpuworker/rollback_gpu.sh
```

### **Problema: "Directory gpuworker non trovata"**

```bash
# Crea e prepara directory
mkdir -p /opt/kbsearch/gpuworker

# Copia file scaricati da Claude
cp /percorso/download/*.yml /opt/kbsearch/gpuworker/
cp /percorso/download/Dockerfile* /opt/kbsearch/gpuworker/
cp /percorso/download/*.txt /opt/kbsearch/gpuworker/
cp /percorso/download/*.sh /opt/kbsearch/gpuworker/
```

### **Problema: "GPU OOM (Out of Memory)"**

Il worker ha fallback automatico CPU, ma se vuoi ridurre VRAM usage:

```python
# In worker_tasks.py, linea 33:
BATCH_SIZE = 32 if GPU_AVAILABLE else 16  # Riduci da 64 a 32
```

Poi:
```bash
docker compose restart worker
```

---

## 📝 Workflow Completo

### **1. Preparazione**

```bash
cd /opt/kbsearch

# Verifica GPU
nvidia-smi

# Prepara directory
bash setup_gpuworker.sh
# Oppure copia manualmente i file in gpuworker/
```

### **2. Deployment**

```bash
# Esegui deployment automatico
bash gpuworker/deploy_gpu.sh

# Lo script fa tutto e mostra output colorato
# Durata: ~5-10 minuti (download PyTorch CUDA)
```

### **3. Verifica**

```bash
# GPU detection
docker compose logs worker | grep GPU

# GPU usage live
watch -n 1 nvidia-smi

# Health check
curl http://localhost:8000/health
```

### **4. Test Ingestion**

```bash
# Inizializza indici
curl -X POST http://localhost:8000/init_collections

# Start ingestion con Sentence Transformer (veloce con GPU)
curl -X POST 'http://localhost:8000/ingestion/start?model=sentence-transformer'

# Monitor progress
watch -n 2 'curl -s http://localhost:8000/progress | jq'

# Monitor GPU
watch -n 1 nvidia-smi
```

### **5. (Opzionale) Rollback**

Se qualcosa va male:

```bash
bash gpuworker/rollback_gpu.sh
```

---

## 🔍 Verifica Manuale

Se vuoi verificare manualmente che GPU sia configurata:

```bash
# 1. Check docker-compose.yml ha sezioni deploy
cat docker-compose.yml | grep -A 10 "deploy:"

# 2. Check worker container vede GPU
docker exec kbsearch-worker-1 nvidia-smi

# 3. Check PyTorch CUDA
docker exec kbsearch-worker-1 python -c "
import torch
print(f'PyTorch: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'CUDA version: {torch.version.cuda}')
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)}')
"

# 4. Check log worker startup
docker compose logs worker | head -50
```

---

## 📚 Documentazione Completa

- **GPU_DEPLOYMENT_GUIDE.md** → Guida dettagliata con spiegazioni tecniche
- **DEPLOYMENT_CHECKLIST.md** → Checklist passo-passo manuale
- **OCR_OPTIONAL_FUNCTIONS.py** → Funzioni OCR per PDF scansionati

---

## ✅ Checklist Successo

Dopo deployment, verifica:

- [ ] Script `deploy_gpu.sh` completato senza errori
- [ ] Worker log mostra "🎮 Worker GPU DETECTED"
- [ ] Worker log mostra "batch size: 64"
- [ ] `nvidia-smi` mostra GPU in uso durante ingestion
- [ ] API health endpoint risponde: `curl http://localhost:8000/health`
- [ ] Ingestion parte senza errori
- [ ] Tempo per documento ~0.5-1 sec (vs 2-3 sec CPU)

---

## 🎉 Risultato Finale

Con il deployment GPU attivo:

✅ **Worker** usa GPU per embedding → 3-5x più veloce
✅ **Ollama** usa GPU per LLM → 10x più veloce
✅ **API** usa GPU per ricerca → risultati istantanei
✅ **Backup** automatico → rollback facile
✅ **Script** automatici → zero errori umani

**Tempo ingestion 1000 documenti:**
- ❌ CPU: ~40-60 minuti
- ✅ GPU: ~10-15 minuti

**🚀 SPEED-UP: 4-6x!**

---

## 💡 Tips & Tricks

### **Ottimizza batch size per tua GPU**

```python
# Per GPU con poca VRAM (4-6GB)
BATCH_SIZE = 32 if GPU_AVAILABLE else 16

# Per GPU potenti (12-24GB)
BATCH_SIZE = 128 if GPU_AVAILABLE else 16
```

### **Monitor GPU in tempo reale durante ingestion**

```bash
# Terminal 1: GPU usage
watch -n 1 nvidia-smi

# Terminal 2: Worker log
docker compose logs worker -f

# Terminal 3: Progress
watch -n 2 'curl -s http://localhost:8000/progress | jq'
```

### **Test diversi modelli**

```bash
# Sentence Transformer (veloce, ottimo con GPU)
curl -X POST 'http://localhost:8000/ingestion/start?model=sentence-transformer'

# Llama3 (lento ma accurato, beneficia molto da GPU)
curl -X POST 'http://localhost:8000/ingestion/start?model=llama3'

# Mistral (bilanciato)
curl -X POST 'http://localhost:8000/ingestion/start?model=mistral'
```

---

## 🆘 Supporto

Se hai problemi:

1. **Leggi i log**: `docker compose logs worker --tail=100`
2. **Verifica GPU**: `nvidia-smi`
3. **Controlla checklist**: `DEPLOYMENT_CHECKLIST.md`
4. **Fai rollback**: `bash gpuworker/rollback_gpu.sh`

---

## 📄 Licenza

Parte del progetto kbsearch. Usa liberamente per il tuo deployment.

---

**Buon deployment! 🚀🎮**
