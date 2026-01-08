"""
Prometheus Metrics for Agent System
====================================

Custom metrics for monitoring agent performance, costs, and system health.

Usage:
    from monitoring.metrics import AgentMetrics, WorkflowMetrics

    # Record agent execution
    AgentMetrics.agent_execution_total.labels(
        agent_name="invoice_matcher",
        status="success"
    ).inc()

    # Record latency
    with AgentMetrics.agent_execution_duration.labels(
        agent_name="invoice_matcher"
    ).time():
        # Execute agent
        pass
"""

from prometheus_client import Counter, Histogram, Gauge, Summary, Info
import logging

logger = logging.getLogger(__name__)

# Try to import prometheus_client (optional dependency)
try:
    from prometheus_client import Counter, Histogram, Gauge, Summary, Info, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    logger.warning("prometheus_client not installed. Metrics will be no-op. Install with: pip install prometheus-client")
    PROMETHEUS_AVAILABLE = False
    # Create dummy classes
    class Counter:
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def inc(self, *args): pass

    class Histogram:
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def time(self):
            class DummyContext:
                def __enter__(self): return self
                def __exit__(self, *args): pass
            return DummyContext()
        def observe(self, *args): pass

    class Gauge:
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def set(self, *args): pass
        def inc(self, *args): pass
        def dec(self, *args): pass

    class Summary:
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def observe(self, *args): pass

    class Info:
        def __init__(self, *args, **kwargs): pass
        def info(self, *args): pass


class AgentMetrics:
    """Metrics for agent executions."""

    # Total executions
    agent_execution_total = Counter(
        'agent_execution_total',
        'Total number of agent executions',
        ['agent_name', 'status']  # status: success, failure, timeout
    )

    # Execution duration
    agent_execution_duration = Histogram(
        'agent_execution_duration_seconds',
        'Agent execution duration in seconds',
        ['agent_name'],
        buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
    )

    # Token usage
    agent_tokens_total = Counter(
        'agent_tokens_total',
        'Total tokens used by agent',
        ['agent_name', 'token_type']  # token_type: prompt, completion, embedding
    )

    # Cost tracking
    agent_cost_usd = Counter(
        'agent_cost_usd_total',
        'Total cost in USD',
        ['agent_name']
    )

    # Confidence scores (for matching agents)
    agent_confidence_score = Histogram(
        'agent_confidence_score',
        'Confidence score of agent decisions',
        ['agent_name'],
        buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0)
    )

    # Decision types (for routing agents)
    agent_decision_total = Counter(
        'agent_decision_total',
        'Total decisions made by agent',
        ['agent_name', 'decision_type']  # decision_type: auto_match, human_review, no_match
    )


class WorkflowMetrics:
    """Metrics for Temporal workflows."""

    # Workflow executions
    workflow_execution_total = Counter(
        'workflow_execution_total',
        'Total workflow executions',
        ['workflow_name', 'status']  # status: completed, failed, timeout, cancelled
    )

    # Workflow duration
    workflow_duration = Histogram(
        'workflow_duration_seconds',
        'Workflow execution duration',
        ['workflow_name'],
        buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0)
    )

    # Activity executions
    activity_execution_total = Counter(
        'activity_execution_total',
        'Total activity executions',
        ['activity_name', 'status']
    )

    # Activity duration
    activity_duration = Histogram(
        'activity_duration_seconds',
        'Activity execution duration',
        ['activity_name'],
        buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
    )

    # Retries
    activity_retry_total = Counter(
        'activity_retry_total',
        'Total activity retries',
        ['activity_name']
    )


class MemoryMetrics:
    """Metrics for memory system (Qdrant + Redis)."""

    # Memory operations
    memory_operation_total = Counter(
        'memory_operation_total',
        'Total memory operations',
        ['operation', 'collection', 'status']  # operation: search, save, delete
    )

    # Memory query duration
    memory_query_duration = Histogram(
        'memory_query_duration_seconds',
        'Memory query duration',
        ['operation', 'collection'],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0)
    )

    # Cache performance
    memory_cache_hit_total = Counter(
        'memory_cache_hit_total',
        'Total cache hits',
        ['collection']
    )

    memory_cache_miss_total = Counter(
        'memory_cache_miss_total',
        'Total cache misses',
        ['collection']
    )

    # Embedding generation
    embedding_generation_total = Counter(
        'embedding_generation_total',
        'Total embeddings generated',
        ['status']  # status: success, failure
    )

    embedding_generation_duration = Histogram(
        'embedding_generation_duration_seconds',
        'Embedding generation duration',
        buckets=(0.1, 0.2, 0.5, 1.0, 2.0, 5.0)
    )

    # Collection sizes
    memory_collection_size = Gauge(
        'memory_collection_size',
        'Number of documents in collection',
        ['collection']
    )

    # Similarity scores
    memory_similarity_score = Histogram(
        'memory_similarity_score',
        'Similarity scores from memory searches',
        ['collection'],
        buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0)
    )


