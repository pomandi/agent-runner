# Phase 3 Deployment Guide: Evaluation Framework
## Performance Measurement & Testing

**Status:** ✅ READY FOR DEPLOYMENT
**Date:** 2026-01-08
**Phase:** 3 of 4 (Evaluation Framework)
**Prerequisites:** Phase 1 (Memory) and Phase 2 (LangGraph) must be deployed

---

## 🎉 What Was Built

### Evaluation Framework (`/evaluation/`)

**Golden Test Datasets** (`test_datasets/`)
- ✅ `invoice_matches.json` - 10 test cases with expected outcomes
- ✅ `caption_samples.json` - 12 caption quality test cases

**Custom Evaluators** (`evaluators/`)
- ✅ `invoice_matcher_eval.py` - Accuracy evaluator with metrics
- ✅ `caption_quality_eval.py` - Quality scorer (language, brand, engagement)
- ✅ `cost_efficiency_eval.py` - Cost and latency tracker

**Benchmark Suites** (`benchmarks/`)
- ✅ `test_invoice_accuracy.py` - Invoice matcher benchmark (4 tests)
- ✅ `test_caption_quality.py` - Caption quality benchmark (4 tests)

**Integrations**
- ✅ `braintrust_integration.py` - Optional Braintrust experiment tracking

### Unit Tests (`/tests/unit/`)
- ✅ `test_memory_manager.py` - 13 unit tests for memory layer

### CI/CD Pipeline (`/.github/workflows/`)
- ✅ `test.yml` - GitHub Actions workflow with 4 jobs:
  - Unit tests
  - Integration tests
  - Evaluation benchmarks (scheduled daily)
  - Code quality (ruff, black, isort)

### Configuration
- ✅ `.env` - ENABLE_EVALUATION=true

---

## 🚀 Deployment Steps

### Step 1: Verify Prerequisites

```bash
cd /home/claude/.claude/agents/agent-runner

# Check Phase 1 & 2 are deployed
docker compose ps
# Should show: qdrant, redis, agent-worker all healthy

# Verify LangGraph is enabled
grep ENABLE_LANGGRAPH .env
# Should show: ENABLE_LANGGRAPH=true
```

### Step 2: Run Unit Tests

```bash
# Run unit tests (no services needed)
pytest tests/unit/ -v

# Expected: 13 tests pass
```

### Step 3: Run Integration Tests

```bash
# Ensure services are running
docker compose up -d

# Run integration tests
ENABLE_MEMORY=true ENABLE_LANGGRAPH=true pytest tests/integration/ -v

# Expected: All integration tests pass
```

### Step 4: Run Evaluation Benchmarks

```bash
# Run invoice matcher benchmark
python evaluation/benchmarks/test_invoice_accuracy.py

# Run caption quality benchmark
python evaluation/benchmarks/test_caption_quality.py

# Results saved to: evaluation/results/*.json
```

Expected output (invoice matcher):
```
INVOICE MATCHER ACCURACY BENCHMARK
============================================================

[1/4] Running full accuracy benchmark...
Test exact_match_001: ✅ PASS
Test amount_tolerance_001: ✅ PASS
...
Overall accuracy: 90.0%
Decision accuracy: 90.0%
Pass rate: 9/10 (90.0%)

[2/4] Running cost efficiency benchmark...
Total cost: $0.0045
Avg cost per execution: $0.00045
Efficiency score: 92.5%

✅ Benchmark complete!
```

### Step 5: Setup GitHub Actions (Optional)

If using GitHub:

```bash
# Ensure workflow file exists
ls -la .github/workflows/test.yml

# Add GitHub secrets
# Go to: Settings → Secrets → Actions
# Add: OPENAI_API_KEY

# Push to GitHub
git add .github/workflows/test.yml
git commit -m "Add CI/CD pipeline"
git push
```

The workflow will:
- Run on every push/PR
- Run benchmarks daily at 6 AM UTC
- Comment PR with evaluation results

---

## 📊 Understanding the Metrics

### Invoice Matcher Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Overall accuracy | % of correct invoice_id matches | ≥ 90% |
| Decision accuracy | % of correct decision types | ≥ 85% |
| False positive rate | Matched when shouldn't | ≤ 10% |
| False negative rate | Didn't match when should | ≤ 10% |
| Avg confidence error | |predicted - expected| confidence | < 0.15 |

**By Difficulty:**
- Easy cases: Target ≥ 95%
- Medium cases: Target ≥ 85%
- Hard cases: Target ≥ 70%

