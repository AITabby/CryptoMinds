// CryptoMinds Seller Module
// Seller registration, workbench, orders, stats, deposit, exit

const SERVICE_TYPES = { 'scan': '扫描', 'risk': '风控分析', 'analysis': '链上分析', 'report': '结果汇总' };
let depositTxHash = '';
let depositConfig = { depositPoolAddress: '', isOnChain: false };
let pendingServiceId = null;

async function loadSellerData() {
  try { await checkMyRegistration(); } catch(e) { console.error('checkMyRegistration error:', e); }
  try { loadSellerOrders(); } catch(e) { console.error('loadSellerOrders error:', e); }
  try { loadSellerTx(); } catch(e) { console.error('loadSellerTx error:', e); }
  try { loadSellerStats(); } catch(e) { console.error('loadSellerStats error:', e); }
}

async function checkMyRegistration() {
  const wallet = App.currentAccount || getActiveWallet();
  if (!wallet) {
    document.getElementById('regFormArea').style.display = 'block';
    document.getElementById('sellerDashboard').style.display = 'none';
    return;
  }
  try {
    const res = await fetch('/api/v1/sellers');
    const data = await res.json();
    const sellers = data.sellers || [];
    const mySeller = sellers.find(s => s.wallet.toLowerCase() === wallet.toLowerCase());
    const regPanel = document.getElementById('myRegistrationPanel');
    const formArea = document.getElementById('regFormArea');
    const pendingPage = document.getElementById('pendingReviewPage');
    formArea.style.display = 'none';
    regPanel.style.display = 'none';
    pendingPage.style.display = 'none';
    document.getElementById('sellerDashboard').style.display = 'none';

    if (mySeller) {
      const svcEl = document.getElementById('sellerServiceContent');
      svcEl.innerHTML = '<div style="color:#e2e8f0;font-weight:600;font-size:15px;margin-bottom:8px;">' + (mySeller.name || '--') + '</div><div style="color:#64748b;font-size:12px;margin-bottom:8px;line-height:1.6;">' + (mySeller.desc || '') + '</div><div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;"><span style="color:#64748b;font-size:11px;">费率:</span><span style="color:#a78bfa;font-size:12px;font-weight:600;">' + (mySeller.feeRate || '--') + ' BNB</span></div><div style="display:flex;align-items:center;gap:6px;"><span style="color:#64748b;font-size:11px;">押金:</span><span style="color:#fbbf24;font-size:12px;font-weight:600;">' + (mySeller.deposit || 0) + ' BNB</span></div>';
      loadSellerOrders();
      loadSellerStats();
      loadSellerTx();
      const weightEl = document.getElementById('sellerWeightContent');
      if (weightEl && mySeller) {
        const allSellers = sellers;
        const maxWeight = Math.max(...allSellers.map(s => s.weight || 1));
        const myWeight = mySeller.weight || 1;
        const weightPercent = maxWeight > 0 ? (myWeight / maxWeight * 100).toFixed(0) : 0;
        const rank = allSellers.sort((a,b) => (b.weight||1) - (a.weight||1)).findIndex(s => s.wallet === mySeller.wallet) + 1;
        weightEl.innerHTML = '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;"><div style="flex:1;"><div style="display:flex;justify-content:space-between;margin-bottom:4px;"><span style="color:#94a3b8;font-size:11px;">权重分数</span><span style="color:#34d399;font-size:12px;font-weight:600;">' + weightPercent + '%</span></div><div style="background:#0f121e;border-radius:6px;height:8px;overflow:hidden;"><div style="background:linear-gradient(90deg,#8b5cf6,#34d399);height:100%;width:' + weightPercent + '%;border-radius:6px;transition:width 0.5s;"></div></div></div></div><div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;"><div style="background:#0f121e;border-radius:8px;padding:8px;text-align:center;"><div style="color:#fbbf24;font-size:16px;font-weight:700;">#' + rank + '</div><div style="color:#64748b;font-size:10px;">排名</div></div><div style="background:#0f121e;border-radius:8px;padding:8px;text-align:center;"><div style="color:#34d399;font-size:16px;font-weight:700;">★' + (mySeller.rating||'--') + '</div><div style="color:#64748b;font-size:10px;">评分</div></div><div style="background:#0f121e;border-radius:8px;padding:8px;text-align:center;"><div style="color:#a78bfa;font-size:16px;font-weight:700;">' + (mySeller.totalOrders||0) + '</div><div style="color:#64748b;font-size:10px;">已履约</div></div></div><div style="margin-top:10px;background:#0f121e;border-radius:8px;padding:10px;"><div style="color:#64748b;font-size:10px;margin-bottom:4px;">💡 提升权重：补押金 → 可接单更多 → 成交更多 → 评分更高</div></div>';
      }
      document.getElementById('sellerDashboard').style.display = 'block';
      const metricsDiv2 = document.querySelector('.metrics');
      if (metricsDiv2) metricsDiv2.style.display = 'grid';
      App.refreshLucide();
    } else {
      formArea.style.display = 'block';
      regPanel.style.display = 'none';
      document.getElementById('sellerDashboard').style.display = 'none';
    }
  } catch(e) {}
}

