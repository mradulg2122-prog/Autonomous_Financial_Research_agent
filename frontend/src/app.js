/**
 * ARA-1 Frontend Application
 * Vanilla JS SPA with WebSocket real-time updates
 */

const API_BASE = 'http://localhost:8000/api/v1';
const WS_BASE = 'ws://localhost:8000/api/v1/research/ws';

// ── State ────────────────────────────────────────────────────
const state = {
  currentView: 'dashboard',
  activeSession: null,
  ws: null,
  sessions: [],
  reports: [],
  activeMemoryTab: 'short-term',
};

// ── Utils ────────────────────────────────────────────────────
function toast(msg, type = 'info', duration = 4000) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  const container = document.getElementById('toast-container');
  container.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, duration);
}

function formatDuration(seconds) {
  if (!seconds) return '—';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${(seconds % 60).toFixed(0)}s`;
}

function statusBadge(status) {
  return `<span class="badge badge-${status}">${status}</span>`;
}

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

// ── Simple Markdown Parser ────────────────────────────────────
function renderMarkdown(md) {
  if (!md) return '<p class="text-muted">No content available.</p>';
  let html = md
    .replace(/^#{1} (.+)$/gm, '<h1>$1</h1>')
    .replace(/^#{2} (.+)$/gm, '<h2>$1</h2>')
    .replace(/^#{3} (.+)$/gm, '<h3>$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^---$/gm, '<hr />')
    .replace(/^[-*] (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/^([^<\n].+)$/gm, '<p>$1</p>');
  return `<div class="report-markdown">${html}</div>`;
}

// ── Navigation ────────────────────────────────────────────────
function switchView(viewName) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const view = document.getElementById(`view-${viewName}`);
  const nav = document.getElementById(`nav-${viewName}`);
  if (view) view.classList.add('active');
  if (nav) nav.classList.add('active');

  const titles = {
    'dashboard': ['Research Dashboard', 'Autonomous multi-agent financial research'],
    'agent-trace': ['Agent Trace Viewer', 'Monitor agent execution in detail'],
    'tool-monitor': ['Tool Usage Monitor', 'All 15 registered research tools'],
    'memory': ['Memory Viewer', 'Short-term, long-term, and episodic memory'],
    'report': ['Research Report Viewer', 'View and export generated reports'],
    'evaluation': ['Evaluation Dashboard', '25+ quality metrics across 11 categories'],
  };

  const [title, sub] = titles[viewName] || ['ARA-1', ''];
  document.getElementById('page-title').textContent = title;
  document.getElementById('page-subtitle').textContent = sub;

  state.currentView = viewName;

  if (viewName === 'tool-monitor') loadTools();
}

document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => switchView(item.dataset.view));
});

document.getElementById('new-research-btn').addEventListener('click', () => {
  switchView('dashboard');
  document.getElementById('research-query').focus();
});

// ── Research Submission ───────────────────────────────────────
document.getElementById('submit-research').addEventListener('click', async () => {
  const query = document.getElementById('research-query').value.trim();
  const ticker = document.getElementById('ticker-input').value.trim().toUpperCase();
  const company = document.getElementById('company-name-input').value.trim();

  if (!query) { toast('Please enter a research query', 'error'); return; }

  const btn = document.getElementById('submit-research');
  btn.disabled = true;
  btn.textContent = 'Launching...';

  try {
    const data = await apiPost('/research', {
      query,
      company_ticker: ticker || undefined,
      company_name: company || undefined,
    });

    state.activeSession = data.session_id;
    toast(`Research session started! ${ticker || ''}`, 'success');
    showActiveSession(data);
    connectWebSocket(data.session_id);
    refreshSessions();

  } catch (err) {
    toast(`Failed to start research: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><polygon points="5,3 19,12 5,21 5,3"/></svg> Launch Research`;
  }
});

// ── Active Session UI ─────────────────────────────────────────
function showActiveSession(data) {
  const panel = document.getElementById('active-session-panel');
  panel.classList.remove('hidden');

  document.getElementById('session-id-display').textContent = `ID: ${data.session_id.slice(0, 8)}...`;
  document.getElementById('session-status-text').textContent = 'Planning research...';
  if (data.query) {
    const ticker = document.getElementById('ticker-input').value.trim();
    if (ticker) document.getElementById('session-ticker-badge').textContent = ticker;
  }

  // Reset pipeline nodes
  document.querySelectorAll('.pipeline-node').forEach(n => {
    n.classList.remove('active', 'complete', 'error');
  });
  document.getElementById('event-feed').innerHTML = '';
}

const AGENT_TO_NODE = {
  'planner_agent': 'node-planner',
  'parallel_research': 'node-research',
  'sec_research_agent': 'node-research',
  'financial_data_agent': 'node-research',
  'news_intelligence_agent': 'node-research',
  'earnings_transcript_agent': 'node-research',
  'fact_verification_agent': 'node-verify',
  'synthesis_agent': 'node-synthesis',
  'report_writer_agent': 'node-report',
  'evaluation_agent': 'node-eval',
};

const STATUS_TO_NODE = {
  'planning': 'node-planner',
  'researching': 'node-research',
  'verifying': 'node-verify',
  'synthesizing': 'node-synthesis',
  'reporting': 'node-report',
  'evaluating': 'node-eval',
};

function setNodeState(nodeId, newState) {
  const node = document.getElementById(nodeId);
  if (!node) return;
  node.classList.remove('active', 'complete', 'error');
  node.classList.add(newState);

  // If setting active, mark previous nodes as complete
  if (newState === 'active') {
    const order = ['node-planner', 'node-research', 'node-verify', 'node-synthesis', 'node-report', 'node-eval'];
    const idx = order.indexOf(nodeId);
    order.slice(0, idx).forEach(id => {
      const n = document.getElementById(id);
      if (n && !n.classList.contains('complete')) n.classList.add('complete');
    });
  }
}

function addEventToFeed(type, message) {
  const feed = document.getElementById('event-feed');
  const time = new Date().toLocaleTimeString();
  const item = document.createElement('div');
  item.className = 'event-item';
  item.innerHTML = `
    <span class="event-type ${type}">${type.replace('_', ' ')}</span>
    <span class="event-message">${message}</span>
    <span class="event-time">${time}</span>
  `;
  feed.appendChild(item);
  feed.scrollTop = feed.scrollHeight;
}

// ── WebSocket ─────────────────────────────────────────────────
function connectWebSocket(sessionId) {
  if (state.ws) { state.ws.close(); state.ws = null; }

  const ws = new WebSocket(`${WS_BASE}/${sessionId}`);
  state.ws = ws;

  ws.onopen = () => {
    document.getElementById('ws-indicator').style.background = 'rgba(16,185,129,0.1)';
    const wsText = document.querySelector('.ws-indicator span');
    if (wsText) wsText.textContent = 'Live';
  };

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      handleWsMessage(msg);
    } catch {}
  };

  ws.onclose = () => {
    const wsText = document.querySelector('.ws-indicator span');
    if (wsText) wsText.textContent = 'Disconnected';
  };

  // Ping keepalive
  const ping = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send('ping');
    else clearInterval(ping);
  }, 30000);
}

function handleWsMessage(msg) {
  const { type, data } = msg;

  switch (type) {
    case 'status': {
      const statusText = document.getElementById('session-status-text');
      if (statusText) statusText.textContent = data.message || data.status;

      const nodeId = STATUS_TO_NODE[data.status];
      if (nodeId) setNodeState(nodeId, 'active');

      addEventToFeed('status', data.message || data.status);

      if (data.status === 'complete') {
        document.querySelectorAll('.pipeline-node').forEach(n => n.classList.add('complete'));
        document.getElementById('session-spinner').style.display = 'none';
        toast('Research complete! View the report.', 'success', 6000);
        refreshSessions();
        updateSessionDropdowns();
      } else if (data.status === 'failed') {
        toast('Research failed. Check logs.', 'error');
      }
      break;
    }
    case 'agent_trace': {
      const nodeId = AGENT_TO_NODE[data.agent];
      if (nodeId) setNodeState(nodeId, data.status === 'complete' ? 'complete' : 'active');
      addEventToFeed('agent_trace', `${data.agent}: ${data.status}`);
      break;
    }
    case 'tool_call': {
      addEventToFeed('tool_call', `🔧 ${data.tool}(${JSON.stringify(data.args || {}).slice(0, 60)}...)`);
      break;
    }
  }
}

// ── Sessions Table ────────────────────────────────────────────
async function refreshSessions() {
  try {
    const data = await apiGet('/research');
    state.sessions = data.sessions || [];
    renderSessionsTable(state.sessions);
    document.getElementById('metric-sessions').textContent = state.sessions.length;
    const completed = state.sessions.filter(s => s.status === 'complete').length;
    document.getElementById('metric-reports').textContent = completed;
    updateSessionDropdowns();
  } catch (err) {
    console.error('Failed to refresh sessions:', err);
  }
}

function renderSessionsTable(sessions) {
  const tbody = document.getElementById('sessions-tbody');
  if (!sessions.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No sessions yet. Start your first research above.</td></tr>';
    return;
  }

  tbody.innerHTML = sessions.map(s => `
    <tr>
      <td style="max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${s.query}">${s.query}</td>
      <td><span style="font-family:var(--font-mono);font-size:13px;color:var(--accent-primary-light);">${s.company_ticker || '—'}</span></td>
      <td>${statusBadge(s.status)}</td>
      <td style="font-family:var(--font-mono);font-size:12px;color:var(--text-muted);">${formatDuration(s.duration_seconds)}</td>
      <td>
        <button class="btn btn-ghost btn-sm" onclick="viewReport('${s.session_id}')" ${s.status !== 'complete' ? 'disabled' : ''}>Report</button>
        <button class="btn btn-ghost btn-sm" onclick="viewTrace('${s.session_id}')" style="margin-left:6px">Trace</button>
      </td>
    </tr>
  `).join('');
}

function updateSessionDropdowns() {
  const selects = ['trace-session-select', 'report-session-select', 'eval-session-select'];
  selects.forEach(id => {
    const sel = document.getElementById(id);
    const currentVal = sel.value;
    sel.innerHTML = '<option value="">-- Select --</option>' +
      state.sessions.map(s => `<option value="${s.session_id}" ${s.session_id === currentVal ? 'selected' : ''}>${s.company_ticker || 'N/A'} — ${s.query.slice(0, 60)} (${s.status})</option>`).join('');
  });
}

// ── Agent Trace View ──────────────────────────────────────────
document.getElementById('load-trace-btn').addEventListener('click', async () => {
  const sessionId = document.getElementById('trace-session-select').value;
  if (!sessionId) { toast('Select a session first', 'error'); return; }

  try {
    const data = await apiGet(`/agents/traces/${sessionId}`);
    renderTrace(data);
  } catch (err) {
    toast(`Failed to load trace: ${err.message}`, 'error');
  }
});

function renderTrace(data) {
  const container = document.getElementById('trace-content');
  const { agent_traces = [], tool_calls = [] } = data;

  if (!agent_traces.length && !tool_calls.length) {
    container.innerHTML = '<div class="placeholder-state"><div class="placeholder-icon">🔍</div><p>No trace data available for this session</p></div>';
    return;
  }

  const agentHtml = agent_traces.map(t => `
    <div class="trace-card">
      <div class="trace-card-header">
        <span class="trace-agent-name">🤖 ${t.agent_name}</span>
        <span class="trace-duration">${t.duration_ms ? `${t.duration_ms.toFixed(0)}ms` : '—'}</span>
      </div>
      ${statusBadge(t.status)}
      ${t.reasoning ? `<p style="font-size:13px;color:var(--text-secondary);margin-top:10px;">${t.reasoning.slice(0, 300)}...</p>` : ''}
    </div>
  `).join('');

  const toolHtml = tool_calls.map(tc => `
    <div class="trace-card" style="border-left:2px solid ${tc.success ? 'var(--accent-green)' : 'var(--accent-red)'}">
      <div class="trace-card-header">
        <span class="trace-agent-name">🔧 ${tc.tool_name}</span>
        <span class="trace-duration">${tc.duration_ms ? `${tc.duration_ms.toFixed(0)}ms` : '—'}</span>
      </div>
      ${tc.error_message ? `<p style="color:var(--accent-red);font-size:12px;margin-top:6px;">${tc.error_message}</p>` : ''}
    </div>
  `).join('');

  container.innerHTML = `
    <h3 style="margin-bottom:16px;font-size:15px;font-weight:700;">Agent Executions (${agent_traces.length})</h3>
    ${agentHtml || '<p class="text-muted">No agent traces recorded.</p>'}
    <h3 style="margin:24px 0 16px;font-size:15px;font-weight:700;">Tool Calls (${tool_calls.length})</h3>
    ${toolHtml || '<p class="text-muted">No tool calls recorded.</p>'}
  `;
}

function viewTrace(sessionId) {
  switchView('agent-trace');
  document.getElementById('trace-session-select').value = sessionId;
  document.getElementById('load-trace-btn').click();
}

// ── Tools Monitor ─────────────────────────────────────────────
async function loadTools() {
  try {
    const data = await apiGet('/agents/tools');
    const grid = document.getElementById('tools-grid');
    grid.innerHTML = (data.tools || []).map(t => `
      <div class="tool-card">
        <div class="tool-card-name">${t.name}</div>
        <div class="tool-card-desc">${t.description}</div>
        <div class="tool-card-timeout">⏱ Timeout: ${t.timeout_seconds}s</div>
      </div>
    `).join('');
  } catch (err) {
    document.getElementById('tools-grid').innerHTML = `<div class="placeholder-state"><div class="placeholder-icon">⚠️</div><p>${err.message}</p></div>`;
  }
}

// ── Memory View ───────────────────────────────────────────────
document.querySelectorAll('.memory-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.memory-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    state.activeMemoryTab = tab.dataset.tab;
    const input = document.getElementById('memory-session-id');
    input.placeholder = state.activeMemoryTab === 'long-term'
      ? 'Enter search query...'
      : state.activeMemoryTab === 'episodic'
      ? 'Enter ticker or leave blank for all...'
      : 'Enter Session ID...';
  });
});

document.getElementById('memory-search-btn').addEventListener('click', async () => {
  const query = document.getElementById('memory-session-id').value.trim();
  const container = document.getElementById('memory-results');

  try {
    let data;
    if (state.activeMemoryTab === 'short-term') {
      if (!query) { toast('Enter a session ID', 'error'); return; }
      data = await apiGet(`/memory/short-term/${query}`);
    } else if (state.activeMemoryTab === 'long-term') {
      if (!query) { toast('Enter a search query', 'error'); return; }
      data = await apiGet(`/memory/long-term/search?query=${encodeURIComponent(query)}&top_k=10`);
    } else {
      data = await apiGet(`/memory/episodic${query ? `?ticker=${query}` : ''}`);
    }

    container.innerHTML = `<div class="json-viewer">${JSON.stringify(data, null, 2)}</div>`;
  } catch (err) {
    toast(`Memory query failed: ${err.message}`, 'error');
  }
});

// ── Report View ───────────────────────────────────────────────
document.getElementById('load-report-btn').addEventListener('click', async () => {
  const sessionId = document.getElementById('report-session-select').value;
  if (!sessionId) { toast('Select a session first', 'error'); return; }
  await loadReport(sessionId);
});

async function loadReport(sessionId) {
  const container = document.getElementById('report-content');
  container.innerHTML = '<div class="placeholder-state"><div class="placeholder-icon">⏳</div><p>Loading report...</p></div>';

  try {
    const md = await fetch(`${API_BASE}/reports/${sessionId}/markdown`).then(r => r.text());
    container.innerHTML = renderMarkdown(md);
    state.currentReportMd = md;
    state.currentReportSession = sessionId;
    document.getElementById('report-session-select').value = sessionId;
  } catch {
    try {
      const data = await apiGet(`/reports/${sessionId}`);
      const sections = data.sections || {};
      const mdParts = Object.entries(sections)
        .filter(([, v]) => v)
        .map(([k, v]) => `## ${k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}\n\n${v}`)
        .join('\n\n---\n\n');
      container.innerHTML = renderMarkdown(`# ${data.company_name || 'Research Report'}\n\n${mdParts}`);
    } catch (err) {
      toast(`Failed to load report: ${err.message}`, 'error');
      container.innerHTML = `<div class="placeholder-state"><div class="placeholder-icon">⚠️</div><p>${err.message}</p></div>`;
    }
  }
}

