// Project Hidra — BTC AUDIT page.
// Pull on-chain transactions for an address (persisted + member-linked),
// paginate with "pull next 30", and search saved audits by npub / address.
(() => {
  const ADDR_KEY = 'hidra_audit_addr';
  const addrInput = document.getElementById('addr-input');
  const auditStatus = document.getElementById('audit-status');
  const linkCard = document.getElementById('link-card');
  const txWrap = document.getElementById('tx-wrap');
  const txTable = document.getElementById('tx-table');
  const moreBtn = document.getElementById('more-btn');

  let state = { address: '', lastTxid: null, count: 0 };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function fmtDate(unix) {
    if (!unix) return 'pending';
    return new Date(unix * 1000).toLocaleDateString(undefined,
      { year: 'numeric', month: 'short', day: 'numeric' });
  }
  function shortTxid(t) { return t.slice(0, 10) + '…' + t.slice(-6); }

  // Persist the address as it's typed so it survives reloads.
  addrInput.value = localStorage.getItem(ADDR_KEY) || '';
  addrInput.addEventListener('input', () => localStorage.setItem(ADDR_KEY, addrInput.value.trim()));

  function txRows(txs) {
    return txs.map((t) => {
      const dir = t.direction === 'incoming'
        ? '<span class="status ok" style="display:inline">in</span>'
        : '<span class="status err" style="display:inline">out</span>';
      const npub = t.npub ? esc(t.npub.slice(0, 14)) + '…' : '—';
      return `<tr>
        <td>${esc(fmtDate(t.block_time))}</td>
        <td>${dir}</td>
        <td>${t.amount_btc.toFixed(8)}</td>
        <td><a href="https://blockstream.info/tx/${esc(t.txid)}" target="_blank" rel="noopener">${esc(shortTxid(t.txid))}</a></td>
        <td>${npub}</td>
      </tr>`;
    }).join('');
  }
  function renderTable(target, txs, withNpub) {
    if (!txs.length) { target.innerHTML = '<p class="status">No transactions.</p>'; return; }
    target.innerHTML = `<table class="tbl">
      <tr><th>Date</th><th>Dir</th><th>BTC</th><th>Txid</th><th>${withNpub ? 'npub' : 'Member'}</th></tr>
      ${txRows(txs)}</table>`;
  }
  function appendRows(txs) {
    const tbl = txTable.querySelector('table');
    if (!tbl) { renderTable(txTable, txs, true); return; }
    tbl.insertAdjacentHTML('beforeend', txRows(txs));
  }

  // ---------- AUDIT (first page) ----------
  document.getElementById('audit-btn').addEventListener('click', () => pull(false));
  addrInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') pull(false); });
  moreBtn.addEventListener('click', () => pull(true));

  async function pull(next) {
    const address = addrInput.value.trim();
    if (!address) { auditStatus.textContent = 'Enter a BTC address.'; auditStatus.className = 'status err'; return; }
    localStorage.setItem(ADDR_KEY, address);

    if (!next) { state = { address, lastTxid: null, count: 0 }; txTable.innerHTML = ''; }
    auditStatus.textContent = next ? 'Pulling next 30…' : 'Querying blockchain…';
    auditStatus.className = 'status';
    moreBtn.disabled = true;

    try {
      const body = { address, count: next ? 30 : 20, before_txid: next ? state.lastTxid : null };
      const r = await API.post('/api/audit/pull', body);
      if (!r.success) { auditStatus.textContent = '❌ ' + (r.error || 'Audit failed'); auditStatus.className = 'status err'; moreBtn.disabled = false; return; }

      const txs = r.transactions || [];
      state.lastTxid = r.last_txid;
      state.count += txs.length;

      document.getElementById('o-addr').textContent = address.slice(0, 12) + '…' + address.slice(-8);
      document.getElementById('o-npub').textContent = r.npub || '— (no member linked)';
      document.getElementById('o-count').textContent = state.count;
      linkCard.classList.remove('hidden');
      txWrap.classList.remove('hidden');

      if (next) appendRows(txs); else renderTable(txTable, txs, true);

      // show "pull next" only while pages keep coming back
      moreBtn.classList.toggle('hidden', !(r.has_more && txs.length));
      moreBtn.disabled = false;
      auditStatus.textContent = `Saved ${txs.length} transaction(s). Total shown: ${state.count}.`;
      auditStatus.className = 'status ok';
    } catch (err) {
      auditStatus.textContent = '❌ ' + err.message; auditStatus.className = 'status err'; moreBtn.disabled = false;
    }
  }

  document.getElementById('clear-btn').addEventListener('click', () => {
    addrInput.value = ''; localStorage.removeItem(ADDR_KEY);
    linkCard.classList.add('hidden'); txWrap.classList.add('hidden');
    txTable.innerHTML = ''; auditStatus.textContent = '';
    state = { address: '', lastTxid: null, count: 0 };
  });

  // ---------- SEARCH ----------
  const searchInput = document.getElementById('search-input');
  const searchStatus = document.getElementById('search-status');
  const searchTable = document.getElementById('search-table');
  document.getElementById('search-btn').addEventListener('click', doSearch);
  searchInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') doSearch(); });

  async function doSearch() {
    const q = searchInput.value.trim();
    if (!q) { searchStatus.textContent = 'Enter an npub or BTC address.'; searchStatus.className = 'status err'; return; }
    searchStatus.textContent = 'Searching…'; searchStatus.className = 'status';
    try {
      const r = await API.get('/api/audit/search?q=' + encodeURIComponent(q));
      const rows = r.results || [];
      if (!rows.length) { searchTable.innerHTML = ''; searchStatus.textContent = 'No saved transactions match.'; searchStatus.className = 'status'; return; }
      // reuse the same renderer (rows carry address too)
      searchTable.innerHTML = `<table class="tbl">
        <tr><th>Date</th><th>Dir</th><th>BTC</th><th>Address</th><th>Txid</th><th>npub</th></tr>
        ${rows.map((t) => {
          const dir = t.direction === 'incoming'
            ? '<span class="status ok" style="display:inline">in</span>'
            : '<span class="status err" style="display:inline">out</span>';
          return `<tr>
            <td>${esc(fmtDate(t.block_time))}</td>
            <td>${dir}</td>
            <td>${(t.amount_btc || 0).toFixed(8)}</td>
            <td>${esc(t.btc_address.slice(0, 8))}…${esc(t.btc_address.slice(-6))}</td>
            <td><a href="https://blockstream.info/tx/${esc(t.txid)}" target="_blank" rel="noopener">${esc(shortTxid(t.txid))}</a></td>
            <td>${t.npub ? esc(t.npub.slice(0, 14)) + '…' : '—'}</td>
          </tr>`;
        }).join('')}</table>`;
      searchStatus.textContent = `${rows.length} result(s).`; searchStatus.className = 'status ok';
    } catch (err) { searchStatus.textContent = '❌ ' + err.message; searchStatus.className = 'status err'; }
  }
})();
