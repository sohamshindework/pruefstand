'use strict';

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
};
const pct = value => value == null ? 'N/A' : `${(value * 100).toFixed(1)}%`;
const eur = value => new Intl.NumberFormat('en-IE', {style: 'currency', currency: 'EUR', maximumFractionDigits: 2}).format(value);
const nice = value => String(value).replaceAll('_', ' ').replaceAll('-', ' ').replace(/\b\w/g, c => c.toUpperCase());
const agentLabel = value => ({'vulnerable-retry': 'Vulnerable retry', 'idempotent-agent': 'Idempotent agent'}[value] || value);
const pill = success => el('span', `pill ${success ? 'pass' : 'fail'}`, success ? 'PASSED' : 'FAILED');
let data, currentAgent, selectedRun, category = '', demoTimer, demoGeneration = 0;

function toast(message) {
  $('#toast').textContent = message;
  $('#toast').hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { $('#toast').hidden = true; }, 4500);
}

function validate(value) {
  if (value?.schema_version !== 1 || !Array.isArray(value.profiles) || !value.profiles.length || !Array.isArray(value.traces) || !Array.isArray(value.faults)) throw Error('Expected a Prü​fstand site-data export with profiles, traces, and faults.');
  if (value.profiles.length > 50 || value.traces.length > 10000 || value.faults.length > 100) throw Error('Experiment is too large for this viewer.');
  for (const p of value.profiles) {
    if (typeof p.agent !== 'string' || !Number.isFinite(p.n_runs) || !Number.isFinite(p.mean_loss_eur) || !p.latency_ms || !Number.isFinite(p.latency_ms.p95)) throw Error('Invalid profile.');
    for (const name of ['success_rate', 'consistency', 'robustness', 'predictability', 'safety']) {
      const metric = p.metrics?.[name];
      if (!metric || (metric.value !== null && (!Number.isFinite(metric.value) || metric.value < 0 || metric.value > 1))) throw Error('Invalid reliability score.');
    }
  }
  for (const run of value.traces) {
    if (typeof run.agent !== 'string' || typeof run.task_id !== 'string' || typeof run.run_id !== 'string' || typeof run.condition !== 'string' || typeof run.success !== 'boolean' || !Array.isArray(run.events) || !Number.isFinite(run.loss_eur)) throw Error('Invalid trace.');
  }
  return value;
}

function conditionScore(agent, condition) {
  const aggregate = data.conditions?.find(c => c.agent === agent && c.condition === condition);
  if (aggregate) return aggregate.success_rate;
  const runs = data.traces.filter(r => r.agent === agent && r.condition === condition);
  return runs.length ? runs.filter(r => r.success).length / runs.length : null;
}

function hydrate(value) {
  data = validate(value);
  currentAgent = data.profiles.find(p => p.agent === 'vulnerable-retry')?.agent || data.profiles[0].agent;
  $('#agent-select').replaceChildren();
  $('#roi-agent').replaceChildren();
  for (const p of data.profiles) {
    for (const selector of ['#agent-select', '#roi-agent']) {
      const option = el('option', '', agentLabel(p.agent));
      option.value = p.agent;
      $(selector).append(option);
    }
  }
  $('#agent-select').value = currentAgent;
  $('#roi-agent').value = currentAgent;
  $('#trace-count').textContent = data.traces.length;
  $('#condition-filter').replaceChildren(el('option', '', 'All conditions'));
  $('#condition-filter').firstChild.value = '';
  for (const condition of [...new Set(data.traces.map(r => r.condition))].sort()) {
    const option = el('option', '', nice(condition));
    option.value = condition;
    $('#condition-filter').append(option);
  }
  const synthetic = data.profiles.every(p => p.synthetic);
  $('.local-badge').lastChild.textContent = synthetic ? ' Synthetic benchmark' : ' Imported experiment';
  $('.notice strong').textContent = synthetic ? 'A transparent starting point.' : 'Imported experiment.';
  $('.notice span:nth-child(2)').childNodes[1].textContent = synthetic ? ' These are executable fixture agents, not ratings of third-party frameworks. ' : ' Results are supplied by the imported file. Check provenance and evaluation scope before using them. ';
  renderOverview(); renderProfile(); renderFaultChart(); renderTraces(); renderFaults(); renderROI();
  selectedRun = null;
  $('#trace-detail').replaceChildren(el('div', 'empty-state', 'Select a run to inspect its trace.'));
  route();
}

