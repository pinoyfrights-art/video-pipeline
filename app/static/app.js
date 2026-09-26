const state = {
  pid: null,
  settings: {},
  voices: [],
  scenes: [],
  voiceChoice: null,
  genderFilter: 'All',
  ageFilter: 'All',
  accentFilter: 'All',
  previewAudio: null,
  archive: [],
  styles: [],
  visualStyle: 'stock',
};

const STAGES = ['voiceover', 'visuals', 'audio', 'assembly'];
const IMPLEMENTED = ['voiceover', 'visuals', 'audio', 'assembly'];

const EXAMPLE = `visual: golden retriever puppy running in a park
sfx: playful dog bark
music: upbeat acoustic
Golden retrievers are one of the friendliest dog breeds in the world.
They were originally bred in Scotland to retrieve game for hunters.

visual: golden retriever swimming in a lake
sfx: water splash
Golden retrievers love water, and their water-repellent coats keep them warm.
Today they are popular family pets, guide dogs, and search-and-rescue dogs.`;

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || 'GET',
    headers: { 'Content-Type': 'application/json' },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { const d = await res.json(); detail = d.detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.json();
}

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._t);
  t._t = setTimeout(() => t.classList.remove('show'), 2600);
}

/* ---------------------------------------------------------------- init */
async function init() {
  try { state.settings = await api('/api/settings'); } catch {}
  try { state.voices = await api('/api/voices'); } catch {}
  try { state.styles = await api('/api/styles'); } catch {}
  renderSettings();
  loadArchive();

  const saved = localStorage.getItem('vp_pid');
  if (saved) {
    state.pid = saved;
    try { await refreshProject(); return; } catch {}
  }
  await newProject();
}

async function newProject() {
  const p = await api('/api/projects', { method: 'POST' });
  state.pid = p.id;
  localStorage.setItem('vp_pid', state.pid);
  $('pid').textContent = p.id;
  state.scenes = [];
  renderScenes();
  resetStages();
  loadArchive();
  toast('New project created');
}

async function refreshProject() {
  const p = await api(`/api/projects/${state.pid}`);
  $('pid').textContent = p.id;
  $('script').value = p.script || '';
  state.scenes = p.scenes || [];
  renderScenes();
  resetStages();
  for (const [name, s] of Object.entries(p.stages || {})) {
    if (s.status === 'done') setBadge(name, 'done');
    else if (s.status === 'error') setBadge(name, 'error');
    if (s.status === 'done' && s.result) renderResult(name, s.result);
  }
}

/* ---------------------------------------------------------------- settings */
function renderSettings() {
  state.voiceChoice = state.settings.voice || 'en-US-AriaNeural';
  renderVoiceTrigger();
  populateAccentOptions();
  $('set-rate').value = state.settings.voice_rate || '+0%';
  $('set-pitch').value = state.settings.voice_pitch || '+0Hz';
  $('set-resolution').value = state.settings.resolution || '1920x1080';
  $('set-captions').checked = state.settings.captions !== false;
  state.visualStyle = state.settings.visual_style || 'stock';
  renderVisualStyles();
  $('set-openrouter-key').value = state.settings.openrouter_api_key || '';
  $('set-openrouter-model').value = state.settings.openrouter_image_model || 'black-forest-labs/flux-schnell';
  $('set-renderer').value = state.settings.renderer || 'remotion';
}

function renderVisualStyles() {
  const sel = $('visual-style');
  if (!sel) return;
  sel.innerHTML = '';
  (state.styles || []).forEach((s) => {
    const o = document.createElement('option');
    o.value = s.id;
    o.textContent = s.name + (s.needs_key ? ' (AI)' : '');
    o.title = s.description;
    if (s.id === state.visualStyle) o.selected = true;
    sel.appendChild(o);
  });
}

async function onVisualStyleChange() {
  state.visualStyle = $('visual-style').value;
  try {
    await api('/api/settings', { method: 'POST', body: { settings: { visual_style: state.visualStyle } } });
  } catch {}
}

function toggleMenu() {
  const panel = $('menu-panel');
  const willOpen = panel.classList.contains('hidden');
  panel.classList.toggle('hidden');
  if (willOpen) loadArchive();
}

