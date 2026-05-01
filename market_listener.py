"""
CryptoMinds 市场监听器

Agent 自动发现市场中的新任务：
- 轮询市场 API
- 过滤匹配的任务
- 自动接单（可配置）
"""

import os
import json
import time
import threading
from decimal import Decimal
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class MarketTask:
    """市场任务"""
    task_id: str
    task_type: str
    buyer_wallet: str
    amount: Decimal
    chain: str
    channel_id: str
    params: Dict = field(default_factory=dict)
    created_at: int = 0
    deadline: int = 0

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "buyer_wallet": self.buyer_wallet,
            "amount": str(self.amount),
            "chain": self.chain,
            "channel_id": self.channel_id,
            "params": self.params,
            "created_at": self.created_at,
            "deadline": self.deadline,
        }


class MarketListener:
    """
    市场监听器

    负责：
    1. 轮询市场 API
    2. 过滤匹配的任务
    3. 通知 Agent 守护进程
    """

    def __init__(
        self,
        market_url: str = None,
        poll_interval: float = 5.0,
    ):
        """
        Args:
            market_url: 市场 API 地址
            poll_interval: 轮询间隔（秒）
        """
        self.market_url = market_url or os.getenv("CRYPTOMINDS_MARKET", "http://localhost:3458")
        self.poll_interval = poll_interval

        # 已处理的任务
        self._processed_tasks: set = set()

        # 回调
        self._callbacks: List[Callable] = []

        # 线程
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ── 回调注册 ─────────────────────────────────────

    def on_task(self, callback: Callable) -> None:
        """
        注册任务回调

        当发现新任务时，调用回调函数。
        回调签名: callback(task: MarketTask) -> bool
        返回 True 表示接受任务
        """
        self._callbacks.append(callback)

    # ── 生命周期 ─────────────────────────────────────

    def start(self) -> None:
        """启动监听"""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        logger.info(f"市场监听器启动: {self.market_url}")

    def stop(self) -> None:
        """停止监听"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("市场监听器停止")

    # ── 主循环 ────────────────────────────────────────

    def _run_loop(self) -> None:
        """主循环"""
        while self._running:
            try:
                # 获取市场任务
                tasks = self._fetch_tasks()

                # 处理新任务
                for task in tasks:
                    if task.task_id not in self._processed_tasks:
                        self._handle_task(task)
                        self._processed_tasks.add(task.task_id)

                # 清理旧记录
                if len(self._processed_tasks) > 10000:
                    self._processed_tasks = set(list(self._processed_tasks)[-5000:])

            except Exception as e:
                logger.error(f"市场监听异常: {e}")

            time.sleep(self.poll_interval)

    def _fetch_tasks(self) -> List[MarketTask]:
        """获取市场任务"""
        try:
            import urllib.request
            import urllib.error

            url = f"{self.market_url}/api/v1/market/tasks"
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())

            tasks = []
            for item in data.get("tasks", []):
                tasks.append(MarketTask(
                    task_id=item.get("task_id", ""),
                    task_type=item.get("task_type", ""),
                    buyer_wallet=item.get("buyer_wallet", ""),
                    amount=Decimal(str(item.get("amount", 0))),
                    chain=item.get("chain", "bsc"),
                    channel_id=item.get("channel_id", ""),
                    params=item.get("params", {}),
                    created_at=item.get("created_at", 0),
                    deadline=item.get("deadline", 0),
                ))

            return tasks

        except urllib.error.URLError:
            # 市场不可用，返回空
            return []
        except Exception as e:
            logger.error(f"获取市场任务失败: {e}")
            return []

    def _handle_task(self, task: MarketTask) -> None:
        """处理任务"""
        logger.info(f"发现新任务: {task.task_id} ({task.task_type})")

        # 调用回调
        for callback in self._callbacks:
            try:
                accepted = callback(task)
                if accepted:
                    logger.info(f"任务已接受: {task.task_id}")
                    break
            except Exception as e:
                logger.error(f"回调异常: {e}")

    # ── 手动提交 ──────────────────────────────────────

    def submit_task(self, task: MarketTask) -> bool:
        """
        手动提交任务到市场

        Returns:
            是否成功
        """
        try:
            import urllib.request

            url = f"{self.market_url}/api/v1/market/tasks"
            data = json.dumps(task.to_dict()).encode()
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read())

            return result.get("ok", False)

        except Exception as e:
            logger.error(f"提交任务失败: {e}")
            return False


class TaskMatcher:
    """
    任务匹配器

    根据 Agent 能力过滤和匹配任务。
    """

    def __init__(
        self,
        task_types: List[str] = None,
        supported_chains: List[str] = None,
        min_amount: Decimal = None,
        max_amount: Decimal = None,
    ):
        self.task_types = task_types or []
        self.supported_chains = supported_chains or []
        self.min_amount = min_amount
        self.max_amount = max_amount

    def match(self, task: MarketTask) -> bool:
        """
        检查任务是否匹配

        Returns:
            是否匹配
        """
        # 检查任务类型
        if self.task_types and task.task_type not in self.task_types:
            return False

        # 检查链
        if self.supported_chains and task.chain not in self.supported_chains:
            return False

        # 检查金额
        if self.min_amount and task.amount < self.min_amount:
            return False

        if self.max_amount and task.amount > self.max_amount:
            return False

        return True


# ── 集成到守护进程 ────────────────────────────────────

def create_listener_for_daemon(daemon, market_url: str = None) -> MarketListener:
    """
    为守护进程创建市场监听器

    Args:
        daemon: AgentDaemon 实例
        market_url: 市场 API 地址

    Returns:
        MarketListener 实例
    """
    from agent_daemon import Task

    def on_new_task(market_task: MarketTask) -> bool:
        """处理新任务"""
        # 构造守护进程任务
        task = Task(
            task_id=market_task.task_id,
            task_type=market_task.task_type,
            buyer_wallet=market_task.buyer_wallet,
            seller_wallet=daemon.config.wallet,
            amount=market_task.amount,
            chain=market_task.chain,
            channel_id=market_task.channel_id,
            params=market_task.params,
        )

        # 提交到守护进程
        return daemon.submit_task(task)

    listener = MarketListener(market_url=market_url)
    listener.on_task(on_new_task)

    return listener


# ── 测试 ────────────────────────────────────────────

if __name__ == "__main__":
    print("=== 市场监听器测试 ===\n")

    # 创建监听器
    listener = MarketListener(
        market_url="http://localhost:3458",
        poll_interval=2.0,
    )

    # 注册回调
    def on_task(task: MarketTask) -> bool:
        print(f"收到任务: {task.task_id}")
        print(f"  类型: {task.task_type}")
        print(f"  金额: {task.amount}")
        print(f"  链: {task.chain}")
        return True

    listener.on_task(on_task)

    # 启动
    listener.start()
    print("监听器已启动，等待任务...\n")

    # 模拟运行
    time.sleep(5)

    # 停止
    listener.stop()
    print("\n监听器已停止")
