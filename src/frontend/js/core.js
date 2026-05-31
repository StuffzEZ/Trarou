const API = window.location.hostname === 'localhost'
  ? 'http://10.0.0.1:8000/api'
  : `http://${window.location.hostname}:8000/api`;

const Auth = {
  _key: 'trarou_token',
  get token() { return sessionStorage.getItem(this._key); },
  set token(v) {
    if (v) sessionStorage.setItem(this._key, v);
    else sessionStorage.removeItem(this._key);
  },
  get isAdmin() { return !!this.token; },
  logout() { this.token = null; }
};

async function apiFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (Auth.token) headers['Authorization'] = `Bearer ${Auth.token}`;
  if (opts.body instanceof FormData) delete headers['Content-Type'];
  const res = await fetch(`${API}${path}`, { ...opts, headers });
  if (res.status === 401) {
    Auth.logout();
    showPage('login');
    throw new Error('Unauthorised');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
}

async function apiGet(path)        { return apiFetch(path); }
async function apiPost(path, body) { return apiFetch(path, { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body) }); }
async function apiDelete(path)     { return apiFetch(path, { method: 'DELETE' }); }

let _toastTimer;
function toast(msg, duration = 2800) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), duration);
}

const pages = {};
let currentPage = null;

function registerPage(id, { init, show, hide } = {}) {
  pages[id] = { init, show, hide, initialised: false };
}

function showPage(id, ...args) {
  if (currentPage && pages[currentPage]?.hide) pages[currentPage].hide();
  document.querySelectorAll('.page-section').forEach(el => el.style.display = 'none');
  const section = document.getElementById(`page-${id}`);
  if (!section) return;
  section.style.display = 'flex';
  section.classList.remove('page-enter');
  void section.offsetWidth;
  section.classList.add('page-enter');
  currentPage = id;
  const pg = pages[id];
  if (!pg) return;
  if (!pg.initialised && pg.init) {
    pg.init();
    pg.initialised = true;
  }
  if (pg.show) pg.show(...args);
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

function mimeEmoji(mime) {
  if (!mime) return '📄';
  if (mime.startsWith('video'))  return '🎬';
  if (mime.startsWith('audio'))  return '🎵';
  if (mime.startsWith('image'))  return '🖼️';
  if (mime.includes('pdf'))      return '📕';
  if (mime.includes('zip') || mime.includes('tar')) return '📦';
  if (mime.includes('text'))     return '📝';
  return '📄';
}

function signalBars(strength) {
  // strength is 0-100 from nmcli or negative dBm from iwlist
  let level = 0;
  let pct = strength;
  // Convert dBm to percentage if negative
  if (strength < 0) {
    pct = Math.min(100, Math.max(0, (strength + 100) * 2));
  }
  if (pct > 75)      level = 4;
  else if (pct > 50) level = 3;
  else if (pct > 25) level = 2;
  else if (pct > 0)  level = 1;
  return `<div class="signal-bars">
    ${[1,2,3,4].map(i => `<div class="signal-bar ${i <= level ? 'active' : ''}"></div>`).join('')}
  </div>`;
}

function securityBadge(sec) {
  if (!sec || sec === 'Open' || sec === '--') return '<span class="badge badge-orange">Open</span>';
  return '<span class="badge badge-green">' + sec + '</span>';
}

const Icon = {
  back: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>`,
  chevron: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16"><path d="M9 18l6-6-6-6"/></svg>`,
};

// Safe string escaping for use in HTML attribute JavaScript strings
function escStr(s) {
  return String(s)
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/"/g, '\\"')
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r')
    .replace(/</g, '\\x3c')
    .replace(/>/g, '\\x3e');
}
