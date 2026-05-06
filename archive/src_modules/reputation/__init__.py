"""
CryptoMinds 信誉层

履约记录存证、信誉分计算、信用货币基础。
"""

from .record import PerformanceRecord, RecordStore
from .score import ReputationScore, ReputationCalculator
from .credit import CreditCurrency, CreditRegistry

__all__ = [
    "PerformanceRecord",
    "RecordStore",
    "ReputationScore",
    "ReputationCalculator",
    "CreditCurrency",
    "CreditRegistry",
]


def init_reputation():
    """初始化信誉层"""
    # 默认使用内存存储
    pass


# 自动初始化
init_reputation()