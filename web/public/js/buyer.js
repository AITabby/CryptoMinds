// CryptoMinds Buyer Module
// Buyer stats, agent brain, order rendering, rating, registration

async function loadBuyerStats() {
  console.log('[loadBuyerStats] called, currentAccount:', App.currentAccount);
  if (!App.currentAccount) { console.log('[loadBuyerStats] ABORT: no currentAccount'); return; }
  const tabSnapshot = App.activeTab;
  try {
    const balRes = await fetch('/api/balance?wallet=' + App.currentAccount);
    const balData = await balRes.json();
    const balEl = document.getElementById('buyerBalance');
    if (balEl && balData.ok) balEl.textContent = parseFloat(balData.balance).toFixed(4) + ' BNB';

    const orderRes = await fetch('/api/my-orders?wallet=' + App.currentAccount);
    const orderData = await orderRes.json();
    if (orderData.ok) {
      const orders = orderData.orders || [];
      console.log('[loadBuyerStats] orders:', orders.length, 'activeTab:', App.activeTab, 'account:', App.currentAccount?.slice(0,10));
      window._cachedBuyerOrders = orders;
      const orderEl = document.getElementById('buyerOrders');
      if (orderEl) orderEl.textContent = orders.length;
      const totalSpent = orders.reduce((sum, o) => sum + parseFloat(o.price || 0), 0);
      const spentEl = document.getElementById('buyerTotalSpent');
      if (spentEl) spentEl.textContent = totalSpent.toFixed(4) + ' BNB';
      const completedOrders = orders.filter(o => o.status === 'completed' || o.status === 'delivered');
      const receivedEl = document.getElementById('buyerReceived');
      if (receivedEl) receivedEl.textContent = completedOrders.length + ' 笔';
      renderBuyerTxTable(orders, true);
      console.log('[loadBuyerStats] renderBuyerTxTable called, orders:', orders.length);
      renderAgentBrain(orders);
      console.log('[loadBuyerStats] renderAgentBrain called');
    }
  } catch(e) {}
}