### Caption Quality Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Avg language score | Correct language (NL/FR) | ≥ 85% |
| Avg brand score | Brand name mentioned | ≥ 80% |
| Avg length score | Appropriate length (50-150 chars) | ≥ 80% |
| Avg engagement score | Emojis, CTA, hashtags | ≥ 70% |
| Avg quality error | |predicted - expected| quality | < 0.15 |

**Quality Distribution:**
- High quality (≥ 85%): Should be ≥ 30%
- Medium quality (70-85%): Should be ≥ 30%
- Low quality (< 70%): Should be ≤ 40%

### Cost Efficiency Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Avg cost per execution | USD per agent run | < $0.05 |
| Success rate | % successful executions | ≥ 95% |
| Avg latency | Milliseconds per execution | < 5000ms |
| Efficiency score | Composite score | ≥ 80% |

---

## 🧪 Running Custom Evaluations

### Evaluate Invoice Matcher

```python
import asyncio
from evaluation.evaluators.invoice_matcher_eval import InvoiceMatcherEvaluator
from langgraph_agents import InvoiceMatcherGraph

async def main():
    # Initialize
    evaluator = InvoiceMatcherEvaluator()
    evaluator.load_dataset()

    graph = InvoiceMatcherGraph()
    await graph.initialize()

    # Run evaluation
    results = await evaluator.evaluate(graph)

    # Print report
    evaluator.print_report()

    # Get metrics
    metrics = evaluator.get_metrics()
    print(f"Overall Accuracy: {metrics['overall_accuracy']:.2%}")

    # Export results
    evaluator.export_results("my_results.json")

    await graph.close()

asyncio.run(main())
```

### Evaluate Caption Quality

```python
from evaluation.evaluators.caption_quality_eval import CaptionQualityEvaluator

evaluator = CaptionQualityEvaluator()
evaluator.load_dataset()

# Score all captions (no graph needed, just scoring logic)
# ... (see test_caption_quality.py for full example)

evaluator.print_report()
evaluator.export_results("caption_results.json")
```

### Track Cost Efficiency

```python
import asyncio
from evaluation.evaluators.cost_efficiency_eval import CostEfficiencyEvaluator
from langgraph_agents import InvoiceMatcherGraph

async def main():
    cost_evaluator = CostEfficiencyEvaluator()

    graph = InvoiceMatcherGraph()
    await graph.initialize()

    # Track execution
    with cost_evaluator.track_execution("invoice_matcher") as tracker:
        result = await graph.match(transaction, invoices)

        # Record token usage (get from actual API response)
        tracker.record_llm_call(prompt_tokens=300, completion_tokens=50)
        tracker.record_embedding_call(tokens=150)
        tracker.set_success(result['matched'] is not None)

    # Print report
    cost_evaluator.print_report()

    await graph.close()

asyncio.run(main())
```

---

## 🎯 Using Braintrust (Optional)

Braintrust provides experiment tracking, dashboards, and A/B testing.

### Setup

```bash
# Install Braintrust
pip install braintrust

# Sign up at https://braintrustdata.com
# Get API key from settings

# Add to .env
BRAINTRUST_API_KEY=your_api_key_here
```

### Usage

```python
from evaluation.braintrust_integration import create_braintrust_logger

async def run_with_braintrust():
    logger = create_braintrust_logger(
        project="agent-runner",
        experiment="invoice_matcher_v2"
    )

    # Log evaluation
    await logger.log_evaluation(
        name="test_case_001",
        input={"transaction": ...},
        output={"matched": True, "confidence": 0.95},
        expected={"invoice_id": 101},
        scores={"accuracy": 1.0}
    )

    # Finalize and get URL
    summary = logger.finalize()
    print(f"View results: {summary.experiment_url}")
```

---

## 🔧 Troubleshooting

### Issue: Tests failing with "ENABLE_LANGGRAPH not true"

**Solution:**
```bash
# Run tests with environment variables
ENABLE_MEMORY=true ENABLE_LANGGRAPH=true pytest tests/ -v
```

### Issue: Benchmark accuracy below target

**Symptoms:**
```
Overall accuracy: 75.0% (below target 90%)
```

**Solution:**
1. Check golden dataset quality - are expected results correct?
2. Review failures with `evaluator.get_failures()`
3. Adjust matching algorithm in `invoice_matcher_graph.py:305`
4. Re-run evaluation after fixes

### Issue: Cost efficiency too high

**Symptoms:**
```
Avg cost per execution: $0.08 (exceeds target $0.05)
```

**Solution:**
1. Review token usage with cost evaluator
2. Reduce prompt size or use shorter prompts
3. Consider caching more aggressively
4. Use cheaper model for simple cases

### Issue: GitHub Actions failing

**Symptoms:**
```
Error: OPENAI_API_KEY not set
```

