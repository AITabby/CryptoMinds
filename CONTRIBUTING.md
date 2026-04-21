# 贡献指南

感谢你对 CryptoMinds 的兴趣！

## 开发环境

```bash
# 克隆项目
git clone https://github.com/AITabby/CryptoMinds.git
cd CryptoMinds

# 安装依赖
cd web && npm install

# 启动开发服务器
npm run dev
```

## 项目结构

```
CryptoMinds/
├── contracts/          # Solidity 合约
│   └── ServiceEscrow.sol
├── web/                # 后端服务
│   ├── server.js       # Express 服务
│   ├── public/         # 前端静态文件
│   │   └── index.js    # 前端逻辑
│   └── lib/            # 工具模块
│       └── escrow.js   # 合约交互
├── scripts/            # 部署脚本
├── tests/              # 测试文件
└── docs/               # 文档
```

## 代码规范

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
