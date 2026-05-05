#!/usr/bin/env node
/**
 * Deploy ServiceEscrowV2 (BNB + ERC-20 dual mode) to BSC
 *
 * Usage:
 *   BSC_RPC=https://data-seed-prebsc-1-s1.binance.org:8545/ \
 *   BSC_CHAIN_ID=97 \
 *   ESCROW_BUYER_TIMEOUT=86400 \
 *   ESCROW_SELLER_TIMEOUT=1800 \
 *   TOKEN_ADDRESS=0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d \
 *   TOKEN_DECIMALS=18 \
 *   node scripts/deploy_service_escrow_v2.js
 *
 * Set TOKEN_ADDRESS=0x0000000000000000000000000000000000000000 for BNB-only mode.
 */
const fs = require('fs');
const path = require('path');
const { Web3 } = require(path.join(__dirname, '..', 'web', 'node_modules', 'web3'));

const ROOT = path.resolve(__dirname, '..');
const BUILD_DIR = path.join(ROOT, 'build');
const WALLETS_PATH = path.join(ROOT, 'wallets.json');
const OUT_PATH = path.join(ROOT, 'escrow_deployment_v2.json');

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
  const buyerTimeout = Number(process.env.ESCROW_BUYER_TIMEOUT || 86400);
  const sellerTimeout = Number(process.env.ESCROW_SELLER_TIMEOUT || 1800);
  const tokenAddress = process.env.TOKEN_ADDRESS || '0x0000000000000000000000000000000000000000';
  const tokenDecimals = Number(process.env.TOKEN_DECIMALS || '18');

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

  const abi = JSON.parse(fs.readFileSync(path.join(BUILD_DIR, 'contracts_ServiceEscrowV2_sol_ServiceEscrowV2.abi'), 'utf8'));
  const bytecode = fs.readFileSync(path.join(BUILD_DIR, 'contracts_ServiceEscrowV2_sol_ServiceEscrowV2.bin'), 'utf8').trim();
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
    arguments: [buyerTimeout, sellerTimeout, tokenAddress, tokenDecimals],
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
    version: 'V2',
    tokenAddress,
    tokenDecimals,
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