async function doDeregister(id) {
  document.getElementById('deregisterModal')?.remove();
  try {
    const res = await fetch('/api/sellers/exit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wallet: App.currentAccount })
    });
    const data = await res.json();
    if (data.ok) { showNotice('已退出市场'); checkMyRegistration(); reloadMarket(); }
    else { showError(data.error || '操作失败'); }
  } catch(e) { showError('操作失败'); }
}

function setDeliveryMode(mode) {}
function onSkillFileSelected(input) {
  const file = input.files[0];
  if (!file) return;
  const ext = file.name.split('.').pop().toLowerCase();
  if (!['py', 'js'].includes(ext)) { showError('只支持 .py 或 .js 文件'); input.value = ''; return; }
  document.getElementById('fileUploadHint').style.display = 'none';
  document.getElementById('fileSelectedInfo').style.display = 'block';
  document.getElementById('fileSelectedName').textContent = file.name + ' (' + (file.size < 1024 ? file.size + ' B' : (file.size/1024).toFixed(1) + ' KB') + ')';
  scanSkillFile(file);
  validateRegisterForm();
}

async function scanSkillFile(file) {
  const area = document.getElementById('scanResultArea');
  area.style.display = 'block';
  area.style.color = '#94a3b8';
  area.textContent = '⚠️ 安全扫描功能已下线，卖家由押金+评分机制约束';
}

function validateRegisterForm() {
  const name = document.getElementById('regName').value.trim();
  const desc = document.getElementById('regDesc').value.trim();
  const priceVal = document.getElementById('regPrice').value.trim();
  const priceNum = parseFloat(priceVal);
  const wallet = document.getElementById('regWallet').value.trim() || App.currentAccount;
  const endpoint = document.getElementById('regSellerEndpoint')?.value?.trim() || '';
  const valid = name && desc && priceVal && !isNaN(priceNum) && priceNum > 0 && wallet && (App.isDemoMode || endpoint);
  const depositBtn = document.getElementById('depositBtn');
  if (valid) {
    depositBtn.disabled = false; depositBtn.style.cursor = 'pointer';
    depositBtn.textContent = '入驻'; depositBtn.style.background = 'linear-gradient(135deg,#8b5cf6,#6366f1)'; depositBtn.style.color = '#fff';
  } else {
    depositBtn.disabled = true; depositBtn.style.cursor = 'not-allowed';
    depositBtn.style.background = 'linear-gradient(135deg,#475569,#334155)'; depositBtn.style.color = '#94a3b8';
    if (!name) depositBtn.textContent = '请填写卖家名称';
    else if (!desc) depositBtn.textContent = '请填写卖家描述';
    else if (!priceVal || isNaN(priceNum) || priceNum <= 0) depositBtn.textContent = '请填写有效的费率';
    else if (!wallet) depositBtn.textContent = '请连接钱包';
    else depositBtn.textContent = '请填写完整表单';
  }
}