let _brainAnimTimer = null;
function renderAgentBrain(orders, animate) {
  const el = document.getElementById('myAgentFeed');
  if (!el) return;
  if (_brainAnimTimer) { clearTimeout(_brainAnimTimer); _brainAnimTimer = null; }
  if (!orders.length) {
    el.innerHTML = '<div style="color:#475569; text-align:center; padding:40px 0;"><i data-lucide="brain" style="width:32px;height:32px;color:#475569;display:block;margin:0 auto 12px;"></i>Agent 自主决策日志<br><span style="font-size:11px;margin-top:6px;display:block;">Agent 自主搜索、选择、执行<br>此处实时展示 Agent 的决策过程</span></div>';
    App.refreshLucide();
    return;
  }
  const sorted = [...orders].sort((a, b) => new Date(b.time || 0) - new Date(a.time || 0));
  const showOrders = animate ? [sorted[0]] : sorted;
  if (animate && showOrders.length) {
    const o = showOrders[0];
    const time = new Date(o.time).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', hour12:false});
    const isDone = o.status === 'completed' || o.status === 'delivered';
    const expert = o.expert || '未知卖家';
    const price = o.price || 0;
    const txHash = o.txHash || '';
    const tokenAmt = o.tokenAmount || '?';
    const txLink = txHash ? '<a href="https://bscscan.com/tx/' + txHash + '" target="_blank" style="color:#8b5cf6;">' + txHash.slice(0,10) + '...</a>' : '--';

    const prevHtml = sorted.slice(1).map(prevOrder => {
      const pt = new Date(prevOrder.time).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', hour12:false});
      const pExpert = prevOrder.expert || '未知';
      const pPrice = prevOrder.price || 0;
      const pDone = prevOrder.status === 'completed' || prevOrder.status === 'delivered';
      const pToken = prevOrder.tokenAmount || '?';
      return '<div style="padding:8px;background:rgba(100,116,139,0.05);border-radius:6px;margin-bottom:4px;opacity:0.6;"><div style="color:#64748b;font-size:10px;">' + pt + '</div><div style="color:#94a3b8;font-size:11px;">' + (pDone ? '✅' : '⏳') + ' ' + pExpert + ' · ' + pPrice + ' BNB → ' + pToken + ' TOKEN</div></div>';
    }).join('');

    const steps = [
      { icon: '🔍', color: '#a78bfa', label: '搜索卖家', detail: '扫描服务市场 15 个卖家，按权重/评分/额度筛选...', tags: '<span style="background:rgba(139,92,246,0.1);color:#a78bfa;padding:2px 6px;border-radius:4px;font-size:10px;">' + expert + ' ★</span>' },
      { icon: '🎯', color: '#34d399', label: '选择最优', detail: '选中 <b style="color:#34d399;">' + expert + '</b> — 评分最高、押金充足' },
      { icon: '💰', color: '#fbbf24', label: '付款', detail: price + ' BNB → ' + expert + ' ' + (isDone ? '<span style="color:#34d399;">✅ 链上确认</span>' : '<span style="color:#fbbf24;">⏳ 待确认</span>'), extra: txHash ? 'TX: ' + txLink : '' },
      { icon: '🤖', color: '#8b5cf6', label: '卖家 Agent 自主执行', detail: expert + ' 收到指令，自主完成任务...' },
      { icon: '📦', color: '#60a5fa', label: '代币转回', detail: expert + ' 将 <b style="color:#60a5fa;">' + tokenAmt + ' TOKEN</b> 转入你的钱包' },
      { icon: '✅', color: '#34d399', label: '交易完成', detail: '💰 花费 <b style="color:#fbbf24;">' + price + ' BNB</b> → 📦 收到 <b style="color:#60a5fa;">' + tokenAmt + ' TOKEN</b>', sub: '卖家 Agent ' + expert + ' 自主执行', isFinal: true },
    ];

    let html = '<div style="margin-bottom:4px;color:#64748b;font-size:10px;">' + time + '</div>';
    el.innerHTML = html;
    let stepIdx = 0;
    function showNextStep() {
      if (stepIdx >= steps.length) {
        el.innerHTML = html + (prevHtml ? '<div style="border-top:1px dashed rgba(139,92,246,0.15); margin:8px 0;"></div><div style="color:#64748b;font-size:10px;margin-bottom:4px;">历史记录</div>' + prevHtml : '');
        App.refreshLucide();
        return;
      }
      const s = steps[stepIdx];
      if (s.isFinal) {
        html += '<div style="padding:8px; background:rgba(34,211,153,0.08);border-radius:8px;margin-top:4px;border:1px solid rgba(34,211,153,0.15); animation:fadeIn 0.3s;"><div style="color:#34d399;font-size:12px;font-weight:600;">' + s.icon + ' ' + s.label + '</div><div style="color:#94a3b8;font-size:11px;margin-top:4px;">' + s.detail + '</div><div style="color:#64748b;font-size:10px;margin-top:2px;">' + s.sub + '</div></div>';
      } else {
        html += '<div style="padding:6px 0; border-bottom:1px solid rgba(139,92,246,0.06); animation:fadeIn 0.3s;"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;"><span style="color:' + s.color + ';font-size:12px;">' + s.icon + ' ' + s.label + '</span></div><div style="color:#94a3b8;font-size:11px;">' + s.detail + '</div>' + (s.tags ? '<div style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap;">' + s.tags + '</div>' : '') + (s.extra ? '<div style="color:#94a3b8;font-size:11px;margin-top:2px;">' + s.extra + '</div>' : '') + '</div>';
      }
      el.innerHTML = html;
      stepIdx++;
      _brainAnimTimer = setTimeout(showNextStep, isDone ? 1200 : 800);
    }
    showNextStep();
    return;
  }
  let html = '';
  sorted.forEach((o, idx) => {
    const time = new Date(o.time).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', hour12:false});
    const isDone = o.status === 'completed' || o.status === 'delivered';
    const expert = o.expert || '未知卖家';
    const price = o.price || 0;
    const txHash = o.txHash || '';
    const tokenAmt = o.tokenAmount || '?';
    const txLink = txHash ? '<a href="https://bscscan.com/tx/' + txHash + '" target="_blank" style="color:#8b5cf6;">' + txHash.slice(0,10) + '...</a>' : '--';
    if (idx > 0) html += '<div style="border-top:1px dashed rgba(139,92,246,0.15); margin:8px 0;"></div>';
    html += '<div style="margin-bottom:4px;color:#64748b;font-size:10px;">' + time + '</div>';
    html += '<div style="padding:6px 0; border-bottom:1px solid rgba(139,92,246,0.06);"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;"><span style="color:#a78bfa;font-size:12px;">🔍 搜索卖家</span></div><div style="color:#94a3b8;font-size:11px;">扫描服务市场，按权重/评分/额度筛选...</div><div style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap;"><span style="background:rgba(139,92,246,0.1);color:#a78bfa;padding:2px 6px;border-radius:4px;font-size:10px;">' + expert + ' ★</span></div></div>';
    html += '<div style="padding:6px 0; border-bottom:1px solid rgba(139,92,246,0.06);"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;"><span style="color:#34d399;font-size:12px;">🎯 选择最优</span></div><div style="color:#94a3b8;font-size:11px;">选中 <b style="color:#34d399;">' + expert + '</b></div></div>';
    html += '<div style="padding:6px 0; border-bottom:1px solid rgba(139,92,246,0.06);"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;"><span style="color:#fbbf24;font-size:12px;">💰 付款</span></div><div style="color:#94a3b8;font-size:11px;">' + price + ' BNB → ' + expert + ' ' + (isDone ? '<span style="color:#34d399;">✅ 链上确认</span>' : '<span style="color:#fbbf24;">⏳ 待确认</span>') + '</div>' + (txHash ? '<div style="color:#94a3b8;font-size:11px;margin-top:2px;">TX: ' + txLink + '</div>' : '') + '</div>';
    if (isDone) {
      html += '<div style="padding:6px 0; border-bottom:1px solid rgba(139,92,246,0.06);"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;"><span style="color:#8b5cf6;font-size:12px;">🤖 卖家 Agent 自主执行</span></div><div style="color:#94a3b8;font-size:11px;">' + expert + ' 收到指令，自主完成任务...</div></div>';
      html += '<div style="padding:6px 0; border-bottom:1px solid rgba(139,92,246,0.06);"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;"><span style="color:#60a5fa;font-size:12px;">📦 代币转回</span></div><div style="color:#94a3b8;font-size:11px;">' + expert + ' 将 <b style="color:#60a5fa;">' + tokenAmt + ' TOKEN</b> 转入你的钱包</div></div>';
      html += '<div style="padding:8px; background:rgba(34,211,153,0.08);border-radius:8px;margin-top:4px;border:1px solid rgba(34,211,153,0.15);"><div style="color:#34d399;font-size:12px;font-weight:600;">✅ 交易完成</div><div style="color:#94a3b8;font-size:11px;margin-top:4px;">💰 花费 <b style="color:#fbbf24;">' + price + ' BNB</b> → 📦 收到 <b style="color:#60a5fa;">' + tokenAmt + ' TOKEN</b></div><div style="color:#64748b;font-size:10px;margin-top:2px;">卖家 Agent ' + expert + ' 自主执行</div></div>';
    }
  });
  el.innerHTML = html;
  App.refreshLucide();
}

