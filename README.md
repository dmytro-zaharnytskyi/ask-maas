# Ask MaaS (Ask Model-as-a-Service)

A production-ready Retrieval-Augmented Generation (RAG) system for Red Hat OpenShift that enables intelligent Q&A on technical documentation using state-of-the-art LLMs.

## 🚀 Features

- **Intelligent Q&A**: Ask questions about technical articles and get context-aware responses
- **RAG Architecture**: Combines retrieval of relevant document chunks with LLM generation
- **GPU Optimized**: Supports NVIDIA GPUs (L40S, A100, T4) with automatic detection
- **Production Ready**: Full observability, health checks, and scalable architecture
- **Multi-Model Support**: Choose between Qwen 2.5 32B (recommended) or Mistral 7B

## 📋 Prerequisites

- **OpenShift Cluster**: Version 4.12+ 
- **GPU Node**: NVIDIA GPU with 20GB+ VRAM (L40S, A100, or T4)
- **Storage**: 100GB+ available storage
- **Access**: Cluster-admin privileges
- **Tools**: 
  - `oc` CLI installed and configured
  - `podman` or `docker` for building images
  - `git` for cloning the repository

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Frontend (Next.js)                 │
│                   ask-maas-frontend namespace           │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                  Orchestrator API (FastAPI)             │
│                    ask-maas-api namespace               │
│  ┌────────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │  Ingestion │  │    Chat   │  │  Health/Metrics  │  │
│  │   Service  │  │  Service  │  │     Endpoints    │  │
│  └────────────┘  └───────────┘  └──────────────────┘  │
└────────┬──────────────┬─────────────────┬──────────────┘
         │              │                 │
         ▼              ▼                 ▼
┌──────────────┐ ┌─────────────┐ ┌──────────────────────┐
│    Redis     │ │   TEI       │ │      vLLM Model      │
│   (Cache)    │ │ Embeddings  │ │  (Qwen/Mistral)      │
│              │ │ & Reranker  │ │    GPU-Enabled       │
└──────────────┘ └─────────────┘ └──────────────────────┘
   ask-maas-api    ask-maas-models    ask-maas-models
```

### Components

1. **Frontend (Ghost Site)**
   - Next.js application serving articles
   - Chat widget for Q&A interface
   - Article viewer with syntax highlighting

2. **Orchestrator API**
   - FastAPI backend handling all business logic
   - RAG pipeline orchestration
   - Article ingestion and chunking
   - Chat session management

3. **Model Services**
   - **vLLM**: High-performance LLM inference (Qwen 2.5 32B or Mistral 7B)
   - **TEI Embeddings**: BGE-M3 for document embeddings (1024 dimensions)
   - **TEI Reranker**: BGE-reranker-large for result optimization

4. **Storage**
   - **Redis**: Caching for indexed articles and embeddings
   - **FAISS**: Vector similarity search

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/your-org/ask-maas.git
cd ask-maas
```

### 2. Deploy the System

Deploy with Qwen 2.5 32B (recommended for L40S/A100):
```bash
./deploy-ask-maas.sh
```

Or deploy with Mistral 7B (for smaller GPUs):
```bash
./deploy-ask-maas.sh --model mistral
```

### 3. Access the Application

After deployment completes (15-20 minutes), access:
- Frontend: `https://ask-maas-frontend.apps.<your-cluster-domain>`
- API: `https://ask-maas-api.apps.<your-cluster-domain>`

### 4. Test the System

1. Open the frontend URL
2. Click on an article (e.g., "Dynamic GPU slicing with NVIDIA MIG")
3. Click the "Ask This Page" button
4. Ask questions like:
   - "What GPU is described in this article?"
   - "What are the benefits of MIG?"
   - "How does MIG work with OpenShift?"

## 📘 Detailed Deployment Guide

### Step 1: Prepare Your Cluster

```bash
# Login to OpenShift
oc login --server=https://api.<cluster-domain>:6443

# Verify GPU node exists
oc get nodes -l nvidia.com/gpu.present=true

# If no GPU node is labeled, label it manually
oc label node <node-name> nvidia.com/gpu.present=true
```

