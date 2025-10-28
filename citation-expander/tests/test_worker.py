"""Tests for RQ worker jobs."""

import pytest
from unittest.mock import patch, MagicMock

from worker.jobs import (
    canonicalize_url,
    fetch_url,
    parse_normalize,
    embed_upsert,
    fetch_and_process_citation
)


def test_canonicalize_url():
    """Test URL canonicalization."""
    # Test removing fragments
    assert canonicalize_url("https://example.com/page#section") == "https://example.com/page"
    
    # Test removing trailing slash
    assert canonicalize_url("https://example.com/page/") == "https://example.com/page"
    
    # Test sorting query parameters
    url1 = "https://example.com/page?b=2&a=1"
    url2 = "https://example.com/page?a=1&b=2"
    assert canonicalize_url(url1) == canonicalize_url(url2)
    
    # Test case normalization
    assert canonicalize_url("HTTPS://EXAMPLE.COM") == "https://example.com"


@patch("worker.jobs.is_url_allowed")
def test_fetch_url(mock_allowed, mock_requests):
    """Test URL fetching."""
    mock_allowed.return_value = True
    
    result = fetch_url("https://example.com/page")
    
    assert result["url"] == "https://example.com"
    assert result["content"] == b"Test content"
    assert result["content_type"] == "text/html"
    assert "fetched_at" in result


def test_fetch_url_not_allowed(mock_requests):
    """Test fetching disallowed URL."""
    with patch("worker.jobs.is_url_allowed", return_value=False):
        with pytest.raises(ValueError, match="not allowed"):
            fetch_url("https://blocked.com")


def test_parse_normalize_html(sample_html_content):
    """Test HTML parsing and normalization."""
    result = parse_normalize(
        sample_html_content,
        "text/html",
        "https://example.com"
    )
    
    assert "text" in result
    assert "MaaS" in result["text"]
    assert "links" in result
    assert len(result["links"]) > 0


def test_parse_normalize_markdown(sample_markdown_content):
    """Test Markdown parsing and normalization."""
    result = parse_normalize(
        sample_markdown_content,
        "text/markdown",
        "https://example.com/doc.md"
    )
    
    assert "text" in result
    assert "Models-as-a-Service" in result["text"]
    assert "links" in result
    assert any("github.com" in link for link in result["links"])


@patch("worker.jobs.embed_text")
@patch("worker.jobs.upsert_to_qdrant")
def test_embed_upsert(mock_upsert, mock_embed, mock_redis):
    """Test embedding and upserting."""
    mock_embed.return_value = [0.1] * 768
    mock_upsert.return_value = {"status": "success"}
    
    result = embed_upsert(
        text="Test content",
        url="https://example.com",
        parent_doc_id="doc-001",
        parent_chunk_id="chunk-001",
        depth=0
    )
    
    assert result["status"] == "success"
    assert "citation_id" in result
    mock_embed.assert_called_once()
    mock_upsert.assert_called_once()


@patch("worker.jobs.fetch_url")
@patch("worker.jobs.parse_normalize")
@patch("worker.jobs.embed_upsert")
def test_fetch_and_process_citation(
    mock_embed_upsert,
    mock_parse,
    mock_fetch,
    mock_redis
):
    """Test full citation processing pipeline."""
    mock_fetch.return_value = {
        "url": "https://example.com",
        "content": b"Test content",
        "content_type": "text/html"
    }
    
    mock_parse.return_value = {
        "text": "Parsed text",
        "title": "Test Title",
        "links": []
    }
    
    mock_embed_upsert.return_value = {
        "citation_id": "test-id",
        "status": "success"
    }
    
    result = fetch_and_process_citation(
        url="https://example.com",
        parent_doc_id="doc-001",
        parent_chunk_id="chunk-001",
        depth=0
    )
    
    assert result["status"] == "success"
    assert result["citation_id"] == "test-id"
    mock_fetch.assert_called_once()
    mock_parse.assert_called_once()
    mock_embed_upsert.assert_called_once()
