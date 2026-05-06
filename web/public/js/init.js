// CryptoMinds Init Module
// Bootstrap: DOMContentLoaded, auto-refresh timers, Web Push, demo mode

// Demo mode flag
let isDemoMode = window.__BOOTSTRAP__?.demoMode || false;

function applyDemoMode() {
  const reqSpan = document.getElementById('endpointRequired');
  const hintDiv = document.getElementById('endpointHint');
  if (isDemoMode) {
    if (reqSpan) reqSpan.style.display = 'none';
    if (hintDiv) hintDiv.textContent = 'Demo模式下可选填，未填则平台代执行';
  } else {
    if (reqSpan) reqSpan.style.display = '';
    if (hintDiv) hintDiv.textContent = '卖家必须有自己的 Agent 大脑，平台不代决策代执行';
  }
}

// Auto-refresh transactions + metrics (every 15s)
if (window._txPollTimer) clearInterval(window._txPollTimer);
window._txPollTimer = setInterval(() => {
  const w = getActiveWallet();
  if (w) {
    fetch('/api/v1/sync-chain?wallet=' + w).catch(() => {});
    autoLoadWalletData();
  }
  if (document.getElementById('panel-market').style.display !== 'none' || document.getElementById('panel-live').style.display !== 'none') {
    reloadMarket();
  }
  loadPendingPurchases();
}, 15000);

// Periodic seller bell update (every 10s)
setInterval(async () => {
  if (!App.currentAccount) return;
  try {
    const res = await fetch('/api/notifications?wallet=' + App.currentAccount);
    const data = await res.json();
    if (data.ok) {
      const badge = document.getElementById('sellerUnread');
      if (badge) badge.textContent = data.unread;
      const buyerBadge = document.getElementById('myUnread');
      if (buyerBadge) buyerBadge.textContent = data.unread;
    }
  } catch(e) {}
}, 10000);

// Debug helper
window.debugCards = function() {
  document.querySelectorAll('.metrics .metric-card').forEach((c, i) => {
    const label = c.querySelector('.label');
    const value = c.querySelector('.value');
    const trend = c.querySelector('.trend');
    console.log('Card ' + i + ': offsetHeight=' + c.offsetHeight + ', label.offsetHeight=' + label.offsetHeight + ', value.offsetHeight=' + value.offsetHeight + ', trend.offsetHeight=' + trend.offsetHeight);
    console.log('  label text="' + label.textContent + '", value text="' + value.textContent + '", trend text="' + trend.textContent + '"');
  });
};

// Web Push
async function initWebPush() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;
  try {
    const reg = await navigator.serviceWorker.register('/sw.js');
    const perm = await Notification.requestPermission();
    if (perm !== 'granted') return;
    const sub = await reg.pushManager.getSubscription();
    if (sub) return;
    const keyRes = await fetch('/api/v1/push/vapidPublicKey');
    const { publicKey } = await keyRes.json();
    const newSub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: publicKey
    });
    const waitForWallet = setInterval(() => {
      if (App.currentAccount) {
        clearInterval(waitForWallet);
        fetch('/api/v1/push/subscribe', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ wallet: App.currentAccount, subscription: newSub.toJSON() })
        });
      }
    }, 1000);
  } catch (e) { console.warn('Web Push init failed:', e); }
}
initWebPush();

// Initial load
loadPendingPurchases();

// DOMContentLoaded bootstrap
window.addEventListener('DOMContentLoaded', () => {
  console.log('[DOMContentLoaded] START');
  initMetricsBackup();
  initLang();
  applyDemoMode();
  updateMetrics(window.__BOOTSTRAP__.transactions, window.__BOOTSTRAP__.sellers);
  reloadMarket();
  loadSellerData();
  loadLiveFeed();
  loadTxsFeed();
  setTimeout(() => {
    console.log('[DOMContentLoaded] Force loadBuyerStats after 1s');
    if (App.currentAccount) {
      loadBuyerStats();
    } else {
      App.currentAccount = '0x40992619077f0e42A1b7713C02B7324Fa1d8715c';
      loadBuyerStats();
    }
  }, 1000);
  restoreTab();
  App.refreshLucide();
  document.querySelectorAll('[data-identicon]').forEach(el => {
    el.innerHTML = identiconSvg(el.dataset.identicon, parseInt(el.style.width) || 30);
  });
  autoReconnectWallet();
});

window.applyDemoMode = applyDemoMode;
window.isDemoMode = isDemoMode;
