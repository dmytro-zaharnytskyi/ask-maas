"""Citation Expander FastAPI Application with Health and Metrics."""

import os
import logging
from typing import Dict, Any
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import (
    Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
)
import redis
from redis import Redis
from rq import Queue

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Prometheus metrics
metrics = {
    "fetched_ok": Counter("citation_fetched_ok_total", "Successfully fetched citations"),
    "fetched_err": Counter("citation_fetched_err_total", "Failed citation fetches"),
    "embedded_ok": Counter("citation_embedded_ok_total", "Successfully embedded citations"),
    "size_bytes": Histogram("citation_size_bytes", "Size of fetched citations in bytes"),
    "queue_depth": Gauge("citation_queue_depth", "Current depth of citation processing queue"),
}

# Global connections
redis_client: Redis = None
rq_queue: Queue = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global redis_client, rq_queue
    
    # Startup
    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis_client = redis.from_url(redis_url, decode_responses=True)
        rq_queue = Queue("citations", connection=redis_client)
        logger.info("Successfully connected to Redis and initialized RQ queue")
    except Exception as e:
        logger.error(f"Failed to initialize Redis/RQ: {e}")
        raise
    
    yield
    
    # Shutdown
    if redis_client:
        redis_client.close()
        logger.info("Closed Redis connection")


app = FastAPI(
    title="Citation Expander",
    description="Microservice for expanding article citations into searchable context",
    version="0.1.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint for Kubernetes probes."""
    try:
        # Check Redis connection
        redis_status = "healthy" if redis_client and redis_client.ping() else "unhealthy"
        
        # Check RQ queue
        queue_status = "healthy"
        queue_size = 0
        if rq_queue:
            try:
                queue_size = len(rq_queue)
                metrics["queue_depth"].set(queue_size)
            except Exception as e:
                logger.warning(f"Failed to get queue size: {e}")
                queue_status = "degraded"
        
        health_status = {
            "status": "healthy" if redis_status == "healthy" else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {
                "redis": redis_status,
                "rq_queue": queue_status,
                "queue_depth": queue_size
            }
        }
        
        status_code = status.HTTP_200_OK if health_status["status"] == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
        return health_status
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }


@app.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/enqueue")
async def enqueue_citation(url: str, parent_doc_id: str, parent_chunk_id: str, depth: int = 0) -> Dict[str, Any]:
    """Enqueue a URL for citation processing."""
    try:
        from worker.jobs import fetch_and_process_citation
        
        job = rq_queue.enqueue(
            fetch_and_process_citation,
            url=url,
            parent_doc_id=parent_doc_id,
            parent_chunk_id=parent_chunk_id,
            depth=depth,
            job_timeout="10m"
        )
        
        return {
            "job_id": job.id,
            "status": "enqueued",
            "url": url
        }
    
    except Exception as e:
        logger.error(f"Failed to enqueue citation: {e}")
        metrics["fetched_err"].inc()
        return {
            "error": str(e),
            "status": "failed"
        }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "citation-expander",
        "version": "0.1.0",
        "status": "running"
    }
