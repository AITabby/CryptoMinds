#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { Web3 } = require(path.join(__dirname, '..', 'web', 'node_modules', 'web3'));

const ROOT = path.resolve(__dirname, '..');
const BUILD_DIR = path.join(ROOT, 'build');
const ABI_PATH = path.join(BUILD_DIR, 'contracts_ServiceEscrow_sol_ServiceEscrow.abi');
const BIN_PATH = path.join(BUILD_DIR, 'contracts_ServiceEscrow_sol_ServiceEscrow.bin');
const WALLETS_PATH = path.join(ROOT, 'wallets.json');
const OUT_PATH = path.join(ROOT, 'escrow_deployment.json');

function getRequiredRpc() {
  const rpc = process.env.BSC_RPC;
  if (!rpc) {
    throw new Error('BSC_RPC is required. Refusing to use a default mainnet RPC for deployment.');
  }
  return rpc;
}

function networkName(chainId) {
  if (chainId === 56) return 'BSC Mainnet';
  if (chainId === 97) return 'BSC Testnet';
  return `Chain ${chainId}`;
}

function validateChainId(chainId) {
  const expected = Number(process.env.BSC_CHAIN_ID || process.env.EXPECTED_CHAIN_ID || 97);
  if (!Number.isFinite(expected) || expected <= 0) {
    throw new Error('BSC_CHAIN_ID/EXPECTED_CHAIN_ID must be a positive number');
  }
  if (chainId !== expected) {
    throw new Error(`RPC chainId mismatch: expected ${expected}, got ${chainId}`);
  }
  if (chainId === 56 && process.env.ALLOW_MAINNET_DEPLOY !== 'true') {
    throw new Error('Refusing mainnet deployment. Set ALLOW_MAINNET_DEPLOY=true to proceed intentionally.');
  }
}

async function main() {
  const rpc = getRequiredRpc();
  const buyerTimeout = Number(process.env.ESCROW_BUYER_TIMEOUT || 86400);    // 24h
  const sellerTimeout = Number(process.env.ESCROW_SELLER_TIMEOUT || 1800);    // 30min
  if (!Number.isFinite(buyerTimeout) || buyerTimeout <= 0) {
    throw new Error('ESCROW_BUYER_TIMEOUT must be a positive number');
  }
  if (!Number.isFinite(sellerTimeout) || sellerTimeout <= 0) {
    throw new Error('ESCROW_SELLER_TIMEOUT must be a positive number');
  }

  const wallets = JSON.parse(fs.readFileSync(WALLETS_PATH, 'utf8'));
  const deployer = wallets.four_meme;
  if (!deployer?.private_key || !deployer?.address) {
    throw new Error('wallets.json is missing four_meme deployer credentials');
  }

  const abi = JSON.parse(fs.readFileSync(ABI_PATH, 'utf8'));
  const bytecode = fs.readFileSync(BIN_PATH, 'utf8').trim();
  const w3 = new Web3(rpc);

  const privateKey = deployer.private_key.startsWith('0x')
    ? deployer.private_key
    : `0x${deployer.private_key}`;

  const account = w3.eth.accounts.privateKeyToAccount(privateKey);
  if (account.address.toLowerCase() !== deployer.address.toLowerCase()) {
    throw new Error('Deployer private key does not match wallets.json address');
  }

  const chainId = Number(await w3.eth.getChainId());
  validateChainId(chainId);
  const nonce = await w3.eth.getTransactionCount(account.address, 'pending');
  const contract = new w3.eth.Contract(abi);
  const deployTx = contract.deploy({
    data: `0x${bytecode}`,
    arguments: [buyerTimeout, sellerTimeout],
  });

  const gas = await deployTx.estimateGas({ from: account.address });
  const gasPrice = await w3.eth.getGasPrice();
  const signed = await account.signTransaction({
    from: account.address,
    data: deployTx.encodeABI(),
    gas: Number(gas) + 300000,
    gasPrice,
    nonce,
    chainId,
    value: '0x0',
  });

  const receipt = await w3.eth.sendSignedTransaction(signed.rawTransaction);

  const output = {
    contractAddress: receipt.contractAddress,
    address: receipt.contractAddress,
    txHash: receipt.transactionHash,
    deployer: account.address,
    network: networkName(chainId),
    chainId,
    deployedAt: new Date().toISOString(),
    buyerTimeoutSeconds: buyerTimeout,
    sellerTimeoutSeconds: sellerTimeout,
    gasUsed: Number(receipt.gasUsed),
    abi,
  };

  fs.writeFileSync(OUT_PATH, `${JSON.stringify(output, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(output, null, 2)}\n`);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
