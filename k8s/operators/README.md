# OpenShift Operators Installation Guide

## Required Operators for Ask MaaS MVP

Install these operators through the OpenShift Console (OperatorHub). Navigate to **Operators → OperatorHub** and install each operator with the specified configuration.

### 1. OpenShift Service Mesh (Red Hat OpenShift Service Mesh)
- **Channel**: stable
- **Installation Mode**: All namespaces on the cluster
- **Update Approval**: Automatic
- **Purpose**: Provides Istio-based service mesh for mTLS between components

### 2. OpenShift GitOps (Red Hat OpenShift GitOps)
- **Channel**: latest
- **Installation Mode**: All namespaces on the cluster
- **Update Approval**: Automatic
- **Purpose**: Argo CD for declarative deployments

### 3. OpenShift Pipelines (Red Hat OpenShift Pipelines)
- **Channel**: latest
- **Installation Mode**: All namespaces on the cluster
- **Update Approval**: Automatic
- **Purpose**: Tekton-based CI/CD pipelines

### 4. OpenShift Serverless (Red Hat OpenShift Serverless)
- **Channel**: stable
- **Installation Mode**: All namespaces on the cluster
- **Update Approval**: Automatic
- **Purpose**: Required for KServe model serving

### 5. NVIDIA GPU Operator
- **Channel**: stable
- **Installation Mode**: All namespaces on the cluster
- **Update Approval**: Automatic
- **Configuration**:
  - Enable DCGM monitoring
  - Enable GPU Feature Discovery
  - Enable Time Slicing if needed for development

### 6. OpenTelemetry Operator (Red Hat OpenShift distributed tracing data collection)
- **Channel**: stable
- **Installation Mode**: All namespaces on the cluster
- **Update Approval**: Automatic
- **Purpose**: Distributed tracing and observability

### 7. Kuadrant Operator
- **Channel**: stable
- **Installation Mode**: All namespaces on the cluster
- **Update Approval**: Automatic
- **Purpose**: API Gateway with Authorino (AuthN/AuthZ) and Limitador (Rate Limiting)

### 8. Redis Operator (Redis Enterprise Operator)
- **Channel**: stable
- **Installation Mode**: All namespaces on the cluster
- **Update Approval**: Automatic
- **Purpose**: Cache layer for FAISS indexes

### 9. Sealed Secrets Operator (Sealed Secrets Operator)
- **Channel**: stable
- **Installation Mode**: All namespaces on the cluster
- **Update Approval**: Automatic
- **Purpose**: Secure secret management

## Post-Installation Steps

After installing all operators:

1. **Create namespaces**:
   ```bash
   oc apply -f ../namespaces/namespaces.yaml
   ```

2. **Configure GPU nodes**:
   ```bash
   oc apply -f ../gpu/gpu-node-config.yaml
   
   # Run the node labeling script
   oc create job gpu-label-job \
     --from=cronjob/gpu-node-labeler \
     -n ask-maas-cicd
   ```

3. **Create Service Mesh Control Plane**:
   ```bash
   oc apply -f service-mesh-control-plane.yaml
   ```

4. **Configure KServe**:
   ```bash
   oc apply -f kserve-config.yaml
   ```

## Verification

Verify all operators are installed and running:

```bash
# Check operator subscriptions
oc get subscriptions -A | grep -E "servicemesh|gitops|pipelines|serverless|gpu|opentelemetry|kuadrant|redis|sealed"

# Check operator pods
oc get pods -A | grep -E "operator|controller-manager"

# Verify GPU nodes
oc get nodes -l node-role.kubernetes.io/gpu=true
oc describe node <gpu-node-name> | grep nvidia

# Check Service Mesh
oc get smcp -A
oc get smmr -A
```

## Troubleshooting

If any operator fails to install:
1. Check the operator logs: `oc logs -n openshift-operators deployment/<operator-name>`
2. Verify cluster resources are sufficient
3. Check for any conflicting operators or configurations
4. Review the OperatorHub UI for specific error messages