function route() {
  let view = location.hash.slice(1) || 'overview';
  if (!['overview', 'recorder', 'faults', 'evidence', 'methodology'].includes(view)) view = 'overview';
  $$('.view').forEach(node => { node.hidden = node.id !== `view-${view}`; });
  $$('nav a').forEach(node => {
    node.classList.toggle('active', node.dataset.view === view);
    if (node.dataset.view === view) node.setAttribute('aria-current', 'page');
    else node.removeAttribute('aria-current');
  });
  $('#breadcrumb').textContent = {overview: 'Overview', recorder: 'Flight recorder', faults: 'Fault library', evidence: 'Evidence & impact', methodology: 'Methodology'}[view];
}

function renderOverview() {
  const p = data.profiles.find(p => p.agent === currentAgent);
  const metrics = [
    ['Task success', pct(p.metrics.success_rate.value), 'Across all conditions', `${p.n_tasks} tasks`],
    ['Harmful runs', `${p.harmful_runs}`, 'Ground-truth evaluator', p.harmful_runs === 0 ? 'No observed harm' : `${pct(p.harmful_runs / p.n_runs)} of runs`],
    ['p95 call duration', `${p.latency_ms.p95.toFixed(2)}`, 'Sum of recorded calls', 'ms / run'],
    ['Recorded runs', p.n_runs.toLocaleString(), 'Seeded repeated trials', p.synthetic ? 'SYNTHETIC' : 'IMPORTED'],
  ];
  $('#metric-grid').replaceChildren(...metrics.map(([label, value, foot, tag]) => {
    const card = el('div', 'metric-card');
    const heading = el('div', 'metric-label', label); heading.append(el('span', '', '↗'));
    const bottom = el('div', 'metric-bottom'); bottom.append(el('span', 'tag', tag), el('span', '', foot));
    card.append(heading, el('div', 'metric-value', value), bottom);
    return card;
  }));
  const candidates = data.traces.filter(r => r.condition !== 'baseline');
  const preferred = [...candidates.filter(r => !r.success), ...candidates.filter(r => r.success)];
  const recent = [], seen = new Set();
  for (const run of preferred) {
    const key = `${run.agent}:${run.condition}`;
    if (!seen.has(key)) { recent.push(run); seen.add(key); }
    if (recent.length === 5) break;
  }
  $('#recent-runs').replaceChildren(...recent.map(run => {
    const row = el('tr');
    row.append(el('td', '', nice(run.task_id)), el('td', '', agentLabel(run.agent)));
    const condition = el('td'); condition.append(el('code', '', run.condition)); row.append(condition);
    const verdict = el('td'); verdict.append(pill(run.success)); row.append(verdict);
    row.append(el('td', 'mono', eur(run.loss_eur)));
    const action = el('td'); const button = el('button', '', '↗'); button.setAttribute('aria-label', `Inspect ${run.task_id} ${run.condition}`);
    button.onclick = () => inspectRun(run); action.append(button); row.append(action); return row;
  }));
}

function renderProfile() {
  const agents = [...data.profiles].sort((a, b) => (a.agent === 'idempotent-agent' ? -1 : 0) - (b.agent === 'idempotent-agent' ? -1 : 0)).slice(0, 2);
  $('.chart-legend').replaceChildren(...agents.map((p, index) => {
    const span = el('span'); span.append(el('i', `legend-color ${index ? 'gray' : 'lime'}`), document.createTextNode(agentLabel(p.agent))); return span;
  }));
  $('#profile-chart').replaceChildren(...['consistency', 'robustness', 'predictability', 'safety'].map(metric => {
    const row = el('div', 'profile-row'); const pair = el('div', 'bar-pair');
    for (const [index, p] of agents.entries()) {
      const score = p.metrics[metric].value;
      const track = el('div', `bar-track ${index ? 'secondary-bar' : ''}`), bar = el('div');
      bar.style.width = `${(score ?? 0) * 100}%`;
      track.title = `${agentLabel(p.agent)}: ${score == null ? 'unavailable' : score.toFixed(3)} · 95% CI ${JSON.stringify(p.metrics[metric].ci95)}`;
      track.append(bar); pair.append(track);
    }
    const value = agents.find(a => a.agent === currentAgent)?.metrics[metric].value ?? data.profiles.find(a => a.agent === currentAgent).metrics[metric].value;
    row.append(el('span', '', nice(metric)), pair, el('span', '', value == null ? 'N/A' : value.toFixed(2))); return row;
  }));
}

