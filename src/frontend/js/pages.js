/* ── Admin gating ────────────────────────────── */
let pendingAdminAction = null;

function requireAdmin(action) {
  if (Auth.isAdmin) { showPage(action); }
  else { pendingAdminAction = action; showPage('admin-login'); }
}

function showAdminLoginPrompt() {
  pendingAdminAction = null;
  document.getElementById('admin-login-pw').value = '';
  document.getElementById('admin-login-error').classList.remove('show');
  showPage('admin-login');
}

function updateAdminUI() {
  document.getElementById('sys-admin-section').style.display = Auth.isAdmin ? 'block' : 'none';
  const lbl = document.getElementById('admin-icon-label');
  if (lbl) lbl.textContent = Auth.isAdmin ? 'Admin' : 'Admin';
}

function endAdminSession() {
  Auth.logout();
  updateAdminUI();
  toast('Logged out');
  showPage('home');
}

document.addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    if (currentPage === 'login') doCaptiveLogin();
    else if (currentPage === 'admin-login') doAdminLogin();
  }
});

/* ═══════════════════════════════════════════════
   PAGE: LOGIN
   ═══════════════════════════════════════════════ */
document.getElementById('login-btn').addEventListener('click', doCaptiveLogin);
document.getElementById('login-password').addEventListener('keydown', e => {
  if (e.key === 'Enter') doCaptiveLogin();
});

async function doCaptiveLogin() {
  const username = document.getElementById('login-username').value.trim() || 'admin';
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  if (!password) {
    errEl.textContent = 'Password is required';
    errEl.classList.add('show');
    return;
  }
  errEl.classList.remove('show');
  document.getElementById('login-btn-text').style.display = 'none';
  document.getElementById('login-btn-spinner').style.display = 'inline-block';
  document.getElementById('login-btn').disabled = true;
  try {
    const params = new URLSearchParams(window.location.search);
    const mac = params.get('mac') || '';
    const res = await apiPost('/auth/captive-login', { username, password, mac });
    if (res.redirect && !window.location.href.startsWith(res.redirect)) {
      window.location.href = res.redirect;
    } else {
      showPage('home');
    }
  } catch (err) {
    errEl.textContent = err.message || 'Login failed';
    errEl.classList.add('show');
  } finally {
    document.getElementById('login-btn-text').style.display = 'inline';
    document.getElementById('login-btn-spinner').style.display = 'none';
    document.getElementById('login-btn').disabled = false;
  }
}

registerPage('login', {
  show() {
    document.getElementById('login-username').value = 'admin';
    document.getElementById('login-password').value = '';
    document.getElementById('login-error').classList.remove('show');
    document.getElementById('login-username').focus();
  }
});

/* ═══════════════════════════════════════════════
   PAGE: HOME
   ═══════════════════════════════════════════════ */
let homeInterval;

registerPage('home', {
  init() { fetchHomeStatus(); },
  show() {
    fetchHomeStatus();
    updateClock();
    homeInterval = setInterval(() => {
      fetchHomeStatus();
      updateClock();
    }, 10000);
  },
  hide() { clearInterval(homeInterval); }
});

async function fetchHomeStatus() {
  try {
    const data = await apiGet('/network/status');
    document.getElementById('home-ssid').textContent = data.ap_ssid || 'Trarou';
    document.getElementById('quick-ap').textContent = data.ap_active ? 'AP active' : 'AP offline';
    document.getElementById('quick-client').textContent = data.client_connected
      ? 'Connected to ' + data.client_ssid : 'No upstream connection';
    const badge = document.getElementById('quick-internet-badge');
    badge.innerHTML = data.internet_reachable
      ? '<span class="badge badge-green">Online</span>'
      : '<span class="badge badge-orange">Offline</span>';
    document.getElementById('home-dot').classList.toggle('offline', !data.internet_reachable);
  } catch (e) { /* silent */ }
}

