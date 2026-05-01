"""
争议窗口定时器

后台定时扫描 DISPUTED 状态的 escrow，自动解决过期争议。
"""

import time
import threading
from typing import Callable, Optional

from escrow.arbitration import ArbitrationEngine


class DisputeTimer:
    """争议窗口定时器"""

    def __init__(self, arbitration_engine: ArbitrationEngine,
                 escrow_store, check_interval: int = 300):
        self._engine = arbitration_engine
        self._store = escrow_store
        self._check_interval = check_interval  # seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while self._running:
            try:
                self._check_disputes()
            except Exception:
                pass
            time.sleep(self._check_interval)

    def _check_disputes(self):
        from settlement.escrow_state import EscrowState

        disputed_orders = self._store.get_by_state(EscrowState.DISPUTED)
        now = time.time()

        for order in disputed_orders:
            deadline = order.disputed_at + order.dispute_window_seconds
            if now >= deadline:
                self._engine.auto_resolve_timeout(order.escrow_id)

    def check_once(self) -> list:
        """单次检查, 返回解决的 escrow ID 列表"""
        from settlement.escrow_state import EscrowState

        resolved = []
        disputed_orders = self._store.get_by_state(EscrowState.DISPUTED)
        now = time.time()

        for order in disputed_orders:
            deadline = order.disputed_at + order.dispute_window_seconds
            if now >= deadline:
                result = self._engine.auto_resolve_timeout(order.escrow_id)
                if result.get("ok"):
                    resolved.append(order.escrow_id)

        return resolved