// CryptoMinds Orders & Notifications Module
// Buyer-side: toggleNotificationPanel, loadMyOrdersInNotif, loadMyOrders,
//   viewOrderResult, loadNotifications, markAllRead, loadPendingPurchases,
//   confirmPurchase, claimSellerTimeout, toggleMyOrders
// Seller-side modals: toggleSellerOrders, toggleSellerNotif

let myOrdersOpen = false;
let sellerOrdersOpen = false;
let sellerNotifOpen = false;

function toggleNotificationPanel() {
  notifPanelOpen = !notifPanelOpen;
  if (!notifPanelOpen) {
    const m = document.getElementById('notifModal');
    if (m) m.remove();
    return;
  }
  const modal = document.createElement('div');
  modal.id = 'notifModal';
  modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:99999;display:flex;justify-content:center;align-items:center;';
  modal.onclick = (e) => { if (e.target === modal) { notifPanelOpen = false; modal.remove(); } };
  modal.innerHTML = '<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);border:2px solid rgba(139,92,246,0.4);border-radius:16px;padding:28px;width:560px;max-width:90vw;max-height:80vh;display:flex;flex-direction:column;"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;"><div style="color:#a78bfa;font-weight:600;font-size:16px;"><i data-lucide="bell" class="icon-inline"></i> 我的订单</div><button onclick="notifPanelOpen=false;document.getElementById(\'notifModal\').remove()" style="background:none;border:none;color:#94a3b8;font-size:20px;cursor:pointer;">✕</button></div><div id="ordersList" style="color:#94a3b8;font-size:13px;overflow-y:auto;flex:1;">加载中...</div></div>';
  document.body.appendChild(modal);
  App.refreshLucide();
  loadMyOrdersInNotif();
  if (App.currentAccount) {
    fetch('/api/v1/notifications/read-all', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ wallet: App.currentAccount }) }).then(() => {
      const el = document.getElementById('myUnread'); if (el) el.textContent = '0';
      const badge = document.getElementById('notifBadge'); if (badge) badge.style.display = 'none';
    });
  }
}
let notifPanelOpen = false;

async function loadMyOrdersInNotif() {
  if (!App.currentAccount) return;
  const list = document.getElementById('ordersList');
  if (!list) return;
  list.innerHTML = '加载中...';
  try {
    const res = await fetch('/api/my-orders?wallet=' + App.currentAccount);
    const data = await res.json();
    if (!data.ok) { list.innerHTML = '<div style="color:#ef4444;text-align:center;padding:20px;">加载失败</div>'; return; }
    if (data.orders.length === 0) {
      list.innerHTML = '<div style="color:#475569;text-align:center;padding:20px;">暂无订单</div>';
      return;
    }
    list.innerHTML = data.orders.map(o => {
      const time = new Date(o.time).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai'});
      let statusText = '', statusColor = '';
      if (o.status === 'pending') { statusText = '<i data-lucide="clock" class="icon-inline"></i> 待卖家交付'; statusColor = '#fbbf24'; }
      else if (o.status === 'executing') { statusText = '<i data-lucide="loader" class="icon-inline" style="animation:spin 1s linear infinite"></i> 卖家执行中'; statusColor = '#8b5cf6'; }
      else if (o.status === 'delivered') { statusText = '<i data-lucide="check-circle" class="icon-inline"></i> 待确认收货'; statusColor = '#34d399'; }
      else if (o.status === 'seller_timeout') { statusText = '<i data-lucide="alert-triangle" class="icon-inline"></i> 卖家超时'; statusColor = '#ef4444'; }
      else if (o.status === 'refunded') { statusText = '<i data-lucide="rotate-ccw" class="icon-inline"></i> 已退款'; statusColor = '#60a5fa'; }
      else if (o.status === 'confirmed') { statusText = '<i data-lucide="refresh-cw" class="icon-inline"></i> 已确认'; statusColor = '#60a5fa'; }
      else if (o.status === 'completed') { statusText = '<i data-lucide="check-circle" class="icon-inline"></i> 已完成'; statusColor = '#34d399'; }
      else { statusText = o.status; statusColor = '#94a3b8'; }
      const hasResult = o.result || o.report;
      const needConfirm = o.status === 'delivered';
      const canRefund = o.status === 'seller_timeout' && o.escrowOrderId;
      return '<div style="padding:12px 0;border-bottom:1px solid rgba(139,92,246,0.08);"><div style="display:flex;justify-content:space-between;align-items:center;"><div><div style="color:#e2e8f0;font-weight:600;">' + escapeHtml(o.sellerName || '订单') + '</div><div style="color:#64748b;font-size:11px;margin-top:4px;">卖家: ' + escapeHtml(o.expert || '未知') + ' | ' + escapeHtml(time) + '</div><div style="color:#64748b;font-size:11px;">价格: ' + o.price + ' BNB</div></div><div style="text-align:right;padding-right:4px;"><div style="color:' + statusColor + ';font-size:12px;font-weight:600;">' + statusText + '</div>' + (needConfirm ? '<button onclick="confirmPurchase(\'' + o.id + '\')" style="margin-top:6px;background:linear-gradient(135deg,#34d399,#10b981);color:#fff;border:none;border-radius:6px;padding:4px 12px;font-size:11px;cursor:pointer;">确认收货</button>' : '') + (canRefund ? '<button onclick="claimSellerTimeout(\'' + o.id + '\', \'' + o.escrowOrderId + '\')" style="margin-top:6px;background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff;border:none;border-radius:6px;padding:4px 12px;font-size:11px;cursor:pointer;">申请退款</button>' : '') + (hasResult ? '<button onclick="viewOrderResult(\'' + o.id + '\')" style="margin-top:6px;background:linear-gradient(135deg,#8b5cf6,#6366f1);color:#fff;border:none;border-radius:6px;padding:4px 12px;font-size:11px;cursor:pointer;">查看结果</button>' : '') + '</div></div></div>';
    }).join('');
    App.refreshLucide();
  } catch(e) {
    list.innerHTML = '<div style="color:#ef4444;text-align:center;padding:20px;">加载失败</div>';
  }
}

