"""
Chat endpoint for Q&A with SSE streaming
"""
import asyncio
import json
import time
from typing import AsyncGenerator, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
import structlog

from app.services.vector_retrieval import VectorRetrievalService
from app.services.llm import LLMService
# Cache service removed - using Qdrant only
from app.models.chat import ChatRequest, ChatResponse, Citation, StreamEvent
from app.utils.metrics import track_request_duration, track_token_usage

logger = structlog.get_logger()

# Try to import citation expansion if available
try:
    from app.services.citation_expansion import expand_context
    citation_expansion_available = True
    logger.info("Citation expansion enabled")
except ImportError:
    citation_expansion_available = False
    logger.warning("Citation expansion not available")

router = APIRouter(tags=["chat"])


class ChatRequestBody(BaseModel):
    """Chat request model"""
    query: str = Field(..., min_length=1, max_length=500, description="User's question")
    page_url: str = Field(..., description="URL of the article being queried")
    session_id: Optional[str] = Field(default=None, description="Session ID for conversation tracking")
    stream: bool = Field(default=True, description="Enable SSE streaming")
    

class ChatResponseChunk(BaseModel):
    """Response chunk for streaming"""
    id: str
    type: str  # "text", "citation", "error", "done"
    content: Optional[str] = None
    citations: Optional[List[Citation]] = None
    metadata: Optional[Dict] = None


