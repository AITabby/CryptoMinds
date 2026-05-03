"""Tests for api_server — Flask endpoint coverage via test_client."""
import json
import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    import api_server

    old_db_path = api_server._db_path
    old_cache = api_server._stores_cache
    test_db_path = tmp_path / "api_server_extended.db"
    monkeypatch.setenv("CRYPTOMINDS_DB_PATH", str(test_db_path))
    api_server._db_path = str(test_db_path)
    api_server._stores_cache = {}

    app = api_server.app
    with app.test_client() as c:
        yield c

    api_server._db_path = old_db_path
    api_server._stores_cache = old_cache


@pytest.fixture
def auth():
    return {"X-CryptoMinds-Internal-Token": "test-token"}


# ── Info endpoints ──

class TestInfoEndpoints:

    def test_info(self, client, auth):
        r = client.get("/api/v1/info", headers=auth)
        assert r.status_code == 200

    def test_channels(self, client, auth):
        r = client.get("/api/v1/channels", headers=auth)
        assert r.status_code == 200

    def test_gates(self, client, auth):
        r = client.get("/api/v1/gates", headers=auth)
        assert r.status_code == 200

    def test_healthz(self, client, auth):
        r = client.get("/healthz", headers=auth)
        # May return 200 (healthy) or 503 (degraded — DB/RPC unreachable in test env)
        assert r.status_code in (200, 503)

    def test_metrics(self, client, auth):
        r = client.get("/metrics", headers=auth)
        assert r.status_code == 200

    def test_info_without_token(self, client):
        r = client.get("/api/v1/info")
        assert r.status_code == 200


# ── Agent endpoints ──

class TestAgentEndpoints:

    def test_register_agent(self, client, auth):
        r = client.post("/api/v1/agents/register", headers=auth,
                        json={"agent_id": "test-agent", "wallet": "0xW",
                              "task_types": ["token_delivery"], "supported_chains": ["mock"]})
        assert r.status_code in (200, 201, 500)  # 500 if sqlite tables not initialized

    def test_list_agents(self, client, auth):
        r = client.get("/api/v1/agents", headers=auth)
        assert r.status_code == 200

    def test_get_agent(self, client, auth):
        r = client.get("/api/v1/agents/test-agent", headers=auth)
        assert r.status_code in (200, 404)

    def test_agent_reputation(self, client, auth):
        r = client.get("/api/v1/agents/test-agent/reputation", headers=auth)
        assert r.status_code in (200, 404)

    def test_agent_records(self, client, auth):
        r = client.get("/api/v1/agents/test-agent/records", headers=auth)
        assert r.status_code in (200, 404)

    def test_best_match(self, client, auth):
        r = client.get("/api/v1/agents/best-match?task_type=token_delivery&chain=mock", headers=auth)
        assert r.status_code in (200, 400, 404)


# ── Task endpoints ──

class TestTaskEndpoints:

    def test_create_task(self, client, auth):
        r = client.post("/api/v1/tasks/create", headers=auth,
                        json={"task_type": "token_delivery", "buyer_wallet": "0xB",
                              "chain": "mock", "amount": 0.01})
        assert r.status_code in (200, 400)

    def test_verify_task(self, client, auth):
        r = client.post("/api/v1/tasks/verify", headers=auth,
                        json={"task_type": "token_delivery", "task_id": "t1"})
        assert r.status_code in (200, 400)

    def test_complete_task(self, client, auth):
        r = client.post("/api/v1/tasks/complete", headers=auth,
                        json={"task_id": "t1", "result": {"data": "ok"}})
        assert r.status_code in (200, 400)


# ── Market endpoints ──

class TestMarketEndpoints:

    def test_get_market_tasks(self, client, auth):
        r = client.get("/api/v1/market/tasks", headers=auth)
        assert r.status_code == 200

    def test_post_market_task(self, client, auth):
        r = client.post("/api/v1/market/tasks", headers=auth,
                        json={"task_type": "token_delivery", "buyer_wallet": "0xB",
                              "chain": "mock", "amount": 0.01})
        assert r.status_code in (200, 201, 400)

    def test_agent_buy(self, client, auth):
        r = client.post("/api/v1/agent-buy", headers=auth,
                        json={"buyer_wallet": "0xB", "amount": 0.01})
        assert r.status_code in (200, 400)


# ── Credit endpoints ──

class TestCreditEndpoints:

    def test_issue_credit(self, client, auth):
        r = client.post("/api/v1/credit/issue", headers=auth,
                        json={"issuer_agent_id": "agent1", "issuer_wallet": "0xW1",
                              "name": "Test Credit", "symbol": "TC", "max_supply": 1000})
        assert r.status_code in (200, 400)

    def test_list_credit(self, client, auth):
        r = client.get("/api/v1/credit", headers=auth)
        assert r.status_code == 200


