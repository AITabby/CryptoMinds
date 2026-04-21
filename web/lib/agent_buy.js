const path = require('path');

function createAgentBuyHandlers({
  fetchImpl,
  minimaxApiKey,
  minimaxBaseUrl,
  pythonBin,
  execFileSync,
  getSellers,
  saveSellers,
  addPurchase,
  addTx,
}) {
  const projectRoot = path.join(__dirname, '..', '..');
  const transferBnbScript = path.join(projectRoot, 'transfer_bnb.py');
  const tokenBuyerScript = path.join(projectRoot, 'token_buyer.py');

  const sellerWalletMap = {
    '0xd2f899ce74320aef9d8f2359183232a554f4c0e1': 'gangdan',
    '0xce0de97496c20dd773d75f560d3e4494cf542d96': 'tiedan',
    '0x40992619077f0e42a1b7713c02b7324fa1d8715c': 'choudan',
    '0x0badb40bed90515cb436282c1d5be059d17566bc': 'pidan',
    '0x4190877f1959e260b4613793e3d07e8a332bc44b': 'ludan',
  };

  function clampChoice(index, items) {
    return items[Math.max(0, Math.min(index, items.length - 1))];
  }

  async function chooseWithMiniMax(prompt) {
    const mmRes = await fetchImpl(`${minimaxBaseUrl}/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${minimaxApiKey}` },
      body: JSON.stringify({
        model: 'MiniMax-Text-01',
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.3,
        max_tokens: 10
      }),
    });
    const mmData = await mmRes.json();
    const text = mmData.choices?.[0]?.message?.content?.trim() || '1';
    return Number.parseInt(text.replace(/[^0-9]/g, ''), 10) - 1;
  }

  async function buyerAgentPickSeller(sellers, buyerWallet, amount, buyerEndpoint) {
    const availableSellers = sellers.filter((s) => s.wallet.toLowerCase() !== buyerWallet.toLowerCase());
    if (!availableSellers.length) {
      throw new Error('没有可用的卖家');
    }
    const sellerList = availableSellers
      .map((s, i) => `${i + 1}. ${s.name} | 策略:${s.strategy} | 评分:${s.rating} | 费率:${s.feeRate} | 模式:${s.agentMode || '平台托管'} | 描述:${s.desc}`)
      .join('\n');

    if (buyerEndpoint) {
      try {
        const resp = await fetchImpl(buyerEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'pickSeller', sellers: sellerList, buyerWallet, amount }),
          signal: AbortSignal.timeout(10000),
        });
        const data = await resp.json();
        const idx = (data.index || data.choice || 1) - 1;
        const chosen = clampChoice(idx, availableSellers);
        console.log('[agent-buy] 买家Agent(endpoint)选中:', chosen?.name);
        return chosen;
      } catch (e) {
        console.log('[agent-buy] 买家Agent endpoint失败，降级平台托管:', e.message);
      }
    }

    const prompt = `你是买家的 Agent，帮买家从以下卖家中选一个最合适的来执行买币任务。\n\n买家钱包: ${buyerWallet}\n买入金额: ${amount} BNB\n\n可选卖家：\n${sellerList}\n\n请只返回你选的卖家编号（数字），不要其他内容。`;
    const idx = await chooseWithMiniMax(prompt);
    const chosen = clampChoice(idx, availableSellers);
    console.log('[agent-buy] 买家Agent(平台托管)选中:', chosen?.name);
    return chosen;
  }

  async function sellerAgentPickToken(seller) {
    const tokens = ['0x3518D7aEE5248b9307b8A82B7c3Fa49e073c4444'];
    const tokenList = tokens.map((t, i) => `${i + 1}. AIBT (${t}) - four.meme已毕业, PancakeSwap V2可买`).join('\n');

    if (seller.endpoint) {
      try {
        const resp = await fetchImpl(seller.endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'pickToken', sellerName: seller.name, strategy: seller.strategy, tokens: tokenList }),
          signal: AbortSignal.timeout(10000),
        });
        const data = await resp.json();
        const idx = (data.index || data.choice || 1) - 1;
        const chosen = clampChoice(idx, tokens);
        console.log('[agent-buy] 卖家Agent(endpoint)选中代币:', chosen);
        return chosen;
      } catch (e) {
        console.log('[agent-buy] 卖家Agent endpoint失败，降级平台托管:', e.message);
      }
    }

    const prompt = `你是卖家「${seller.name}」，策略是「${seller.strategy}」。你要在 BSC 链上帮买家买一个代币。\n\n当前可买：\n${tokenList}\n\n根据策略选一个，只返回编号。`;
    const idx = await chooseWithMiniMax(prompt);
    return clampChoice(idx, tokens);
  }

  async function pickSellerHandler(req, res) {
    try {
      const { buyerWallet, amount } = req.body;
      const sellers = getSellers().sellers;
      if (!sellers.length) {
        return res.json({ ok: false, error: '暂无可用卖家' });
      }
      const seller = sellers[0];
      return res.json({ ok: true, seller, buyerWallet, amount });
    } catch (e) {
      return res.json({ ok: false, error: e.message });
    }
  }

  async function agentBuyHandler(req, res) {
    try {
      const { buyerWallet, amount = 0.001 } = req.body;
      if (!buyerWallet) {
        return res.json({ ok: false, error: '请先连接钱包' });
      }
      const sellers = getSellers().sellers;
      if (!sellers.length) {
        return res.json({ ok: false, error: '暂无可用卖家' });
      }

      const buyerInfo = sellers.find((s) => s.wallet.toLowerCase() === buyerWallet.toLowerCase());
      const buyerEndpoint = buyerInfo?.endpoint || '';
      const seller = await buyerAgentPickSeller(sellers, buyerWallet, amount, buyerEndpoint);
      const sellerWalletName = sellerWalletMap[seller.wallet.toLowerCase()] || 'gangdan';
      console.log('[agent-buy] 买家Agent选中卖家:', seller.name, '策略:', seller.strategy);

      const buyerWalletName = sellerWalletMap[buyerWallet.toLowerCase()];
      if (!buyerWalletName) {
        return res.json({ ok: false, error: '买家钱包未托管' });
      }

      console.log('[agent-buy] 买家', buyerWalletName, '转', amount, 'BNB给卖家', sellerWalletName);
      let transferTxHash = '';
      try {
        const transferOut = execFileSync(pythonBin, [transferBnbScript, buyerWalletName, seller.wallet, String(amount)], {
          cwd: projectRoot,
          timeout: 30000,
          encoding: 'utf-8'
        });
        const transferResult = JSON.parse(transferOut.trim().split('\n').pop());
        if (transferResult.ok) {
          transferTxHash = transferResult.txHash;
          addTx({
            time: new Date().toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai' }),
            from: buyerWalletName,
            to: seller.name,
            amount,
            reason: '买币',
            tx: transferTxHash
          });
        }
      } catch (e) {
        console.log('[agent-buy] BNB转账失败:', e.message);
        return res.json({ ok: false, error: `BNB转账失败: ${e.message}` });
      }

      const tokenAddr = await sellerAgentPickToken(seller);
      console.log('[agent-buy] 卖家Agent选中代币:', tokenAddr);

      const output = execFileSync(pythonBin, [tokenBuyerScript, sellerWalletName, buyerWallet, tokenAddr, String(amount)], {
        cwd: projectRoot,
        timeout: 120000,
        encoding: 'utf-8'
      });
      const lines = output.trim().split('\n');
      const lastLine = lines[lines.length - 1];
      try {
        const result = JSON.parse(lastLine);
        result.sellerName = seller.name;
        result.sellerStrategy = seller.strategy;
        const orderId = `buy-${Date.now()}`;
        const orderData = {
          id: orderId,
          buyerWallet,
          expertWallet: seller.wallet,
          expert: seller.name,
          serviceName: result.symbol || 'Token',
          price: amount,
          priceCurrency: 'BNB',
          status: 'completed',
          time: new Date().toISOString(),
          completedAt: new Date().toISOString(),
          txHash: result.swapHash,
          transferHash: result.transferHash,
          tokenAmount: result.amount,
          token: result.token,
          sellerWallet: seller.wallet
        };
        try {
          addPurchase(orderData);
        } catch (e) {
          console.log('[agent-buy] 写入 purchases 失败:', e.message);
        }
        try {
          const data = getSellers();
          data.orders = data.orders || [];
          data.orders.unshift(orderData);
          if (data.orders.length > 100) data.orders = data.orders.slice(0, 100);
          saveSellers(data);
          console.log('[agent-buy] 写入 sellers.json orders 成功:', orderId);
        } catch (e) {
          console.log('[agent-buy] 写入 sellers orders 失败:', e.message);
        }
        console.log('[agent-buy] 交易完成');
        return res.json(result);
      } catch {
        return res.json({ ok: true, raw: output.slice(-300), sellerName: seller.name });
      }
    } catch (e) {
      return res.json({ ok: false, error: e.message.slice(0, 200) });
    }
  }

  return {
    pickSellerHandler,
    agentBuyHandler,
  };
}

module.exports = { createAgentBuyHandlers };
