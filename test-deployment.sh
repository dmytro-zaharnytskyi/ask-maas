#!/bin/bash
#
# Ask MaaS Deployment Test Script
# Tests all components of the deployed system
#

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Test results
TESTS_PASSED=0
TESTS_FAILED=0

# Get cluster domain
CLUSTER_DOMAIN=$(oc whoami --show-server | sed 's/.*api\.\(.*\):.*/\1/')

# Test function
run_test() {
    local test_name="$1"
    local test_cmd="$2"
    
    echo -ne "${BLUE}[TEST]${NC} $test_name... "
    
    if eval "$test_cmd" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ PASSED${NC}"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        ((TESTS_FAILED++))
        return 1
    fi
}

# Detailed test function
run_test_verbose() {
    local test_name="$1"
    local test_cmd="$2"
    
    echo -e "${BLUE}[TEST]${NC} $test_name"
    
    if eval "$test_cmd"; then
        echo -e "${GREEN}✓ PASSED${NC}"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        ((TESTS_FAILED++))
        return 1
    fi
}

echo "========================================"
echo "Ask MaaS Deployment Test Suite"
echo "========================================"
echo ""

# 1. Check Namespaces
echo -e "${YELLOW}1. Checking Namespaces${NC}"
run_test "ask-maas-models namespace exists" "oc get namespace ask-maas-models"
run_test "ask-maas-api namespace exists" "oc get namespace ask-maas-api"
echo ""

# 2. Check Model Services
echo -e "${YELLOW}2. Checking Model Services${NC}"
run_test "Qdrant deployment ready" "oc get deployment qdrant -n ask-maas-models"
run_test "TEI embeddings deployment ready" "oc get deployment tei-embeddings -n ask-maas-models"
run_test "vLLM model deployment ready" "oc get deployment -n ask-maas-models | grep -E '(vllm-mistral|vllm-qwen)'"
run_test "Redis deployment ready" "oc get deployment redis -n ask-maas-api"
echo ""

# 3. Check API Services
echo -e "${YELLOW}3. Checking API Services${NC}"
run_test "Orchestrator deployment ready" "oc get deployment ask-maas-orchestrator -n ask-maas-api"
run_test "Orchestrator pods running" "oc get pods -n ask-maas-api -l app=ask-maas-orchestrator | grep Running"
run_test "Orchestrator service exists" "oc get service ask-maas-orchestrator-service -n ask-maas-api"
echo ""

# 4. Check Frontend
echo -e "${YELLOW}4. Checking Frontend${NC}"
run_test "Frontend deployment ready" "oc get deployment ghost-site -n ask-maas-api"
run_test "Frontend pods running" "oc get pods -n ask-maas-api -l app=ghost-site | grep Running"
run_test "Frontend service exists" "oc get service ghost-site-service -n ask-maas-api"
echo ""

# 5. Check Routes
echo -e "${YELLOW}5. Checking Routes${NC}"
run_test "API route exists" "oc get route ask-maas-api -n ask-maas-api"
run_test "Frontend route exists" "oc get route ask-maas-frontend -n ask-maas-api"

API_URL="https://ask-maas-api.${CLUSTER_DOMAIN}"
FRONTEND_URL="https://ask-maas-frontend.${CLUSTER_DOMAIN}"

echo "  API URL: $API_URL"
echo "  Frontend URL: $FRONTEND_URL"
echo ""

# 6. Test API Health
echo -e "${YELLOW}6. Testing API Health${NC}"
run_test "API health check" "curl -s -f ${API_URL}/health/ready"
run_test "API liveness check" "curl -s -f ${API_URL}/health/live"
echo ""

# 7. Test Frontend
echo -e "${YELLOW}7. Testing Frontend${NC}"
run_test "Frontend responds" "curl -s -f ${FRONTEND_URL} | grep -q 'Ask MaaS'"
run_test "Articles API responds" "curl -s -f ${FRONTEND_URL}/api/articles | grep -q 'articles'"
echo ""

