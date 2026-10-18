'use strict';
// DDS AutoDiag dashboard. No inline handlers: the page runs under a strict CSP.

const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const state = {local: null, peer: null, topics: [], selectedTopic: '', sampleTimer: null, sampling: false,
  bt: {events: [], index: 0, timer: null, paused: false}};

const store = {
  get(k) { try { return localStorage.getItem('autodiag.' + k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem('autodiag.' + k, v); } catch { /* storage unavailable */ } },
};

// ---------- helpers ----------
async function api(url, opts = {}) {
  let res;
  try { res = await fetch(url, {credentials: 'same-origin', ...opts}); }
  catch { throw new Error('Cannot reach the AutoDiag server. Is it still running?'); }
  if (res.status === 401) { location.href = '/login'; throw new Error('Sign-in required'); }
  const type = res.headers.get('content-type') || '';
  const body = type.includes('json') ? await res.json() : await res.text();
  if (!res.ok) {
    let detail = body && body.detail;
    if (Array.isArray(detail)) detail = detail.map(d => d.msg).join('; ');
    throw new Error(detail || ('HTTP ' + res.status));
  }
  return body;
}
const post = (url, payload) => api(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});

function toast(message, kind = 'info') {
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.textContent = message;
  $('toasts').appendChild(el);
  setTimeout(() => el.remove(), kind === 'error' ? 8000 : 4000);
}

async function busy(button, fn) {
  if (button) { button.disabled = true; button.dataset.label = button.innerHTML; button.innerHTML = '<span class="spinner"></span>' + button.innerHTML; }
  try { return await fn(); }
  catch (e) { toast(e.message, 'error'); }
  finally { if (button) { button.disabled = false; button.innerHTML = button.dataset.label; } }
}

const loading = text => '<span class="spinner"></span>' + esc(text);

