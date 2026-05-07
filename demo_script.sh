#!/bin/bash
# CryptoMinds Demo Script - 录屏专用
# 确保先启动 API: python3 src/api_server.py

API="http://localhost:3458"

echo "=========================================="
echo "CryptoMinds Demo - AI Agent 信任基础设施"
echo "=========================================="
echo ""

# 1. 信用分排行榜
echo "📊 1. 信用分排行榜（Top 5）"
echo "---"
curl -s "$API/api/v1/credit/ranking?limit=5" | python3 -m json.tool
echo ""
echo "按 Enter 继续..."
read
echo ""

# 2. 查询 AAA 级 Agent 信用分
echo "🏆 2. 查询 AAA 级 Agent 信用分"
echo "---"
curl -s "$API/api/v1/credit/agent_high_0001" | python3 -m json.tool
echo ""
echo "按 Enter 继续..."
read
echo ""

# 3. 查询低信用 Agent 对比
echo "⚠️  3. 查询 B 级 Agent 信用分（对比）"
echo "---"
curl -s "$API/api/v1/credit/agent_malicious_0031" | python3 -m json.tool
echo ""
echo "按 Enter 继续..."
read
echo ""

# 4. 押金折扣预览（AAA 级）
echo "💰 4. 押金折扣预览 - AAA 级 Agent"
echo "---"
echo "原价 1.0 BNB，AAA 级只需..."
curl -s -X POST "$API/api/v1/escrow/discount-preview" \
  -H "Content-Type: application/json" \
  -d '{"seller": "agent_high_0001", "amount": 1.0}' | python3 -m json.tool
echo ""
echo "按 Enter 继续..."
read
echo ""

# 5. 创建托管（带折扣）
echo "📝 5. 创建托管交易（自动应用信用分折扣）"
echo "---"
curl -s -X POST "$API/api/v1/escrow/create" \
  -H "Content-Type: application/json" \
  -d '{"buyer": "buyer_001", "seller": "agent_high_0001", "amount": 1.0}' | python3 -m json.tool
echo ""
echo "按 Enter 继续..."
read
echo ""

# 6. Voucher 额度预览
echo "🎫 6. Voucher 额度预览（信用分 → 额度上限）"
echo "---"
echo "AAA 级 Agent 额度上限..."
curl -s -X POST "$API/api/v1/voucher/limit-preview" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "agent_high_0001"}' | python3 -m json.tool
echo ""
echo "对比 B 级 Agent..."
curl -s -X POST "$API/api/v1/voucher/limit-preview" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "agent_malicious_0031"}' | python3 -m json.tool
echo ""
echo "按 Enter 继续..."
read
echo ""

# 7. 仲裁权重预览
echo "⚖️  7. 仲裁权重预览（信用分 → 投票权重）"
echo "---"
echo "AAA 级仲裁员权重..."
curl -s -X POST "$API/api/v1/arbitrate/weight-preview" \
  -H "Content-Type: application/json" \
  -d '{"arbitrator": "agent_high_0001"}' | python3 -m json.tool
echo ""
echo "B 级仲裁员权重..."
curl -s -X POST "$API/api/v1/arbitrate/weight-preview" \
  -H "Content-Type: application/json" \
  -d '{"arbitrator": "agent_malicious_0031"}' | python3 -m json.tool
echo ""

echo "=========================================="
echo "✅ Demo 完成！"
echo ""
echo "展示的核心价值："
echo "  - 信用分体系：AAA vs B 级对比"
echo "  - 押金折扣：AAA 级省 30%"
echo "  - Voucher 额度：AAA 级 5x 额度"
echo "  - 仲裁权重：AAA 级 2x 权重"
echo "=========================================="
