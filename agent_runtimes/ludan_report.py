#!/usr/bin/env python3
"""
Flow Surfer — 汇总卖家
汇总各卖家结果生成最终报告
"""
import json
import time


def run(task_description=None, token_address=None):
    """执行报告整理"""
    try:
        from agent_events import think as _think, execute as _exec, result as _result
    except ImportError:
        _think = _exec = _result = lambda *a, **kw: None

    _think("Flow Surfer", "收到报告任务，汇总各卖家结果")
    
    scan_data = None
    risk_data = None

    # 尝试从 task 中解析其他卖家的结果
    if isinstance(task_description, dict):
        scan_data = task_description.get("scan_result")
        risk_data = task_description.get("risk_result")
    elif isinstance(task_description, str):
        try:
            parsed = json.loads(task_description)
            scan_data = parsed.get("scan_result")
            risk_data = parsed.get("risk_result")
        except Exception:
            pass

    report = {
        "title": "CryptoMinds Meme 币综合分析报告",
        "timestamp": time.time(),
        "agent": "ludan",
    }

    if scan_data and isinstance(scan_data, dict):
        tokens = scan_data.get("hot_tokens", [])
        recommendation = scan_data.get("recommendation", "暂无推荐")
        report["scan_summary"] = f"扫描到 {len(tokens)} 个 BSC 最新代币"
        report["top_picks"] = [
            {"symbol": t.get("symbol"), "price": t.get("price_usd"),
             "volume_24h": t.get("volume_24h"), "change_24h": t.get("price_change_24h")}
            for t in tokens[:3]
        ]
        report["recommendation"] = recommendation
    else:
        report["scan_summary"] = "扫描数据未传入，请参考独立报告"

    if risk_data and isinstance(risk_data, dict):
        report["risk_summary"] = f"{risk_data.get('symbol', '未知代币')} 风控评分: {risk_data.get('score', 'N/A')}/100 ({risk_data.get('risk', '未知')})"
        report["risk_conclusion"] = risk_data.get("conclusion", "风控分析未传入")
        report["risk_checks"] = risk_data.get("checks", [])
    else:
        report["risk_summary"] = "风控数据未传入，请参考独立报告"

    # 综合建议
    if scan_data and risk_data:
        scan_ok = isinstance(scan_data, dict) and scan_data.get("recommendation", "暂无") != "暂无明确推荐"
        risk_ok = isinstance(risk_data, dict) and risk_data.get("score", 0) >= 50
        if scan_ok and risk_ok:
            report["verdict"] = "✅ 值得关注：扫描有亮点且风控达标，建议小仓位试水"
        elif scan_ok:
            report["verdict"] = "⚠️ 谨慎参与：有热点但风控存在隐患，控制仓位"
        elif risk_ok:
            report["verdict"] = "⚠️ 观望为主：风控尚可但缺乏热点信号"
        else:
            report["verdict"] = "❌ 暂不推荐：热点不足且风控风险较高"
    else:
        report["verdict"] = "📋 各卖家报告已收录，请综合参考后决策"

    _result("Flow Surfer", f"报告生成完毕: {report.get('verdict', '')[:40]}")

    return {"report": report}