function updateClock() {
  document.getElementById('home-time').textContent =
    new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/* ═══════════════════════════════════════════════
   PAGE: MEDIA BROWSER
   ═══════════════════════════════════════════════ */
let allMediaFiles = [];

function renderMediaGrid(files) {
  if (!files || files.length === 0)
    return '<div style="text-align:center;padding:40px 0;color:var(--text-3);font-size:13px">No files</div>';
  return '<div class="media-grid">' + files.map(f =>
    '<div class="media-card" onclick="playMedia(\'' + escStr(f.path) + '\')">' +
      '<div class="media-card-thumb">' + mimeEmoji(f.mime_type) + '</div>' +
      '<div class="media-card-info">' +
        '<div class="media-card-name">' + escapeHtml(f.name) + '</div>' +
        '<div class="media-card-meta">' + formatBytes(f.size_bytes) + '</div>' +
      '</div>' +
    '</div>'
  ).join('') + '</div>';
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function playMedia(path) {
  const file = allMediaFiles.find(f => f.path === path);
  if (!file) return;
  const mime = file.mime_type || '';
  if (mime.startsWith('video/') || mime.startsWith('audio/')) {
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.92);display:flex;align-items:center;justify-content:center;padding:20px;flex-direction:column';
    overlay.onclick = () => overlay.remove();
    const closeBtn = document.createElement('button');
    closeBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" width="24" height="24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
    closeBtn.style.cssText = 'position:absolute;top:16px;right:16px;background:none;border:none;cursor:pointer;padding:8px';
    closeBtn.onclick = () => overlay.remove();
    const el = mime.startsWith('video/') ? document.createElement('video') : document.createElement('audio');
    el.controls = true;
    el.autoplay = true;
    el.style.cssText = 'max-width:100%;max-height:90vh;border-radius:12px';
    el.src = file.url;
    overlay.appendChild(closeBtn);
    overlay.appendChild(el);
    el.onclick = e => e.stopPropagation();
    document.body.appendChild(overlay);
  } else {
    window.open(file.url, '_blank');
  }
}

function mediaOpenFolder(folderPath) {
  const prefix = folderPath + '/';
  const subFiles = allMediaFiles.filter(f =>
    f.path.startsWith(prefix) && f.path.split('/').length === folderPath.split('/').length + 1
  );
  document.getElementById('media-folders').innerHTML = '';
  document.getElementById('media-files-section').innerHTML =
    '<div class="section-title">' + escapeHtml(folderPath) + '</div>' +
    renderMediaGrid(subFiles);
  document.getElementById('media-breadcrumb').style.display = 'block';
}

function mediaNavUp() {
  const bc = document.getElementById('media-breadcrumb');
  const folders = document.getElementById('media-folders');
  const filesSection = document.getElementById('media-files-section');
  if (folders.innerHTML && !filesSection.innerHTML) { bc.style.display = 'none'; return; }
  bc.style.display = 'none';
  const loading = document.getElementById('media-loading');
  const empty = document.getElementById('media-empty');
  loading.style.display = 'block';
  empty.style.display = 'none';
  folders.innerHTML = '';
  filesSection.innerHTML = '';
  loadMediaTree(loading, empty, folders, filesSection);
}

registerPage('media', {
  show() {
    allMediaFiles = [];
    const loading = document.getElementById('media-loading');
    const empty = document.getElementById('media-empty');
    const foldersEl = document.getElementById('media-folders');
    const filesEl = document.getElementById('media-files-section');
    const breadcrumb = document.getElementById('media-breadcrumb');
    loading.style.display = 'block';
    empty.style.display = 'none';
    foldersEl.innerHTML = '';
    filesEl.innerHTML = '';
    breadcrumb.style.display = 'none';
    loadMediaTree(loading, empty, foldersEl, filesEl);
  }
});

async function loadMediaTree(loading, empty, foldersEl, filesEl) {
    try {
      const data = await apiGet('/media/tree');
      loading.style.display = 'none';
      allMediaFiles = data.files || [];
      const folders = data.folders || [];
      if (folders.length === 0 && allMediaFiles.length === 0) {
        empty.style.display = 'block';
        return;
      }
      if (folders.length > 0) {
        foldersEl.innerHTML = '<div class="section-title">Folders</div><div class="row-list">' +
          folders.map(f =>
            '<div class="folder-row" onclick="mediaOpenFolder(\'' + escStr(f.path) + '\')">' +
              '<span style="font-size:20px">&#128193;</span>' +
              '<div style="flex:1">' +
                '<div style="font-size:14px;font-weight:500">' + escapeHtml(f.name) + '</div>' +
                '<div style="font-size:11px;color:var(--text-3)">' + f.children_count + ' items</div>' +
              '</div>' +
            '</div>'
          ).join('') +
          '</div>';
      }
      const rootFiles = allMediaFiles.filter(f => !f.path.includes('/'));
      if (rootFiles.length > 0) {
        filesEl.innerHTML = '<div class="section-title" style="margin-top:16px">Files</div>' +
          renderMediaGrid(rootFiles);
      }
    } catch (err) {
      loading.style.display = 'none';
      empty.innerHTML = '<div style="color:#f87171;font-size:14px">Error: ' + escapeHtml(err.message) + '</div>';
      empty.style.display = 'block';
    }
}

/* ═══════════════════════════════════════════════
   PAGE: UPLOAD
   ═══════════════════════════════════════════════ */
let uploadQueue = [];

function renderUploadQueue() {
  const list = document.getElementById('upload-queue-list');
  const section = document.getElementById('upload-queue');
  if (uploadQueue.length === 0) { section.style.display = 'none'; return; }
  section.style.display = 'block';
  list.innerHTML = uploadQueue.map((f, i) =>
    '<div class="row" style="cursor:default">' +
      '<div class="row-body">' +
        '<div class="row-title" style="font-size:13px">' + escapeHtml(f.name) + '</div>' +
        '<div class="row-sub">' + formatBytes(f.size) + '</div>' +
      '</div>' +
      '<div class="row-end" style="cursor:pointer" onclick="removeUpload(' + i + ')">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>' +
      '</div>' +
    '</div>'
  ).join('');
}

function removeUpload(i) {
  uploadQueue.splice(i, 1);
  renderUploadQueue();
  document.getElementById('upload-btn').style.display = (Auth.isAdmin && uploadQueue.length > 0) ? 'flex' : 'none';
}

registerPage('upload', {
  show() {
    document.getElementById('upload-btn').style.display = (Auth.isAdmin && uploadQueue.length > 0) ? 'flex' : 'none';
  }
});

const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  addFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', () => {
  addFiles(fileInput.files);
  fileInput.value = '';
});

function addFiles(files) {
  for (const f of files) uploadQueue.push(f);
  renderUploadQueue();
  if (Auth.isAdmin && uploadQueue.length > 0)
    document.getElementById('upload-btn').style.display = 'flex';
}

document.getElementById('upload-btn').addEventListener('click', doUpload);