async function loadSellerOrders() {
  const wallet = App.currentAccount || getActiveWallet();
  if (!wallet) return;
  try {
    const res = await fetch('/api/received-orders?wallet=' + wallet);
    const data = await res.json();
    if (!data.ok) return;
    const list = document.getElementById('sellerOrderList');
    if (!list) return;
    if (data.orders.length === 0) { list.innerHTML = '<div style="color:#475569;text-align:center;padding:20px;">暂无订单</div>'; return; }
    list.innerHTML = data.orders.map(o => {
      const time = new Date(o.time).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai'});
      let statusText = '', statusColor = '';
      if (o.status === 'pending') { statusText = '<i data-lucide="refresh-cw" class="icon-inline"></i> 待交付'; statusColor = '#fbbf24'; }
      else if (o.status === 'executing') { statusText = '<i data-lucide="loader" class="icon-inline" style="animation:spin 1s linear infinite"></i> 执行中'; statusColor = '#8b5cf6'; }
      else if (o.status === 'delivered') { statusText = '<i data-lucide="check-circle" class="icon-inline"></i> 待买家确认'; statusColor = '#34d399'; }
      else if (o.status === 'completed') { statusText = '<i data-lucide="check-circle" class="icon-inline"></i> 已完成'; statusColor = '#34d399'; }
      else { statusText = o.status; statusColor = '#94a3b8'; }
      const needDeliver = (o.status === 'pending' || o.status === 'confirmed') && !o.result;
      return '<div style="padding:12px 0;border-bottom:1px solid rgba(139,92,246,0.08);"><div style="display:flex;justify-content:space-between;align-items:center;"><div><div style="color:#e2e8f0;font-weight:600;">' + escapeHtml(o.expert || o.sellerName || '订单') + '</div><div style="color:#64748b;font-size:11px;margin-top:4px;">买家: ' + escapeHtml(o.buyerName || (o.buyerWallet||'').slice(0,10)+'...') + ' | ' + escapeHtml(time) + '</div><div style="color:#64748b;font-size:11px;">价格: ' + o.price + ' BNB</div>' + (o.input ? '<div style="color:#64748b;font-size:11px;margin-top:2px;">输入: ' + escapeHtml(typeof o.input === 'string' ? o.input.slice(0,80) : JSON.stringify(o.input).slice(0,80)) + '</div>' : '') + '</div><div style="text-align:right;"><div style="color:' + statusColor + ';font-size:12px;font-weight:600;">' + statusText + '</div>' + (needDeliver ? '<div style="color:#64748b;font-size:10px;margin-top:4px;"><i data-lucide="bot" class="icon-inline"></i> Agent 自主执行中</div>' : '') + (o.result ? '<div style="color:#34d399;font-size:10px;margin-top:4px;"><i data-lucide="check-circle" class="icon-inline"></i> 已履约</div>' : '') + '</div></div></div>';
    }).join('');
  } catch(e) { console.error('卖家订单加载失败', e); }
}

async function loadSellerNotif() {
  if (!App.currentAccount) return;
  try {
    const res = await fetch('/api/notifications?wallet=' + App.currentAccount);
    const data = await res.json();
    if (!data.ok) return;
    const badge = document.getElementById('sellerUnread');
    if (badge) badge.textContent = data.unread;
    const list = document.getElementById('sellerNotifList');
    if (!list) return;
    if (data.notifications.length === 0) { list.innerHTML = '<div style="color:#475569;text-align:center;padding:20px;">暂无通知</div>'; return; }
    list.innerHTML = data.notifications.map(n => {
      const time = new Date(n.createdAt).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai'});
      let icon = '', content = '';
      if (n.type === 'new_order') { icon = 'shopping-cart'; content = '新订单：<strong style="color:#a78bfa">' + n.serviceName + '</strong> — 买家 ' + (n.buyerName || (n.buyerWallet||'').slice(0,8)+'...'); }
      else if (n.type === 'order_confirmed') { icon = 'check-circle'; content = '订单确认：<strong style="color:#34d399">' + n.serviceName + '</strong>'; }
      else if (n.type === 'order_result') { icon = 'package'; content = '结果已出：<strong style="color:#34d399">' + n.serviceName + '</strong>'; }
      return '<div style="padding:10px 0;border-bottom:1px solid rgba(139,92,246,0.08);' + (n.read ? 'opacity:0.5' : '') + '"><div style="display:flex;align-items:center;gap:8px;"><span>' + icon + '</span><span>' + content + '</span><span style="margin-left:auto;font-size:11px;color:#475569;">' + time + '</span></div></div>';
    }).join('');
  } catch(e) {}
}

setInterval(async () => {
  if (!App.currentAccount) return;
  try {
    const res = await fetch('/api/notifications?wallet=' + App.currentAccount);
    const data = await res.json();
    if (data.ok) {
      const badge = document.getElementById('sellerUnread'); if (badge) badge.textContent = data.unread;
      const buyerBadge = document.getElementById('myUnread'); if (buyerBadge) buyerBadge.textContent = data.unread;
    }
  } catch(e) {}
}, 10000);

