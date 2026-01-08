"""
Braintrust Integration (Optional)
===================================

Integration with Braintrust for experiment tracking, dashboards, and A/B testing.

Braintrust is a SaaS platform for AI evaluation. Free tier: 10K evals/month.
Website: https://braintrustdata.com

To use:
1. Sign up at braintrustdata.com
2. Get API key from settings
3. Set BRAINTRUST_API_KEY in .env
4. pip install braintrust

Example usage:
    from evaluation.braintrust_integration import BraintrustLogger

    logger = BraintrustLogger(project="agent-runner")

    # Log evaluation
    await logger.log_evaluation(
        name="invoice_matcher_accuracy",
        input={"transaction": ...},
        output={"matched": True, "confidence": 0.95},
        expected={"invoice_id": 101},
        scores={"accuracy": 1.0, "confidence_error": 0.05}
    )
"""

import os
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Try to import braintrust (optional dependency)
try:
    import braintrust
    BRAINTRUST_AVAILABLE = True
except ImportError:
    BRAINTRUST_AVAILABLE = False
    logger.warning("Braintrust not installed. Install with: pip install braintrust")


class BraintrustLogger:
    """
    Optional Braintrust integration for evaluation logging.

    If Braintrust is not available or not configured, methods will no-op silently.
    """

    def __init__(self, project: str = "agent-runner", experiment: Optional[str] = None):
        """
        Initialize Braintrust logger.

        Args:
            project: Braintrust project name
            experiment: Optional experiment name (auto-generated if None)
        """
        self.project = project
        self.experiment_name = experiment
        self.experiment = None
        self.enabled = False

        # Check if Braintrust is available and configured
        if not BRAINTRUST_AVAILABLE:
            logger.info("Braintrust integration disabled: library not installed")
            return

        api_key = os.getenv('BRAINTRUST_API_KEY')
        if not api_key:
            logger.info("Braintrust integration disabled: BRAINTRUST_API_KEY not set")
            return

        try:
            # Initialize experiment
            self.experiment = braintrust.init(
                project=self.project,
                experiment=self.experiment_name
            )
            self.enabled = True
            logger.info(f"Braintrust experiment initialized: {self.experiment.name}")
        except Exception as e:
            logger.warning(f"Failed to initialize Braintrust: {e}")

    async def log_evaluation(
        self,
        name: str,
        input: Dict[str, Any],
        output: Dict[str, Any],
        expected: Optional[Dict[str, Any]] = None,
        scores: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log single evaluation to Braintrust.

        Args:
            name: Evaluation name/identifier
            input: Input data
            output: Model output
            expected: Expected output (ground truth)
            scores: Evaluation scores (accuracy, precision, etc.)
            metadata: Additional metadata
        """
        if not self.enabled:
            return

        try:
            self.experiment.log(
                name=name,
                input=input,
                output=output,
                expected=expected,
                scores=scores or {},
                metadata=metadata or {}
            )
        except Exception as e:
            logger.error(f"Failed to log to Braintrust: {e}")

    async def log_batch_evaluations(
        self,
        evaluations: list[Dict[str, Any]]
    ):
        """
        Log batch of evaluations to Braintrust.

        Args:
            evaluations: List of evaluation dicts (each with name, input, output, etc.)
        """
        if not self.enabled:
            return

        for eval_data in evaluations:
            await self.log_evaluation(**eval_data)

    def finalize(self):
        """Finalize experiment and upload to Braintrust."""
        if not self.enabled:
            return

        try:
            summary = self.experiment.summarize()
            logger.info(f"Braintrust experiment finalized. View at: {summary.experiment_url}")
            return summary
        except Exception as e:
            logger.error(f"Failed to finalize Braintrust experiment: {e}")
            return None


# Convenience function
def create_braintrust_logger(
    project: str = "agent-runner",
    experiment: Optional[str] = None
) -> BraintrustLogger:
    """
    Create Braintrust logger.

    Args:
        project: Project name
        experiment: Optional experiment name

    Returns:
        BraintrustLogger instance (may be disabled if not configured)
    """
    return BraintrustLogger(project=project, experiment=experiment)


# Example usage
if __name__ == "__main__":
    import asyncio

    async def example():
        # Create logger
        logger = create_braintrust_logger(
            project="agent-runner",
            experiment="invoice_matcher_test"
        )

        # Log evaluation
        await logger.log_evaluation(
            name="exact_match_001",
            input={
                "transaction": {"vendorName": "SNCB", "amount": 22.70},
                "invoices": [{"id": 101, "vendorName": "SNCB", "amount": 22.70}]
            },
            output={
                "matched": True,
                "invoice_id": 101,
                "confidence": 0.95
            },
            expected={
                "invoice_id": 101
            },
            scores={
                "accuracy": 1.0,
                "confidence_error": 0.05
            },
            metadata={
                "difficulty": "easy",
                "tags": ["exact_match"]
            }
        )

        # Finalize
        summary = logger.finalize()
        if summary:
            print(f"View results: {summary.experiment_url}")

    asyncio.run(example())