async function doUpload() {
  if (uploadQueue.length === 0 || !Auth.isAdmin) return;
  const folder = document.getElementById('upload-folder').value.trim();
  const progressWrap = document.getElementById('upload-progress-wrap');
  const progressFill = document.getElementById('upload-progress-fill');
  const progressLabel = document.getElementById('upload-progress-label');
  const btn = document.getElementById('upload-btn');
  btn.disabled = true;
  progressWrap.style.display = 'block';
  progressFill.style.width = '0%';
  progressLabel.textContent = 'Uploading 0 / ' + uploadQueue.length + ' ...';
  let completed = 0;
  for (const file of uploadQueue) {
    const fd = new FormData();
    fd.append('files', file);
    if (folder) fd.append('folder', folder);
    try {
      await apiPost('/media/upload', fd);
      completed++;
      const pct = Math.round((completed / uploadQueue.length) * 100);
      progressFill.style.width = pct + '%';
      progressLabel.textContent = 'Uploading ' + completed + ' / ' + uploadQueue.length + ' ...';
    } catch (err) {
      toast('Upload failed: ' + err.message);
      btn.disabled = false;
      return;
    }
  }
  progressLabel.textContent = 'Upload complete';
  setTimeout(() => { progressWrap.style.display = 'none'; }, 2000);
  uploadQueue = [];
  renderUploadQueue();
  btn.disabled = false;
  btn.style.display = 'none';
  toast('Uploaded ' + completed + ' file(s)');
}

/* ═══════════════════════════════════════════════
   PAGE: NETWORK
   ═══════════════════════════════════════════════ */
let pendingConnectSsid = null;

registerPage('network', {
  show() {
    this._refreshStatus();
    document.getElementById('net-connect-form').style.display = 'none';
    document.getElementById('net-scan-results').innerHTML =
      '<div style="text-align:center;padding:32px 0;color:var(--text-3);font-size:13px">Press Scan to search for networks</div>';
  },
  _refreshStatus: async () => {
    try {
      const data = await apiGet('/network/status');
      document.getElementById('net-ap-ssid').textContent = data.ap_ssid || '—';
      document.getElementById('net-ap-ip').textContent = data.ap_active ? 'Active' : 'Offline';
      document.getElementById('net-ap-badge').innerHTML = data.ap_active
        ? '<span class="badge badge-green">Active</span>'
        : '<span class="badge badge-red">Offline</span>';
      if (data.client_connected) {
        document.getElementById('net-client-ssid').textContent = data.client_ssid || 'Connected';
        document.getElementById('net-client-ip').textContent = data.client_ip || '—';
        document.getElementById('net-internet-badge').innerHTML = data.internet_reachable
          ? '<span class="badge badge-green">Online</span>'
          : '<span class="badge badge-orange">Offline</span>';
        document.getElementById('net-disconnect-row').style.display = 'flex';
      } else {
        document.getElementById('net-client-ssid').textContent = 'Not connected';
        document.getElementById('net-client-ip').textContent = '—';
        document.getElementById('net-internet-badge').innerHTML = '';
        document.getElementById('net-disconnect-row').style.display = 'none';
      }
    } catch (e) { /* silent */ }
  }
});

async function scanNetworks() {
  const results = document.getElementById('net-scan-results');
  results.innerHTML = '<div style="text-align:center;padding:32px 0"><div class="spinner" style="border-top-color:var(--accent)"></div></div>';
  document.getElementById('scan-btn').disabled = true;
  try {
    const data = await apiGet('/network/scan');
    const nets = data.networks || [];
    if (nets.length === 0) {
      results.innerHTML = '<div style="text-align:center;padding:32px 0;color:var(--text-3);font-size:13px">No networks found</div>';
      return;
    }
    results.innerHTML = '<div class="row-list">' +
      nets.map(n =>
        '<div class="row" onclick="showConnectForm(\'' + escStr(n.ssid) + '\')">' +
          '<div class="row-icon" style="background:var(--grad-network)">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" style="width:16px;height:16px"><path d="M1.42 9a16 16 0 0121.16 0"/><path d="M5 12.55a11 11 0 0114.08 0"/><path d="M8.53 16.11a6 6 0 016.95 0"/><circle cx="12" cy="20" r="1" fill="#fff" stroke="none"/></svg>' +
          '</div>' +
          '<div class="row-body"><div class="row-title" style="font-size:13px">' + escapeHtml(n.ssid) + '</div></div>' +
          '<div class="row-end">' + signalBars(n.signal_strength) + securityBadge(n.security) + '</div>' +
        '</div>'
      ).join('') +
      '</div>';
  } catch (err) {
    results.innerHTML = '<div style="text-align:center;padding:32px 0;color:#f87171;font-size:13px">Scan failed: ' + escapeHtml(err.message) + '</div>';
  } finally {
    document.getElementById('scan-btn').disabled = false;
  }
}

function showConnectForm(ssid) {
  pendingConnectSsid = ssid;
  document.getElementById('connect-ssid-label').textContent = ssid;
  document.getElementById('net-connect-form').style.display = 'block';
  document.getElementById('connect-password').value = '';
  document.getElementById('connect-password').focus();
}

function cancelConnect() {
  document.getElementById('net-connect-form').style.display = 'none';
  pendingConnectSsid = null;
}

async function doConnect() {
  if (!pendingConnectSsid) return;
  const password = document.getElementById('connect-password').value;
  document.getElementById('connect-btn').disabled = true;
  try {
    await apiPost('/network/connect', { ssid: pendingConnectSsid, password: password || null });
    toast('Connected to ' + pendingConnectSsid);
    cancelConnect();
    const pg = pages['network'];
    if (pg) pg._refreshStatus();
  } catch (err) {
    toast('Connection failed: ' + err.message);
  } finally {
    document.getElementById('connect-btn').disabled = false;
  }
}

async function disconnectWifi() {
  try {
    await apiPost('/network/disconnect');
    toast('Disconnected');
    const pg = pages['network'];
    if (pg) pg._refreshStatus();
  } catch (err) {
    toast('Disconnect failed: ' + err.message);
  }
}

/* ═══════════════════════════════════════════════
   PAGE: REMOTE DESKTOP (VNC)
   ═══════════════════════════════════════════════ */
registerPage('vnc', {
  show() { refreshVncStatus(); }
});

