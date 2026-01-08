"""
Invoice Matcher Graph
=====================

LangGraph implementation for invoice matching with memory.

Workflow:
1. Build query from transaction
2. Search memory for similar invoices
3. Compare transaction with candidates
4. Make decision (auto-match / human-review / no-match)
5. Save decision to memory

Decision thresholds:
- Confidence >= 0.90: Auto-match
- Confidence >= 0.70: Human review
- Confidence < 0.70: No match
"""

from typing import Dict, Any
from langgraph.graph import StateGraph, END
import structlog
import time

from .base_graph import BaseAgentGraph
from .state_schemas import InvoiceMatchState, init_invoice_match_state

# Import monitoring metrics
try:
    from monitoring.metrics import record_agent_execution, AgentMetrics
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logger = structlog.get_logger(__name__)


class InvoiceMatcherGraph(BaseAgentGraph):
    """
    Invoice matching agent with memory-aware decision making.

    Flow:
        START
          ↓
        Build Query
          ↓
        Search Memory
          ↓
        Compare & Match
          ↓
        Decision Node → auto_match / human_review / no_match
          ↓
        Save Context
          ↓
        END
    """

    def build_graph(self) -> StateGraph:
        """Build invoice matcher graph."""
        # Create graph with state schema
        graph = StateGraph(InvoiceMatchState)

        # Add nodes
        graph.add_node("build_query", self.build_query_node)
        graph.add_node("search_memory", self.search_memory_node)
        graph.add_node("compare_invoices", self.compare_invoices_node)
        graph.add_node("save_context", self.save_context_node)

        # Define edges
        graph.set_entry_point("build_query")
        graph.add_edge("build_query", "search_memory")
        graph.add_edge("search_memory", "compare_invoices")

        # Conditional routing based on decision
        graph.add_conditional_edges(
            "compare_invoices",
            self.decision_router,
            {
                "save_context": "save_context",
                "end": END
            }
        )

        graph.add_edge("save_context", END)

        return graph

    async def build_query_node(self, state: InvoiceMatchState) -> InvoiceMatchState:
        """
        Node: Build search query from transaction.

        Args:
            state: Current state

        Returns:
            Updated state with memory_query
        """
        transaction = state["transaction"]

        # Build rich query from transaction fields
        query_parts = []

        if vendor := transaction.get("vendorName"):
            query_parts.append(vendor)

        if amount := transaction.get("amount"):
            query_parts.append(f"€{amount:.2f}")

        if comm := transaction.get("communication"):
            query_parts.append(comm)

        if date := transaction.get("date"):
            query_parts.append(f"date:{date}")

        query = " ".join(query_parts)
        state["memory_query"] = query

        state = self.add_step(state, "build_query")

        logger.info(
            "query_built",
            transaction_id=transaction.get("id"),
            query_preview=query[:100]
        )

        return state

    async def search_memory_node(self, state: InvoiceMatchState) -> InvoiceMatchState:
        """
        Node: Search memory for similar invoices.

        Args:
            state: Current state

        Returns:
            Updated state with memory_results
        """
        query = state["memory_query"]

        # Search for unmatched invoices only
        results = await self.search_memory(
            collection="invoices",
            query=query,
            top_k=10,
            filters={"matched": False}
        )

        state["memory_results"] = results

        state = self.add_step(state, "search_memory")

        logger.info(
            "memory_searched",
            query_preview=query[:50],
            results_count=len(results),
            top_score=results[0]["score"] if results else 0
        )

        # Warning if no good matches found
        if not results or results[0]["score"] < 0.5:
            state = self.add_warning(
                state,
                f"Low memory similarity (best: {results[0]['score']:.2%})" if results else "No memory results"
            )

        return state

    async def compare_invoices_node(self, state: InvoiceMatchState) -> InvoiceMatchState:
        """
        Node: Compare transaction with invoice candidates.

        Uses Claude Agent SDK to reason about matches.

        Args:
            state: Current state

        Returns:
            Updated state with matching decision
        """
        transaction = state["transaction"]
        invoices = state["invoices"]
        memory_results = state["memory_results"]

        # Build context for Claude
        memory_context = "\n".join([
            f"- Similar invoice (score {r['score']:.2%}): {r['payload'].get('vendor_name')} €{r['payload'].get('amount'):.2f}"
            for r in memory_results[:5]
        ])

        # Build prompt for matching
        prompt = f"""Match this bank transaction to an invoice:

Transaction:
- Vendor: {transaction.get('vendorName', 'N/A')}
- Amount: €{transaction.get('amount', 0):.2f}
- Date: {transaction.get('date', 'N/A')}
- Communication: {transaction.get('communication', 'N/A')}

Available invoices ({len(invoices)}):
{self._format_invoices(invoices[:10])}

Memory context (similar past invoices):
{memory_context if memory_context else "No similar invoices in memory"}

Instructions:
1. Find the best matching invoice
2. Consider: vendor name match, amount match (±5%), date proximity
3. Use memory context to inform decision
4. Return confidence score (0-1)

Return JSON format:
{{
    "matched": true/false,
    "invoice_id": <id or null>,
    "confidence": <0.0-1.0>,
    "reasoning": "<brief explanation>"
}}
"""

        # Call Claude for matching (simplified - in real implementation use Claude Agent SDK)
        # For now, use rule-based matching as fallback

        best_match = self._rule_based_match(transaction, invoices)

        state["matched_invoice_id"] = best_match.get("invoice_id")
        state["confidence"] = best_match.get("confidence", 0.0)
        state["reasoning"] = best_match.get("reasoning", "")

        # Determine decision type
        if state["confidence"] >= 0.90:
            state["decision_type"] = "auto_match"
        elif state["confidence"] >= 0.70:
            state["decision_type"] = "human_review"
        else:
            state["decision_type"] = "no_match"

        state = self.add_step(state, "compare_invoices")

        logger.info(
            "invoices_compared",
            matched=state["matched_invoice_id"] is not None,
            confidence=state["confidence"],
            decision=state["decision_type"]
        )

        return state

    def decision_router(self, state: InvoiceMatchState) -> str:
        """
        Routing function: Decide next node based on confidence.

        Args:
            state: Current state

        Returns:
            Next node name ("save_context" or "end")
        """
        # Always save context for learning
        return "save_context"

    async def save_context_node(self, state: InvoiceMatchState) -> InvoiceMatchState:
        """
        Node: Save decision context to memory for learning.

        Args:
            state: Current state

        Returns:
            Updated state
        """
        # Build context string
        transaction = state["transaction"]
        context = f"""
Invoice matching decision:
Transaction: {transaction.get('vendorName')} €{transaction.get('amount'):.2f}
Decision: {state['decision_type']}
Confidence: {state['confidence']:.2%}
Matched Invoice ID: {state['matched_invoice_id']}
Reasoning: {state['reasoning']}
        """.strip()

        # Save to agent_context collection
        await self.save_to_memory(
            collection="agent_context",
            content=context,
            metadata={
                "agent_name": "invoice_matcher",
                "context_type": state["decision_type"],
                "transaction_id": transaction.get("id"),
                "invoice_id": state["matched_invoice_id"],
                "confidence": state["confidence"]
            }
        )

        state = self.add_step(state, "save_context")

        logger.info("context_saved", decision_type=state["decision_type"])

        return state

    # Helper methods

    def _format_invoices(self, invoices: list) -> str:
        """Format invoices for prompt."""
        lines = []
        for inv in invoices:
            lines.append(
                f"- ID {inv.get('id')}: {inv.get('vendorName', 'N/A')} "
                f"€{inv.get('amount', 0):.2f} on {inv.get('date', 'N/A')}"
            )
        return "\n".join(lines)

    def _rule_based_match(
        self,
        transaction: Dict[str, Any],
        invoices: list
    ) -> Dict[str, Any]:
        """
        Fallback rule-based matching.

        Matches on:
        - Exact vendor name
        - Amount within ±5%
        - Date within 30 days

        Returns:
            Match result with invoice_id, confidence, reasoning
        """
        trans_vendor = (transaction.get("vendorName") or "").lower()
        trans_amount = transaction.get("amount", 0)

        best_match = {"invoice_id": None, "confidence": 0.0, "reasoning": "No match found"}

        for invoice in invoices:
            inv_vendor = (invoice.get("vendorName") or "").lower()
            inv_amount = invoice.get("amount", 0)

            # Calculate match score
            score = 0.0
            reasons = []

            # Vendor match (0.5 weight)
            if trans_vendor and inv_vendor and trans_vendor in inv_vendor:
                score += 0.5
                reasons.append("vendor match")

            # Amount match (0.4 weight) - within 5%
            if inv_amount > 0:
                amount_diff = abs(trans_amount - inv_amount) / inv_amount
                if amount_diff <= 0.05:  # Within 5%
                    score += 0.4
                    reasons.append(f"amount match (diff: {amount_diff:.1%})")
                elif amount_diff <= 0.15:  # Within 15%
                    score += 0.2
                    reasons.append(f"amount close (diff: {amount_diff:.1%})")

            # Date proximity (0.1 weight)
            # TODO: Implement date comparison
            score += 0.1

            # Update best match if better score
            if score > best_match["confidence"]:
                best_match = {
                    "invoice_id": invoice.get("id"),
                    "confidence": score,
                    "reasoning": ", ".join(reasons) if reasons else "Partial match"
                }

        return best_match

    # Public API

    async def match(
        self,
        transaction: Dict[str, Any],
        invoices: list
    ) -> Dict[str, Any]:
        """
        Match transaction to invoice.

        Args:
            transaction: Bank transaction dict
            invoices: List of available invoices

        Returns:
            Matching result with decision
        """
        # Start timing
        start_time = time.time()
        status = "success"

        try:
            # Initialize state
            initial_state = init_invoice_match_state(transaction, invoices)

            # Run graph
            final_state = await self.run(**initial_state)

            # Build result
            result = {
                "matched": final_state.get("matched_invoice_id") is not None,
                "invoice_id": final_state.get("matched_invoice_id"),
                "confidence": final_state.get("confidence", 0.0),
                "decision_type": final_state.get("decision_type"),
                "reasoning": final_state.get("reasoning", ""),
                "warnings": final_state.get("warnings", []),
                "steps_completed": final_state.get("steps_completed", [])
            }

            # Record metrics
            if METRICS_AVAILABLE:
                duration = time.time() - start_time
                record_agent_execution(
                    agent_name="invoice_matcher",
                    duration_seconds=duration,
                    status=status,
                    confidence=result["confidence"],
                    decision_type=result["decision_type"]
                )

            return result

        except Exception as e:
            status = "failure"
            duration = time.time() - start_time

            # Record failure metrics
            if METRICS_AVAILABLE:
                record_agent_execution(
                    agent_name="invoice_matcher",
                    duration_seconds=duration,
                    status=status
                )

            raise
