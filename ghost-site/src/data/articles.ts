export const articles = [
  {
    id: 'air-gapped-openshift',
    title: 'Simplify OpenShift Installation in Air-Gapped Environments',
    category: 'OpenShift Installation',
    lastUpdated: '2024-10-14',
    githubLinks: [],
    externalUrl: 'https://developers.redhat.com/articles/2025/10/14/simplify-openshift-installation-air-gapped-environments',
    content: `
# Simplify OpenShift Installation in Air-Gapped Environments

This article discusses how to simplify OpenShift installation in air-gapped (disconnected) environments. Air-gapped environments are isolated from the internet for security reasons and require special considerations for software deployment.

Note: This content will be dynamically loaded from the Red Hat Developer website.
    `,
  },
  {
    id: 'openshift-ai-deployment',
    title: 'Deploying Red Hat OpenShift AI on Your Cluster',
    category: 'OpenShift AI',
    lastUpdated: '2024-10-14',
    githubLinks: [
      'https://github.com/redhat-cop/openshift-ai-samples/blob/main/deploy/operator-install.yaml',
      'https://github.com/redhat-cop/openshift-ai-samples/blob/main/examples/notebook-server.yaml',
    ],
    content: `
# Deploying Red Hat OpenShift AI on Your Cluster

Red Hat OpenShift AI (RHOAI) provides a comprehensive platform for developing, training, and serving AI/ML models on OpenShift. This guide walks you through the installation and configuration process.

## Prerequisites

Before installing OpenShift AI, ensure you have:

- OpenShift Container Platform 4.12 or later
- Cluster admin privileges
- At least 3 worker nodes with 16GB RAM each
- GPU nodes (optional, but recommended for model training)

## Installation Steps

### 1. Install the OpenShift AI Operator

First, install the Red Hat OpenShift AI operator from the OperatorHub:

\`\`\`yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: rhods-operator
  namespace: openshift-operators
spec:
  channel: stable
  name: rhods-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
\`\`\`

### 2. Create a DataScienceCluster Instance

After the operator is installed, create a DataScienceCluster resource:

\`\`\`yaml
apiVersion: datasciencecluster.opendatahub.io/v1
kind: DataScienceCluster
metadata:
  name: default
  namespace: redhat-ods-applications
spec:
  components:
    codeflare:
      managementState: Managed
    dashboard:
      managementState: Managed
    datasciencepipelines:
      managementState: Managed
    kserve:
      managementState: Managed
      serving:
        ingressGateway:
          certificate:
            type: SelfSigned
        managementState: Managed
        name: knative-serving
    modelmeshserving:
      managementState: Managed
    ray:
      managementState: Managed
    workbenches:
      managementState: Managed
\`\`\`

### 3. Configure GPU Support (Optional)

If you have GPU nodes, install the NVIDIA GPU Operator:

\`\`\`bash
oc create -f https://github.com/NVIDIA/gpu-operator/releases/download/v23.3.2/gpu-operator.yaml
\`\`\`

Label your GPU nodes:

\`\`\`bash
oc label node <node-name> nvidia.com/gpu.accelerator=tesla-t4
\`\`\`

### 4. Create a Data Science Project

Once OpenShift AI is installed, create a new data science project:

\`\`\`yaml
apiVersion: v1
kind: Namespace
metadata:
  name: my-ai-project
  labels:
    opendatahub.io/dashboard: "true"
    modelmesh-enabled: "true"
\`\`\`

### 5. Deploy a Jupyter Notebook

Create a notebook server for development:

\`\`\`yaml
apiVersion: kubeflow.org/v1
kind: Notebook
metadata:
  name: my-notebook
  namespace: my-ai-project
spec:
  template:
    spec:
      containers:
      - name: notebook
        image: quay.io/modh/odh-minimal-notebook-image:v2-2023b
        resources:
          requests:
            memory: 4Gi
            cpu: 1
          limits:
            memory: 8Gi
            cpu: 2
\`\`\`

## Model Serving with KServe

OpenShift AI includes KServe for serving machine learning models. Here's how to deploy a model:

### 1. Create an InferenceService

\`\`\`yaml
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: sklearn-iris
  namespace: my-ai-project
spec:
  predictor:
    model:
      modelFormat:
        name: sklearn
      storageUri: gs://kfserving-examples/models/sklearn/1.0/model
\`\`\`

### 2. Test the Deployed Model

Once deployed, test your model endpoint:

\`\`\`bash
MODEL_NAME=sklearn-iris
INPUT_PATH=@input.json
SERVICE_HOSTNAME=$(oc get inferenceservice $MODEL_NAME -o jsonpath='{.status.url}')

curl -v -H "Content-Type: application/json" -d $INPUT_PATH $SERVICE_HOSTNAME/v1/models/$MODEL_NAME:predict
\`\`\`

## Monitoring and Observability

OpenShift AI integrates with OpenShift's monitoring stack:

1. **Metrics**: View model serving metrics in the OpenShift console
2. **Logging**: Access logs through the OpenShift logging subsystem
3. **Distributed Tracing**: Use Jaeger for request tracing

## Best Practices

1. **Resource Management**: Set appropriate resource limits for notebooks and model servers
2. **Security**: Use network policies to restrict traffic between namespaces
3. **Storage**: Configure persistent volumes for notebook data and model artifacts
4. **Scaling**: Use HPA for automatic scaling of model inference services

## Troubleshooting Common Issues

### Notebook Server Won't Start

Check the pod events:
\`\`\`bash
oc describe pod <notebook-pod-name> -n my-ai-project
\`\`\`

### Model Serving Errors

Verify the InferenceService status:
\`\`\`bash
oc get inferenceservice -n my-ai-project
oc describe inferenceservice <model-name> -n my-ai-project
\`\`\`

## Related Resources

- [Official OpenShift AI Documentation](https://access.redhat.com/documentation/en-us/red_hat_openshift_ai_self-managed)
- [OpenShift AI Examples Repository](https://github.com/redhat-cop/openshift-ai-samples)
- [KServe Documentation](https://kserve.github.io/website/)
    `,
  },
  {
    id: 'kuadrant-setup',
    title: 'Setting Up Kuadrant for API Gateway Management',
    category: 'API Management',
    lastUpdated: '2024-10-14',
    githubLinks: [
      'https://github.com/Kuadrant/kuadrant-operator/blob/main/config/samples/kuadrant_v1beta2_kuadrant.yaml',
      'https://github.com/Kuadrant/kuadrant-operator/blob/main/doc/rate-limiting.md',
    ],
    content: `
# Setting Up Kuadrant for API Gateway Management

Kuadrant extends Kubernetes Gateway API with enterprise-grade API management capabilities including authentication, authorization, and rate limiting.

## What is Kuadrant?

Kuadrant is a Kubernetes-native API management solution that provides:
- **Authorino**: Authentication and authorization
- **Limitador**: Rate limiting
- **DNS management**: Multi-cluster DNS
- **TLS management**: Certificate lifecycle

## Prerequisites

- OpenShift 4.12+ or Kubernetes 1.25+
- Gateway API CRDs installed
- Cert-manager (for TLS)
- Cluster admin access

## Installation

### 1. Install Gateway API CRDs

\`\`\`bash
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v0.8.0/standard-install.yaml
\`\`\`

### 2. Install Kuadrant Operator

\`\`\`yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: kuadrant-operator
  namespace: kuadrant-system
spec:
  channel: stable
  name: kuadrant-operator
  source: community-operators
  sourceNamespace: openshift-marketplace
\`\`\`

### 3. Create Kuadrant Instance

\`\`\`yaml
apiVersion: kuadrant.io/v1beta1
kind: Kuadrant
metadata:
  name: kuadrant
  namespace: kuadrant-system
spec: {}
\`\`\`

## Configuring a Gateway

### 1. Create a Gateway Class

\`\`\`yaml
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: kuadrant-gateway-class
spec:
  controllerName: kuadrant.io/gateway-controller
\`\`\`

### 2. Deploy a Gateway

\`\`\`yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: api-gateway
  namespace: gateway-system
spec:
  gatewayClassName: kuadrant-gateway-class
  listeners:
  - name: http
    protocol: HTTP
    port: 80
    allowedRoutes:
      namespaces:
        from: All
  - name: https
    protocol: HTTPS
    port: 443
    tls:
      certificateRefs:
      - name: api-tls-cert
    allowedRoutes:
      namespaces:
        from: All
\`\`\`

## Rate Limiting with Limitador

### 1. Create a RateLimitPolicy

\`\`\`yaml
apiVersion: kuadrant.io/v1beta2
kind: RateLimitPolicy
metadata:
  name: api-rate-limit
  namespace: gateway-system
spec:
  targetRef:
    group: gateway.networking.k8s.io
    kind: HTTPRoute
    name: api-route
  limits:
  - rates:
    - limit: 100
      duration: 1m
    when:
    - selector: request.path
      operator: eq
      value: "/api/v1/users"
  - rates:
    - limit: 1000
      duration: 1h
    counters:
    - request.headers.x-api-key
\`\`\`

### 2. Configure HTTPRoute

\`\`\`yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: api-route
  namespace: gateway-system
spec:
  parentRefs:
  - name: api-gateway
  hostnames:
  - "api.example.com"
  rules:
  - matches:
    - path:
        type: PathPrefix
        value: /api/v1
    backendRefs:
    - name: api-service
      port: 8080
\`\`\`

## Authentication with Authorino

### 1. Create an AuthPolicy

\`\`\`yaml
apiVersion: kuadrant.io/v1beta2
kind: AuthPolicy
metadata:
  name: api-auth-policy
  namespace: gateway-system
spec:
  targetRef:
    group: gateway.networking.k8s.io
    kind: HTTPRoute
    name: api-route
  rules:
    authentication:
      "api-key-users":
        apiKey:
          selector:
            matchLabels:
              app: api
        credentials:
          authorizationHeader:
            prefix: "API-Key"
      
      "jwt-users":
        jwt:
          issuerUrl: https://auth.example.com
          audiences:
          - api.example.com
        credentials:
          authorizationHeader:
            prefix: Bearer
    
    authorization:
      "admin-only":
        when:
        - selector: request.path
          operator: matches
          value: "^/api/v1/admin"
        opa:
          rego: |
            allow = true
            allow = false { not "admin" in input.auth.roles }
    
    response:
      success:
        headers:
          "X-User-Id":
            selector: auth.identity.sub
\`\`\`

### 2. Configure API Keys

\`\`\`yaml
apiVersion: v1
kind: Secret
metadata:
  name: api-key-1
  namespace: gateway-system
  labels:
    app: api
    authorino.kuadrant.io/managed-by: authorino
type: Opaque
data:
  api_key: <base64-encoded-key>
stringData:
  user: alice
  roles: '["user", "admin"]'
\`\`\`

## Multi-cluster Setup

### 1. Configure DNS Policy

\`\`\`yaml
apiVersion: kuadrant.io/v1alpha1
kind: DNSPolicy
metadata:
  name: api-dns-policy
  namespace: gateway-system
spec:
  targetRef:
    group: gateway.networking.k8s.io
    kind: Gateway
    name: api-gateway
  routingStrategy: loadbalanced
  loadBalancing:
    geo:
      defaultGeo: US
  healthCheck:
    endpoint: /health
    interval: 60s
\`\`\`

## Observability

### 1. Enable Metrics

\`\`\`yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: kuadrant-config
  namespace: kuadrant-system
data:
  config.yaml: |
    metrics:
      enabled: true
      port: 8080
    tracing:
      enabled: true
      endpoint: jaeger-collector:14268
\`\`\`

### 2. Create ServiceMonitor

\`\`\`yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: kuadrant-metrics
  namespace: kuadrant-system
spec:
  selector:
    matchLabels:
      app: kuadrant
  endpoints:
  - port: metrics
    interval: 30s
\`\`\`

## Best Practices

1. **Rate Limit Design**: Start with conservative limits and adjust based on monitoring
2. **Authentication Layers**: Combine multiple auth methods for defense in depth
3. **Circuit Breaking**: Implement circuit breakers for backend protection
4. **Monitoring**: Set up alerts for rate limit violations and auth failures
5. **Testing**: Use tools like k6 or vegeta for load testing

## Troubleshooting

### Gateway Not Accepting Traffic

\`\`\`bash
kubectl describe gateway api-gateway -n gateway-system
kubectl logs -n kuadrant-system deployment/kuadrant-controller
\`\`\`

### Rate Limiting Not Working

\`\`\`bash
kubectl get ratelimitpolicy -n gateway-system
kubectl logs -n kuadrant-system deployment/limitador
\`\`\`

### Authentication Issues

\`\`\`bash
kubectl get authpolicy -n gateway-system
kubectl logs -n kuadrant-system deployment/authorino
\`\`\`

## Performance Tuning

- Adjust Limitador memory limits based on counter storage needs
- Configure Redis for distributed rate limiting
- Use connection pooling for backend services
- Implement caching strategies for auth decisions

## Related Resources

- [Kuadrant Documentation](https://docs.kuadrant.io)
- [Gateway API Documentation](https://gateway-api.sigs.k8s.io)
- [Authorino Documentation](https://github.com/Kuadrant/authorino)
    `,
  },
  {
    id: 'service-mesh-mtls',
    title: 'Implementing mTLS with OpenShift Service Mesh',
    category: 'Service Mesh',
    lastUpdated: '2024-10-14',
    githubLinks: [
      'https://github.com/maistra/istio-operator/blob/maistra-2.4/samples/smcp-v2.4.yaml',
      'https://github.com/maistra/istio-operator/blob/maistra-2.4/samples/smmr.yaml',
    ],
    content: `
# Implementing mTLS with OpenShift Service Mesh

OpenShift Service Mesh provides a powerful way to secure service-to-service communication using mutual TLS (mTLS). This guide covers installation, configuration, and best practices.

## Understanding mTLS

Mutual TLS (mTLS) ensures:
- **Authentication**: Both client and server verify each other's identity
- **Encryption**: All traffic is encrypted in transit
- **Integrity**: Data cannot be tampered with

## Installation

### 1. Install Required Operators

Install these operators in order:

1. **OpenShift Elasticsearch** (for logging)
2. **Red Hat OpenShift distributed tracing** (Jaeger)
3. **Kiali Operator** (for observability)
4. **Red Hat OpenShift Service Mesh**

### 2. Create Service Mesh Control Plane

\`\`\`yaml
apiVersion: maistra.io/v2
kind: ServiceMeshControlPlane
metadata:
  name: production
  namespace: istio-system
spec:
  version: v2.4
  tracing:
    type: Jaeger
    sampling: 10000
  general:
    logging:
      logAsJSON: true
      logLevels:
        default: info
  profiles:
    - default
  proxy:
    networking:
      trafficControl:
        inbound: {}
        outbound:
          policy: REGISTRY_ONLY
  policy:
    type: Istiod
  telemetry:
    type: Istiod
  addons:
    prometheus:
      enabled: true
    grafana:
      enabled: true
      install:
        config:
          env:
            GF_SECURITY_ADMIN_PASSWORD: admin
    kiali:
      enabled: true
      install:
        dashboard:
          viewOnly: false
    jaeger:
      install:
        storage:
          type: Memory
  runtime:
    defaults:
      container:
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 500m
            memory: 512Mi
\`\`\`

### 3. Create Service Mesh Member Roll

\`\`\`yaml
apiVersion: maistra.io/v1
kind: ServiceMeshMemberRoll
metadata:
  name: default
  namespace: istio-system
spec:
  members:
    - bookinfo
    - prod-apps
    - staging-apps
\`\`\`

## Configuring mTLS

### 1. Strict mTLS for All Services

\`\`\`yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: istio-system
spec:
  mtls:
    mode: STRICT
\`\`\`

### 2. Namespace-Specific mTLS

\`\`\`yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: prod-mtls
  namespace: prod-apps
spec:
  mtls:
    mode: STRICT
---
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: prod-services
  namespace: prod-apps
spec:
  host: "*.prod-apps.svc.cluster.local"
  trafficPolicy:
    tls:
      mode: ISTIO_MUTUAL
\`\`\`

### 3. Service-Level mTLS Configuration

\`\`\`yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: payment-service-mtls
  namespace: prod-apps
spec:
  selector:
    matchLabels:
      app: payment-service
  mtls:
    mode: STRICT
  portLevelMtls:
    8080:
      mode: STRICT
    8090:
      mode: PERMISSIVE  # Health check port
\`\`\`

## Authorization Policies

### 1. Allow Only Specific Services

\`\`\`yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: payment-authz
  namespace: prod-apps
spec:
  selector:
    matchLabels:
      app: payment-service
  action: ALLOW
  rules:
  - from:
    - source:
        principals: ["cluster.local/ns/prod-apps/sa/checkout-service"]
    to:
    - operation:
        methods: ["POST"]
        paths: ["/api/v1/payment"]
\`\`\`

### 2. Deny All by Default

\`\`\`yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: deny-all
  namespace: prod-apps
spec:
  {}  # Empty spec denies all traffic
---
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: allow-frontend
  namespace: prod-apps
spec:
  selector:
    matchLabels:
      app: frontend
  action: ALLOW
  rules:
  - from:
    - source:
        namespaces: ["istio-system"]  # Allow ingress gateway
\`\`\`

## Certificate Management

### 1. Custom Root CA

\`\`\`yaml
apiVersion: v1
kind: Secret
metadata:
  name: cacerts
  namespace: istio-system
type: Opaque
data:
  root-cert.pem: <base64-encoded-root-cert>
  cert-chain.pem: <base64-encoded-cert-chain>
  ca-cert.pem: <base64-encoded-ca-cert>
  ca-key.pem: <base64-encoded-ca-key>
\`\`\`

### 2. Certificate Rotation

Configure automatic rotation in SMCP:

\`\`\`yaml
spec:
  security:
    certificateAuthority:
      type: Istiod
      istiod:
        privateKey:
          rootCADir: /etc/cacerts
        workloadCertTTL: 24h
        rootCertTTL: 87600h  # 10 years
\`\`\`

## Traffic Management with mTLS

### 1. Circuit Breaking

\`\`\`yaml
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: payment-cb
  namespace: prod-apps
spec:
  host: payment-service
  trafficPolicy:
    tls:
      mode: ISTIO_MUTUAL
    connectionPool:
      tcp:
        maxConnections: 100
      http:
        http1MaxPendingRequests: 100
        http2MaxRequests: 100
    outlierDetection:
      consecutiveErrors: 5
      interval: 30s
      baseEjectionTime: 30s
\`\`\`

### 2. Retry Policy

\`\`\`yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: payment-vs
  namespace: prod-apps
spec:
  hosts:
  - payment-service
  http:
  - route:
    - destination:
        host: payment-service
    retry:
      attempts: 3
      perTryTimeout: 5s
      retryOn: gateway-error,connect-failure,refused-stream
\`\`\`

## Monitoring mTLS

### 1. Verify mTLS Status

\`\`\`bash
# Check mTLS configuration
oc get peerauthentication --all-namespaces

# Verify certificates
oc exec <pod-name> -c istio-proxy -- openssl s_client -connect <service>:8080 -showcerts

# Check Envoy configuration
oc exec <pod-name> -c istio-proxy -- pilot-agent request GET config_dump
\`\`\`

### 2. Kiali Dashboard

Access Kiali to visualize mTLS status:
- Green padlock: mTLS enabled
- Open padlock: Plain text
- Red padlock: mTLS misconfiguration

### 3. Prometheus Metrics

Key metrics to monitor:
- \`istio_tcp_connections_opened_ssl_total\`
- \`istio_tcp_connections_opened_no_ssl_total\`
- \`envoy_ssl_handshake_errors\`

## Troubleshooting

### Connection Refused

\`\`\`bash
# Check if sidecar is injected
oc get pod <pod-name> -o jsonpath='{.spec.containers[*].name}'

# Verify mTLS mode
oc get peerauthentication -n <namespace>
\`\`\`

### Certificate Errors

\`\`\`bash
# Check certificate validity
oc exec <pod> -c istio-proxy -- openssl x509 -text -noout -in /etc/certs/cert-chain.pem

# Verify root CA
oc exec <pod> -c istio-proxy -- openssl x509 -text -noout -in /etc/certs/root-cert.pem
\`\`\`

### Performance Issues

1. Check proxy CPU/memory usage
2. Verify circuit breaker settings
3. Review outlier detection configuration

## Best Practices

1. **Start with PERMISSIVE**: Gradually migrate to STRICT mode
2. **Monitor before enforcing**: Use dashboards to verify traffic flow
3. **Service Accounts**: Use dedicated SA for each service
4. **Namespace isolation**: Separate environments using namespaces
5. **Regular rotation**: Implement certificate rotation policies
6. **Backup certificates**: Store root CA securely

## Migration Strategy

### Phase 1: Enable PERMISSIVE
\`\`\`yaml
spec:
  mtls:
    mode: PERMISSIVE
\`\`\`

### Phase 2: Monitor and Fix
- Use Kiali to identify plain text traffic
- Update clients to use mTLS

### Phase 3: Enable STRICT
\`\`\`yaml
spec:
  mtls:
    mode: STRICT
\`\`\`

## Related Resources

- [OpenShift Service Mesh Documentation](https://docs.openshift.com/container-platform/latest/service_mesh)
- [Istio Security Documentation](https://istio.io/latest/docs/concepts/security/)
- [mTLS Best Practices](https://github.com/maistra/maistra.github.io)
    `,
  },
];
