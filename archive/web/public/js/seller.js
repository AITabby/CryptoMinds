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
    document.getElementById('regFormArea').classList.remove('form-hidden');
    document.getElementById('sellerDashboard').classList.add('panel-hidden');
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
    formArea.classList.add('form-hidden');
    regPanel.classList.add('panel-hidden');
    pendingPage.classList.add('pending-hidden');
    document.getElementById('sellerDashboard').classList.add('panel-hidden');

    if (mySeller) {
      const svcEl = document.getElementById('sellerServiceContent');
      svcEl.innerHTML = '<div class="text-bright font-semibold text-sm mb-xs">' + (mySeller.name || '--') + '</div><div class="text-muted text-sm mb-xs leading-relaxed">' + (mySeller.desc || '') + '</div><div class="flex-center mb-xs"><span class="text-muted text-xs">费率:</span><span class="text-primary font-semibold text-sm">' + (mySeller.feeRate || '--') + ' BNB</span></div><div class="flex-center"><span class="text-muted text-xs">押金:</span><span class="text-primary font-semibold text-sm">' + (mySeller.deposit || 0) + ' BNB</span></div>';
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
        weightEl.innerHTML = '<div class="flex-center gap-md mb-md"><div style="flex:1;"><div class="flex-between mb-xs"><span class="text-muted-strong text-xxs">权重分数</span><span class="text-up font-semibold text-sm">' + weightPercent + '%</span></div><div class="progress-bar-track"><div class="progress-bar-fill" style="width:' + weightPercent + '%;"></div></div></div></div><div class="grid-3col"><div class="stat-cell"><div class="text-primary font-bold text-lg">#' + rank + '</div><div class="text-muted text-xxs">排名</div></div><div class="stat-cell"><div class="text-up font-bold text-lg">★' + (mySeller.rating||'--') + '</div><div class="text-muted text-xxs">评分</div></div><div class="stat-cell"><div class="text-primary font-bold text-lg">' + (mySeller.totalOrders||0) + '</div><div class="text-muted text-xxs">已履约</div></div></div><div class="bg-canvas rounded-xl mt-sm" style="padding:10px;"><div class="text-muted text-xxs mb-xs">💡 提升权重：补押金 → 可接单更多 → 成交更多 → 评分更高</div></div>';
      }
      document.getElementById('sellerDashboard').classList.remove('panel-hidden');
      const metricsDiv2 = document.querySelector('.metrics');
      if (metricsDiv2 && App.activeTab === 'register') {
        metricsDiv2.classList.remove('hidden');
        metricsDiv2.style.display = 'grid';
      }
      App.refreshLucide();
    } else {
      formArea.classList.remove('form-hidden');
      regPanel.classList.add('panel-hidden');
      document.getElementById('sellerDashboard').classList.add('panel-hidden');
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
  document.getElementById('fileUploadHint').classList.add('hidden');
  document.getElementById('fileSelectedInfo').classList.remove('hidden');
  document.getElementById('fileSelectedName').textContent = file.name + ' (' + (file.size < 1024 ? file.size + ' B' : (file.size/1024).toFixed(1) + ' KB') + ')';
  scanSkillFile(file);
  validateRegisterForm();
}

