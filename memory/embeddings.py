"""
Embedding Generation
===================

Generates vector embeddings for text using OpenAI's text-embedding-3-small model.
Includes batching, caching, and error handling.
"""

import os
import hashlib
import asyncio
from typing import List, Dict, Optional
from openai import AsyncOpenAI
import tiktoken
import structlog

logger = structlog.get_logger(__name__)


class EmbeddingGenerator:
    """
    Generates embeddings using OpenAI API with batching and caching.

    Features:
    - Batch processing for efficiency
    - Token counting and validation
    - Error handling and retries
    - Content hash caching
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        batch_size: int = 100,
        max_retries: int = 3
    ):
        """
        Initialize embedding generator.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Embedding model name
            dimensions: Vector dimensions
            batch_size: Max texts per API call
            max_retries: Retry attempts on failure
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required (OPENAI_API_KEY env var)")

        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size
        self.max_retries = max_retries

        self.client = AsyncOpenAI(api_key=self.api_key)
        self.encoding = tiktoken.encoding_for_model("text-embedding-3-small")

        # In-memory cache: content_hash -> embedding
        self._cache: Dict[str, List[float]] = {}

        logger.info(
            "embedding_generator_initialized",
            model=self.model,
            dimensions=self.dimensions,
            batch_size=self.batch_size
        )

    def _compute_hash(self, text: str) -> str:
        """Compute stable hash for text content."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]

    def count_tokens(self, text: str) -> int:
        """Count tokens in text (useful for cost estimation)."""
        return len(self.encoding.encode(text))

    async def generate_single(self, text: str, use_cache: bool = True) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed
            use_cache: Use in-memory cache

        Returns:
            Embedding vector (list of floats)
        """
        if not text or not text.strip():
            logger.warning("empty_text_provided")
            return [0.0] * self.dimensions

        # Check cache
        text_hash = self._compute_hash(text)
        if use_cache and text_hash in self._cache:
            logger.debug("embedding_cache_hit", text_preview=text[:50])
            return self._cache[text_hash]

        # Generate embedding
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimensions
            )

            embedding = response.data[0].embedding

            # Cache result
            if use_cache:
                self._cache[text_hash] = embedding

            logger.debug(
                "embedding_generated",
                text_preview=text[:50],
                tokens=self.count_tokens(text),
                dim=len(embedding)
            )

            return embedding

        except Exception as e:
            logger.error("embedding_generation_failed", error=str(e), text_preview=text[:50])
            raise

    async def generate_batch(
        self,
        texts: List[str],
        use_cache: bool = True,
        show_progress: bool = False
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (batched for efficiency).

        Args:
            texts: List of texts to embed
            use_cache: Use in-memory cache
            show_progress: Log progress updates

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        embeddings: List[Optional[List[float]]] = [None] * len(texts)
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        # Check cache first
        if use_cache:
            for i, text in enumerate(texts):
                text_hash = self._compute_hash(text)
                if text_hash in self._cache:
                    embeddings[i] = self._cache[text_hash]
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(text)
        else:
            uncached_indices = list(range(len(texts)))
            uncached_texts = texts

        if not uncached_texts:
            logger.info("all_embeddings_cached", total=len(texts))
            return embeddings  # type: ignore

        logger.info(
            "generating_batch_embeddings",
            total=len(texts),
            cached=len(texts) - len(uncached_texts),
            to_generate=len(uncached_texts)
        )

        # Process in batches
        for batch_start in range(0, len(uncached_texts), self.batch_size):
            batch_end = min(batch_start + self.batch_size, len(uncached_texts))
            batch_texts = uncached_texts[batch_start:batch_end]
            batch_indices = uncached_indices[batch_start:batch_end]

            if show_progress:
                logger.info(
                    "processing_batch",
                    batch=f"{batch_start}-{batch_end}",
                    total=len(uncached_texts)
                )

            try:
                # API call with retries
                for attempt in range(self.max_retries):
                    try:
                        response = await self.client.embeddings.create(
                            model=self.model,
                            input=batch_texts,
                            dimensions=self.dimensions
                        )

                        # Extract embeddings
                        for i, data in enumerate(response.data):
                            original_idx = batch_indices[i]
                            embedding = data.embedding
                            embeddings[original_idx] = embedding

                            # Cache result
                            if use_cache:
                                text_hash = self._compute_hash(batch_texts[i])
                                self._cache[text_hash] = embedding

                        break  # Success

                    except Exception as e:
                        if attempt < self.max_retries - 1:
                            wait_time = 2 ** attempt  # Exponential backoff
                            logger.warning(
                                "embedding_batch_retry",
                                attempt=attempt + 1,
                                wait_seconds=wait_time,
                                error=str(e)
                            )
                            await asyncio.sleep(wait_time)
                        else:
                            logger.error("embedding_batch_failed", error=str(e))
                            raise

            except Exception as e:
                logger.error("batch_processing_failed", batch=f"{batch_start}-{batch_end}", error=str(e))
                # Fill with zero vectors for failed batches
                for idx in batch_indices:
                    if embeddings[idx] is None:
                        embeddings[idx] = [0.0] * self.dimensions

        logger.info("batch_embeddings_complete", total=len(texts))
        return embeddings  # type: ignore

    async def estimate_cost(self, texts: List[str]) -> Dict[str, float]:
        """
        Estimate API cost for embedding generation.

        Args:
            texts: Texts to estimate cost for

        Returns:
            Dict with token count and estimated USD cost
        """
        total_tokens = sum(self.count_tokens(text) for text in texts)

        # OpenAI pricing: $0.020 per 1M tokens for text-embedding-3-small
        cost_per_million = 0.020
        estimated_cost = (total_tokens / 1_000_000) * cost_per_million

        return {
            "total_tokens": total_tokens,
            "estimated_usd": round(estimated_cost, 6),
            "text_count": len(texts),
            "avg_tokens_per_text": round(total_tokens / len(texts), 1) if texts else 0
        }

    def clear_cache(self):
        """Clear in-memory embedding cache."""
        cache_size = len(self._cache)
        self._cache.clear()
        logger.info("embedding_cache_cleared", entries_removed=cache_size)

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "cached_embeddings": len(self._cache),
            "cache_memory_mb": sum(len(v) * 4 for v in self._cache.values()) / (1024 * 1024)  # Rough estimate
        }


# Global instance (lazy initialized)
_embedding_generator: Optional[EmbeddingGenerator] = None


def get_embedding_generator() -> EmbeddingGenerator:
    """Get or create global embedding generator instance."""
    global _embedding_generator

    if _embedding_generator is None:
        _embedding_generator = EmbeddingGenerator(
            model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "1536")),
            batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "100"))
        )

    return _embedding_generator
