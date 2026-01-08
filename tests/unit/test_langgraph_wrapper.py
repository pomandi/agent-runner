"""
Unit tests for LangGraph wrapper activities.

Tests:
- check_caption_quality: Quality scoring logic
- check_caption_duplicate: Duplicate detection (without memory)
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestCheckCaptionQuality:
    """Test caption quality scoring."""

    @pytest.fixture
    def quality_checker(self):
        """Import the activity function."""
        from temporal_app.activities.langgraph_wrapper import check_caption_quality
        return check_caption_quality

    @pytest.mark.asyncio
    async def test_high_quality_dutch_caption(self, quality_checker):
        """Test high quality Dutch caption passes all checks."""
        caption = "✨ Nieuw binnen! De perfecte blazer voor jouw stijl 🛍️ #Pomandi #Fashion"

        result = await quality_checker(caption, "pomandi", "nl")

        assert result["quality_score"] >= 0.85
        assert result["passed"] is True
        assert result["auto_approved"] is True
        assert len(result["warnings"]) == 0

    @pytest.mark.asyncio
    async def test_high_quality_french_caption(self, quality_checker):
        """Test high quality French caption passes all checks."""
        caption = "✨ Nouveau! L'élégance à la française pour votre garde-robe 🇫🇷 #Costume #Mode"

        result = await quality_checker(caption, "costume", "fr")

        assert result["quality_score"] >= 0.85
        assert result["passed"] is True
        assert result["auto_approved"] is True

    @pytest.mark.asyncio
    async def test_missing_language_words(self, quality_checker):
        """Test caption without language-specific words gets penalized."""
        caption = "✨ Amazing product! Check it out 🛍️ #Pomandi"

        result = await quality_checker(caption, "pomandi", "nl")

        # Should lose 0.3 for missing Dutch words
        assert result["quality_score"] <= 0.70
        assert "Caption may not be in Dutch" in result["warnings"]

    @pytest.mark.asyncio
    async def test_missing_brand_mention(self, quality_checker):
        """Test caption without brand mention gets penalized."""
        caption = "✨ Nieuw binnen! Perfect voor jouw stijl 🛍️ #Fashion"

        result = await quality_checker(caption, "pomandi", "nl")

        # Should lose 0.2 for missing brand
        assert "Brand name not mentioned" in result["warnings"]

    @pytest.mark.asyncio
    async def test_too_short_caption(self, quality_checker):
        """Test short caption gets penalized."""
        caption = "Nieuw! Pomandi"

        result = await quality_checker(caption, "pomandi", "nl")

        assert "Caption too short" in result["warnings"]

    @pytest.mark.asyncio
    async def test_too_long_caption(self, quality_checker):
        """Test long caption gets penalized."""
        caption = "✨ Nieuw binnen bij Pomandi! " * 20 + "🛍️"

        result = await quality_checker(caption, "pomandi", "nl")

        assert "Caption too long" in result["warnings"]

    @pytest.mark.asyncio
    async def test_no_emoji_caption(self, quality_checker):
        """Test caption without emojis gets penalized."""
        caption = "Nieuw binnen bij Pomandi! Perfect voor jouw stijl. #Pomandi"

        result = await quality_checker(caption, "pomandi", "nl")

        assert "No emojis used" in result["warnings"]

    @pytest.mark.asyncio
    async def test_quality_threshold_boundary(self, quality_checker):
        """Test quality threshold boundaries."""
        # Caption that should be at boundary
        caption = "Nieuw! Perfect Pomandi item 🛍️"  # Short but has key elements

        result = await quality_checker(caption, "pomandi", "nl")

        # Should be passed but maybe not auto_approved
        assert result["passed"] == (result["quality_score"] >= 0.70)
        assert result["auto_approved"] == (result["quality_score"] >= 0.85)


class TestCheckCaptionDuplicate:
    """Test caption duplicate detection."""

    @pytest.fixture
    def duplicate_checker(self):
        """Import the activity function."""
        from temporal_app.activities.langgraph_wrapper import check_caption_duplicate
        return check_caption_duplicate

    @pytest.mark.asyncio
    async def test_duplicate_check_memory_disabled(self, duplicate_checker):
        """Test duplicate check when memory is disabled."""
        with patch.dict(os.environ, {"ENABLE_MEMORY": "false"}):
            result = await duplicate_checker("pomandi", "facebook", "Test caption")

        assert result["is_duplicate"] is False
        assert result["memory_enabled"] is False

    @pytest.mark.asyncio
    async def test_duplicate_check_no_duplicates(self, duplicate_checker):
        """Test duplicate check with no similar captions in memory."""
        mock_manager = AsyncMock()
        mock_manager.search.return_value = []

        with patch.dict(os.environ, {"ENABLE_MEMORY": "true"}):
            with patch("temporal_app.activities.langgraph_wrapper.get_memory_manager",
                      return_value=mock_manager):
                # Import fresh to get patched version
                from importlib import reload
                import temporal_app.activities.langgraph_wrapper as wrapper
                reload(wrapper)

                result = await wrapper.check_caption_duplicate(
                    "pomandi", "facebook", "Unique caption"
                )

        assert result["is_duplicate"] is False

    @pytest.mark.asyncio
    async def test_duplicate_check_high_similarity(self, duplicate_checker):
        """Test duplicate detection with high similarity match."""
        mock_manager = AsyncMock()
        mock_manager.search.return_value = [
            {
                "score": 0.95,
                "payload": {"caption_text": "Very similar caption"}
            }
        ]

        with patch.dict(os.environ, {"ENABLE_MEMORY": "true"}):
            with patch("temporal_app.activities.langgraph_wrapper.get_memory_manager",
                      return_value=mock_manager):
                from importlib import reload
                import temporal_app.activities.langgraph_wrapper as wrapper
                reload(wrapper)

                result = await wrapper.check_caption_duplicate(
                    "pomandi", "facebook", "Almost same caption"
                )

        assert result["is_duplicate"] is True
        assert result["similarity_score"] == 0.95


class TestQualityIntegration:
    """Integration tests for quality workflow."""

    @pytest.mark.asyncio
    async def test_pomandi_workflow_quality(self):
        """Test typical Pomandi caption through quality check."""
        from temporal_app.activities.langgraph_wrapper import check_caption_quality

        # Typical Pomandi caption
        caption = "✨ Nieuw binnen! Deze prachtige blazer is perfect voor jouw najaarslook 🍂 Shop nu bij Pomandi! 🛍️ #Pomandi #Fashion #Najaar"

        result = await check_caption_quality(caption, "pomandi", "nl")

        assert result["passed"] is True
        assert result["quality_score"] >= 0.70

    @pytest.mark.asyncio
    async def test_costume_workflow_quality(self):
        """Test typical Costume caption through quality check."""
        from temporal_app.activities.langgraph_wrapper import check_caption_quality

        # Typical Costume caption
        caption = "✨ Nouveau! Découvrez notre nouvelle collection d'automne 🍂 L'élégance à la française chez Costume 🇫🇷 #Costume #Mode #Automne"

        result = await check_caption_quality(caption, "costume", "fr")

        assert result["passed"] is True
        assert result["quality_score"] >= 0.70


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
