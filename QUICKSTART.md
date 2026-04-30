# CryptoMinds 快速启动指南

## 一键启动 Agent 服务

```bash
# 1. 安装依赖
pip3 install flask web3 --break-system-packages

# 2. 启动 API 服务（端口 3458）
python3 api_server.py

# 3. 启动 Agent 服务（另一个终端）
python3 agent_service.py \
  --agent-id test-agent \
  --wallet 0xd2f899CE74320AEf9d8f2359183232a554f4C0E1 \
  --task-types token_delivery \
  --chains mock,bsc
```

## 测试完整流程

```python
# test_flow.py
from agent_service import create_service, Task
from decimal import Decimal

# 创建服务
service = create_service(
    agent_id="test-seller",
    wallet="0xseller",
    task_types=["token_delivery"],
    supported_chains=["mock"],
)

# 启动
service.start()

# 提交任务
task = Task(
    task_id="test-001",
    task_type="token_delivery",
    buyer_wallet="0xbuyer",
    seller_wallet="0xseller",
    amount=Decimal("0.01"),
    chain="mock",
    channel_id="mock",
)
service.submit_task(task)

# 等待执行
import time
time.sleep(2)

# 查看状态
print(service.get_status())

# 停止
service.stop()
```

## 当前协议能力

```
结算通道: BSC, ETH, SOL, Mock
验证门: token_delivery, data_delivery, compute_result, signal_stream, content_delivery
任务闭环: 执行 → 验证 → 结算 → 履约 → 信誉
信用货币: 发行 → 转账 → 支付
```

## 核心文件

| 文件 | 用途 |
|------|------|
| `agent_service.py` | Agent 服务入口 |
| `api_server.py` | HTTP API 服务 |
| `protocol.py` | 协议统一入口 |
| `agent_daemon.py` | 任务执行守护进程 |
| `task_closer.py` | 验证+结算闭环 |
| `market_listener.py` | 市场任务监听 |