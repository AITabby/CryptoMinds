// CryptoMinds Common Utilities
// Pure functions with no business logic dependencies

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[ch]));
}

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  const now = new Date();
  const diff = (now - d) / 1000;
  if (diff < 60) return '刚刚';
  if (diff < 3600) return Math.floor(diff / 60) + 'min ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

function identiconSvg(address, size = 40) {
  try {
    if (typeof Identicon !== 'undefined' && typeof Identicon === 'function') {
      return '<img src="data:image/png;base64,' + new Identicon(address.replace('0x',''), { size: size, format: 'png' }).toString() + '" style="width:' + size + 'px;height:' + size + 'px;border-radius:8px;">';
    }
  } catch(e) {}
  const hue = parseInt(address.slice(2, 8), 16) % 360;
  return '<div style="width:' + size + 'px;height:' + size + 'px;border-radius:8px;background:hsl(' + hue + ',60%,50%);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:' + (size/3) + 'px;">' + address.slice(2,4).toUpperCase() + '</div>';
}

function sortObjectKeys(value) {
  if (Array.isArray(value)) return value.map(sortObjectKeys);
  if (!value || typeof value !== 'object') return value;
  return Object.keys(value).sort().reduce((acc, key) => {
    acc[key] = sortObjectKeys(value[key]);
    return acc;
  }, {});
}

function base64EncodeUnicode(value) {
  return btoa(unescape(encodeURIComponent(value)));
}

function encodeTransferData(to, amountBaseUnits) {
  const methodId = 'a9059cbb';
  const address = to.toLowerCase().replace(/^0x/, '').padStart(64, '0');
  const amountHex = BigInt(amountBaseUnits).toString(16).padStart(64, '0');
  return `0x${methodId}${address}${amountHex}`;
}

function toTokenBaseUnits(amount, decimals) {
  const [wholePart, fractionPart = ''] = String(amount).split('.');
  const fraction = (fractionPart + '0'.repeat(decimals)).slice(0, decimals);
  return BigInt(`${wholePart || '0'}${fraction}`);
}

function normalizeCsvInput(value) {
  return value.split(',').map(v => v.trim()).filter(Boolean);
}

function copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.innerHTML = '<i data-lucide="check" class="icon-inline"></i> 已复制'; App.refreshLucide();
    btn.style.color = '#34d399';
    setTimeout(() => { btn.textContent = orig; btn.style.color = ''; }, 1500);
  });
}

function getActiveWallet() {
  return App.currentAccount;
}

function showError(msg) {
  let el = document.getElementById('errorToast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'errorToast';
    el.style.cssText = 'position:fixed;top:20px;right:20px;background:#f87171;color:#fff;padding:16px 24px;border-radius:12px;z-index:9999;font-size:14px;max-width:400px;box-shadow:0 4px 20px rgba(0,0,0,0.4);';
    document.body.appendChild(el);
  }
  el.innerHTML = msg;
  el.style.display = 'block';
  setTimeout(() => { el.style.display = 'none'; }, 5000);
}

function showNotice(msg) {
  let el = document.getElementById('noticeToast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'noticeToast';
    el.style.cssText = 'position:fixed;top:20px;right:20px;background:linear-gradient(135deg,#8b5cf6,#6366f1);color:#fff;padding:16px 24px;border-radius:12px;z-index:9999;font-size:14px;max-width:400px;box-shadow:0 4px 20px rgba(139,92,246,0.4);';
    document.body.appendChild(el);
  }
  el.innerHTML = msg;
  el.style.display = 'block';
  setTimeout(() => { el.style.display = 'none'; }, 4000);
}

// Expose to window for onclick handlers and other modules
window.escapeHtml = escapeHtml;
window.formatTime = formatTime;
window.identiconSvg = identiconSvg;
window.sortObjectKeys = sortObjectKeys;
window.base64EncodeUnicode = base64EncodeUnicode;
window.encodeTransferData = encodeTransferData;
window.toTokenBaseUnits = toTokenBaseUnits;
window.normalizeCsvInput = normalizeCsvInput;
window.copyToClipboard = copyToClipboard;
window.getActiveWallet = getActiveWallet;
window.showError = showError;
window.showNotice = showNotice;
