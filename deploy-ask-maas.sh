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
# Usage: ./deploy-ask-maas.sh [--skip-operators] [--skip-build] [--cleanup] [--model qwen|mistral]
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
    
    # Build the image
    if [ "$SKIP_BUILD" = false ]; then
        log_info "Building orchestrator API image..."
        cd "$PROJECT_ROOT/ask-maas-api"
        
        # Create simplified Dockerfile
        cat > Dockerfile.simple <<'EOF'
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Run the application
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF
        
        execute $CONTAINER_TOOL build -f Dockerfile.simple -t orchestrator-api:latest .
        
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

# Deploy model services
deploy_model_services() {
    log_info "Deploying model services..."
    
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
        
        # Create simplified Dockerfile
        cat > Dockerfile.simple <<EOF
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:18-alpine
WORKDIR /app
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

# Copy built application
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json

# Copy articles to static directory
RUN mkdir -p public/static-articles
COPY --chown=nextjs:nodejs articles/*.html public/static-articles/ 2>/dev/null || true
COPY --chown=nextjs:nodejs articles/*_files public/static-articles/ 2>/dev/null || true

USER nextjs
EXPOSE 3000

ENV NODE_ENV=production
ENV NEXT_PUBLIC_API_URL=https://ask-maas-api.apps.${CLUSTER_DOMAIN}

CMD ["npm", "start"]
EOF
        
        execute $CONTAINER_TOOL build -f Dockerfile.simple -t ghost-article-site:latest .
        
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
          value: "https://ask-maas-api.apps.${CLUSTER_DOMAIN}"
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
    log_info "Frontend URL: https://ask-maas-frontend.apps.${CLUSTER_DOMAIN}"
    log_info "API URL: https://ask-maas-api.apps.${CLUSTER_DOMAIN}"
}

# Ingest initial articles
ingest_articles() {
    log_info "Ingesting initial articles..."
    
    API_URL="https://ask-maas-api.apps.${CLUSTER_DOMAIN}"
    
    # Wait for API to be ready
    sleep 10
    
    # Ingest MIG article
    log_info "Ingesting MIG article..."
    curl -s -X POST "${API_URL}/api/v1/ingest/page" \
      -H "Content-Type: application/json" \
      -d "{
        \"page_url\": \"https://ask-maas-frontend.apps.${CLUSTER_DOMAIN}/static-articles/Dynamic%20GPU%20slicing%20with%20Red%20Hat%20OpenShift%20and%20NVIDIA%20MIG%20_%20Red%20Hat%20Developer.html\",
        \"force_refresh\": true
      }" || log_warning "Article ingestion failed"
    
    log_success "Articles ingested"
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
    API_URL="https://ask-maas-api.apps.${CLUSTER_DOMAIN}"
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
    echo "  Frontend: https://ask-maas-frontend.apps.${CLUSTER_DOMAIN}"
    echo "  API: https://ask-maas-api.apps.${CLUSTER_DOMAIN}"
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
    
    # Run deployment steps
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