@router.post("/chat")
async def chat_endpoint(
    request: ChatRequestBody,
    req: Request,
    background_tasks: BackgroundTasks
) -> EventSourceResponse:
    """
    Handle chat requests with SSE streaming
    """
    start_time = time.time()
    request_id = str(uuid4())
    
    logger.info(
        "Chat request received",
        request_id=request_id,
        query_length=len(request.query),
        page_url=request.page_url,
        stream=request.stream
    )
    
    # Get services from app state
    app = req.app
    # No cache service - using Qdrant directly
    settings = app.state.settings
    
    # Initialize services - use vector retrieval for semantic search
    vector_retrieval_service = VectorRetrievalService(settings)
    llm_service = LLMService(settings)
    
    async def generate_response() -> AsyncGenerator[str, None]:
        """Generate SSE stream"""
        try:
            # Send initial acknowledgment
            yield create_sse_message({
                "id": request_id,
                "type": "start",
                "metadata": {
                    "timestamp": time.time(),
                    "page_url": request.page_url
                }
            })
            
            # ALWAYS perform fresh vector-based retrieval for EVERY query
            logger.info(f"Starting FRESH vector-based semantic search for query: {request.query[:100]}", request_id=request_id)
            retrieval_start = time.time()
            
            # Use pure vector embeddings for semantic similarity - NO keyword matching
            # Always search globally across ALL articles for comprehensive context
            retrieved_chunks = await vector_retrieval_service.retrieve_with_vectors(
                query=request.query,
                top_k=30,  # Get more chunks initially for reranking
                similarity_threshold=0.0  # No threshold initially, let reranker decide
            )
            
            # Rerank chunks for better relevance
            if len(retrieved_chunks) > 0:
                logger.info(f"Reranking {len(retrieved_chunks)} chunks for better relevance", request_id=request_id)
                retrieved_chunks = await vector_retrieval_service.rerank_chunks(request.query, retrieved_chunks)
                # Take only top chunks after reranking
                retrieved_chunks = retrieved_chunks[:15]  # Keep top 15 after reranking
            
            retrieval_time = time.time() - retrieval_start
            logger.info(
                "Retrieval and reranking completed",
                request_id=request_id,
                chunks_retrieved=len(retrieved_chunks),
                retrieval_time=retrieval_time
            )
            
            # Check if we have enough evidence
            if not retrieved_chunks:
                logger.warning("No chunks retrieved for query", request_id=request_id)
                yield create_sse_message({
                    "id": request_id,
                    "type": "text",
                    "content": "I couldn't find relevant information to answer your question. Please try rephrasing or asking about a different topic."
                })
                yield create_sse_message({"id": request_id, "type": "done"})
                return
            
            # Log retrieved chunks for debugging
            logger.info(
                "Retrieved chunks from pages",
                request_id=request_id,
                chunks_count=len(retrieved_chunks),
                top_scores=[chunk.score for chunk in retrieved_chunks[:3]],
                pages=[chunk.metadata.get("page_title", "Unknown") for chunk in retrieved_chunks[:3]]
            )
            
            # IMPORTANT: Try citation expansion BEFORE abstaining
            # Even if base chunks have low scores, citations might have better info
            citation_snippets_found = []
            if citation_expansion_available:
                logger.info(f"Citation expansion available, attempting for query", request_id=request_id)
                try:
                    # Convert chunks to expected format
                    base_chunks = [
                        {
                            "id": str(chunk.id) if hasattr(chunk, 'id') else str(i),
                            "doc_id": chunk.metadata.get("page_url", ""),
                            "text": chunk.text,
                            "score": chunk.score
                        }
                        for i, chunk in enumerate(retrieved_chunks)
                    ]
                    
                    # Try citation expansion
                    async def expand_citations():
                        return await asyncio.to_thread(
                            expand_context, 
                            request.query, 
                            base_chunks,
                            800
                        )
                    
                    citation_snippets, citation_metadata = await asyncio.wait_for(
                        expand_citations(),
                        timeout=1.0
                    )
                    
                    if citation_snippets:
                        logger.info(
                            "Citation expansion successful", 
                            request_id=request_id,
                            citations_found=len(citation_snippets)
                        )
                        citation_snippets_found = citation_snippets
                    
                except asyncio.TimeoutError:
                    logger.warning("Citation expansion timed out", request_id=request_id)
                except Exception as e:
                    logger.warning("Citation expansion failed", request_id=request_id, error=str(e))
            
            # Only abstain if confidence is very low AND no citations found
            if retrieved_chunks[0].score < 0.05 and not citation_snippets_found:  # Very low threshold
                yield create_sse_message({
                    "id": request_id,
                    "type": "text",
                    "content": settings.ABSTAIN_MESSAGE
                })
                
                # Send top links as citations
                citations = [
                    Citation(
                        text=chunk.text[:200] + "...",
                        url=chunk.url,
                        title=chunk.title or chunk.metadata.get("page_title", "Article"),
                        score=chunk.score
                    )
                    for chunk in retrieved_chunks[:3]
                ]
                yield create_sse_message({
                    "id": request_id,
                    "type": "citation",
                    "citations": [c.dict() for c in citations]
                })
                
                yield create_sse_message({"id": request_id, "type": "done"})
                return
            
            # Generate response with LLM
            logger.info("Starting LLM generation", request_id=request_id)
            generation_start = time.time()
            
            # Prepare context from retrieved chunks
            context = vector_retrieval_service.format_context(retrieved_chunks)
            
            # Add citation snippets if found (from earlier expansion)
            if citation_snippets_found:
                logger.info(f"Adding {len(citation_snippets_found)} citation snippets to context", request_id=request_id)
                context += "\n\n## Additional Context from Citations:\n"
                context += "\n\n".join(citation_snippets_found[:3])
            
            # Stream tokens from LLM
            token_count = 0
            first_token_time = None
            accumulated_text = ""
            
            async for token_chunk in llm_service.generate_stream(
                query=request.query,
                context=context,
                max_tokens=settings.MAX_TOKENS
            ):
                if first_token_time is None:
                    first_token_time = time.time()
                    logger.info(
                        "First token received",
                        request_id=request_id,
                        time_to_first_token=first_token_time - start_time
                    )
                
                token_count += 1
                accumulated_text += token_chunk
                
                # Send text chunk
                yield create_sse_message({
                    "id": request_id,
                    "type": "text",
                    "content": token_chunk
                })
                
                # Small delay to prevent overwhelming client
                if token_count % 10 == 0:
                    await asyncio.sleep(0.01)
            
            generation_time = time.time() - generation_start
            
            # Extract and send citations with proper article attribution
            citations = extract_citations_with_context(accumulated_text, retrieved_chunks)
            
            # Add external citations from citation expansion
            if citation_snippets_found:
                logger.info(f"Adding {len(citation_snippets_found)} external citation sources", request_id=request_id)
                for snippet in citation_snippets_found:
                    # Parse snippet format: "(source: domain/title)\ntext"
                    if "(source:" in snippet:
                        source_line = snippet.split("\n")[0]
                        source_text = source_line.replace("(source:", "").replace(")", "").strip()
                        snippet_text = snippet.split("\n", 1)[1] if "\n" in snippet else snippet
                        
                        # Create citation object
                        citations.append(Citation(
                            text="",  # Don't include snippet text
                            url=f"https://{source_text.split('/')[0]}",  # Extract domain
                            title=source_text,
                            score=0.8  # High score for external citations
                        ))
            
            if citations:
                yield create_sse_message({
                    "id": request_id,
                    "type": "citation",
                    "citations": [c.dict() for c in citations]
                })
            
            # Send completion event
            yield create_sse_message({
                "id": request_id,
                "type": "done",
                "metadata": {
                    "total_time": time.time() - start_time,
                    "retrieval_time": retrieval_time,
                    "generation_time": generation_time,
                    "token_count": token_count,
                    "chunks_used": len(retrieved_chunks)
                }
            })
            
            # Track metrics in background
            background_tasks.add_task(
                track_metrics,
                request_id=request_id,
                total_time=time.time() - start_time,
                retrieval_time=retrieval_time,
                generation_time=generation_time,
                token_count=token_count,
                chunks_used=len(retrieved_chunks)
            )
            
            logger.info(
                "Chat request completed",
                request_id=request_id,
                total_time=time.time() - start_time,
                token_count=token_count
            )
            
        except asyncio.CancelledError:
            logger.warning("Chat stream cancelled", request_id=request_id)
            yield create_sse_message({
                "id": request_id,
                "type": "error",
                "content": "Stream cancelled by client"
            })
            raise
            
        except Exception as e:
            logger.error(
                "Chat request failed",
                request_id=request_id,
                error=str(e),
                exc_info=True
            )
            yield create_sse_message({
                "id": request_id,
                "type": "error",
                "content": f"An error occurred: {str(e)}"
            })
            yield create_sse_message({"id": request_id, "type": "done"})
    
    # Return SSE response
    return EventSourceResponse(
        generate_response(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "X-Request-ID": request_id
        }
    )


