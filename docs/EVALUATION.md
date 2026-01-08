# Evaluation Framework Documentation

**Measuring and Improving Agent Performance with Golden Datasets and Custom Evaluators**

Version: 1.0
Last Updated: 2026-01-08
Status: Production

---

## Table of Contents

1. [Overview](#overview)
2. [Evaluation Philosophy](#evaluation-philosophy)
3. [Test Datasets](#test-datasets)
4. [Custom Evaluators](#custom-evaluators)
5. [Benchmark Suites](#benchmark-suites)
6. [Braintrust Integration](#braintrust-integration)
7. [CI/CD Integration](#cicd-integration)
8. [Metrics and Targets](#metrics-and-targets)
9. [Running Evaluations](#running-evaluations)
10. [Interpreting Results](#interpreting-results)

---

## Overview

The Evaluation Framework provides systematic testing and measurement of agent performance using:

- **Golden Datasets**: Curated test cases with expected outcomes
- **Custom Evaluators**: Specialized metrics for each agent type
- **Benchmark Suites**: Automated test runs with pytest
- **Braintrust Integration**: Experiment tracking and A/B testing (optional)
- **CI/CD Pipeline**: Automated evaluation on every commit

### Why Evaluate?

| Without Evaluation | With Evaluation |
|-------------------|-----------------|
| ❌ No visibility into accuracy | ✅ Track accuracy over time |
| ❌ Regressions go unnoticed | ✅ Catch regressions in CI/CD |
| ❌ Arbitrary "looks good" | ✅ Data-driven decisions |
| ❌ Manual testing only | ✅ Automated testing |
| ❌ Unknown cost per execution | ✅ Cost tracking and optimization |

### Evaluation Flow

```
┌─────────────────────────────────────────────────────────┐
│                  Golden Dataset                          │
│  (10+ test cases with expected results)                 │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                 Run Agent on Tests                       │
│  (Generate actual results for each test case)           │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│              Custom Evaluator                            │
│  (Compare expected vs actual, calculate metrics)        │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                Evaluation Report                         │
│  • Overall accuracy: 92%                                 │
│  • Decision accuracy: 95%                                │
│  • False positive rate: 3%                               │
│  • Cost per execution: $0.03                             │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│           Pass/Fail Thresholds                           │
│  ✅ accuracy >= 90% → PASS                               │
│  ❌ accuracy < 90% → FAIL (block deployment)             │
└─────────────────────────────────────────────────────────┘
```

---

## Evaluation Philosophy

### Golden Datasets > Unit Tests

Traditional unit tests check implementation details. Golden datasets test outcomes.

```python
# ❌ Unit test: Tests implementation
def test_invoice_matching_logic():
    matcher = InvoiceMatcher()
    assert matcher.vendor_match_score("SNCB", "SNCB") == 1.0

# ✅ Golden dataset: Tests real-world outcome
{
  "test_case": "exact_match_001",
  "input": {
    "transaction": {"vendorName": "SNCB", "amount": 22.70},
    "invoices": [{"id": 1, "vendorName": "SNCB", "amount": 22.70}]
  },
  "expected": {
    "matched": true,
    "invoice_id": 1,
    "confidence": 1.0,
    "decision_type": "auto_match"
  }
}
```

**Benefits of Golden Datasets**:
- Tests end-to-end behavior, not implementation
- Can refactor code without breaking tests
- Real-world test cases from production
- Easy for non-engineers to review

### Metrics That Matter

Focus on business-relevant metrics, not vanity metrics.

| Vanity Metric | Business Metric |
|--------------|-----------------|
| LLM response time | Time to resolution (end-to-end) |
| Token count | Cost per execution |
| Number of tool calls | Success rate |
| Prompt complexity | User satisfaction score |

### Continuous Improvement

Evaluation is not one-time. Build a feedback loop:

```
1. Collect production examples
   ↓
2. Add to golden dataset
   ↓
3. Run evaluation → Find gaps
   ↓
4. Improve agent (prompts, logic, memory)
   ↓
5. Re-evaluate → Measure improvement
   ↓
(repeat)
```

---

## Test Datasets

### Dataset Structure

Golden datasets are JSON files in `evaluation/test_datasets/`.

```json
{
  "dataset_name": "invoice_matches_golden",
  "version": "1.0",
  "created_at": "2025-01-08",
  "test_cases": [
    {
      "id": "exact_match_001",
      "difficulty": "easy",
      "description": "Exact vendor name and amount match",
      "input": {
        "transaction": {
          "vendorName": "SNCB",
          "amount": 22.70,
          "date": "2025-01-03"
        },
        "invoices": [
          {
            "id": 1,
            "vendorName": "SNCB",
            "amount": 22.70,
            "date": "2025-01-03"
          }
        ]
      },
      "expected_result": {
        "matched": true,
        "invoice_id": 1,
        "confidence": 1.0,
        "decision_type": "auto_match"
      }
    },
    {
      "id": "fuzzy_match_001",
      "difficulty": "medium",
      "description": "Vendor name variation, amount within tolerance",
      "input": {
        "transaction": {
          "vendorName": "NMBS",
          "amount": 22.50,
          "date": "2025-01-03"
        },
        "invoices": [
          {
            "id": 2,
            "vendorName": "SNCB/NMBS",
            "amount": 22.70,
            "date": "2025-01-03"
          }
        ]
      },
      "expected_result": {
        "matched": true,
        "invoice_id": 2,
        "confidence": 0.85,
        "decision_type": "human_review"
      }
    }
  ]
}
```

### Invoice Matching Dataset

**File**: `evaluation/test_datasets/invoice_matches.json`

**Test Cases**: 10 scenarios

| ID | Difficulty | Scenario |
|----|-----------|----------|
| exact_match_001 | Easy | Exact match on all fields |
| fuzzy_match_001 | Medium | Vendor name variation |
| amount_tolerance_001 | Medium | Amount within 5% tolerance |
| multiple_candidates_001 | Hard | Multiple potential matches |
| no_match_001 | Easy | No suitable invoice |
| date_mismatch_001 | Medium | Date off by 7 days |
| partial_vendor_001 | Hard | Partial vendor name |
| amount_mismatch_001 | Easy | Amount difference >10% |
| missing_invoice_data_001 | Medium | Invoice missing key fields |
| edge_case_001 | Hard | Complex scenario |

**Usage**:

```python
from evaluation.evaluators import InvoiceMatcherEvaluator

evaluator = InvoiceMatcherEvaluator(
    dataset_path="evaluation/test_datasets/invoice_matches.json"
)

results = await evaluator.evaluate(invoice_matcher_graph)
metrics = evaluator.get_metrics()

print(f"Accuracy: {metrics['overall_accuracy']:.1%}")
```

### Caption Quality Dataset

**File**: `evaluation/test_datasets/caption_samples.json`

**Test Cases**: 12 scenarios

| ID | Language | Quality | Issue |
|----|----------|---------|-------|
| high_quality_nl_001 | Dutch | High | None |
| high_quality_fr_001 | French | High | None |
| medium_quality_nl_001 | Dutch | Medium | Minor length issue |
| low_quality_nl_001 | Dutch | Low | Wrong language |
| duplicate_nl_001 | Dutch | Medium | Very similar to past |
| missing_brand_nl_001 | Dutch | Low | No brand mention |
| too_short_nl_001 | Dutch | Low | <30 characters |
| no_emoji_nl_001 | Dutch | Medium | No emojis |
| wrong_language_001 | Dutch | Low | French words in NL |
| excellent_fr_001 | French | High | Perfect score |
| duplicate_fr_001 | French | Medium | Similar to past |
| low_engagement_fr_001 | French | Medium | Poor engagement words |

**Expected Quality Scores**:

```python
# Quality calculation (from caption_quality_eval.py)
quality_score = (
    language_score * 0.35 +  # Correct language
    brand_score * 0.30 +      # Brand consistency
    length_score * 0.15 +     # Appropriate length
    engagement_score * 0.20   # Engagement potential
)
```

### Creating New Datasets

#### 1. Collect Real Examples

Start with production data:

```python
# scripts/collect_examples.py
async def collect_invoice_matches():
    """Collect real invoice matches from production."""
    # Query database for matched invoices
    matches = await db.query("""
        SELECT transaction, invoice, confidence
        FROM invoice_matches
        WHERE matched_at > NOW() - INTERVAL '30 days'
        AND confidence IS NOT NULL
        ORDER BY RANDOM()
        LIMIT 100
    """)

    # Convert to test cases
    test_cases = []
    for match in matches:
        test_case = {
            "id": f"real_{match['id']}",
            "difficulty": "real",
            "input": {
                "transaction": match["transaction"],
                "invoices": [match["invoice"]]
            },
            "expected_result": {
                "matched": True,
                "invoice_id": match["invoice"]["id"],
                "confidence": match["confidence"]
            }
        }
        test_cases.append(test_case)

    return test_cases
```

#### 2. Add Edge Cases

Manually create challenging scenarios:

```python
edge_cases = [
    {
        "id": "edge_currency_symbol",
        "description": "Transaction uses $ instead of €",
        "input": {
            "transaction": {"vendorName": "Amazon", "amount": "$25.00"}
        },
        "expected_result": {"matched": False}
    },
    {
        "id": "edge_unicode_vendor",
        "description": "Vendor name has unicode characters",
        "input": {
            "transaction": {"vendorName": "Café René"}
        },
        "expected_result": {"matched": True, "invoice_id": 456}
    }
]
```

#### 3. Balance Dataset

Ensure diverse coverage:

```python
def analyze_dataset_coverage(test_cases):
    """Analyze dataset balance."""
    by_difficulty = Counter(tc["difficulty"] for tc in test_cases)
    by_outcome = Counter(tc["expected_result"]["matched"] for tc in test_cases)

    print(f"Difficulty distribution: {dict(by_difficulty)}")
    print(f"Outcome distribution: {dict(by_outcome)}")

    # Target: 40% easy, 40% medium, 20% hard
    # Target: 70% matched, 30% unmatched
```

#### 4. Review and Validate

Have domain experts review test cases:

```python
def validate_test_case(test_case):
    """Validate test case makes sense."""
    input_data = test_case["input"]
    expected = test_case["expected_result"]

    # Check consistency
    if expected["matched"]:
        assert expected["invoice_id"] is not None
        assert expected["confidence"] > 0

    # Check realism
    assert 0 <= expected["confidence"] <= 1

    return True
```

---

## Custom Evaluators

### Evaluator Pattern

All evaluators follow this pattern:

```python
class BaseEvaluator:
    """Base evaluator interface."""

    def __init__(self, dataset_path: str):
        self.dataset = self.load_dataset(dataset_path)
        self.results: List[EvalResult] = []

    def load_dataset(self, path: str) -> Dict:
        """Load test dataset from JSON."""
        with open(path, 'r') as f:
            return json.load(f)

    async def evaluate(self, agent) -> List[EvalResult]:
        """
        Run agent on all test cases.

        Returns:
            List of evaluation results (one per test case)
        """
        raise NotImplementedError

    def get_metrics(self) -> Dict[str, Any]:
        """
        Calculate aggregate metrics from results.

        Returns:
            Dictionary of metric names to values
        """
        raise NotImplementedError
```

### Invoice Matcher Evaluator

**File**: `evaluation/evaluators/invoice_matcher_eval.py`

**Metrics Calculated**:

1. **Overall Accuracy**: % of correct match decisions
2. **Decision Accuracy**: % of correct decision types (auto/review/no match)
3. **False Positive Rate**: % of incorrect matches
4. **False Negative Rate**: % of missed matches
5. **Confidence Calibration**: How well confidence scores predict accuracy
6. **Average Latency**: Mean execution time

```python
class InvoiceMatcherEvaluator(BaseEvaluator):
    async def evaluate(self, graph: InvoiceMatcherGraph) -> List[MatchResult]:
        """Run invoice matcher on all test cases."""
        results = []

        for test_case in self.dataset['test_cases']:
            # Extract inputs
            transaction = test_case['input']['transaction']
            invoices = test_case['input']['invoices']
            expected = test_case['expected_result']

            # Run agent
            start_time = time.time()
            try:
                actual = await graph.match(transaction, invoices)
                latency = time.time() - start_time
                error = None
            except Exception as e:
                actual = None
                latency = time.time() - start_time
                error = str(e)

            # Compare expected vs actual
            result = MatchResult(
                test_case_id=test_case['id'],
                difficulty=test_case['difficulty'],
                expected=expected,
                actual=actual,
                latency=latency,
                error=error,
                correct=self._is_correct(expected, actual)
            )

            results.append(result)

        self.results = results
        return results

    def _is_correct(self, expected: Dict, actual: Dict) -> bool:
        """Check if actual matches expected."""
        if actual is None:
            return False

        # Check match decision
        if expected['matched'] != actual['matched']:
            return False

        # If matched, check invoice_id
        if expected['matched']:
            if expected['invoice_id'] != actual['invoice_id']:
                return False

        return True

    def get_metrics(self) -> Dict[str, Any]:
        """Calculate aggregate metrics."""
        total = len(self.results)
        correct = sum(1 for r in self.results if r.correct)

        # Overall accuracy
        overall_accuracy = correct / total if total > 0 else 0

        # Decision accuracy (auto_match vs human_review vs no_match)
        decision_correct = sum(
            1 for r in self.results
            if r.actual and r.expected['decision_type'] == r.actual['decision_type']
        )
        decision_accuracy = decision_correct / total if total > 0 else 0

        # False positives (predicted match, should be no match)
        false_positives = sum(
            1 for r in self.results
            if not r.expected['matched'] and r.actual and r.actual['matched']
        )
        false_positive_rate = false_positives / total if total > 0 else 0

        # False negatives (predicted no match, should be match)
        false_negatives = sum(
            1 for r in self.results
            if r.expected['matched'] and (not r.actual or not r.actual['matched'])
        )
        false_negative_rate = false_negatives / total if total > 0 else 0

        # Latency stats
        latencies = [r.latency for r in self.results if r.latency]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0

        return {
            'overall_accuracy': overall_accuracy,
            'decision_accuracy': decision_accuracy,
            'false_positive_rate': false_positive_rate,
            'false_negative_rate': false_negative_rate,
            'avg_latency_seconds': avg_latency,
            'p95_latency_seconds': p95_latency,
            'total_test_cases': total,
            'correct_count': correct,
            'error_count': sum(1 for r in self.results if r.error)
        }
```

### Caption Quality Evaluator

**File**: `evaluation/evaluators/caption_quality_eval.py`

**Quality Components**:

```python
def score_caption(self, caption: str, expected_language: str, brand: str) -> float:
    """Score caption quality (0-1)."""

    # 1. Language check (35% weight)
    language_score = self.score_language(caption, expected_language)

    # 2. Brand consistency (30% weight)
    brand_score = self.score_brand(caption, brand)

    # 3. Length appropriateness (15% weight)
    length_score = self.score_length(caption)

    # 4. Engagement potential (20% weight)
    engagement_score = self.score_engagement(caption)

    # Weighted total
    quality_score = (
        language_score * 0.35 +
        brand_score * 0.30 +
        length_score * 0.15 +
        engagement_score * 0.20
    )

    return quality_score

def score_language(self, caption: str, expected: str) -> float:
    """Check if caption uses correct language."""
    if expected == "nl":
        # Dutch keywords
        dutch_words = ["nieuw", "voor", "jouw", "binnen", "naar", "het", "de"]
        matches = sum(1 for word in dutch_words if word in caption.lower())
        return 1.0 if matches >= 2 else 0.0

    elif expected == "fr":
        # French keywords
        french_words = ["nouveau", "pour", "votre", "dans", "à", "le", "la"]
        matches = sum(1 for word in french_words if word in caption.lower())
        return 1.0 if matches >= 2 else 0.0

    return 0.0

def score_brand(self, caption: str, brand: str) -> float:
    """Check brand mention and consistency."""
    # Brand must be mentioned
    if brand.lower() not in caption.lower():
        return 0.0

    # Brand should be capitalized correctly
    if brand in caption:
        return 1.0
    else:
        return 0.7  # Mentioned but not capitalized

def score_length(self, caption: str) -> float:
    """Check caption length appropriateness."""
    length = len(caption)

    if 50 <= length <= 150:
        return 1.0  # Ideal length
    elif 30 <= length < 50 or 150 < length <= 200:
        return 0.7  # Acceptable
    else:
        return 0.3  # Too short or too long

def score_engagement(self, caption: str) -> float:
    """Check engagement potential."""
    score = 0.0

    # Emoji presence (positive)
    emoji_count = sum(1 for char in caption if ord(char) > 127)
    if emoji_count >= 2:
        score += 0.5

    # Call-to-action words
    cta_words = ["shop", "discover", "check", "new", "limited", "shop now"]
    if any(word in caption.lower() for word in cta_words):
        score += 0.3

    # Hashtag presence
    if "#" in caption:
        score += 0.2

    return min(score, 1.0)
```

### Cost Efficiency Evaluator

**File**: `evaluation/evaluators/cost_efficiency_eval.py`

**Tracks**:
- Token usage (prompt, completion, embedding)
- API costs in USD
- Execution latency
- Efficiency score (value per dollar)

```python
class CostEfficiencyEvaluator:
    def __init__(self):
        self.tracker = ExecutionTracker()

    async def evaluate_cost(self, agent_execution_fn, **kwargs):
        """Track cost and performance for agent execution."""

        start_time = time.time()

        # Run agent with tracking
        result = await agent_execution_fn(**kwargs)

        latency = time.time() - start_time

        # Calculate costs
        costs = self.tracker.calculate_costs()

        return CostReport(
            latency_seconds=latency,
            prompt_tokens=self.tracker.prompt_tokens,
            completion_tokens=self.tracker.completion_tokens,
            embedding_tokens=self.tracker.embedding_tokens,
            total_cost_usd=costs['total'],
            cost_per_token=costs['total'] / max(1, costs['total_tokens']),
            tokens_per_second=costs['total_tokens'] / max(0.001, latency)
        )


class ExecutionTracker:
    """Track LLM API usage during execution."""

    def __init__(self):
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.embedding_tokens = 0

    def record_llm_call(self, prompt_tokens: int, completion_tokens: int):
        """Record Claude API call."""
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens

    def record_embedding_call(self, tokens: int):
        """Record OpenAI embedding call."""
        self.embedding_tokens += tokens

    def calculate_costs(self) -> Dict[str, float]:
        """Calculate total cost in USD."""
        # Claude Opus 4.5 pricing
        prompt_cost = self.prompt_tokens * (15.00 / 1_000_000)
        completion_cost = self.completion_tokens * (75.00 / 1_000_000)

        # OpenAI text-embedding-3-small pricing
        embedding_cost = self.embedding_tokens * (0.02 / 1_000_000)

        total_cost = prompt_cost + completion_cost + embedding_cost
        total_tokens = self.prompt_tokens + self.completion_tokens + self.embedding_tokens

        return {
            'prompt_cost': prompt_cost,
            'completion_cost': completion_cost,
            'embedding_cost': embedding_cost,
            'total': total_cost,
            'total_tokens': total_tokens
        }
```

---

## Benchmark Suites

Benchmark suites run evaluators as pytest tests.

### Invoice Accuracy Benchmark

**File**: `evaluation/benchmarks/test_invoice_accuracy.py`

```python
import pytest
from langgraph_agents import InvoiceMatcherGraph
from evaluation.evaluators import InvoiceMatcherEvaluator


@pytest.fixture(scope="module")
async def invoice_matcher():
    """Create and initialize invoice matcher."""
    graph = InvoiceMatcherGraph()
    await graph.initialize()
    yield graph
    await graph.close()


@pytest.fixture(scope="module")
async def evaluator():
    """Create evaluator with golden dataset."""
    return InvoiceMatcherEvaluator(
        dataset_path="evaluation/test_datasets/invoice_matches.json"
    )


@pytest.mark.asyncio
async def test_full_accuracy_benchmark(invoice_matcher, evaluator):
    """Test overall invoice matching accuracy."""
    # Run evaluation
    results = await evaluator.evaluate(invoice_matcher)
    metrics = evaluator.get_metrics()

    # Assert targets
    assert metrics['overall_accuracy'] >= 0.90, \
        f"Accuracy {metrics['overall_accuracy']:.1%} below target 90%"

    assert metrics['error_count'] == 0, \
        f"Found {metrics['error_count']} errors during evaluation"

    print(f"✅ Accuracy: {metrics['overall_accuracy']:.1%}")
    print(f"✅ Decision accuracy: {metrics['decision_accuracy']:.1%}")
    print(f"✅ Avg latency: {metrics['avg_latency_seconds']:.2f}s")


@pytest.mark.asyncio
async def test_accuracy_by_difficulty(invoice_matcher, evaluator):
    """Test accuracy broken down by difficulty level."""
    results = await evaluator.evaluate(invoice_matcher)

    # Group by difficulty
    by_difficulty = {}
    for result in results:
        diff = result.difficulty
        if diff not in by_difficulty:
            by_difficulty[diff] = {'total': 0, 'correct': 0}

        by_difficulty[diff]['total'] += 1
        if result.correct:
            by_difficulty[diff]['correct'] += 1

    # Calculate accuracy per difficulty
    for diff, stats in by_difficulty.items():
        accuracy = stats['correct'] / stats['total']
        print(f"{diff}: {accuracy:.1%}")

        # Targets
        if diff == "easy":
            assert accuracy >= 0.95, f"Easy cases: {accuracy:.1%} < 95%"
        elif diff == "medium":
            assert accuracy >= 0.85, f"Medium cases: {accuracy:.1%} < 85%"
        elif diff == "hard":
            assert accuracy >= 0.70, f"Hard cases: {accuracy:.1%} < 70%"


@pytest.mark.asyncio
async def test_confidence_calibration(invoice_matcher, evaluator):
    """Test if confidence scores correlate with accuracy."""
    results = await evaluator.evaluate(invoice_matcher)

    # Group by confidence bins
    bins = {
        "high (>0.9)": [],
        "medium (0.7-0.9)": [],
        "low (<0.7)": []
    }

    for result in results:
        if not result.actual:
            continue

        confidence = result.actual['confidence']
        if confidence >= 0.9:
            bins["high (>0.9)"].append(result.correct)
        elif confidence >= 0.7:
            bins["medium (0.7-0.9)"].append(result.correct)
        else:
            bins["low (<0.7)"].append(result.correct)

    # High confidence should have high accuracy
    high_accuracy = sum(bins["high (>0.9)"]) / len(bins["high (>0.9)"])
    assert high_accuracy >= 0.95, \
        f"High confidence accuracy {high_accuracy:.1%} < 95%"

    print(f"High confidence accuracy: {high_accuracy:.1%}")


@pytest.mark.asyncio
async def test_cost_efficiency(invoice_matcher, evaluator):
    """Test cost per execution is within budget."""
    from evaluation.evaluators import CostEfficiencyEvaluator

    cost_eval = CostEfficiencyEvaluator()

    # Run on sample test case
    test_case = evaluator.dataset['test_cases'][0]

    report = await cost_eval.evaluate_cost(
        invoice_matcher.match,
        transaction=test_case['input']['transaction'],
        invoices=test_case['input']['invoices']
    )

    # Assert cost target
    assert report.total_cost_usd < 0.05, \
        f"Cost {report.total_cost_usd:.4f} exceeds $0.05 target"

    print(f"✅ Cost: ${report.total_cost_usd:.4f}")
    print(f"✅ Latency: {report.latency_seconds:.2f}s")
```

### Running Benchmarks

```bash
# Run all benchmarks
pytest evaluation/benchmarks/ -v

# Run specific benchmark
pytest evaluation/benchmarks/test_invoice_accuracy.py -v

# Run with coverage
pytest evaluation/benchmarks/ --cov=langgraph_agents --cov-report=html

# Run and save results
pytest evaluation/benchmarks/ --json-report --json-report-file=results.json
```

---

## Braintrust Integration

Braintrust provides experiment tracking and A/B testing (optional).

### Setup

```python
# evaluation/braintrust_integration.py
import braintrust
import os


class BraintrustLogger:
    """Log evaluations to Braintrust for tracking."""

    def __init__(self, project_name: str = "agent-runner"):
        self.project_name = project_name
        self.api_key = os.getenv("BRAINTRUST_API_KEY")
        self.experiment = None

    async def start_experiment(self, name: str, metadata: Dict = None):
        """Start a new experiment."""
        self.experiment = braintrust.init(
            project=self.project_name,
            experiment=name,
            metadata=metadata or {}
        )

    async def log_evaluation(
        self,
        name: str,
        input: Dict,
        output: Dict,
        expected: Dict,
        scores: Dict[str, float]
    ):
        """Log a single evaluation result."""
        self.experiment.log(
            name=name,
            input=input,
            output=output,
            expected=expected,
            scores=scores
        )

    async def finalize(self):
        """Finalize experiment and upload results."""
        summary = self.experiment.summarize()
        print(f"Experiment complete: {summary}")
        return summary
```

### Usage

```python
# Run evaluation with Braintrust logging
from evaluation.braintrust_integration import BraintrustLogger

logger = BraintrustLogger()
await logger.start_experiment(
    name="invoice-matcher-v2",
    metadata={"version": "2.0", "model": "claude-opus-4.5"}
)

evaluator = InvoiceMatcherEvaluator(...)
results = await evaluator.evaluate(invoice_matcher)

for result in results:
    await logger.log_evaluation(
        name=result.test_case_id,
        input=result.test_case_input,
        output=result.actual,
        expected=result.expected,
        scores={
            "correct": 1.0 if result.correct else 0.0,
            "confidence": result.actual['confidence'] if result.actual else 0.0
        }
    )

summary = await logger.finalize()
```

### A/B Testing

```python
# Compare two versions
async def ab_test(version_a: InvoiceMatcherGraph, version_b: InvoiceMatcherGraph):
    """Compare two versions of invoice matcher."""

    evaluator = InvoiceMatcherEvaluator(...)

    # Test version A
    logger_a = BraintrustLogger()
    await logger_a.start_experiment("invoice-matcher-baseline")
    results_a = await evaluator.evaluate(version_a)
    metrics_a = evaluator.get_metrics()
    await logger_a.finalize()

    # Test version B
    logger_b = BraintrustLogger()
    await logger_b.start_experiment("invoice-matcher-improved")
    results_b = await evaluator.evaluate(version_b)
    metrics_b = evaluator.get_metrics()
    await logger_b.finalize()

    # Compare
    print(f"Baseline accuracy: {metrics_a['overall_accuracy']:.1%}")
    print(f"Improved accuracy: {metrics_b['overall_accuracy']:.1%}")

    improvement = metrics_b['overall_accuracy'] - metrics_a['overall_accuracy']
    print(f"Improvement: {improvement:+.1%}")
```

---

## CI/CD Integration

### GitHub Actions Workflow

**File**: `.github/workflows/test.yml`

```yaml
name: Agent Evaluation

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 6 * * *'  # Daily at 6 AM UTC

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov

      - name: Run unit tests
        run: pytest tests/unit/ -v --cov=langgraph_agents

  integration-tests:
    runs-on: ubuntu-latest
    services:
      qdrant:
        image: qdrant/qdrant:v1.11.3
        ports:
          - 6333:6333

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run integration tests
        env:
          QDRANT_HOST: localhost
          QDRANT_PORT: 6333
          REDIS_HOST: localhost
          REDIS_PORT: 6379
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: pytest tests/integration/ -v

  benchmarks:
    runs-on: ubuntu-latest
    if: github.event_name == 'schedule' || contains(github.event.head_commit.message, '[benchmark]')
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run benchmarks
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          pytest evaluation/benchmarks/ -v --json-report --json-report-file=benchmark-results.json

      - name: Upload benchmark results
        uses: actions/upload-artifact@v3
        with:
          name: benchmark-results
          path: benchmark-results.json

      - name: Comment PR with results
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v6
        with:
          script: |
            const fs = require('fs');
            const results = JSON.parse(fs.readFileSync('benchmark-results.json'));

            const comment = `## 📊 Benchmark Results

            - Overall accuracy: ${results.accuracy}
            - Decision accuracy: ${results.decision_accuracy}
            - Avg latency: ${results.avg_latency}s
            - Cost per execution: $${results.cost_per_execution}

            ${results.passed ? '✅ All benchmarks passed!' : '❌ Some benchmarks failed'}
            `;

            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: comment
            });
```

---

## Metrics and Targets

### Evaluation Targets

| Metric | Target | Alert If | Critical If |
|--------|--------|----------|-------------|
| Invoice matching accuracy | ≥90% | <85% | <80% |
| Caption quality score | ≥0.80 | <0.70 | <0.60 |
| False positive rate | ≤5% | >10% | >15% |
| Avg latency | <5s | >7s | >10s |
| Cost per execution | <$0.05 | >$0.10 | >$0.15 |
| Error rate | 0% | >2% | >5% |

### Tracking Metrics Over Time

```python
# scripts/track_metrics.py
async def track_metrics_over_time():
    """Track how metrics change over time."""

    # Run evaluation
    evaluator = InvoiceMatcherEvaluator(...)
    results = await evaluator.evaluate(invoice_matcher)
    metrics = evaluator.get_metrics()

    # Save to database
    await db.execute("""
        INSERT INTO evaluation_metrics (
            date, agent_name, accuracy, latency, cost
        ) VALUES ($1, $2, $3, $4, $5)
    """, datetime.now(), "invoice_matcher",
        metrics['overall_accuracy'],
        metrics['avg_latency_seconds'],
        0.03  # calculated cost
    )

    # Query trends
    trends = await db.query("""
        SELECT date, accuracy
        FROM evaluation_metrics
        WHERE agent_name = 'invoice_matcher'
        AND date > NOW() - INTERVAL '30 days'
        ORDER BY date
    """)

    # Check for regressions
    if len(trends) >= 2:
        latest = trends[-1]['accuracy']
        previous = trends[-2]['accuracy']

        if latest < previous - 0.05:  # 5% drop
            print(f"⚠️ Accuracy regression detected: {previous:.1%} → {latest:.1%}")
```

---

## Running Evaluations

### Local Development

```bash
# Run all evaluations
python -m pytest evaluation/benchmarks/ -v

# Run specific evaluator
python -m pytest evaluation/benchmarks/test_invoice_accuracy.py::test_full_accuracy_benchmark -v

# Run with detailed output
python -m pytest evaluation/benchmarks/ -v -s

# Save results to file
python -m pytest evaluation/benchmarks/ --json-report --json-report-file=eval-results.json
```

### Production Monitoring

```python
# scripts/scheduled_evaluation.py
"""Run evaluations on schedule (cron job)."""

import asyncio
from evaluation.evaluators import InvoiceMatcherEvaluator
from langgraph_agents import InvoiceMatcherGraph


async def run_scheduled_evaluation():
    """Run evaluation and alert if metrics drop."""

    # Initialize
    graph = InvoiceMatcherGraph()
    await graph.initialize()

    evaluator = InvoiceMatcherEvaluator(
        dataset_path="evaluation/test_datasets/invoice_matches.json"
    )

    # Run evaluation
    results = await evaluator.evaluate(graph)
    metrics = evaluator.get_metrics()

    # Check thresholds
    if metrics['overall_accuracy'] < 0.90:
        await send_alert(
            severity="warning",
            message=f"Invoice matcher accuracy dropped to {metrics['overall_accuracy']:.1%}"
        )

    if metrics['overall_accuracy'] < 0.80:
        await send_alert(
            severity="critical",
            message=f"Invoice matcher accuracy critically low: {metrics['overall_accuracy']:.1%}"
        )

    # Log metrics
    print(f"Evaluation complete: {metrics['overall_accuracy']:.1%} accuracy")

    await graph.close()


if __name__ == "__main__":
    asyncio.run(run_scheduled_evaluation())
```

**Cron job** (runs daily at 6 AM):

```bash
0 6 * * * cd /app && python scripts/scheduled_evaluation.py
```

---

## Interpreting Results

### Reading Evaluation Reports

```python
# Example evaluation report
{
  "overall_accuracy": 0.92,           # 92% of test cases correct
  "decision_accuracy": 0.95,          # 95% of decision types correct
  "false_positive_rate": 0.03,        # 3% incorrect matches
  "false_negative_rate": 0.05,        # 5% missed matches
  "avg_latency_seconds": 2.3,         # Avg 2.3s per execution
  "p95_latency_seconds": 4.1,         # 95th percentile 4.1s
  "total_test_cases": 10,
  "correct_count": 9,
  "error_count": 0
}
```

### Analysis

**High Overall Accuracy (92%)** ✅
- Agent performs well on golden dataset
- Above 90% target
- Safe to deploy

**High Decision Accuracy (95%)** ✅
- Confidence thresholds well-calibrated
- Correctly routes to auto/review/no-match

**Low False Positive Rate (3%)** ✅
- Rarely matches incorrectly
- Low risk of bad matches

**Moderate False Negative Rate (5%)** ⚠️
- Missing 5% of valid matches
- Could improve with better memory search
- Action: Review missed cases, improve prompts

**Good Latency (2.3s avg, 4.1s p95)** ✅
- Below 5s target
- User experience acceptable

### Improving Low Scores

**If accuracy < 90%**:

1. **Review failed test cases**
   ```python
   failed = [r for r in results if not r.correct]
   for result in failed:
       print(f"Failed: {result.test_case_id}")
       print(f"Expected: {result.expected}")
       print(f"Actual: {result.actual}")
   ```

2. **Analyze patterns**
   - Are failures concentrated in specific difficulty level?
   - Do failures have common characteristics?
   - Is memory search returning relevant results?

3. **Iterate on improvements**
   - Improve prompts
   - Adjust confidence thresholds
   - Enhance memory search queries
   - Add more training data

4. **Re-evaluate**
   ```python
   # After improvements
   new_results = await evaluator.evaluate(improved_graph)
   new_metrics = evaluator.get_metrics()

   improvement = new_metrics['overall_accuracy'] - old_metrics['overall_accuracy']
   print(f"Improvement: {improvement:+.1%}")
   ```

---

## Related Documentation

- [System Architecture](./ARCHITECTURE.md)
- [Memory Layer](./MEMORY.md)
- [LangGraph Patterns](./LANGGRAPH.md)
- [Braintrust Docs](https://www.braintrust.dev/docs)
- [pytest Documentation](https://docs.pytest.org/)

---

**Maintained by**: Agent Platform Team
**Contact**: platform@yourdomain.com
**Last Updated**: 2026-01-08
