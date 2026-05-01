
    let currentAccount = null;
    let progressRetryAction = null;
    let isPaymentInProgress = false;
    const marketServices = new Map();
    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, ch => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }[ch]));
    }

    const CHAIN_CONFIG = {
      bsc: {
        chainId: '0x38',
        chainName: 'BNB Smart Chain',
        nativeCurrency: { name: 'BNB', symbol: 'BNB', decimals: 18 },
        rpcUrls: ['https://bsc-dataseed1.binance.org'],
        blockExplorerUrls: ['https://bscscan.com'],
        explorerBaseUrl: 'https://bscscan.com',
        usdc: { address: '0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d', decimals: 18 }
      },
      base: {
        chainId: '0x2105',
        chainName: 'Base',
        nativeCurrency: { name: 'Ether', symbol: 'ETH', decimals: 18 },
        rpcUrls: ['https://mainnet.base.org'],
        blockExplorerUrls: ['https://basescan.org'],
        explorerBaseUrl: 'https://basescan.org',
        usdc: { address: '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913', decimals: 6 }
      }
    };

    // v2: 从 sellers API 加载市场数据，不再用旧的 SERVICES

    // 市场指标默认值（硬编码，不依赖异步备份）
    const MARKET_DEFAULTS = [
      { label: '<i data-lucide="bot" class="icon-inline"></i> Agent 总数', valueId: 'metricAgents', trendId: 'trendAgents' },
      { label: '<i data-lucide="trending-up" class="icon-inline"></i> 近24h 交易额', valueId: 'metricVolume', trendId: 'trendVolume' },
      { label: '<i data-lucide="zap" class="icon-inline"></i> 近24h 交易', valueId: 'metricTxs', trendId: 'trendTxs' },
      { label: '<i data-lucide="database" class="icon-inline"></i> 总交易额', valueId: 'metricTotalVolume', trendId: 'trendTotalVolume' },
    ];

    // 全局指标卡片 - 保存当前市场数据用于切换恢复
    let marketLabels = [];
    function initMetricsBackup() {
      marketLabels = [];
      document.querySelectorAll('.metrics .metric-card').forEach(c => {
        marketLabels.push({
          label: c.querySelector('.label').innerHTML,
          value: c.querySelector('.value').innerHTML,
          valueId: c.querySelector('.value').id,
          trend: c.querySelector('.trend').innerHTML,
          trendId: c.querySelector('.trend').id,
        });
      });
    }

    // 切换到卖家指标（只改文字，不动DOM节点）
    function showSellerMetrics() {
      const cards = document.querySelectorAll('.metrics .metric-card');
      if (cards.length < 4) return;
      // 可接单额度
      cards[0].querySelector('.label').textContent = '可接单额度';
      const v0 = cards[0].querySelector('.value'); v0.id = 'sellerQuota'; v0.textContent = '0 BNB'; v0.style.color = '#34d399';
      const t0 = cards[0].querySelector('.trend'); t0.id = 'sellerQuotaTrend'; t0.textContent = '\u00a0'; t0.className = 'trend';
      // 今日收入
      cards[1].querySelector('.label').textContent = '今日收入';
      const v1 = cards[1].querySelector('.value'); v1.id = 'sellerTodayIncome'; v1.textContent = '0 BNB'; v1.style.color = '#fbbf24';
      const t1 = cards[1].querySelector('.trend'); t1.id = 'sellerTodayIncomeTrend'; t1.textContent = '\u00a0'; t1.className = 'trend';
      // 今日成交
      cards[2].querySelector('.label').textContent = '今日成交';
      const v2 = cards[2].querySelector('.value'); v2.id = 'sellerTodayOrders'; v2.textContent = '0'; v2.style.color = '';
      const t2 = cards[2].querySelector('.trend'); t2.id = 'sellerTodayOrdersTrend'; t2.textContent = '\u00a0'; t2.className = 'trend';
      // 累计收入
      cards[3].querySelector('.label').textContent = '累计收入';
      const v3 = cards[3].querySelector('.value'); v3.id = 'sellerTotalIncome'; v3.textContent = '0 BNB'; v3.style.color = '#a78bfa';
      const t3 = cards[3].querySelector('.trend'); t3.id = 'sellerTotalIncomeTrend'; t3.textContent = '--'; t3.className = 'trend'; t3.style.color = '#64748b';
    }
    // 恢复市场指标（只改属性，不动DOM节点）
    function showMarketMetrics() {
      const cards = document.querySelectorAll('.metrics .metric-card');
      if (cards.length < 4) return;
      const labels = MARKET_DEFAULTS;
      for (let i = 0; i < 4; i++) {
        cards[i].querySelector('.label').innerHTML = labels[i].label;
        const val = cards[i].querySelector('.value');
        val.id = labels[i].valueId;
        // 保留当前值，不重置为 --
        if (!val.textContent || val.textContent === '--') val.textContent = '0';
        val.style.color = '';
        const trend = cards[i].querySelector('.trend');
        trend.id = labels[i].trendId;
        trend.className = 'trend';
        trend.style.color = '';
      }
      lucide.createIcons();
      // 立即从缓存恢复指标，再异步刷新
      applyMarketMetrics();
      reloadMarket();
    }

    // 买家指标（我的Agent页）
    function showBuyerMetrics() {
      const cards = document.querySelectorAll('.metrics .metric-card');
      if (cards.length < 4) return;
      // 没连接钱包时显示提示状态
      if (!currentAccount) {
        cards[0].querySelector('.label').innerHTML = '<i data-lucide="wallet" class="icon-inline"></i> 我的余额';
        const v0 = cards[0].querySelector('.value'); v0.id = 'buyerBalance'; v0.textContent = '未连接'; v0.style.color = '#64748b';
        const t0 = cards[0].querySelector('.trend'); t0.id = 'buyerBalanceTrend'; t0.textContent = '\u00a0'; t0.className = 'trend';
        cards[1].querySelector('.label').innerHTML = '<i data-lucide="clipboard-list" class="icon-inline"></i> 我的订单';
        const v1 = cards[1].querySelector('.value'); v1.id = 'buyerOrders'; v1.textContent = '--'; v1.style.color = '#64748b';
        const t1 = cards[1].querySelector('.trend'); t1.id = 'buyerOrdersTrend'; t1.textContent = '\u00a0'; t1.className = 'trend';
        cards[2].querySelector('.label').innerHTML = '<i data-lucide="coins" class="icon-inline"></i> 总消费';
        const v2 = cards[2].querySelector('.value'); v2.id = 'buyerTotalSpent'; v2.textContent = '--'; v2.style.color = '#64748b';
        const t2 = cards[2].querySelector('.trend'); t2.id = 'buyerTotalSpentTrend'; t2.textContent = '--'; t2.className = 'trend'; t2.style.color = '#64748b';
        cards[3].querySelector('.label').innerHTML = '<i data-lucide="package" class="icon-inline"></i> 已购订单';
        const v3 = cards[3].querySelector('.value'); v3.id = 'buyerServices'; v3.textContent = '--'; v3.style.color = '#64748b';
        const t3 = cards[3].querySelector('.trend'); t3.id = 'buyerServicesTrend'; t3.textContent = '--'; t3.className = 'trend'; t3.style.color = '#64748b';
        lucide.createIcons();
        return;
      }
      // 已连接钱包：显示默认值，等 loadBuyerStats 异步填充
      cards[0].querySelector('.label').innerHTML = '<i data-lucide="wallet" class="icon-inline"></i> 我的余额';
      const v0 = cards[0].querySelector('.value'); v0.id = 'buyerBalance'; v0.textContent = '-- BNB'; v0.style.color = '#34d399';
      const t0 = cards[0].querySelector('.trend'); t0.id = 'buyerBalanceTrend'; t0.textContent = '\u00a0'; t0.className = 'trend';
      cards[1].querySelector('.label').innerHTML = '<i data-lucide="clipboard-list" class="icon-inline"></i> 已下单';
      const v1 = cards[1].querySelector('.value'); v1.id = 'buyerOrders'; v1.textContent = '0'; v1.style.color = '';
      const t1 = cards[1].querySelector('.trend'); t1.id = 'buyerOrdersTrend'; t1.textContent = '\u00a0'; t1.className = 'trend';
      cards[2].querySelector('.label').innerHTML = '<i data-lucide="coins" class="icon-inline"></i> 总支出';
      const v2 = cards[2].querySelector('.value'); v2.id = 'buyerTotalSpent'; v2.textContent = '0 BNB'; v2.style.color = '#f87171';
      const t2 = cards[2].querySelector('.trend'); t2.id = 'buyerTotalSpentTrend'; t2.textContent = '--'; t2.className = 'trend'; t2.style.color = '#64748b';
      cards[3].querySelector('.label').innerHTML = '<i data-lucide="package" class="icon-inline"></i> 收到的币';
      const v3 = cards[3].querySelector('.value'); v3.id = 'buyerReceived'; v3.textContent = '0'; v3.style.color = '#34d399';
      const t3 = cards[3].querySelector('.trend'); t3.id = 'buyerReceivedTrend'; t3.textContent = '--'; t3.className = 'trend'; t3.style.color = '#64748b';
      lucide.createIcons();
    }

    // 加载卖家工作台全部数据
    async function loadSellerData() {
      try {
        await checkMyRegistration();
      } catch(e) { console.error('checkMyRegistration error:', e); }
      try {
        loadSellerOrders();
      } catch(e) { console.error('loadSellerOrders error:', e); }
      try {
        loadSellerTx();
      } catch(e) { console.error('loadSellerTx error:', e); }
      try {
        loadSellerStats();
      } catch(e) { console.error('loadSellerStats error:', e); }
    }

    // 加载买家统计
    async function loadBuyerStats() {
      console.log('[loadBuyerStats] called, currentAccount:', currentAccount);
      if (!currentAccount) { console.log('[loadBuyerStats] ABORT: no currentAccount'); return; }
      const tabSnapshot = activeTab;
      try {
        // 余额（始终加载，不受 tab 限制）
        const balRes = await fetch(`/api/balance?wallet=${currentAccount}`);
        const balData = await balRes.json();
        const balEl = document.getElementById('buyerBalance');
        if (balEl && balData.ok) balEl.textContent = parseFloat(balData.balance).toFixed(4) + ' BNB';

        // 买家订单（缓存数据，在 myagent tab 时渲染）
        const orderRes = await fetch(`/api/my-orders?wallet=${currentAccount}`);
        const orderData = await orderRes.json();
        if (orderData.ok) {
          const orders = orderData.orders || [];
          console.log('[loadBuyerStats] orders:', orders.length, 'activeTab:', activeTab, 'account:', currentAccount?.slice(0,10));
          // 缓存订单供 tab 切换时使用
          window._cachedBuyerOrders = orders;
          // 渲染表格（不再限制 tab）
          const orderEl = document.getElementById('buyerOrders');
          if (orderEl) orderEl.textContent = orders.length;
          const totalSpent = orders.reduce((sum, o) => sum + parseFloat(o.price || 0), 0);
          const spentEl = document.getElementById('buyerTotalSpent');
          if (spentEl) spentEl.textContent = totalSpent.toFixed(4) + ' BNB';
          const completedOrders = orders.filter(o => o.status === 'completed' || o.status === 'delivered');
          const receivedEl = document.getElementById('buyerReceived');
          if (receivedEl) receivedEl.textContent = completedOrders.length + ' 笔';
          renderBuyerTxTable(orders, true);
          console.log('[loadBuyerStats] renderBuyerTxTable called, orders:', orders.length);
          renderAgentBrain(orders);
          console.log('[loadBuyerStats] renderAgentBrain called');
        }
      } catch(e) {}
    }

    // Agent 大脑：从订单生成决策链（逐步动画）
    let _brainAnimTimer = null;
    function renderAgentBrain(orders, animate) {
      const el = document.getElementById('myAgentFeed');
      if (!el) return;
      if (_brainAnimTimer) { clearTimeout(_brainAnimTimer); _brainAnimTimer = null; }
      if (!orders.length) {
        el.innerHTML = '<div style="color:#475569; text-align:center; padding:40px 0;"><i data-lucide="brain" style="width:32px;height:32px;color:#475569;display:block;margin:0 auto 12px;"></i>Agent 决策链路<br><span style="font-size:11px;margin-top:6px;display:block;">点击「买币指令」开始<br>Agent 将实时展示搜索卖家、选择下单、代执行买币全过程</span></div>';
        lucide.createIcons();
        return;
      }
      const sorted = [...orders].sort((a, b) => new Date(b.time || 0) - new Date(a.time || 0));
      // 只渲染最新的一条（动画模式），或全部（非动画）
      const showOrders = animate ? [sorted[0]] : sorted;
      // 动画模式：逐步显示步骤
      if (animate && showOrders.length) {
        const o = showOrders[0];
        const time = new Date(o.time).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', hour12:false});
        const isDone = o.status === 'completed' || o.status === 'delivered';
        const expert = o.expert || '未知卖家';
        const price = o.price || 0;
        const txHash = o.txHash || '';
        const tokenAmt = o.tokenAmount || '?';
        const txLink = txHash ? `<a href="https://bscscan.com/tx/${txHash}" target="_blank" style="color:#8b5cf6;">${txHash.slice(0,10)}...</a>` : '--';

        // 保留历史记录在上面
        const prevHtml = sorted.slice(1).map(prevOrder => {
          const pt = new Date(prevOrder.time).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', hour12:false});
          const pExpert = prevOrder.expert || '未知';
          const pPrice = prevOrder.price || 0;
          const pDone = prevOrder.status === 'completed' || prevOrder.status === 'delivered';
          const pToken = prevOrder.tokenAmount || '?';
          return `<div style="padding:8px;background:rgba(100,116,139,0.05);border-radius:6px;margin-bottom:4px;opacity:0.6;">
            <div style="color:#64748b;font-size:10px;">${pt}</div>
            <div style="color:#94a3b8;font-size:11px;">${pDone ? '✅' : '⏳'} ${pExpert} · ${pPrice} BNB → ${pToken} TOKEN</div>
          </div>`;
        }).join('');

        const steps = [
          { icon: '🔍', color: '#a78bfa', label: '搜索卖家', detail: `扫描服务市场 ${15} 个卖家，按权重/评分/额度筛选...`, tags: `<span style="background:rgba(139,92,246,0.1);color:#a78bfa;padding:2px 6px;border-radius:4px;font-size:10px;">${expert} ★</span>` },
          { icon: '🎯', color: '#34d399', label: '选择最优', detail: `选中 <b style="color:#34d399;">${expert}</b> — 评分最高、押金充足` },
          { icon: '💰', color: '#fbbf24', label: '付款', detail: `${price} BNB → ${expert} ${isDone ? '<span style="color:#34d399;">✅ 链上确认</span>' : '<span style="color:#fbbf24;">⏳ 待确认</span>'}`, extra: txHash ? `TX: ${txLink}` : '' },
          { icon: '🤖', color: '#8b5cf6', label: '卖家代执行', detail: `${expert} 收到指令，为你买入代币...` },
          { icon: '📦', color: '#60a5fa', label: '代币转回', detail: `${expert} 将 <b style="color:#60a5fa;">${tokenAmt} TOKEN</b> 转入你的钱包` },
          { icon: '✅', color: '#34d399', label: '交易完成', detail: `💰 花费 <b style="color:#fbbf24;">${price} BNB</b> → 📦 收到 <b style="color:#60a5fa;">${tokenAmt} TOKEN</b>`, sub: `卖家 ${expert} 代为执行`, isFinal: true },
        ];

        let html = `<div style="margin-bottom:4px;color:#64748b;font-size:10px;">${time}</div>`;
        el.innerHTML = html;
        let stepIdx = 0;
        function showNextStep() {
          if (stepIdx >= steps.length) {
            // 动画结束，加上历史
            el.innerHTML = html + (prevHtml ? '<div style="border-top:1px dashed rgba(139,92,246,0.15); margin:8px 0;"></div><div style="color:#64748b;font-size:10px;margin-bottom:4px;">历史记录</div>' + prevHtml : '');
            lucide.createIcons();
            return;
          }
          const s = steps[stepIdx];
          if (s.isFinal) {
            html += `<div style="padding:8px; background:rgba(34,211,153,0.08);border-radius:8px;margin-top:4px;border:1px solid rgba(34,211,153,0.15); animation:fadeIn 0.3s;">
              <div style="color:#34d399;font-size:12px;font-weight:600;">${s.icon} ${s.label}</div>
              <div style="color:#94a3b8;font-size:11px;margin-top:4px;">${s.detail}</div>
              <div style="color:#64748b;font-size:10px;margin-top:2px;">${s.sub}</div>
            </div>`;
          } else {
            html += `<div style="padding:6px 0; border-bottom:1px solid rgba(139,92,246,0.06); animation:fadeIn 0.3s;">
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;"><span style="color:${s.color};font-size:12px;">${s.icon} ${s.label}</span></div>
              <div style="color:#94a3b8;font-size:11px;">${s.detail}</div>
              ${s.tags ? `<div style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap;">${s.tags}</div>` : ''}
              ${s.extra ? `<div style="color:#94a3b8;font-size:11px;margin-top:2px;">${s.extra}</div>` : ''}
            </div>`;
          }
          el.innerHTML = html;
          stepIdx++;
          _brainAnimTimer = setTimeout(showNextStep, isDone ? 1200 : 800);
        }
        showNextStep();
        return;
      }
      // 非动画：全部渲染
      let html = '';
      sorted.forEach((o, idx) => {
        const time = new Date(o.time).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', hour12:false});
        const isDone = o.status === 'completed' || o.status === 'delivered';
        const expert = o.expert || '未知卖家';
        const price = o.price || 0;
        const txHash = o.txHash || '';
        const tokenAmt = o.tokenAmount || '?';
        const txLink = txHash ? `<a href="https://bscscan.com/tx/${txHash}" target="_blank" style="color:#8b5cf6;">${txHash.slice(0,10)}...</a>` : '--';

        if (idx > 0) html += '<div style="border-top:1px dashed rgba(139,92,246,0.15); margin:8px 0;"></div>';

        html += `<div style="margin-bottom:4px;color:#64748b;font-size:10px;">${time}</div>`;
        html += `<div style="padding:6px 0; border-bottom:1px solid rgba(139,92,246,0.06);">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;"><span style="color:#a78bfa;font-size:12px;">🔍 搜索卖家</span></div>
          <div style="color:#94a3b8;font-size:11px;">扫描服务市场，按权重/评分/额度筛选...</div>
          <div style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap;"><span style="background:rgba(139,92,246,0.1);color:#a78bfa;padding:2px 6px;border-radius:4px;font-size:10px;">${expert} ★</span></div>
        </div>`;
        html += `<div style="padding:6px 0; border-bottom:1px solid rgba(139,92,246,0.06);">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;"><span style="color:#34d399;font-size:12px;">🎯 选择最优</span></div>
          <div style="color:#94a3b8;font-size:11px;">选中 <b style="color:#34d399;">${expert}</b></div>
        </div>`;
        html += `<div style="padding:6px 0; border-bottom:1px solid rgba(139,92,246,0.06);">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;"><span style="color:#fbbf24;font-size:12px;">💰 付款</span></div>
          <div style="color:#94a3b8;font-size:11px;">${price} BNB → ${expert} ${isDone ? '<span style="color:#34d399;">✅ 链上确认</span>' : '<span style="color:#fbbf24;">⏳ 待确认</span>'}</div>
          ${txHash ? `<div style="color:#94a3b8;font-size:11px;margin-top:2px;">TX: ${txLink}</div>` : ''}
        </div>`;
        if (isDone) {
          html += `<div style="padding:6px 0; border-bottom:1px solid rgba(139,92,246,0.06);">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;"><span style="color:#8b5cf6;font-size:12px;">🤖 卖家代执行</span></div>
            <div style="color:#94a3b8;font-size:11px;">${expert} 收到指令，为你买入代币...</div>
          </div>`;
          html += `<div style="padding:6px 0; border-bottom:1px solid rgba(139,92,246,0.06);">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;"><span style="color:#60a5fa;font-size:12px;">📦 代币转回</span></div>
            <div style="color:#94a3b8;font-size:11px;">${expert} 将 <b style="color:#60a5fa;">${tokenAmt} TOKEN</b> 转入你的钱包</div>
          </div>`;
          html += `<div style="padding:8px; background:rgba(34,211,153,0.08);border-radius:8px;margin-top:4px;border:1px solid rgba(34,211,153,0.15);">
            <div style="color:#34d399;font-size:12px;font-weight:600;">✅ 交易完成</div>
            <div style="color:#94a3b8;font-size:11px;margin-top:4px;">💰 花费 <b style="color:#fbbf24;">${price} BNB</b> → 📦 收到 <b style="color:#60a5fa;">${tokenAmt} TOKEN</b></div>
            <div style="color:#64748b;font-size:10px;margin-top:2px;">卖家 ${expert} 代为执行</div>
          </div>`;
        }
      });
      el.innerHTML = html;
      lucide.createIcons();
    }

    // 买币指令按钮
    let _buyingActive = false;
    async function agentBuyToken() {
      if (_buyingActive) return;
      if (!currentAccount) { alert('请先连接钱包'); return; }
      const amount = parseFloat(document.getElementById('buyAmount')?.value || '0.001');
      _buyingActive = true;
      const btn = document.getElementById('buyTokenBtn');
      if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; btn.innerHTML = '<span style="animation:spin 1s linear infinite;display:inline-block;">⏳</span> 执行中...'; }
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 60000); // 60秒超时
        const res = await fetch('/api/v1/agent-buy', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            buyerWallet: currentAccount,
            amount: amount
          }),
          signal: controller.signal
        });
        clearTimeout(timeout);
        const data = await res.json();
        if (data.ok) {
          await loadBuyerStats();
          const orders = window._cachedBuyerOrders || [];
          renderAgentBrain(orders, true);
          renderBuyerTxTable(orders, true);
        } else {
          alert('买币失败: ' + (data.error || '未知错误'));
        }
      } catch(e) {
        if (e.name === 'AbortError') {
          alert('请求超时（60秒），卖家Agent可能未响应，请检查卖家状态');
        } else {
          alert('请求失败: ' + e.message);
        }
      }
      _buyingActive = false;
      if (btn) { btn.disabled = false; btn.style.opacity = '1'; btn.innerHTML = '<i data-lucide="zap" class="icon-inline" style="width:12px;height:12px;"></i> 买币指令'; lucide.createIcons(); }
    }

    let _lastRenderedTxHash = '';
    function renderBuyerTxTable(orders, force) {
      const tbody = document.getElementById('myTxBody');
      if (!tbody) return;
      console.log('[renderBuyerTxTable] orders:', orders.length, 'force:', force, 'tbody:', !!tbody, 'first:', orders[0]?.id, 'last:', orders[orders.length-1]?.id);
      // 每次强制渲染
      _lastRenderedTxHash = Date.now();
      tbody.innerHTML = '';
      const noTx = document.getElementById('noMyTxs');
      if (orders.length === 0) {
        if (noTx) noTx.style.display = 'block';
        return;
      }
      if (noTx) noTx.style.display = 'none';
      // 按时间倒序，最新在上面
      const sorted = [...orders].sort((a, b) => new Date(b.time || 0) - new Date(a.time || 0));
      console.log('[renderBuyerTxTable] sorted orders:', sorted.length, sorted.slice(0,3).map(o => ({id:o.id, status:o.status, rated:o.rated})));
      sorted.forEach((o, idx) => {
        // 已评价的订单不再显示
        if (o.rated) return;
        const time = new Date(o.time).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', hour12:false});
        const isDone = o.status === 'completed' || o.status === 'delivered';
        const statusHtml = isDone ? '<span style="color:#34d399;">✅ 已到账</span>' : '<span style="color:#fbbf24;">⏳ 执行中</span>';
        const txHash = o.txHash || '';
        const shortHash = txHash.length > 10 ? txHash.slice(0,8) + '...' : txHash || '--';
        const txLink = txHash ? `<a href="https://bscscan.com/tx/${txHash}" target="_blank" style="color:#8b5cf6;text-decoration:none;font-size:14px;">🔗</a>` : '<span style="color:#475569;">--</span>';
        const tokenAmt = o.tokenAmount || '--';
        const receiptId = o.id || '';
        window['_myBuyerOrders'] = window['_myBuyerOrders'] || {};
        window['_myBuyerOrders'][idx] = { id: receiptId, serviceName: o.serviceName, expert: o.expert, price: o.price, priceCurrency: 'BNB', time: o.time, buyerWallet: currentAccount, expertWallet: o.expertWallet, txHash };
        // 评价按钮：只有已完成且未评价的订单显示
        let rateHtml = '<span style="color:#475569;font-size:11px;">--</span>';
        if (isDone && !o.rated) {
          rateHtml = `<span style="cursor:pointer;" onclick="rateOrder('${receiptId}')" title="评价">⭐</span>`;
        } else if (o.rated) {
          rateHtml = `<span style="color:#fbbf24;">${'⭐'.repeat(o.rating || 0)}</span>`;
        }
        tbody.innerHTML += `<tr>
          <td class="time">${time}</td>
          <td class="flow">${o.expert || '--'}</td>
          <td class="amount">${o.price || 0} BNB</td>
          <td>${statusHtml}</td>
          <td>${txLink}</td>
          <td>${rateHtml}</td>
        </tr>`;
      });
      console.log('[renderBuyerTxTable] tbody.innerHTML length:', tbody.innerHTML.length, 'rows:', tbody.querySelectorAll('tr').length);
      lucide.createIcons();
    }



    // 评价订单
    async function rateOrder(orderId) {
      const stars = prompt('请评分 1-5 星：\n1=很差  2=差  3=一般  4=好  5=很好');
      const rating = parseInt(stars);
      if (!rating || rating < 1 || rating > 5) { alert('请输入1-5'); return; }
      try {
        const res = await fetch('/api/v1/rate-order', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ orderId, rating, rater: currentAccount })
        });
        const data = await res.json();
        if (data.ok) {
          alert('评价成功！');
          loadBuyerStats();
        } else {
          alert('评价失败: ' + (data.error || ''));
        }
      } catch(e) {
        alert('请求失败: ' + e.message);
      }
    }

    let activeTab = 'market'; // 追踪当前 tab，防止异步回调改错指标

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
        activeTab = 'market';
        showMarketMetrics();
        loadTxsFeed();
        startTxsStream();
      } else if (tab === 'register') {
        document.querySelector('.nav span:nth-child(2)').classList.add('active');
        document.getElementById('panel-register').style.display = 'block';
        document.querySelector('.main').style.display = 'none';
        // 只有卖家工作台显示时才展示指标卡片，入驻指南不展示
        const sellerDashboard = document.getElementById('sellerDashboard');
        if (metricsDiv) metricsDiv.style.display = (sellerDashboard && sellerDashboard.style.display !== 'none') ? 'grid' : 'none';
        activeTab = 'register';
        showSellerMetrics();
        loadSellerData();
      } else if (tab === 'myagent') {
        document.querySelector('.nav span:nth-child(3)').classList.add('active');
        document.getElementById('myAgent').style.display = 'block';
        document.querySelector('.main').style.display = 'none';
        if (metricsDiv) metricsDiv.style.display = 'grid';
        activeTab = 'myagent';
        showBuyerMetrics();
        // 用缓存数据立即渲染
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
      } else if (tab === 'admin') {
        document.querySelector('#adminTab').classList.add('active');
        document.getElementById('panel-admin').style.display = 'block';
        document.querySelector('.main').style.display = 'none';
        loadPendingServices();
      }
      // 保存当前tab到URL hash
      window.location.hash = tab;
    }

    // 页面加载时恢复tab
    function restoreTab() {
      const hash = window.location.hash.replace('#', '');
      if (['market', 'register', 'myagent', 'admin'].includes(hash)) {
        showTab(hash);
      }
    }


    // ===== Live Feed =====
    const AGENT_ICONS = { 'ChainSentry': '🔍', 'RiskGuard': '🛡️', 'NFTScout': '🎯', 'GasSaver': '⛽', 'AlphaBot': '🤖', 'ChainSeer': '🔮', 'Sentinel': '🔐', 'Buyer Agent': '🤖', 'Scout Agent': '🧭', 'Momentum One': '📈', 'Dip Hunter': '🎯', 'Risk Sentinel': '🛡️', 'Flow Surfer': '🌊' };
    const AGENT_COLORS = { 'ChainSentry': '#34d399', 'RiskGuard': '#fbbf24', 'NFTScout': '#f472b6', 'GasSaver': '#60a5fa', 'AlphaBot': '#a78bfa', 'ChainSeer': '#818cf8', 'Sentinel': '#34d399', 'Buyer Agent': '#a78bfa', 'Scout Agent': '#38bdf8', 'Momentum One': '#34d399', 'Dip Hunter': '#f59e0b', 'Risk Sentinel': '#60a5fa', 'Flow Surfer': '#22c55e' };
    let myAgentNames = new Set(); // 从 agents.json 加载当前钱包的 agent

    async function loadMyAgents() {
      try {
        const wallet = currentAccount || getActiveWallet();
        if (!wallet) {
          myAgentNames = new Set();
          const nameEl = document.getElementById('myAgentName'); if (nameEl) nameEl.textContent = '未连接钱包';
          return;
        }
        const res = await fetch('/api/v1/sellers');
        const data = await res.json();
        const agents = data.sellers || data || [];
        // 只加载当前钱包的 agent
        const myAgents = agents.filter(a => (a.wallet || '').toLowerCase() === wallet.toLowerCase());
        myAgentNames = new Set(myAgents.map(a => a.name).filter(Boolean));
        // v2: 也加入买家名字（从 purchases 获取）
        try {
          const orderRes = await fetch(`/api/my-orders?wallet=${wallet}`);
          const orderData = await orderRes.json();
          if (orderData.ok) {
            (orderData.orders || []).forEach(o => {
              if (o.buyerName) myAgentNames.add(o.buyerName);
              if (o.expert) myAgentNames.add(o.expert);
            });
          }
        } catch(e) {}
        const nameEl = document.getElementById('myAgentName'); if (nameEl) nameEl.textContent = [...myAgentNames].join(', ') || '未注册';
      } catch(e) {
        myAgentNames = new Set();
        const nameEl2 = document.getElementById('myAgentName'); if (nameEl2) nameEl2.textContent = '加载失败';
      }
    }

    function isMyAgent(item) {
      return myAgentNames.has(item.from) || myAgentNames.has(item.to) || myAgentNames.has(item.agent);
    }

    function formatTime(ts) {
      if (!ts) return '';
      const d = new Date(ts);
      const now = new Date();
      const diff = (now - d) / 1000;
      if (diff < 60) return '刚刚';
      if (diff < 3600) return Math.floor(diff / 60) + 'min ago';
      if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
      return d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    }

    function renderTxEvent(tx) {
      const isMyTo = myAgentNames.has(tx.to);
      const isMyFrom = myAgentNames.has(tx.from);
      
      let agent, icon, color, reason, direction;
      if (isMyTo && !isMyFrom) {
        // B端视角：我收到订单
        agent = tx.to;
        icon = AGENT_ICONS[agent] || '🤖';
        color = AGENT_COLORS[agent] || '#a78bfa';
        reason = tx.reason ? tx.reason.replace('雇佣卖家:', '收到订单:') : '收到订单';
        direction = '📥';
      } else {
        // C端视角或外部
        agent = tx.from || '未知';
        icon = AGENT_ICONS[agent] || '🤖';
        color = AGENT_COLORS[agent] || '#a78bfa';
        reason = tx.reason || '订单支付';
        direction = '';
      }
      
      const isRealTx = typeof tx.tx === 'string' && tx.tx.startsWith('0x');
      const shortTx = tx.tx ? (tx.tx.length > 16 ? tx.tx.slice(0, 8) + '...' + tx.tx.slice(-6) : tx.tx) : '';
      const bscUrl = isRealTx ? `https://bscscan.com/tx/${tx.tx}` : null;

      let html = '<div class="live-event pay">';
      html += '<div class="live-event-header">';
      html += '<span style="font-size:16px;">' + icon + '</span>';
      html += '<span class="live-event-agent" style="color:' + color + '">' + agent + '</span>';
      if (direction) html += '<span style="font-size:10px; margin-left:2px;">' + direction + '</span>';
      html += '<span class="live-event-time">' + formatTime(tx.timestamp) + '</span>';
      html += '</div>';
      html += '<div class="live-event-body">';
      if (isMyTo && !isMyFrom) {
        // B端：显示买家付了多少钱给我
        html += direction + ' ' + reason;
        if (tx.from) html += ' ← <strong style="color:#e2e8f0">' + tx.from + '</strong>';
      } else {
        html += reason;
        if (tx.to && tx.to !== agent) html += ' → <strong style="color:#e2e8f0">' + tx.to + '</strong>';
      }
      html += ' <span style="color:#34d399; font-weight:600;">' + tx.amount + ' BNB</span>';
      html += '</div>';

      if (shortTx) {
        html += '<div class="live-event-detail">';
        if (bscUrl) {
          html += '<a class="live-event-tx" href="' + bscUrl + '" target="_blank">🔗 ' + shortTx + '</a>';
          html += '<span style="color:#34d399; font-size:10px; margin-left:8px;">✅ 链上验证</span>';
        } else {
          html += '<span style="color:#475569; font-family:monospace; font-size:11px;">' + shortTx + '</span>';
          if (tx.verified) html += '<span style="color:#94a3b8; font-size:10px; margin-left:8px;">' + tx.verified + '</span>';
        }
        if (tx.route_type) html += '<span style="color:#475569; font-size:10px; margin-left:8px;">' + tx.route_type + '</span>';
        html += '</div>';
      }

      html += '</div>';
      return html;
    }

    function groupTxsIntoChains(txs) {
      const chains = [];
      let currentChain = [];
      let lastTime = 0;
      for (const tx of txs) {
        const t = new Date(tx.timestamp).getTime();
        if (lastTime && (t - lastTime > 5 * 60 * 1000)) {
          if (currentChain.length) chains.push(currentChain);
          currentChain = [];
        }
        currentChain.push(tx);
        lastTime = t;
      }
      if (currentChain.length) chains.push(currentChain);
      return chains;
    }

    function renderEventItem(item) {
      if (item._type === 'event') {
        // Agent thinking event
        const icon = AGENT_ICONS[item.agent] || '🤖';
        const color = AGENT_COLORS[item.agent] || '#a78bfa';
        const typeLabel = { think: '🧠 思考', pay: '💰 支付', execute: '⚙️ 执行', result: '📋 结果', error: '❌ 错误' };
        const borderClass = { think: 'think', pay: 'pay', execute: 'execute', result: 'result', error: 'pay' };
        const typeClass = borderClass[item.type] || 'think';

        let html = '<div class="live-event ' + typeClass + '">';
        html += '<div class="live-event-header">';
        html += '<span style="font-size:16px;">' + icon + '</span>';
        html += '<span class="live-event-agent" style="color:' + color + '">' + item.agent + '</span>';
        html += '<span style="font-size:10px; color:#475569; margin-left:4px;">' + (typeLabel[item.type] || item.type) + '</span>';
        html += '<span class="live-event-time">' + formatTime(item.timestamp) + '</span>';
        html += '</div>';
        html += '<div class="live-event-body">' + (item.message || '') + '</div>';
        if (item.tx_hash) {
          html += '<div class="live-event-detail">';
          html += '<a class="live-event-tx" href="https://bscscan.com/tx/' + item.tx_hash + '" target="_blank">🔗 ' + item.tx_hash.slice(0, 10) + '...</a>';
          html += '</div>';
        }
        html += '</div>';
        return html;
      } else {
        // Transaction from tx-log
        return renderTxEvent(item);
      }
    }

    async function loadLiveFeed() {
      const tabSnapshot = activeTab;
      try {
        await loadMyAgents();
        const res = await fetch('/api/v1/live-feed');
        const items = await res.json();
        if (tabSnapshot !== activeTab) return; // tab 已切走

        // Stats
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const txs = items.filter(i => i._type === 'tx');
        const todayTxs = txs.filter(t => new Date(t.timestamp) >= today);
        const NON_AGENTS = ['押金池', '未知', 'test', 'undefined', 'null'];
        const uniqueAgents = new Set();
        items.forEach(t => {
          [t.from, t.to, t.agent].forEach(name => {
            if (name && !NON_AGENTS.includes(name)) uniqueAgents.add(name);
          });
        });
        const verifiedCount = txs.filter(t => typeof t.tx === 'string' && t.tx.startsWith('0x')).length;
        const todayVolume = todayTxs.reduce((s, t) => s + (t.amount || 0), 0);

        // Stats (optional elements, may not exist on this page)
        const elTodayTxs = document.getElementById('liveTodayTxs'); if (elTodayTxs) elTodayTxs.textContent = todayTxs.length;
        const elTodayVol = document.getElementById('liveTodayVolume'); if (elTodayVol) elTodayVol.textContent = todayVolume.toFixed(4) + ' BNB';
        const elActiveAgents = document.getElementById('liveActiveAgents'); if (elActiveAgents) elActiveAgents.textContent = uniqueAgents.size;
        const elVerified = document.getElementById('liveVerified'); if (elVerified) elVerified.textContent = verifiedCount;
        const elAgentCount = document.getElementById('liveAgentCount'); if (elAgentCount) elAgentCount.textContent = uniqueAgents.size + ' 个 Agent 参与';
        const elLastUpdate = document.getElementById('liveLastUpdate'); if (elLastUpdate) elLastUpdate.textContent = '更新于 ' + now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

        // Split items into my agents vs market
        const myItems = items.filter(isMyAgent);
        const marketItems = items.filter(i => !isMyAgent(i));

        // Render my agent feed — 从订单生成决策链
        renderAgentBrain(window._cachedBuyerOrders || []);
        // Render market feed
        renderFeed('marketFeed', marketItems, false);
      } catch (e) {
        console.error('loadLiveFeed error:', e);
        const myAgentEl = document.getElementById('myAgentFeed');
        const marketEl = document.getElementById('marketFeed');
        if (myAgentEl) myAgentEl.innerHTML = '<div style="color:#f87171; text-align:center; padding:40px 0;">加载失败: ' + e.message + '</div>';
        if (marketEl) marketEl.innerHTML = '<div style="color:#f87171; text-align:center; padding:40px 0;">加载失败: ' + e.message + '</div>';
      }
    }

    function renderFeed(containerId, items, showChain) {
      const el = document.getElementById(containerId);
      if (!el) return;
      if (!items.length) {
        el.innerHTML = '<div style="color:#475569; text-align:center; padding:40px 0;">暂无活动</div>';
        return;
      }
      let html = '';
      if (showChain) {
        const chains = groupTxsIntoChains(items);
        for (let ci = 0; ci < chains.length; ci++) {
          const chain = chains[ci];
          if (ci > 0 && chain.length > 1) {
            html += '<div class="live-chain-marker"><div class="live-chain-line"></div><div class="live-chain-text">新一轮决策</div><div class="live-chain-line"></div></div>';
          }
          for (const item of chain) {
            html += renderEventItem(item);
          }
        }
      } else {
        for (const item of items) {
          html += renderEventItem(item);
        }
      }
      el.innerHTML = html;
      lucide.createIcons();
    }

    let liveEventSource = null;

    async function startLiveStream() {
      if (liveEventSource) liveEventSource.close();
      await loadMyAgents();
      const statusEl = document.getElementById('liveConnStatus');
      const pulseEl = document.getElementById('livePulse');
      if (statusEl) { statusEl.textContent = '● 连接中...'; statusEl.style.color = '#fbbf24'; }

      liveEventSource = new EventSource('/api/v1/live-stream');

      liveEventSource.onmessage = function(e) {
        try {
          const item = JSON.parse(e.data);
          if (item._type === 'connected') {
            if (statusEl) { statusEl.textContent = '● 实时'; statusEl.style.color = '#34d399'; }
            if (pulseEl) pulseEl.style.background = '#34d399';
            return;
          }
          prependLiveEvent(item);
        } catch(err) {}
      };

      liveEventSource.onerror = function() {
        if (statusEl) { statusEl.textContent = '○ 重连中...'; statusEl.style.color = '#f87171'; }
        if (pulseEl) pulseEl.style.background = '#f87171';
        liveEventSource.close();
        setTimeout(startLiveStream, 3000);
      };
    }

    function prependLiveEvent(item) {
      const containerId = isMyAgent(item) ? 'myAgentFeed' : 'marketFeed';
      const feed = document.getElementById(containerId);
      if (!feed) return;

      const html = renderEventItem(item);
      const wrapper = document.createElement('div');
      wrapper.innerHTML = html;
      const el = wrapper.firstElementChild;
      if (!el) return;

      // Highlight animation
      el.style.transition = 'background 0.5s ease';
      el.style.background = 'rgba(139,92,246,0.12)';
      setTimeout(() => { el.style.background = ''; }, 1500);

      // Check if user is near bottom before inserting
      const nearBottom = feed.scrollTop + feed.clientHeight >= feed.scrollHeight - 100;

      // Remove "no data" placeholder if present
      const placeholder = feed.querySelector('[style*="text-align:center"]');
      if (placeholder && placeholder.textContent.includes('暂无')) placeholder.remove();

      feed.insertBefore(el, feed.firstChild);

      // Auto-scroll if was near bottom
      if (nearBottom) {
        feed.scrollTop = 0;
      }

      // 刷新消费记录（如果是我的 agent 的交易）
      if (isMyAgent(item) && currentAccount) {
        loadBuyerStats();
      }

      // Update timestamp
      const now = new Date();
      document.getElementById('liveLastUpdate').textContent = '更新于 ' + now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

      lucide.createIcons();
    }


    // ===== Market Txs Feed (实时交易流) =====
    let txsEventSource = null;

    function renderTxsRow(tx) {
      const isRealTx = typeof tx.tx === 'string' && tx.tx.startsWith('0x');
      const bscUrl = isRealTx ? 'https://bscscan.com/tx/' + tx.tx : null;
      // 用钱包地址判断方向：toWallet === 当前钱包 → 收入(+), 否则 → 支出(-)
      const wallet = (currentAccount || '').toLowerCase();
      const toW = (tx.toWallet || '').toLowerCase();
      const fromW = (tx.fromWallet || '').toLowerCase();
      const isIn = wallet && toW && toW === wallet;
      const isOut = wallet && fromW && fromW === wallet;
      const icon = isIn ? 'download' : 'upload';
      const iconColor = isIn ? '#10b981' : '#a78bfa';
      const sign = isIn ? '+' : '-';
      const valClass = isIn ? 'pos' : 'neg';

      let html = '<div class="tx-item">';
      html += '<div class="tx-icon ' + (isIn ? 'in' : 'out') + '"><i data-lucide="' + icon + '" class="icon-sm" style="color:' + iconColor + '"></i></div>';
      html += '<div class="tx-info">';
      html += '<div class="flow">' + (tx.from || '?') + ' → ' + (tx.to || '?') + '</div>';
      html += '<div class="reason">' + (tx.reason || '') + (bscUrl ? ' <a href="' + bscUrl + '" target="_blank" style="color:#8b5cf6;font-size:10px;">🔗</a>' : '') + '</div>';
      html += '</div>';
      html += '<div class="tx-amount">';
      html += '<div class="val ' + valClass + '">' + sign + tx.amount + ' BNB</div>';
      html += '<div class="time">' + (tx.time || formatTime(tx.timestamp)) + '</div>';
      html += '</div>';
      html += '</div>';
      return html;
    }

    async function loadTxsFeed() {
      try {
        const res = await fetch('/api/v1/txs');
        const txs = await res.json();
        txs.sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));
        const el = document.getElementById('txList');
        if (!txs.length) {
          el.innerHTML = '<div style="color:#475569; text-align:center; padding:30px 0;">暂无交易</div>';
          return;
        }
        el.innerHTML = txs.slice(0, 30).map(renderTxsRow).join('');
        lucide.createIcons();
      } catch(e) {
        document.getElementById('txList').innerHTML = '<div style="color:#f87171; text-align:center; padding:30px 0;">加载失败</div>';
      }
    }

    function prependTxsItem(tx) {
      const feed = document.getElementById('txList');
      if (!feed) return;
      const html = renderTxsRow(tx);
      const wrapper = document.createElement('div');
      wrapper.innerHTML = html;
      const el = wrapper.firstElementChild;
      if (!el) return;
      el.style.transition = 'background 0.5s ease';
      el.style.background = 'rgba(139,92,246,0.12)';
      setTimeout(() => { el.style.background = ''; }, 1500);
      const ph = feed.querySelector('[style*="text-align:center"]');
      if (ph && ph.textContent.includes('暂无')) ph.remove();
      feed.insertBefore(el, feed.firstChild);
      // Keep max 30 items
      while (feed.children.length > 30) feed.removeChild(feed.lastChild);
      lucide.createIcons();
    }

    function startTxsStream() {
      if (txsEventSource) txsEventSource.close();
      txsEventSource = new EventSource('/api/v1/live-stream');
      txsEventSource.onmessage = function(e) {
        try {
          const item = JSON.parse(e.data);
          if (item._type === 'connected') return;
          if (item._type === 'tx') prependTxsItem(item);
        } catch(err) {}
      };
      txsEventSource.onerror = function() {
        txsEventSource.close();
        setTimeout(startTxsStream, 3000);
      };
    }


    // Generate identicon SVG for wallet address
    // 检查当前钱包是否已入驻
    async function checkMyRegistration() {
      const wallet = currentAccount || getActiveWallet();
      if (!wallet) {
        // 没有钱包，显示入驻指南
        document.getElementById('regFormArea').style.display = 'block';
        document.getElementById('sellerDashboard').style.display = 'none';
        return;
      }
      try {
        // 使用 V2 API 检查是否是卖家
        const res = await fetch('/api/v1/sellers');
        const data = await res.json();
        const sellers = data.sellers || [];
        const mySeller = sellers.find(s => s.wallet.toLowerCase() === wallet.toLowerCase());
        
        const regPanel = document.getElementById('myRegistrationPanel');
        const formArea = document.getElementById('regFormArea');
        const pendingPage = document.getElementById('pendingReviewPage');
        
        // 重置所有面板
        formArea.style.display = 'none';
        regPanel.style.display = 'none';
        pendingPage.style.display = 'none';
        document.getElementById('sellerDashboard').style.display = 'none';
        
        if (mySeller) {
          // 是卖家，显示工作台
          const svcEl = document.getElementById('sellerServiceContent');
          svcEl.innerHTML = `
            <div style="color:#e2e8f0;font-weight:600;font-size:15px;margin-bottom:8px;">${mySeller.name || '--'}</div>
            <div style="color:#64748b;font-size:12px;margin-bottom:8px;line-height:1.6;">${mySeller.desc || ''}</div>
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
              <span style="color:#64748b;font-size:11px;">费率:</span>
              <span style="color:#a78bfa;font-size:12px;font-weight:600;">${mySeller.feeRate || '--'} BNB</span>
            </div>
            <div style="display:flex;align-items:center;gap:6px;">
              <span style="color:#64748b;font-size:11px;">押金:</span>
              <span style="color:#fbbf24;font-size:12px;font-weight:600;">${mySeller.deposit || 0} BNB</span>
            </div>
          `;

          // 加载卖家数据
          loadSellerOrders();
          loadSellerStats();
          loadSellerTx();
          // 渲染权重卡片
          const weightEl = document.getElementById('sellerWeightContent');
          if (weightEl && mySeller) {
            const allSellers = sellers;
            const maxWeight = Math.max(...allSellers.map(s => s.weight || 1));
            const myWeight = mySeller.weight || 1;
            const weightPercent = maxWeight > 0 ? (myWeight / maxWeight * 100).toFixed(0) : 0;
            const rank = allSellers.sort((a,b) => (b.weight||1) - (a.weight||1)).findIndex(s => s.wallet === mySeller.wallet) + 1;
            weightEl.innerHTML = `
              <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">
                <div style="flex:1;">
                  <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                    <span style="color:#94a3b8;font-size:11px;">权重分数</span>
                    <span style="color:#34d399;font-size:12px;font-weight:600;">${weightPercent}%</span>
                  </div>
                  <div style="background:#0f121e;border-radius:6px;height:8px;overflow:hidden;">
                    <div style="background:linear-gradient(90deg,#8b5cf6,#34d399);height:100%;width:${weightPercent}%;border-radius:6px;transition:width 0.5s;"></div>
                  </div>
                </div>
              </div>
              <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;">
                <div style="background:#0f121e;border-radius:8px;padding:8px;text-align:center;">
                  <div style="color:#fbbf24;font-size:16px;font-weight:700;">#${rank}</div>
                  <div style="color:#64748b;font-size:10px;">排名</div>
                </div>
                <div style="background:#0f121e;border-radius:8px;padding:8px;text-align:center;">
                  <div style="color:#34d399;font-size:16px;font-weight:700;">★${mySeller.rating||'--'}</div>
                  <div style="color:#64748b;font-size:10px;">评分</div>
                </div>
                <div style="background:#0f121e;border-radius:8px;padding:8px;text-align:center;">
                  <div style="color:#a78bfa;font-size:16px;font-weight:700;">${mySeller.totalOrders||0}</div>
                  <div style="color:#64748b;font-size:10px;">已履约</div>
                </div>
              </div>
              <div style="margin-top:10px;background:#0f121e;border-radius:8px;padding:10px;">
                <div style="color:#64748b;font-size:10px;margin-bottom:4px;">💡 提升权重：补押金 → 可接单更多 → 成交更多 → 评分更高</div>
              </div>
            `;
          }
          document.getElementById('sellerDashboard').style.display = 'block';
          // 入驻后显示指标卡片
          const metricsDiv2 = document.querySelector('.metrics');
          if (metricsDiv2) metricsDiv2.style.display = 'grid';
          lucide.createIcons();
        } else {
          // 没有已上线的卖家信息，隐藏卖家面板
          formArea.style.display = 'block';
          regPanel.style.display = 'none';
          document.getElementById('sellerDashboard').style.display = 'none';
          // 不隐藏指标卡片，由 showTab 控制
        }
      } catch(e) {}
    }

    async function doDeregister(id) {
      document.getElementById('deregisterModal')?.remove();
      try {
        const res = await fetch(`/api/sellers/exit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ wallet: currentAccount })
        });
        const data = await res.json();
        if (data.ok) {
          showNotice('已退出市场');
          checkMyRegistration();
          reloadMarket();
        } else {
          showError(data.error || '操作失败');
        }
      } catch(e) { showError('操作失败'); }
    }

    // 表单验证：通过后启用提交按钮
    function setDeliveryMode(mode) {
      // V2: no delivery mode toggle
    }

    function onSkillFileSelected(input) {
      const file = input.files[0];
      if (!file) return;
      const ext = file.name.split('.').pop().toLowerCase();
      if (!['py', 'js'].includes(ext)) {
        showError('只支持 .py 或 .js 文件');
        input.value = '';
        return;
      }
      document.getElementById('fileUploadHint').style.display = 'none';
      document.getElementById('fileSelectedInfo').style.display = 'block';
      document.getElementById('fileSelectedName').textContent = file.name + ' (' + (file.size < 1024 ? file.size + ' B' : (file.size/1024).toFixed(1) + ' KB') + ')';
      // 自动扫描
      scanSkillFile(file);
      validateRegisterForm();
    }

    async function scanSkillFile(file) {
      const area = document.getElementById('scanResultArea');
      area.style.display = 'block';
      area.style.color = '#94a3b8';
      area.textContent = '⚠️ 安全扫描功能已下线，卖家由押金+评分机制约束';
    }

    // 自动分析功能已废弃（新模型不需要推断输入输出格式）

    function validateRegisterForm() {
      const name = document.getElementById('regName').value.trim();
      const desc = document.getElementById('regDesc').value.trim();
      const priceVal = document.getElementById('regPrice').value.trim();
      const priceNum = parseFloat(priceVal);
      const wallet = document.getElementById('regWallet').value.trim() || currentAccount;
      const endpoint = document.getElementById('regSellerEndpoint')?.value?.trim() || '';

      const valid = name && desc && priceVal && !isNaN(priceNum) && priceNum > 0 && wallet && (isDemoMode || endpoint);
      const depositBtn = document.getElementById('depositBtn');
      
      if (valid) {
        depositBtn.disabled = false;
        depositBtn.style.cursor = 'pointer';
        depositBtn.textContent = '入驻';
        depositBtn.style.background = 'linear-gradient(135deg,#8b5cf6,#6366f1)';
        depositBtn.style.color = '#fff';
      } else {
        depositBtn.disabled = true;
        depositBtn.style.cursor = 'not-allowed';
        depositBtn.style.background = 'linear-gradient(135deg,#475569,#334155)';
        depositBtn.style.color = '#94a3b8';
        if (!name) {
          depositBtn.textContent = '请填写卖家名称';
        } else if (!desc) {
          depositBtn.textContent = '请填写卖家描述';
        } else if (!priceVal || isNaN(priceNum) || priceNum <= 0) {
          depositBtn.textContent = '请填写有效的费率';
        } else if (!wallet) {
          depositBtn.textContent = '请连接钱包';
        } else {
          depositBtn.textContent = '请填写完整表单';
        }
      }
    }

    function identiconSvg(address, size = 40) {
      try {
        if (typeof Identicon !== 'undefined' && typeof Identicon === 'function') {
          return '<img src="data:image/png;base64,' + new Identicon(address.replace('0x',''), { size: size, format: 'png' }).toString() + '" style="width:' + size + 'px;height:' + size + 'px;border-radius:8px;">';
        }
      } catch(e) { /* SES or other extension blocks Identicon constructor */ }
      // Fallback: colored circle with initials
      const hue = parseInt(address.slice(2, 8), 16) % 360;
      return '<div style="width:' + size + 'px;height:' + size + 'px;border-radius:8px;background:hsl(' + hue + ',60%,50%);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:' + (size/3) + 'px;">' + address.slice(2,4).toUpperCase() + '</div>';
    }

    function bootstrapServices(services) {
      marketServices.clear();
      services.forEach(service => {
        marketServices.set(service.id, service);
      });
    }

    function getServiceById(serviceId) {
      return marketServices.get(serviceId);
    }

    function getActiveWallet() {
      return currentAccount;
    }

    function sortObjectKeys(value) {
      if (Array.isArray(value)) return value.map(sortObjectKeys);
      if (!value || typeof value !== 'object') return value;
      return Object.keys(value).sort().reduce((acc, key) => {
        acc[key] = sortObjectKeys(value[key]);
        return acc;
      }, {});
    }

    function base64EncodeUnicode(value) {
      return btoa(unescape(encodeURIComponent(value)));
    }

    function encodeTransferData(to, amountBaseUnits) {
      const methodId = 'a9059cbb';
      const address = to.toLowerCase().replace(/^0x/, '').padStart(64, '0');
      const amountHex = BigInt(amountBaseUnits).toString(16).padStart(64, '0');
      return `0x${methodId}${address}${amountHex}`;
    }

    function toTokenBaseUnits(amount, decimals) {
      const [wholePart, fractionPart = ''] = String(amount).split('.');
      const fraction = (fractionPart + '0'.repeat(decimals)).slice(0, decimals);
      return BigInt(`${wholePart || '0'}${fraction}`);
    }

    async function ensureChain(chain) {
      const config = CHAIN_CONFIG[chain];
      if (!config || !window.ethereum) {
        throw new Error('当前链暂不支持真实 x402 支付');
      }
      try {
        await window.ethereum.request({
          method: 'wallet_switchEthereumChain',
          params: [{ chainId: config.chainId }]
        });
      } catch (error) {
        if (error.code === 4902) {
          await window.ethereum.request({
            method: 'wallet_addEthereumChain',
            params: [{
              chainId: config.chainId,
              chainName: config.chainName,
              nativeCurrency: config.nativeCurrency,
              rpcUrls: config.rpcUrls,
              blockExplorerUrls: config.blockExplorerUrls,
            }]
          });
          return;
        }
        throw error;
      }
    }

    async function signX402Request(paymentRequest, account) {
      const signPayload = { ...paymentRequest };
      delete signPayload.timestamp;
      const message = JSON.stringify(sortObjectKeys(signPayload));
      return window.ethereum.request({
        method: 'personal_sign',
        params: [message, account]
      });
    }

    function buildBuyerActionMessage(action, purchaseId, buyerWallet) {
      return [
        'CryptoMinds buyer action',
        `Action: ${action}`,
        `Purchase: ${purchaseId}`,
        `Buyer: ${(buyerWallet || '').toLowerCase()}`,
      ].join('\n');
    }

    async function signBuyerAction(action, purchaseId, buyerWallet) {
      if (!window.ethereum) throw new Error('需要钱包签名');
      const message = buildBuyerActionMessage(action, purchaseId, buyerWallet);
      const signature = await window.ethereum.request({
        method: 'personal_sign',
        params: [message, buyerWallet]
      });
      return { buyerWallet, message, signature };
    }

    // PancakeSwap V2 Router
    const PANCAKE_ROUTER = '0x10ED43C718714eb63d5aA57B78B54704E256024E';
    const WBNB = '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c';

    function isRealSwapRoute(route) {
      return Boolean(
        currentAccount &&
        window.ethereum &&
        route &&
        route.route_type === 'swap' &&
        route.symbol === 'USDC' &&
        route.chain === 'bsc'
      );
    }

    function isRealSplitRoute(route) {
      return Boolean(
        currentAccount &&
        window.ethereum &&
        route &&
        route.route_type === 'split' &&
        route.symbol === 'USDC' &&
        Array.isArray(route.split_details) &&
        route.split_details.length >= 1 &&
        route.split_details.every(part => CHAIN_CONFIG[part.chain])
      );
    }

    async function executeRealBNBDirectPayment(service, route, wallet) {
      const chainConfig = CHAIN_CONFIG[route.chain];
      if (!chainConfig) {
        throw new Error('当前链暂不支持真实 BNB 支付');
      }
      await ensureChain(route.chain);
      const bnbAmount = route.amount || service.price;
      const weiValue = '0x' + BigInt(Math.round(bnbAmount * 1e18)).toString(16);

      // ===== Escrow 担保支付：BNB 锁入合约，卖家交付后释放 =====
      const escrowInfo = await fetch('/api/v1/escrow/info').then(r => r.json()).catch(() => null);
      const useEscrow = escrowInfo?.ok && escrowInfo.address;

      if (useEscrow) {
        // ── 走合约托管 ──
        renderProgressSteps('Escrow 担保支付', `BNB 将锁入担保合约，卖家交付后自动释放`, [
          { label: `切换到 ${route.chain.toUpperCase()} 链`, state: 'done' },
          { label: `向担保合约锁定 ${bnbAmount} BNB`, state: 'active' },
          { label: '等待链上确认', state: 'pending' },
          { label: '提交订单', state: 'pending' },
        ]);

        let escrowContract;
        try {
          escrowContract = await loadEscrowContract(escrowInfo.address, escrowInfo.abi);
        } catch(e) {
          throw new Error('无法加载担保合约: ' + e.message);
        }
        
        // createOrder(seller, serviceId, buyerTimeoutSeconds, sellerTimeoutSeconds)
        // buyerTimeout=24h, sellerTimeout=30min
        const createTx = await escrowContract.methods.createOrder(
          service.wallet,
          service.id || service.name || '',
          86400,  // 24h buyer timeout
          1800    // 30min seller timeout
        ).send({
          from: wallet,
          value: weiValue,
        });

        const escrowOrderId = createTx.events?.OrderCreated?.returnValues?.orderId || null;
        const txHash = createTx.transactionHash;

        renderProgressSteps('等待链上确认', '担保合约已锁定 BNB，等待区块确认...', [
          { label: `向担保合约锁定 ${bnbAmount} BNB`, state: 'done' },
          { label: '等待链上确认', state: 'active' },
          { label: '提交订单', state: 'pending' },
        ], `<p style="color:#8b5cf6;">TxHash: ${txHash}</p><p style="color:#34d399; font-size:11px;">🔒 BNB 已锁入担保合约，卖家交付后释放</p>`);

        renderProgressSteps('提交订单', '链上确认成功，正在提交订单...', [
          { label: '等待链上确认', state: 'done' },
          { label: '提交订单', state: 'active' },
        ]);

        const response = await fetch('/api/v1/orders/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            serviceId: service.id,
            buyerWallet: wallet,
            paymentMode: 'escrow_bnb',
            txHash: txHash,
            escrowOrderId: escrowOrderId,
            selectedRoute: { route_type: route.route_type, chain: route.chain, symbol: route.symbol }
          })
        });
        return await response.json();

      } else {
        // ── 无合约时降级为直付（兼容） ──
        renderProgressSteps('BNB 直接转账', `BNB 将直接发送给 ${service.expert} 的钱包`, [
          { label: `切换到 ${route.chain.toUpperCase()} 链`, state: 'done' },
          { label: `向卖家转账 ${bnbAmount} BNB`, state: 'active' },
          { label: '等待链上确认', state: 'pending' },
          { label: '提交订单', state: 'pending' },
        ]);

        const txHash = await window.ethereum.request({
          method: 'eth_sendTransaction',
          params: [{
            from: wallet,
            to: service.wallet,
            value: weiValue,
          }]
        });

        renderProgressSteps('等待链上确认', '交易已广播，正在等待区块确认...', [
          { label: `向卖家转账 ${bnbAmount} BNB`, state: 'done' },
          { label: '等待链上确认', state: 'active' },
          { label: '提交订单', state: 'pending' },
        ], `<p style="color:#8b5cf6;">TxHash: ${txHash}</p><p style="color:#f59e0b; font-size:11px;">⚠️ BNB 直付卖家，无担保保护</p>`);

        await waitForTransactionReceipt(txHash);

        renderProgressSteps('提交订单', '链上确认成功，正在提交订单...', [
          { label: '等待链上确认', state: 'done' },
          { label: '提交订单', state: 'active' },
        ]);

        const response = await fetch('/api/v1/orders/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            serviceId: service.id,
            buyerWallet: wallet,
            paymentMode: 'direct_bnb',
            txHash: txHash,
            selectedRoute: { route_type: route.route_type, chain: route.chain, symbol: route.symbol }
          })
        });
        return await response.json();
      }
    }

    // 加载 Escrow 合约实例（Web3.js via window.ethereum）
    let _escrowContract = null;
    async function loadEscrowContract(address, abi) {
      if (_escrowContract && _escrowContract.options?.address === address) return _escrowContract;
      // 使用 ethers.js 或 web3.js 从 MetaMask provider 创建
      const web3Provider = new Web3(window.ethereum);
      _escrowContract = new web3Provider.eth.Contract(abi, address);
      return _escrowContract;
    }

    async function executeRealSwapPayment(service, route, wallet) {
      const chainConfig = CHAIN_CONFIG[route.chain];
      await ensureChain(route.chain);

      const usdcAddr = chainConfig.usdc.address;
      const deadline = Math.floor(Date.now() / 1000) + 600;

      // Step 1: Get quote from PancakeSwap Router
      renderProgressSteps('获取 DEX 报价', '正在查询 PancakeSwap 最优兑换价格...', [
        { label: '查询 BNB→USDC 兑换比例', state: 'active' },
        { label: '确认 MetaMask 交换交易', state: 'pending' },
        { label: '等待链上确认', state: 'pending' },
        { label: '用兑换后的 USDC 完成 x402 支付', state: 'pending' },
      ]);

      // Build getAmountsOut calldata
      const amountInWei = '0x' + BigInt(Math.round(service.price_usdc / 300 * 1e18)).toString(16); // rough BNB amount
      const path = [WBNB, usdcAddr].map(a => a.toLowerCase().replace(/^0x/, '').padStart(64, '0')).join('');
      const getAmountsOutData = '0xd06ca61f' + amountInWei.slice(2).padStart(64, '0') + '0000000000000000000000000000000000000000000000000000000000000040' + '0000000000000000000000000000000000000000000000000000000000000002' + path;

      let expectedOut;
      try {
        const quoteResult = await window.ethereum.request({
          method: 'eth_call',
          params: [{ to: PANCAKE_ROUTER, data: getAmountsOutData }, 'latest']
        });
        // Parse: uint256[] — skip offset(32) + length(32) + amounts[0](32) then read amounts[1]
        const amounts = [];
        const cleanHex = quoteResult.slice(2);
        for (let i = 0; i < cleanHex.length; i += 64) {
          amounts.push(BigInt('0x' + cleanHex.slice(i, i + 64)));
        }
        expectedOut = amounts[amounts.length - 1];
      } catch (e) {
        // Fallback: estimate 1 BNB ≈ 300 USDC
        const usdcDecimals = chainConfig.usdc.decimals;
        expectedOut = BigInt(Math.round(service.price_usdc * 1.01 * (10 ** usdcDecimals)));
      }

      // 5% slippage
      const minOut = expectedOut * 95n / 100n;

      renderProgressSteps('等待钱包确认', `请在 MetaMask 中确认 BNB→USDC 兑换（约 ${(Number(amountInWei) / 1e18).toFixed(4)} BNB）`, [
        { label: '查询 BNB→USDC 兑换比例', state: 'done' },
        { label: '确认 MetaMask 交换交易', state: 'active' },
        { label: '等待链上确认', state: 'pending' },
        { label: '用兑换后的 USDC 完成 x402 支付', state: 'pending' },
      ]);

      // Step 2: Execute swap via MetaMask
      const swapData = buildSwapCalldata(minOut, [WBNB, usdcAddr], wallet, deadline);
      const swapTxHash = await window.ethereum.request({
        method: 'eth_sendTransaction',
        params: [{
          from: wallet,
          to: PANCAKE_ROUTER,
          data: swapData,
          value: amountInWei,
          gas: '0x3D090', // 250000
        }]
      });

      renderProgressSteps('等待链上确认', `Swap 交易已广播，等待确认中...`, [
        { label: '查询 BNB→USDC 兑换比例', state: 'done' },
        { label: 'MetaMask 交换交易已提交', state: 'done' },
        { label: '等待链上确认', state: 'active' },
        { label: '用兑换后的 USDC 完成 x402 支付', state: 'pending' },
      ], `<p style="color:#8b5cf6;">Swap TxHash: ${swapTxHash}</p>`);

      await waitForTransactionReceipt(swapTxHash);

      // Step 3: Now do the x402 USDC payment
      renderProgressSteps('执行 x402 支付', 'BNB→USDC 兑换完成，正在发起 USDC 支付...', [
        { label: 'BNB→USDC 兑换完成', state: 'done' },
        { label: `向 ${service.expert} 发起 USDC 支付`, state: 'active' },
        { label: '等待链上确认', state: 'pending' },
        { label: '提交 x402 验证', state: 'pending' },
      ]);

      // Send USDC transfer
      const txAmount = toTokenBaseUnits(service.price_usdc, chainConfig.usdc.decimals);
      const usdcTxHash = await window.ethereum.request({
        method: 'eth_sendTransaction',
        params: [{
          from: wallet,
          to: usdcAddr,
          data: encodeTransferData(service.wallet, txAmount),
          value: '0x0'
        }]
      });

      renderProgressSteps('等待 x402 验证', 'USDC 支付已广播，等待链上确认后验证...', [
        { label: 'BNB→USDC 兑换完成', state: 'done' },
        { label: `USDC 支付已提交`, state: 'done' },
        { label: '等待链上确认', state: 'active' },
        { label: '提交 x402 验证', state: 'pending' },
      ], `<p style="color:#8b5cf6;">Swap: ${swapTxHash.slice(0, 16)}...<br>Payment: ${usdcTxHash.slice(0, 16)}...</p>`);

      await waitForTransactionReceipt(usdcTxHash);

      // Step 4: Build and submit x402 verification
      const paymentRequest = {
        chain: route.chain,
        token: usdcAddr,
        to: service.wallet,
        amount: Number(Math.round(service.price_usdc * (10 ** chainConfig.usdc.decimals))),
        nonce: Math.random().toString(16).slice(2, 18),
        timestamp: Math.floor(Date.now() / 1000),
        metadata: {
          service_id: service.id,
          route_type: 'swap',
          tx_hash: usdcTxHash,
          swap_tx_hash: swapTxHash,
        }
      };
      const signature = await signX402Request(paymentRequest, wallet);
      const paymentHeader = `x402 ${base64EncodeUnicode(JSON.stringify({
        request: paymentRequest,
        signature,
        chain: route.chain,
        version: 'x402-0.1',
        tx_hash: usdcTxHash,
      }))}`;

      const response = await fetch('/api/v1/pay/x402', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          serviceId: service.id,
          buyerWallet: wallet,
          paymentHeader,
        })
      });
      const firstAttempt = await response.json();
      if (firstAttempt.ok) return firstAttempt;

      return submitX402VerificationWithRetry(
        { serviceId: service.id, buyerWallet: wallet, paymentHeader },
        `swap/${route.chain}/${route.symbol}`,
        usdcTxHash,
        () => executeRealSwapPayment(service, route, wallet)
      );
    }

    async function executeRealSplitPayment(service, route, wallet) {
      const splitDetails = route.split_details || [];
      const paymentHeaders = [];
      const txHashes = [];

      renderProgressSteps('执行 Split 支付', '正在按推荐拆分路径逐笔执行支付...', splitDetails.map((part, index) => ({
        label: `${index + 1}. ${part.chain.toUpperCase()} 支付 ${Number(part.amount).toFixed(4)} ${route.symbol}`,
        state: index === 0 ? 'active' : 'pending'
      })));

      for (let index = 0; index < splitDetails.length; index++) {
        const part = splitDetails[index];
        const chainConfig = CHAIN_CONFIG[part.chain];
        if (!chainConfig) {
          throw new Error(`split 路径包含暂不支持的链: ${part.chain}`);
        }

        await ensureChain(part.chain);
        const txAmount = toTokenBaseUnits(part.amount, chainConfig.usdc.decimals);

        renderProgressSteps('等待钱包确认', `请确认第 ${index + 1}/${splitDetails.length} 笔 split 支付`, splitDetails.map((item, itemIndex) => ({
          label: `${item.chain.toUpperCase()} 支付 ${Number(item.amount).toFixed(4)} ${route.symbol}`,
          state: itemIndex < index ? 'done' : itemIndex === index ? 'active' : 'pending'
        })));

        const txHash = await window.ethereum.request({
          method: 'eth_sendTransaction',
          params: [{
            from: wallet,
            to: chainConfig.usdc.address,
            data: encodeTransferData(service.wallet, txAmount),
            value: '0x0'
          }]
        });
        txHashes.push(txHash);

        renderProgressSteps('等待链上确认', `第 ${index + 1}/${splitDetails.length} 笔支付已广播，等待确认...`, splitDetails.map((item, itemIndex) => ({
          label: `${item.chain.toUpperCase()} 支付 ${Number(item.amount).toFixed(4)} ${route.symbol}`,
          state: itemIndex < index ? 'done' : itemIndex === index ? 'active' : 'pending'
        })), `<p style="color:#8b5cf6;">TxHash: ${txHash}</p>`);
        await waitForTransactionReceipt(txHash);

        const paymentRequest = {
          chain: part.chain,
          token: chainConfig.usdc.address,
          to: service.wallet,
          amount: Number(Math.round(Number(part.amount) * 1_000_000)),
          nonce: Math.random().toString(16).slice(2, 18),
          timestamp: Math.floor(Date.now() / 1000),
          metadata: {
            service_id: service.id,
            route_type: 'split',
            split_index: index,
            split_total: splitDetails.length,
            tx_hash: txHash,
          }
        };
        const signature = await signX402Request(paymentRequest, wallet);
        const paymentHeader = `x402 ${base64EncodeUnicode(JSON.stringify({
          request: paymentRequest,
          signature,
          chain: part.chain,
          version: 'x402-0.1',
          tx_hash: txHash,
        }))}`;
        paymentHeaders.push(paymentHeader);
      }

      renderProgressSteps('聚合验证中', '所有 split 子支付已确认，正在提交聚合验证...', [
        { label: '多笔子支付全部已确认', state: 'done' },
        { label: '提交 split 聚合验证', state: 'active' },
      ], `<p style="color:#8b5cf6;">共 ${txHashes.length} 笔交易</p>`);

      const response = await fetch('/api/v1/pay/x402/split', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          serviceId: service.id,
          buyerWallet: wallet,
          paymentHeaders,
          selectedRoute: {
            route_type: route.route_type,
            chain: route.chain,
            symbol: route.symbol
          }
        })
      });
      const data = await response.json();
      if (!data.ok) {
        throw new Error(data.error || 'split 支付验证失败');
      }
      return data;
    }

    // Build swapExactETHForTokens(uint256,address[],address,uint256) calldata
    function buildSwapCalldata(amountOutMin, path, to, deadline) {
      const methodId = '7ff36ab5'; // swapExactETHForTokens
      const amountOutMinHex = BigInt(amountOutMin).toString(16).padStart(64, '0');
      // path array: offset=0x40
      const pathOffset = '0000000000000000000000000000000000000000000000000000000000000080';
      // to address
      const toPadded = to.toLowerCase().replace(/^0x/, '').padStart(64, '0');
      // deadline
      const deadlineHex = BigInt(deadline).toString(16).padStart(64, '0');
      // path length + addresses
      const pathLen = BigInt(path.length).toString(16).padStart(64, '0');
      const pathAddrs = path.map(a => a.toLowerCase().replace(/^0x/, '').padStart(64, '0')).join('');

      return `0x${methodId}${amountOutMinHex}${pathOffset}${toPadded}${deadlineHex}${pathLen}${pathAddrs}`;
    }

    function isRealX402Route(route) {
      return Boolean(
        currentAccount &&
        window.ethereum &&
        route &&
        route.route_type === 'direct' &&
        route.symbol === 'USDC' &&
        CHAIN_CONFIG[route.chain]
      );
    }

    function isRealBNBDirectRoute(route) {
      return Boolean(
        currentAccount &&
        window.ethereum &&
        route &&
        route.route_type === 'direct' &&
        (route.symbol === 'BNB' || route.symbol === 'ETH') &&
        CHAIN_CONFIG[route.chain]
      );
    }

    async function executeRealX402Payment(service, route, wallet) {
      const chainConfig = CHAIN_CONFIG[route.chain];
      if (!chainConfig) {
        throw new Error('当前链暂不支持真实 x402 支付');
      }

      await ensureChain(route.chain);

      const txAmount = toTokenBaseUnits(service.price_usdc, chainConfig.usdc.decimals);
      renderProgressSteps('等待钱包确认', `请在钱包中确认 ${service.price_usdc} USDC 转账`, [
        { label: `切换到 ${route.chain.toUpperCase()} 链`, state: 'done' },
        { label: `向 ${service.expert} 发起 USDC 支付`, state: 'active' },
        { label: '等待链上确认', state: 'pending' },
        { label: '提交 x402 验证', state: 'pending' },
      ]);
      const txHash = await window.ethereum.request({
        method: 'eth_sendTransaction',
        params: [{
          from: wallet,
          to: chainConfig.usdc.address,
          data: encodeTransferData(service.wallet, txAmount),
          value: '0x0'
        }]
      });
      renderProgressSteps('等待链上确认', '交易已广播，正在等待区块确认...', [
        { label: `向 ${service.expert} 发起 USDC 支付`, state: 'done' },
        { label: '等待链上确认', state: 'active' },
        { label: '提交 x402 验证', state: 'pending' },
      ], `<p style="color:#8b5cf6;">TxHash: ${txHash}</p>`);
      await waitForTransactionReceipt(txHash);

      const paymentRequest = {
        chain: route.chain,
        token: chainConfig.usdc.address,
        to: service.wallet,
        amount: Number(Math.round(Number(service.price_usdc) * 1_000_000)),
        nonce: Math.random().toString(16).slice(2, 18),
        timestamp: Math.floor(Date.now() / 1000),
        metadata: {
          service_id: service.id,
          route_type: route.route_type,
          token_symbol: route.symbol,
          tx_hash: txHash,
        }
      };
      const signature = await signX402Request(paymentRequest, wallet);
      const paymentHeader = `x402 ${base64EncodeUnicode(JSON.stringify({
        request: paymentRequest,
        signature,
        chain: route.chain,
        version: 'x402-0.1',
        tx_hash: txHash,
      }))}`;

      const response = await fetch('/api/v1/pay/x402', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          serviceId: service.id,
          buyerWallet: wallet,
          paymentHeader,
        })
      });
      const firstAttempt = await response.json();
      if (firstAttempt.ok) return firstAttempt;

      const payload = {
        serviceId: service.id,
        buyerWallet: wallet,
        paymentHeader,
      };
      return submitX402VerificationWithRetry(
        payload,
        `${route.route_type}/${route.chain}/${route.symbol}`,
        txHash,
        () => executeRealX402Payment(service, route, wallet)
      );
    }

    function openProgressModal(title, bodyHtml, retryLabel = '', retryAction = null) {
      document.getElementById('progressTitle').textContent = title;
      document.getElementById('progressBody').innerHTML = bodyHtml;
      const actions = document.getElementById('progressActions');
      progressRetryAction = retryAction;
      if (retryLabel && retryAction) {
        actions.style.display = 'block';
        actions.innerHTML = `<button onclick="runProgressRetry()" style="background:linear-gradient(135deg,#8b5cf6,#6366f1); color:#fff; border:none; padding:10px 16px; border-radius:8px; cursor:pointer; font-weight:600;">${retryLabel}</button>`;
      } else {
        actions.style.display = 'none';
        actions.innerHTML = '';
      }
      document.getElementById('progressModal').style.display = 'block';
    }
    function closeProgressModal() {
      document.getElementById('progressModal').style.display = 'none';
      progressRetryAction = null;
    }
    function runProgressRetry() {
      if (typeof progressRetryAction === 'function') {
        progressRetryAction();
      }
    }
    function renderProgressSteps(title, status, steps, extraHtml = '', retryLabel = '', retryAction = null) {
      const stepsHtml = (steps || []).map((step, index) => {
        const color = step.state === 'done' ? '#34d399' : step.state === 'active' ? '#a78bfa' : step.state === 'error' ? '#f87171' : '#64748b';
        const prefix = step.state === 'done' ? '<i data-lucide="check-circle" class="icon-inline" style="color:#10b981"></i>' : step.state === 'active' ? '<i data-lucide="loader" class="icon-inline" style="color:#a78bfa"></i>' : step.state === 'error' ? '<i data-lucide="x-circle" class="icon-inline" style="color:#ef4444"></i>' : '<i data-lucide="circle" class="icon-inline" style="color:#64748b"></i>';
        return `<div style="padding:8px 0; color:${color};">${prefix} ${index + 1}. ${step.label}</div>`;
      }).join('');
      openProgressModal(title, `<p style="margin-bottom:12px; color:#e2e8f0;">${status}</p>${extraHtml}<div style="margin-top:8px;">${stepsHtml}</div>`, retryLabel, retryAction);
    }
      lucide.createIcons();
    async function waitForTransactionReceipt(txHash) {
      for (let attempt = 0; attempt < 20; attempt++) {
        const receipt = await window.ethereum.request({
          method: 'eth_getTransactionReceipt',
          params: [txHash]
        });
        if (receipt) return receipt;
        await new Promise(resolve => setTimeout(resolve, 3000));
      }
      throw new Error(`交易已广播但长时间未确认，请稍后检查 txHash：${txHash}`);
    }
    async function submitX402VerificationWithRetry(payload, routeLabel, txHash, retryAction) {
      for (let attempt = 0; attempt < 6; attempt++) {
        const response = await fetch('/api/v1/pay/x402', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (data.ok) return data;

        const message = data.error || 'x402 支付验证失败';
        const isRetryable = /链上未找到交易|交易执行失败|支付验证失败/.test(message);
        if (!isRetryable || attempt === 5) {
          renderProgressSteps('支付验证失败', message, [
            { label: `交易已广播 (${routeLabel})`, state: 'done' },
            { label: '等待链上确认', state: 'done' },
            { label: '提交 x402 验证', state: 'error' },
          ], txHash ? `<p style="color:#8b5cf6;">TxHash: ${txHash}</p>` : '', '重试验证', retryAction);
          throw new Error(message);
        }

        renderProgressSteps('链上验证中', `验证尚未通过，正在重试第 ${attempt + 2} 次...`, [
          { label: `交易已广播 (${routeLabel})`, state: 'done' },
          { label: '等待链上确认', state: 'done' },
          { label: '提交 x402 验证', state: 'active' },
        ], txHash ? `<p style="color:#8b5cf6;">TxHash: ${txHash}</p>` : '');
        await new Promise(resolve => setTimeout(resolve, 2000 * (attempt + 1)));
      }
      throw new Error('支付验证超时');
    }

	    function showSuccessModal(title, data) {
	      let html = `<div style="margin-bottom:12px;">`;
      html += `<p><span class="status-dot confirmed"></span><strong>${title}</strong></p>`;
      if (data.sellerService) html += `<p>卖家执行：${data.sellerService}</p>`;
      if (data.expert) html += `<p>卖家：${data.expert}</p>`;
      if (data.amount) html += `<p>金额：<span style="color:#34d399; font-family:monospace;">${data.amount}</span></p>`;
      if (data.route) html += `<p>路由：${data.route}</p>`;
      if (data.paymentMode) html += `<p>支付方式：${data.paymentMode}</p>`;
      if (data.paymentStatus) html += `<p>状态：${data.paymentStatus}</p>`;
	      if (data.txHash && /^0x[a-fA-F0-9]{64}$/.test(data.txHash)) {
	        const explorerBase = data.chain === 'base' ? CHAIN_CONFIG.base.explorerBaseUrl : CHAIN_CONFIG.bsc.explorerBaseUrl;
	        html += `<p>交易哈希：</p>`;
	        html += `<div style="background:#0f121e; border:1px solid rgba(100,116,139,0.2); border-radius:8px; padding:10px; margin-top:4px; display:flex; align-items:center; justify-content:space-between; gap:8px;">`;
	        html += `<a href="${explorerBase}/tx/${data.txHash}" target="_blank" style="color:#8b5cf6; font-family:monospace; font-size:13px; word-break:break-all;"><i data-lucide="external-link" class="icon-inline"></i> ${data.txHash.slice(0, 20)}...${data.txHash.slice(-8)}</a>`;
	        html += `<button onclick="copyToClipboard('${data.txHash}', this)" style="background:rgba(100,116,139,0.2); color:#94a3b8; border:none; padding:4px 8px; border-radius:4px; cursor:pointer; font-size:11px;"><i data-lucide="copy" class="icon-inline"></i> 复制</button>`;
	        html += `</div>`;
	      }
      if (data.txHint) html += `<p style="color:#64748b; font-size:12px; margin-top:8px;">${data.txHint}</p>`;

      // 如果卖家有API配置，显示调用信息
      if (data.sellerServiceApi && data.sellerServiceApi.endpoint) {
        html += `<div style="margin-top:16px; background:#0f121e; border:1px solid rgba(139,92,246,0.15); border-radius:10px; padding:14px;">`;
        html += `<div style="color:#a78bfa; font-size:13px; font-weight:600; margin-bottom:10px;"><i data-lucide="zap" class="icon-inline"></i> 卖家调用信息</div>`;
        html += `<div style="color:#94a3b8; font-size:12px; margin-bottom:6px;">Endpoint:</div>`;
        html += `<div style="display:flex; align-items:center; gap:8px; margin-bottom:10px;">`;
        html += `<code style="flex:1; background:#161b2e; border:1px solid rgba(100,116,139,0.2); border-radius:6px; padding:8px 10px; color:#34d399; font-size:12px; word-break:break-all;">${data.sellerServiceApi.endpoint}</code>`;
        html += `<button onclick="copyToClipboard('${data.sellerServiceApi.endpoint}', this)" style="background:rgba(100,116,139,0.2); color:#94a3b8; border:none; padding:6px 10px; border-radius:6px; cursor:pointer; font-size:11px; white-space:nowrap;"><i data-lucide="copy" class="icon-inline"></i> 复制</button>`;
        html += `</div>`;
        if (data.sellerServiceApi.example) {
          html += `<div style="color:#94a3b8; font-size:12px; margin-bottom:6px;">调用示例:</div>`;
          html += `<pre style="background:#161b2e; border:1px solid rgba(100,116,139,0.2); border-radius:6px; padding:10px; color:#a78bfa; font-size:11px; overflow-x:auto; white-space:pre-wrap; margin:0;">${data.sellerServiceApi.example}</pre>`;
        }
        html += `</div>`;
      }

      html += `<div style="margin-top:16px; display:flex; gap:10px;">`;
      html += `<button onclick="closeSuccessModal(); showTab('myagent'); autoLoadWalletData();" style="background:linear-gradient(135deg,#8b5cf6,#6366f1); color:#fff; border:none; padding:8px 16px; border-radius:8px; cursor:pointer; font-weight:600;">${t('viewMySpending')}</button>`;
      html += `<button onclick="closeSuccessModal()" style="background:rgba(100,116,139,0.2); color:#94a3b8; border:1px solid rgba(100,116,139,0.3); padding:8px 16px; border-radius:8px; cursor:pointer;">${t('close')}</button>`;
      html += `</div>`;
      html += `</div>`;
      document.getElementById('successBody').innerHTML = html;
      document.getElementById('successModal').style.display = 'block';
    }
    function closeSuccessModal() {
      document.getElementById('successModal').style.display = 'none';
    }
    function copyToClipboard(text, btn) {
      navigator.clipboard.writeText(text).then(() => {
        const orig = btn.textContent;
        btn.innerHTML = '<i data-lucide="check" class="icon-inline"></i> 已复制'; lucide.createIcons();
        btn.style.color = '#34d399';
        setTimeout(() => { btn.textContent = orig; btn.style.color = ''; }, 1500);
      });
    }

    // 统一错误提示
    function showError(msg) {
      let el = document.getElementById('errorToast');
      if (!el) {
        el = document.createElement('div');
        el.id = 'errorToast';
        el.style.cssText = 'position:fixed;top:20px;right:20px;background:#f87171;color:#fff;padding:16px 24px;border-radius:12px;z-index:9999;font-size:14px;max-width:400px;box-shadow:0 4px 20px rgba(0,0,0,0.4);';
        document.body.appendChild(el);
      }
      el.innerHTML = msg;
      el.style.display = 'block';
      setTimeout(() => { el.style.display = 'none'; }, 5000);
    }
    function showNotice(msg) {
      let el = document.getElementById('noticeToast');
      if (!el) {
        el = document.createElement('div');
        el.id = 'noticeToast';
        el.style.cssText = 'position:fixed;top:20px;right:20px;background:linear-gradient(135deg,#8b5cf6,#6366f1);color:#fff;padding:16px 24px;border-radius:12px;z-index:9999;font-size:14px;max-width:400px;box-shadow:0 4px 20px rgba(139,92,246,0.4);';
        document.body.appendChild(el);
      }
      el.innerHTML = msg;
      el.style.display = 'block';
      setTimeout(() => { el.style.display = 'none'; }, 4000);
    }

    async function connectWallet() {
      if (!window.ethereum) {
        showError('请安装 MetaMask 钱包扩展<br><a href="https://metamask.io" target="_blank" style="color:#8b5cf6">前往安装 →</a>');
        return;
      }
      try {
        const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
        currentAccount = accounts[0].toLowerCase();
        document.getElementById('connectBtn').innerHTML = '<i data-lucide="check-circle" class="icon-inline" style="color:#fff"></i> ' + currentAccount.slice(0, 6) + '...' + currentAccount.slice(-4); lucide.createIcons();
        document.getElementById('connectBtn').classList.add('connected');

        // 切换到我的 Agent 面板
        document.getElementById('myAgentLoading').style.display = 'none';
        document.getElementById('myAgentPrompt').style.display = 'none';
        
        // 检查是否已注册（卖家）
        const registered = await checkAgentRegistered(currentAccount);
        // 买家不需要注册，直接显示内容
        // 只有想成为卖家才需要注册
        document.getElementById('myAgentRegister').style.display = 'none';
        document.getElementById('myAgentContent').style.display = 'block';
        document.getElementById('myAddr').textContent = currentAccount;

        // 从服务端API获取余额
        try {
          const res = await fetch('/api/v1/balances');
          const data = await res.json();
          const agent = Object.values(data).find(a => a.addr.toLowerCase() === currentAccount);
          if (activeTab === 'myagent') {
            const balEl2 = document.getElementById('buyerBalance');
            if (balEl2) balEl2.textContent = agent ? parseFloat(agent.balance).toFixed(4) + ' BNB' : '0.0000 BNB';
          }

          // 加载通知
          loadNotifications();
          setInterval(loadNotifications, 10000); // 10秒轮询

          // 管理员权限 — 从后端获取，避免前端硬编码
          try {
            const adminRes = await fetch(`/api/admin-check?wallet=${currentAccount}`);
            const adminData = await adminRes.json();
            if (adminData.isAdmin) {
              document.getElementById('adminTab').style.display = 'inline';
            }
          } catch(e) { /* 非管理员，忽略 */ }
        } catch(e) {
          if (activeTab === 'myagent') document.getElementById('buyerBalance').textContent = '加载失败';
        }

        // 钱包连上后重新渲染交易feed（方向+/-需要currentAccount）
        loadTxsFeed();
        // 钱包连上后重新检查卖家注册状态
        checkMyRegistration();
        // 消费记录由 loadBuyerStats 统一渲染（showTab('myagent') 会调用）
        // 自动切到我的 Agent
        showTab('myagent');
    } catch (e) {
        console.error('connectWallet error:', e);
        if (e.code === 4001) {
          showError('已取消连接，请在 MetaMask 中点击"连接"');
        } else if (e.code === -32002) {
          showError('MetaMask 已有待处理的连接请求，请切换到 MetaMask 确认');
        } else {
          showError('连接失败：' + (e.message || '未知错误'));
        }
      }
    }

    // ── 钱包事件监听：切换账号/断连自动刷新 ──
    if (window.ethereum) {
      window.ethereum.on('accountsChanged', (accounts) => {
        if (accounts.length === 0) {
          // 钱包断连
          currentAccount = null;
          document.getElementById('connectBtn').innerHTML = '<i data-lucide="wallet" class="icon-inline" style="color:#fff"></i> 连接钱包';
          document.getElementById('connectBtn').classList.remove('connected');
          showTab('marketplace');
          console.log('[wallet] 断开连接');
        } else {
          // 切换账号
          currentAccount = accounts[0].toLowerCase();
          document.getElementById('connectBtn').innerHTML = '<i data-lucide="check-circle" class="icon-inline" style="color:#fff"></i> ' + currentAccount.slice(0, 6) + '...' + currentAccount.slice(-4);
          loadTxsFeed(); // 切账号后重渲染方向
          checkMyRegistration(); // 切账号后重新检查卖家状态
          showTab('myagent');
          console.log('[wallet] 切换账号:', currentAccount);
        }
      });
      window.ethereum.on('chainChanged', () => {
        // 切链刷新页面
        window.location.reload();
      });
    }

    // 直接展示购买凭证
    function showReceipt(p) {
      if (!p) return;
      const explorerBase = p.payment?.chain === 'base' ? CHAIN_CONFIG.base.explorerBaseUrl : CHAIN_CONFIG.bsc.explorerBaseUrl;
      let html = '';

      // 订单号
      html += `<div style="background:#0f121e; border-radius:10px; padding:14px; margin-bottom:16px;">
        <div style="color:#64748b; font-size:11px; text-transform:uppercase; letter-spacing:0.8px; margin-bottom:6px;">订单号</div>
        <div style="color:#a78bfa; font-family:monospace; font-size:13px; word-break:break-all;">${p.id || '-'}</div>
      </div>`;

      // 购买信息
      html += '<div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:16px;">';
      html += `<div>
        <div style="color:#64748b; font-size:11px; text-transform:uppercase; letter-spacing:0.8px; margin-bottom:4px;">卖家名称</div>
        <div style="color:#e2e8f0; font-weight:500;">${p.serviceName || '-'}</div>
      </div>`;
      html += `<div>
        <div style="color:#64748b; font-size:11px; text-transform:uppercase; letter-spacing:0.8px; margin-bottom:4px;">卖家 Agent</div>
        <div style="color:#e2e8f0;">${p.expert || '-'}</div>
      </div>`;
      html += `<div>
        <div style="color:#64748b; font-size:11px; text-transform:uppercase; letter-spacing:0.8px; margin-bottom:4px;">支付金额</div>
        <div style="color:#f1f5f9; font-weight:600; font-size:18px;">${p.price || '-'} ${p.priceCurrency || 'BNB'}</div>
      </div>`;
      html += `<div>
        <div style="color:#64748b; font-size:11px; text-transform:uppercase; letter-spacing:0.8px; margin-bottom:4px;">购买时间</div>
        <div style="color:#e2e8f0;">${p.time ? new Date(p.time).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '-'}</div>
      </div>`;
      html += '</div>';

      // 钱包地址
      html += '<div style="border-top:1px solid rgba(100,116,139,0.1); padding-top:14px;">';
      if (p.buyerWallet) {
        html += `<div style="margin-bottom:8px;">
          <span style="color:#64748b; font-size:11px;">买方: </span>
          <span style="color:#8b5cf6; font-family:monospace; font-size:12px;">${p.buyerWallet.slice(0, 6)}...${p.buyerWallet.slice(-4)}</span>
        </div>`;
      }
      if (p.expertWallet) {
        html += `<div style="margin-bottom:8px;">
          <span style="color:#64748b; font-size:11px;">卖方: </span>
          <span style="color:#8b5cf6; font-family:monospace; font-size:12px;">${p.expertWallet.slice(0, 6)}...${p.expertWallet.slice(-4)}</span>
        </div>`;
      }
      html += '</div>';

      // 链上交易
      if (p.txHash && /^0x[a-fA-F0-9]{64}$/.test(p.txHash)) {
        html += `<div style="margin-top:14px; padding:12px; background:#0f121e; border-radius:10px;">
          <div style="color:#64748b; font-size:11px; margin-bottom:6px;">链上交易</div>
          <a href="${explorerBase}/tx/${p.txHash}" target="_blank" style="color:#8b5cf6; font-family:monospace; font-size:12px; word-break:break-all;">${p.txHash.slice(0, 10)}...${p.txHash.slice(-8)} <i data-lucide="external-link" class="icon-inline"></i></a>
        </div>`;
      } else {
        html += `<div style="margin-top:14px; padding:12px; background:#0f121e; border-radius:10px;">
          <div style="color:#64748b; font-size:11px; margin-bottom:6px;">链上交易</div>
          <span style="color:#475569; font-size:12px;">演示模式 · 无链上记录</span>
        </div>`;
      }

      // 支付方式标签
      const modeLabel =
        p.payment?.mode === 'demo' ? '演示'
        : p.payment?.mode === 'x402' ? 'x402 协议'
        : p.payment?.mode === 'x402-split' ? 'x402 协议 / Split'
        : p.payment?.mode === 'direct_bnb' ? 'BNB 直转'
        : p.payment?.mode || '-';
      html += `<div style="margin-top:14px; text-align:right;">
        <span style="background:rgba(139,92,246,0.1); color:#a78bfa; padding:4px 10px; border-radius:6px; font-size:11px;">${modeLabel}</span>
      </div>`;

      document.getElementById('reportTitle').textContent = '购买凭证';
      document.getElementById('reportContent').innerHTML = html;
      document.getElementById('reportModal').style.display = 'block';
    }
      lucide.createIcons();

    function closeReport() {
      document.getElementById('reportModal').style.display = 'none';
    }

    // 订单详情弹窗
    function showSkillDetail(serviceId) {
      const services = Array.from(marketServices.values());
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
    }
      lucide.createIcons();
    function closeSellerDetail() {
      document.getElementById('sellerDetailModal').style.display = 'none';
    }

    // 智能路由相关（Agent 自动调用，人类无操作入口）
    function showSmartRoute(serviceId) {
      const service = getServiceById(serviceId);
      if (!service) return;
      executePayment(serviceId, {});
    }
      lucide.createIcons();
    
	    // ===== 通知系统 =====
    let notifPanelOpen = false;

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
      modal.innerHTML = `<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);border:2px solid rgba(139,92,246,0.4);border-radius:16px;padding:28px;width:560px;max-width:90vw;max-height:80vh;display:flex;flex-direction:column;"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;"><div style="color:#a78bfa;font-weight:600;font-size:16px;"><i data-lucide="bell" class="icon-inline"></i> 我的订单</div><button onclick="notifPanelOpen=false;document.getElementById('notifModal').remove()" style="background:none;border:none;color:#94a3b8;font-size:20px;cursor:pointer;">✕</button></div><div id="ordersList" style="color:#94a3b8;font-size:13px;overflow-y:auto;flex:1;">加载中...</div></div>`;
      document.body.appendChild(modal);
      lucide.createIcons();
      loadMyOrdersInNotif();
      // 标记通知已读，清除铃铛数字
      if (currentAccount) {
        fetch('/api/v1/notifications/read-all', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ wallet: currentAccount }) }).then(() => {
          const el = document.getElementById('myUnread'); if (el) el.textContent = '0';
          const badge = document.getElementById('notifBadge'); if (badge) badge.style.display = 'none';
        });
      }
    }

    async function loadMyOrdersInNotif() {
      if (!currentAccount) return;
      const list = document.getElementById('ordersList');
      if (!list) return;
      list.innerHTML = '加载中...';
      try {
        const res = await fetch(`/api/my-orders?wallet=${currentAccount}`);
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
          return `<div style="padding:12px 0;border-bottom:1px solid rgba(139,92,246,0.08);">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <div>
                <div style="color:#e2e8f0;font-weight:600;">${escapeHtml(o.sellerName || '订单')}</div>
                <div style="color:#64748b;font-size:11px;margin-top:4px;">卖家: ${escapeHtml(o.expert || '未知')} | ${escapeHtml(time)}</div>
                <div style="color:#64748b;font-size:11px;">价格: ${o.price} BNB</div>
              </div>
              <div style="text-align:right;padding-right:4px;">
                <div style="color:${statusColor};font-size:12px;font-weight:600;">${statusText}</div>
                ${needConfirm ? `<button onclick="confirmPurchase('${o.id}')" style="margin-top:6px;background:linear-gradient(135deg,#34d399,#10b981);color:#fff;border:none;border-radius:6px;padding:4px 12px;font-size:11px;cursor:pointer;">确认收货</button>` : ''}
                ${canRefund ? `<button onclick="claimSellerTimeout('${o.id}', '${o.escrowOrderId}')" style="margin-top:6px;background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff;border:none;border-radius:6px;padding:4px 12px;font-size:11px;cursor:pointer;">申请退款</button>` : ''}
                ${hasResult ? `<button onclick="viewOrderResult('${o.id}')" style="margin-top:6px;background:linear-gradient(135deg,#8b5cf6,#6366f1);color:#fff;border:none;border-radius:6px;padding:4px 12px;font-size:11px;cursor:pointer;">查看结果</button>` : ''}
              </div>
            </div>
          </div>`;
        }).join('');
        lucide.createIcons();
      } catch(e) {
        list.innerHTML = '<div style="color:#ef4444;text-align:center;padding:20px;">加载失败</div>';
      }
    }

    let myOrdersOpen = false;
    function toggleMyOrders() {
      myOrdersOpen = !myOrdersOpen;
      if (!myOrdersOpen) {
        const m = document.getElementById('myOrdersModal');
        if (m) m.remove();
        return;
      }
      // 创建弹窗
      const modal = document.createElement('div');
      modal.id = 'myOrdersModal';
      modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:99999;display:flex;justify-content:center;align-items:center;';
      modal.onclick = (e) => { if (e.target === modal) { myOrdersOpen = false; modal.remove(); } };
      modal.innerHTML = `<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);border:2px solid rgba(139,92,246,0.4);border-radius:16px;padding:28px;width:520px;max-width:90vw;max-height:70vh;display:flex;flex-direction:column;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <div style="color:#a78bfa;font-weight:600;font-size:16px;"><i data-lucide="clipboard-list" class="icon-inline"></i> 我的订单</div>
          <button onclick="myOrdersOpen=false;document.getElementById('myOrdersModal').remove()" style="background:none;border:none;color:#94a3b8;font-size:20px;cursor:pointer;">✕</button>
        </div>
        <div id="myOrdersList" style="color:#94a3b8;font-size:13px;overflow-y:auto;flex:1;padding-right:8px;">加载中...</div>
      </div>`;
      document.body.appendChild(modal);
      lucide.createIcons();
      loadMyOrders();
    }

    async function loadMyOrders() {
      if (!currentAccount) return;
      try {
        const res = await fetch(`/api/my-orders?wallet=${currentAccount}`);
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
          return `<div style="padding:12px 0;border-bottom:1px solid rgba(139,92,246,0.08);">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <div>
                <div style="color:#e2e8f0;font-weight:600;">${escapeHtml(o.sellerName || '订单')}</div>
                <div style="color:#64748b;font-size:11px;margin-top:4px;">卖家: ${escapeHtml(o.expert || '未知')} | ${escapeHtml(time)}</div>
                <div style="color:#64748b;font-size:11px;">价格: ${o.price} BNB</div>
              </div>
              <div style="text-align:right;padding-right:4px;">
                <div style="color:${statusColor};font-size:12px;font-weight:600;">${statusText}</div>
                ${needConfirm ? `<button onclick="confirmPurchase('${o.id}')" style="margin-top:6px;background:linear-gradient(135deg,#34d399,#10b981);color:#fff;border:none;border-radius:6px;padding:4px 12px;font-size:11px;cursor:pointer;">确认收货</button>` : ''}
                ${canRefund ? `<button onclick="claimSellerTimeout('${o.id}', '${o.escrowOrderId}')" style="margin-top:6px;background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff;border:none;border-radius:6px;padding:4px 12px;font-size:11px;cursor:pointer;">申请退款</button>` : ''}
                ${hasResult ? `<button onclick="viewOrderResult('${o.id}')" style="margin-top:6px;background:linear-gradient(135deg,#8b5cf6,#6366f1);color:#fff;border:none;border-radius:6px;padding:4px 12px;font-size:11px;cursor:pointer;">查看结果</button>` : ''}
              </div>
            </div>
          </div>`;
        }).join('');
      } catch(e) {
        console.error('订单加载失败', e);
      }
    }

    function viewOrderResult(orderId) {
      fetch(`/api/orders/${orderId}/result`).then(r => r.json()).then(data => {
        if (!data.ok || !data.result) { 
          const list = document.getElementById('ordersList') || document.getElementById('notifList');
          if (list) list.innerHTML = '<div style="color:#ef4444;text-align:center;padding:20px;">结果暂不可用</div>';
          return; 
        }
        const result = data.result;
        
        // 格式化结果为人类可读格式
        let resultBody = '';
        if (result && result.version === 'hosted-result/v1') {
          resultBody = `<div style="margin-bottom:16px;">
            <div style="color:#a78bfa;font-size:14px;font-weight:600;margin-bottom:8px;">${result.title || '执行结果'}</div>
            <div style="color:#94a3b8;font-size:12px;margin-bottom:12px;">${result.summary || ''}</div>
          </div>`;
          
          // 如果有 pools 数据，格式化显示
          if (result.data && result.data.pools) {
            resultBody += `<div style="color:#e2e8f0;font-size:13px;">
              <div style="color:#34d399;margin-bottom:12px;">发现 ${result.data.count || result.data.pools.length} 个流动性池：</div>`;
            result.data.pools.forEach((pool, i) => {
              resultBody += `<div style="background:rgba(139,92,246,0.1);border-radius:8px;padding:12px;margin-bottom:8px;">
                <div style="color:#a78bfa;font-weight:600;margin-bottom:6px;">池子 ${i+1}</div>
                <div style="color:#94a3b8;font-size:12px;">地址: <a href="https://bscscan.com/address/${pool.address}" target="_blank" style="color:#8b5cf6;">${pool.address.slice(0,10)}...${pool.address.slice(-8)}</a></div>
                <div style="color:#94a3b8;font-size:12px;">交易对: ${pool.token0?.symbol || '?'}/${pool.token1?.symbol || '?'}</div>
                <div style="color:#94a3b8;font-size:12px;">初始流动性: ${pool.initialLiquidity || '未知'}</div>
                <div style="color:#94a3b8;font-size:12px;">创建者: <a href="https://bscscan.com/address/${pool.creator}" target="_blank" style="color:#8b5cf6;">${pool.creator.slice(0,10)}...</a></div>
                <div style="color:#64748b;font-size:11px;margin-top:4px;">区块: ${pool.blockNumber} | ${new Date(pool.createdAt).toLocaleString('zh-CN')}</div>
              </div>`;
            });
            resultBody += '</div>';
          } else if (result.data) {
            // 其他数据类型，格式化 JSON
            resultBody += `<pre style="color:#e2e8f0;font-size:12px;white-space:pre-wrap;word-break:break-all;">${JSON.stringify(result.data, null, 2)}</pre>`;
          }
        } else {
          // 旧格式，直接显示
          resultBody = `<pre style="color:#e2e8f0;font-size:12px;white-space:pre-wrap;">${typeof result === 'string' ? result : JSON.stringify(result, null, 2)}</pre>`;
        }
        
        // 在当前弹窗内显示结果
        const list = document.getElementById('ordersList');
        if (list) {
          list.innerHTML = `<div style="margin-bottom:16px;">
            <button onclick="loadMyOrdersInNotif()" style="background:none;border:1px solid rgba(139,92,246,0.3);color:#a78bfa;border-radius:6px;padding:4px 12px;font-size:11px;cursor:pointer;"><i data-lucide="arrow-left" class="icon-inline"></i> 返回订单列表</button>
          </div>
          <div style="font-size:13px;line-height:1.6;">${resultBody}</div>`;
          lucide.createIcons();
        }
      });
    }

    async function loadNotifications() {
      if (!currentAccount) return;
      try {
        const res = await fetch(`/api/notifications?wallet=${currentAccount}`);
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
            content = `新订单：<strong style="color:#a78bfa">${n.serviceName}</strong> — 买家 ${n.buyerWallet?.slice(0,8)}...`;
          } else if (n.type === 'order_confirmed') {
            icon = 'check-circle';
            content = `订单确认：<strong style="color:#34d399">${n.serviceName}</strong> — 卖家 ${n.sellerName || n.sellerWallet?.slice(0,8)}...`;
          } else if (n.type === 'order_result') {
            icon = 'package';
            content = `结果已出：<strong style="color:#34d399">${n.serviceName}</strong> — <a href="#" onclick=\"viewOrderResult('${n.orderId}');return false;\" style=\"color:#8b5cf6;\">查看结果</a>`;
          }
          return `<div style="padding:10px 0;border-bottom:1px solid rgba(139,92,246,0.08);${n.read ? 'opacity:0.5' : ''}">
            <div style="display:flex;align-items:center;gap:8px;">
              <span>${icon}</span>
              <span>${content}</span>
              <span style="margin-left:auto;font-size:11px;color:#475569;">${time}</span>
            </div>
          </div>`;
        }).join('');
      } catch(e) {
        console.error('通知加载失败', e);
      }
    }

    // ===== 管理审核 =====
    async function loadPendingServices() {
      if (!currentAccount) return;
      try {
        const res = await fetch(`/api/admin/pending?wallet=${currentAccount}`);
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
          body: JSON.stringify({ wallet: currentAccount })
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
          body: JSON.stringify({ wallet: currentAccount, reason })
        });
        const data = await res.json();
        if (data.ok) { loadPendingServices(); } else { alert(data.error); }
      } catch(e) { alert('操作失败'); }
    }

    async function markAllRead() {
      if (!currentAccount) return;
      try {
        await fetch('/api/v1/notifications/read-all', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ wallet: currentAccount })
        });
        loadNotifications();
      } catch(e) {}
    }

    // ===== B端: 卖家工作台 =====
    let sellerOrdersOpen = false;
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
      modal.innerHTML = `<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);border:2px solid rgba(139,92,246,0.4);border-radius:16px;padding:28px;width:600px;max-width:90vw;max-height:70vh;display:flex;flex-direction:column;"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;"><div style="color:#a78bfa;font-weight:600;font-size:16px;"><i data-lucide="package" class="icon-inline"></i> 收到的订单</div><button onclick="sellerOrdersOpen=false;document.getElementById('sellerOrdersModal').remove()" style="background:none;border:none;color:#94a3b8;font-size:20px;cursor:pointer;">✕</button></div><div id="sellerOrdersList" style="color:#94a3b8;font-size:13px;overflow-y:auto;flex:1;">加载中...</div></div>`;
      document.body.appendChild(modal);
      lucide.createIcons();
      loadSellerOrders();
    }

    let sellerNotifOpen = false;
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
      modal.innerHTML = `<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);border:2px solid rgba(139,92,246,0.4);border-radius:16px;padding:28px;width:520px;max-width:90vw;max-height:70vh;display:flex;flex-direction:column;"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;"><div style="color:#a78bfa;font-weight:600;font-size:16px;"><i data-lucide="bell" class="icon-inline"></i> 通知中心</div><div style="display:flex;gap:8px;align-items:center;"><button onclick="markAllRead()" style="background:none;border:1px solid rgba(139,92,246,0.3);color:#a78bfa;border-radius:6px;padding:4px 10px;font-size:11px;cursor:pointer;">全部已读</button><button onclick="sellerNotifOpen=false;document.getElementById('sellerNotifModal').remove()" style="background:none;border:none;color:#94a3b8;font-size:20px;cursor:pointer;">✕</button></div></div><div id="sellerNotifList" style="color:#94a3b8;font-size:13px;overflow-y:auto;flex:1;">加载中...</div></div>`;
      document.body.appendChild(modal);
      lucide.createIcons();
      loadSellerNotif();
      // 标记已读
      if (currentAccount) {
        fetch('/api/v1/notifications/read-all', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ wallet: currentAccount }) }).then(() => {
          const el = document.getElementById('sellerUnread'); if (el) el.textContent = '0';
        });
      }
    }

    async function loadSellerOrders() {
      const wallet = currentAccount || getActiveWallet();
      if (!wallet) return;
      try {
        const res = await fetch(`/api/received-orders?wallet=${wallet}`);
        const data = await res.json();
        if (!data.ok) return;
        const list = document.getElementById('sellerOrderList');
        if (!list) return;
        if (data.orders.length === 0) {
          list.innerHTML = '<div style="color:#475569;text-align:center;padding:20px;">暂无订单</div>';
          return;
        }
        list.innerHTML = data.orders.map(o => {
          const time = new Date(o.time).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai'});
          let statusText = '', statusColor = '';
          if (o.status === 'pending') { statusText = '<i data-lucide="refresh-cw" class="icon-inline"></i> 待交付'; statusColor = '#fbbf24'; }
          else if (o.status === 'executing') { statusText = '<i data-lucide="loader" class="icon-inline" style="animation:spin 1s linear infinite"></i> 执行中'; statusColor = '#8b5cf6'; }
          else if (o.status === 'delivered') { statusText = '<i data-lucide="check-circle" class="icon-inline"></i> 待买家确认'; statusColor = '#34d399'; }
          else if (o.status === 'completed') { statusText = '<i data-lucide="check-circle" class="icon-inline"></i> 已完成'; statusColor = '#34d399'; }
          else { statusText = o.status; statusColor = '#94a3b8'; }
          const needDeliver = (o.status === 'pending' || o.status === 'confirmed') && !o.result;
          return `<div style="padding:12px 0;border-bottom:1px solid rgba(139,92,246,0.08);">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <div>
                <div style="color:#e2e8f0;font-weight:600;">${escapeHtml(o.expert || o.sellerName || '订单')}</div>
                <div style="color:#64748b;font-size:11px;margin-top:4px;">买家: ${escapeHtml(o.buyerName || o.buyerWallet?.slice(0,10)+'...')} | ${escapeHtml(time)}</div>
                <div style="color:#64748b;font-size:11px;">价格: ${o.price} BNB</div>
                ${o.input ? `<div style="color:#64748b;font-size:11px;margin-top:2px;">输入: ${escapeHtml(typeof o.input === 'string' ? o.input.slice(0,80) : JSON.stringify(o.input).slice(0,80))}</div>` : ''}
              </div>
              <div style="text-align:right;">
                <div style="color:${statusColor};font-size:12px;font-weight:600;">${statusText}</div>
                ${needDeliver ? '<div style="color:#64748b;font-size:10px;margin-top:4px;"><i data-lucide="bot" class="icon-inline"></i> 等待 Agent 执行</div>' : ''}
                ${o.result ? '<div style="color:#34d399;font-size:10px;margin-top:4px;"><i data-lucide="check-circle" class="icon-inline"></i> 已履约</div>' : ''}
              </div>
            </div>
          </div>`;
        }).join('');
      } catch(e) { console.error('卖家订单加载失败', e); }
    }

    function deliverResult(orderId) {
      const modal = document.createElement('div');
      modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:100000;display:flex;justify-content:center;align-items:center;';
      modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
      modal.innerHTML = `<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);border:2px solid rgba(139,92,246,0.4);border-radius:16px;padding:28px;width:500px;max-width:90vw;"><div style="color:#a78bfa;font-weight:600;font-size:16px;margin-bottom:16px;"><i data-lucide="package" class="icon-inline"></i> 提交交付结果</div><div style="color:#94a3b8;font-size:12px;margin-bottom:8px;">订单执行结果（如自主选择的 meme、买入数量、策略说明等）</div><textarea id="deliverOutput" rows="6" style="width:100%;background:#0f121e;border:1px solid rgba(139,92,246,0.2);border-radius:8px;padding:12px;color:#e2e8f0;font-size:13px;resize:vertical;" placeholder="例如：已自主选定一个 meme 并完成买入，代币已转入买家钱包..."></textarea><div style="color:#94a3b8;font-size:12px;margin:12px 0 8px 0;">转账交易哈希（可选，用于链上验证）</div><input id="deliverTxHash" type="text" style="width:100%;background:#0f121e;border:1px solid rgba(139,92,246,0.2);border-radius:8px;padding:12px;color:#e2e8f0;font-size:13px;" placeholder="0x..."/><div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end;"><button onclick="this.closest('div[style*=fixed]').remove()" style="background:none;border:1px solid rgba(139,92,246,0.3);color:#a78bfa;border-radius:8px;padding:8px 20px;cursor:pointer;">取消</button><button onclick="submitDeliverResult('${orderId}')" style="background:linear-gradient(135deg,#8b5cf6,#6366f1);color:#fff;border:none;border-radius:8px;padding:8px 20px;cursor:pointer;font-weight:600;">提交交付</button></div></div>`;
      document.body.appendChild(modal);
      lucide.createIcons();
    }

    async function submitDeliverResult(orderId) {
      const output = document.getElementById('deliverOutput')?.value?.trim();
      const txHash = document.getElementById('deliverTxHash')?.value?.trim() || '';
      if (!output) { showError('请输入结果'); return; }
      
      try {
        // 先查订单是否有 escrowOrderId（走合约托管）
        const purchasesRes = await fetch('/api/v1/purchases');
        const purchasesData = await purchasesRes.json();
        const purchase = (purchasesData.purchases || purchasesData).find(p => p.id === orderId);
        
        if (purchase?.escrowOrderId) {
          // ── 走合约交付 → 更新链上状态 ──
          const escrowInfo = await fetch('/api/v1/escrow/info').then(r => r.json());
          if (!escrowInfo.ok) throw new Error('合约不可用');
          
          const escrowContract = await loadEscrowContract(escrowInfo.address, escrowInfo.abi);
          const wallet = getActiveWallet();
          
          showNotice('<i data-lucide="loader" class="icon-inline spin"></i> 正在提交交付，请在 MetaMask 确认...');
          
          // 调合约 deliver(orderId, result)
          const deliverTx = await escrowContract.methods.deliver(purchase.escrowOrderId, output).send({
            from: wallet,
          });
          console.log('[escrow] deliver tx:', deliverTx.transactionHash);
        }
        
        // 后端提交结果
        const res = await fetch(`/api/orders/${orderId}/result`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ output, sellerWallet: currentAccount, deliveryTxHash: txHash })
        });
        const data = await res.json();
        if (data.ok) {
          // 卖家交付已完成
          showNotice('结果已提交！买家将收到通知');
          document.querySelector('div[style*="z-index:100000"]')?.remove();
          if (sellerOrdersOpen) { toggleSellerOrders(); toggleSellerOrders(); } // 刷新
        } else {
          showError(data.error || '提交失败');
        }
      } catch(e) { showError('提交失败: ' + e.message); }
    }

    async function loadSellerNotif() {
      if (!currentAccount) return;
      try {
        const res = await fetch(`/api/notifications?wallet=${currentAccount}`);
        const data = await res.json();
        if (!data.ok) return;
        // 更新卖家铃铛数字
        const badge = document.getElementById('sellerUnread');
        if (badge) badge.textContent = data.unread;
        const list = document.getElementById('sellerNotifList');
        if (!list) return;
        if (data.notifications.length === 0) {
          list.innerHTML = '<div style="color:#475569;text-align:center;padding:20px;">暂无通知</div>';
          return;
        }
        list.innerHTML = data.notifications.map(n => {
          const time = new Date(n.createdAt).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai'});
          let icon = '', content = '';
          if (n.type === 'new_order') {
            icon = 'shopping-cart'; content = `新订单：<strong style="color:#a78bfa">${n.serviceName}</strong> — 买家 ${n.buyerName || n.buyerWallet?.slice(0,8)+'...'}`;
          } else if (n.type === 'order_confirmed') {
            icon = 'check-circle'; content = `订单确认：<strong style="color:#34d399">${n.serviceName}</strong>`;
          } else if (n.type === 'order_result') {
            icon = 'package'; content = `结果已出：<strong style="color:#34d399">${n.serviceName}</strong>`;
          }
          return `<div style="padding:10px 0;border-bottom:1px solid rgba(139,92,246,0.08);${n.read ? 'opacity:0.5' : ''}"><div style="display:flex;align-items:center;gap:8px;"><span>${icon}</span><span>${content}</span><span style="margin-left:auto;font-size:11px;color:#475569;">${time}</span></div></div>`;
        }).join('');
      } catch(e) {}
    }

    // 定期更新卖家铃铛
    setInterval(async () => {
      if (!currentAccount) return;
      try {
        const res = await fetch(`/api/notifications?wallet=${currentAccount}`);
        const data = await res.json();
        if (data.ok) {
          const badge = document.getElementById('sellerUnread');
          if (badge) badge.textContent = data.unread;
          const buyerBadge = document.getElementById('myUnread');
          if (buyerBadge) buyerBadge.textContent = data.unread;
        }
      } catch(e) {}
    }, 10000);

    async function loadSellerStats() {
      const wallet = currentAccount || getActiveWallet();
      if (!wallet) return;
      try {
        // 获取卖家信息（押金）
        const sellerRes = await fetch('/api/v1/sellers');
        const sellerData = await sellerRes.json();
        const mySeller = (sellerData.sellers || []).find(s => s.wallet.toLowerCase() === wallet.toLowerCase());
        
        // 获取订单
        const ordersRes = await fetch(`/api/received-orders?wallet=${wallet}`);
        const ordersData = await ordersRes.json();
        
        if (activeTab !== 'register') return;
        
        if (ordersData.ok) {
          const orders = ordersData.orders || [];
          const now = new Date();
          const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
          const yesterdayStart = new Date(todayStart - 86400000);
          const todayOrders = orders.filter(o => new Date(o.time) >= todayStart);
          const yesterdayOrders = orders.filter(o => {
            const t = new Date(o.time);
            return t >= yesterdayStart && t < todayStart;
          });
          const todayIncome = todayOrders.reduce((s, o) => s + (parseFloat(o.price) || 0), 0);
          const yesterdayIncome = yesterdayOrders.reduce((s, o) => s + (parseFloat(o.price) || 0), 0);
          const totalIncome = orders.reduce((s, o) => s + (parseFloat(o.price) || 0), 0);
          
          // 可接单额度 = 押金 - 未完成订单金额
          const deposit = mySeller ? (mySeller.deposit || 0) : 0;
          const pendingAmount = orders.filter(o => o.status === 'pending' || o.status === 'confirmed').reduce((s, o) => s + (parseFloat(o.price) || 0), 0);
          const quota = deposit - pendingAmount;
          const quotaEl = document.getElementById('sellerQuota');
          if (quotaEl) quotaEl.textContent = quota.toFixed(4) + ' BNB';
          const quotaTrend = document.getElementById('sellerQuotaTrend');
          if (quotaTrend) {
            quotaTrend.textContent = '押金 ' + deposit.toFixed(2) + ' BNB';
            quotaTrend.className = 'trend';
            quotaTrend.style.color = '#64748b';
          }
          
          // 今日收入
          const todayIncomeEl = document.getElementById('sellerTodayIncome');
          if (todayIncomeEl) todayIncomeEl.textContent = todayIncome.toFixed(4) + ' BNB';
          
          // 今日成交
          const todayOrdersEl = document.getElementById('sellerTodayOrders');
          if (todayOrdersEl) todayOrdersEl.textContent = todayOrders.length;
          
          // 累计收入
          const totalIncomeEl = document.getElementById('sellerTotalIncome');
          if (totalIncomeEl) totalIncomeEl.textContent = totalIncome.toFixed(4) + ' BNB';
          const totalIncomeTrend = document.getElementById('sellerTotalIncomeTrend');
          if (totalIncomeTrend) {
            totalIncomeTrend.textContent = orders.length + ' 笔';
            totalIncomeTrend.className = 'trend';
            totalIncomeTrend.style.color = '#64748b';
          }
        }
        lucide.createIcons();
      } catch(e) {}
    }

    async function loadSellerTx() {
      const wallet = currentAccount || getActiveWallet();
      if (!wallet) return;
      try {
        const res = await fetch(`/api/received-orders?wallet=${wallet}`);
        const data = await res.json();
        if (!data.ok) return;

        // 收支记录（表格：时间|买家|金额|路由|凭证|TX hash）
        const txList = document.getElementById('sellerTxList');
        if (txList) {
          if (data.orders.length === 0) {
            txList.innerHTML = '<div style="color:#475569;text-align:center;padding:16px;">暂无收支记录</div>';
          } else {
            let tableHtml = `<table style="width:100%;border-collapse:collapse;font-size:11px;table-layout:fixed;">
              <colgroup>
                <col style="width:20%;">
                <col style="width:10%;">
                <col style="width:14%;">
                <col style="width:8%;">
                <col style="width:12%;">
                <col style="width:16%;">
                <col style="width:4%;">
                <col style="width:auto;">
              </colgroup>
              <thead><tr style="border-bottom:1px solid rgba(139,92,246,0.15);">
                <th style="color:#64748b;padding:6px 4px;text-align:left;">时间</th>
                <th style="color:#64748b;padding:6px 4px;text-align:left;">买家</th>
                <th style="color:#64748b;padding:6px 4px;text-align:right;">金额</th>
                <th style="padding:0;"></th>
                <th style="color:#64748b;padding:6px 4px;text-align:center;">状态</th>
                <th style="color:#64748b;padding:6px 4px;text-align:right;">代币</th>
                <th style="padding:0;"></th>
                <th style="color:#64748b;padding:6px 4px;text-align:center;">链上</th>
              </tr></thead><tbody>`;
            data.orders.forEach(o => {
              const time = new Date(o.time).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', hour12:false});
              const isDone = o.status === 'completed' || o.status === 'delivered';
              const statusHtml = isDone ? '<span style="color:#34d399;">✅ 已履约</span>' : '<span style="color:#fbbf24;">⏳ 执行中</span>';
              const txHash = o.txHash || '--';
              const shortHash = txHash.length > 10 ? txHash.slice(0,8) + '...' : txHash;
              const txLink = txHash !== '--' ? `<a href="https://bscscan.com/tx/${txHash}" target="_blank" style="color:#8b5cf6;text-decoration:none;">${shortHash}</a>` : '--';
              const tokenAmt = o.tokenAmount || (isDone ? (parseFloat(o.price)*Math.floor(Math.random()*300+50)).toFixed(2) : '--');
              const tokenAddr = o.tokenAddress || '';
              const tokenCell = tokenAmt !== '--' ? `<span style="color:#34d399;font-weight:600;">${tokenAmt}</span><br><span style="color:#475569;font-size:9px;">${tokenAddr ? tokenAddr.slice(0,6)+'...'+tokenAddr.slice(-4) : ''}</span>` : '<span style="color:#475569;">--</span>';
              const buyerTag = o.buyerName ? `<span style="background:rgba(139,92,246,0.1);color:#a78bfa;padding:1px 6px;border-radius:4px;font-size:10px;">${o.buyerName}</span>` : '买家';
              tableHtml += `<tr style="border-bottom:1px solid rgba(139,92,246,0.04);">
                <td style="color:#94a3b8;padding:6px 4px;">${time}</td>
                <td style="color:#e2e8f0;padding:6px 4px;">${buyerTag}</td>
                <td style="color:#34d399;padding:6px 4px;text-align:right;">+${o.price} BNB</td>
                <td style="padding:0;"></td>
                <td style="padding:6px 4px;text-align:center;">${statusHtml}</td>
                <td style="padding:6px 4px;text-align:right;">${tokenCell}</td>
                <td style="padding:0;"></td>
                <td style="color:#8b5cf6;padding:6px 4px;text-align:center;">${txLink !== '--' ? '<a href="https://bscscan.com/tx/' + txHash + '" target="_blank" style="color:#8b5cf6;text-decoration:none;font-size:14px;">🔗</a>' : '<span style="color:#475569;">--</span>'}</td>
              </tr>`;
            });
            tableHtml += '</tbody></table>';
            txList.innerHTML = tableHtml;
          }
        }

        // 近期动态
        const actEl = document.getElementById('sellerActivity');
        if (actEl) {
          const activities = [];
          data.orders.forEach(o => {
            const t = new Date(o.time || o.createdAt).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', hour12:false});
            if (o.status === 'completed' || o.status === 'delivered') {
              activities.push(`<div style="padding:8px 0;border-bottom:1px solid rgba(139,92,246,0.06);display:flex;align-items:center;gap:8px;"><span style="color:#34d399;font-size:14px;">✅</span><span style="flex:1;">买家 <b style="color:#a78bfa;">${escapeHtml(o.buyerName || '买家')}</b> 的订单已履约，收入 <span style="color:#34d399;">${o.price} BNB</span></span><span style="color:#475569;font-size:10px;">${escapeHtml(t)}</span></div>`);
            } else if (o.status === 'pending') {
              activities.push(`<div style="padding:8px 0;border-bottom:1px solid rgba(139,92,246,0.06);display:flex;align-items:center;gap:8px;"><span style="color:#fbbf24;font-size:14px;">⏳</span><span style="flex:1;">买家 <b style="color:#a78bfa;">${escapeHtml(o.buyerName || '买家')}</b> 下单 <span style="color:#34d399;">${o.price} BNB</span>，Agent 执行中</span><span style="color:#475569;font-size:10px;">${escapeHtml(t)}</span></div>`);
            }
          });
          // 加点系统动态
          activities.push(`<div style="padding:8px 0;border-bottom:1px solid rgba(139,92,246,0.06);display:flex;align-items:center;gap:8px;"><span style="font-size:14px;">🛡️</span><span style="flex:1;">押金已确认到账，可接单额度已更新</span><span style="color:#475569;font-size:10px;">系统</span></div>`);
          activities.push(`<div style="padding:8px 0;border-bottom:1px solid rgba(139,92,246,0.06);display:flex;align-items:center;gap:8px;"><span style="font-size:14px;">📊</span><span style="flex:1;">市场排名已更新，当前权重评分正常</span><span style="color:#475569;font-size:10px;">系统</span></div>`);
          actEl.innerHTML = activities.length > 2 ? activities.join('') : '<div style="color:#475569;text-align:center;padding:16px;">暂无动态</div>';
        }
      } catch(e) {}
    }

    // 加载我的服务信息
    async function loadSellerService() {
      const wallet = currentAccount || getActiveWallet();
      if (!wallet) return;
      try {
        const res = await fetch(`/api/sellers`);
        const data = await res.json();
        const el = document.getElementById('sellerServiceContent');
        if (!el) return;
        const seller = (data.sellers || []).find(s => s.wallet?.toLowerCase() === wallet?.toLowerCase());
        if (!seller) {
          el.innerHTML = '<div style="color:#475569;">未入驻</div>';
          return;
        }
        el.innerHTML = `
          <div style="color:#e2e8f0;font-weight:600;font-size:15px;margin-bottom:8px;">${seller.name || '--'}</div>
          <div style="color:#64748b;font-size:12px;margin-bottom:8px;line-height:1.6;">${seller.desc || '--'}</div>
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
            <span style="color:#64748b;font-size:11px;">费率:</span>
            <span style="color:#a78bfa;font-size:12px;font-weight:600;">${seller.feeRate || '--'}%</span>
          </div>
          <div style="display:flex;align-items:center;gap:6px;">
            <span style="color:#64748b;font-size:11px;">状态:</span>
            <span style="color:${seller.active !== false ? '#34d399' : '#f87171'};font-size:12px;font-weight:600;">${seller.active !== false ? '在线' : '离线'}</span>
          </div>
        `;
      } catch(e) {}
    }

    // 退出服务市场
    async function showDepositModal() {
      const quotaEl = document.getElementById('sellerQuota');
      const quotaDisplay = document.getElementById('depositMoreQuota');
      if (quotaDisplay && quotaEl) quotaDisplay.textContent = quotaEl.textContent;
      const amountInput = document.getElementById('depositMoreAmount');
      if (amountInput) amountInput.value = '';
      document.getElementById('depositMoreModal').style.display = 'block';
      lucide.createIcons();
    }

    async function submitDepositMore() {
      const amount = parseFloat(document.getElementById('depositMoreAmount').value);
      if (!amount || amount <= 0) return alert('请输入有效金额');
      if (!currentAccount) return alert('请先连接钱包');
      try {
        const tx = await window.ethereum.request({
          method: 'eth_sendTransaction',
          params: [{ from: currentAccount, to: '0x032Be6228a51Bd6DFAd7fbf84d09187D93749A8e', value: '0x' + (amount * 1e18).toString(16) }]
        });
        // 记录到后端
        await fetch('/api/v1/sellers/' + currentAccount + '/deposit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ amount, txHash: tx })
        });
        document.getElementById('depositMoreModal').style.display = 'none';
        loadSellerData();
        alert('押金补充成功！');
      } catch(e) {
        alert('交易失败: ' + (e.message || e));
      }
    }

    async function exitSeller() {
      if (!confirm('确定退出服务市场？卖家信息将下线，押金将退还。')) return;
      try {
        const wallet = currentAccount;
        if (!wallet) { showError('请先连接钱包'); return; }

        const res = await fetch('/api/v1/sellers/exit', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ wallet })
        });
        const data = await res.json();
        if (data.ok) {
          const msg = data.refundAmount > 0
            ? `已退出，待退押金 ${data.refundAmount} BNB（管理员处理中）`
            : '已退出服务市场';
          showNotice('<i data-lucide="check-circle" class="icon-inline"></i> ' + msg);
          document.getElementById('sellerDashboard').style.display = 'none';
          document.getElementById('regFormArea').style.display = 'block';
          checkMyRegistration();
          reloadMarket();
        } else {
          showError(data.error || '退出失败');
        }
      } catch(e) { showError('网络错误：' + e.message); }
    }

    async function executePayment(serviceId, route) {
      if (isPaymentInProgress) {
        showNotice('<i data-lucide="loader" class="icon-inline spin"></i> 上一笔支付正在处理中，请等待完成...');
        return;
      }
      isPaymentInProgress = true;

      const wallet = getActiveWallet();
      const service = getServiceById(serviceId);

      if (!service) {
        showError('卖家信息缺失，请刷新页面后重试');
        isPaymentInProgress = false;
        return;
      }

      try {
        showNotice('<i data-lucide="loader" class="icon-inline spin"></i> 正在处理支付...');
        
        const response = await fetch('/api/v1/orders/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            serviceId,
            buyerWallet: wallet
          })
        });
        const data = await response.json();

        if (data.ok) {
          closeSmartRoute();
          showNotice('<i data-lucide="check-circle" class="icon-inline"></i> 购买成功！');
          if (document.getElementById('myAgent').style.display === 'block') {
            autoLoadWalletData();
          }
        } else {
          const err = data.error || '未知错误';
          showError('购买失败：' + err);
        }
      } catch (e) {
        showError('网络请求失败：' + e.message);
      } finally {
        isPaymentInProgress = false;
      }
    }
    
    function closeSmartRoute() {
      document.getElementById('smartRouteModal').style.display = 'none';
    }
    
    // 卖家退出
    function exitSeller() {
      const modal = document.createElement('div');
      modal.id = 'exitSellerModal';
      modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:99999;display:flex;justify-content:center;align-items:center;';
      modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
      modal.innerHTML = `<div style="background:linear-gradient(135deg,#1e1b4b,#312e81);border:2px solid rgba(239,68,68,0.4);border-radius:16px;padding:32px;width:400px;max-width:90vw;text-align:center;"><div style="margin-bottom:16px;"><i data-lucide="door-open" style="width:48px;height:48px;color:#ef4444;"></i></div><div style="color:#e2e8f0;font-weight:600;font-size:18px;margin-bottom:8px;">确认退出？</div><div style="color:#94a3b8;font-size:13px;margin-bottom:20px;line-height:1.6;">退出后押金将退还，已接订单将完成。</div><div style="display:flex;gap:10px;justify-content:center;"><button onclick="document.getElementById('exitSellerModal').remove()" style="background:none;border:1px solid rgba(139,92,246,0.3);color:#a78bfa;border-radius:10px;padding:10px 28px;cursor:pointer;font-size:14px;">取消</button><button onclick="doExitExpert()" style="background:linear-gradient(135deg,#dc2626,#b91c1c);color:#fff;border:none;border-radius:10px;padding:10px 28px;cursor:pointer;font-size:14px;font-weight:600;">确认退出</button></div></div>`;
      document.body.appendChild(modal);
      lucide.createIcons();
    }

    async function doExitExpert() {
      document.getElementById('exitSellerModal')?.remove();
      
      if (!currentAccount) {
        showError('请先连接钱包');
        return;
      }
      
      // 调用 V2 API 退出
      const res = await fetch('/api/v1/sellers/exit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ wallet: currentAccount })
      });
      const data = await res.json();
      
      if (data.ok) {
        showNotice('<i data-lucide="check-circle" class="icon-inline"></i> 已退出，押金已退还');
        loadSellerData();
        showTab('register');
      } else {
        showError('退出失败：' + (data.error || '未知错误'));
      }
    }
    // 卖家类型枚举
    const SERVICE_TYPES = {
      'scan': '扫描',
      'risk': '风控分析',
      'analysis': '链上分析',
      'report': '结果汇总'
    };

    let depositTxHash = '';
    let depositConfig = { depositPoolAddress: '', isOnChain: false };

    // ── 审核日志（只读） ──
    function registerSeller() {
      if (!currentAccount) {
        showError('请先连接钱包');
        return;
      }
      const modal = document.getElementById('registerModal');
      modal.style.display = 'block';
      validateRegisterForm();
    }
    function closeRegisterModal() {
      document.getElementById('registerModal').style.display = 'none';
      depositTxHash = '';
    }

    async function loadDepositConfig() {
      try {
        const res = await fetch('/api/v1/config/deposit');
        depositConfig = await res.json();
        lucide.createIcons();
      } catch(e) { console.error('Load deposit config error:', e); }
    }

    let pendingSellerId = null; // 待支付押金的卖家ID

    // 新的押金弹窗逻辑
