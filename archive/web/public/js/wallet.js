// CryptoMinds Wallet Module
// Wallet connection, reconnection, signing, chain switching

function getChainConfig(chain) {
  return CHAIN_CONFIG[chain];
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

async function signWalletMessage(wallet, message) {
  if (!window.ethereum) throw new Error('需要钱包签名');
  return window.ethereum.request({
    method: 'personal_sign',
    params: [message, wallet]
  });
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
    'Action: ' + action,
    'Purchase: ' + purchaseId,
    'Buyer: ' + (buyerWallet || '').toLowerCase(),
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

async function checkAgentRegistered(wallet) {
  try {
    const res = await fetch('/api/v1/agents');
    const agents = await res.json();
    return agents.find(a => (a.wallet || '').toLowerCase() === wallet.toLowerCase());
  } catch(e) { return null; }
}

async function connectWallet() {
  if (!window.ethereum) {
    showError('请安装 MetaMask 钱包扩展<br><a href="https://metamask.io" target="_blank" style="color:#8b5cf6">前往安装 →</a>');
    return;
  }
  try {
    const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
    App.currentAccount = accounts[0].toLowerCase();
    document.getElementById('connectBtn').innerHTML = '<i data-lucide="check-circle" class="icon-inline" style="color:#fff"></i> ' + App.currentAccount.slice(0, 6) + '...' + App.currentAccount.slice(-4);
    App.refreshLucide();
    document.getElementById('connectBtn').classList.add('connected');

    document.getElementById('myAgentLoading').classList.add('hidden');
    document.getElementById('myAgentPrompt').style.display = 'none';
    document.getElementById('myAgentContent').style.display = 'block';
    document.getElementById('myAddr').textContent = App.currentAccount;

    try {
      const res = await fetch('/api/v1/balances');
      const data = await res.json();
      const agent = Object.values(data).find(a => a.addr.toLowerCase() === App.currentAccount);
      if (App.activeTab === 'myagent') {
        const balEl2 = document.getElementById('buyerBalance');
        if (balEl2) balEl2.textContent = agent ? parseFloat(agent.balance).toFixed(4) + ' BNB' : '0.0000 BNB';
      }

      loadNotifications();
      setInterval(loadNotifications, 10000);

      try {
        const adminRes = await fetch('/api/admin-check?wallet=' + App.currentAccount);
        const adminData = await adminRes.json();
        if (adminData.isAdmin) {
          document.getElementById('adminTab').classList.remove('hidden');
        }
      } catch(e) { /* 非管理员 */ }
    } catch(e) {
      if (App.activeTab === 'myagent') document.getElementById('buyerBalance').textContent = '加载失败';
    }

    // Notify other modules that wallet changed
    App.emit('wallet-changed', App.currentAccount);
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

async function autoReconnectWallet() {
  console.log('[autoReconnectWallet] START');
  if (!window.ethereum) {
    const loading = document.getElementById('myAgentLoading');
    if (loading) loading.classList.add('hidden');
    const prompt = document.getElementById('myAgentPrompt');
    if (prompt) prompt.style.display = 'block';
    return;
  }
  try {
    const accounts = await window.ethereum.request({ method: 'eth_accounts' });
    console.log('[autoReconnect] eth_accounts returned:', accounts);
    if (accounts && accounts.length > 0) {
      App.currentAccount = accounts[0].toLowerCase();
      console.log('[autoReconnect] Setting currentAccount to:', App.currentAccount);
      document.getElementById('myAgentLoading').classList.add('hidden');
      document.getElementById('myAgentPrompt').style.display = 'none';
      document.getElementById('myAgentContent').style.display = 'block';
      document.getElementById('myAddr').textContent = App.currentAccount;

      console.log('[autoReconnect] About to call loadBuyerStats');
    } else {
      console.log('[autoReconnect] No accounts, showing prompt');
      const loading = document.getElementById('myAgentLoading');
      if (loading) loading.classList.add('hidden');
      const prompt = document.getElementById('myAgentPrompt');
      if (prompt) prompt.style.display = 'block';
    }
  } catch (e) {
    console.warn('autoReconnectWallet failed:', e);
    const loading = document.getElementById('myAgentLoading');
    if (loading) loading.classList.add('hidden');
    const prompt = document.getElementById('myAgentPrompt');
    if (prompt) prompt.style.display = 'block';
  }
}

async function autoLoadWalletData() {
  if (!App.currentAccount) {
    console.log('[autoLoadWalletData] currentAccount is null, skipping');
    return;
  }

  const wallet = getActiveWallet();
  if (App.currentAccount) {
    document.getElementById('connectBtn').innerHTML = '<i data-lucide="check-circle" class="icon-inline" style="color:#fff"></i> ' + App.currentAccount.slice(0, 6) + '...' + App.currentAccount.slice(-4);
    App.refreshLucide();
    document.getElementById('connectBtn').classList.add('connected');
  }

  document.getElementById('myAgentLoading').classList.add('hidden');
  document.getElementById('myAgentPrompt').classList.add('hidden');

  const registered = await checkAgentRegistered(wallet);
  document.getElementById('myAgentRegister').classList.add('hidden');
  document.getElementById('myAgentContent').classList.remove('hidden');

  // 只在 myagent tab 时显示 myAgent 面板
  if (App.activeTab === 'myagent') {
    document.getElementById('myAgent').classList.remove('hidden');
  }

  document.getElementById('myAddr').textContent = wallet;

  try {
    const res = await fetch('/api/v1/balances');
    const data = await res.json();
    const agent = Object.values(data).find(a => a.addr.toLowerCase() === wallet);
    if (App.activeTab === 'myagent') {
      const balEl = document.getElementById('buyerBalance');
      if (balEl) balEl.textContent = agent ? parseFloat(agent.balance).toFixed(4) + ' BNB' : '0.0000 BNB';
    }
  } catch(e) {}

  loadBuyerStats();
  if (!window._brainPollTimer) {
    window._brainPollTimer = setInterval(() => {
      if (App.currentAccount && App.activeTab === 'myagent') loadBuyerStats();
    }, 15000);
  }

  loadNotifications();
  setInterval(loadNotifications, 10000);
}

// Wallet event listeners
if (window.ethereum) {
  window.ethereum.on('accountsChanged', (accounts) => {
    if (accounts.length === 0) {
      App.currentAccount = null;
      document.getElementById('connectBtn').innerHTML = '<i data-lucide="wallet" class="icon-inline" style="color:#fff"></i> 连接钱包';
      App.refreshLucide();
      document.getElementById('connectBtn').classList.remove('connected');
      showTab('marketplace');
      console.log('[wallet] 断开连接');
      App.emit('wallet-changed', null);
    } else {
      App.currentAccount = accounts[0].toLowerCase();
      document.getElementById('connectBtn').innerHTML = '<i data-lucide="check-circle" class="icon-inline" style="color:#fff"></i> ' + App.currentAccount.slice(0, 6) + '...' + App.currentAccount.slice(-4);
      App.emit('wallet-changed', App.currentAccount);
      showTab('myagent');
      console.log('[wallet] 切换账号:', App.currentAccount);
    }
  });
  window.ethereum.on('chainChanged', () => {
    window.location.reload();
  });
}

window.connectWallet = connectWallet;
window.autoReconnectWallet = autoReconnectWallet;
window.autoLoadWalletData = autoLoadWalletData;
window.checkAgentRegistered = checkAgentRegistered;
window.signWalletMessage = signWalletMessage;
window.signX402Request = signX402Request;
window.signBuyerAction = signBuyerAction;
window.ensureChain = ensureChain;
window.getChainConfig = getChainConfig;

// API 文档
function copyApiDocLink() {
  const link = window.location.origin + '/api/docs';
  navigator.clipboard.writeText(link).then(() => {
    showNotice('链接已复制: ' + link);
  }).catch(() => {
    showNotice('链接: ' + link);
  });
}

function downloadApiDoc() {
  const doc = {
    name: "CryptoMinds API",
    version: "1.0",
    description: "Agent 交易市场 API - 你的 Agent 调用这些 API 来购物",
    base_url: window.location.origin,
    endpoints: [
      {
        method: "GET",
        path: "/api/v1/sellers",
        description: "获取卖家列表（含评分、价格、服务描述）",
        note: "你的 Agent 必须自己分析这个列表，选择卖家"
      },
      {
        method: "POST",
        path: "/api/v1/orders/create",
        description: "创建订单",
        body: {
          buyer_wallet: "你的钱包地址",
          seller_wallet: "你选择的卖家地址",
          price: 0.01,
          input: "任务描述"
        },
        note: "必须指定卖家，平台不帮你选"
      },
      {
        method: "GET",
        path: "/api/v1/orders/:id",
        description: "查询订单状态"
      },
      {
        method: "GET",
        path: "/api/v1/orders/:id/result",
        description: "获取执行结果"
      },
      {
        method: "GET",
        path: "/api/v1/purchases?wallet=你的钱包地址",
        description: "获取购买记录"
      }
    ],
    important: "平台只提供数据，不帮买家做决策。你的 Agent 必须自己分析、选择、下单。"
  };

  const blob = new Blob([JSON.stringify(doc, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'cryptominds_api.json';
  a.click();
  URL.revokeObjectURL(url);
}

window.copyApiDocLink = copyApiDocLink;
window.downloadApiDoc = downloadApiDoc;
