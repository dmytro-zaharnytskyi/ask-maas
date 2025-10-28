.PHONY: help build test clean docker-build docker-push deploy undeploy logs dev install lint format

# Variables
DOCKER_REGISTRY ?= quay.io/askmaas
IMAGE_NAME ?= citation-expander
IMAGE_TAG ?= latest
NAMESPACE ?= ask-maas
PYTHON_VERSION = 3.11

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "Citation Expander - Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "${GREEN}%-20s${NC} %s\n", $$1, $$2}'

install: ## Install dependencies
	@echo "${YELLOW}Installing dependencies...${NC}"
	pip install --upgrade pip setuptools wheel
	pip install -r requirements.txt
	pip install -e .

install-dev: ## Install development dependencies
	@echo "${YELLOW}Installing development dependencies...${NC}"
	pip install --upgrade pip setuptools wheel
	pip install -r requirements.txt
	pip install -e ".[dev]"

test: ## Run tests with coverage
	@echo "${YELLOW}Running tests...${NC}"
	pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html

test-fast: ## Run tests without coverage
	@echo "${YELLOW}Running fast tests...${NC}"
	pytest tests/ -v -x

lint: ## Run linting checks
	@echo "${YELLOW}Running linters...${NC}"
	flake8 app/ worker/ libs/ tests/
	mypy app/ worker/ libs/ --ignore-missing-imports

format: ## Format code with black
	@echo "${YELLOW}Formatting code...${NC}"
	black app/ worker/ libs/ tests/

clean: ## Clean up generated files
	@echo "${YELLOW}Cleaning up...${NC}"
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache/ .coverage htmlcov/

build: clean ## Build Python package
	@echo "${GREEN}Building Python package...${NC}"
	python -m build

