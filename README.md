# KB Search - Sistema di Ricerca Semantica Multi-Modello

Sistema enterprise di ricerca semantica su knowledge base documentale, con supporto multi-modello (Sentence Transformer, LLaMA 3, Mistral) e indicizzazione intelligente.

## 🚀 Features

- **Multi-Model Search**: Sentence-Transformer (veloce), LLaMA 3, Mistral
- **Hybrid Search**: Semantic + BM25 keyword matching
- **GPU Accelerated**: CUDA support per embedding generation
- **Document Processing**: PDF, DOCX, XLSX, PPT con LibreOffice + OCR
- **Vector Store**: Qdrant per similarity search
- **Full-Text**: Meilisearch per keyword search
- **Admin Dashboard**: Monitoring real-time ingestion
- **Multi-tenancy**: Support per più knowledge base

## 📋 Tech Stack

- **API**: FastAPI + Python 3.11
- **Worker**: RQ (Redis Queue) + GPU
- **Vector DB**: Qdrant
- **Search**: Meilisearch
- **Database**: PostgreSQL 15
- **Cache**: Redis
- **OCR**: Tesseract + LibreOffice
- **Models**: sentence-transformers, Ollama (LLaMA3/Mistral)

## 🏗️ Architecture
```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   FastAPI   │────▶│ Redis Queue  │────▶│ GPU Worker  │
│    (API)    │     │              │     │  (RQ + GPU) │
└─────────────┘     └──────────────┘     └─────────────┘
       │                                         │
       ▼                                         ▼
┌─────────────┐                          ┌─────────────┐
│  PostgreSQL │                          │   Qdrant    │
│  (Metadata) │                          │  (Vectors)  │
└─────────────┘                          └─────────────┘
                                                │
                                         ┌─────────────┐
                                         │ Meilisearch │
                                         │  (Keywords) │
                                         └─────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Docker + Docker Compose
- NVIDIA GPU (opzionale, per accelerazione)
- 16GB RAM (minimo), 32GB consigliato
- 50GB disk space

### Installation
```bash
# Clone repo
git clone https://github.com/YOUR_USERNAME/kbsearch.git
cd kbsearch

# Crea docker-compose.override.yml (opzionale)
cp docker-compose.override.yml.example docker-compose.override.yml

# Start services
docker compose up -d

# Verifica
docker compose ps
curl http://localhost:8000/health
```

### Configuration

Vedi `docker-compose.yml` per configurazioni principali.

Per GPU support, assicurati di avere:
- NVIDIA drivers installati
- nvidia-docker2
- CUDA 12.x

## 📚 Usage

### Web Interface

- Dashboard: http://localhost:8000
- Admin Panel: http://localhost:8000/admin
- Search: http://localhost:8000/?q=your+query

### API Endpoints
```bash
# Health check
curl http://localhost:8000/health

# Start ingestion
curl -X POST "http://localhost:8000/ingestion/start?model=sentence-transformer&mode=incremental"

# Search
curl "http://localhost:8000/search?q_text=query&model=sentence-transformer&top_k=10"

# Progress
curl http://localhost:8000/progress
```

## 🛠️ Development

### Structure
```
/opt/kbsearch/
├── main.py                      # FastAPI application
├── search_utils.py              # Search utilities
├── requirements_api.txt         # API dependencies
├── requirements_worker.txt      # Worker dependencies
├── Dockerfile_api
├── Dockerfile_worker
├── docker-compose.yml
├── frontend/                    # Web UI
│   ├── static/
│   └── templates/
└── migrations/                  # DB migrations
```

### Adding Features

1. Modify `main.py` for API changes
2. Modify `worker/worker_tasks.py` for processing changes
3. Rebuild: `docker compose build`
4. Restart: `docker compose restart api worker`

## 📊 Monitoring

Access monitoring dashboard at:
- http://localhost:8000/hostmonitor

Metrics include:
- Ingestion progress
- GPU utilization
- Database stats
- Queue status

## 🐛 Troubleshooting

### Worker not processing
```bash
# Check worker logs
docker compose logs worker --tail=50

# Restart worker
docker compose restart worker
```

### GPU not detected
```bash
# Verify NVIDIA drivers
nvidia-smi

# Check container GPU access
docker compose exec worker nvidia-smi
```

## 📝 License

MIT License - see LICENSE file

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repo
2. Create feature branch
3. Commit changes
4. Push and create PR

## 📧 Contact

For questions: [your-email@example.com]
