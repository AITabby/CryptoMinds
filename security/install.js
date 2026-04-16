/**
 * CryptoMinds Skill 自动安装器
 * 
 * 购买成功后，自动将 Skill 安装到买家 Agent 的技能库
 * 安装后 Agent 可直接调用新能力
 */

const fs = require('fs');
const path = require('path');

const SKILLS_DIR = path.join(__dirname, '..', 'data', 'installed-skills');

// 确保目录存在
if (!fs.existsSync(SKILLS_DIR)) {
  fs.mkdirSync(SKILLS_DIR, { recursive: true });
}

/**
 * 安装 Skill 到买家 Agent
 * @param {object} options
 * @param {string} options.agentWallet - 买家 Agent 钱包地址
 * @param {string} options.skillId - Skill ID
 * @param {string} options.skillName - Skill 名称
 * @param {string} options.seller - 卖家名称
 * @param {string} options.code - Skill 代码（可选，真实场景从卖家获取）
 * @param {object} options.metadata - 额外元数据
 * @returns {object} 安装结果
 */
function installSkill({ agentWallet, skillId, skillName, seller, code = '', metadata = {} }) {
  const agentDir = path.join(SKILLS_DIR, agentWallet.toLowerCase());
  if (!fs.existsSync(agentDir)) {
    fs.mkdirSync(agentDir, { recursive: true });
  }

  // 检查是否已安装
  const manifestPath = path.join(agentDir, 'manifest.json');
  let manifest = { skills: [] };
  if (fs.existsSync(manifestPath)) {
    try { manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8')); } catch (e) {}
  }

  const existing = manifest.skills.find(s => s.skillId === skillId);
  if (existing) {
    return { ok: false, error: 'Skill 已安装', skill: existing };
  }

  // 安装 Skill
  const skillDir = path.join(agentDir, skillId.replace(/[^a-zA-Z0-9-_]/g, '_'));
  if (!fs.existsSync(skillDir)) {
    fs.mkdirSync(skillDir, { recursive: true });
  }

  const skillRecord = {
    skillId,
    skillName,
    seller,
    installedAt: new Date().toISOString(),
    version: '1.0.0',
    status: 'active',
    ...metadata,
  };

  // 保存 Skill 元数据
  fs.writeFileSync(path.join(skillDir, 'skill.json'), JSON.stringify(skillRecord, null, 2));

  // 保存代码（如果有）
  if (code) {
    fs.writeFileSync(path.join(skillDir, 'index.js'), code);
  }

  // 更新 manifest
  manifest.skills.push(skillRecord);
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));

  return { ok: true, skill: skillRecord };
}

/**
 * 获取 Agent 已安装的所有 Skill
 * @param {string} agentWallet
 * @returns {Array}
 */
function getInstalledSkills(agentWallet) {
  const agentDir = path.join(SKILLS_DIR, agentWallet.toLowerCase());
  const manifestPath = path.join(agentDir, 'manifest.json');
  if (!fs.existsSync(manifestPath)) return [];

  try {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    return manifest.skills.filter(s => s.status === 'active');
  } catch (e) {
    return [];
  }
}

/**
 * 检查 Agent 是否已安装某个 Skill
 */
function hasSkill(agentWallet, skillId) {
  return getInstalledSkills(agentWallet).some(s => s.skillId === skillId);
}

/**
 * 卸载 Skill
 */
function uninstallSkill(agentWallet, skillId) {
  const agentDir = path.join(SKILLS_DIR, agentWallet.toLowerCase());
  const manifestPath = path.join(agentDir, 'manifest.json');
  if (!fs.existsSync(manifestPath)) return { ok: false, error: 'Agent 未安装任何 Skill' };

  let manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const idx = manifest.skills.findIndex(s => s.skillId === skillId);
  if (idx === -1) return { ok: false, error: 'Skill 未安装' };

  manifest.skills[idx].status = 'uninstalled';
  manifest.skills[idx].uninstalledAt = new Date().toISOString();
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));

  return { ok: true };
}

module.exports = { installSkill, getInstalledSkills, hasSkill, uninstallSkill };

// CLI
if (require.main === module) {
  const args = process.argv.slice(2);
  const cmd = args[0];
  if (cmd === 'list') {
    const wallet = args[1];
    if (!wallet) { console.error('用法: node install.js list <wallet>'); process.exit(1); }
    console.log(JSON.stringify(getInstalledSkills(wallet), null, 2));
  } else {
    console.log('命令: list <wallet>');
  }
}