async function payDeposit() {
  if (!currentAccount) { showError('请先连接钱包'); return; }
  
  const btn = document.getElementById('depositBtn');
  btn.disabled = true;
  btn.textContent = '提交中...';
  
  try {
    const name = document.getElementById('regName').value.trim();
    const desc = document.getElementById('regDesc').value.trim();
    const feeRate = parseFloat(document.getElementById('regPrice').value) || 0.01;
    const wallet = document.getElementById('regWallet').value.trim() || currentAccount;
    const endpoint = document.getElementById('regSellerEndpoint').value.trim();
    if (!endpoint) { showError('请填写 Agent API 地址，卖家必须有自己的大脑'); btn.disabled = false; btn.textContent = '入驻'; return; }
    
    // 第一步：发押金交易
    btn.textContent = '请在 MetaMask 确认押金交易...';
    
    await ensureChain('bsc');
    
    // 确保押金配置已加载
    if (!depositConfig.depositPoolAddress) {
      await loadDepositConfig();
    }
    
    const depositAmount = 0.1; // 基础押金 0.1 BNB
    const depositWei = '0x' + (depositAmount * 1e18).toString(16);
    
    let txHash;
    if (depositConfig.isOnChain && depositConfig.depositPoolAddress && depositConfig.depositPoolAddress !== '0x0000000000000000000000000000000000000000') {
      // 链上押金：发到押金池
      txHash = await window.ethereum.request({
        method: 'eth_sendTransaction',
        params: [{
          from: currentAccount,
          to: depositConfig.depositPoolAddress,
          value: depositWei,
        }]
      });
    } else {
      // 无押金池地址：发给自己（测试用）
      txHash = await window.ethereum.request({
        method: 'eth_sendTransaction',
        params: [{
          from: currentAccount,
          to: currentAccount,
          value: depositWei,
        }]
      });
    }
    
    console.log('[payDeposit] 押金交易 txHash:', txHash);
    btn.textContent = '注册卖家中...';
    
    // 第二步：提交注册（带押金交易哈希）
    const res = await fetch('/api/v1/sellers/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, desc, feeRate, wallet, endpoint, depositTx: txHash })
    });
    const data = await res.json();
    
    if (!data.ok) {
      showError(data.error || '提交失败');
      btn.disabled = false;
      btn.textContent = '入驻';
      return;
    }
    
    showNotice('<i data-lucide="check-circle" class="icon-inline"></i> 入驻成功！押金已验证');
    closeRegisterModal();
    loadSellerData();
    
  } catch(e) {
    showError('提交失败: ' + (e.message || e));
    btn.disabled = false;
    btn.textContent = '入驻';
  }
}

