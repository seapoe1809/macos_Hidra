// Project Hidra — tiny API client shared by USER and PROVIDER pages.
const API = {
  async _json(method, path, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch (_) { /* no body */ }
    if (!res.ok) {
      const detail = (data && (data.detail || data.error)) || res.statusText;
      throw new Error(detail);
    }
    return data;
  },
  get(path) { return this._json('GET', path); },
  post(path, body) { return this._json('POST', path, body); },

  // POST that triggers a file download (e.g. the contract PDF).
  async download(path, body, filename) {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  },

  // WebSocket helper for the live mailbox.
  openMailbox(nsec, interval, onMessage, onError) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/api/messages/ws`);
    ws.onopen = () => ws.send(JSON.stringify({ nsec, interval }));
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.error) { onError && onError(data.error); return; }
      onMessage(data.conversations || {});
    };
    ws.onerror = () => onError && onError('WebSocket error');
    return ws;
  },
};

// localStorage-backed token store (the original app's BrowserState).
const Store = {
  KEY: 'hidra_nsec',
  get() { return localStorage.getItem(this.KEY) || ''; },
  set(v) { localStorage.setItem(this.KEY, v); },
  clear() { localStorage.removeItem(this.KEY); },
};

function copyText(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    if (!btn) return;
    const old = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = old; }, 1200);
  });
}
