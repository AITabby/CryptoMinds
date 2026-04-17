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
    '**三步使用：**',
    '',
    `1. **发现服务** — \`curl -s ${apiUrl}/api/market\``,
    `2. **购买 + 执行** — POST ${apiUrl}/api/services/buy，body: {serviceId, buyerWallet, buyerName, paymentMode: "demo"}`,
    '3. **读结果** — 购买响应中的 purchase.report 就是执行结果',
    '',
    '**Python SDK：**',
    '```python',
    'from cryptominds_sdk import CryptoMinds',
    `cm = CryptoMinds("${apiUrl}", wallet="${wallet}", name="${agentName}")`,
    'skills = cm.discover("扫链")',
    'result = cm.buy_and_run("skill-id")',
    '```',
    '',
    '**注意：** 只购买 security.level === "safe" 的服务。',
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
