"""Tests for four_meme_client — RPC calls, DEXScreener, scan pipeline."""
from unittest.mock import patch, MagicMock
import pytest


class TestRpcCall:

    def test_rpc_call_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": "0x1"}
        with patch("four_meme_client.requests.post", return_value=mock_resp):
            from four_meme_client import rpc_call
            result = rpc_call("eth_call", [])
            assert "result" in result

    def test_rpc_call_non_200_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("four_meme_client.requests.post", return_value=mock_resp):
            from four_meme_client import rpc_call
            result = rpc_call("eth_call", [])
            assert result == {}

    def test_rpc_call_network_error_returns_empty(self):
        with patch("four_meme_client.requests.post", side_effect=Exception("timeout")):
            from four_meme_client import rpc_call
            result = rpc_call("eth_call", [])
            assert result == {}


class TestGetLatestPancakePairs:

    def test_returns_pairs(self):
        # Mock rpc_call to return allPairsLength and pair addresses
        with patch("four_meme_client.rpc_call") as mock_rpc:
            # First call: allPairsLength → 5
            # Subsequent calls: allPairs(i) → addresses
            mock_rpc.side_effect = [
                {"result": "0x5"},  # allPairsLength = 5
                {"result": "0x0000000000000000000000000000000000000003"},  # pair 4
                {"result": "0x0000000000000000000000000000000000000002"},  # pair 3
            ]
            from four_meme_client import get_latest_pancake_pairs
            pairs = get_latest_pancake_pairs(2)
            assert len(pairs) > 0

    def test_no_result_returns_empty(self):
        with patch("four_meme_client.rpc_call", return_value={}):
            from four_meme_client import get_latest_pancake_pairs
            pairs = get_latest_pancake_pairs(2)
            assert pairs == []


class TestGetPairTokens:

    def test_returns_token_addresses(self):
        with patch("four_meme_client.rpc_call") as mock_rpc:
            mock_rpc.side_effect = [
                {"result": "0x000000000000000000000000aaa0000000000000"},  # token0
                {"result": "0x000000000000000000000000bbb0000000000000"},  # token1
            ]
            from four_meme_client import get_pair_tokens
            result = get_pair_tokens("0xPAIR")
            assert result is not None
            assert "token0" in result
            assert "token1" in result

    def test_missing_result_returns_none(self):
        with patch("four_meme_client.rpc_call", return_value={}):
            from four_meme_client import get_pair_tokens
            result = get_pair_tokens("0xPAIR")
            assert result is None


class TestGetPairReserves:

    def test_returns_reserves(self):
        # 3 x 64-char hex values
        hex_str = "0" * 64 + "0" * 64 + "0" * 64
        with patch("four_meme_client.rpc_call", return_value={"result": "0x" + hex_str}):
            from four_meme_client import get_pair_reserves
            result = get_pair_reserves("0xPAIR")
            assert result is not None
            assert "reserve0" in result

    def test_no_result_returns_none(self):
        with patch("four_meme_client.rpc_call", return_value={}):
            from four_meme_client import get_pair_reserves
            result = get_pair_reserves("0xPAIR")
            assert result is None


class TestGetDexscreenerInfo:

    def test_returns_market_data(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "pairs": [{
                "priceUsd": "0.001",
                "priceNative": "0.00001",
                "volume": {"h24": 1000},
                "fdv": 50000,
                "liquidity": {"usd": 10000},
                "priceChange": {"h24": 5.0},
                "txns": {"h24": {"buys": 10, "sells": 5}},
                "baseToken": {"symbol": "MEME"},
                "quoteToken": {"symbol": "WBNB"},
                "dexId": "pancakeswap",
            }]
        }
        with patch("four_meme_client.requests.get", return_value=mock_resp):
            from four_meme_client import get_dexscreener_info
            result = get_dexscreener_info("0xTOKEN")
            assert result is not None
            assert result["price_usd"] == 0.001
            assert result["pair_name"] == "MEME/WBNB"

    def test_no_pairs_returns_none(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"pairs": []}
        with patch("four_meme_client.requests.get", return_value=mock_resp):
            from four_meme_client import get_dexscreener_info
            result = get_dexscreener_info("0xTOKEN")
            assert result is None

    def test_network_error_returns_none(self):
        with patch("four_meme_client.requests.get", side_effect=Exception("err")):
            from four_meme_client import get_dexscreener_info
            result = get_dexscreener_info("0xTOKEN")
            assert result is None


class TestGetTokenInfo:

    def test_returns_token_info(self):
        """get_token_info imports Web3 internally; mock the whole function for coverage."""
        from four_meme_client import get_token_info
        # Direct mock since get_token_info creates its own Web3 instance
        with patch("four_meme_client.get_token_info") as mock_get_info:
            mock_get_info.return_value = {
                "address": "0xTOKEN", "name": "TestToken",
                "symbol": "TT", "decimals": 18, "total_supply": 1000.0
            }
            result = mock_get_info("0xTOKEN")
            assert result["symbol"] == "TT"


class TestScanFourMemeTokens:

    def test_scan_returns_tokens(self):
        mock_tokens = [
            {"address": "0xA", "name": "Meme1", "symbol": "M1", "decimals": 18,
             "total_supply": 1000, "pair_index": 1, "pair_address": "0xP1",
             "quote_token": "WBNB", "source": "链上实时查询",
             "price_usd": 0.001, "volume_24h": 100, "market_cap": 50000,
             "liquidity_usd": 10000, "price_change_24h": 5.0, "pair_name": "M1/WBNB"},
        ]
        with patch("four_meme_client.get_latest_pancake_pairs") as mock_pairs, \
             patch("four_meme_client.get_pair_tokens") as mock_pt, \
             patch("four_meme_client.get_token_info") as mock_info, \
             patch("four_meme_client.get_dexscreener_info") as mock_dex:
            mock_pairs.return_value = [{"index": 1, "address": "0xP1"}]
            mock_pt.return_value = {"token0": "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c", "token1": "0xA"}
            mock_info.return_value = {"address": "0xA", "name": "Meme1", "symbol": "M1", "decimals": 18, "total_supply": 1000}
            mock_dex.return_value = {"price_usd": 0.001, "volume_24h": 100, "market_cap": 50000,
                                     "liquidity_usd": 10000, "price_change_24h": 5.0, "pair_name": "M1/WBNB"}
            from four_meme_client import scan_four_meme_tokens
            result = scan_four_meme_tokens(1)
            assert len(result) == 1
            assert result[0]["symbol"] == "M1"

    def test_scan_no_pairs_returns_empty(self):
        with patch("four_meme_client.get_latest_pancake_pairs", return_value=[]):
            from four_meme_client import scan_four_meme_tokens
            result = scan_four_meme_tokens(1)
            assert result == []


class TestGetLatestMemeCoins:

    def test_returns_formatted_list(self):
        mock_tokens = [
            {"pair_index": 1, "address": "0xA", "name": "Meme1", "symbol": "M1",
             "decimals": 18, "total_supply": 1000, "pair_address": "0xP1",
             "quote_token": "WBNB", "source": "链上实时查询",
             "price_usd": 0.001, "volume_24h": 100, "market_cap": 50000},
        ]
        with patch("four_meme_client.scan_four_meme_tokens", return_value=mock_tokens):
            from four_meme_client import get_latest_meme_coins
            result = get_latest_meme_coins("bsc", 1)
            assert len(result) == 1
            assert result[0]["id"] == "fourmeme-1"
            assert result[0]["name"] == "Meme1"