function toggleMyOrders() {
  myOrdersOpen = !myOrdersOpen;
  if (!myOrdersOpen) {
    const m = document.getElementById('myOrdersModal');
    if (m) m.remove();
    return;
  }
  const modal = document.createElement('div');
  modal.id = 'myOrdersModal';
  modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:99999;display:flex;justify-content:center;align-items:center;';
  modal.onclick = (e) => { if (e.target === modal) { myOrdersOpen = false; modal.remove(); } };
  modal.innerHTML = '<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);border:2px solid rgba(139,92,246,0.4);border-radius:16px;padding:28px;width:520px;max-width:90vw;max-height:70vh;display:flex;flex-direction:column;"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;"><div style="color:#a78bfa;font-weight:600;font-size:16px;"><i data-lucide="clipboard-list" class="icon-inline"></i> 我的订单</div><button onclick="myOrdersOpen=false;document.getElementById(\'myOrdersModal\').remove()" style="background:none;border:none;color:#94a3b8;font-size:20px;cursor:pointer;">✕</button></div><div id="myOrdersList" style="color:#94a3b8;font-size:13px;overflow-y:auto;flex:1;padding-right:8px;">加载中...</div></div>';
  document.body.appendChild(modal);
  App.refreshLucide();
  loadMyOrders();
}

