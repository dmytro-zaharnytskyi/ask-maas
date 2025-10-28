"""Enhanced Chat Router with Citation Expansion."""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.services.vector_retrieval import search_documents
from app.services.llm import generate_response
from app.services.config import get_settings
from ask_maas_orchestrator_patch import expand_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

settings = get_settings()


class ChatRequest(BaseModel):
    """Chat request model."""
    query: str = Field(..., description="User query")
    session_id: Optional[str] = Field(None, description="Session ID for context")
    expand_citations: bool = Field(True, description="Enable citation expansion")
    max_chunks: int = Field(5, description="Maximum document chunks to retrieve")


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    sources: List[Dict[str, Any]]
    citations: List[Dict[str, Any]]
    session_id: str
    timestamp: str


async def expand_context_async(
    query: str,
    base_chunks: List[Dict[str, Any]],
    timeout_ms: int = 800
) -> tuple:
    """Async wrapper for expand_context with timeout."""
    try:
        # Run in thread pool to not block event loop
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(
            None,
            expand_context,
            query,
            base_chunks,
            timeout_ms
        )
        
        # Wait with timeout
        snippets, metadata = await asyncio.wait_for(
            future,
            timeout=timeout_ms / 1000.0
        )
        
        return snippets, metadata
    
    except asyncio.TimeoutError:
        logger.warning("Citation expansion timed out")
        return [], {"error": "timeout"}
    except Exception as e:
        logger.error(f"Citation expansion failed: {e}")
        return [], {"error": str(e)}


@router.post("/enhanced", response_model=ChatResponse)
async def chat_with_citations(
    request: ChatRequest,
    background_tasks: BackgroundTasks
):
    """
    Enhanced chat endpoint with citation expansion.
    
    This endpoint:
    1. Searches for relevant document chunks
    2. Expands context with citation sources
    3. Generates response with enriched context
    """
    try:
        # Step 1: Search for relevant documents
        search_results = await search_documents(
            query=request.query,
            limit=request.max_chunks
        )
        
        if not search_results:
            raise HTTPException(
                status_code=404,
                detail="No relevant documents found"
            )
        
        # Extract base chunks
        base_chunks = [
            {
                "id": result.get("id"),
                "doc_id": result.get("doc_id"),
                "text": result.get("text"),
                "score": result.get("score")
            }
            for result in search_results
        ]
        
        # Step 2: Expand context with citations (if enabled)
        citation_snippets = []
        citation_metadata = {}
        
        if request.expand_citations:
            citation_snippets, citation_metadata = await expand_context_async(
                query=request.query,
                base_chunks=base_chunks,
                timeout_ms=800  # 800ms budget
            )
        
        # Step 3: Build enriched context
        context_parts = []
        
        # Add base document chunks
        context_parts.append("## Relevant Documentation:\n")
        for chunk in base_chunks:
            context_parts.append(f"{chunk['text']}\n\n")
        
        # Add citation snippets if available
        if citation_snippets:
            context_parts.append("\n## Additional Context from Citations:\n")
            for snippet in citation_snippets:
                context_parts.append(f"{snippet}\n")
        
        enriched_context = "".join(context_parts)
        
        # Step 4: Generate response with enriched context
        llm_response = await generate_response(
            query=request.query,
            context=enriched_context,
            session_id=request.session_id
        )
        
        # Prepare response
        response = ChatResponse(
            response=llm_response["response"],
            sources=[
                {
                    "doc_id": chunk["doc_id"],
                    "score": chunk["score"],
                    "preview": chunk["text"][:200]
                }
                for chunk in base_chunks[:3]
            ],
            citations=[
                {
                    "source": snippet.split("\n")[0],  # First line has source
                    "text": snippet.split("\n", 1)[1] if "\n" in snippet else snippet
                }
                for snippet in citation_snippets
            ],
            session_id=llm_response.get("session_id", request.session_id),
            timestamp=datetime.utcnow().isoformat()
        )
        
        # Log metrics in background
        background_tasks.add_task(
            log_chat_metrics,
            query_length=len(request.query),
            response_length=len(llm_response["response"]),
            chunks_used=len(base_chunks),
            citations_found=citation_metadata.get("citations_found", 0),
            urls_enqueued=citation_metadata.get("urls_enqueued", 0),
            expansion_time_ms=citation_metadata.get("time_ms", 0)
        )
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat processing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to process chat request"
        )


def log_chat_metrics(**kwargs):
    """Log chat metrics for monitoring."""
    logger.info(f"Chat metrics: {kwargs}")
    
    # TODO: Send to Prometheus or other monitoring system
    # Example with prometheus_client:
    # chat_queries_total.inc()
    # chat_response_length.observe(kwargs["response_length"])
    # citation_expansion_time.observe(kwargs["expansion_time_ms"])


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "chat-enhanced"}
