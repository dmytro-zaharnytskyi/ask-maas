export const articles = [
  {
    id: 'maas-complete-guide',
    title: 'What is MaaS (Models-as-a-Service) and how to set it up fast on OpenShift',
    category: 'MaaS',
    lastUpdated: '2024-12-06',
    githubLinks: ['https://github.com/opendatahub-io/maas-billing'],
    externalUrl: '/articles/MaaS%20Complete%20Setup%20Guide%20_%20Red%20Hat%20Developer.html',
    localFile: 'MaaS Complete Setup Guide _ Red Hat Developer.html',
    content: `
# What is MaaS (Models-as-a-Service) and how to set it up fast on OpenShift

MaaS is a governance and multi-tenancy control plane that sits on top of a model runtime like KServe, providing self-service, access control, rate limiting, and tier-based subscriptions.

TL;DR — one command does the heavy lifting. Run ./deployment/scripts/deploy-openshift.sh from the opendatahub-io/maas-billing repo.

This comprehensive guide covers:
- Quick start deployment with one command
- MaaS architecture and components
- Gateway configuration and policies
- Tier management and RBAC
- Quota and rate limiting
- Troubleshooting and observability
    `,
  },
  {
    id: 'maas-kustomize',
    title: 'All you can kustomize during the MaaS deployment',
    category: 'MaaS Deployment',
    lastUpdated: '2024-10-14',
    githubLinks: [],
    externalUrl: '/articles/All%20you%20can%20kustomize%20during%20the%20MaaS%20deployment%20_%20Red%20Hat%20Developer.html',
    localFile: 'All you can kustomize during the MaaS deployment _ Red Hat Developer.html',
    content: `
# All you can kustomize during the MaaS deployment

This article explores the various customization options available when deploying Models-as-a-Service (MaaS) on OpenShift. Learn how to tailor your MaaS deployment to your specific requirements using Kustomize and other configuration techniques.

The article covers:
- Customizing model serving configurations
- Adjusting resource allocations
- Configuring networking and security settings
- Setting up monitoring and logging
- Optimizing for different workload types
    `,
  },
  {
    id: 'llama3-vllm',
    title: 'Deploy Llama 3 8B with vLLM',
    category: 'Model Deployment',
    lastUpdated: '2024-10-14',
    githubLinks: [],
    externalUrl: '/articles/Deploy%20Llama%203%208B%20with%20vLLM%20_%20Red%20Hat%20Developer.html',
    localFile: 'Deploy Llama 3 8B with vLLM _ Red Hat Developer.html',
    content: `
# Deploy Llama 3 8B with vLLM

A comprehensive guide to deploying the Llama 3 8B model using vLLM on Red Hat OpenShift. This article provides step-by-step instructions for setting up high-performance inference with the latest Llama model.

Topics covered include:
- Setting up vLLM on OpenShift
- Configuring GPU resources
- Optimizing inference performance
- Handling model quantization
- Scaling strategies for production
    `,
  },
  {
    id: 'ollama-vs-vllm',
    title: 'Ollama vs. vLLM: A deep dive into performance benchmarking',
    category: 'Performance',
    lastUpdated: '2024-10-14',
    githubLinks: [],
    externalUrl: '/articles/Ollama%20vs.%20vLLM_%20A%20deep%20dive%20into%20performance%20benchmarking%20_%20Red%20Hat%20Developer.html',
    localFile: 'Ollama vs. vLLM_ A deep dive into performance benchmarking _ Red Hat Developer.html',
    content: `
# Ollama vs. vLLM: A deep dive into performance benchmarking

An in-depth comparison of Ollama and vLLM for serving large language models. This article presents comprehensive benchmarking results and helps you choose the right inference server for your use case.

Key metrics analyzed:
- Time to First Token (TTFT)
- Inter-Token Latency (ITL)
- Throughput under various loads
- Memory consumption
- GPU utilization
- Scalability characteristics
    `,
  },
  {
    id: 'vllm-profiling',
    title: 'Profiling vLLM Inference Server with GPU acceleration on RHEL',
    category: 'Performance',
    lastUpdated: '2024-10-14',
    githubLinks: [],
    externalUrl: '/articles/Profiling%20vLLM%20Inference%20Server%20with%20GPU%20acceleration%20on%20RHEL%20_%20Red%20Hat%20Developer.html',
    localFile: 'Profiling vLLM Inference Server with GPU acceleration on RHEL _ Red Hat Developer.html',
    content: `
# Profiling vLLM Inference Server with GPU acceleration on RHEL

Learn how to profile and optimize vLLM inference server performance on Red Hat Enterprise Linux with GPU acceleration. This article provides practical techniques for identifying and resolving performance bottlenecks.

Topics include:
- Setting up profiling tools
- Analyzing GPU utilization
- Memory profiling techniques
- Identifying performance bottlenecks
- Optimization strategies
- Real-world case studies
    `,
  },
];