async function loadMyOrders() {
  if (!App.currentAccount) return;
  try {
    const res = await fetch('/api/my-orders?wallet=' + App.currentAccount);
    const data = await res.json();
    if (!data.ok) return;
    const list = document.getElementById('myOrdersList');
    if (data.orders.length === 0) {
      list.innerHTML = '<div style="color:#475569;text-align:center;padding:20px;">暂无订单</div>';
      return;
    }
    list.innerHTML = data.orders.map(o => {
      const time = new Date(o.time).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai'});
      let statusText = '', statusColor = '';
      if (o.status === 'pending') { statusText = '<i data-lucide="clock" class="icon-inline"></i> 待卖家交付'; statusColor = '#fbbf24'; }
      else if (o.status === 'executing') { statusText = '<i data-lucide="loader" class="icon-inline" style="animation:spin 1s linear infinite"></i> 卖家执行中'; statusColor = '#8b5cf6'; }
      else if (o.status === 'delivered') { statusText = '<i data-lucide="check-circle" class="icon-inline"></i> 待确认收货'; statusColor = '#34d399'; }
      else if (o.status === 'seller_timeout') { statusText = '<i data-lucide="alert-triangle" class="icon-inline"></i> 卖家超时'; statusColor = '#ef4444'; }
      else if (o.status === 'refunded') { statusText = '<i data-lucide="rotate-ccw" class="icon-inline"></i> 已退款'; statusColor = '#60a5fa'; }
      else if (o.status === 'confirmed') { statusText = '<i data-lucide="refresh-cw" class="icon-inline"></i> 已确认'; statusColor = '#60a5fa'; }
      else if (o.status === 'completed') { statusText = '<i data-lucide="check-circle" class="icon-inline"></i> 已完成'; statusColor = '#34d399'; }
      else { statusText = o.status; statusColor = '#94a3b8'; }
      const hasResult = o.result || o.report;
      const needConfirm = o.status === 'delivered';
      const canRefund = o.status === 'seller_timeout' && o.escrowOrderId;
      return '<div style="padding:12px 0;border-bottom:1px solid rgba(139,92,246,0.08);"><div style="display:flex;justify-content:space-between;align-items:center;"><div><div style="color:#e2e8f0;font-weight:600;">' + escapeHtml(o.sellerName || '订单') + '</div><div style="color:#64748b;font-size:11px;margin-top:4px;">卖家: ' + escapeHtml(o.expert || '未知') + ' | ' + escapeHtml(time) + '</div><div style="color:#64748b;font-size:11px;">价格: ' + o.price + ' BNB</div></div><div style="text-align:right;padding-right:4px;"><div style="color:' + statusColor + ';font-size:12px;font-weight:600;">' + statusText + '</div>' + (needConfirm ? '<button onclick="confirmPurchase(\'' + o.id + '\')" style="margin-top:6px;background:linear-gradient(135deg,#34d399,#10b981);color:#fff;border:none;border-radius:6px;padding:4px 12px;font-size:11px;cursor:pointer;">确认收货</button>' : '') + (canRefund ? '<button onclick="claimSellerTimeout(\'' + o.id + '\', \'' + o.escrowOrderId + '\')" style="margin-top:6px;background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff;border:none;border-radius:6px;padding:4px 12px;font-size:11px;cursor:pointer;">申请退款</button>' : '') + (hasResult ? '<button onclick="viewOrderResult(\'' + o.id + '\')" style="margin-top:6px;background:linear-gradient(135deg,#8b5cf6,#6366f1);color:#fff;border:none;border-radius:6px;padding:4px 12px;font-size:11px;cursor:pointer;">查看结果</button>' : '') + '</div></div></div>';
    }).join('');
  } catch(e) {
    console.error('订单加载失败', e);
  }
}

