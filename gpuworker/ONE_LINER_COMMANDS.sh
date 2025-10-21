#!/bin/bash
# =============================================================================
# ONE-LINER COMMANDS - KBSearch GPU Deployment
# =============================================================================
# Comandi pronti da copiare/incollare per deployment veloce
# =============================================================================

# ============================================
# METODO 1: DEPLOYMENT COMPLETO AUTOMATICO
# ============================================
# Questo comando fa TUTTO in una volta:
# - Verifica prerequisiti
# - Backup configurazione
# - Deploy GPU
# - Verifica funzionamento

cd /opt/kbsearch && \
  bash gpuworker/deploy_gpu.sh


# ============================================
# METODO 2: STEP-BY-STEP MANUALE
# ============================================

# 1. Vai in directory kbsearch
cd /opt/kbsearch

# 2. Verifica GPU disponibile
nvidia-smi && echo "✓ GPU OK"

# 3. Verifica Docker accesso GPU
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi && echo "✓ Docker GPU OK"

# 4. Backup configurazione attuale
cp docker-compose.yml docker-compose.yml.backup.$(date +%Y%m%d_%H%M%S) && \
cp Dockerfile_worker Dockerfile_worker.backup.$(date +%Y%m%d_%H%M%S) && \
cp requirements_worker.txt requirements_worker.txt.backup.$(date +%Y%m%d_%H%M%S) && \
echo "✓ Backup OK"

# 5. Copia nuovi file con GPU support
cp gpuworker/docker-compose.yml ./ && \
cp gpuworker/Dockerfile_worker ./ && \
cp gpuworker/requirements_worker.txt ./ && \
echo "✓ File copiati"

# 6. Stop servizi
docker compose down && echo "✓ Servizi fermati"

# 7. Rebuild con GPU
docker compose build --no-cache worker api && echo "✓ Rebuild completato"

# 8. Start con GPU
docker compose up -d && echo "✓ Servizi avviati"

# 9. Verifica GPU detection
sleep 20 && docker compose logs worker | grep -i "gpu" && echo "✓ GPU attiva"


# ============================================
# METODO 3: SUPER QUICK (un solo comando)
# ============================================
# Attenzione: senza backup! Usa solo se sei sicuro.

cd /opt/kbsearch && \
  cp gpuworker/docker-compose.yml ./ && \
  cp gpuworker/Dockerfile_worker ./ && \
  cp gpuworker/requirements_worker.txt ./ && \
  docker compose down && \
  docker compose build --no-cache && \
  docker compose up -d && \
  sleep 20 && \
  docker compose logs worker | grep "GPU"


# ============================================
# VERIFICHE RAPIDE
# ============================================

# Verifica GPU detection nel worker
docker compose logs worker | grep -E "(GPU DETECTED|batch size|CUDA)"

# Verifica tutti i servizi running
docker compose ps

# Health check API
curl http://localhost:8000/health && echo "✓ API OK"

# GPU usage real-time
watch -n 1 nvidia-smi

# Worker log live
docker compose logs worker -f

# Progress ingestion live
watch -n 2 'curl -s http://localhost:8000/progress | jq'


# ============================================
# COMANDI DI EMERGENZA
# ============================================

# Rollback completo (torna alla configurazione precedente)
cd /opt/kbsearch && bash gpuworker/rollback_gpu.sh

# Restart worker solo
docker compose restart worker

# Rebuild worker solo (se ha problemi)
docker compose stop worker && \
docker compose build --no-cache worker && \
docker compose up -d worker

# Verifica PyTorch CUDA nel worker
docker exec kbsearch-worker-1 python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"CPU\"}')"

# Pulisci tutto e ricomincia da zero (⚠️ CANCELLA DATI!)
docker compose down -v && \
docker compose build --no-cache && \
docker compose up -d


# ============================================
# TEST INGESTION VELOCE
# ============================================

# Inizializza indici
curl -X POST http://localhost:8000/init_collections && echo "✓ Indici inizializzati"

# Start ingestion con Sentence Transformer (veloce con GPU)
curl -X POST 'http://localhost:8000/ingestion/start?model=sentence-transformer' && echo "✓ Ingestion avviata"

# Monitor progress
watch -n 2 'curl -s http://localhost:8000/progress | jq'


# ============================================
# MONITORING COMPLETO (3 terminali)
# ============================================

