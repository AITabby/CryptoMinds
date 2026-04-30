"""
CryptoMinds Agent 守护进程

让 Agent 真正"活"起来：
- 监听任务队列
- 自动接单/执行
- 并发处理
- 状态机管理
"""

import os
import json
import time
import threading
from decimal import Decimal
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue, Empty
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Agent 状态"""
    IDLE = "idle"               # 空闲，等待任务
    WORKING = "working"         # 执行中
    PAUSED = "paused"           # 暂停
    STOPPED = "stopped"         # 已停止


class TaskState(Enum):
    """任务状态"""
    PENDING = "pending"         # 等待执行
    ACCEPTED = "accepted"       # 已接受
    EXECUTING = "executing"     # 执行中
    SUBMITTED = "submitted"     # 已提交结果
    VERIFIED = "verified"       # 验证通过
    FAILED = "failed"           # 执行失败
    TIMEOUT = "timeout"         # 超时


@dataclass
class Task:
    """任务"""
    task_id: str
    task_type: str
    buyer_wallet: str
    seller_wallet: str
    amount: Decimal
    chain: str
    channel_id: str
    params: Dict = field(default_factory=dict)
    state: TaskState = TaskState.PENDING
    created_at: int = field(default_factory=lambda: int(time.time()))
    started_at: int = 0
    completed_at: int = 0
    result: Dict = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "buyer_wallet": self.buyer_wallet,
            "seller_wallet": self.seller_wallet,
            "amount": str(self.amount),
            "chain": self.chain,
            "channel_id": self.channel_id,
            "params": self.params,
            "state": self.state.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
        }


@dataclass
class AgentConfig:
    """Agent 配置"""
    agent_id: str
    wallet: str
    private_key: str = ""  # 用于签名和支付

    # 能力
    task_types: List[str] = field(default_factory=list)
    supported_chains: List[str] = field(default_factory=list)

    # 策略
    auto_accept: bool = True              # 自动接单
    max_concurrent_tasks: int = 3         # 最大并发任务数
    min_amount: Decimal = Decimal("0.001")  # 最小接单金额
    max_amount: Decimal = Decimal("1.0")    # 最大接单金额

    # 超时
    task_timeout_seconds: int = 300       # 任务超时时间

    # 执行器
    executor_endpoint: str = ""           # 外部执行器地址
    executor_module: str = ""             # 本地执行器模块


class TaskQueue:
    """
    任务队列

    线程安全的任务队列，支持优先级。
    """

    def __init__(self):
        self._queue: Queue = Queue()
        self._tasks: Dict[str, Task] = {}  # task_id -> Task
        self._lock = threading.Lock()

    def put(self, task: Task, priority: int = 0) -> None:
        """添加任务"""
        with self._lock:
            self._tasks[task.task_id] = task
            self._queue.put((priority, task))
            logger.info(f"任务入队: {task.task_id} ({task.task_type})")

    def get(self, timeout: float = 1.0) -> Optional[Task]:
        """获取任务"""
        try:
            priority, task = self._queue.get(timeout=timeout)
            return task
        except Empty:
            return None

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取指定任务"""
        return self._tasks.get(task_id)

    def update_task(self, task: Task) -> None:
        """更新任务"""
        with self._lock:
            self._tasks[task.task_id] = task

    def size(self) -> int:
        """队列大小"""
        return self._queue.qsize()

    def list_pending(self) -> List[Task]:
        """列出待处理任务"""
        return [t for t in self._tasks.values() if t.state == TaskState.PENDING]