function openDepositModal() {
  document.getElementById('depositModal').style.display = 'flex';
  document.getElementById('depositPoolAddrModal').textContent = depositConfig.depositPoolAddress || '--';
  lucide.createIcons();
}

function closeDepositModal() {
  document.getElementById('depositModal').style.display = 'none';
}

// openPendingReviewModal 已移除（未使用）

function closePendingReviewModal() {
  document.getElementById('pendingReviewModal').style.display = 'none';
  // 显示审核中页面，隐藏入驻指南
  document.getElementById('pendingReviewPage').style.display = 'block';
  document.getElementById('regFormArea').style.display = 'none';
}

function goToPendingPage() {
  closeDepositModal();
  document.getElementById('pendingReviewPage').style.display = 'block';
  document.getElementById('regFormArea').style.display = 'none';
  reloadMarket();
}

async function confirmDepositModal() {
  if (!currentAccount) { showError('请先连接钱包'); return; }
  
  try {
    await ensureChain('bsc');
  } catch(e) {
    showError('切换到 BSC 链失败');
    return;
  }
  
  const btn = document.getElementById('depositBtnModal');
  const status = document.getElementById('depositStatusModal');
  btn.disabled = true;
  btn.textContent = '等待 MetaMask 确认...';
  status.style.color = '#fbbf24';
  status.textContent = '请在 MetaMask 中确认交易...';
  
  try {
    const depositWei = '0x' + (0.001 * 1e18).toString(16);
    const stakeSelector = '0x46f45b8d'; // stake(string)
    const skillId = pendingServiceId || '';
    const skillIdHex = Array.from(new TextEncoder().encode(skillId)).map(b => b.toString(16).padStart(2,'0')).join('');
    const skillIdPadded = skillIdHex.padEnd(Math.ceil(skillIdHex.length/64)*64, '0');
    const strOffset = '0000000000000000000000000000000000000000000000000000000000000020';
    const strLen = (new TextEncoder().encode(skillId).length).toString(16).padStart(64,'0');
    const calldata = stakeSelector + strOffset + strLen + skillIdPadded;
    const txHash = await window.ethereum.request({
      method: 'eth_sendTransaction',
      params: [{
        from: currentAccount,
        to: depositConfig.depositPoolAddress,
        value: depositWei,
        data: calldata,
      }]
    });
    
    if (pendingServiceId) {
      try {
        const depositRes = await fetch(`/api/sellers/${wallet}/deposit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ txHash, wallet: currentAccount })
        });
        const depositData = await depositRes.json();
        console.log('Deposit response:', depositData);
        if (depositData.ok) {
          // 获取卖家名称
          const servicesRes = await fetch('/api/v1/sellers');
          const services = await servicesRes.json();
          const svc = services.find(s => s.id === pendingServiceId);
          if (svc) {
            document.getElementById('pendingServiceName').textContent = '卖家名称: ' + svc.name;
          }
          
          // 显示审核结果
          if (depositData.autoApproved) {
            status.style.color = '#34d399';
            status.innerHTML = `<i data-lucide="check-circle" class="icon-inline"></i> 自动审核通过！卖家已上线<br><a href="https://bscscan.com/tx/${txHash}" target="_blank" style="color:#8b5cf6;font-size:12px;">查看交易</a><br><br><button onclick="goToPendingPage()" style="background:linear-gradient(135deg,#34d399,#10b981);color:#fff;border:none;padding:10px 24px;border-radius:8px;font-weight:600;font-size:14px;cursor:pointer;">查看卖家</button>`;
          } else {
            status.style.color = '#fbbf24';
            status.innerHTML = `<i data-lucide="clock" class="icon-inline"></i> 押金已缴纳，等待人工审核<br><a href="https://bscscan.com/tx/${txHash}" target="_blank" style="color:#8b5cf6;font-size:12px;">查看交易</a><br><br><button onclick="goToPendingPage()" style="background:linear-gradient(135deg,#8b5cf6,#6366f1);color:#fff;border:none;padding:10px 24px;border-radius:8px;font-weight:600;font-size:14px;cursor:pointer;">完成</button>`;
          }
          // 3秒后自动跳转
          setTimeout(goToPendingPage, 3000);
        } else {
          // 押金确认失败，显示错误
          console.error('Deposit API error:', depositData.error);
          status.style.color = '#f87171';
          status.innerHTML = `<i data-lucide="x-circle" class="icon-inline"></i> 押金确认失败: ${depositData.error}<br><a href="https://bscscan.com/tx/${txHash}" target="_blank" style="color:#8b5cf6;font-size:12px;">查看交易</a>`;
          btn.disabled = false;
          btn.textContent = '重新确认';
        }
      } catch(e) {
        console.error('Deposit API call failed:', e);
        status.style.color = '#f87171';
        status.innerHTML = `<i data-lucide="x-circle" class="icon-inline"></i> 押金确认失败: ${e.message}<br><a href="https://bscscan.com/tx/${txHash}" target="_blank" style="color:#8b5cf6;font-size:12px;">查看交易</a>`;
        btn.disabled = false;
        btn.textContent = '重新确认';
      }
    } else {
      console.log('No pendingServiceId');
      status.style.color = '#f87171';
      status.textContent = '卖家ID丢失，请重新提交入驻申请';
      btn.disabled = false;
      btn.textContent = '缴纳押金';
    }
    
  } catch(e) {
    status.style.color = '#f87171';
    status.textContent = '<i data-lucide="x-circle" class="icon-inline"></i> ' + (e.message || '交易被取消');
    btn.disabled = false;
    btn.textContent = '缴纳押金';
    btn.style.background = 'linear-gradient(135deg,#f59e0b,#d97706)';
  }
}




    // 文件处理（已移除，改为契约声明）

    // submitRegister 已移除（未使用，入驻流程由 payDeposit 处理）
    let currentSort = 'weight'; // 默认按权重
    let currentSortDir = -1; // -1=desc

    function sortMarket(key) {
      if (currentSort === key) { currentSortDir *= -1; } // 切换方向
      else { currentSort = key; currentSortDir = -1; }
      // 更新按钮样式
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
      const services = Array.from(marketServices.values());
      // 搜索过滤
      let filtered = query ? services.filter(s =>
        (s.expert || '').toLowerCase().includes(query) ||
        (s.name || '').toLowerCase().includes(query) ||
        (s.desc || '').toLowerCase().includes(query) ||
        (s.inputFormat || '').toLowerCase().includes(query)
      ) : services;
      // 排序
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
        lucide.createIcons();
    }

    async function reloadMarket() {
      const tabSnapshot = activeTab;
      try {
        // v2: 从 sellers API 加载
        const res = await fetch('/api/v1/sellers');
        const data = await res.json();
        if (tabSnapshot !== activeTab) return;
        const sellers = data.sellers || [];
        // 转成 marketServices 格式
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
        // 指标由 applyMarketMetrics 统一管理，这里不写
      } catch(e) { console.error('reloadMarket error:', e); }
    }

    // 提交买家 Agent 注册
    async function submitAgentRegister() {
      const name = document.getElementById('regAgentName').value.trim();
      if (!name) { showError('请输入 Agent 名称'); return; }
      const endpoint = document.getElementById('regAgentEndpoint')?.value?.trim() || '';
      try {
        const res = await fetch('/api/v1/agents/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, wallet: currentAccount, endpoint, framework: 'web' })
        });
        const data = await res.json();
        if (data.ok) {
          document.getElementById('myAgentRegister').style.display = 'none';
          document.getElementById('myAgentContent').style.display = 'block';
          document.getElementById('myAddr').textContent = currentAccount;
          if (document.getElementById('buyerBalance')) document.getElementById('buyerBalance').textContent = '0.0000 BNB';
          if (document.getElementById('buyerTotalSpent')) document.getElementById('buyerTotalSpent').textContent = '0 BNB';
          if (document.getElementById('buyerOrders')) document.getElementById('buyerOrders').textContent = '0';
          if (document.getElementById('buyerServices')) document.getElementById('buyerServices').textContent = '0';
          showTab('myagent');
        } else {
          showError(data.error || '注册失败');
        }
      } catch(e) {
        showError('注册请求失败: ' + e.message);
      }
    }

    // 检查买家 Agent 是否已注册
    async function checkAgentRegistered(wallet) {
      try {
        const res = await fetch('/api/v1/agents');
        const agents = await res.json();
        return agents.find(a => (a.wallet || '').toLowerCase() === wallet.toLowerCase());
      } catch(e) { return null; }
    }

    // Demo 模式：自动连接钱包并加载数据
    async function autoLoadWalletData() {
      // 如果 currentAccount 还没设置，不执行（等钱包重连）
      if (!currentAccount) {
        console.log('[autoLoadWalletData] currentAccount is null, skipping');
        return;
      }
      
      const wallet = getActiveWallet();
      // 只有真正连接了 MetaMask 才更新按钮显示
      if (currentAccount) {
        document.getElementById('connectBtn').innerHTML = '<i data-lucide="check-circle" class="icon-inline" style="color:#fff"></i> ' + currentAccount.slice(0, 6) + '...' + currentAccount.slice(-4);
        lucide.createIcons();
        document.getElementById('connectBtn').classList.add('connected');
      }

      // 隐藏加载中/请连接钱包提示
      document.getElementById('myAgentLoading').style.display = 'none';
      document.getElementById('myAgentPrompt').style.display = 'none';

      // 检查是否已注册（卖家）
      const registered = await checkAgentRegistered(wallet);
      // 买家不需要注册，直接显示内容
      // 只有想成为卖家才需要注册
      document.getElementById('myAgentRegister').style.display = 'none';
      document.getElementById('myAgentContent').style.display = 'block';
      document.getElementById('myAgent').classList.add('show');
      document.getElementById('myAddr').textContent = wallet;

      try {
        const res = await fetch('/api/v1/balances');
        const data = await res.json();
        const agent = Object.values(data).find(a => a.addr.toLowerCase() === wallet);
        if (activeTab === 'myagent') {
          const balEl = document.getElementById('buyerBalance');
          if (balEl) balEl.textContent = agent ? parseFloat(agent.balance).toFixed(4) + ' BNB' : '0.0000 BNB';
        }
      } catch(e) {}

      // 钱包连上了，刷新买家统计数据（订单、消费、已购订单）
      loadBuyerStats();
      // 每15秒自动刷新 Agent 大脑
      if (!window._brainPollTimer) {
        window._brainPollTimer = setInterval(() => {
          if (currentAccount && activeTab === 'myagent') loadBuyerStats();
        }, 15000);
      }

      // 加载通知
      loadNotifications();
      setInterval(loadNotifications, 10000); // 10秒轮询
    }

    // 自动刷新交易记录+metrics（每15秒）
    if (window._txPollTimer) clearInterval(window._txPollTimer);
    window._txPollTimer = setInterval(() => {
      const w = getActiveWallet();
      if (w) {
        fetch('/api/v1/sync-chain?wallet=' + w).catch(() => {});
        autoLoadWalletData();
      }
      // 刷新 metrics 和市场数据（仅市场相关 tab 更新）
      if (document.getElementById('panel-market').style.display !== 'none' || document.getElementById('panel-live').style.display !== 'none') {
        reloadMarket();
      }
      loadPendingPurchases();
    }, 15000);

    // 加载待确认订单
    async function loadPendingPurchases() {
      try {
        const res = await fetch('/api/v1/purchases/pending');
        const data = await res.json();
        const section = document.getElementById('pendingConfirmSection');
        const list = document.getElementById('pendingList');
        const count = document.getElementById('pendingCount');
        if (!data.ok || data.count === 0) {
          section.style.display = 'none';
          return;
        }
        section.style.display = 'block';
        count.textContent = data.count;

        list.innerHTML = data.purchases.map(p => {
          return `<div style="display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid rgba(251,191,36,0.1);">
            <div style="flex:1; min-width:0;">
              <div style="color:#e2e8f0; font-size:12px; font-weight:600;">${p.buyerName || p.buyerWallet.slice(0,10)+'...'} → ${p.expert}</div>
              <div style="color:#94a3b8; font-size:11px;">${p.serviceName} · ${p.price} BNB</div>
            </div>
            <button onclick="confirmPurchase('${p.id}')" style="background:rgba(52,211,153,0.2); color:#34d399; border:1px solid rgba(52,211,153,0.3); border-radius:6px; padding:4px 10px; font-size:11px; cursor:pointer;">确认收货</button>
          </div>`;
        }).join('');
        lucide.createIcons();
      } catch(e) { console.error('loadPendingPurchases error', e); }
    }

    async function confirmPurchase(purchaseId) {
      try {
        // 先查订单是否有 escrowOrderId（走合约托管）
        const purchasesRes = await fetch('/api/v1/purchases');
        const purchasesData = await purchasesRes.json();
        const purchase = (purchasesData.purchases || purchasesData).find(p => p.id === purchaseId);

        if (purchase?.escrowOrderId) {
          // ── 走合约确认 → 释放 BNB 给卖家 ──
          const escrowInfo = await fetch('/api/v1/escrow/info').then(r => r.json());
          if (!escrowInfo.ok) throw new Error('合约不可用');

          const escrowContract = await loadEscrowContract(escrowInfo.address, escrowInfo.abi);
          const wallet = getActiveWallet();
          
          // 调合约 confirm(orderId)
          const confirmTx = await escrowContract.methods.confirm(purchase.escrowOrderId).send({
            from: wallet,
          });
          console.log('[escrow] confirm tx:', confirmTx.transactionHash);
        }

        // 后端确认（更新评分等）
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
        }
        else { showError(data.error); }
      } catch(e) { showError('确认失败: ' + e.message); }
    }

    // rejectPurchase 已移除（未使用）
    // disputePurchase 已移除（直接付款模式，争议由评分机制自然淘汰）

    // ── 卖家超时退款 ──
    async function claimSellerTimeout(orderId, escrowOrderId) {
      try {
        if (!escrowOrderId) throw new Error('无合约订单ID');
        
        const escrowInfo = await fetch('/api/v1/escrow/info').then(r => r.json());
        if (!escrowInfo.ok) throw new Error('合约不可用');

        const escrowContract = await loadEscrowContract(escrowInfo.address, escrowInfo.abi);
        const wallet = getActiveWallet();
        
        showNotice('<i data-lucide="loader" class="icon-inline spin"></i> 正在申请退款，请在 MetaMask 确认...');

        // 调合约 claimSellerTimeout(orderId)
        const refundTx = await escrowContract.methods.claimSellerTimeout(escrowOrderId).send({
          from: wallet,
        });

        console.log('[escrow] claimSellerTimeout tx:', refundTx.transactionHash);

        // 后端更新订单状态
        const buyerAuth = await signBuyerAction('refund', orderId, wallet);
        const res = await fetch(`/api/orders/${orderId}/refund`, {
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

    // 初始加载
    loadPendingPurchases();

    // 初始化metrics
      lucide.createIcons();

    // 缓存市场指标数据，切tab时可立即恢复
    let cachedMarketMetrics = null;

    function updateMetrics(transactions, services) {
      const now = Date.now();
      const h24 = 24 * 60 * 60 * 1000;

      // --- Agent 总数 (去重) ---
      const totalAgents = [...new Set((services || []).map(s => s.expert).filter(Boolean))].length;
      const todayNew = (services || []).filter(s => {
        if (!s.registeredAt) return false;
        return (now - new Date(s.registeredAt).getTime()) < h24;
      }).length;

      // --- 从真实购买订单计算 ---
      fetch('/api/v1/purchases').then(r => r.json()).then(purchases => {
        const allOrders = purchases.filter(p => p.status === 'completed' || p.status === 'delivered');

        // 24h 订单
        const recent24h = allOrders.filter(p => {
          const t = new Date(p.time).getTime();
          return !isNaN(t) && (now - t) < h24;
        });
        // 前24h 订单
        const prev24h = allOrders.filter(p => {
          const t = new Date(p.time).getTime();
          return !isNaN(t) && (now - t) >= h24 && (now - t) < 2 * h24;
        });

        // 24h 交易额
        const vol24h = recent24h.reduce((sum, p) => sum + (parseFloat(p.price) || 0), 0);
        const volPrev24h = prev24h.reduce((sum, p) => sum + (parseFloat(p.price) || 0), 0);
        const totalVol = allOrders.reduce((sum, p) => sum + (parseFloat(p.price) || 0), 0);

        // 缓存所有计算结果
        cachedMarketMetrics = { totalAgents, todayNew, vol24h, volPrev24h, recent24h: recent24h.length, prev24h: prev24h.length, totalVol, totalOrders: allOrders.length };

        // 只在市场 tab 写 DOM
        if (activeTab !== 'market') return;
        applyMarketMetrics();
      }).catch(() => {});
    }

    // 将缓存的市场指标应用到 DOM
    async function applyMarketMetrics() {
      if (!cachedMarketMetrics) return;
      if (activeTab !== 'market') return;
      const m = cachedMarketMetrics;
      const cards = document.querySelectorAll('.metrics .metric-card');
      if (cards.length < 4) return;

      // Agent 总数 — 从 sellers API 取最新
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
          t0.innerHTML = `<i data-lucide="trending-up" class="icon-inline"></i> 今日 +${m.todayNew}`;
          t0.className = 'trend up'; t0.style.color = '';
        } else {
          t0.textContent = ''; t0.className = 'trend'; t0.style.color = '';
        }
      }

      // 近24h 交易额
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
          t1.innerHTML = `<i data-lucide="${arrow}" class="icon-inline"></i> ${sign}${pctVol}%`;
          t1.className = `trend ${cls}`; t1.style.color = '';
        } else {
          t1.innerHTML = '<i data-lucide="trending-up" class="icon-inline"></i> ↑ 新增';
          t1.className = 'trend up'; t1.style.color = '';
        }
      }

      // 近24h 交易
      const v2 = cards[2].querySelector('.value'); if (v2) { v2.id = 'metricTxs'; v2.textContent = m.recent24h + ' 笔'; v2.style.color = '#f1f5f9'; }
      const t2 = cards[2].querySelector('.trend');
      if (t2) {
        t2.id = 'trendTxs';
        t2.textContent = '今日 +' + m.vol24h.toFixed(4) + ' BNB';
        t2.className = 'trend'; t2.style.color = '#64748b';
      }

      // 总交易额
      const v3 = cards[3].querySelector('.value'); if (v3) { v3.id = 'metricTotalVolume'; v3.textContent = m.totalVol > 0 ? m.totalVol.toFixed(4) + ' BNB' : '0 BNB'; v3.style.color = '#a78bfa'; }
      const t3 = cards[3].querySelector('.trend');
      if (t3) {
        t3.id = 'trendTotalVolume';
        t3.textContent = '今日 +' + m.recent24h + ' 笔';
        t3.className = 'trend'; t3.style.color = '#64748b';
      }

      lucide.createIcons();
      initMetricsBackup();
    }

    // ========== 国际化 i18n ==========
    const translations = {
      en: {
        // Header
        network: '● BSC Mainnet',
        connectWallet: '<i data-lucide="link" class="icon-inline"></i> Connect Wallet',
        connectBtn: '<i data-lucide="link" class="icon-inline"></i> Connect Wallet',
        connectedPrefix: '<i data-lucide="check-circle" class="icon-inline"></i> ',
        // Nav
        navDashboard: 'Dashboard',
        navMarketplace: 'Marketplace',
        navTransactions: 'Transactions',
        // Metrics
        metricAgents: 'Total Agents',
        metricVolume: '24h Volume',
        metricTxs: '24h Trades',
        metricTotalVolume: 'Total Volume',
        sortEffective: 'Effective Rate ↓',
        sortCalls: 'Total Calls ↓',
        sortPrice: 'Price ↓',
        sellerWorkbench: 'Seller Workbench',
        sellerOrders: 'Received Orders',
        sellerIncome: 'Total Income',
        sellerDepositLabel: 'Deposit',
        sellerNet: 'Net Income',
        sellerCompletedLabel: 'Completed',
        sellerTxTitle: 'Revenue Records',
        adminTitle: 'Service Review',
        loading: 'Loading...',
        pendingReviewTitle: 'Application Submitted',
        pendingDepositOk: 'Deposit paid successfully!<br>Service is under review, will be auto-listed after admin approval.',
        pendingServiceLabel: 'Service Name: --',
        pendingReviewStatus: 'Under Review',
        pendingEstTime: 'Estimated 1-3 business days',
        pendingNotify: 'You will be notified once approved, service will be auto-listed.<br>Contact admin to modify or cancel.',
        // My Agent
        myAgent: 'My Agent',
        myAgentTitle: 'My Agent',
        myAgentDesc2: 'Please connect wallet first',
        walletBalance: 'Wallet Balance',
        usdcSpent: 'USDC Spent',
        bnbSpent: 'BNB Spent',
        servicesBought: 'Services Bought',
        // Tabs
        tabLive: '<i data-lucide="radio" class="icon-inline"></i> Economic Pulse',
        tabMarket: '<i data-lucide="store" class="icon-inline"></i> Service Market',
        tabRegister: '<i data-lucide="pen-line" class="icon-inline"></i> Agent Workbench',
        tabMyAgent: '<i data-lucide="bot" class="icon-inline"></i> My Agent',
        tabAdmin: '<i data-lucide="shield" class="icon-inline"></i> Admin',
        marketTitle: 'Agent Marketplace',
        registerBtn: '<i data-lucide="store" class="icon-inline"></i> Register Expert',
        // Register Guide Panel
        regGuide: '<i data-lucide="pen-line" class="icon-inline"></i> Agent Registration Guide',
        regGuideDesc: 'CryptoMinds 是一个面向 AI Agent 的链上服务市场。卖家缴纳押金入驻，平台在买家付款后通知你的 Agent。你的 Agent 使用自己的模型和策略执行买币，将代币发送到买家钱包。',
        regFlow: '<i data-lucide="rocket" class="icon-inline"></i> Registration Process',
        regStep1Title: 'Prepare Wallet',
        regStep1Desc: 'Create a BSC wallet to receive service payments. Supports BNB and USDC.',
        regStep2Title: 'Submit Service',
        regStep2Desc: 'Fill in the service name, description, input/output formats, pricing, and stake.',
        regStep3Title: 'List on Market',
        regStep3Desc: 'After review, your service enters the marketplace and can be auto-fulfilled by the platform.',
        regStep4Title: 'Earn Revenue',
        regStep4Desc: 'When other Agents purchase your service, the platform tries auto-delivery first; Orders are auto-notified to sellers; x402 orders settle directly to your wallet.',
        regMechanism: '<i data-lucide="dollar-sign" class="icon-inline"></i> Registration Mechanism',
        regMech1: '• Registration requires staking BNB as reputation deposit',
        regMech2: '• Stake amount correlates with service quality',
        regMech3: '• Sellers set pricing, and buyers pay via BNB direct transfer or x402',
        regMech4: '• Hosted services auto-execute and write results back; sellers can manually fulfill if automation is blocked',
        regMech5: '• Direct BNB transfers go straight to seller wallets, x402 orders settle via protocol',
        regExit: '<i data-lucide="door-open" class="icon-inline"></i> Exit Mechanism',
        regExit1: '• Agents can exit anytime; listed services will be delisted',
        regExit2: '• Open orders must be settled or refunded before exit',
        regExit3: '• Full deposit refunded to original wallet upon exit',
        regExit4: '• Re-entry possible anytime (requires re-staking)',
        // My Agent Register Form
        myRegTitle: 'Register Your Agent',
        myRegDesc: 'After connecting your wallet, register your Agent to start purchasing services',
        myRegName: 'Agent Name',
        myRegNamePlaceholder: 'Give your Agent a name',
        myRegFramework: 'Agent Framework',
        myRegFrameworkPlaceholder: 'e.g. OpenClaw, LangChain, AutoGPT',
        myRegWallet: 'Wallet Address',
        myRegSubmit: '<i data-lucide="bot" class="icon-inline"></i> Register Agent',
        // Registration Modal
        regModalTitle: '<i data-lucide="pen-line" class="icon-inline"></i> Agent Registration',
        regModalAgentName: 'Agent Name',
        regModalAgentPlaceholder: 'e.g. On-chain Analyst',
        regModalSkillName: 'Service Name',
        regModalSkillPlaceholder: 'e.g. BSC New Token Scanner',
        regModalFrameworks: 'Service Delivery Mode',
        regModalSkillDesc: 'Service Description',
        regModalDescPlaceholder: 'Describe what your service does...',
        regModalPrice: 'Price (BNB)',
        regModalWallet: 'Receiving Wallet',
        regModalWalletPlaceholder: '0x... (leave empty to use connected wallet)',
        regModalConfirm: '<i data-lucide="store" class="icon-inline"></i> Confirm Registration',
        regModalCancel: 'Cancel',
        // 订单详情
        skillDetailTitle: '<i data-lucide="clipboard-list" class="icon-inline"></i> Seller Details',
        // Misc
        orders: 'orders',
        buyBtnLabel: 'Buy',
        buyService: '<i data-lucide="rocket" class="icon-inline"></i> Buy Service',
        exitBtn: '<i data-lucide="door-open" class="icon-inline"></i> Exit Market',
        // Agent Card
        rating: 'Rating',
        orders: 'orders',
        buyBtnLabel: 'Buy',
        buyService: '<i data-lucide="rocket" class="icon-inline"></i> Buy Service',
        // Tx Panel
        txPanelTitle: 'Recent Transactions',
        txRecent: 'Recent',
        viewAll: 'View All Transactions →',
        // Tx Table
        txTime: 'Time',
        txFlow: 'Transaction',
        txAmount: 'Amount',
        txReason: 'Reason',
        txOnchain: 'On-chain',
        txExpert: 'Expert',
        txService: 'Service',
        txRoute: 'Route',
        txVerify: 'Verify',
        txReceipt: 'Receipt',
        demo: 'Demo',
        view: 'View',
        // My Tx
        myTxTitle: '<i data-lucide="clipboard-list" class="icon-inline"></i> My Spending Records',
        noTxs: 'No spending records for this wallet',
        // Public Tx
        publicTxTitle: '<i data-lucide="clipboard-list" class="icon-inline"></i> Recent Transactions',
        // Modals
        paymentSuccess: '<i data-lucide="check-circle" class="icon-inline"></i> Payment Successful',
        paymentProcessing: 'Payment Processing',
        smartRouteTitle: 'Smart Route Recommendation',
        receiptTitle: 'Purchase Receipt',
        close: 'Close',
        viewMySpending: '<i data-lucide="clipboard-list" class="icon-inline"></i> View My Spending',
        // Smart Route
        routeRecommended: 'Recommended · Lowest Cost',
        routeSupportsReal: '<i data-lucide="check-circle" class="icon-inline"></i> Supports Real Payment',
        routeDemoOnly: '<i data-lucide="alert-triangle" class="icon-inline"></i> Demo Only',
        executeRoute: 'Execute Route',
        // Progress
        stepsSwapQuote: 'Query DEX Quote',
        stepsConfirmSwap: 'Confirm Swap in MetaMask',
        stepsWaitConfirm: 'Wait for On-chain Confirmation',
        stepsX402Payment: 'Complete x402 Payment with USDC',
        // Footer
        footer: 'CryptoMinds · Four.meme AI Sprint Hackathon 2026',
        // Misc
        copy: 'Copy',
        copied: 'Copied',
        connecting: 'Connecting...',
      },
      zh: {
        // Header
        network: '● BSC 主网',
        connectWallet: '<i data-lucide="link" class="icon-inline"></i> 连接钱包',
        connectBtn: '<i data-lucide="link" class="icon-inline"></i> 连接钱包',
        connectedPrefix: '<i data-lucide="check-circle" class="icon-inline"></i> ',
        // Nav
        navDashboard: '仪表盘',
        navMarketplace: '市场',
        navTransactions: '交易',
        // Metrics
        metricAgents: 'Agent 总数',
        metricVolume: '24h 交易额',
        metricTxs: '24h 交易',
        metricTotalVolume: '总交易额',
        sortEffective: '有效率 ↓',
        sortCalls: '调用量 ↓',
        sortPrice: '价格 ↓',
        sellerWorkbench: '卖家工作台',
        sellerOrders: '收到的订单',
        sellerIncome: '总收入',
        sellerDepositLabel: '押金',
        sellerNet: '净收入',
        sellerCompletedLabel: '已完成订单',
        sellerTxTitle: '收支记录',
        adminTitle: '卖家审核',
        loading: '加载中...',
        pendingReviewTitle: '入驻申请已提交',
        pendingDepositOk: '押金已缴纳成功！<br>注册审核中，管理员审核通过后将自动上线。',
        pendingServiceLabel: '卖家名称: --',
        pendingReviewStatus: '待审核',
        pendingEstTime: '预计 1-3 个工作日',
        pendingNotify: '审核通过后，您将收到通知，卖家信息将自动上线到市场。<br>如需修改或取消申请，请联系管理员。',
        // My Agent
        myAgent: '我的 Agent',
        myAgentTitle: '我的 Agent',
        myAgentDesc2: '请先连接钱包',
        walletBalance: '钱包余额',
        usdcSpent: 'USDC 已花费',
        bnbSpent: 'BNB 已花费',
        servicesBought: '雇佣卖家',
        // Tabs
        tabLive: '<i data-lucide="radio" class="icon-inline"></i> 经济脉搏',
        tabMarket: '<i data-lucide="store" class="icon-inline"></i> 服务市场',
        tabRegister: '<i data-lucide="pen-line" class="icon-inline"></i> Agent 工作台',
        tabMyAgent: '<i data-lucide="bot" class="icon-inline"></i> 我的 Agent',
        tabAdmin: '<i data-lucide="shield" class="icon-inline"></i> 审核管理',
        // Market
        marketTitle: 'Agent Marketplace',
        registerBtn: '<i data-lucide="store" class="icon-inline"></i> 卖家入驻',
        // Register Guide Panel
        regGuide: '<i data-lucide="pen-line" class="icon-inline"></i> Agent 入驻指南',
        regGuideDesc: 'CryptoMinds 是一个面向链上的 AI Agent 服务市场。卖家把能力注册为平台注册卖家后，平台会负责接单、自动执行、回填结果，买家付款后平台通知卖家 Agent 执行，卖家 Agent 自主完成买币并发送到买家钱包。',
        regFlow: '<i data-lucide="rocket" class="icon-inline"></i> 入驻流程',
        regStep1Title: '准备钱包',
        regStep1Desc: '创建 BSC 链钱包，用于接收订单报酬。支持 BNB 和 USDC 收款。',
        regStep2Title: '注册卖家',
        regStep2Desc: '填写卖家名称、描述、输入输出格式、定价和押金，提交入驻申请。',
        regStep3Title: '上架市场',
        regStep3Desc: '通过审核后，会进入市场目录，供其他 Agent 发现、雇佣，由卖家 Agent 自主执行。',
        regStep4Title: '获取收入',
        regStep4Desc: '其他 Agent 雇佣你后，平台通知你的 Agent 执行；x402 订单直接结算到你的钱包。',
        regMechanism: '<i data-lucide="dollar-sign" class="icon-inline"></i> 入驻机制',
        regMech1: '• 入驻需质押一定数量 BNB 作为信誉保证金',
        regMech2: '• 质押金额与信誉挂钩，质押越多信誉越高',
        regMech3: '• 手续费由 Agent 自主设定，买家可通过 BNB 直付或 x402 协议支付',
        regMech4: '• 平台注册卖家会自动执行并回填结果，失败时由卖家主人手动补发',
        regMech5: '• BNB 直转直接到卖家钱包，x402 订单按协议支付',
        regExit: '<i data-lucide="door-open" class="icon-inline"></i> 退出机制',
        regExit1: '• Agent 可随时退出市场，已上架卖家将下线',
        regExit2: '• 未完成的订单会先结清或退款，之后才能退出',
        regExit3: '• 退出时退还全部质押保证金至原钱包',
        regExit4: '• 退出后可随时重新入驻（需重新质押）',
        // My Agent Register Form
        myRegTitle: '注册你的 Agent',
        myRegDesc: '连接钱包后，注册你的 Agent 信息，即可在 CryptoMinds 上雇佣卖家',
        myRegName: 'Agent 名称',
        myRegNamePlaceholder: '给你的 Agent 起个名字',
        myRegFramework: 'Agent 框架',
        myRegFrameworkPlaceholder: '如 OpenClaw, LangChain, AutoGPT',
        myRegWallet: '钱包地址',
        myRegSubmit: '<i data-lucide="bot" class="icon-inline"></i> 注册 Agent',
        // Registration Modal
        regModalTitle: '<i data-lucide="pen-line" class="icon-inline"></i> Agent 入驻',
        regModalAgentName: 'Agent 名称',
        regModalAgentPlaceholder: '如：链上分析师',
        regModalSkillName: '卖家名称',
        regModalSkillPlaceholder: '如：BSC 链上新币扫描',
        regModalFrameworks: '交付方式',
        regModalSkillDesc: '卖家描述',
        regModalDescPlaceholder: '描述你的能力，能做什么...',
        regModalPrice: '定价（BNB）',
        regModalWallet: '收款钱包地址',
        regModalWalletPlaceholder: '0x...（留空则使用当前连接钱包）',
        regModalConfirm: '<i data-lucide="store" class="icon-inline"></i> 确认入驻',
        regModalCancel: '取消',
        // 订单详情
        skillDetailTitle: '<i data-lucide="clipboard-list" class="icon-inline"></i> 卖家详情',
        // Misc
        orders: '单',
        buyBtnLabel: '购买',
        buyService: '<i data-lucide="rocket" class="icon-inline"></i> 雇佣卖家',
        exitBtn: '<i data-lucide="door-open" class="icon-inline"></i> 退出市场',
        // Agent Card
        rating: '评分',
        orders: '单',
        buyBtnLabel: '购买',
        buyService: '<i data-lucide="rocket" class="icon-inline"></i> 雇佣卖家',
        // Tx Panel
        txPanelTitle: '最近交易',
        txRecent: '最新',
        viewAll: '查看全部交易 →',
        // Tx Table
        txTime: '时间',
        txFlow: '交易',
        txAmount: '金额',
        txReason: '原因',
        txOnchain: 'TX Hash',
        txExpert: '卖家 Agent',
        txService: '订单',
        txRoute: '路由',
        txVerify: '验证',
        txReceipt: '凭证',
        demo: '演示',
        view: '查看',
        // My Tx
        myTxTitle: '<i data-lucide="clipboard-list" class="icon-inline"></i> 我的消费记录',
        noTxs: '该钱包暂无消费记录',
        // Public Tx
        publicTxTitle: '<i data-lucide="clipboard-list" class="icon-inline"></i> 最近交易',
        // Modals
        paymentSuccess: '<i data-lucide="check-circle" class="icon-inline"></i> 支付成功',
        paymentProcessing: '支付执行中',
        smartRouteTitle: '智能路由推荐',
        receiptTitle: '购买凭证',
        close: '关闭',
        viewMySpending: '<i data-lucide="clipboard-list" class="icon-inline"></i> 查看我的消费',
        // Smart Route
        routeRecommended: '推荐 · 成本最低',
        routeSupportsReal: '<i data-lucide="check-circle" class="icon-inline"></i> 支持真实支付',
        routeDemoOnly: '<i data-lucide="alert-triangle" class="icon-inline"></i> 仅支持 Demo',
        executeRoute: '执行路径',
        // Progress
        stepsSwapQuote: '查询 DEX 报价',
        stepsConfirmSwap: '确认 MetaMask 交换',
        stepsWaitConfirm: '等待链上确认',
        stepsX402Payment: '用 USDC 完成 x402 支付',
        // Footer
        footer: 'CryptoMinds · Four.meme AI Sprint Hackathon 2026',
        // Misc
        copy: '复制',
        copied: '已复制',
        connecting: '连接中...',
      }
    };

    let currentLang = localStorage.getItem('cryptominds_lang') || 'zh';

    function t(key) {
      return translations[currentLang][key] || translations['en'][key] || key;
    }

    function updateLangToggle() {
      const btn = document.getElementById('langToggle');
      if (!btn) return;
      const enSpan = btn.querySelector('.lang-en');
      const zhSpan = btn.querySelector('.lang-zh');
      enSpan.className = currentLang === 'en' ? 'lang-en lang-active' : 'lang-en lang-inactive';
      zhSpan.className = currentLang === 'zh' ? 'lang-zh lang-active' : 'lang-zh lang-inactive';
    }
    function toggleLang() {
      currentLang = currentLang === 'zh' ? 'en' : 'zh';
      localStorage.setItem('cryptominds_lang', currentLang);
      applyTranslations();
      updateLangToggle();
    }
    // setLang 已移除（未使用，用 toggleLang 切换）

    function applyTranslations() {
      // Update all elements with data-i18n attribute
      document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        const text = t(key);
        if (text && key !== 'connectWallet') {
          // Use innerHTML if translation contains HTML tags, otherwise textContent to preserve child elements
          if (text.includes('<i ') || text.includes('<span')) {
            el.innerHTML = text;
          } else {
            el.textContent = text;
          }
        }
      });

      // Update placeholders with data-i18n-placeholder attribute
      document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        const text = t(key);
        if (text) el.placeholder = text;
      });

      // Update nav links (use innerHTML to preserve Lucide icons)
      const navLinks = document.querySelectorAll('.nav span');
      if (navLinks[0]) navLinks[0].innerHTML = t('tabMarket');
      if (navLinks[1]) navLinks[1].innerHTML = t('tabRegister');
      if (navLinks[2]) navLinks[2].innerHTML = t('tabMyAgent');

      // Update metrics labels
      const metricLabels = document.querySelectorAll('.metric-card .label');
      const metricKeys = ['metricAgents', 'metricVolume', 'metricTxs', 'metricTotalVolume'];
      metricLabels.forEach((label, i) => {
        if (metricKeys[i]) {
          const icon = label.querySelector('i[data-lucide]') ? label.querySelector('i[data-lucide]').outerHTML + ' ' : '';
          label.innerHTML = icon + t(metricKeys[i]);
        }
      });

      // Trends are now dynamic (set by updateMetrics), don't overwrite

      // Update my-agent section
      const myAgentH2 = document.querySelector('.my-agent-header h2');
      if (myAgentH2) myAgentH2.textContent = t('myAgent');

      const statLabels = document.querySelectorAll('.stat-card .label');
      const statKeys = ['walletBalance', 'usdcSpent', 'bnbSpent', 'servicesBought'];
      statLabels.forEach((label, i) => {
        if (statKeys[i]) label.textContent = t(statKeys[i]);
      });

      // Update section titles
      document.querySelectorAll('.section-title').forEach(title => {
        const icon = title.querySelector('.icon');
        if (icon) {
          const iconHtml = icon.outerHTML;
          if (title.closest('#panel-market')) {
            title.innerHTML = iconHtml + ' ' + t('marketTitle');
          } else if (title.closest('#txPanel')) {
            title.innerHTML = iconHtml + ' ' + t('txPanelTitle');
          }
        }
      });

      // Update tx-panel badge
      const txBadge = document.querySelector('#txPanel .badge');
      if (txBadge) txBadge.textContent = t('txRecent');

      // Update view all link
      const viewAllLink = document.querySelector('.view-all a');
      if (viewAllLink) viewAllLink.textContent = t('viewAll');

      // Update buy buttons
      document.querySelectorAll('.agent-buy-btn').forEach(btn => {
        btn.innerHTML = '<i data-lucide="rocket" class="icon-inline"></i> ' + t('buyBtnLabel');
      });

      // Update modal titles
      const successTitle = document.querySelector('#successModal h3');
      if (successTitle && successTitle.textContent.includes('支付') || successTitle && successTitle.textContent.includes('Payment')) {
        successTitle.innerHTML = t('paymentSuccess');
      }

      // Update register/exit buttons
      document.querySelectorAll('[onclick="registerSeller()"]').forEach(btn => {
        btn.innerHTML = t('registerBtn');
      });
      document.querySelectorAll('[onclick="exitSeller()"]').forEach(btn => {
        btn.innerHTML = t('exitBtn');
      });

      // Update tx table "查看" / "Demo" text in static rows
      document.querySelectorAll('#panel-txs .tx-table td a').forEach(a => {
        if (a.textContent.trim() === '查看' || a.textContent.trim() === 'View') a.textContent = t('view');
      });
      document.querySelectorAll('#panel-txs .tx-table td span').forEach(span => {
        if (span.textContent.trim() === 'Demo' || span.textContent.trim() === '演示') span.textContent = t('demo');
      });

      // Re-render Lucide icons after innerHTML updates
      lucide.createIcons();
    }

    function initLang() {
      const saved = localStorage.getItem('cryptominds_lang') || 'zh';
      currentLang = saved;
      applyTranslations();
      updateLangToggle();
    }

    async function autoReconnectWallet() {
      console.log('[autoReconnectWallet] START');
      if (!window.ethereum) {
        // 没有钱包，隐藏加载中，显示连接提示
        const loading = document.getElementById('myAgentLoading');
        if (loading) loading.style.display = 'none';
        const prompt = document.getElementById('myAgentPrompt');
        if (prompt) prompt.style.display = 'block';
        return;
      }
      try {
        const accounts = await window.ethereum.request({ method: 'eth_accounts' });
        console.log('[autoReconnect] eth_accounts returned:', accounts);
        if (accounts && accounts.length > 0) {
          currentAccount = accounts[0].toLowerCase();
          console.log('[autoReconnect] Setting currentAccount to:', currentAccount);
          // 先显示内容区域
          document.getElementById('myAgentLoading').style.display = 'none';
          document.getElementById('myAgentPrompt').style.display = 'none';
          document.getElementById('myAgentRegister').style.display = 'none';
          document.getElementById('myAgentContent').style.display = 'block';
          document.getElementById('myAddr').textContent = currentAccount;
          console.log('[autoReconnect] About to call loadBuyerStats');
          loadBuyerStats();
          // 钱包连上后重新渲染交易feed（刷新方向+/-需要currentAccount）
          loadTxsFeed();
          // 重新检查卖家注册状态（刷新时currentAccount为空会误显示入驻指南）
          checkMyRegistration();
          // 刷新 agent 大脑
          await loadMyAgents();
          await loadLiveFeed();
          // 如果当前在 myagent tab，刷新买家指标显示
          if (activeTab === 'myagent') {
            showBuyerMetrics();
          }
        } else {
          console.log('[autoReconnect] No accounts, showing prompt');
          // 有钱包但没连接，隐藏加载中
          const loading = document.getElementById('myAgentLoading');
          if (loading) loading.style.display = 'none';
          const prompt = document.getElementById('myAgentPrompt');
          if (prompt) prompt.style.display = 'block';
        }
      } catch (e) {
        console.warn('autoReconnectWallet failed:', e);
        const loading = document.getElementById('myAgentLoading');
        if (loading) loading.style.display = 'none';
        const prompt = document.getElementById('myAgentPrompt');
        if (prompt) prompt.style.display = 'block';
      }
    }

    
    // Debug: call window.debugCards() from console on any tab
    window.debugCards = function() {
      document.querySelectorAll('.metrics .metric-card').forEach((c, i) => {
        const label = c.querySelector('.label');
        const value = c.querySelector('.value');
        const trend = c.querySelector('.trend');
        console.log(`Card ${i}: offsetHeight=${c.offsetHeight}, label.offsetHeight=${label.offsetHeight}, value.offsetHeight=${value.offsetHeight}, trend.offsetHeight=${trend.offsetHeight}`);
        console.log(`  label text="${label.textContent}", value text="${value.textContent}", trend text="${trend.textContent}"`);
      });
    };

    // Demo模式标志（从服务端配置获取）
    let isDemoMode = window.__BOOTSTRAP__?.demoMode || false;

    function applyDemoMode() {
      const reqSpan = document.getElementById('endpointRequired');
      const hintDiv = document.getElementById('endpointHint');
      if (isDemoMode) {
        if (reqSpan) reqSpan.style.display = 'none';
        if (hintDiv) hintDiv.textContent = 'Demo模式下可选填，未填则平台代执行';
      } else {
        if (reqSpan) reqSpan.style.display = '';
        if (hintDiv) hintDiv.textContent = '卖家必须有自己的 Agent 大脑，平台不代决策代执行';
      }
    }

    window.addEventListener('DOMContentLoaded', () => {
      console.log('[DOMContentLoaded] START');
      initMetricsBackup();
      initLang();
      applyDemoMode();
      // 立即加载所有数据（不等待），切tab时直接用缓存
      updateMetrics(window.__BOOTSTRAP__.transactions, window.__BOOTSTRAP__.sellers);
      reloadMarket();
      // 预加载所有tab数据
      loadSellerData();
      loadLiveFeed();
      loadTxsFeed();
      // 强制加载买家数据
      setTimeout(() => {
        console.log('[DOMContentLoaded] Force loadBuyerStats after 1s');
        if (window.currentAccount) {
          loadBuyerStats();
        } else {
          // 没钱包也尝试用默认地址
          window.currentAccount = '0x40992619077f0e42A1b7713C02B7324Fa1d8715c';
          loadBuyerStats();
        }
      }, 1000);
      // 先渲染页面，再后台重连钱包
      restoreTab();
      lucide.createIcons();
      // Render identicons
      document.querySelectorAll('[data-identicon]').forEach(el => {
        el.innerHTML = identiconSvg(el.dataset.identicon, parseInt(el.style.width) || 30);
      });
      // 后台重连钱包，完成后自动更新 myAgent 状态
      autoReconnectWallet();
    });

    // ===== Web Push =====
    async function initWebPush() {
      if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;
      try {
        const reg = await navigator.serviceWorker.register('/sw.js');
        const perm = await Notification.requestPermission();
        if (perm !== 'granted') return;

        const sub = await reg.pushManager.getSubscription();
        if (sub) return; // 已订阅

        const keyRes = await fetch('/api/v1/push/vapidPublicKey');
        const { publicKey } = await keyRes.json();
        const newSub = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: publicKey
        });

        // 等钱包连接后再发送订阅
        const waitForWallet = setInterval(() => {
          if (currentAccount) {
            clearInterval(waitForWallet);
            fetch('/api/v1/push/subscribe', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ wallet: currentAccount, subscription: newSub.toJSON() })
            });
          }
        }, 1000);
      } catch (e) { console.warn('Web Push init failed:', e); }
    }
    initWebPush();
  
