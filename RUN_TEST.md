# Running Feed Publisher Test

## From Coolify Container

```bash
# SSH into your Coolify server
ssh user@46.224.117.155

# Execute script inside agent-worker container
docker exec -it agent-worker python3 /app/scripts/trigger_workflow.py pomandi

# Or for Costume brand
docker exec -it agent-worker python3 /app/scripts/trigger_workflow.py costume
```

## Expected Output

```
🔗 Connecting to Temporal at temporal:7233...
✅ Connected to Temporal

🚀 Starting Feed Publisher workflow...
   Brand: pomandi
   Workflow ID: feed-publisher-test-pomandi
   Task Queue: agent-tasks

✅ Workflow started successfully!
   Run ID: xxxxx-xxxxx-xxxxx

⏳ Waiting for workflow to complete (max 5 minutes)...

🎉 Workflow completed!

📊 Results:
{'status': 'success', 'posts_published': 1, 'brand': 'pomandi', ...}
```

## Via Temporal UI

1. Go to: http://ns0w8ogg40w0cggko04gwck8.46.224.117.155.sslip.io
2. Click "Start Workflow"
3. Enter:
   - Workflow Type: `FeedPublisherWorkflow`
   - Task Queue: `agent-tasks`
   - Input: `["pomandi"]`
4. Click "Start" and watch execution

## Troubleshooting

### Container not found
```bash
# List containers
docker ps

# Find correct container name
docker ps | grep agent-worker
```

### Connection refused
```bash
# Check Temporal is running
docker exec -it temporal tctl cluster health
```

### View logs
```bash
# Agent worker logs
docker logs -f agent-worker

# Temporal logs
docker logs -f temporal
```
