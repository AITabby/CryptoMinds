#!/usr/bin/env python3
"""
测试 CryptoMinds 网络调用
"""

import json
import time
import sys
import os
import requests as req

# 添加项目路径
DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

def test_network_call():
    """测试网络调用是否正常工作"""
    print("=== 测试网络调用 ===")
    
    # 测试端点
    endpoints = {
        "tiedan": "http://localhost:5001",
        "choudan": "http://localhost:5002",
        "ludan": "http://localhost:5003",
        "four_meme": "http://localhost:5004",
    }
    
    print("1. 检查端点可达性...")
    for agent, endpoint in endpoints.items():
        try:
            # 测试健康检查端点
            resp = req.get(f"{endpoint}/health", timeout=2)
            if resp.status_code == 200:
                print(f"  ✅ {agent}: 端点可达 ({endpoint})")
            else:
                print(f"  ⚠️  {agent}: 端点返回 {resp.status_code}")
        except req.ConnectionError:
            print(f"  ❌ {agent}: 端点不可达 ({endpoint})")
        except Exception as e:
            print(f"  ❌ {agent}: 连接失败 - {e}")
    
    print("\n2. 测试声誉查询端点...")
    for agent, endpoint in endpoints.items():
        try:
            # 测试声誉查询端点
            resp = req.get(f"{endpoint}/reputation", timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                print(f"  ✅ {agent}: 声誉分数 {data.get('reputation_score', 'N/A')}")
            elif resp.status_code == 503:
                print(f"  ⚠️  {agent}: 声誉系统未启用")
            else:
                print(f"  ⚠️  {agent}: 端点返回 {resp.status_code}")
        except req.ConnectionError:
            print(f"  ❌ {agent}: 端点不可达")
        except Exception as e:
            print(f"  ❌ {agent}: 查询失败 - {e}")
    
    print("\n3. 测试执行任务端点（简单任务）...")
    for agent, endpoint in endpoints.items():
        try:
            # 发送一个简单的测试任务
            payload = {
                "request_id": f"test-{agent}-{int(time.time())}",
                "task": f"测试 {agent} 任务",
                "timestamp": time.time(),
            }
            resp = req.post(f"{endpoint}/execute", json=payload, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                duration = data.get('timestamp', time.time()) - payload['timestamp']
                print(f"  ✅ {agent}: 任务执行成功 ({duration:.2f}s)")
            else:
                print(f"  ⚠️  {agent}: 任务执行返回 {resp.status_code}")
        except req.ConnectionError:
            print(f"  ❌ {agent}: 端点不可达")
        except Exception as e:
            print(f"  ❌ {agent}: 任务执行失败 - {e}")
    
    print("\n✅ 网络调用测试完成\n")


def test_orchestrator_call():
    """测试 orchestrator 的网络调用"""
    print("=== 测试 Orchestrator 网络调用 ===")
    
    try:
        from orchestrator import run_agent_task, AGENT_ENDPOINTS
        
        print("1. 测试 run_agent_task 函数...")
        
        # 测试每个 agent
        for agent in AGENT_ENDPOINTS.keys():
            try:
                print(f"  调用 {agent}...")
                result = run_agent_task(agent, "测试任务")
                print(f"    ✅ {agent} 调用成功")
            except Exception as e:
                print(f"    ❌ {agent} 调用失败: {e}")
        
        print("\n✅ Orchestrator 网络调用测试完成\n")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}\n")


def main():
    """运行所有测试"""
    print("CryptoMinds 网络调用测试")
    print("=" * 50)
    
    test_network_call()
    test_orchestrator_call()
    
    print("=" * 50)
    print("网络调用测试完成！")
    print("\n提示:")
    print("1. 确保 Agent 服务已启动:")
    print("   python3 agents/agent_server.py --agent tiedan --port 5001")
    print("   python3 agents/agent_server.py --agent choudan --port 5002")
    print("   python3 agents/agent_server.py --agent ludan --port 5003")
    print("   python3 agents/agent_server.py --agent four_meme --port 5004")
    print("2. 如果服务未启动，orchestrator 会自动降级到本地执行")


if __name__ == "__main__":
    main()