"""
Escrow Watchdog — 自动触发超时订单的状态转换

后台线程定期扫描 FUNDED/EXECUTING/DELIVERED/DISPUTED 状态的 escrow，
检查 seller_timeout_at / buyer_timeout_at / dispute_window 是否已过期，
自动推进状态：seller timeout → REFUNDED_TIMEOUT，buyer timeout → EXPIRED，
dispute timeout → auto-resolve。

关键设计：链上优先。有链上订单时，先执行链上 claim，成功后再推进本地终态。
链上失败则保持原状态，仅记录 pending settlement 供后续重试。
"""
import logging
import time
import threading

logger = logging.getLogger(__name__)


class EscrowWatchdog:
    """Escrow 超时看门狗"""

    def __init__(self, escrow_store, record_store=None, agent_registry=None, check_interval: int = 60):
        self._store = escrow_store
        self._record_store = record_store
        self._agent_registry = agent_registry
        self._check_interval = check_interval
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("EscrowWatchdog started (interval=%ds)", self._check_interval)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("EscrowWatchdog stopped")

    def _loop(self):
        while self._running:
            try:
                self._check_seller_timeouts()
                self._check_buyer_timeouts()
                self._check_dispute_timeouts()
            except Exception as e:
                logger.error("watchdog check error: %s", e)
            time.sleep(self._check_interval)

    def _check_seller_timeouts(self):
        from settlement.escrow_state import EscrowState, EscrowStateMachine, InvalidTransitionError

        now = int(time.time())
        for state in (EscrowState.FUNDED, EscrowState.EXECUTING):
            for order in self._store.get_by_state(state):
                if order.seller_timeout_at and now >= order.seller_timeout_at:
                    self._trigger_seller_timeout(order)

    def _check_buyer_timeouts(self):
        from settlement.escrow_state import EscrowState, EscrowStateMachine, InvalidTransitionError

        now = int(time.time())
        for order in self._store.get_by_state(EscrowState.DELIVERED):
            if order.buyer_timeout_at and now >= order.buyer_timeout_at:
                self._trigger_buyer_timeout(order)

    def _check_dispute_timeouts(self):
        from settlement.escrow_state import EscrowState
        from escrow.arbitration import ArbitrationEngine

        now = int(time.time())
        for order in self._store.get_by_state(EscrowState.DISPUTED):
            if order.disputed_at and order.dispute_window_seconds:
                deadline = order.disputed_at + order.dispute_window_seconds
                if now >= deadline:
                    try:
                        if order.channel_id == "bsc-native" and order.on_chain_order_id:
                            decision = self._auto_resolution_decision(order)
                            if decision == "split":
                                logger.warning(
                                    "watchdog: bsc-native split auto-resolution unsupported for %s; keeping disputed",
                                    order.escrow_id,
                                )
                                order.chain_synced = False
                                self._store.save(order)
                                continue
                            if not self._try_chain_arbitration(order, decision):
                                logger.warning(
                                    "watchdog: on-chain dispute resolution failed for %s, keeping disputed",
                                    order.escrow_id,
                                )
                                order.chain_synced = False
                                self._store.save(order)
                                continue

                        if not self._record_store or not self._agent_registry:
                            logger.warning(
                                "watchdog: arbitration dependencies unavailable for %s; keeping disputed",
                                order.escrow_id,
                            )
                            continue
                        engine = ArbitrationEngine(self._store, self._record_store, self._agent_registry)
                        result = engine.auto_resolve_timeout(order.escrow_id)
                        if result.get("ok"):
                            updated = self._store.get(order.escrow_id) or order
                            updated.chain_synced = True
                            self._store.save(updated)
                        logger.info("watchdog: auto-resolved dispute %s", order.escrow_id)
                    except Exception as e:
                        logger.error("watchdog: dispute resolve failed for %s: %s", order.escrow_id, e)

    def _auto_resolution_decision(self, order) -> str:
        """Return buyer_win/seller_win/split from stored arbitration weights."""
        buyer_weight = getattr(order, "arbitration_weight_buyer", 0) or 0
        seller_weight = getattr(order, "arbitration_weight_seller", 0) or 0
        if seller_weight > buyer_weight:
            return "seller_win"
        if buyer_weight > seller_weight:
            return "buyer_win"
        return "split"

    def _trigger_seller_timeout(self, order):
        from settlement.escrow_state import EscrowStateMachine, InvalidTransitionError

        try:
            # Chain first: if there's an on-chain component, execute claim before changing local state
            needs_chain = order.channel_id == "bsc-native" and order.on_chain_order_id
            if needs_chain:
                chain_ok = self._try_chain_claim(order, "claimSellerTimeout")
                if not chain_ok:
                    logger.warning("watchdog: on-chain claim failed for %s, keeping original state (pending settlement)", order.escrow_id)
                    order.chain_synced = False
                    self._store.save(order)
                    return

            sm = EscrowStateMachine(order.state)
            sm.transition("seller_timeout", timestamp=int(time.time()),
                          actor="system", reason="seller delivery timeout (watchdog)")
            order.state = sm.state
            order.chain_synced = True
            self._store.save(order)
            logger.info("watchdog: seller timeout triggered for %s → %s", order.escrow_id, order.state.value)

        except InvalidTransitionError as e:
            logger.warning("watchdog: seller timeout invalid for %s: %s", order.escrow_id, e)

    def _trigger_buyer_timeout(self, order):
        from settlement.escrow_state import EscrowStateMachine, InvalidTransitionError

        try:
            # Chain first: if there's an on-chain component, execute claim before changing local state
            needs_chain = order.channel_id == "bsc-native" and order.on_chain_order_id
            if needs_chain:
                chain_ok = self._try_chain_claim(order, "claimBuyerTimeout")
                if not chain_ok:
                    logger.warning("watchdog: on-chain claim failed for %s, keeping original state (pending settlement)", order.escrow_id)
                    order.chain_synced = False
                    self._store.save(order)
                    return

            sm = EscrowStateMachine(order.state)
            sm.transition("buyer_timeout", timestamp=int(time.time()),
                          actor="system", reason="buyer confirmation timeout (watchdog)")
            order.state = sm.state
            order.chain_synced = True
            self._store.save(order)
            logger.info("watchdog: buyer timeout triggered for %s → %s", order.escrow_id, order.state.value)

        except InvalidTransitionError as e:
            logger.warning("watchdog: buyer timeout invalid for %s: %s", order.escrow_id, e)

    def _try_chain_claim(self, order, action) -> bool:
        """Execute on-chain timeout claim via BSC channel. Returns True on success."""
        if order.channel_id != "bsc-native" or not order.on_chain_order_id:
            return True  # no on-chain component, consider synced
        try:
            import os
            admin_key = os.getenv("ADMIN_PRIVATE_KEY", "")
            if not admin_key:
                logger.warning("watchdog: ADMIN_PRIVATE_KEY not set, cannot execute on-chain %s for %s",
                               action, order.escrow_id)
                return False

            if not admin_key.startswith("0x"):
                admin_key = "0x" + admin_key

            from settlement.channels.bsc_native import BSCNativeChannel
            channel = BSCNativeChannel()
            result = channel.escrow_prepare_contract_call(
                action=action,
                on_chain_order_id=order.on_chain_order_id,
            )
            if not result.get("method") == action:
                logger.warning("watchdog: unexpected prepare result for %s: %s", order.escrow_id, result)
                return False

            # Execute the on-chain claim
            from web3 import Web3
            contract_address = result["contract_address"]
            abi = result["abi"]
            admin_account = channel.w3.eth.account.from_key(admin_key)
            tx = channel.w3.eth.contract(
                address=Web3.to_checksum_address(contract_address),
                abi=abi,
            ).functions[action](Web3.to_bytes(hexstr=order.on_chain_order_id)
                                if order.on_chain_order_id.startswith("0x")
                                else Web3.to_bytes(text=order.on_chain_order_id)
            ).build_transaction({
                'from': admin_account.address,
                'nonce': channel.w3.eth.get_transaction_count(admin_account.address),
                'gas': 100000,
                'gasPrice': channel.w3.eth.gas_price,
                'chainId': channel.chain_id,
            })

            signed = channel.w3.eth.account.sign_transaction(tx, admin_key)
            raw_tx = getattr(signed, 'raw_transaction', None) or getattr(signed, 'rawTransaction')
            tx_hash = channel.w3.eth.send_raw_transaction(raw_tx)
            receipt = channel.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

            if receipt.status == 1:
                logger.info("watchdog: on-chain %s executed for %s (tx: %s)",
                            action, order.escrow_id, tx_hash.hex())
                return True
            else:
                logger.error("watchdog: on-chain %s reverted for %s", action, order.escrow_id)
                return False

        except Exception as e:
            logger.warning("watchdog: on-chain claim failed for %s: %s", order.escrow_id, e)
            return False

    def _try_chain_arbitration(self, order, decision: str) -> bool:
        """Execute on-chain dispute arbitration before local auto-resolution."""
        try:
            import os
            admin_key = os.getenv("ADMIN_PRIVATE_KEY", "")
            if not admin_key:
                logger.warning("watchdog: ADMIN_PRIVATE_KEY not set, cannot arbitrate %s", order.escrow_id)
                return False

            from settlement.channels.bsc_native import BSCNativeChannel
            channel = BSCNativeChannel()
            if decision == "buyer_win":
                result = channel.escrow_refund_on_chain(
                    escrow_id=order.escrow_id,
                    on_chain_order_id=order.on_chain_order_id,
                    reason="auto: dispute window expired, buyer reputation higher",
                    admin_private_key=admin_key,
                )
            elif decision == "seller_win":
                result = channel.escrow_confirm_on_chain(
                    escrow_id=order.escrow_id,
                    on_chain_order_id=order.on_chain_order_id,
                    admin_private_key=admin_key,
                )
            else:
                return False

            if result.success:
                logger.info(
                    "watchdog: on-chain dispute arbitration executed for %s (tx: %s)",
                    order.escrow_id,
                    result.tx_hash,
                )
                return True
            logger.warning("watchdog: on-chain dispute arbitration failed for %s: %s", order.escrow_id, result.error)
            return False
        except Exception as e:
            logger.warning("watchdog: on-chain dispute arbitration failed for %s: %s", order.escrow_id, e)
            return False

    def check_once(self) -> list:
        """Single check, returns list of triggered escrow IDs."""
        triggered = []

        from settlement.escrow_state import EscrowState, EscrowStateMachine, InvalidTransitionError

        now = int(time.time())
        for state in (EscrowState.FUNDED, EscrowState.EXECUTING):
            for order in self._store.get_by_state(state):
                if order.seller_timeout_at and now >= order.seller_timeout_at:
                    triggered.append(order.escrow_id)

        for order in self._store.get_by_state(EscrowState.DELIVERED):
            if order.buyer_timeout_at and now >= order.buyer_timeout_at:
                triggered.append(order.escrow_id)

        return triggered