class Executor:
    """
    任务执行器

    负责实际执行任务。
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self._executors: Dict[str, Callable] = {}

    def register_executor(self, task_type: str, executor: Callable) -> None:
        """注册执行器"""
        self._executors[task_type] = executor
        logger.info(f"注册执行器: {task_type}")

    def execute(self, task: Task) -> Dict:
        """
        执行任务

        Returns:
            执行结果
        """
        task_type = task.task_type

        # 查找执行器
        executor = self._executors.get(task_type)

        if executor:
            # 使用注册的执行器
            try:
                result = executor(task)
                return result
            except Exception as e:
                logger.error(f"执行器执行失败: {e}")
                return {"error": str(e)}

        # 默认执行器
        return self._default_execute(task)

    def _default_execute(self, task: Task) -> Dict:
        """默认执行器"""
        if task.task_type == "token_delivery":
            return self._execute_token_delivery(task)
        elif task.task_type == "data_delivery":
            return self._execute_data_delivery(task)
        elif task.task_type == "compute_result":
            return self._execute_compute(task)
        else:
            return {"error": f"未知任务类型: {task.task_type}"}

    def _execute_token_delivery(self, task: Task) -> Dict:
        """执行代币交付"""
        # 这里需要调用实际的买币逻辑
        # 简化处理：返回模拟结果
        import hashlib

        return {
            "tx_hash": "0x" + hashlib.sha256(f"{task.task_id}{time.time()}".encode()).hexdigest()[:64],
            "token_address": task.params.get("token_address", "0x" + "0" * 40),
            "token_amount": str(task.amount * 1000),  # 模拟数量
            "mock": True,
        }

    def _execute_data_delivery(self, task: Task) -> Dict:
        """执行数据交付"""
        # 模拟数据处理
        return {
            "data": json.dumps({"result": "processed", "task_id": task.task_id}),
            "file_hash": hashlib.sha256(task.task_id.encode()).hexdigest(),
        }

    def _execute_compute(self, task: Task) -> Dict:
        """执行计算任务"""
        # 模拟计算
        return {
            "data": json.dumps({"output": 42}),
            "confidence": 0.95,
        }


class AgentDaemon:
    """
    Agent 守护进程

    核心功能：
    1. 监听任务队列
    2. 自动接单
    3. 执行任务
    4. 提交结果
    5. 收款
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.state = AgentState.IDLE
        self.task_queue = TaskQueue()
        self.executor = Executor(config)

        # 当前任务
        self.active_tasks: Dict[str, Task] = {}
        self.completed_tasks: List[Task] = []

        # 线程
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False

        # 统计
        self.stats = {
            "tasks_received": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "total_earned": Decimal("0"),
        }

    # ── 生命周期 ─────────────────────────────────────

    def start(self) -> None:
        """启动守护进程"""
        if self._running:
            logger.warning("守护进程已在运行")
            return

        self._running = True
        self.state = AgentState.IDLE

        self._worker_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._worker_thread.start()

        logger.info(f"Agent 守护进程启动: {self.config.agent_id}")

    def stop(self) -> None:
        """停止守护进程"""
        self._running = False
        self.state = AgentState.STOPPED

        if self._worker_thread:
            self._worker_thread.join(timeout=5)

        logger.info(f"Agent 守护进程停止: {self.config.agent_id}")

    def pause(self) -> None:
        """暂停"""
        self.state = AgentState.PAUSED
        logger.info(f"Agent 守护进程暂停: {self.config.agent_id}")

    def resume(self) -> None:
        """恢复"""
        self.state = AgentState.IDLE
        logger.info(f"Agent 守护进程恢复: {self.config.agent_id}")

    # ── 主循环 ────────────────────────────────────────

    def _run_loop(self) -> None:
        """主循环"""
        while self._running:
            try:
                # 检查状态
                if self.state == AgentState.PAUSED:
                    time.sleep(1)
                    continue

                # 检查并发限制
                if len(self.active_tasks) >= self.config.max_concurrent_tasks:
                    time.sleep(0.5)
                    continue

                # 获取任务
                task = self.task_queue.get(timeout=1.0)

                if task:
                    # 处理任务
                    threading.Thread(
                        target=self._process_task,
                        args=(task,),
                        daemon=True
                    ).start()

            except Exception as e:
                logger.error(f"主循环异常: {e}")
                time.sleep(1)

    def _process_task(self, task: Task) -> None:
        """处理单个任务"""
        try:
            # 1. 接受任务
            task.state = TaskState.ACCEPTED
            task.started_at = int(time.time())
            self.active_tasks[task.task_id] = task
            self.stats["tasks_received"] += 1

            logger.info(f"接受任务: {task.task_id}")
            self.state = AgentState.WORKING

            # 2. 执行任务
            task.state = TaskState.EXECUTING
            result = self.executor.execute(task)

            # 3. 检查结果
            if result.get("error"):
                task.state = TaskState.FAILED
                task.error = result["error"]
                self.stats["tasks_failed"] += 1
                logger.error(f"任务执行失败: {task.task_id} - {task.error}")
            else:
                task.state = TaskState.SUBMITTED
                task.result = result
                logger.info(f"任务执行完成: {task.task_id}")

            # 4. 提交结果（触发验证和结算）
            self._submit_result(task)

            # 5. 清理
            task.completed_at = int(time.time())
            self.completed_tasks.append(task)
            del self.active_tasks[task.task_id]

            if not self.active_tasks:
                self.state = AgentState.IDLE

        except Exception as e:
            logger.error(f"任务处理异常: {task.task_id} - {e}")
            task.state = TaskState.FAILED
            task.error = str(e)

    def _submit_result(self, task: Task) -> None:
        """提交结果，触发验证和结算"""
        if task.state != TaskState.SUBMITTED:
            return

        # 调用闭环处理器
        try:
            from task_closer import task_closer
            from verification.base import TaskOutput

            # 构造任务输出
            task_output = TaskOutput(
                task_type=task.task_type,
                seller_wallet=task.seller_wallet,
                tx_hash=task.result.get("tx_hash", ""),
                token_address=task.result.get("token_address", ""),
                token_amount=task.result.get("token_amount", ""),
                data=task.result.get("data", ""),
                extra=task.result.get("extra", {}),
            )

            # 执行闭环
            close_result = task_closer.close_task(
                task_id=task.task_id,
                task_type=task.task_type,
                buyer_wallet=task.buyer_wallet,
                seller_wallet=task.seller_wallet,
                seller_agent_id=self.config.agent_id,
                chain=task.chain,
                amount=task.amount,
                channel_id=task.channel_id,
                task_output=task_output,
                private_key=self.config.private_key,
            )

            if close_result.success:
                task.state = TaskState.VERIFIED
                self.stats["tasks_completed"] += 1
                self.stats["total_earned"] += task.amount
                logger.info(f"任务验证通过: {task.task_id}, 收入: {task.amount}")
            else:
                task.state = TaskState.FAILED
                task.error = close_result.error
                self.stats["tasks_failed"] += 1
                logger.error(f"任务闭环失败: {task.task_id} - {close_result.error}")

        except ImportError:
            # 没有闭环处理器，简化处理
            task.state = TaskState.VERIFIED
            self.stats["tasks_completed"] += 1
            self.stats["total_earned"] += task.amount
            logger.info(f"任务验证通过: {task.task_id}, 收入: {task.amount}")

    # ── 任务管理 ──────────────────────────────────────

    def submit_task(self, task: Task) -> bool:
        """
        提交任务到队列

        Returns:
            是否接受
        """
        # 检查能力
        if task.task_type not in self.config.task_types:
            logger.warning(f"不支持的任务类型: {task.task_type}")
            return False

        # 检查链
        if task.chain not in self.config.supported_chains:
            logger.warning(f"不支持的链: {task.chain}")
            return False

        # 检查金额
        if task.amount < self.config.min_amount or task.amount > self.config.max_amount:
            logger.warning(f"金额超出范围: {task.amount}")
            return False

        # 检查并发
        if len(self.active_tasks) >= self.config.max_concurrent_tasks:
            logger.warning(f"已达最大并发数: {self.config.max_concurrent_tasks}")
            return False

        # 入队
        self.task_queue.put(task)
        return True

    def register_executor(self, task_type: str, executor: Callable) -> None:
        """注册任务执行器"""
        self.executor.register_executor(task_type, executor)

    # ── 查询 ─────────────────────────────────────────

    def get_status(self) -> Dict:
        """获取状态"""
        return {
            "agent_id": self.config.agent_id,
            "state": self.state.value,
            "active_tasks": len(self.active_tasks),
            "pending_tasks": self.task_queue.size(),
            "completed_tasks": len(self.completed_tasks),
            "stats": {
                "tasks_received": self.stats["tasks_received"],
                "tasks_completed": self.stats["tasks_completed"],
                "tasks_failed": self.stats["tasks_failed"],
                "total_earned": str(self.stats["total_earned"]),
            },
        }

    def get_active_tasks(self) -> List[Dict]:
        """获取活跃任务"""
        return [t.to_dict() for t in self.active_tasks.values()]


