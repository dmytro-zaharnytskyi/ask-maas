"""
Ask MaaS Orchestrator API
Main FastAPI application for page-local Q&A with RAG
"""
import os
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from starlette.responses import Response

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from app.routers import chat, ingest
try:
    from app.routers import chat_enhanced
    chat_enhanced_available = True
except ImportError:
    chat_enhanced_available = False
try:
    from app.routers import chat_unified
    chat_unified_available = True
except ImportError:
    chat_unified_available = False
from app.services.cache import CacheService
from app.services.config import Settings
from app.utils.logging import setup_logging

# Configure structured logging
logger = structlog.get_logger()

# Load settings
settings = Settings()

# Metrics
request_counter = Counter(
    'ask_maas_requests_total', 
    'Total number of requests', 
    ['method', 'endpoint', 'status']
)
request_duration = Histogram(
    'ask_maas_request_duration_seconds', 
    'Request duration', 
    ['method', 'endpoint']
)
active_connections = Gauge(
    'ask_maas_active_connections', 
    'Number of active connections'
)
cache_hits = Counter(
    'ask_maas_cache_hits_total', 
    'Cache hit count', 
    ['cache_type']
)
cache_misses = Counter(
    'ask_maas_cache_misses_total', 
    'Cache miss count', 
    ['cache_type']
)

# Initialize services
cache_service: Optional[CacheService] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    global cache_service
    
    # Startup
    logger.info("Starting Ask MaaS Orchestrator API", 
                version=settings.API_VERSION,
                environment=settings.ENVIRONMENT)
    
    # Initialize cache service
    cache_service = CacheService(settings)
    await cache_service.initialize()
    
    # Setup OpenTelemetry if enabled
    if settings.OTEL_ENABLED:
        trace.set_tracer_provider(TracerProvider())
        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.OTEL_ENDPOINT,
            insecure=True
        )
        span_processor = BatchSpanProcessor(otlp_exporter)
        trace.get_tracer_provider().add_span_processor(span_processor)
        
        # Instrument FastAPI
        FastAPIInstrumentor.instrument_app(app)
    
    # Set services in app state
    app.state.cache_service = cache_service
    app.state.settings = settings
    
    logger.info("API initialization complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Ask MaaS Orchestrator API")
    
    if cache_service:
        await cache_service.close()
    
    logger.info("Shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="Ask MaaS Orchestrator API",
    description="Page-local Q&A service with RAG for developer.redhat.com articles",
    version=settings.API_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Rate-Limit-Remaining"],
)

# Middleware for request tracking
@app.middleware("http")
async def track_requests(request: Request, call_next):
    """Track request metrics and add request ID"""
    import time
    import uuid
    
    # Generate request ID
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    
    # Track active connections
    active_connections.inc()
    
    # Time the request
    start_time = time.time()
    
    # Add request ID to logger context
    structlog.contextvars.bind_contextvars(request_id=request_id)
    
    try:
        response = await call_next(request)
        
        # Record metrics
        duration = time.time() - start_time
        request_counter.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code
        ).inc()
        request_duration.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)
        
        # Add request ID to response
        response.headers["X-Request-ID"] = request_id
        
        logger.info(
            "Request completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration=duration
        )
        
        return response
        
    except Exception as e:
        logger.error(
            "Request failed",
            method=request.method,
            path=request.url.path,
            error=str(e)
        )
        request_counter.labels(
            method=request.method,
            endpoint=request.url.path,
            status=500
        ).inc()
        raise
        
    finally:
        active_connections.dec()
        structlog.contextvars.unbind_contextvars("request_id")

# Include routers
app.include_router(chat.router, prefix="/api/v1")
app.include_router(ingest.router, prefix="/api/v1")

# Include enhanced chat router with citation expansion if available
if chat_enhanced_available:
    app.include_router(chat_enhanced.router, prefix="/api/v1")
    logger.info("Enhanced chat router with citation expansion enabled")

# Include unified chat router if available
if chat_unified_available:
    app.include_router(chat_unified.router, prefix="/api/v1")
    logger.info("Unified chat router enabled")

# Health check endpoints
@app.get("/health")
async def health_check():
    """Basic health check"""
    return {"status": "healthy", "version": settings.API_VERSION}

@app.get("/health/ready")
async def readiness_check():
    """Readiness probe - checks if all services are ready"""
    checks = {
        "api": "healthy",
        "cache": "unknown",
        "models": "unknown"
    }
    
    # Check cache connection
    try:
        if app.state.cache_service:
            await app.state.cache_service.ping()
            checks["cache"] = "healthy"
    except Exception as e:
        logger.error("Cache health check failed", error=str(e))
        checks["cache"] = "unhealthy"
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "checks": checks}
        )
    
    # Check model services (TEI and vLLM)
    # This would be implemented based on actual service endpoints
    # For now, we'll assume they're healthy if configured
    if settings.TEI_EMBEDDINGS_URL and settings.VLLM_URL:
        checks["models"] = "healthy"
    
    all_healthy = all(v == "healthy" for v in checks.values())
    
    if all_healthy:
        return {"status": "ready", "checks": checks}
    else:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "checks": checks}
        )

@app.get("/health/live")
async def liveness_check():
    """Liveness probe - checks if the application is running"""
    return {"status": "alive"}

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type="text/plain")

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Ask MaaS Orchestrator API",
        "version": settings.API_VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs" if settings.ENVIRONMENT == "development" else None,
        "health": "/health",
        "metrics": "/metrics"
    }

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    logger.warning(
        "HTTP exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code}
    )

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle validation errors"""
    logger.error("Validation error", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=400,
        content={"error": str(exc), "status_code": 400}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    logger.error(
        "Unhandled exception",
        error=str(exc),
        path=request.url.path,
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "status_code": 500,
            "request_id": request.headers.get("X-Request-ID")
        }
    )

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development",
        log_config=None,  # Use structlog instead
        access_log=False,  # Handled by middleware
        workers=1  # Single worker for stateful FAISS indexes
    )
