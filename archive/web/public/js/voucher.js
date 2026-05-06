// CryptoMinds — Voucher Module
// Constants: VOUCHER_STATE_LABELS
// Functions: loadVouchers

(function () {
  'use strict';

  const VOUCHER_STATE_LABELS = {
    'ISSUED': '已发行', 'ACTIVE': '已激活', 'USED': '使用中',
    'EXHAUSTED': '已耗尽', 'EXPIRED': '已过期', 'DISPUTED': '争议中',
    'RESOLVED': '已仲裁'
  };

  async function loadVouchers() {
    const listEl = document.getElementById('voucherList');
    const wallet = App.currentAccount || getActiveWallet();
    if (!wallet) {
      listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;">请先连接钱包</div>';
      return;
    }
    listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;">加载中...</div>';
    try {
      const res = await fetch('/api/v1/protocol/voucher/agent/' + encodeURIComponent(wallet));
      const data = await res.json();
      const vouchers = data.vouchers || [];
      if (vouchers.length === 0) {
        listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;">暂无 Voucher</div>';
        return;
      }
      listEl.innerHTML = vouchers.map(v => {
        const vchId = v.voucher_id || v.voucherId || '--';
        const state = v.state || 'ISSUED';
        const stateLabel = VOUCHER_STATE_LABELS[state] || state;
        const stateColor = state === 'EXHAUSTED' ? '#34d399' : state === 'ACTIVE' ? '#a78bfa' : state === 'DISPUTED' ? '#fbbf24' : '#64748b';
        const usedPercent = v.total_units ? ((v.units_used || 0) / v.total_units * 100).toFixed(1) : 0;

        // Voucher state progression
        const VCH_STATES = ['ISSUED','ACTIVE','USED','EXHAUSTED'];
        const vchStateIdx = VCH_STATES.indexOf(state);
        const progressHtml = VCH_STATES.map((s, i) => {
          const done = i <= vchStateIdx && vchStateIdx >= 0;
          const current = i === vchStateIdx;
          const color = done ? '#34d399' : '#334155';
          const label = VOUCHER_STATE_LABELS[s];
          return `<div style="display:flex;align-items:center;gap:2px;">
            <div style="width:8px;height:8px;border-radius:50%;background:${current ? '#fbbf24' : color};border:${current ? '2px solid #fbbf24' : done ? 'none' : '1px solid #475569'};"></div>
            <span style="font-size:10px;color:${done ? '#e2e8f0' : '#475569'};">${label}</span>
            ${i < 3 ? '<div style="width:12px;height:1px;background:' + (done ? '#34d399' : '#334155') + ';"></div>' : ''}
          </div>`;
        }).join('');

        // Read-only: no manual action buttons, Agent operates autonomously

        return `<div style="background:#0f121e;border:1px solid rgba(139,92,246,0.15);border-radius:10px;padding:16px;margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <div style="color:#a78bfa;font-weight:600;font-size:13px;font-family:monospace;">${vchId}</div>
            <div style="background:rgba(${state === 'EXHAUSTED' ? '34,211,153' : state === 'ACTIVE' ? '139,92,246' : '100,116,139'},0.15);color:${stateColor};font-size:11px;padding:3px 8px;border-radius:4px;font-weight:600;">${stateLabel}</div>
          </div>
          <div style="display:flex;gap:2px;margin-bottom:10px;overflow:hidden;">${progressHtml}</div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;font-size:12px;color:#94a3b8;">
            <div>服务: <span style="color:#e2e8f0;">${v.service_type || '--'}</span></div>
            <div>卖家: <span style="color:#e2e8f0;">${v.seller_agent_id || '--'}</span></div>
            <div>单价: <span style="color:#fbbf24;">${v.price_per_unit || '--'} BNB</span></div>
            <div>已用: <span style="color:#e2e8f0;">${v.units_used || 0}/${v.total_units || 0} (${usedPercent}%)</span></div>
            <div>链: <span style="color:#e2e8f0;">${v.chain || '--'}</span></div>
            <div>总价: <span style="color:#fbbf24;">${((v.total_units || 0) * parseFloat(v.price_per_unit || 0)).toFixed(4)} BNB</span></div>
          </div>
        </div>`;
      }).join('');
    } catch (e) {
      listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#f87171;">加载失败: ' + e.message + '</div>';
    }
  }

  // Expose via window
  window.VOUCHER_STATE_LABELS = VOUCHER_STATE_LABELS;
  window.loadVouchers = loadVouchers;
})();