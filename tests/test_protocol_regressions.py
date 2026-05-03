#!/usr/bin/env python3
"""
Regression tests for protocol runtime edges.
"""
import os
import sys
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DIR)

# Set internal token and debug mode before importing api_server (module reads env at import)
os.environ["CRYPTOMINDS_INTERNAL_TOKEN"] = "test-token"
os.environ["CRYPTOMINDS_DEBUG"] = "true"

from agent_daemon import AgentConfig, Executor, Task
from reputation.record import TaskStatus
from task_closer import TaskCloser
from verification.base import TaskOutput
from escrow.models import EscrowOrder
from settlement.escrow_state import EscrowState


class ProtocolRegressionTests(unittest.TestCase):
    def test_task_output_to_dict_uses_instance_data(self):
        output = TaskOutput(task_type="data_delivery", data="hello")
        self.assertEqual(output.to_dict()["data"], "hello")

    def test_default_data_delivery_executor_imports_hashlib(self):
        executor = Executor(AgentConfig(
            agent_id="agent-1",
            wallet="0xseller",
            task_types=["data_delivery"],
            supported_chains=["mock"],
        ))
        task = Task(
            task_id="task-1",
            task_type="data_delivery",
            buyer_wallet="0xbuyer",
            seller_wallet="0xseller",
            amount=Decimal("0.01"),
            chain="mock",
            channel_id="mock",
            params={"data_type": "raw"},
        )

        result = executor.execute(task)

        self.assertNotIn("error", result)
        self.assertTrue(result["file_hash"])

    def test_settlement_failure_is_not_successful_completion(self):
        closer = TaskCloser()
        output = TaskOutput(
            task_type="token_delivery",
            seller_wallet="0xseller",
            tx_hash="0xabc123",
            token_address="0xtoken",
            token_amount="1",
        )

        result = closer.close_task(
            task_id="settlement-fail-task",
            task_type="token_delivery",
            buyer_wallet="0xbuyer",
            seller_wallet="0xseller",
            seller_agent_id="seller-1",
            chain="mock",
            amount=Decimal("0.01"),
            channel_id="missing-channel",
            task_output=output,
        )

        self.assertFalse(result.success)
        self.assertFalse(result.paid)
        self.assertIn("结算失败", result.error)

    def test_complete_task_api_requires_internal_token(self):
        from api_server import app

        client = app.test_client()
        resp = client.post("/api/v1/tasks/complete", json={
            "task_id": "task-1",
            "task_type": "token_delivery",
            "buyer_wallet": "0xbuyer",
            "seller_wallet": "0xseller",
            "seller_agent_id": "seller-1",
            "chain": "mock",
            "amount": "0.01",
            "status": TaskStatus.SETTLED.value,
        })

        self.assertEqual(resp.status_code, 403)

    def test_market_tasks_endpoint_round_trips(self):
        from api_server import app, MARKET_TASKS

        MARKET_TASKS.clear()
        client = app.test_client()
        # POST requires internal token
        headers = {"X-CryptoMinds-Internal-Token": "test-token"}
        create_resp = client.post("/api/v1/market/tasks", json={
            "task_id": "market-task-1",
            "task_type": "data_delivery",
            "buyer_wallet": "0xbuyer",
            "amount": "0.01",
            "chain": "mock",
            "channel_id": "mock",
            "params": {"data_type": "raw"},
        }, headers=headers)
        list_resp = client.get("/api/v1/market/tasks")

        self.assertEqual(create_resp.status_code, 201)
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(list_resp.get_json()["tasks"][0]["task_id"], "market-task-1")

    def test_pg_table_init_does_not_require_sqlite_executescript(self):
        import sys
        import types

        if "psycopg2" not in sys.modules:
            fake_psycopg2 = types.ModuleType("psycopg2")
            fake_pool = types.ModuleType("psycopg2.pool")
            fake_pool.SimpleConnectionPool = object
            fake_psycopg2.pool = fake_pool
            sys.modules["psycopg2"] = fake_psycopg2
            sys.modules["psycopg2.pool"] = fake_pool

        from data.pg_store import _ensure_tables

        class FakeCursor:
            def __init__(self):
                self.sqls = []

            def execute(self, sql):
                self.sqls.append(sql)

            def close(self):
                pass

        class FakePgConnection:
            def __init__(self):
                self.cursor_obj = FakeCursor()
                self.committed = False

            def cursor(self):
                return self.cursor_obj

            def commit(self):
                self.committed = True

        conn = FakePgConnection()
        _ensure_tables(conn)

        self.assertTrue(conn.committed)
        self.assertTrue(
            any("CREATE TABLE IF NOT EXISTS performance_records" in s for s in conn.cursor_obj.sqls),
            "expected performance_records CREATE TABLE in executed SQL"
        )

    def test_demo_session_key_placeholder_rejected_in_protected_env(self):
        import api_server

        old_debug = api_server.DEBUG_MODE
        old_env = dict(api_server._env_config)
        old_debug_env = os.environ.get("CRYPTOMINDS_DEBUG")
        try:
            api_server.DEBUG_MODE = False
            api_server._env_config["env"] = "staging"
            api_server._env_config["DEMO_MODE"] = False
            os.environ["CRYPTOMINDS_DEBUG"] = "false"

            with api_server.app.test_request_context("/"):
                response, status = api_server._reject_demo_private_key("DEMO")

            self.assertEqual(status, 400)
            self.assertIn("DEMO", response.get_json()["error"])
        finally:
            api_server.DEBUG_MODE = old_debug
            api_server._env_config.clear()
            api_server._env_config.update(old_env)
            if old_debug_env is None:
                os.environ.pop("CRYPTOMINDS_DEBUG", None)
            else:
                os.environ["CRYPTOMINDS_DEBUG"] = old_debug_env

    def test_bsc_release_requires_chain_confirmation_before_local_release(self):
        import api_server

        order = EscrowOrder(
            escrow_id="esc-bsc-1",
            task_id="t1",
            order_id="o1",
            buyer_wallet="0xBuyer",
            seller_wallet="0xSeller",
            seller_agent_id="seller-1",
            amount=Decimal("1"),
            channel_id="bsc-native",
            on_chain_order_id="0xabc",
            state=EscrowState.VERIFIED,
        )
        store = MagicMock()
        store.get.return_value = order

        channel = MagicMock()
        channel.escrow_sync_state.return_value = {"status_mapped": "delivered"}
        channel.escrow_prepare_contract_call.return_value = {"method": "confirm"}

        with patch.object(api_server, "_get_escrow_store", return_value=store), \
             patch.object(api_server, "_is_demo_mode", return_value=True), \
             patch("settlement.channels.bsc_native.BSCNativeChannel", return_value=channel):
            resp = api_server.app.test_client().post(
                "/api/v1/escrow/esc-bsc-1/release",
                headers={"X-CryptoMinds-Internal-Token": "test-token"},
                json={"wallet": "0xBuyer"},
            )

        self.assertEqual(resp.status_code, 202)
        self.assertEqual(order.state, EscrowState.VERIFIED)
        store.save.assert_not_called()

    def test_bsc_resolve_does_not_mutate_local_state_when_chain_fails(self):
        import api_server

        order = EscrowOrder(
            escrow_id="esc-bsc-2",
            task_id="t1",
            order_id="o1",
            buyer_wallet="0xBuyer",
            seller_wallet="0xSeller",
            seller_agent_id="seller-1",
            amount=Decimal("1"),
            channel_id="bsc-native",
            on_chain_order_id="0xabc",
            state=EscrowState.DISPUTED,
            disputed_at=1,
        )
        store = MagicMock()
        store.get.return_value = order
        record_store = MagicMock()

        failed = MagicMock(success=False, error="chain failed", tx_hash="")
        channel = MagicMock()
        channel.escrow_refund_on_chain.return_value = failed

        old_secret = os.environ.get("ADMIN_SECRET")
        old_admin_key = os.environ.get("ADMIN_PRIVATE_KEY")
        os.environ["ADMIN_SECRET"] = "x" * 40
        os.environ["ADMIN_PRIVATE_KEY"] = "0x" + "1" * 64
        try:
            with patch.object(api_server, "_get_escrow_store", return_value=store), \
                 patch.object(api_server, "_get_record_store", return_value=record_store), \
                 patch("settlement.channels.bsc_native.BSCNativeChannel", return_value=channel):
                resp = api_server.app.test_client().post(
                    "/api/v1/escrow/esc-bsc-2/resolve",
                    headers={"X-Admin-Secret": "x" * 40},
                    json={"decision": "buyer_win", "reason": "failed delivery"},
                )
        finally:
            if old_secret is None:
                os.environ.pop("ADMIN_SECRET", None)
            else:
                os.environ["ADMIN_SECRET"] = old_secret
            if old_admin_key is None:
                os.environ.pop("ADMIN_PRIVATE_KEY", None)
            else:
                os.environ["ADMIN_PRIVATE_KEY"] = old_admin_key

        self.assertEqual(resp.status_code, 502)
        self.assertEqual(order.state, EscrowState.DISPUTED)
        store.save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
