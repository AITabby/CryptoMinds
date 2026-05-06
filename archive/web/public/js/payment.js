// CryptoMinds Payment Module
// All payment-related functions: route validation, execution, escrow, progress modal, success modal, x402 verification

// ===== Constants =====
const PANCAKE_ROUTER = '0x10ED43C718714eb63d5aA57B78B54704E256024E';
const WBNB = '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c';

// ===== Route Validation =====

function isRealSwapRoute(route) {
  return Boolean(
    App.currentAccount &&
    window.ethereum &&
    route &&
    route.route_type === 'swap' &&
    route.symbol === 'USDC' &&
    route.chain === 'bsc'
  );
}

function isRealSplitRoute(route) {
  return Boolean(
    App.currentAccount &&
    window.ethereum &&
    route &&
    route.route_type === 'split' &&
    route.symbol === 'USDC' &&
    Array.isArray(route.split_details) &&
    route.split_details.length >= 1 &&
    route.split_details.every(part => CHAIN_CONFIG[part.chain])
  );
}

function isRealX402Route(route) {
  return Boolean(
    App.currentAccount &&
    window.ethereum &&
    route &&
    route.route_type === 'direct' &&
    route.symbol === 'USDC' &&
    CHAIN_CONFIG[route.chain]
  );
}

function isRealBNBDirectRoute(route) {
  return Boolean(
    App.currentAccount &&
    window.ethereum &&
    route &&
    route.route_type === 'direct' &&
    (route.symbol === 'BNB' || route.symbol === 'ETH') &&
    CHAIN_CONFIG[route.chain]
  );
}

// ===== Main Payment Entry Point =====

async function executePayment(serviceId, route) {
  if (App.isPaymentInProgress) {
    showNotice('<i data-lucide="loader" class="icon-inline spin"></i> 上一笔支付正在处理中，请等待完成...');
    return;
  }
  App.isPaymentInProgress = true;

  const wallet = getActiveWallet();
  const service = getServiceById(serviceId);

  if (!service) {
    showError('卖家信息缺失，请刷新页面后重试');
    App.isPaymentInProgress = false;
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
      if (!document.getElementById('myAgent').classList.contains('hidden')) {
        autoLoadWalletData();
      }
    } else {
      const err = data.error || '未知错误';
      showError('购买失败：' + err);
    }
  } catch (e) {
    showError('网络请求失败：' + e.message);
  } finally {
    App.isPaymentInProgress = false;
  }
}

// ===== BNB Direct Payment =====

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
    ], `<p class="text-primary font-number">TxHash: ${txHash}</p><p class="text-up text-xs">🔒 BNB 已锁入担保合约，卖家交付后释放</p>`);

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
    ], `<p class="text-primary font-number">TxHash: ${txHash}</p><p class="text-down text-xs">⚠️ BNB 直付卖家，无担保保护</p>`);

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

// ===== Escrow Contract Loader =====

let _escrowContract = null;
async function loadEscrowContract(address, abi) {
  if (_escrowContract && _escrowContract.options?.address === address) return _escrowContract;
  // 使用 web3.js 从 MetaMask provider 创建
  const web3Provider = new Web3(window.ethereum);
  _escrowContract = new web3Provider.eth.Contract(abi, address);
  return _escrowContract;
}

// ===== Swap Payment (BNB → USDC via PancakeSwap, then x402) =====

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
  ], `<p class="text-primary font-number">Swap TxHash: ${swapTxHash}</p>`);

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
  ], `<p class="text-primary font-number">Swap: ${swapTxHash.slice(0, 16)}...<br>Payment: ${usdcTxHash.slice(0, 16)}...</p>`);

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

// ===== Split Payment (multi-chain, multi-step) =====

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
    })), `<p class="text-primary font-number">TxHash: ${txHash}</p>`);
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
  ], `<p class="text-primary">共 ${txHashes.length} 笔交易</p>`);

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

// ===== x402 Direct Payment (USDC) =====

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
  ], `<p class="text-primary font-number">TxHash: ${txHash}</p>`);
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

// ===== Swap Calldata Builder =====

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