function viewOrderResult(orderId) {
  fetch('/api/orders/' + orderId + '/result').then(r => r.json()).then(data => {
    if (!data.ok || !data.result) {
      const list = document.getElementById('ordersList') || document.getElementById('notifList');
      if (list) list.innerHTML = '<div style="color:#ef4444;text-align:center;padding:20px;">结果暂不可用</div>';
      return;
    }
    const result = data.result;
    let resultBody = '';
    if (result && result.version === 'hosted-result/v1') {
      resultBody = '<div style="margin-bottom:16px;"><div style="color:#a78bfa;font-size:14px;font-weight:600;margin-bottom:8px;">' + (result.title || '执行结果') + '</div><div style="color:#94a3b8;font-size:12px;margin-bottom:12px;">' + (result.summary || '') + '</div></div>';
      if (result.data && result.data.pools) {
        resultBody += '<div style="color:#e2e8f0;font-size:13px;"><div style="color:#34d399;margin-bottom:12px;">发现 ' + (result.data.count || result.data.pools.length) + ' 个流动性池：</div>';
        result.data.pools.forEach((pool, i) => {
          resultBody += '<div style="background:rgba(139,92,246,0.1);border-radius:8px;padding:12px;margin-bottom:8px;"><div style="color:#a78bfa;font-weight:600;margin-bottom:6px;">池子 ' + (i+1) + '</div><div style="color:#94a3b8;font-size:12px;">地址: <a href="https://bscscan.com/address/' + pool.address + '" target="_blank" style="color:#8b5cf6;">' + pool.address.slice(0,10) + '...' + pool.address.slice(-8) + '</a></div><div style="color:#94a3b8;font-size:12px;">交易对: ' + (pool.token0?.symbol || '?') + '/' + (pool.token1?.symbol || '?') + '</div><div style="color:#94a3b8;font-size:12px;">初始流动性: ' + (pool.initialLiquidity || '未知') + '</div><div style="color:#94a3b8;font-size:12px;">创建者: <a href="https://bscscan.com/address/' + pool.creator + '" target="_blank" style="color:#8b5cf6;">' + pool.creator.slice(0,10) + '...</a></div><div style="color:#64748b;font-size:11px;margin-top:4px;">区块: ' + pool.blockNumber + ' | ' + new Date(pool.createdAt).toLocaleString('zh-CN') + '</div></div>';
        });
        resultBody += '</div>';
      } else if (result.data) {
        resultBody += '<pre style="color:#e2e8f0;font-size:12px;white-space:pre-wrap;word-break:break-all;">' + JSON.stringify(result.data, null, 2) + '</pre>';
      }
    } else {
      resultBody = '<pre style="color:#e2e8f0;font-size:12px;white-space:pre-wrap;">' + (typeof result === 'string' ? result : JSON.stringify(result, null, 2)) + '</pre>';
    }
    const list = document.getElementById('ordersList');
    if (list) {
      list.innerHTML = '<div style="margin-bottom:16px;"><button onclick="loadMyOrdersInNotif()" style="background:none;border:1px solid rgba(139,92,246,0.3);color:#a78bfa;border-radius:6px;padding:4px 12px;font-size:11px;cursor:pointer;"><i data-lucide="arrow-left" class="icon-inline"></i> 返回订单列表</button></div><div style="font-size:13px;line-height:1.6;">' + resultBody + '</div>';
      App.refreshLucide();
    }
  });
}

async function loadNotifications() {
  if (!App.currentAccount) return;
  try {
    const res = await fetch('/api/notifications?wallet=' + App.currentAccount);
    const data = await res.json();
    if (!data.ok) return;
    const unreadEl = document.getElementById('myUnread'); if (unreadEl) unreadEl.textContent = data.unread;
    const badgeEl = document.getElementById('notifBadge'); if (badgeEl) badgeEl.style.display = data.unread > 0 ? 'block' : 'none';
    const list = document.getElementById('notifList');
    if (!list) return;
    if (data.notifications.length === 0) {
      list.innerHTML = '<div style="color:#475569;text-align:center;padding:20px;">暂无通知</div>';
      return;
    }
    list.innerHTML = data.notifications.map(n => {
      const time = new Date(n.createdAt).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai'});
      let icon = '', content = '';
      if (n.type === 'new_order') {
        icon = 'shopping-cart';
        content = '新订单：<strong style="color:#a78bfa">' + n.serviceName + '</strong> — 买家 ' + (n.buyerWallet?.slice(0,8) || '...') + '...';
      } else if (n.type === 'order_confirmed') {
        icon = 'check-circle';
        content = '订单确认：<strong style="color:#34d399">' + n.serviceName + '</strong> — 卖家 ' + (n.sellerName || n.sellerWallet?.slice(0,8) || '...') + '...';
      } else if (n.type === 'order_result') {
        icon = 'package';
        content = '结果已出：<strong style="color:#34d399">' + n.serviceName + '</strong> — <a href="#" onclick="viewOrderResult(\'' + n.orderId + '\');return false;" style="color:#8b5cf6;">查看结果</a>';
      }
      return '<div style="padding:10px 0;border-bottom:1px solid rgba(139,92,246,0.08);' + (n.read ? 'opacity:0.5' : '') + '"><div style="display:flex;align-items:center;gap:8px;"><span>' + icon + '</span><span>' + content + '</span><span style="margin-left:auto;font-size:11px;color:#475569;">' + time + '</span></div></div>';
    }).join('');
  } catch(e) {
    console.error('通知加载失败', e);
  }
}

