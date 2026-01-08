"""
Caption Quality Benchmark
==========================

Comprehensive test suite for caption quality evaluation using golden dataset.

Run with:
    pytest evaluation/benchmarks/test_caption_quality.py -v

Or run as script:
    python evaluation/benchmarks/test_caption_quality.py
"""

import pytest
import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from evaluation.evaluators.caption_quality_eval import CaptionQualityEvaluator


pytestmark = pytest.mark.asyncio


class TestCaptionQualityBenchmark:
    """Benchmark test suite for caption quality."""

    def test_language_accuracy_evaluation(self):
        """
        Test language accuracy scoring.

        Target: >= 85% average language accuracy
        """
        evaluator = CaptionQualityEvaluator()
        evaluator.load_dataset()

        # Score all captions (without graph execution, just scoring logic)
        evaluator.results = []
        for test_case in evaluator.dataset['test_cases']:
            caption = test_case['caption']
            brand = test_case['brand']
            language = test_case['language']

            language_score = evaluator.score_language(caption, language)
            brand_score = evaluator.score_brand(caption, brand)
            length_score = evaluator.score_length(caption)
            engagement_score = evaluator.score_engagement(caption)

            predicted_quality = evaluator.calculate_overall_quality(
                language_score, brand_score, length_score, engagement_score
            )

            from evaluation.evaluators.caption_quality_eval import CaptionResult

            result = CaptionResult(
                test_case_id=test_case['id'],
                brand=brand,
                language=language,
                caption=caption,
                expected_overall_quality=test_case['expected_scores']['overall_quality'],
                predicted_overall_quality=predicted_quality,
                language_score=language_score,
                brand_score=brand_score,
                length_score=length_score,
                engagement_score=engagement_score,
                quality_error=abs(predicted_quality - test_case['expected_scores']['overall_quality']),
                tags=test_case['tags'],
                issues=[]
            )

            evaluator.results.append(result)

        metrics = evaluator.get_metrics()

        # Assert language accuracy target
        assert metrics['avg_language_score'] >= 0.85, \
            f"Language accuracy {metrics['avg_language_score']:.2%} below target 85%"

    def test_brand_consistency_evaluation(self):
        """
        Test brand consistency scoring.

        Target: >= 80% average brand consistency
        """
        evaluator = CaptionQualityEvaluator()
        evaluator.load_dataset()

        # Score all captions
        evaluator.results = []
        for test_case in evaluator.dataset['test_cases']:
            caption = test_case['caption']
            brand = test_case['brand']
            language = test_case['language']

            language_score = evaluator.score_language(caption, language)
            brand_score = evaluator.score_brand(caption, brand)
            length_score = evaluator.score_length(caption)
            engagement_score = evaluator.score_engagement(caption)

            predicted_quality = evaluator.calculate_overall_quality(
                language_score, brand_score, length_score, engagement_score
            )

            from evaluation.evaluators.caption_quality_eval import CaptionResult

            result = CaptionResult(
                test_case_id=test_case['id'],
                brand=brand,
                language=language,
                caption=caption,
                expected_overall_quality=test_case['expected_scores']['overall_quality'],
                predicted_overall_quality=predicted_quality,
                language_score=language_score,
                brand_score=brand_score,
                length_score=length_score,
                engagement_score=engagement_score,
                quality_error=abs(predicted_quality - test_case['expected_scores']['overall_quality']),
                tags=test_case['tags'],
                issues=[]
            )

            evaluator.results.append(result)

        metrics = evaluator.get_metrics()

        # Assert brand consistency target
        assert metrics['avg_brand_score'] >= 0.80, \
            f"Brand consistency {metrics['avg_brand_score']:.2%} below target 80%"

    def test_overall_quality_benchmark(self):
        """
        Test overall quality scoring accuracy.

        Target: Average quality error < 0.15
        """
        evaluator = CaptionQualityEvaluator()
        evaluator.load_dataset()

        # Score all captions
        evaluator.results = []
        for test_case in evaluator.dataset['test_cases']:
            caption = test_case['caption']
            brand = test_case['brand']
            language = test_case['language']

            language_score = evaluator.score_language(caption, language)
            brand_score = evaluator.score_brand(caption, brand)
            length_score = evaluator.score_length(caption)
            engagement_score = evaluator.score_engagement(caption)

            predicted_quality = evaluator.calculate_overall_quality(
                language_score, brand_score, length_score, engagement_score
            )

            from evaluation.evaluators.caption_quality_eval import CaptionResult

            result = CaptionResult(
                test_case_id=test_case['id'],
                brand=brand,
                language=language,
                caption=caption,
                expected_overall_quality=test_case['expected_scores']['overall_quality'],
                predicted_overall_quality=predicted_quality,
                language_score=language_score,
                brand_score=brand_score,
                length_score=length_score,
                engagement_score=engagement_score,
                quality_error=abs(predicted_quality - test_case['expected_scores']['overall_quality']),
                tags=test_case['tags'],
                issues=[]
            )

            evaluator.results.append(result)

        # Print report
        evaluator.print_report()

        metrics = evaluator.get_metrics()

        # Assert quality error target
        assert metrics['avg_quality_error'] < 0.15, \
            f"Quality error {metrics['avg_quality_error']:.3f} exceeds target 0.15"

    def test_quality_distribution(self):
        """
        Test quality distribution matches expectations.

        Target: >= 60% high or medium quality captions
        """
        evaluator = CaptionQualityEvaluator()
        evaluator.load_dataset()

        # Score all captions
        evaluator.results = []
        for test_case in evaluator.dataset['test_cases']:
            caption = test_case['caption']
            brand = test_case['brand']
            language = test_case['language']

            language_score = evaluator.score_language(caption, language)
            brand_score = evaluator.score_brand(caption, brand)
            length_score = evaluator.score_length(caption)
            engagement_score = evaluator.score_engagement(caption)

            predicted_quality = evaluator.calculate_overall_quality(
                language_score, brand_score, length_score, engagement_score
            )

            from evaluation.evaluators.caption_quality_eval import CaptionResult

            result = CaptionResult(
                test_case_id=test_case['id'],
                brand=brand,
                language=language,
                caption=caption,
                expected_overall_quality=test_case['expected_scores']['overall_quality'],
                predicted_overall_quality=predicted_quality,
                language_score=language_score,
                brand_score=brand_score,
                length_score=length_score,
                engagement_score=engagement_score,
                quality_error=abs(predicted_quality - test_case['expected_scores']['overall_quality']),
                tags=test_case['tags'],
                issues=[]
            )

            evaluator.results.append(result)

        # Check distribution
        high_medium = sum(
            1 for r in evaluator.results
            if r.predicted_overall_quality >= 0.70
        )
        total = len(evaluator.results)
        high_medium_pct = high_medium / total

        assert high_medium_pct >= 0.60, \
            f"High/medium quality rate {high_medium_pct:.2%} below target 60%"