def create_sse_message(data: Dict) -> str:
    """Create SSE message format"""
    # EventSourceResponse adds the "data: " prefix automatically
    # So we just return the JSON string
    return json.dumps(data)


def extract_citations_with_context(text: str, chunks: List) -> List[Citation]:
    """
    Extract citations with proper article context
    """
    citations = []
    seen_pages = set()
    
    # Use top chunks as citations, ensuring diversity across articles
    for chunk in chunks[:5]:
        page_title = chunk.metadata.get("page_title", chunk.title or "Article")
        
        # Skip if we already have a citation from this page
        if page_title in seen_pages and len(citations) >= 3:
            continue
        
        citations.append(
            Citation(
                text="",  # Don't include chunk text in citations
                url=chunk.url,
                title=page_title,
                score=chunk.score
            )
        )
        seen_pages.add(page_title)
        
        if len(citations) >= 3:
            break
    
    return citations


async def track_metrics(
    request_id: str,
    total_time: float,
    retrieval_time: float,
    generation_time: float,
    token_count: int,
    chunks_used: int
):
    """Track performance metrics"""
    # This would integrate with Prometheus metrics
    logger.info(
        "Performance metrics",
        request_id=request_id,
        total_time=total_time,
        retrieval_time=retrieval_time,
        generation_time=generation_time,
        token_count=token_count,
        chunks_used=chunks_used,
        tokens_per_second=token_count / generation_time if generation_time > 0 else 0
    )
