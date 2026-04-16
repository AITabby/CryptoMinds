#!/usr/bin/env python3
"""
CryptoMinds Agent 声誉系统
跟踪每个 Agent 的交易记录和性能指标
"""

import json
import time
import os
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

class AgentReputation:
    """Agent 声誉管理系统"""
    
    def __init__(self, data_file: str = None):
        """
        初始化声誉系统
        
        Args:
            data_file: 声誉数据存储文件路径
        """
        if data_file is None:
            # 默认存储在 agents 目录下
            base_dir = os.path.dirname(os.path.abspath(__file__))
            data_file = os.path.join(base_dir, "reputation_data.json")
        
        self.data_file = data_file
        self.agents_data = self._load_data()
        
        # 声誉评分权重配置
        self.weights = {
            "success_rate": 0.4,      # 成功率权重
            "response_time": 0.3,     # 响应时间权重
            "stability": 0.3,         # 稳定性权重（异常次数）
        }
        
        # 响应时间阈值（秒）
        self.response_time_thresholds = {
            "excellent": 1.0,    # < 1秒为优秀
            "good": 3.0,         # < 3秒为良好
            "acceptable": 10.0,  # < 10秒为可接受
            # > 10秒为差
        }
    
    def _load_data(self) -> Dict:
        """加载声誉数据"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ 加载声誉数据失败: {e}")
        
        # 返回默认结构
        return {
            "agents": {},
            "transactions": [],
            "last_updated": time.time()
        }
    
    def _save_data(self):
        """保存声誉数据"""
        try:
            self.agents_data["last_updated"] = time.time()
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.agents_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ 保存声誉数据失败: {e}")
    
    def _get_agent_data(self, agent_name: str) -> Dict:
        """获取或创建 Agent 数据"""
        if agent_name not in self.agents_data["agents"]:
            self.agents_data["agents"][agent_name] = {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "total_response_time": 0.0,
                "response_times": [],  # 最近100次响应时间
                "exceptions": [],
                "reputation_score": 100.0,  # 初始声誉分数
                "created_at": time.time(),
                "last_active": time.time()
            }
        return self.agents_data["agents"][agent_name]
    
    def record_transaction(self, agent_name: str, success: bool, response_time: float = 0.0, 
                          error_message: str = None, request_id: str = None):
        """
        记录交易执行结果
        
        Args:
            agent_name: Agent 名称
            success: 是否成功
            response_time: 响应时间（秒）
            error_message: 错误信息（如果有）
            request_id: 请求 ID
        """
        agent_data = self._get_agent_data(agent_name)
        
        # 更新基础统计
        agent_data["total_requests"] += 1
        agent_data["last_active"] = time.time()
        
        if success:
            agent_data["successful_requests"] += 1
            agent_data["total_response_time"] += response_time
            
            # 保存响应时间（只保留最近100次）
            agent_data["response_times"].append(response_time)
            if len(agent_data["response_times"]) > 100:
                agent_data["response_times"].pop(0)
        else:
            agent_data["failed_requests"] += 1
            if error_message:
                agent_data["exceptions"].append({
                    "timestamp": time.time(),
                    "error": error_message,
                    "request_id": request_id
                })
                # 只保留最近50个异常记录
                if len(agent_data["exceptions"]) > 50:
                    agent_data["exceptions"].pop(0)
        
        # 记录到全局交易日志
        transaction_record = {
            "agent": agent_name,
            "timestamp": time.time(),
            "success": success,
            "response_time": response_time,
            "request_id": request_id
        }
        if error_message:
            transaction_record["error"] = error_message
        
        self.agents_data["transactions"].append(transaction_record)
        
        # 只保留最近1000条交易记录
        if len(self.agents_data["transactions"]) > 1000:
            self.agents_data["transactions"] = self.agents_data["transactions"][-1000:]
        
        # 重新计算声誉分数
        self._calculate_reputation(agent_name)
        
        # 保存到文件
        self._save_data()
    
    def _calculate_reputation(self, agent_name: str):
        """计算 Agent 的声誉分数"""
        agent_data = self._get_agent_data(agent_name)
        
        if agent_data["total_requests"] == 0:
            return
        
        # 1. 成功率评分 (0-100)
        success_rate = agent_data["successful_requests"] / agent_data["total_requests"]
        success_score = success_rate * 100
        
        # 2. 响应时间评分 (0-100)
        response_time_score = 100
        if agent_data["response_times"]:
            avg_response_time = sum(agent_data["response_times"]) / len(agent_data["response_times"])
            
            if avg_response_time <= self.response_time_thresholds["excellent"]:
                response_time_score = 100
            elif avg_response_time <= self.response_time_thresholds["good"]:
                response_time_score = 80
            elif avg_response_time <= self.response_time_thresholds["acceptable"]:
                response_time_score = 60
            else:
                response_time_score = 40
        
        # 3. 稳定性评分 (基于最近异常次数)
        recent_exceptions = 0
        current_time = time.time()
        hour_ago = current_time - 3600
        
        for exc in agent_data["exceptions"]:
            if exc["timestamp"] > hour_ago:
                recent_exceptions += 1
        
        # 最近1小时内异常次数越少，分数越高
        if recent_exceptions == 0:
            stability_score = 100
        elif recent_exceptions <= 2:
            stability_score = 80
        elif recent_exceptions <= 5:
            stability_score = 60
        elif recent_exceptions <= 10:
            stability_score = 40
        else:
            stability_score = 20
        
        # 计算综合声誉分数
        total_score = (
            success_score * self.weights["success_rate"] +
            response_time_score * self.weights["response_time"] +
            stability_score * self.weights["stability"]
        )
        
        agent_data["reputation_score"] = round(total_score, 2)
    
    def get_reputation(self, agent_name: str) -> Dict:
        """
        获取 Agent 的声誉信息
        
        Returns:
            包含声誉分数和详细统计的字典
        """
        agent_data = self._get_agent_data(agent_name)
        
        # 计算平均响应时间
        avg_response_time = 0
        if agent_data["response_times"]:
            avg_response_time = sum(agent_data["response_times"]) / len(agent_data["response_times"])
        
        # 计算成功率
        success_rate = 0
        if agent_data["total_requests"] > 0:
            success_rate = agent_data["successful_requests"] / agent_data["total_requests"]
        
        # 确定声誉等级
        score = agent_data["reputation_score"]
        if score >= 90:
            grade = "A+"
            description = "优秀"
        elif score >= 80:
            grade = "A"
            description = "良好"
        elif score >= 70:
            grade = "B"
            description = "一般"
        elif score >= 60:
            grade = "C"
            description = "较差"
        else:
            grade = "D"
            description = "差"
        
        return {
            "agent": agent_name,
            "reputation_score": score,
            "grade": grade,
            "description": description,
            "statistics": {
                "total_requests": agent_data["total_requests"],
                "successful_requests": agent_data["successful_requests"],
                "failed_requests": agent_data["failed_requests"],
                "success_rate": round(success_rate * 100, 2),
                "avg_response_time": round(avg_response_time, 3),
                "last_active": agent_data["last_active"],
                "recent_exceptions": len([
                    e for e in agent_data["exceptions"] 
                    if e["timestamp"] > time.time() - 3600
                ])
            }
        }
    
    def get_all_reputations(self) -> List[Dict]:
        """获取所有 Agent 的声誉信息"""
        result = []
        for agent_name in self.agents_data["agents"]:
            result.append(self.get_reputation(agent_name))
        
        # 按声誉分数排序
        result.sort(key=lambda x: x["reputation_score"], reverse=True)
        return result
    
    def get_transaction_history(self, agent_name: str = None, limit: int = 50) -> List[Dict]:
        """
        获取交易历史
        
        Args:
            agent_name: Agent 名称（可选）
            limit: 返回记录数量限制
        """
        transactions = self.agents_data["transactions"]
        
        if agent_name:
            transactions = [t for t in transactions if t["agent"] == agent_name]
        
        # 按时间倒序排序
        transactions.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return transactions[:limit]
    
    def get_agent_health_status(self, agent_name: str) -> Dict:
        """
        获取 Agent 健康状态
        
        Returns:
            健康状态信息
        """
        reputation = self.get_reputation(agent_name)
        
        # 检查最近活动
        last_active = reputation["statistics"]["last_active"]
        time_since_active = time.time() - last_active
        
        # 检查最近异常
        recent_exceptions = reputation["statistics"]["recent_exceptions"]
        
        # 确定健康状态
        if reputation["reputation_score"] >= 70 and recent_exceptions <= 2:
            if time_since_active < 300:  # 5分钟内活跃
                health_status = "healthy"
                status_emoji = "🟢"
            else:
                health_status = "idle"
                status_emoji = "🟡"
        elif reputation["reputation_score"] >= 50:
            health_status = "degraded"
            status_emoji = "🟠"
        else:
            health_status = "unhealthy"
            status_emoji = "🔴"
        
        return {
            "agent": agent_name,
            "health_status": health_status,
            "status_emoji": status_emoji,
            "reputation_score": reputation["reputation_score"],
            "last_active": last_active,
            "time_since_active": round(time_since_active, 1),
            "recent_exceptions": recent_exceptions,
            "recommendation": self._get_health_recommendation(health_status, reputation)
        }
    
    def _get_health_recommendation(self, health_status: str, reputation: Dict) -> str:
        """获取健康状态建议"""
        if health_status == "healthy":
            return "Agent 运行正常，可继续使用"
        elif health_status == "idle":
            return "Agent 一段时间未活跃，但状态正常"
        elif health_status == "degraded":
            return "Agent 性能下降，建议检查日志或重启服务"
        else:
            return "Agent 状态异常，建议立即检查或重启服务"
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """清理旧数据"""
        current_time = time.time()
        cutoff_time = current_time - (days_to_keep * 24 * 3600)
        
        # 清理旧的交易记录
        self.agents_data["transactions"] = [
            t for t in self.agents_data["transactions"]
            if t["timestamp"] > cutoff_time
        ]
        
        # 清理 Agent 的旧异常记录
        for agent_data in self.agents_data["agents"].values():
            agent_data["exceptions"] = [
                e for e in agent_data["exceptions"]
                if e["timestamp"] > cutoff_time
            ]
        
        self._save_data()
        print(f"🧹 已清理 {days_to_keep} 天前的数据")


# 创建全局实例
_reputation_system = None

def get_reputation_system() -> AgentReputation:
    """获取全局声誉系统实例"""
    global _reputation_system
    if _reputation_system is None:
        _reputation_system = AgentReputation()
    return _reputation_system


# 便捷函数
def record_success(agent_name: str, response_time: float, request_id: str = None):
    """记录成功交易"""
    system = get_reputation_system()
    system.record_transaction(agent_name, True, response_time, None, request_id)

def record_failure(agent_name: str, error_message: str, request_id: str = None):
    """记录失败交易"""
    system = get_reputation_system()
    system.record_transaction(agent_name, False, 0.0, error_message, request_id)

def get_reputation(agent_name: str) -> Dict:
    """获取 Agent 声誉"""
    system = get_reputation_system()
    return system.get_reputation(agent_name)

def get_all_reputations() -> List[Dict]:
    """获取所有 Agent 声誉"""
    system = get_reputation_system()
    return system.get_all_reputations()


if __name__ == "__main__":
    # 测试代码
    print("=== CryptoMinds 声誉系统测试 ===\n")
    
    # 创建测试数据
    rep = AgentReputation("test_reputation.json")
    
    # 模拟一些交易
    import random
    
    agents = ["tiedan", "choudan", "ludan", "four_meme"]
    for agent in agents:
        for i in range(20):
            success = random.random() > 0.1  # 90% 成功率
            response_time = random.uniform(0.5, 5.0)
            if success:
                rep.record_transaction(agent, True, response_time, request_id=f"test-{i}")
            else:
                rep.record_transaction(agent, False, 0.0, "测试错误", request_id=f"test-{i}")
    
    print("\n=== 声誉排名 ===")
    all_reps = rep.get_all_reputations()
    for i, r in enumerate(all_reps, 1):
        print(f"{i}. {r['agent']}: {r['reputation_score']}分 ({r['grade']}) - {r['description']}")
        print(f"   成功率: {r['statistics']['success_rate']}%, 平均响应: {r['statistics']['avg_response_time']}s")
    
    print("\n=== 健康状态 ===")
    for agent in agents:
        health = rep.get_agent_health_status(agent)
        print(f"{health['status_emoji']} {agent}: {health['health_status']} ({health['reputation_score']}分)")
    
    # 清理测试文件
    if os.path.exists("test_reputation.json"):
        os.remove("test_reputation.json")