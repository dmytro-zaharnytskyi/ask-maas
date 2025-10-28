"""Context expansion using citation sources."""

import os
import time
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse

import redis
import requests
from rq import Queue

logger = logging.getLogger(__name__)

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TEI_URL = os.getenv("TEI_URL", "http://tei-embeddings:8080")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
RERANKER_URL = os.getenv("RERANKER_URL", "http://tei-reranker:8080")
CITATION_API_URL = os.getenv("CITATION_API_URL", "http://citation-expander:8000")

# Initialize Redis client
redis_client = redis.from_url(REDIS_URL, decode_responses=True)


def search_citations_vectordb(
    query: str,
    filter_urls: Optional[List[str]] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Search citations in Qdrant vector database."""
    try:
        # First, get query embedding from TEI
        response = requests.post(
            f"{TEI_URL}/embed",
            json={"inputs": [query]},
            timeout=5
        )
        response.raise_for_status()
        embedding = response.json()[0]
        
        # Search in Qdrant
        search_payload = {
            "vector": embedding,
            "limit": limit,
            "with_payload": True
        }
        
        if filter_urls:
            search_payload["filter"] = {
                "should": [
                    {"key": "source_url", "match": {"value": url}}
                    for url in filter_urls
                ]
            }
        
        response = requests.post(
            f"{QDRANT_URL}/collections/ask-maas-citations/points/search",
            json=search_payload,
            timeout=5
        )
        response.raise_for_status()
        
        results = response.json().get("result", [])
        
        return [
            {
                "id": hit["id"],
                "score": hit["score"],
                "text": hit["payload"].get("text_preview", ""),
                "source_url": hit["payload"].get("source_url"),
                "title": hit["payload"].get("title"),
                **hit["payload"]
            }
            for hit in results
        ]
    
    except Exception as e:
        logger.error(f"Failed to search citations: {e}")
        return []


def rerank_results(
    query: str,
    documents: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Rerank results using BGE reranker if available."""
    if not RERANKER_URL or not documents:
        return documents
    
    try:
        # Prepare texts for reranking
        texts = [doc.get("text", doc.get("text_preview", ""))[:1000] for doc in documents]
        
        # Call reranker
        response = requests.post(
            f"{RERANKER_URL}/rerank",
            json={
                "query": query,
                "texts": texts
            },
            timeout=3
        )
        
        if response.status_code == 200:
            scores = response.json()
            
            # Add rerank scores and sort
            for i, doc in enumerate(documents):
                if i < len(scores):
                    doc["rerank_score"] = scores[i]["score"]
            
            # Sort by rerank score
            documents.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        else:
            logger.warning(f"Reranker returned status {response.status_code}")
    
    except Exception as e:
        logger.warning(f"Reranking failed, using original order: {e}")
    
    return documents


def enqueue_url_for_processing(
    url: str,
    parent_doc_id: str,
    parent_chunk_id: str
) -> Optional[str]:
    """Enqueue URL for citation processing."""
    try:
        response = requests.post(
            f"{CITATION_API_URL}/enqueue",
            params={
                "url": url,
                "parent_doc_id": parent_doc_id,
                "parent_chunk_id": parent_chunk_id,
                "depth": 0
            },
            timeout=2
        )
        
        if response.status_code == 200:
            result = response.json()
            return result.get("job_id")
    
    except Exception as e:
        logger.error(f"Failed to enqueue URL {url}: {e}")
    
    return None


def get_chunk_links(chunk_ids: List[str]) -> Dict[str, List[str]]:
    """Load per-chunk links from Redis hash."""
    chunk_links = {}
    
    for chunk_id in chunk_ids:
        # Try to get citation links for this chunk
        redis_key = f"citation_links:{chunk_id}"
        links_data = redis_client.hgetall(redis_key)
        
        if links_data and "urls" in links_data:
            urls = links_data["urls"].split(",")
            chunk_links[chunk_id] = urls
    
    return chunk_links


def extract_domain(url: str) -> str:
    """Extract domain from URL for display."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        return domain
    except Exception:
        return "unknown"


def format_citation_snippet(citation: Dict[str, Any]) -> str:
    """Format citation as a snippet for context."""
    source_url = citation.get("source_url", "")
    domain = extract_domain(source_url)
    title = citation.get("title", "Citation")
    text = citation.get("text", citation.get("text_preview", ""))[:500]
    
    return f"(source: {domain}/{title})\n{text}\n"


def expand_context(
    query: str,
    base_chunks: List[Dict[str, Any]],
    timeout_ms: int = 800
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Expand context by searching and fetching citation sources.
    
    Args:
        query: User's search query
        base_chunks: Original document chunks with IDs
        timeout_ms: Maximum time budget in milliseconds
    
    Returns:
        Tuple of (expanded snippets, metadata)
    """
    start_time = time.time() * 1000
    expanded_snippets = []
    metadata = {
        "citations_found": 0,
        "urls_enqueued": 0,
        "time_ms": 0
    }
    
    try:
        # ALWAYS do semantic search across all citations
        # This ensures we find the most relevant content regardless of whether
        # the article explicitly linked to it
        logger.info(f"Searching citations semantically for query: {query[:50]}...")
        
        try:
            # Generate query embedding
            import requests
            tei_url = os.getenv("TEI_URL", "http://tei-embeddings:8080")
            response = requests.post(
                f"{tei_url}/embed",
                json={"inputs": [query]},
                timeout=2
            )
            
            if response.status_code == 200:
                query_embedding = response.json()
                if isinstance(query_embedding, list) and len(query_embedding) > 0:
                    query_embedding = query_embedding[0]
                
                # Search Qdrant with the query embedding
                qdrant_url = os.getenv("QDRANT_URL", "http://qdrant:6333")
                search_response = requests.post(
                    f"{qdrant_url}/collections/ask-maas-citations/points/search",
                    json={
                        "vector": query_embedding,
                        "limit": 5,  # Get top 5 citations
                        "with_payload": True,
                        "score_threshold": 0.3  # Only include relevant results
                    },
                    timeout=2
                )
                
                if search_response.status_code == 200:
                    results = search_response.json().get("result", [])
                    citations = []
                    for r in results:
                        payload = r.get("payload", {})
                        citations.append({
                            "source_url": payload.get("source_url", ""),
                            "title": payload.get("title", "Citation"),
                            "text": payload.get("text", payload.get("text_preview", "")),
                            "score": r.get("score", 0)
                        })
                    
                    logger.info(f"Found {len(citations)} citations via semantic search")
                else:
                    logger.warning(f"Qdrant search failed: {search_response.status_code}")
                    citations = []
            else:
                logger.warning(f"TEI embedding failed: {response.status_code}")
                citations = []
                
        except Exception as e:
            logger.warning(f"Semantic citation search failed: {e}")
            citations = []
        
        # Check timeout
        if (time.time() * 1000 - start_time) > timeout_ms * 0.7:
            # Use 70% of budget for search
            logger.info("Timeout approaching, skipping reranking")
            citations = citations[:3]
        else:
            # Rerank if we have time and reranker is available
            citations = rerank_results(query, citations)[:3]
        
        metadata["citations_found"] = len(citations)
        
        # If less than 3 hits, enqueue unseen URLs
        if len(citations) < 3:
            # Get already processed URLs
            processed_urls = {c.get("source_url") for c in citations}
            
            # Find unprocessed URLs
            unprocessed = [url for url in unique_urls if url not in processed_urls][:3]
            
            # Enqueue for processing (fire and forget)
            for url in unprocessed:
                # Use first chunk as parent
                if chunk_ids:
                    job_id = enqueue_url_for_processing(
                        url=url,
                        parent_doc_id=base_chunks[0].get("doc_id", "unknown"),
                        parent_chunk_id=chunk_ids[0]
                    )
                    if job_id:
                        metadata["urls_enqueued"] += 1
        
        # Format citation snippets
        for citation in citations:
            snippet = format_citation_snippet(citation)
            expanded_snippets.append(snippet)
    
    except Exception as e:
        logger.error(f"Context expansion failed: {e}")
    
    finally:
        metadata["time_ms"] = int(time.time() * 1000 - start_time)
    
    return expanded_snippets, metadata


def expand_context_async(
    query: str,
    base_chunks: List[Dict[str, Any]],
    callback_url: Optional[str] = None
) -> str:
    """
    Asynchronously expand context (returns immediately, processes in background).
    
    Args:
        query: User's search query
        base_chunks: Original document chunks
        callback_url: Optional webhook for results
    
    Returns:
        Job ID for tracking
    """
    try:
        # Create job in Redis queue
        q = Queue("citations", connection=redis_client)
        
        job = q.enqueue(
            expand_context,
            query=query,
            base_chunks=base_chunks,
            timeout_ms=5000,  # Longer timeout for async
            job_timeout="30s"
        )
        
        # Store callback URL if provided
        if callback_url:
            redis_client.setex(
                f"citation_callback:{job.id}",
                300,  # 5 minute TTL
                callback_url
            )
        
        return job.id
    
    except Exception as e:
        logger.error(f"Failed to enqueue async expansion: {e}")
        raise