class SystemMetrics:
    """System health and resource metrics."""

    # System info
    system_info = Info(
        'system_info',
        'System information'
    )

    # Active connections
    active_connections = Gauge(
        'active_connections_total',
        'Number of active connections',
        ['service']  # service: qdrant, redis, postgresql, temporal
    )

    # Error rates
    error_total = Counter(
        'error_total',
        'Total errors',
        ['component', 'error_type']
    )

    # Queue sizes
    queue_size = Gauge(
        'queue_size',
        'Queue size',
        ['queue_name']
    )

    # Database connections
    db_connections_active = Gauge(
        'db_connections_active',
        'Active database connections',
        ['database']
    )


# Convenience functions

def record_agent_execution(agent_name: str, duration_seconds: float,
                          status: str = "success",
                          confidence: float = None,
                          decision_type: str = None):
    """
    Record agent execution metrics.

    Args:
        agent_name: Name of agent
        duration_seconds: Execution duration
        status: success/failure/timeout
        confidence: Optional confidence score
        decision_type: Optional decision type
    """
    AgentMetrics.agent_execution_total.labels(
        agent_name=agent_name,
        status=status
    ).inc()

    AgentMetrics.agent_execution_duration.labels(
        agent_name=agent_name
    ).observe(duration_seconds)

    if confidence is not None:
        AgentMetrics.agent_confidence_score.labels(
            agent_name=agent_name
        ).observe(confidence)

    if decision_type is not None:
        AgentMetrics.agent_decision_total.labels(
            agent_name=agent_name,
            decision_type=decision_type
        ).inc()


def record_agent_cost(agent_name: str,
                     prompt_tokens: int = 0,
                     completion_tokens: int = 0,
                     embedding_tokens: int = 0,
                     cost_usd: float = 0.0):
    """
    Record agent cost metrics.

    Args:
        agent_name: Name of agent
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        embedding_tokens: Number of embedding tokens
        cost_usd: Total cost in USD
    """
    if prompt_tokens > 0:
        AgentMetrics.agent_tokens_total.labels(
            agent_name=agent_name,
            token_type="prompt"
        ).inc(prompt_tokens)

    if completion_tokens > 0:
        AgentMetrics.agent_tokens_total.labels(
            agent_name=agent_name,
            token_type="completion"
        ).inc(completion_tokens)

    if embedding_tokens > 0:
        AgentMetrics.agent_tokens_total.labels(
            agent_name=agent_name,
            token_type="embedding"
        ).inc(embedding_tokens)

    if cost_usd > 0:
        AgentMetrics.agent_cost_usd.labels(
            agent_name=agent_name
        ).inc(cost_usd)


def record_memory_operation(operation: str, collection: str,
                           duration_seconds: float,
                           status: str = "success",
                           cache_hit: bool = None,
                           similarity_score: float = None):
    """
    Record memory operation metrics.

    Args:
        operation: search/save/delete
        collection: Collection name
        duration_seconds: Operation duration
        status: success/failure
        cache_hit: Whether cache was hit (for searches)
        similarity_score: Top similarity score (for searches)
    """
    MemoryMetrics.memory_operation_total.labels(
        operation=operation,
        collection=collection,
        status=status
    ).inc()

    MemoryMetrics.memory_query_duration.labels(
        operation=operation,
        collection=collection
    ).observe(duration_seconds)

    if cache_hit is not None:
        if cache_hit:
            MemoryMetrics.memory_cache_hit_total.labels(
                collection=collection
            ).inc()
        else:
            MemoryMetrics.memory_cache_miss_total.labels(
                collection=collection
            ).inc()

    if similarity_score is not None:
        MemoryMetrics.memory_similarity_score.labels(
            collection=collection
        ).observe(similarity_score)


# Metrics endpoint (for exposing to Prometheus)
def setup_metrics_endpoint(app, port: int = 8000):
    """
    Setup metrics endpoint for Prometheus scraping.

    Args:
        app: FastAPI or Flask app
        port: Port to expose metrics on
    """
    if not PROMETHEUS_AVAILABLE:
        logger.warning("Prometheus client not available, skipping metrics endpoint")
        return

    try:
        from prometheus_client import make_asgi_app

        # Mount metrics endpoint
        metrics_app = make_asgi_app()
        app.mount("/metrics", metrics_app)

        logger.info(f"Metrics endpoint available at http://localhost:{port}/metrics")
    except Exception as e:
        logger.error(f"Failed to setup metrics endpoint: {e}")
