# Temporal Workflow System

Production-ready agentic AI orchestration using Temporal.io

## Overview

This system replaces traditional cron/scheduler approaches with Temporal workflows for:
- ✅ **Durable execution** - Workflows survive crashes and restarts
- ✅ **Automatic retries** - Activities retry on failure with backoff
- ✅ **State persistence** - Workflow state is automatically saved
- ✅ **Observability** - Full execution history in Temporal UI + Langfuse traces
- ✅ **Scalability** - Horizontal scaling of workers

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Temporal Server                         │
│  (PostgreSQL + gRPC API + Web UI)                          │
└─────────────────────────────────────────────────────────────┘
                           ↕
┌─────────────────────────────────────────────────────────────┐
│                   Agent Worker (Python)                     │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  FeedPublisherWorkflow                                │  │
│  │  ├─ get_random_unused_photo (MCP)                     │  │
│  │  ├─ view_image (MCP)                                  │  │
│  │  ├─ generate_caption (Claude SDK)  ← Langfuse trace  │  │
│  │  ├─ publish_facebook (MCP) ┐                          │  │
│  │  └─ publish_instagram (MCP)┘ (parallel)               │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Activities call MCP servers:                               │
│  • feed-publisher-mcp (S3 + Meta API)                       │
│  • agent-outputs-mcp (PostgreSQL)                           │
└─────────────────────────────────────────────────────────────┘
                           ↕
┌─────────────────────────────────────────────────────────────┐
│                   Langfuse (Monitoring)                     │
│  Traces, costs, spans, errors                              │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Prerequisites

```bash
# Install Docker and Docker Compose
docker --version
docker compose version

# Copy environment template
cp .env.example .env
# Edit .env with your credentials
```

### 2. Start Temporal Infrastructure

```bash
# Start Temporal server + PostgreSQL + UI
docker compose -f docker-compose.temporal.yml up -d

# Verify Temporal is running
docker compose -f docker-compose.temporal.yml ps

# Access Temporal UI
open http://localhost:8088
```

### 3. Start Agent Worker

```bash
# Build and start the worker
docker compose up -d agent-worker

# View logs
docker compose logs -f agent-worker

# Verify worker is connected
# You should see: "Worker initialized on task queue: agent-tasks"
```

### 4. Setup Daily Schedules

```bash
# Setup schedules (one-time operation)
docker compose run --rm agent-worker sh -c "RUN_MODE=scheduler python3 -m temporal_app.schedules.daily_tasks"

# Verify schedules in Temporal UI
open http://localhost:8088/schedules
```

Expected schedules:
- **pomandi-daily-posts**: 09:00 and 18:00 UTC
- **costume-daily-posts**: 10:00 and 19:00 UTC

## Manual Workflow Execution

### Trigger Workflow Manually

```python
# Python script to trigger workflow
import asyncio
from temporalio.client import Client
from temporal_app.workflows.feed_publisher import FeedPublisherWorkflow

async def trigger_workflow(brand: str):
    client = await Client.connect("localhost:7233")

    result = await client.execute_workflow(
        FeedPublisherWorkflow.run,
        args=[brand],
        id=f"{brand}-manual-{int(time.time())}",
        task_queue="agent-tasks",
    )

    print(f"✅ Workflow completed: {result}")

# Run it
asyncio.run(trigger_workflow("pomandi"))
```

Or using Temporal CLI:

```bash
# Install Temporal CLI
brew install temporal

# Execute workflow
temporal workflow execute \
  --task-queue agent-tasks \
  --type FeedPublisherWorkflow \
  --input '"pomandi"' \
  --workflow-id pomandi-manual-test
```

## Project Structure

```
temporal_app/
├── __init__.py
├── client.py                    # Temporal client singleton
├── worker.py                    # Worker entry point
├── monitoring.py                # Langfuse integration
├── workflows/
│   ├── __init__.py
│   └── feed_publisher.py        # Main workflow
├── activities/
│   ├── __init__.py
│   └── social_media.py          # Activity implementations
└── schedules/
    ├── __init__.py
    └── daily_tasks.py           # Schedule setup

docker-compose.temporal.yml      # Temporal infrastructure
docker-compose.yml               # Agent services
Dockerfile                       # Multi-mode container
entrypoint.sh                    # Entry script (worker/api/scheduler modes)
```

