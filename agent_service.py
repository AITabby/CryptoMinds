"""
CryptoMinds Agent 服务

完整的 Agent 服务，整合：
- 守护进程（任务执行）
- 市场监听（任务发现）
- 闭环处理（验证+结算）
"""

import os
import json
import time
import signal
import threading
from decimal import Decimal
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
import logging

from logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

from scripts.env_loader import load_env
_env_config = load_env()

from agent_daemon import AgentDaemon, AgentConfig, Task, AgentState
from market_listener import MarketListener, TaskMatcher, MarketTask
from task_closer import TaskCloser, EscrowManager


@dataclass
class AgentServiceConfig:
    """Agent 服务配置"""
    # 基本信息
    agent_id: str
    wallet: str
    private_key: str = ""

    # 能力
    task_types: List[str] = None
    supported_chains: List[str] = None

    # 策略
    auto_accept: bool = True
    max_concurrent_tasks: int = 3
    min_amount: Decimal = Decimal("0.001")
    max_amount: Decimal = Decimal("1.0")
    task_timeout_seconds: int = 300

    # 市场
    market_url: str = "http://localhost:3458"
    poll_interval: float = 5.0

    # 执行器
    executor_endpoint: str = ""
    executor_module: str = ""


class AgentService:
    """
    Agent 服务

    完整的 Agent 运行时：
    1. 市场监听 - 发现新任务
    2. 任务匹配 - 过滤适合的任务
    3. 守护进程 - 执行任务
    4. 闭环处理 - 验证+结算
    """

    def __init__(self, config: AgentServiceConfig):
        self.config = config

        # 守护进程
        self.daemon = AgentDaemon(AgentConfig(
            agent_id=config.agent_id,
            wallet=config.wallet,
            private_key=config.private_key,
            task_types=config.task_types or [],
            supported_chains=config.supported_chains or [],
            auto_accept=config.auto_accept,
            max_concurrent_tasks=config.max_concurrent_tasks,
            min_amount=config.min_amount,
            max_amount=config.max_amount,
            task_timeout_seconds=config.task_timeout_seconds,
            executor_endpoint=config.executor_endpoint,
            executor_module=config.executor_module,
        ))

        # 市场监听
        self.listener = MarketListener(
            market_url=config.market_url,
            poll_interval=config.poll_interval,
        )

        # 任务匹配器
        self.matcher = TaskMatcher(
            task_types=config.task_types,
            supported_chains=config.supported_chains,
            min_amount=config.min_amount,
            max_amount=config.max_amount,
        )

        # 闭环处理器
        self.closer = TaskCloser()

        # 注册回调
        self._setup_callbacks()

        # 状态
        self._running = False

    def _setup_callbacks(self) -> None:
        """设置回调"""
        # 市场监听回调
        def on_market_task(task: MarketTask) -> bool:
            # 检查是否匹配
            if not self.matcher.match(task):
                logger.debug(f"任务不匹配: {task.task_id}")
                return False

            # 构造守护进程任务
            daemon_task = Task(
                task_id=task.task_id,
                task_type=task.task_type,
                buyer_wallet=task.buyer_wallet,
                seller_wallet=self.config.wallet,
                amount=task.amount,
                chain=task.chain,
                channel_id=task.channel_id,
                params=task.params,
            )

            # 提交到守护进程
            return self.daemon.submit_task(daemon_task)

        self.listener.on_task(on_market_task)

    # ── 生命周期 ─────────────────────────────────────

    def start(self) -> None:
        """启动服务"""
        if self._running:
            logger.warning("服务已在运行")
            return

        self._running = True

        # 启动守护进程
        self.daemon.start()

        # 启动市场监听
        self.listener.start()

        logger.info(f"Agent 服务启动: {self.config.agent_id}")

    def stop(self) -> None:
        """停止服务"""
        self._running = False

        # 停止市场监听
        self.listener.stop()

        # 停止守护进程
        self.daemon.stop()

        logger.info(f"Agent 服务停止: {self.config.agent_id}")

    def pause(self) -> None:
        """暂停"""
        self.daemon.pause()
        logger.info(f"Agent 服务暂停: {self.config.agent_id}")

    def resume(self) -> None:
        """恢复"""
        self.daemon.resume()
        logger.info(f"Agent 服务恢复: {self.config.agent_id}")

    # ── 执行器注册 ────────────────────────────────────

    def register_executor(self, task_type: str, executor: Callable) -> None:
        """
        注册任务执行器

        Args:
            task_type: 任务类型
            executor: 执行函数，签名: (task: Task) -> Dict
        """
        self.daemon.register_executor(task_type, executor)
        logger.info(f"注册执行器: {task_type}")

    # ── 状态查询 ─────────────────────────────────────

    def get_status(self) -> Dict:
        """获取服务状态"""
        daemon_status = self.daemon.get_status()

        return {
            "agent_id": self.config.agent_id,
            "wallet": self.config.wallet,
            "running": self._running,
            "daemon_state": daemon_status["state"],
            "active_tasks": daemon_status["active_tasks"],
            "pending_tasks": daemon_status["pending_tasks"],
            "completed_tasks": daemon_status["completed_tasks"],
            "stats": daemon_status["stats"],
            "config": {
                "task_types": self.config.task_types,
                "supported_chains": self.config.supported_chains,
                "auto_accept": self.config.auto_accept,
                "max_concurrent_tasks": self.config.max_concurrent_tasks,
            },
        }

    # ── 手动操作 ─────────────────────────────────────

    def submit_task(self, task: Task) -> bool:
        """手动提交任务"""
        return self.daemon.submit_task(task)