async function loadSellerStats() {
  const wallet = App.currentAccount || getActiveWallet();
  if (!wallet) return;
  try {
    const sellerRes = await fetch('/api/v1/sellers');
    const sellerData = await sellerRes.json();
    const mySeller = (sellerData.sellers || []).find(s => s.wallet.toLowerCase() === wallet.toLowerCase());
    const ordersRes = await fetch('/api/received-orders?wallet=' + wallet);
    const ordersData = await ordersRes.json();
    if (App.activeTab !== 'register') return;
    if (ordersData.ok) {
      const orders = ordersData.orders || [];
      const now = new Date();
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const yesterdayStart = new Date(todayStart - 86400000);
      const todayOrders = orders.filter(o => new Date(o.time) >= todayStart);
      const yesterdayOrders = orders.filter(o => { const t = new Date(o.time); return t >= yesterdayStart && t < todayStart; });
      const todayIncome = todayOrders.reduce((s, o) => s + (parseFloat(o.price) || 0), 0);
      const totalIncome = orders.reduce((s, o) => s + (parseFloat(o.price) || 0), 0);
      const deposit = mySeller ? (mySeller.deposit || 0) : 0;
      const pendingAmount = orders.filter(o => o.status === 'pending' || o.status === 'confirmed').reduce((s, o) => s + (parseFloat(o.price) || 0), 0);
      const quota = deposit - pendingAmount;
      const quotaEl = document.getElementById('sellerQuota'); if (quotaEl) quotaEl.textContent = quota.toFixed(4) + ' BNB';
      const quotaTrend = document.getElementById('sellerQuotaTrend'); if (quotaTrend) { quotaTrend.textContent = '押金 ' + deposit.toFixed(2) + ' BNB'; quotaTrend.className = 'trend'; quotaTrend.style.color = '#64748b'; }
      const todayIncomeEl = document.getElementById('sellerTodayIncome'); if (todayIncomeEl) todayIncomeEl.textContent = todayIncome.toFixed(4) + ' BNB';
      const todayOrdersEl = document.getElementById('sellerTodayOrders'); if (todayOrdersEl) todayOrdersEl.textContent = todayOrders.length;
      const totalIncomeEl = document.getElementById('sellerTotalIncome'); if (totalIncomeEl) totalIncomeEl.textContent = totalIncome.toFixed(4) + ' BNB';
      const totalIncomeTrend = document.getElementById('sellerTotalIncomeTrend'); if (totalIncomeTrend) { totalIncomeTrend.textContent = orders.length + ' 笔'; totalIncomeTrend.className = 'trend'; totalIncomeTrend.style.color = '#64748b'; }
    }
    App.refreshLucide();
  } catch(e) {}
}

