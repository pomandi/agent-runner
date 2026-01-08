"""
Evaluation framework for agent performance measurement.

Provides:
- Custom evaluators (accuracy, quality, cost)
- Golden test datasets
- Benchmark suites
- Braintrust integration (optional)
"""

from .evaluators.invoice_matcher_eval import InvoiceMatcherEvaluator
from .evaluators.caption_quality_eval import CaptionQualityEvaluator
from .evaluators.cost_efficiency_eval import CostEfficiencyEvaluator

__all__ = [
    "InvoiceMatcherEvaluator",
    "CaptionQualityEvaluator",
    "CostEfficiencyEvaluator",
]
__version__ = "1.0.0"