function switchTab(name) {
  const map = {
    settings: ['tab-settings', 'pane-settings'],
    archive: ['tab-archive', 'pane-archive'],
  };
  Object.entries(map).forEach(([key, [tabId, paneId]]) => {
    const active = key === name;
    $(tabId).classList.toggle('active', active);
    $(paneId).classList.toggle('hidden', !active);
  });
  if (name === 'archive') loadArchive();
}

// Close the menu when clicking outside of it
document.addEventListener('click', (e) => {
  const panel = $('menu-panel');
  const btn = $('menu-btn');
  if (!panel.classList.contains('hidden') && !panel.contains(e.target) && !btn.contains(e.target)) {
    panel.classList.add('hidden');
  }
});

async function saveSettings() {
  const settings = {
    voice: state.voiceChoice || 'en-US-AriaNeural',
    voice_rate: $('set-rate').value,
    voice_pitch: $('set-pitch').value,
    resolution: $('set-resolution').value,
    captions: $('set-captions').checked,
    visual_style: state.visualStyle,
    openrouter_api_key: $('set-openrouter-key').value.trim(),
    openrouter_image_model: $('set-openrouter-model').value.trim(),
    renderer: $('set-renderer').value,
  };
  state.settings = await api('/api/settings', { method: 'POST', body: { settings } });
  toast('Settings saved');
}

/* ---------------------------------------------------------------- archive */
async function loadArchive() {
  try { state.archive = await api('/api/projects'); } catch { state.archive = []; }
  renderArchive();
}

function renderArchive() {
  const list = $('archive-list');
  const delAll = $('archive-delete-all');
  list.innerHTML = '';
  const projects = state.archive || [];
  if (!projects.length) {
    const empty = document.createElement('div');
    empty.className = 'archive-empty';
    empty.textContent = 'No saved projects yet.';
    list.appendChild(empty);
    if (delAll) delAll.disabled = true;
    return;
  }
  if (delAll) delAll.disabled = false;
  projects.forEach((p) => {
    const done = Object.values(p.stages || {}).filter((s) => s === 'done').length;
    const total = Object.keys(p.stages || {}).length;
    const date = new Date((p.created_at || 0) * 1000).toLocaleString();
    const current = p.id === state.pid;

    const row = document.createElement('div');
    row.className = 'archive-item';

    const meta = document.createElement('div');
    meta.className = 'archive-meta';
    meta.innerHTML = `<span class="archive-title">${esc(p.id)}${current ? ' <em class="cur">(current)</em>' : ''}</span>
      <span class="archive-sub">${esc(date)} · ${p.scenes} scene(s) · ${done}/${total} stages done</span>`;

    const openBtn = document.createElement('button');
    openBtn.className = 'btn';
    openBtn.textContent = 'Open';
    openBtn.disabled = current;
    openBtn.addEventListener('click', () => openProject(p.id));

    const delBtn = document.createElement('button');
    delBtn.className = 'btn danger';
    delBtn.textContent = 'Delete';
    delBtn.addEventListener('click', () => deleteProject(p.id));

    row.appendChild(meta);
    row.appendChild(openBtn);
    row.appendChild(delBtn);
    list.appendChild(row);
  });
}

async function openProject(pid) {
  state.pid = pid;
  localStorage.setItem('vp_pid', pid);
  await refreshProject();
  loadArchive();
  toast(`Opened ${pid}`);
}

async function deleteProject(pid) {
  if (!confirm(`Delete project ${pid}? This permanently removes all its files.`)) return;
  await api(`/api/projects/${pid}`, { method: 'DELETE' });
  toast(`Deleted ${pid}`);
  if (pid === state.pid) await newProject();
  else loadArchive();
}

async function deleteAllProjects() {
  const n = (state.archive || []).length;
  if (!n) return;
  if (!confirm(`Delete ALL ${n} project(s)? This permanently removes all their files.`)) return;
  await api('/api/projects', { method: 'DELETE' });
  toast(`Deleted ${n} project(s)`);
  await newProject();
}

/* ---------------------------------------------------------------- voice picker */
function voiceById(id) { return (state.voices || []).find((v) => v.id === id); }

function voiceLabel(v) { return `${v.name} · ${v.accent} · ${v.gender}`; }

