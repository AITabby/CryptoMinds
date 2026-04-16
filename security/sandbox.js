/**
 * CryptoMinds Skill 沙箱执行器
 * 
 * 在隔离环境中执行 Skill，验证输出安全性和正确性
 * 使用 Node.js vm 模块 + 进程隔离
 */

const vm = require('vm');
const { execFile } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const SANDBOX_TIMEOUT = 30000; // 30 秒超时
const MAX_OUTPUT_SIZE = 1024 * 1024; // 1MB 输出限制
const MAX_MEMORY_MB = 128; // 内存限制

/**
 * 在沙箱中执行 Skill 代码
 * @param {string} code - 代码内容
 * @param {object} options - 执行选项
 * @returns {Promise<{success: boolean, output: any, error: string|null, duration: number}>}
 */
async function execute(code, options = {}) {
  const { language = 'js', testInput = {}, timeout = SANDBOX_TIMEOUT } = options;

  if (language === 'py') {
    return executePython(code, testInput, timeout);
  }
  return executeJS(code, testInput, timeout);
}

/**
 * 执行 JavaScript Skill
 */
async function executeJS(code, testInput, timeout) {
  const startTime = Date.now();

  // 创建受限的全局环境
  const sandbox = {
    // 允许的基础对象
    console: {
      log: (...args) => { sandbox._output.push(args.join(' ')); },
      error: (...args) => { sandbox._errors.push(args.join(' ')); },
      warn: (...args) => { sandbox._warnings.push(args.join(' ')); },
    },
    JSON,
    Math,
    Date,
    Array,
    Object,
    String,
    Number,
    Boolean,
    RegExp,
    Map,
    Set,
    Promise,
    setTimeout: undefined, // 禁止定时器
    setInterval: undefined,
    // 输入数据
    input: testInput,
    // 内部收集器
    _output: [],
    _errors: [],
    _warnings: [],
    _result: null,
  };

  // 拦截危险全局对象
  sandbox.process = undefined;
  sandbox.global = undefined;
  sandbox.globalThis = undefined;
  sandbox.window = undefined;
  sandbox.document = undefined;
  sandbox.require = undefined;
  sandbox.__dirname = undefined;
  sandbox.__filename = undefined;

  // 注入安全的 fetch（仅白名单域名）
  const ALLOWED_DOMAINS = require('./scanner').ALLOWED_DOMAINS;
  sandbox.fetch = function safeFetch(url, opts) {
    try {
      const urlObj = new URL(url);
      const allowed = ALLOWED_DOMAINS.some(d => urlObj.hostname.includes(d));
      if (!allowed) {
        sandbox._errors.push(`BLOCKED: 请求被拦截 — 域名 ${urlObj.hostname} 不在白名单`);
        return Promise.resolve({ ok: false, status: 403, text: () => Promise.resolve('blocked') });
      }
      // 白名单内的请求也不真正执行，返回模拟数据
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ mock: true, note: '沙箱模式，返回模拟数据' }),
        text: () => Promise.resolve('{"mock":true}'),
      });
    } catch (e) {
      return Promise.reject(new Error('无效 URL'));
    }
  };

  try {
    // 包装代码以捕获返回值
    const wrappedCode = `
${code}
;
if (typeof main === 'function') {
  _result = main(input);
}
`;
    const script = new vm.Script(wrappedCode, { filename: 'skill-sandbox.js' });
    const context = vm.createContext(sandbox);

    script.runInContext(context, {
      timeout,
      displayErrors: true,
    });

    // 处理 async 返回值（Promise）
    if (sandbox._result && typeof sandbox._result.then === 'function') {
      sandbox._result = await sandbox._result;
    }

    const duration = Date.now() - startTime;

    return {
      success: sandbox._errors.length === 0,
      output: sandbox._output,
      errors: sandbox._errors,
      warnings: sandbox._warnings,
      result: sandbox._result,
      duration,
    };
  } catch (e) {
    return {
      success: false,
      output: sandbox._output,
      errors: [e.message],
      warnings: sandbox._warnings,
      result: null,
      duration: Date.now() - startTime,
    };
  }
}

/**
 * 执行 Python Skill（子进程隔离）
 */
async function executePython(code, testInput, timeout) {
  const startTime = Date.now();
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'crypto-sandbox-'));
  const scriptPath = path.join(tmpDir, 'skill.py');
  const inputPath = path.join(tmpDir, 'input.json');
  const outputPath = path.join(tmpDir, 'output.json');

  // 写入代码和测试输入
  const wrappedCode = `
import json, sys, os

# 限制危险操作
_orig_import = __builtins__.__import__
def _safe_import(name, *args, **kwargs):
    BLOCKED = ['subprocess', 'socket', 'ftplib', 'smtplib', 'telnetlib', 'ctypes']
    if name in BLOCKED:
        raise ImportError(f"模块 {name} 在沙箱中被禁止")
    return _orig_import(name, *args, **kwargs)
__builtins__.__import__ = _safe_import

# 禁止访问环境变量
os.environ = {}

# 加载输入
with open('${inputPath}', 'r') as f:
    input_data = json.load(f)

# 用户代码开始
${code}
# 用户代码结束

# 输出结果
try:
    result = main(input_data)
    with open('${outputPath}', 'w') as f:
        json.dump({"ok": True, "result": result}, f, ensure_ascii=False)
except Exception as e:
    with open('${outputPath}', 'w') as f:
        json.dump({"ok": False, "error": str(e)}, f)
`;

  fs.writeFileSync(scriptPath, wrappedCode);
  fs.writeFileSync(inputPath, JSON.stringify(testInput));

  return new Promise((resolve) => {
    const child = execFile('python3', [scriptPath], {
      timeout,
      maxBuffer: MAX_OUTPUT_SIZE,
      cwd: tmpDir,
    }, (error, stdout, stderr) => {
      const duration = Date.now() - startTime;
      let result = null;

      try {
        if (fs.existsSync(outputPath)) {
          result = JSON.parse(fs.readFileSync(outputPath, 'utf8'));
        }
      } catch (e) {}

      // 清理临时文件
      try {
        fs.rmSync(tmpDir, { recursive: true, force: true });
      } catch (e) {}

      if (error && error.killed) {
        resolve({ success: false, output: [], errors: ['执行超时（30秒）'], warnings: [], result: null, duration });
        return;
      }

      resolve({
        success: !error && (result?.ok !== false),
        output: stdout ? stdout.split('\n').filter(Boolean) : [],
        errors: stderr ? [stderr] : (result?.error ? [result.error] : []),
        warnings: [],
        result: result?.result || null,
        duration,
      });
    });
  });
}

module.exports = { execute, SANDBOX_TIMEOUT };

// CLI 用法：node sandbox.js <file> [test-input-json]
if (require.main === module) {
  const file = process.argv[2];
  const testInput = process.argv[3] ? JSON.parse(process.argv[3]) : {};
  if (!file) { console.error('用法: node sandbox.js <skill-file> [test-input-json]'); process.exit(1); }
  const code = fs.readFileSync(file, 'utf8');
  const lang = file.endsWith('.py') ? 'py' : 'js';
  execute(code, { language: lang, testInput }).then(result => {
    console.log(JSON.stringify(result, null, 2));
  });
}
