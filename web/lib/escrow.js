/**
 * CryptoMinds Escrow 合约集成模块
 * 
 * 管理 ServiceEscrow 合约的读写交互：
 * - 前端通过 MetaMask 调合约（createOrder, confirm, deliver, dispute, claimSellerTimeout）
 * - 后端通过 Web3 调合约（定时检查卖家超时、仲裁）
 */

const { Web3 } = require('web3');
const path = require('path');
const fs = require('fs');

const ROOT = path.resolve(__dirname, '..');
const BSC_RPC = process.env.BSC_RPC || 'https://bsc-dataseed1.binance.org/';
const w3 = new Web3(BSC_RPC);

// 加载 ABI
const ABI_PATH = path.join(ROOT, '..', 'build', 'contracts_ServiceEscrow_sol_ServiceEscrow.abi');
const BIN_PATH = path.join(ROOT, '..', 'build', 'contracts_ServiceEscrow_sol_ServiceEscrow.bin');
const DEPLOY_PATH = path.join(ROOT, '..', 'escrow_deployment.json');

let escrowABI;
try {
  escrowABI = JSON.parse(fs.readFileSync(ABI_PATH, 'utf8'));
} catch (e) {
  console.error('[escrow] 无法加载 ABI:', e.message);
  escrowABI = [];
}

// 获取合约地址
function getEscrowAddress() {
  try {
    if (fs.existsSync(DEPLOY_PATH)) {
      const deploy = JSON.parse(fs.readFileSync(DEPLOY_PATH, 'utf8'));
      return deploy.address;
    }
  } catch (e) {}
  return process.env.ESCROW_CONTRACT_ADDRESS || null;
}

// 获取合约实例（后端只读用）
function getEscrowContract() {
  const addr = getEscrowAddress();
  if (!addr) return null;
  return new w3.eth.Contract(escrowABI, addr);
}

// 将字符串 orderId 转为 bytes32
function orderIdToBytes32(orderId) {
  // 如果已经是 0x 开头的 hex 且长度 66，直接返回
  if (orderId.startsWith('0x') && orderId.length === 66) return orderId;
  // 否则用 keccak256 哈希
  return w3.utils.keccak256(orderId);
}

// ── 合约查询 ──────────────────────────────────────────

async function getOrderFromChain(orderId) {
  const contract = getEscrowContract();
  if (!contract) return null;
  try {
    const b32 = orderIdToBytes32(orderId);
    const order = await contract.methods.getOrder(b32).call();
    const buyer = order.buyer ?? order[0];
    const seller = order.seller ?? order[1];
    const serviceId = order.serviceId ?? order[2];
    const amount = order.amount ?? order[3];
    const createdAt = order.createdAt ?? order[4];
    const deliveredAt = order.deliveredAt ?? order[5];
    const buyerTimeoutAt = order.buyerTimeoutAt ?? order[6];
    const sellerTimeoutAt = order.sellerTimeoutAt ?? order[7];
    const status = order.status ?? order[8];
    const deliverResult = order.deliverResult ?? order[9];

    return {
      buyer,
      seller,
      serviceId,
      amount: amount?.toString(),
      status: status?.toString(),
      createdAt: createdAt?.toString(),
      deliveredAt: deliveredAt?.toString(),
      deliverResult,
      buyerTimeout: buyerTimeoutAt?.toString(),
      sellerTimeout: sellerTimeoutAt?.toString(),
    };
  } catch (e) {
    console.error('[escrow] getOrderFromChain error:', e.message);
    return null;
  }
}

async function getEscrowStats() {
  const contract = getEscrowContract();
  if (!contract) return null;
  try {
    const [totalEscrowed, totalReleased, totalRefunded, totalDisputed, orderCount] = await Promise.all([
      contract.methods.totalEscrowed().call(),
      contract.methods.totalReleased().call(),
      contract.methods.totalRefunded().call(),
      contract.methods.totalDisputed().call(),
      contract.methods.getOrderCount().call(),
    ]);
    return {
      totalEscrowed: w3.utils.fromWei(totalEscrowed, 'ether'),
      totalReleased: w3.utils.fromWei(totalReleased, 'ether'),
      totalRefunded: w3.utils.fromWei(totalRefunded, 'ether'),
      totalDisputed: totalDisputed?.toString(),
      orderCount: orderCount?.toString(),
    };
  } catch (e) {
    console.error('[escrow] getEscrowStats error:', e.message);
    return null;
  }
}

// ── 合约写入（后端私钥调用，用于仲裁和超时处理）──

