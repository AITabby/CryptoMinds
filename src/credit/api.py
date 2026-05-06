"""
信用分 API 蓝图

SACRED 五维信用分查询接口。
"""

import os
from flask import Blueprint, jsonify, request

from .calculator import SacredCalculator
from .store import CreditScoreStore

# 蓝图
credit_bp = Blueprint("credit", __name__)

# 懒初始化
_store = None
_calculator = None


def _ensure_initialized():
    global _store, _calculator
    if _store is None:
        db_path = os.getenv("CREDIT_SCORE_DB_PATH", "credit_score.db")
        _store = CreditScoreStore(db_path=db_path)
    if _calculator is None:
        _calculator = SacredCalculator()


@credit_bp.route("/<address>", methods=["GET"])
def get_score(address: str):
    """查询信用分

    Args:
        address: Agent 钱包地址或 Agent ID
    """
    _ensure_initialized()

    # 先从存储查询
    score = _store.get_latest_score(address)
    if score is not None:
        return jsonify(score.to_dict())

    # 没有历史数据，返回冷启动默认分
    # 新 Agent 基础分 250，等级 CCC
    from .models import SacredScore, CreditGrade
    from .config import COLD_START_SCORE

    score = SacredScore(
        agent_id=address,
        wallet=address,
        total_score=COLD_START_SCORE,
        grade=CreditGrade.CCC.value,
        is_cold_start=True,
    )

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
        "history": [h.to_dict() for h in history]
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
        "total": len(ranking)
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
