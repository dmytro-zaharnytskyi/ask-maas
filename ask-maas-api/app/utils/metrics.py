"""
Metrics tracking utilities
"""
from prometheus_client import Counter, Histogram, Gauge
import structlog

logger = structlog.get_logger()

# Define metrics
token_counter = Counter(
    'ask_maas_tokens_generated_total',
    'Total number of tokens generated',
    ['model']
)

first_token_latency = Histogram(
    'ask_maas_first_token_latency_seconds',
    'Time to first token',
    buckets=[0.1, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0]
)

chunk_retrieval_count = Histogram(
    'ask_maas_chunks_retrieved',
    'Number of chunks retrieved per query',
    buckets=[1, 5, 10, 15, 20, 30, 50]
)

reranker_score_histogram = Histogram(
    'ask_maas_reranker_score',
    'Distribution of reranker scores',
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

abstention_counter = Counter(
    'ask_maas_abstentions_total',
    'Total number of abstentions due to low confidence'
)

retrieval_duration = Histogram(
    'ask_maas_retrieval_duration_seconds',
    'Time spent in retrieval',
    buckets=[0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
)


def track_request_duration(duration: float, endpoint: str):
    """Track request duration"""
    logger.info(
        "Request completed",
        duration=duration,
        endpoint=endpoint
    )


def track_token_usage(tokens: int, model: str = "mistral-7b"):
    """Track token usage"""
    token_counter.labels(model=model).inc(tokens)
    logger.info(
        "Tokens generated",
        tokens=tokens,
        model=model
    )
