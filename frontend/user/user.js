// Project Hidra — USER page logic: enroll → identity reveal → messenger.
(() => {
  const views = {
    enroll: document.getElementById('enroll-view'),
    identity: document.getElementById('identity-view'),
    messenger: document.getElementById('messenger-view'),
    login: document.getElementById('login-view'),
  };
  const show = (name) => {
    Object.entries(views).forEach(([k, el]) => el.classList.toggle('hidden', k !== name));
  };

  const qrBtn = document.getElementById('qr-btn');
  let ws = null;
  let currentNpub = '';
  let provider = null;   // {name, btc_address, ...} fetched if enrolled via a link

  // ---- provider id + hospital npub from the shareable link ----
  const params = new URLSearchParams(location.search);
  const providerId = params.get('provider');
  let hubNpub = (params.get('hub') || '').trim();   // hospital mailbox the intake goes to

  // Resolve which hospital mailbox to send the intake to. If the link carried
  // the npub, use it; else look it up from the provider id; else ask the member.
  async function resolveHub() {
    if (!hubNpub && providerId) {
      try {
        provider = await API.get('/api/provider/' + Number(providerId));
        hubNpub = (provider && provider.npub) ? provider.npub.trim() : '';
      } catch (_) { provider = null; }
    }
    const field = document.getElementById('hub-field');
    const note = document.getElementById('hub-note');
    if (hubNpub) {
      field.classList.add('hidden');
      note.textContent = '✉ Your info will be sent to: ' + hubNpub.slice(0, 16) + '…';
      note.className = 'status ok';
    } else {
      field.classList.remove('hidden');   // member must supply the hospital npub
      note.classList.add('hidden');
    }
  }

  // ---- copy buttons (delegated) ----
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-copy]');
    if (!btn) return;
    const el = document.querySelector(btn.getAttribute('data-copy'));
    if (el) copyText(el.textContent, btn);
  });

  // ---- QR toggle ----
  function setQR(npub) {
    document.getElementById('qr-img').src = `/api/qr?data=${encodeURIComponent(npub)}`;
    qrBtn.classList.remove('hidden');
  }
  qrBtn.addEventListener('click', () => {
    document.getElementById('qr-card').classList.toggle('hidden');
  });

  // ---- enrollment ----
  document.getElementById('enroll-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target;
    const status = document.getElementById('enroll-status');
    const agree = f.querySelector('input[name=agree]:checked').value === 'yes';
    if (!agree) { status.textContent = 'Please consent to continue.'; status.className = 'status err'; return; }

    // Hospital mailbox: resolved from the link, or typed in when not provided.
    const hub = hubNpub || (f.hub_npub ? f.hub_npub.value.trim() : '');
    if (!hub) { status.textContent = 'Enter the hospital npub to send your info to.'; status.className = 'status err'; return; }

    const btn = document.getElementById('submit-btn');
    btn.disabled = true; status.textContent = 'Enrolling and publishing to relays…'; status.className = 'status';

    const dob = f.dob.value.trim();
    const body = {
      first_name: f.first_name.value.trim(),
      last_name: f.last_name.value.trim(),
      phone: f.phone.value.trim(),
      dob: dob,
      year_of_birth: dob ? dob.split('/').pop() : null,
      birth_place: f.birth_place.value.trim(),
      btc_address: f.btc_address.value.trim(),
      provider_id: providerId ? Number(providerId) : null,
      hub_npub: hub,
      agree: true,
      send_message: true,
    };

    try {
      const res = await API.post('/api/enroll', body);
      const nsec = res.identity.nsec;
      Store.set(nsec);
      currentNpub = res.identity.npub;
      document.getElementById('nsec-out').textContent = nsec;
      document.getElementById('npub-out').textContent = currentNpub;
      setQR(currentNpub);
      if (providerId) {
        try { provider = await API.get('/api/provider/' + Number(providerId)); } catch (_) { provider = null; }
      }
      show('identity');
    } catch (err) {
      status.textContent = 'Error: ' + err.message; status.className = 'status err';
    } finally {
      btn.disabled = false;
    }
  });

  // ---- contract + payment ----
  document.getElementById('contract-btn').addEventListener('click', async (e) => {
    const btn = e.target; btn.disabled = true;
    const old = btn.textContent; btn.textContent = 'Generating…';
    try {
      await API.download('/api/contract', {
        hospital_name: provider ? provider.name : 'Your Hospital',
        individual_name: document.querySelector('#enroll-form [name=first_name]').value + ' ' +
                         document.querySelector('#enroll-form [name=last_name]').value,
        npub: currentNpub,
        btc_address: provider ? provider.btc_address : null,
        services: provider && provider.services ? JSON.parse(provider.services) : null,
      }, 'hidra_contract.pdf');
    } catch (err) { alert('Contract failed: ' + err.message); }
    finally { btn.disabled = false; btn.textContent = old; }
  });

  document.getElementById('payment-btn').addEventListener('click', async (e) => {
    const btn = e.target;
    const payAddr = provider ? provider.btc_address : null;
    if (!payAddr) { alert('No hospital BTC address — enroll via a hospital link to set up payment.'); return; }
    btn.disabled = true; const old = btn.textContent; btn.textContent = 'Pricing…';
    try {
      const r = await API.post('/api/payments/request', {
        btc_address: payAddr, monthly_usd: 20, label: provider ? provider.name : null,
      });
      document.getElementById('pay-addr').textContent = r.btc_address;
      document.getElementById('pay-amt').textContent = `${r.amount_btc} BTC  ($${r.monthly_usd} @ $${Math.round(r.btc_usd_price)}/BTC)`;
      document.getElementById('pay-due').textContent = r.due_date;
      document.getElementById('pay-uri').textContent = r.bip21_uri;
      document.getElementById('pay-qr').src = `/api/qr?data=${encodeURIComponent(r.bip21_uri)}`;
      document.getElementById('pay-note').textContent = r.note;
      document.getElementById('payment-box').classList.remove('hidden');
    } catch (err) { alert('Payment setup failed: ' + err.message); }
    finally { btn.disabled = false; btn.textContent = old; }
  });

  document.getElementById('goto-messenger').addEventListener('click', () => startMessenger(Store.get()));

  // ---- messenger ----
  function renderConversations(convos) {
    const box = document.getElementById('mailbox');
    box.innerHTML = '';
    const peers = Object.keys(convos);
    if (peers.length === 0) {
      box.innerHTML = '<p class="status">No messages yet.</p>';
      return;
    }
    for (const peer of peers) {
      const head = document.createElement('div');
      head.className = 'convo-head';
      head.textContent = `Hub ${peer.slice(0, 12)}…${peer.slice(-6)}`;
      box.appendChild(head);
      for (const m of convos[peer]) {
        const div = document.createElement('div');
        div.className = 'msg ' + (m.is_sent ? 'out' : 'in');
        div.innerHTML = `<span class="t">${m.formatted_time}</span>${escapeHtml(m.content)}`;
        box.appendChild(div);
      }
    }
    box.scrollTop = box.scrollHeight;
  }

  function setMbStatus(text, cls) {
    const s = document.getElementById('mb-status');
    s.textContent = text; s.className = 'status ' + (cls || '');
  }

  function startMessenger(nsec) {
    if (!nsec) { show('enroll'); return; }
    if (currentNpub) setQR(currentNpub);
    show('messenger');
    setMbStatus('Connecting to relays…');
    if (ws) { try { ws.close(); } catch (_) {} }
    ws = API.openMailbox(nsec, 30,
      (convos) => { renderConversations(convos); setMbStatus('Last refreshed ' + new Date().toLocaleTimeString(), 'ok'); },
      (err) => setMbStatus('Error: ' + err, 'err'));
  }

  document.getElementById('send-btn').addEventListener('click', sendMessage);
  document.getElementById('mail-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') sendMessage(); });

  async function sendMessage() {
    const input = document.getElementById('mail-input');
    const text = input.value.trim();
    if (!text) return;
    setMbStatus('Sending…');
    input.value = '';
    try {
      await API.post('/api/messages/send', { nsec: Store.get(), message: text });
      setMbStatus('Sent. Refreshing…', 'ok');
      refreshOnce();
    } catch (err) { setMbStatus('Send failed: ' + err.message, 'err'); }
  }

  async function refreshOnce() {
    try {
      const res = await API.post('/api/messages/conversations', { nsec: Store.get() });
      renderConversations(res.conversations || {});
      setMbStatus('Last refreshed ' + new Date().toLocaleTimeString(), 'ok');
    } catch (err) { setMbStatus('Refresh failed: ' + err.message, 'err'); }
  }
  document.getElementById('refresh-btn').addEventListener('click', refreshOnce);

  document.getElementById('logout-btn').addEventListener('click', () => {
    Store.clear();
    if (ws) { try { ws.close(); } catch (_) {} }
    show('enroll');
  });

  // ---- returning-user landing ----
  document.getElementById('open-messenger').addEventListener('click', () => startMessenger(Store.get()));
  document.getElementById('new-enroll').addEventListener('click', () => show('enroll'));

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  // ---- initial view ----
  resolveHub();
  if (Store.get()) show('login'); else show('enroll');
})();