function renderFaultChart() {
  const faults = ['timeout_after', 'rate_limit', 'malformed_json', 'missing_field', 'prompt_injection', 'stale_response', 'model_swap'].filter(f => data.faults.some(item => item.name === f));
  const agents = [...data.profiles].sort((a, b) => (a.agent === 'idempotent-agent' ? -1 : 0) - (b.agent === 'idempotent-agent' ? -1 : 0)).slice(0, 2);
  $('#fault-chart').replaceChildren(...faults.map(fault => {
    const column = el('div', 'fault-column'), bars = el('div', 'fault-bars');
    for (const p of agents) {
      const score = conditionScore(p.agent, fault);
      const bar = el('div'); bar.style.height = `${(score ?? 0) * 100}%`;
      bar.title = `${agentLabel(p.agent)}: ${pct(score)}`;
      bar.append(el('span', '', score == null ? '—' : `${Math.round(score * 100)}%`)); bars.append(bar);
    }
    column.append(bars, el('span', '', nice(fault))); return column;
  }));
}

function filteredTraces() {
  const search = $('#trace-search').value.toLowerCase(), condition = $('#condition-filter').value, verdict = $('#verdict-filter').value;
  return data.traces.filter(r => (!search || `${r.task_id} ${r.agent} ${r.run_id} ${r.condition}`.toLowerCase().includes(search)) && (!condition || r.condition === condition) && (!verdict || r.success === (verdict === 'pass')));
}

function renderTraces() {
  const runs = filteredTraces();
  $('#filter-count').textContent = `${runs.length} traces`;
  $('#trace-list').replaceChildren(...runs.map(run => {
    const button = el('button', `trace-item${selectedRun?.run_id === run.run_id ? ' selected' : ''}`);
    const first = el('div'); first.append(el('strong', '', nice(run.task_id)), pill(run.success));
    button.append(first, el('small', '', agentLabel(run.agent)), el('code', '', run.condition));
    button.onclick = () => { selectedRun = run; renderTraces(); renderDetail(run); }; return button;
  }));
  if (!runs.length) $('#trace-list').append(el('div', 'empty-state', 'No traces match these filters.'));
}

function inspectRun(run) {
  selectedRun = run; $('#trace-search').value = ''; $('#condition-filter').value = ''; $('#verdict-filter').value = '';
  location.hash = 'recorder'; renderTraces(); renderDetail(run); route();
  $('.trace-item.selected')?.scrollIntoView({block: 'nearest'});
}

function renderDetail(run) {
  const detail = $('#trace-detail');
  const heading = el('div', 'detail-heading'); heading.append(el('div', 'eyebrow', run.run_id.slice(0, 16)), el('h2', '', nice(run.task_id)));
  const meta = el('div', 'detail-meta'); meta.append(pill(run.success), el('span', 'chip', agentLabel(run.agent)), el('span', 'chip mono', run.condition)); heading.append(meta);
  const summary = el('div', 'detail-summary');
  for (const [label, value] of [['Observed loss', eur(run.loss_eur)], ['Harmful actions', run.harmful_actions], ['Recorded calls', run.events.length], ['Seed', run.seed]]) {
    const node = el('div'); node.append(el('small', '', label), el('strong', '', value)); summary.append(node);
  }
  const timeline = el('div', 'timeline');
  for (const event of run.events) {
    const row = el('div', `event${event.error ? ' error' : ''}`), body = el('div'), header = el('div', 'event-header');
    header.append(el('code', '', event.name), el('span', 'event-type', event.fault ? `ϟ ${event.fault}` : event.kind.toUpperCase()));
    const details = el('details'); details.append(el('summary', '', `${event.error ? 'Error recorded' : 'Response recorded'} · ${event.duration_ms.toFixed(2)} ms · inspect payload`));
    details.append(el('pre', '', JSON.stringify({inputs: event.inputs, output: event.output, error: event.error, privacy_findings: event.privacy_findings}, null, 2)));
    body.append(header, details); row.append(el('span', 'event-number', event.sequence + 1), body); timeline.append(row);
  }
  const output = el('div', 'outcome'); output.append(el('h3', '', 'BUSINESS OUTCOME / RECORDED GROUND TRUTH'), el('pre', 'raw-output', JSON.stringify(run.output, null, 2)));
  detail.replaceChildren(heading, summary, timeline, output);
}

function renderFaults() {
  $('#fault-cards').replaceChildren(...data.faults.filter(f => !category || f.category === category).map(fault => {
    const card = el('article', 'fault-card'), top = el('div'); top.append(el('span', 'fault-icon', 'ϟ'), el('span', 'chip mono', fault.category.toUpperCase()));
    card.append(top, el('h3', '', nice(fault.name)), el('p', '', fault.description));
    const comparison = el('div', 'fault-comparison');
    for (const p of data.profiles.slice(0, 2)) comparison.append(el('span', '', `${agentLabel(p.agent)}: ${pct(conditionScore(p.agent, fault.name))}`));
    const button = el('button', '', 'Inspect recorded fault →');
    button.onclick = () => {
      const run = data.traces.find(r => r.condition === fault.name && !r.success) || data.traces.find(r => r.condition === fault.name);
      if (run) inspectRun(run); else toast('No recorded trace for this fault in the imported experiment.');
    };
    card.append(comparison, button); return card;
  }));
}

