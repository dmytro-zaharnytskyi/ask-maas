# Ask MaaS - Pure RAG System

A production-ready Retrieval-Augmented Generation (RAG) system for Red Hat Developer articles, implementing pure vector-based semantic search with global context awareness.

## 🚀 Features

- **Pure Vector Search**: Uses ONLY embeddings and cosine similarity (no keyword matching)
- **Global Context Search**: Every query searches across ALL indexed articles
- **Fresh Retrieval**: Each query performs fresh context retrieval without caching
- **Streaming Responses**: Real-time SSE streaming for chat responses
- **Production Ready**: Deployed on OpenShift with Redis caching and horizontal scaling

## 📁 Project Structure

```
ask-maas/
├── ask-maas-api/              # Backend API service
│   ├── app/                   # Core application
│   │   ├── routers/          # API endpoints
│   │   │   ├── chat.py       # Chat endpoint with pure RAG
│   │   │   └── ingest.py     # Document ingestion
│   │   ├── services/         # Business logic
│   │   │   ├── vector_retrieval.py  # Pure vector search implementation
│   │   │   ├── llm.py        # LLM integration
│   │   │   ├── cache.py      # Redis caching
│   │   │   └── config.py     # Configuration
│   │   └── models/           # Data models
│   ├── Dockerfile            # Container definition
│   ├── requirements.txt      # Python dependencies
│   └── ingest.py            # Article ingestion script
├── ghost-site/               # Frontend application
│   ├── src/                  # React/Next.js source
│   ├── Dockerfile           # Frontend container
│   └── package.json         # Node dependencies
├── k8s/                     # Kubernetes/OpenShift configs
│   ├── api/                # API deployment configs
│   ├── models/             # Model service configs
│   └── namespaces/         # Namespace definitions
├── articles/               # Sample articles for testing
├── deploy-ask-maas.sh     # Deployment script
└── IMPROVEMENTS.md        # Technical improvements documentation
```

## 🛠️ Technology Stack

- **Backend**: FastAPI, Python 3.11
- **Vector Search**: FAISS with cosine similarity
- **LLM**: vLLM with Mistral-7B
- **Embeddings**: Text Embeddings Inference (TEI)
- **Cache**: Redis
- **Frontend**: Next.js, React
- **Deployment**: OpenShift/Kubernetes

## 📦 Installation

### Prerequisites
- Python 3.11+
- Docker/Podman
- OpenShift CLI (oc) or kubectl
- Access to OpenShift cluster

### Local Development

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/ask-maas.git
cd ask-maas
```

2. **Setup Python environment**
```bash
cd ask-maas-api
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. **Configure environment**
```bash
cp example-env .env
# Edit .env with your configuration
```

4. **Start Redis locally**
```bash
docker run -d -p 6379:6379 redis:latest
```

5. **Run the API**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 🚀 Deployment

### Build and Push Image
```bash
cd ask-maas-api
podman build -t ask-maas-api:latest .
podman tag ask-maas-api:latest your-registry/ask-maas-api:latest
podman push your-registry/ask-maas-api:latest
```

### Deploy to OpenShift
```bash
# Deploy using the provided script
./deploy-ask-maas.sh

# Or manually
oc apply -f k8s/namespaces/
oc apply -f k8s/api/
oc apply -f k8s/models/
```

### Ingest Articles
```bash
cd ask-maas-api
python ingest.py
```

## 📊 API Endpoints

### Health Check
```bash
GET /health
```

### Chat (Pure RAG)
```bash
POST /api/v1/chat
{
  "query": "What is MaaS?",
  "page_url": "any-url",
  "stream": true
}
```

### Ingest Content
```bash
POST /api/v1/ingest/content
{
  "page_url": "https://example.com/article",
  "title": "Article Title",
  "content": "Article content...",
  "content_type": "text",
  "force_refresh": true
}
```

## 🔑 Key Improvements (Pure RAG)

This system implements a **pure RAG approach**:

1. **No Keyword Matching**: Completely removed BM25 and lexical search
2. **Pure Vector Search**: Uses only embeddings and cosine similarity
3. **Global Context**: Every query searches across ALL indexed articles
4. **Fresh Retrieval**: No query result caching, fresh search for each request
5. **Optimized Performance**: Batch embedding generation, reduced chunk sizes

See [IMPROVEMENTS.md](IMPROVEMENTS.md) for detailed technical changes.

## 🧪 Testing

### Test a Query
```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/chat",
    json={
        "query": "What is MaaS?",
        "page_url": "test",
        "stream": False
    }
)
print(response.json())
```

### Expected Queries That Work
- "What is MaaS?" → Returns MaaS definition
- "How does vLLM compare to Ollama?" → Returns comparison
- "What is TTFT and ITL?" → Returns metrics definitions
- "How to deploy Llama 3 with vLLM?" → Returns deployment guide

## 🔧 Configuration

Key environment variables in `.env`:

```env
# Model Services
VLLM_URL=http://vllm-service:8080
TEI_EMBEDDINGS_URL=http://tei-embeddings:8080
TEI_RERANKER_URL=http://tei-reranker:8080

# Redis Cache
REDIS_HOST=redis-service
REDIS_PORT=6379

# Retrieval Settings
RETRIEVAL_TOP_K=20          # Reduced for performance
MIN_SIMILARITY_SCORE=0.1    # Minimum similarity threshold
CHUNK_SIZE=800              # Optimized chunk size
```

## 📈 Performance

- **Query Success Rate**: 83% (5/6 test queries)
- **Average Response Time**: ~30 seconds (can be optimized with GPU)
- **Global Context**: ✅ Working across all articles
- **Pure Vector Search**: ✅ No keyword matching

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/improvement`)
3. Commit changes (`git commit -am 'Add feature'`)
4. Push to branch (`git push origin feature/improvement`)
5. Create Pull Request

## 📝 License

[Your License]

## 🆘 Support

For issues and questions:
- Open an issue on GitHub
- Check [IMPROVEMENTS.md](IMPROVEMENTS.md) for technical details
- Review the deployment logs for troubleshooting

## 🏗️ Architecture

```
User Query
    ↓
Vector Embedding Generation (Fresh)
    ↓
Global Search Across All Articles
    ↓
Cosine Similarity Scoring
    ↓
Result Diversification (Max 3 per article)
    ↓
Optional Reranking
    ↓
LLM Response Generation
    ↓
SSE Streaming to User
```

## 🚦 System Status

- **Production URL**: Configure in deployment
- **Health Endpoint**: `/health`
- **Metrics**: Prometheus-compatible `/metrics`
- **Logs**: Structured JSON logging with correlation IDs

---
*Built with ❤️ for pure semantic search*