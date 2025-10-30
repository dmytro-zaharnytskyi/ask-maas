"""
Simplified Chat API with Unified Vector Retrieval
"""
import asyncio
import time
import uuid
import json
import structlog

from typing import AsyncGenerator
from fastapi import APIRouter, Request, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.models.chat import ChatRequest, ChatResponse, Citation
from app.services.unified_vector_retrieval import UnifiedVectorRetrievalService

logger = structlog.get_logger()
router = APIRouter()


def create_sse_message(data: dict) -> str:
    """Create SSE message - EventSourceResponse adds 'data: ' prefix automatically"""
    return json.dumps(data)


@router.post("/chat/unified")
async def chat_unified(request: ChatRequest, req: Request) -> EventSourceResponse:
    """
    Unified chat endpoint - searches ALL content in one go
    """
    request_id = str(uuid.uuid4())
    logger.info(
        "Chat request received (unified)",
        request_id=request_id,
        query=request.query[:100]
    )
    
    async def generate_response() -> AsyncGenerator[str, None]:
        try:
            # Get services from app state
            app = req.app
            settings = app.state.settings
            
            # Initialize LLM service if not present
            from app.services.llm import LLMService
            if not hasattr(app.state, 'llm_service'):
                app.state.llm_service = LLMService(settings)
            llm_service = app.state.llm_service
            
            # Use unified retrieval
            unified_service = UnifiedVectorRetrievalService(settings)
            
            # Send initial acknowledgment
            yield create_sse_message({
                "id": request_id,
                "type": "start",
                "metadata": {"timestamp": time.time()}
            })
            
            # Search across ALL content (articles + citations) in one query
            logger.info(f"Searching unified vector DB for: {request.query[:100]}")
            retrieval_start = time.time()
            
            retrieved_chunks = await unified_service.search_unified(
                query=request.query,
                top_k=30,  # Get more chunks initially for better selection
                score_threshold=0.0  # No initial threshold, rely on reranking
            )
            
            # Rerank if we have chunks and reranker is available
            if retrieved_chunks and hasattr(unified_service, 'rerank_chunks'):
                logger.info(f"Reranking {len(retrieved_chunks)} chunks", request_id=request_id)
                # Rerank and take top 15
                from app.services.vector_retrieval import VectorRetrievalService
                vector_service = VectorRetrievalService(settings)
                retrieved_chunks = await vector_service.rerank_chunks(request.query, retrieved_chunks)
                retrieved_chunks = retrieved_chunks[:15]
            
            retrieval_time = time.time() - retrieval_start
            logger.info(
                "Unified retrieval and reranking completed",
                request_id=request_id,
                chunks_retrieved=len(retrieved_chunks),
                retrieval_time=retrieval_time,
                sources=[f"{c.metadata.get('source_type')}:{c.title[:30]}" for c in retrieved_chunks[:3]]
            )
            
            # Check if we have results
            if not retrieved_chunks or retrieved_chunks[0].score < 0.3:
                yield create_sse_message({
                    "id": request_id,
                    "type": "text",
                    "content": "I don't have enough information to answer that question. Please try rephrasing or ask about something else."
                })
                yield create_sse_message({"id": request_id, "type": "done"})
                return
            
            # Build context from ALL retrieved chunks
            # Don't add article labels that LLM will echo back
            context_parts = []
            for chunk in retrieved_chunks:
                text = chunk.text
                # Just add the text without labels
                context_parts.append(text)
            
            context = "\n\n".join(context_parts)
            
            # Generate LLM response
            logger.info("Generating LLM response", request_id=request_id)
            llm_start = time.time()
            
            response_text = ""
            async for chunk in llm_service.generate_stream(
                query=request.query,
                context=context,
                max_tokens=2000
            ):
                response_text += chunk
                yield create_sse_message({
                    "id": request_id,
                    "type": "text",
                    "content": chunk
                })
            
            llm_time = time.time() - llm_start
            logger.info(
                "LLM generation completed",
                request_id=request_id,
                llm_time=llm_time,
                response_length=len(response_text)
            )
            
            # Send citations (ALL sources shown)
            citations = []
            seen_sources = set()
            
            for chunk in retrieved_chunks:
                source_url = chunk.url or chunk.metadata.get('source_url', '')
                title = chunk.title
                
                # Deduplicate by URL+title
                source_key = f"{source_url}:{title}"
                if source_key not in seen_sources:
                    seen_sources.add(source_key)
                    
                    # Create citation
                    citations.append(Citation(
                        text="",  # Don't include chunk text in citations, just article name
                        url=source_url,
                        title=title,
                        score=chunk.score
                    ))
            
            # Sort by score
            citations.sort(key=lambda c: c.score, reverse=True)
            
            if citations:
                yield create_sse_message({
                    "id": request_id,
                    "type": "citation",
                    "citations": [c.dict() for c in citations]
                })
            
            # Send completion
            yield create_sse_message({
                "id": request_id,
                "type": "done",
                "metadata": {
                    "retrieval_time": retrieval_time,
                    "llm_time": llm_time,
                    "total_time": time.time() - retrieval_start,
                    "chunks_used": len(retrieved_chunks),
                    "sources": len(citations)
                }
            })
            
        except Exception as e:
            logger.error("Chat request failed", request_id=request_id, error=str(e))
            yield create_sse_message({
                "id": request_id,
                "type": "error",
                "error": "An error occurred processing your request"
            })
            yield create_sse_message({"id": request_id, "type": "done"})
    
    return EventSourceResponse(generate_response())


@router.post("/ingest/unified")
async def ingest_unified(request: dict, req: Request):
    """
    Simple unified ingestion - indexes content directly to Qdrant
    """
    try:
        app = req.app
        settings = app.state.settings
        
        unified_service = UnifiedVectorRetrievalService(settings)
        
        # Extract content
        text = request.get("content", "")
        source_url = request.get("page_url", "")
        title = request.get("title", "Document")
        source_type = request.get("source_type", "article")
        
        # Quick cache check - if already indexed, return immediately
        if not request.get("force_refresh", False):
            # For now, always index to ensure content is there
            # In production, implement proper caching
            pass
        
        # Index content
        chunk_count = await unified_service.index_content(
            text=text,
            source_url=source_url,
            title=title,
            source_type=source_type
        )
        
        return {
            "status": "success",
            "chunk_count": chunk_count,
            "cached": False
        }
        
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "chunk_count": 0
        }