let _buyingActive = false;
async function agentBuyToken() {
  if (_buyingActive) return;
  if (!App.currentAccount) { alert('请先连接钱包'); return; }
  const amount = parseFloat(document.getElementById('buyAmount')?.value || '0.001');
  _buyingActive = true;
  const btn = document.getElementById('buyTokenBtn');
  if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; btn.innerHTML = '<span style="animation:spin 1s linear infinite;display:inline-block;">⏳</span> 执行中...'; }
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60000);
    const res = await fetch('/api/v1/agent-buy', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ buyerWallet: App.currentAccount, amount }),
      signal: controller.signal
    });
    clearTimeout(timeout);
    const data = await res.json();
    if (data.ok) {
      await loadBuyerStats();
      const orders = window._cachedBuyerOrders || [];
      renderAgentBrain(orders, true);
      renderBuyerTxTable(orders, true);
    } else {
      alert('下单失败: ' + (data.error || '未知错误'));
    }
  } catch(e) {
    if (e.name === 'AbortError') {
      alert('请求超时（60秒），卖家Agent可能未响应，请检查卖家状态');
    } else {
      alert('请求失败: ' + e.message);
    }
  }
  _buyingActive = false;
  if (btn) { btn.disabled = false; btn.style.opacity = '1'; }
}

