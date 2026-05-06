// CryptoMinds App State & Event Bus
// All modules read from window.App instead of bare globals

window.App = {
  currentAccount: null,
  activeTab: 'market',
  isDemoMode: false,
  isPaymentInProgress: false,
  progressRetryAction: null,
  marketServices: new Map(),
  marketLabels: [],

  // Event bus for cross-module communication
  _listeners: {},
  on(event, fn) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(fn);
  },
  off(event, fn) {
    if (!this._listeners[event]) return;
    this._listeners[event] = this._listeners[event].filter(f => f !== fn);
  },
  emit(event, data) {
    if (!this._listeners[event]) return;
    for (const fn of this._listeners[event]) {
      try { fn(data); } catch(e) { console.error(`App.emit('${event}') error:`, e); }
    }
  },

  // Lucide icon refresh (called ~20 times across modules)
  refreshLucide() {
    if (typeof lucide !== 'undefined') lucide.createIcons();
  }
};

// Chain configuration
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

// Market metric card defaults
const MARKET_DEFAULTS = [
  { label: '<i data-lucide="bot" class="icon-inline"></i> Agent 总数', valueId: 'metricAgents', trendId: 'trendAgents' },
  { label: '<i data-lucide="trending-up" class="icon-inline"></i> 近24h 交易额', valueId: 'metricVolume', trendId: 'trendVolume' },
  { label: '<i data-lucide="zap" class="icon-inline"></i> 近24h 交易', valueId: 'metricTxs', trendId: 'trendTxs' },
  { label: '<i data-lucide="database" class="icon-inline"></i> 总交易额', valueId: 'metricTotalVolume', trendId: 'trendTotalVolume' },
];
