"""
Cost Efficiency Evaluator
==========================

Tracks API costs and performance metrics for agents.

Metrics:
- Total token usage (prompt + completion)
- Total cost in USD
- Cost per execution
- Cost per successful match/caption
- Latency (execution time)
- Cost efficiency score
"""

import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExecutionMetrics:
    """Metrics for a single agent execution."""
    agent_name: str
    execution_id: str
    timestamp: str
    success: bool
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    embedding_tokens: int = 0
    cost_usd: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class CostEfficiencyEvaluator:
    """
    Evaluator for cost and performance tracking.

    Usage:
        evaluator = CostEfficiencyEvaluator()

        with evaluator.track_execution("invoice_matcher") as tracker:
            result = await graph.match(transaction, invoices)
            tracker.record_llm_call(prompt_tokens=500, completion_tokens=150)
            tracker.record_embedding_call(tokens=200)

        print(evaluator.get_metrics())
    """

    # Pricing (OpenAI as of 2024)
    PRICING = {
        'gpt-4': {
            'prompt': 0.03 / 1000,  # $0.03 per 1K tokens
            'completion': 0.06 / 1000  # $0.06 per 1K tokens
        },
        'gpt-3.5-turbo': {
            'prompt': 0.0015 / 1000,
            'completion': 0.002 / 1000
        },
        'text-embedding-3-small': {
            'input': 0.02 / 1_000_000  # $0.02 per 1M tokens
        },
        'claude-3-sonnet': {
            'prompt': 0.003 / 1000,
            'completion': 0.015 / 1000
        }
    }

    def __init__(self, default_model: str = 'claude-3-sonnet'):
        """
        Initialize evaluator.

        Args:
            default_model: Default model for cost calculation
        """
        self.default_model = default_model
        self.executions: List[ExecutionMetrics] = []
        self.current_tracking: Optional['ExecutionTracker'] = None

    def track_execution(self, agent_name: str, execution_id: Optional[str] = None) -> 'ExecutionTracker':
        """
        Start tracking an execution.

        Args:
            agent_name: Name of agent being executed
            execution_id: Optional execution ID (auto-generated if None)

        Returns:
            ExecutionTracker context manager
        """
        if execution_id is None:
            execution_id = f"{agent_name}_{int(time.time() * 1000)}"

        return ExecutionTracker(self, agent_name, execution_id)

    def _add_execution(self, metrics: ExecutionMetrics):
        """Add execution metrics (called by tracker)."""
        self.executions.append(metrics)
        logger.info(
            f"Execution tracked: {metrics.agent_name} - "
            f"latency={metrics.latency_ms:.0f}ms, "
            f"tokens={metrics.total_tokens}, "
            f"cost=${metrics.cost_usd:.4f}"
        )

    def calculate_cost(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        embedding_tokens: int = 0,
        model: Optional[str] = None
    ) -> float:
        """
        Calculate cost for token usage.

        Args:
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            embedding_tokens: Number of embedding tokens
            model: Model name (uses default if None)

        Returns:
            Cost in USD
        """
        if model is None:
            model = self.default_model

        cost = 0.0

        # LLM costs
        if model in self.PRICING and prompt_tokens + completion_tokens > 0:
            cost += prompt_tokens * self.PRICING[model]['prompt']
            cost += completion_tokens * self.PRICING[model]['completion']

        # Embedding costs
        if embedding_tokens > 0:
            cost += embedding_tokens * self.PRICING['text-embedding-3-small']['input']

        return cost

    def get_metrics(self) -> Dict[str, Any]:
        """
        Calculate aggregate metrics.

        Returns:
            Dict with cost and performance metrics
        """
        if not self.executions:
            return {"error": "No executions tracked"}

        total_executions = len(self.executions)
        successful = sum(1 for e in self.executions if e.success)
        failed = total_executions - successful

        total_tokens = sum(e.total_tokens + e.embedding_tokens for e in self.executions)
        total_cost = sum(e.cost_usd for e in self.executions)
        avg_latency = sum(e.latency_ms for e in self.executions) / total_executions

        # Per-agent breakdown
        by_agent = {}
        for agent_name in set(e.agent_name for e in self.executions):
            agent_execs = [e for e in self.executions if e.agent_name == agent_name]
            by_agent[agent_name] = {
                'count': len(agent_execs),
                'success_rate': sum(1 for e in agent_execs if e.success) / len(agent_execs),
                'avg_latency_ms': sum(e.latency_ms for e in agent_execs) / len(agent_execs),
                'total_tokens': sum(e.total_tokens + e.embedding_tokens for e in agent_execs),
                'total_cost_usd': sum(e.cost_usd for e in agent_execs),
                'cost_per_execution': sum(e.cost_usd for e in agent_execs) / len(agent_execs)
            }

        metrics = {
            'total_executions': total_executions,
            'successful': successful,
            'failed': failed,
            'success_rate': successful / total_executions,
            'total_tokens': total_tokens,
            'total_cost_usd': total_cost,
            'avg_cost_per_execution': total_cost / total_executions,
            'cost_per_success': total_cost / successful if successful > 0 else 0,
            'avg_latency_ms': avg_latency,
            'by_agent': by_agent
        }

        return metrics

    def get_cost_efficiency_score(self) -> float:
        """
        Calculate cost efficiency score (0-1).

        Higher is better:
        - Low cost per success
        - High success rate
        - Low latency

        Returns:
            Efficiency score 0-1
        """
        metrics = self.get_metrics()

        if 'error' in metrics:
            return 0.0

        # Normalize metrics
        # Target: $0.01 per execution, 95% success rate, 2s latency
        target_cost = 0.01
        target_success_rate = 0.95
        target_latency = 2000  # ms

        cost_score = min(1.0, target_cost / max(metrics['avg_cost_per_execution'], 0.001))
        success_score = metrics['success_rate'] / target_success_rate
        latency_score = min(1.0, target_latency / metrics['avg_latency_ms'])

        # Weighted average
        efficiency = (
            cost_score * 0.4 +
            success_score * 0.4 +
            latency_score * 0.2
        )

        return min(1.0, efficiency)

    def print_report(self):
        """Print cost efficiency report to console."""
        metrics = self.get_metrics()

        if 'error' in metrics:
            print(f"Error: {metrics['error']}")
            return

        print("\n" + "=" * 60)
        print("COST EFFICIENCY REPORT")
        print("=" * 60)
        print(f"\nTotal executions: {metrics['total_executions']}")
        print(f"Success rate: {metrics['success_rate']:.2%} ({metrics['successful']}/{metrics['total_executions']})")
        print(f"\n--- COST METRICS ---")
        print(f"Total tokens: {metrics['total_tokens']:,}")
        print(f"Total cost: ${metrics['total_cost_usd']:.4f}")
        print(f"Avg cost per execution: ${metrics['avg_cost_per_execution']:.4f}")
        print(f"Cost per success: ${metrics['cost_per_success']:.4f}")
        print(f"\n--- PERFORMANCE METRICS ---")
        print(f"Avg latency: {metrics['avg_latency_ms']:.0f}ms")
        print(f"Efficiency score: {self.get_cost_efficiency_score():.2%}")

        print("\n--- BY AGENT ---")
        for agent_name, agent_metrics in metrics['by_agent'].items():
            print(f"\n{agent_name}:")
            print(f"  Executions: {agent_metrics['count']}")
            print(f"  Success rate: {agent_metrics['success_rate']:.2%}")
            print(f"  Avg latency: {agent_metrics['avg_latency_ms']:.0f}ms")
            print(f"  Total tokens: {agent_metrics['total_tokens']:,}")
            print(f"  Total cost: ${agent_metrics['total_cost_usd']:.4f}")
            print(f"  Cost per execution: ${agent_metrics['cost_per_execution']:.4f}")

        print("=" * 60 + "\n")

    def export_results(self, output_path: str):
        """
        Export results to JSON file.

        Args:
            output_path: Path to output JSON file
        """
        import json

        data = {
            'metrics': self.get_metrics(),
            'efficiency_score': self.get_cost_efficiency_score(),
            'executions': [
                {
                    'agent_name': e.agent_name,
                    'execution_id': e.execution_id,
                    'timestamp': e.timestamp,
                    'success': e.success,
                    'latency_ms': e.latency_ms,
                    'prompt_tokens': e.prompt_tokens,
                    'completion_tokens': e.completion_tokens,
                    'total_tokens': e.total_tokens,
                    'embedding_tokens': e.embedding_tokens,
                    'cost_usd': e.cost_usd,
                    'metadata': e.metadata
                }
                for e in self.executions
            ]
        }

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Results exported to {output_path}")


