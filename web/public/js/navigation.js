// CryptoMinds Navigation Module
// Tab switching, metrics display modes, page restore

function initMetricsBackup() {
  App.marketLabels = [];
  document.querySelectorAll('.metrics .metric-card').forEach(c => {
    App.marketLabels.push({
      label: c.querySelector('.label').innerHTML,
      value: c.querySelector('.value').innerHTML,
      valueId: c.querySelector('.value').id,
      trend: c.querySelector('.trend').innerHTML,
      trendId: c.querySelector('.trend').id,
    });
  });
}

function showSellerMetrics() {
  const cards = document.querySelectorAll('.metrics .metric-card');
  if (cards.length < 4) return;
  cards[0].querySelector('.label').textContent = '可接单额度';
  const v0 = cards[0].querySelector('.value'); v0.id = 'sellerQuota'; v0.textContent = '0 BNB'; v0.style.color = '#34d399';
  const t0 = cards[0].querySelector('.trend'); t0.id = 'sellerQuotaTrend'; t0.textContent = ' '; t0.className = 'trend';
  cards[1].querySelector('.label').textContent = '今日收入';
  const v1 = cards[1].querySelector('.value'); v1.id = 'sellerTodayIncome'; v1.textContent = '0 BNB'; v1.style.color = '#fbbf24';
  const t1 = cards[1].querySelector('.trend'); t1.id = 'sellerTodayIncomeTrend'; t1.textContent = ' '; t1.className = 'trend';
  cards[2].querySelector('.label').textContent = '今日成交';
  const v2 = cards[2].querySelector('.value'); v2.id = 'sellerTodayOrders'; v2.textContent = '0'; v2.style.color = '';
  const t2 = cards[2].querySelector('.trend'); t2.id = 'sellerTodayOrdersTrend'; t2.textContent = ' '; t2.className = 'trend';
  cards[3].querySelector('.label').textContent = '累计收入';
  const v3 = cards[3].querySelector('.value'); v3.id = 'sellerTotalIncome'; v3.textContent = '0 BNB'; v3.style.color = '#a78bfa';
  const t3 = cards[3].querySelector('.trend'); t3.id = 'sellerTotalIncomeTrend'; t3.textContent = '--'; t3.className = 'trend'; t3.style.color = '#64748b';
}

function showMarketMetrics() {
  const cards = document.querySelectorAll('.metrics .metric-card');
  if (cards.length < 4) return;
  const labels = MARKET_DEFAULTS;
  for (let i = 0; i < 4; i++) {
    cards[i].querySelector('.label').innerHTML = labels[i].label;
    const val = cards[i].querySelector('.value');
    val.id = labels[i].valueId;
    if (!val.textContent || val.textContent === '--') val.textContent = '0';
    val.style.color = '';
    const trend = cards[i].querySelector('.trend');
    trend.id = labels[i].trendId;
    trend.className = 'trend';
    trend.style.color = '';
  }
  App.refreshLucide();
  applyMarketMetrics();
  reloadMarket();
}

function showBuyerMetrics() {
  const cards = document.querySelectorAll('.metrics .metric-card');
  if (cards.length < 4) return;
  if (!App.currentAccount) {
    cards[0].querySelector('.label').innerHTML = '<i data-lucide="wallet" class="icon-inline"></i> 我的余额';
    const v0 = cards[0].querySelector('.value'); v0.id = 'buyerBalance'; v0.textContent = '未连接'; v0.style.color = '#64748b';
    const t0 = cards[0].querySelector('.trend'); t0.id = 'buyerBalanceTrend'; t0.textContent = ' '; t0.className = 'trend';
    cards[1].querySelector('.label').innerHTML = '<i data-lucide="clipboard-list" class="icon-inline"></i> 我的订单';
    const v1 = cards[1].querySelector('.value'); v1.id = 'buyerOrders'; v1.textContent = '--'; v1.style.color = '#64748b';
    const t1 = cards[1].querySelector('.trend'); t1.id = 'buyerOrdersTrend'; t1.textContent = ' '; t1.className = 'trend';
    cards[2].querySelector('.label').innerHTML = '<i data-lucide="coins" class="icon-inline"></i> 总消费';
    const v2 = cards[2].querySelector('.value'); v2.id = 'buyerTotalSpent'; v2.textContent = '--'; v2.style.color = '#64748b';
    const t2 = cards[2].querySelector('.trend'); t2.id = 'buyerTotalSpentTrend'; t2.textContent = '--'; t2.className = 'trend'; t2.style.color = '#64748b';
    cards[3].querySelector('.label').innerHTML = '<i data-lucide="package" class="icon-inline"></i> 已购订单';
    const v3 = cards[3].querySelector('.value'); v3.id = 'buyerServices'; v3.textContent = '--'; v3.style.color = '#64748b';
    const t3 = cards[3].querySelector('.trend'); t3.id = 'buyerServicesTrend'; t3.textContent = '--'; t3.className = 'trend'; t3.style.color = '#64748b';
    App.refreshLucide();
    return;
  }
  cards[0].querySelector('.label').innerHTML = '<i data-lucide="wallet" class="icon-inline"></i> 我的余额';
  const v0 = cards[0].querySelector('.value'); v0.id = 'buyerBalance'; v0.textContent = '-- BNB'; v0.style.color = '#34d399';
  const t0 = cards[0].querySelector('.trend'); t0.id = 'buyerBalanceTrend'; t0.textContent = ' '; t0.className = 'trend';
  cards[1].querySelector('.label').innerHTML = '<i data-lucide="clipboard-list" class="icon-inline"></i> 已下单';
  const v1 = cards[1].querySelector('.value'); v1.id = 'buyerOrders'; v1.textContent = '0'; v1.style.color = '';
  const t1 = cards[1].querySelector('.trend'); t1.id = 'buyerOrdersTrend'; t1.textContent = ' '; t1.className = 'trend';
  cards[2].querySelector('.label').innerHTML = '<i data-lucide="coins" class="icon-inline"></i> 总支出';
  const v2 = cards[2].querySelector('.value'); v2.id = 'buyerTotalSpent'; v2.textContent = '0 BNB'; v2.style.color = '#f87171';
  const t2 = cards[2].querySelector('.trend'); t2.id = 'buyerTotalSpentTrend'; t2.textContent = '--'; t2.className = 'trend'; t2.style.color = '#64748b';
  cards[3].querySelector('.label').innerHTML = '<i data-lucide="package" class="icon-inline"></i> 收到的币';
  const v3 = cards[3].querySelector('.value'); v3.id = 'buyerReceived'; v3.textContent = '0'; v3.style.color = '#34d399';
  const t3 = cards[3].querySelector('.trend'); t3.id = 'buyerReceivedTrend'; t3.textContent = '--'; t3.className = 'trend'; t3.style.color = '#64748b';
  App.refreshLucide();
}

