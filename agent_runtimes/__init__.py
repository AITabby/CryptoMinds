"""
CryptoMinds Agent Runtimes
每个 Agent 的具体业务逻辑，独立于 SDK。
SDK 只管调用，不管怎么执行。
"""
from .tiedan_scan import run as tiedan_scan
from .choudan_risk import run as choudan_risk
from .ludan_report import run as ludan_report
from .four_meme import run as four_meme

# Agent 名称 → 执行函数
RUNTIMES = {
    "tiedan": tiedan_scan,
    "choudan": choudan_risk,
    "ludan": ludan_report,
    "four_meme": four_meme,
}

__all__ = ["RUNTIMES"]