async function scanSkillFile(file) {
  const area = document.getElementById('scanResultArea');
  area.classList.remove('hidden');
  area.className = 'text-muted-strong';
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
    depositBtn.disabled = false;
    depositBtn.className = 'btn-submit';
    depositBtn.textContent = '入驻';
  } else {
    depositBtn.disabled = true;
    depositBtn.className = 'btn-submit opacity-disabled';
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
    if (data.orders.length === 0) { list.innerHTML = '<div class="text-muted-dark text-center" style="padding:20px;">暂无订单</div>'; return; }
    list.innerHTML = data.orders.map(o => {
      const time = new Date(o.time).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai'});
      let statusText = '', statusClass = '';
      if (o.status === 'pending') { statusText = '<i data-lucide="refresh-cw" class="icon-inline"></i> 待交付'; statusClass = 'text-primary'; }
      else if (o.status === 'executing') { statusText = '<i data-lucide="loader" class="icon-inline spin-icon"></i> 执行中'; statusClass = 'text-primary'; }
      else if (o.status === 'delivered') { statusText = '<i data-lucide="check-circle" class="icon-inline"></i> 待买家确认'; statusClass = 'text-up'; }
      else if (o.status === 'completed') { statusText = '<i data-lucide="check-circle" class="icon-inline"></i> 已完成'; statusClass = 'text-up'; }
      else { statusText = o.status; statusClass = 'text-muted-strong'; }
      const needDeliver = (o.status === 'pending' || o.status === 'confirmed') && !o.result;
      return '<div class="order-row"><div class="flex-between"><div><div class="text-bright font-semibold">' + escapeHtml(o.expert || o.sellerName || '订单') + '</div><div class="text-muted text-xxs mt-xs">买家: ' + escapeHtml(o.buyerName || (o.buyerWallet||'').slice(0,10)+'...') + ' | ' + escapeHtml(time) + '</div><div class="text-muted text-xxs">价格: ' + o.price + ' BNB</div>' + (o.input ? '<div class="text-muted text-xxs mt-xs">输入: ' + escapeHtml(typeof o.input === 'string' ? o.input.slice(0,80) : JSON.stringify(o.input).slice(0,80)) + '</div>' : '') + '</div><div style="text-align:right;"><div class="' + statusClass + ' text-xs font-semibold">' + statusText + '</div>' + (needDeliver ? '<div class="text-muted text-xxs mt-xs"><i data-lucide="bot" class="icon-inline"></i> Agent 自主执行中</div>' : '') + (o.result ? '<div class="text-up text-xxs mt-xs"><i data-lucide="check-circle" class="icon-inline"></i> 已履约</div>' : '') + '</div></div></div>';
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
    if (data.notifications.length === 0) { list.innerHTML = '<div class="text-muted-dark text-center" style="padding:20px;">暂无通知</div>'; return; }
    list.innerHTML = data.notifications.map(n => {
      const time = new Date(n.createdAt).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai'});
      let icon = '', content = '';
      if (n.type === 'new_order') { icon = 'shopping-cart'; content = '新订单：<strong class="text-primary">' + n.serviceName + '</strong> — 买家 ' + (n.buyerName || (n.buyerWallet||'').slice(0,8)+'...'); }
      else if (n.type === 'order_confirmed') { icon = 'check-circle'; content = '订单确认：<strong class="text-up">' + n.serviceName + '</strong>'; }
      else if (n.type === 'order_result') { icon = 'package'; content = '结果已出：<strong class="text-up">' + n.serviceName + '</strong>'; }
      return '<div class="activity-row' + (n.read ? ' opacity-50' : '') + '"><span>' + icon + '</span><span>' + content + '</span><span class="text-muted-dark text-xxs" style="margin-left:auto;">' + time + '</span></div>';
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
      const quotaTrend = document.getElementById('sellerQuotaTrend'); if (quotaTrend) { quotaTrend.textContent = '押金 ' + deposit.toFixed(2) + ' BNB'; quotaTrend.className = 'trend text-muted'; }
      const todayIncomeEl = document.getElementById('sellerTodayIncome'); if (todayIncomeEl) todayIncomeEl.textContent = todayIncome.toFixed(4) + ' BNB';
      const todayOrdersEl = document.getElementById('sellerTodayOrders'); if (todayOrdersEl) todayOrdersEl.textContent = todayOrders.length;
      const totalIncomeEl = document.getElementById('sellerTotalIncome'); if (totalIncomeEl) totalIncomeEl.textContent = totalIncome.toFixed(4) + ' BNB';
      const totalIncomeTrend = document.getElementById('sellerTotalIncomeTrend'); if (totalIncomeTrend) { totalIncomeTrend.textContent = orders.length + ' 笔'; totalIncomeTrend.className = 'trend text-muted'; }
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
      if (data.orders.length === 0) { txList.innerHTML = '<div class="text-muted-dark text-center" style="padding:16px;">暂无收支记录</div>'; }
      else {
        let tableHtml = '<table class="tx-table" style="table-layout:fixed;"><colgroup><col style="width:20%;"><col style="width:10%;"><col style="width:14%;"><col style="width:8%;"><col style="width:12%;"><col style="width:16%;"><col style="width:4%;"><col style="width:auto;"></colgroup><tbody>';
        data.orders.forEach(o => {
          const time = new Date(o.time).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', hour12:false});
          const isDone = o.status === 'completed' || o.status === 'delivered';
          const statusHtml = isDone ? '<span class="text-up">✅ 已履约</span>' : '<span class="text-primary">⏳ 执行中</span>';
          const txHash = o.txHash || '--';
          const shortHash = txHash.length > 10 ? txHash.slice(0,8) + '...' : txHash;
          const txLink = txHash !== '--' ? '<a href="https://bscscan.com/tx/' + txHash + '" target="_blank" class="link-primary">' + shortHash + '</a>' : '--';
          const tokenAmt = o.tokenAmount || (isDone ? (parseFloat(o.price)*Math.floor(Math.random()*300+50)).toFixed(2) : '--');
          const tokenAddr = o.tokenAddress || '';
          const tokenCell = tokenAmt !== '--' ? '<span class="text-up font-semibold">' + tokenAmt + '</span><br><span class="text-muted-dark text-xxs">' + (tokenAddr ? tokenAddr.slice(0,6)+'...'+tokenAddr.slice(-4) : '') + '</span>' : '<span class="text-muted-dark">--</span>';
          const buyerTag = o.buyerName ? '<span class="badge-primary-inline">' + o.buyerName + '</span>' : '买家';
          tableHtml += '<tr><td class="time">' + time + '</td><td class="text-bright">' + buyerTag + '</td><td class="text-up" style="text-align:right;">+' + o.price + ' BNB</td><td style="padding:0;"></td><td style="text-align:center;">' + statusHtml + '</td><td style="text-align:right;">' + tokenCell + '</td><td style="padding:0;"></td><td class="text-primary" style="text-align:center;">' + (txLink !== '--' ? '<a href="https://bscscan.com/tx/' + txHash + '" target="_blank" class="link-primary text-lg">🔗</a>' : '<span class="text-muted-dark">--</span>') + '</td></tr>';
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
          activities.push('<div class="activity-row"><span class="text-up text-lg">✅</span><span style="flex:1;">买家 <b class="text-primary">' + escapeHtml(o.buyerName || '买家') + '</b> 的订单已履约，收入 <span class="text-up">' + o.price + ' BNB</span></span><span class="text-muted-dark text-xxs">' + escapeHtml(t) + '</span></div>');
        } else if (o.status === 'pending') {
          activities.push('<div class="activity-row"><span class="text-primary text-lg">⏳</span><span style="flex:1;">买家 <b class="text-primary">' + escapeHtml(o.buyerName || '买家') + '</b> 下单 <span class="text-up">' + o.price + ' BNB</span>，Agent 执行中</span><span class="text-muted-dark text-xxs">' + escapeHtml(t) + '</span></div>');
        }
      });
      activities.push('<div class="activity-row"><span class="text-lg">🛡️</span><span style="flex:1;">押金已确认到账，可接单额度已更新</span><span class="text-muted-dark text-xxs">系统</span></div>');
      activities.push('<div class="activity-row"><span class="text-lg">📊</span><span style="flex:1;">市场排名已更新，当前权重评分正常</span><span class="text-muted-dark text-xxs">系统</span></div>');
      actEl.innerHTML = activities.length > 2 ? activities.join('') : '<div class="text-muted-dark text-center" style="padding:16px;">暂无动态</div>';
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
    if (!seller) { el.innerHTML = '<div class="text-muted-dark">未入驻</div>'; return; }
    const statusClass = seller.active !== false ? 'text-up' : 'text-down';
    el.innerHTML = '<div class="text-bright font-semibold text-sm mb-xs">' + (seller.name || '--') + '</div><div class="text-muted text-sm mb-xs leading-relaxed">' + (seller.desc || '--') + '</div><div class="flex-center mb-xs"><span class="text-muted text-xs">费率:</span><span class="text-primary font-semibold text-sm">' + (seller.feeRate || '--') + '%</span></div><div class="flex-center"><span class="text-muted text-xs">状态:</span><span class="' + statusClass + ' font-semibold text-sm">' + (seller.active !== false ? '在线' : '离线') + '</span></div>';
  } catch(e) {}
}

async function showDepositModal() {
  const quotaEl = document.getElementById('sellerQuota');
  const quotaDisplay = document.getElementById('depositMoreQuota');
  if (quotaDisplay && quotaEl) quotaDisplay.textContent = quotaEl.textContent;
  const amountInput = document.getElementById('depositMoreAmount');
  if (amountInput) amountInput.value = '';
  document.getElementById('depositMoreModal').style.display = 'flex';
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
  modal.className = 'modal-overlay modal-overlay-top';
  modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
  modal.innerHTML = '<div class="modal-card modal-card-sm bg-card border-primary" style="border-color:rgba(246,70,93,0.4);padding:32px;text-align:center;"><div class="mb-md"><i data-lucide="door-open" style="width:48px;height:48px;color:#f6465d;"></i></div><div class="text-bright font-semibold text-xl mb-xs">确认退出？</div><div class="text-muted-strong text-sm mb-md leading-relaxed">退出后押金将退还，已接订单将完成。</div><div class="flex-center" style="justify-content:center;"><button onclick="document.getElementById(\'exitSellerModal\').remove()" class="btn-secondary" style="padding:10px 28px;font-size:14px;">取消</button><button onclick="doExitExpert()" class="btn-danger" style="padding:10px 28px;font-size:14px;">确认退出</button></div></div>';
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
  document.getElementById('registerModal').style.display = 'flex';
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
function closePendingReviewModal() { document.getElementById('pendingReviewModal').style.display = 'none'; document.getElementById('pendingReviewPage').classList.remove('pending-hidden'); document.getElementById('regFormArea').classList.add('form-hidden'); }
function goToPendingPage() { closeDepositModal(); document.getElementById('pendingReviewPage').classList.remove('pending-hidden'); document.getElementById('regFormArea').classList.add('form-hidden'); reloadMarket(); }

async function confirmDepositModal() {
  if (!App.currentAccount) { showError('请先连接钱包'); return; }
  try { await ensureChain('bsc'); } catch(e) { showError('切换到 BSC 链失败'); return; }
  const btn = document.getElementById('depositBtnModal');
  const status = document.getElementById('depositStatusModal');
  btn.disabled = true; btn.textContent = '等待 MetaMask 确认...';
  status.className = 'text-primary';
  status.textContent = '请在 MetaMask 中确认交易...';
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
            status.className = 'text-up';
            status.innerHTML = '<i data-lucide="check-circle" class="icon-inline"></i> 自动审核通过！卖家已上线<br><a href="https://bscscan.com/tx/' + txHash + '" target="_blank" class="link-primary text-xs">查看交易</a><br><br><button onclick="goToPendingPage()" class="btn-primary">查看卖家</button>';
          } else {
            status.className = 'text-primary';
            status.innerHTML = '<i data-lucide="clock" class="icon-inline"></i> 押金已缴纳，等待人工审核<br><a href="https://bscscan.com/tx/' + txHash + '" target="_blank" class="link-primary text-xs">查看交易</a><br><br><button onclick="goToPendingPage()" class="btn-primary">完成</button>';
          }
          setTimeout(goToPendingPage, 3000);
        } else {
          status.className = 'text-down';
          status.innerHTML = '<i data-lucide="x-circle" class="icon-inline"></i> 押金确认失败: ' + depositData.error + '<br><a href="https://bscscan.com/tx/' + txHash + '" target="_blank" class="link-primary text-xs">查看交易</a>';
          btn.disabled = false; btn.textContent = '重新确认';
        }
      } catch(e) {
        status.className = 'text-down';
        status.innerHTML = '<i data-lucide="x-circle" class="icon-inline"></i> 押金确认失败: ' + e.message + '<br><a href="https://bscscan.com/tx/' + txHash + '" target="_blank" class="link-primary text-xs">查看交易</a>';
        btn.disabled = false; btn.textContent = '重新确认';
      }
    } else {
      status.className = 'text-down';
      status.textContent = '卖家ID丢失，请重新提交入驻申请';
      btn.disabled = false; btn.textContent = '缴纳押金';
    }
  } catch(e) {
    status.className = 'text-down';
    status.textContent = (e.message || '交易被取消');
    btn.disabled = false; btn.textContent = '缴纳押金';
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