class ExecutionTracker:
    """Context manager for tracking single execution."""

    def __init__(self, evaluator: CostEfficiencyEvaluator, agent_name: str, execution_id: str):
        self.evaluator = evaluator
        self.agent_name = agent_name
        self.execution_id = execution_id
        self.start_time = None
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.embedding_tokens = 0
        self.success = False
        self.metadata = {}

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        latency_ms = (time.time() - self.start_time) * 1000

        # Calculate cost
        cost = self.evaluator.calculate_cost(
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            embedding_tokens=self.embedding_tokens
        )

        # Create metrics
        metrics = ExecutionMetrics(
            agent_name=self.agent_name,
            execution_id=self.execution_id,
            timestamp=datetime.now().isoformat(),
            success=self.success and exc_type is None,
            latency_ms=latency_ms,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.prompt_tokens + self.completion_tokens,
            embedding_tokens=self.embedding_tokens,
            cost_usd=cost,
            metadata=self.metadata
        )

        self.evaluator._add_execution(metrics)

        # Don't suppress exceptions
        return False

    def record_llm_call(self, prompt_tokens: int, completion_tokens: int):
        """Record LLM API call tokens."""
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens

    def record_embedding_call(self, tokens: int):
        """Record embedding API call tokens."""
        self.embedding_tokens += tokens

    def set_success(self, success: bool = True):
        """Mark execution as successful."""
        self.success = success

    def add_metadata(self, key: str, value: Any):
        """Add metadata to execution."""
        self.metadata[key] = value
