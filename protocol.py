"""
CryptoMinds 协议入口

统一入口，串联结算层、验证层、Agent层、信誉层。
"""

from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import os
from pathlib import Path

from settlement import ChannelRegistry, init_default_channels
from settlement.base import PaymentResult
from verification import GateRegistry, init_default_gates
from verification.base import TaskInput, TaskOutput, VerificationResult
from agent import AgentRegistry, AgentCapability, CapabilitySpec
from reputation import RecordStore, ReputationCalculator, CreditRegistry
from reputation.record import PerformanceRecord, TaskStatus

from data.sqlite_store import SqliteRecordStore, SqliteCreditStore, SqliteAgentBridge


def init_protocol():
    """初始化协议（结算 + 验证 + Agent + 信誉）"""
    init_default_channels()
    init_default_gates()


# SQLite 数据库路径
_DB_PATH = str(Path(__file__).parent / "web" / "cryptominds.db")

# 全局实例 — 使用 SQLite 替代 JSON/内存存储
_record_store = SqliteRecordStore(_DB_PATH)
_reputation_calculator = ReputationCalculator(_record_store)
_credit_registry = SqliteCreditStore(_DB_PATH)
_agent_bridge = SqliteAgentBridge(_DB_PATH)

# AgentRegistry 仍使用内存+JSON 作为主存储，但通过 bridge 同步到 SQLite
AgentRegistry.set_persistence(os.path.join(os.path.dirname(__file__), 'agents_registry.json'))
AgentRegistry.set_sqlite_bridge(_agent_bridge)

# 自动初始化
init_protocol()


# ── 协议信息 ────────────────────────────────────────

def get_protocol_info() -> Dict:
    """获取协议信息"""
    return {
        "channels": ChannelRegistry.list_all(),
        "gates": GateRegistry.list_all(),
        "agents": AgentRegistry.get_stats(),
        "credit_currencies": len(_credit_registry.list_all()),
        "supported_chains": ChannelRegistry.list_supported_chains(),
        "supported_task_types": GateRegistry.list_task_types(),
    }


# ── 任务执行流程 ────────────────────────────────────

def create_task(
    task_type: str,
    buyer_wallet: str,
    seller_wallet: str,
    amount: Decimal,
    chain: str = "bsc",
    channel_id: str = None,
    **params
) -> Dict:
    """
    创建任务

    Args:
        task_type: 任务类型（token_delivery, data_delivery, ...）
        buyer_wallet: 买家钱包
        seller_wallet: 卖家钱包
        amount: 金额
        chain: 链
        channel_id: 结算通道 ID（可选，自动选择）
        params: 其他参数

    Returns:
        任务信息
    """
    # 获取验证门
    gate = GateRegistry.get(task_type)
    if not gate:
        return {"error": f"未知任务类型: {task_type}"}

    # 检查链支持
    if not gate.supports_chain(chain):
        return {"error": f"验证门 {task_type} 不支持链 {chain}"}

    # 选择结算通道
    if not channel_id:
        # 先尝试 {chain}-native，再尝试 {chain}
        channel_id = f"{chain}-native"
        if not ChannelRegistry.get(channel_id):
            channel_id = chain

    channel = ChannelRegistry.get(channel_id)
    if not channel:
        return {"error": f"未知结算通道: {channel_id}"}

    # 创建任务输入
    task_input = TaskInput(
        task_type=task_type,
        buyer_wallet=buyer_wallet,
        seller_wallet=seller_wallet,
        chain=chain,
        amount=amount,
        params=params,
    )

    # 验证输入
    valid, msg = gate.validate_input(task_input)
    if not valid:
        return {"error": f"输入验证失败: {msg}"}

    return {
        "ok": True,
        "task_id": f"task-{task_input.buyer_wallet[:8]}-{int(__import__('time').time())}",
        "task_type": task_type,
        "chain": chain,
        "channel_id": channel_id,
        "amount": str(amount),
        "buyer_wallet": buyer_wallet,
        "seller_wallet": seller_wallet,
    }


def verify_task(
    task_type: str,
    input: TaskInput,
    output: TaskOutput
) -> VerificationResult:
    """
    验证任务完成

    Args:
        task_type: 任务类型
        input: 任务输入
        output: 卖家提交的输出

    Returns:
        VerificationResult
    """
    gate = GateRegistry.get(task_type)
    if not gate:
        return VerificationResult(
            success=False,
            gate_id="unknown",
            task_type=task_type,
            error=f"未知任务类型: {task_type}",
        )

    return gate.verify(input, output)


# ── 结算流程 ────────────────────────────────────────