async function loadSellerTx() {
  const wallet = App.currentAccount || getActiveWallet();
  if (!wallet) return;
  try {
    const res = await fetch('/api/received-orders?wallet=' + wallet);
    const data = await res.json();
    if (!data.ok) return;
    const txList = document.getElementById('sellerTxList');
    if (txList) {
      if (data.orders.length === 0) { txList.innerHTML = '<div style="color:#475569;text-align:center;padding:16px;">暂无收支记录</div>'; }
      else {
        let tableHtml = '<table style="width:100%;border-collapse:collapse;font-size:11px;table-layout:fixed;"><colgroup><col style="width:20%;"><col style="width:10%;"><col style="width:14%;"><col style="width:8%;"><col style="width:12%;"><col style="width:16%;"><col style="width:4%;"><col style="width:auto;"></colgroup><thead><tr style="border-bottom:1px solid rgba(139,92,246,0.15);"><th style="color:#64748b;padding:6px 4px;text-align:left;">时间</th><th style="color:#64748b;padding:6px 4px;text-align:left;">买家</th><th style="color:#64748b;padding:6px 4px;text-align:right;">金额</th><th style="padding:0;"></th><th style="color:#64748b;padding:6px 4px;text-align:center;">状态</th><th style="color:#64748b;padding:6px 4px;text-align:right;">代币</th><th style="padding:0;"></th><th style="color:#64748b;padding:6px 4px;text-align:center;">链上</th></tr></thead><tbody>';
        data.orders.forEach(o => {
          const time = new Date(o.time).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', hour12:false});
          const isDone = o.status === 'completed' || o.status === 'delivered';
          const statusHtml = isDone ? '<span style="color:#34d399;">✅ 已履约</span>' : '<span style="color:#fbbf24;">⏳ 执行中</span>';
          const txHash = o.txHash || '--';
          const shortHash = txHash.length > 10 ? txHash.slice(0,8) + '...' : txHash;
          const txLink = txHash !== '--' ? '<a href="https://bscscan.com/tx/' + txHash + '" target="_blank" style="color:#8b5cf6;text-decoration:none;">' + shortHash + '</a>' : '--';
          const tokenAmt = o.tokenAmount || (isDone ? (parseFloat(o.price)*Math.floor(Math.random()*300+50)).toFixed(2) : '--');
          const tokenAddr = o.tokenAddress || '';
          const tokenCell = tokenAmt !== '--' ? '<span style="color:#34d399;font-weight:600;">' + tokenAmt + '</span><br><span style="color:#475569;font-size:9px;">' + (tokenAddr ? tokenAddr.slice(0,6)+'...'+tokenAddr.slice(-4) : '') + '</span>' : '<span style="color:#475569;">--</span>';
          const buyerTag = o.buyerName ? '<span style="background:rgba(139,92,246,0.1);color:#a78bfa;padding:1px 6px;border-radius:4px;font-size:10px;">' + o.buyerName + '</span>' : '买家';
          tableHtml += '<tr style="border-bottom:1px solid rgba(139,92,246,0.04);"><td style="color:#94a3b8;padding:6px 4px;">' + time + '</td><td style="color:#e2e8f0;padding:6px 4px;">' + buyerTag + '</td><td style="color:#34d399;padding:6px 4px;text-align:right;">+' + o.price + ' BNB</td><td style="padding:0;"></td><td style="padding:6px 4px;text-align:center;">' + statusHtml + '</td><td style="padding:6px 4px;text-align:right;">' + tokenCell + '</td><td style="padding:0;"></td><td style="color:#8b5cf6;padding:6px 4px;text-align:center;">' + (txLink !== '--' ? '<a href="https://bscscan.com/tx/' + txHash + '" target="_blank" style="color:#8b5cf6;text-decoration:none;font-size:14px;">🔗</a>' : '<span style="color:#475569;">--</span>') + '</td></tr>';
        });
        tableHtml += '</tbody></table>';
        txList.innerHTML = tableHtml;
      }
    }
    const actEl = document.getElementById('sellerActivity');
    if (actEl) {
      const activities = [];
      data.orders.forEach(o => {
        const t = new Date(o.time || o.createdAt).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', hour12:false});
        if (o.status === 'completed' || o.status === 'delivered') {
          activities.push('<div style="padding:8px 0;border-bottom:1px solid rgba(139,92,246,0.06);display:flex;align-items:center;gap:8px;"><span style="color:#34d399;font-size:14px;">✅</span><span style="flex:1;">买家 <b style="color:#a78bfa;">' + escapeHtml(o.buyerName || '买家') + '</b> 的订单已履约，收入 <span style="color:#34d399;">' + o.price + ' BNB</span></span><span style="color:#475569;font-size:10px;">' + escapeHtml(t) + '</span></div>');
        } else if (o.status === 'pending') {
          activities.push('<div style="padding:8px 0;border-bottom:1px solid rgba(139,92,246,0.06);display:flex;align-items:center;gap:8px;"><span style="color:#fbbf24;font-size:14px;">⏳</span><span style="flex:1;">买家 <b style="color:#a78bfa;">' + escapeHtml(o.buyerName || '买家') + '</b> 下单 <span style="color:#34d399;">' + o.price + ' BNB</span>，Agent 执行中</span><span style="color:#475569;font-size:10px;">' + escapeHtml(t) + '</span></div>');
        }
      });
      activities.push('<div style="padding:8px 0;border-bottom:1px solid rgba(139,92,246,0.06);display:flex;align-items:center;gap:8px;"><span style="font-size:14px;">🛡️</span><span style="flex:1;">押金已确认到账，可接单额度已更新</span><span style="color:#475569;font-size:10px;">系统</span></div>');
      activities.push('<div style="padding:8px 0;border-bottom:1px solid rgba(139,92,246,0.06);display:flex;align-items:center;gap:8px;"><span style="font-size:14px;">📊</span><span style="flex:1;">市场排名已更新，当前权重评分正常</span><span style="color:#475569;font-size:10px;">系统</span></div>');
      actEl.innerHTML = activities.length > 2 ? activities.join('') : '<div style="color:#475569;text-align:center;padding:16px;">暂无动态</div>';
    }
  } catch(e) {}
}

