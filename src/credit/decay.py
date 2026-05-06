"""
时间衰减函数
"""

import math
from typing import List, Tuple

from .config import SHORT_HALF_LIFE, LONG_HALF_LIFE, SEVERE_VIOLATION_TYPES


def time_decay(days_ago: float, half_life: float) -> float:
    """指数时间衰减: 2^(-d/half_life)，一个半衰期后权重恰好为0.5"""
    if days_ago <= 0:
        return 1.0
    return 2.0 ** (-days_ago / half_life)


def days_between(timestamp: int, now: int) -> float:
    """两个时间戳之间的天数"""
    return max(0.0, (now - timestamp) / 86400.0)


def apply_decay_to_records(
    records: list,
    half_life: float,
    now: int = None,
) -> List[Tuple]:
    """对记录列表施加时间衰减，返回 (record, weight) 列表"""
    import time as _time
    if now is None:
        now = int(_time.time())

    result = []
    for record in records:
        d = days_between(record.created_at, now)
        weight = time_decay(d, half_life)
        result.append((record, weight))

    return result


def no_decay_violation(resolution: str) -> bool:
    """判断是否为严重违约（不衰减）"""
    return resolution in SEVERE_VIOLATION_TYPES


def weighted_success_rate(records: list, now: int = None) -> float:
    """衰减加权的成功率"""
    import time as _time
    if now is None:
        now = int(_time.time())

    if not records:
        return 0.0

    from .models import TaskStatus

    weighted_success = 0.0
    weighted_total = 0.0

    for record in records:
        d = days_between(record.created_at, now)
        weight = time_decay(d, LONG_HALF_LIFE)
        weighted_total += weight
        if record.status == TaskStatus.SETTLED:
            weighted_success += weight

    return weighted_success / weighted_total if weighted_total > 0 else 0.0
