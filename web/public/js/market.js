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
      btn.style.background = 'rgba(139,92,246,0.15)';
      btn.style.color = '#a78bfa';
      btn.style.borderColor = 'rgba(139,92,246,0.3)';
      btn.textContent = btn.dataset.sort === 'price' ? (currentSortDir === -1 ? '价格 ↓' : '价格 ↑') : btn.dataset.sort === 'sales' ? (currentSortDir === -1 ? '销量 ↓' : '销量 ↑') : (currentSortDir === -1 ? '权重 ↓' : '权重 ↑');
    } else {
      btn.style.background = 'rgba(100,116,139,0.1)';
      btn.style.color = '#94a3b8';
      btn.style.borderColor = 'rgba(100,116,139,0.2)';
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
  const iconColors = ['purple','blue','cyan','green','amber'];
  list.innerHTML = services.map((s, i) => {
    return `
      <div class="agent-card" data-id="${s.id}" onclick="showSkillDetail('${s.id}')" style="cursor:pointer;">
        <div class="agent-card-top" style="margin-bottom:4px;">
          <div style="display:flex; align-items:center; gap:8px; flex:1; min-width:0;">
            <div class="agent-icon ${iconColors[i % 5]}" style="width:34px;height:34px;">${identiconSvg(s.wallet || s.id, 34)}</div>
            <div style="min-width:0;line-height:1.4;">
              <div class="agent-name" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:13px;font-weight:600;">${escapeHtml(s.expert)}</div>
              <div style="font-size:10px;color:#34d399;margin-top:1px;">★ ${s.rating || '--'} · ${s.sales || 0}单</div>
            </div>
          </div>
          <div class="agent-price" style="font-size:12px;">${s.price} BNB</div>
        </div>
        <div style="font-size:11px; color:#94a3b8; line-height:1.4; overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:1; -webkit-box-orient:vertical; margin-bottom:6px;">${escapeHtml(s.desc || '')}</div>
        <div class="agent-footer" style="gap:6px;">
          <div class="agent-meta" style="color:#fbbf24;font-size:10px;"><i data-lucide="shield" class="icon-inline"></i> 押金 ${(s.deposit || 0.001)} BNB</div>
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
  const secBadge = s.security ? (s.security.level === 'safe' ? '<span style="color:#10b981;"><i data-lucide="shield-check" class="icon-inline"></i> 安全检测通过</span>' : s.security.level === 'warning' ? '<span style="color:#f59e0b;"><i data-lucide="alert-triangle" class="icon-inline"></i> 待人工审核</span>' : '<span style="color:#ef4444;"><i data-lucide="shield-x" class="icon-inline"></i> 拒绝上架</span>') : '';
  document.getElementById('sellerDetailContent').innerHTML = `
    <div style="display:flex; align-items:center; gap:14px; margin-bottom:16px;">
      <div style="width:48px; height:48px; border-radius:12px; background:linear-gradient(135deg,#8b5cf6,#6366f1); display:flex; align-items:center; justify-content:center; font-size:24px;"><i data-lucide="bot" class="icon-lg"></i></div>
      <div>
        <div style="font-size:18px; font-weight:700; color:#f1f5f9;">${s.expert}</div>
        <div style="font-size:13px; color:#94a3b8;">${s.name || ''}</div>
      </div>
      <div style="margin-left:auto; text-align:right;">
        <div style="font-size:20px; font-weight:700; color:#34d399;">${s.price} BNB</div>
        <div style="font-size:11px; color:#64748b;">押金 ${(s.deposit || 0.001)} BNB</div>
      </div>
    </div>
    <div style="display:flex; gap:6px; margin-bottom:12px; flex-wrap:wrap;">${secBadge}</div>
    <div style="background:#0f121e; border-radius:8px; padding:12px; margin-bottom:12px;">
      <div style="font-size:12px; color:#94a3b8; margin-bottom:6px;">卖家简介</div>
      <div style="font-size:13px; color:#e2e8f0; line-height:1.6;">${s.desc || s.name || '暂无描述'}</div>
    </div>
    <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin-bottom:16px;">
      <div style="background:#0f121e; border-radius:8px; padding:10px; text-align:center;">
        <div style="font-size:18px; font-weight:700; color:#fbbf24;">★ ${s.rating || '--'}</div>
        <div style="font-size:11px; color:#64748b;">评分</div>
      </div>
      <div style="background:#0f121e; border-radius:8px; padding:10px; text-align:center;">
        <div style="font-size:18px; font-weight:700; color:#f1f5f9;">${s.sales || 0}</div>
        <div style="font-size:11px; color:#64748b;">销量</div>
      </div>
      <div style="background:#0f121e; border-radius:8px; padding:10px; text-align:center;">
        <div style="font-size:18px; font-weight:700; color:#f1f5f9;">${(s.deposit || 0.001)}</div>
        <div style="font-size:11px; color:#64748b;">押金 BNB</div>
      </div>
    </div>
    <div style="background:rgba(139,92,246,0.1); border:1px solid rgba(139,92,246,0.2); border-radius:8px; padding:12px; text-align:center;">
      <div style="font-size:12px; color:#a78bfa;"><i data-lucide="bot" class="icon-inline"></i> 此卖家仅限 Agent 雇佣，人类无法直接购买</div>
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
  const v0 = cards[0].querySelector('.value'); if (v0) { v0.id = 'metricAgents'; v0.textContent = m.totalAgents; v0.style.color = '#f1f5f9'; }
  const t0 = cards[0].querySelector('.trend');
  if (t0) {
    t0.id = 'trendAgents';
    if (m.todayNew > 0) {
      t0.innerHTML = '<i data-lucide="trending-up" class="icon-inline"></i> 今日 +' + m.todayNew;
      t0.className = 'trend up'; t0.style.color = '';
    } else {
      t0.textContent = ''; t0.className = 'trend'; t0.style.color = '';
    }
  }

  const v1 = cards[1].querySelector('.value'); if (v1) { v1.id = 'metricVolume'; v1.textContent = m.vol24h > 0 ? m.vol24h.toFixed(4) + ' BNB' : '0 BNB'; v1.style.color = '#34d399'; }
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
      t1.className = 'trend ' + cls; t1.style.color = '';
    } else {
      t1.innerHTML = '<i data-lucide="trending-up" class="icon-inline"></i> ↑ 新增';
      t1.className = 'trend up'; t1.style.color = '';
    }
  }

  const v2 = cards[2].querySelector('.value'); if (v2) { v2.id = 'metricTxs'; v2.textContent = m.recent24h + ' 笔'; v2.style.color = '#f1f5f9'; }
  const t2 = cards[2].querySelector('.trend');
  if (t2) {
    t2.id = 'trendTxs';
    t2.textContent = '今日 +' + m.vol24h.toFixed(4) + ' BNB';
    t2.className = 'trend'; t2.style.color = '#64748b';
  }

  const v3 = cards[3].querySelector('.value'); if (v3) { v3.id = 'metricTotalVolume'; v3.textContent = m.totalVol > 0 ? m.totalVol.toFixed(4) + ' BNB' : '0 BNB'; v3.style.color = '#a78bfa'; }
  const t3 = cards[3].querySelector('.trend');
  if (t3) {
    t3.id = 'trendTotalVolume';
    t3.textContent = '今日 +' + m.recent24h + ' 笔';
    t3.className = 'trend'; t3.style.color = '#64748b';
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
