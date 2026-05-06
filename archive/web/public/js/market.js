// CryptoMinds Market Module
// Market loading, rendering, sorting, metrics, skill detail

let currentSort = 'weight';
let currentSortDir = -1;
let cachedMarketMetrics = null;

function bootstrapServices(services) {
  App.marketServices.clear();
  services.forEach(service => {
    App.marketServices.set(service.id, service);
  });
}

function getServiceById(serviceId) {
  return App.marketServices.get(serviceId);
}

function isMyAgent(item) {
  return myAgentNames.has(item.from) || myAgentNames.has(item.to) || myAgentNames.has(item.agent);
}

function sortMarket(key) {
  if (currentSort === key) { currentSortDir *= -1; }
  else { currentSort = key; currentSortDir = -1; }
  document.querySelectorAll('.sort-btn').forEach(btn => {
    if (btn.dataset.sort === key) {
      btn.classList.add('active');
      btn.textContent = btn.dataset.sort === 'price' ? (currentSortDir === -1 ? '价格 ↓' : '价格 ↑') : btn.dataset.sort === 'sales' ? (currentSortDir === -1 ? '销量 ↓' : '销量 ↑') : (currentSortDir === -1 ? '权重 ↓' : '权重 ↑');
    } else {
      btn.classList.remove('active');
      btn.textContent = btn.dataset.sort === 'price' ? '价格' : btn.dataset.sort === 'sales' ? '销量' : '权重';
    }
  });
  applyMarketFilter();
}

function applyMarketFilter() {
  const query = (document.getElementById('marketSearch')?.value || '').toLowerCase().trim();
  const services = Array.from(App.marketServices.values());
  let filtered = query ? services.filter(s =>
    (s.expert || '').toLowerCase().includes(query) ||
    (s.name || '').toLowerCase().includes(query) ||
    (s.desc || '').toLowerCase().includes(query) ||
    (s.inputFormat || '').toLowerCase().includes(query)
  ) : services;
  filtered.sort((a, b) => {
    if (currentSort === 'weight') {
      const wa = (a.deposit || 0.001) * (a.sales || 0) * (a.rating || 1);
      const wb = (b.deposit || 0.001) * (b.sales || 0) * (b.rating || 1);
      return (wa - wb) * currentSortDir;
    }
    let va = a[currentSort] || 0, vb = b[currentSort] || 0;
    if (currentSort === 'price') { va = Number(va); vb = Number(vb); }
    return (va - vb) * currentSortDir;
  });
  renderMarketCards(filtered);
}

function renderMarketCards(services) {
  const list = document.getElementById('sellersList');
  const iconColors = ['yellow','green','red','blue','gray'];
  list.innerHTML = services.map((s, i) => {
    return `
      <div class="agent-card" data-id="${s.id}" onclick="showSkillDetail('${s.id}')">
        <div class="agent-card-top">
          <div style="display:flex; align-items:center; gap:8px; flex:1; min-width:0;">
            <div class="agent-icon ${iconColors[i % 5]}">${identiconSvg(s.wallet || s.id, 34)}</div>
            <div style="min-width:0;line-height:1.4;">
              <div class="agent-name">${escapeHtml(s.expert)}</div>
              <div class="text-up" style="font-size:10px;margin-top:1px;">★ ${s.rating || '--'} · ${s.sales || 0}单</div>
            </div>
          </div>
          <div class="agent-price">${s.price} BNB</div>
        </div>
        <div class="agent-desc">${escapeHtml(s.desc || '')}</div>
        <div class="agent-footer">
          <div class="agent-meta text-primary" style="font-size:10px;"><i data-lucide="shield" class="icon-inline"></i> 押金 ${(s.deposit || 0.001)} BNB</div>
        </div>
      </div>
    `;}).join('');
  App.refreshLucide();
}

async function reloadMarket() {
  const tabSnapshot = App.activeTab;
  try {
    const res = await fetch('/api/v1/sellers');
    const data = await res.json();
    if (tabSnapshot !== App.activeTab) return;
    const sellers = data.sellers || [];
    const services = sellers.map(s => ({
      id: s.wallet,
      expert: s.name,
      name: s.name,
      desc: s.desc || '',
      price: s.feeRate || 0,
      deposit: s.deposit || 0.1,
      rating: s.rating || 0,
      sales: s.totalOrders || 0,
      wallet: s.wallet,
      active: true,
    }));
    bootstrapServices(services);
    applyMarketFilter();
  } catch(e) { console.error('reloadMarket error:', e); }
}

