# LangGraph Integration Guide

**Graph-Based Agent Orchestration with Memory-Aware Decision Making**

Version: 1.0
Last Updated: 2026-01-08
Status: Production

---

## Table of Contents

1. [Why LangGraph](#why-langgraph)
2. [Architecture Overview](#architecture-overview)
3. [Base Graph Pattern](#base-graph-pattern)
4. [State Management](#state-management)
5. [Node Types](#node-types)
6. [Memory Integration](#memory-integration)
7. [Conditional Routing](#conditional-routing)
8. [Agent Examples](#agent-examples)
9. [Best Practices](#best-practices)
10. [Testing Patterns](#testing-patterns)

---

## Why LangGraph

### The Problem

Traditional agent implementations face challenges:

```python
# ❌ Traditional approach: Linear execution
async def match_invoice(transaction, invoices):
    # 1. Search (always runs)
    similar = await search_db(transaction)

    # 2. Claude reasoning (always runs)
    match = await claude_match(transaction, invoices, similar)

    # 3. Save (always runs)
    await save_result(match)

    return match
```

**Issues**:
- No conditional logic (all steps always execute)
- Hard to add memory lookups
- Difficult to test individual steps
- No state tracking between steps
- Cannot easily modify flow based on confidence

### The LangGraph Solution

```python
# ✅ LangGraph approach: Graph-based with routing
class InvoiceMatcherGraph(BaseAgentGraph):
    def build_graph(self):
        graph = StateGraph(InvoiceMatchState)

        # Nodes
        graph.add_node("build_query", self.build_query_node)
        graph.add_node("search_memory", self.search_memory_node)
        graph.add_node("compare_invoices", self.compare_invoices_node)
        graph.add_node("save_context", self.save_context_node)

        # Edges (flow control)
        graph.set_entry_point("build_query")
        graph.add_edge("build_query", "search_memory")
        graph.add_edge("search_memory", "compare_invoices")

        # Conditional routing based on confidence
        graph.add_conditional_edges(
            "compare_invoices",
            self.decision_router,  # Decides next step
            {
                "save_context": "save_context",
                "end": END
            }
        )

        return graph
```

**Benefits**:
- ✅ Conditional execution based on state
- ✅ Memory retrieval integrated into flow
- ✅ Each node is independently testable
- ✅ State tracked automatically
- ✅ Easy to visualize and debug
- ✅ Retry logic per node

---

## Architecture Overview

### System Integration

```
┌───────────────────────────────────────────────────────┐
│              Temporal Workflow                         │
│  (Orchestration, scheduling, error handling)          │
└───────────────────────────────────────────────────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │  Temporal Activity            │
        │  run_invoice_matcher_graph()  │
        └───────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────┐
│              LangGraph Agent                           │
│  (Reasoning, memory, decision routing)                │
│                                                        │
│   START → Build Query → Search Memory → Compare       │
│            ↓              ↓               ↓            │
│          [State]       [State]         [State]        │
│                                          ↓             │
│                                    Decision Router    │
│                                          │             │
│                        ┌─────────────────┴──────┐     │
│                        ▼                        ▼     │
│                  Save Context                  END    │
└───────────────────────────────────────────────────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │      Memory Layer             │
        │  • Qdrant (vectors)           │
        │  • Redis (cache)              │
        └───────────────────────────────┘
```

### Separation of Concerns

| Layer | Technology | Responsibility |
|-------|-----------|----------------|
| **Orchestration** | Temporal | Workflow lifecycle, retries, scheduling |
| **Reasoning** | LangGraph | Agent logic, memory, decision routing |
| **Execution** | Claude Agent SDK | Tool use, LLM calls |
| **Memory** | Qdrant + Redis | Vector search, caching |

---

## Base Graph Pattern

All LangGraph agents inherit from `BaseAgentGraph`, providing common functionality.

### Base Class

```python
# langgraph_agents/base_graph.py
from typing import Dict, Any, Optional
from langgraph.graph import StateGraph
import structlog

logger = structlog.get_logger(__name__)


class BaseAgentGraph:
    """
    Base class for all LangGraph agents.

    Provides:
    - Memory integration
    - State management helpers
    - Error handling
    - Logging
    """

    def __init__(self):
        self.memory_manager: Optional[MemoryManager] = None
        self.graph: Optional[StateGraph] = None

    async def initialize(self):
        """Initialize memory manager and build graph."""
        from memory import MemoryManager

        self.memory_manager = MemoryManager()
        await self.memory_manager.initialize()

        self.graph = self.build_graph().compile()

        logger.info("graph_initialized", agent=self.__class__.__name__)

    async def close(self):
        """Clean up resources."""
        if self.memory_manager:
            await self.memory_manager.close()

    def build_graph(self) -> StateGraph:
        """
        Build graph structure. Must be implemented by subclass.

        Returns:
            StateGraph instance
        """
        raise NotImplementedError

    # Memory helpers

    async def search_memory(
        self,
        collection: str,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict] = None
    ) -> list:
        """Search vector memory."""
        return await self.memory_manager.search(
            collection=collection,
            query=query,
            top_k=top_k,
            filters=filters
        )

    async def save_to_memory(
        self,
        collection: str,
        content: str,
        metadata: Dict[str, Any]
    ) -> int:
        """Save to vector memory."""
        return await self.memory_manager.save(
            collection=collection,
            content=content,
            metadata=metadata
        )

    # State helpers

    def add_step(self, state: Dict, step_name: str) -> Dict:
        """Add step to completion tracking."""
        state["steps_completed"] = state.get("steps_completed", []) + [step_name]
        return state

    def add_warning(self, state: Dict, warning: str) -> Dict:
        """Add warning to state."""
        state["warnings"] = state.get("warnings", []) + [warning]
        return state

    # Execution

    async def run(self, **initial_state) -> Dict[str, Any]:
        """Run graph with initial state."""
        if not self.graph:
            raise RuntimeError("Graph not initialized. Call initialize() first.")

        result = await self.graph.ainvoke(initial_state)
        return result
```

### Creating a New Agent

```python
# langgraph_agents/my_agent_graph.py
from langgraph.graph import StateGraph, END
from .base_graph import BaseAgentGraph
from .state_schemas import MyAgentState


class MyAgentGraph(BaseAgentGraph):
    """My custom agent with memory."""

    def build_graph(self) -> StateGraph:
        """Build agent graph structure."""
        graph = StateGraph(MyAgentState)

        # Add nodes
        graph.add_node("step1", self.step1_node)
        graph.add_node("step2", self.step2_node)

        # Define flow
        graph.set_entry_point("step1")
        graph.add_edge("step1", "step2")
        graph.add_edge("step2", END)

        return graph

    async def step1_node(self, state: MyAgentState) -> MyAgentState:
        """First processing step."""
        # Your logic here
        state["result"] = "processed"
        return self.add_step(state, "step1")

    async def step2_node(self, state: MyAgentState) -> MyAgentState:
        """Second processing step."""
        # Your logic here
        return self.add_step(state, "step2")

    # Public API
    async def process(self, input_data: Dict) -> Dict:
        """Public method to run agent."""
        initial_state = {"input": input_data}
        final_state = await self.run(**initial_state)
        return final_state
```

---

## State Management

### State Schema

LangGraph uses Pydantic-like TypedDict for state validation.

```python
# langgraph_agents/state_schemas.py
from typing import TypedDict, List, Dict, Any, Optional


class InvoiceMatchState(TypedDict):
    """State for invoice matching workflow."""

    # Inputs
    transaction: Dict[str, Any]  # Bank transaction to match
    invoices: List[Dict[str, Any]]  # Available invoices

    # Memory
    memory_query: str  # Search query for memory
    memory_results: List[Dict[str, Any]]  # Memory search results

    # Matching
    matched_invoice_id: Optional[int]  # Matched invoice ID (or None)
    confidence: float  # Confidence score (0-1)
    reasoning: str  # Explanation of match
    decision_type: str  # auto_match, human_review, no_match

    # Tracking
    steps_completed: List[str]  # Steps executed
    warnings: List[str]  # Warnings collected


def init_invoice_match_state(
    transaction: Dict[str, Any],
    invoices: List[Dict[str, Any]]
) -> InvoiceMatchState:
    """Initialize invoice match state with defaults."""
    return InvoiceMatchState(
        transaction=transaction,
        invoices=invoices,
        memory_query="",
        memory_results=[],
        matched_invoice_id=None,
        confidence=0.0,
        reasoning="",
        decision_type="no_match",
        steps_completed=[],
        warnings=[]
    )
```

### State Updates

States are immutable in LangGraph - each node returns a new state.

```python
async def search_memory_node(self, state: InvoiceMatchState) -> InvoiceMatchState:
    """Node that searches memory and updates state."""

    # Read from state
    query = state["memory_query"]

    # Perform operation
    results = await self.search_memory(
        collection="invoices",
        query=query,
        top_k=10
    )

    # Update state (create new dict with changes)
    state["memory_results"] = results
    state = self.add_step(state, "search_memory")

    # Return updated state
    return state
```

### State Accumulation

LangGraph accumulates state updates from each node.

```python
# Initial state
state = {"counter": 0, "items": []}

# Node 1 returns
return {"counter": 1, "items": ["a"]}

# Node 2 returns
return {"counter": 2, "items": ["a", "b"]}

# Final state (accumulated)
# {"counter": 2, "items": ["a", "b"]}
```

---

## Node Types

### 1. Data Transformation Nodes

Transform input data for next steps.

```python
async def build_query_node(self, state: InvoiceMatchState) -> InvoiceMatchState:
    """Transform transaction into search query."""
    transaction = state["transaction"]

    # Build rich query
    query_parts = []
    if vendor := transaction.get("vendorName"):
        query_parts.append(vendor)
    if amount := transaction.get("amount"):
        query_parts.append(f"€{amount:.2f}")

    state["memory_query"] = " ".join(query_parts)
    return self.add_step(state, "build_query")
```

**Characteristics**:
- Pure transformation (no side effects)
- Fast execution (<100ms)
- Deterministic output

### 2. Memory Retrieval Nodes

Fetch data from vector memory.

```python
async def search_memory_node(self, state: InvoiceMatchState) -> InvoiceMatchState:
    """Search memory for similar documents."""
    query = state["memory_query"]

    # Search Qdrant + Redis cache
    results = await self.search_memory(
        collection="invoices",
        query=query,
        top_k=10,
        filters={"matched": False}
    )

    state["memory_results"] = results

    # Add warning if no good results
    if not results or results[0]["score"] < 0.5:
        state = self.add_warning(state, "Low memory similarity")

    return self.add_step(state, "search_memory")
```

**Characteristics**:
- Async I/O operation
- Cached results (faster on cache hit)
- May return empty results

### 3. Reasoning Nodes

Use Claude for complex decision making.

```python
async def compare_invoices_node(self, state: InvoiceMatchState) -> InvoiceMatchState:
    """Use Claude to match transaction to invoice."""
    transaction = state["transaction"]
    invoices = state["invoices"]
    memory_results = state["memory_results"]

    # Build context from memory
    memory_context = "\n".join([
        f"- Similar: {r['payload']['vendor_name']} €{r['payload']['amount']}"
        for r in memory_results[:5]
    ])

    # Build prompt
    prompt = f"""Match this transaction to an invoice:

Transaction: {transaction['vendorName']} €{transaction['amount']:.2f}

Invoices: {len(invoices)} available

Memory context:
{memory_context}

Return JSON: {{"matched": bool, "invoice_id": int, "confidence": float, "reasoning": str}}
"""

    # Call Claude (via Agent SDK)
    # response = await self.agent.run(prompt)

    # For now, use rule-based fallback
    match = self._rule_based_match(transaction, invoices)

    state["matched_invoice_id"] = match["invoice_id"]
    state["confidence"] = match["confidence"]
    state["reasoning"] = match["reasoning"]

    # Determine decision type
    if state["confidence"] >= 0.90:
        state["decision_type"] = "auto_match"
    elif state["confidence"] >= 0.70:
        state["decision_type"] = "human_review"
    else:
        state["decision_type"] = "no_match"

    return self.add_step(state, "compare_invoices")
```

**Characteristics**:
- Most expensive operation (LLM call)
- Non-deterministic output
- May require retries

### 4. Persistence Nodes

Save results to memory or database.

```python
async def save_context_node(self, state: InvoiceMatchState) -> InvoiceMatchState:
    """Save decision context for learning."""
    transaction = state["transaction"]

    context = f"""
Invoice matching decision:
Transaction: {transaction['vendorName']} €{transaction['amount']}
Decision: {state['decision_type']}
Confidence: {state['confidence']:.2%}
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
            "confidence": state["confidence"]
        }
    )

    return self.add_step(state, "save_context")
```

**Characteristics**:
- Side effects (database writes)
- May fail (needs error handling)
- Idempotent (safe to retry)

---

## Memory Integration

### Pattern 1: Pre-fetch Context

Retrieve context before reasoning.

```python
def build_graph(self):
    graph = StateGraph(MyState)

    graph.add_node("fetch_context", self.fetch_context_node)
    graph.add_node("reason", self.reason_node)

    graph.set_entry_point("fetch_context")
    graph.add_edge("fetch_context", "reason")  # Context feeds into reasoning

    return graph

async def fetch_context_node(self, state):
    """Fetch context from memory."""
    query = state["query"]

    results = await self.search_memory(
        collection="agent_context",
        query=query,
        top_k=5
    )

    state["context"] = results
    return state

async def reason_node(self, state):
    """Reason with context."""
    context = state["context"]  # Use pre-fetched context

    prompt = f"Context: {context}\n\nNow reason about: {state['query']}"
    # ... Claude reasoning
    return state
```

### Pattern 2: Post-save Results

Save results after decision making.

```python
def build_graph(self):
    graph = StateGraph(MyState)

    graph.add_node("decide", self.decide_node)
    graph.add_node("save", self.save_node)

    graph.set_entry_point("decide")
    graph.add_edge("decide", "save")  # Save after decision

    return graph

async def decide_node(self, state):
    """Make decision."""
    state["decision"] = "approved"
    state["confidence"] = 0.95
    return state

async def save_node(self, state):
    """Save decision to memory."""
    await self.save_to_memory(
        collection="decisions",
        content=f"Decision: {state['decision']}",
        metadata={"confidence": state["confidence"]}
    )
    return state
```

### Pattern 3: Duplicate Detection

Check memory before creating new content.

```python
async def check_duplicate_node(self, state):
    """Check if content already exists."""
    content = state["content"]

    # Search for similar content
    results = await self.search_memory(
        collection="social_posts",
        query=content,
        top_k=1
    )

    # Check for high similarity
    if results and results[0]["score"] > 0.90:
        state["is_duplicate"] = True
        state["similar_content"] = results[0]["payload"]
        state = self.add_warning(
            state,
            f"Duplicate detected (similarity: {results[0]['score']:.2%})"
        )
    else:
        state["is_duplicate"] = False

    return state
```

---

## Conditional Routing

### Router Function

Router functions decide next node based on state.

```python
def decision_router(self, state: InvoiceMatchState) -> str:
    """Route based on confidence score."""
    confidence = state["confidence"]

    if confidence >= 0.90:
        return "auto_match_path"
    elif confidence >= 0.70:
        return "human_review_path"
    else:
        return "no_match_path"
```

### Conditional Edges

```python
def build_graph(self):
    graph = StateGraph(InvoiceMatchState)

    graph.add_node("compare", self.compare_node)
    graph.add_node("auto_match", self.auto_match_node)
    graph.add_node("human_review", self.human_review_node)
    graph.add_node("no_match", self.no_match_node)

    graph.set_entry_point("compare")

    # Conditional routing
    graph.add_conditional_edges(
        "compare",
        self.decision_router,  # Router function
        {
            "auto_match_path": "auto_match",
            "human_review_path": "human_review",
            "no_match_path": "no_match"
        }
    )

    # All paths lead to END
    graph.add_edge("auto_match", END)
    graph.add_edge("human_review", END)
    graph.add_edge("no_match", END)

    return graph
```

### Multi-condition Routing

```python
def quality_router(self, state: FeedPublisherState) -> str:
    """Route based on multiple conditions."""
    quality_score = state["caption_quality_score"]
    duplicate = state["duplicate_detected"]
    rejection_reason = state.get("rejection_reason")

    # Priority 1: Rejection
    if rejection_reason:
        return "reject"

    # Priority 2: Duplicate
    if duplicate:
        return "human_review"

    # Priority 3: Quality score
    if quality_score >= 0.85:
        return "auto_publish"
    elif quality_score >= 0.70:
        return "human_review"
    else:
        return "reject"
```

---

## Agent Examples

### Example 1: Invoice Matcher

**Full implementation**: `langgraph_agents/invoice_matcher_graph.py`

```python
class InvoiceMatcherGraph(BaseAgentGraph):
    """
    Match bank transactions to invoices using memory.

    Flow:
      START
        ↓
      Build Query (transform)
        ↓
      Search Memory (retrieve)
        ↓
      Compare Invoices (reason)
        ↓
      Decision Router (route)
        ├─→ confidence >= 0.90 → Auto Match
        ├─→ confidence >= 0.70 → Human Review
        └─→ confidence < 0.70 → No Match
        ↓
      Save Context (persist)
        ↓
      END
    """

    def build_graph(self):
        graph = StateGraph(InvoiceMatchState)

        # Nodes
        graph.add_node("build_query", self.build_query_node)
        graph.add_node("search_memory", self.search_memory_node)
        graph.add_node("compare_invoices", self.compare_invoices_node)
        graph.add_node("save_context", self.save_context_node)

        # Flow
        graph.set_entry_point("build_query")
        graph.add_edge("build_query", "search_memory")
        graph.add_edge("search_memory", "compare_invoices")

        # Conditional routing
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

    # Public API
    async def match(self, transaction: Dict, invoices: List[Dict]) -> Dict:
        """Match transaction to invoice."""
        initial_state = init_invoice_match_state(transaction, invoices)
        final_state = await self.run(**initial_state)

        return {
            "matched": final_state["matched_invoice_id"] is not None,
            "invoice_id": final_state["matched_invoice_id"],
            "confidence": final_state["confidence"],
            "decision_type": final_state["decision_type"]
        }
```

**Usage**:

```python
# Create graph
graph = InvoiceMatcherGraph()
await graph.initialize()

# Match transaction
result = await graph.match(
    transaction={"vendorName": "SNCB", "amount": 22.70},
    invoices=[...]
)

# result = {
#   "matched": True,
#   "invoice_id": 123,
#   "confidence": 0.95,
#   "decision_type": "auto_match"
# }
```

### Example 2: Feed Publisher

**Full implementation**: `langgraph_agents/feed_publisher_graph.py`

```python
class FeedPublisherGraph(BaseAgentGraph):
    """
    Generate and publish social media captions with duplicate detection.

    Flow:
      START
        ↓
      Check Caption History (memory)
        ↓
      View Image (S3)
        ↓
      Generate Caption (Claude)
        ↓
      Quality Check (validate)
        ↓
      Decision Router (route)
        ├─→ quality >= 0.85 → Auto Publish
        ├─→ quality >= 0.70 → Human Review
        └─→ quality < 0.70 → Reject
        ↓
      Publish (if approved)
        ↓
      Save to Memory
        ↓
      END
    """

    def build_graph(self):
        graph = StateGraph(FeedPublisherState)

        # Nodes
        graph.add_node("check_history", self.check_caption_history_node)
        graph.add_node("view_image", self.view_image_node)
        graph.add_node("generate_caption", self.generate_caption_node)
        graph.add_node("quality_check", self.quality_check_node)
        graph.add_node("publish", self.publish_node)
        graph.add_node("save_memory", self.save_memory_node)

        # Flow
        graph.set_entry_point("check_history")
        graph.add_edge("check_history", "view_image")
        graph.add_edge("view_image", "generate_caption")
        graph.add_edge("generate_caption", "quality_check")

        # Conditional routing
        graph.add_conditional_edges(
            "quality_check",
            self.decision_router,
            {
                "publish": "publish",
                "human_review": "save_memory",  # Skip publish
                "reject": END  # End without publishing
            }
        )

        graph.add_edge("publish", "save_memory")
        graph.add_edge("save_memory", END)

        return graph

    # Public API
    async def publish(self, brand: str, platform: str, photo_s3_key: str) -> Dict:
        """Generate and publish caption."""
        initial_state = init_feed_publisher_state(brand, platform, photo_s3_key)
        final_state = await self.run(**initial_state)

        return {
            "published": final_state.get("published_at") is not None,
            "caption": final_state["caption"],
            "quality_score": final_state["caption_quality_score"],
            "requires_approval": final_state["requires_approval"]
        }
```

---

## Best Practices

### 1. Keep Nodes Focused

Each node should have a single responsibility.

```python
# ❌ Bad: Node does too much
async def process_node(self, state):
    # Fetch data
    data = await fetch_data()

    # Transform
    transformed = transform(data)

    # Validate
    is_valid = validate(transformed)

    # Save
    await save(transformed)

    return state

# ✅ Good: Split into focused nodes
async def fetch_node(self, state):
    state["data"] = await fetch_data()
    return state

async def transform_node(self, state):
    state["transformed"] = transform(state["data"])
    return state

async def validate_node(self, state):
    state["is_valid"] = validate(state["transformed"])
    return state

async def save_node(self, state):
    if state["is_valid"]:
        await save(state["transformed"])
    return state
```

### 2. Use Type Hints

Strong typing catches errors early.

```python
# ✅ Good: Type hints for state
async def search_memory_node(
    self,
    state: InvoiceMatchState  # Type hint
) -> InvoiceMatchState:  # Return type
    query: str = state["memory_query"]  # Type hint
    results: List[Dict[str, Any]] = await self.search_memory(...)
    state["memory_results"] = results
    return state
```

### 3. Handle Errors Gracefully

Don't let one node failure crash entire graph.

```python
async def search_memory_node(self, state):
    try:
        results = await self.search_memory(
            collection="invoices",
            query=state["memory_query"],
            top_k=10
        )
        state["memory_results"] = results

    except Exception as e:
        logger.error("memory_search_failed", error=str(e))
        state["memory_results"] = []  # Empty results, continue
        state = self.add_warning(state, f"Memory search failed: {e}")

    return state
```

### 4. Log State Transitions

Track state changes for debugging.

```python
async def compare_invoices_node(self, state):
    logger.info(
        "node_start",
        node="compare_invoices",
        transaction_id=state["transaction"].get("id"),
        invoices_count=len(state["invoices"]),
        memory_results_count=len(state["memory_results"])
    )

    # ... node logic ...

    logger.info(
        "node_complete",
        node="compare_invoices",
        confidence=state["confidence"],
        decision=state["decision_type"]
    )

    return state
```

### 5. Make Nodes Testable

Design nodes to be independently testable.

```python
# ✅ Good: Pure function, easy to test
async def build_query_node(self, state):
    transaction = state["transaction"]

    query_parts = []
    if vendor := transaction.get("vendorName"):
        query_parts.append(vendor)
    if amount := transaction.get("amount"):
        query_parts.append(f"€{amount:.2f}")

    state["memory_query"] = " ".join(query_parts)
    return state

# Test
async def test_build_query_node():
    graph = InvoiceMatcherGraph()
    state = {
        "transaction": {"vendorName": "SNCB", "amount": 22.70}
    }

    result = await graph.build_query_node(state)

    assert result["memory_query"] == "SNCB €22.70"
```

### 6. Use Descriptive Node Names

Names should describe what the node does.

```python
# ❌ Bad: Generic names
graph.add_node("process", self.process)
graph.add_node("step1", self.step1)

# ✅ Good: Descriptive names
graph.add_node("search_memory", self.search_memory_node)
graph.add_node("compare_invoices", self.compare_invoices_node)
graph.add_node("save_context", self.save_context_node)
```

### 7. Document Decision Logic

Explain routing conditions clearly.

```python
def decision_router(self, state: InvoiceMatchState) -> str:
    """
    Route based on confidence score.

    Rules:
    - confidence >= 0.90: Auto-match (high confidence)
    - confidence >= 0.70: Human review (medium confidence)
    - confidence < 0.70: No match (low confidence)

    Args:
        state: Current graph state

    Returns:
        Next node name
    """
    confidence = state["confidence"]

    if confidence >= 0.90:
        return "save_context"  # Auto-match path
    else:
        return "end"  # Skip saving for low confidence
```

---

## Testing Patterns

### Unit Test: Individual Nodes

```python
# tests/unit/test_invoice_matcher_graph.py
import pytest
from langgraph_agents import InvoiceMatcherGraph


@pytest.fixture
async def graph():
    g = InvoiceMatcherGraph()
    await g.initialize()
    yield g
    await g.close()


async def test_build_query_node(graph):
    """Test query building from transaction."""
    state = {
        "transaction": {
            "vendorName": "SNCB",
            "amount": 22.70,
            "date": "2025-01-03"
        }
    }

    result = await graph.build_query_node(state)

    assert "SNCB" in result["memory_query"]
    assert "€22.70" in result["memory_query"]
    assert "build_query" in result["steps_completed"]
```

### Integration Test: Full Graph

```python
async def test_full_matching_flow(graph):
    """Test complete invoice matching flow."""
    transaction = {"vendorName": "SNCB", "amount": 22.70}
    invoices = [
        {"id": 1, "vendorName": "SNCB", "amount": 22.70},
        {"id": 2, "vendorName": "De Lijn", "amount": 15.00}
    ]

    result = await graph.match(transaction, invoices)

    assert result["matched"] == True
    assert result["invoice_id"] == 1
    assert result["confidence"] >= 0.90
    assert result["decision_type"] == "auto_match"
```

### Mock Memory for Tests

```python
from unittest.mock import AsyncMock, patch


async def test_with_mocked_memory(graph):
    """Test with mocked memory responses."""
    # Mock memory search
    with patch.object(graph, 'search_memory', new_callable=AsyncMock) as mock_search:
        mock_search.return_value = [
            {
                "score": 0.95,
                "payload": {"vendor_name": "SNCB", "amount": 22.70}
            }
        ]

        result = await graph.match(
            transaction={"vendorName": "SNCB", "amount": 22.70},
            invoices=[...]
        )

        mock_search.assert_called_once()
        assert result["confidence"] > 0.90
```

---

## Related Documentation

- [System Architecture](./ARCHITECTURE.md)
- [Memory Layer](./MEMORY.md)
- [Evaluation Framework](./EVALUATION.md)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)

---

**Maintained by**: Agent Platform Team
**Contact**: platform@yourdomain.com
**Last Updated**: 2026-01-08
