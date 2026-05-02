"""Tests for CryptoMinds SDK — urllib-based HTTP client."""
from unittest.mock import patch, MagicMock
import json
import pytest

from cryptominds_sdk import CryptoMinds


def _mock_urlopen_response(data_dict):
    """Create a mock urllib response that returns JSON data."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(data_dict).encode()
    return mock_resp


class TestCryptoMindsInit:

    def test_default_api_url(self):
        cm = CryptoMinds()
        assert cm.api_url == "http://localhost:3457"

    def test_custom_api_url_trailing_slash_removed(self):
        cm = CryptoMinds(api_url="http://custom:9999/", wallet="0xW")
        assert cm.api_url == "http://custom:9999"

    def test_wallet_and_name(self):
        cm = CryptoMinds(wallet="0xW", name="test-agent")
        assert cm.wallet == "0xW"
        assert cm.name == "test-agent"

    def test_default_name(self):
        cm = CryptoMinds(wallet="0xW")
        assert cm.name == "agent"


class TestCryptoMindsGet:

    def test_get_success(self):
        mock_resp = _mock_urlopen_response({"result": "ok"})
        cm = CryptoMinds(api_url="http://test:3457", wallet="0xW")
        with patch("cryptominds_sdk.urllib.request.urlopen", return_value=mock_resp):
            result = cm._get("/api/v1/test")
        assert result["result"] == "ok"


class TestCryptoMindsPost:

    def test_post_success(self):
        mock_resp = _mock_urlopen_response({"ok": True})
        cm = CryptoMinds(api_url="http://test:3457", wallet="0xW")
        with patch("cryptominds_sdk.urllib.request.urlopen", return_value=mock_resp):
            result = cm._post("/api/v1/test", {"key": "val"})
        assert result["ok"] is True


class TestSearchSellers:

    def test_search_with_query_filter(self):
        sellers = [
            {"name": "FastMeme", "desc": "meme scanner", "wallet": "0xA"},
            {"name": "SlowData", "desc": "data provider", "wallet": "0xB"},
        ]
        mock_resp = _mock_urlopen_response({"sellers": sellers})
        cm = CryptoMinds(api_url="http://test:3457", wallet="0xW")
        with patch("cryptominds_sdk.urllib.request.urlopen", return_value=mock_resp):
            result = cm.search_sellers("meme")
        assert len(result) == 1
        assert result[0]["name"] == "FastMeme"

    def test_search_no_query_returns_all(self):
        sellers = [{"name": "A"}, {"name": "B"}]
        mock_resp = _mock_urlopen_response({"sellers": sellers})
        cm = CryptoMinds(api_url="http://test:3457", wallet="0xW")
        with patch("cryptominds_sdk.urllib.request.urlopen", return_value=mock_resp):
            result = cm.search_sellers()
        assert len(result) == 2


class TestBuyerMethods:

    def test_create_order_requires_wallet(self):
        cm = CryptoMinds(api_url="http://test:3457")
        with pytest.raises(ValueError, match="未设置钱包"):
            cm.create_order("0xSELLER", 0.01)

    def test_create_order_success(self):
        mock_resp = _mock_urlopen_response({"orderId": "o1"})
        cm = CryptoMinds(api_url="http://test:3457", wallet="0xBUYER")
        with patch("cryptominds_sdk.urllib.request.urlopen", return_value=mock_resp):
            result = cm.create_order("0xSELLER", 0.01)
        assert "orderId" in result

    def test_auto_buy_requires_wallet(self):
        cm = CryptoMinds(api_url="http://test:3457")
        with pytest.raises(ValueError, match="未设置钱包"):
            cm.auto_buy(0.01)

    def test_auto_buy_success(self):
        mock_resp = _mock_urlopen_response({"ok": True})
        cm = CryptoMinds(api_url="http://test:3457", wallet="0xBUYER")
        with patch("cryptominds_sdk.urllib.request.urlopen", return_value=mock_resp):
            result = cm.auto_buy(0.01)
        assert result["ok"] is True

    def test_get_orders_requires_wallet(self):
        cm = CryptoMinds(api_url="http://test:3457")
        with pytest.raises(ValueError, match="未设置钱包"):
            cm.get_orders()

    def test_get_orders_success(self):
        mock_resp = _mock_urlopen_response({"orders": []})
        cm = CryptoMinds(api_url="http://test:3457", wallet="0xBUYER")
        with patch("cryptominds_sdk.urllib.request.urlopen", return_value=mock_resp):
            result = cm.get_orders()
        assert "orders" in result

    def test_confirm_purchase(self):
        mock_resp = _mock_urlopen_response({"confirmed": True})
        cm = CryptoMinds(api_url="http://test:3457", wallet="0xBUYER")
        with patch("cryptominds_sdk.urllib.request.urlopen", return_value=mock_resp):
            result = cm.confirm_purchase("p1", rating=5)
        assert result["confirmed"] is True


class TestSellerMethods:

    def test_register_seller_requires_wallet(self):
        cm = CryptoMinds(api_url="http://test:3457")
        with pytest.raises(ValueError, match="未设置钱包"):
            cm.register_seller("name", "desc", 0.01, "http://ep")

    def test_register_seller_success(self):
        mock_resp = _mock_urlopen_response({"registered": True})
        cm = CryptoMinds(api_url="http://test:3457", wallet="0xSELLER")
        with patch("cryptominds_sdk.urllib.request.urlopen", return_value=mock_resp):
            result = cm.register_seller("name", "desc", 0.01, "http://ep")
        assert result["registered"] is True

    def test_deposit_requires_wallet(self):
        cm = CryptoMinds(api_url="http://test:3457")
        with pytest.raises(ValueError, match="未设置钱包"):
            cm.deposit(0.01)

    def test_exit_market_requires_wallet(self):
        cm = CryptoMinds(api_url="http://test:3457")
        with pytest.raises(ValueError, match="未设置钱包"):
            cm.exit_market()

    def test_deliver_result(self):
        mock_resp = _mock_urlopen_response({"delivered": True})
        cm = CryptoMinds(api_url="http://test:3457", wallet="0xSELLER")
        with patch("cryptominds_sdk.urllib.request.urlopen", return_value=mock_resp):
            result = cm.deliver_result("o1", {"data": "result"})
        assert result["delivered"] is True


class TestGeneralMethods:

    def test_get_market(self):
        mock_resp = _mock_urlopen_response({"sellers": []})
        cm = CryptoMinds(api_url="http://test:3457", wallet="0xW")
        with patch("cryptominds_sdk.urllib.request.urlopen", return_value=mock_resp):
            result = cm.get_market()
        assert "sellers" in result

    def test_smart_route(self):
        mock_resp = _mock_urlopen_response({"route": "bsc"})
        cm = CryptoMinds(api_url="http://test:3457", wallet="0xW")
        with patch("cryptominds_sdk.urllib.request.urlopen", return_value=mock_resp):
            result = cm.smart_route("seller-1")
        assert "route" in result

    def test_health(self):
        mock_resp = _mock_urlopen_response({"status": "ok"})
        cm = CryptoMinds(api_url="http://test:3457", wallet="0xW")
        with patch("cryptominds_sdk.urllib.request.urlopen", return_value=mock_resp):
            result = cm.health()
        assert result["status"] == "ok"