### Step 2: Install Required Operators

Install from OpenShift Console → OperatorHub:
- NVIDIA GPU Operator
- Red Hat OpenShift GitOps (optional)
- Red Hat OpenShift Pipelines (optional)

### Step 3: Run Deployment Script

```bash
# Full deployment (builds images and deploys all components)
./deploy-ask-maas.sh

# Skip operator checks (if already installed)
./deploy-ask-maas.sh --skip-operators

# Skip image building (use existing images)
./deploy-ask-maas.sh --skip-build

# Dry run (show what would be done)
./deploy-ask-maas.sh --dry-run
```

### Step 4: Monitor Deployment

```bash
# Watch pod creation
watch oc get pods -n ask-maas-models

# Check logs for model loading
oc logs -f deployment/vllm-qwen2-32b -n ask-maas-models

# Verify all services are running
oc get pods --all-namespaces | grep ask-maas
```

## 🔧 Configuration

### Environment Variables

Key environment variables in the Orchestrator:

| Variable | Description | Default |
|----------|-------------|---------|
| `VLLM_URL` | vLLM service endpoint | `http://vllm-qwen2-service:8080` |
| `MODEL_NAME` | Model identifier | `qwen2-32b-instruct` |
| `MAX_CONTEXT_LENGTH` | Maximum context tokens | `8192` |
| `TEI_EMBEDDINGS_URL` | Embeddings service | `http://tei-embeddings-service:8080` |
| `TEI_RERANKER_URL` | Reranker service | `http://tei-reranker-service:8080` |
| `REDIS_HOST` | Redis hostname | `redis-service` |
| `MIN_RERANK_SCORE` | Minimum score threshold | `0.001` |
| `CORS_ORIGINS` | Allowed origins | `["*"]` |

### Model Selection

**Qwen 2.5 32B AWQ** (Recommended)
- Best quality responses
- 8K context window
- Requires ~20GB VRAM
- Apache 2.0 license

**Mistral 7B Instruct AWQ**
- Smaller footprint
- 4K context window
- Requires ~8GB VRAM
- Apache 2.0 license

## 📝 API Usage

### Ingest an Article

```bash
curl -X POST https://ask-maas-api.apps.<cluster>/api/v1/ingest/page \
  -H "Content-Type: application/json" \
  -d '{
    "page_url": "https://example.com/article.html",
    "force_refresh": true
  }'
```

### Ask a Question

```bash
curl -X POST https://ask-maas-api.apps.<cluster>/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is Kubernetes?",
    "page_url": "https://example.com/article.html",
    "stream": false
  }'
```

### Health Checks

```bash
# Liveness probe
curl https://ask-maas-api.apps.<cluster>/health/live

# Readiness probe
curl https://ask-maas-api.apps.<cluster>/health/ready

# Metrics
curl https://ask-maas-api.apps.<cluster>/metrics
```

## 🐛 Troubleshooting

### Common Issues and Solutions

#### 1. Model Pod Stuck in Pending
**Symptom**: vLLM pod shows `Pending` status
```bash
oc describe pod <pod-name> -n ask-maas-models
```

**Solutions**:
- Check GPU node exists: `oc get nodes -l nvidia.com/gpu.present=true`
- Verify GPU operator: `oc get csv -n openshift-operators | grep gpu`
- Check resource requests: Reduce CPU/memory if needed

#### 2. Model Returns Empty Responses
**Symptom**: Chat responds but with no text

**Solution**: This is a known issue with Mixtral AWQ. Switch to Qwen:
```bash
./deploy-ask-maas.sh --cleanup
./deploy-ask-maas.sh --model qwen
```

#### 3. "Page not indexed" Error
**Symptom**: Chat says page needs to be ingested first

**Solutions**:
- Ingest the article first using the API
- Check Redis is running: `oc get pods -n ask-maas-api | grep redis`
- Verify embeddings service: `oc logs deployment/tei-bge-m3-embeddings -n ask-maas-models`