async function markAllRead() {
  if (!App.currentAccount) return;
  try {
    await fetch('/api/v1/notifications/read-all', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wallet: App.currentAccount })
    });
    loadNotifications();
  } catch(e) {}
}

async function loadPendingPurchases() {
  try {
    const res = await fetch('/api/v1/purchases/pending');
    const data = await res.json();
    const section = document.getElementById('pendingConfirmSection');
    const list = document.getElementById('pendingList');
    const count = document.getElementById('pendingCount');
    if (!data.ok || data.count === 0) {
      if (section) section.style.display = 'none';
      return;
    }
    if (section) section.style.display = 'block';
    if (count) count.textContent = data.count;
    if (!list) return;
    list.innerHTML = data.purchases.map(p => {
      return '<div style="display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid rgba(251,191,36,0.1);"><div style="flex:1; min-width:0;"><div style="color:#e2e8f0; font-size:12px; font-weight:600;">' + (p.buyerName || p.buyerWallet.slice(0,10) + '...') + ' → ' + p.expert + '</div><div style="color:#94a3b8; font-size:11px;">' + p.serviceName + ' · ' + p.price + ' BNB</div></div><button onclick="confirmPurchase(\'' + p.id + '\')" style="background:rgba(52,211,153,0.2); color:#34d399; border:1px solid rgba(52,211,153,0.3); border-radius:6px; padding:4px 10px; font-size:11px; cursor:pointer;">确认收货</button></div>';
    }).join('');
    App.refreshLucide();
  } catch(e) { console.error('loadPendingPurchases error', e); }
}

async function confirmPurchase(purchaseId) {
  try {
    const purchasesRes = await fetch('/api/v1/purchases');
    const purchasesData = await purchasesRes.json();
    const purchase = (purchasesData.purchases || purchasesData).find(p => p.id === purchaseId);

    if (purchase?.escrowOrderId) {
      const escrowInfo = await fetch('/api/v1/escrow/info').then(r => r.json());
      if (!escrowInfo.ok) throw new Error('合约不可用');
      const escrowContract = await loadEscrowContract(escrowInfo.address, escrowInfo.abi);
      const wallet = getActiveWallet();
      const confirmTx = await escrowContract.methods.confirm(purchase.escrowOrderId).send({ from: wallet });
      console.log('[escrow] confirm tx:', confirmTx.transactionHash);
    }

    const buyerAuth = await signBuyerAction('confirm', purchaseId, getActiveWallet());
    const res = await fetch('/api/v1/purchases/confirm/' + purchaseId, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buyerAuth)
    });
    const data = await res.json();
    if (data.ok) {
      showNotice('<i data-lucide="check-circle" class="icon-inline"></i> 购买已确认，BNB 已释放给卖家');
      loadPendingPurchases();
      loadMyOrders();
      reloadMarket();
    } else { showError(data.error); }
  } catch(e) { showError('确认失败: ' + e.message); }
}

async function claimSellerTimeout(orderId, escrowOrderId) {
  try {
    if (!escrowOrderId) throw new Error('无合约订单ID');
    const escrowInfo = await fetch('/api/v1/escrow/info').then(r => r.json());
    if (!escrowInfo.ok) throw new Error('合约不可用');
    const escrowContract = await loadEscrowContract(escrowInfo.address, escrowInfo.abi);
    const wallet = getActiveWallet();
    showNotice('<i data-lucide="loader" class="icon-inline spin"></i> 正在申请退款，请在 MetaMask 确认...');
    const refundTx = await escrowContract.methods.claimSellerTimeout(escrowOrderId).send({ from: wallet });
    console.log('[escrow] claimSellerTimeout tx:', refundTx.transactionHash);
    const buyerAuth = await signBuyerAction('refund', orderId, wallet);
    const res = await fetch('/api/orders/' + orderId + '/refund', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'seller_timeout', txHash: refundTx.transactionHash, ...buyerAuth })
    });
    const data = await res.json();
    if (data.ok) {
      showNotice('<i data-lucide="check-circle" class="icon-inline"></i> 退款成功！BNB 已退回您的钱包');
      loadMyOrders();
      reloadMarket();
    } else {
      showError(data.error || '退款失败');
    }
  } catch(e) {
    showError('退款失败: ' + e.message);
  }
}

