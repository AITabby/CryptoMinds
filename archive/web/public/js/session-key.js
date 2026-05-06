// CryptoMinds Session Key Module
// Session key creation, revocation, quota increase, listing

async function loadSessionKeys() {
  const listEl = document.getElementById('sessionKeyList');
  const wallet = App.currentAccount || getActiveWallet();
  if (!wallet) {
    listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;">请先连接钱包</div>';
    return;
  }
  listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;">加载中...</div>';
  try {
    const res = await fetch('/api/v1/protocol/session-keys/agent/' + encodeURIComponent(wallet));
    const data = await res.json();
    const keys = data.keys || [];
    if (keys.length === 0) {
      listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;">当前钱包无 Session Key</div>';
      return;
    }
    listEl.innerHTML = keys.map(k => {
      const expired = k.expires_at && Date.now() / 1000 > k.expires_at;
      const statusColor = k.revoked ? '#f87171' : expired ? '#64748b' : '#34d399';
      const statusLabel = k.revoked ? '已撤销' : expired ? '已过期' : '有效';
      const expiresAt = k.expires_at ? new Date(k.expires_at * 1000).toLocaleString('zh-CN') : '--';
      const usedPercent = k.total_quota ? (parseFloat(k.total_used) / parseFloat(k.total_quota) * 100).toFixed(1) : 0;
      return '<div style="background:#0f121e;border:1px solid rgba(139,92,246,0.15);border-radius:10px;padding:16px;margin-bottom:12px;"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;"><div style="color:#a78bfa;font-weight:600;font-size:13px;font-family:monospace;">' + (k.session_key_id) + '</div><div style="background:rgba(' + (k.revoked ? '239,68,68' : expired ? '100,116,139' : '34,211,153') + ',0.15);color:' + statusColor + ';font-size:11px;padding:3px 8px;border-radius:4px;font-weight:600;">' + statusLabel + '</div></div><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px;color:#94a3b8;"><div>Agent: <span style="color:#e2e8f0;">' + (k.agent_id) + '</span></div><div>地址: <span style="color:#e2e8f0;font-family:monospace;">' + ((k.session_address || '').slice(0,10)) + '...</span></div><div>链: <span style="color:#e2e8f0;">' + ((k.available_chains || []).join(', ')) + '</span></div><div>动作: <span style="color:#e2e8f0;">' + ((k.callable_actions || []).join(', ')) + '</span></div><div>单笔上限: <span style="color:#fbbf24;">' + (k.per_tx_limit) + ' BNB</span></div><div>额度: <span style="color:#fbbf24;">' + (k.total_used) + '/' + (k.total_quota) + ' BNB (' + usedPercent + '%)</span></div><div>有效期至: ' + expiresAt + '</div><div>Nonce: ' + (k.nonce || 0) + '</div></div>' + (!k.revoked && !expired ? '<div style="display:flex;gap:8px;margin-top:12px;"><button onclick="revokeSessionKeyUI(\'' + (k.session_key_id) + '\')" style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);color:#f87171;padding:6px 12px;border-radius:6px;cursor:pointer;font-size:11px;">撤销</button><button onclick="increaseQuotaUI(\'' + (k.session_key_id) + '\')" style="background:rgba(34,211,153,0.1);border:1px solid rgba(34,211,153,0.3);color:#34d399;padding:6px 12px;border-radius:6px;cursor:pointer;font-size:11px;">提额</button></div>' : '') + '</div>';
    }).join('');
  } catch (e) {
    listEl.innerHTML = '<div style="text-align:center;padding:20px;color:#f87171;">加载失败: ' + e.message + '</div>';
  }
}

function buildSessionKeyAuthMessage(agentId, chains, perTxLimit, totalQuota, actions, expiresAt, sessionAddress) {
  return [
    'CryptoMinds session key authorization',
    'Agent: ' + agentId,
    'Chains: ' + chains.join(','),
    'PerTxLimit: ' + perTxLimit,
    'TotalQuota: ' + totalQuota,
    'Actions: ' + actions.join(','),
    'Nonce: 0',
    'Expires: ' + expiresAt,
    'SessionAddress: ' + sessionAddress
  ].join('\n');
}