function renderVoiceTrigger() {
  const v = voiceById(state.voiceChoice);
  const el = $('voice-current');
  if (el) el.textContent = v ? voiceLabel(v) : '';
}

function populateAccentOptions() {
  const sel = $('voice-accent');
  const accents = [...new Set((state.voices || []).map((v) => v.accent))].sort();
  sel.innerHTML = '<option value="All">All accents</option>';
  accents.forEach((a) => {
    const o = document.createElement('option');
    o.value = a; o.textContent = a;
    if (a === state.accentFilter) o.selected = true;
    sel.appendChild(o);
  });
}

function setGenderFilter(btn) {
  state.genderFilter = btn.dataset.g;
  document.querySelectorAll('#voice-gender .chip').forEach((c) => c.classList.remove('active'));
  btn.classList.add('active');
  renderVoiceList();
}

function setAgeFilter(btn) {
  state.ageFilter = btn.dataset.a;
  document.querySelectorAll('#voice-age .chip').forEach((c) => c.classList.remove('active'));
  btn.classList.add('active');
  renderVoiceList();
}

function openVoicePicker() {
  $('voice-modal').classList.remove('hidden');
  $('voice-search').value = '';
  renderVoiceList();
  $('voice-search').focus();
}

function closeVoicePicker() {
  $('voice-modal').classList.add('hidden');
  stopPreview();
}