function download(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const a = document.createElement('a');
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const SEVERITY_LABEL = {error: 'Problem', warning: 'Warning', info: 'Note'};
const CHECK_LABEL = {host_collector: 'Collector', ros2_cli: 'ROS 2 CLI', ros2_daemon: 'ROS 2 daemon', ros_graph: 'ROS graph',
  topic_data_flow: 'Topic data flow', application_nodes: 'Application nodes', dds_transport: 'DDS transport', intra_process: 'Intra-process'};
const CHECK_KIND = {ok: 'ok', running: 'ok', unavailable: 'warning', not_sourced: 'error', stopped: 'neutral', unknown: 'neutral',
  not_tested: 'neutral', not_verified: 'neutral'};

function findingHTML(f) {
  const sev = f.severity || 'info';
  const evidence = f.evidence && typeof f.evidence === 'object' && Object.keys(f.evidence).length
    ? '<p class="muted">Evidence: ' + Object.entries(f.evidence).map(([k, v]) => '<code>' + esc(k) + '=' + esc(typeof v === 'object' ? JSON.stringify(v) : v) + '</code>').join(' ') + '</p>'
    : (typeof f.evidence === 'string' && f.evidence ? '<p class="muted">Evidence: ' + esc(f.evidence) + '</p>' : '');
  const docs = (f.documentation || []).map(d => '<a href="' + esc(d.url) + '" target="_blank" rel="noopener noreferrer">' + esc(d.label) + ' docs ↗</a>').join('');
  const action = f.recommended_action || f.next_test || f.recommendation;
  return '<div class="finding ' + esc(sev) + '"><div class="head"><span class="badge ' + esc(sev) + '">' + esc(SEVERITY_LABEL[sev] || sev) + '</span>'
    + '<span class="code">' + esc(f.code) + '</span>' + (f.confidence ? '<small>confidence: ' + esc(f.confidence) + '</small>' : '') + '</div>'
    + '<p>' + esc(f.summary || f.conclusion || f.explanation || '') + '</p>' + evidence
    + (action ? '<p class="next"><b>Next step:</b> ' + esc(action) + '</p>' : '')
    + (docs ? '<div class="docs">' + docs + '</div>' : '') + '</div>';
}

function findingsHTML(issues, emptyText) {
  if (!issues || !issues.length) return '<div class="finding ok"><div class="head"><span class="badge ok">No rule matched</span></div><p>' + esc(emptyText || 'No configured rule detected a problem. This is not proof that messages are delivered; read a live sample to confirm.') + '</p></div>';
  return issues.map(findingHTML).join('');
}

function metric(label, value) {
  return '<div class="metric"><div class="label">' + esc(label) + '</div><div class="value">' + esc(value ?? '—') + '</div></div>';
}

function setBanner(health) {
  const errors = health.status === 'issue_detected';
  const cls = errors ? 'error' : health.status === 'healthy' ? 'ok' : 'warning';
  const title = errors ? 'Configuration problem found' : health.status === 'healthy' ? 'No problems detected' : 'No confirmed problems — data flow not yet verified';
  const text = errors ? 'See the findings below for what to fix first.' : 'Configuration looks consistent. Inspect a topic and read a live sample to confirm delivery.';
  $('banner').className = 'status ' + cls;
  $('banner').innerHTML = '<span class="dot"></span><div><b>' + esc(title) + '</b><span class="muted">' + esc(text) + '</span></div>';
}

// ---------- event log: every check lands here, newest first ----------
const EVENT_LEVEL = {error: 'ERROR', warning: 'WARN', info: 'NOTE', ok: 'OK', waiting: 'WAIT'};
const events = [];

function logEvents(items) {
  const tm = new Date().toLocaleTimeString([], {hour12: false});
  events.unshift(...items.map(x => ({tm, ...x})));
  events.length = Math.min(events.length, 200);
  $('events-count').textContent = events.length + (events.length === 1 ? ' entry' : ' entries');
  $('events').innerHTML = events.map((e, i) => '<div class="ev"' + (e.topic || e.tab ? ' data-go="' + i + '" tabindex="0" role="button"' : '') + '>'
    + '<span class="tm">' + esc(e.tm) + '</span><span class="lvl ' + esc(e.level) + '">' + esc(EVENT_LEVEL[e.level] || e.level) + '</span>'
    + '<span class="tgt">' + esc(e.target || '') + '</span><span class="what">' + esc(e.what || '') + '</span>'
    + '<span class="who">' + esc(e.who || '') + '</span></div>').join('');
}

function findingEvents(issues, fallbackTarget, okText) {
  if (!issues || !issues.length) return [{level: 'ok', target: fallbackTarget, what: okText, tab: 'overview'}];
  return issues.map(f => {
    const ev = f.evidence && typeof f.evidence === 'object' ? f.evidence : {};
    const topic = ev.topic || '';
    return {level: f.severity || 'info', target: topic || fallbackTarget, what: f.code,
      who: ev.publisher && ev.subscriber ? ev.publisher + ' → ' + ev.subscriber : (f.summary || '').slice(0, 80),
      topic, tab: topic ? '' : 'overview'};
  });
}

function setEventsOpen(open) {
  $('events-strip').classList.toggle('collapsed', !open);
  $('events-toggle').textContent = open ? 'Hide' : 'Show';
  $('events-toggle').setAttribute('aria-expanded', String(open));
  store.set('events', open ? 'open' : 'closed');
}

// ---------- status bar ----------
function setStatusBar(o) {
  const s = o.summary, rmw = o.capabilities.rmw;
  const chip = (k, v) => '<span class="chip">' + esc(k) + ' <b>' + esc(v ?? '—') + '</b></span>';
  $('status-chips').innerHTML = chip('DOMAIN', s.domain_id) + chip('RMW', rmw.effective || s.rmw || 'default')
    + chip('DISTRO', s.ros_distro || 'not sourced') + chip('NODES', s.node_count) + chip('TOPICS', s.topic_count);
  const count = sev => o.issues.filter(i => i.severity === sev).length;
  alarms.host = {error: count('error'), warning: count('warning'), healthy: o.health.status === 'healthy'};
  renderAlarms();
  $('alert-overview').hidden = !alarms.host.error;
  $('host-tag').innerHTML = esc(s.host || 'this host') + ' · checked <span id="checked-at">' + esc(new Date().toLocaleTimeString([], {hour12: false})) + '</span>';
}

// Problems found anywhere (host checks, the graph) add up in the status bar; each alarm opens where most of them are.
const alarms = {host: null, graph: null};
function renderAlarms() {
  const h = alarms.host || {error: 0, warning: 0}, g = alarms.graph || {error: 0, warning: 0};
  const chip = (sev, n, word) => {
    const tab = g[sev] > h[sev] ? 'graph' : 'overview';
    return '<a class="alarm ' + sev + '" href="#' + tab + '" data-tab-link="' + tab + '">' + n + ' ' + word + (n === 1 ? '' : 'S') + '</a>';
  };
  const errors = h.error + g.error, warnings = h.warning + g.warning;
  $('alarms').innerHTML = (errors ? chip('error', errors, 'PROBLEM') : '') + (warnings ? chip('warning', warnings, 'WARNING') : '')
    + (errors || warnings ? '' : '<span class="alarm neutral">NO RULE MATCHED</span>');
  $('health-dot').className = 'health ' + (errors ? 'error' : warnings || !(alarms.host && alarms.host.healthy) ? 'warning' : 'ok');
}

// ---------- navigation ----------
const TITLES = {overview: 'System overview', topics: 'Topic inspector', graph: 'Who talks to whom', environments: 'Compare hosts & containers',
  diagnose: 'Transport diagnosis', assistant: 'Diagnostic assistant', tools: 'Tools & self-test', about: 'About & settings'};
const EYEBROWS = {overview: 'Health · this host', topics: 'Topics · live discovery', graph: 'Graph · live discovery', environments: 'Hosts · compare',
  diagnose: 'Transport · checks', assistant: 'Assistant · docs + AI', tools: 'Tools', about: 'Settings'};
const loaded = new Set();

function showTab(tab) {
  if (!TITLES[tab]) tab = 'overview';
  document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id === tab));
  document.querySelectorAll('.nav a').forEach(a => {
    const on = a.dataset.tab === tab;
    a.classList.toggle('active', on);
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  $('page-title').textContent = TITLES[tab];
  $('page-eyebrow').textContent = EYEBROWS[tab];
  if (location.hash.slice(1) !== tab) history.replaceState(null, '', '#' + tab);
  if (!loaded.has(tab)) {
    loaded.add(tab);
    if (tab === 'topics') loadTopics();
    if (tab === 'graph') loadGraph();
    if (tab === 'environments') loadDocker();
    if (tab === 'about') { loadAbout(); loadProviders(); }
  }
  if (tab === 'assistant') loadOllama();
}

// ---------- overview ----------
async function refresh(button) {
  await busy(button, async () => {
    const o = await api('/api/v09/overview');
    state.local = o.snapshot;
    const s = o.summary, rmw = o.capabilities.rmw, shm = o.capabilities.shm;
    setBanner(o.health);
    setStatusBar(o);
    logEvents(findingEvents(o.issues, 'host', 'host checks: no rule matched'));
    $('version-tag').textContent = 'v' + o.version;
    $('metrics').innerHTML = metric('Host', s.host) + metric('ROS distro', s.ros_distro || 'not sourced')
      + metric('Domain ID', s.domain_id) + metric('RMW', rmw.effective || s.rmw || 'default')
      + metric('Discovery range', s.discovery_range || 'default (SUBNET)')
      + metric('Nodes visible', s.node_count ?? '—') + metric('Topics visible', s.topic_count ?? '—')
      + metric('Running in container', s.container ? 'yes' : 'no');
    const errors = o.issues.filter(i => i.severity === 'error').length;
    $('finding-count').textContent = o.issues.length ? o.issues.length + ' finding(s), ' + errors + ' problem(s)' : '';
    $('overview-findings').className = '';
    $('overview-findings').innerHTML = findingsHTML(o.issues);
    $('checks').innerHTML = Object.entries(o.health.checks).map(([k, v]) =>
      '<div class="check-row"><span>' + esc(CHECK_LABEL[k] || k) + '</span><span class="badge ' + (CHECK_KIND[v] || 'neutral') + '">' + esc(String(v).replace(/_/g, ' ')) + '</span></div>').join('');
    $('rmw').className = '';
    $('rmw').innerHTML = '<p><b>Detected:</b> ' + esc(rmw.effective || 'unknown') + '<br><b>Configured (RMW_IMPLEMENTATION):</b> ' + esc(rmw.configured || 'not set — distro default') + '</p>'
      + '<p class="muted">Source: ' + esc(rmw.method) + '. Scope: ' + esc(rmw.scope) + '. Individual nodes may override this.</p>';
    $('shm-summary').className = '';
    $('shm-summary').innerHTML = '<table><tbody>' + shm.observations.map(x => '<tr><td>' + esc(x.name) + '</td><td>' + esc(x.detail) + '</td></tr>').join('') + '</tbody></table>';
  });
  if (!state.local) {
    $('banner').className = 'status error';
    $('banner').innerHTML = '<span class="dot"></span><div><b>Could not collect diagnostics</b><span class="muted">Check that the AutoDiag server is running, then press Refresh.</span></div>';
  }
}

async function exportSnapshot(button) {
  await busy(button, async () => {
    const redact = $('redact-export').checked;
    const snap = await api('/api/snapshot' + (redact ? '?redact=true' : ''));
    download('dds-autodiag-snapshot' + (redact ? '-redacted' : '') + '.json', JSON.stringify(snap, null, 2), 'application/json');
    toast(redact ? 'Redacted snapshot downloaded' : 'Snapshot downloaded (contains hostnames and IPs)', 'ok');
  });
}

async function downloadReport(button) {
  if (!state.local) return toast('Wait for the overview to finish loading', 'error');
  await busy(button, async () => {
    const text = await post('/api/report', {host_a: withMode(state.local), host_b: state.peer});
    download('dds-autodiag-report.md', text, 'text/markdown');
    toast('Report downloaded', 'ok');
  });
}

function withMode(snapshot) {
  const s = structuredClone(snapshot);
  s.transport = {...(s.transport || {}), requested_mode: $('mode').value};
  return s;
}

// ---------- topics ----------
async function loadTopics(button) {
  $('topic-rows').innerHTML = '<tr><td colspan="2">' + loading('Querying the ROS graph…') + '</td></tr>';
  await busy(button, async () => {
    const o = await api('/api/topics');
    state.topics = o.topics || [];
    if (o.state !== 'ok') {
      $('topic-rows').innerHTML = '<tr><td colspan="2"><div class="notice error">' + esc(o.error || o.state) + '</div></td></tr>';
      return;
    }
    renderTopics();
  });
}

function renderTopics() {
  const q = $('topic-filter').value.trim().toLowerCase();
  const rows = state.topics.filter(t => !q || t.topic.toLowerCase().includes(q) || t.type.toLowerCase().includes(q));
  $('topic-count').textContent = rows.length + ' of ' + state.topics.length + ' topics';
  $('topic-rows').innerHTML = rows.length ? rows.map(t =>
    '<tr class="selectable' + (t.topic === state.selectedTopic ? ' selected' : '') + '" tabindex="0" data-topic="' + esc(t.topic) + '"><td class="mono">' + esc(t.topic) + '</td><td class="mono muted">' + esc(t.type) + '</td></tr>').join('')
    : '<tr><td colspan="2" class="muted">' + (state.topics.length ? 'No topic matches the filter.' : 'No topics discovered. Are your nodes running on this ROS_DOMAIN_ID?') + '</td></tr>';
}

function selectTopic(topic) {
  state.selectedTopic = topic;
  stopSamples();
  const t = state.topics.find(x => x.topic === topic);
  $('selected-topic').innerHTML = '<b class="mono">' + esc(topic) + '</b>' + (t ? ' <span class="muted">' + esc(t.type) + '</span>' : '');
  renderTopics();
  inspectTopic();
}

async function inspectTopic(button) {
  const topic = state.selectedTopic;
  if (!topic) return toast('Select a topic first');
  $('topic-findings').innerHTML = loading('Inspecting endpoints…');
  $('endpoint-table').innerHTML = '';
  await busy(button, async () => {
    const o = await api('/api/topic-inspect?topic=' + encodeURIComponent(topic));
    $('topic-result').textContent = JSON.stringify(o, null, 2);
    if (o.state !== 'ok') { $('topic-findings').innerHTML = '<div class="notice error">' + esc(o.error || o.state) + '</div>'; return; }
    logEvents(o.findings.length ? findingEvents(o.findings, topic).map(e => ({...e, target: topic, topic}))
      : [{level: o.publisher_count ? 'ok' : 'waiting', target: topic, topic,
        what: o.publisher_count ? 'advertised QoS compatible' : 'no publisher visible',
        who: o.publisher_count + ' pub · ' + o.subscriber_count + ' sub'}]);
    $('topic-findings').innerHTML = '<p class="muted">' + o.publisher_count + ' publisher(s), ' + o.subscriber_count + ' subscriber(s)</p>'
      + (o.findings.length ? o.findings.map(findingHTML).join('') : '<div class="finding ok"><p>Advertised QoS is compatible. Delivery is not verified until you read a sample.</p></div>')
      + (o.publisher_count === 0 ? '<div class="notice warning">No publisher is visible on this topic from here.</div>' : '');
    $('endpoint-table').innerHTML = o.endpoints.length ? '<div class="table-wrap"><table><thead><tr><th>Role</th><th>Node</th><th>Reliability</th><th>Durability</th><th>History</th></tr></thead><tbody>'
      + o.endpoints.map(e => '<tr><td>' + esc(e.kind) + '</td><td class="mono">' + esc(e.node) + '</td><td>' + esc(e.qos.reliability) + '</td><td>' + esc(e.qos.durability) + '</td><td>' + esc(e.qos.history) + '</td></tr>').join('')
      + '</tbody></table></div>' : '';
  });
}

async function readSample() {
  const topic = state.selectedTopic;
  if (!topic) return toast('Select a topic first');
  if (state.sampling) return;
  state.sampling = true;
  const timeout = $('sample-timeout').value;
  $('sample-result').textContent = 'Waiting up to ' + timeout + ' s for one message on ' + topic + '…';
  try {
    const o = await api('/api/topic-sample?topic=' + encodeURIComponent(topic) + '&timeout=' + timeout + '&reliability=' + encodeURIComponent($('probe').value));
    $('sample-result').textContent = o.state === 'ok'
      ? '[' + new Date().toLocaleTimeString() + ']\n' + (o.raw || '(empty message)') + (o.truncated ? '\n[truncated]' : '')
      : (o.state === 'timeout' ? 'No message within ' + timeout + ' s. The publisher may be idle, or QoS/transport may block delivery. Try the other reliability setting.' : 'No sample: ' + (o.error || o.state));
  } catch (e) { $('sample-result').textContent = e.message; stopSamples(); }
  finally { state.sampling = false; }
}

function stopSamples() {
  if (state.sampleTimer) clearInterval(state.sampleTimer);
  state.sampleTimer = null;
  $('auto-samples').checked = false;
}

// ---------- environments / compare ----------
async function loadDocker(button) {
  $('docker-results').innerHTML = loading('Scanning…');
  await busy(button, async () => {
    const d = await api('/api/v09/environments');
    if (d.state !== 'ok') { $('docker-results').innerHTML = '<div class="notice warning">' + esc(d.reason) + '</div>'; return; }
    if (!d.environments.length) { $('docker-results').innerHTML = '<p class="muted">No running containers.</p>'; return; }
    $('docker-results').innerHTML = '<div class="table-wrap"><table><thead><tr><th>Container</th><th>Image</th><th>Network</th><th>Collect snapshot</th></tr></thead><tbody>'
      + d.environments.map(c => '<tr><td><b>' + esc(c.name) + '</b><br><small>' + esc(c.status) + '</small></td><td class="mono"><small>' + esc(c.image) + '</small></td><td>' + esc(c.network) + '</td>'
        + '<td><code>docker exec ' + esc(c.name) + ' bash -lc "dds-autodiag collect" &gt; ' + esc(c.name) + '.json</code></td></tr>').join('')
      + '</tbody></table></div><p class="muted">' + esc(d.reason) + ' AutoDiag must be installed in the container for the collect command.</p>';
  });
}

function renderComparison(o, label) {
  const a = o.summary_a || {}, b = o.summary_b || {};
  const rows = [['Host', 'host'], ['ROS distro', 'ros_distro'], ['Domain ID', 'domain_id'], ['RMW', 'rmw'], ['Discovery range', 'discovery_range'],
    ['Container', 'container'], ['Nodes visible', 'node_count'], ['Topics visible', 'topic_count']];
  const fmt = v => v === true ? 'yes' : v === false ? 'no' : (v ?? '—');
  const val = (sum, k) => fmt(sum[k] ?? (['rmw', 'discovery_range'].includes(k) ? 'default' : null));
  const table = '<div class="table-wrap"><table><thead><tr><th></th><th>This host</th><th>' + esc(label) + '</th></tr></thead><tbody>'
    + rows.map(([l, k]) => '<tr' + (['domain_id', 'rmw', 'ros_distro', 'discovery_range'].includes(k) && String(val(a, k)) !== String(val(b, k)) ? ' class="diff"' : '') + '><td>' + esc(l) + '</td><td>' + esc(val(a, k)) + '</td><td>' + esc(val(b, k)) + '</td></tr>').join('')
    + '</tbody></table></div>';
  $('remote-results').className = '';
  $('remote-results').innerHTML = table + '<h3>Findings</h3>' + findingsHTML(o.issues);
}

async function compareWith(peer, label, button) {
  if (!state.local) return toast('Wait for the overview to finish loading', 'error');
  await busy(button, async () => {
    const o = await post('/api/compare', {host_a: withMode(state.local), host_b: peer});
    state.peer = peer;
    renderComparison(o, label);
    toast('Comparison updated', 'ok');
  });
}

function parseSnapshot(text) {
  let data;
  try { data = JSON.parse(text); } catch { throw new Error('That is not valid JSON.'); }
  if (!data || typeof data !== 'object' || !data.environment) throw new Error('This JSON does not look like an AutoDiag snapshot (no "environment" field).');
  return data;
}

async function compareSnapshot(button) {
  try {
    const file = $('snapshot-file').files[0];
    const text = file ? await file.text() : $('snapshot-input').value;
    if (!text.trim()) return toast('Choose a snapshot file or paste JSON', 'error');
    const peer = parseSnapshot(text);
    await compareWith(peer, (peer.identity && peer.identity.host) || 'Peer snapshot', button);
  } catch (e) { toast(e.message, 'error'); }
}

async function compareRemote(button) {
  if (!state.local) return toast('Wait for the overview to finish loading', 'error');
  const url = $('remoteUrl').value.trim();
  if (!url) return toast('Enter the collector URL', 'error');
  store.set('remoteUrl', url);
  await busy(button, async () => {
    const o = await post('/api/remote-compare', {url, token: $('remoteToken').value, host_a: withMode(state.local)});
    state.peer = o.remote;
    renderComparison(o, (o.remote.identity && o.remote.identity.host) || 'Remote');
    toast('Connected to remote collector', 'ok');
  });
}

// ---------- transport ----------
async function runDiagnostic(button) {
  if (!state.local) return toast('Wait for the overview to finish loading', 'error');
  $('diagnostic-results').innerHTML = loading('Running checks…');
  await busy(button, async () => {
    const o = await post('/api/compare', {host_a: withMode(state.local), host_b: state.peer});
    let html = '<p class="muted">' + (state.peer ? 'Compared with the loaded peer.' : 'Single-host checks only. Load a peer in “Compare hosts” for cross-host rules.') + '</p>' + findingsHTML(o.issues);
    if ($('mode').value === 'dds_shm') {
      const shm = await api('/api/v09/shm');
      html += '<h3>Shared-memory prerequisites (this host)</h3><table><tbody>' + shm.observations.map(x => '<tr><td>' + esc(x.name) + '</td><td><span class="badge ' + (x.result === 'pass' ? 'ok' : x.result === 'warning' ? 'warning' : 'neutral') + '">' + esc(x.result) + '</span></td><td>' + esc(x.detail) + '</td></tr>').join('') + '</tbody></table>'
        + '<p class="hint">' + esc(shm.summary) + ' ' + esc(shm.recommended_next_test) + '</p>'
        + shm.documentation.map(d => '<a href="' + esc(d.url) + '" target="_blank" rel="noopener noreferrer">' + esc(d.label) + ' ↗</a>').join(' · ');
    }
    $('diagnostic-results').className = '';
    $('diagnostic-results').innerHTML = html;
  });
}

// ---------- assistant ----------
let aiAbort = null;

// Small, safe Markdown subset for model answers: text is escaped first, then formatted.
let aiSources = {};

function renderMarkdown(text) {
  // [doc-id] citations become links to the curated documentation; unknown ids stay plain text.
  const cite = s => s.replace(/\[([a-z0-9-]+)\]/g, (m, id) => aiSources[id]
    ? '<a href="' + esc(aiSources[id].url) + '" target="_blank" rel="noopener noreferrer">' + esc(aiSources[id].title) + ' ↗</a>' : m);
  const inline = s => cite(esc(s))
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/(^|[\s(])\*([^*\s][^*]*)\*/g, '$1<i>$2</i>');
  const out = [];
  let list = false, code = false, codeLines = [];
  for (const line of text.split('\n')) {
    if (line.trim().startsWith('```')) {
      if (code) { out.push('<pre>' + esc(codeLines.join('\n')) + '</pre>'); codeLines = []; }
      code = !code; continue;
    }
    if (code) { codeLines.push(line); continue; }
    const bullet = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
    if (bullet) { if (!list) { out.push('<ul>'); list = true; } out.push('<li>' + inline(bullet[1]) + '</li>'); continue; }
    if (list) { out.push('</ul>'); list = false; }
    const heading = line.match(/^#{1,4}\s+(.*)$/);
    if (heading) out.push('<h3>' + inline(heading[1]) + '</h3>');
    else if (line.trim()) out.push('<p>' + inline(line) + '</p>');
  }
  if (code) out.push('<pre>' + esc(codeLines.join('\n')) + '</pre>');
  if (list) out.push('</ul>');
  return out.join('');
}

async function loadOllama() {
  try {
    const [o, p] = await Promise.all([api('/api/v09/ollama'), api('/api/ai/providers')]);
    const select = $('ai-provider');
    const previous = select.value || store.get('aiProvider') || p.default;
    select.innerHTML = p.providers.map(x => '<option value="' + esc(x.id) + '"' + (x.ready ? '' : ' disabled') + '>'
      + esc(x.label.replace(/ \(.*\)$/, '')) + (x.ready ? '' : ' (not set up)') + '</option>').join('');
    const usable = p.providers.find(x => x.id === previous && x.ready) ? previous : p.default;
    select.value = usable;
    updatePrivacyNote(p.providers);
    fillAssistantModels();
    let help = '';
    if (o.state === 'model_missing') help = ' Run <code>ollama pull ' + esc(o.expected_model) + '</code>.';
    if (o.state === 'unreachable') help = ' Start it with <code>ollama serve</code>, or link a cloud provider in <a href="#about" data-tab-link="about">About &amp; settings</a>.';
    $('ollama').className = o.state === 'ready' ? 'notice ok' : 'notice warning';
    $('ollama').innerHTML = '<b>Local AI:</b> ' + esc(o.message) + '.' + help
      + ' <span class="muted">Cloud providers linked: ' + (p.providers.filter(x => x.cloud && x.ready).map(x => esc(x.label)).join(', ') || 'none') + '.</span>';
    if (o.state === 'ready' && $('ai-provider').value === 'ollama') api('/api/ai/warmup', {method: 'POST'}).catch(() => {});
  } catch (e) { $('ollama').textContent = 'AI status unavailable: ' + e.message; }
}

function updatePrivacyNote(providers) {
  const chosen = (providers || []).find(x => x.id === $('ai-provider').value);
  $('ai-privacy').textContent = chosen && chosen.cloud
    ? 'Sends finding codes and summaries, your question and documentation excerpts to ' + chosen.label + '. Snapshots, hostnames and IPs are not sent.'
    : 'Runs on this machine. Nothing leaves it.';
}

// Fill a <select> with the provider's models (live list when available). Returns the API response.
async function fillModelSelect(provider, select, current, withOther) {
  select.innerHTML = '<option value="">Loading models…</option>';
  let r;
  try { r = await api('/api/ai/providers/' + encodeURIComponent(provider) + '/models'); }
  catch (e) { r = {models: [], source: 'error', message: e.message}; }
  const chosen = current || r.current || '';
  const models = r.models.includes(chosen) || !chosen ? r.models : [chosen, ...r.models];
  select.innerHTML = models.map(m => '<option value="' + esc(m) + '">' + esc(m) + '</option>').join('')
    + (withOther ? '<option value="__other">Other… (type a name)</option>' : '');
  select.value = chosen && models.includes(chosen) ? chosen : (models[0] || (withOther ? '__other' : ''));
  return r;
}

let modelFill = 0, modelFillProvider = null;
async function fillAssistantModels() {
  const provider = $('ai-provider').value;
  // Keep what the user picked if this provider's list is just being refreshed.
  const keep = modelFillProvider === provider ? $('ai-model').value : null;
  const wanted = keep || store.get('aiModel.' + provider);
  const seq = ++modelFill;
  const scratch = document.createElement('select');
  await fillModelSelect(provider, scratch, wanted, false);
  if (seq !== modelFill) return;  // a newer refresh superseded this one
  $('ai-model').innerHTML = scratch.innerHTML;
  $('ai-model').value = scratch.value;
  modelFillProvider = provider;
}

async function ask(button, useAI) {
  if (!state.local) {  // asked before the first snapshot arrived: collect it, then continue
    $('ai-results').innerHTML = loading('Collecting this machine\'s ROS 2 information first…');
    await refresh();
    if (!state.local) return toast('Could not collect diagnostics; check the server', 'error');
  }
  if (aiAbort) aiAbort.abort();
  const box = $('ai-results'), answer = $('ai-answer');
  box.className = ''; answer.innerHTML = '';
  if (!useAI) {
    box.innerHTML = loading('Searching documentation…');
    await busy(button, async () => {
      const o = await post('/api/v06/explain', {host_a: withMode(state.local), host_b: state.peer, question: $('question').value,
        semantic_search: $('semantic').checked, use_local_ai: false});
      renderContext(o);
    });
    return;
  }
  const provider = $('ai-provider').value;
  store.set('aiProvider', provider);
  aiAbort = new AbortController();
  $('stop-ai').hidden = false; button.disabled = true;
  answer.innerHTML = '<div class="ai-answer"><div class="ai-head muted">' + loading('Connecting…') + '</div><div class="ai-body"></div></div>';
  box.innerHTML = '';
  const head = answer.querySelector('.ai-head'), body = answer.querySelector('.ai-body');
  let text = '', meta = null, pending = false;
  const paint = () => { pending = false; body.innerHTML = renderMarkdown(text); };
  try {
    const res = await fetch('/api/assistant/stream', {method: 'POST', credentials: 'same-origin', signal: aiAbort.signal,
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({host_a: withMode(state.local), host_b: state.peer, question: $('question').value,
        provider, model: $('ai-model').value || null, semantic_search: $('semantic').checked, topics_from_question: true})});
    if (res.status === 401) { location.href = '/login'; return; }
    if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || 'HTTP ' + res.status); }
    const reader = res.body.getReader(), decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      let nl;
      while ((nl = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, nl); buffer = buffer.slice(nl + 1);
        if (!line.trim()) continue;
        const ev = JSON.parse(line);
        if (ev.type === 'context') { aiSources = Object.fromEntries((ev.sources || []).map(x => [x.id, x])); renderContext(ev); }
        else if (ev.type === 'meta') { meta = ev; head.innerHTML = loading(ev.label + ' · ' + ev.model + ' is writing…'); }
        else if (ev.type === 'thinking') head.innerHTML = loading(meta.model + ' is reasoning before it answers… (' + ev.chars + ' characters so far)');
        else if (ev.type === 'token') {
          text += ev.text;
          if (!pending) { pending = true; requestAnimationFrame(paint); }
        } else if (ev.type === 'done') {
          paint();
          head.innerHTML = '<b>' + esc(meta ? meta.label : 'AI') + '</b> <small class="muted">' + esc(meta ? meta.model : '')
            + ' · first words after ' + esc(ev.first_token_seconds ?? '–') + ' s · done in ' + esc(ev.seconds) + ' s · unverified, trust the findings first</small>';
        } else if (ev.type === 'error') {
          paint();
          head.innerHTML = '<div class="notice error">' + esc(ev.message) + '</div>';
        }
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') head.innerHTML = '<small class="muted">Stopped.</small>';
    else head.innerHTML = '<div class="notice error">' + esc(e.message) + '</div>';
  } finally {
    aiAbort = null; $('stop-ai').hidden = true; button.disabled = false;
  }
}

function renderContext(o) {
  let html = (o.topics || []).length ? '<p class="muted">Included the live endpoints and QoS of ' + o.topics.map(t => '<code>' + esc(t) + '</code>').join(', ') + ' (named in your question).</p>' : '';
  html += '<h3>Relevant documentation <small>(' + esc(o.retrieval_mode) + (o.retrieval_note ? ', ' + esc(o.retrieval_note) : '') + ')</small></h3>';
  html += (o.sources || []).length ? o.sources.map(s => '<div class="finding info"><a href="' + esc(s.url) + '" target="_blank" rel="noopener noreferrer"><b>' + esc(s.title) + '</b> ↗</a> <small class="muted">[' + esc(s.id) + ']</small><p class="muted">' + esc(s.excerpt) + '</p></div>').join('')
    : '<p class="muted">No matching documentation. Try describing the symptom in different words.</p>';
  if (o.issues && o.issues.length) html += '<details><summary>Findings used as context (' + o.issues.length + ')</summary>' + o.issues.map(findingHTML).join('') + '</details>';
  $('ai-results').className = '';
  $('ai-results').innerHTML = html;
}

// ---------- AI provider settings ----------
async function loadProviders() {
  try {
    const p = await api('/api/ai/providers');
    $('ai-config-file').textContent = 'Saved in ' + p.config_file;
    $('ai-providers').className = 'providers';
    $('ai-providers').innerHTML = p.providers.map(x => {
      const status = x.ready ? '<span class="badge ok">ready</span>' : (x.key_source === 'sdk_missing'
        ? '<span class="badge warning">install anthropic SDK</span>' : '<span class="badge neutral">not set up</span>');
      const key = x.needs_key
        ? '<label class="field"><span>API key ' + (x.key_configured ? '(linked ' + esc(x.key_hint) + (x.key_source && x.key_source.startsWith('env:') ? ', from ' + esc(x.key_source.slice(4)) : '') + ')' : '') + '</span>'
          + '<input type="password" autocomplete="off" data-prov="' + esc(x.id) + '" name="api_key" placeholder="' + (x.key_configured ? 'Leave empty to keep the current key' : 'Paste API key') + '"></label>' : '';
      return '<div class="provider" data-provider="' + esc(x.id) + '"><div class="card-head"><h3>' + esc(x.label) + '</h3>' + status
        + (p.default === x.id ? ' <span class="badge info">default</span>' : '') + '</div>' + key
        + (x.needs_base_url ? '<label class="field"><span>Base URL</span><input data-prov="' + esc(x.id) + '" name="base_url" value="' + esc(x.base_url || '') + '" placeholder="https://api.groq.com/openai/v1"></label>' : '')
        + '<label class="field"><span>Model <button type="button" class="link" data-action="prov-models" data-id="' + esc(x.id) + '" title="Reload the model list">↻ refresh</button></span>'
        + '<select data-model-for="' + esc(x.id) + '" aria-label="Model"></select>'
        + '<input data-prov="' + esc(x.id) + '" name="model" value="' + esc(x.model) + '" placeholder="Type a model name" hidden></label>'
        + '<small class="muted model-source"></small>'
        + '<div class="actions tight"><button type="button" class="primary" data-action="prov-save" data-id="' + esc(x.id) + '">Save</button>'
        + '<button type="button" data-action="prov-test" data-id="' + esc(x.id) + '">Test</button>'
        + '<button type="button" data-action="prov-default" data-id="' + esc(x.id) + '">Make default</button>'
        + (x.needs_key && x.key_configured && x.key_source === 'saved' ? '<button type="button" data-action="prov-remove" data-id="' + esc(x.id) + '">Remove key</button>' : '')
        + (x.key_url ? ' <a href="' + esc(x.key_url) + '" target="_blank" rel="noopener noreferrer">Get a key ↗</a>' : '') + '</div>'
        + '<p class="muted prov-result"></p></div>';
    }).join('');
    p.providers.forEach(x => loadProviderModels(x.id, x.model));
  } catch (e) { $('ai-providers').textContent = 'Could not load providers: ' + e.message; }
}

async function loadProviderModels(id, current, refresh) {
  const card = document.querySelector('.provider[data-provider="' + id + '"]');
  if (!card) return;
  const select = card.querySelector('[data-model-for]'), input = card.querySelector('input[name=model]');
  if (refresh) await api('/api/ai/providers/' + encodeURIComponent(id) + '/models?refresh=true').catch(() => {});
  const r = await fillModelSelect(id, select, current || input.value, true);
  input.hidden = select.value !== '__other';
  if (select.value !== '__other') input.value = select.value;
  card.querySelector('.model-source').textContent = r.source === 'live'
    ? r.models.length + ' models available from ' + (id === 'ollama' ? 'your Ollama install' : 'your account') + '.'
    : 'Suggested models. ' + (r.message || '');
}

function providerForm(id) {
  const out = {};
  document.querySelectorAll('[data-prov="' + id + '"]').forEach(el => { out[el.name] = el.value.trim(); });
  if (!out.api_key) delete out.api_key;  // empty = keep the saved key
  return out;
}

async function saveProvider(button, extra = {}) {
  const id = button.dataset.id;
  await busy(button, async () => {
    await api('/api/ai/providers/' + encodeURIComponent(id), {method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({...providerForm(id), ...extra})});
    toast(extra.make_default ? 'Default AI provider updated' : 'Saved', 'ok');
    await loadProviders(); loadOllama();
  });
}

async function testProvider(button) {
  const id = button.dataset.id;
  const out = button.closest('.provider').querySelector('.prov-result');
  out.innerHTML = loading('Testing…');
  await busy(button, async () => {
    const r = await api('/api/ai/providers/' + encodeURIComponent(id) + '/test', {method: 'POST'});
    out.innerHTML = r.ok ? '<span class="badge ok">works</span> replied “' + esc(r.reply) + '” in ' + esc(r.seconds) + ' s'
      : '<span class="badge error">failed</span> ' + esc(r.message);
  });
}

async function removeKey(button) {
  await busy(button, async () => {
    await api('/api/ai/providers/' + encodeURIComponent(button.dataset.id) + '/key', {method: 'DELETE'});
    toast('API key removed', 'ok');
    await loadProviders(); loadOllama();
  });
}

// ---------- tools ----------
async function selftest(button) {
  await busy(button, async () => {
    const o = await api('/api/selftest');
    $('selftest-results').innerHTML = '<div class="notice ' + (o.ok ? 'ok' : 'error') + '"><b>' + o.passed + ' of ' + o.total + ' rules passed.</b></div>'
      + '<div class="table-wrap"><table><thead><tr><th>Scenario</th><th>Expected rule</th><th>Result</th></tr></thead><tbody>'
      + o.results.map(r => '<tr><td>' + esc(r.description) + '</td><td class="mono">' + esc(r.expected_code || '(none)') + '</td><td><span class="badge ' + (r.passed ? 'ok' : 'error') + '">' + (r.passed ? 'pass' : 'fail') + '</span></td></tr>').join('')
      + '</tbody></table></div>';
  });
}

function endpointValues(role) {
  const out = {};
  document.querySelectorAll('[data-ep="' + role + '"]').forEach(el => { out[el.name] = el.value.trim(); });
  return out;
}

async function endpointCheck(button) {
  await busy(button, async () => {
    const o = await post('/api/endpoint-check', {publisher: endpointValues('publisher'), subscriber: endpointValues('subscriber')});
    $('endpoint-results').innerHTML = '<p class="muted">Engine: ' + esc(o.engine) + '. Checks the described configuration only.</p>'
      + findingsHTML(o.findings, 'The described publisher and subscriber are compatible for the supported checks.');
  });
}

function btClear() {
  const bt = state.bt;
  if (bt.timer) clearTimeout(bt.timer);
  bt.timer = null; bt.index = 0; bt.paused = false;
  $('btPause').textContent = 'Pause';
  ['collect', 'qos', 'report'].forEach(x => { $('bt-' + x).className = 'bt-step'; $('bt-' + x).querySelector('small').textContent = 'IDLE'; });
  $('log').textContent = '';
}

async function runBT(button, fault) {
  btClear();
  await busy(button, async () => {
    const o = await api('/api/v08/bt/run?fault=' + fault, {method: 'POST'});
    state.bt.events = o.events || [];
    $('bt-origin').textContent = o.source === 'native' ? 'Native BehaviorTree.CPP trace on sample data (not live ROS 2)'
      : o.source === 'simulated' ? 'Simulated trace — build the C++ core with BehaviorTree.CPP for a native run' : 'Runner error: ' + o.warning;
    tickBT();
  });
}

function tickBT() {
  const bt = state.bt;
  if (bt.paused || bt.index >= bt.events.length) return;
  const e = bt.events[bt.index++];
  if (e.event === 'bt_transition' && ['collect', 'qos', 'report'].includes(e.node)) {
    $('bt-' + e.node).className = 'bt-step ' + e.status.toLowerCase();
    $('bt-' + e.node).querySelector('small').textContent = e.status;
  }
  if (e.event === 'diagnosis') $('bt-origin').textContent += ' · ' + e.issue_count + ' issue(s) found';
  $('log').textContent += JSON.stringify(e) + '\n';
  bt.timer = setTimeout(tickBT, Number($('btSpeed').value));
}

// ---------- about ----------
async function loadAbout() {
  await busy(null, async () => {
    const v = await api('/api/version');
    const s = v.settings;
    const yes = b => b ? '<span class="badge ok">yes</span>' : '<span class="badge neutral">no</span>';
    $('about-info').className = '';
    $('about-info').innerHTML = '<table><tbody>'
      + '<tr><td>Version</td><td>' + esc(v.version) + '</td></tr>'
      + '<tr><td>Dashboard token required</td><td>' + yes(s.ui_auth_enabled) + '</td></tr>'
      + '<tr><td>Remote collector endpoint enabled</td><td>' + yes(s.agent_token_configured) + '</td></tr>'
      + '<tr><td>Native C++ core built</td><td>' + yes(v.native_core_available) + '</td></tr>'
      + '<tr><td>BehaviorTree.CPP runner built</td><td>' + yes(v.native_bt_available) + '</td></tr>'
      + '<tr><td>Ollama URL / model</td><td class="mono">' + esc(s.ollama_url) + ' · ' + esc(s.ollama_model) + '</td></tr>'
      + '<tr><td>Embedding model</td><td class="mono">' + esc(s.embed_model) + '</td></tr>'
      + '</tbody></table><p class="muted">Configure with <code>AUTODIAG_*</code> environment variables; see the README.</p>';
    $('logout-form').hidden = !s.ui_auth_enabled;
  });
}

// ---------- theme ----------
function applyTheme(theme) {
  if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}
function toggleTheme() {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === 'dark'
    : matchMedia('(prefers-color-scheme: dark)').matches;
  const next = dark ? 'light' : 'dark';
  applyTheme(next);
  store.set('theme', next);
}

// ---------- diagnosis graph ----------
const SVG_NS = 'http://www.w3.org/2000/svg';
const GRAPH = {box: {w: 230, h: 52}, colGap: 200, rowGap: 26, pad: 28};
const RANK = {ok: 0, waiting: 1, warning: 2, error: 3};

function svg(tag, attrs = {}, text) {
  const el = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
  if (text !== undefined) el.textContent = text;
  return el;
}

const shortName = (s, n = 24) => (s.length > n ? s.slice(0, n - 1) + '…' : s);
// `ros2 topic pub/echo` run as anonymous _ros2cli_<pid> nodes; name them by what they do.
const nodeLabel = n => (n.id.startsWith('_ros2cli_') ? (n.publishes.length ? 'ros2 topic pub' : 'ros2 topic echo') + ' · ' + n.id.slice(9)
  : n.id.startsWith('transform_listener_impl_') ? 'TF listener' : n.id);
const idLabel = (id, role) => (id.startsWith('_ros2cli_') ? (role === 'publisher' ? 'ros2 topic pub' : 'ros2 topic echo') + ' (' + id.slice(9) + ')'
  : id.startsWith('transform_listener_impl_') ? 'TF listener' : id);

function layoutGraph(data) {
  // Columns by role: only publishes | both | only subscribes; "waiting" topics get a ghost source on the left.
  const cols = [[], [], []];
  data.nodes.forEach(n => cols[n.publishes.length && n.subscribes.length ? 1 : n.publishes.length ? 0 : 2].push(n.id));
  cols[0].push(...data.waiting.map(w => 'ghost:' + w.topic));
  const links = data.edges.map(e => [e.source, e.target])
    .concat(data.waiting.flatMap(w => w.subscribers.map(s => ['ghost:' + w.topic, s])));
  const used = cols.filter(c => c.length);
  // Two barycenter sweeps: order each column by the average row of its neighbours, so lines cross less.
  const order = () => Object.fromEntries(used.flatMap(c => c.map((id, i) => [id, i])));
  const sweep = (col, neighbours) => {
    const rank = order();
    const score = id => { const r = neighbours(id).map(n => rank[n]).filter(x => x !== undefined); return r.length ? r.reduce((a, b) => a + b, 0) / r.length : rank[id]; };
    col.sort((a, b) => score(a) - score(b) || a.localeCompare(b));
  };
  const incoming = id => links.filter(l => l[1] === id).map(l => l[0]);
  const outgoing = id => links.filter(l => l[0] === id).map(l => l[1]);
  for (let pass = 0; pass < 2; pass++) {
    used.slice(1).forEach(col => sweep(col, incoming));
    used.slice(0, -1).reverse().forEach(col => sweep(col, outgoing));
  }
  const pos = {};
  const {w, h} = GRAPH.box;
  used.forEach((col, i) => col.forEach((id, j) => {
    pos[id] = {x: GRAPH.pad + i * (w + GRAPH.colGap), y: GRAPH.pad + j * (h + GRAPH.rowGap)};
  }));
  const rows = Math.max(1, ...used.map(c => c.length));
  return {pos, width: GRAPH.pad * 2 + used.length * w + (used.length - 1) * GRAPH.colGap,
    height: GRAPH.pad * 2 + rows * h + (rows - 1) * GRAPH.rowGap};
}

// Point and heading on a cubic Bézier, for topic labels and break marks.
function bezier(p, t) {
  const u = 1 - t;
  return [0, 1].map(i => u * u * u * p[0][i] + 3 * u * u * t * p[1][i] + 3 * u * t * t * p[2][i] + t * t * t * p[3][i]);
}
function bezierAngle(p, t) {
  const u = 1 - t;
  const d = [0, 1].map(i => 3 * u * u * (p[1][i] - p[0][i]) + 6 * u * t * (p[2][i] - p[1][i]) + 3 * t * t * (p[3][i] - p[2][i]));
  return Math.atan2(d[1], d[0]) * 180 / Math.PI;
}

function drawGraph(data) {
  const view = $('graph-view');
  view.innerHTML = '';
  if (!data.nodes.length && !data.waiting.length) {
    view.innerHTML = '<p class="muted">No publishers or subscribers found on the visible topics. Is ROS 2 sourced, and are your nodes running on the same ROS_DOMAIN_ID?</p>';
    return;
  }
  const {pos, width, height} = layoutGraph(data);
  const {w, h} = GRAPH.box;
  const root = svg('svg', {viewBox: `0 0 ${width} ${height}`, width, height, class: 'graph', role: 'img',
    'aria-label': 'Publisher to subscriber graph'});
  // Shrink to fit the pane, but never below 60 %: past that the pane scrolls instead of the text getting unreadable.
  root.style.maxWidth = width + 'px';
  root.style.minWidth = Math.round(width * 0.6) + 'px';
  const byId = Object.fromEntries(data.nodes.map(n => [n.id, n]));

  // One drawn link per publisher → subscriber pair, plus each subscriber waiting for a topic nobody publishes.
  const links = data.edges.map(e => ({source: e.source, target: e.target, status: e.status, edge: e,
    label: e.topics.length === 1 ? e.topics[0].topic : e.topics.length + ' topics'}))
    .concat(data.waiting.flatMap(wt => wt.subscribers.map(s => ({source: 'ghost:' + wt.topic, target: s, status: 'waiting', waiting: wt, label: wt.topic}))))
    .filter(l => pos[l.source] && pos[l.target]);

  // Ports: every link gets its own point on the node's edge, ordered by where its other end sits.
  const ports = new Map();
  const side = (id, end, other) => {
    const list = links.filter(l => l[end] === id).sort((a, b) => pos[a[other]].y - pos[b[other]].y);
    const step = Math.min(14, (h - 22) / Math.max(1, list.length - 1));
    list.forEach((l, i) => ports.set(end + l.source + '>' + l.target, h / 2 + (i - (list.length - 1) / 2) * step));
  };
  Object.keys(pos).forEach(id => { side(id, 'source', 'target'); side(id, 'target', 'source'); });

  const edgeLayer = svg('g'), labelLayer = svg('g'), nodeLayer = svg('g'), portLayer = svg('g');
  const placed = [];
  const nodeEls = {};
  let selected = null;
  const select = (g, l) => {
    root.querySelectorAll('.selected,.linked').forEach(x => x.classList.remove('selected', 'linked'));
    g.classList.add('selected');
    [l.source, l.target].forEach(id => nodeEls[id] && nodeEls[id].classList.add('linked'));
    if (l.waiting) waitingDetails(l.waiting); else edgeDetails(l.edge);
  };

  [...links].sort((a, b) => RANK[a.status] - RANK[b.status]).forEach(l => {
    const a = pos[l.source], b = pos[l.target], key = l.source + '>' + l.target;
    const x1 = a.x + w, y1 = a.y + ports.get('source' + key), x2 = b.x, y2 = b.y + ports.get('target' + key);
    const dx = Math.max(60, (x2 - x1) / 2);
    const p = [[x1, y1], [x1 + dx, y1], [x2 - dx, y2], [x2, y2]];
    const d = `M${x1},${y1} C${p[1]} ${p[2]} ${x2},${y2}`;
    const g = svg('g', {class: 'edge ' + l.status, tabindex: '0', role: 'button',
      'aria-label': l.waiting ? `${l.target} waits for ${l.label}` : `${l.source} to ${l.target}: ${l.edge.topics.map(t => t.topic).join(', ')} (${l.status})`});
    ['hit', 'halo', 'glow', 'line'].forEach(c => g.appendChild(svg('path', {d, class: c})));
    if (l.status === 'ok') g.appendChild(svg('path', {d, class: 'flow'}));
    if (l.status === 'error') {
      const [bx, by] = bezier(p, 0.5);
      const brk = svg('g', {class: 'brk', transform: `translate(${bx},${by}) rotate(${bezierAngle(p, 0.5)})`});
      brk.appendChild(svg('rect', {x: -7, y: -9, width: 14, height: 18}));
      brk.appendChild(svg('line', {x1: -5, y1: -9, x2: -5, y2: 9}));
      brk.appendChild(svg('line', {x1: 5, y1: -9, x2: 5, y2: 9}));
      g.appendChild(brk);
    }
    // Topic label: the first spot along the curve that doesn't cover another label.
    const text = shortName(l.label, 28), lw = text.length * 7.1 + 14, lh = 20;
    let spot = null;
    for (const t of [0.5, 0.34, 0.66, 0.24, 0.76]) {
      const [cx, cy] = bezier(p, t);
      const box = {x: cx - lw / 2, y: cy - lh / 2, w: lw, h: lh};
      if (!placed.some(o => box.x < o.x + o.w + 4 && o.x < box.x + box.w + 4 && box.y < o.y + o.h + 3 && o.y < box.y + box.h + 3)) { spot = box; break; }
      spot = spot || box;
    }
    placed.push(spot);
    const lab = svg('g', {class: 'edge-label ' + l.status, transform: `translate(${spot.x},${spot.y})`});
    lab.appendChild(svg('rect', {width: lw, height: lh, rx: 2}));
    lab.appendChild(svg('text', {x: lw / 2, y: 14, 'text-anchor': 'middle'}, text));
    labelLayer.appendChild(lab);
    portLayer.appendChild(svg('circle', {cx: x1, cy: y1, r: 4, class: 'port ' + l.status}));
    portLayer.appendChild(svg('circle', {cx: x2, cy: y2, r: 4, class: 'port ' + l.status}));
    const open = () => select(g, l);
    g.addEventListener('click', open);
    g.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); } });
    edgeLayer.appendChild(g);
    if (!selected || RANK[l.status] >= RANK[selected.l.status]) selected = {g, l};
  });

  Object.entries(pos).forEach(([id, p]) => {
    const ghost = id.startsWith('ghost:');
    const g = svg('g', {class: 'gnode' + (ghost ? ' ghost' : '')});
    g.appendChild(svg('rect', {x: p.x, y: p.y, width: w, height: h, rx: 2}));
    if (ghost) {
      const t = svg('text', {x: p.x + w / 2, y: p.y + h / 2 + 4, 'text-anchor': 'middle', class: 'name'}, shortName('nobody publishes ' + id.slice(6), 30));
      g.appendChild(t);
    } else {
      const n = byId[id];
      const role = n.publishes.length && n.subscribes.length ? 'PUB + SUB' : n.publishes.length ? 'PUBLISHER' : 'SUBSCRIBER';
      g.appendChild(svg('text', {x: p.x + 13, y: p.y + 19, class: 'role'}, role));
      const t = svg('text', {x: p.x + 13, y: p.y + 39, class: 'name'}, shortName(nodeLabel(n), 26));
      t.appendChild(svg('title', {}, nodeLabel(n)));
      g.appendChild(t);
    }
    nodeEls[id] = g;
    nodeLayer.appendChild(g);
  });
  [edgeLayer, nodeLayer, portLayer, labelLayer].forEach(x => root.appendChild(x));
  view.appendChild(root);
  // Open the worst link straight away: that is usually the one to fix.
  if (selected) select(selected.g, selected.l);
}