function renderROI() {
  const p = data.profiles.find(p => p.agent === $('#roi-agent').value);
  const volume = Math.max(1, Math.min(100000000, Number($('#roi-volume').value) || 1));
  const review = Math.max(0, Math.min(100000, Number($('#roi-review').value) || 0));
  const loss = volume * p.mean_loss_eur, reviewCost = volume * (1 - p.metrics.success_rate.value) * review;
  const grid = el('div', 'roi-numbers');
  for (const [label, value] of [['Projected direct loss / month', eur(loss)], ['Projected review cost / month', eur(reviewCost)]]) {
    const item = el('div'); item.append(el('small', '', label), el('strong', '', value)); grid.append(item);
  }
  grid.append(el('div', 'roi-verdict', p.harmful_runs > 0 ? '↳ NO-GO: observed harmful actions require remediation.' : '↳ REVIEW: no observed harm within this test scope.'));
  $('#roi-result').replaceChildren(grid);
}

function playDemo(fixed = false) {
  const run = data.traces.find(r => r.agent === (fixed ? 'idempotent-agent' : 'vulnerable-retry') && r.task_id === 'support-refund' && r.condition === 'timeout_after');
  if (!run) { toast('Import the bundled fixture experiment to replay this demo.'); return; }
  clearTimeout(demoTimer); const generation = ++demoGeneration;
  $('#demo-dialog').showModal(); $('#demo-title').textContent = fixed ? 'Same fault. One refund.' : 'One timeout. Two refunds.';
  $('#demo-timeline').replaceChildren(); $('#demo-verdict').textContent = ''; $('#demo-fix').hidden = true;
  let index = 0;
  function step() {
    if (generation !== demoGeneration || !$('#demo-dialog').open) return;
    if (index < run.events.length) {
      const event = run.events[index++], row = el('div', `demo-step${event.error ? ' error' : ''}`);
      row.append(el('span', '', `${index}. ${event.name}`), el('span', '', event.error ? event.fault || 'ERROR' : 'RECORDED OK'));
      $('#demo-timeline').append(row); demoTimer = setTimeout(step, 650);
    } else {
      $('#demo-verdict').textContent = `${run.harmful_actions} harmful action(s) · ${eur(run.loss_eur)} observed loss · ${run.success ? 'PASSED' : 'FAILED'}`;
      $('#demo-fix').hidden = fixed;
    }
  }
  step();
}

window.addEventListener('hashchange', route);
$('#agent-select').addEventListener('change', event => { currentAgent = event.target.value; renderOverview(); renderProfile(); });
for (const selector of ['#trace-search', '#condition-filter', '#verdict-filter']) $(selector).addEventListener('input', renderTraces);
for (const selector of ['#roi-agent', '#roi-volume', '#roi-review']) $(selector).addEventListener('input', renderROI);
$('#fault-tabs').addEventListener('click', event => {
  const button = event.target.closest('button'); if (!button) return;
  category = button.dataset.category; $$('#fault-tabs button').forEach(node => node.classList.toggle('active', node === button)); renderFaults();
});
$('#inspect-refund').onclick = () => {
  const run = data.traces.find(r => r.agent === 'vulnerable-retry' && r.task_id === 'support-refund' && r.condition === 'timeout_after');
  if (run) inspectRun(run); else toast('The imported experiment does not include the refund fixture.');
};
$('#demo-button').onclick = () => playDemo();
$('#demo-fix').onclick = () => playDemo(true);
$('#close-demo').onclick = () => $('#demo-dialog').close();
$('#demo-dialog').addEventListener('close', () => { clearTimeout(demoTimer); demoGeneration++; });
$('#import-button').onclick = () => $('#import-file').click();
$('#import-file').addEventListener('change', async event => {
  const file = event.target.files[0]; if (!file) return;
  try {
    if (file.size > 15_000_000) throw Error('Please use an export smaller than 15 MB.');
    hydrate(JSON.parse(await file.text())); toast('Experiment imported locally. No data was uploaded.');
  } catch (error) { toast(`Import failed: ${error.message}`); }
  event.target.value = '';
});
$('#export-button').onclick = () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'}));
  const a = el('a'); a.href = url; a.download = 'pruefstand-experiment.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
};

fetch('data.json').then(response => { if (!response.ok) throw Error(`HTTP ${response.status}`); return response.json(); }).then(hydrate).catch(error => {
  $('.notice').textContent = `Could not load experiment: ${error.message}. Serve this folder over HTTP or import a site-data JSON export.`;
  toast('Experiment unavailable. Use Import run to load a local site-data export.'); route();
});
