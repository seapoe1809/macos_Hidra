// Project Hidra — BILLS page.
// Add a bill (npub + amount + date + optional PDF/photo), search by npub,
// and mark a bill paid (stamps the click time). New schema: bills.
(() => {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (unix) => unix ? new Date(unix * 1000).toLocaleDateString(undefined,
    { year: 'numeric', month: 'short', day: 'numeric' }) : '—';

  const addStatus = document.getElementById('add-status');
  const listStatus = document.getElementById('list-status');
  const list = document.getElementById('bills-list');

  // default the date field to today
  const dateInput = document.getElementById('b-date');
  dateInput.value = new Date().toISOString().slice(0, 10);

  // ---------- ADD BILL (multipart) ----------
  document.getElementById('bill-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const npub = document.getElementById('b-npub').value.trim();
    const amount = document.getElementById('b-amount').value.trim();
    const date = dateInput.value;
    const fileEl = document.getElementById('b-file');
    if (!npub || !amount || !date) { addStatus.textContent = 'npub, amount and date are required.'; addStatus.className = 'status err'; return; }

    const fd = new FormData();
    fd.append('member_npub', npub);
    fd.append('amount_usd', amount);
    fd.append('bill_date', date);
    if (fileEl.files[0]) fd.append('file', fileEl.files[0]);

    const btn = document.getElementById('b-submit');
    btn.disabled = true; addStatus.textContent = 'Saving…'; addStatus.className = 'status';
    try {
      const res = await fetch('/api/bills/add', { method: 'POST', body: fd });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error((data && (data.detail || data.error)) || res.statusText);
      addStatus.textContent = `✅ Bill #${data.id} added for ${npub.slice(0, 14)}…`;
      addStatus.className = 'status ok';
      document.getElementById('b-amount').value = '';
      fileEl.value = '';
      document.getElementById('search-npub').value = npub;
      loadBills(npub);
    } catch (err) { addStatus.textContent = '❌ ' + err.message; addStatus.className = 'status err'; }
    finally { btn.disabled = false; }
  });

  // ---------- LIST / SEARCH ----------
  document.getElementById('search-btn').addEventListener('click', () => loadBills(document.getElementById('search-npub').value.trim()));
  document.getElementById('all-btn').addEventListener('click', () => { document.getElementById('search-npub').value = ''; loadBills(''); });
  document.getElementById('search-npub').addEventListener('keydown', (e) => { if (e.key === 'Enter') loadBills(e.target.value.trim()); });

  function billCard(b) {
    const amt = (b.amount_usd != null ? b.amount_usd : b.total_usd || 0);
    const att = b.attachment_name
      ? `<a href="/api/bills/${b.id}/attachment" target="_blank" rel="noopener">📎 ${esc(b.attachment_name)}</a>`
      : '<span class="sub">no attachment</span>';
    const paidBtn = b.paid
      ? `<span class="status ok" style="display:inline">✓ Paid ${esc(fmt(b.paid_at))}</span>`
      : `<button class="mark-paid" data-id="${b.id}">Mark Paid</button>`;
    return `<div class="box" data-bill="${b.id}" style="margin-bottom:.6rem">
      <div class="convo-head">
        <div>
          <p class="kv" style="margin:0"><b>#${b.id}</b> · ${esc(b.bill_date || fmt(b.created_at))}</p>
          <p class="kv" style="margin:.15rem 0"><b>npub</b> ${esc((b.member_npub || '').slice(0, 22))}…</p>
          <p class="kv" style="margin:.15rem 0"><b>Amount</b> $${Number(amt).toFixed(2)}</p>
          <p class="kv" style="margin:.15rem 0">${att}</p>
        </div>
        <div style="text-align:right">${paidBtn}</div>
      </div>
    </div>`;
  }

  async function loadBills(npub) {
    listStatus.textContent = 'Loading…'; listStatus.className = 'status';
    try {
      const url = '/api/bills/search' + (npub ? '?npub=' + encodeURIComponent(npub) : '');
      const r = await API.get(url);
      const bills = r.bills || [];
      if (!bills.length) { list.innerHTML = ''; listStatus.textContent = npub ? 'No bills for that npub.' : 'No bills yet.'; listStatus.className = 'status'; return; }
      list.innerHTML = bills.map(billCard).join('');
      listStatus.textContent = `${bills.length} bill(s).`; listStatus.className = 'status ok';
    } catch (err) { listStatus.textContent = '❌ ' + err.message; listStatus.className = 'status err'; }
  }

  // ---------- MARK PAID (delegated) ----------
  list.addEventListener('click', async (e) => {
    const btn = e.target.closest('.mark-paid');
    if (!btn) return;
    btn.disabled = true; btn.textContent = 'Saving…';
    try {
      const b = await API.post(`/api/bills/${btn.getAttribute('data-id')}/paid`);
      const card = list.querySelector(`[data-bill="${b.id}"] div[style*="text-align:right"]`);
      if (card) card.innerHTML = `<span class="status ok" style="display:inline">✓ Paid ${esc(fmt(b.paid_at))}</span>`;
    } catch (err) { btn.disabled = false; btn.textContent = 'Mark Paid'; alert('Failed: ' + err.message); }
  });

  loadBills('');
})();
