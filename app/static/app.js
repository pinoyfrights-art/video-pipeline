const state = { pid: null, settings: {}, voices: [], scenes: [] };

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
  renderSettings();

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
  toast('New project created');
}

async function refreshProject() {
  const p = await api(`/api/projects/${state.pid}`);
  $('pid').textContent = p.id;
  state.scenes = p.scenes || [];
  renderScenes();
  for (const [name, s] of Object.entries(p.stages || {})) {
    if (s.status === 'done') setBadge(name, 'done');
    else if (s.status === 'error') setBadge(name, 'error');
    if (s.status === 'done' && s.result) renderResult(name, s.result);
  }
}

/* ---------------------------------------------------------------- settings */
function renderSettings() {
  const sel = $('set-voice');
  sel.innerHTML = '';
  (state.voices || []).forEach(([id, label]) => {
    const o = document.createElement('option');
    o.value = id; o.textContent = label;
    if (id === state.settings.voice) o.selected = true;
    sel.appendChild(o);
  });
  $('set-rate').value = state.settings.voice_rate || '+0%';
  $('set-pitch').value = state.settings.voice_pitch || '+0Hz';
  $('set-resolution').value = state.settings.resolution || '1920x1080';
  $('set-captions').checked = state.settings.captions !== false;
}

function toggleSettings() { $('settings').classList.toggle('hidden'); }

async function saveSettings() {
  const settings = {
    voice: $('set-voice').value,
    voice_rate: $('set-rate').value,
    voice_pitch: $('set-pitch').value,
    resolution: $('set-resolution').value,
    captions: $('set-captions').checked,
  };
  state.settings = await api('/api/settings', { method: 'POST', body: { settings } });
  toast('Settings saved');
}

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
    const r = await api(`/api/projects/${state.pid}/stages/${stage}/run`, { method: 'POST' });
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
  if (r.scenes && r.scenes.length) {
    r.scenes.forEach((s) => {
      const row = document.createElement('div');
      row.className = 'audio-row';
      row.innerHTML = `<span class="scene-label">${esc(s.scene)}</span>`;
      const a = document.createElement('audio');
      a.controls = true; a.src = s.file;
      row.appendChild(a);
      const d = document.createElement('span');
      d.className = 'dur'; d.textContent = s.duration.toFixed(1) + 's';
      row.appendChild(d);
      el.appendChild(row);
    });
  }
  if (r.combined) {
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
