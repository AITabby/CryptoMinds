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
  const v0 = cards[0].querySelector('.value'); v0.id = 'sellerQuota'; v0.textContent = '0 BNB'; v0.className = 'value text-up';
  const t0 = cards[0].querySelector('.trend'); t0.id = 'sellerQuotaTrend'; t0.textContent = ' '; t0.className = 'trend';
  cards[1].querySelector('.label').textContent = '今日收入';
  const v1 = cards[1].querySelector('.value'); v1.id = 'sellerTodayIncome'; v1.textContent = '0 BNB'; v1.className = 'value text-income';
  const t1 = cards[1].querySelector('.trend'); t1.id = 'sellerTodayIncomeTrend'; t1.textContent = ' '; t1.className = 'trend';
  cards[2].querySelector('.label').textContent = '今日成交';
  const v2 = cards[2].querySelector('.value'); v2.id = 'sellerTodayOrders'; v2.textContent = '0'; v2.className = 'value';
  const t2 = cards[2].querySelector('.trend'); t2.id = 'sellerTodayOrdersTrend'; t2.textContent = ' '; t2.className = 'trend';
  cards[3].querySelector('.label').textContent = '累计收入';
  const v3 = cards[3].querySelector('.value'); v3.id = 'sellerTotalIncome'; v3.textContent = '0 BNB'; v3.className = 'value text-purple';
  const t3 = cards[3].querySelector('.trend'); t3.id = 'sellerTotalIncomeTrend'; t3.textContent = '--'; t3.className = 'trend text-muted';
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
    val.className = 'value';
    const trend = cards[i].querySelector('.trend');
    trend.id = labels[i].trendId;
    trend.className = 'trend';
  }
  App.refreshLucide();
  applyMarketMetrics();
}

function showBuyerMetrics() {
  const cards = document.querySelectorAll('.metrics .metric-card');
  if (cards.length < 4) return;
  if (!App.currentAccount) {
    cards[0].querySelector('.label').innerHTML = '<i data-lucide="wallet" class="icon-inline"></i> 我的余额';
    const v0 = cards[0].querySelector('.value'); v0.id = 'buyerBalance'; v0.textContent = '未连接'; v0.className = 'value text-muted';
    const t0 = cards[0].querySelector('.trend'); t0.id = 'buyerBalanceTrend'; t0.textContent = ' '; t0.className = 'trend';
    cards[1].querySelector('.label').innerHTML = '<i data-lucide="clipboard-list" class="icon-inline"></i> 我的订单';
    const v1 = cards[1].querySelector('.value'); v1.id = 'buyerOrders'; v1.textContent = '--'; v1.className = 'value text-muted';
    const t1 = cards[1].querySelector('.trend'); t1.id = 'buyerOrdersTrend'; t1.textContent = ' '; t1.className = 'trend';
    cards[2].querySelector('.label').innerHTML = '<i data-lucide="coins" class="icon-inline"></i> 总消费';
    const v2 = cards[2].querySelector('.value'); v2.id = 'buyerTotalSpent'; v2.textContent = '--'; v2.className = 'value text-muted';
    const t2 = cards[2].querySelector('.trend'); t2.id = 'buyerTotalSpentTrend'; t2.textContent = '--'; t2.className = 'trend text-muted';
    cards[3].querySelector('.label').innerHTML = '<i data-lucide="package" class="icon-inline"></i> 已购订单';
    const v3 = cards[3].querySelector('.value'); v3.id = 'buyerServices'; v3.textContent = '--'; v3.className = 'value text-muted';
    const t3 = cards[3].querySelector('.trend'); t3.id = 'buyerServicesTrend'; t3.textContent = '--'; t3.className = 'trend text-muted';
    App.refreshLucide();
    return;
  }
  cards[0].querySelector('.label').innerHTML = '<i data-lucide="wallet" class="icon-inline"></i> 我的余额';
  const v0 = cards[0].querySelector('.value'); v0.id = 'buyerBalance'; v0.textContent = '-- BNB'; v0.className = 'value text-up';
  const t0 = cards[0].querySelector('.trend'); t0.id = 'buyerBalanceTrend'; t0.textContent = ' '; t0.className = 'trend';
  cards[1].querySelector('.label').innerHTML = '<i data-lucide="clipboard-list" class="icon-inline"></i> 已下单';
  const v1 = cards[1].querySelector('.value'); v1.id = 'buyerOrders'; v1.textContent = '0'; v1.className = 'value';
  const t1 = cards[1].querySelector('.trend'); t1.id = 'buyerOrdersTrend'; t1.textContent = ' '; t1.className = 'trend';
  cards[2].querySelector('.label').innerHTML = '<i data-lucide="coins" class="icon-inline"></i> 总支出';
  const v2 = cards[2].querySelector('.value'); v2.id = 'buyerTotalSpent'; v2.textContent = '0 BNB'; v2.className = 'value text-expense';
  const t2 = cards[2].querySelector('.trend'); t2.id = 'buyerTotalSpentTrend'; t2.textContent = '--'; t2.className = 'trend text-muted';
  cards[3].querySelector('.label').innerHTML = '<i data-lucide="package" class="icon-inline"></i> 收到的币';
  const v3 = cards[3].querySelector('.value'); v3.id = 'buyerReceived'; v3.textContent = '0'; v3.className = 'value text-up';
  const t3 = cards[3].querySelector('.trend'); t3.id = 'buyerReceivedTrend'; t3.textContent = '--'; t3.className = 'trend text-muted';
  App.refreshLucide();
}