def settle_payment(
    channel_id: str,
    from_address: str,
    to_address: str,
    amount: Decimal,
    order_id: str,
    private_key: str,
    description: str = "",
) -> PaymentResult:
    """
    执行结算

    Args:
        channel_id: 结算通道 ID
        from_address: 发送方地址
        to_address: 接收方地址
        amount: 金额
        order_id: 订单 ID
        private_key: 私钥
        description: 描述

    Returns:
        PaymentResult
    """
    channel = ChannelRegistry.get(channel_id)
    if not channel:
        return PaymentResult(
            success=False,
            channel_id=channel_id,
            order_id=order_id,
            error=f"未知结算通道: {channel_id}",
        )

    # 创建支付请求
    request = channel.create_payment(
        from_address=from_address,
        to_address=to_address,
        amount=amount,
        order_id=order_id,
        description=description,
    )

    # 签名
    signature = channel.sign_payment(request, private_key)

    # 执行
    return channel.execute_payment(request, signature, private_key)


# ── 完整流程 ────────────────────────────────────────

def execute_task(
    task_type: str,
    buyer_wallet: str,
    seller_wallet: str,
    amount: Decimal,
    chain: str = "bsc",
    channel_id: str = None,
    seller_output: TaskOutput = None,
) -> Dict:
    """
    执行完整任务流程

    1. 创建任务
    2. 卖家执行（外部）
    3. 验证完成
    4. 结算支付

    Args:
        task_type: 任务类型
        buyer_wallet: 买家钱包
        seller_wallet: 卖家钱包
        amount: 金额
        chain: 链
        channel_id: 结算通道
        seller_output: 卖家提交的输出

    Returns:
        执行结果
    """
    # 1. 创建任务
    task = create_task(
        task_type=task_type,
        buyer_wallet=buyer_wallet,
        seller_wallet=seller_wallet,
        amount=amount,
        chain=chain,
        channel_id=channel_id,
    )

    if not task.get("ok"):
        return task

    # 2. 如果没有卖家输出，返回任务信息等待执行
    if not seller_output:
        return {
            "ok": True,
            "status": "pending",
            "task": task,
            "message": "等待卖家执行并提交输出",
        }

    # 3. 验证完成
    task_input = TaskInput(
        task_type=task_type,
        buyer_wallet=buyer_wallet,
        seller_wallet=seller_wallet,
        chain=chain,
        amount=amount,
    )

    verify_result = verify_task(task_type, task_input, seller_output)

    if not verify_result.success:
        return {
            "ok": False,
            "status": "verification_failed",
            "task": task,
            "verify_result": verify_result.to_dict(),
        }

    # 4. 结算支付（这里返回任务信息，实际支付需要私钥）
    return {
        "ok": True,
        "status": "verified",
        "task": task,
        "verify_result": verify_result.to_dict(),
        "message": "验证通过，等待结算",
    }


# ── Agent 发现与匹配 ──────────────────────────────────

def register_agent(agent: AgentCapability) -> Dict:
    """
    注册 Agent

    Args:
        agent: Agent 能力描述

    Returns:
        注册结果
    """
    # 验证能力
    for cap in agent.capabilities:
        gate = GateRegistry.get(cap.verification_gate)
        if not gate:
            return {"error": f"未知验证门: {cap.verification_gate}"}

        # 验证通道支持
        for channel_id in cap.supported_channels:
            channel = ChannelRegistry.get(channel_id)
            if not channel:
                return {"error": f"未知结算通道: {channel_id}"}

    # 注册
    AgentRegistry.register(agent)

    return {
        "ok": True,
        "agent_id": agent.agent_id,
        "message": "Agent 注册成功",
    }


def search_agents(
    task_type: str = None,
    chain: str = None,
    amount: Decimal = None,
    min_reputation: float = None,
    sort_by: str = "reputation",
    limit: int = 10,
) -> List[Dict]:
    """
    搜索 Agent

    Args:
        task_type: 任务类型
        chain: 链
        amount: 金额
        min_reputation: 最低信誉分
        sort_by: 排序方式
        limit: 返回数量

    Returns:
        Agent 列表
    """
    agents = AgentRegistry.search(
        task_type=task_type,
        chain=chain,
        amount=amount,
        min_reputation=min_reputation,
        sort_by=sort_by,
        limit=limit,
    )

    return [a.to_dict() for a in agents]


def find_best_agent(
    task_type: str,
    chain: str,
    amount: Decimal,
    strategy: str = "balanced",
) -> Optional[Dict]:
    """
    找到最佳匹配的 Agent

    Args:
        task_type: 任务类型
        chain: 链
        amount: 金额
        strategy: 选择策略 (reputation, price, balanced)

    Returns:
        最佳 Agent 信息
    """
    agent = AgentRegistry.find_best_match(
        task_type=task_type,
        chain=chain,
        amount=amount,
        strategy=strategy,
    )

    if agent:
        return agent.to_dict()
    return None