// ===== Progress Modal =====

function openProgressModal(title, bodyHtml, retryLabel = '', retryAction = null) {
  document.getElementById('progressTitle').textContent = title;
  document.getElementById('progressBody').innerHTML = bodyHtml;
  const actions = document.getElementById('progressActions');
  App.progressRetryAction = retryAction;
  if (retryLabel && retryAction) {
    actions.classList.remove('hidden');
    actions.innerHTML = `<button onclick="runProgressRetry()" class="btn-primary">${retryLabel}</button>`;
  } else {
    actions.classList.add('hidden');
    actions.innerHTML = '';
  }
  document.getElementById('progressModal').style.display = 'flex';
}

function closeProgressModal() {
  document.getElementById('progressModal').style.display = 'none';
  App.progressRetryAction = null;
}

function runProgressRetry() {
  if (typeof App.progressRetryAction === 'function') {
    App.progressRetryAction();
  }
}

function renderProgressSteps(title, status, steps, extraHtml = '', retryLabel = '', retryAction = null) {
  const stepsHtml = (steps || []).map((step, index) => {
    const colorClass = step.state === 'done' ? 'text-up' : step.state === 'active' ? 'text-primary' : step.state === 'error' ? 'text-down' : 'text-muted';
    const prefix = step.state === 'done' ? '<i data-lucide="check-circle" class="icon-inline text-up"></i>' : step.state === 'active' ? '<i data-lucide="loader" class="icon-inline text-primary"></i>' : step.state === 'error' ? '<i data-lucide="x-circle" class="icon-inline text-down"></i>' : '<i data-lucide="circle" class="icon-inline text-muted"></i>';
    return `<div class="${colorClass}" style="padding:8px 0;">${prefix} ${index + 1}. ${step.label}</div>`;
  }).join('');
  openProgressModal(title, `<p class="text-body" style="margin-bottom:12px;">${status}</p>${extraHtml}<div style="margin-top:8px;">${stepsHtml}</div>`, retryLabel, retryAction);
  App.refreshLucide();
}

// ===== Transaction Receipt Polling =====

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

// ===== x402 Verification with Retry =====

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
      ], txHash ? `<p class="text-primary font-number">TxHash: ${txHash}</p>` : '', '重试验证', retryAction);
      throw new Error(message);
    }

    renderProgressSteps('链上验证中', `验证尚未通过，正在重试第 ${attempt + 2} 次...`, [
      { label: `交易已广播 (${routeLabel})`, state: 'done' },
      { label: '等待链上确认', state: 'done' },
      { label: '提交 x402 验证', state: 'active' },
    ], txHash ? `<p class="text-primary font-number">TxHash: ${txHash}</p>` : '');
    await new Promise(resolve => setTimeout(resolve, 2000 * (attempt + 1)));
  }
  throw new Error('支付验证超时');
}

// ===== Success Modal =====