function showTab(tab) {
  document.querySelectorAll('.nav span').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('[id^="panel-"]').forEach(p => {
    p.classList.add('panel-hidden');
    p.classList.remove('pre-show');
    p.style.display = '';
  });
  document.getElementById('myAgent').classList.add('hidden');
  document.getElementById('myAgent').classList.remove('pre-show');
  document.getElementById('myAgent').style.display = '';
  document.getElementById('txPanel').classList.add('hidden');
  document.getElementById('txPanel').style.display = '';
  document.querySelector('.main').classList.add('hidden');
  document.querySelector('.main').classList.remove('pre-show-grid');
  document.querySelector('.main').style.display = '';
  const metricsDiv = document.querySelector('.metrics');
  if (metricsDiv) {
    metricsDiv.classList.add('hidden');
    metricsDiv.classList.remove('pre-show-grid');
    metricsDiv.style.display = '';
  }

  if (tab === 'market') {
    document.querySelector('.nav span:nth-child(1)').classList.add('active');
    document.querySelector('.main').classList.remove('hidden');
    document.querySelector('.main').style.display = 'grid';
    document.getElementById('panel-market').classList.remove('panel-hidden');
    document.getElementById('panel-market').style.display = 'flex';
    document.getElementById('txPanel').classList.remove('hidden');
    document.getElementById('txPanel').style.display = 'flex';
    if (metricsDiv) {
      metricsDiv.classList.remove('hidden');
      metricsDiv.style.display = 'grid';
    }
    App.activeTab = 'market';
    showMarketMetrics();
    reloadMarket();
    loadTxsFeed();
    startTxsStream();
  } else if (tab === 'register') {
    document.querySelector('.nav span:nth-child(2)').classList.add('active');
    document.getElementById('panel-register').classList.remove('panel-hidden');
    document.getElementById('panel-register').style.display = 'block';
    document.querySelector('.main').classList.add('hidden');
    // metrics 显示由 loadSellerData 决定，先隐藏
    if (metricsDiv) {
      metricsDiv.classList.add('hidden');
    }
    App.activeTab = 'register';
    showSellerMetrics();
    loadSellerData();
  } else if (tab === 'myagent') {
    document.querySelector('.nav span:nth-child(3)').classList.add('active');
    document.getElementById('myAgent').classList.remove('hidden');
    document.getElementById('myAgent').style.display = 'block';
    document.querySelector('.main').classList.add('hidden');
    if (metricsDiv) {
      metricsDiv.classList.remove('hidden');
      metricsDiv.style.display = 'grid';
    }
    App.activeTab = 'myagent';
    showBuyerMetrics();

    // 根据钱包连接状态显示对应内容
    if (App.currentAccount) {
      document.getElementById('myAgentLoading').classList.add('hidden');
      document.getElementById('myAgentPrompt').style.display = 'none';
      document.getElementById('myAgentContent').style.display = 'block';
      document.getElementById('myAddr').textContent = App.currentAccount;
    } else {
      document.getElementById('myAgentLoading').classList.add('hidden');
      document.getElementById('myAgentPrompt').style.display = 'block';
      document.getElementById('myAgentContent').style.display = 'none';
    }

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
    document.querySelector('.main').classList.add('hidden');
    if (metricsDiv) metricsDiv.classList.add('hidden');
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
  } else {
    // 默认显示 market tab
    showTab('market');
  }
}

window.showTab = showTab;
window.restoreTab = restoreTab;
window.showBuyerMetrics = showBuyerMetrics;
window.showSellerMetrics = showSellerMetrics;
window.showMarketMetrics = showMarketMetrics;
window.initMetricsBackup = initMetricsBackup;
