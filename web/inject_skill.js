/**
 * 注册时自动注入 CryptoMinds 买服务能力到 Agent workspace
 * - 如果传了 workspacePath，直接写入该目录
 * - 否则按 OpenClaw 约定尝试 ~/.openclaw/workspace-{name}/
 */
const fs = require('fs');
const path = require('path');
const os = require('os');

function injectCryptoMindsSkill(agentName, wallet, workspacePath) {
  // 确定 workspace 目录
  let wsDir = workspacePath;
  if (!wsDir) {
    wsDir = path.join(os.homedir(), '.openclaw', `workspace-${agentName}`);
  }

  if (!fs.existsSync(wsDir)) {
    try {
      fs.mkdirSync(wsDir, { recursive: true });
      console.log(`[inject] 已创建 workspace: ${wsDir}`);
    } catch (e) {
      console.log(`[inject] 无法创建 workspace: ${wsDir}，跳过自动注入`);
      return false;
    }
  }

  const apiUrl = process.env.MARKET_URL || 'http://localhost:3456';

  const lines = [
    '### CryptoMinds — Agent 市场（注册时自动注入）',
    '',
    `你已在 CryptoMinds 市场注册，钱包: ${wallet}。当你缺少某个能力时，可以自主在市场发现并购买服务。`,
    '',
    '**四步使用：**',
    '',
    `1. **发现服务** — \`curl -s ${apiUrl}/api/market\``,
    `2. **先拿推荐** — POST ${apiUrl}/api/agents/${wallet}/discover-plan，body: {task}`,
    `3. **Agent 自己决定再执行** — POST ${apiUrl}/api/agents/${wallet}/auto-buy，body: {task, purchasePlan, paymentPreference}`,
    '4. **读结果** — auto-buy 响应中的 finalResult，或订单里的 purchase.result / purchase.report',
    '',
    '**Python SDK：**',
    '```python',
    'from cryptominds_sdk import CryptoMinds',
    `cm = CryptoMinds("${apiUrl}", wallet="${wallet}", name="${agentName}")`,
    'skills = cm.discover("扫链")',
    'result = cm.buy_and_run("skill-id")',
    '# 先 discover-plan，再由你的 Agent 自己决定 purchasePlan 后调用 auto-buy',
    '```',
    '',
    '**注意：** 只购买 security.level === "safe" 的服务。',
    '',
    '### 通知 API（统一通知通道）',
    '',
    '人和 Agent 共用同一套通知 API，有新订单/结果时自动产生通知。',
    '',
    `- **检查通知** — curl -s ${apiUrl}/api/notifications?wallet=${wallet}`,
    `- **未读数量** — curl -s "${apiUrl}/api/notifications?wallet=${wallet}&unread=true" 返回 unread 字段`,
    `- **标记已读** — POST ${apiUrl}/api/notifications/{id}/read`,
    '',
    '**轮询建议：** 每 10-30 秒检查一次通知，有 new_order 类型的通知说明有人购买了你的服务，应自动执行交付。',
  ];

  const CRYPTOMINDS_BLOCK = lines.join('\n');

  // 写入 TOOLS.md（追加，不覆盖）
  const toolsPath = path.join(wsDir, 'TOOLS.md');
  let existing = '';
  if (fs.existsSync(toolsPath)) {
    existing = fs.readFileSync(toolsPath, 'utf8');
    // 防重复注入
    if (existing.includes('CryptoMinds — Agent 市场')) {
      console.log(`[inject] ${toolsPath} 已有 CryptoMinds 配置，跳过`);
      return true;
    }
  }

  const newContent = existing
    ? existing + '\n\n' + CRYPTOMINDS_BLOCK
    : CRYPTOMINDS_BLOCK + '\n';

  fs.writeFileSync(toolsPath, newContent, 'utf8');
  console.log(`[inject] 已写入 CryptoMinds 能力到 ${toolsPath}`);
  return true;
}

module.exports = { injectCryptoMindsSkill };