docker-build: ## Build Docker image
	@echo "${GREEN}Building Docker image...${NC}"
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .
	docker tag $(IMAGE_NAME):$(IMAGE_TAG) $(DOCKER_REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

docker-push: docker-build ## Push Docker image to registry
	@echo "${GREEN}Pushing Docker image...${NC}"
	docker push $(DOCKER_REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

docker-run: ## Run Docker container locally
	@echo "${GREEN}Running Docker container...${NC}"
	docker run --rm -it \
		-p 8000:8000 \
		-e REDIS_URL=redis://host.docker.internal:6379/0 \
		-e LOG_LEVEL=DEBUG \
		$(IMAGE_NAME):$(IMAGE_TAG)

# Kubernetes/OpenShift targets
k8s-create-namespace: ## Create namespace
	@echo "${GREEN}Creating namespace...${NC}"
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -

k8s-apply: ## Apply Kubernetes manifests
	@echo "${GREEN}Applying Kubernetes manifests...${NC}"
	kubectl apply -f k8s/configmap.yaml -n $(NAMESPACE)
	kubectl apply -f k8s/networkpolicy.yaml -n $(NAMESPACE)
	kubectl apply -f k8s/deployment.yaml -n $(NAMESPACE)
	kubectl apply -f k8s/cron-ttl.yaml -n $(NAMESPACE)

k8s-delete: ## Delete Kubernetes resources
	@echo "${RED}Deleting Kubernetes resources...${NC}"
	kubectl delete -f k8s/ -n $(NAMESPACE) --ignore-not-found=true

k8s-rollout: docker-push ## Build, push and rollout new version
	@echo "${GREEN}Rolling out new version...${NC}"
	kubectl set image deployment/citation-expander \
		api=$(DOCKER_REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG) \
		worker=$(DOCKER_REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG) \
		-n $(NAMESPACE)
	kubectl rollout status deployment/citation-expander -n $(NAMESPACE)

openshift-deploy: ## Deploy to OpenShift
	@echo "${GREEN}Deploying to OpenShift...${NC}"
	oc new-project $(NAMESPACE) 2>/dev/null || true
	oc apply -f k8s/configmap.yaml -n $(NAMESPACE)
	oc apply -f k8s/deployment.yaml -n $(NAMESPACE)
	oc apply -f k8s/networkpolicy.yaml -n $(NAMESPACE)
	oc apply -f k8s/cron-ttl.yaml -n $(NAMESPACE)
	oc expose service citation-expander -n $(NAMESPACE) 2>/dev/null || true

logs: ## Show logs from all pods
	@echo "${YELLOW}Showing logs...${NC}"
	kubectl logs -l app=citation-expander -n $(NAMESPACE) --tail=50 -f

logs-worker: ## Show worker logs
	@echo "${YELLOW}Showing worker logs...${NC}"
	kubectl logs -l app=citation-expander -n $(NAMESPACE) -c worker --tail=50 -f

# Development targets
dev-redis: ## Start Redis for local development
	@echo "${GREEN}Starting Redis...${NC}"
	docker run --rm -d --name redis-dev -p 6379:6379 redis:alpine

dev-qdrant: ## Start Qdrant for local development
	@echo "${GREEN}Starting Qdrant...${NC}"
	docker run --rm -d --name qdrant-dev -p 6333:6333 qdrant/qdrant

dev-env: dev-redis dev-qdrant ## Start all development services
	@echo "${GREEN}Development environment ready!${NC}"
	@echo "Redis: redis://localhost:6379"
	@echo "Qdrant: http://localhost:6333"

dev-stop: ## Stop development services
	@echo "${RED}Stopping development services...${NC}"
	docker stop redis-dev qdrant-dev 2>/dev/null || true

run-api: ## Run FastAPI application locally
	@echo "${GREEN}Starting FastAPI application...${NC}"
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run-worker: ## Run RQ worker locally
	@echo "${GREEN}Starting RQ worker...${NC}"
	rq worker --url redis://localhost:6379/0 citations

# Integration with existing Ask-MaaS
integrate: ## Update ask-maas-api to use citation expander
	@echo "${GREEN}Integrating with ask-maas-api...${NC}"
	@echo "${YELLOW}Adding orchestrator patch to ask-maas-api...${NC}"
	cp -r ../ask_maas_orchestrator_patch ../ask-maas-api/
	@echo "${YELLOW}Updating ask-maas-api requirements...${NC}"
	@echo "# Citation Expander dependencies" >> ../ask-maas-api/requirements.txt
	@echo "redis>=5.0.0" >> ../ask-maas-api/requirements.txt
	@echo "rq>=1.15.0" >> ../ask-maas-api/requirements.txt
	@echo "${GREEN}Integration complete! Update your ask-maas-api to import from ask_maas_orchestrator_patch${NC}"

# Monitoring
metrics: ## Show current metrics
	@echo "${YELLOW}Fetching metrics...${NC}"
	curl -s http://localhost:8000/metrics | grep citation

health: ## Check health status
	@echo "${YELLOW}Checking health...${NC}"
	curl -s http://localhost:8000/healthz | python -m json.tool

# CI/CD helpers
ci-test: install-dev lint test ## Run CI test suite

ci-build: ci-test build docker-build ## Run CI build pipeline

# Kind/local k8s deployment
kind-load: docker-build ## Load image into kind cluster
	@echo "${GREEN}Loading image into kind...${NC}"
	kind load docker-image $(IMAGE_NAME):$(IMAGE_TAG)

kind-deploy: kind-load k8s-apply ## Deploy to kind cluster
	@echo "${GREEN}Deployed to kind cluster!${NC}"
	kubectl wait --for=condition=available --timeout=300s deployment/citation-expander -n $(NAMESPACE)

kind-run: kind-deploy logs ## Full deployment to kind with logs

# Quick start
quickstart: install dev-env ## Quick start for development
	@echo "${GREEN}Quickstart complete!${NC}"
	@echo ""
	@echo "Run the following commands in separate terminals:"
	@echo "  1. make run-api    # Start the API server"
	@echo "  2. make run-worker # Start the RQ worker"
	@echo ""
	@echo "Then test with:"
	@echo "  curl http://localhost:8000/healthz"

.DEFAULT_GOAL := help