# ── 便捷函数 ────────────────────────────────────────

def create_service(
    agent_id: str,
    wallet: str,
    task_types: List[str] = None,
    supported_chains: List[str] = None,
    market_url: str = "http://localhost:3458",
    **kwargs
) -> AgentService:
    """
    创建 Agent 服务

    Args:
        agent_id: Agent ID
        wallet: 钱包地址
        task_types: 支持的任务类型
        supported_chains: 支持的链
        market_url: 市场 API 地址
        **kwargs: 其他配置

    Returns:
        AgentService 实例
    """
    config = AgentServiceConfig(
        agent_id=agent_id,
        wallet=wallet,
        task_types=task_types or ["token_delivery"],
        supported_chains=supported_chains or ["mock", "bsc"],
        market_url=market_url,
        **kwargs
    )

    return AgentService(config)


def run_service(config: AgentServiceConfig) -> None:
    """
    运行 Agent 服务（阻塞）

    处理 SIGINT/SIGTERM 优雅退出。
    """
    service = AgentService(config)

    # 信号处理
    def on_signal(signum, frame):
        logger.info(f"收到信号 {signum}，正在停止...")
        service.stop()
        exit(0)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    # 启动
    service.start()

    # 阻塞
    logger.info("Agent 服务运行中，按 Ctrl+C 停止")
    while True:
        time.sleep(1)


# ── CLI 入口 ────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CryptoMinds Agent 服务")
    parser.add_argument("--agent-id", required=True, help="Agent ID")
    parser.add_argument("--wallet", required=True, help="钱包地址")
    parser.add_argument("--task-types", default="token_delivery", help="任务类型（逗号分隔）")
    parser.add_argument("--chains", default="mock,bsc", help="支持的链（逗号分隔）")
    parser.add_argument("--market-url", default="http://localhost:3458", help="市场 API 地址")
    parser.add_argument("--max-concurrent", type=int, default=3, help="最大并发任务数")
    parser.add_argument("--min-amount", type=float, default=0.001, help="最小接单金额")
    parser.add_argument("--max-amount", type=float, default=1.0, help="最大接单金额")

    args = parser.parse_args()

    config = AgentServiceConfig(
        agent_id=args.agent_id,
        wallet=args.wallet,
        private_key="",
        task_types=args.task_types.split(","),
        supported_chains=args.chains.split(","),
        market_url=args.market_url,
        max_concurrent_tasks=args.max_concurrent,
        min_amount=Decimal(str(args.min_amount)),
        max_amount=Decimal(str(args.max_amount)),
    )

    print(f"=== CryptoMinds Agent 服务 ===")
    print(f"Agent ID: {config.agent_id}")
    print(f"钱包: {config.wallet}")
    print(f"任务类型: {config.task_types}")
    print(f"支持链: {config.supported_chains}")
    print(f"市场: {config.market_url}")
    print()

    run_service(config)