async function createSessionKey() {
  const wallet = App.currentAccount || getActiveWallet();
  if (!wallet) { alert('请先连接钱包'); return; }
  const agentId = document.getElementById('skAgentId').value.trim();
  const sessionAddress = document.getElementById('skSessionAddress').value.trim();
  const chains = normalizeCsvInput(document.getElementById('skChains').value.trim());
  const perTxLimit = document.getElementById('skPerTxLimit').value.trim();
  const totalQuota = document.getElementById('skTotalQuota').value.trim();
  const actions = normalizeCsvInput(document.getElementById('skActions').value.trim());
  const validityHours = parseInt(document.getElementById('skValidityHours').value || '24');
  if (!agentId || !sessionAddress || !perTxLimit || !totalQuota) {
    alert('请填写 Agent ID、Session Address、单笔上限、总额度');
    return;
  }
  try {
    const expiresAt = Math.floor(Date.now() / 1000) + validityHours * 3600;
    const message = buildSessionKeyAuthMessage(agentId, chains, perTxLimit, totalQuota, actions, expiresAt, sessionAddress);
    const signature = await signWalletMessage(wallet, message);
    const res = await fetch('/api/v1/protocol/session-keys/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        main_wallet: wallet, agent_id: agentId, session_address: sessionAddress,
        chains, per_tx_limit: perTxLimit, total_quota: totalQuota,
        actions, validity_seconds: validityHours * 3600, expires_at: expiresAt,
        message, signature, authorization_signature: signature,
      })
    });
    const data = await res.json();
    if (data.ok || data.session_key_id) {
      alert('Session Key 创建成功!\nID: ' + (data.session_key_id || '--'));
      loadSessionKeys();
    } else {
      alert('创建失败: ' + (data.error || '未知错误'));
    }
  } catch (e) {
    alert('创建请求失败: ' + e.message);
  }
}

async function revokeSessionKeyUI(keyId) {
  const wallet = App.currentAccount || getActiveWallet();
  if (!wallet) return;
  if (!confirm('确认撤销 Session Key ' + keyId + '?')) return;
  try {
    const message = 'CryptoMinds revoke session key\nKey: ' + keyId + '\nWallet: ' + wallet;
    const signature = await signWalletMessage(wallet, message);
    const res = await fetch('/api/v1/protocol/session-keys/' + keyId + '/revoke', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ main_wallet: wallet, message, signature })
    });
    const data = await res.json();
    if (data.ok) { alert('已撤销'); loadSessionKeys(); }
    else { alert('撤销失败: ' + (data.error || '未知错误')); }
  } catch (e) {
    alert('撤销请求失败: ' + e.message);
  }
}

async function increaseQuotaUI(keyId) {
  const additional = prompt('输入增加额度 (BNB):');
  if (!additional) return;
  const wallet = App.currentAccount || getActiveWallet();
  if (!wallet) return;
  try {
    const message = ['CryptoMinds increase session key quota', 'Key: ' + keyId, 'Additional: ' + additional, 'Wallet: ' + wallet].join('\n');
    const signature = await signWalletMessage(wallet, message);
    const res = await fetch('/api/v1/protocol/session-keys/' + keyId + '/increase-quota', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ additional_quota: additional, main_wallet: wallet, message, signature })
    });
    const data = await res.json();
    if (data.ok) { alert('提额成功! 新额度: ' + (data.total_quota || '--')); loadSessionKeys(); }
    else { alert('提额失败: ' + (data.error || '未知错误')); }
  } catch (e) {
    alert('提额请求失败: ' + e.message);
  }
}

window.loadSessionKeys = loadSessionKeys;
window.buildSessionKeyAuthMessage = buildSessionKeyAuthMessage;
window.createSessionKey = createSessionKey;
window.revokeSessionKeyUI = revokeSessionKeyUI;
window.increaseQuotaUI = increaseQuotaUI;
