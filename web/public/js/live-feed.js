// CryptoMinds Live Feed Module
// Live event feed, txs feed, SSE streams, event rendering

const AGENT_ICONS = { 'ChainSentry': '🔍', 'RiskGuard': '🛡️', 'NFTScout': '🎯', 'GasSaver': '⛽', 'AlphaBot': '🤖', 'ChainSeer': '🔮', 'Sentinel': '🔐', 'Buyer Agent': '🤖', 'Scout Agent': '🧭', 'Momentum One': '📈', 'Dip Hunter': '🎯', 'Risk Sentinel': '🛡️', 'Flow Surfer': '🌊' };
const AGENT_COLORS = { 'ChainSentry': '#34d399', 'RiskGuard': '#fbbf24', 'NFTScout': '#f472b6', 'GasSaver': '#60a5fa', 'AlphaBot': '#a78bfa', 'ChainSeer': '#818cf8', 'Sentinel': '#34d399', 'Buyer Agent': '#a78bfa', 'Scout Agent': '#38bdf8', 'Momentum One': '#34d399', 'Dip Hunter': '#f59e0b', 'Risk Sentinel': '#60a5fa', 'Flow Surfer': '#22c55e' };
let myAgentNames = new Set();

async function loadMyAgents() {
  try {
    const wallet = App.currentAccount || getActiveWallet();
    if (!wallet) {
      myAgentNames = new Set();
      const nameEl = document.getElementById('myAgentName'); if (nameEl) nameEl.textContent = '未连接钱包';
      return;
    }
    const res = await fetch('/api/v1/sellers');
    const data = await res.json();
    const agents = data.sellers || data || [];
    const myAgents = agents.filter(a => (a.wallet || '').toLowerCase() === wallet.toLowerCase());
    myAgentNames = new Set(myAgents.map(a => a.name).filter(Boolean));
    try {
      const orderRes = await fetch('/api/my-orders?wallet=' + wallet);
      const orderData = await orderRes.json();
      if (orderData.ok) {
        (orderData.orders || []).forEach(o => {
          if (o.buyerName) myAgentNames.add(o.buyerName);
          if (o.expert) myAgentNames.add(o.expert);
        });
      }
    } catch(e) {}
    const nameEl = document.getElementById('myAgentName'); if (nameEl) nameEl.textContent = [...myAgentNames].join(', ') || '未注册';
  } catch(e) {
    myAgentNames = new Set();
    const nameEl2 = document.getElementById('myAgentName'); if (nameEl2) nameEl2.textContent = '加载失败';
  }
}

function renderTxEvent(tx) {
  const isMyTo = myAgentNames.has(tx.to);
  const isMyFrom = myAgentNames.has(tx.from);
  let agent, icon, color, reason, direction;
  if (isMyTo && !isMyFrom) {
    agent = tx.to;
    icon = AGENT_ICONS[agent] || '🤖';
    color = AGENT_COLORS[agent] || '#a78bfa';
    reason = tx.reason ? tx.reason.replace('雇佣卖家:', '收到订单:') : '收到订单';
    direction = '📥';
  } else {
    agent = tx.from || '未知';
    icon = AGENT_ICONS[agent] || '🤖';
    color = AGENT_COLORS[agent] || '#a78bfa';
    reason = tx.reason || '订单支付';
    direction = '';
  }
  const isRealTx = typeof tx.tx === 'string' && tx.tx.startsWith('0x');
  const shortTx = tx.tx ? (tx.tx.length > 16 ? tx.tx.slice(0, 8) + '...' + tx.tx.slice(-6) : tx.tx) : '';
  const bscUrl = isRealTx ? 'https://bscscan.com/tx/' + tx.tx : null;

  let html = '<div class="live-event pay">';
  html += '<div class="live-event-header">';
  html += '<span style="font-size:16px;">' + icon + '</span>';
  html += '<span class="live-event-agent" style="color:' + color + '">' + agent + '</span>';
  if (direction) html += '<span style="font-size:10px; margin-left:2px;">' + direction + '</span>';
  html += '<span class="live-event-time">' + formatTime(tx.timestamp) + '</span>';
  html += '</div>';
  html += '<div class="live-event-body">';
  if (isMyTo && !isMyFrom) {
    html += direction + ' ' + reason;
    if (tx.from) html += ' ← <strong style="color:#e2e8f0">' + tx.from + '</strong>';
  } else {
    html += reason;
    if (tx.to && tx.to !== agent) html += ' → <strong style="color:#e2e8f0">' + tx.to + '</strong>';
  }
  html += ' <span style="color:#34d399; font-weight:600;">' + tx.amount + ' BNB</span>';
  html += '</div>';
  if (shortTx) {
    html += '<div class="live-event-detail">';
    if (bscUrl) {
      html += '<a class="live-event-tx" href="' + bscUrl + '" target="_blank">🔗 ' + shortTx + '</a>';
      html += '<span style="color:#34d399; font-size:10px; margin-left:8px;">✅ 链上验证</span>';
    } else {
      html += '<span style="color:#475569; font-family:monospace; font-size:11px;">' + shortTx + '</span>';
      if (tx.verified) html += '<span style="color:#94a3b8; font-size:10px; margin-left:8px;">' + tx.verified + '</span>';
    }
    if (tx.route_type) html += '<span style="color:#475569; font-size:10px; margin-left:8px;">' + tx.route_type + '</span>';
    html += '</div>';
  }
  html += '</div>';
  return html;
}

