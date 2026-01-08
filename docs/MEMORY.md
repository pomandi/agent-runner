# Memory Layer Documentation

**Vector Memory, Semantic Search, and Caching Strategy**

Version: 1.0
Last Updated: 2026-01-08
Status: Production

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Memory Manager](#memory-manager)
4. [Qdrant Vector Database](#qdrant-vector-database)
5. [Redis Cache](#redis-cache)
6. [Embedding Generation](#embedding-generation)
7. [Usage Patterns](#usage-patterns)
8. [Performance Optimization](#performance-optimization)
9. [Troubleshooting](#troubleshooting)
10. [API Reference](#api-reference)

---

## Overview

The Memory Layer provides long-term semantic memory for agents, enabling them to:

- **Remember past decisions** and learn from history
- **Search for similar content** using semantic similarity
- **Avoid duplicates** by detecting high-similarity content
- **Build context** from historical data
- **Cache frequently accessed data** for performance

### Memory Types

| Memory Type | Storage | Duration | Use Case |
|-------------|---------|----------|----------|
| **Working Memory** | Redis | 24 hours | Active sessions, temporary state |
| **Semantic Memory** | Qdrant | Permanent | Historical context, decisions, content |
| **Structured Memory** | PostgreSQL | Permanent | Relational data, transactions |

### Design Goals

1. **Fast Retrieval**: <2s for semantic search (p95)
2. **High Accuracy**: >85% similarity for matches
3. **Cost Efficient**: Embedding caching to reduce API calls
4. **Scalable**: Handle 1M+ vectors without performance degradation
5. **Simple API**: Single interface for all memory operations

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Memory Manager                           │
│  (Unified Interface - memory/memory_manager.py)              │
├─────────────────────────────────────────────────────────────┤
│  • save(collection, content, metadata)                       │
│  • search(collection, query, top_k, filters)                 │
│  • batch_save(collection, items)                             │
│  • update_metadata(collection, doc_id, updates)              │
│  • delete(collection, doc_id)                                │
│  • get_system_stats()                                        │
└─────────────────────────────────────────────────────────────┘
              │                          │
    ┌─────────┴────────┐      ┌─────────┴─────────┐
    │                  │      │                   │
    ▼                  ▼      ▼                   ▼
┌─────────────┐  ┌──────────────┐  ┌──────────────────┐
│   Qdrant    │  │ Redis Cache  │  │ Embedding Gen    │
│  (Vectors)  │  │  (L1 Cache)  │  │ (OpenAI API)     │
├─────────────┤  ├──────────────┤  ├──────────────────┤
│ • Search    │  │ • Get/Set    │  │ • generate()     │
│ • Upsert    │  │ • TTL        │  │ • batch_gen()    │
│ • Scroll    │  │ • Eviction   │  │ • token_count()  │
│ • Delete    │  │ • Clear      │  │ • cost_calc()    │
└─────────────┘  └──────────────┘  └──────────────────┘
      │                 │                    │
      └─────────────────┴────────────────────┘
                        │
                        ▼
              ┌──────────────────┐
              │   Collections    │
              ├──────────────────┤
              │ • invoices       │
              │ • social_posts   │
              │ • ad_reports     │
              │ • agent_context  │
              └──────────────────┘
```

### Three-Tier Memory Strategy

**Tier 1: Redis (Working Memory)**
- **Purpose**: Session state, query caching
- **TTL**: 24 hours (sessions), 1 hour (queries)
- **Size**: 512MB max
- **Eviction**: LRU (Least Recently Used)
- **Hit Rate**: Target >80%

**Tier 2: Qdrant (Semantic Memory)**
- **Purpose**: Long-term vector storage
- **Persistence**: Permanent (with backups)
- **Size**: Unlimited (disk-backed)
- **Query Speed**: <100ms for 1M vectors
- **Similarity**: Cosine distance

**Tier 3: PostgreSQL (Structured Memory)**
- **Purpose**: Relational data, metadata
- **Persistence**: Permanent
- **Query**: SQL-based
- **Integration**: Via MCP PostgreSQL server

---

## Memory Manager

The `MemoryManager` class provides a unified interface to all memory operations.

### Initialization

```python
# memory/memory_manager.py
from memory import MemoryManager

# Create manager instance
manager = MemoryManager()

# Initialize connections
await manager.initialize()

# Manager is now ready to use
```

### Configuration

```python
# Configuration (via environment variables)
QDRANT_HOST=qdrant
QDRANT_PORT=6333
REDIS_HOST=redis
REDIS_PORT=6379
OPENAI_API_KEY=sk-xxx
EMBEDDING_MODEL=text-embedding-3-small  # 1536 dimensions
```

### Core Operations

#### Save Document

```python
# Save a single document to memory
doc_id = await manager.save(
    collection="invoices",
    content="Invoice from SNCB for €22.70 dated 2025-01-03",
    metadata={
        "vendor_name": "SNCB",
        "amount": 22.70,
        "date": "2025-01-03",
        "matched": False,
        "invoice_id": 12345
    }
)
# Returns: 1 (document ID in Qdrant)
```

**What happens**:
1. Generate embedding for content (OpenAI API)
2. Cache embedding in Redis (key: `embed:<hash>`, TTL: 7 days)
3. Upsert vector to Qdrant collection
4. Return document ID

#### Search Similar Documents

```python
# Search for similar documents
results = await manager.search(
    collection="invoices",
    query="SNCB train ticket €22.70",
    top_k=10,
    filters={"matched": False}  # Only unmatched invoices
)

# Results format:
# [
#   {
#     "id": 1,
#     "score": 0.95,  # Cosine similarity (0-1)
#     "payload": {
#       "vendor_name": "SNCB",
#       "amount": 22.70,
#       "date": "2025-01-03",
#       "matched": False,
#       "invoice_id": 12345
#     }
#   },
#   ...
# ]
```

**What happens**:
1. Check Redis cache for query results (key: `query:<hash>`)
2. If cache miss:
   - Generate embedding for query
   - Search Qdrant vectors
   - Cache results in Redis (TTL: 1 hour)
3. Return results sorted by score

#### Batch Save

```python
# Batch save multiple documents (efficient)
items = [
    {
        "content": "Invoice from SNCB €22.70",
        "metadata": {"vendor_name": "SNCB", "amount": 22.70}
    },
    {
        "content": "Invoice from De Lijn €15.00",
        "metadata": {"vendor_name": "De Lijn", "amount": 15.00}
    },
    # ... up to 100 items
]

count = await manager.batch_save(
    collection="invoices",
    items=items
)
# Returns: 2 (number of documents saved)
```

**Performance**: ~10x faster than individual saves for large batches.

#### Update Metadata

```python
# Update metadata without re-embedding
success = await manager.update_metadata(
    collection="invoices",
    doc_id=1,
    metadata_updates={"matched": True, "matched_at": "2025-01-08"}
)
# Returns: True
```

#### Delete Document

```python
# Delete from memory
success = await manager.delete(
    collection="invoices",
    doc_id=1
)
# Returns: True
```

#### System Statistics

```python
# Get memory system stats
stats = await manager.get_system_stats()

# Stats format:
# {
#   "cache": {
#     "hit_rate_percent": 78.5,
#     "total_hits": 1523,
#     "total_misses": 412,
#     "memory_used_mb": 234.5
#   },
#   "collections": {
#     "invoices": {
#       "count": 1245,
#       "avg_score": 0.82
#     },
#     "social_posts": {
#       "count": 567,
#       "avg_score": 0.75
#     }
#   },
#   "embeddings": {
#     "total_generated": 2134,
#     "cached_percentage": 65.2,
#     "cost_usd": 0.04
#   }
# }
```

---

## Qdrant Vector Database

### Collection Schemas

#### Invoices Collection

```python
# memory/collections.py
INVOICE_COLLECTION = {
    "name": "invoices",
    "vectors": {
        "size": 1536,  # OpenAI text-embedding-3-small
        "distance": "Cosine"
    },
    "payload_schema": {
        "vendor_name": {"type": "keyword"},
        "amount": {"type": "float"},
        "date": {"type": "keyword"},
        "matched": {"type": "bool"},
        "invoice_id": {"type": "integer"},
        "invoice_number": {"type": "keyword"},
        "description": {"type": "text"}
    },
    "hnsw_config": {
        "m": 16,  # Number of edges per node
        "ef_construct": 100  # Construction time search depth
    }
}
```

**Use Case**: Store invoice documents for matching against bank transactions.

**Query Example**:
```python
results = await manager.search(
    collection="invoices",
    query="SNCB train ticket Belgium 22 euros",
    top_k=5,
    filters={"matched": False, "amount": {"gte": 20, "lte": 25}}
)
```

#### Social Posts Collection

```python
SOCIAL_POSTS_COLLECTION = {
    "name": "social_posts",
    "vectors": {"size": 1536, "distance": "Cosine"},
    "payload_schema": {
        "brand": {"type": "keyword"},  # pomandi, costume
        "platform": {"type": "keyword"},  # facebook, instagram
        "caption_text": {"type": "text"},
        "caption_language": {"type": "keyword"},  # nl, fr
        "quality_score": {"type": "float"},
        "published": {"type": "bool"},
        "published_at": {"type": "keyword"},
        "facebook_post_id": {"type": "keyword"},
        "instagram_post_id": {"type": "keyword"},
        "photo_s3_key": {"type": "keyword"}
    }
}
```

**Use Case**: Detect duplicate captions before publishing.

**Query Example**:
```python
# Check for similar captions
results = await manager.search(
    collection="social_posts",
    query="Nieuw binnen! Perfect voor jouw stijl",
    top_k=10,
    filters={"brand": "pomandi", "platform": "instagram"}
)

# Duplicate if top score > 0.90
if results and results[0]["score"] > 0.90:
    print("⚠️ Similar caption already published!")
```

#### Ad Reports Collection

```python
AD_REPORTS_COLLECTION = {
    "name": "ad_reports",
    "vectors": {"size": 1536, "distance": "Cosine"},
    "payload_schema": {
        "platform": {"type": "keyword"},  # google_ads, meta_ads
        "campaign_name": {"type": "keyword"},
        "report_date": {"type": "keyword"},
        "spend_usd": {"type": "float"},
        "conversions": {"type": "integer"},
        "cpa": {"type": "float"},
        "roas": {"type": "float"}
    }
}
```

**Use Case**: Store advertising performance reports for trend analysis.

#### Agent Context Collection

```python
AGENT_CONTEXT_COLLECTION = {
    "name": "agent_context",
    "vectors": {"size": 1536, "distance": "Cosine"},
    "payload_schema": {
        "agent_name": {"type": "keyword"},
        "context_type": {"type": "keyword"},  # decision, error, warning
        "confidence": {"type": "float"},
        "timestamp": {"type": "keyword"},
        "metadata": {"type": "json"}
    }
}
```

**Use Case**: Store agent decision history for learning and debugging.

### Advanced Queries

#### Filtered Search

```python
# Search with complex filters
results = await qdrant_client.search(
    collection_name="invoices",
    query_vector=embedding,
    query_filter=qdrant.Filter(
        must=[
            qdrant.FieldCondition(
                key="matched",
                match=qdrant.MatchValue(value=False)
            ),
            qdrant.FieldCondition(
                key="amount",
                range=qdrant.Range(gte=20.0, lte=30.0)
            )
        ]
    ),
    limit=10
)
```

#### Scroll API (Bulk Operations)

```python
# Iterate through all documents (efficient for large collections)
from qdrant_client import models as qdrant

offset = None
while True:
    results, offset = await qdrant_client.scroll(
        collection_name="invoices",
        scroll_filter=qdrant.Filter(
            must=[
                qdrant.FieldCondition(
                    key="matched",
                    match=qdrant.MatchValue(value=False)
                )
            ]
        ),
        limit=100,
        offset=offset,
        with_vectors=False  # Don't fetch vectors (faster)
    )

    if not results:
        break

    # Process batch
    for point in results:
        print(point.id, point.payload)
```

#### Aggregations

```python
# Count documents by filter
count = await qdrant_client.count(
    collection_name="invoices",
    count_filter=qdrant.Filter(
        must=[
            qdrant.FieldCondition(
                key="matched",
                match=qdrant.MatchValue(value=True)
            )
        ]
    )
)
print(f"Matched invoices: {count}")
```

---

## Redis Cache

### Cache Strategy

**L1 Cache (Redis)**: Fast lookup for frequently accessed data.

#### Cache Keys

| Key Pattern | Value Type | TTL | Purpose |
|-------------|-----------|-----|---------|
| `embed:<hash>` | Vector (binary) | 7 days | Embedding cache |
| `query:<hash>` | JSON | 1 hour | Search result cache |
| `session:<id>` | JSON | 24 hours | Agent session state |
| `stats:cache` | JSON | 5 minutes | Cache statistics |

#### Embedding Cache

```python
# memory/redis_cache.py
import hashlib
import redis.asyncio as redis

class RedisCache:
    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get cached embedding for text."""
        cache_key = f"embed:{self._hash(text)}"

        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)  # Hit!

        return None  # Miss

    async def set_embedding(self, text: str, vector: List[float]):
        """Cache embedding with 7-day TTL."""
        cache_key = f"embed:{self._hash(text)}"

        await self.redis.setex(
            cache_key,
            timedelta(days=7),
            json.dumps(vector)
        )

    def _hash(self, text: str) -> str:
        """Generate cache key hash."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]
```

**Benefits**:
- Reduces OpenAI API calls by ~65%
- Saves ~$0.02/day in embedding costs
- Improves latency by 500ms per cached embedding

#### Query Cache

```python
async def get_query_results(
    self,
    collection: str,
    query: str,
    filters: Dict
) -> Optional[List[Dict]]:
    """Get cached search results."""
    cache_key = f"query:{self._hash_query(collection, query, filters)}"

    cached = await self.redis.get(cache_key)
    if cached:
        return json.loads(cached)

    return None

async def set_query_results(
    self,
    collection: str,
    query: str,
    filters: Dict,
    results: List[Dict]
):
    """Cache search results with 1-hour TTL."""
    cache_key = f"query:{self._hash_query(collection, query, filters)}"

    await self.redis.setex(
        cache_key,
        timedelta(hours=1),
        json.dumps(results)
    )
```

**Benefits**:
- Avoids duplicate Qdrant queries
- Improves p95 latency by 80% (from 2s to 400ms)
- Reduces Qdrant load

### Cache Invalidation

#### Manual Invalidation

```python
# Clear cache for specific collection
await manager.redis_cache.clear_collection("invoices")

# Clear all cache
await manager.redis_cache.clear_all()
```

#### Automatic Invalidation

- **TTL Expiration**: Automatic after TTL expires
- **LRU Eviction**: Automatic when memory limit reached (512MB)
- **On Update**: Query cache invalidated when collection updated

### Monitoring Cache Performance

```python
# Get cache statistics
stats = await manager.redis_cache.get_stats()

# {
#   "hit_rate_percent": 78.5,
#   "total_hits": 1523,
#   "total_misses": 412,
#   "memory_used_mb": 234.5,
#   "evictions": 45,
#   "keys_count": 2567
# }
```

**Target Metrics**:
- Hit rate: >80%
- Memory usage: <512MB
- Evictions: <100/hour

---

## Embedding Generation

### OpenAI Integration

```python
# memory/embeddings.py
from openai import AsyncOpenAI

class EmbeddingGenerator:
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.dimension = 1536

    async def generate_single(self, text: str) -> List[float]:
        """Generate embedding for single text."""
        response = await self.client.embeddings.create(
            input=text,
            model=self.model
        )
        return response.data[0].embedding

    async def generate_batch(
        self,
        texts: List[str],
        batch_size: int = 100
    ) -> List[List[float]]:
        """Generate embeddings for batch (up to 2048 texts)."""
        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]

            response = await self.client.embeddings.create(
                input=batch,
                model=self.model
            )

            embeddings.extend([item.embedding for item in response.data])

        return embeddings
```

### Cost Calculation

```python
def calculate_cost(token_count: int, model: str) -> float:
    """Calculate embedding cost in USD."""
    pricing = {
        "text-embedding-3-small": 0.02 / 1_000_000,  # $0.02 per 1M tokens
        "text-embedding-3-large": 0.13 / 1_000_000   # $0.13 per 1M tokens
    }

    return token_count * pricing[model]

# Example: Embed 10,000 documents (avg 200 tokens each)
tokens = 10_000 * 200  # 2M tokens
cost = calculate_cost(tokens, "text-embedding-3-small")
print(f"Cost: ${cost:.2f}")  # $0.04
```

### Token Counting

```python
import tiktoken

def count_tokens(text: str, model: str = "text-embedding-3-small") -> int:
    """Count tokens for text."""
    encoding = tiktoken.encoding_for_model("text-embedding-ada-002")  # Same tokenizer
    return len(encoding.encode(text))

# Example
text = "Invoice from SNCB for €22.70 dated 2025-01-03"
tokens = count_tokens(text)
print(f"Tokens: {tokens}")  # ~15 tokens
```

### Optimization Tips

1. **Batch Requests**: Use `generate_batch()` for >10 texts (10x faster)
2. **Cache Aggressively**: 7-day TTL reduces API calls by 65%
3. **Truncate Long Texts**: Max 8191 tokens per text
4. **Use Small Model**: text-embedding-3-small is 85% cheaper than large

---

## Usage Patterns

### Pattern 1: Agent Memory Search

**Use Case**: Agent retrieves similar past decisions before making new decision.

```python
# langgraph_agents/invoice_matcher_graph.py
async def search_memory_node(self, state: InvoiceMatchState) -> InvoiceMatchState:
    """Search memory for similar past matches."""
    query = state["memory_query"]

    # Search for similar transactions
    results = await self.search_memory(
        collection="agent_context",
        query=query,
        top_k=5,
        filters={"agent_name": "invoice_matcher", "context_type": "auto_match"}
    )

    state["memory_results"] = results

    # Build context for Claude
    context = "\n".join([
        f"Past match (score {r['score']:.2%}): {r['payload']['summary']}"
        for r in results
    ])

    state["memory_context"] = context
    return state
```

**Benefits**:
- Agent learns from past decisions
- Improves accuracy over time
- Reduces hallucinations

### Pattern 2: Duplicate Detection

**Use Case**: Prevent publishing duplicate social media captions.

```python
# langgraph_agents/feed_publisher_graph.py
async def check_caption_history_node(
    self,
    state: FeedPublisherState
) -> FeedPublisherState:
    """Check for similar captions to avoid duplicates."""
    brand = state["brand"]
    platform = state["platform"]

    # Search for similar captions
    results = await self.search_memory(
        collection="social_posts",
        query=f"{brand} {platform} fashion post",
        top_k=10,
        filters={"brand": brand, "platform": platform, "published": True}
    )

    # Check for near-duplicate (>90% similarity)
    if results and results[0]["score"] > 0.90:
        state["duplicate_detected"] = True
        state["similar_caption"] = results[0]["payload"]["caption_text"]
        state = self.add_warning(
            state,
            f"Very similar caption found: {results[0]['payload']['caption_text'][:50]}..."
        )
    else:
        state["duplicate_detected"] = False

    return state
```

**Benefits**:
- Avoids publishing duplicate content
- Maintains brand consistency
- Reduces manual review time

### Pattern 3: Context Building

**Use Case**: Build rich context from historical data for better reasoning.

```python
async def build_context_from_memory(
    transaction: Dict,
    manager: MemoryManager
) -> str:
    """Build context for invoice matching from memory."""

    # Search 1: Similar transactions
    similar_transactions = await manager.search(
        collection="agent_context",
        query=f"{transaction['vendorName']} €{transaction['amount']}",
        top_k=3,
        filters={"context_type": "auto_match"}
    )

    # Search 2: Vendor history
    vendor_history = await manager.search(
        collection="invoices",
        query=transaction['vendorName'],
        top_k=5,
        filters={"vendor_name": transaction['vendorName'], "matched": True}
    )

    # Build context
    context = f"""
## Similar Past Matches
{format_results(similar_transactions)}

## Vendor History
{format_vendor_history(vendor_history)}

This context helps you understand typical patterns for this vendor.
"""

    return context
```

**Benefits**:
- Provides relevant historical context
- Improves decision accuracy
- Reduces token usage (vs including all history in prompt)

### Pattern 4: Bulk Backfill

**Use Case**: Migrate existing data to memory layer.

```python
# scripts/backfill_embeddings.py
async def backfill_invoices(manager: MemoryManager):
    """Backfill existing invoices to memory."""

    # Fetch from PostgreSQL
    invoices = await fetch_invoices_from_db()

    # Prepare batch items
    items = []
    for invoice in invoices:
        content = f"""
Invoice {invoice['invoice_number']}
Vendor: {invoice['vendor_name']}
Amount: €{invoice['amount']:.2f}
Date: {invoice['date']}
Description: {invoice['description']}
        """.strip()

        items.append({
            "content": content,
            "metadata": {
                "vendor_name": invoice['vendor_name'],
                "amount": invoice['amount'],
                "date": invoice['date'],
                "matched": invoice['matched'],
                "invoice_id": invoice['id']
            }
        })

    # Batch save (efficient)
    count = await manager.batch_save(
        collection="invoices",
        items=items
    )

    print(f"✅ Backfilled {count} invoices to memory")

# Run backfill
asyncio.run(backfill_invoices(manager))
```

**Performance**:
- 1000 documents: ~2 minutes
- 10,000 documents: ~15 minutes
- Cost: ~$0.04 per 10,000 documents

---

## Performance Optimization

### Query Optimization

#### 1. Use Filters to Reduce Search Space

```python
# ❌ Bad: Search entire collection
results = await manager.search(
    collection="invoices",
    query="SNCB €22.70",
    top_k=10
)

# ✅ Good: Filter to relevant subset
results = await manager.search(
    collection="invoices",
    query="SNCB €22.70",
    top_k=10,
    filters={"matched": False, "amount": {"gte": 20, "lte": 25}}
)
# 5x faster for large collections
```

#### 2. Reduce top_k When Possible

```python
# ❌ Bad: Fetch 100 results (slow)
results = await manager.search(
    collection="invoices",
    query="SNCB",
    top_k=100
)

# ✅ Good: Fetch only what you need
results = await manager.search(
    collection="invoices",
    query="SNCB",
    top_k=10  # Usually 5-10 is enough
)
# 3x faster
```

#### 3. Use with_vectors=False for Metadata-Only Queries

```python
# ❌ Bad: Fetch vectors unnecessarily
results = await qdrant_client.search(
    collection_name="invoices",
    query_vector=embedding,
    limit=10,
    with_vectors=True  # Returns 1536-dim vectors (slow)
)

# ✅ Good: Skip vectors if not needed
results = await qdrant_client.search(
    collection_name="invoices",
    query_vector=embedding,
    limit=10,
    with_vectors=False  # Only returns metadata (fast)
)
# 2x faster, 10x less bandwidth
```

### Caching Optimization

#### 1. Increase Redis Memory

```yaml
# docker-compose.yaml
redis:
  command: redis-server --maxmemory 1gb  # Increase from 512mb
```

**Impact**: Cache hit rate 65% → 85% (+20%)

#### 2. Optimize TTL Values

```python
# Longer TTL for stable data
EMBEDDING_CACHE_TTL = timedelta(days=14)  # Was 7 days

# Shorter TTL for dynamic data
QUERY_CACHE_TTL = timedelta(minutes=30)  # Was 1 hour
```

#### 3. Pre-warm Cache

```python
# scripts/warm_cache.py
async def warm_cache(manager: MemoryManager):
    """Pre-warm cache with common queries."""
    common_queries = [
        "SNCB train ticket",
        "De Lijn bus ticket",
        "Colruyt grocery shopping",
        # ... top 100 queries
    ]

    for query in common_queries:
        await manager.search(
            collection="invoices",
            query=query,
            top_k=10
        )
        # Results now cached

    print(f"✅ Cache warmed with {len(common_queries)} queries")
```

Run after deployment or cache clear.

### Embedding Optimization

#### 1. Batch Embed When Possible

```python
# ❌ Bad: Generate one by one (slow)
for text in texts:
    embedding = await embedding_gen.generate_single(text)

# ✅ Good: Batch generate (10x faster)
embeddings = await embedding_gen.generate_batch(texts, batch_size=100)
```

#### 2. Reuse Embeddings

```python
# If same text appears multiple times, embed once
unique_texts = list(set(texts))
embeddings_map = {
    text: embedding
    for text, embedding in zip(
        unique_texts,
        await embedding_gen.generate_batch(unique_texts)
    )
}

# Reuse embeddings
for text in texts:
    embedding = embeddings_map[text]  # No API call
```

---

## Troubleshooting

### Common Issues

#### 1. Low Cache Hit Rate (<50%)

**Symptoms**:
- High embedding API costs
- Slow search queries
- Redis memory not fully utilized

**Diagnosis**:
```python
stats = await manager.get_system_stats()
print(f"Hit rate: {stats['cache']['hit_rate_percent']:.1f}%")
```

**Solutions**:
- Increase Redis memory (512MB → 1GB)
- Increase embedding TTL (7 days → 14 days)
- Pre-warm cache with common queries
- Check for query variations (normalize queries)

#### 2. Qdrant Query Timeout

**Symptoms**:
- Search queries take >5s
- TimeoutError exceptions
- High Qdrant CPU usage

**Diagnosis**:
```bash
# Check Qdrant collection size
curl http://localhost:6333/collections/invoices

# Check HNSW index status
docker exec qdrant qdrant-cli collection info invoices
```

**Solutions**:
- Optimize HNSW parameters (increase `ef_construct`)
- Add filters to reduce search space
- Reduce `top_k` value
- Consider collection sharding for >1M vectors

#### 3. Embedding API Rate Limits

**Symptoms**:
- RateLimitError from OpenAI
- Batch operations failing
- High API costs

**Diagnosis**:
```python
# Check embedding generation rate
stats = await manager.get_system_stats()
print(f"Embeddings generated: {stats['embeddings']['total_generated']}")
print(f"Cost: ${stats['embeddings']['cost_usd']:.2f}")
```

**Solutions**:
- Implement exponential backoff retry
- Reduce batch size (100 → 50)
- Increase cache TTL to reduce API calls
- Consider local embedding model (sentence-transformers)

#### 4. Memory Usage Too High

**Symptoms**:
- Redis evictions increasing
- Memory alerts firing
- Slow cache performance

**Diagnosis**:
```bash
# Check Redis memory
docker exec redis redis-cli INFO memory

# Check evictions
docker exec redis redis-cli INFO stats | grep evicted_keys
```

**Solutions**:
- Reduce TTL values
- Increase maxmemory limit
- Clear old cache: `await manager.redis_cache.clear_all()`
- Adjust eviction policy (allkeys-lru → volatile-lru)

#### 5. Duplicate Documents

**Symptoms**:
- Same document appearing multiple times in results
- Collection count higher than expected

**Diagnosis**:
```python
# Check for duplicates
from qdrant_client import models as qdrant

offset = None
seen_ids = set()
duplicates = []

while True:
    results, offset = await qdrant_client.scroll(
        collection_name="invoices",
        limit=100,
        offset=offset
    )

    if not results:
        break

    for point in results:
        doc_id = point.payload.get("invoice_id")
        if doc_id in seen_ids:
            duplicates.append(doc_id)
        seen_ids.add(doc_id)

print(f"Found {len(duplicates)} duplicates")
```

**Solutions**:
- Use upsert with unique IDs
- Implement deduplication in backfill scripts
- Add unique constraint on invoice_id in metadata

### Debugging Tools

#### Memory Inspector

```python
# scripts/inspect_memory.py
async def inspect_collection(collection: str):
    """Inspect collection contents."""
    manager = MemoryManager()
    await manager.initialize()

    # Get collection info
    info = await qdrant_client.get_collection(collection)
    print(f"Collection: {collection}")
    print(f"Vectors: {info.vectors_count}")
    print(f"Points: {info.points_count}")

    # Sample random documents
    offset = None
    samples = []
    for _ in range(10):
        results, offset = await qdrant_client.scroll(
            collection_name=collection,
            limit=1,
            offset=offset
        )
        if results:
            samples.append(results[0])

    # Display samples
    for point in samples:
        print(f"\nID: {point.id}")
        print(f"Payload: {point.payload}")

asyncio.run(inspect_collection("invoices"))
```

#### Cache Monitor

```python
# Monitor cache in real-time
import asyncio

async def monitor_cache():
    manager = MemoryManager()
    await manager.initialize()

    while True:
        stats = await manager.redis_cache.get_stats()
        print(f"[{datetime.now()}] Hit rate: {stats['hit_rate_percent']:.1f}% | "
              f"Memory: {stats['memory_used_mb']:.0f}MB | "
              f"Keys: {stats['keys_count']}")
        await asyncio.sleep(10)

asyncio.run(monitor_cache())
```

---

## API Reference

### MemoryManager

```python
class MemoryManager:
    async def initialize() -> None
    async def close() -> None

    async def save(
        collection: str,
        content: str,
        metadata: Dict[str, Any]
    ) -> int

    async def search(
        collection: str,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]

    async def batch_save(
        collection: str,
        items: List[Dict[str, Any]]
    ) -> int

    async def update_metadata(
        collection: str,
        doc_id: int,
        metadata_updates: Dict[str, Any]
    ) -> bool

    async def delete(
        collection: str,
        doc_id: int
    ) -> bool

    async def get_system_stats() -> Dict[str, Any]
```

### RedisCache

```python
class RedisCache:
    async def get_embedding(text: str) -> Optional[List[float]]
    async def set_embedding(text: str, vector: List[float]) -> None

    async def get_query_results(
        collection: str,
        query: str,
        filters: Dict
    ) -> Optional[List[Dict]]

    async def set_query_results(
        collection: str,
        query: str,
        filters: Dict,
        results: List[Dict]
    ) -> None

    async def clear_collection(collection: str) -> None
    async def clear_all() -> None
    async def get_stats() -> Dict[str, Any]
```

### EmbeddingGenerator

```python
class EmbeddingGenerator:
    async def generate_single(text: str) -> List[float]
    async def generate_batch(
        texts: List[str],
        batch_size: int = 100
    ) -> List[List[float]]

    def count_tokens(text: str) -> int
    def calculate_cost(token_count: int) -> float
```

---

## Related Documentation

- [System Architecture](./ARCHITECTURE.md)
- [LangGraph Patterns](./LANGGRAPH.md)
- [Evaluation Framework](./EVALUATION.md)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [OpenAI Embeddings Guide](https://platform.openai.com/docs/guides/embeddings)

---

**Maintained by**: Agent Platform Team
**Contact**: platform@yourdomain.com
**Last Updated**: 2026-01-08