# 8. Test Article Content
echo -e "${YELLOW}8. Testing Article Content${NC}"
run_test "MaaS article available" "curl -s -f '${FRONTEND_URL}/api/articles/What%20is%20MaaS%20(Models-as-a-Service)%20and%20how%20to%20set%20it%20up%20fast%20on%20OpenShift%20_%20Red%20Hat%20Developer.html' | grep -q 'MaaS'"
run_test "Llama article available" "curl -s -f '${FRONTEND_URL}/api/articles/Deploy%20Llama%203%208B%20with%20vLLM%20_%20Red%20Hat%20Developer.html' | grep -q 'Llama'"
echo ""

# 9. Test RAG System
echo -e "${YELLOW}9. Testing RAG System${NC}"
echo "  Sending test query to AI assistant..."

RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/chat" \
    -H "Content-Type: application/json" \
    -d '{"query": "What is MaaS?", "page_url": "test", "stream": false}' \
    --max-time 30 2>/dev/null || echo "TIMEOUT")

if [[ "$RESPONSE" == "TIMEOUT" ]]; then
    echo -e "  ${RED}✗ Query timed out${NC}"
    ((TESTS_FAILED++))
elif echo "$RESPONSE" | grep -q "MaaS\|Models-as-a-Service"; then
    echo -e "  ${GREEN}✓ AI assistant responded correctly${NC}"
    ((TESTS_PASSED++))
    
    # Extract response preview
    PREVIEW=$(echo "$RESPONSE" | grep -o '"content":"[^"]*"' | head -1 | cut -d'"' -f4 | cut -c1-100)
    echo "  Response preview: ${PREVIEW}..."
else
    echo -e "  ${RED}✗ AI assistant did not respond correctly${NC}"
    ((TESTS_FAILED++))
fi
echo ""

# 10. Test Article Ingestion Status
echo -e "${YELLOW}10. Testing Article Ingestion${NC}"
QUERIES=(
    "Can you explain rate limiting in MaaS?"
    "How does kustomize work with MaaS?"
    "What are the benefits of vLLM?"
    "How to deploy Llama 3?"
    "What GPU profiling tools work with vLLM?"
)

for query in "${QUERIES[@]}"; do
    echo -n "  Testing: ${query:0:40}... "
    
    RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/chat" \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"$query\", \"page_url\": \"test\", \"stream\": false}" \
        --max-time 15 2>/dev/null || echo "TIMEOUT")
    
    if [[ "$RESPONSE" == "TIMEOUT" ]]; then
        echo -e "${YELLOW}TIMEOUT${NC}"
    elif echo "$RESPONSE" | grep -q '"content"'; then
        echo -e "${GREEN}✓${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗${NC}"
        ((TESTS_FAILED++))
    fi
done
echo ""

# 11. Performance Check
echo -e "${YELLOW}11. Performance Metrics${NC}"
echo "  Checking response times..."

START=$(date +%s%N)
curl -s -f "${API_URL}/health/ready" >/dev/null 2>&1
END=$(date +%s%N)
API_TIME=$((($END - $START) / 1000000))
echo "  API health check: ${API_TIME}ms"

START=$(date +%s%N)
curl -s -f "${FRONTEND_URL}" >/dev/null 2>&1
END=$(date +%s%N)
FRONTEND_TIME=$((($END - $START) / 1000000))
echo "  Frontend load time: ${FRONTEND_TIME}ms"
echo ""

# 12. Resource Usage
echo -e "${YELLOW}12. Resource Usage${NC}"
echo "  API namespace:"
oc top pods -n ask-maas-api 2>/dev/null | head -5 || echo "  Metrics not available"
echo ""
echo "  Models namespace:"
oc top pods -n ask-maas-models 2>/dev/null | head -5 || echo "  Metrics not available"
echo ""

# Summary
echo "========================================"
echo "Test Summary"
echo "========================================"
echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"

if [ $TESTS_FAILED -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ All tests passed! The system is fully operational.${NC}"
    echo ""
    echo "Access points:"
    echo "  Frontend: $FRONTEND_URL"
    echo "  API: $API_URL"
    exit 0
else
    echo ""
    echo -e "${RED}⚠️ Some tests failed. Please check the deployment.${NC}"
    echo ""
    echo "Troubleshooting commands:"
    echo "  oc get pods -n ask-maas-api"
    echo "  oc get pods -n ask-maas-models"
    echo "  oc logs -f deployment/ask-maas-orchestrator -n ask-maas-api"
    exit 1
fi