# ── Agent 自主下单流程 ─────────────────────────────────

def agent_buy(
    buyer_wallet: str,
    task_type: str,
    amount: Decimal,
    chain: str = "bsc",
    strategy: str = "balanced",
) -> Dict:
    """
    Agent 自主下单流程

    1. 搜索卖家 Agent
    2. 选择最佳卖家
    3. 创建任务
    4. 等待卖家执行

    Args:
        buyer_wallet: 买家钱包
        task_type: 任务类型
        amount: 金额
        chain: 链
        strategy: 选择策略

    Returns:
        任务信息
    """
    # 1. 搜索卖家
    seller = AgentRegistry.find_best_match(
        task_type=task_type,
        chain=chain,
        amount=amount,
        strategy=strategy,
    )

    if not seller:
        return {
            "error": f"没有找到可用的卖家 Agent (任务: {task_type}, 链: {chain}, 金额: {amount})",
        }

    # 2. 创建任务
    task = create_task(
        task_type=task_type,
        buyer_wallet=buyer_wallet,
        seller_wallet=seller.wallet,
        amount=amount,
        chain=chain,
    )

    if not task.get("ok"):
        return task

    # 3. 返回任务信息
    return {
        "ok": True,
        "status": "pending",
        "task": task,
        "seller": {
            "agent_id": seller.agent_id,
            "name": seller.name,
            "wallet": seller.wallet,
            "reputation": seller.reputation.to_dict(),
            "price": str(seller.get_price(task_type, amount)),
        },
        "message": f"已选择卖家 {seller.name}，等待执行",
    }


# ── 信誉层接口 ──────────────────────────────────────

def record_task_completion(
    task_id: str,
    task_type: str,
    buyer_wallet: str,
    seller_wallet: str,
    seller_agent_id: str,
    chain: str,
    amount: Decimal,
    status: TaskStatus,
    score: float = 0.0,
    response_time_ms: int = 0,
    payment_tx: str = "",
    payment_amount: Decimal = Decimal("0"),
    evidence: Dict = None,
) -> Dict:
    """
    记录任务完成

    Args:
        task_id: 任务 ID
        task_type: 任务类型
        buyer_wallet: 买家钱包
        seller_wallet: 卖家钱包
        seller_agent_id: 卖家 Agent ID
        chain: 链
        amount: 金额
        status: 任务状态
        score: 验证门评分
        response_time_ms: 响应时间
        payment_tx: 支付交易哈希
        payment_amount: 支付金额
        evidence: 验证证据

    Returns:
        记录结果
    """
    record = PerformanceRecord.create(
        task_id=task_id,
        task_type=task_type,
        buyer_wallet=buyer_wallet,
        seller_wallet=seller_wallet,
        seller_agent_id=seller_agent_id,
        chain=chain,
        amount=amount,
        status=status,
        success=(status == TaskStatus.SETTLED),
        score=score,
        response_time_ms=response_time_ms,
        payment_tx=payment_tx,
        payment_amount=payment_amount,
        evidence=evidence or {},
    )

    record.completed_at = int(__import__('time').time())

    _record_store.save(record)

    return {
        "ok": True,
        "record_id": record.record_id,
        "message": "履约记录已保存",
    }


def get_agent_reputation(agent_id: str, wallet: str) -> Dict:
    """
    获取 Agent 信誉分

    Args:
        agent_id: Agent ID
        wallet: 钱包地址

    Returns:
        信誉分信息
    """
    score = _reputation_calculator.calculate(agent_id, wallet)
    return score.to_dict()


def update_agent_reputation(agent_id: str) -> Dict:
    """
    更新 Agent 信誉分

    基于履约记录重新计算信誉分，并更新 Agent 信息。

    Args:
        agent_id: Agent ID

    Returns:
        更新结果
    """
    agent = AgentRegistry.get(agent_id)
    if not agent:
        return {"error": f"未知 Agent: {agent_id}"}

    # 计算信誉分
    score = _reputation_calculator.calculate(agent_id, agent.wallet)

    # 更新 Agent 信誉信息
    agent.reputation.score = score.score
    agent.reputation.tasks_completed = score.completed_tasks
    agent.reputation.tasks_failed = score.failed_tasks
    agent.reputation.total_volume = score.total_volume
    agent.reputation.avg_response_time_ms = score.avg_response_time_ms
    agent.reputation.last_24h_tasks = score.last_24h_tasks
    agent.reputation.last_24h_success_rate = score.last_24h_success_rate

    return {
        "ok": True,
        "agent_id": agent_id,
        "score": score.score,
        "rank": score.rank,
        "message": f"信誉分已更新: {score.score:.2f} ({score.rank})",
    }