async function refreshVncStatus() {
  try {
    const data = await apiGet('/vnc/status');
    document.getElementById('vnc-status-text').textContent = data.running ? 'Running' : 'Stopped';
    document.getElementById('vnc-status-badge').innerHTML = data.running
      ? '<span class="badge badge-green">Running</span>'
      : '<span class="badge badge-red">Stopped</span>';
    document.getElementById('vnc-start-btn').disabled = data.running;
    document.getElementById('vnc-stop-btn').disabled = !data.running;
    if (data.running && data.novnc_url) {
      document.getElementById('vnc-placeholder').style.display = 'none';
      const iframe = document.getElementById('vnc-iframe');
      iframe.src = data.novnc_url;
      iframe.style.display = 'block';
      document.getElementById('vnc-open-btn').style.display = 'flex';
    } else {
      document.getElementById('vnc-placeholder').style.display = 'flex';
      document.getElementById('vnc-iframe').style.display = 'none';
      document.getElementById('vnc-iframe').src = '';
      document.getElementById('vnc-open-btn').style.display = 'none';
    }
  } catch (e) { /* silent */ }
}

async function startVnc() {
  try {
    const data = await apiPost('/vnc/start');
    toast('Remote desktop started');
    refreshVncStatus();
  } catch (err) {
    toast('Start failed: ' + err.message);
  }
}

async function stopVnc() {
  try {
    await apiPost('/vnc/stop');
    toast('Remote desktop stopped');
    refreshVncStatus();
  } catch (err) {
    toast('Stop failed: ' + err.message);
  }
}

function openVncTab() {
  const iframe = document.getElementById('vnc-iframe');
  if (iframe.src) window.open(iframe.src, '_blank');
}

/* ═══════════════════════════════════════════════
   PAGE: SYSTEM
   ═══════════════════════════════════════════════ */
let sysInterval;

registerPage('system', {
  show() {
    updateAdminUI();
    this._refresh();
    sysInterval = setInterval(() => this._refresh(), 5000);
  },
  hide() { clearInterval(sysInterval); },
  _refresh: async () => {
    try {
      const data = await apiGet('/system/info');
      document.getElementById('sys-hostname').textContent = data.hostname;
      const cpu = Math.round(data.cpu_percent);
      document.getElementById('sys-cpu').textContent = cpu;
      document.getElementById('sys-cpu-bar').style.width = cpu + '%';
      const memPct = Math.round((data.memory_used_mb / data.memory_total_mb) * 100);
      document.getElementById('sys-mem').textContent = memPct;
      document.getElementById('sys-mem-bar').style.width = memPct + '%';
      const diskPct = Math.round((data.disk_used_gb / data.disk_total_gb) * 100);
      document.getElementById('sys-disk').textContent = diskPct;
      document.getElementById('sys-disk-bar').style.width = diskPct + '%';
      document.getElementById('sys-uptime').textContent = formatUptime(data.uptime_seconds);
      document.getElementById('sys-load').textContent = data.load_avg.map(v => v.toFixed(2)).join('  ');
    } catch (e) { /* silent */ }
  }
});

function formatUptime(s) {
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  let r = '';
  if (d > 0) r += d + 'd ';
  if (h > 0) r += h + 'h ';
  r += m + 'm';
  return r;
}

function confirmReboot() {
  if (confirm('Reboot the router?')) {
    apiPost('/system/reboot').then(() => toast('Rebooting...')).catch(e => toast(e.message));
  }
}

function confirmShutdown() {
  if (confirm('Shut down the router?')) {
    apiPost('/system/shutdown').then(() => toast('Shutting down...')).catch(e => toast(e.message));
  }
}

async function changePassword() {
  const p1 = document.getElementById('new-pw-1').value;
  const p2 = document.getElementById('new-pw-2').value;
  if (!p1 || p1.length < 8) { toast('Minimum 8 characters'); return; }
  if (p1 !== p2) { toast('Passwords do not match'); return; }
  try {
    await apiPost('/system/set-password', { new_password: p1 });
    toast('Password updated');
    document.getElementById('new-pw-1').value = '';
    document.getElementById('new-pw-2').value = '';
    showPage('system');
  } catch (err) {
    toast('Failed: ' + err.message);
  }
}

/* ═══════════════════════════════════════════════
   PAGE: ADMIN LOGIN
   ═══════════════════════════════════════════════ */
document.getElementById('admin-login-btn').addEventListener('click', doAdminLogin);
document.getElementById('admin-login-pw').addEventListener('keydown', e => {
  if (e.key === 'Enter') doAdminLogin();
});

async function doAdminLogin() {
  const pw = document.getElementById('admin-login-pw').value;
  const errEl = document.getElementById('admin-login-error');
  if (!pw) {
    errEl.textContent = 'Password is required';
    errEl.classList.add('show');
    return;
  }
  errEl.classList.remove('show');
  document.getElementById('admin-login-btn').disabled = true;
  try {
    const fd = new URLSearchParams({ username: 'admin', password: pw });
    const res = await fetch(API + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: fd
    });
    if (!res.ok) throw new Error('Incorrect password');
    const data = await res.json();
    Auth.token = data.access_token;
    updateAdminUI();
    toast('Admin access granted');
    if (pendingAdminAction) {
      const action = pendingAdminAction;
      pendingAdminAction = null;
      showPage(action);
    } else {
      showPage('home');
    }
  } catch (err) {
    errEl.textContent = err.message || 'Login failed';
    errEl.classList.add('show');
  } finally {
    document.getElementById('admin-login-btn').disabled = false;
  }
}

registerPage('admin-login', {
  show() {
    document.getElementById('admin-login-pw').value = '';
    document.getElementById('admin-login-error').classList.remove('show');
    setTimeout(() => document.getElementById('admin-login-pw').focus(), 100);
  }
});

