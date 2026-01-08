# Testing Guide

Complete guide for running tests on the agent system.

---

## Test Structure

```
tests/
├── unit/                           # Unit tests (fast)
│   └── test_memory_manager.py      # Memory layer unit tests
├── integration/                    # Integration tests (require services)
│   ├── test_temporal_langgraph.py  # Temporal + LangGraph integration
│   └── conftest.py                 # Shared fixtures
├── system/                         # Full system tests (comprehensive)
│   ├── test_full_system_integration.py  # End-to-end system test
│   └── __init__.py
└── TESTING.md                      # This file
```

---

## Quick Start

### Prerequisites

1. **Services Running**:
   ```bash
   # Start required services
   docker compose up -d qdrant redis postgresql

   # OR start everything including monitoring
   docker compose --profile monitoring up -d
   ```

2. **Environment Variables**:
   ```bash
   # Required
   export OPENAI_API_KEY=sk-xxx
   export ANTHROPIC_API_KEY=sk-ant-xxx

   # Optional (for Braintrust)
   export BRAINTRUST_API_KEY=sk-xxx
   ```

3. **Install Test Dependencies**:
   ```bash
   pip install pytest pytest-asyncio pytest-cov pytest-mock
   ```

---

## Running Tests

### 1. Full System Integration Test

**Comprehensive end-to-end test covering everything:**

```bash
# Run full system test
pytest tests/system/test_full_system_integration.py -v -s

# Run specific test
pytest tests/system/test_full_system_integration.py::test_memory_layer_end_to_end -v -s

# Save results to file
pytest tests/system/test_full_system_integration.py -v --json-report --json-report-file=system-test-results.json
```

**What it tests:**
- ✅ Memory Layer (Qdrant + Redis + Embeddings)
- ✅ Invoice Matcher (LangGraph + Memory)
- ✅ Feed Publisher (LangGraph + Duplicate Detection)
- ✅ Monitoring Metrics Recording
- ✅ Evaluation Framework
- ✅ Concurrent Operations (Stress Test)
- ✅ System Health Check

**Expected output:**
```
🧪 TEST 1: Memory Layer Integration
============================================================
1.1 Testing save to memory...
✅ Saved document with ID: 1
1.2 Testing memory search (cache miss)...
✅ Found 1 results (top score: 95.2%)
   Cache miss latency: 0.823s
1.3 Testing memory search (cache hit)...
✅ Cache hit successful
   Cache hit latency: 0.015s
   Speedup: 54.9x faster
...
✅ MEMORY LAYER TEST PASSED

🧪 TEST 2: Invoice Matcher Integration
...
✅ INVOICE MATCHER TEST PASSED

...

📊 FULL SYSTEM TEST SUMMARY
============================================================
Tests Passed: 7/7
Status: ✅ ALL TESTS PASSED
```

### 2. Unit Tests

**Fast tests for individual components:**

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ --cov=memory --cov=langgraph_agents --cov-report=html

# Open coverage report
open htmlcov/index.html
```

### 3. Integration Tests

**Tests requiring services:**

```bash
# Run all integration tests
pytest tests/integration/ -v

# Run specific integration test
pytest tests/integration/test_temporal_langgraph.py -v
```

### 4. Evaluation Benchmarks

**Run evaluation framework benchmarks:**

```bash
# Run all benchmarks
pytest evaluation/benchmarks/ -v

# Run invoice accuracy benchmark
pytest evaluation/benchmarks/test_invoice_accuracy.py -v

# Run with detailed output
pytest evaluation/benchmarks/ -v -s

# Save benchmark results
pytest evaluation/benchmarks/ --json-report --json-report-file=benchmark-results.json
```

### 5. Run All Tests

```bash
# Run everything (unit + integration + system)
pytest tests/ -v

# With coverage
pytest tests/ --cov=. --cov-report=html

# Parallel execution (faster)
pytest tests/ -n auto
```

---

## Test Categories

### By Speed

| Category | Duration | When to Run |
|----------|----------|-------------|
| Unit | <1 min | Every commit |
| Integration | 2-5 min | Before PR |
| System | 5-10 min | Daily / Before deploy |
| Benchmarks | 10-20 min | Weekly |

### By Requirement

| Test Type | Requires Services | Requires API Keys |
|-----------|------------------|------------------|
| Unit | ❌ No | ❌ No |
| Integration | ✅ Qdrant, Redis | ✅ OpenAI |
| System | ✅ All services | ✅ OpenAI, Claude |
| Benchmarks | ✅ All services | ✅ OpenAI, Claude |

---

## Continuous Integration

### GitHub Actions

Tests run automatically on:
- Every push to `main` or `develop`
- Every pull request
- Daily at 6 AM UTC (benchmarks)

```yaml
# .github/workflows/test.yml
jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - name: Run unit tests
        run: pytest tests/unit/ -v

  integration-tests:
    services:
      qdrant, redis
    steps:
      - name: Run integration tests
        run: pytest tests/integration/ -v

  system-tests:
    if: github.event_name == 'schedule'
    steps:
      - name: Run full system test
        run: pytest tests/system/ -v
