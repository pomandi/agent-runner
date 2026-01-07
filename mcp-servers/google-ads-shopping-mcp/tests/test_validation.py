"""Tests for input validation."""
import pytest
from google_ads_shopping_mcp.security import (
    ValidationError,
    validate_campaign_name,
    validate_daily_budget,
    validate_country_code,
    validate_bidding_strategy,
    validate_ad_group_name,
    validate_campaign_id,
    validate_keywords,
    validate_product_groups
)


class TestCampaignNameValidation:
    def test_valid_campaign_name(self):
        assert validate_campaign_name("Summer Sale 2025")

    def test_empty_campaign_name(self):
        with pytest.raises(ValidationError):
            validate_campaign_name("")

    def test_too_long_campaign_name(self):
        with pytest.raises(ValidationError):
            validate_campaign_name("a" * 256)

    def test_invalid_characters(self):
        with pytest.raises(ValidationError):
            validate_campaign_name("Campaign <script>")


class TestBudgetValidation:
    def test_valid_budget(self):
        assert validate_daily_budget(50.0)
        assert validate_daily_budget(100)

    def test_zero_budget(self):
        with pytest.raises(ValidationError):
            validate_daily_budget(0)

    def test_negative_budget(self):
        with pytest.raises(ValidationError):
            validate_daily_budget(-10)

    def test_excessive_budget(self):
        with pytest.raises(ValidationError):
            validate_daily_budget(2000000)


class TestCountryCodeValidation:
    def test_valid_be(self):
        assert validate_country_code("BE")

    def test_valid_nl(self):
        assert validate_country_code("NL")

    def test_lowercase(self):
        assert validate_country_code("be")

    def test_invalid_country(self):
        with pytest.raises(ValidationError):
            validate_country_code("US")


class TestBiddingStrategyValidation:
    def test_valid_manual_cpc(self):
        assert validate_bidding_strategy("MANUAL_CPC")

    def test_valid_maximize_clicks(self):
        assert validate_bidding_strategy("MAXIMIZE_CLICKS")

    def test_invalid_strategy(self):
        with pytest.raises(ValidationError):
            validate_bidding_strategy("INVALID_STRATEGY")


class TestCampaignIdValidation:
    def test_valid_campaign_id(self):
        assert validate_campaign_id("12345")

    def test_invalid_non_numeric(self):
        with pytest.raises(ValidationError):
            validate_campaign_id("abc123")


class TestKeywordsValidation:
    def test_valid_keywords(self):
        assert validate_keywords(["gratis", "goedkoop"])

    def test_empty_list(self):
        with pytest.raises(ValidationError):
            validate_keywords([])

    def test_non_list(self):
        with pytest.raises(ValidationError):
            validate_keywords("not a list")

    def test_too_many_keywords(self):
        with pytest.raises(ValidationError):
            validate_keywords(["keyword"] * 6000)

    def test_keyword_too_long(self):
        with pytest.raises(ValidationError):
            validate_keywords(["a" * 100])

    def test_invalid_characters(self):
        with pytest.raises(ValidationError):
            validate_keywords(["valid", "<script>"])


class TestProductGroupsValidation:
    def test_valid_product_groups(self):
        groups = [
            {"dimension": "brand", "value": "Nike", "bid": 2.0}
        ]
        assert validate_product_groups(groups)

    def test_empty_list(self):
        with pytest.raises(ValidationError):
            validate_product_groups([])

    def test_invalid_dimension(self):
        groups = [
            {"dimension": "invalid_dimension", "value": "test"}
        ]
        with pytest.raises(ValidationError):
            validate_product_groups(groups)

    def test_missing_dimension(self):
        groups = [
            {"value": "Nike", "bid": 2.0}
        ]
        with pytest.raises(ValidationError):
            validate_product_groups(groups)