let _lastRenderedTxHash = '';
function renderBuyerTxTable(orders, force) {
  const tbody = document.getElementById('myTxBody');
  if (!tbody) return;
  _lastRenderedTxHash = Date.now();
  tbody.innerHTML = '';
  const noTx = document.getElementById('noMyTxs');
  if (orders.length === 0) {
    if (noTx) noTx.style.display = 'block';
    return;
  }
  if (noTx) noTx.style.display = 'none';
  const sorted = [...orders].sort((a, b) => new Date(b.time || 0) - new Date(a.time || 0));
  sorted.forEach((o, idx) => {
    if (o.rated) return;
    const time = new Date(o.time).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', hour12:false});
    const isDone = o.status === 'completed' || o.status === 'delivered';
    const statusHtml = isDone ? '<span style="color:#34d399;">✅ 已到账</span>' : '<span style="color:#fbbf24;">⏳ 执行中</span>';
    const txHash = o.txHash || '';
    const shortHash = txHash.length > 10 ? txHash.slice(0,8) + '...' : txHash || '--';
    const txLink = txHash ? '<a href="https://bscscan.com/tx/' + txHash + '" target="_blank" style="color:#8b5cf6;text-decoration:none;font-size:14px;">🔗</a>' : '<span style="color:#475569;">--</span>';
    const tokenAmt = o.tokenAmount || '--';
    const receiptId = o.id || '';
    window['_myBuyerOrders'] = window['_myBuyerOrders'] || {};
    window['_myBuyerOrders'][idx] = { id: receiptId, serviceName: o.serviceName, expert: o.expert, price: o.price, priceCurrency: 'BNB', time: o.time, buyerWallet: App.currentAccount, expertWallet: o.expertWallet, txHash };
    let rateHtml = '<span style="color:#475569;font-size:11px;">--</span>';
    if (isDone && !o.rated) {
      rateHtml = '<span style="cursor:pointer;" onclick="rateOrder(\'' + receiptId + '\')" title="评价">⭐</span>';
    } else if (o.rated) {
      rateHtml = '<span style="color:#fbbf24;">' + '⭐'.repeat(o.rating || 0) + '</span>';
    }
    tbody.innerHTML += '<tr><td class="time">' + time + '</td><td class="flow">' + (o.expert || '--') + '</td><td class="amount">' + (o.price || 0) + ' BNB</td><td>' + statusHtml + '</td><td>' + txLink + '</td><td>' + rateHtml + '</td></tr>';
  });
  App.refreshLucide();
}

async function rateOrder(orderId) {
  const stars = prompt('请评分 1-5 星：\n1=很差  2=差  3=一般  4=好  5=很好');
  const rating = parseInt(stars);
  if (!rating || rating < 1 || rating > 5) { alert('请输入1-5'); return; }
  try {
    const res = await fetch('/api/v1/rate-order', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ orderId, rating, rater: App.currentAccount })
    });
    const data = await res.json();
    if (data.ok) {
      alert('评价成功！');
      loadBuyerStats();
    } else {
      alert('评价失败: ' + (data.error || ''));
    }
  } catch(e) {
    alert('请求失败: ' + e.message);
  }
}

async function submitAgentRegister() {
  const name = document.getElementById('regAgentName').value.trim();
  if (!name) { showError('请输入 Agent 名称'); return; }
  const endpoint = document.getElementById('regAgentEndpoint')?.value?.trim() || '';
  try {
    const res = await fetch('/api/v1/agents/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, wallet: App.currentAccount, endpoint, framework: 'web' })
    });
    const data = await res.json();
    if (data.ok) {
      document.getElementById('myAgentRegister').style.display = 'none';
      document.getElementById('myAgentContent').style.display = 'block';
      document.getElementById('myAddr').textContent = App.currentAccount;
      if (document.getElementById('buyerBalance')) document.getElementById('buyerBalance').textContent = '0.0000 BNB';
      if (document.getElementById('buyerTotalSpent')) document.getElementById('buyerTotalSpent').textContent = '0 BNB';
      if (document.getElementById('buyerOrders')) document.getElementById('buyerOrders').textContent = '0';
      if (document.getElementById('buyerServices')) document.getElementById('buyerServices').textContent = '0';
      showTab('myagent');
    } else {
      showError(data.error || '注册失败');
    }
  } catch(e) {
    showError('注册请求失败: ' + e.message);
  }
}

window.loadBuyerStats = loadBuyerStats;
window.renderAgentBrain = renderAgentBrain;
window.agentBuyToken = agentBuyToken;
window.renderBuyerTxTable = renderBuyerTxTable;
window.rateOrder = rateOrder;
window.submitAgentRegister = submitAgentRegister;