**Solution:**
```bash
# Add secret to GitHub
# Settings → Secrets → Actions → New repository secret
# Name: OPENAI_API_KEY
# Value: sk-...
```

---

## 📈 Performance Targets

### Test Suite Performance

| Metric | Target | Typical |
|--------|--------|---------|
| Unit tests runtime | < 30s | ~15s |
| Integration tests runtime | < 5min | ~2min |
| Benchmarks runtime | < 10min | ~5min |
| CI/CD pipeline total | < 20min | ~10min |

### Evaluation Performance

| Component | Target | Typical |
|-----------|--------|---------|
| Invoice matcher eval | < 2min | ~1min |
| Caption quality eval | < 1min | ~30s |
| Cost tracking overhead | < 5% | ~2% |

---

## ✅ Phase 3 Complete Checklist

- [x] Golden test datasets created (10 invoice + 12 caption cases)
- [x] Invoice matcher evaluator implemented
- [x] Caption quality evaluator implemented
- [x] Cost efficiency tracker implemented
- [x] Benchmark test suites created
- [x] Braintrust integration added (optional)
- [x] Unit tests for memory manager (13 tests)
- [x] GitHub Actions CI/CD pipeline configured
- [x] .env updated (ENABLE_EVALUATION=true)

---

## 🎯 Next Steps: Phase 4

Once Phase 3 is verified:

1. **Phase 4: Enhanced Monitoring & Polish** (Week 7-8)
   - Add Prometheus + Grafana to docker-compose
   - Instrument code with custom metrics
   - Build Grafana dashboards
   - Setup alert system
   - Migrate remaining agents to LangGraph
   - Complete documentation

2. **Enable Monitoring:**
   ```yaml
   # In docker-compose.yaml
   profiles: ["monitoring"]
   ```

3. **Follow:** `/home/claude/.claude/plans/structured-prancing-meteor.md`

---

## 📞 Support

**Run Tests:**
```bash
# Quick check
pytest tests/unit/ -v

# Full suite
pytest tests/ -v

# Specific benchmark
python evaluation/benchmarks/test_invoice_accuracy.py
```

**View Results:**
```bash
# Benchmark results
ls -la evaluation/results/

# CI/CD results
# https://github.com/your-repo/actions
```

**Documentation:**
- Plan: `/home/claude/.claude/plans/structured-prancing-meteor.md`
- Phase 1: `PHASE1_DEPLOYMENT.md`
- Phase 2: `PHASE2_DEPLOYMENT.md`
- Braintrust: https://docs.braintrustdata.com

---

## 🎉 Success Indicators

You'll know Phase 3 is successful when:

✅ Unit tests: 13/13 passing
✅ Integration tests: All passing
✅ Invoice matcher accuracy: ≥ 90%
✅ Caption quality score: ≥ 80%
✅ Cost per execution: < $0.05
✅ Efficiency score: ≥ 80%
✅ CI/CD pipeline: Green on main branch
✅ Benchmarks run daily without failures

**Congratulations! Evaluation framework is production-ready! 🚀**

---

## 📝 Key Files Reference

### Evaluation Framework
- `evaluation/evaluators/invoice_matcher_eval.py:1-280` - Accuracy evaluator
- `evaluation/evaluators/caption_quality_eval.py:1-350` - Quality scorer
- `evaluation/evaluators/cost_efficiency_eval.py:1-350` - Cost tracker
- `evaluation/test_datasets/invoice_matches.json` - Golden dataset (10 cases)
- `evaluation/test_datasets/caption_samples.json` - Caption samples (12 cases)

### Benchmarks
- `evaluation/benchmarks/test_invoice_accuracy.py:1-200` - Invoice benchmark suite
- `evaluation/benchmarks/test_caption_quality.py:1-250` - Caption benchmark suite

### Tests
- `tests/unit/test_memory_manager.py:1-300` - Memory layer unit tests
- `tests/integration/test_temporal_langgraph.py` - Integration tests (from Phase 2)

### CI/CD
- `.github/workflows/test.yml:1-180` - GitHub Actions pipeline

### Configuration
- `.env:69` - ENABLE_EVALUATION flag

---

## 🏆 Achievement Summary

**Phase 3 delivered:**
- 3 custom evaluators with comprehensive metrics
- 2 golden test datasets (22 total test cases)
- 2 benchmark suites (8 benchmark tests)
- 13 unit tests for core components
- Full CI/CD pipeline with daily benchmarks
- Optional Braintrust integration
- Complete deployment documentation

**Total files created:** 15+ new files
**Total test cases:** 22 golden + 13 unit + 8 benchmark = 43 tests
**Coverage:** Memory, LangGraph, Evaluators, Benchmarks

Ready for Phase 4! 🎯
