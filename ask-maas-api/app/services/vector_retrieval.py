"""
Vector-based retrieval service using embeddings and cosine similarity
"""
from typing import List, Dict, Any, Optional
import httpx
import structlog
import math

from app.services.config import Settings
from app.models.chat import Chunk

logger = structlog.get_logger()


class VectorRetrievalService:
    """Service for vector-based document retrieval with semantic search"""
    
    def __init__(self, cache_service, settings: Settings):
        self.cache_service = cache_service
        self.settings = settings
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.embeddings_url = settings.TEI_EMBEDDINGS_URL
        self.reranker_url = settings.TEI_RERANKER_URL
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    async def get_query_embedding(self, query: str) -> Optional[List[float]]:
        """Generate embedding for the query using TEI service"""
        try:
            response = await self.http_client.post(
                f"{self.embeddings_url}/embed",
                json={"inputs": [query]}
            )
            
            if response.status_code == 200:
                embeddings = response.json()
                if embeddings and len(embeddings) > 0:
                    return embeddings[0]
            
            logger.warning(f"Failed to get embeddings: {response.status_code}")
            return None
            
        except Exception as e:
            logger.error(f"Error generating query embedding: {e}")
            return None
    
    async def retrieve_with_vectors(
        self,
        query: str,
        top_k: int = 10,
        similarity_threshold: float = 0.0
    ) -> List[Chunk]:
        """
        Perform PURE vector-based retrieval across all indexed content.
        Always performs fresh search for every query.
        """
        try:
            # Always generate fresh query embedding for each query
            logger.info(f"Generating fresh embedding for query: {query[:100]}...")
            query_embedding = await self.get_query_embedding(query)
            
            if query_embedding is None:
                logger.error("Could not generate query embedding")
                return []
            
            query_vector = query_embedding
            
            # Get all indexed pages - fresh retrieval every time
            all_page_urls = await self.cache_service.get_all_page_urls()
            
            if not all_page_urls:
                logger.warning("No indexed pages found")
                return []
            
            logger.info(f"Searching across {len(all_page_urls)} indexed pages")
            
            # Collect ALL chunks with embeddings for global search
            all_chunks_with_scores = []
            total_chunks_searched = 0
            
            # Process pages in parallel for better performance
            for page_url in all_page_urls:
                page_index = await self.cache_service.get_page_index(page_url)
                if not page_index:
                    continue
                
                chunks = page_index.get("chunks", [])
                page_title = page_index.get("metadata", {}).get("title", "Unknown")
                
                # Process each chunk's embedding
                for i, chunk in enumerate(chunks):
                    # Get embedding from chunk
                    chunk_embedding = chunk.get("embedding")
                    
                    if chunk_embedding and len(chunk_embedding) > 0:
                        # Calculate cosine similarity
                        similarity = self.cosine_similarity(query_vector, chunk_embedding)
                        
                        # Only add chunks above threshold for efficiency
                        if similarity > similarity_threshold:
                            all_chunks_with_scores.append({
                                "chunk": chunk,
                                "score": float(similarity),
                                "page_url": page_url,
                                "page_title": page_title,
                                "chunk_index": i
                            })
                        total_chunks_searched += 1
            
            logger.info(f"Searched {total_chunks_searched} chunks, found {len(all_chunks_with_scores)} above threshold")
            
            # Sort by similarity score
            all_chunks_with_scores.sort(key=lambda x: x["score"], reverse=True)
            
            # Take top-k results with diversity
            top_chunks = self._diversify_results(all_chunks_with_scores, top_k)
            
            logger.info(f"Selected {len(top_chunks)} diverse chunks for query")
            
            # Convert to Chunk objects
            result_chunks = []
            for item in top_chunks:
                chunk_data = item["chunk"]
                result_chunks.append(Chunk(
                    id=f"{item['page_url']}_{item['chunk_index']}",
                    text=chunk_data.get("text", "")[:2000],
                    url=item["page_url"],
                    title=item["page_title"],
                    score=item["score"],
                    chunk_id=item["chunk_index"],
                    metadata={
                        "source": "vector_search",
                        "similarity": item["score"],
                        "page_title": item["page_title"]
                    }
                ))
            
            # Apply reranking if available for better relevance
            if self.reranker_url and len(result_chunks) > 0:
                logger.info("Applying reranking for better relevance")
                result_chunks = await self.rerank_chunks(query, result_chunks)
            
            return result_chunks
            
        except Exception as e:
            logger.error(f"Vector retrieval failed: {e}", exc_info=True)
            return []
    
    async def rerank_chunks(self, query: str, chunks: List[Chunk]) -> List[Chunk]:
        """Rerank chunks using the reranker model for better relevance"""
        try:
            # Prepare pairs for reranking
            pairs = [[query, chunk.text] for chunk in chunks]
            
            response = await self.http_client.post(
                f"{self.reranker_url}/rerank",
                json={
                    "query": query,
                    "texts": [chunk.text for chunk in chunks],
                    "raw_scores": False
                }
            )
            
            if response.status_code == 200:
                rerank_results = response.json()
                
                # Update chunk scores with rerank scores
                for i, score in enumerate(rerank_results):
                    if i < len(chunks):
                        chunks[i].score = float(score.get("score", chunks[i].score))
                
                # Resort by new scores
                chunks.sort(key=lambda x: x.score, reverse=True)
                logger.info(f"Reranked {len(chunks)} chunks")
            else:
                logger.warning(f"Reranking failed: {response.status_code}")
        
        except Exception as e:
            logger.error(f"Error during reranking: {e}")
        
        return chunks
    
    def _diversify_results(self, chunks_with_scores: List[Dict], top_k: int) -> List[Dict]:
        """Ensure diversity in results by limiting chunks from same page"""
        selected = []
        page_counts = {}
        max_per_page = 3  # Maximum chunks from same page
        
        for item in chunks_with_scores:
            page_url = item["page_url"]
            
            # Count chunks from this page
            if page_url not in page_counts:
                page_counts[page_url] = 0
            
            # Add chunk if under limit or very high score
            if page_counts[page_url] < max_per_page or item["score"] > 0.8:
                selected.append(item)
                page_counts[page_url] += 1
                
                if len(selected) >= top_k:
                    break
        
        return selected
    
    def format_context(self, chunks: List[Chunk]) -> str:
        """Format retrieved chunks into context string"""
        if not chunks:
            return ""
        
        context_parts = []
        for i, chunk in enumerate(chunks[:5], 1):  # Limit context to top 5 chunks
            source_info = f"[Source {i}: {chunk.title}]"
            context_parts.append(f"{source_info}\n{chunk.text}\n")
        
        return "\n".join(context_parts)
    
    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()
