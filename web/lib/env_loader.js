/**
 * CryptoMinds Node.js environment loader
 * - Loads .env, then .env.dev/.env.staging/.env.prod based on CRYPTOMINDS_ENV
 * - Validates required vars for non-dev environments
 * - Logs config summary on startup
 */
const path = require('path');
const fs = require('fs');

const PROJECT_ROOT = path.join(__dirname, '..', '..');
const ENVIRONMENTS_DIR = path.join(PROJECT_ROOT, 'environments');

const REQUIRED_PROD = ['CRYPTOMINDS_INTERNAL_TOKEN', 'ADMIN_SECRET', 'BSC_RPC', 'DEPOSIT_POOL_ADDRESS'];
const REQUIRED_STAGING = ['CRYPTOMINDS_INTERNAL_TOKEN', 'ADMIN_SECRET', 'BSC_RPC'];

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return false;
  const content = fs.readFileSync(filePath, 'utf-8');
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const [key, ...rest] = trimmed.split('=');
    const value = rest.join('=').trim();
    if (key.trim() && !process.env[key.trim()]) {
      process.env[key.trim()] = value;
    }
  }
  return true;
}

function loadEnvironment() {
  const envName = (process.env.CRYPTOMINDS_ENV || process.env.NODE_ENV || 'dev').toLowerCase();

  // 1. Load base .env
  loadEnvFile(path.join(PROJECT_ROOT, '.env'));

  // 2. Load environment-specific file
  const envFile = path.join(ENVIRONMENTS_DIR, `.env.${envName}`);
  const loaded = loadEnvFile(envFile);
  if (!loaded && envName !== 'dev') {
    console.warn(`[ENV] Environment file ${envFile} not found`);
  }

  // 3. Validate
  const errors = validate(envName);
  if (errors.length > 0) {
    for (const err of errors) {
      console.error(`[ENV-ERROR] ${err}`);
    }
    if (envName === 'prod') {
      console.error('[ENV] Production startup aborted');
      process.exit(1);
    }
  }

  // 4. Log summary
  const config = readConfig(envName);
  console.log(`[ENV-OK] Environment: ${envName}`);
  console.log(`  BSC_RPC=${config.BSC_RPC}`);
  console.log(`  DEMO_MODE=${config.DEMO_MODE}`);
  console.log(`  LOG_JSON=${config.LOG_JSON}`);
  console.log(`  INTERNAL_TOKEN=${config.INTERNAL_TOKEN ? '<set>' : '<empty>'}`);

  return config;
}

function validate(envName) {
  const errors = [];
  const required = envName === 'prod' ? REQUIRED_PROD : envName === 'staging' ? REQUIRED_STAGING : [];

  for (const varName of required) {
    if (!process.env[varName]) {
      errors.push(`Missing required env var: ${varName}`);
    }
  }

  // Prod safety checks
  if (envName === 'prod') {
    if (process.env.DEMO_MODE === 'true') errors.push('DEMO_MODE must be false in production');
    if (process.env.CRYPTOMINDS_DEBUG === 'true') errors.push('CRYPTOMINDS_DEBUG must be false in production');
  }

  return errors;
}

function readConfig(envName) {
  return {
    env: envName,
    BSC_RPC: process.env.BSC_RPC || 'https://bsc-dataseed1.binance.org/',
    DEMO_MODE: (process.env.DEMO_MODE || 'false').toLowerCase() === 'true',
    DEBUG: (process.env.CRYPTOMINDS_DEBUG || 'false').toLowerCase() === 'true',
    LOG_LEVEL: (process.env.CRYPTOMINDS_LOG_LEVEL || 'INFO').toUpperCase(),
    LOG_JSON: (process.env.CRYPTOMINDS_LOG_JSON || (envName === 'prod' ? 'true' : 'false')).toLowerCase() === 'true',
    INTERNAL_TOKEN: process.env.CRYPTOMINDS_INTERNAL_TOKEN || '',
    PORT: parseInt(process.env.PORT || '3457', 10),
  };
}

module.exports = { loadEnvironment };
