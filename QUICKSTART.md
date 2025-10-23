# Ask MaaS Quick Start Guide

## 🚀 Deploy in 5 Minutes

### Prerequisites Check
```bash
# Check OpenShift access
oc whoami

# Check if you have GPU nodes
oc get nodes -l nvidia.com/gpu.present=true

# Check podman/docker
podman --version || docker --version
```

### 1. Clone and Deploy
```bash
# Clone the repository
git clone https://github.com/yourusername/ask-maas.git
cd ask-maas

# Deploy everything with one command
./deploy-ask-maas.sh

# Or deploy with Mistral model instead of Qwen
./deploy-ask-maas.sh --model mistral
```

### 2. Wait for Deployment (15-20 minutes)
The script will:
- ✅ Create namespaces
- ✅ Deploy vector database (Qdrant)
- ✅ Deploy Redis cache
- ✅ Deploy embedding service (TEI)
- ✅ Deploy LLM service (vLLM)
- ✅ Build and deploy API
- ✅ Build and deploy frontend
- ✅ Ingest all documentation
- ✅ Configure routes

### 3. Verify Deployment
```bash
# Run automated tests
./test-deployment.sh

# Or check manually
oc get pods -n ask-maas-api
oc get pods -n ask-maas-models
```

### 4. Access the System
The script will output your URLs:
```
Frontend: https://ask-maas-frontend.apps.your-cluster.com
API: https://ask-maas-api.apps.your-cluster.com
```

## 🎯 Common Tasks

### Re-ingest Articles
```bash
./deploy-ask-maas.sh --ingest-only
```

### Clean Reinstall
```bash
./deploy-ask-maas.sh --cleanup
./deploy-ask-maas.sh
```

### Deploy Without Building Images
```bash
./deploy-ask-maas.sh --skip-build
```

### Switch Models
```bash
# Deploy with Mistral-7B (faster, less memory)
./deploy-ask-maas.sh --model mistral

# Deploy with Qwen2.5-32B (better quality, more memory)
./deploy-ask-maas.sh --model qwen
```

## 🔍 Test the AI Assistant

1. **Open the Frontend**
   - Navigate to your frontend URL
   - Click on any article

2. **Ask Questions**
   Try these sample queries:
   - "How to customize rate limit policy?"
   - "What are the benefits of MaaS?"
   - "How to deploy Llama 3 with vLLM?"
   - "Compare Ollama vs vLLM performance"

3. **Test Global Context**
   The AI has knowledge of ALL articles, not just the current one!

## 🐛 Troubleshooting

### Pods Not Starting
```bash
# Check pod status
oc get pods -n ask-maas-api
oc describe pod <pod-name> -n ask-maas-api

# Check logs
oc logs -f deployment/ask-maas-orchestrator -n ask-maas-api
```

### Model Service Issues
```bash
# Check GPU allocation
oc describe pod -l app=vllm-mistral-7b -n ask-maas-models

# Check model logs
oc logs -f deployment/vllm-mistral-7b -n ask-maas-models
```

### Frontend Not Loading
```bash
# Check frontend logs
oc logs -f deployment/ghost-site -n ask-maas-api

# Restart frontend
oc rollout restart deployment/ghost-site -n ask-maas-api
```

### AI Not Responding
```bash
# Check CORS settings
oc set env deployment/ask-maas-orchestrator -n ask-maas-api \
  CORS_ORIGINS='["*"]'

# Restart orchestrator
oc rollout restart deployment/ask-maas-orchestrator -n ask-maas-api
```

## 📊 Resource Requirements

### Minimum Requirements
- **CPU**: 8 cores total
- **Memory**: 32GB total
- **GPU**: 1x NVIDIA GPU with 16GB+ VRAM
- **Storage**: 100GB

### Recommended Requirements
- **CPU**: 16 cores total
- **Memory**: 64GB total
- **GPU**: 1x NVIDIA A10G or better (24GB+ VRAM)
- **Storage**: 200GB

### Model Memory Requirements
| Model | GPU Memory | System Memory |
|-------|------------|---------------|
| Mistral-7B | 16GB | 24GB |
| Llama-3-8B | 16GB | 24GB |
| Mixtral-8x7B | 48GB | 64GB |
| Qwen2.5-32B | 64GB | 96GB |

## 🎉 Success Indicators

You know the deployment is successful when:
- ✅ All pods are Running (no CrashLoopBackOff)
- ✅ Frontend shows 5 articles
- ✅ Articles open with proper styling
- ✅ AI Assistant responds to queries
- ✅ Test script shows all tests passed

## 📚 Next Steps

1. **Read the Documentation**
   - [README.md](README.md) - Full system documentation
   - [ARCHITECTURE.md](docs/ARCHITECTURE.md) - Technical details

2. **Customize the System**
   - Add your own articles
   - Adjust model parameters
   - Configure rate limiting

3. **Monitor Performance**
   - Check Prometheus metrics
   - Review response times
   - Analyze token usage

## 🆘 Getting Help

- **Logs**: Always check logs first
- **Issues**: Open GitHub issue with logs
- **Community**: Join our Discord server

---

*Happy deploying! 🚀*
