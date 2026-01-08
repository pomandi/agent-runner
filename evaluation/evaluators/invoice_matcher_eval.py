"""
Invoice Matcher Evaluator
==========================

Measures accuracy of invoice matching against golden dataset.

Metrics:
- Exact match accuracy (invoice_id matches expected)
- Decision type accuracy (auto_match, human_review, no_match)
- Confidence calibration (predicted confidence vs actual accuracy)
- False positive rate
- False negative rate
"""

import json
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Single match evaluation result."""
    test_case_id: str
    expected_invoice_id: Optional[int]
    predicted_invoice_id: Optional[int]
    expected_decision: str
    predicted_decision: str
    expected_confidence: float
    predicted_confidence: float
    is_correct: bool
    is_decision_correct: bool
    confidence_error: float
    difficulty: str
    tags: List[str]


class InvoiceMatcherEvaluator:
    """
    Evaluator for invoice matching accuracy.

    Usage:
        evaluator = InvoiceMatcherEvaluator()
        await evaluator.load_dataset()
        results = await evaluator.evaluate(graph)
        print(evaluator.get_metrics())
    """

    def __init__(self, dataset_path: Optional[str] = None):
        """
        Initialize evaluator.

        Args:
            dataset_path: Path to golden dataset JSON (optional)
        """
        if dataset_path is None:
            # Default to project test datasets
            base_dir = os.path.dirname(os.path.dirname(__file__))
            dataset_path = os.path.join(base_dir, "test_datasets", "invoice_matches.json")

        self.dataset_path = dataset_path
        self.dataset: Optional[Dict[str, Any]] = None
        self.results: List[MatchResult] = []

    def load_dataset(self) -> Dict[str, Any]:
        """
        Load golden dataset from JSON file.

        Returns:
            Dataset dict with test cases
        """
        with open(self.dataset_path, 'r') as f:
            self.dataset = json.load(f)

        logger.info(
            f"Loaded dataset: {self.dataset['dataset_name']} "
            f"with {len(self.dataset['test_cases'])} test cases"
        )

        return self.dataset

    async def evaluate(self, graph) -> List[MatchResult]:
        """
        Evaluate invoice matcher graph against dataset.

        Args:
            graph: InvoiceMatcherGraph instance

        Returns:
            List of match results
        """
        if self.dataset is None:
            self.load_dataset()

        self.results = []

        for test_case in self.dataset['test_cases']:
            logger.info(f"Evaluating test case: {test_case['id']}")

            # Run graph
            result = await graph.match(
                transaction=test_case['transaction'],
                invoices=test_case['invoices']
            )

            # Extract expected vs predicted
            expected = test_case['expected_result']
            predicted_invoice_id = result.get('invoice_id')
            expected_invoice_id = expected['invoice_id']

            # Determine if match is correct
            is_correct = predicted_invoice_id == expected_invoice_id

            # Check decision type
            is_decision_correct = result['decision_type'] == expected['decision_type']

            # Calculate confidence error
            confidence_error = abs(result['confidence'] - expected['confidence'])

            # Create result
            match_result = MatchResult(
                test_case_id=test_case['id'],
                expected_invoice_id=expected_invoice_id,
                predicted_invoice_id=predicted_invoice_id,
                expected_decision=expected['decision_type'],
                predicted_decision=result['decision_type'],
                expected_confidence=expected['confidence'],
                predicted_confidence=result['confidence'],
                is_correct=is_correct,
                is_decision_correct=is_decision_correct,
                confidence_error=confidence_error,
                difficulty=test_case['difficulty'],
                tags=test_case['tags']
            )

            self.results.append(match_result)

            logger.info(
                f"Test {test_case['id']}: "
                f"{'✅ PASS' if is_correct else '❌ FAIL'} "
                f"(predicted: {predicted_invoice_id}, expected: {expected_invoice_id})"
            )

        return self.results

    def get_metrics(self) -> Dict[str, Any]:
        """
        Calculate evaluation metrics.

        Returns:
            Dict with accuracy metrics
        """
        if not self.results:
            return {"error": "No results to evaluate"}

        total = len(self.results)
        correct = sum(1 for r in self.results if r.is_correct)
        decision_correct = sum(1 for r in self.results if r.is_decision_correct)

        # Calculate by difficulty
        by_difficulty = {}
        for difficulty in ['easy', 'medium', 'hard']:
            diff_results = [r for r in self.results if r.difficulty == difficulty]
            if diff_results:
                by_difficulty[difficulty] = {
                    'count': len(diff_results),
                    'accuracy': sum(1 for r in diff_results if r.is_correct) / len(diff_results)
                }

        # False positives (predicted match when should not match)
        false_positives = sum(
            1 for r in self.results
            if r.expected_invoice_id is None and r.predicted_invoice_id is not None
        )

        # False negatives (predicted no match when should match)
        false_negatives = sum(
            1 for r in self.results
            if r.expected_invoice_id is not None and r.predicted_invoice_id is None
        )

        # Average confidence error
        avg_confidence_error = sum(r.confidence_error for r in self.results) / total

        metrics = {
            'overall_accuracy': correct / total,
            'decision_accuracy': decision_correct / total,
            'total_cases': total,
            'correct_matches': correct,
            'incorrect_matches': total - correct,
            'false_positive_rate': false_positives / total,
            'false_negative_rate': false_negatives / total,
            'avg_confidence_error': avg_confidence_error,
            'by_difficulty': by_difficulty,
            'pass_rate': f"{correct}/{total} ({correct/total*100:.1f}%)"
        }

        return metrics

    def get_failures(self) -> List[MatchResult]:
        """
        Get all failed test cases.

        Returns:
            List of failed match results
        """
        return [r for r in self.results if not r.is_correct]

    def print_report(self):
        """Print evaluation report to console."""
        metrics = self.get_metrics()

        print("\n" + "=" * 60)
        print("INVOICE MATCHER EVALUATION REPORT")
        print("=" * 60)
        print(f"\nDataset: {self.dataset['dataset_name']}")
        print(f"Version: {self.dataset['version']}")
        print(f"Total test cases: {metrics['total_cases']}")
        print("\n--- ACCURACY METRICS ---")
        print(f"Overall accuracy: {metrics['overall_accuracy']:.2%}")
        print(f"Decision accuracy: {metrics['decision_accuracy']:.2%}")
        print(f"Pass rate: {metrics['pass_rate']}")
        print(f"\nFalse positive rate: {metrics['false_positive_rate']:.2%}")
        print(f"False negative rate: {metrics['false_negative_rate']:.2%}")
        print(f"Avg confidence error: {metrics['avg_confidence_error']:.3f}")

        print("\n--- BY DIFFICULTY ---")
        for difficulty, stats in metrics['by_difficulty'].items():
            print(f"{difficulty.capitalize()}: {stats['accuracy']:.2%} ({stats['count']} cases)")

        # Show failures
        failures = self.get_failures()
        if failures:
            print(f"\n--- FAILURES ({len(failures)}) ---")
            for fail in failures:
                print(f"❌ {fail.test_case_id}")
                print(f"   Expected: invoice_id={fail.expected_invoice_id}, decision={fail.expected_decision}")
                print(f"   Predicted: invoice_id={fail.predicted_invoice_id}, decision={fail.predicted_decision}")
                print(f"   Tags: {', '.join(fail.tags)}")
        else:
            print("\n✅ ALL TESTS PASSED!")

        print("=" * 60 + "\n")

    def export_results(self, output_path: str):
        """
        Export results to JSON file.

        Args:
            output_path: Path to output JSON file
        """
        data = {
            'dataset': self.dataset['dataset_name'],
            'metrics': self.get_metrics(),
            'results': [
                {
                    'test_case_id': r.test_case_id,
                    'expected_invoice_id': r.expected_invoice_id,
                    'predicted_invoice_id': r.predicted_invoice_id,
                    'expected_decision': r.expected_decision,
                    'predicted_decision': r.predicted_decision,
                    'expected_confidence': r.expected_confidence,
                    'predicted_confidence': r.predicted_confidence,
                    'is_correct': r.is_correct,
                    'is_decision_correct': r.is_decision_correct,
                    'confidence_error': r.confidence_error,
                    'difficulty': r.difficulty,
                    'tags': r.tags
                }
                for r in self.results
            ]
        }

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Results exported to {output_path}")
