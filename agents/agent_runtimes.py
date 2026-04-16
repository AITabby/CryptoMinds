"""
Mock Agent Runtimes — Demo 模式下返回模拟数据
"""
import json
import time

def tiedan_runtime(task_description="", token_address=None, **kwargs):
    return {
        "agent": "tiedan",
        "task": task_description,
        "result": {
            "tokens": [
                {"symbol": "PEPE2", "name": "Pepe 2.0", "price": "0.00000123", "marketCap": "$1.2M", "change24h": "+45%", "risk": "medium"},
                {"symbol": "DOGE3", "name": "Doge 3.0", "price": "0.00000456", "marketCap": "$890K", "change24h": "+12%", "risk": "low"},
                {"symbol": "SHIB2", "name": "Shiba 2.0", "price": "0.00000789", "marketCap": "$2.1M", "change24h": "-5%", "risk": "high"},
            ],
            "recommendation": "推荐 PEPE2，市值适中，24h 涨幅 45%，社区活跃度高",
            "summary": f"扫描完成，发现 3 个新上线 meme 币，推荐关注 PEPE2"
        },
        "timestamp": time.time()
    }

def choudan_runtime(task_description="", token_address=None, **kwargs):
    return {
        "agent": "choudan",
        "task": task_description,
        "result": {
            "risk_level": "medium",
            "score": 72,
            "checks": {
                "owner_renounced": True,
                "mint_function": False,
                "blacklist": False,
                "tax": "5%",
                "liquidity_locked": True
            },
            "summary": "合约基本安全，5% 交易税偏高但可接受，流动性已锁定"
        },
        "timestamp": time.time()
    }

def ludan_runtime(task_description="", token_address=None, **kwargs):
    return {
        "agent": "ludan",
        "task": task_description,
        "result": {
            "report": "根据当前市场分析，PEPE2 是最具潜力的标的。建议分批建仓，止损 -20%，止盈 +100%。注意控制仓位不超过总资金的 5%。",
            "format": "investment_report"
        },
        "timestamp": time.time()
    }

def pidan_runtime(task_description="", token_address=None, **kwargs):
    return {
        "agent": "pidan",
        "task": task_description,
        "result": {
            "holder_analysis": {
                "top_10_concentration": "35%",
                "whale_count": 12,
                "smart_money_inflow": "+$45K (24h)"
            },
            "summary": "持仓分布健康，前10地址占比35%，有聪明钱流入迹象"
        },
        "timestamp": time.time()
    }

RUNTIMES = {
    "tiedan": tiedan_runtime,
    "choudan": choudan_runtime,
    "ludan": ludan_runtime,
    "pidan": pidan_runtime,
}