## Workflows

### FeedPublisherWorkflow

**Purpose**: Daily social media post publisher

**Steps**:
1. Get random unused photo from S3 (brand-specific)
2. Analyze image with Claude
3. Generate AI caption in brand language (NL/FR)
4. Publish to Facebook and Instagram (parallel)
5. Save publication report

**Features**:
- Automatic retry on API failures
- Activity timeouts (2-5 min per step)
- Parallel publishing to save time
- Full Langfuse trace for observability
- Crash recovery (workflow resumes if worker crashes)

**Schedule**:
- Pomandi: 09:00 and 18:00 UTC (NL captions)
- Costume: 10:00 and 19:00 UTC (FR captions)

## Activities

Activities are individual units of work that can fail and retry:

| Activity | Timeout | Retries | Description |
|----------|---------|---------|-------------|
| `get_random_unused_photo` | 2 min | 3 | Fetch unused S3 photo |
| `view_image` | 1 min | 2 | Analyze image with Claude |
| `generate_caption` | 3 min | 2 | AI caption generation |
| `publish_facebook_photo` | 5 min | 3 | Post to Facebook Page |
| `publish_instagram_photo` | 5 min | 3 | Post to Instagram |
| `save_publication_report` | 1 min | 2 | Save to DB |

## Monitoring

### Temporal UI

Access: http://localhost:8088

Features:
- View all workflow executions
- See activity history and retries
- Inspect workflow state and errors
- Trigger workflows manually
- Manage schedules

### Langfuse Traces

Access: https://langfuse.pomandi.com

What's tracked:
- ✅ Workflow start/completion
- ✅ AI activity calls (generate_caption)
- ✅ Cost tracking (token usage)
- ✅ Execution time per activity
- ✅ Error stack traces

## Schedule Management

### Pause a Schedule

```python
from temporal_app.schedules import pause_schedule
await pause_schedule("pomandi-daily-posts")
```

### Resume a Schedule

```python
from temporal_app.schedules import unpause_schedule
await unpause_schedule("pomandi-daily-posts")
```

### Trigger Schedule Manually

```python
from temporal_app.schedules import trigger_schedule_now
await trigger_schedule_now("pomandi-daily-posts")
```

### Delete a Schedule

```python
from temporal_app.schedules import delete_schedule
await delete_schedule("pomandi-daily-posts")
```

## Development

### Local Development Setup

```bash
# Start Temporal
docker compose -f docker-compose.temporal.yml up -d

# Install dependencies
pip install -r requirements.txt

# Run worker locally (for debugging)
python -m temporal_app.worker

# In another terminal, trigger workflow
python -c "
import asyncio
from temporal_app.client import get_temporal_client
from temporal_app.workflows.feed_publisher import FeedPublisherWorkflow

async def test():
    client = await get_temporal_client()
    result = await client.execute_workflow(
        FeedPublisherWorkflow.run,
        args=['pomandi'],
        id='test-local',
        task_queue='agent-tasks',
    )
    print(result)

asyncio.run(test())
"
```

### Adding New Workflows

1. Create workflow in `temporal_app/workflows/`:

```python
@workflow.defn
@observe_workflow
class MyWorkflow:
    @workflow.run
    async def run(self, param: str) -> dict:
        # Your workflow logic
        result = await workflow.execute_activity(
            my_activity,
            args=[param],
            start_to_close_timeout=timedelta(minutes=5),
        )
        return result
```

2. Create activities in `temporal_app/activities/`:

```python
@activity.defn
@observe_activity
async def my_activity(param: str) -> dict:
    # Your activity logic
    return {"result": "done"}
```

3. Register in `worker.py`:

```python
worker = Worker(
    client,
    task_queue=task_queue,
    workflows=[FeedPublisherWorkflow, MyWorkflow],  # Add here
    activities=[..., my_activity],  # Add here
)
```

### Testing Activities

Activities can be tested independently:

```python
# Test activity directly
from temporal_app.activities.social_media import generate_caption

result = await generate_caption(
    image_description="Red suit",
    brand="pomandi",
    language="nl"
)
print(result)
```

## Deployment

### Production Deployment on Coolify