const STATE_TEXT = {error: ['Problem', 'No data gets through'], warning: ['Warning', 'Some data can be missed'],
  ok: ['Compatible', 'QoS and message types match'], waiting: ['Waiting', 'Nobody publishes this topic']};
const QOS_ROWS = ['reliability', 'durability', 'history', 'deadline', 'lifespan', 'liveliness'];

function linkState(status) {
  const [k, t] = STATE_TEXT[status] || STATE_TEXT.ok;
  return '<div class="link-state ' + esc(status) + '"><span class="k">' + esc(k) + '</span><span class="t">' + esc(t) + '</span></div>';
}

// Offered against requested QoS, side by side; the policies a finding blames are marked.
function qosTable(t) {
  const pub = t.publisher_qos || {}, sub = t.subscriber_qos || {};
  const blamed = k => (t.findings || []).find(f => (f.code || '').includes(k.toUpperCase()) || (k === 'durability' && (f.code || '').includes('LATCHED')));
  const rows = QOS_ROWS.filter(k => pub[k] || sub[k]);
  if (!rows.length) return '';
  return '<table class="qos"><thead><tr><th>Policy</th><th>Publisher offers</th><th>Subscriber asks</th></tr></thead><tbody>'
    + rows.map(k => { const f = blamed(k);
      return '<tr' + (f ? ' class="bad ' + esc(f.severity) + '"' : '') + '><td>' + esc(k) + '</td><td>' + esc(pub[k] || '—') + '</td><td>' + esc(sub[k] || '—') + '</td></tr>'; }).join('')
    + '</tbody></table>';
}