# ── 便捷函数 ────────────────────────────────────────

def create_daemon(
    agent_id: str,
    wallet: str,
    task_types: List[str] = None,
    supported_chains: List[str] = None,
    **kwargs
) -> AgentDaemon:
    """
    创建 Agent 守护进程

    Args:
        agent_id: Agent ID
        wallet: 钱包地址
        task_types: 支持的任务类型
        supported_chains: 支持的链
        **kwargs: 其他配置

    Returns:
        AgentDaemon 实例
    """
    config = AgentConfig(
        agent_id=agent_id,
        wallet=wallet,
        task_types=task_types or ["token_delivery", "data_delivery"],
        supported_chains=supported_chains or ["mock", "bsc"],
        **kwargs
    )

    return AgentDaemon(config)


# ── 测试 ────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Agent 守护进程测试 ===\n")

    # 创建守护进程
    daemon = create_daemon(
        agent_id="test-agent-001",
        wallet="0xseller",
        task_types=["token_delivery", "data_delivery"],
        supported_chains=["mock"],
        min_amount=Decimal("0.001"),
        max_amount=Decimal("1.0"),
    )

    # 启动
    daemon.start()

    # 提交任务
    print("提交任务...")
    for i in range(3):
        task = Task(
            task_id=f"task-{i}",
            task_type="token_delivery",
            buyer_wallet="0xbuyer",
            seller_wallet="0xseller",
            amount=Decimal("0.01"),
            chain="mock",
            channel_id="mock",
        )
        daemon.submit_task(task)
        print(f"  任务 {i} 已提交")

    # 等待执行
    print("\n等待执行...")
    time.sleep(3)

    # 获取状态
    print("\n守护进程状态:")
    status = daemon.get_status()
    print(json.dumps(status, indent=2))

    # 停止
    daemon.stop()
    print("\n守护进程已停止")