/* ═══════════════════════════════════════════════
   PAGE: CHANGE PASSWORD
   ═══════════════════════════════════════════════ */
registerPage('change-password', {
  show() {
    document.getElementById('new-pw-1').value = '';
    document.getElementById('new-pw-2').value = '';
  }
});

/* ═══════════════════════════════════════════════
   PAGE: ABOUT
   ═══════════════════════════════════════════════ */
registerPage('about', {
  async show() { await loadAbout(); }
});

async function loadAbout() {
  try {
    var sys = await apiGet('/system/info');
    document.getElementById('about-hostname').textContent = sys.hostname;
    var d = Math.floor(sys.uptime_seconds / 86400);
    var h = Math.floor((sys.uptime_seconds % 86400) / 3600);
    var m = Math.floor((sys.uptime_seconds % 3600) / 60);
    document.getElementById('about-uptime').textContent = (d > 0 ? d + 'd ' : '') + h + 'h ' + m + 'm';
  } catch (e) { /* silent */ }

  try {
    var net = await apiGet('/network/status');
    document.getElementById('about-ap-iface').textContent = net.ap_interface;
    document.getElementById('about-client-iface').textContent = net.client_interface;
  } catch (e) { /* silent */ }

  try {
    var upd = await apiGet('/system/update-check');
    document.getElementById('about-version').textContent = upd.local_version || 'dev';
  } catch (e) {
    document.getElementById('about-version').textContent = 'dev';
  }

  document.getElementById('about-installer').textContent = 'Trarou User';
}

/* ═══════════════════════════════════════════════
   PAGE: AI CHAT
   ═══════════════════════════════════════════════ */
let aiMessages = [];
let aiStreaming = false;

registerPage('ai', {
  async show() {
    await refreshAiStatus();
  }
});

async function refreshAiStatus() {
  try {
    var data = await apiGet('/ai/status');
    var badge = document.getElementById('ai-backend-badge');
    var modelInfo = document.getElementById('ai-model-info');
    var backend = data.active_backend;
    var labels = { ollama: 'Local', browser: 'Browser' };
    var colors = { ollama: 'green', browser: 'orange' };
    badge.innerHTML = '<span class="badge badge-' + (colors[backend] || 'orange') + '" style="font-size:11px">' + (labels[backend] || backend) + '</span>';

    var models = data.ollama ? data.ollama.models : [];
    var rec = data.recommendation || {};
    if (modelInfo) {
      if (models.length > 0) {
        modelInfo.innerHTML = '<span style="font-size:11px;color:var(--text-3)">Model: ' + models[0] + '</span>';
      } else if (data.ollama && data.ollama.available && rec.recommended) {
        modelInfo.innerHTML = '<span style="font-size:11px;color:var(--text-3)">Recommended: ' + rec.recommended + '</span>' +
          '<button class="btn btn-secondary" style="padding:4px 10px;font-size:11px;margin-left:8px" onclick="autoSetupAi()">Install</button>';
      } else if (!data.ollama || !data.ollama.available) {
        modelInfo.innerHTML = '<span style="font-size:11px;color:var(--text-3)">Install Ollama for local AI: <code>curl -fsSL https://ollama.com/install.sh | sh</code></span>';
      }
    }

    var mgmt = document.getElementById('ai-model-mgmt');
    if (mgmt && Auth.isAdmin && models.length > 0) {
      var html = '<div class="row-list">';
      models.forEach(function(m) {
        html += '<div class="row"><div class="row-body"><div class="row-title" style="font-size:13px">' + m + '</div></div>';
        html += '<div class="row-end" style="cursor:pointer" onclick="deleteAiModel(\'' + m + '\')">';
        html += '<svg viewBox="0 0 24 24" fill="none" stroke="#f87171" stroke-width="2" width="14" height="14"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>';
        html += '</div></div>';
      });
      html += '</div>';
      mgmt.innerHTML = html;
      mgmt.style.display = 'block';
    }
  } catch (e) { /* silent */ }
}

async function autoSetupAi() {
  try {
    var result = await apiPost('/ai/auto-setup');
    if (result.status === 'pulling') {
      toast('Downloading ' + result.model + '...');
    } else if (result.status === 'already_configured') {
      toast('Models already installed');
    }
    await refreshAiStatus();
  } catch (err) {
    toast('Error: ' + err.message);
  }
}

async function deleteAiModel(model) {
  if (!confirm('Delete model ' + model + '?')) return;
  try {
    await apiDelete('/ai/delete-model/' + encodeURIComponent(model));
    toast('Model removed');
    await refreshAiStatus();
  } catch (err) {
    toast('Error: ' + err.message);
  }
}

function clearAiChat() {
  aiMessages = [];
  var msgs = document.getElementById('ai-chat-messages');
  msgs.innerHTML = '<div class="ai-welcome"><div class="ai-welcome-icon">&#10022;</div><div class="ai-welcome-title">Trarou AI</div><div class="ai-welcome-sub">Ask me anything about your travel router.</div></div>';
}

function setAiPrompt(text) {
  var input = document.getElementById('ai-input');
  input.value = text;
  input.focus();
  autoResizeTextarea(input);
}

function autoResizeTextarea(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

function aiInputKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendAiMessage();
  }
  autoResizeTextarea(e.target);
}

document.getElementById('ai-input').addEventListener('input', function() {
  autoResizeTextarea(this);
});