function groupTxsIntoChains(txs) {
  const chains = [];
  let currentChain = [];
  let lastTime = 0;
  for (const tx of txs) {
    const t = new Date(tx.timestamp).getTime();
    if (lastTime && (t - lastTime > 5 * 60 * 1000)) {
      if (currentChain.length) chains.push(currentChain);
      currentChain = [];
    }
    currentChain.push(tx);
    lastTime = t;
  }
  if (currentChain.length) chains.push(currentChain);
  return chains;
}

function renderEventItem(item) {
  if (item._type === 'event') {
    const icon = AGENT_ICONS[item.agent] || '🤖';
    const color = AGENT_COLORS[item.agent] || '#a78bfa';
    const typeLabel = { think: '🧠 思考', pay: '💰 支付', execute: '⚙️ 执行', result: '📋 结果', error: '❌ 错误' };
    const borderClass = { think: 'think', pay: 'pay', execute: 'execute', result: 'result', error: 'pay' };
    const typeClass = borderClass[item.type] || 'think';

    let html = '<div class="live-event ' + typeClass + '">';
    html += '<div class="live-event-header">';
    html += '<span style="font-size:16px;">' + icon + '</span>';
    html += '<span class="live-event-agent" style="color:' + color + '">' + item.agent + '</span>';
    html += '<span style="font-size:10px; color:#475569; margin-left:4px;">' + (typeLabel[item.type] || item.type) + '</span>';
    html += '<span class="live-event-time">' + formatTime(item.timestamp) + '</span>';
    html += '</div>';
    html += '<div class="live-event-body">' + (item.message || '') + '</div>';
    if (item.tx_hash) {
      html += '<div class="live-event-detail">';
      html += '<a class="live-event-tx" href="https://bscscan.com/tx/' + item.tx_hash + '" target="_blank">🔗 ' + item.tx_hash.slice(0, 10) + '...</a>';
      html += '</div>';
    }
    html += '</div>';
    return html;
  } else {
    return renderTxEvent(item);
  }
}

