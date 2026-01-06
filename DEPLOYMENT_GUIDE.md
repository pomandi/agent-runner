# Production Deployment Guide - Coolify

Step-by-step guide to deploy the Temporal workflow system to Coolify.

## Prerequisites

- ✅ Code pushed to GitHub: https://github.com/pomandi/agent-runner
- ✅ Coolify instance running
- ✅ External PostgreSQL database available (for agent_outputs)
- ✅ All credentials ready (Meta tokens, AWS keys, etc.)

## Deployment Steps

### Single Coolify Service (Recommended)

This deploys everything in one go: Temporal infrastructure + Agent worker

1. **Create New Service in Coolify**:
   - Type: **Docker Compose**
   - Name: `temporal-agent-runner`
   - Repository: `pomandi/agent-runner`
   - Branch: `main`
   - Docker Compose File: `docker-compose.yml` (default)

2. **Ports to Expose**:
   - Port `7233`: Temporal gRPC API (internal, optional)
   - Port `8088`: Temporal Web UI (expose publicly to access UI)
   - Port `8080`: Agent API (optional, only if using API mode)

3. **Environment Variables** (CRITICAL):

```bash
# Temporal Infrastructure
TEMPORAL_DB_PASSWORD=your_secure_temporal_password_here

# Agent Worker Configuration
RUN_MODE=worker
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=agent-tasks

# Claude SDK (REQUIRED)
CLAUDE_CODE_OAUTH_TOKEN=<your_oauth_token_from_claude_setup-token>

# Langfuse Monitoring
LANGFUSE_HOST=https://leng.pomandi.com
LANGFUSE_PUBLIC_KEY=pk-lf-fcb5d82f-ffd1-4ec2-8d62-60d2e25cd81c
LANGFUSE_SECRET_KEY=sk-lf-24a86d7a-7cb6-4a5a-a35d-8993f36c37d2

# AWS S3
AWS_ACCESS_KEY_ID=<your_aws_access_key_id>
AWS_SECRET_ACCESS_KEY=<your_aws_secret_access_key>
AWS_STORAGE_BUCKET_NAME=saleorme
AWS_S3_REGION_NAME=us-east-1

# PostgreSQL
POSTGRES_HOST=<your_postgres_host>
POSTGRES_PORT=5432
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<your_postgres_password>

# Meta API - Pomandi
META_ACCESS_TOKEN_POMANDI=<your_pomandi_token>
META_PAGE_ID_POMANDI=335388637037718
META_IG_ACCOUNT_ID_POMANDI=17841406855004574

# Meta API - Costume
META_ACCESS_TOKEN_COSTUME=<your_costume_token>
META_PAGE_ID_COSTUME=101071881743506
META_IG_ACCOUNT_ID_COSTUME=17841441106266856

# Logging
LOG_LEVEL=INFO
```

4. **Deploy**:
   - Click "Deploy"
   - Wait for all services to start (postgresql → temporal → temporal-ui → agent-worker)
   - Monitor logs: Should see "Worker initialized on task queue: agent-tasks"

5. **Access Temporal UI**:
   - URL: `http://your-coolify-domain:8088`
   - Should see Temporal Web UI dashboard

### Step 2: Setup Daily Schedules

After worker is running, setup the schedules (ONE-TIME OPERATION):

```bash
# SSH into your Coolify server or use Coolify console

# Find the agent-worker container name (might be different in Coolify)
docker ps | grep agent-worker

# Execute schedule setup
docker exec -it <container-name> python3 -m temporal_app.schedules.daily_tasks

# Example:
docker exec -it temporal-agent-runner-agent-worker-1 python3 -m temporal_app.schedules.daily_tasks
```

Expected output:
```
📅 Creating schedule: pomandi-daily-posts
   Posts at: 09:00 UTC and 18:00 UTC
✅ Schedule 'pomandi-daily-posts' created successfully

📅 Creating schedule: costume-daily-posts
   Posts at: 10:00 UTC and 19:00 UTC
✅ Schedule 'costume-daily-posts' created successfully
```

### Step 3: Verify Deployment

1. **Check Temporal UI**:
   - URL: `http://your-coolify-domain:8088`
   - Go to Schedules tab
   - Should see: `pomandi-daily-posts` and `costume-daily-posts`

2. **Check Worker Logs**:
   ```bash
   docker logs -f agent-worker
   ```
   Should see:
   ```
   ✅ Worker initialized on task queue: agent-tasks
   🎧 Listening for workflow tasks...
   ```

3. **Check Langfuse**:
   - URL: https://leng.pomandi.com
   - Project: `claude-agents-prod`
   - Should see traces when workflows execute

4. **Manual Test** (Optional):
   ```python
   # Trigger workflow manually
   docker exec -it agent-worker python3 -c "
   import asyncio
   from temporalio.client import Client
   from temporal_app.workflows.feed_publisher import FeedPublisherWorkflow

   async def test():
       client = await Client.connect('localhost:7233')
       result = await client.execute_workflow(
           FeedPublisherWorkflow.run,
           args=['pomandi'],
           id='test-manual',
           task_queue='agent-tasks'
       )
       print(result)

   asyncio.run(test())
   "
   ```

### Step 4: Monitor First Scheduled Run