function edgeDetails(e) {
  $('graph-details').className = '';
  $('graph-details').innerHTML = linkState(e.status)
    + '<div class="route"><span>' + esc(idLabel(e.source, 'publisher')) + '</span><span class="arrow">──▶</span><span>' + esc(idLabel(e.target, 'subscriber')) + '</span></div>'
    + e.topics.map(t => '<div class="graph-topic"><div class="card-head"><h3>' + esc(t.topic) + ' <small class="muted">' + esc(t.type) + '</small></h3>'
      + '<a href="#topics" data-inspect-topic="' + esc(t.topic) + '">Inspect topic →</a></div>'
      + qosTable(t)
      + findingsHTML(t.findings, 'The QoS and message types of this connection are compatible. This does not prove that messages arrive; read a live sample to confirm.')
      + '</div>').join('');
}

function waitingDetails(wt) {
  const subs = wt.subscribers.map(id => idLabel(id, 'subscriber'));
  $('graph-details').className = '';
  $('graph-details').innerHTML = linkState('waiting')
    + '<div class="route"><span class="muted">nobody</span><span class="arrow">──▶</span><span>' + esc(subs.join(', ')) + '</span></div>'
    + '<div class="graph-topic"><div class="card-head"><h3>' + esc(wt.topic) + (wt.type ? ' <small class="muted">' + esc(wt.type) + '</small>' : '') + '</h3>'
    + '<a href="#topics" data-inspect-topic="' + esc(wt.topic) + '">Inspect topic →</a></div>'
    + '<div class="finding warning"><p>' + esc(subs.join(', ')) + ' subscribe' + (subs.length === 1 ? 's' : '')
    + ' to <code>' + esc(wt.topic) + '</code>, but no publisher is visible from this machine.</p>'
    + '<p class="next"><b>Next step</b> Start the node that publishes it, check the topic name and remapping, or compare hosts if it runs on another machine or container (domain ID, discovery range, RMW).</p>'
    + '<div class="docs"><a href="#environments" data-tab-link="environments">Compare hosts →</a></div></div></div>';
}

