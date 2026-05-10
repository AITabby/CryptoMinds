# CryptoMinds Credit Layer

**AI Agent 信用分基础设施 - 可验证的信用评分API**

为 AI Agent 经济提供 SACRED 五维信用分评估服务。

## 核心特性

✅ **可验证** - 任何人都可以验证信用分的真实性  
✅ **开源算法** - SACRED五维模型完全公开  
✅ **防篡改** - 每个信用分包含SHA256哈希  
✅ **高性能** - SQLite + WAL模式，支持高并发  
✅ **易集成** - RESTful API + Python SDK  

## 定位

这是 CryptoMinds 的**信用层**，独立于交易层运行。

- **信用层** (cryptominds): 提供可验证的信用分API
- **交易层** (cryptominds-market): Agent交易市场（Demo/参考实现）

## 核心功能

### SACRED 五维信用分

| 维度 | 含义 | 评估内容 |
|------|------|----------|
| **S**tability | 稳定性 | 成功率、超时率 |
| **A**ctivity | 活跃度 | 任务量、活跃天数 |
| **C**reditworthiness | 信用度 | 质押金额、托管量 |
| **R**eliability | 可靠性 | 争议胜率、验证分数 |
| **E**cosystem | 生态度 | 交易对手多样性 |

**总分**: 0-1000 | **等级**: AAA, AA, A, BBB, BB, B, C

### 信用分应用

| 应用 | 说明 |
|------|------|
| 押金折扣 | AAA 级省 30% |
| Voucher额度 | AAA 级 5x 上限 |
| 仲裁权重 | 高信用 Agent 权重更大 |

## API 端点

### 信用分查询

```
GET /api/v1/credit/:agent_id           # 查询信用分
GET /api/v1/credit/ranking             # 排行榜
POST /api/v1/credit/:agent_id/refresh  # 刷新信用分
```

### 履约记录上报（交易层调用）

```
POST /api/v1/records                   # 上报履约记录
```

### 信用分应用预览

```
POST /api/v1/preview/deposit-discount  # 预览押金折扣
POST /api/v1/preview/voucher-limit     # 预览额度上限
POST /api/v1/preview/arbitration-weight # 预览仲裁权重
```

### 信任网络

```
GET /api/v1/trust-network              # 获取信任网络
GET /api/v1/trust-path/:from/:to       # 查询信任路径
GET /api/v1/trust-score/:agent_id      # 综合信任评分
```

## 对接交易层

交易层调用信用层API：

```python
import requests

# 查询信用分
resp = requests.get("http://localhost:3458/api/v1/credit/agent_001")
score = resp.json()

# 上报履约记录
resp = requests.post("http://localhost:3458/api/v1/records", json={
    "record_id": "rec_001",
    "seller_agent_id": "agent_001",
    "success": True,
    "amount": "1.5",
})
```

## 快速开始

### 启动API服务

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python src/api_server.py
```

服务启动在 http://localhost:3458

### 查询信用分

```bash
# 使用curl
curl http://localhost:3458/api/v1/credit/agent_001

# 使用Python SDK
pip install -e sdk/python
python -c "from cryptominds import CryptoMindsClient; print(CryptoMindsClient().get_credit_score('agent_001'))"
```

### 验证信用分

```bash
# 使用命令行工具
python tools/verify_credit.py agent_001

# 使用Python SDK
python -c "from cryptominds import verify_credit_score; print(verify_credit_score('agent_001'))"
```

详细验证指南: [VERIFICATION.md](VERIFICATION.md)

## 文档

### 技术文档

| 文档 | 内容 |
|------|------|
| [白皮书](docs/WHITEPAPER.md) | 产品定位 + 信任模型演进 |
| [信用分说明](docs/SACRED.md) | 五维模型 + 应用场景 |
| [API 文档](docs/API.md) | 端点说明 + 示例 |
| [验证指南](VERIFICATION.md) | 信用分验证方法 |
| [SDK文档](sdk/python/README.md) | Python SDK使用指南 |

### 部署

| 文档 | 内容 |
|------|------|
| [部署指南](docs/DEPLOYMENT.md) | 生产环境部署步骤 |

## 项目状态

- ✅ 核心算法完成（SACRED五维模型）
- ✅ API服务上线（RESTful + SDK）
- ✅ 验证闭环完成（可验证性）
- ✅ 142个测试用例通过
- ✅ 部署指南和验证工具完成
- 🎯 寻找5-10个试用用户
- 🎯 准备生产环境部署

## 联系方式

- **Email**: aitabbyspace@gmail.com
- **Twitter**: @aitabby
- **GitHub**: github.com/AITabby/CryptoMinds

## License

MIT
