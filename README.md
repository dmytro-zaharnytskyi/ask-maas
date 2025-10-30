# Ask MaaS - AI-Powered Documentation Assistant

A production-ready Retrieval-Augmented Generation (RAG) system for Red Hat Developer articles, featuring an AI assistant that can answer questions about MaaS (Models-as-a-Service), vLLM, Kuadrant, and OpenShift deployments.

## 🌟 System Overview

Ask MaaS is a comprehensive AI documentation assistant that combines:
- **Interactive Web Interface**: Browse and read technical articles
- **AI-Powered Chat**: Ask questions about any article or topic with conversation memory
- **RAG System**: Pure Qdrant vector database for all storage (no Redis/FAISS)
- **Production Deployment**: Full OpenShift/Kubernetes deployment with GPU acceleration

### Key Features
- 🤖 **Intelligent AI Assistant**: Answers questions with source citations and conversation history
- 📚 **Global Context Awareness**: AI has knowledge of all indexed articles
- 💬 **Conversation Memory**: Maintains context across multiple questions in a session
- 🚀 **Streaming Responses**: Real-time SSE streaming for better UX
- 🎨 **Beautiful UI**: Modern, responsive interface with styled articles
- 🔍 **Semantic Search**: Pure vector embeddings with BGE-M3 for accurate retrieval
- 🎯 **Smart Reranking**: BGE-Reranker-Large for improved relevance
- ⚡ **GPU Acceleration**: vLLM with optimized inference on NVIDIA GPUs
- 🗄️ **Single Storage Backend**: Qdrant vector database only (Redis/FAISS removed)
- 🔄 **Optimized Chunking**: 1500-token chunks with 200-token overlap for better context

## 🏗️ Architecture Updates

### Storage Simplification
- **Before**: Redis + FAISS + Qdrant (complex multi-storage)
- **After**: Qdrant only (simplified single source of truth)
- All articles and citations stored in `ask-maas-citations` collection
- No caching layer - direct vector search for every query

### Improved Retrieval Pipeline
1. **Query Processing**: User query → TEI embeddings (BGE-M3)
2. **Initial Search**: Retrieve 30 most similar chunks from Qdrant
3. **Reranking**: BGE-Reranker-Large selects top 15 most relevant
4. **Context Management**: 
   - With conversation history: 10 chunks + history summary
   - Without history: 15 chunks for maximum context
5. **Response Generation**: LLM generates answer with citations

### Conversation Memory
- Session-based conversation tracking
- Stores last 10 messages per session
- Automatically summarizes older conversations
- Dynamic chunk adjustment based on history length

## 📚 Adding Articles to the System

### Article Format and Placement

The Ask-MaaS system dynamically loads HTML articles from the filesystem. To add new articles:

1. **Article Location**: Place HTML files in the `ghost-site/public/articles/` directory
2. **File Format**: Articles must be in HTML format with `.html` extension
3. **Naming Convention**: Use descriptive filenames (e.g., `Deploy Llama 3 8B with vLLM _ Red Hat Developer.html`)

### Article Ingestion

Articles are automatically ingested into Qdrant with:
- **Chunk Size**: 1500 tokens (optimized from 1000)
- **Overlap**: 200 tokens (increased from 120)
- **Better Context**: Headings stay with their content

To manually ingest articles:
```bash
curl -X POST https://<api-url>/api/v1/ingest/unified \
  -H "Content-Type: application/json" \
  -d '{
    "url": "article-url",
    "title": "Article Title",
    "content": "Article content...",
    "source_type": "article"
  }'
```

## 🚀 Quick Start

### Prerequisites
- OpenShift 4.12+ cluster with GPU node (NVIDIA L40S or similar)
- `oc` CLI installed and logged in
- Podman or Docker for building images
- Python 3.11+ for local development

### One-Command Deployment

```bash
# Deploy everything with optimized Qwen model
./deploy-ask-maas.sh

# Or deploy with Mistral for lower GPU requirements
./deploy-ask-maas.sh --model mistral
```

This script will:
1. Create namespaces (ask-maas-models, ask-maas-api, ask-maas-frontend)
2. Deploy Qdrant vector database (no Redis/FAISS)
3. Deploy model services (vLLM, TEI embeddings, TEI reranker)
4. Deploy orchestrator API with citation expansion
5. Deploy frontend with article viewer
6. Configure routes and ingress
7. Ingest initial articles into Qdrant

## 📦 Component Details

### Storage Layer (Simplified)
- **Qdrant**: Vector database for all content
  - Collection: `ask-maas-citations`
  - Distance metric: Cosine similarity
  - Vector size: 768 (BGE-M3)