async function loadGraph(button) {
  $('graph-view').innerHTML = '<p class="muted">' + loading('Inspecting every topic… this takes a few seconds.') + '</p>';
  await busy(button, async () => {
    const data = await api('/api/graph');
    if (data.state !== 'ok') {
      $('graph-view').innerHTML = '<div class="finding warning"><p>' + esc(data.error || 'The ROS graph could not be read.') + '</p></div>';
      return;
    }
    const c = data.counts;
    $('graph-summary').textContent = `${c.error} no data · ${c.warning} warning · ${c.ok} ok · ${c.waiting} waiting`;
    $('graph-note').textContent = `${data.topics_inspected} of ${data.topics_total} topics inspected in ${data.seconds} s`
      + (data.truncated ? ' (limited; the rest are not shown)' : '') + (data.hidden_topics.length ? '. Hidden: ' + data.hidden_topics.join(', ') : '')
      + '. ' + data.limitations.join(' ');
    $('alert-graph').hidden = !c.error;
    alarms.graph = {error: c.error, warning: c.warning};
    renderAlarms();
    drawGraph(data);
    logEvents(data.edges.flatMap(e => e.topics.filter(t => t.status !== 'ok').map(t => ({level: t.status, target: t.topic, topic: t.topic,
      what: (t.findings[0] && t.findings[0].code) || t.status, who: idLabel(e.source, 'publisher') + ' → ' + idLabel(e.target, 'subscriber')})))
      .concat(data.waiting.map(wt => ({level: 'waiting', target: wt.topic, topic: wt.topic, what: 'subscriber waiting, nobody publishes',
        who: wt.subscribers.map(s => idLabel(s, 'subscriber')).join(', ')})))
      .concat([{level: 'ok', target: 'graph', tab: 'graph', what: c.ok + (c.ok === 1 ? ' link' : ' links') + ' compatible',
        who: data.topics_inspected + ' topics · ' + data.seconds + ' s'}]));
  });
}

