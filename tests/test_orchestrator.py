"""Tests for orchestrator — search, pick, buy (mocked HTTP)."""
from unittest.mock import patch, MagicMock
from decimal import Decimal
import pytest

from orchestrator import search_sellers, pick_seller, buy_tokens


MOCK_SELLERS = [
    {"name": "Alpha", "wallet": "0xA", "deposit": 10, "totalOrders": 50,
     "rating": 4.5, "feeRate": 0.005, "activeOrders": 2, "desc": "fast delivery"},
    {"name": "Beta", "wallet": "0xB", "deposit": 5, "totalOrders": 20,
     "rating": 3.0, "feeRate": 0.003, "activeOrders": 0, "desc": "cheap"},
]


class TestSearchSellers:

    def test_search_returns_sellers(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"sellers": MOCK_SELLERS}
        with patch("requests.get", return_value=mock_resp):
            result = search_sellers()
        assert len(result) == 2

    def test_search_with_query_filter(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"sellers": MOCK_SELLERS}
        with patch("requests.get", return_value=mock_resp):
            result = search_sellers(query="fast")
        assert len(result) == 1
        assert result[0]["name"] == "Alpha"

    def test_search_non_200_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("requests.get", return_value=mock_resp):
            assert search_sellers() == []

    def test_search_network_error_returns_empty(self):
        with patch("requests.get", side_effect=Exception("timeout")):
            assert search_sellers() == []

    def test_sort_by_rating(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"sellers": MOCK_SELLERS}
        with patch("requests.get", return_value=mock_resp):
            result = search_sellers(sort_by="rating")
        assert result[0]["rating"] >= result[1]["rating"]

    def test_sort_by_price(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"sellers": MOCK_SELLERS}
        with patch("requests.get", return_value=mock_resp):
            result = search_sellers(sort_by="price")
        assert result[0]["feeRate"] <= result[1]["feeRate"]


class TestPickSeller:

    def test_pick_eligible_seller(self):
        seller = pick_seller(MOCK_SELLERS, 0.01)
        assert seller is not None
        assert seller["_quota"] >= 0.01

    def test_no_eligible_seller(self):
        # All sellers have too small quota for 100 BNB
        result = pick_seller(MOCK_SELLERS, 100)
        assert result is None

    def test_zero_deposit_not_eligible(self):
        sellers = [{"name": "Free", "wallet": "0x0", "deposit": 0,
                     "totalOrders": 0, "rating": 0, "feeRate": 0, "activeOrders": 0}]
        assert pick_seller(sellers, 0.01) is None

    def test_single_eligible(self):
        sellers = [{"name": "Solo", "wallet": "0xS", "deposit": 1,
                     "totalOrders": 10, "rating": 4.0, "feeRate": 0.005, "activeOrders": 0}]
        result = pick_seller(sellers, 0.01)
        assert result is not None
        assert result["name"] == "Solo"


class TestBuyTokens:

    def test_unknown_buyer_returns_error(self):
        with patch("config.load_wallets", return_value={}):
            result = buy_tokens("unknown", 0.01)
        assert "error" in result

    def test_no_sellers_returns_error(self):
        wallets = {"buyer": {"address": "0xBUY", "private_key": "0xKEY"}}
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("config.load_wallets", return_value=wallets), \
             patch("requests.get", return_value=mock_resp):
            result = buy_tokens("buyer", 0.01)
        assert "error" in result