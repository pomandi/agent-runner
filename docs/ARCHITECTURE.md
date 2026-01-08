# Agent System Architecture

**Production-Grade Agentic System with Vector Memory, LangGraph Orchestration, and Comprehensive Monitoring**

Version: 2.0
Last Updated: 2026-01-08
Status: Production

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Core Components](#core-components)
4. [Technology Stack](#technology-stack)
5. [Data Flow](#data-flow)
6. [Deployment Architecture](#deployment-architecture)
7. [Security & Access Control](#security--access-control)
8. [Scaling Strategy](#scaling-strategy)
9. [Disaster Recovery](#disaster-recovery)

---

## System Overview

This is a production-grade agent orchestration system that combines:

- **Claude Agent SDK** - AI agent execution with tool use
- **Temporal** - Workflow orchestration, scheduling, and retry logic
- **LangGraph** - Graph-based agent reasoning and state management
- **Qdrant** - Vector database for semantic memory
- **Redis** - Session cache and working memory
- **PostgreSQL** - Structured data storage (3 databases)
- **Prometheus + Grafana** - Metrics and monitoring
- **Langfuse** - LLM observability and cost tracking

### Design Principles

1. **Separation of Concerns**: Temporal handles orchestration, LangGraph handles reasoning
2. **Memory-Aware Agents**: All agents leverage vector memory for context
3. **Fail-Safe by Default**: Graceful degradation, retries, circuit breakers
4. **Observable**: Comprehensive metrics, traces, and logs
5. **Cost-Conscious**: Token tracking, cost alerts, efficient caching

### Current Agents

| Agent | Type | Purpose | Memory Collections Used |
|-------|------|---------|------------------------|
| `invoice-matcher` | LangGraph | Match bank transactions to invoices | invoices, agent_context |
| `feed-publisher` | LangGraph | Generate and publish social media posts | social_posts, agent_context |
| `invoice-extractor` | Traditional | Extract invoice data from PDFs | invoices |
| `invoice-finder` | Traditional | Search invoices in ERP system | invoices |
| `credit-note-creator` | Traditional | Generate credit notes | - |
| `google-ads-analyzer` | Traditional | Analyze Google Ads performance | ad_reports |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INTERFACES                          │
│  Web Dashboard │ CLI │ API │ Temporal UI │ Grafana │ Langfuse   │
└─────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────┼─────────────────────────────────┐
│                       ORCHESTRATION LAYER                         │
│                                                                   │
│  ┌─────────────────────┐     ┌──────────────────────────┐       │
│  │   Temporal Server    │────▶│   LangGraph Agents       │       │
│  │  - Workflow Engine   │     │  - State Machines        │       │
│  │  - Task Queue        │     │  - Memory Integration    │       │
│  │  - Retry Logic       │     │  - Decision Routing      │       │
│  │  - Scheduling        │     └──────────────────────────┘       │
│  └─────────────────────┘              │                          │
│           │                            │                          │
│           ▼                            ▼                          │
│  ┌──────────────────────────────────────────────────┐           │
│  │            Claude Agent SDK Runtime              │           │
│  │  - Tool Execution  - Prompt Management           │           │
│  │  - Context Building  - Response Parsing          │           │
│  └──────────────────────────────────────────────────┘           │
└───────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────┼─────────────────────────────────┐
│                          MEMORY LAYER                             │
│                                                                   │
│  ┌────────────┐      ┌────────────┐      ┌──────────────┐       │
│  │   Qdrant   │      │   Redis    │      │  PostgreSQL  │       │
│  │  (Vectors) │      │  (Cache)   │      │ (Structured) │       │
│  ├────────────┤      ├────────────┤      ├──────────────┤       │
│  │ invoices   │      │ Sessions   │      │ saleor_prod  │       │
│  │ social_posts      │ Embeddings │      │ last_afspraak│       │
│  │ ad_reports │      │ Query Cache│      │ saleorme     │       │
│  │ agent_context     └────────────┘      └──────────────┘       │
│  └────────────┘                                                  │
│                                                                   │
│  ┌──────────────────────────────────────────────────────┐       │
│  │         Memory Manager (Unified Interface)            │       │
│  │  - Embedding Generation (OpenAI)                      │       │
│  │  - Cache Strategy (L1: Redis, L2: Qdrant)            │       │
│  │  - Collection Management                              │       │
│  └──────────────────────────────────────────────────────┘       │
└───────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────┼─────────────────────────────────┐
│                        MCP SERVER LAYER                           │
│                                                                   │
│  30+ MCP Servers providing tools:                                │
│  - PostgreSQL queries  - S3 operations  - API integrations       │
│  - Google Ads API  - Meta Ads API  - Shopify API                 │
│  - Memory operations  - Email sending  - PDF processing          │
└───────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────┼─────────────────────────────────┐
│                      OBSERVABILITY LAYER                          │
│                                                                   │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐        │
│  │ Prometheus   │   │   Grafana    │   │  Langfuse    │        │
│  │ - Metrics    │──▶│ - Dashboards │   │ - LLM Traces │        │
│  │ - Alerts     │   │ - Alerts     │   │ - Cost Track │        │
│  └──────────────┘   └──────────────┘   └──────────────┘        │
│                                                                   │
│  Metrics Exposed:                                                │
│  - agent_execution_total (counter)                               │
│  - agent_execution_duration_seconds (histogram)                  │
│  - agent_cost_usd_total (counter)                                │
│  - memory_cache_hit_total (counter)                              │
│  - workflow_execution_total (counter)                            │
└───────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Orchestration Layer

#### Temporal Workflows

- **Purpose**: Long-running orchestration, scheduling, error handling
- **Port**: 7233
- **Features**:
  - Workflow versioning
  - Activity retries with exponential backoff
  - Timeouts and cancellation
  - Child workflows
  - Signals and queries

**Key Workflows**:

```python
# temporal_app/workflows/invoice_matching_workflow.py
@workflow.defn
class InvoiceMatchingWorkflow:
    """
    Orchestrates invoice matching process:
    1. Fetch transactions (activity)
    2. Fetch invoices (activity)
    3. Run invoice matcher graph (activity)
    4. Update database (activity)
    """
```

#### LangGraph Agents

- **Purpose**: Complex reasoning, memory-aware decision making
- **Integration**: Run as Temporal activities
- **Features**:
  - State management
  - Conditional routing
  - Memory retrieval/storage
  - Step tracking

**Graph Pattern**:

```python
# langgraph_agents/invoice_matcher_graph.py
START
  ↓
Build Query
  ↓
Search Memory (Qdrant)
  ↓
Compare & Match (Claude)
  ↓
Decision Node → [auto_match | human_review | no_match]
  ↓
Save Context (Memory)
  ↓
END
```

### 2. Memory Layer

#### Qdrant Vector Database

- **Port**: 6333
- **Storage**: Persistent volume
- **Collections**:
  - `invoices` - Invoice documents and metadata
  - `social_posts` - Published captions and images
  - `ad_reports` - Google/Meta Ads analysis
  - `agent_context` - Agent decision history

**Collection Schema Example**:

```python
# memory/collections.py
InvoiceCollection = {
    "name": "invoices",
    "vectors": {
        "size": 1536,  # OpenAI text-embedding-3-small
        "distance": "Cosine"
    },
    "payload_schema": {
        "vendor_name": "keyword",
        "amount": "float",
        "date": "keyword",
        "matched": "bool",
        "invoice_id": "integer"
    }
}
```

#### Redis Cache

- **Port**: 6379
- **Usage**:
  - Session storage (24h TTL)
  - Embedding cache (7d TTL)
  - Query result cache (1h TTL)
- **Max Memory**: 512MB with LRU eviction

#### PostgreSQL Databases

1. **saleor_prod** - E-commerce data (products, orders, customers)
2. **last_afspraak** - Appointment scheduling and visitor tracking
3. **saleorme** - Internal operations and analytics

### 3. Observability Stack

#### Prometheus Metrics

**Scrape Configuration** (`monitoring/prometheus.yml`):

```yaml
scrape_configs:
  - job_name: 'agent-worker'
    scrape_interval: 15s
    static_configs:
      - targets: ['agent-worker:8000']
```

**Custom Metrics**:

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `agent_execution_total` | Counter | agent_name, status | Track executions |
| `agent_execution_duration_seconds` | Histogram | agent_name | Latency tracking |
| `agent_cost_usd_total` | Counter | agent_name | Cost monitoring |
| `agent_confidence_score` | Histogram | agent_name | Decision quality |
| `memory_cache_hit_total` | Counter | collection | Cache efficiency |
| `workflow_execution_total` | Counter | workflow_name, status | Workflow tracking |

#### Grafana Dashboards

**Agent System Overview** (`monitoring/dashboards/agent_system_overview.json`):

- Agent execution rate (timeseries)
- Agent execution duration p95 (gauge)
- Agent decision distribution (pie chart)
- Total cost (stat)
- Memory cache hit rate (timeseries)
- Error rate (stat)

**Access**: http://localhost:3000 (admin/admin)

#### Langfuse Traces

- **Endpoint**: Coolify-hosted instance
- **Features**:
  - Prompt versioning
  - Token usage tracking
  - Cost attribution
  - Session replay
  - User feedback

---

## Technology Stack

### Core Technologies

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Agent SDK | Claude Agent SDK | 0.1.0 | AI agent execution |
| Orchestration | Temporal | 1.8.0 | Workflow engine |
| Reasoning | LangGraph | 0.2.45 | Graph-based agents |
| Vector DB | Qdrant | 1.11.3 | Semantic memory |
| Cache | Redis | 7-alpine | Working memory |
| Database | PostgreSQL | 15 | Structured data |
| Embeddings | OpenAI API | - | text-embedding-3-small |
| LLM | Claude 4 | Opus 4.5 | Agent reasoning |
| Monitoring | Prometheus | latest | Metrics collection |
| Dashboards | Grafana | latest | Visualization |
| Observability | Langfuse | 2.0.0 | LLM traces |

### Supporting Libraries

```txt
# requirements.txt
claude-agent-sdk>=0.1.0
temporalio>=1.8.0
langgraph==0.2.45
qdrant-client==1.11.3
redis[hiredis]>=5.0.0
openai>=1.54.0
prometheus-client>=0.20.0
fastapi>=0.115.0
structlog>=24.0.0
pydantic>=2.0.0
```

---

## Data Flow

### Example: Invoice Matching Flow

```
1. TRIGGER: Cron schedule (daily at 9 AM)
   ↓
2. Temporal starts InvoiceMatchingWorkflow
   ↓
3. Activity: Fetch unmatched transactions from PostgreSQL
   → Result: List[Transaction]
   ↓
4. Activity: Fetch unmatched invoices from PostgreSQL
   → Result: List[Invoice]
   ↓
5. Activity: run_invoice_matcher_graph(transaction, invoices)
   ├─ LangGraph START
   ├─ Build Query: "SNCB €22.70 2025-01-03"
   ├─ Search Memory: Qdrant.search("invoices", query, top_k=10)
   │  ├─ Check Redis cache (miss)
   │  ├─ Generate embedding (OpenAI API)
   │  ├─ Query Qdrant vectors
   │  └─ Cache results in Redis
   ├─ Compare Invoices: Claude analyzes transaction + candidates + memory
   │  ├─ Prompt: "Match transaction to invoice..."
   │  ├─ Claude returns: {matched: true, confidence: 0.95, invoice_id: 123}
   │  └─ Langfuse records trace
   ├─ Decision: confidence >= 0.90 → auto_match
   ├─ Save Context: Qdrant.save("agent_context", decision)
   └─ LangGraph END
   → Result: {matched: true, invoice_id: 123, confidence: 0.95}
   ↓
6. Activity: Update database (mark as matched)
   ↓
7. Prometheus metrics recorded:
   - agent_execution_total{agent_name="invoice_matcher", status="success"} +1
   - agent_execution_duration_seconds{agent_name="invoice_matcher"} 2.3s
   - agent_confidence_score{agent_name="invoice_matcher"} 0.95
   - memory_cache_miss_total{collection="invoices"} +1
   ↓
8. Workflow completes successfully
```

### Example: Social Media Publishing Flow

```
1. TRIGGER: API call /publish-feed
   ↓
2. Temporal starts FeedPublishingWorkflow
   ↓
3. Activity: run_feed_publisher_graph(brand, platform, photo_s3_key)
   ├─ LangGraph START
   ├─ Check Caption History: Search memory for similar captions
   │  ├─ Query: "pomandi instagram post"
   │  ├─ Qdrant returns: 5 similar captions (top score: 0.65)
   │  └─ No duplicate detected (score < 0.90)
   ├─ View Image: Fetch from S3, generate description
   ├─ Generate Caption: Claude creates Dutch caption
   │  ├─ Prompt: "Generate Dutch caption for pomandi..."
   │  ├─ Context: Similar captions (avoid duplication)
   │  └─ Claude returns: "✨ Nieuw binnen! Perfect voor jouw stijl 🛍️"
   ├─ Quality Check: Rule-based + language validation
   │  ├─ Language: NL keywords found ✓
   │  ├─ Length: 53 chars ✓
   │  ├─ Brand mention: "Pomandi" not found ✗ (-0.2)
   │  ├─ Emoji count: 3 ✓
   │  └─ Quality score: 0.80 → Requires human review
   ├─ Decision: 0.70 <= score < 0.85 → human_review
   ├─ Save Memory: Qdrant.save("social_posts", caption + metadata)
   └─ LangGraph END
   → Result: {published: false, requires_approval: true, quality_score: 0.80}
   ↓
4. Workflow notifies user for review
```

---

## Deployment Architecture

### Docker Compose Services

```yaml
# docker-compose.yaml
services:
  # Core Services
  temporal:
    image: temporalio/auto-setup:latest
    ports: ["7233:7233", "8233:8233"]

  agent-worker:
    build: .
    depends_on: [temporal, qdrant, redis]
    environment:
      - TEMPORAL_HOST=temporal:7233
      - QDRANT_HOST=qdrant:6333
      - REDIS_HOST=redis:6379
      - OPENAI_API_KEY=${OPENAI_API_KEY}

  # Memory Layer
  qdrant:
    image: qdrant/qdrant:v1.11.3
    ports: ["6333:6333"]
    volumes: ["qdrant-storage:/qdrant/storage"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes: ["redis-data:/data"]
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru

  postgresql:
    image: postgres:15-alpine
    ports: ["5432:5432"]
    environment:
      - POSTGRES_MULTIPLE_DATABASES=saleor_prod,last_afspraak,saleorme

  # Monitoring (Optional Profile)
  prometheus:
    image: prom/prometheus:latest
    ports: ["9090:9090"]
    volumes: ["./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro"]
    profiles: ["monitoring"]

  grafana:
    image: grafana/grafana:latest
    ports: ["3000:3000"]
    volumes:
      - "grafana-data:/var/lib/grafana"
      - "./monitoring/datasources.yml:/etc/grafana/provisioning/datasources/datasources.yml:ro"
      - "./monitoring/dashboards:/etc/grafana/provisioning/dashboards:ro"
    profiles: ["monitoring"]
```

### Environment Configuration

```bash
# .env
# Claude API
ANTHROPIC_API_KEY=sk-ant-xxx

# OpenAI (Embeddings)
OPENAI_API_KEY=sk-xxx
EMBEDDING_MODEL=text-embedding-3-small

# Temporal
TEMPORAL_HOST=temporal
TEMPORAL_PORT=7233
TEMPORAL_NAMESPACE=default

# Memory
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_COLLECTION_SIZE=1536
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_MAX_MEMORY=512mb

# PostgreSQL
POSTGRES_HOST=postgresql
POSTGRES_PORT=5432
SALEOR_DB=saleor_prod
AFSPRAAK_DB=last_afspraak
SALEORME_DB=saleorme

# Langfuse
LANGFUSE_HOST=https://langfuse.yourdomain.com
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx

# Feature Flags
ENABLE_MEMORY=true
ENABLE_LANGGRAPH=true
ENABLE_EVALUATION=true
ENABLE_MONITORING=true
```

### Deployment Commands

```bash
# Standard deployment
docker compose up -d

# With monitoring
docker compose --profile monitoring up -d

# Health checks
docker compose ps
curl http://localhost:6333/healthz  # Qdrant
curl http://localhost:8000/metrics  # Agent worker
curl http://localhost:9090/-/healthy  # Prometheus

# Logs
docker compose logs -f agent-worker
docker compose logs -f temporal

# Shutdown
docker compose down
docker compose down -v  # Remove volumes
```

---

## Security & Access Control

### Network Security

- **Internal Network**: All services on Docker bridge network
- **Exposed Ports**: Only necessary ports exposed to host
- **Firewall**: UFW configured on Hetzner VPS

### API Keys & Secrets

- **Storage**: Environment variables (`.env` file)
- **Never Committed**: `.env` in `.gitignore`
- **Rotation**: Quarterly rotation policy
- **Access**: Stored in Coolify secrets manager

### Database Security

- **PostgreSQL**: Strong passwords, connection limits
- **Qdrant**: No authentication (internal network only)
- **Redis**: No authentication (internal network only)

### Agent Safety

- **Tool Validation**: All MCP tools validated before execution
- **Cost Limits**: Per-agent cost budgets
- **Rate Limiting**: API call rate limits
- **Human-in-the-Loop**: Confidence thresholds for approval

---

## Scaling Strategy

### Current Capacity

- **Throughput**: ~100 agent executions/hour
- **Memory**: 1M+ vectors in Qdrant
- **Latency**: p95 < 5s per agent execution
- **Cost**: ~$70/month (Claude API + infrastructure)

### Scaling Dimensions

#### Horizontal Scaling (More Workers)

```yaml
# docker-compose.yaml
agent-worker:
  replicas: 3  # Scale to 3 workers
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 4G
```

#### Vertical Scaling (Bigger Machines)

- Current: 4 vCPU, 8GB RAM
- Next tier: 8 vCPU, 16GB RAM
- Bottleneck: Qdrant memory usage

#### Database Scaling

- **Qdrant**: Cluster mode (3 nodes)
- **Redis**: Redis Sentinel for HA
- **PostgreSQL**: Read replicas

### Load Testing

```python
# evaluation/load_tests/test_invoice_matching.py
async def test_concurrent_matching():
    """Test 100 concurrent invoice matching requests."""
    tasks = [
        match_invoice(transaction, invoices)
        for _ in range(100)
    ]
    results = await asyncio.gather(*tasks)

    assert all(r['latency'] < 10.0 for r in results)  # p100 < 10s
    assert sum(r['success'] for r in results) >= 95  # 95% success rate
```

---

## Disaster Recovery

### Backup Strategy

#### Qdrant Vectors

```bash
# Backup (daily cron)
docker exec qdrant qdrant-backup create /backups/qdrant-$(date +%Y%m%d).tar.gz

# Restore
docker exec qdrant qdrant-restore /backups/qdrant-20260108.tar.gz
```

#### PostgreSQL Databases

```bash
# Backup (daily cron)
docker exec postgresql pg_dumpall -U postgres > /backups/postgres-$(date +%Y%m%d).sql

# Restore
docker exec -i postgresql psql -U postgres < /backups/postgres-20260108.sql
```

#### Redis (Ephemeral - No Backup Needed)

- Session data: Can be regenerated
- Cache: Warm-up from Qdrant after restart

### Recovery Procedures

**Scenario: Agent Worker Crash**

```bash
# 1. Check logs
docker compose logs -f agent-worker

# 2. Restart worker
docker compose restart agent-worker

# 3. Verify health
curl http://localhost:8000/metrics

# Recovery time: <1 minute
```

**Scenario: Qdrant Data Loss**

```bash
# 1. Stop services
docker compose stop

# 2. Restore Qdrant backup
docker exec qdrant qdrant-restore /backups/qdrant-20260107.tar.gz

# 3. Re-run embeddings for missing data (last 24h)
python scripts/backfill_embeddings.py --since yesterday

# 4. Restart services
docker compose up -d

# Recovery time: ~30 minutes (depends on data volume)
```

**Scenario: Complete Infrastructure Failure**

```bash
# 1. Provision new VPS (Hetzner)
# 2. Clone repository
git clone <repo-url>

# 3. Restore .env file from secrets manager
# 4. Restore database backups
./scripts/restore_backups.sh

# 5. Deploy stack
docker compose up -d

# 6. Verify all services healthy
./scripts/health_check.sh

# Recovery time: ~2 hours
```

---

## Performance Optimization

### Memory Optimization

**Embedding Cache**:

- **Hit Rate Target**: >80%
- **Current**: ~65% (needs improvement)
- **Strategy**: Increase Redis memory to 1GB

**Qdrant Query Optimization**:

```python
# Use scroll API for bulk operations
results = qdrant_client.scroll(
    collection_name="invoices",
    scroll_filter=qdrant.Filter(...),
    limit=100,
    with_vectors=False  # Don't fetch vectors if not needed
)
```

### Cost Optimization

**Token Usage Reduction**:

- **Memory Context**: Reduce prompt size by 30%
- **Caching**: Cache similar queries for 1 hour
- **Model Selection**: Use Claude Haiku for simple tasks

**Estimated Savings**: $20/month (28% reduction)

---

## Monitoring & Alerts

### Key Metrics Dashboard

| Metric | Target | Alert Threshold |
|--------|--------|----------------|
| Agent execution success rate | >95% | <90% |
| Agent p95 latency | <5s | >10s |
| Memory cache hit rate | >80% | <50% |
| Error rate | <2% | >5% |
| Cost per execution | <$0.05 | >$0.10 |
| Workflow completion rate | >98% | <95% |

### Alert Rules

**High Latency** (`monitoring/alerts.py`):

```python
create_high_latency_alert(
    threshold_seconds=10.0,
    severity="warning",
    cooldown_minutes=30
)
```

**High Error Rate**:

```python
create_high_error_rate_alert(
    threshold_rate=0.05,  # 5%
    severity="critical",
    cooldown_minutes=30
)
```

**High Cost**:

```python
create_high_cost_alert(
    threshold_usd_per_hour=2.0,
    severity="warning",
    cooldown_minutes=60
)
```

### Notification Channels

- **Slack**: #agent-alerts channel
- **Email**: ops@yourdomain.com
- **Grafana**: Built-in alerting

---

## Future Enhancements

### Phase 5 (Q2 2026)

- [ ] Multi-tenant support
- [ ] Advanced RAG with re-ranking
- [ ] A/B testing framework
- [ ] Agent marketplace

### Phase 6 (Q3 2026)

- [ ] Kubernetes deployment
- [ ] Multi-region setup
- [ ] Advanced security (mTLS, encryption at rest)
- [ ] Custom agent training

---

## References

- [Memory Layer Documentation](./MEMORY.md)
- [LangGraph Patterns](./LANGGRAPH.md)
- [Evaluation Framework](./EVALUATION.md)
- [Temporal Docs](https://docs.temporal.io/)
- [Qdrant Docs](https://qdrant.tech/documentation/)
- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk)

---

**Maintained by**: Agent Platform Team
**Contact**: platform@yourdomain.com
**License**: Internal Use Only