```

---

## Test Configuration

### pytest.ini

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --strict-markers
    --tb=short
    --color=yes
markers =
    unit: Unit tests (fast)
    integration: Integration tests (require services)
    system: System tests (comprehensive)
    slow: Slow tests (>30s)
```

### conftest.py

Shared fixtures for all tests:

```python
# tests/conftest.py
import pytest
import asyncio

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

---

## Debugging Tests

### Run Single Test with Debug Output

```bash
pytest tests/system/test_full_system_integration.py::test_memory_layer_end_to_end -v -s --pdb
```

### Print All Output

```bash
pytest tests/ -v -s --capture=no
```

### Stop on First Failure

```bash
pytest tests/ -x
```

### Run Last Failed Tests

```bash
pytest tests/ --lf
```

### Show Slowest Tests

```bash
pytest tests/ --durations=10
```

---

## Writing New Tests

### Test Template

```python
import pytest
from memory import MemoryManager

@pytest.fixture(scope="module")
async def memory_manager():
    """Initialize memory manager for tests."""
    manager = MemoryManager()
    await manager.initialize()
    yield manager
    await manager.close()

@pytest.mark.asyncio
async def test_my_feature(memory_manager):
    """Test description."""
    # Arrange
    test_data = {"key": "value"}

    # Act
    result = await memory_manager.save(
        collection="test",
        content="test content",
        metadata=test_data
    )

    # Assert
    assert result is not None
    assert result > 0
```

### Naming Conventions

- Test files: `test_*.py`
- Test functions: `test_*`
- Test classes: `Test*`
- Fixtures: descriptive names (no `test_` prefix)

### Best Practices

1. **Use fixtures** for setup/teardown
2. **Test one thing** per test function
3. **Use descriptive names** that explain what's being tested
4. **Add docstrings** to complex tests
5. **Mock external services** when possible
6. **Clean up** test data after tests

---

## Troubleshooting

### Tests Hang

```bash
# Set timeout
pytest tests/ --timeout=300

# Or kill hanging tests
pkill -f pytest
```

### Connection Errors

```bash
# Check services are running
docker compose ps

# Restart services
docker compose restart qdrant redis

# Check logs
docker compose logs qdrant
docker compose logs redis
```

### Import Errors

```bash
# Install dependencies
pip install -r requirements.txt

# Set PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### API Rate Limits

```bash
# OpenAI rate limit
# Wait 60 seconds or use different API key

# Add delay between tests
pytest tests/ --dist=loadscope
```

---

## Performance Targets

### System Test Performance

| Metric | Target | Alert If |
|--------|--------|----------|
| Total duration | <10 min | >15 min |
| Memory test | <2 min | >5 min |
| Invoice matcher test | <3 min | >5 min |
| Feed publisher test | <2 min | >4 min |
| Stress test | <1 min | >3 min |

### Individual Test Performance

| Test | Target | Critical If |
|------|--------|-------------|
| Memory save | <0.5s | >2s |
| Memory search (cache miss) | <1s | >3s |
| Memory search (cache hit) | <0.1s | >0.5s |
| Invoice match | <5s | >10s |
| Caption generation | <3s | >8s |

---

## Test Coverage

### Current Coverage

```bash
# Generate coverage report
pytest tests/ --cov=. --cov-report=html --cov-report=term

# Coverage targets
# - Memory layer: >90%
# - LangGraph agents: >80%
# - Activities: >70%
# - Overall: >75%
```

### View Coverage

```bash
# Open HTML report
open htmlcov/index.html

# Terminal summary
pytest tests/ --cov=. --cov-report=term-missing
```

---

## Related Documentation

- [Evaluation Framework](../docs/EVALUATION.md)
- [Memory Layer](../docs/MEMORY.md)
- [LangGraph Patterns](../docs/LANGGRAPH.md)
- [System Architecture](../docs/ARCHITECTURE.md)

---

**Maintained by**: Agent Platform Team
**Last Updated**: 2026-01-08
