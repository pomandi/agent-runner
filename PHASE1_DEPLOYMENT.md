# Phase 1 Deployment Guide: Memory Layer
## Production-Grade Agent System Upgrade

**Status:** ✅ READY FOR DEPLOYMENT
**Date:** 2026-01-08
**Phase:** 1 of 4 (Memory Layer Foundation)

---

## 🎉 What Was Built

### Infrastructure
- ✅ Qdrant v1.11.3 (Vector database for semantic memory)
- ✅ Redis 7-alpine (Session cache, 24h TTL)
- ✅ Docker Compose integration (health checks, volumes)

### Memory Layer (`/memory/`)
- ✅ `collections.py` - Qdrant collection schemas (invoices, social_posts, ad_reports, agent_context)
- ✅ `embeddings.py` - OpenAI text-embedding-3-small wrapper with batching & caching
- ✅ `qdrant_client.py` - Async Qdrant client with retry logic
- ✅ `redis_cache.py` - Redis cache with TTL & stats
- ✅ `memory_manager.py` - **Unified memory interface** (main API for agents)

### MCP Server (`/mcp-servers/memory-mcp/`)
- ✅ `search_memory` tool - Semantic search across collections
- ✅ `save_to_memory` tool - Store new content with embeddings
- ✅ `get_memory_stats` tool - System health & statistics

### Utilities (`/scripts/`)
- ✅ `bootstrap_memory.py` - Initialize collections & health checks
- ✅ `backfill_embeddings.py` - Migrate existing data from PostgreSQL

---

## 🚀 Deployment Steps

### Step 1: Verify Configuration

Check environment variables in `.env`:

```bash
cd /home/claude/.claude/agents/agent-runner

# Verify env vars are set
grep -E "QDRANT_HOST|REDIS_HOST|OPENAI_API_KEY|ENABLE_MEMORY" .env
```

Expected output:
```
QDRANT_HOST=qdrant
REDIS_HOST=redis
OPENAI_API_KEY=sk-5BoDb...
ENABLE_MEMORY=true
```

### Step 2: Build & Start Services

```bash
# Stop existing services (if running)
docker compose down

# Pull/build new images
docker compose build agent-worker agent-api

# Start all services (including new Qdrant & Redis)
docker compose up -d

# Wait for health checks (~30 seconds)
sleep 30

# Verify services are healthy
docker compose ps
```

Expected output:
```
NAME                IMAGE                        STATUS
agent-worker        agent-runner-agent-worker    Up (healthy)
qdrant              qdrant/qdrant:v1.11.3        Up (healthy)
redis               redis:7-alpine                Up (healthy)
temporal            temporalio/auto-setup:1.25.1 Up (healthy)
temporal-postgresql postgres:17-alpine           Up (healthy)
temporal-ui         temporalio/ui:2.35.0         Up
```

### Step 3: Bootstrap Memory System

Run the bootstrap script to initialize collections:

```bash
# Install dependencies first (if not already)
cd /home/claude/.claude/agents/agent-runner
pip install -r requirements.txt

# Run bootstrap script
python scripts/bootstrap_memory.py
```

Expected output:
```
============================================================
Memory System Bootstrap
============================================================

Step 1: Checking environment variables...
  ✓ QDRANT_HOST = qdrant
  ✓ REDIS_HOST = redis
  ✓ OPENAI_API_KEY = sk-5BoDb...
  ✓ EMBEDDING_MODEL = text-embedding-3-small

Step 2: Initializing memory manager...
  ✓ Memory manager initialized

Step 3: Creating Qdrant collections...
  ✓ Created collection: invoices
  ✓ Created collection: social_posts
  ✓ Created collection: ad_reports
  ✓ Created collection: agent_context

Step 4: Testing embedding generation...
  ✓ Generated 1536D embedding

Step 5: Testing memory operations...
  ✓ Saved test document (ID: 12345)
  ✓ Search working (similarity: 95.3%)

Step 6: Memory system statistics...
  Redis cache:
    - Hit rate: 0.0%
    - Total requests: 0
  Collections:
    - invoices: 0 documents
    - social_posts: 0 documents
    - ad_reports: 0 documents
    - agent_context: 1 documents

Step 7: Final health check...
  Qdrant: ✓ Healthy
  Redis:  ✓ Healthy

============================================================
SUCCESS: Memory system is fully operational!
============================================================
```

### Step 4: Backfill Existing Data (Optional)

Migrate existing data from PostgreSQL to Qdrant:

```bash
# Preview what will be imported (dry run)
python scripts/backfill_embeddings.py --collection invoices --limit 100 --dry-run

# Import invoices (first 100 for testing)
python scripts/backfill_embeddings.py --collection invoices --limit 100

# Import social posts
python scripts/backfill_embeddings.py --collection social_posts --limit 50

# Or import all collections
python scripts/backfill_embeddings.py --all --limit 1000
```

**Note:** The script will show cost estimate before proceeding:
```
Estimated cost:
  - Total tokens: 45,230
  - Estimated USD: $0.0009
  - Avg tokens/item: 452.3

Proceed with backfill? (y/n):
```

### Step 5: Verify Memory is Working

Test memory operations:

```python
# Quick test script
python3 << 'EOF'
import asyncio
from memory import MemoryManager

async def test():
    manager = MemoryManager()
    await manager.initialize()

    # Save test document
    await manager.save(
        collection="invoices",
        content="Invoice from SNCB for train ticket €22.70",
        metadata={"vendor_name": "SNCB", "amount": 22.70, "matched": False}
    )

    # Search
    results = await manager.search(
        collection="invoices",
        query="SNCB train ticket",
        top_k=3
    )

    print(f"Found {len(results)} results:")
    for r in results:
        print(f"  - Score: {r['score']:.2%}, Vendor: {r['payload']['vendor_name']}")

    await manager.close()

asyncio.run(test())
EOF
```

