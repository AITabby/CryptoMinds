"""
测试托管存储
"""

import pytest
import tempfile
import os
from src.escrow.store import EscrowStore


class TestEscrowStore:
    """托管存储测试"""

    @pytest.fixture
    def store(self):
        """创建临时存储"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        store = EscrowStore(db_path=db_path)
        yield store
        os.unlink(db_path)

    def test_create_escrow(self, store):
        """测试创建托管"""
        escrow = store.create(
            buyer="0x1111111111111111111111111111111111111111",
            seller="0x2222222222222222222222222222222222222222",
            amount=1.0,
            token="BNB"
        )
        assert escrow["state"] == "created"
        assert escrow["buyer"] == "0x1111111111111111111111111111111111111111"
        assert escrow["amount"] == 1.0

    def test_get_escrow(self, store):
        """测试获取托管"""
        created = store.create(
            buyer="0x1111111111111111111111111111111111111111",
            seller="0x2222222222222222222222222222222222222222",
            amount=0.5
        )
        escrow_id = created["escrow_id"]

        retrieved = store.get(escrow_id)
        assert retrieved is not None
        assert retrieved["escrow_id"] == escrow_id

    def test_fund_escrow(self, store):
        """测试托管资金"""
        created = store.create(
            buyer="0x1111111111111111111111111111111111111111",
            seller="0x2222222222222222222222222222222222222222",
            amount=0.5
        )
        escrow_id = created["escrow_id"]

        funded = store.fund(escrow_id, "0xtx123")
        assert funded["state"] == "funded"
        assert funded["fund_tx_hash"] == "0xtx123"

    def test_deliver_escrow(self, store):
        """测试交付"""
        created = store.create(
            buyer="0x1111111111111111111111111111111111111111",
            seller="0x2222222222222222222222222222222222222222",
            amount=0.5
        )
        store.fund(created["escrow_id"], "0xtx123")

        delivered = store.deliver(created["escrow_id"], {"tx": "0xdel"})
        assert delivered["state"] == "delivered"

    def test_release_escrow(self, store):
        """测试释放"""
        created = store.create(
            buyer="0x1111111111111111111111111111111111111111",
            seller="0x2222222222222222222222222222222222222222",
            amount=0.5
        )
        store.fund(created["escrow_id"], "0xtx123")
        store.deliver(created["escrow_id"], {"tx": "0xdel"})

        released = store.release(created["escrow_id"])
        assert released["state"] == "released"

    def test_refund_escrow(self, store):
        """测试退款"""
        created = store.create(
            buyer="0x1111111111111111111111111111111111111111",
            seller="0x2222222222222222222222222222222222222222",
            amount=0.5
        )
        store.fund(created["escrow_id"], "0xtx123")

        refunded = store.refund(created["escrow_id"])
        assert refunded["state"] == "refunded"

    def test_list_by_buyer(self, store):
        """测试按买家查询"""
        store.create(
            buyer="0x1111111111111111111111111111111111111111",
            seller="0x2222222222222222222222222222222222222222",
            amount=0.5
        )
        store.create(
            buyer="0x1111111111111111111111111111111111111111",
            seller="0x3333333333333333333333333333333333333333",
            amount=0.3
        )

        escrows = store.list_by_buyer("0x1111111111111111111111111111111111111111")
        assert len(escrows) == 2

    def test_list_by_seller(self, store):
        """测试按卖家查询"""
        store.create(
            buyer="0x1111111111111111111111111111111111111111",
            seller="0x2222222222222222222222222222222222222222",
            amount=0.5
        )
        store.create(
            buyer="0x3333333333333333333333333333333333333333",
            seller="0x2222222222222222222222222222222222222222",
            amount=0.3
        )

        escrows = store.list_by_seller("0x2222222222222222222222222222222222222222")
        assert len(escrows) == 2

    def test_get_nonexistent(self, store):
        """测试获取不存在的托管"""
        escrow = store.get("nonexistent_id")
        assert escrow is None
