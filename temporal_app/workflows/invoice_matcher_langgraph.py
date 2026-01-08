"""
Invoice Matcher Workflow (LangGraph Version) - Memory-aware invoice matching.

This workflow uses LangGraph for:
- Memory-based similar invoice retrieval
- Context-aware matching decisions
- Confidence-based routing (auto-match vs human review)
- Learning from decisions (save to memory)
"""
from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Dict, Any, List
import logging

# Import activities
with workflow.unsafe.imports_passed_through():
    from temporal_app.activities.langgraph_activities import run_invoice_matcher_graph
    from temporal_app.monitoring import observe_workflow

logger = logging.getLogger(__name__)


@workflow.defn
class InvoiceMatcherLangGraphWorkflow:
    """
    LangGraph-powered invoice matcher workflow with memory.

    Flow:
    1. Run InvoiceMatcherGraph (LangGraph):
       - Build query from transaction
       - Search memory for similar invoices
       - Compare transaction with candidates
       - Make decision (auto-match / human-review / no-match)
       - Save decision to memory
    2. Return matching result

    Features:
    - Memory-aware matching (learns from past decisions)
    - Confidence-based decision routing
    - Auto-match for high confidence (≥90%)
    - Human review for medium confidence (70-90%)
    - No match for low confidence (<70%)
    - Decision context saved for future learning
    """

    @workflow.run
    async def run(
        self,
        transaction: Dict[str, Any],
        invoices: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Execute the LangGraph-powered invoice matching workflow.

        Args:
            transaction: Bank transaction to match (dict with vendorName, amount, date, etc.)
            invoices: List of available invoices to match against

        Returns:
            Matching result with invoice_id, confidence, decision_type
        """
        workflow.logger.info(
            f"🚀 Starting LangGraph invoice matcher - "
            f"Transaction: {transaction.get('vendorName')} €{transaction.get('amount')}, "
            f"Available invoices: {len(invoices)}"
        )

        try:
            # Run LangGraph workflow
            workflow.logger.info("🤖 Running LangGraph invoice matcher...")
            graph_result = await workflow.execute_activity(
                run_invoice_matcher_graph,
                args=[transaction, invoices],
                start_to_close_timeout=timedelta(minutes=3),
                retry_policy=RetryPolicy(
                    maximum_attempts=2,
                    initial_interval=timedelta(seconds=20),
                ),
            )

            workflow.logger.info(
                f"✅ LangGraph complete - "
                f"Matched: {graph_result['matched']}, "
                f"Confidence: {graph_result['confidence']:.2%}, "
                f"Decision: {graph_result['decision_type']}"
            )

            # Build final result
            result = {
                "success": True,
                "matched": graph_result["matched"],
                "invoice_id": graph_result["invoice_id"],
                "confidence": graph_result["confidence"],
                "decision_type": graph_result["decision_type"],
                "reasoning": graph_result["reasoning"],
                "transaction_id": transaction.get("id"),
                "transaction_vendor": transaction.get("vendorName"),
                "transaction_amount": transaction.get("amount"),
                "warnings": graph_result["warnings"],
                "steps_completed": graph_result["steps_completed"],
                "workflow_id": workflow.info().workflow_id,
                "run_id": workflow.info().run_id,
                "matched_at": workflow.now().isoformat() if graph_result["matched"] else None
            }

            # Log different outcomes
            if result["decision_type"] == "auto_match":
                workflow.logger.info(
                    f"🎉 Auto-matched - "
                    f"Invoice {result['invoice_id']} (confidence: {result['confidence']:.2%})"
                )
            elif result["decision_type"] == "human_review":
                workflow.logger.warning(
                    f"⚠️  Requires human review - "
                    f"Invoice {result['invoice_id']} (confidence: {result['confidence']:.2%})"
                )
            else:
                workflow.logger.info(
                    f"❌ No match found - "
                    f"Confidence too low ({result['confidence']:.2%})"
                )

            return result

        except Exception as e:
            workflow.logger.error(f"❌ LangGraph invoice matching failed: {e}")
            raise