# Terminal 1 - GPU usage
watch -n 1 nvidia-smi

# Terminal 2 - Worker log
docker compose logs worker -f

# Terminal 3 - Progress
watch -n 2 'curl -s http://localhost:8000/progress | jq'


# ============================================
# BENCHMARK GPU vs CPU
# ============================================

# Test con 10 documenti GPU
time docker compose exec worker python -c "
from worker.worker_tasks import run_ingestion
result = run_ingestion({'mode': 'full', 'model': 'sentence-transformer'})
print(f'Device: {result.get(\"device\", \"unknown\")}')
"

# Forza CPU (per confronto)
CUDA_VISIBLE_DEVICES="" docker compose exec worker python -c "
from worker.worker_tasks import run_ingestion
result = run_ingestion({'mode': 'full', 'model': 'sentence-transformer'})
print(f'Device: {result.get(\"device\", \"unknown\")}')
"


# ============================================
# PULIZIA E MANUTENZIONE
# ============================================

# Rimuovi container vecchi
docker compose down --remove-orphans

# Pulisci immagini non usate
docker image prune -f

# Pulisci cache build
docker builder prune -f

# Pulisci volumi non usati (⚠️ attenzione ai dati)
docker volume prune -f

# Pulisci tutto Docker (⚠️ PERICOLOSO)
docker system prune -af --volumes


# ============================================
# EXPORT/IMPORT CONFIGURAZIONE
# ============================================

# Export configurazione GPU (per backup)
tar -czf kbsearch_gpu_config_$(date +%Y%m%d).tar.gz \
  docker-compose.yml \
  Dockerfile_worker \
  requirements_worker.txt \
  worker/

# Import configurazione da backup
tar -xzf kbsearch_gpu_config_20250115.tar.gz -C /opt/kbsearch/


# ============================================
# DEBUG AVANZATO
# ============================================

# Controlla tutte le env variables nel worker
docker compose exec worker env | grep -E "(CUDA|GPU|TORCH)"

# Test PyTorch dettagliato
docker compose exec worker python -c "
import torch
print(f'PyTorch version: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'CUDA version: {torch.version.cuda}')
print(f'cuDNN version: {torch.backends.cudnn.version()}')
print(f'GPU count: {torch.cuda.device_count()}')
if torch.cuda.is_available():
    print(f'GPU 0: {torch.cuda.get_device_name(0)}')
    print(f'GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB')
"

# Test Sentence Transformers con GPU
docker compose exec worker python -c "
from sentence_transformers import SentenceTransformer
import torch
model = SentenceTransformer('all-MiniLM-L6-v2')
device = 'cuda' if torch.cuda.is_available() else 'cpu'
model = model.to(device)
embedding = model.encode(['test'], device=device)
print(f'Device: {device}')
print(f'Embedding shape: {embedding.shape}')
print('✓ GPU embedding OK' if device == 'cuda' else '⚠ CPU fallback')
"

# Controlla GPU memory usage
docker compose exec worker python -c "
import torch
if torch.cuda.is_available():
    print(f'Allocated: {torch.cuda.memory_allocated(0) / 1024**2:.1f} MB')
    print(f'Cached: {torch.cuda.memory_reserved(0) / 1024**2:.1f} MB')
    print(f'Max allocated: {torch.cuda.max_memory_allocated(0) / 1024**2:.1f} MB')
else:
    print('GPU not available')
"


# ============================================
# PERFORMANCE TESTING
# ============================================

# Test velocità embedding GPU vs CPU
docker compose exec worker python -c "
import time
from sentence_transformers import SentenceTransformer
import torch

texts = ['test sentence'] * 100

# GPU
if torch.cuda.is_available():
    model = SentenceTransformer('all-MiniLM-L6-v2', device='cuda')
    start = time.time()
    embeddings = model.encode(texts, batch_size=64)
    gpu_time = time.time() - start
    print(f'GPU: {gpu_time:.2f}s ({len(texts)/gpu_time:.1f} docs/sec)')

# CPU
model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')
start = time.time()
embeddings = model.encode(texts, batch_size=16)
cpu_time = time.time() - start
print(f'CPU: {cpu_time:.2f}s ({len(texts)/cpu_time:.1f} docs/sec)')

if torch.cuda.is_available():
    print(f'Speedup: {cpu_time/gpu_time:.1f}x')
"
