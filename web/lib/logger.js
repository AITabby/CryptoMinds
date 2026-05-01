/**
 * CryptoMinds structured logger for Node.js.
 * Outputs JSON-formatted logs to stdout/stderr for production observability.
 */

function log(level, module, message, meta = {}) {
  const entry = {
    timestamp: new Date().toISOString(),
    level,
    module,
    message,
    ...meta,
  };
  if (level === 'error') {
    process.stderr.write(JSON.stringify(entry) + '\n');
  } else {
    process.stdout.write(JSON.stringify(entry) + '\n');
  }
}

module.exports = {
  info: (module, message, meta) => log('info', module, message, meta),
  warn: (module, message, meta) => log('warn', module, message, meta),
  error: (module, message, meta) => log('error', module, message, meta),
  debug: (module, message, meta) => log('debug', module, message, meta),
};