async function loadLiveFeed() {
  const tabSnapshot = App.activeTab;
  try {
    await loadMyAgents();
    const res = await fetch('/api/v1/live-feed');
    const items = await res.json();
    if (tabSnapshot !== App.activeTab) return;

    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const txs = items.filter(i => i._type === 'tx');
    const todayTxs = txs.filter(t => new Date(t.timestamp) >= today);
    const NON_AGENTS = ['押金池', '未知', 'test', 'undefined', 'null'];
    const uniqueAgents = new Set();
    items.forEach(t => {
      [t.from, t.to, t.agent].forEach(name => {
        if (name && !NON_AGENTS.includes(name)) uniqueAgents.add(name);
      });
    });
    const verifiedCount = txs.filter(t => typeof t.tx === 'string' && t.tx.startsWith('0x')).length;
    const todayVolume = todayTxs.reduce((s, t) => s + (t.amount || 0), 0);

    const elTodayTxs = document.getElementById('liveTodayTxs'); if (elTodayTxs) elTodayTxs.textContent = todayTxs.length;
    const elTodayVol = document.getElementById('liveTodayVolume'); if (elTodayVol) elTodayVol.textContent = todayVolume.toFixed(4) + ' BNB';
    const elActiveAgents = document.getElementById('liveActiveAgents'); if (elActiveAgents) elActiveAgents.textContent = uniqueAgents.size;
    const elVerified = document.getElementById('liveVerified'); if (elVerified) elVerified.textContent = verifiedCount;
    const elAgentCount = document.getElementById('liveAgentCount'); if (elAgentCount) elAgentCount.textContent = uniqueAgents.size + ' 个 Agent 参与';
    const elLastUpdate = document.getElementById('liveLastUpdate'); if (elLastUpdate) elLastUpdate.textContent = '更新于 ' + now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

    const myItems = items.filter(isMyAgent);
    const marketItems = items.filter(i => !isMyAgent(i));

    renderAgentBrain(window._cachedBuyerOrders || []);
    renderFeed('marketFeed', marketItems, false);
  } catch (e) {
    console.error('loadLiveFeed error:', e);
    const myAgentEl = document.getElementById('myAgentFeed');
    const marketEl = document.getElementById('marketFeed');
    if (myAgentEl) myAgentEl.innerHTML = '<div style="color:#f87171; text-align:center; padding:40px 0;">加载失败: ' + e.message + '</div>';
    if (marketEl) marketEl.innerHTML = '<div style="color:#f87171; text-align:center; padding:40px 0;">加载失败: ' + e.message + '</div>';
  }
}

function renderFeed(containerId, items, showChain) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!items.length) {
    el.innerHTML = '<div style="color:#475569; text-align:center; padding:40px 0;">暂无活动</div>';
    return;
  }
  let html = '';
  if (showChain) {
    const chains = groupTxsIntoChains(items);
    for (let ci = 0; ci < chains.length; ci++) {
      const chain = chains[ci];
      if (ci > 0 && chain.length > 1) {
        html += '<div class="live-chain-marker"><div class="live-chain-line"></div><div class="live-chain-text">新一轮决策</div><div class="live-chain-line"></div></div>';
      }
      for (const item of chain) {
        html += renderEventItem(item);
      }
    }
  } else {
    for (const item of items) {
      html += renderEventItem(item);
    }
  }
  el.innerHTML = html;
  App.refreshLucide();
}

let liveEventSource = null;

async function startLiveStream() {
  if (liveEventSource) liveEventSource.close();
  await loadMyAgents();
  const statusEl = document.getElementById('liveConnStatus');
  const pulseEl = document.getElementById('livePulse');
  if (statusEl) { statusEl.textContent = '● 连接中...'; statusEl.style.color = '#fbbf24'; }

  liveEventSource = new EventSource('/api/v1/live-stream');
  liveEventSource.onmessage = function(e) {
    try {
      const item = JSON.parse(e.data);
      if (item._type === 'connected') {
        if (statusEl) { statusEl.textContent = '● 实时'; statusEl.style.color = '#34d399'; }
        if (pulseEl) pulseEl.style.background = '#34d399';
        return;
      }
      prependLiveEvent(item);
    } catch(err) {}
  };
  liveEventSource.onerror = function() {
    if (statusEl) { statusEl.textContent = '○ 重连中...'; statusEl.style.color = '#f87171'; }
    if (pulseEl) pulseEl.style.background = '#f87171';
    liveEventSource.close();
    setTimeout(startLiveStream, 3000);
  };
}

function prependLiveEvent(item) {
  const containerId = isMyAgent(item) ? 'myAgentFeed' : 'marketFeed';
  const feed = document.getElementById(containerId);
  if (!feed) return;
  const html = renderEventItem(item);
  const wrapper = document.createElement('div');
  wrapper.innerHTML = html;
  const el = wrapper.firstElementChild;
  if (!el) return;
  el.style.transition = 'background 0.5s ease';
  el.style.background = 'rgba(139,92,246,0.12)';
  setTimeout(() => { el.style.background = ''; }, 1500);
  const nearBottom = feed.scrollTop + feed.clientHeight >= feed.scrollHeight - 100;
  const placeholder = feed.querySelector('[style*="text-align:center"]');
  if (placeholder && placeholder.textContent.includes('暂无')) placeholder.remove();
  feed.insertBefore(el, feed.firstChild);
  if (nearBottom) feed.scrollTop = 0;
  if (isMyAgent(item) && App.currentAccount) loadBuyerStats();
  const now = new Date();
  const elLastUpdate = document.getElementById('liveLastUpdate');
  if (elLastUpdate) elLastUpdate.textContent = '更新于 ' + now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  App.refreshLucide();
}

