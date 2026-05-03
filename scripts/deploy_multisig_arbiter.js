#!/usr/bin/env node
/**
 * Deploy MultiSigEscrowArbiter (2-of-3 arbitration) to BSC
 *
 * Usage:
 *   BSC_RPC=https://bsc-dataseed1.binance.org/ \
 *   ARBITER_1=0xAddr1 ARBITER_2=0xAddr2 ARBITER_3=0xAddr3 \
 *   ESCROW_CONTRACT_ADDRESS=0x1A81a18dFC26676AC30f95f4659Fe4c0b4355EC3 \
 *   ADMIN_ADDRESS=0xAdminAddr \
 *   node scripts/deploy_multisig_arbiter.js
 */
const fs = require('fs');
const path = require('path');
const { Web3 } = require(path.join(__dirname, '..', 'web', 'node_modules', 'web3'));

const ROOT = path.resolve(__dirname, '..');
const BUILD_DIR = path.join(ROOT, 'build');
const WALLETS_PATH = path.join(ROOT, 'wallets.json');
const OUT_PATH = path.join(ROOT, 'multisig_deployment.json');

async function main() {
  const rpc = process.env.BSC_RPC || 'https://bsc-dataseed1.binance.org/';
  const arbiter1 = process.env.ARBITER_1 || '';
  const arbiter2 = process.env.ARBITER_2 || '';
  const arbiter3 = process.env.ARBITER_3 || '';
  const escrowContract = process.env.ESCROW_CONTRACT_ADDRESS || '';
  const adminAddress = process.env.ADMIN_ADDRESS || '';

  if (!arbiter1 || !arbiter2 || !arbiter3) {
    throw new Error('ARBITER_1, ARBITER_2, ARBITER_3 are all required');
  }
  if (!escrowContract) {
    throw new Error('ESCROW_CONTRACT_ADDRESS is required (the ServiceEscrow/V2 contract to arbitrate)');
  }
  if (!adminAddress) {
    throw new Error('ADMIN_ADDRESS is required (emergency admin, can bypass multi-sig)');
  }

  const wallets = JSON.parse(fs.readFileSync(WALLETS_PATH, 'utf8'));
  const deployer = wallets.four_meme;
  if (!deployer?.private_key || !deployer?.address) {
    throw new Error('wallets.json is missing four_meme deployer credentials');
  }

  const abi = JSON.parse(fs.readFileSync(path.join(BUILD_DIR, 'contracts_MultiSigEscrowArbiter_sol_MultiSigEscrowArbiter.abi'), 'utf8'));
  const bytecode = fs.readFileSync(path.join(BUILD_DIR, 'contracts_MultiSigEscrowArbiter_sol_MultiSigEscrowArbiter.bin'), 'utf8').trim();
  const w3 = new Web3(rpc);

  const privateKey = deployer.private_key.startsWith('0x')
    ? deployer.private_key
    : `0x${deployer.private_key}`;

  const account = w3.eth.accounts.privateKeyToAccount(privateKey);
  if (account.address.toLowerCase() !== deployer.address.toLowerCase()) {
    throw new Error('Deployer private key does not match wallets.json address');
  }

  const chainId = Number(await w3.eth.getChainId());
  const nonce = await w3.eth.getTransactionCount(account.address, 'pending');
  const contract = new w3.eth.Contract(abi);
  const deployTx = contract.deploy({
    data: `0x${bytecode}`,
    arguments: [[arbiter1, arbiter2, arbiter3], escrowContract, adminAddress],
  });

  const gas = await deployTx.estimateGas({ from: account.address });
  const gasPrice = await w3.eth.getGasPrice();
  const signed = await account.signTransaction({
    from: account.address,
    data: deployTx.encodeABI(),
    gas: Number(gas) + 200000,
    gasPrice,
    nonce,
    chainId,
    value: '0x0',
  });

  const receipt = await w3.eth.sendSignedTransaction(signed.rawTransaction);

  const output = {
    contractAddress: receipt.contractAddress,
    txHash: receipt.transactionHash,
    deployer: account.address,
    network: chainId === 56 ? 'BSC Mainnet' : `Chain ${chainId}`,
    chainId,
    deployedAt: new Date().toISOString(),
    version: 'MultiSig-2of3',
    arbiters: [arbiter1, arbiter2, arbiter3],
    escrowContract,
    adminAddress,
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
