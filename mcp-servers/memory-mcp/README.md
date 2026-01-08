# Memory MCP Server

Model Context Protocol server for agent memory operations.

## Features

- **search_memory**: Semantic search across memory collections
- **save_to_memory**: Store new content with embeddings
- **get_memory_stats**: System statistics and health

## Collections

- `invoices`: Invoice matching against transactions
- `social_posts`: Social media history
- `ad_reports`: Google Ads performance
- `agent_context`: General agent execution history

## Usage

Agents can use memory tools via MCP:

```python
# Search for similar invoices
results = await mcp_client.call_tool(
    "search_memory",
    {
        "collection": "invoices",
        "query": "SNCB train ticket around 20 euros",
        "top_k": 5,
        "filters": {"matched": False}
    }
)

# Save new invoice
await mcp_client.call_tool(
    "save_to_memory",
    {
        "collection": "invoices",
        "content": "Invoice from Delhaize for groceries €45.30",
        "metadata": {
            "vendor_name": "Delhaize",
            "amount": 45.30,
            "date": "2024-01-08",
            "matched": False
        }
    }
)
```

## Configuration

Environment variables (from parent .env):
- `ENABLE_MEMORY`: Enable/disable memory system
- `QDRANT_HOST`: Qdrant server host
- `REDIS_HOST`: Redis cache host
- `OPENAI_API_KEY`: For embeddings

## Dependencies

Requires parent memory layer:
- `/memory/memory_manager.py`
- `/memory/qdrant_client.py`
- `/memory/redis_cache.py`
- `/memory/embeddings.py`