#### 4. 404 on Articles
**Symptom**: Articles don't load in frontend

**Solutions**:
- Check articles are copied: `oc exec deployment/ghost-article-site -n ask-maas-frontend -- ls /app/public/static-articles`
- Verify route: `oc get route -n ask-maas-frontend`

#### 5. Model OOM (Out of Memory)
**Symptom**: Model pod crashes with CUDA OOM

**Solutions**:
- Reduce `gpu-memory-utilization` in deployment
- Switch to smaller model (mistral)
- Check GPU memory: `oc exec <pod> -- nvidia-smi`

### Debug Commands

```bash
# Check all pods status
oc get pods --all-namespaces | grep ask-maas

# View orchestrator logs
oc logs -f deployment/ask-maas-orchestrator -n ask-maas-api

# Check model loading progress
oc logs deployment/vllm-qwen2-32b -n ask-maas-models | grep -i "loading\|ready"

# Test Redis connection
oc exec deployment/redis -n ask-maas-api -- redis-cli -a $(oc get secret redis-credentials -n ask-maas-api -o jsonpath='{.data.password}' | base64 -d) ping

# Check GPU allocation
oc describe node <gpu-node> | grep -A10 "Allocated resources"

# Test embeddings service
oc exec deployment/ask-maas-orchestrator -n ask-maas-api -- \
  curl -X POST http://tei-embeddings-service.ask-maas-models:8080/embed \
  -H "Content-Type: application/json" \
  -d '{"inputs": ["test"]}'

# Force restart a deployment
oc rollout restart deployment/ask-maas-orchestrator -n ask-maas-api
```

## 🔄 Updates and Maintenance

### Update the Orchestrator
```bash
cd ask-maas-api
# Make your changes
podman build -f Dockerfile.simple -t orchestrator-api:v2 .
podman push <registry>/ask-maas-api/orchestrator-api:v2
oc set image deployment/ask-maas-orchestrator orchestrator=<registry>/ask-maas-api/orchestrator-api:v2 -n ask-maas-api
```

### Update the Frontend
```bash
cd ghost-site
# Make your changes
podman build -f Dockerfile.simple -t ghost-article-site:v2 .
podman push <registry>/ask-maas-frontend/ghost-article-site:v2
oc set image deployment/ghost-article-site frontend=<registry>/ask-maas-frontend/ghost-article-site:v2 -n ask-maas-frontend
```

### Clean Up
```bash
# Remove all Ask MaaS components
./deploy-ask-maas.sh --cleanup
```

## 📊 Performance Tuning

### GPU Memory Optimization
```yaml
# Adjust in vLLM deployment
--gpu-memory-utilization: "0.95"  # Use 95% of GPU memory
--max-model-len: "8192"           # Reduce for less memory usage
--max-num-seqs: "16"              # Concurrent sequences
```

### Redis Optimization
```bash
# Disable persistence for better performance
oc exec deployment/redis -n ask-maas-api -- redis-cli CONFIG SET save ""
oc exec deployment/redis -n ask-maas-api -- redis-cli CONFIG SET stop-writes-on-bgsave-error no
```

### Scaling Orchestrator
```bash
# Scale to handle more requests
oc scale deployment/ask-maas-orchestrator --replicas=5 -n ask-maas-api
```

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the Apache 2.0 License.

## 🙏 Acknowledgments

- **Models**: Qwen (Alibaba), Mistral AI
- **Frameworks**: vLLM, TEI (Hugging Face), LangChain
- **Infrastructure**: Red Hat OpenShift, NVIDIA GPU Operator

## 📞 Support

For issues and questions:
1. Check the [Troubleshooting](#-troubleshooting) section
2. Search existing [GitHub Issues](https://github.com/your-org/ask-maas/issues)
3. Create a new issue with:
   - OpenShift version
   - GPU type and driver version
   - Error logs
   - Steps to reproduce

---

Built with ❤️ by the Red Hat team