async function sendTx(method, from, privateKey) {
  const contract = getEscrowContract();
  if (!contract) throw new Error('合约未部署');

  const gas = await method.estimateGas({ from });
  const gasPrice = await w3.eth.getGasPrice();
  const nonce = await w3.eth.getTransactionCount(from, 'pending');
  const tx = {
    from,
    to: contract.options.address,
    data: method.encodeABI(),
    gas: Math.min(Number(gas) * 2, 500000),
    gasPrice,
    nonce,
  };
  const signed = await w3.eth.accounts.signTransaction(tx, privateKey);
  const receipt = await w3.eth.sendSignedTransaction(signed.rawTransaction);
  return receipt;
}

// 后端仲裁：强制放款给卖家
async function arbitrateRelease(orderId, adminAddr, adminKey) {
  const contract = getEscrowContract();
  const b32 = orderIdToBytes32(orderId);
  return await sendTx(contract.methods.arbitrateRelease(b32), adminAddr, adminKey);
}

// 后端仲裁：强制退款给买家
async function arbitrateRefund(orderId, reason, adminAddr, adminKey) {
  const contract = getEscrowContract();
  const b32 = orderIdToBytes32(orderId);
  return await sendTx(contract.methods.arbitrateRefund(b32, reason), adminAddr, adminKey);
}

// ── 卖家超时检查（定时调用）──

async function checkSellerTimeouts(getSellers, saveSellers) {
  const contract = getEscrowContract();
  if (!contract) return;

  const data = getSellers();
  if (!data.orders) return;

  const now = Math.floor(Date.now() / 1000);
  let changed = false;

  for (const order of data.orders) {
    // 只检查链上 pending 且本地的订单
    if (order.status !== 'pending' && order.status !== 'paid') continue;
    if (!order.escrowOrderId) continue; // 非合约订单不处理

    try {
      const chainOrder = await getOrderFromChain(order.escrowOrderId);
      if (!chainOrder) continue;

      // 链上状态 = 0 (Pending) 且超时
      const SELLER_TIMEOUT = 30 * 60; // 30分钟
      if (Number(chainOrder.status) === 0 &&
          Number(chainOrder.createdAt) > 0 &&
          (now - Number(chainOrder.createdAt)) > SELLER_TIMEOUT) {
        
        console.log(`[escrow-timeout] 卖家超时: order=${order.id}, seller=${order.sellerName}`);
        order.status = 'seller_timeout';
        order.timeoutAt = new Date().toISOString();
        order.timeoutReason = '卖家超时未交付，买家可退款';
        changed = true;

        // 同步 purchases
        try {
          const PURCHASES_FILE = path.join(ROOT, 'purchases.json');
          if (fs.existsSync(PURCHASES_FILE)) {
            const purchases = JSON.parse(fs.readFileSync(PURCHASES_FILE, 'utf8'));
            const p = purchases.find(x => x.id === order.id);
            if (p) {
              p.status = 'seller_timeout';
              p.timeoutAt = order.timeoutAt;
              fs.writeFileSync(PURCHASES_FILE, JSON.stringify(purchases, null, 2));
            }
          }
        } catch (e) {}
      }
    } catch (e) {
      // 静默，不阻断其他订单检查
    }
  }

  if (changed) saveSellers(data);
}

// ── 部署合约 ──────────────────────────────────────────

async function deployEscrow(deployerKey) {
  const account = w3.eth.accounts.privateKeyToAccount(deployerKey);
  console.log(`[escrow] 部署账户: ${account.address}`);

  const bin = fs.readFileSync(BIN_PATH, 'utf8').trim();
  const contract = new w3.eth.Contract(escrowABI);

  // defaultTimeout=24h, sellerTimeout=30min
  const deployTx = contract.deploy({
    data: '0x' + bin,
    arguments: [86400, 1800],
  });

  const gas = await deployTx.estimateGas({ from: account.address });
  const gasPrice = await w3.eth.getGasPrice();

  const deployed = await deployTx.send({
    from: account.address,
    gas: Math.min(Number(gas) * 2, 5000000),
    gasPrice,
  });

  const addr = deployed.options.address;
  console.log(`[escrow] 合约已部署: ${addr}`);

  fs.writeFileSync(DEPLOY_PATH, JSON.stringify({
    address: addr,
    deployer: account.address,
    network: 'bsc-mainnet',
    deployedAt: new Date().toISOString(),
    defaultTimeout: 86400,
    sellerTimeout: 1800,
  }, null, 2));

  return addr;
}

module.exports = {
  w3,
  escrowABI,
  getEscrowAddress,
  getEscrowContract,
  orderIdToBytes32,
  getOrderFromChain,
  getEscrowStats,
  arbitrateRelease,
  arbitrateRefund,
  checkSellerTimeouts,
  deployEscrow,
};