function showTab(tab) {
  document.querySelectorAll('.nav span').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('[id^="panel-"]').forEach(p => { p.style.display = 'none'; });
  document.getElementById('myAgent').style.display = 'none';
  document.getElementById('txPanel').style.display = 'none';

  const metricsDiv = document.querySelector('.metrics');

  if (tab === 'market') {
    document.querySelector('.nav span:nth-child(1)').classList.add('active');
    document.querySelector('.main').style.display = 'grid';
    document.getElementById('panel-market').style.display = 'flex';
    document.getElementById('txPanel').style.display = 'flex';
    if (metricsDiv) metricsDiv.style.display = 'grid';
    App.activeTab = 'market';
    showMarketMetrics();
    loadTxsFeed();
    startTxsStream();
  } else if (tab === 'register') {
    document.querySelector('.nav span:nth-child(2)').classList.add('active');
    document.getElementById('panel-register').style.display = 'block';
    document.querySelector('.main').style.display = 'none';
    const sellerDashboard = document.getElementById('sellerDashboard');
    if (metricsDiv) metricsDiv.style.display = (sellerDashboard && sellerDashboard.style.display !== 'none') ? 'grid' : 'none';
    App.activeTab = 'register';
    showSellerMetrics();
    loadSellerData();
  } else if (tab === 'myagent') {
    document.querySelector('.nav span:nth-child(3)').classList.add('active');
    document.getElementById('myAgent').style.display = 'block';
    document.querySelector('.main').style.display = 'none';
    if (metricsDiv) metricsDiv.style.display = 'grid';
    App.activeTab = 'myagent';
    showBuyerMetrics();
    if (window._cachedBuyerOrders) {
      const orders = window._cachedBuyerOrders;
      const orderEl = document.getElementById('buyerOrders');
      if (orderEl) orderEl.textContent = orders.length;
      const totalSpent = orders.reduce((sum, o) => sum + parseFloat(o.price || 0), 0);
      const spentEl = document.getElementById('buyerTotalSpent');
      if (spentEl) spentEl.textContent = totalSpent.toFixed(4) + ' BNB';
      const completedOrders = orders.filter(o => o.status === 'completed' || o.status === 'delivered');
      const receivedEl = document.getElementById('buyerReceived');
      if (receivedEl) receivedEl.textContent = completedOrders.length + ' 笔';
      renderBuyerTxTable(orders, true);
      renderAgentBrain(orders);
    }
    loadLiveFeed();
    loadBuyerStats();
    loadEscrowLifecycle();
    loadVouchers();
    loadSessionKeys();
  } else if (tab === 'admin') {
    document.querySelector('#adminTab').classList.add('active');
    document.getElementById('panel-admin').style.display = 'block';
    document.querySelector('.main').style.display = 'none';
    if (metricsDiv) metricsDiv.style.display = 'none';
    loadPendingServices();
    loadDisputedEscrows();
  }
  window.location.hash = tab;
  App.emit('tab-changed', tab);
}

function restoreTab() {
  const hash = window.location.hash.replace('#', '');
  if (['market', 'register', 'myagent', 'admin'].includes(hash)) {
    showTab(hash);
  }
}

window.showTab = showTab;
window.restoreTab = restoreTab;
window.showBuyerMetrics = showBuyerMetrics;
window.showSellerMetrics = showSellerMetrics;
window.showMarketMetrics = showMarketMetrics;
window.initMetricsBackup = initMetricsBackup;