// Txs feed
let txsEventSource = null;

function renderTxsRow(tx) {
  const isRealTx = typeof tx.tx === 'string' && tx.tx.startsWith('0x');
  const bscUrl = isRealTx ? 'https://bscscan.com/tx/' + tx.tx : null;
  const wallet = (App.currentAccount || '').toLowerCase();
  const toW = (tx.toWallet || '').toLowerCase();
  const fromW = (tx.fromWallet || '').toLowerCase();
  const isIn = wallet && toW && toW === wallet;
  const isOut = wallet && fromW && fromW === wallet;
  const icon = isIn ? 'download' : 'upload';
  const iconColor = isIn ? '#10b981' : '#a78bfa';
  const sign = isIn ? '+' : '-';
  const valClass = isIn ? 'pos' : 'neg';

  let html = '<div class="tx-item">';
  html += '<div class="tx-icon ' + (isIn ? 'in' : 'out') + '"><i data-lucide="' + icon + '" class="icon-sm" style="color:' + iconColor + '"></i></div>';
  html += '<div class="tx-info">';
  html += '<div class="flow">' + (tx.from || '?') + ' → ' + (tx.to || '?') + '</div>';
  html += '<div class="reason">' + (tx.reason || '') + (bscUrl ? ' <a href="' + bscUrl + '" target="_blank" style="color:#8b5cf6;font-size:10px;">🔗</a>' : '') + '</div>';
  html += '</div>';
  html += '<div class="tx-amount">';
  html += '<div class="val ' + valClass + '">' + sign + tx.amount + ' BNB</div>';
  html += '<div class="time">' + (tx.time || formatTime(tx.timestamp)) + '</div>';
  html += '</div>';
  html += '</div>';
  return html;
}

async function loadTxsFeed() {
  try {
    const res = await fetch('/api/v1/txs');
    const txs = await res.json();
    txs.sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));
    const el = document.getElementById('txList');
    if (!txs.length) {
      el.innerHTML = '<div style="color:#475569; text-align:center; padding:30px 0;">暂无交易</div>';
      return;
    }
    el.innerHTML = txs.slice(0, 30).map(renderTxsRow).join('');
    App.refreshLucide();
  } catch(e) {
    console.error('loadTxsFeed error:', e);
    const el = document.getElementById('txList');
    if (el) el.innerHTML = '<div style="color:#475569; text-align:center; padding:30px 0;">暂无交易</div>';
  }
}

function prependTxsItem(tx) {
  const feed = document.getElementById('txList');
  if (!feed) return;
  const html = renderTxsRow(tx);
  const wrapper = document.createElement('div');
  wrapper.innerHTML = html;
  const el = wrapper.firstElementChild;
  if (!el) return;
  el.style.transition = 'background 0.5s ease';
  el.style.background = 'rgba(139,92,246,0.12)';
  setTimeout(() => { el.style.background = ''; }, 1500);
  const ph = feed.querySelector('[style*="text-align:center"]');
  if (ph && ph.textContent.includes('暂无')) ph.remove();
  feed.insertBefore(el, feed.firstChild);
  while (feed.children.length > 30) feed.removeChild(feed.lastChild);
  App.refreshLucide();
}

function startTxsStream() {
  if (txsEventSource) txsEventSource.close();
  txsEventSource = new EventSource('/api/v1/live-stream');
  txsEventSource.onmessage = function(e) {
    try {
      const item = JSON.parse(e.data);
      if (item._type === 'connected') return;
      if (item._type === 'tx') prependTxsItem(item);
    } catch(err) {}
  };
  txsEventSource.onerror = function() {
    txsEventSource.close();
    setTimeout(startTxsStream, 3000);
  };
}

window.loadMyAgents = loadMyAgents;
window.loadLiveFeed = loadLiveFeed;
window.startLiveStream = startLiveStream;
window.loadTxsFeed = loadTxsFeed;
window.startTxsStream = startTxsStream;
window.myAgentNames = myAgentNames;
