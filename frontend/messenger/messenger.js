// Darnahi · Project Hidra — standalone Messenger page.
// Mirrors sample_reading_message.py: show your token, list conversations,
// copy an npub to address, type a message, Send / Refresh. Every load also
// persists the decrypted DMs to the `messenger` table (server side).
(() => {
  const views = {
    connect: document.getElementById('connect-view'),
    mailbox: document.getElementById('mailbox-view'),
  };
  const show = (name) =>
    Object.entries(views).forEach(([k, el]) => el.classList.toggle('hidden', k !== name));

  // The dashboard stores the hub token here; the user page stores its own.
  const HUB_KEY = 'hidra_hub_nsec';
  const USER_KEY = 'hidra_nsec';
  let nsec = localStorage.getItem(HUB_KEY) || localStorage.getItem(USER_KEY) || '';
  let timer = null;

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function setStatus(text, cls) {
    const s = document.getElementById('mb-status');
    s.textContent = text; s.className = 'status ' + (cls || '');
  }

  // delegated copy buttons (#selector copies, [data-copy-npub] copies a literal)
  document.addEventListener('click', (e) => {
    const sel = e.target.closest('[data-copy]');
    if (sel) {
      const el = document.querySelector(sel.getAttribute('data-copy'));
      if (el) copyText(el.textContent, sel);
      return;
    }
    const np = e.target.closest('[data-copy-npub]');
    if (np) {
      const npub = np.getAttribute('data-copy-npub');
      document.getElementById('recipient').value = npub;  // fill the receiver
      copyText(npub, np);
    }
  });

  // ---------- connect ----------
  document.getElementById('connect-btn').addEventListener('click', () => {
    const v = document.getElementById('nsec-input').value.trim();
    const st = document.getElementById('connect-status');
    if (!v) { st.textContent = 'Enter a token.'; st.className = 'status err'; return; }
    nsec = v;
    localStorage.setItem(HUB_KEY, v);
    start();
  });

  document.getElementById('forget-btn').addEventListener('click', () => {
    localStorage.removeItem(HUB_KEY);
    if (timer) clearInterval(timer);
    nsec = '';
    show('connect');
  });

  // ---------- mailbox ----------
  function renderConversations(convos) {
    const box = document.getElementById('mailbox');
    box.innerHTML = '';
    const peers = Object.keys(convos);
    if (!peers.length) { box.innerHTML = '<p class="status">No messages yet.</p>'; return; }
    for (const peer of peers) {
      const head = document.createElement('div');
      head.className = 'convo-head';
      head.innerHTML =
        `<span>${peer.slice(0, 12)}…${peer.slice(-6)}</span>` +
        `<button class="secondary intake-btn" data-copy-npub="${peer}">Copy npub</button>`;
      box.appendChild(head);
      for (const m of convos[peer]) {
        const div = document.createElement('div');
        div.className = 'msg ' + (m.is_sent ? 'out' : 'in');
        div.innerHTML = `<span class="t">${m.formatted_time || ''}</span>${escapeHtml(m.content)}`;
        box.appendChild(div);
      }
    }
    box.scrollTop = box.scrollHeight;
  }

  async function loadMailbox() {
    setStatus('Reading relays…');
    try {
      const res = await API.post('/api/messages/load', { nsec });
      document.getElementById('npub-out').textContent = res.npub || '';
      renderConversations(res.conversations || {});
      const n = res.message_count || 0;
      setStatus(`Last refreshed ${new Date().toLocaleTimeString()} · ${n} message(s) saved`, 'ok');
    } catch (err) {
      setStatus('Error: ' + err.message, 'err');
    }
  }

  document.getElementById('refresh-btn').addEventListener('click', loadMailbox);
  document.getElementById('send-btn').addEventListener('click', sendMessage);
  document.getElementById('mail-input').addEventListener('keydown',
    (e) => { if (e.key === 'Enter') sendMessage(); });

  async function sendMessage() {
    const input = document.getElementById('mail-input');
    const text = input.value.trim();
    if (!text) return;
    const recipient = document.getElementById('recipient').value.trim() || null;
    setStatus('Sending…');
    input.value = '';
    try {
      await API.post('/api/messages/send', { nsec, message: text, recipient });
      setStatus('Sent. Refreshing…', 'ok');
      loadMailbox();
    } catch (err) { setStatus('Send failed: ' + err.message, 'err'); }
  }

  function start() {
    show('mailbox');
    loadMailbox();
    if (timer) clearInterval(timer);
    timer = setInterval(loadMailbox, 30000);  // live refresh
  }

  // ---------- init ----------
  if (nsec) start(); else show('connect');
})();