function showSuccessModal(title, data) {
  let html = `<div style="margin-bottom:12px;">`;
  html += `<p><span class="status-dot confirmed"></span><strong>${title}</strong></p>`;
  if (data.sellerService) html += `<p>卖家执行：${data.sellerService}</p>`;
  if (data.expert) html += `<p>卖家：${data.expert}</p>`;
  if (data.amount) html += `<p>金额：<span class="text-up font-number">${data.amount}</span></p>`;
  if (data.route) html += `<p>路由：${data.route}</p>`;
  if (data.paymentMode) html += `<p>支付方式：${data.paymentMode}</p>`;
  if (data.paymentStatus) html += `<p>状态：${data.paymentStatus}</p>`;
  if (data.txHash && /^0x[a-fA-F0-9]{64}$/.test(data.txHash)) {
    const explorerBase = data.chain === 'base' ? CHAIN_CONFIG.base.explorerBaseUrl : CHAIN_CONFIG.bsc.explorerBaseUrl;
    html += `<p>交易哈希：</p>`;
    html += `<div class="bg-canvas border-hairline rounded-xl" style="padding:10px; margin-top:4px; display:flex; align-items:center; justify-content:space-between; gap:8px;">`;
    html += `<a href="${explorerBase}/tx/${data.txHash}" target="_blank" class="tx-hash-link"><i data-lucide="external-link" class="icon-inline"></i> ${data.txHash.slice(0, 20)}...${data.txHash.slice(-8)}</a>`;
    html += `<button onclick="copyToClipboard('${data.txHash}', this)" class="btn-muted-tint" style="padding:4px 8px; font-size:11px;"><i data-lucide="copy" class="icon-inline"></i> 复制</button>`;
    html += `</div>`;
  }
  if (data.txHint) html += `<p class="text-muted text-sm" style="margin-top:8px;">${data.txHint}</p>`;

  // 如果卖家有API配置，显示调用信息
  if (data.sellerServiceApi && data.sellerServiceApi.endpoint) {
    html += `<div class="bg-canvas border-primary rounded-xl" style="margin-top:16px; padding:14px;">`;
    html += `<div class="panel-heading" style="margin-bottom:10px;"><i data-lucide="zap" class="icon-inline"></i> 卖家调用信息</div>`;
    html += `<div class="input-label">Endpoint:</div>`;
    html += `<div class="flex-center" style="margin-bottom:10px;">`;
    html += `<code class="bg-card border-hairline rounded-md text-up font-number" style="flex:1; padding:8px 10px; font-size:12px; word-break:break-all;">${data.sellerServiceApi.endpoint}</code>`;
    html += `<button onclick="copyToClipboard('${data.sellerServiceApi.endpoint}', this)" class="btn-muted-tint" style="padding:6px 10px; font-size:11px; white-space:nowrap;"><i data-lucide="copy" class="icon-inline"></i> 复制</button>`;
    html += `</div>`;
    if (data.sellerServiceApi.example) {
      html += `<div class="input-label">调用示例:</div>`;
      html += `<pre class="bg-card border-hairline rounded-md text-primary font-number" style="padding:10px; font-size:11px; overflow-x:auto; white-space:pre-wrap; margin:0;">${data.sellerServiceApi.example}</pre>`;
    }
    html += `</div>`;
  }

  html += `<div class="flex-gap" style="margin-top:16px;">`;
  html += `<button onclick="closeSuccessModal(); showTab('myagent'); autoLoadWalletData();" class="btn-primary">${t('viewMySpending')}</button>`;
  html += `<button onclick="closeSuccessModal()" class="btn-secondary">${t('close')}</button>`;
  html += `</div>`;
  html += `</div>`;
  document.getElementById('successBody').innerHTML = html;
  document.getElementById('successModal').style.display = 'flex';
  App.refreshLucide();
}

function closeSuccessModal() {
  document.getElementById('successModal').style.display = 'none';
}

function closeSmartRoute() {
  document.getElementById('smartRouteModal').style.display = 'none';
}

// ===== Expose to window for onclick handlers and other modules =====
window.PANCAKE_ROUTER = PANCAKE_ROUTER;
window.WBNB = WBNB;
window.isRealSwapRoute = isRealSwapRoute;
window.isRealSplitRoute = isRealSplitRoute;
window.isRealX402Route = isRealX402Route;
window.isRealBNBDirectRoute = isRealBNBDirectRoute;
window.executePayment = executePayment;
window.executeRealBNBDirectPayment = executeRealBNBDirectPayment;
window.executeRealSwapPayment = executeRealSwapPayment;
window.executeRealSplitPayment = executeRealSplitPayment;
window.executeRealX402Payment = executeRealX402Payment;
window.loadEscrowContract = loadEscrowContract;
window.buildSwapCalldata = buildSwapCalldata;
window.openProgressModal = openProgressModal;
window.closeProgressModal = closeProgressModal;
window.runProgressRetry = runProgressRetry;
window.renderProgressSteps = renderProgressSteps;
window.waitForTransactionReceipt = waitForTransactionReceipt;
window.submitX402VerificationWithRetry = submitX402VerificationWithRetry;
window.showSuccessModal = showSuccessModal;
window.closeSuccessModal = closeSuccessModal;
window.closeSmartRoute = closeSmartRoute;