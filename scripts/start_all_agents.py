#!/usr/bin/env python3
"""
启动所有 Agent 服务
用法: python3 start_all_agents.py
"""

import subprocess
import sys
import time
import os
import signal

def main():
    print("🚀 启动所有 CryptoMinds Agent 服务...")
    print("=" * 50)
    
    # Agent 配置
    agents = [
        {"name": "tiedan", "port": 5001, "description": "扫链卖家"},
        {"name": "choudan", "port": 5002, "description": "风控卖家"},
        {"name": "ludan", "port": 5003, "description": "汇总卖家"},
        {"name": "four_meme", "port": 5004, "description": "Four.meme 分析卖家"},
    ]
    
    # 存储进程
    processes = []
    
    try:
        # 启动每个 Agent
        for agent in agents:
            print(f"📡 启动 {agent['name']} ({agent['description']})...")
            
            cmd = [
                "python3", "agents/agent_server.py",
                "--agent", agent["name"],
                "--port", str(agent["port"])
            ]
            
            # 在后台启动进程
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            processes.append({
                "name": agent["name"],
                "process": process,
                "port": agent["port"]
            })
            
            # 等待一下，让服务启动
            time.sleep(1)
            
            # 检查进程是否还在运行
            if process.poll() is not None:
                print(f"  ❌ {agent['name']} 启动失败")
                stdout, stderr = process.communicate()
                print(f"     stdout: {stdout}")
                print(f"     stderr: {stderr}")
            else:
                print(f"  ✅ {agent['name']} 已启动 (端口 {agent['port']})")
        
        print("\n" + "=" * 50)
        print("✅ 所有 Agent 服务已启动!")
        print("\n服务地址:")
        for agent in agents:
            print(f"  {agent['name']}: http://localhost:{agent['port']}")
        
        print("\nAPI 端点:")
        print("  健康检查: GET /health")
        print("  服务信息: GET /info")
        print("  声誉查询: GET /reputation")
        print("  健康状态: GET /health-status")
        print("  执行任务: POST /execute")
        
        print("\n按 Ctrl+C 停止所有服务...")
        print("=" * 50)
        
        # 等待所有进程
        while True:
            time.sleep(1)
            
            # 检查是否有进程退出
            for proc_info in processes[:]:
                if proc_info["process"].poll() is not None:
                    print(f"⚠️ {proc_info['name']} 服务已停止")
                    processes.remove(proc_info)
            
            # 如果所有进程都停止了，退出
            if not processes:
                print("所有服务都已停止")
                break
    
    except KeyboardInterrupt:
        print("\n\n🛑 收到停止信号，正在停止所有服务...")
        
        # 停止所有进程
        for proc_info in processes:
            print(f"  停止 {proc_info['name']}...")
            try:
                proc_info["process"].terminate()
                proc_info["process"].wait(timeout=5)
                print(f"    ✅ {proc_info['name']} 已停止")
            except subprocess.TimeoutExpired:
                proc_info["process"].kill()
                print(f"    ⚠️ {proc_info['name']} 强制停止")
            except Exception as e:
                print(f"    ❌ 停止 {proc_info['name']} 失败: {e}")
        
        print("✅ 所有服务已停止")

if __name__ == "__main__":
    main()