"""Embeddings and Vector Storage Integration."""

import os
import hashlib
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import requests
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, Range,
    UpdateStatus
)

logger = logging.getLogger(__name__)

# Configuration
TEI_URL = os.getenv("TEI_URL", "http://tei-embeddings:8080")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
COLLECTION_NAME = "ask-maas-citations"
EMBEDDING_DIM = 768
BATCH_SIZE = 32


class EmbeddingClient:
    """Client for Text Embeddings Inference (TEI) service."""
    
    def __init__(self, base_url: str = TEI_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
    
    def embed(self, text: str) -> List[float]:
        """Generate embedding for single text."""
        return self.embed_batch([text])[0]
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for batch of texts."""
        try:
            response = self.session.post(
                f"{self.base_url}/embed",
                json={"inputs": texts},
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            return result if isinstance(result[0], list) else [result]
        
        except requests.exceptions.RequestException as e:
            logger.error(f"TEI embedding failed: {e}")
            raise
    
    def close(self):
        """Close session."""
        self.session.close()


class QdrantStorage:
    """Client for Qdrant vector storage."""
    
    def __init__(self, url: str = QDRANT_URL):
        self.client = QdrantClient(url=url)
        self.collection_name = COLLECTION_NAME
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Ensure the collection exists with proper configuration."""
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if self.collection_name not in collection_names:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM,
                    distance=Distance.COSINE
                )
            )
            logger.info(f"Created Qdrant collection: {self.collection_name}")
    
    def upsert(
        self,
        citation_id: str,
        embedding: List[float],
        text: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Upsert a citation to Qdrant."""
        # Convert string ID to numeric hash for Qdrant
        numeric_id = int(hashlib.sha256(citation_id.encode()).hexdigest()[:16], 16)
        
        point = PointStruct(
            id=numeric_id,
            vector=embedding,
            payload={
                **metadata,
                "citation_id": citation_id,  # Store original ID in payload
                "text": text[:10000]  # Limit text size in payload
            }
        )
        
        result = self.client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )
        
        if result.status == UpdateStatus.COMPLETED:
            return {
                "status": "success",
                "citation_id": citation_id,
                "numeric_id": numeric_id
            }
        else:
            raise Exception(f"Qdrant upsert failed: {result}")
    
    def search(
        self,
        query_embedding: List[float],
        filter_urls: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for similar citations."""
        query_filter = None
        
        if filter_urls:
            query_filter = Filter(
                should=[
                    FieldCondition(
                        key="source_url",
                        match={"value": url}
                    )
                    for url in filter_urls
                ]
            )
        
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            query_filter=query_filter,
            limit=limit,
            with_payload=True
        )
        
        return [
            {
                "id": hit.id,
                "score": hit.score,
                **hit.payload
            }
            for hit in results
        ]
    
    def cleanup_expired(self) -> Dict[str, Any]:
        """Remove expired citations based on TTL."""
        current_time = datetime.utcnow().isoformat()
        
        # Delete points where ttl_expires_at < current_time
        result = self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="ttl_expires_at",
                        range=Range(lt=current_time)
                    )
                ]
            )
        )
        
        return {
            "status": "completed",
            "deleted_count": result.status if hasattr(result, 'status') else 0,
            "cleanup_time": current_time
        }


# Global instances
_embedding_client: Optional[EmbeddingClient] = None
_qdrant_storage: Optional[QdrantStorage] = None


def get_embedding_client() -> EmbeddingClient:
    """Get or create embedding client."""
    global _embedding_client
    if not _embedding_client:
        _embedding_client = EmbeddingClient()
    return _embedding_client


def get_qdrant_storage() -> QdrantStorage:
    """Get or create Qdrant storage."""
    global _qdrant_storage
    if not _qdrant_storage:
        _qdrant_storage = QdrantStorage()
    return _qdrant_storage


def embed_text(text: str) -> List[float]:
    """Generate embedding for text."""
    client = get_embedding_client()
    
    # Truncate text if too long (TEI has input limits)
    max_length = 512 * 4  # ~512 tokens
    if len(text) > max_length:
        text = text[:max_length]
    
    return client.embed(text)


def upsert_to_qdrant(
    citation_id: str,
    embedding: List[float],
    text: str,
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """Upsert citation to Qdrant."""
    storage = get_qdrant_storage()
    return storage.upsert(citation_id, embedding, text, metadata)


def search_citations(
    query: str,
    filter_urls: Optional[List[str]] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Search citations by query."""
    embedding = embed_text(query)
    storage = get_qdrant_storage()
    return storage.search(embedding, filter_urls, limit)


def cleanup_expired_from_qdrant() -> Dict[str, Any]:
    """Cleanup expired citations."""
    storage = get_qdrant_storage()
    return storage.cleanup_expired()