function showSkillDetail(serviceId) {
  const services = Array.from(App.marketServices.values());
  const s = services.find(x => x.id === serviceId);
  if (!s) return;
  const secBadge = s.security ? (s.security.level === 'safe' ? '<span class="text-up"><i data-lucide="shield-check" class="icon-inline"></i> 安全检测通过</span>' : s.security.level === 'warning' ? '<span class="text-primary"><i data-lucide="alert-triangle" class="icon-inline"></i> 待人工审核</span>' : '<span class="text-down"><i data-lucide="shield-x" class="icon-inline"></i> 拒绝上架</span>') : '';
  document.getElementById('sellerDetailContent').innerHTML = `
    <div class="flex-center" style="gap:14px;margin-bottom:16px;">
      <div class="agent-icon yellow" style="width:48px;height:48px;border-radius:12px;font-size:24px;"><i data-lucide="bot" class="icon-lg"></i></div>
      <div>
        <div class="text-bright" style="font-size:18px;font-weight:700;">${s.expert}</div>
        <div class="text-muted-strong" style="font-size:13px;">${s.name || ''}</div>
      </div>
      <div style="margin-left:auto;text-align:right;">
        <div class="text-up" style="font-size:20px;font-weight:700;">${s.price} BNB</div>
        <div class="text-muted" style="font-size:11px;">押金 ${(s.deposit || 0.001)} BNB</div>
      </div>
    </div>
    <div style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap;">${secBadge}</div>
    <div class="bg-canvas rounded-lg" style="padding:12px;margin-bottom:12px;">
      <div class="text-muted-strong" style="font-size:12px;margin-bottom:6px;">卖家简介</div>
      <div class="text-body" style="font-size:13px;line-height:1.6;">${s.desc || s.name || '暂无描述'}</div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:16px;">
      <div class="bg-canvas rounded-lg text-center" style="padding:10px;">
        <div class="text-primary font-number" style="font-size:18px;font-weight:700;">★ ${s.rating || '--'}</div>
        <div class="text-muted" style="font-size:11px;">评分</div>
      </div>
      <div class="bg-canvas rounded-lg text-center" style="padding:10px;">
        <div class="text-bright font-number" style="font-size:18px;font-weight:700;">${s.sales || 0}</div>
        <div class="text-muted" style="font-size:11px;">销量</div>
      </div>
      <div class="bg-canvas rounded-lg text-center" style="padding:10px;">
        <div class="text-bright font-number" style="font-size:18px;font-weight:700;">${(s.deposit || 0.001)}</div>
        <div class="text-muted" style="font-size:11px;">押金 BNB</div>
      </div>
    </div>
    <div class="bg-primary-tint border-primary rounded-lg text-center" style="padding:12px;">
      <div class="text-primary" style="font-size:12px;"><i data-lucide="bot" class="icon-inline"></i> 此卖家仅限 Agent 雇佣，人类无法直接购买</div>
    </div>
  `;
  document.getElementById('sellerDetailModal').style.display = 'block';
  App.refreshLucide();
}

function closeSellerDetail() {
  document.getElementById('sellerDetailModal').style.display = 'none';
}

function showSmartRoute(serviceId) {
  const service = getServiceById(serviceId);
  if (!service) return;
  executePayment(serviceId, {});
}

function updateMetrics(transactions, services) {
  const now = Date.now();
  const h24 = 24 * 60 * 60 * 1000;
  const totalAgents = [...new Set((services || []).map(s => s.expert).filter(Boolean))].length;
  const todayNew = (services || []).filter(s => {
    if (!s.registeredAt) return false;
    return (now - new Date(s.registeredAt).getTime()) < h24;
  }).length;

  fetch('/api/v1/purchases').then(r => r.json()).then(purchases => {
    const allOrders = purchases.filter(p => p.status === 'completed' || p.status === 'delivered');
    const recent24h = allOrders.filter(p => {
      const t = new Date(p.time).getTime();
      return !isNaN(t) && (now - t) < h24;
    });
    const prev24h = allOrders.filter(p => {
      const t = new Date(p.time).getTime();
      return !isNaN(t) && (now - t) >= h24 && (now - t) < 2 * h24;
    });
    const vol24h = recent24h.reduce((sum, p) => sum + (parseFloat(p.price) || 0), 0);
    const volPrev24h = prev24h.reduce((sum, p) => sum + (parseFloat(p.price) || 0), 0);
    const totalVol = allOrders.reduce((sum, p) => sum + (parseFloat(p.price) || 0), 0);
    cachedMarketMetrics = { totalAgents, todayNew, vol24h, volPrev24h, recent24h: recent24h.length, prev24h: prev24h.length, totalVol, totalOrders: allOrders.length };
    if (App.activeTab !== 'market') return;
    applyMarketMetrics();
  }).catch(() => {});
}