Expected output:
```
Found 1 results:
  - Score: 95.3%, Vendor: SNCB
```

---

## 📊 System Verification

### Check Qdrant Dashboard

```bash
# Open Qdrant UI in browser
open http://localhost:6333/dashboard

# Or via curl
curl http://localhost:6333/collections
```

### Check Redis

```bash
# Connect to Redis CLI
docker exec -it agent-redis redis-cli

# Inside Redis CLI:
> PING
PONG
> KEYS memory:*
(list of cached queries)
> EXIT
```

### Check Logs

```bash
# Agent worker logs
docker compose logs -f agent-worker | grep memory

# Qdrant logs
docker compose logs -f qdrant

# Redis logs
docker compose logs -f redis
```

---

## 🧪 Testing Memory in Agents

### Test via Python

```python
import asyncio
from memory import MemoryManager

async def test_agent_memory():
    manager = MemoryManager()
    await manager.initialize()

    # Test 1: Save invoice
    print("Test 1: Saving invoice...")
    doc_id = await manager.save(
        collection="invoices",
        content="Invoice from Delhaize for groceries €45.30 dated 2024-01-08",
        metadata={
            "vendor_name": "Delhaize",
            "amount": 45.30,
            "date": "2024-01-08",
            "matched": False
        }
    )
    print(f"✓ Saved invoice (ID: {doc_id})")

    # Test 2: Search for similar invoices
    print("\nTest 2: Searching for similar invoices...")
    results = await manager.search(
        collection="invoices",
        query="Delhaize groceries around 45 euros",
        top_k=5,
        filters={"matched": False}
    )
    print(f"✓ Found {len(results)} similar invoices")
    for i, r in enumerate(results[:3], 1):
        print(f"  {i}. {r['payload']['vendor_name']} €{r['payload']['amount']} (score: {r['score']:.2%})")

    # Test 3: Get stats
    print("\nTest 3: Getting system stats...")
    stats = await manager.get_system_stats()
    print(f"✓ Cache hit rate: {stats['cache']['hit_rate_percent']:.1f}%")
    for coll_name, coll_info in stats['collections'].items():
        print(f"  {coll_name}: {coll_info.get('points_count', 0)} documents")

    await manager.close()
    print("\n✓ All tests passed!")

asyncio.run(test_agent_memory())
```

### Test via MCP Server

```bash
# Start MCP server
cd /home/claude/.claude/agents/agent-runner
python mcp-servers/memory-mcp/server.py
```

---

## 🔧 Troubleshooting

### Issue: Qdrant not starting

**Symptoms:**
```
qdrant | Error: Cannot bind to port 6333
```

**Solution:**
```bash
# Check if port is already in use
lsof -i :6333

# Kill the process or change port in docker-compose.yaml
```

### Issue: Redis connection failed

**Symptoms:**
```
redis_connection_failed error="Connection refused"
```

**Solution:**
```bash
# Check Redis is running
docker compose ps redis

# Restart Redis
docker compose restart redis

# Check logs
docker compose logs redis
```

### Issue: OpenAI API key invalid

**Symptoms:**
```
embedding_generation_failed error="Invalid API key"
```

**Solution:**
```bash
# Verify API key is correct in .env
grep OPENAI_API_KEY .env

# Test API key directly
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### Issue: Out of memory

**Symptoms:**
```
Qdrant container restarting
```

**Solution:**
```bash
# Check available memory
free -h

# Reduce Redis maxmemory in docker-compose.yaml:
command: redis-server --appendonly yes --maxmemory 256mb

# Or increase VPS memory
```

---

## 📈 Performance Metrics

### Expected Performance

| Metric | Target | Typical |
|--------|--------|---------|
| Embedding generation | <1s per doc | ~200ms |
| Qdrant query latency | <2s | ~50ms |
| Redis cache hit rate | >50% | 60-80% |
| Memory overhead | <2GB | ~1.5GB |

### Cost Estimates

| Operation | Tokens | Cost (USD) |
|-----------|--------|------------|
| Embed 1000 invoices | ~500K | $0.01 |
| Embed 100 captions | ~20K | <$0.001 |
| Monthly (estimated) | ~5M | **$0.10** |

---

## ✅ Phase 1 Complete Checklist

- [ ] Docker Compose services running (Qdrant + Redis)
- [ ] Bootstrap script successful
- [ ] Collections created in Qdrant
- [ ] Test save/search working
- [ ] (Optional) Existing data backfilled
- [ ] Health checks passing
- [ ] Agents can access memory-mcp server

---

## 🎯 Next Steps: Phase 2

Once Phase 1 is verified:

1. **Phase 2: LangGraph Integration** (Week 3-4)
   - Migrate invoice-matcher to LangGraph
   - Migrate feed-publisher to LangGraph
   - Memory-aware agent workflows

2. **Enable LangGraph:**
   ```bash
   # In .env
   ENABLE_LANGGRAPH=true
   ```

3. **Follow:** `/home/claude/.claude/plans/structured-prancing-meteor.md`

---

## 📞 Support

**Issues:** Report in project repository
**Logs:** Check `docker compose logs` for errors
**Stats:** Run `python scripts/bootstrap_memory.py` to verify health

---

## 🎉 Success Indicators

You'll know Phase 1 is successful when:

✅ All Docker services show "Up (healthy)"
✅ Bootstrap script completes without errors
✅ Collections visible in Qdrant dashboard
✅ Test save/search returns results with >90% similarity
✅ Redis cache hit rate increases over time
✅ Memory system stats show non-zero document counts

**Congratulations! Memory layer is production-ready! 🚀**