- ~~**Redis**: Removed - no longer needed~~
- ~~**FAISS**: Removed - replaced by Qdrant~~

### Model Services
- **vLLM**: LLM inference server
  - Qwen 2.5 32B AWQ (recommended) or Mistral 7B AWQ
  - GPU accelerated with NVIDIA L40S
  - Optimized for high throughput
- **TEI Embeddings**: BGE-M3 for text embeddings
- **TEI Reranker**: BGE-Reranker-Large for result reranking

### API Services
- **Orchestrator API**: Main backend service
  - `/chat`: Main chat endpoint with Qdrant retrieval
  - `/chat/unified`: Alternative unified search endpoint
  - `/ingest/unified`: Direct Qdrant ingestion endpoint
  - Citation expansion service (simplified, no Redis)
  - Conversation history management

### Frontend
- **Ghost Article Site**: Next.js application
  - Dynamic article loading from filesystem
  - Interactive chat widget with SSE streaming
  - Session management for conversation history
  - Clean citation display (titles only, no text)

## 🛠️ Configuration

### Environment Variables

```bash
# Model Configuration
MODEL_NAME=qwen2-32b-instruct
MAX_TOKENS=2000
TEMPERATURE=0.3

# Chunking Configuration (Optimized)
CHUNK_SIZE=1500        # Increased from 1000
CHUNK_OVERLAP=200      # Increased from 120
MAX_CHUNK_SIZE=1800    # Increased from 1200

# Retrieval Configuration  
RETRIEVAL_TOP_K=30     # Initial retrieval
RERANK_TOP_K=15        # After reranking

# Service URLs
QDRANT_URL=http://qdrant-service:6333
TEI_EMBEDDINGS_URL=http://tei-embeddings-service:8080
TEI_RERANKER_URL=http://tei-reranker-service:8080
VLLM_URL=http://vllm-service:8080
```

## 📈 Performance Optimizations

### Chunking Improvements
- Larger chunks (1500 tokens) preserve more context
- Increased overlap (200 tokens) prevents information loss
- Headings stay with their content for better comprehension

### Retrieval Enhancements
- Two-stage retrieval: broad search → focused reranking
- No similarity threshold initially - let reranker decide
- Dynamic chunk count based on conversation history

### Simplified Architecture
- Removed Redis caching layer - direct Qdrant queries
- Removed FAISS indexes - all vectors in Qdrant
- Single source of truth for all content

## 🔍 API Endpoints

### Chat Endpoints
```bash
# Main chat with conversation history
POST /api/v1/chat
{
  "query": "What is MaaS?",
  "page_url": "article-url",
  "session_id": "unique-session-id",
  "stream": true
}

# Clear conversation history
DELETE /api/v1/chat/history/{session_id}
```

### Ingestion Endpoints
```bash
# Direct Qdrant ingestion (recommended)
POST /api/v1/ingest/unified
{
  "url": "article-url",
  "title": "Article Title",
  "content": "Article content...",
  "source_type": "article"
}
```

## 📊 Monitoring

### Health Checks
```bash
# API health
curl https://<api-url>/health

# Check Qdrant status
curl http://qdrant-service:6333/collections/ask-maas-citations
```

### Metrics
- Retrieval time and chunk counts
- LLM generation time
- Conversation history length
- Session tracking

## 🚨 Troubleshooting

### Common Issues

1. **"Content not found" errors**
   - Ensure articles are properly ingested into Qdrant
   - Check if using `/chat/unified` endpoint (uses Qdrant)
   - Verify chunk size isn't splitting important content

2. **No conversation memory**
   - Include `session_id` in requests
   - Check if session history was cleared

3. **Slow responses**
   - Reduce initial retrieval from 30 to 20 chunks
   - Ensure reranker is functioning
   - Check GPU utilization for vLLM

## 📝 Recent Changes

### Major Updates
1. **Removed Redis/FAISS** - Simplified to Qdrant-only storage
2. **Added Conversation Memory** - Session-based history tracking
3. **Improved Chunking** - 1500 tokens with 200 overlap
4. **Citation Expansion Refactored** - Moved from patch directory to services
5. **Fixed Retrieval** - All endpoints now use Qdrant
6. **Clean Citations** - Show only titles, no chunk text

### Migration Notes
- All articles must be re-ingested with new chunking settings
- Redis deployments can be removed from cluster
- Update environment variables to remove Redis configuration

## 🤝 Contributing

Contributions are welcome! Please ensure:
- Code follows existing patterns
- No Redis/FAISS dependencies added
- Tests pass with Qdrant-only storage
- Documentation is updated

## 📜 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- Red Hat Developer team for articles
- OpenShift for container platform
- Qdrant for vector database
- vLLM team for inference optimization
- Hugging Face for TEI services