1. **Push code to GitHub**:
```bash
git add .
git commit -m "Add Temporal workflow system"
git push origin main
```

2. **Configure Coolify application**:
   - Set `RUN_MODE=worker`
   - Add all environment variables from `.env.example`
   - Set `TEMPORAL_HOST=temporal:7233` (if Temporal is another Coolify service)

3. **Deploy Temporal infrastructure first**:
   - Deploy `docker-compose.temporal.yml` as separate Coolify service
   - Wait for health checks to pass

4. **Deploy agent worker**:
   - Deploy main application (Dockerfile)
   - Worker will auto-connect to Temporal

5. **Setup schedules** (one-time):
```bash
# SSH into server or run via Coolify console
docker exec -it agent-worker python3 -m temporal_app.schedules.daily_tasks
```

### Environment Variables for Production

Required:
```bash
RUN_MODE=worker
TEMPORAL_HOST=temporal:7233  # Or external Temporal URL
CLAUDE_CODE_OAUTH_TOKEN=xxx
META_ACCESS_TOKEN_POMANDI=xxx
META_ACCESS_TOKEN_COSTUME=xxx
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
DATABASE_URL=postgresql://...
```

Optional but recommended:
```bash
LANGFUSE_HOST=https://langfuse.pomandi.com
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
```

## Troubleshooting

### Worker Not Connecting

**Symptom**: Worker starts but no workflows execute

**Fix**:
```bash
# Check Temporal is running
docker compose -f docker-compose.temporal.yml ps

# Check network connectivity
docker exec agent-worker ping temporal

# Verify task queue name matches
# Worker: TEMPORAL_TASK_QUEUE=agent-tasks
# Workflow: task_queue="agent-tasks"
```

### Workflow Stuck / Not Completing

**Symptom**: Workflow shows "Running" for too long

**Fix**:
1. Check Temporal UI → Workflow → Event History
2. Look for activity timeouts or errors
3. Check worker logs: `docker compose logs agent-worker`

### Activity Keeps Retrying

**Symptom**: Same activity fails repeatedly

**Fix**:
```python
# Check activity retry policy in workflow
retry_policy=workflow.RetryPolicy(
    maximum_attempts=3,  # Limit retries
    initial_interval=timedelta(seconds=10),
)
```

### Langfuse Traces Not Appearing

**Symptom**: No traces in Langfuse dashboard

**Fix**:
```bash
# Verify environment variables
echo $LANGFUSE_PUBLIC_KEY
echo $LANGFUSE_SECRET_KEY

# Check worker logs for Langfuse errors
docker compose logs agent-worker | grep -i langfuse

# Test Langfuse connection
python -c "
from langfuse import Langfuse
client = Langfuse(
    host='https://langfuse.pomandi.com',
    public_key='pk-...',
    secret_key='sk-...'
)
print('Connected:', client is not None)
"
```

## Migration from Old System

If migrating from cron/scheduler:

1. ✅ Keep old system running during migration
2. ✅ Deploy Temporal infrastructure
3. ✅ Deploy agent worker (will start executing schedules)
4. ✅ Monitor both systems for 1-2 days
5. ✅ Verify posts are published correctly
6. ✅ Disable old cron jobs
7. ✅ Remove old scheduler code

## Costs

**Temporal Server**: Free (self-hosted, open-source MIT license)

**Infrastructure Costs**:
- PostgreSQL: ~$20/month (for Temporal + agent-outputs)
- Worker VM: ~$10/month (1 CPU, 2GB RAM)
- Total: ~$30/month for production-grade orchestration

**AI Costs** (per workflow execution):
- Caption generation: ~$0.01-0.02 per post
- Daily total: ~$0.08 (4 posts × 2 brands)
- Monthly: ~$2.40

## Resources

- [Temporal Documentation](https://docs.temporal.io/)
- [Python SDK Guide](https://docs.temporal.io/dev-guide/python)
- [Temporal UI Guide](https://docs.temporal.io/web-ui)
- [Langfuse Python SDK](https://langfuse.com/docs/sdk/python)

## Support

For issues or questions:
1. Check Temporal UI event history
2. Check worker logs: `docker compose logs -f agent-worker`
3. Check Langfuse traces for errors
4. Review this README troubleshooting section