Wait for the first scheduled execution (09:00 UTC for Pomandi):

1. **Watch Worker Logs**:
   ```bash
   docker logs -f agent-worker
   ```

2. **Check Temporal UI**:
   - Go to Workflows
   - Should see workflow execution with status COMPLETED

3. **Verify Posts**:
   - Check Facebook page: https://facebook.com/pomandi
   - Check Instagram: https://instagram.com/pomandi

4. **Check Langfuse Trace**:
   - Should see full trace with all activities
   - Cost tracking
   - Execution time

## Troubleshooting

### Worker Not Connecting to Temporal

**Symptom**: Worker starts but logs show connection errors

**Fix**:
1. Verify all services are running: `docker ps`
   - Should see: postgresql, temporal, temporal-ui, agent-worker
2. Check temporal health: `docker logs temporal-agent-runner-temporal-1`
3. Check worker can reach temporal:
   ```bash
   docker exec temporal-agent-runner-agent-worker-1 ping temporal
   ```

### Missing Environment Variables

**Symptom**: Worker crashes with "Missing X configuration"

**Fix**:
1. Check Coolify environment variables
2. Ensure no typos in variable names
3. Verify all tokens are valid (not expired)

### Workflow Fails with "No product images found"

**Symptom**: get_random_unused_photo activity fails

**Fix**:
1. Verify AWS credentials are correct
2. Check S3 bucket has images in `products/` prefix
3. Test: `aws s3 ls s3://saleorme/products/`

### Instagram Publish Fails

**Symptom**: Instagram activity fails with API error

**Fix**:
1. Verify Meta access token is valid (not expired)
2. Check Instagram Business Account ID is correct
3. Ensure image URL is publicly accessible (presigned URL)
4. Token might need refresh (60-day expiry)

### Schedule Not Triggering

**Symptom**: Time passes but workflow doesn't start

**Fix**:
1. Check Temporal UI → Schedules → Verify schedule exists
2. Check schedule is not paused
3. Verify worker is running and listening
4. Check server timezone vs UTC

## Meta Token Refresh

Meta tokens expire every 60 days. To refresh:

```bash
# Get current token health
docker exec -it agent-worker python3 -c "
from mcp_servers.feed_publisher_mcp.server import check_token_health
result = check_token_health('pomandi')
print(result)
"

# If < 7 days remaining, refresh
# Get new short-lived token from Graph API Explorer
# Then run:
docker exec -it agent-worker python3 -c "
from mcp_servers.feed_publisher_mcp.server import exchange_token
new_token = exchange_token('pomandi', 'new_short_token_here')
print('New token:', new_token)
"
```

## Scaling

To scale the agent worker horizontally:

1. **Scale Worker Container**:
   ```bash
   # In docker-compose.yml, add replicas to agent-worker:
   agent-worker:
     deploy:
       replicas: 3  # Run 3 worker instances
   ```

2. **Or Deploy Separate Worker Service**:
   - Create new Coolify service with only the worker
   - Use Dockerfile with RUN_MODE=worker
   - Connect to same Temporal infrastructure
   - All workers share same task queue

3. **Temporal Auto-Load Balancing**:
   - Workflows automatically distributed across workers
   - If one worker crashes, others pick up the work

## Monitoring Dashboard

Access points:

1. **Temporal UI**: http://your-server:8088
   - Workflow history
   - Schedule management
   - Error debugging

2. **Langfuse**: https://leng.pomandi.com
   - AI costs
   - Execution traces
   - Performance metrics

3. **Application Logs**:
   ```bash
   docker logs -f agent-worker
   ```

## Maintenance

### Pause All Schedules

```bash
docker exec -it agent-worker python3 -c "
import asyncio
from temporal_app.schedules import pause_schedule

async def pause_all():
    await pause_schedule('pomandi-daily-posts')
    await pause_schedule('costume-daily-posts')

asyncio.run(pause_all())
"
```

### Resume All Schedules

```bash
docker exec -it agent-worker python3 -c "
import asyncio
from temporal_app.schedules import unpause_schedule

async def resume_all():
    await unpause_schedule('pomandi-daily-posts')
    await unpause_schedule('costume-daily-posts')

asyncio.run(resume_all())
"
```

### Update Worker (Deploy New Code)

1. Push code to GitHub
2. In Coolify: Click "Redeploy"
3. Worker will:
   - Gracefully finish current workflows
   - Stop accepting new work
   - Restart with new code
   - Resume listening

**Note**: Running workflows are NOT interrupted! Temporal's durable execution ensures they continue after restart.

## Cost Estimate

**Infrastructure** (monthly):
- Temporal PostgreSQL: $20
- Worker VM (2GB RAM): $10
- Total: ~$30/month

**AI Costs** (monthly):
- 4 posts/day × 30 days = 120 posts
- Caption generation: ~$0.01/post
- Image analysis: ~$0.01/post
- Total: ~$2.40/month

**Total**: ~$32/month for fully automated social media posting

## Success Criteria

✅ Worker connects to Temporal and stays connected
✅ Schedules created and visible in Temporal UI
✅ First scheduled run completes successfully
✅ Posts appear on Facebook and Instagram
✅ Langfuse traces show full workflow execution
✅ No errors in worker logs

Once all criteria are met, the system is production-ready! 🚀