# Script execution
def main():
    """Run benchmarks as script."""
    print("\n" + "=" * 70)
    print("CAPTION QUALITY BENCHMARK")
    print("=" * 70)

    # Run evaluation
    print("\n[1/1] Running quality benchmark...")
    evaluator = CaptionQualityEvaluator()
    evaluator.load_dataset()

    # Score all captions
    evaluator.results = []
    for test_case in evaluator.dataset['test_cases']:
        caption = test_case['caption']
        brand = test_case['brand']
        language = test_case['language']

        language_score = evaluator.score_language(caption, language)
        brand_score = evaluator.score_brand(caption, brand)
        length_score = evaluator.score_length(caption)
        engagement_score = evaluator.score_engagement(caption)

        predicted_quality = evaluator.calculate_overall_quality(
            language_score, brand_score, length_score, engagement_score
        )

        from evaluation.evaluators.caption_quality_eval import CaptionResult

        result = CaptionResult(
            test_case_id=test_case['id'],
            brand=brand,
            language=language,
            caption=caption,
            expected_overall_quality=test_case['expected_scores']['overall_quality'],
            predicted_overall_quality=predicted_quality,
            language_score=language_score,
            brand_score=brand_score,
            length_score=length_score,
            engagement_score=engagement_score,
            quality_error=abs(predicted_quality - test_case['expected_scores']['overall_quality']),
            tags=test_case['tags'],
            issues=[]
        )

        evaluator.results.append(result)

    evaluator.print_report()

    # Export results
    output_dir = os.path.join(os.path.dirname(__file__), "..", "results")
    os.makedirs(output_dir, exist_ok=True)
    evaluator.export_results(os.path.join(output_dir, "caption_quality_results.json"))

    print("\n✅ Benchmark complete! Results saved to evaluation/results/")


if __name__ == "__main__":
    main()