// ---------- wiring ----------
const ACTIONS = {
  refresh: b => refresh(b), export: b => exportSnapshot(b), report: b => downloadReport(b), theme: () => toggleTheme(),
  'load-topics': b => loadTopics(b), 'load-graph': b => loadGraph(b), 'inspect-topic': b => inspectTopic(b), sample: () => readSample(),
  'copy-sample': () => navigator.clipboard.writeText($('sample-result').textContent).then(() => toast('Copied', 'ok'), () => toast('Clipboard unavailable', 'error')),
  'load-docker': b => loadDocker(b), 'compare-snapshot': b => compareSnapshot(b), 'compare-remote': b => compareRemote(b),
  'clear-peer': () => { state.peer = null; $('remote-results').className = 'muted'; $('remote-results').textContent = 'No peer loaded.'; $('snapshot-file').value = ''; toast('Peer cleared'); },
  'run-diagnostic': b => runDiagnostic(b), ask: b => ask(b, b.dataset.ai === 'true'), selftest: b => selftest(b),
  'endpoint-check': b => endpointCheck(b), bt: b => runBT(b, b.dataset.fault === 'true'),
  'bt-pause': () => { const bt = state.bt; bt.paused = !bt.paused; $('btPause').textContent = bt.paused ? 'Resume' : 'Pause'; if (bt.paused) clearTimeout(bt.timer); else tickBT(); },
  'stop-ai': () => { if (aiAbort) aiAbort.abort(); },
  'prov-models': b => loadProviderModels(b.dataset.id, null, true),
  'prov-save': b => saveProvider(b), 'prov-default': b => saveProvider(b, {make_default: true}),
  'prov-test': b => testProvider(b), 'prov-remove': b => removeKey(b),
  'bt-replay': () => { const events = state.bt.events; btClear(); state.bt.events = events; tickBT(); },
  'toggle-events': () => setEventsOpen($('events-strip').classList.contains('collapsed')),
};