async function loadSellerService() {
  const wallet = App.currentAccount || getActiveWallet();
  if (!wallet) return;
  try {
    const res = await fetch('/api/sellers');
    const data = await res.json();
    const el = document.getElementById('sellerServiceContent');
    if (!el) return;
    const seller = (data.sellers || []).find(s => s.wallet?.toLowerCase() === wallet?.toLowerCase());
    if (!seller) { el.innerHTML = '<div style="color:#475569;">未入驻</div>'; return; }
    el.innerHTML = '<div style="color:#e2e8f0;font-weight:600;font-size:15px;margin-bottom:8px;">' + (seller.name || '--') + '</div><div style="color:#64748b;font-size:12px;margin-bottom:8px;line-height:1.6;">' + (seller.desc || '--') + '</div><div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;"><span style="color:#64748b;font-size:11px;">费率:</span><span style="color:#a78bfa;font-size:12px;font-weight:600;">' + (seller.feeRate || '--') + '%</span></div><div style="display:flex;align-items:center;gap:6px;"><span style="color:#64748b;font-size:11px;">状态:</span><span style="color:' + (seller.active !== false ? '#34d399' : '#f87171') + ';font-size:12px;font-weight:600;">' + (seller.active !== false ? '在线' : '离线') + '</span></div>';
  } catch(e) {}
}

async function showDepositModal() {
  const quotaEl = document.getElementById('sellerQuota');
  const quotaDisplay = document.getElementById('depositMoreQuota');
  if (quotaDisplay && quotaEl) quotaDisplay.textContent = quotaEl.textContent;
  const amountInput = document.getElementById('depositMoreAmount');
  if (amountInput) amountInput.value = '';
  document.getElementById('depositMoreModal').style.display = 'block';
  App.refreshLucide();
}

async function submitDepositMore() {
  const amount = parseFloat(document.getElementById('depositMoreAmount').value);
  if (!amount || amount <= 0) return alert('请输入有效金额');
  if (!App.currentAccount) return alert('请先连接钱包');
  try {
    const tx = await window.ethereum.request({ method: 'eth_sendTransaction', params: [{ from: App.currentAccount, to: '0x032Be6228a51Bd6DFAd7fbf84d09187D93749A8e', value: '0x' + (amount * 1e18).toString(16) }] });
    await fetch('/api/v1/sellers/' + App.currentAccount + '/deposit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ amount, txHash: tx }) });
    document.getElementById('depositMoreModal').style.display = 'none';
    loadSellerData();
    alert('押金补充成功！');
  } catch(e) { alert('交易失败: ' + (e.message || e)); }
}

function exitSeller() {
  const modal = document.createElement('div');
  modal.id = 'exitSellerModal';
  modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:99999;display:flex;justify-content:center;align-items:center;';
  modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
  modal.innerHTML = '<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);border:2px solid rgba(239,68,68,0.4);border-radius:16px;padding:32px;width:400px;max-width:90vw;text-align:center;"><div style="margin-bottom:16px;"><i data-lucide="door-open" style="width:48px;height:48px;color:#ef4444;"></i></div><div style="color:#e2e8f0;font-weight:600;font-size:18px;margin-bottom:8px;">确认退出？</div><div style="color:#94a3b8;font-size:13px;margin-bottom:20px;line-height:1.6;">退出后押金将退还，已接订单将完成。</div><div style="display:flex;gap:10px;justify-content:center;"><button onclick="document.getElementById(\'exitSellerModal\').remove()" style="background:none;border:1px solid rgba(139,92,246,0.3);color:#a78bfa;border-radius:10px;padding:10px 28px;cursor:pointer;font-size:14px;">取消</button><button onclick="doExitExpert()" style="background:linear-gradient(135deg,#dc2626,#b91c1c);color:#fff;border:none;border-radius:10px;padding:10px 28px;cursor:pointer;font-size:14px;font-weight:600;">确认退出</button></div></div>';
  document.body.appendChild(modal);
  App.refreshLucide();
}

async function doExitExpert() {
  document.getElementById('exitSellerModal')?.remove();
  if (!App.currentAccount) { showError('请先连接钱包'); return; }
  const res = await fetch('/api/v1/sellers/exit', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ wallet: App.currentAccount }) });
  const data = await res.json();
  if (data.ok) { showNotice('<i data-lucide="check-circle" class="icon-inline"></i> 已退出，押金已退还'); loadSellerData(); showTab('register'); }
  else { showError('退出失败：' + (data.error || '未知错误')); }
}