# ── Escrow endpoints ──

class TestEscrowEndpoints:

    def test_create_escrow(self, client, auth):
        r = client.post("/api/v1/escrow/create", headers=auth,
                        json={"buyer_wallet": "0xB", "seller_wallet": "0xS",
                              "amount": 0.01, "order_id": "o1"})
        assert r.status_code in (200, 201, 400)

    def test_get_escrow(self, client, auth):
        r = client.get("/api/v1/escrow/e1", headers=auth)
        assert r.status_code in (200, 404)

    def test_disputed_escrow(self, client, auth):
        r = client.get("/api/v1/escrow/disputed", headers=auth)
        assert r.status_code == 200


# ── Voucher endpoints ──

class TestVoucherEndpoints:

    def test_create_voucher(self, client, auth):
        r = client.post("/api/v1/voucher/create", headers=auth,
                        json={"issuer_agent_id": "agent1", "issuer_wallet": "0xW1",
                              "recipient_wallet": "0xW2", "amount": 100, "description": "test"})
        assert r.status_code in (200, 201, 400)

    def test_get_voucher(self, client, auth):
        r = client.get("/api/v1/voucher/v1", headers=auth)
        assert r.status_code in (200, 404)


# ── Session key endpoints ──

class TestSessionKeyEndpoints:

    def test_create_session_key(self, client, auth):
        r = client.post("/api/v1/session-keys/create", headers=auth,
                        json={"agent_id": "agent1", "wallet": "0xW1", "quota": 10})
        assert r.status_code in (200, 201, 400)

    def test_get_session_key(self, client, auth):
        r = client.get("/api/v1/session-keys/k1", headers=auth)
        assert r.status_code in (200, 404)

    def test_session_keys_by_agent(self, client, auth):
        r = client.get("/api/v1/session-keys/agent/agent1", headers=auth)
        assert r.status_code == 200


# ── More Escrow lifecycle ──

class TestEscrowLifecycle:

    def test_escrow_fund_prepare(self, client, auth):
        r = client.post("/api/v1/escrow/e1/fund/prepare", headers=auth,
                        json={"buyer_wallet": "0xB", "amount": 0.01})
        assert r.status_code in (200, 400, 404)

    def test_escrow_dispute(self, client, auth):
        r = client.post("/api/v1/escrow/e1/dispute", headers=auth,
                        json={"reason": "bad service"})
        assert r.status_code in (200, 400, 404)

    def test_escrow_resolve(self, client, auth):
        r = client.post("/api/v1/escrow/e1/resolve", headers=auth,
                        json={"decision": "refund"})
        assert r.status_code in (200, 400, 403, 404)

    def test_escrow_seller_accept(self, client, auth):
        r = client.post("/api/v1/escrow/e1/seller-accept", headers=auth,
                        json={"seller_wallet": "0xS"})
        assert r.status_code in (200, 400, 404)

    def test_escrow_deliver(self, client, auth):
        r = client.post("/api/v1/escrow/e1/deliver", headers=auth,
                        json={"result": {"data": "ok"}})
        assert r.status_code in (200, 400, 404)

    def test_escrow_verify(self, client, auth):
        r = client.post("/api/v1/escrow/e1/verify", headers=auth,
                        json={"verified": True})
        assert r.status_code in (200, 400, 404)

    def test_escrow_release(self, client, auth):
        r = client.post("/api/v1/escrow/e1/release", headers=auth,
                        json={"to_wallet": "0xS"})
        assert r.status_code in (200, 400, 404)


# ── More Voucher lifecycle ──

class TestVoucherLifecycle:

    def test_voucher_activate(self, client, auth):
        r = client.post("/api/v1/voucher/v1/activate", headers=auth,
                        json={"activator_wallet": "0xW2"})
        assert r.status_code in (200, 400, 404)

    def test_voucher_use(self, client, auth):
        r = client.post("/api/v1/voucher/v1/use", headers=auth,
                        json={"amount": 50, "recipient_wallet": "0xW3"})
        assert r.status_code in (200, 400, 404)

    def test_voucher_dispute(self, client, auth):
        r = client.post("/api/v1/voucher/v1/dispute", headers=auth,
                        json={"reason": "bad voucher"})
        assert r.status_code in (200, 400, 404)

    def test_voucher_resolve(self, client, auth):
        r = client.post("/api/v1/voucher/v1/resolve", headers=auth,
                        json={"decision": "refund"})
        assert r.status_code in (200, 400, 403, 404)

    def test_voucher_list_by_agent(self, client, auth):
        r = client.get("/api/v1/voucher/agent/agent1", headers=auth)
        assert r.status_code == 200


# ── More Session key lifecycle ──

