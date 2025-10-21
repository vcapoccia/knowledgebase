# 🎮 KBSearch - Deployment GPU Ready

## ✅ Cosa è stato aggiornato

### 1. **docker-compose.yml** 
Aggiunto supporto GPU a:
- ✅ **worker** → CRITICO per ingestion veloce con SentenceTransformers
- ✅ **ollama** → Accelera Llama3/Mistral
- ✅ **api** → Accelera embedding durante ricerca

### 2. **worker_tasks.py**
Il tuo file è **GIÀ COMPLETO** con:
- ✅ GPU detection automatica con PyTorch
- ✅ Batch size ottimizzato (64 GPU vs 16 CPU)
- ✅ GPU memory management (clear cache)
- ✅ Fallback CPU automatico in caso di OOM
- ✅ Device logging per debug

---

## 🚀 Deploy con GPU

### **Prerequisiti**
```bash
# Verifica GPU disponibile
nvidia-smi

# Verifica Docker ha accesso GPU
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
```

### **Avvio Servizi**
```bash
cd /opt/kbsearch

# Stop servizi attuali
docker compose down

# Rebuild con nuovo docker-compose.yml
docker compose build --no-cache

# Avvio con GPU
docker compose up -d

# Verifica log worker
docker compose logs worker -f
```

### **Verifica GPU Detection**
Dovresti vedere nei log del worker:
```
🎮 Worker GPU DETECTED: NVIDIA GeForce RTX 3080
🎮 CUDA Version: 12.0
📦 Worker batch size: 64 (GPU optimized)
📄 Worker caricamento modello all-MiniLM-L6-v2 su cuda...
✅ Worker modello all-MiniLM-L6-v2 caricato su cuda
```

Se vedi:
```
💻 GPU non disponibile, worker usa CPU
```
Significa che:
- Docker non ha accesso GPU (manca `--gpus all` in runtime)
- Driver NVIDIA non installato
- PyTorch non trova CUDA

---

## 📦 Tesseract per DOC/XLS Vecchi

### **Problema**
Il worker usa:
- `python-docx` per DOCX moderni
- `LibreOffice` per DOC/XLS/PPT vecchi
- `pdftotext` per PDF

Ma per **documenti scansionati** o **immagini embedded** serve **Tesseract OCR**.

### **Soluzione: Aggiorna Dockerfile_worker**

Apri `Dockerfile_worker` e aggiungi:

```dockerfile
FROM python:3.11-slim

# Installa dipendenze sistema + Tesseract OCR
RUN apt-get update && apt-get install -y \
    poppler-utils \
    libreoffice \
    tesseract-ocr \
    tesseract-ocr-ita \
    tesseract-ocr-eng \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker /app/worker

CMD ["rq", "worker", "-u", "${REDIS_URL}", "${RQ_QUEUE}"]
```

**Note:**
- `tesseract-ocr` → Core engine
- `tesseract-ocr-ita` → Lingua italiana
- `tesseract-ocr-eng` → Lingua inglese
- Aggiungi altre lingue se necessario

### **Aggiorna requirements.txt (se usi pytesseract)**
```txt
# ... altri requirements ...
pytesseract==0.3.10
pillow==10.0.0
```

Poi nel `worker_tasks.py` puoi aggiungere funzione OCR:

```python
def _extract_ocr_from_pdf(path: str) -> str:
    """Estrae testo da PDF scansionato con OCR"""
    try:
        import pytesseract
        from pdf2image import convert_from_path
        
        images = convert_from_path(path, dpi=300)
        text_parts = []
        
        for i, img in enumerate(images):
            text = pytesseract.image_to_string(img, lang='ita+eng')
            text_parts.append(text)
        
        return "\n\n".join(text_parts)
    
    except Exception as e:
        log.error(f"OCR fallito su {os.path.basename(path)}: {e}")
        return ""
```

---

## 🔥 Performance Attese

### **Con GPU (RTX 3080/4090)**
| Metrica | Sentence Transformer | Llama3 | Mistral |
|---------|---------------------|---------|---------|
| **Tempo/doc** | 0.5-1 sec | 3-5 sec | 2-4 sec |
| **Batch size** | 64 | N/A | N/A |
| **RAM** | 500MB | 6GB | 5GB |
| **VRAM** | 2GB | 8GB | 6GB |

### **Senza GPU (CPU)**
| Metrica | Sentence Transformer | Llama3 | Mistral |
|---------|---------------------|---------|---------|
| **Tempo/doc** | 2-3 sec | 30-60 sec | 20-40 sec |
| **Batch size** | 16 | N/A | N/A |
| **RAM** | 500MB | 8GB | 6GB |

**Speed-up con GPU:** 3-10x più veloce!

---

## 🐛 Troubleshooting

### **GPU non rilevata dal Worker**
```bash
# Verifica PyTorch vede GPU
docker exec kbsearch-worker-1 python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"

# Se False, verifica driver
nvidia-smi

# Se OK, rebuild worker
docker compose stop worker
docker compose build --no-cache worker
docker compose up -d worker
```

### **GPU OOM (Out of Memory)**
Il worker ha **fallback automatico CPU**, ma se vuoi forzare batch size più piccolo:

```python
# In worker_tasks.py, linea 33
BATCH_SIZE = 32 if GPU_AVAILABLE else 16  # Riduci da 64 a 32
```

### **Ollama non usa GPU**
```bash
# Verifica Ollama vede GPU
docker exec kbsearch-ollama ollama run llama3 "test"

# Se lento, verifica deploy GPU in docker-compose
docker compose config | grep -A 10 "ollama:"
```

### **API non usa GPU**
L'API usa GPU solo durante ricerca semantica. Per verificare:

```bash
# Fai una ricerca
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "mode": "semantic", "model": "sentence-transformer"}'

# Verifica log API
docker compose logs api | grep "GPU"
```

---

## ✅ Checklist Finale

Prima di partire con ingestion:

- [ ] `nvidia-smi` mostra GPU disponibile
- [ ] `docker compose config` mostra sezioni `deploy` per worker/ollama/api
- [ ] Log worker mostra "🎮 Worker GPU DETECTED"
- [ ] Log worker mostra "📦 Worker batch size: 64 (GPU optimized)"
- [ ] Tesseract installato in Dockerfile_worker (se serve OCR)
- [ ] Test ingestion con 10 documenti va veloce

---

## 🚀 Comandi Rapidi

```bash
# Stop tutto
docker compose down

# Rebuild tutto
docker compose build --no-cache

# Start con GPU
docker compose up -d

# Monitor worker GPU usage
watch -n 1 nvidia-smi

# Log worker real-time
docker compose logs worker -f

# Progress ingestion
watch -n 2 "curl -s http://localhost:8000/progress | jq"

# Start ingestion
curl -X POST "http://localhost:8000/ingestion/start?model=sentence-transformer"
```

---

## 📝 Note Finali

1. **Il tuo worker_tasks.py è GIÀ COMPLETO** - non serve modificarlo
2. **Sostituisci solo il docker-compose.yml** con quello fornito
3. **Aggiungi Tesseract al Dockerfile_worker** se serve OCR
4. **Rebuild e riavvia** con `docker compose up -d --build`
5. **Monitora i log** per vedere GPU detection

Buona ingestion! 🚀🎮
