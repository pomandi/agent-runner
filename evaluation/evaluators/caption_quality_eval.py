"""
Caption Quality Evaluator
==========================

Measures quality of social media captions against golden dataset.

Metrics:
- Language accuracy (correct language for brand)
- Brand consistency (brand name mentioned, brand voice)
- Length appropriateness (50-150 chars ideal)
- Engagement potential (emojis, CTA, hashtags)
- Originality (not too similar to recent posts)
- Overall quality score
"""

import json
import os
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class CaptionResult:
    """Single caption evaluation result."""
    test_case_id: str
    brand: str
    language: str
    caption: str
    expected_overall_quality: float
    predicted_overall_quality: float
    language_score: float
    brand_score: float
    length_score: float
    engagement_score: float
    quality_error: float
    tags: List[str]
    issues: List[str]


class CaptionQualityEvaluator:
    """
    Evaluator for caption quality assessment.

    Usage:
        evaluator = CaptionQualityEvaluator()
        evaluator.load_dataset()
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
            dataset_path = os.path.join(base_dir, "test_datasets", "caption_samples.json")

        self.dataset_path = dataset_path
        self.dataset: Optional[Dict[str, Any]] = None
        self.results: List[CaptionResult] = []

        # Language keywords for detection
        self.dutch_keywords = ['nieuw', 'voor', 'jouw', 'binnen', 'deze', 'onze', 'bij', 'nu', 'het', 'de']
        self.french_keywords = ['nouveau', 'pour', 'votre', 'nouveau', 'notre', 'chez', 'maintenant', 'le', 'la']

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

    def score_language(self, caption: str, expected_language: str) -> float:
        """
        Score language accuracy.

        Args:
            caption: Caption text
            expected_language: Expected language code (nl/fr)

        Returns:
            Score 0-1
        """
        caption_lower = caption.lower()

        if expected_language == 'nl':
            # Check for Dutch keywords
            dutch_matches = sum(1 for word in self.dutch_keywords if word in caption_lower)
            # Check for French keywords (should be absent)
            french_matches = sum(1 for word in self.french_keywords if word in caption_lower)

            if french_matches > 0:
                return 0.0  # Wrong language detected

            if dutch_matches >= 2:
                return 1.0
            elif dutch_matches == 1:
                return 0.7
            else:
                return 0.3

        elif expected_language == 'fr':
            # Check for French keywords
            french_matches = sum(1 for word in self.french_keywords if word in caption_lower)
            # Check for Dutch keywords (should be absent)
            dutch_matches = sum(1 for word in self.dutch_keywords if word in caption_lower)

            if dutch_matches > 0:
                return 0.0  # Wrong language detected

            if french_matches >= 2:
                return 1.0
            elif french_matches == 1:
                return 0.7
            else:
                return 0.3

        return 0.5

    def score_brand(self, caption: str, brand: str) -> float:
        """
        Score brand consistency.

        Args:
            caption: Caption text
            brand: Brand name (pomandi/costume)

        Returns:
            Score 0-1
        """
        caption_lower = caption.lower()
        brand_lower = brand.lower()

        # Check if brand name is mentioned
        if brand_lower in caption_lower:
            brand_score = 1.0
        else:
            brand_score = 0.0

        # Check for hashtag with brand (bonus)
        if f"#{brand_lower}" in caption_lower:
            brand_score = min(1.0, brand_score + 0.2)

        return brand_score

    def score_length(self, caption: str) -> float:
        """
        Score length appropriateness.

        Args:
            caption: Caption text

        Returns:
            Score 0-1
        """
        length = len(caption)

        # Ideal range: 50-150 characters
        if 50 <= length <= 150:
            return 1.0
        elif 30 <= length < 50:
            return 0.8
        elif 150 < length <= 200:
            return 0.7
        elif length < 30:
            return 0.3
        else:  # > 200
            return 0.5

    def score_engagement(self, caption: str) -> float:
        """
        Score engagement potential.

        Args:
            caption: Caption text

        Returns:
            Score 0-1
        """
        score = 0.0

        # Check for emojis
        emoji_count = sum(1 for char in caption if ord(char) > 127)
        if emoji_count >= 2:
            score += 0.4
        elif emoji_count == 1:
            score += 0.2

        # Check for call-to-action words
        cta_words = ['shop', 'koop', 'bestel', 'ontdek', 'découvrez', 'achetez']
        if any(word in caption.lower() for word in cta_words):
            score += 0.3

        # Check for hashtags
        hashtag_count = caption.count('#')
        if 2 <= hashtag_count <= 5:
            score += 0.3
        elif hashtag_count == 1:
            score += 0.2
        elif hashtag_count > 10:
            score -= 0.2  # Too many hashtags

        return min(1.0, score)

    def calculate_overall_quality(
        self,
        language_score: float,
        brand_score: float,
        length_score: float,
        engagement_score: float
    ) -> float:
        """
        Calculate overall quality score (weighted average).

        Args:
            language_score: Language accuracy score
            brand_score: Brand consistency score
            length_score: Length appropriateness score
            engagement_score: Engagement potential score

        Returns:
            Overall quality score 0-1
        """
        # Weights
        weights = {
            'language': 0.35,
            'brand': 0.30,
            'length': 0.15,
            'engagement': 0.20
        }

        overall = (
            language_score * weights['language'] +
            brand_score * weights['brand'] +
            length_score * weights['length'] +
            engagement_score * weights['engagement']
        )

        return overall

    async def evaluate(self, graph) -> List[CaptionResult]:
        """
        Evaluate caption quality against dataset.

        Args:
            graph: FeedPublisherGraph instance

        Returns:
            List of caption results
        """
        if self.dataset is None:
            self.load_dataset()

        self.results = []

        for test_case in self.dataset['test_cases']:
            logger.info(f"Evaluating test case: {test_case['id']}")

            # Score the caption
            caption = test_case['caption']
            brand = test_case['brand']
            language = test_case['language']

            language_score = self.score_language(caption, language)
            brand_score = self.score_brand(caption, brand)
            length_score = self.score_length(caption)
            engagement_score = self.score_engagement(caption)

            predicted_quality = self.calculate_overall_quality(
                language_score, brand_score, length_score, engagement_score
            )

            expected_quality = test_case['expected_scores']['overall_quality']
            quality_error = abs(predicted_quality - expected_quality)

            # Identify issues
            issues = []
            if language_score < 0.7:
                issues.append("Language issue")
            if brand_score < 0.5:
                issues.append("Missing brand mention")
            if length_score < 0.5:
                issues.append("Length inappropriate")
            if engagement_score < 0.5:
                issues.append("Low engagement potential")

            # Create result
            caption_result = CaptionResult(
                test_case_id=test_case['id'],
                brand=brand,
                language=language,
                caption=caption,
                expected_overall_quality=expected_quality,
                predicted_overall_quality=predicted_quality,
                language_score=language_score,
                brand_score=brand_score,
                length_score=length_score,
                engagement_score=engagement_score,
                quality_error=quality_error,
                tags=test_case['tags'],
                issues=issues
            )

            self.results.append(caption_result)

            logger.info(
                f"Test {test_case['id']}: "
                f"Quality={predicted_quality:.2%} "
                f"(expected: {expected_quality:.2%}, error: {quality_error:.3f})"
            )

        return self.results

    def get_metrics(self) -> Dict[str, Any]:
        """
        Calculate evaluation metrics.

        Returns:
            Dict with quality metrics
        """
        if not self.results:
            return {"error": "No results to evaluate"}

        total = len(self.results)

        # Average scores
        avg_language = sum(r.language_score for r in self.results) / total
        avg_brand = sum(r.brand_score for r in self.results) / total
        avg_length = sum(r.length_score for r in self.results) / total
        avg_engagement = sum(r.engagement_score for r in self.results) / total
        avg_overall = sum(r.predicted_overall_quality for r in self.results) / total

        # Average error
        avg_quality_error = sum(r.quality_error for r in self.results) / total

        # Quality distribution
        high_quality = sum(1 for r in self.results if r.predicted_overall_quality >= 0.85)
        medium_quality = sum(1 for r in self.results if 0.70 <= r.predicted_overall_quality < 0.85)
        low_quality = sum(1 for r in self.results if r.predicted_overall_quality < 0.70)

        # Most common issues
        all_issues = []
        for r in self.results:
            all_issues.extend(r.issues)
        issue_counts = {issue: all_issues.count(issue) for issue in set(all_issues)}

        metrics = {
            'avg_language_score': avg_language,
            'avg_brand_score': avg_brand,
            'avg_length_score': avg_length,
            'avg_engagement_score': avg_engagement,
            'avg_overall_quality': avg_overall,
            'avg_quality_error': avg_quality_error,
            'total_cases': total,
            'quality_distribution': {
                'high_quality': f"{high_quality}/{total} ({high_quality/total*100:.1f}%)",
                'medium_quality': f"{medium_quality}/{total} ({medium_quality/total*100:.1f}%)",
                'low_quality': f"{low_quality}/{total} ({low_quality/total*100:.1f}%)"
            },
            'common_issues': issue_counts
        }

        return metrics

    def print_report(self):
        """Print evaluation report to console."""
        metrics = self.get_metrics()

        print("\n" + "=" * 60)
        print("CAPTION QUALITY EVALUATION REPORT")
        print("=" * 60)
        print(f"\nDataset: {self.dataset['dataset_name']}")
        print(f"Version: {self.dataset['version']}")
        print(f"Total test cases: {metrics['total_cases']}")
        print("\n--- AVERAGE SCORES ---")
        print(f"Overall quality: {metrics['avg_overall_quality']:.2%}")
        print(f"Language accuracy: {metrics['avg_language_score']:.2%}")
        print(f"Brand consistency: {metrics['avg_brand_score']:.2%}")
        print(f"Length appropriateness: {metrics['avg_length_score']:.2%}")
        print(f"Engagement potential: {metrics['avg_engagement_score']:.2%}")
        print(f"\nAvg quality error: {metrics['avg_quality_error']:.3f}")

        print("\n--- QUALITY DISTRIBUTION ---")
        for quality_level, count in metrics['quality_distribution'].items():
            print(f"{quality_level.replace('_', ' ').title()}: {count}")

        print("\n--- COMMON ISSUES ---")
        for issue, count in sorted(metrics['common_issues'].items(), key=lambda x: x[1], reverse=True):
            print(f"- {issue}: {count} cases")

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
                    'brand': r.brand,
                    'language': r.language,
                    'caption': r.caption,
                    'expected_overall_quality': r.expected_overall_quality,
                    'predicted_overall_quality': r.predicted_overall_quality,
                    'language_score': r.language_score,
                    'brand_score': r.brand_score,
                    'length_score': r.length_score,
                    'engagement_score': r.engagement_score,
                    'quality_error': r.quality_error,
                    'tags': r.tags,
                    'issues': r.issues
                }
                for r in self.results
            ]
        }

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Results exported to {output_path}")