async function applyMarketMetrics() {
  if (!cachedMarketMetrics) return;
  if (App.activeTab !== 'market') return;
  const m = cachedMarketMetrics;
  const cards = document.querySelectorAll('.metrics .metric-card');
  if (cards.length < 4) return;

  try {
    const sRes = await fetch('/api/v1/sellers');
    const sData = await sRes.json();
    m.totalAgents = (sData.sellers || []).length;
  } catch(e) {}
  const v0 = cards[0].querySelector('.value'); if (v0) { v0.id = 'metricAgents'; v0.textContent = m.totalAgents; }
  const t0 = cards[0].querySelector('.trend');
  if (t0) {
    t0.id = 'trendAgents';
    if (m.todayNew > 0) {
      t0.innerHTML = '<i data-lucide="trending-up" class="icon-inline"></i> 今日 +' + m.todayNew;
      t0.className = 'trend up';
    } else {
      t0.textContent = ''; t0.className = 'trend';
    }
  }

  const v1 = cards[1].querySelector('.value'); if (v1) { v1.id = 'metricVolume'; v1.textContent = m.vol24h > 0 ? m.vol24h.toFixed(4) + ' BNB' : '0 BNB'; v1.className = 'value text-up'; }
  const t1 = cards[1].querySelector('.trend');
  if (t1) {
    t1.id = 'trendVolume';
    let pctVol;
    if (m.volPrev24h > 0) {
      pctVol = ((m.vol24h - m.volPrev24h) / m.volPrev24h * 100).toFixed(1);
    } else {
      pctVol = m.vol24h > 0 ? null : '0';
    }
    if (pctVol !== null) {
      const numPct = parseFloat(pctVol);
      const arrow = numPct > 0 ? 'trending-up' : numPct < 0 ? 'trending-down' : 'minus';
      const cls = numPct > 0 ? 'up' : numPct < 0 ? 'down' : '';
      const sign = numPct > 0 ? '+' : '';
      t1.innerHTML = '<i data-lucide="' + arrow + '" class="icon-inline"></i> ' + sign + pctVol + '%';
      t1.className = 'trend ' + cls;
    } else {
      t1.innerHTML = '<i data-lucide="trending-up" class="icon-inline"></i> ↑ 新增';
      t1.className = 'trend up';
    }
  }

  const v2 = cards[2].querySelector('.value'); if (v2) { v2.id = 'metricTxs'; v2.textContent = m.recent24h + ' 笔'; }
  const t2 = cards[2].querySelector('.trend');
  if (t2) {
    t2.id = 'trendTxs';
    t2.textContent = '今日 +' + m.vol24h.toFixed(4) + ' BNB';
    t2.className = 'trend';
  }

  const v3 = cards[3].querySelector('.value'); if (v3) { v3.id = 'metricTotalVolume'; v3.textContent = m.totalVol > 0 ? m.totalVol.toFixed(4) + ' BNB' : '0 BNB'; v3.className = 'value text-primary'; }
  const t3 = cards[3].querySelector('.trend');
  if (t3) {
    t3.id = 'trendTotalVolume';
    t3.textContent = '今日 +' + m.recent24h + ' 笔';
    t3.className = 'trend';
  }

  App.refreshLucide();
  initMetricsBackup();
}

window.bootstrapServices = bootstrapServices;
window.getServiceById = getServiceById;
window.isMyAgent = isMyAgent;
window.sortMarket = sortMarket;
window.applyMarketFilter = applyMarketFilter;
window.renderMarketCards = renderMarketCards;
window.reloadMarket = reloadMarket;
window.showSkillDetail = showSkillDetail;
window.closeSellerDetail = closeSellerDetail;
window.showSmartRoute = showSmartRoute;
function closeReport() {
  document.getElementById('reportModal').style.display = 'none';
}

window.closeReport = closeReport;
window.updateMetrics = updateMetrics;
window.applyMarketMetrics = applyMarketMetrics;
