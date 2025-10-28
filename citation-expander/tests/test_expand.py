"""Tests for context expansion functionality."""

import pytest
from unittest.mock import patch, MagicMock
import time

from ask_maas_orchestrator_patch.expand import (
    expand_context,
    search_citations_vectordb,
    rerank_results,
    get_chunk_links,
    format_citation_snippet,
    extract_domain
)


def test_extract_domain():
    """Test domain extraction from URLs."""
    assert extract_domain("https://www.github.com/test") == "github.com"
    assert extract_domain("https://docs.openshift.com/page") == "docs.openshift.com"
    assert extract_domain("http://example.com:8080/path") == "example.com:8080"
    assert extract_domain("invalid-url") == "unknown"


def test_format_citation_snippet():
    """Test citation snippet formatting."""
    citation = {
        "source_url": "https://github.com/test/repo",
        "title": "Test Repository",
        "text": "This is a long text that should be truncated after 500 characters" * 20
    }
    
    snippet = format_citation_snippet(citation)
    assert "github.com/Test Repository" in snippet
    assert len(snippet.split("\n")[1]) <= 500


@patch("ask_maas_orchestrator_patch.expand.redis_client")
def test_get_chunk_links(mock_redis):
    """Test loading chunk links from Redis."""
    mock_redis.hgetall.return_value = {
        "urls": "https://example1.com,https://example2.com",
        "parent_chunk_id": "chunk-001"
    }
    
    links = get_chunk_links(["chunk-001", "chunk-002"])
    
    assert "chunk-001" in links
    assert len(links["chunk-001"]) == 2
    assert "https://example1.com" in links["chunk-001"]


@patch("requests.post")
def test_search_citations_vectordb(mock_post):
    """Test searching citations in vector database."""
    # Mock TEI embedding response
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.side_effect = [
        [[0.1] * 768],  # Embedding response
        {
            "result": [
                {
                    "id": "citation-001",
                    "score": 0.95,
                    "payload": {
                        "text_preview": "Test citation",
                        "source_url": "https://example.com",
                        "title": "Example"
                    }
                }
            ]
        }
    ]
    
    results = search_citations_vectordb(
        query="test query",
        filter_urls=["https://example.com"],
        limit=5
    )
    
    assert len(results) == 1
    assert results[0]["id"] == "citation-001"
    assert results[0]["score"] == 0.95


@patch("requests.post")
def test_rerank_results(mock_post):
    """Test result reranking."""
    documents = [
        {"text": "Document 1", "score": 0.8},
        {"text": "Document 2", "score": 0.9},
        {"text": "Document 3", "score": 0.7}
    ]
    
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = [
        {"score": 0.6},
        {"score": 0.95},
        {"score": 0.4}
    ]
    
    reranked = rerank_results("query", documents)
    
    assert reranked[0]["rerank_score"] == 0.95
    assert reranked[0]["text"] == "Document 2"


@patch("ask_maas_orchestrator_patch.expand.search_citations_vectordb")
@patch("ask_maas_orchestrator_patch.expand.get_chunk_links")
@patch("ask_maas_orchestrator_patch.expand.redis_client")
def test_expand_context(mock_redis, mock_get_links, mock_search, sample_chunks):
    """Test context expansion with citations."""
    # Setup mocks
    mock_get_links.return_value = {
        "chunk-001": ["https://github.com/test", "https://docs.example.com"]
    }
    
    mock_search.return_value = [
        {
            "id": "citation-001",
            "score": 0.95,
            "text": "Citation content about MaaS",
            "source_url": "https://github.com/test",
            "title": "MaaS Documentation"
        }
    ]
    
    # Call expand_context
    snippets, metadata = expand_context(
        query="What is MaaS?",
        base_chunks=sample_chunks,
        timeout_ms=800
    )
    
    # Assertions
    assert len(snippets) == 1
    assert "github.com/MaaS Documentation" in snippets[0]
    assert metadata["citations_found"] == 1
    assert metadata["time_ms"] > 0


@patch("ask_maas_orchestrator_patch.expand.search_citations_vectordb")
@patch("ask_maas_orchestrator_patch.expand.enqueue_url_for_processing")
@patch("ask_maas_orchestrator_patch.expand.get_chunk_links")
@patch("ask_maas_orchestrator_patch.expand.redis_client")
def test_expand_context_enqueue_missing(
    mock_redis,
    mock_get_links,
    mock_enqueue,
    mock_search,
    sample_chunks
):
    """Test that missing citations are enqueued for processing."""
    # Setup mocks - return no citations to trigger enqueueing
    mock_get_links.return_value = {
        "chunk-001": ["https://github.com/new", "https://docs.new.com"]
    }
    
    mock_search.return_value = []  # No citations found
    
    mock_enqueue.return_value = "job-123"
    
    # Call expand_context
    snippets, metadata = expand_context(
        query="What is MaaS?",
        base_chunks=sample_chunks,
        timeout_ms=800
    )
    
    # Assertions
    assert len(snippets) == 0
    assert metadata["citations_found"] == 0
    assert metadata["urls_enqueued"] > 0
    mock_enqueue.assert_called()


def test_expand_context_timeout(sample_chunks):
    """Test context expansion with timeout."""
    with patch("ask_maas_orchestrator_patch.expand.search_citations_vectordb") as mock_search:
        # Make search take too long
        def slow_search(*args, **kwargs):
            time.sleep(0.1)
            return []
        
        mock_search.side_effect = slow_search
        
        with patch("ask_maas_orchestrator_patch.expand.get_chunk_links") as mock_links:
            mock_links.return_value = {"chunk-001": ["https://example.com"]}
            
            # Very short timeout
            snippets, metadata = expand_context(
                query="test",
                base_chunks=sample_chunks,
                timeout_ms=50
            )
            
            # Should handle timeout gracefully
            assert metadata["time_ms"] >= 50