async function sendAiMessage() {
  if (aiStreaming) return;
  var input = document.getElementById('ai-input');
  var text = input.value.trim();
  if (!text) return;

  document.getElementById('ai-quick-prompts').style.display = 'none';
  input.value = '';
  input.style.height = 'auto';

  var welcome = document.querySelector('.ai-welcome');
  if (welcome) welcome.remove();

  aiMessages.push({ role: 'user', content: text });
  renderUserMessage(text);

  var assistantBubble = appendAssistantBubble();
  aiStreaming = true;
  document.getElementById('ai-send-btn').disabled = true;

  // Try browser AI first (Chrome 127+ Gemini Nano)
  if (window.ai && window.ai.languageModel) {
    try {
      await streamBrowserAI(text, assistantBubble);
      return;
    } catch (e) { /* Fall through to server */ }
  }

  await streamServerAI(assistantBubble);
}

async function streamBrowserAI(text, bubble) {
  var session = await window.ai.languageModel.create({
    systemPrompt: "You are the Trarou AI assistant. Help users with networking, travel router setup, and troubleshooting."
  });
  var stream = await session.promptStreaming(text);
  var full = '';
  var content = bubble.querySelector('.ai-bubble-content');
  for await (var chunk of stream) {
    full = chunk;
    content.innerHTML = renderMarkdown(full);
    scrollAiToBottom();
  }
  session.destroy();
  aiMessages.push({ role: 'assistant', content: full });
  finishAiStream(bubble);
}

async function streamServerAI(bubble) {
  var content = bubble.querySelector('.ai-bubble-content');
  var fullText = '';

  try {
    var res = await fetch(API + '/ai/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(Auth.token ? { 'Authorization': 'Bearer ' + Auth.token } : {}),
      },
      body: JSON.stringify({ messages: aiMessages }),
    });

    if (!res.ok) throw new Error('AI request failed');
    if (!res.body) throw new Error('No response body');

    var reader = res.body.getReader();
    var decoder = new TextDecoder();

    while (true) {
      var result = await reader.read();
      if (result.done) break;
      var text = decoder.decode(result.value);
      for (var line of text.split('\n')) {
        if (line.startsWith('data: ')) {
          try {
            var obj = JSON.parse(line.slice(6));
            if (obj.chunk) {
              fullText += obj.chunk;
              content.innerHTML = renderMarkdown(fullText);
              scrollAiToBottom();
            }
            if (obj.done) break;
            if (obj.error) {
              content.innerHTML = '<span style="color:#f87171">' + escapeHtml(obj.error) + '</span>';
            }
          } catch (e) { /* partial JSON */ }
        }
      }
    }
  } catch (err) {
    content.innerHTML = '<span style="color:#f87171">Error: ' + escapeHtml(err.message) + '</span>';
  }

  if (fullText) aiMessages.push({ role: 'assistant', content: fullText });
  finishAiStream(bubble);
}

function renderUserMessage(text) {
  var msgs = document.getElementById('ai-chat-messages');
  var div = document.createElement('div');
  div.className = 'ai-msg ai-msg-user';
  div.innerHTML = '<div class="ai-bubble ai-bubble-user">' + escapeHtml(text) + '</div>';
  msgs.appendChild(div);
  scrollAiToBottom();
}

function appendAssistantBubble() {
  var msgs = document.getElementById('ai-chat-messages');
  var div = document.createElement('div');
  div.className = 'ai-msg ai-msg-assistant';
  div.innerHTML = '<div class="ai-avatar">&#10022;</div><div class="ai-bubble ai-bubble-assistant"><div class="ai-bubble-content ai-thinking"><span class="ai-dot"></span><span class="ai-dot"></span><span class="ai-dot"></span></div></div>';
  msgs.appendChild(div);
  scrollAiToBottom();
  return div;
}

function finishAiStream(bubble) {
  aiStreaming = false;
  document.getElementById('ai-send-btn').disabled = false;
  bubble.querySelector('.ai-bubble-content').classList.remove('ai-thinking');
}

function scrollAiToBottom() {
  var msgs = document.getElementById('ai-chat-messages');
  msgs.scrollTop = msgs.scrollHeight;
}

function renderMarkdown(text) {
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/^### (.+)$/gm, '<h4 style="margin:8px 0 4px;font-size:13px;font-weight:600">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 style="margin:10px 0 5px;font-size:14px;font-weight:600">$1</h3>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/s, '<ul style="padding-left:18px;margin:6px 0">$1</ul>')
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n/g, '<br>');
}

/* ═══════════════════════════════════════════════
   PAGE: TAILSCALE
   ═══════════════════════════════════════════════ */
registerPage('tailscale', {
  async show() {
    await refreshTailscale();
  }
});

