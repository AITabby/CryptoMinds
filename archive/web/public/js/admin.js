// CryptoMinds — Admin Module
// Functions: loadPendingServices, approveService, rejectService

(function () {
  'use strict';

  async function loadPendingServices() {
    if (!App.currentAccount) return;
    try {
      const res = await fetch(`/api/admin/pending?wallet=${App.currentAccount}`);
      const data = await res.json();
      if (!data.ok) {
        document.getElementById('pendingList').innerHTML = `<div style="color:#ef4444;">${data.error}</div>`;
        return;
      }
      if (data.pending.length === 0) {
        document.getElementById('pendingList').innerHTML = '<div style="color:#475569;text-align:center;padding:20px;"><i data-lucide="check-circle" class="icon-inline"></i> 暂无待审核卖家</div>';
        return;
      }
      document.getElementById('pendingList').innerHTML = data.pending.map(s => {
        const time = new Date(s.registeredAt).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai'});
        return `<div style="background:#0f121e;border:1px solid rgba(139,92,246,0.1);border-radius:10px;padding:16px;margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <div>
              <span style="color:#a78bfa;font-weight:600;font-size:15px;">${s.expert}</span>
              <span style="color:#64748b;margin:0 6px;">→</span>
              <span style="color:#e2e8f0;font-size:14px;">${s.name}</span>
            </div>
            <span style="color:#475569;font-size:11px;">${time}</span>
          </div>
          <div style="color:#94a3b8;font-size:12px;margin-bottom:8px;">${s.desc || '无描述'}</div>
          <div style="display:flex;gap:16px;font-size:12px;color:#64748b;margin-bottom:12px;">
            <span><i data-lucide="coins" class="icon-inline"></i> ${s.price} BNB</span>
            <span><i data-lucide="download" class="icon-inline"></i> ${s.inputFormat}</span>
            <span><i data-lucide="upload" class="icon-inline"></i> ${s.outputFormat}</span>
            <span><i data-lucide="timer" class="icon-inline"></i> ${s.latency || '-'}</span>
          </div>
          <div style="color:#475569;font-size:11px;margin-bottom:10px;">钱包: ${s.wallet}</div>
          <div style="display:flex;gap:8px;">
            <button onclick="approveService('${s.id}')" style="background:#059669;color:#fff;border:none;padding:6px 16px;border-radius:6px;cursor:pointer;font-size:12px;font-weight:600;"><i data-lucide="check-circle" class="icon-inline"></i> 通过</button>
            <button onclick="rejectService('${s.id}')" style="background:#dc2626;color:#fff;border:none;padding:6px 16px;border-radius:6px;cursor:pointer;font-size:12px;font-weight:600;"><i data-lucide="x-circle" class="icon-inline"></i> 拒绝</button>
          </div>
        </div>`;
      }).join('');
    } catch(e) {
      document.getElementById('pendingList').innerHTML = `<div style="color:#ef4444;">加载失败</div>`;
    }
  }

  async function approveService(id) {
    try {
      const res = await fetch(`/api/admin/approve/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ wallet: App.currentAccount })
      });
      const data = await res.json();
      if (data.ok) { loadPendingServices(); } else { alert(data.error); }
    } catch(e) { alert('操作失败'); }
  }

  async function rejectService(id) {
    const reason = prompt('拒绝原因：') || '';
    try {
      const res = await fetch(`/api/admin/reject/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ wallet: App.currentAccount, reason })
      });
      const data = await res.json();
      if (data.ok) { loadPendingServices(); } else { alert(data.error); }
    } catch(e) { alert('操作失败'); }
  }

  // Expose via window
  window.loadPendingServices = loadPendingServices;
  window.approveService = approveService;
  window.rejectService = rejectService;
})();