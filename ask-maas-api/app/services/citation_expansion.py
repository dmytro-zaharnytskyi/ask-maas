"""
Simplified citation expansion without Redis dependency
"""
import os
import time
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

def expand_context(
    query: str,
    base_chunks: List[Dict[str, Any]],
    timeout_ms: int = 800
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Simplified citation expansion - just returns empty results
    since we're using Qdrant for everything now
    
    Args:
        query: User's search query
        base_chunks: Original document chunks with IDs
        timeout_ms: Maximum time budget in milliseconds
    
    Returns:
        Tuple of (expanded snippets, metadata)
    """
    start_time = time.time() * 1000
    
    metadata = {
        "citations_found": 0,
        "urls_enqueued": 0,
        "time_ms": int(time.time() * 1000 - start_time)
    }
    
    # Return empty snippets since we're not using citation expansion anymore
    # All content is already in Qdrant
    return [], metadata

def rerank_results(query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Simplified reranking - just returns results as-is
    Actual reranking happens in the main retrieval pipeline
    """
    return results

def format_citation_snippet(citation: Dict[str, Any]) -> str:
    """
    Format a citation for display
    """
    title = citation.get("title", "Citation")
    text = citation.get("text", "")
    source_url = citation.get("source_url", "")
    
    if source_url:
        return f"[{title}]({source_url}): {text[:200]}..."
    return f"{title}: {text[:200]}..."