async function refreshTailscale() {
  try {
    var data = await apiGet('/tailscale/status');
    var tsText = document.getElementById('ts-status-text');
    var tsSub = document.getElementById('ts-status-sub');
    var tsBadge = document.getElementById('ts-status-badge');
    var tsUpBtn = document.getElementById('ts-up-btn');
    var tsDownBtn = document.getElementById('ts-down-btn');
    var tsLoginSection = document.getElementById('ts-login-section');
    var tsExitSection = document.getElementById('ts-exit-section');
    var tsPeersSection = document.getElementById('ts-peers-section');

    if (!data.installed) {
      tsText.textContent = 'Tailscale not installed';
      tsSub.textContent = 'Run: curl -fsSL https://tailscale.com/install.sh | sh';
      tsBadge.innerHTML = '<span class="badge badge-red">Not Installed</span>';
      return;
    }

    if (data.running) {
      tsText.textContent = 'Connected';
      tsSub.textContent = data.hostname ? data.hostname + ' (' + (data.ips || []).join(', ') + ')' : '';
      tsBadge.innerHTML = '<span class="badge badge-green">Connected</span>';
      tsUpBtn.disabled = true;
      tsDownBtn.disabled = false;

      // Show exit nodes
      if (data.peers && data.peers.length > 0) {
        tsExitSection.style.display = 'block';
        var exitHtml = '';
        data.peers.forEach(function(p) {
          if (p.exit_node_option) {
            var active = p.exit_node;
            exitHtml += '<div class="row" onclick="setTsExitNode(\'' + p.ips[0] + '\')" style="cursor:pointer">';
            exitHtml += '<div class="row-body"><div class="row-title" style="font-size:13px">' + escapeHtml(p.hostname) + '</div>';
            exitHtml += '<div class="row-sub">' + p.ips.join(', ') + '</div></div>';
            exitHtml += '<div class="row-end">' + (active ? '<span class="badge badge-green">Active</span>' : '') + '</div></div>';
          }
        });
        if (exitHtml) {
          exitHtml = '<div class="row" onclick="setTsExitNode(null)" style="cursor:pointer"><div class="row-body"><div class="row-title" style="font-size:13px;color:#f87171">Clear exit node</div></div></div>' + exitHtml;
          document.getElementById('ts-exit-nodes').innerHTML = exitHtml;
        }
      }

      // Show peers as device browser
      renderTailscalePeers(data.peers || []);
    } else {
      tsText.textContent = 'Disconnected';
      tsSub.textContent = data.error || '';
      tsBadge.innerHTML = '<span class="badge badge-red">Disconnected</span>';
      tsUpBtn.disabled = false;
      tsDownBtn.disabled = true;
      tsExitSection.style.display = 'none';
      tsPeersSection.innerHTML = '<div style="text-align:center;padding:32px 0;color:var(--text-3);font-size:13px">Connect to Tailscale to see devices</div>';
    }
  } catch (e) { /* silent */ }
}

function renderTailscalePeers(peers) {
  var el = document.getElementById('ts-peers-list');
  if (!peers || peers.length === 0) {
    el.innerHTML = '<div style="text-align:center;padding:32px 0;color:var(--text-3);font-size:13px">No devices on your Tailscale network</div>';
    return;
  }
  var html = '<div class="row-list">';
  peers.forEach(function(p) {
    var osIcon = p.os === 'linux' ? '&#128241;' : p.os === 'windows' ? '&#128187;' : p.os === 'darwin' ? '&#128187;' : '&#128241;';
    html += '<div class="ts-device">';
    html += '<div class="ts-device-icon">' + osIcon + '</div>';
    html += '<div style="flex:1;min-width:0">';
    html += '<div style="font-size:13px;font-weight:500">' + escapeHtml(p.hostname) + '</div>';
    html += '<div style="font-size:11px;color:var(--text-3);font-family:var(--font-mono)">' + p.ips.join(', ') + '</div>';
    html += '</div>';
    html += '<div class="' + (p.online ? 'ts-device-online' : 'ts-device-offline') + '"></div>';
    html += '</div>';
  });
  html += '</div>';
  el.innerHTML = html;
}

async function tailscaleUp() {
  var authKey = document.getElementById('ts-auth-key').value || null;
  document.getElementById('ts-up-btn').disabled = true;
  try {
    var result = await apiPost('/tailscale/up', { auth_key: authKey });
    if (result.status === 'needs_auth') {
      document.getElementById('ts-login-section').style.display = 'block';
      document.getElementById('ts-login-url').href = result.login_url;
      document.getElementById('ts-login-url').textContent = result.login_url;
      toast('Open the link to authenticate');
    } else if (result.status === 'connected') {
      toast('Connected to Tailscale');
    } else {
      toast(result.message || 'Connection failed');
    }
    await refreshTailscale();
  } catch (err) {
    toast('Error: ' + err.message);
    document.getElementById('ts-up-btn').disabled = false;
  }
}

async function tailscaleDown() {
  try {
    await apiPost('/tailscale/down');
    toast('Disconnected from Tailscale');
    document.getElementById('ts-login-section').style.display = 'none';
    await refreshTailscale();
  } catch (err) {
    toast('Error: ' + err.message);
  }
}

async function setTsExitNode(ip) {
  try {
    await apiPost('/tailscale/set-exit-node', { ip: ip });
    toast(ip ? 'Exit node set' : 'Exit node cleared');
    await refreshTailscale();
  } catch (err) {
    toast('Error: ' + err.message);
  }
}

/* ═══════════════════════════════════════════════
   PAGE: SHORTCUTS
   ═══════════════════════════════════════════════ */
let userShortcuts = [];

registerPage('shortcuts', {
  async show() {
    await loadShortcuts();
    document.getElementById('add-shortcut-form').style.display = 'none';
  }
});

async function loadShortcuts() {
  try {
    var data = await apiGet('/shortcuts');
    userShortcuts = data.shortcuts || [];
  } catch (e) {
    userShortcuts = [];
  }
  renderShortcuts();
}

function renderShortcuts() {
  var el = document.getElementById('shortcuts-list');
  var addBtn = document.getElementById('shortcuts-add-btn');
  if (addBtn) addBtn.style.display = Auth.isAdmin ? 'flex' : 'none';

  if (userShortcuts.length === 0) {
    el.innerHTML = '<div style="text-align:center;padding:32px 0;color:var(--text-3);font-size:13px">No shortcuts yet.' + (Auth.isAdmin ? ' Tap + to add one.' : '') + '</div>';
    return;
  }
  var html = '';
  userShortcuts.forEach(function(s, i) {
    html += '<div class="row" onclick="window.open(\'' + escStr(s.url) + '\', \'_blank\')" style="cursor:pointer">';
    html += '<div style="font-size:24px;width:36px;text-align:center">' + (s.icon || '&#128241;') + '</div>';
    html += '<div class="row-body"><div class="row-title" style="font-size:13px">' + escapeHtml(s.name) + '</div>';
    html += '<div class="row-sub">' + escapeHtml(s.url) + '</div></div>';
    if (Auth.isAdmin) {
      html += '<div class="row-end" style="cursor:pointer" onclick="event.stopPropagation();removeShortcut(' + i + ')">';
      html += '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
      html += '</div>';
    }
    html += '</div>';
  });
  el.innerHTML = html;
}

