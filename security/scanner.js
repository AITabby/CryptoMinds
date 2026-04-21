/**
 * ⚠️ DEPRECATED — 旧 Skill 安全扫描器，现由卖家 Agent endpoint 自行负责安全
 * CryptoMinds Skill 静态安全扫描器
 * 
 * 检测危险代码模式，返回安全评级
 */

const DANGEROUS_PATTERNS = [
  // 🔴 高危 - 直接拒绝
  {
    level: 'critical',
    name: '私钥/密钥读取',
    patterns: [
      /private[_-]?key/i,
      /mnemonic/i,
      /seed[_-]?phrase/i,
      /readFile.*wallet/i,
      /readFile.*\.ssh/i,
      /readFile.*\.env/i,
      /readFileSync.*\/etc\/passwd/i,
      /wallet.*json/i,
    ]
  },
  {
    level: 'critical',
    name: '数据外泄',
    patterns: [
      /fetch\s*\(\s*['"][^'"]*['"]\s*,\s*\{[^}]*body\s*:/i,
      /axios\.\w+\s*\(\s*['"][^'"]*['"]\s*,/i,
      /requests\.\w+\s*\(\s*['"][^'"]*['"]\s*,/i,
      /urllib/i,
      /http\.request\s*\(\s*\{[^}]*method\s*:\s*['"]POST/i,
      /XMLHttpRequest/i,
    ]
  },
  {
    level: 'critical',
    name: '签名/加密操作',
    patterns: [
      /sign\s*\(\s*(?:tx|transaction|message|hash)/i,
      /eth_sign/i,
      /personal_sign/i,
      /privateKeySign/i,
      /createSign\b/i,
      /crypto\.createCipher/i,
    ]
  },
  {
    level: 'critical',
    name: '网络监听',
    patterns: [
      /createServer\s*\(/i,
      /listen\s*\(\s*\d+/i,
      /net\.createServer/i,
      /child_process/i,
      /exec\s*\(/i,
      /spawn\s*\(/i,
    ]
  },
  // 🟡 中危 - 一律视为不安全，拒绝上架
  {
    level: 'warning',
    name: '环境变量访问',
    patterns: [
      /process\.env/i,
      /os\.environ/i,
      /getenv/i,
    ]
  },
  // 🔴 高危 - 敏感环境变量
  {
    level: 'critical',
    name: '敏感环境变量读取',
    patterns: [
      /process\.env\.(PRIVATE_KEY|MNEMONIC|SEED|API_KEY|SECRET)/i,
      /os\.environ\.get\s*\(\s*['"](PRIVATE_KEY|MNEMONIC|SEED|API_KEY|SECRET)/i,
    ]
  },
  {
    level: 'critical',
    name: '动态代码执行',
    patterns: [
      /eval\s*\(/i,
      /new\s+Function\s*\(/i,
      /execSync/i,
      /__import__/i,
      /getattr\s*\(\s*__builtins__/i,
    ]
  },
  {
    level: 'critical',
    name: '文件写入',
    patterns: [
      /writeFile/i,
      /appendFile/i,
      /createWriteStream/i,
      /open\s*\([^)]*['"]w['"]/i,
    ]
  },
  {
    level: 'critical',
    name: '敏感路径读取',
    patterns: [
      /readFile.*\/Users\//i,
      /readFile.*\/home\//i,
      /readFile.*\/root\//i,
      /readdir\s*\(\s*['"]\//i,
    ]
  },
];

// 允许调用的域名白名单
const ALLOWED_DOMAINS = [
  'binance.org',
  'bscscan.com',
  'basescan.org',
  'four.meme',
  'dexscreener.com',
  'coingecko.com',
  'geckoterminal.com',
  'dex.guru',
  'etherscan.io',
  'bsc-dataseed',
  'mainnet.base.org',
];

// 允许的链上 RPC 调用模式
const ALLOWED_CHAIN_PATTERNS = [
  /eth_blockNumber/i,
  /eth_getBalance/i,
  /eth_getTransaction/i,
  /eth_call/i,
  /eth_getLogs/i,
  /eth_getBlock/i,
];

/**
 * 扫描代码，返回安全检测结果
 * @param {string} code - Skill 代码内容
 * @param {string} [language] - 语言 (js, py, auto)
 * @returns {{ level: 'safe'|'warning'|'critical', issues: Array, score: number }}
 */
function scan(code, language = 'auto') {
  if (language === 'auto') {
    language = detectLanguage(code);
  }

  const issues = [];
  const lines = code.split('\n');

  for (const pattern of DANGEROUS_PATTERNS) {
    for (const regex of pattern.patterns) {
      const matches = code.match(new RegExp(regex, 'gm'));
      if (matches) {
        // 找到对应的行号
        for (const match of matches) {
          const lineNum = findLineNumber(code, match);
          issues.push({
            level: pattern.level,
            category: pattern.name,
            snippet: truncate(match, 80),
            line: lineNum,
          });
        }
      }
    }
  }

  // 检查外部网络请求的域名
  const urlMatches = code.match(/['"]https?:\/\/[^'"]+['"]/g) || [];
  for (const url of urlMatches) {
    const domain = extractDomain(url);
    if (domain && !isDomainAllowed(domain)) {
      issues.push({
        level: 'critical',
        category: '未白名单域名请求',
        snippet: truncate(url, 80),
        line: findLineNumber(code, url),
        detail: `域名 ${domain} 不在白名单中`,
      });
    }
  }

  // 去重（同一行同一类别只报一次）
  const deduped = deduplicate(issues);

  // 确定整体评级：只有 critical 问题才拒绝上架
  const hasCritical = deduped.some(i => i.level === 'critical');
  let level = deduped.length === 0 ? 'safe' : (hasCritical ? 'critical' : 'warning');

  // 计算安全分数 (0-100)
  let score = 100;
  for (const issue of deduped) {
    score -= issue.level === 'critical' ? 30 : 10;  // critical 扣30，warning 扣10
  }
  score = Math.max(0, score);

  return {
    level,
    language,
    issues: deduped,
    score,
    summary: generateSummary(level, deduped),
  };
}

function detectLanguage(code) {
  if (/\bdef\s+\w+\s*\(/.test(code) || /\bimport\s+\w+/.test(code) && /:\s*$/.test(code.split('\n')[0] || '')) return 'py';
  return 'js';
}

function findLineNumber(code, match) {
  const idx = code.indexOf(typeof match === 'string' ? match : match[0]);
  if (idx === -1) return 0;
  return code.substring(0, idx).split('\n').length;
}

function extractDomain(urlStr) {
  const m = urlStr.match(/https?:\/\/([^/'"]+)/);
  return m ? m[1].toLowerCase() : null;
}

function isDomainAllowed(domain) {
  return ALLOWED_DOMAINS.some(allowed => domain.includes(allowed.toLowerCase()));
}

function truncate(str, max) {
  return str.length > max ? str.slice(0, max) + '...' : str;
}

function deduplicate(issues) {
  const seen = new Set();
  return issues.filter(i => {
    const key = `${i.level}:${i.category}:${i.line}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function generateSummary(level, issues) {
  if (issues.length === 0) return '✅ 未检测到危险模式，代码安全';
  const critical = issues.filter(i => i.level === 'critical').length;
  const warning = issues.filter(i => i.level === 'warning').length;
  if (critical > 0) return `❌ 检测到 ${critical} 个高危风险项，拒绝上架`;
  if (warning > 0) return `⚠️ 检测到 ${warning} 个警告项，允许上架但建议优化`;
  return '✅ 未检测到危险模式，代码安全';
}

module.exports = { scan, isDomainAllowed, ALLOWED_DOMAINS };

// CLI 用法：node scanner.js <file>
if (require.main === module) {
  const fs = require('fs');
  const file = process.argv[2];
  if (!file) { console.error('用法: node scanner.js <skill-file>'); process.exit(1); }
  const code = fs.readFileSync(file, 'utf8');
  const result = scan(code);
  console.log(JSON.stringify(result, null, 2));
}