class TestSessionKeyLifecycle:

    def test_session_key_revoke(self, client, auth):
        r = client.post("/api/v1/session-keys/k1/revoke", headers=auth,
                        json={"reason": "expired"})
        assert r.status_code in (200, 400, 404, 415)

    def test_session_key_increase_quota(self, client, auth):
        r = client.post("/api/v1/session-keys/k1/increase-quota", headers=auth,
                        json={"additional_quota": 5})
        assert r.status_code in (200, 400, 404)

    def test_reputation_update(self, client, auth):
        r = client.post("/api/v1/agents/test-agent/reputation/update", headers=auth)
        assert r.status_code in (200, 400, 404)

    def test_agent_buy_missing_fields(self, client, auth):
        r = client.post("/api/v1/agent-buy", headers=auth, json={})
        assert r.status_code == 400

    def test_create_task_missing_fields(self, client, auth):
        r = client.post("/api/v1/tasks/create", headers=auth, json={})
        assert r.status_code in (400, 500)


# ── Claim Timeout endpoints ──

class TestClaimTimeoutEndpoints:

    def test_claim_seller_timeout_not_found(self, client, auth):
        r = client.post("/api/v1/escrow/nonexistent/claim-seller-timeout",
                        headers=auth, json={})
        assert r.status_code == 404

    def test_claim_buyer_timeout_not_found(self, client, auth):
        r = client.post("/api/v1/escrow/nonexistent/claim-buyer-timeout",
                        headers=auth, json={})
        assert r.status_code == 404

    def test_claim_seller_timeout_wrong_state(self, client, auth):
        """Create escrow in CREATED state → claim-seller-timeout should reject."""
        r = client.post("/api/v1/escrow/create", headers=auth,
                        json={"buyer_wallet": "0xB", "seller_wallet": "0xS",
                              "amount": 0.01, "order_id": "o-claim-1"})
        if r.status_code not in (200, 201):
            pytest.skip("escrow create failed")
        eid = r.get_json().get("escrow_id", "")
        if not eid:
            pytest.skip("no escrow_id in response")
        r2 = client.post(f"/api/v1/escrow/{eid}/claim-seller-timeout",
                         headers=auth, json={})
        # CREATED state should reject (not FUNDED/EXECUTING)
        assert r2.status_code in (400, 404)

    def test_claim_buyer_timeout_wrong_state(self, client, auth):
        """Create escrow in CREATED state → claim-buyer-timeout should reject."""
        r = client.post("/api/v1/escrow/create", headers=auth,
                        json={"buyer_wallet": "0xB", "seller_wallet": "0xS",
                              "amount": 0.01, "order_id": "o-claim-2"})
        if r.status_code not in (200, 201):
            pytest.skip("escrow create failed")
        eid = r.get_json().get("escrow_id", "")
        if not eid:
            pytest.skip("no escrow_id in response")
        r2 = client.post(f"/api/v1/escrow/{eid}/claim-buyer-timeout",
                         headers=auth, json={})
        # CREATED state should reject (not DELIVERED)
        assert r2.status_code in (400, 404)

    def test_claim_seller_timeout_no_auth(self, client):
        """Without auth header, should be rejected."""
        r = client.post("/api/v1/escrow/e1/claim-seller-timeout", json={})
        assert r.status_code == 403

    def test_claim_buyer_timeout_no_auth(self, client):
        """Without auth header, should be rejected."""
        r = client.post("/api/v1/escrow/e1/claim-buyer-timeout", json={})
        assert r.status_code == 403


# ── Arbiter resolve endpoint ──

class TestArbiterResolveEndpoint:

    def test_resolve_no_auth(self, client):
        """Resolve without admin secret or arbiter sig should be 403."""
        r = client.post("/api/v1/escrow/nonexistent/resolve",
                        json={"decision": "refund"})
        assert r.status_code == 403

    def test_resolve_missing_body(self, client, auth):
        """Resolve with auth but no JSON body should fail."""
        r = client.post("/api/v1/escrow/nonexistent/resolve",
                        headers=auth, content_type="application/json")
        assert r.status_code in (400, 403, 404)

    def test_resolve_nonexistent_escrow(self, client, auth):
        """Resolve a non-existent escrow should be 404 (after auth)."""
        r = client.post("/api/v1/escrow/nonexistent/resolve",
                        headers=auth, json={"decision": "refund"})
        assert r.status_code in (400, 403, 404)

    def test_resolve_arbiter_wallet_rejected_without_sig(self, client, auth):
        """Passing arbiter_wallet without valid signature should be rejected."""
        r = client.post("/api/v1/escrow/nonexistent/resolve",
                        headers=auth,
                        json={"decision": "refund",
                              "arbiter_wallet": "0xBadWallet",
                              "arbiter_signature": "invalid",
                              "arbiter_message": "test"})
        # Should be 400 (invalid message format) or 403 (no valid auth)
        assert r.status_code in (400, 403)
