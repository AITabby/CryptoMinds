/**
 * Agent 路由
 *
 * /api/agents/register
 * /api/agents
 * /api/agents/:wallet/discover-plan
 * /api/agents/:wallet/auto-buy
 */

const express = require('express');
const router = express.Router();

function createAgentRoutes({
  getAgents,
  saveAgent,
  getAgent,
  getPurchases,
  getSellers,
  MINIMAX_API_KEY,
  MINIMAX_BASE_URL,
  MINIMAX_MODEL,  // 新增：可配置模型
  demoMode,
  DEMO_WALLET,
  w3,
}) {
  const AI_MODEL = MINIMAX_MODEL || 'abab6.5s-chat';  // 默认值但可配置
  // Agent 注册
  router.post('/agents/register', async (req, res) => {
    const { agent_id, name, wallet, framework, skills, active, feeRate, deposit, signature, message } = req.body;

    if (!agent_id || !wallet) {
      return res.json({ ok: false, error: '缺少 agent_id 或 wallet' });
    }

    if (!w3.utils.isAddress(wallet)) {
      return res.json({ ok: false, error: '无效的钱包地址' });
    }

    // 签名验证：防止冒充他人钱包注册
    if (signature && message) {
      try {
        const recovered = w3.eth.accounts.recover(message, signature);
        if (recovered.toLowerCase() !== wallet.toLowerCase()) {
          return res.json({ ok: false, error: '签名与钱包地址不一致' });
        }
      } catch {
        return res.json({ ok: false, error: '签名验证失败' });
      }
    } else if (!demoMode) {
      return res.json({ ok: false, error: '非 Demo 模式必须提供钱包签名' });
    }

    try {
      const agent = {
        id: agent_id,
        wallet: wallet.toLowerCase(),
        name: name || agent_id,
        framework: framework || 'generic',
        skills: skills || [],
        active: active !== false,
        feeRate: feeRate || 0,
        deposit: deposit || 0,
        createdAt: new Date().toISOString(),
      };

      await saveAgent(agent);
      res.json({ ok: true, agent });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 列出所有 Agent
  router.get('/agents', async (req, res) => {
    try {
      const agents = await getAgents();
      res.json({ ok: true, agents });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 发现计划（AI 分析）
  router.post('/agents/:wallet/discover-plan', async (req, res) => {
    const { wallet } = req.params;
    const { input, amount, chain } = req.body;

    if (!MINIMAX_API_KEY) {
      return res.json({ ok: false, error: 'AI 服务未配置' });
    }

    try {
      const sellers = await getSellers();
      const sellerList = sellers.sellers || [];

      // 构建 AI prompt
      // 清洗用户输入，防止 prompt 注入
      const sanitizedInput = String(input).replace(/[\n\r]/g, ' ').slice(0, 200);
      const prompt = `你是一个加密货币交易助手。用户需求: "${sanitizedInput}"
可用卖家列表:
${sellerList.map(s => `- ${s.name}: 押金 ${s.deposit} BNB, 评分 ${s.rating}, 费率 ${s.feeRate}`).join('\n')}

请分析并推荐最合适的卖家。返回 JSON 格式:
{
  "recommended_seller": "卖家名称",
  "reason": "推荐理由",
  "strategy": "建议策略",
  "risk_level": "低/中/高"
}`;

      const response = await fetch(`${MINIMAX_BASE_URL}/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${MINIMAX_API_KEY}`,
        },
        body: JSON.stringify({
          model: AI_MODEL,
          messages: [{ role: 'user', content: prompt }],
          temperature: 0.7,
        }),
      });

      const data = await response.json();
      const content = data.choices?.[0]?.message?.content || '';

      // 尝试解析 JSON
      let plan = null;
      try {
        const jsonMatch = content.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          plan = JSON.parse(jsonMatch[0]);
        }
      } catch {}

      res.json({
        ok: true,
        plan,
        raw: content,
        sellers: sellerList.slice(0, 5),
      });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // 自动购买
  router.post('/agents/:wallet/auto-buy', async (req, res) => {
    const { wallet } = req.params;
    const { input, amount, chain, strategy } = req.body;

    if (!amount || amount <= 0) {
      return res.json({ ok: false, error: '无效金额' });
    }

    try {
      const sellers = await getSellers();
      const sellerList = sellers.sellers || [];

      if (sellerList.length === 0) {
        return res.json({ ok: false, error: '没有可用的卖家' });
      }

      // 简单选择：按权重排序
      const sorted = sellerList.sort((a, b) => (b.weight || 0) - (a.weight || 0));
      const selected = sorted[0];

      res.json({
        ok: true,
        seller: {
          wallet: selected.wallet,
          name: selected.name,
          rating: selected.rating,
          feeRate: selected.feeRate,
        },
        amount,
        chain: chain || 'bsc',
        status: 'pending',
      });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  // Agent 自主下单（简化版）
  router.post('/agent-buy', async (req, res) => {
    const { buyer_wallet, amount_bnb, task_type, params } = req.body;

    if (!buyer_wallet || !amount_bnb) {
      return res.json({ ok: false, error: '缺少 buyer_wallet 或 amount_bnb' });
    }

    try {
      const sellers = await getSellers();
      const sellerList = sellers.sellers || [];

      if (sellerList.length === 0) {
        return res.json({ ok: false, error: '没有可用的卖家' });
      }

      // 选择最优卖家
      const sorted = sellerList.sort((a, b) => (b.weight || 0) - (a.weight || 0));
      const selected = sorted[0];

      res.json({
        ok: true,
        order: {
          buyer_wallet,
          seller_wallet: selected.wallet,
          seller_name: selected.name,
          amount: amount_bnb,
          task_type: task_type || 'token_delivery',
          params: params || {},
          status: 'matched',
        },
      });
    } catch (err) {
      res.json({ ok: false, error: err.message });
    }
  });

  return router;
}

module.exports = { createAgentRoutes };