document.getElementById('export-markdown-btn').addEventListener('click', () => {
  if (!state.currentReportMd) { toast('Load a report first', 'error'); return; }
  const blob = new Blob([state.currentReportMd], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `ara1_report_${state.currentReportSession?.slice(0, 8) || 'report'}.md`;
  a.click();
  URL.revokeObjectURL(url);
  toast('Report exported as Markdown', 'success');
});

function viewReport(sessionId) {
  switchView('report');
  document.getElementById('report-session-select').value = sessionId;
  loadReport(sessionId);
}

// ── Evaluation View ───────────────────────────────────────────
document.getElementById('load-eval-btn').addEventListener('click', async () => {
  const sessionId = document.getElementById('eval-session-select').value;
  if (!sessionId) { toast('Select a session first', 'error'); return; }

  const container = document.getElementById('eval-content');
  container.innerHTML = '<div class="placeholder-state"><div class="placeholder-icon">⏳</div><p>Loading evaluation...</p></div>';

  try {
    const data = await apiGet(`/evaluation/${sessionId}`);
    renderEvaluation(data);
  } catch (err) {
    toast(`No evaluation found: ${err.message}`, 'error');
    container.innerHTML = `<div class="placeholder-state"><div class="placeholder-icon">⚠️</div><p>${err.message}</p></div>`;
  }
});

function renderEvaluation(data) {
  const container = document.getElementById('eval-content');
  const catScores = data.category_scores || {};
  const metrics = data.detailed_metrics || {};

  const categoryCards = Object.entries(catScores).map(([k, v]) => {
    const pct = Math.round((v || 0) * 100);
    const label = k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    return `
      <div class="eval-category-card">
        <div class="eval-cat-name">${label}</div>
        <div class="eval-cat-score" style="color:${v >= 0.8 ? 'var(--accent-green)' : v >= 0.6 ? 'var(--accent-amber)' : 'var(--accent-red)'}">${pct}%</div>
        <div class="eval-bar-track">
          <div class="eval-bar-fill" style="width:${pct}%"></div>
        </div>
      </div>
    `;
  }).join('');

  container.innerHTML = `
    <div class="eval-score-hero">
      <div class="eval-grade">${data.grade || '—'}</div>
      <div class="eval-score-text">Overall Score: <strong>${((data.overall_score || 0) * 100).toFixed(1)}%</strong></div>
    </div>

    <h3 style="margin-bottom:16px;font-size:14px;font-weight:600;color:var(--text-muted);">CATEGORY SCORES</h3>
    <div class="eval-categories">${categoryCards}</div>

    <h3 style="margin-bottom:12px;font-size:14px;font-weight:600;color:var(--text-muted);">DETAILED METRICS (${Object.keys(metrics).length} metrics)</h3>
    <div class="json-viewer">${JSON.stringify(metrics, null, 2)}</div>
  `;
}

document.getElementById('run-benchmarks-btn').addEventListener('click', async () => {
  try {
    await apiPost('/evaluation/benchmarks/run', {});
    toast('Benchmark suite started! This will take several minutes.', 'info', 8000);
  } catch (err) {
    toast(`Failed to start benchmarks: ${err.message}`, 'error');
  }
});

// ── Refresh Button ────────────────────────────────────────────
document.getElementById('refresh-sessions-btn').addEventListener('click', refreshSessions);

// ── API Status Check ──────────────────────────────────────────
async function checkApiStatus() {
  try {
    await fetch('http://localhost:8000/health');
    document.querySelector('.status-dot').style.background = 'var(--accent-green)';
    document.querySelector('.api-status span').textContent = 'API Connected';
  } catch {
    document.querySelector('.status-dot').style.background = 'var(--accent-red)';
    document.querySelector('.api-status span').textContent = 'API Offline';
  }
}

// ── Initialize ────────────────────────────────────────────────
async function init() {
  checkApiStatus();
  await refreshSessions();
  setInterval(refreshSessions, 15000);
  setInterval(checkApiStatus, 30000);
}

init();
