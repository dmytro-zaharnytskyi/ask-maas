"""
Unified Vector Retrieval Service - Simple RAG with Qdrant
"""
from typing import List, Dict, Any, Optional
import httpx
import structlog
import hashlib
import time

from app.services.config import Settings
from app.models.chat import Chunk

logger = structlog.get_logger()


class UnifiedVectorRetrievalService:
    """
    Simple unified vector retrieval directly from Qdrant.
    All content (articles + citations) are in one collection.
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.embeddings_url = settings.TEI_EMBEDDINGS_URL
        self.qdrant_url = settings.QDRANT_URL
        # Use the existing citations collection that has all the content
        self.collection_name = "ask-maas-citations"
        
    async def ensure_collection(self):
        """Ensure unified collection exists"""
        try:
            # Check if collection exists
            response = await self.http_client.get(
                f"{self.qdrant_url}/collections/{self.collection_name}"
            )
            
            if response.status_code == 404:
                # Create collection
                config = {
                    "vectors": {
                        "size": 768,
                        "distance": "Cosine"
                    }
                }
                
                response = await self.http_client.put(
                    f"{self.qdrant_url}/collections/{self.collection_name}",
                    json=config
                )
                logger.info(f"Created unified collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Failed to ensure collection: {e}")
    
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
            logger.error(f"Embedding generation failed: {e}")
            return None
    
    async def search_unified(
        self,
        query: str,
        top_k: int = 10,
        score_threshold: float = 0.3
    ) -> List[Chunk]:
        """
        Search across ALL content in unified Qdrant collection.
        This includes articles, citations, and any indexed content.
        """
        try:
            # Get query embedding
            query_embedding = await self.get_query_embedding(query)
            if not query_embedding:
                logger.error("Failed to get query embedding")
                return []
            
            # Search in Qdrant - use simple request format that works
            search_request = {
                "vector": query_embedding,
                "limit": top_k,
                "with_payload": True
            }
            
            # Add score threshold if specified
            if score_threshold > 0:
                search_request["score_threshold"] = score_threshold
            
            response = await self.http_client.post(
                f"{self.qdrant_url}/collections/{self.collection_name}/points/search",
                json=search_request
            )
            
            if response.status_code != 200:
                logger.error(f"Qdrant search failed: {response.status_code}, {response.text[:200]}")
                return []
            
            results = response.json().get('result', [])
            
            # Convert to Chunk objects
            chunks = []
            for i, result in enumerate(results):
                payload = result.get('payload', {})
                score = result.get('score', 0)
                
                # Extract text
                text = payload.get('text', payload.get('text_preview', ''))[:2000]
                
                # Create chunk
                chunk = Chunk(
                    id=payload.get('doc_id', f"qdrant_{i}"),
                    text=text,
                    url=payload.get('source_url', payload.get('page_url', '')),
                    title=payload.get('title', 'Unknown'),
                    score=score,
                    chunk_id=i,
                    metadata={
                        "source": "qdrant_unified",
                        "source_type": payload.get('source_type', 'unknown'),
                        "content_type": payload.get('content_type', 'text'),
                        "similarity": score
                    }
                )
                chunks.append(chunk)
            
            logger.info(
                f"Unified search found {len(chunks)} chunks",
                top_scores=[c.score for c in chunks[:3]],
                sources=[c.metadata.get('source_type') for c in chunks[:3]]
            )
            
            return chunks
            
        except Exception as e:
            logger.error(f"Unified search failed: {e}")
            return []
    
    async def index_content(
        self,
        text: str,
        source_url: str,
        title: str,
        source_type: str = "article",
        chunk_size: int = 1000,
        overlap: int = 100
    ) -> int:
        """
        Index content directly to unified Qdrant collection.
        This replaces the complex citation expander.
        """
        try:
            await self.ensure_collection()
            
            # Chunk text
            chunks = []
            if len(text) <= chunk_size:
                chunks = [text]
            else:
                for i in range(0, len(text), chunk_size - overlap):
                    chunk = text[i:i + chunk_size]
                    if chunk.strip():
                        chunks.append(chunk)
            
            indexed = 0
            for i, chunk_text in enumerate(chunks):
                # Get embedding
                embedding = await self.get_query_embedding(chunk_text)
                if not embedding:
                    continue
                
                # Create unique ID
                doc_id = f"{source_type}_{hashlib.sha256(f'{source_url}_{i}'.encode()).hexdigest()[:16]}"
                numeric_id = int(hashlib.sha256(doc_id.encode()).hexdigest()[:16], 16)
                
                # Prepare point
                point = {
                    "id": numeric_id,
                    "vector": embedding,
                    "payload": {
                        "doc_id": doc_id,
                        "text": chunk_text[:10000],
                        "source_url": source_url,
                        "title": title,
                        "source_type": source_type,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "indexed_at": time.time()
                    }
                }
                
                # Index to Qdrant
                response = await self.http_client.put(
                    f"{self.qdrant_url}/collections/{self.collection_name}/points",
                    json={"points": [point]}
                )
                
                if response.status_code == 200:
                    indexed += 1
            
            logger.info(f"Indexed {indexed}/{len(chunks)} chunks for {title}")
            return indexed
            
        except Exception as e:
            logger.error(f"Failed to index content: {e}")
            return 0
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.http_client.aclose()
