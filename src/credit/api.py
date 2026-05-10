"""
信用分 API 蓝图

SACRED 五维信用分查询接口。
"""

import os
from flask import Blueprint, jsonify, request

from .calculator import SacredCalculator
from .models import SacredScore, DimensionScore, CreditGrade
from .config import COLD_START_SCORE

# 蓝图
credit_bp = Blueprint("credit", __name__)

# 懒初始化
_store = None
_calculator = None


def _ensure_initialized():
    global _store, _calculator
    db_path = os.getenv("CRYPTOMINDS_DB_PATH", "cryptominds.db")
    if _store is None or getattr(_store, "_db_path", None) != db_path:
        from store import UnifiedStore
        _store = UnifiedStore(db_path=db_path)
    if _calculator is None:
        _calculator = SacredCalculator()


def _cold_start_score(address: str) -> SacredScore:
    """
    创建冷启动信用分

    每个维度 50 分，总分 250，等级 CCC。
    """
    import time as _time
    now = int(_time.time())
    score = SacredScore(
        agent_id=address,
        wallet=address,
        is_cold_start=True,
        calculated_at=now,
    )

    # 每维 50 分（250/5）
    base_score = COLD_START_SCORE / 5
    for dim, name, attr in [
        ("S", "Stability", "stability"),
        ("A", "Activity", "activity"),
        ("C", "Creditworthiness", "creditworthiness"),
        ("R", "Reliability", "reliability"),
        ("E", "Ecosystem", "ecosystem"),
    ]:
        setattr(score, attr, DimensionScore(
            dimension=dim,
            name=name,
            raw_score=base_score,
            weighted_score=base_score,
            components={"cold_start": base_score},
        ))

    score.total_score = COLD_START_SCORE
    score.grade = CreditGrade.CCC.value
    score.compute_hash()
    return score


@credit_bp.route("/<address>", methods=["GET"])
def get_score(address: str):
    """查询信用分

    Args:
        address: Agent 钱包地址或 Agent ID
    """
    _ensure_initialized()

    # 先从存储查询
    cached = _store.get_latest_score(address)
    if cached is not None:
        return jsonify(cached.to_dict())

    # 从履约记录计算
    records = _store.get_performance_records(agent_id=address)

    if not records:
        # 冷启动
        return jsonify(_cold_start_score(address).to_dict())

    # 计算信用分
    score = _calculator.calculate(
        agent_id=address,
        wallet=address,
        records=records,
    )

    # 保存
    _store.save_score(score)
    return jsonify(score.to_dict())


@credit_bp.route("/<address>/history", methods=["GET"])
def get_history(address: str):
    """查询信用分历史"""
    _ensure_initialized()

    limit = request.args.get("limit", 10, type=int)
    limit = min(limit, 100)

    history = _store.get_score_history(address, limit=limit)
    return jsonify({
        "address": address,
        "history": history,
    })


@credit_bp.route("/ranking", methods=["GET"])
def get_ranking():
    """信用分排行榜"""
    _ensure_initialized()

    limit = request.args.get("limit", 100, type=int)
    limit = min(limit, 200)

    ranking = _store.get_leaderboard(limit=limit)
    return jsonify({
        "ranking": ranking,
        "total": len(ranking),
    })


@credit_bp.route("/<address>/refresh", methods=["POST"])
def refresh_score(address: str):
    """触发重新计算信用分

    需要提供 Agent 的履约记录等数据。
    """
    _ensure_initialized()

    data = request.json or {}
    agent_id = data.get("agent_id", address)
    wallet = data.get("wallet", address)
    records = data.get("records", [])
    credit_data = data.get("credit_data", {})
    agent_info = data.get("agent_info", {})

    score = _calculator.calculate(
        agent_id=agent_id,
        wallet=wallet,
        records=records,
        credit_data=credit_data,
        agent_info=agent_info,
    )

    _store.save_score(score)
    return jsonify(score.to_dict())


@credit_bp.route("/<address>/records", methods=["GET"])
def get_records(address: str):
    """获取履约记录（供验证使用）

    返回该Agent的所有履约记录，任何人都可以用这些记录验证信用分
    """
    _ensure_initialized()

    limit = request.args.get("limit", 1000, type=int)
    limit = min(limit, 2000)

    records = _store.get_performance_records(agent_id=address, limit=limit)

    return jsonify({
        "agent_id": address,
        "records": [
            {
                "record_id": r.record_id,
                "task_id": r.task_id,
                "task_type": r.task_type,
                "buyer_wallet": r.buyer_wallet,
                "seller_wallet": r.seller_wallet,
                "seller_agent_id": r.seller_agent_id,
                "chain": r.chain,
                "amount": r.amount,
                "status": r.status.value,
                "success": r.success,
                "score": r.score,
                "created_at": r.created_at,
                "completed_at": r.completed_at,
                "response_time_ms": r.response_time_ms,
                "payment_tx": r.payment_tx,
                "payment_amount": r.payment_amount,
                "evidence": r.evidence,
                "disputed": r.disputed,
                "dispute_reason": r.dispute_reason,
                "resolution": r.resolution,
            }
            for r in records
        ],
        "total": len(records),
    })


@credit_bp.route("/<address>/verify", methods=["GET"])
def verify_score(address: str):
    """验证信用分

    返回信用分及其计算所需的所有数据，供第三方验证
    """
    _ensure_initialized()

    # 获取信用分
    score = _store.get_latest_score(address)
    if not score:
        return jsonify({"error": "信用分不存在"}), 404

    # 获取履约记录
    records = _store.get_performance_records(agent_id=address)

    # 获取Agent信息（如果有）
    agent_info = {}
    credit_data = {}

    return jsonify({
        "ok": True,
        "agent_id": address,
        "score": score.to_dict(),
        "records": [
            {
                "record_id": r.record_id,
                "task_id": r.task_id,
                "task_type": r.task_type,
                "buyer_wallet": r.buyer_wallet,
                "seller_wallet": r.seller_wallet,
                "seller_agent_id": r.seller_agent_id,
                "chain": r.chain,
                "amount": r.amount,
                "status": r.status.value,
                "success": r.success,
                "score": r.score,
                "created_at": r.created_at,
                "completed_at": r.completed_at,
                "response_time_ms": r.response_time_ms,
                "payment_tx": r.payment_tx,
                "payment_amount": r.payment_amount,
                "evidence": r.evidence,
                "disputed": r.disputed,
                "dispute_reason": r.dispute_reason,
                "resolution": r.resolution,
            }
            for r in records
        ],
        "agent_info": agent_info,
        "credit_data": credit_data,
        "verification_note": "使用开源算法和这些数据可以验证信用分的哈希值",
    })
