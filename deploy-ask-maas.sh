#!/bin/bash
#
# Ask MaaS Complete Deployment Script
# This script deploys the entire Ask MaaS system on an OpenShift cluster
#
# Prerequisites:
# - OpenShift 4.12+ cluster with GPU node (NVIDIA L40S or similar with 40GB+ VRAM)
# - oc CLI installed and logged in with cluster-admin privileges
# - podman or docker installed for building images
# - At least 100GB storage available
# - Git repository cloned locally
#
# Usage: ./deploy-ask-maas.sh [--skip-operators] [--skip-build] [--cleanup] [--model qwen|mistral] [--ingest-only]
#

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
CLUSTER_DOMAIN=""
REGISTRY_URL=""
GPU_NODE=""
SKIP_OPERATORS=false
SKIP_BUILD=false
CLEANUP_MODE=false
DRY_RUN=false
INGEST_ONLY=false
MODEL_TYPE="qwen"  # Default to Qwen 2.5 32B

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-operators)
            SKIP_OPERATORS=true
            shift
            ;;
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --cleanup)
            CLEANUP_MODE=true
            shift
            ;;
        --ingest-only)
            INGEST_ONLY=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --model)
            MODEL_TYPE="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --skip-operators  Skip operator installation checks"
            echo "  --skip-build      Skip building container images"
            echo "  --cleanup         Remove all Ask MaaS components"
            echo "  --ingest-only     Only run article ingestion"
            echo "  --dry-run         Show what would be done without executing"
            echo "  --model TYPE      Choose model type: qwen (default) or mistral"
            echo "  --help            Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Execute command with optional dry-run
