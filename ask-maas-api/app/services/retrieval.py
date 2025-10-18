"""
Retrieval service for hybrid search and reranking
"""
import asyncio
import json
from typing import List, Dict, Any, Optional
import numpy as np
from rank_bm25 import BM25Okapi
import faiss
import httpx
import structlog

from app.services.config import Settings
from app.models.chat import Chunk

logger = structlog.get_logger()


class RetrievalService:
    """Service for document retrieval and ranking"""
    
    def __init__(self, cache_service, settings: Settings):
        self.cache_service = cache_service
        self.settings = settings
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    async def retrieve(
        self, 
        query: str, 
        page_url: str, 
        page_index: Dict[str, Any]
    ) -> List[Chunk]:
        """
        Perform hybrid retrieval with lexical and dense search
        """
        try:
            # Extract chunks from page index
            chunks = page_index.get("chunks", [])
            if not chunks:
                logger.warning("No chunks found in page index", page_url=page_url)
                return []
            
            # Check if this is a simplified index (no FAISS)
            if page_index.get("metadata", {}).get("simplified", False):
                # Simple text search for MVP - now with multiple chunks
                logger.info(f"Using simplified text search on {len(chunks)} chunks", page_url=page_url)
                
                # Score chunks based on keyword overlap with query
                query_words = set(query.lower().split())
                scored_chunks = []
                
                for chunk in chunks[:10]:  # Process first 10 chunks for speed
                    chunk_text = chunk.get("text", "").lower()
                    chunk_words = set(chunk_text.split())
                    
                    # Calculate simple relevance score - more generous scoring
                    overlap = len(query_words.intersection(chunk_words))
                    # Use minimum of query words and overlap to be more lenient
                    score = overlap / max(min(len(query_words), 5), 1)  # Cap denominator at 5
                    
                    # Boost score if exact query substring appears
                    if query.lower() in chunk_text:
                        score += 0.5
                    
                    # Ensure minimum score for any matching chunk
                    if overlap > 0:
                        score = max(score, 0.2)  # Minimum score of 0.2 for any match
                    
                    if score > 0:
                        scored_chunks.append(Chunk(
                            id=str(chunk.get("chunk_id", 0)),
                            text=chunk.get("text", "")[:1500],  # Limit chunk size for LLM
                            url=chunk.get("url", page_url),
                            title=chunk.get("title", "Article"),
                            score=min(score, 1.0),
                            chunk_id=chunk.get("chunk_id", 0)
                        ))
                
                # Sort by score and return top chunks
                scored_chunks.sort(key=lambda x: x.score, reverse=True)
                return scored_chunks[:3]  # Return top 3 relevant chunks
            
            # Get FAISS index for regular processing
            faiss_index = page_index.get("index")
            if not faiss_index:
                # Fallback to simple search if no index
                logger.info("No FAISS index, using simple search", page_url=page_url)
                if chunks:
                    chunk = chunks[0]
                    return [Chunk(
                        id=str(chunk.get("chunk_id", 0)),
                        text=chunk.get("text", ""),
                        url=chunk.get("url", page_url),
                        title=chunk.get("title", "Article"),
                        score=0.9,
                        chunk_id=0
                    )]
                return []
            
            # Check if faiss_index is the right type
            import faiss
            if not isinstance(faiss_index, faiss.Index):
                logger.error(f"Invalid FAISS index type: {type(faiss_index)}")
                # Fallback to simple search
                if chunks:
                    chunk = chunks[0]
                    return [Chunk(
                        id=str(chunk.get("chunk_id", 0)),
                        text=chunk.get("text", ""),
                        url=chunk.get("url", page_url),
                        title=chunk.get("title", "Article"),
                        score=0.9,
                        chunk_id=0
                    )]
                return []
            
            # Perform hybrid search
            candidates = await self._hybrid_search(
                query=query,
                chunks=chunks,
                faiss_index=faiss_index
            )
            
            # Rerank candidates
            reranked = await self._rerank(query, candidates)
            
            return reranked[:self.settings.RERANK_TOP_K]
            
        except Exception as e:
            logger.error("Retrieval failed", error=str(e), exc_info=True)
            return []
    
    async def _hybrid_search(
        self, 
        query: str, 
        chunks: List[Dict], 
        faiss_index: Any
    ) -> List[Chunk]:
        """
        Combine lexical and dense retrieval
        """
        # Lexical search with BM25
        texts = [chunk.get("text", "") for chunk in chunks]
        tokenized_texts = [text.lower().split() for text in texts]
        tokenized_query = query.lower().split()
        
        bm25 = BM25Okapi(tokenized_texts)
        lexical_scores = bm25.get_scores(tokenized_query)
        
        # Dense search with FAISS
        query_embedding = await self._get_embedding(query)
        
        if query_embedding is not None:
            k = min(self.settings.RETRIEVAL_TOP_K, len(chunks))
            try:
                # FAISS search returns distances and indices
                distances, indices = faiss_index.search(
                    np.array([query_embedding], dtype=np.float32), 
                    k
                )
                # Convert distances to scores (lower distance = higher score)
                # Using negative distance as score
                dense_scores = -distances[0]  
                indices = indices[0]
            except Exception as e:
                logger.error(f"FAISS search failed: {e}")
                # Fallback to lexical only
                indices = np.argsort(lexical_scores)[::-1][:self.settings.RETRIEVAL_TOP_K]
                dense_scores = np.zeros(len(indices))
        else:
            # Fallback to lexical only
            indices = np.argsort(lexical_scores)[::-1][:self.settings.RETRIEVAL_TOP_K]
            dense_scores = np.zeros(len(indices))
        
        # Reciprocal Rank Fusion (RRF)
        candidates = []
        k = 60  # RRF constant
        
        for i, idx in enumerate(indices):
            if idx < len(chunks):
                chunk_data = chunks[idx]
                
                # Calculate RRF score
                lexical_rank = np.where(np.argsort(lexical_scores)[::-1] == idx)[0]
                lexical_rank = lexical_rank[0] if len(lexical_rank) > 0 else len(chunks)
                
                rrf_score = (1 / (k + i + 1)) + (1 / (k + lexical_rank + 1))
                
                candidates.append(Chunk(
                    id=chunk_data.get("id", str(idx)),
                    text=chunk_data.get("text", ""),
                    score=float(rrf_score),
                    url=chunk_data.get("url", ""),
                    title=chunk_data.get("title", ""),
                    headings=chunk_data.get("headings", []),
                    source=chunk_data.get("source", "article"),
                    metadata=chunk_data.get("metadata", {})
                ))
        
        return sorted(candidates, key=lambda x: x.score, reverse=True)
    
    async def _get_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        Get embedding from TEI service
        """
        try:
            response = await self.http_client.post(
                f"{self.settings.TEI_EMBEDDINGS_URL}/embed",
                json={"inputs": [text]}
            )
            
            if response.status_code == 200:
                result = response.json()
                if result and len(result) > 0:
                    return np.array(result[0], dtype=np.float32)
            
            logger.error("Failed to get embedding", status=response.status_code)
            return None
            
        except Exception as e:
            logger.error("Embedding request failed", error=str(e))
            return None
    
    async def _rerank(self, query: str, candidates: List[Chunk]) -> List[Chunk]:
        """
        Rerank candidates using cross-encoder
        """
        if not candidates:
            return []
        
        try:
            # Prepare pairs for reranking
            pairs = [[query, candidate.text] for candidate in candidates]
            
            response = await self.http_client.post(
                f"{self.settings.TEI_RERANKER_URL}/rerank",
                json={"query": query, "texts": [c.text for c in candidates]}
            )
            
            if response.status_code == 200:
                scores = response.json()
                
                # Update candidate scores based on reranker results
                # The reranker returns list of {index: int, score: float}
                for result in scores:
                    if isinstance(result, dict) and 'index' in result and 'score' in result:
                        idx = result['index']
                        if idx < len(candidates):
                            candidates[idx].score = float(result['score'])
                
                # Sort by reranker score
                return sorted(candidates, key=lambda x: x.score, reverse=True)
            
            logger.warning("Reranking failed, using original scores")
            return candidates
            
        except Exception as e:
            logger.error("Reranking failed", error=str(e))
            return candidates
    
    def format_context(self, chunks: List[Chunk]) -> str:
        """
        Format retrieved chunks into context for LLM
        """
        context_parts = []
        
        for i, chunk in enumerate(chunks):
            # Add source information
            source_info = f"[Source {i+1}: {chunk.title or chunk.source}]"
            
            # Add headings if available
            if chunk.headings:
                heading_path = " > ".join(chunk.headings)
                source_info += f"\n{heading_path}"
            
            # Add URL if available
            if chunk.url:
                source_info += f"\nURL: {chunk.url}"
            
            # Add the chunk text
            context_parts.append(f"{source_info}\n\n{chunk.text}\n")
        
        return "\n---\n".join(context_parts)
    
    async def close(self):
        """Clean up resources"""
        await self.http_client.aclose()
