// Project Hidra — PROVIDER page: login → register → 2x2 dashboard.
(() => {
  const views = {
    login: document.getElementById('login-view'),
    register: document.getElementById('register-view'),
    dashboard: document.getElementById('dashboard-view'),
  };
  const show = (name) => {
    Object.entries(views).forEach(([k, el]) => el.classList.toggle('hidden', k !== name));
    document.getElementById('logout-btn').classList.toggle('hidden', name !== 'dashboard');
  };
  const HUB_KEY = 'hidra_hub_nsec';
  const TOKEN_KEY = 'hidra_provider_token';  // sessionStorage — active until the browser/tab closes
  const BTC_KEY = 'hidra_provider_btc';      // hospital btc address — carries to dashboard
  const PID_KEY = 'hidra_provider_id';
  let ws = null;
  let enrollLink = '';   // current dashboard enrollment link (built from provider id)

  // Build the shareable member enrollment link from the dashboard's provider id.
  // Looks up the provider's npub so the link routes intake to this hospital.
  async function refreshEnrollLink() {
    const box = document.getElementById('dash-enroll-link');
    const pid = (document.getElementById('ctx-provider').value || '').trim();
    if (!pid) { enrollLink = ''; box.textContent = 'Enter Provider ID above to load the link'; return; }
    try {
      const p = await API.get('/api/provider/' + Number(pid));
      enrollLink = location.origin + '/user/?provider=' + Number(pid) +
        (p.npub ? '&hub=' + encodeURIComponent(p.npub) : '');
      box.textContent = enrollLink;
    } catch (_) { enrollLink = ''; box.textContent = 'Provider not found for that ID'; }
  }

  // Reveal the dashboard and restore saved context (hub token, btc, provider id).
  function enterDashboard() {
    show('dashboard');
    const btc = document.getElementById('ctx-btc');
    const pid = document.getElementById('ctx-provider');
    if (btc && !btc.value) btc.value = localStorage.getItem(BTC_KEY) || '';
    if (pid && !pid.value) pid.value = localStorage.getItem(PID_KEY) || '';
    const saved = localStorage.getItem(HUB_KEY);
    if (saved) { document.getElementById('hub-nsec').value = saved; connectHub(); }
    refreshEnrollLink();
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function ctxProvider() {
    const v = document.getElementById('ctx-provider').value.trim();
    return v ? Number(v) : null;
  }

  // delegated copy buttons
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-copy]');
    if (!btn) return;
    const el = document.querySelector(btn.getAttribute('data-copy'));
    if (el) copyText(el.textContent, btn);
  });

  // ---------- LOGIN ----------
  document.getElementById('login-btn').addEventListener('click', login);
  document.getElementById('token-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') login(); });
  async function login() {
    const status = document.getElementById('login-status');
    const token = document.getElementById('token-input').value;
    status.textContent = 'Checking…'; status.className = 'status';
    try {
      await API.post('/api/provider/login', { token });
      sessionStorage.setItem(TOKEN_KEY, token);  // stay logged in for this session
      enterDashboard();
    } catch (err) {
      status.textContent = '❌ ' + err.message; status.className = 'status err';
    }
  }

  document.getElementById('show-register').addEventListener('click', () => show('register'));
  document.getElementById('back-to-login').addEventListener('click', () => show('login'));
  document.getElementById('logout-btn').addEventListener('click', () => {
    if (ws) { try { ws.close(); } catch (_) {} }
    sessionStorage.removeItem(TOKEN_KEY);
    show('login');
  });

  // ---------- REGISTER ----------
  document.getElementById('register-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target;
    const checked = [...f.querySelectorAll('input[name=services]:checked')].map((c) => c.value);
    const other = (f.services_other.value || '').split(',').map((s) => s.trim()).filter(Boolean);
    const services = [...checked, ...other];
    const body = {
      name: f.name.value.trim(),
      address: f.address.value.trim() || null,
      btc_address: f.btc_address.value.trim(),
      npub: f.npub.value.trim() || null,           // blank -> server generates a key
      services,
      monthly_usd: Number(f.monthly_usd.value) || 20,
      markup_pct: Number(f.markup_pct.value) || 10,
    };
    try {
      const res = await API.post('/api/provider/register', body);
      document.getElementById('r-pid').textContent = res.provider_id;
      document.getElementById('r-link').textContent = location.origin + res.enroll_link;
      document.getElementById('r-token').textContent = res.login_token;

      // If the server generated a key, surface it so the provider saves it.
      if (res.generated_keys) {
        document.getElementById('r-nsec').textContent = res.generated_keys.nsec;
        document.getElementById('r-npub').textContent = res.generated_keys.npub;
        document.getElementById('r-genkey').classList.remove('hidden');
      } else {
        document.getElementById('r-genkey').classList.add('hidden');
      }

      // Persist: login token (session) + btc & provider id (carry to dashboard).
      sessionStorage.setItem(TOKEN_KEY, res.login_token);
      if (res.btc_address) localStorage.setItem(BTC_KEY, res.btc_address);
      if (res.provider_id) localStorage.setItem(PID_KEY, res.provider_id);

      document.getElementById('register-result').classList.remove('hidden');
      document.getElementById('r-dashboard').onclick = () => enterDashboard();
      // wire the contract download to this provider's details
      document.getElementById('r-contract').onclick = async (ev) => {
        ev.target.disabled = true;
        try {
          await API.download('/api/contract', {
            hospital_name: body.name, btc_address: body.btc_address, npub: res.npub,
            monthly_usd: body.monthly_usd, markup_pct: body.markup_pct, services: body.services,
          }, 'hidra_contract.pdf');
        } catch (e) { alert('Contract failed: ' + e.message); }
        finally { ev.target.disabled = false; }
      };
    } catch (err) { alert('Register failed: ' + err.message); }
  });

  // ---------- BOX 1: HUB MESSENGER ----------
  // Connect just saves the hub token on this device; the full messenger lives
  // on its own page (/messenger/) which reads & persists the mailbox.
  // Persist edits to the hospital btc / provider id so they carry across loads.
  document.getElementById('ctx-btc').addEventListener('input', (e) =>
    localStorage.setItem(BTC_KEY, e.target.value.trim()));
  document.getElementById('ctx-provider').addEventListener('input', (e) =>
    localStorage.setItem(PID_KEY, e.target.value.trim()));
  document.getElementById('ctx-provider').addEventListener('change', refreshEnrollLink);

  // Copy the dashboard enrollment link (build it first if needed).
  document.getElementById('copy-enroll-link').addEventListener('click', async (e) => {
    if (!enrollLink) await refreshEnrollLink();
    if (enrollLink) copyText(enrollLink, e.target);
  });

  document.getElementById('connect-hub').addEventListener('click', connectHub);
  function connectHub() {
    const nsec = document.getElementById('hub-nsec').value.trim();
    const status = document.getElementById('hub-status');
    if (!nsec) { status.textContent = 'Enter the hub nsec.'; status.className = 'status err'; return; }
    localStorage.setItem(HUB_KEY, nsec);
    status.textContent = 'Token saved. Click “Open Messenger →”.'; status.className = 'status ok';
  }

  document.getElementById('open-messenger').addEventListener('click', () => {
    const nsec = document.getElementById('hub-nsec').value.trim();
    const status = document.getElementById('hub-status');
    if (nsec) localStorage.setItem(HUB_KEY, nsec);
    if (!localStorage.getItem(HUB_KEY)) {
      status.textContent = 'Enter the hub nsec first.'; status.className = 'status err'; return;
    }
    window.open('/messenger/', '_blank');
  });

  // intake button (delegated)
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-intake]');
    if (!btn) return;
    const message_text = decodeURIComponent(btn.getAttribute('data-intake'));
    const peer_npub = btn.getAttribute('data-peer');
    btn.disabled = true; btn.textContent = 'Saving…';
    try {
      const res = await API.post('/api/provider/intake', { provider_id: ctxProvider(), peer_npub, message_text });
      btn.textContent = '✓ Saved #' + res.intake_id;
    } catch (err) { btn.textContent = '✗ ' + err.message; btn.disabled = false; }
  });

  // ---------- BOX 2: ID CHECK ----------
  document.getElementById('idc-btn').addEventListener('click', async () => {
    const out = document.getElementById('idc-result');
    const body = {
      npub: document.getElementById('idc-npub').value.trim() || null,
      year_of_birth: document.getElementById('idc-yob').value.trim() || null,
      last_name: document.getElementById('idc-last').value.trim() || null,
      city_of_birth: document.getElementById('idc-city').value.trim() || null,
    };
    out.textContent = 'Checking…'; out.className = 'status';
    try {
      const res = await API.post('/api/identity/check', body);
      if (res.success) {
        const who = res.matched_npub ? ` (${res.matched_npub.slice(0, 14)}…)` : '';
        out.textContent = `✅ MEMBER${who} — matched on ${res.matches.join(', ')}`;
        out.className = 'status ok';
      } else { out.textContent = '❌ ' + (res.error || 'No match — not a member'); out.className = 'status err'; }
    } catch (err) { out.textContent = 'Error: ' + err.message; out.className = 'status err'; }
  });

  // ---------- BOX 3: AUDIT ----------
  // The full audit (pull, persist, member-link, search) lives on its own page.
  document.getElementById('open-audit').addEventListener('click', () => {
    window.open('/audit/', '_blank');
  });

  // ---------- BOX 4: BILLS ----------
  // The full bills workflow (add with attachment, search, mark paid) is its own page.
  document.getElementById('open-bills').addEventListener('click', () => {
    window.open('/bills/', '_blank');
  });

  // ---------- SESSION RESTORE ----------
  // If a validated token is saved, go straight to the dashboard — no re-entry.
  async function restore() {
    const token = sessionStorage.getItem(TOKEN_KEY);
    if (!token) { show('login'); return; }
    try {
      await API.post('/api/provider/login', { token });
      enterDashboard();
    } catch (_) {
      sessionStorage.removeItem(TOKEN_KEY);  // stale/invalid token
      show('login');
    }
  }
  restore();
})();
