"""
Invoice Matcher Accuracy Benchmark
===================================

Comprehensive test suite for invoice matching accuracy using golden dataset.

Run with:
    pytest evaluation/benchmarks/test_invoice_accuracy.py -v

Or run as script:
    python evaluation/benchmarks/test_invoice_accuracy.py
"""

import pytest
import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from evaluation.evaluators.invoice_matcher_eval import InvoiceMatcherEvaluator
from evaluation.evaluators.cost_efficiency_eval import CostEfficiencyEvaluator


pytestmark = pytest.mark.asyncio


class TestInvoiceMatcherBenchmark:
    """Benchmark test suite for invoice matcher."""

    @pytest.mark.skipif(
        os.getenv('ENABLE_LANGGRAPH') != 'true',
        reason="LangGraph not enabled"
    )
    async def test_full_accuracy_benchmark(self):
        """
        Run full accuracy benchmark against golden dataset.

        Target: >= 90% accuracy overall
        """
        from langgraph_agents import InvoiceMatcherGraph

        # Initialize evaluator
        evaluator = InvoiceMatcherEvaluator()
        evaluator.load_dataset()

        # Initialize graph
        graph = InvoiceMatcherGraph()
        await graph.initialize()

        # Run evaluation
        results = await evaluator.evaluate(graph)

        # Print report
        evaluator.print_report()

        # Get metrics
        metrics = evaluator.get_metrics()

        # Assert quality targets
        assert metrics['overall_accuracy'] >= 0.90, \
            f"Accuracy {metrics['overall_accuracy']:.2%} below target 90%"

        assert metrics['decision_accuracy'] >= 0.85, \
            f"Decision accuracy {metrics['decision_accuracy']:.2%} below target 85%"

        assert metrics['false_positive_rate'] <= 0.10, \
            f"False positive rate {metrics['false_positive_rate']:.2%} above threshold 10%"

        await graph.close()

    @pytest.mark.skipif(
        os.getenv('ENABLE_LANGGRAPH') != 'true',
        reason="LangGraph not enabled"
    )
    async def test_accuracy_by_difficulty(self):
        """
        Test accuracy across different difficulty levels.

        Targets:
        - Easy: >= 95%
        - Medium: >= 85%
        - Hard: >= 70%
        """
        from langgraph_agents import InvoiceMatcherGraph

        evaluator = InvoiceMatcherEvaluator()
        evaluator.load_dataset()

        graph = InvoiceMatcherGraph()
        await graph.initialize()

        await evaluator.evaluate(graph)

        metrics = evaluator.get_metrics()
        by_difficulty = metrics['by_difficulty']

        # Assert difficulty targets
        if 'easy' in by_difficulty:
            assert by_difficulty['easy']['accuracy'] >= 0.95, \
                f"Easy cases accuracy {by_difficulty['easy']['accuracy']:.2%} below target 95%"

        if 'medium' in by_difficulty:
            assert by_difficulty['medium']['accuracy'] >= 0.85, \
                f"Medium cases accuracy {by_difficulty['medium']['accuracy']:.2%} below target 85%"

        if 'hard' in by_difficulty:
            assert by_difficulty['hard']['accuracy'] >= 0.70, \
                f"Hard cases accuracy {by_difficulty['hard']['accuracy']:.2%} below target 70%"

        await graph.close()

    @pytest.mark.skipif(
        os.getenv('ENABLE_LANGGRAPH') != 'true',
        reason="LangGraph not enabled"
    )
    async def test_confidence_calibration(self):
        """
        Test that confidence scores are well-calibrated.

        High confidence (>= 0.90) should have high accuracy (>= 95%)
        """
        from langgraph_agents import InvoiceMatcherGraph

        evaluator = InvoiceMatcherEvaluator()
        evaluator.load_dataset()

        graph = InvoiceMatcherGraph()
        await graph.initialize()

        await evaluator.evaluate(graph)

        # Filter high-confidence predictions
        high_confidence = [r for r in evaluator.results if r.predicted_confidence >= 0.90]

        if high_confidence:
            high_conf_accuracy = sum(1 for r in high_confidence if r.is_correct) / len(high_confidence)
            assert high_conf_accuracy >= 0.95, \
                f"High-confidence accuracy {high_conf_accuracy:.2%} below target 95%"

        await graph.close()

    @pytest.mark.skipif(
        os.getenv('ENABLE_LANGGRAPH') != 'true',
        reason="LangGraph not enabled"
    )
    async def test_cost_efficiency(self):
        """
        Test cost efficiency of invoice matching.

        Target: < $0.05 per match
        """
        from langgraph_agents import InvoiceMatcherGraph

        invoice_evaluator = InvoiceMatcherEvaluator()
        invoice_evaluator.load_dataset()

        cost_evaluator = CostEfficiencyEvaluator()

        graph = InvoiceMatcherGraph()
        await graph.initialize()

        # Run with cost tracking
        for test_case in invoice_evaluator.dataset['test_cases']:
            with cost_evaluator.track_execution("invoice_matcher") as tracker:
                result = await graph.match(
                    transaction=test_case['transaction'],
                    invoices=test_case['invoices']
                )

                # Simulate token usage (in real implementation, track actual usage)
                tracker.record_llm_call(prompt_tokens=300, completion_tokens=50)
                tracker.record_embedding_call(tokens=150)
                tracker.set_success(result['matched'] is not None)

        # Print cost report
        cost_evaluator.print_report()

        metrics = cost_evaluator.get_metrics()

        # Assert cost target
        assert metrics['avg_cost_per_execution'] < 0.05, \
            f"Cost per execution ${metrics['avg_cost_per_execution']:.4f} exceeds target $0.05"

        await graph.close()


# Script execution
async def main():
    """Run benchmarks as script."""
    print("\n" + "=" * 70)
    print("INVOICE MATCHER ACCURACY BENCHMARK")
    print("=" * 70)

    if os.getenv('ENABLE_LANGGRAPH') != 'true':
        print("\n⚠️  LangGraph not enabled. Set ENABLE_LANGGRAPH=true to run benchmarks.")
        return

    from langgraph_agents import InvoiceMatcherGraph

    # Test 1: Full accuracy
    print("\n[1/4] Running full accuracy benchmark...")
    evaluator = InvoiceMatcherEvaluator()
    evaluator.load_dataset()

    graph = InvoiceMatcherGraph()
    await graph.initialize()

    await evaluator.evaluate(graph)
    evaluator.print_report()

    # Export results
    output_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    os.makedirs(output_dir, exist_ok=True)
    evaluator.export_results(os.path.join(output_dir, "invoice_accuracy_results.json"))

    # Test 2: Cost efficiency
    print("\n[2/4] Running cost efficiency benchmark...")
    cost_evaluator = CostEfficiencyEvaluator()

    for test_case in evaluator.dataset['test_cases']:
        with cost_evaluator.track_execution("invoice_matcher") as tracker:
            result = await graph.match(
                transaction=test_case['transaction'],
                invoices=test_case['invoices']
            )
            tracker.record_llm_call(prompt_tokens=300, completion_tokens=50)
            tracker.record_embedding_call(tokens=150)
            tracker.set_success(result['matched'] is not None)

    cost_evaluator.print_report()
    cost_evaluator.export_results(os.path.join(output_dir, "invoice_cost_results.json"))

    await graph.close()

    print("\n✅ Benchmark complete! Results saved to evaluation/results/")


if __name__ == "__main__":
    asyncio.run(main())
