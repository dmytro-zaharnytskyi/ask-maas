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

from app.services.retrieval import RetrievalService
from app.services.llm import LLMService
from app.services.cache import CacheService
from app.models.chat import ChatRequest, ChatResponse, Citation, StreamEvent
from app.utils.metrics import track_request_duration, track_token_usage

logger = structlog.get_logger()
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
    cache_service: CacheService = app.state.cache_service
    settings = app.state.settings
    
    # Initialize services
    retrieval_service = RetrievalService(cache_service, settings)
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
            
            # Check if page index exists in cache
            page_index = await cache_service.get_page_index(request.page_url)
            
            if not page_index:
                # Page not indexed yet
                yield create_sse_message({
                    "id": request_id,
                    "type": "error",
                    "content": "Page not indexed. Please ingest the page first.",
                    "metadata": {"error_code": "PAGE_NOT_INDEXED"}
                })
                yield create_sse_message({"id": request_id, "type": "done"})
                return
            
            # Perform retrieval
            logger.info("Starting retrieval", request_id=request_id)
            retrieval_start = time.time()
            
            retrieved_chunks = await retrieval_service.retrieve(
                query=request.query,
                page_url=request.page_url,
                page_index=page_index
            )
            
            retrieval_time = time.time() - retrieval_start
            logger.info(
                "Retrieval completed",
                request_id=request_id,
                chunks_retrieved=len(retrieved_chunks),
                retrieval_time=retrieval_time
            )
            
            # Check if we have enough evidence
            if not retrieved_chunks or (
                retrieved_chunks[0].score < settings.MIN_RERANK_SCORE
            ):
                # Low confidence - abstain
                yield create_sse_message({
                    "id": request_id,
                    "type": "text",
                    "content": settings.ABSTAIN_MESSAGE
                })
                
                # Send top links as citations
                if retrieved_chunks:
                    citations = [
                        Citation(
                            text=chunk.text[:200] + "...",
                            url=chunk.url,
                            title=chunk.title,
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
            context = retrieval_service.format_context(retrieved_chunks)
            
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
            
            # Extract and send citations
            citations = extract_citations(accumulated_text, retrieved_chunks)
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


def extract_citations(text: str, chunks: List) -> List[Citation]:
    """
    Extract citations from generated text
    This is a simple implementation - could be enhanced with NLP
    """
    citations = []
    
    # Look for citation patterns in text (e.g., [1], [2], etc.)
    # For MVP, we'll just use the top chunks as citations
    for i, chunk in enumerate(chunks[:3]):
        citations.append(
            Citation(
                text=chunk.text[:200] + "...",
                url=chunk.url,
                title=chunk.title or f"Section {i+1}",
                score=chunk.score
            )
        )
    
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
