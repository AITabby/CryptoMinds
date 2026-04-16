#!/usr/bin/env python3
"""
启动单个 Agent 服务
用法: python3 start_agent.py <agent_name> [port]
示例: python3 start_agent.py tiedan 5001
"""

import sys
import subprocess
import os

def main():
    if len(sys.argv) < 2:
        print("用法: python3 start_agent.py <agent_name> [port]")
        print("可用的 agents: tiedan, choudan, ludan, four_meme")
        sys.exit(1)
    
    agent_name = sys.argv[1]
    port = sys.argv[2] if len(sys.argv) > 2 else None
    
    valid_agents = ["tiedan", "choudan", "ludan", "four_meme"]
    if agent_name not in valid_agents:
        print(f"❌ 未知的 agent: {agent_name}")
        print(f"可用的 agents: {', '.join(valid_agents)}")
        sys.exit(1)
    
    # 构建命令
    cmd = ["python3", "agents/agent_server.py", "--agent", agent_name]
    if port:
        cmd.extend(["--port", port])
    
    print(f"🚀 启动 {agent_name} Agent...")
    print(f"   命令: {' '.join(cmd)}")
    print(f"   按 Ctrl+C 停止服务")
    print()
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print(f"\n🛑 {agent_name} Agent 已停止")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()