function renderVoiceList() {
  const q = ($('voice-search').value || '').toLowerCase().trim();
  state.accentFilter = $('voice-accent').value;
  const list = $('voice-list');
  list.innerHTML = '';

  const matches = (state.voices || []).filter((v) => {
    if (state.genderFilter !== 'All' && v.gender !== state.genderFilter) return false;
    if (state.ageFilter !== 'All' && v.age !== state.ageFilter) return false;
    if (state.accentFilter !== 'All' && v.accent !== state.accentFilter) return false;
    if (q) {
      const hay = `${v.name} ${v.gender} ${v.accent} ${v.age} ${v.persona}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  if (!matches.length) {
    const empty = document.createElement('div');
    empty.className = 'voice-empty';
    empty.textContent = 'No voices match your filters.';
    list.appendChild(empty);
    return;
  }

  matches.forEach((v) => {
    const row = document.createElement('div');
    row.className = 'voice-item' + (v.id === state.voiceChoice ? ' selected' : '');
    row.innerHTML = `
      <button class="vplay" title="Preview" data-id="${esc(v.id)}">▶</button>
      <div class="vmeta">
        <span class="vname">${esc(v.name)}</span>
        <span class="vsub">${esc(v.gender)} · ${esc(v.accent)} · ${esc(v.age)}</span>
      </div>
      <span class="vpersona">${esc(v.persona)}</span>
    `;
    row.addEventListener('click', (e) => {
      if (e.target.classList.contains('vplay')) return;
      selectVoice(v.id);
    });
    list.appendChild(row);
  });
}

function selectVoice(id) {
  state.voiceChoice = id;
  renderVoiceTrigger();
  renderVoiceList();
  closeVoicePicker();
  saveSettings().then(() => toast(`Voice saved: ${voiceLabel(voiceById(id))}`));
}

async function previewVoice(id) {
  stopPreview();
  const btn = document.querySelector(`.vplay[data-id="${CSS.escape(id)}"]`);
  if (btn) btn.textContent = '…';
  try {
    const r = await api('/api/voices/preview', { method: 'POST', body: { voice: id } });
    const a = new Audio(r.url);
    state.previewAudio = a;
    a.onended = () => { if (btn) btn.textContent = '▶'; state.previewAudio = null; };
    a.play();
    if (btn) btn.textContent = '■';
  } catch (e) {
    if (btn) btn.textContent = '▶';
    toast(`Preview failed: ${e.message || e}`);
  }
}

function stopPreview() {
  if (state.previewAudio) {
    state.previewAudio.pause();
    state.previewAudio = null;
  }
  document.querySelectorAll('.vplay').forEach((b) => { b.textContent = '▶'; });
}

// Attach preview handler via delegation on the voice list
document.addEventListener('click', (e) => {
  if (e.target.classList && e.target.classList.contains('vplay')) {
    e.stopPropagation();
    previewVoice(e.target.dataset.id);
  }
});

/* ---------------------------------------------------------------- script */
function loadExample() { $('script').value = EXAMPLE; }

async function saveScript() {
  const script = $('script').value.trim();
  if (!script) { toast('Paste a script first'); return; }
  const p = await api(`/api/projects/${state.pid}/script`, { method: 'POST', body: { script } });
  state.scenes = p.scenes || [];
  renderScenes();
  for (const s of STAGES) { setBadge(s, 'pending'); clearOutput(s); }
  setBadge('script', 'done');
  toast(`Stage 1 done: ${state.scenes.length} scene(s) parsed`);
}

function renderScenes() {
  const wrap = $('scenes');
  wrap.innerHTML = '';
  $('scenes-card').classList.toggle('hidden', state.scenes.length === 0);
  $('scenes-count').textContent = `${state.scenes.length} scene(s)`;
  state.scenes.forEach((sc) => {
    const div = document.createElement('div');
    div.className = 'scene';
    div.innerHTML = `
      <span class="idx">${sc.index}</span>
      <div class="meta">
        <p class="narration">${esc(sc.narration || '<em>no narration</em>')}</p>
        ${sc.visual ? `<p class="visual">🎬 ${esc(sc.visual)}</p>` : ''}
        ${sc.sfx ? `<p class="visual">🔊 ${esc(sc.sfx)}</p>` : ''}
      </div>
      ${sc.audio_duration ? `<span class="dur">${sc.audio_duration}s</span>` : ''}
    `;
    wrap.appendChild(div);
  });
}

/* ---------------------------------------------------------------- stages */
function setBadge(stage, status, text) {
  const b = $(`badge-${stage}`);
  if (!b) return;
  b.className = `badge ${status}`;
  b.textContent = text || status;
}

function setBusy(stage, busy) {
  $(`run-${stage}`).disabled = busy;
  $(`run-all`).disabled = busy;
}

function setProgress(stage, p) { $(`prog-${stage}`).style.width = p + '%'; }

function clearOutput(stage) {
  $(`result-${stage}`).innerHTML = '';
  $(`log-${stage}`).innerHTML = '';
  $(`log-${stage}`).classList.remove('visible');
  $(`prog-${stage}`).style.width = '0%';
}

function resetStages() {
  for (const s of STAGES) {
    setBadge(s, 'pending', 'pending');
    clearOutput(s);
  }
}

function appendLog(stage, msg, isErr) {
  const el = $(`log-${stage}`);
  el.classList.add('visible');
  const line = document.createElement('div');
  if (isErr) line.className = 'err';
  line.textContent = msg;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
}

async function runStage(stage) {
  setBusy(stage, true);
  setBadge(stage, 'running');
  clearOutput(stage);
  try {
    let url = `/api/projects/${state.pid}/stages/${stage}/run`;
    if (stage === 'visuals') {
      state.visualStyle = $('visual-style').value || 'stock';
      url += `?style=${encodeURIComponent(state.visualStyle)}`;
    }
    const r = await api(url, { method: 'POST' });
    await pollJob(r.job_id, stage);
    await refreshProject();
  } catch (e) {
    setBadge(stage, 'error');
    appendLog(stage, e.message || String(e), true);
    toast(`Stage failed: ${e.message || e}`);
  } finally {
    setBusy(stage, false);
  }
}

async function pollJob(jobId, stage) {
  let last = 0;
  for (;;) {
    const j = await api(`/api/jobs/${jobId}`);
    for (let i = last; i < j.log.length; i++) appendLog(stage, j.log[i].msg);
    last = j.log.length;
    setProgress(stage, j.progress);
    if (j.status === 'done') {
      renderResult(stage, j.result);
      setBadge(stage, 'done');
      return;
    }
    if (j.status === 'error') {
      const tail = (j.error || 'Stage failed').trim().split('\n').slice(-1)[0];
      appendLog(stage, j.error || '', true);
      throw new Error(tail);
    }
    await sleep(600);
  }
}

async function runAll() {
  for (const stage of IMPLEMENTED) { await runStage(stage); }
  toast('Run all complete');
}

/* ---------------------------------------------------------------- results */
function renderResult(stage, result) {
  const el = $(`result-${stage}`);
  el.innerHTML = '';
  if (!result) return;
  if (stage === 'voiceover') renderVoiceover(el, result);
  else if (stage === 'visuals') renderVisuals(el, result);
  else if (stage === 'audio') renderAudio(el, result);
  else if (stage === 'assembly') renderAssembly(el, result);
}

function renderVoiceover(el, r) {
  if (!r || !r.combined) return;
  const row = document.createElement('div');
  row.className = 'audio-row';
  row.innerHTML = `<span class="scene-label">Full narration</span>`;
  const a = document.createElement('audio');
  a.controls = true; a.src = r.combined;
  row.appendChild(a);
  if (r.total_duration) {
    const d = document.createElement('span');
    d.className = 'dur'; d.textContent = r.total_duration.toFixed(1) + 's';
    row.appendChild(d);
  }
  el.appendChild(row);
}

function renderVisuals(el, r) {
  if (!r.scenes || !r.scenes.length) return;
  const grid = document.createElement('div');
  grid.className = 'thumb-grid';
  r.scenes.forEach((s) => {
    const card = document.createElement('div');
    card.className = 'thumb';
    let media = '';
    if (s.type === 'video') {
      media = `<video controls preload="metadata" src="${esc(s.clip)}"${s.image ? ` poster="${esc(s.image)}"` : ''}></video>`;
    } else if (s.type === 'image') {
      media = `<img src="${esc(s.image)}" alt="${esc(s.scene)}" loading="lazy">`;
    } else {
      media = `<div class="cap none">⚠ no visual (${esc(s.reason || 'unknown')})</div>`;
    }
    const bits = [s.source_title, s.author && `by ${s.author}`, s.license].filter(Boolean).join(' · ');
    const cap = bits ? `${s.source || ''}${s.source ? ' — ' : ''}${bits}` : '';
    card.innerHTML = media + `<div class="cap">${esc(s.scene)}${cap ? ' · ' + esc(cap) : ''}</div>`;
    grid.appendChild(card);
  });
  el.appendChild(grid);
}
function renderAudio(el, r) {
  if (!r) return;
  if (r.music) {
    const row = document.createElement('div');
    row.className = 'audio-row';
    row.innerHTML = `<span class="scene-label">🎵 Music</span>`;
    const a = document.createElement('audio');
    a.controls = true; a.loop = true; a.src = r.music.file;
    row.appendChild(a);
    const d = document.createElement('span');
    d.className = 'dur'; d.textContent = (r.music.duration || 0).toFixed(1) + 's';
    row.appendChild(d);
    el.appendChild(row);
    const cap = document.createElement('div');
    cap.className = 'hint';
    cap.textContent = [r.music.source_title, r.music.author && `by ${r.music.author}`, r.music.license].filter(Boolean).join(' · ')
      || (r.music.procedural ? 'procedurally generated' : '');
    el.appendChild(cap);
  }
  (r.sfx || []).forEach((s) => {
    const row = document.createElement('div');
    row.className = 'audio-row';
    row.innerHTML = `<span class="scene-label">🔊 ${esc(s.scene)}</span>`;
    const a = document.createElement('audio');
    a.controls = true; a.src = s.file;
    row.appendChild(a);
    const d = document.createElement('span');
    d.className = 'dur'; d.textContent = (s.duration || 0).toFixed(1) + 's';
    row.appendChild(d);
    el.appendChild(row);
  });
}
function renderAssembly(el, r) {
  if (!r || !r.final) return;
  const row = document.createElement('div');
  row.className = 'video-row';
  const v = document.createElement('video');
  v.controls = true; v.src = r.final;
  row.appendChild(v);
  el.appendChild(row);
  const cap = document.createElement('div');
  cap.className = 'hint';
  cap.textContent = `Final video · ${r.duration.toFixed(1)}s · ${r.scenes} scene(s) · ${r.resolution}`;
  el.appendChild(cap);
  const link = document.createElement('a');
  link.className = 'btn';
  link.href = r.final;
  link.setAttribute('download', '');
  link.textContent = '⬇ Download final video';
  el.appendChild(link);
}

/* ---------------------------------------------------------------- utils */
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

init();
