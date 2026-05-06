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
    if _store is None:
        # 使用统一存储
        from store import UnifiedStore
        db_path = os.getenv("CREDIT_SCORE_DB_PATH", "cryptominds.db")
        _store = UnifiedStore(db_path=db_path)
    if _calculator is None:
        _calculator = SacredCalculator()


def _cold_start_score(address: str) -> SacredScore:
    """
    创建冷启动信用分

    每个维度 50 分，总分 250，等级 CCC。
    """
    now = int(__import__("time").time())
    score = SacredScore(
        agent_id=address,
        wallet=address,
        is_cold_start=True,
        calculated_at=now,
    )

    # 每维 50 分（250/5）
    base_score = COLD_START_SCORE / 5
    for dim, name in [
        ("S", "Stability"),
        ("A", "Activity"),
        ("C", "Creditworthiness"),
        ("R", "Reliability"),
        ("E", "Ecosystem"),
    ]:
        setattr(score, dim.lower(), DimensionScore(
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

    return jsonify(score.to_dict())


@credit_bp.route("/<address>/history", methods=["GET"])
def get_history(address: str):
    """查询信用分历史"""
    _ensure_initialized()

    limit = request.args.get("limit", 10, type=int)
    limit = min(limit, 100)

    # TODO: 从 sacred_scores 表查询历史
    return jsonify({
        "address": address,
        "history": []
    })


@credit_bp.route("/ranking", methods=["GET"])
def get_ranking():
    """信用分排行榜"""
    _ensure_initialized()

    limit = request.args.get("limit", 100, type=int)
    limit = min(limit, 200)

    # TODO: 从 sacred_scores 表查询排行榜
    return jsonify({
        "ranking": [],
        "total": 0
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

    # TODO: 保存到 sacred_scores 表
    return jsonify(score.to_dict())
