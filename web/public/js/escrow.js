// CryptoMinds — Escrow Lifecycle Module
// Constants: ESCROW_STATE_LABELS, ESCROW_LIFECYCLE_STATES
// Functions: loadEscrowLifecycle, loadDisputedEscrows, resolveEscrow

(function () {
  'use strict';

  const ESCROW_STATE_LABELS = {
    'CREATED': '已创建', 'FUNDED': '已锁资', 'EXECUTING': '执行中',
    'DELIVERED': '已交付', 'VERIFIED': '已验证', 'RELEASED': '已释放',
    'DISPUTED': '争议中', 'RESOLVED_REFUND': '退款', 'RESOLVED_RELEASE': '仲裁释放',
    'EXPIRED': '已过期', 'REFUNDED_TIMEOUT': '超时退款'
  };

  const ESCROW_LIFECYCLE_STATES = ['CREATED','FUNDED','EXECUTING','DELIVERED','VERIFIED','RELEASED'];

  async function loadDisputedEscrows() {
    const listEl = document.getElementById('disputedEscrowList');
    listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;">加载中...</div>';
    try {
      const res = await fetch('/api/v1/protocol/escrow/disputed');
      const data = await res.json();
      if (!data.ok && !data.orders) {
        listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;">暂无争议订单</div>';
        return;
      }
      const orders = data.orders || [];
      if (orders.length === 0) {
        listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;">暂无争议订单</div>';
        return;
      }
      listEl.innerHTML = orders.map(o => {
        const escrowId = o.escrow_id || o.escrowId || '--';
        const stateLabel = ESCROW_STATE_LABELS[o.state] || o.state;
        const disputeTime = o.disputed_at ? new Date(o.disputed_at * 1000).toLocaleString('zh-CN') : '--';
        const disputeWindow = o.dispute_window_seconds ? Math.round(o.dispute_window_seconds / 3600) + 'h' : '48h';
        return `<div style="background:#0f121e;border:1px solid rgba(234,179,8,0.2);border-radius:10px;padding:16px;margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <div style="color:#fbbf24;font-weight:600;font-size:13px;">${escrowId}</div>
            <div style="background:rgba(234,179,8,0.15);color:#fbbf24;font-size:11px;padding:3px 8px;border-radius:4px;font-weight:600;">${stateLabel}</div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px;color:#94a3b8;">
            <div>买家: <span style="color:#e2e8f0;font-family:monospace;">${(o.buyer_wallet || '').slice(0,10)}...</span></div>
            <div>卖家: <span style="color:#e2e8f0;font-family:monospace;">${(o.seller_wallet || '').slice(0,10)}...</span></div>
            <div>金额: <span style="color:#fbbf24;">${o.amount || '--'} BNB</span></div>
            <div>争议时间: ${disputeTime}</div>
            <div>争议窗口: ${disputeWindow}</div>
            <div>原因: ${o.dispute_reason || '--'}</div>
            <div>买家权重: ${o.arbitration_weight_buyer || 0}</div>
            <div>卖家权重: ${o.arbitration_weight_seller || 0}</div>
          </div>
          <div style="display:flex;gap:8px;margin-top:12px;">
            <button onclick="resolveEscrow('${escrowId}','buyer_win')" style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);color:#f87171;padding:6px 12px;border-radius:6px;cursor:pointer;font-size:11px;">买家胜</button>
            <button onclick="resolveEscrow('${escrowId}','seller_win')" style="background:rgba(34,211,153,0.1);border:1px solid rgba(34,211,153,0.3);color:#34d399;padding:6px 12px;border-radius:6px;cursor:pointer;font-size:11px;">卖家胜</button>
            <button onclick="resolveEscrow('${escrowId}','split')" style="background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.3);color:#a78bfa;padding:6px 12px;border-radius:6px;cursor:pointer;font-size:11px;">分账</button>
          </div>
        </div>`;
      }).join('');
    } catch (e) {
      listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#f87171;">加载失败: ' + e.message + '</div>';
    }
  }

  async function resolveEscrow(escrowId, decision) {
    const adminSecret = prompt('输入管理员密钥 (ADMIN_SECRET):');
    if (!adminSecret) return;
    try {
      const res = await fetch(`/api/v1/protocol/escrow/${escrowId}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Secret': adminSecret },
        body: JSON.stringify({ decision })
      });
      const data = await res.json();
      if (data.ok || data.resolution) {
        alert('仲裁完成: ' + (data.resolution || decision));
        loadDisputedEscrows();
      } else {
        alert('仲裁失败: ' + (data.error || '未知错误'));
      }
    } catch (e) {
      alert('仲裁请求失败: ' + e.message);
    }
  }

  async function loadEscrowLifecycle() {
    const listEl = document.getElementById('escrowLifecycleList');
    const wallet = App.currentAccount || getActiveWallet();
    if (!wallet) {
      listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;">请先连接钱包</div>';
      return;
    }
    listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;">加载中...</div>';
    try {
      const res = await fetch('/api/v1/protocol/market/tasks');
      const data = await res.json();
      const tasks = data.tasks || [];
      if (tasks.length === 0) {
        listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;">暂无 Escrow 订单</div>';
        return;
      }
      listEl.innerHTML = tasks.map(t => {
        const escrowId = t.escrow_id || t.escrowId || '--';
        const state = t.state || 'CREATED';
        const stateLabel = ESCROW_STATE_LABELS[state] || state;
        const isLifecycle = ESCROW_LIFECYCLE_STATES.includes(state);
        const stateColor = state === 'RELEASED' ? '#34d399' : state === 'DISPUTED' ? '#fbbf24' : isLifecycle ? '#a78bfa' : '#64748b';
        const buyerShort = (t.buyer_wallet || '').slice(0,10) + '...';
        const sellerShort = (t.seller_wallet || '').slice(0,10) + '...';
        const createdAt = t.created_at ? new Date(t.created_at * 1000).toLocaleString('zh-CN') : '--';

        // State progression bar (read-only — no manual buttons)
        const stateIdx = ESCROW_LIFECYCLE_STATES.indexOf(state);
        const progressHtml = ESCROW_LIFECYCLE_STATES.map((s, i) => {
          const done = i <= stateIdx && stateIdx >= 0;
          const current = i === stateIdx;
          const color = done ? '#34d399' : '#334155';
          const label = ESCROW_STATE_LABELS[s];
          return `<div style="display:flex;align-items:center;gap:2px;">
            <div style="width:8px;height:8px;border-radius:50%;background:${current ? '#fbbf24' : color};border:${current ? '2px solid #fbbf24' : done ? 'none' : '1px solid #475569'};"></div>
            <span style="font-size:10px;color:${done ? '#e2e8f0' : '#475569'};">${label}</span>
            ${i < 5 ? '<div style="width:12px;height:1px;background:' + (done ? '#34d399' : '#334155') + ';"></div>' : ''}
          </div>`;
        }).join('');

        return `<div style="background:#0f121e;border:1px solid rgba(139,92,246,0.15);border-radius:10px;padding:16px;margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <div style="color:#a78bfa;font-weight:600;font-size:13px;font-family:monospace;">${escrowId}</div>
            <div style="background:rgba(${state === 'RELEASED' ? '34,211,153' : state === 'DISPUTED' ? '234,179,8' : '139,92,246'},0.15);color:${stateColor};font-size:11px;padding:3px 8px;border-radius:4px;font-weight:600;">${stateLabel}</div>
          </div>
          <div style="display:flex;gap:2px;margin-bottom:10px;overflow:hidden;">${progressHtml}</div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;font-size:12px;color:#94a3b8;">
            <div>买家: <span style="color:#e2e8f0;font-family:monospace;">${buyerShort}</span></div>
            <div>卖家: <span style="color:#e2e8f0;font-family:monospace;">${sellerShort}</span></div>
            <div>金额: <span style="color:#fbbf24;">${t.amount || '--'} BNB</span></div>
          </div>
        </div>`;
      }).join('');
    } catch (e) {
      listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#f87171;">加载失败: ' + e.message + '</div>';
    }
  }

  // Expose via window
  window.ESCROW_STATE_LABELS = ESCROW_STATE_LABELS;
  window.ESCROW_LIFECYCLE_STATES = ESCROW_LIFECYCLE_STATES;
  window.loadEscrowLifecycle = loadEscrowLifecycle;
  window.loadDisputedEscrows = loadDisputedEscrows;
  window.resolveEscrow = resolveEscrow;
})();