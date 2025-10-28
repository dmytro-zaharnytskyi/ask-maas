"""RQ Worker Jobs for Citation Processing."""

import os
import re
import time
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse, urlunparse, urljoin

import redis
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from libs.normalizers import normalize_content
from libs.links import extract_links, is_url_allowed
from worker.embeddings import embed_text, upsert_to_qdrant

logger = logging.getLogger(__name__)

# Configuration
MAX_CONTENT_SIZE = 512 * 1024  # 512KB
CONNECT_TIMEOUT = 5  # seconds
READ_TIMEOUT = 10  # seconds
MAX_REDIRECTS = 2
TTL_DAYS = int(os.getenv("CITATION_TTL_DAYS", "7"))

# Redis client for caching
redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)


def create_http_session() -> requests.Session:
    """Create HTTP session with retry logic and timeouts."""
    session = requests.Session()
    
    retry = Retry(
        total=2,
        backoff_factor=0.3,
        status_forcelist=[500, 502, 503, 504]
    )
    
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Set headers
    session.headers.update({
        "User-Agent": "CitationExpander/1.0 (compatible; ask-maas)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    })
    
    return session


def canonicalize_url(url: str) -> str:
    """Canonicalize URL for consistent storage."""
    parsed = urlparse(url.lower())
    
    # Remove fragment
    parsed = parsed._replace(fragment="")
    
    # Remove trailing slash from path
    path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
    parsed = parsed._replace(path=path)
    
    # Sort query parameters
    if parsed.query:
        params = sorted(parsed.query.split("&"))
        parsed = parsed._replace(query="&".join(params))
    
    return urlunparse(parsed)


def fetch_url(url: str, session: Optional[requests.Session] = None) -> Dict[str, Any]:
    """Fetch URL with timeout and size limits."""
    from app.main import metrics
    
    if not session:
        session = create_http_session()
    
    canonical_url = canonicalize_url(url)
    
    # Check if URL is allowed
    if not is_url_allowed(canonical_url):
        logger.warning(f"URL not allowed by filter: {canonical_url}")
        metrics["fetched_err"].inc()
        raise ValueError(f"URL not allowed by filter: {canonical_url}")
    
    try:
        response = session.get(
            canonical_url,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            stream=True,
            allow_redirects=True,
            verify=True
        )
        response.raise_for_status()
        
        # Check content size
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_CONTENT_SIZE:
            metrics["fetched_err"].inc()
            raise ValueError(f"Content too large: {content_length} bytes")
        
        # Read content with size limit
        content_chunks = []
        total_size = 0
        
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                content_chunks.append(chunk)
                total_size += len(chunk)
                
                if total_size > MAX_CONTENT_SIZE:
                    metrics["fetched_err"].inc()
                    raise ValueError(f"Content exceeds maximum size: {total_size} bytes")
        
        content = b"".join(content_chunks)
        
        metrics["fetched_ok"].inc()
        metrics["size_bytes"].observe(total_size)
        
        return {
            "url": response.url,  # Final URL after redirects
            "canonical_url": canonical_url,
            "content": content,
            "content_type": response.headers.get("Content-Type", "text/html"),
            "status_code": response.status_code,
            "size": total_size,
            "fetched_at": datetime.utcnow().isoformat()
        }
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch URL {url}: {e}")
        metrics["fetched_err"].inc()
        raise


def parse_normalize(content: bytes, content_type: str, url: str) -> Dict[str, Any]:
    """Parse and normalize content based on type."""
    try:
        normalized = normalize_content(content, content_type, url)
        
        # Extract links from normalized content
        links = extract_links(normalized.get("text", ""), url)
        
        return {
            **normalized,
            "links": links,
            "parsed_at": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Failed to parse/normalize content: {e}")
        raise


def chunk_text(text: str, max_length: int = 500, overlap: int = 50) -> List[str]:
    """Split text into overlapping chunks."""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = min(start + max_length, len(text))
        
        # Try to break at sentence boundary
        if end < len(text):
            # Look for sentence end markers
            for marker in ['. ', '\n\n', '\n', '! ', '? ']:
                last_marker = text.rfind(marker, start, end)
                if last_marker != -1 and last_marker > start + max_length // 2:
                    end = last_marker + len(marker.rstrip())
                    break
        
        chunks.append(text[start:end])
        start = end - overlap if end < len(text) else end
    
    return chunks


def embed_upsert(
    text: str,
    url: str,
    parent_doc_id: str,
    parent_chunk_id: str,
    depth: int,
    title: Optional[str] = None,
    content_type: str = "text/html"
) -> Dict[str, Any]:
    """Embed text and upsert to Qdrant."""
    from app.main import metrics
    
    try:
        # Chunk the text if it's too large (use 400 chars for TEI limit)
        chunks = chunk_text(text, max_length=400, overlap=50)
        logger.info(f"Split text into {len(chunks)} chunks for {url}")
        
        results = []
        stored_chunks = 0
        
        for chunk_idx, chunk_content in enumerate(chunks):
            # Generate unique ID for this chunk
            citation_id = hashlib.sha256(f"{parent_chunk_id}:{url}:chunk_{chunk_idx}".encode()).hexdigest()
            
            try:
                # Embed text chunk
                embedding = embed_text(chunk_content)
                
                # Prepare metadata
                metadata = {
                    "source_url": url,
                    "parent_doc_id": parent_doc_id,
                    "parent_chunk_id": parent_chunk_id,
                    "fetched_at": datetime.utcnow().isoformat(),
                    "ttl_expires_at": (datetime.utcnow() + timedelta(days=TTL_DAYS)).isoformat(),
                    "depth": depth,
                    "title": title or url,
                    "content_type": content_type,
                    "text_preview": chunk_content[:500] if chunk_content else "",
                    "chunk_index": chunk_idx,
                    "total_chunks": len(chunks)
                }
                
                # Upsert to Qdrant
                result = upsert_to_qdrant(
                    citation_id=citation_id,
                    embedding=embedding,
                    text=chunk_content,
                    metadata=metadata
                )
                
                stored_chunks += 1
                results.append({
                    "citation_id": citation_id,
                    "chunk_idx": chunk_idx,
                    **result
                })
                
            except Exception as chunk_error:
                logger.error(f"Failed to embed chunk {chunk_idx}: {chunk_error}")
                # Continue with other chunks
        
        # Store links in Redis for the first chunk
        if text and stored_chunks > 0:
            links = extract_links(text, url)
            if links:
                redis_key = f"citation_links:{parent_chunk_id}:{url}"
                redis_client.hset(redis_key, mapping={
                    "urls": ",".join(links[:10]),  # Store up to 10 links
                    "parent_chunk_id": parent_chunk_id
                })
                redis_client.expire(redis_key, TTL_DAYS * 86400)
        
        if stored_chunks > 0:
            metrics["embedded_ok"].inc()
            logger.info(f"Successfully stored {stored_chunks}/{len(chunks)} chunks for {url}")
        
        return {
            "status": "success" if stored_chunks > 0 else "partial",
            "chunks_stored": stored_chunks,
            "total_chunks": len(chunks),
            "results": results[:3]  # Return first 3 results for brevity
        }
    
    except Exception as e:
        logger.error(f"Failed to embed/upsert: {e}")
        raise


def fetch_and_process_citation(
    url: str,
    parent_doc_id: str,
    parent_chunk_id: str,
    depth: int = 0
) -> Dict[str, Any]:
    """Main job to fetch, parse, embed and store a citation."""
    logger.info(f"Processing citation: {url} (depth={depth})")
    
    # Check if already processed recently
    cache_key = f"citation_processed:{hashlib.sha256(url.encode()).hexdigest()}"
    if redis_client.exists(cache_key):
        logger.info(f"Citation already processed recently: {url}")
        return {"status": "cached", "url": url}
    
    session = create_http_session()
    
    try:
        # Step 1: Fetch URL
        fetch_result = fetch_url(url, session)
        
        # Step 2: Parse and normalize
        parse_result = parse_normalize(
            fetch_result["content"],
            fetch_result["content_type"],
            fetch_result["url"]
        )
        
        # Step 3: Embed and upsert
        embed_result = embed_upsert(
            text=parse_result["text"],
            url=fetch_result["url"],
            parent_doc_id=parent_doc_id,
            parent_chunk_id=parent_chunk_id,
            depth=depth,
            title=parse_result.get("title"),
            content_type=fetch_result["content_type"]
        )
        
        # Mark as processed with TTL
        redis_client.setex(cache_key, TTL_DAYS * 86400, "1")
        
        # Process child links if depth allows
        if depth < 2 and parse_result.get("links"):
            from rq import Queue
            q = Queue("citations", connection=redis_client)
            
            for link in parse_result["links"][:3]:  # Process up to 3 child links
                child_cache_key = f"citation_processed:{hashlib.sha256(link.encode()).hexdigest()}"
                if not redis_client.exists(child_cache_key):
                    q.enqueue(
                        fetch_and_process_citation,
                        url=link,
                        parent_doc_id=parent_doc_id,
                        parent_chunk_id=parent_chunk_id,
                        depth=depth + 1,
                        job_timeout="10m"
                    )
        
        # Extract citation_id from results (might be multiple chunks)
        citation_id = None
        if embed_result.get("results") and len(embed_result["results"]) > 0:
            citation_id = embed_result["results"][0].get("citation_id")
        
        return {
            "status": "success",
            "url": url,
            "citation_id": citation_id,
            "chunks_stored": embed_result.get("chunks_stored", 0),
            "depth": depth
        }
    
    except Exception as e:
        logger.error(f"Failed to process citation {url}: {e}")
        return {
            "status": "error",
            "url": url,
            "error": str(e)
        }
    
    finally:
        session.close()


def cleanup_expired_citations():
    """Cleanup expired citations from Qdrant (run as cron job)."""
    from worker.embeddings import cleanup_expired_from_qdrant
    
    logger.info("Starting citation cleanup job")
    
    try:
        result = cleanup_expired_from_qdrant()
        logger.info(f"Cleanup completed: {result}")
        return result
    
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise
