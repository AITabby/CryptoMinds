# 贡献指南

感谢你对 CryptoMinds 的兴趣！

## 项目定位

CryptoMinds 是 **API 基础设施提供商**，为 AI Agent 平台提供信用评估和交易保障服务。

## 开发环境

```bash
# 克隆项目
git clone https://github.com/AITabby/CryptoMinds.git
cd CryptoMinds

# 安装依赖
pip install -r requirements.txt

# 启动 API 服务
python src/api_server.py

# 运行测试
pytest tests/
```

## 项目结构

```
CryptoMinds/
├── src/
│   ├── api_server.py      # REST API 服务
│   ├── credit/            # SACRED 信用分模块
│   ├── escrow/            # 托管模块
│   ├── reputation/        # 信誉层
│   └── settlement/        # 结算层
├── sdk/
│   ├── python/            # Python SDK
│   └── javascript/        # JavaScript SDK
├── demo/
│   ├── index.html         # Dashboard Demo
│   └── leaderboard.html   # 排行榜
├── scripts/
│   └── generate_data.py   # 数据生成脚本
├── tests/                 # 测试文件
├── docs/                  # 文档
│   ├── WHITEPAPER.md      # 白皮书
│   ├── SACRED.md          # 信用分说明
│   ├── API.md             # API 文档
│   └── QUICKSTART.md      # 快速开始
└── contracts/             # 智能合约
    └── ServiceEscrow.sol
```

## 代码规范

- Python: PEP 8, 使用 Black 格式化
- JavaScript: Standard 风格
- Solidity: Prettier + Solhint
- 提交信息: Conventional Commits

## 提交 PR

1. Fork 项目
2. 创建分支: `git checkout -b feature/xxx`
3. 提交代码: `git commit -m "feat: xxx"`
4. 推送分支: `git push origin feature/xxx`
5. 创建 Pull Request

## 报告问题

请在 GitHub Issues 中提交，包含：
- 问题描述
- 复现步骤
- 预期行为
- 实际行为
- 环境信息

## 许可证

MIT License