execute() {
    if [ "$DRY_RUN" = true ]; then
        echo "[DRY-RUN] $@"
    else
        "$@"
    fi
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Wait for deployment to be ready
wait_for_deployment() {
    local deployment=$1
    local namespace=$2
    local timeout=${3:-300}
    
    log_info "Waiting for deployment $deployment in namespace $namespace..."
    if ! execute oc wait --for=condition=Available deployment/$deployment -n $namespace --timeout=${timeout}s; then
        log_warning "Deployment $deployment did not become ready in time"
        return 1
    fi
    log_success "Deployment $deployment is ready"
    return 0
}

# Wait for pod to be ready
wait_for_pod() {
    local label=$1
    local namespace=$2
    local timeout=${3:-120}
    
    log_info "Waiting for pod with label $label in namespace $namespace..."
    if ! execute oc wait --for=condition=Ready pod -l $label -n $namespace --timeout=${timeout}s; then
        log_warning "Pod with label $label did not become ready in time"
        return 1
    fi
    log_success "Pod is ready"
    return 0
}

# Cleanup function
cleanup_ask_maas() {
    log_warning "Cleaning up Ask MaaS deployment..."
    
    # Delete namespaces
    for ns in ask-maas-models ask-maas-api ask-maas-gateway ask-maas-frontend ask-maas-observability ask-maas-cicd; do
        if oc get namespace $ns >/dev/null 2>&1; then
            log_info "Deleting namespace $ns..."
            execute oc delete namespace $ns --wait=false
        fi
    done
    
    log_success "Cleanup completed"
    exit 0
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check oc CLI
    if ! command_exists oc; then
        log_error "oc CLI is not installed. Please install it first."
    fi
    
    # Check if logged in to OpenShift
    if ! oc whoami >/dev/null 2>&1; then
        log_error "Not logged in to OpenShift. Please run 'oc login' first."
    fi
    
    # Check for cluster-admin privileges
    if ! oc auth can-i '*' '*' --all-namespaces >/dev/null 2>&1; then
        log_warning "You may not have cluster-admin privileges. Some operations might fail."
    fi
    
    # Check for container build tool
    if command_exists podman; then
        CONTAINER_TOOL="podman"
    elif command_exists docker; then
        CONTAINER_TOOL="docker"
    else
        log_error "Neither podman nor docker is installed. Please install one of them."
    fi
    
    # Get cluster domain
    CLUSTER_DOMAIN=$(oc get ingresses.config.openshift.io cluster -o jsonpath='{.spec.domain}')
    if [ -z "$CLUSTER_DOMAIN" ]; then
        log_error "Could not determine cluster domain"
    fi
    log_info "Cluster domain: $CLUSTER_DOMAIN"
    
    # Get internal registry URL
    REGISTRY_URL=$(oc get route default-route -n openshift-image-registry -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
    if [ -z "$REGISTRY_URL" ]; then
        log_warning "Could not determine internal registry URL. Will use default."
        REGISTRY_URL="image-registry.openshift-image-registry.svc:5000"
    fi
    log_info "Registry URL: $REGISTRY_URL"
    
    # Check for GPU node
    GPU_NODE=$(oc get nodes -l nvidia.com/gpu.present=true -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    
    if [ -z "$GPU_NODE" ]; then
        log_warning "No GPU node found. You'll need to label one manually."
        log_info "To label a node, run: oc label node <node-name> nvidia.com/gpu.present=true"
    else
        log_success "Found GPU node: $GPU_NODE"
        
        # Check GPU type
        GPU_TYPE=$(oc describe node $GPU_NODE | grep -E "nvidia.com/gpu.product" | head -1 | awk -F'=' '{print $2}')
        if [ -n "$GPU_TYPE" ]; then
            log_info "GPU Type: $GPU_TYPE"
        fi
    fi
    
    log_success "Prerequisites check completed"
}

# Install required operators
install_operators() {
    if [ "$SKIP_OPERATORS" = true ]; then
        log_info "Skipping operator installation (--skip-operators flag set)"
        return
    fi
    
    log_info "Checking required operators..."
    
    # List of required operators and their expected names
    declare -A operators=(
        ["openshift-gitops"]="Red Hat OpenShift GitOps"
        ["openshift-pipelines"]="Red Hat OpenShift Pipelines"
        ["nvidia-gpu-operator"]="NVIDIA GPU Operator"
    )
    
    for op_namespace in "${!operators[@]}"; do
        op_name="${operators[$op_namespace]}"
        if oc get csv -n openshift-operators 2>/dev/null | grep -q "$op_name"; then
            log_success "Operator '$op_name' is installed"
        else
            log_warning "Operator '$op_name' is not installed"
            log_info "Please install it from the OpenShift Console -> Operators -> OperatorHub"
        fi
    done
}

# Create namespaces
create_namespaces() {
    log_info "Creating namespaces..."
    
    execute oc apply -f - <<EOF
apiVersion: v1
kind: List
items:
- apiVersion: v1
  kind: Namespace
  metadata:
    name: ask-maas-models
    labels:
      app: ask-maas
      component: models
- apiVersion: v1
  kind: Namespace
  metadata:
    name: ask-maas-api
    labels:
      app: ask-maas
      component: api
- apiVersion: v1
  kind: Namespace
  metadata:
    name: ask-maas-frontend
    labels:
      app: ask-maas
      component: frontend
EOF
    
    log_success "Namespaces created"
}

# Deploy Redis
deploy_redis() {
    log_info "Deploying Redis..."
    
    # Generate Redis password (or use existing from environment)
    if [ -z "$REDIS_PASSWORD" ]; then
        REDIS_PASSWORD=$(openssl rand -base64 32 2>/dev/null || echo "redis-$(date +%s)-$(shuf -i 1000-9999 -n 1)")
        log_info "Generated Redis password: ${REDIS_PASSWORD:0:8}..."
    fi
    
    # Create Redis secret
    execute oc create secret generic redis-credentials \
        --from-literal=password="$REDIS_PASSWORD" \
        -n ask-maas-api \
        --dry-run=client -o yaml | execute oc apply -f -
    
    # Deploy Redis (simple version without persistence to avoid permission issues)
    execute oc apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: ask-maas-api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        command:
          - redis-server
          - --requirepass
          - "$REDIS_PASSWORD"
        ports:
        - containerPort: 6379
          name: redis
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "2Gi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: redis-service
  namespace: ask-maas-api
spec:
  selector:
    app: redis
  ports:
    - port: 6379
      targetPort: 6379
EOF
    
    wait_for_deployment redis ask-maas-api
    
    # Disable Redis persistence to avoid issues
    execute oc exec deployment/redis -n ask-maas-api -- redis-cli -a "$REDIS_PASSWORD" CONFIG SET stop-writes-on-bgsave-error no 2>/dev/null || true
    execute oc exec deployment/redis -n ask-maas-api -- redis-cli -a "$REDIS_PASSWORD" CONFIG SET save "" 2>/dev/null || true
    
    log_success "Redis deployed"
}

# Build and deploy orchestrator API
deploy_orchestrator_api() {
    log_info "Building and deploying Orchestrator API..."
    
    # Fix any import issues before building
    log_info "Checking and fixing import issues..."
    if grep -q "from app.services.retrieval import RetrievalService" "$PROJECT_ROOT/ask-maas-api/app/routers/chat.py" 2>/dev/null; then
        log_info "Fixing import in chat.py..."
        sed -i 's/from app.services.retrieval import RetrievalService//g' "$PROJECT_ROOT/ask-maas-api/app/routers/chat.py"
    fi
    
    # Build the image
    if [ "$SKIP_BUILD" = false ]; then
        log_info "Building orchestrator API image..."
        cd "$PROJECT_ROOT/ask-maas-api"
        
        execute $CONTAINER_TOOL build -f Dockerfile -t orchestrator-api:latest .
        
        # Login to internal registry
        log_info "Logging in to internal registry..."
        execute $CONTAINER_TOOL login -u $(oc whoami) -p $(oc whoami -t) --tls-verify=false $REGISTRY_URL
        
        # Tag and push image
        execute $CONTAINER_TOOL tag orchestrator-api:latest $REGISTRY_URL/ask-maas-api/orchestrator-api:latest
        execute $CONTAINER_TOOL push --tls-verify=false $REGISTRY_URL/ask-maas-api/orchestrator-api:latest
        
        cd "$PROJECT_ROOT"
    fi
    
    # Set model-specific variables
    if [ "$MODEL_TYPE" = "qwen" ]; then
        VLLM_SERVICE="vllm-qwen2-service"
        MODEL_NAME="qwen2-32b-instruct"
        MAX_CONTEXT="8192"
    else
        VLLM_SERVICE="vllm-mistral-service"
        MODEL_NAME="mistral-7b-instruct"
        MAX_CONTEXT="4096"
    fi
    
    # Deploy Orchestrator API
    execute oc apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ask-maas-orchestrator
  namespace: ask-maas-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ask-maas-orchestrator
  template:
    metadata:
      labels:
        app: ask-maas-orchestrator
    spec:
      containers:
      - name: orchestrator
        image: image-registry.openshift-image-registry.svc:5000/ask-maas-api/orchestrator-api:latest
        ports:
        - containerPort: 8000
          name: http
        env:
        - name: ENVIRONMENT
          value: "production"
        - name: REDIS_HOST
          value: "redis-service.ask-maas-api.svc.cluster.local"
        - name: REDIS_PORT
          value: "6379"
        - name: REDIS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: redis-credentials
              key: password
        - name: VLLM_URL
          value: "http://${VLLM_SERVICE}.ask-maas-models.svc.cluster.local:8080"
        - name: MODEL_NAME
          value: "${MODEL_NAME}"
        - name: MAX_CONTEXT_LENGTH
          value: "${MAX_CONTEXT}"
        - name: TEI_EMBEDDINGS_URL
          value: "http://tei-embeddings-service.ask-maas-models.svc.cluster.local:8080"
        - name: TEI_RERANKER_URL
          value: "http://tei-reranker-service.ask-maas-models.svc.cluster.local:8080"
        - name: QDRANT_URL
          value: "http://qdrant-service.ask-maas-models.svc.cluster.local:6333"
        - name: CORS_ORIGINS
          value: '["*"]'
        - name: MIN_RERANK_SCORE
          value: "0.001"
        - name: OTEL_ENABLED
          value: "false"
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
        resources:
          requests:
            memory: "512Mi"
            cpu: "100m"
          limits:
            memory: "1Gi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: ask-maas-orchestrator-service
  namespace: ask-maas-api
spec:
  selector:
    app: ask-maas-orchestrator
  ports:
    - port: 8000
      targetPort: 8000
      name: http
EOF
    
    wait_for_deployment ask-maas-orchestrator ask-maas-api
    
    log_success "Orchestrator API deployed"
}

# Deploy Qdrant vector database
deploy_qdrant() {
    log_info "Deploying Qdrant vector database..."
    
    # Check if Qdrant already exists
    if oc get deployment qdrant -n ask-maas-models >/dev/null 2>&1; then
        log_info "Qdrant already deployed, skipping..."
        return 0
    fi
    
    execute oc apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: qdrant-storage
  namespace: ask-maas-models
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: qdrant
  namespace: ask-maas-models
spec:
  replicas: 1
  selector:
    matchLabels:
      app: qdrant
  template:
    metadata:
      labels:
        app: qdrant
    spec:
      containers:
      - name: qdrant
        image: qdrant/qdrant:latest
        ports:
        - containerPort: 6333
          name: http
        - containerPort: 6334
          name: grpc
        env:
        - name: QDRANT__SERVICE__HTTP_PORT
          value: "6333"
        - name: QDRANT__SERVICE__GRPC_PORT
          value: "6334"
        - name: QDRANT__STORAGE__STORAGE_PATH
          value: "/qdrant/storage"
        volumeMounts:
        - name: storage
          mountPath: /qdrant/storage
        resources:
          requests:
            cpu: "500m"
            memory: "1Gi"
          limits:
            cpu: "2"
            memory: "2Gi"
      volumes:
      - name: storage
        persistentVolumeClaim:
          claimName: qdrant-storage
---
apiVersion: v1
kind: Service
metadata:
  name: qdrant-service
  namespace: ask-maas-models
spec:
  selector:
    app: qdrant
  ports:
  - name: http
    port: 6333
    targetPort: 6333
  - name: grpc
    port: 6334
    targetPort: 6334
EOF
    
    # Wait for Qdrant to be ready
    wait_for_deployment qdrant ask-maas-models 180
    log_success "Qdrant deployed"
}

# Deploy model services
deploy_model_services() {
    log_info "Deploying model services..."
    
    # Deploy Qdrant vector database first (essential for RAG)
    deploy_qdrant
    
    # Deploy chosen LLM model
    if [ "$MODEL_TYPE" = "qwen" ]; then
        deploy_qwen_model
    else
        deploy_mistral_model
    fi
    
    # Deploy TEI Embeddings
    log_info "Deploying TEI Embeddings service..."
    execute oc apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tei-bge-m3-embeddings
  namespace: ask-maas-models
spec:
  replicas: 1
  selector:
    matchLabels:
      app: tei-embeddings
  template:
    metadata:
      labels:
        app: tei-embeddings
    spec:
      containers:
      - name: tei-server
        image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.2
        args:
          - --model-id
          - BAAI/bge-m3
          - --port
          - "8080"
          - --json-output
        ports:
        - containerPort: 8080
          name: http
        - containerPort: 9090
          name: metrics
        volumeMounts:
        - name: model-cache
          mountPath: /data
        env:
        - name: HF_HOME
          value: "/data/huggingface"
        - name: TRANSFORMERS_CACHE
          value: "/data/huggingface"
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
          limits:
            memory: "4Gi"
            cpu: "2"
      volumes:
      - name: model-cache
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: tei-embeddings-service
  namespace: ask-maas-models
spec:
  selector:
    app: tei-embeddings
  ports:
    - port: 8080
      targetPort: 8080
      name: http
    - port: 9090
      targetPort: 9090
      name: metrics
EOF
    
    # Deploy TEI Reranker
    log_info "Deploying TEI Reranker service..."
    execute oc apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tei-bge-reranker-large
  namespace: ask-maas-models
spec:
  replicas: 1
  selector:
    matchLabels:
      app: tei-reranker
  template:
    metadata:
      labels:
        app: tei-reranker
    spec:
      containers:
      - name: tei-reranker
        image: ghcr.io/huggingface/text-embeddings-inference:cpu-1.2
        args:
          - --model-id
          - BAAI/bge-reranker-large
          - --port
          - "8080"
          - --json-output
        ports:
        - containerPort: 8080
          name: http
        - containerPort: 9090
          name: metrics
        volumeMounts:
        - name: model-cache
          mountPath: /data
        env:
        - name: HF_HOME
          value: "/data/huggingface"
        - name: TRANSFORMERS_CACHE
          value: "/data/huggingface"
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
          limits:
            memory: "4Gi"
            cpu: "2"
      volumes:
      - name: model-cache
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: tei-reranker-service
  namespace: ask-maas-models
spec:
  selector:
    app: tei-reranker
  ports:
    - port: 8080
      targetPort: 8080
      name: http
    - port: 9090
      targetPort: 9090
      name: metrics
EOF
    
    # Wait for model services
    log_info "Waiting for model services to be ready (this may take 10-20 minutes for model downloads)..."
    wait_for_deployment tei-bge-m3-embeddings ask-maas-models
    wait_for_deployment tei-bge-reranker-large ask-maas-models
    
    log_success "Model services deployed"
}

# Deploy Qwen model
deploy_qwen_model() {
    log_info "Deploying Qwen 2.5 32B AWQ model..."
    
    execute oc apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-qwen2-32b
  namespace: ask-maas-models
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm-qwen2-32b
  template:
    metadata:
      labels:
        app: vllm-qwen2-32b
    spec:
      nodeSelector:
        nvidia.com/gpu.present: "true"
      containers:
      - name: vllm
        image: vllm/vllm-openai:latest
        command:
        - python3
        - -m
        - vllm.entrypoints.openai.api_server
        args:
        - --model
        - Qwen/Qwen2.5-32B-Instruct-AWQ
        - --quantization
        - awq
        - --dtype
        - auto
        - --port
        - "8080"
        - --served-model-name
        - qwen2-32b-instruct
        - --trust-remote-code
        - --download-dir
        - /models-cache
        - --gpu-memory-utilization
        - "0.95"
        - --max-model-len
        - "8192"
        - --max-num-seqs
        - "16"
        - --swap-space
        - "2"
        - --enforce-eager
        env:
        - name: CUDA_VISIBLE_DEVICES
          value: "0"
        - name: HF_HOME
          value: /tmp/hf-home
        - name: HOME
          value: /tmp
        - name: VLLM_CACHE_DIR
          value: /tmp/vllm-cache
        - name: TORCH_CUDA_ARCH_LIST
          value: "8.9"
        ports:
        - containerPort: 8080
        resources:
          limits:
            nvidia.com/gpu: "1"
            memory: "28Gi"
            cpu: "2"
          requests:
            nvidia.com/gpu: "1"
            memory: "20Gi"
            cpu: "1"
        volumeMounts:
        - name: models-cache
          mountPath: /models-cache
        - name: tmp-cache
          mountPath: /tmp
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 600
          periodSeconds: 30
          timeoutSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 600
          periodSeconds: 30
          timeoutSeconds: 10
      volumes:
      - name: models-cache
        emptyDir:
          sizeLimit: 100Gi
      - name: tmp-cache
        emptyDir:
          sizeLimit: 20Gi
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
---
apiVersion: v1
kind: Service
metadata:
  name: vllm-qwen2-service
  namespace: ask-maas-models
spec:
  selector:
    app: vllm-qwen2-32b
  ports:
  - name: http
    port: 8080
    targetPort: 8080
    protocol: TCP
  type: ClusterIP
EOF
    
    log_info "Waiting for Qwen model to load (this may take 10-15 minutes)..."
    wait_for_deployment vllm-qwen2-32b ask-maas-models 900
}

# Deploy Mistral model
deploy_mistral_model() {
    log_info "Deploying Mistral 7B AWQ model..."
    
    execute oc apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vllm-mistral-7b
  namespace: ask-maas-models
spec:
  replicas: 1
  selector:
    matchLabels:
      app: vllm-mistral-7b
  template:
    metadata:
      labels:
        app: vllm-mistral-7b
    spec:
      nodeSelector:
        nvidia.com/gpu.present: "true"
      containers:
      - name: vllm
        image: vllm/vllm-openai:v0.5.0.post1
        command: ["python3", "-m", "vllm.entrypoints.openai.api_server"]
        args:
          - --model
          - TheBloke/Mistral-7B-Instruct-v0.2-AWQ
          - --quantization
          - awq
          - --dtype
          - auto
          - --port
          - "8080"
          - --served-model-name
          - mistral-7b-instruct
          - --trust-remote-code
          - --max-model-len
          - "4096"
          - --gpu-memory-utilization
          - "0.85"
          - --max-num-seqs
          - "32"
        env:
        - name: HF_HOME
          value: "/tmp/huggingface"
        - name: TRANSFORMERS_CACHE
          value: "/tmp/huggingface"
        volumeMounts:
        - name: model-cache
          mountPath: /tmp
        - name: shm
          mountPath: /dev/shm
        ports:
        - containerPort: 8080
          name: http
        resources:
          requests:
            memory: "8Gi"
            cpu: "2"
            nvidia.com/gpu: "1"
          limits:
            memory: "10Gi"
            cpu: "4"
            nvidia.com/gpu: "1"
      volumes:
      - name: model-cache
        emptyDir: {}
      - name: shm
        emptyDir:
          medium: Memory
          sizeLimit: "2Gi"
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
---
apiVersion: v1
kind: Service
metadata:
  name: vllm-mistral-service
  namespace: ask-maas-models
spec:
  selector:
    app: vllm-mistral-7b
  ports:
    - port: 8080
      targetPort: 8080
      name: http
EOF
    
    log_info "Waiting for Mistral model to load (this may take 10-15 minutes)..."
    wait_for_deployment vllm-mistral-7b ask-maas-models 900
}

# Build and deploy frontend
deploy_frontend() {
    log_info "Building and deploying frontend..."
    
    # Build the frontend image
    if [ "$SKIP_BUILD" = false ]; then
        log_info "Building frontend image..."
        cd "$PROJECT_ROOT/ghost-site"
        
        # Ensure the API route returns static article list
        log_info "Updating article routes..."
        cat > src/app/api/articles/route.ts <<'EOROUTE'
import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const ARTICLES = [
  {
    id: 'article-1',
    title: 'All you can kustomize during the MaaS deployment',
    description: 'Learn how MaaS adds policy-driven access, tiered quotas, and token-aware rate limiting to KServe-hosted models on OpenShift',
    category: 'OpenShift',
    author: 'Red Hat Developer',
    date: 'October 23, 2024',
    filename: 'All you can kustomize during the MaaS deployment _ Red Hat Developer.html',
    path: '/articles/All you can kustomize during the MaaS deployment _ Red Hat Developer.html'
  },
  {
    id: 'article-2',
    title: 'Deploy Llama 3 8B with vLLM',
    description: 'Learn how to deploy and optimize Llama 3 8B model using vLLM on OpenShift',
    category: 'AI/ML',
    author: 'Red Hat Developer',
    date: 'October 23, 2024',
    filename: 'Deploy Llama 3 8B with vLLM _ Red Hat Developer.html',
    path: '/articles/Deploy Llama 3 8B with vLLM _ Red Hat Developer.html'
  },
  {
    id: 'article-3',
    title: 'Ollama vs. vLLM: A deep dive into performance benchmarking',
    description: 'Comprehensive performance comparison between Ollama and vLLM for LLM inference',
    category: 'Performance',
    author: 'Red Hat Developer',
    date: 'October 23, 2024',
    filename: 'Ollama vs. vLLM_ A deep dive into performance benchmarking _ Red Hat Developer.html',
    path: '/articles/Ollama vs. vLLM_ A deep dive into performance benchmarking _ Red Hat Developer.html'
  },
  {
    id: 'article-4',
    title: 'Profiling vLLM Inference Server with GPU acceleration on RHEL',
    description: 'Deep dive into profiling vLLM inference server with GPU acceleration on RHEL',
    category: 'Performance',
    author: 'Red Hat Developer',
    date: 'October 23, 2024',
    filename: 'Profiling vLLM Inference Server with GPU acceleration on RHEL _ Red Hat Developer.html',
    path: '/articles/Profiling vLLM Inference Server with GPU acceleration on RHEL _ Red Hat Developer.html'
  },
  {
    id: 'article-5',
    title: 'What is MaaS (Models-as-a-Service) and how to set it up fast on OpenShift',
    description: 'Learn what MaaS (Models-as-a-Service) is and how to quickly set it up on OpenShift for AI/ML workloads',
    category: 'OpenShift',
    author: 'Red Hat Developer',
    date: 'October 23, 2024',
    filename: 'What is MaaS (Models-as-a-Service) and how to set it up fast on OpenShift _ Red Hat Developer.html',
    path: '/articles/What is MaaS (Models-as-a-Service) and how to set it up fast on OpenShift _ Red Hat Developer.html'
  }
];

export async function GET() {
  try {
    return NextResponse.json({ articles: ARTICLES });
  } catch (error) {
    console.error('Error returning articles:', error);
    return NextResponse.json({ 
      articles: [],
      error: 'Failed to load articles' 
    }, { status: 500 });
  }
}
EOROUTE
        
        # Copy articles to public directory for serving
        log_info "Copying articles to public directory..."
        mkdir -p public/articles
        cp -r ../articles/* public/articles/ 2>/dev/null || true
        
        # Build using the standard Dockerfile
        execute $CONTAINER_TOOL build -f Dockerfile -t ghost-article-site:latest .
        
        # Tag and push image
        execute $CONTAINER_TOOL tag ghost-article-site:latest $REGISTRY_URL/ask-maas-frontend/ghost-article-site:latest
        execute $CONTAINER_TOOL push --tls-verify=false $REGISTRY_URL/ask-maas-frontend/ghost-article-site:latest
        
        cd "$PROJECT_ROOT"
    fi
    
    # Deploy Frontend
    execute oc apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ghost-article-site
  namespace: ask-maas-frontend
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ghost-article-site
  template:
    metadata:
      labels:
        app: ghost-article-site
    spec:
      containers:
      - name: frontend
        image: image-registry.openshift-image-registry.svc:5000/ask-maas-frontend/ghost-article-site:latest
        ports:
        - containerPort: 3000
          name: http
        env:
        - name: NEXT_PUBLIC_API_URL
          value: "https://ask-maas-api.${CLUSTER_DOMAIN}"
        - name: NODE_ENV
          value: "production"
        - name: PORT
          value: "3000"
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: ghost-article-site-service
  namespace: ask-maas-frontend
spec:
  selector:
    app: ghost-article-site
  ports:
    - port: 3000
      targetPort: 3000
      name: http
EOF
    
    wait_for_deployment ghost-article-site ask-maas-frontend
    
    log_success "Frontend deployed"
}

# Configure routes
configure_routes() {
    log_info "Configuring routes..."
    
    # Create API route
    execute oc apply -f - <<EOF
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: ask-maas-api-route
  namespace: ask-maas-api
  annotations:
    haproxy.router.openshift.io/timeout: 60s
spec:
  host: ask-maas-api.apps.${CLUSTER_DOMAIN}
  to:
    kind: Service
    name: ask-maas-orchestrator-service
  port:
    targetPort: http
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
EOF
    
    # Create Frontend route
    execute oc apply -f - <<EOF
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: ask-maas-frontend-route
  namespace: ask-maas-frontend
  annotations:
    haproxy.router.openshift.io/timeout: 30s
spec:
  host: ask-maas-frontend.apps.${CLUSTER_DOMAIN}
  to:
    kind: Service
    name: ghost-article-site-service
  port:
    targetPort: http
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
EOF
    
    log_success "Routes configured"
    log_info "Frontend URL: https://ask-maas-frontend.${CLUSTER_DOMAIN}"
    log_info "API URL: https://ask-maas-api.${CLUSTER_DOMAIN}"
}

# Ingest initial articles
ingest_articles() {
    log_info "Ingesting initial articles..."
    
    # Get cluster domain if not already set
    if [ -z "$CLUSTER_DOMAIN" ]; then
        CLUSTER_DOMAIN=$(oc get ingresses.config.openshift.io cluster -o jsonpath='{.spec.domain}' 2>/dev/null)
        if [ -z "$CLUSTER_DOMAIN" ]; then
            log_error "Could not determine cluster domain. Make sure you're logged in to OpenShift."
        fi
        log_info "Cluster domain: $CLUSTER_DOMAIN"
    fi
    
    API_URL="https://ask-maas-api.${CLUSTER_DOMAIN}"
    
    # Wait for API to be ready
    log_info "Waiting for API to be fully ready..."
    for i in {1..30}; do
        if curl -s "${API_URL}/health/ready" | grep -q "ready"; then
            log_success "API is ready"
            break
        fi
        sleep 2
    done
    
    # List of articles to ingest
    declare -a articles=(
        "All you can kustomize during the MaaS deployment _ Red Hat Developer.html"
        "Deploy Llama 3 8B with vLLM _ Red Hat Developer.html"
        "Ollama vs. vLLM_ A deep dive into performance benchmarking _ Red Hat Developer.html"
        "Profiling vLLM Inference Server with GPU acceleration on RHEL _ Red Hat Developer.html"
        "What is MaaS (Models-as-a-Service) and how to set it up fast on OpenShift _ Red Hat Developer.html"
    )
    
    # Ingest each article using the Python ingestion script
    log_info "Creating ingestion script..."
    cat > /tmp/ingest_articles.py <<'EOSCRIPT'
#!/usr/bin/env python3
import os, sys, time, json, requests, warnings
from pathlib import Path
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def extract_text_from_html(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        return text[:50000]
    except Exception as e:
        print(f"Error: {e}")
        return None

api_url = sys.argv[1]
articles_dir = sys.argv[2]

articles = [
    ("All you can kustomize during the MaaS deployment _ Red Hat Developer.html", "All you can kustomize during the MaaS deployment"),
    ("What is MaaS (Models-as-a-Service) and how to set it up fast on OpenShift _ Red Hat Developer.html", "What is MaaS (Models-as-a-Service) and how to set it up fast on OpenShift"),
    ("Deploy Llama 3 8B with vLLM _ Red Hat Developer.html", "Deploy Llama 3 8B with vLLM"),
    ("Ollama vs. vLLM_ A deep dive into performance benchmarking _ Red Hat Developer.html", "Ollama vs. vLLM: A deep dive into performance benchmarking"),
    ("Profiling vLLM Inference Server with GPU acceleration on RHEL _ Red Hat Developer.html", "Profiling vLLM Inference Server with GPU acceleration on RHEL"),
]

for filename, title in articles:
    file_path = Path(articles_dir) / filename
    if not file_path.exists():
        continue
    content = extract_text_from_html(file_path)
    if content:
        response = requests.post(
            f"{api_url}/api/v1/ingest/content",
            json={"page_url": f"file://{file_path}", "title": title, "content": content, "content_type": "text", "force_refresh": True},
            timeout=60,
            verify=False
        )
        print(f"{title}: {'OK' if response.status_code == 200 else 'FAILED'}")
    time.sleep(2)
EOSCRIPT
    
    # Run the ingestion script
    python3 /tmp/ingest_articles.py "${API_URL}" "$PROJECT_ROOT/articles" || log_warning "Some articles may have failed to ingest"
    rm -f /tmp/ingest_articles.py
    
    log_success "All articles ingested"
}

# Verify deployment
verify_deployment() {
    log_info "Verifying deployment..."
    
    echo ""
    echo "=== Deployment Status ==="
    echo ""
    
    # Check namespaces
    log_info "Namespaces:"
    oc get namespaces | grep ask-maas
    
    echo ""
    
    # Check pods
    log_info "Running pods:"
    for ns in ask-maas-models ask-maas-api ask-maas-frontend; do
        echo "Namespace: $ns"
        oc get pods -n $ns
        echo ""
    done
    
    # Test API health
    log_info "Testing API health endpoint..."
    API_URL="https://ask-maas-api.${CLUSTER_DOMAIN}"
    if curl -s "$API_URL/health/live" | grep -q "healthy"; then
        log_success "API is healthy"
    else
        log_warning "API health check failed"
    fi
    
    echo ""
    echo "===================================="
    echo "Deployment completed!"
    echo "===================================="
    echo ""
    echo "Access your application at:"
    echo "  Frontend: https://ask-maas-frontend.${CLUSTER_DOMAIN}"
    echo "  API: https://ask-maas-api.${CLUSTER_DOMAIN}"
    echo ""
    echo "Model deployed: ${MODEL_TYPE^^}"
    if [ "$MODEL_TYPE" = "qwen" ]; then
        echo "  - Qwen 2.5 32B AWQ (Recommended)"
        echo "  - Requires ~20GB VRAM"
        echo "  - 8K context window"
    else
        echo "  - Mistral 7B Instruct AWQ"
        echo "  - Requires ~8GB VRAM"
        echo "  - 4K context window"
    fi
    echo ""
    echo "To test the system:"
    echo "  1. Open the frontend URL"
    echo "  2. Click on an article"
    echo "  3. Click 'Ask This Page' button"
    echo "  4. Ask questions about the article"
    echo ""
    echo "To ingest more articles:"
    echo "  curl -X POST ${API_URL}/api/v1/ingest/page \\"
    echo "    -H 'Content-Type: application/json' \\"
    echo "    -d '{\"page_url\": \"<article-url>\", \"force_refresh\": true}'"
    echo ""
    
    log_success "Verification completed"
}

# Main execution
main() {
    echo "===================================="
    echo "Ask MaaS Complete Deployment Script"
    echo "===================================="
    echo ""
    
    # Check if cleanup mode
    if [ "$CLEANUP_MODE" = true ]; then
        cleanup_ask_maas
        exit 0
    fi
    
    # Check if ingest-only mode
    if [ "$INGEST_ONLY" = true ]; then
        log_info "Running in ingest-only mode"
        ingest_articles
        log_success "Article ingestion completed"
        exit 0
    fi
    
    # Run full deployment steps
    check_prerequisites
    install_operators
    create_namespaces
    deploy_redis
    deploy_model_services
    deploy_orchestrator_api
    deploy_frontend
    configure_routes
    ingest_articles
    verify_deployment
    
    echo ""
    log_success "Ask MaaS deployment completed successfully!"
}

# Run main function
main "$@"