def get_seller_records(seller_wallet: str, limit: int = 100) -> List[Dict]:
    """
    获取卖家履约记录

    Args:
        seller_wallet: 卖家钱包
        limit: 返回数量

    Returns:
        记录列表
    """
    records = _record_store.get_by_seller(seller_wallet, limit=limit)
    return [r.to_dict() for r in records]


# ── 信用货币接口 ⚠️ 实验性 ───────────────────────────
# 注意：信用货币需要先有足够多的 Agent 和交易量才有实际意义
# 目前保留实现，暂不推荐生产使用

def issue_credit_currency(
    issuer_agent_id: str,
    issuer_wallet: str,
    name: str,
    symbol: str,
    max_supply: Decimal,
    backed_by: str = "",
) -> Dict:
    """
    发行信用货币 ⚠️ 实验性功能

    Args:
        issuer_agent_id: 发行者 Agent ID
        issuer_wallet: 发行者钱包
        name: 货币名称
        symbol: 货币符号
        max_supply: 最大发行量
        backed_by: 抵押物

    Returns:
        发行结果
    """
    # 检查信誉分
    agent = AgentRegistry.get(issuer_agent_id)
    if not agent:
        return {"error": f"未知 Agent: {issuer_agent_id}"}

    if agent.reputation.score < 4.0:
        return {"error": f"信誉分不足: {agent.reputation.score:.2f}，需要 >= 4.0"}

    return _credit_registry.issue(
        issuer_agent_id=issuer_agent_id,
        issuer_wallet=issuer_wallet,
        name=name,
        symbol=symbol,
        max_supply=max_supply,
        backed_by=backed_by,
    )


def list_credit_currencies() -> List[Dict]:
    """列出所有信用货币"""
    return _credit_registry.list_all()


def accept_credit_currency(currency_id: str, agent_id: str) -> Dict:
    """
    Agent 接受信用货币

    Args:
        currency_id: 货币 ID
        agent_id: Agent ID

    Returns:
        结果
    """
    success = _credit_registry.accept_currency(currency_id, agent_id)
    if success:
        return {"ok": True, "message": f"已接受货币 {currency_id}"}
    return {"error": f"未知货币: {currency_id}"}


def pay_with_credit_currency(
    currency_id: str,
    from_wallet: str,
    to_wallet: str,
    amount: Decimal,
    to_agent_id: str = None,
) -> Dict:
    """
    用信用货币支付

    Args:
        currency_id: 货币 ID
        from_wallet: 发送方钱包
        to_wallet: 接收方钱包
        amount: 数量
        to_agent_id: 接收方 Agent ID

    Returns:
        支付结果
    """
    return _credit_registry.pay_with_credit(
        currency_id=currency_id,
        from_wallet=from_wallet,
        to_wallet=to_wallet,
        amount=amount,
        to_agent_id=to_agent_id,
    )


def get_acceptable_currencies(agent_id: str, min_trust_score: float = 0.5) -> List[Dict]:
    """
    获取 Agent 可接受的货币列表

    Args:
        agent_id: Agent ID
        min_trust_score: 最低信任分

    Returns:
        货币列表
    """
    return _credit_registry.get_acceptable_currencies(agent_id, min_trust_score)


def check_currency_acceptance(currency_id: str, agent_id: str) -> Dict:
    """
    检查 Agent 是否接受某货币

    Args:
        currency_id: 货币 ID
        agent_id: Agent ID

    Returns:
        接受状态
    """
    return _credit_registry.check_acceptance(currency_id, agent_id)


# ── 测试 ────────────────────────────────────────────

if __name__ == "__main__":
    import json

    print("=== CryptoMinds 协议信息 ===")
    info = get_protocol_info()
    print(json.dumps(info, indent=2, ensure_ascii=False))

    print("\n=== Agent 注册测试 ===")
    from agent.capability import CapabilitySpec, ReputationInfo

    agent = AgentCapability(
        agent_id="test-seller-001",
        name="测试卖家",
        wallet="0xseller",
        capabilities=[
            CapabilitySpec(
                task_type="token_delivery",
                verification_gate="token_delivery",
                supported_chains=["mock"],
                supported_channels=["mock"],
                pricing_model="fixed",
                base_price=Decimal("0.001"),
            )
        ],
        reputation=ReputationInfo(score=4.5, tasks_completed=10),
        staked=Decimal("1.0"),
    )

    result = register_agent(agent)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    print("\n=== Agent 搜索测试 ===")
    agents = search_agents(task_type="token_delivery", chain="mock")
    print(f"找到 {len(agents)} 个 Agent")

    print("\n=== Agent 自主下单测试 ===")
    result = agent_buy(
        buyer_wallet="0xbuyer",
        task_type="token_delivery",
        amount=Decimal("0.01"),
        chain="mock",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
