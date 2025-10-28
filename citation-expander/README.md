# Citation Expander for Ask-MaaS

A microservice that enhances the Ask-MaaS stack by fetching and processing cited sources from articles to improve model context and response quality.

## Features

- **Smart URL Fetching**: Fetches cited URLs with configurable allowlist filtering, canonicalization, and size limits
- **Multi-format Support**: Parses HTML, Markdown, PDF, and GitHub repositories
- **Semantic Search**: Uses TEI embeddings and Qdrant vector database for citation retrieval
- **Context Expansion**: Enriches LLM context with relevant citation snippets
- **Async Processing**: Redis RQ worker for background citation processing
- **TTL Management**: Automatic cleanup of expired citations
- **Production Ready**: Kubernetes manifests, health checks, and Prometheus metrics

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌───────────┐
│  Ask-MaaS   │────▶│  Citation    │────▶│   Redis   │
│     API     │     │  Expander    │     │    RQ     │
└─────────────┘     └──────────────┘     └───────────┘
                            │                    │
                            ▼                    ▼
                    ┌──────────────┐     ┌───────────┐
                    │     TEI      │     │  External │
                    │  Embeddings  │     │   URLs    │
                    └──────────────┘     └───────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │   Qdrant     │
                    │ Vector Store │
                    └──────────────┘
```

## Quick Start

### Local Development

```bash
# Install dependencies
make install-dev

# Start development services
make dev-env

# Run API server
make run-api

# In another terminal, run worker
make run-worker

# Test the service
curl http://localhost:8000/healthz
```

### Docker Deployment

```bash
# Build and run with Docker
make docker-build
make docker-run
```

### Kubernetes/OpenShift Deployment

```bash
# Deploy to OpenShift
make openshift-deploy

# Or deploy to vanilla Kubernetes
make k8s-apply

# Check deployment status
make logs
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `TEI_URL` | Text Embeddings Inference URL | `http://tei-embeddings:8080` |
| `QDRANT_URL` | Qdrant vector database URL | `http://qdrant:6333` |
| `RERANKER_URL` | BGE Reranker URL (optional) | `http://tei-reranker:8080` |
| `CITATION_TTL_DAYS` | Citation TTL in days | `7` |
| `GITHUB_TOKEN` | GitHub API token (optional) | - |
| `LOG_LEVEL` | Logging level | `INFO` |

### URL Allowlist

Configure allowed domains in `k8s/configmap.yaml`:

```yaml
patterns:
  - "^https?://(www\\.)?github\\.com/"
  - "^https?://(www\\.)?docs\\."
  # Add more patterns...
```

## API Endpoints

### Health Check
```bash
GET /healthz
```

### Metrics
```bash
GET /metrics
```

### Enqueue Citation
```bash
POST /enqueue?url=<url>&parent_doc_id=<doc_id>&parent_chunk_id=<chunk_id>
```

## Integration with Ask-MaaS

### 1. Install the Orchestrator Patch

```bash
# Copy patch to ask-maas-api
cp -r ask_maas_orchestrator_patch ../ask-maas-api/
```

### 2. Update Your Chat Handler

```python
from ask_maas_orchestrator_patch import expand_context

# In your chat handler:
async def enhanced_chat(query: str, base_chunks: List[Dict]):
    # Expand context with citations
    citation_snippets, metadata = expand_context(
        query=query,
        base_chunks=base_chunks,
        timeout_ms=800  # 800ms budget
    )
    
    # Add citations to context
    enriched_context = build_context(base_chunks, citation_snippets)
    
    # Generate response
    response = await generate_llm_response(query, enriched_context)
    return response
```

### 3. Deploy Services

```bash
# Deploy citation-expander
kubectl apply -f citation-expander/k8s/

# Update ask-maas-api deployment to include patch
kubectl rollout restart deployment/ask-maas-api
```

## Development

### Running Tests

```bash
# Run all tests with coverage
make test

# Run specific test file
pytest tests/test_worker.py -v

# Run with debugging
pytest tests/ -v -s --pdb
```

### Code Quality

```bash
# Format code
make format

# Run linters
make lint

# Type checking
mypy app/ worker/ libs/
```

## Monitoring

### Prometheus Metrics

- `citation_fetched_ok_total`: Successfully fetched citations
- `citation_fetched_err_total`: Failed citation fetches
- `citation_embedded_ok_total`: Successfully embedded citations
- `citation_size_bytes`: Size distribution of fetched content
- `citation_queue_depth`: Current RQ queue depth

### Grafana Dashboard

Import the dashboard from `k8s/grafana-dashboard.json` (create if needed).

### Alerts

Configured alerts in `k8s/cron-ttl.yaml`:
- High error rate (>10% for 5 minutes)
- Large queue backlog (>100 items for 10 minutes)
- Service down (no response for 2 minutes)

## Troubleshooting

### Check Service Health

```bash
# Check pods
kubectl get pods -l app=citation-expander -n ask-maas

# Check logs
kubectl logs -l app=citation-expander -n ask-maas --tail=100

# Check worker specifically
kubectl logs -l app=citation-expander -c worker -n ask-maas
```

### Common Issues

1. **Redis Connection Failed**
   - Verify Redis is running: `kubectl get svc redis -n ask-maas`
   - Check network policies allow connection

2. **TEI/Qdrant Unavailable**
   - Ensure services are deployed and running
   - Verify service discovery works: `kubectl exec -it <pod> -- nslookup tei-embeddings`

3. **High Memory Usage**
   - Adjust `MAX_CONTENT_SIZE` in worker/jobs.py
   - Increase resource limits in deployment.yaml

4. **Slow Processing**
   - Check if reranker is available and responsive
   - Monitor queue depth with `make metrics`
   - Scale workers: `kubectl scale deployment citation-expander --replicas=3`

## License

MIT

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## TODOs

- [ ] Add support for more document formats (DOCX, RTF)
- [ ] Implement citation quality scoring
- [ ] Add caching layer for frequently accessed citations
- [ ] Create Grafana dashboard template
- [ ] Add OpenTelemetry tracing
- [ ] Implement rate limiting per domain
- [ ] Add support for authenticated sources (behind login)
- [ ] Create Helm chart for easier deployment