function showAddShortcut() {
  if (!Auth.isAdmin) { showPage('admin-login'); pendingAdminAction = 'shortcuts'; return; }
  document.getElementById('add-shortcut-form').style.display = 'block';
  document.getElementById('shortcut-name').value = '';
  document.getElementById('shortcut-url').value = '';
  document.getElementById('shortcut-icon').value = '';
  document.getElementById('shortcut-name').focus();
}

function hideAddShortcut() {
  document.getElementById('add-shortcut-form').style.display = 'none';
}

async function saveShortcut() {
  var name = document.getElementById('shortcut-name').value.trim();
  var url = document.getElementById('shortcut-url').value.trim();
  var icon = document.getElementById('shortcut-icon').value.trim();
  if (!name || !url) { toast('Name and URL required'); return; }
  try {
    await apiPost('/shortcuts', { name: name, url: url, icon: icon });
    hideAddShortcut();
    await loadShortcuts();
    toast('Shortcut added');
  } catch (err) {
    toast('Error: ' + err.message);
  }
}

async function removeShortcut(i) {
  if (!Auth.isAdmin) return;
  try {
    await apiDelete('/shortcuts/' + i);
    await loadShortcuts();
    toast('Shortcut removed');
  } catch (err) {
    toast('Error: ' + err.message);
  }
}

/* ═══════════════════════════════════════════════
   PAGE: SETTINGS
   ═══════════════════════════════════════════════ */
registerPage('settings', {
  async show() {
    if (!Auth.isAdmin) { showPage('admin-login'); pendingAdminAction = 'settings'; return; }
    await loadSettings();
  }
});

async function loadSettings() {
  try {
    var data = await apiGet('/settings');
    var e = data.editable || {};
    document.getElementById('set-ssid').value = e.AP_SSID || '';
    document.getElementById('set-passphrase').value = '';
    document.getElementById('set-channel').value = e.AP_CHANNEL || 6;
    document.getElementById('set-country').value = e.AP_COUNTRY_CODE || 'GB';
    document.getElementById('set-tools-only').checked = e.CAPTIVE_PORTAL_TOOLS_ONLY !== false;
  } catch (err) {
    toast('Failed to load settings');
  }
}

async function saveSettings() {
  var updates = {};
  var ssid = document.getElementById('set-ssid').value.trim();
  var pass = document.getElementById('set-passphrase').value;
  var channel = parseInt(document.getElementById('set-channel').value);
  var country = document.getElementById('set-country').value.trim().toUpperCase();
  var toolsOnly = document.getElementById('set-tools-only').checked;

  if (ssid) updates.AP_SSID = ssid;
  if (pass) updates.AP_PASSPHRASE = pass;
  if (channel) updates.AP_CHANNEL = channel;
  if (country) updates.AP_COUNTRY_CODE = country;
  updates.CAPTIVE_PORTAL_TOOLS_ONLY = toolsOnly;

  try {
    var result = await apiPost('/settings', updates);
    toast('Settings saved');
    if (result.needs_ap_restart) {
      document.getElementById('restart-ap-btn').style.display = 'flex';
    }
  } catch (err) {
    toast('Error: ' + err.message);
  }
}

async function restartAp() {
  try {
    await apiPost('/settings/restart-ap');
    toast('AP restarted');
    document.getElementById('restart-ap-btn').style.display = 'none';
  } catch (err) {
    toast('Error: ' + err.message);
  }
}

/* ═══════════════════════════════════════════════
   UPDATE CHECK
   ═══════════════════════════════════════════════ */
async function checkForUpdates() {
  var statusText = document.getElementById('update-status-text');
  var versionText = document.getElementById('update-version-text');
  var badge = document.getElementById('update-badge');

  statusText.textContent = 'Checking...';
  versionText.textContent = '';
  badge.innerHTML = '';

  try {
    var data = await apiGet('/system/update-check');

    if (data.error) {
      statusText.textContent = 'Could not check for updates';
      versionText.textContent = data.error;
      badge.innerHTML = '<span class="badge badge-orange">Error</span>';
      return;
    }

    var local = data.local_version;
    var latest = data.latest_version;

    if (data.update_available) {
      statusText.textContent = 'Update available';
      versionText.textContent = local + ' → ' + latest;
      badge.innerHTML = '<span class="badge badge-green">New</span>';
    } else {
      statusText.textContent = 'Up to date';
      versionText.textContent = 'v' + local;
      badge.innerHTML = '<span class="badge badge-blue">Current</span>';
    }

    if (data.download_url) {
      versionText.textContent += ' — ';
      var link = document.createElement('a');
      link.href = data.download_url;
      link.target = '_blank';
      link.style.color = 'var(--accent)';
      link.textContent = 'Download';
      versionText.appendChild(link);
    }
  } catch (err) {
    statusText.textContent = 'Could not check for updates';
    versionText.textContent = err.message;
    badge.innerHTML = '<span class="badge badge-orange">Error</span>';
  }
}

/* ── Back button SVG injection ──────────────── */
document.querySelectorAll('.back-btn').forEach(btn => {
  btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>';
});

/* ── Startup ────────────────────────────────── */
(function init() {
  if (!Auth.isAdmin) updateAdminUI();
  var wasRedirected = document.referrer && document.referrer.indexOf('http://10.0.0.1:') === 0;
  showPage(wasRedirected ? 'login' : 'home');
})();
