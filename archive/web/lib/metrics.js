/**
 * CryptoMinds lightweight Prometheus metrics.
 * Exposes counters and gauges in Prometheus text format.
 */

const counters = {};
const gauges = {};

function incCounter(name, labels = {}) {
  const key = metricKey(name, labels);
  counters[key] = (counters[key] || 0) + 1;
}

function setGauge(name, value, labels = {}) {
  const key = metricKey(name, labels);
  gauges[key] = { value, labels };
}

function metricKey(name, labels) {
  const labelStr = Object.entries(labels).map(([k, v]) => `${k}="${v}"`).join(',');
  return labelStr ? `${name}{${labelStr}}` : name;
}

function render() {
  const lines = [];

  for (const [key, count] of Object.entries(counters)) {
    // Extract name from key (before {)
    const name = key.split('{')[0];
    lines.push(`# TYPE ${name} counter`);
    lines.push(`${key} ${count}`);
  }

  for (const [key, { value }] of Object.entries(gauges)) {
    const name = key.split('{')[0];
    lines.push(`# TYPE ${name} gauge`);
    lines.push(`${key} ${value}`);
  }

  return lines.join('\n') + '\n';
}

// Middleware: auto-increment request counters
function metricsMiddleware(req, res, next) {
  const start = Date.now();
  res.on('finish', () => {
    incCounter('cryptominds_http_requests_total', {
      method: req.method,
      path: req.route?.path || req.path,
      status: res.statusCode,
    });
    const duration = (Date.now() - start) / 1000;
    incCounter('cryptominds_http_request_duration_seconds_total', {
      method: req.method,
      path: req.route?.path || req.path,
    });
  });
  next();
}

module.exports = { incCounter, setGauge, render, metricsMiddleware };