function toggleSellerOrders() {
  sellerOrdersOpen = !sellerOrdersOpen;
  if (!sellerOrdersOpen) {
    const m = document.getElementById('sellerOrdersModal');
    if (m) m.remove();
    return;
  }
  const modal = document.createElement('div');
  modal.id = 'sellerOrdersModal';
  modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:99999;display:flex;justify-content:center;align-items:center;';
  modal.onclick = (e) => { if (e.target === modal) { sellerOrdersOpen = false; modal.remove(); } };
  modal.innerHTML = '<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);border:2px solid rgba(139,92,246,0.4);border-radius:16px;padding:28px;width:600px;max-width:90vw;max-height:70vh;display:flex;flex-direction:column;"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;"><div style="color:#a78bfa;font-weight:600;font-size:16px;"><i data-lucide="package" class="icon-inline"></i> 收到的订单</div><button onclick="sellerOrdersOpen=false;document.getElementById(\'sellerOrdersModal\').remove()" style="background:none;border:none;color:#94a3b8;font-size:20px;cursor:pointer;">✕</button></div><div id="sellerOrdersList" style="color:#94a3b8;font-size:13px;overflow-y:auto;flex:1;">加载中...</div></div>';
  document.body.appendChild(modal);
  App.refreshLucide();
  loadSellerOrders();
}

function toggleSellerNotif() {
  sellerNotifOpen = !sellerNotifOpen;
  if (!sellerNotifOpen) {
    const m = document.getElementById('sellerNotifModal');
    if (m) m.remove();
    return;
  }
  const modal = document.createElement('div');
  modal.id = 'sellerNotifModal';
  modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:99999;display:flex;justify-content:center;align-items:center;';
  modal.onclick = (e) => { if (e.target === modal) { sellerNotifOpen = false; modal.remove(); } };
  modal.innerHTML = '<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);border:2px solid rgba(139,92,246,0.4);border-radius:16px;padding:28px;width:520px;max-width:90vw;max-height:70vh;display:flex;flex-direction:column;"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;"><div style="color:#a78bfa;font-weight:600;font-size:16px;"><i data-lucide="bell" class="icon-inline"></i> 通知中心</div><div style="display:flex;gap:8px;align-items:center;"><button onclick="markAllRead()" style="background:none;border:1px solid rgba(139,92,246,0.3);color:#a78bfa;border-radius:6px;padding:4px 10px;font-size:11px;cursor:pointer;">全部已读</button><button onclick="sellerNotifOpen=false;document.getElementById(\'sellerNotifModal\').remove()" style="background:none;border:none;color:#94a3b8;font-size:20px;cursor:pointer;">✕</button></div></div><div id="sellerNotifList" style="color:#94a3b8;font-size:13px;overflow-y:auto;flex:1;">加载中...</div></div>';
  document.body.appendChild(modal);
  App.refreshLucide();
  loadSellerNotif();
  if (App.currentAccount) {
    fetch('/api/v1/notifications/read-all', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ wallet: App.currentAccount }) }).then(() => {
      const el = document.getElementById('sellerUnread'); if (el) el.textContent = '0';
    });
  }
}

window.toggleNotificationPanel = toggleNotificationPanel;
window.loadMyOrdersInNotif = loadMyOrdersInNotif;
window.loadMyOrders = loadMyOrders;
window.viewOrderResult = viewOrderResult;
window.loadNotifications = loadNotifications;
window.markAllRead = markAllRead;
window.loadPendingPurchases = loadPendingPurchases;
window.confirmPurchase = confirmPurchase;
window.claimSellerTimeout = claimSellerTimeout;
window.toggleMyOrders = toggleMyOrders;
window.toggleSellerOrders = toggleSellerOrders;
window.toggleSellerNotif = toggleSellerNotif;