function openEvent(el) {
  const e = events[Number(el.dataset.go)];
  if (!e) return;
  if (e.topic) { showTab('topics'); selectTopic(e.topic); }
  else if (e.tab) showTab(e.tab);
}

document.addEventListener('click', e => {
  const tabLink = e.target.closest('[data-tab],[data-tab-link]');
  if (tabLink) { e.preventDefault(); showTab(tabLink.dataset.tab || tabLink.dataset.tabLink); return; }
  const inspectLink = e.target.closest('[data-inspect-topic]');
  if (inspectLink) { e.preventDefault(); showTab('topics'); selectTopic(inspectLink.dataset.inspectTopic); inspectTopic(); return; }
  const row = e.target.closest('tr[data-topic]');
  if (row) { selectTopic(row.dataset.topic); return; }
  const ev = e.target.closest('.ev[data-go]');
  if (ev) { openEvent(ev); return; }
  const button = e.target.closest('[data-action]');
  if (button && ACTIONS[button.dataset.action]) ACTIONS[button.dataset.action](button);
});
document.addEventListener('keydown', e => {
  const row = e.target.closest && e.target.closest('tr[data-topic]');
  if (row && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); selectTopic(row.dataset.topic); }
  const ev = e.target.closest && e.target.closest('.ev[data-go]');
  if (ev && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openEvent(ev); }
});
$('topic-filter').addEventListener('input', renderTopics);
$('auto-samples').addEventListener('change', () => {
  if (state.sampleTimer) { stopSamples(); return; }
  if ($('auto-samples').checked) {
    if (!state.selectedTopic) { $('auto-samples').checked = false; return toast('Select a topic first'); }
    readSample(); state.sampleTimer = setInterval(readSample, 3000);
  }
});
$('question').addEventListener('keydown', e => { if (e.key === 'Enter') ask($('ask-ai'), true); });
$('ai-provider').addEventListener('change', () => { store.set('aiProvider', $('ai-provider').value); loadOllama(); });
$('ai-model').addEventListener('change', () => store.set('aiModel.' + $('ai-provider').value, $('ai-model').value));
document.addEventListener('change', e => {
  const select = e.target.closest && e.target.closest('[data-model-for]');
  if (!select) return;
  const input = select.parentElement.querySelector('input[name=model]');
  if (select.value === '__other') { input.hidden = false; input.value = ''; input.focus(); }
  else { input.hidden = true; input.value = select.value; }
});
$('redact-export').checked = store.get('redact') !== 'false';
$('redact-export').addEventListener('change', () => store.set('redact', String($('redact-export').checked)));
$('remoteUrl').value = store.get('remoteUrl') || '';
window.addEventListener('hashchange', () => showTab(location.hash.slice(1)));

applyTheme(store.get('theme'));
setEventsOpen(store.get('events') !== 'closed' && !matchMedia('(max-width: 900px)').matches);
showTab(location.hash.slice(1) || 'overview');
refresh();
