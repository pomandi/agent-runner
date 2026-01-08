"""
Base Agent Graph
================

Base class for all LangGraph-based agents.
Provides common functionality: memory access, logging, error handling.
"""

from typing import Any, Dict, Optional
from langgraph.graph import StateGraph, END
import structlog

from memory import MemoryManager

logger = structlog.get_logger(__name__)


class BaseAgentGraph:
    """
    Base class for LangGraph agents with memory integration.

    Subclasses should:
    1. Define state schema (TypedDict)
    2. Implement build_graph() method
    3. Add nodes and edges
    4. Compile the graph

    Features:
    - Memory manager integration
    - Structured logging
    - Error handling
    - State validation
    """

    def __init__(
        self,
        memory_manager: Optional[MemoryManager] = None,
        enable_memory: bool = True
    ):
        """
        Initialize base agent graph.

        Args:
            memory_manager: Custom memory manager (or creates new one)
            enable_memory: Whether memory is enabled
        """
        self.memory_manager = memory_manager
        self.enable_memory = enable_memory
        self.graph: Optional[StateGraph] = None
        self.compiled_graph = None

        logger.info(
            "base_graph_initialized",
            agent=self.__class__.__name__,
            memory_enabled=self.enable_memory
        )

    async def initialize(self):
        """
        Initialize graph (call this before first use).

        - Initializes memory manager
        - Builds graph
        - Compiles graph
        """
        # Initialize memory if enabled
        if self.enable_memory and self.memory_manager is None:
            from memory import get_memory_manager
            self.memory_manager = await get_memory_manager()

        # Build and compile graph
        self.graph = self.build_graph()
        self.compiled_graph = self.graph.compile()

        logger.info(
            "graph_initialized",
            agent=self.__class__.__name__
        )

    def build_graph(self) -> StateGraph:
        """
        Build the graph structure (MUST be implemented by subclass).

        Returns:
            StateGraph instance with nodes and edges defined
        """
        raise NotImplementedError("Subclasses must implement build_graph()")

    async def run(self, **initial_state) -> Dict[str, Any]:
        """
        Run the graph with initial state.

        Args:
            **initial_state: Initial state values

        Returns:
            Final state after graph execution
        """
        if not self.compiled_graph:
            await self.initialize()

        try:
            logger.info(
                "graph_execution_start",
                agent=self.__class__.__name__,
                initial_state_keys=list(initial_state.keys())
            )

            # Run graph
            final_state = await self.compiled_graph.ainvoke(initial_state)

            logger.info(
                "graph_execution_complete",
                agent=self.__class__.__name__,
                has_error=final_state.get("error") is not None
            )

            return final_state

        except Exception as e:
            logger.error(
                "graph_execution_failed",
                agent=self.__class__.__name__,
                error=str(e)
            )
            raise

    async def search_memory(
        self,
        collection: str,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> list:
        """
        Search memory (convenience method for nodes).

        Args:
            collection: Collection name
            query: Search query
            top_k: Number of results
            filters: Optional filters

        Returns:
            List of search results
        """
        if not self.enable_memory or not self.memory_manager:
            logger.warning("memory_disabled_returning_empty")
            return []

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
        """
        Save to memory (convenience method for nodes).

        Args:
            collection: Collection name
            content: Content to embed
            metadata: Metadata

        Returns:
            Document ID
        """
        if not self.enable_memory or not self.memory_manager:
            logger.warning("memory_disabled_skipping_save")
            return -1

        return await self.memory_manager.save(
            collection=collection,
            content=content,
            metadata=metadata
        )

    def add_step(self, state: Dict[str, Any], step_name: str) -> Dict[str, Any]:
        """
        Add step to tracking (convenience method).

        Args:
            state: Current state
            step_name: Name of completed step

        Returns:
            Updated state
        """
        if "steps_completed" not in state:
            state["steps_completed"] = []

        state["steps_completed"].append(step_name)

        logger.debug(
            "step_completed",
            agent=self.__class__.__name__,
            step=step_name,
            total_steps=len(state["steps_completed"])
        )

        return state

    def add_warning(self, state: Dict[str, Any], warning: str) -> Dict[str, Any]:
        """
        Add warning to state.

        Args:
            state: Current state
            warning: Warning message

        Returns:
            Updated state
        """
        if "warnings" not in state:
            state["warnings"] = []

        state["warnings"].append(warning)

        logger.warning(
            "graph_warning",
            agent=self.__class__.__name__,
            warning=warning
        )

        return state

    def set_error(self, state: Dict[str, Any], error: str) -> Dict[str, Any]:
        """
        Set error in state.

        Args:
            state: Current state
            error: Error message

        Returns:
            Updated state
        """
        state["error"] = error

        logger.error(
            "graph_error",
            agent=self.__class__.__name__,
            error=error
        )

        return state

    async def close(self):
        """Close resources (memory manager, etc.)."""
        if self.memory_manager:
            await self.memory_manager.close()

        logger.info("graph_closed", agent=self.__class__.__name__)
