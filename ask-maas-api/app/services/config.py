"""
Configuration settings for Ask MaaS API
"""
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
import json


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # API Configuration
    API_VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=False, env="DEBUG")
    
    # CORS Settings
    CORS_ORIGINS: List[str] = Field(
        default=[
            "http://localhost:3000", 
            "http://localhost:8080",
            "https://ask-maas-frontend.apps.ask-maas-poc.3vpr.s1.devshift.org",
            "http://ask-maas-frontend.apps.ask-maas-poc.3vpr.s1.devshift.org"
        ],
        env="CORS_ORIGINS"
    )
    
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS_ORIGINS from JSON string if needed"""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # If not JSON, treat as comma-separated list
                return [origin.strip() for origin in v.split(",")]
        return v
    
    # Redis Configuration (deprecated - using Qdrant only)
    # Kept for backward compatibility but not used
    REDIS_HOST: str = Field(default="", env="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, env="REDIS_PORT")
    REDIS_PASSWORD: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    REDIS_DB: int = Field(default=0, env="REDIS_DB")
    REDIS_CACHE_TTL: int = Field(default=1800, env="REDIS_CACHE_TTL")  # 30 minutes
    
    # Qdrant Vector Database Configuration
    QDRANT_URL: str = Field(
        default="qdrant-service.ask-maas-models.svc.cluster.local:6333",
        env="QDRANT_URL"
    )
    
    # Model Service URLs
    VLLM_URL: str = Field(
        default="http://vllm-service.ask-maas-models.svc.cluster.local:8080",
        env="VLLM_URL"
    )
    TEI_EMBEDDINGS_URL: str = Field(
        default="http://tei-embeddings.ask-maas.svc.cluster.local:8080",
        env="TEI_EMBEDDINGS_URL"
    )
    TEI_RERANKER_URL: str = Field(
        default="http://tei-reranker-service.ask-maas-models.svc.cluster.local:8080",
        env="TEI_RERANKER_URL"
    )
    QDRANT_URL: str = Field(
        default="http://qdrant.ask-maas.svc.cluster.local:6333",
        env="QDRANT_URL"
    )
    
    # Model Configuration
    MODEL_NAME: str = Field(default="mistral-7b-instruct", env="MODEL_NAME")
    MAX_TOKENS: int = Field(default=512, env="MAX_TOKENS")  # Conservative for chunked context
    TEMPERATURE: float = Field(default=0.3, env="TEMPERATURE")
    TOP_P: float = Field(default=0.9, env="TOP_P")
    STREAM_ENABLED: bool = Field(default=True, env="STREAM_ENABLED")
    
    # Chunking Configuration - Optimized for better context preservation
    CHUNK_SIZE: int = Field(default=1500, env="CHUNK_SIZE")
    CHUNK_OVERLAP: int = Field(default=200, env="CHUNK_OVERLAP")
    MIN_CHUNK_SIZE: int = Field(default=100, env="MIN_CHUNK_SIZE")
    MAX_CHUNK_SIZE: int = Field(default=1800, env="MAX_CHUNK_SIZE")
    
    # Retrieval Configuration - Optimized for PURE vector search
    RETRIEVAL_TOP_K: int = Field(default=20, env="RETRIEVAL_TOP_K")  # Reduced for faster processing
    RERANK_TOP_K: int = Field(default=10, env="RERANK_TOP_K")
    MIN_RERANK_SCORE: float = Field(default=0.05, env="MIN_RERANK_SCORE")  # Lower threshold for better recall
    MIN_SIMILARITY_SCORE: float = Field(default=0.1, env="MIN_SIMILARITY_SCORE")  # Minimum similarity for chunks
    # REMOVED HYBRID_SEARCH_ALPHA - we're using PURE vector search only
    
    # GitHub Configuration
    GITHUB_APP_ID: Optional[str] = Field(default=None, env="GITHUB_APP_ID")
    GITHUB_APP_PRIVATE_KEY: Optional[str] = Field(default=None, env="GITHUB_APP_PRIVATE_KEY")
    GITHUB_TOKEN: Optional[str] = Field(default=None, env="GITHUB_TOKEN")
    GITHUB_ALLOWED_PATHS: List[str] = Field(
        default=["README.md", "docs/", "examples/", "install/", "manifests/"]
    )
    
    # Rate Limiting (local backup if Limitador is down)
    RATE_LIMIT_ENABLED: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = Field(default=60, env="RATE_LIMIT_REQUESTS_PER_MINUTE")
    RATE_LIMIT_BURST: int = Field(default=20, env="RATE_LIMIT_BURST")
    
    # OpenTelemetry Configuration
    OTEL_ENABLED: bool = Field(default=True, env="OTEL_ENABLED")
    OTEL_ENDPOINT: str = Field(
        default="http://otel-collector.ask-maas-observability.svc.cluster.local:4317",
        env="OTEL_ENDPOINT"
    )
    OTEL_SERVICE_NAME: str = Field(default="ask-maas-api", env="OTEL_SERVICE_NAME")
    
    # Security
    JWT_SECRET_KEY: Optional[str] = Field(default=None, env="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = Field(default="HS256", env="JWT_ALGORITHM")
    JWT_EXPIRATION_MINUTES: int = Field(default=30, env="JWT_EXPIRATION_MINUTES")
    
    # System Prompts and Templates
    SYSTEM_PROMPT: str = Field(
        default="""You are a helpful AI assistant for developer.redhat.com articles. 
Your role is to answer questions ONLY based on the provided context from the article and its related resources.

Guidelines:
1. Answer ONLY from the provided context
2. Always include citations with section anchors or line numbers
3. If the context doesn't contain enough information, say so and suggest checking the relevant sections
4. Format code blocks properly with language tags
5. Be concise but thorough
6. Do not make assumptions beyond what's in the context""",
        env="SYSTEM_PROMPT"
    )
    
    ABSTAIN_MESSAGE: str = Field(
        default="I don't have enough information in the current article to answer this question. Please check these relevant sections of the article:",
        env="ABSTAIN_MESSAGE"
    )
    
    # Performance Tuning - Optimized for faster response
    MAX_CONTEXT_LENGTH: int = Field(default=6000, env="MAX_CONTEXT_LENGTH")  # Reduced for faster processing
    REQUEST_TIMEOUT: int = Field(default=20, env="REQUEST_TIMEOUT")  # Reduced timeout
    STREAM_TIMEOUT: int = Field(default=30, env="STREAM_TIMEOUT")  # Reduced for faster failover
    CONNECTION_POOL_SIZE: int = Field(default=20, env="CONNECTION_POOL_SIZE")  # Increased for better concurrency
    BATCH_SIZE: int = Field(default=10, env="BATCH_SIZE")  # For batch embedding generation
    
    # Feature Flags
    ENABLE_CACHING: bool = Field(default=True, env="ENABLE_CACHING")
    ENABLE_GITHUB_FETCH: bool = Field(default=True, env="ENABLE_GITHUB_FETCH")
    ENABLE_METRICS: bool = Field(default=True, env="ENABLE_METRICS")
    ENABLE_TRACING: bool = Field(default=True, env="ENABLE_TRACING")
    
    def get_redis_url(self) -> str:
        """Get Redis connection URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    def get_cache_key(self, page_url: str, etag: str) -> str:
        """Generate cache key for page index"""
        return f"ask-maas:index:{page_url}:{etag}"
