"""Pytest fixtures for citation-expander tests."""

import os
import pytest
from typing import Generator, Dict, Any
from unittest.mock import Mock, MagicMock, patch

import redis
from fastapi.testclient import TestClient
from rq import Queue

# Set test environment
os.environ["TESTING"] = "true"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"  # Use separate DB for tests
os.environ["TEI_URL"] = "http://mock-tei:8080"
os.environ["QDRANT_URL"] = "http://mock-qdrant:6333"


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    with patch("redis.from_url") as mock:
        client = MagicMock()
        client.ping.return_value = True
        client.exists.return_value = False
        client.setex.return_value = True
        client.hgetall.return_value = {}
        mock.return_value = client
        yield client


@pytest.fixture
def mock_rq_queue():
    """Mock RQ Queue."""
    with patch("rq.Queue") as mock:
        queue = MagicMock()
        queue.__len__.return_value = 0
        queue.enqueue.return_value = MagicMock(id="test-job-id")
        mock.return_value = queue
        yield queue


@pytest.fixture
def test_client(mock_redis, mock_rq_queue):
    """Create test client for FastAPI app."""
    from app.main import app
    
    with TestClient(app) as client:
        yield client


@pytest.fixture
def sample_html_content():
    """Sample HTML content for testing."""
    return b"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Article</title>
    </head>
    <body>
        <h1>Understanding MaaS</h1>
        <p>Models-as-a-Service (MaaS) is a cloud computing service model.</p>
        <p>Learn more at <a href="https://github.com/openshift/maas">GitHub</a></p>
        <p>See documentation at https://docs.openshift.com/maas</p>
    </body>
    </html>
    """


@pytest.fixture
def sample_markdown_content():
    """Sample Markdown content for testing."""
    return b"""
# MaaS Documentation

## Introduction
Models-as-a-Service provides ML model serving capabilities.

## Links
- [GitHub Repository](https://github.com/openshift/maas)
- [Documentation](https://docs.openshift.com)
- Check out https://huggingface.co/models for models
"""


@pytest.fixture
def sample_chunks():
    """Sample document chunks for testing."""
    return [
        {
            "id": "chunk-001",
            "doc_id": "doc-001",
            "text": "MaaS enables efficient model serving on Kubernetes.",
            "score": 0.95
        },
        {
            "id": "chunk-002",
            "doc_id": "doc-001",
            "text": "vLLM provides high-performance inference for LLMs.",
            "score": 0.88
        }
    ]


@pytest.fixture
def mock_tei_client():
    """Mock TEI embedding client."""
    with patch("worker.embeddings.EmbeddingClient") as mock:
        client = MagicMock()
        client.embed.return_value = [0.1] * 768  # 768-dim embedding
        client.embed_batch.return_value = [[0.1] * 768]
        mock.return_value = client
        yield client


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client."""
    with patch("worker.embeddings.QdrantStorage") as mock:
        storage = MagicMock()
        storage.upsert.return_value = {"status": "success", "citation_id": "test-id"}
        storage.search.return_value = [
            {
                "id": "citation-001",
                "score": 0.92,
                "text": "Citation text content",
                "source_url": "https://github.com/test/repo",
                "title": "Test Citation"
            }
        ]
        mock.return_value = storage
        yield storage


@pytest.fixture
def mock_requests():
    """Mock requests library."""
    with patch("requests.Session") as mock:
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.content = b"Test content"
        response.headers = {"Content-Type": "text/html"}
        response.url = "https://example.com"
        response.json.return_value = {"result": []}
        
        session.get.return_value = response
        session.post.return_value = response
        mock.return_value = session
        
        yield session


@pytest.fixture
def mock_github_api():
    """Mock GitHub API responses."""
    with patch("libs.github.GitHubFetcher") as mock:
        fetcher = MagicMock()
        fetcher.fetch_repo_docs.return_value = {
            "text": "# Repository README\n\nThis is a test repository.",
            "title": "test-repo",
            "files": 1,
            "source": "github.com/test/repo"
        }
        mock.return_value = fetcher
        yield fetcher
