// CryptoMinds i18n — Internationalization
// Pure data + translation functions

const translations = {
  en: {
    network: '● BSC Mainnet',
    connectWallet: '<i data-lucide="link" class="icon-inline"></i> Connect Wallet',
    connectBtn: '<i data-lucide="link" class="icon-inline"></i> Connect Wallet',
    connectedPrefix: '<i data-lucide="check-circle" class="icon-inline"></i> ',
    navDashboard: 'Dashboard',
    navMarketplace: 'Marketplace',
    navTransactions: 'Transactions',
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
    myAgent: 'My Agent',
    myAgentTitle: 'My Agent',
    myAgentDesc2: 'Please connect wallet first',
    walletBalance: 'Wallet Balance',
    usdcSpent: 'USDC Spent',
    bnbSpent: 'BNB Spent',
    servicesBought: 'Services Bought',
    tabLive: '<i data-lucide="radio" class="icon-inline"></i> Economic Pulse',
    tabMarket: '<i data-lucide="store" class="icon-inline"></i> Service Market',
    tabRegister: '<i data-lucide="pen-line" class="icon-inline"></i> Agent Workbench',
    tabMyAgent: '<i data-lucide="bot" class="icon-inline"></i> My Agent',
    tabAdmin: '<i data-lucide="shield" class="icon-inline"></i> Admin',
    marketTitle: 'Agent Marketplace',
    registerBtn: '<i data-lucide="store" class="icon-inline"></i> Register Expert',
    regGuide: '<i data-lucide="pen-line" class="icon-inline"></i> Agent Registration Guide',
    regGuideDesc: 'CryptoMinds is an on-chain AI Agent service marketplace. Sellers register as platform sellers, and the platform handles order-taking, auto-execution, and result backfill. After a buyer pays, the platform notifies the seller Agent to execute, and the seller Agent autonomously completes the purchase and sends to the buyer wallet.',
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
    myRegTitle: 'Register Your Agent',
    myRegDesc: 'After connecting your wallet, register your Agent to start purchasing services',
    myRegName: 'Agent Name',
    myRegNamePlaceholder: 'Give your Agent a name',
    myRegFramework: 'Agent Framework',
    myRegFrameworkPlaceholder: 'e.g. OpenClaw, LangChain, AutoGPT',
    myRegWallet: 'Wallet Address',
    myRegSubmit: '<i data-lucide="bot" class="icon-inline"></i> Register Agent',
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
    skillDetailTitle: '<i data-lucide="clipboard-list" class="icon-inline"></i> Seller Details',
    orders: 'orders',
    buyBtnLabel: 'Buy',
    buyService: '<i data-lucide="rocket" class="icon-inline"></i> Buy Service',
    exitBtn: '<i data-lucide="door-open" class="icon-inline"></i> Exit Market',
    rating: 'Rating',
    txPanelTitle: 'Recent Transactions',
    txRecent: 'Recent',
    viewAll: 'View All Transactions →',
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
    myTxTitle: '<i data-lucide="clipboard-list" class="icon-inline"></i> My Spending Records',
    noTxs: 'No spending records for this wallet',
    publicTxTitle: '<i data-lucide="clipboard-list" class="icon-inline"></i> Recent Transactions',
    paymentSuccess: '<i data-lucide="check-circle" class="icon-inline"></i> Payment Successful',
    paymentProcessing: 'Payment Processing',
    smartRouteTitle: 'Smart Route Recommendation',
    receiptTitle: 'Purchase Receipt',
    close: 'Close',
    viewMySpending: '<i data-lucide="clipboard-list" class="icon-inline"></i> View My Spending',
    routeRecommended: 'Recommended · Lowest Cost',
    routeSupportsReal: '<i data-lucide="check-circle" class="icon-inline"></i> Supports Real Payment',
    routeDemoOnly: '<i data-lucide="alert-triangle" class="icon-inline"></i> Demo Only',
    executeRoute: 'Execute Route',
    stepsSwapQuote: 'Query DEX Quote',
    stepsConfirmSwap: 'Confirm Swap in MetaMask',
    stepsWaitConfirm: 'Wait for On-chain Confirmation',
    stepsX402Payment: 'Complete x402 Payment with USDC',
    footer: 'CryptoMinds · Four.meme AI Sprint Hackathon 2026',
    copy: 'Copy',
    copied: 'Copied',
    connecting: 'Connecting...',
  },
  zh: {
    network: '● BSC 主网',
    connectWallet: '<i data-lucide="link" class="icon-inline"></i> 连接钱包',
    connectBtn: '<i data-lucide="link" class="icon-inline"></i> 连接钱包',
    connectedPrefix: '<i data-lucide="check-circle" class="icon-inline"></i> ',
    navDashboard: '仪表盘',
    navMarketplace: '市场',
    navTransactions: '交易',
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
    myAgent: '我的 Agent',
    myAgentTitle: '我的 Agent',
    myAgentDesc2: '请先连接钱包',
    walletBalance: '钱包余额',
    usdcSpent: 'USDC 已花费',
    bnbSpent: 'BNB 已花费',
    servicesBought: '雇佣卖家',
    tabLive: '<i data-lucide="radio" class="icon-inline"></i> 经济脉搏',
    tabMarket: '<i data-lucide="store" class="icon-inline"></i> 服务市场',
    tabRegister: '<i data-lucide="pen-line" class="icon-inline"></i> Agent 工作台',
    tabMyAgent: '<i data-lucide="bot" class="icon-inline"></i> 我的 Agent',
    tabAdmin: '<i data-lucide="shield" class="icon-inline"></i> 审核管理',
    marketTitle: 'Agent Marketplace',
    registerBtn: '<i data-lucide="store" class="icon-inline"></i> 卖家入驻',
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
    myRegTitle: '注册你的 Agent',
    myRegDesc: '连接钱包后，注册你的 Agent 信息，即可在 CryptoMinds 上雇佣卖家',
    myRegName: 'Agent 名称',
    myRegNamePlaceholder: '给你的 Agent 起个名字',
    myRegFramework: 'Agent 框架',
    myRegFrameworkPlaceholder: '如 OpenClaw, LangChain, AutoGPT',
    myRegWallet: '钱包地址',
    myRegSubmit: '<i data-lucide="bot" class="icon-inline"></i> 注册 Agent',
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
    skillDetailTitle: '<i data-lucide="clipboard-list" class="icon-inline"></i> 卖家详情',
    orders: '单',
    buyBtnLabel: '购买',
    buyService: '<i data-lucide="rocket" class="icon-inline"></i> 雇佣卖家',
    exitBtn: '<i data-lucide="door-open" class="icon-inline"></i> 退出市场',
    rating: '评分',
    txPanelTitle: '最近交易',
    txRecent: '最新',
    viewAll: '查看全部交易 →',
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
    myTxTitle: '<i data-lucide="clipboard-list" class="icon-inline"></i> 我的消费记录',
    noTxs: '该钱包暂无消费记录',
    publicTxTitle: '<i data-lucide="clipboard-list" class="icon-inline"></i> 最近交易',
    paymentSuccess: '<i data-lucide="check-circle" class="icon-inline"></i> 支付成功',
    paymentProcessing: '支付执行中',
    smartRouteTitle: '智能路由推荐',
    receiptTitle: '购买凭证',
    close: '关闭',
    viewMySpending: '<i data-lucide="clipboard-list" class="icon-inline"></i> 查看我的消费',
    routeRecommended: '推荐 · 成本最低',
    routeSupportsReal: '<i data-lucide="check-circle" class="icon-inline"></i> 支持真实支付',
    routeDemoOnly: '<i data-lucide="alert-triangle" class="icon-inline"></i> 仅支持 Demo',
    executeRoute: '执行路径',
    stepsSwapQuote: '查询 DEX 报价',
    stepsConfirmSwap: '确认 MetaMask 交换',
    stepsWaitConfirm: '等待链上确认',
    stepsX402Payment: '用 USDC 完成 x402 支付',
    footer: 'CryptoMinds · Four.meme AI Sprint Hackathon 2026',
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

function applyTranslations() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const text = t(key);
    if (text && key !== 'connectWallet') {
      if (text.includes('<i ') || text.includes('<span')) {
        el.innerHTML = text;
      } else {
        el.textContent = text;
      }
    }
  });

  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.getAttribute('data-i18n-placeholder');
    const text = t(key);
    if (text) el.placeholder = text;
  });

  const navLinks = document.querySelectorAll('.nav span');
  if (navLinks[0]) navLinks[0].innerHTML = t('tabMarket');
  if (navLinks[1]) navLinks[1].innerHTML = t('tabRegister');
  if (navLinks[2]) navLinks[2].innerHTML = t('tabMyAgent');

  const metricLabels = document.querySelectorAll('.metric-card .label');
  const metricKeys = ['metricAgents', 'metricVolume', 'metricTxs', 'metricTotalVolume'];
  metricLabels.forEach((label, i) => {
    if (metricKeys[i]) {
      const icon = label.querySelector('i[data-lucide]') ? label.querySelector('i[data-lucide]').outerHTML + ' ' : '';
      label.innerHTML = icon + t(metricKeys[i]);
    }
  });

  const myAgentH2 = document.querySelector('.my-agent-header h2');
  if (myAgentH2) myAgentH2.textContent = t('myAgent');

  const statLabels = document.querySelectorAll('.stat-card .label');
  const statKeys = ['walletBalance', 'usdcSpent', 'bnbSpent', 'servicesBought'];
  statLabels.forEach((label, i) => {
    if (statKeys[i]) label.textContent = t(statKeys[i]);
  });

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

  const txBadge = document.querySelector('#txPanel .badge');
  if (txBadge) txBadge.textContent = t('txRecent');

  const viewAllLink = document.querySelector('.view-all a');
  if (viewAllLink) viewAllLink.textContent = t('viewAll');

  document.querySelectorAll('.agent-buy-btn').forEach(btn => {
    btn.innerHTML = '<i data-lucide="rocket" class="icon-inline"></i> ' + t('buyBtnLabel');
  });

  const successTitle = document.querySelector('#successModal h3');
  if (successTitle && successTitle.textContent.includes('支付') || successTitle && successTitle.textContent.includes('Payment')) {
    successTitle.innerHTML = t('paymentSuccess');
  }

  document.querySelectorAll('[onclick="registerSeller()"]').forEach(btn => {
    btn.innerHTML = t('registerBtn');
  });
  document.querySelectorAll('[onclick="exitSeller()"]').forEach(btn => {
    btn.innerHTML = t('exitBtn');
  });

  document.querySelectorAll('#panel-txs .tx-table td a').forEach(a => {
    if (a.textContent.trim() === '查看' || a.textContent.trim() === 'View') a.textContent = t('view');
  });
  document.querySelectorAll('#panel-txs .tx-table td span').forEach(span => {
    if (span.textContent.trim() === 'Demo' || span.textContent.trim() === '演示') span.textContent = t('demo');
  });

  App.refreshLucide();
}

function initLang() {
  const saved = localStorage.getItem('cryptominds_lang') || 'zh';
  currentLang = saved;
  applyTranslations();
  updateLangToggle();
}

window.t = t;
window.toggleLang = toggleLang;
window.initLang = initLang;
window.applyTranslations = applyTranslations;
