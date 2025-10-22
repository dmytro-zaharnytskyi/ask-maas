"""
Cache service for Redis-based storage
"""
import json
import pickle
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
import structlog
import numpy as np

from app.services.config import Settings

logger = structlog.get_logger()


class CacheService:
    """Service for managing cached FAISS indexes and metadata"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.redis_client: Optional[aioredis.Redis] = None
        
    async def initialize(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = await aioredis.from_url(
                self.settings.get_redis_url(),
                encoding="utf-8",
                decode_responses=False,  # We'll handle encoding/decoding
                max_connections=self.settings.CONNECTION_POOL_SIZE
            )
            
            # Test connection
            await self.ping()
            logger.info("Redis connection established")
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            raise
    
    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")
    
    async def ping(self) -> bool:
        """Test Redis connection"""
        try:
            await self.redis_client.ping()
            return True
        except Exception:
            return False
    
    async def get_all_page_urls(self) -> List[str]:
        """
        Get all indexed page URLs from cache
        
        Returns:
            List of page URLs that have been indexed
        """
        try:
            # Get all keys matching the index pattern
            pattern = "ask-maas:index:*:latest"
            keys = await self.redis_client.keys(pattern)
            
            # Extract page URLs from keys
            page_urls = []
            prefix = "ask-maas:index:"
            suffix = ":latest"
            
            for key in keys:
                # Decode key if it's bytes
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                
                # Extract URL from key
                if key.startswith(prefix) and key.endswith(suffix):
                    url = key[len(prefix):-len(suffix)]
                    page_urls.append(url)
            
            logger.info(f"Found {len(page_urls)} indexed pages in cache")
            return page_urls
            
        except Exception as e:
            logger.error(f"Failed to get page URLs from cache: {str(e)}")
            return []
    
    async def get_page_index(self, page_url: str, etag: Optional[str] = None) -> Optional[Dict]:
        """
        Retrieve page index from cache
        
        Args:
            page_url: URL of the page
            etag: Optional ETag for validation
            
        Returns:
            Dictionary containing index data and metadata, or None if not found
        """
        try:
            # Try with ETag first if provided
            if etag:
                cache_key = self.settings.get_cache_key(page_url, etag)
                data = await self.redis_client.get(cache_key)
                if data:
                    logger.info(f"Cache hit with ETag: {page_url}")
                    return pickle.loads(data)
            
            # Try the "latest" key first
            latest_key = f"ask-maas:index:{page_url}:latest"
            data = await self.redis_client.get(latest_key)
            if data:
                logger.info(f"Cache hit with latest key: {page_url}")
                return pickle.loads(data)
            
            # Try pattern search as fallback
            # Escape special characters in URL for pattern matching
            escaped_url = page_url.replace(':', '\\:').replace('/', '\\/')
            pattern = f"ask-maas\\:index\\:{escaped_url}\\:*"
            keys = await self.redis_client.keys(pattern)
            
            if keys:
                # Get the most recent one
                latest_key = sorted(keys)[-1]
                data = await self.redis_client.get(latest_key)
                if data:
                    logger.info(f"Cache hit with pattern search: {page_url}")
                    return pickle.loads(data)
            
            logger.info(f"Cache miss: {page_url}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get page index from cache: {str(e)}")
            return None
    
    async def store_page_index(
        self,
        page_url: str,
        etag: str,
        index: Any,  # FAISS index
        chunks: List[Dict],
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Store page index in cache
        
        Args:
            page_url: URL of the page
            etag: ETag for versioning
            index: FAISS index object
            chunks: List of document chunks
            metadata: Additional metadata
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cache_key = self.settings.get_cache_key(page_url, etag)
            
            # Prepare data for storage
            cache_data = {
                "page_url": page_url,
                "etag": etag,
                "index": index,  # FAISS index will be pickled
                "chunks": chunks,
                "metadata": metadata or {},
                "chunk_count": len(chunks)
            }
            
            # Serialize with pickle (handles FAISS index)
            serialized = pickle.dumps(cache_data)
            
            # Store with TTL
            await self.redis_client.setex(
                cache_key,
                self.settings.REDIS_CACHE_TTL,
                serialized
            )
            
            # Also store a reference without ETag for quick lookup
            latest_key = f"ask-maas:index:{page_url}:latest"
            await self.redis_client.setex(
                latest_key,
                self.settings.REDIS_CACHE_TTL,
                serialized  # Store the full serialized data, not just the etag
            )
            
            logger.info(
                f"Stored page index in cache",
                page_url=page_url,
                etag=etag,
                chunk_count=len(chunks),
                size_bytes=len(serialized)
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to store page index in cache: {str(e)}")
            return False
    
    async def invalidate_page_index(self, page_url: str) -> bool:
        """
        Invalidate all cached indexes for a page
        
        Args:
            page_url: URL of the page
            
        Returns:
            True if successful, False otherwise
        """
        try:
            pattern = f"ask-maas:index:{page_url}:*"
            keys = await self.redis_client.keys(pattern)
            
            if keys:
                await self.redis_client.delete(*keys)
                logger.info(f"Invalidated {len(keys)} cache entries for {page_url}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to invalidate cache: {str(e)}")
            return False
    
    async def get_metadata(self, key: str) -> Optional[Dict]:
        """
        Get metadata from cache
        
        Args:
            key: Metadata key
            
        Returns:
            Metadata dictionary or None
        """
        try:
            data = await self.redis_client.get(f"ask-maas:metadata:{key}")
            if data:
                return json.loads(data.decode('utf-8'))
            return None
            
        except Exception as e:
            logger.error(f"Failed to get metadata: {str(e)}")
            return None
    
    async def set_metadata(self, key: str, value: Dict, ttl: Optional[int] = None) -> bool:
        """
        Store metadata in cache
        
        Args:
            key: Metadata key
            value: Metadata dictionary
            ttl: Optional TTL in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            serialized = json.dumps(value)
            cache_key = f"ask-maas:metadata:{key}"
            
            if ttl:
                await self.redis_client.setex(cache_key, ttl, serialized)
            else:
                await self.redis_client.set(cache_key, serialized)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to set metadata: {str(e)}")
            return False
    
    async def add_to_index_queue(self, task: Dict) -> bool:
        """
        Add a task to the indexing queue
        
        Args:
            task: Task dictionary
            
        Returns:
            True if successful, False otherwise
        """
        try:
            await self.redis_client.lpush(
                "ask-maas:queue:indexing",
                json.dumps(task)
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to add to queue: {str(e)}")
            return False
    
    async def get_from_index_queue(self) -> Optional[Dict]:
        """
        Get a task from the indexing queue
        
        Returns:
            Task dictionary or None
        """
        try:
            data = await self.redis_client.rpop("ask-maas:queue:indexing")
            if data:
                return json.loads(data.decode('utf-8'))
            return None
            
        except Exception as e:
            logger.error(f"Failed to get from queue: {str(e)}")
            return None
    
    async def increment_counter(self, counter_name: str, amount: int = 1) -> int:
        """
        Increment a counter
        
        Args:
            counter_name: Name of the counter
            amount: Amount to increment
            
        Returns:
            New counter value
        """
        try:
            key = f"ask-maas:counter:{counter_name}"
            return await self.redis_client.incrby(key, amount)
            
        except Exception as e:
            logger.error(f"Failed to increment counter: {str(e)}")
            return 0
    
    async def get_counter(self, counter_name: str) -> int:
        """
        Get counter value
        
        Args:
            counter_name: Name of the counter
            
        Returns:
            Counter value
        """
        try:
            key = f"ask-maas:counter:{counter_name}"
            value = await self.redis_client.get(key)
            return int(value) if value else 0
            
        except Exception as e:
            logger.error(f"Failed to get counter: {str(e)}")
            return 0
