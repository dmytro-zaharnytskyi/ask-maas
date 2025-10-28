"""Tests for FastAPI application."""

import pytest
from fastapi.testclient import TestClient


def test_health_endpoint(test_client):
    """Test health check endpoint."""
    response = test_client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "timestamp" in data
    assert "checks" in data


def test_metrics_endpoint(test_client):
    """Test Prometheus metrics endpoint."""
    response = test_client.get("/metrics")
    assert response.status_code == 200
    assert "citation_fetched_ok_total" in response.text
    assert "citation_queue_depth" in response.text


def test_root_endpoint(test_client):
    """Test root endpoint."""
    response = test_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "citation-expander"
    assert "version" in data


def test_enqueue_citation(test_client, mock_rq_queue):
    """Test citation enqueue endpoint."""
    response = test_client.post(
        "/enqueue",
        params={
            "url": "https://github.com/test/repo",
            "parent_doc_id": "doc-001",
            "parent_chunk_id": "chunk-001"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "enqueued"
    assert "job_id" in data