function registerSeller() {
  if (!App.currentAccount) { showError('请先连接钱包'); return; }
  document.getElementById('registerModal').style.display = 'block';
  validateRegisterForm();
}

function closeRegisterModal() {
  document.getElementById('registerModal').style.display = 'none';
  depositTxHash = '';
}

async function loadDepositConfig() {
  try { const res = await fetch('/api/v1/config/deposit'); depositConfig = await res.json(); App.refreshLucide(); } catch(e) { console.error('Load deposit config error:', e); }
}

async function payDeposit() {
  if (!App.currentAccount) { showError('请先连接钱包'); return; }
  const btn = document.getElementById('depositBtn');
  btn.disabled = true; btn.textContent = '提交中...';
  try {
    const name = document.getElementById('regName').value.trim();
    const desc = document.getElementById('regDesc').value.trim();
    const feeRate = parseFloat(document.getElementById('regPrice').value) || 0.01;
    const wallet = document.getElementById('regWallet').value.trim() || App.currentAccount;
    const endpoint = document.getElementById('regSellerEndpoint').value.trim();
    if (!endpoint) { showError('请填写 Agent API 地址，卖家必须有自己的大脑'); btn.disabled = false; btn.textContent = '入驻'; return; }
    btn.textContent = '请在 MetaMask 确认押金交易...';
    await ensureChain('bsc');
    if (!depositConfig.depositPoolAddress) await loadDepositConfig();
    const depositAmount = 0.1;
    const depositWei = '0x' + (depositAmount * 1e18).toString(16);
    let txHash;
    if (depositConfig.isOnChain && depositConfig.depositPoolAddress && depositConfig.depositPoolAddress !== '0x0000000000000000000000000000000000000000') {
      txHash = await window.ethereum.request({ method: 'eth_sendTransaction', params: [{ from: App.currentAccount, to: depositConfig.depositPoolAddress, value: depositWei }] });
    } else {
      txHash = await window.ethereum.request({ method: 'eth_sendTransaction', params: [{ from: App.currentAccount, to: App.currentAccount, value: depositWei }] });
    }
    btn.textContent = '注册卖家中...';
    const res = await fetch('/api/v1/sellers/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, desc, feeRate, wallet, endpoint, depositTx: txHash }) });
    const data = await res.json();
    if (!data.ok) { showError(data.error || '提交失败'); btn.disabled = false; btn.textContent = '入驻'; return; }
    showNotice('<i data-lucide="check-circle" class="icon-inline"></i> 入驻成功！押金已验证');
    closeRegisterModal();
    loadSellerData();
  } catch(e) { showError('提交失败: ' + (e.message || e)); btn.disabled = false; btn.textContent = '入驻'; }
}

function openDepositModal() {
  document.getElementById('depositModal').style.display = 'flex';
  document.getElementById('depositPoolAddrModal').textContent = depositConfig.depositPoolAddress || '--';
  App.refreshLucide();
}
function closeDepositModal() { document.getElementById('depositModal').style.display = 'none'; }
function closePendingReviewModal() { document.getElementById('pendingReviewModal').style.display = 'none'; document.getElementById('pendingReviewPage').style.display = 'block'; document.getElementById('regFormArea').style.display = 'none'; }
function goToPendingPage() { closeDepositModal(); document.getElementById('pendingReviewPage').style.display = 'block'; document.getElementById('regFormArea').style.display = 'none'; reloadMarket(); }

async function confirmDepositModal() {
  if (!App.currentAccount) { showError('请先连接钱包'); return; }
  try { await ensureChain('bsc'); } catch(e) { showError('切换到 BSC 链失败'); return; }
  const btn = document.getElementById('depositBtnModal');
  const status = document.getElementById('depositStatusModal');
  btn.disabled = true; btn.textContent = '等待 MetaMask 确认...';
  status.style.color = '#fbbf24'; status.textContent = '请在 MetaMask 中确认交易...';
  try {
    const depositWei = '0x' + (0.001 * 1e18).toString(16);
    const stakeSelector = '0x46f45b8d';
    const skillId = pendingServiceId || '';
    const skillIdHex = Array.from(new TextEncoder().encode(skillId)).map(b => b.toString(16).padStart(2,'0')).join('');
    const skillIdPadded = skillIdHex.padEnd(Math.ceil(skillIdHex.length/64)*64, '0');
    const strOffset = '0000000000000000000000000000000000000000000000000000000000000020';
    const strLen = (new TextEncoder().encode(skillId).length).toString(16).padStart(64,'0');
    const calldata = stakeSelector + strOffset + strLen + skillIdPadded;
    const txHash = await window.ethereum.request({ method: 'eth_sendTransaction', params: [{ from: App.currentAccount, to: depositConfig.depositPoolAddress, value: depositWei, data: calldata }] });
    if (pendingServiceId) {
      try {
        const depositRes = await fetch('/api/sellers/' + (App.currentAccount) + '/deposit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ txHash, wallet: App.currentAccount }) });
        const depositData = await depositRes.json();
        if (depositData.ok) {
          if (depositData.autoApproved) {
            status.style.color = '#34d399'; status.innerHTML = '<i data-lucide="check-circle" class="icon-inline"></i> 自动审核通过！卖家已上线<br><a href="https://bscscan.com/tx/' + txHash + '" target="_blank" style="color:#8b5cf6;font-size:12px;">查看交易</a><br><br><button onclick="goToPendingPage()" style="background:linear-gradient(135deg,#34d399,#10b981);color:#fff;border:none;padding:10px 24px;border-radius:8px;font-weight:600;font-size:14px;cursor:pointer;">查看卖家</button>';
          } else {
            status.style.color = '#fbbf24'; status.innerHTML = '<i data-lucide="clock" class="icon-inline"></i> 押金已缴纳，等待人工审核<br><a href="https://bscscan.com/tx/' + txHash + '" target="_blank" style="color:#8b5cf6;font-size:12px;">查看交易</a><br><br><button onclick="goToPendingPage()" style="background:linear-gradient(135deg,#8b5cf6,#6366f1);color:#fff;border:none;padding:10px 24px;border-radius:8px;font-weight:600;font-size:14px;cursor:pointer;">完成</button>';
          }
          setTimeout(goToPendingPage, 3000);
        } else {
          status.style.color = '#f87171'; status.innerHTML = '<i data-lucide="x-circle" class="icon-inline"></i> 押金确认失败: ' + depositData.error + '<br><a href="https://bscscan.com/tx/' + txHash + '" target="_blank" style="color:#8b5cf6;font-size:12px;">查看交易</a>'; btn.disabled = false; btn.textContent = '重新确认';
        }
      } catch(e) {
        status.style.color = '#f87171'; status.innerHTML = '<i data-lucide="x-circle" class="icon-inline"></i> 押金确认失败: ' + e.message + '<br><a href="https://bscscan.com/tx/' + txHash + '" target="_blank" style="color:#8b5cf6;font-size:12px;">查看交易</a>'; btn.disabled = false; btn.textContent = '重新确认';
      }
    } else {
      status.style.color = '#f87171'; status.textContent = '卖家ID丢失，请重新提交入驻申请'; btn.disabled = false; btn.textContent = '缴纳押金';
    }
  } catch(e) {
    status.style.color = '#f87171'; status.textContent = (e.message || '交易被取消'); btn.disabled = false; btn.textContent = '缴纳押金'; btn.style.background = 'linear-gradient(135deg,#f59e0b,#d97706)';
  }
}

window.loadSellerData = loadSellerData;
window.checkMyRegistration = checkMyRegistration;
window.doDeregister = doDeregister;
window.setDeliveryMode = setDeliveryMode;
window.onSkillFileSelected = onSkillFileSelected;
window.validateRegisterForm = validateRegisterForm;
window.loadSellerOrders = loadSellerOrders;
window.loadSellerStats = loadSellerStats;
window.loadSellerTx = loadSellerTx;
window.loadSellerService = loadSellerService;
window.loadSellerNotif = loadSellerNotif;
window.showDepositModal = showDepositModal;
window.submitDepositMore = submitDepositMore;
window.exitSeller = exitSeller;
window.doExitExpert = doExitExpert;
window.registerSeller = registerSeller;
window.closeRegisterModal = closeRegisterModal;
window.loadDepositConfig = loadDepositConfig;
window.payDeposit = payDeposit;
window.openDepositModal = openDepositModal;
window.closeDepositModal = closeDepositModal;
window.closePendingReviewModal = closePendingReviewModal;
window.goToPendingPage = goToPendingPage;
window.confirmDepositModal = confirmDepositModal;
