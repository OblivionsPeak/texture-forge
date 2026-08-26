const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

let STATE = { presets: [], shapes: [], treatments: [], providers: [], provider: 'local',
              preset: 'storm', shape: 'mountains', treatment: 'surface',
              texMode: 'describe', busy: false };

/* ------------------------------------------------------------ helpers */

let toastTimer;
function toast(msg, err) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.toggle('err', !!err);
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), err ? 8000 : 4000);
}

async function api(path, body, isForm) {
  const opt = { method: 'POST' };
  if (isForm) opt.body = body;
  else { opt.headers = { 'Content-Type': 'application/json' }; opt.body = JSON.stringify(body || {}); }
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({ ok: false, error: 'bad response from server' }));
  if (!r.ok || j.ok === false) throw new Error(j.error || ('HTTP ' + r.status));
  return j;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function busy(on, el, label) {
  STATE.busy = on;
  $$('button.primary').forEach((b) => { b.disabled = on; });
  if (on && el) el.innerHTML = `<div class="spin"></div><p>${label || 'Working…'}</p>`;
}

/* ------------------------------------------------------------- engine */

async function refreshStatus() {
  try {
    const s = await (await fetch('/api/status')).json();
    STATE.presets = s.presets;
    STATE.shapes = s.shapes;
    STATE.treatments = s.treatments || [];
    const dot = $('#engineDot');
    dot.className = 'dot ' + (s.comfy_up ? 'up' : 'down');
    $('#engineText').textContent = s.comfy_up
      ? (s.vram ? `FLUX ready · ${s.vram.free_gb}/${s.vram.total_gb} GB free` : 'FLUX ready')
      : 'engine stopped';
    $('#btnStart').disabled = s.comfy_up;
    $('#btnStop').disabled = !s.comfy_up;
    if (!$('#presets').children.length) { renderPresets(); renderShapes(); renderTreatments(); }
  } catch (e) {
    $('#engineText').textContent = 'server unreachable';
  }
}

$('#btnStart').onclick = async () => {
  $('#btnStart').disabled = true;
  $('#engineText').textContent = 'starting ComfyUI (model load takes a minute)…';
  try {
    const r = await api('/api/comfy/start');
    toast(r.message === 'already running' ? 'Engine was already up.' : 'Engine started.');
  } catch (e) { toast(e.message, true); }
  refreshStatus();
};

$('#btnStop').onclick = async () => {
  try {
    await api('/api/comfy/stop');
    toast('Engine stopped — VRAM released for iRacing.');
  } catch (e) { toast(e.message, true); }
  refreshStatus();
};

/* -------------------------------------------------------------- tabs */

$$('.tabs button').forEach((b) => {
  b.onclick = () => {
    $$('.tabs button').forEach((x) => x.classList.remove('on'));
    $$('.tab').forEach((x) => x.classList.remove('on'));
    b.classList.add('on');
    $('#tab-' + b.dataset.tab).classList.add('on');
    if (b.dataset.tab === 'setup') refreshSetup(true);
  };
});

/* ---------------------------------------------------------- textures */

function renderPresets() {
  $('#presets').innerHTML = STATE.presets.map((p) =>
    `<button data-id="${p.id}" title="${p.hint}" class="${p.id === STATE.preset ? 'on' : ''}">
       <b>${p.name}</b><i>${p.hint.split('.')[0]}</i></button>`).join('');
  $$('#presets button').forEach((b) => {
    b.onclick = () => {
      STATE.preset = b.dataset.id;
      $$('#presets button').forEach((x) => x.classList.toggle('on', x === b));
      const p = STATE.presets.find((x) => x.id === STATE.preset);
      $('#color').placeholder = p.color;
      $('#genNote').textContent = p.hint;
    };
  });
  const p = STATE.presets.find((x) => x.id === STATE.preset);
  if (p) { $('#color').placeholder = p.color; $('#genNote').textContent = p.hint; }
}

function resultBlock(r, title) {
  const vr = r.value_range;
  return `
    <div class="pair">
      <figure><img src="${r.url}?t=${Date.now()}" alt="texture">
        <figcaption>${title} — ${r.size[0]}×${r.size[1]}</figcaption></figure>
      <figure><img src="${r.squint_url}?t=${Date.now()}" alt="squint test">
        <figcaption>Squint test — what it looks like at track distance</figcaption></figure>
    </div>
    <div class="verdict ${vr.ok ? 'good' : 'bad'}">
      <b>Value range ${vr.spread}</b> — ${vr.verdict}
    </div>
    <div class="acts">
      <a href="${r.url}" download><button>Download PNG</button></a>
      <button onclick="navigator.clipboard.writeText('${r.file}');">Copy filename</button>
    </div>
    <p class="meta">Saved to <code>out/${r.file}</code>${r.seed ? ` · seed ${r.seed}` : ''}${r.provider ? ` · ${esc(r.provider)}` : ''}</p>`;
}

$('#btnGen').onclick = async () => {
  if (STATE.busy) return;
  const prov = STATE.providers.find((x) => x.id === STATE.provider);
  if (STATE.texMode === 'describe' && !$('#subject').value.trim()) {
    toast('Describe what it is inspired by first.', true); return;
  }
  const el = $('#texResult');
  el.classList.remove('empty');
  busy(true, el, prov && prov.cloud ? 'Forging via GPT Image 2…' : 'Forging… first run also loads the model, so allow a minute.');
  try {
    const describing = STATE.texMode === 'describe';
    const r = await api('/api/generate', {
      provider: STATE.provider,
      quality: $('#quality') ? $('#quality').value : 'high',
      freeform: describing,
      subject: describing ? $('#subject').value : null,
      treatment: STATE.treatment,
      preset: STATE.preset,
      color: $('#color').value || null,
      extra: describing ? null : ($('#extra').value || null),
      width: +$('#genSize').value, height: +$('#genSize').value,
      steps: +$('#steps').value,
      seed: $('#seed').value ? +$('#seed').value : null,
      devignette: $('#devig').checked,
      tile: $('#tile').checked,
      contrast: +$('#contrast').value,
      saturation: +$('#sat').value,
    });
    el.innerHTML = resultBlock(r, 'Texture')
      + (r.prompt ? `<div class="prompt-peek"><b>Prompt sent:</b> ${esc(r.prompt)}</div>` : '');
    toast(r.value_range.ok
      ? 'Forged. This one will read at distance.'
      : 'Forged — but the value range is low, so it may go flat on track. Try raising contrast.');
  } catch (e) {
    el.innerHTML = `<p style="color:var(--bad);max-width:52ch">${e.message}</p>`;
    toast(e.message, true);
  }
  busy(false);
};

function renderTreatments() {
  $('#treatments').innerHTML = STATE.treatments.map((t) =>
    `<button data-id="${t.id}" title="${t.hint}" class="${t.id === STATE.treatment ? 'on' : ''}">
       <b>${t.name}</b><i>${t.hint.split('.')[0]}</i></button>`).join('');
  $$('#treatments button').forEach((b) => {
    b.onclick = () => {
      STATE.treatment = b.dataset.id;
      $$('#treatments button').forEach((x) => x.classList.toggle('on', x === b));
      const t = STATE.treatments.find((x) => x.id === STATE.treatment);
      if (t) $('#genNote').textContent = t.hint;
    };
  });
}

$$('#texMode button').forEach((b) => {
  b.onclick = () => { STATE.texMode = b.dataset.m; applyTexMode(); };
});

/* -------------------------------------------------------- silhouettes */

const SHAPE_OPTS = {
  mountains: [['layers', 'Ranges', 1, 6, 1, 4], ['roughness', 'Roughness', 0.2, 2, 0.1, 1],
              ['sharpness', 'Peakiness', 0.6, 3, 0.1, 1.6]],
  treeline: [['rows', 'Rows', 1, 4, 1, 2], ['density', 'Density', 0.3, 2.5, 0.1, 1],
             ['scale', 'Tree size', 0.4, 2, 0.1, 1]],
  skyline: [['density', 'Density', 0.3, 2.5, 0.1, 1]],
  stripes: [['count', 'Stripes', 2, 20, 1, 7], ['angle', 'Angle', -45, 45, 1, 18]],
};

function renderShapes() {
  $('#shapes').innerHTML = STATE.shapes.map((s) =>
    `<button data-id="${s.id}" title="${s.hint}" class="${s.id === STATE.shape ? 'on' : ''}">
       <b>${s.name}</b><i>${s.hint.split('.')[0]}</i></button>`).join('');
  $$('#shapes button').forEach((b) => {
    b.onclick = () => {
      STATE.shape = b.dataset.id;
      $$('#shapes button').forEach((x) => x.classList.toggle('on', x === b));
      renderShapeOpts();
    };
  });
  renderShapeOpts();
}

function renderShapeOpts() {
  const opts = SHAPE_OPTS[STATE.shape] || [];
  $('#shapeOpts').innerHTML = opts.map(([k, label, min, max, step, val]) =>
    `<label class="row"><span>${label}</span>
       <input data-k="${k}" type="range" min="${min}" max="${max}" step="${step}" value="${val}"></label>`).join('');
}

$('#btnShape').onclick = async () => {
  if (STATE.busy) return;
  const el = $('#shapeResult');
  el.classList.remove('empty');
  busy(true, el, 'Drawing…');
  const body = {
    shape: STATE.shape,
    width: +$('#sWidth').value, height: +$('#sHeight').value,
    seed: $('#sSeed').value ? +$('#sSeed').value : null,
  };
  $$('#shapeOpts input').forEach((i) => { body[i.dataset.k] = +i.value; });
  try {
    const r = await api('/api/silhouette', body);
    el.innerHTML = `
      <figure style="margin:0;max-width:100%">
        <img src="${r.url}?t=${Date.now()}" alt="silhouette">
        <figcaption style="font-size:11px;color:var(--mute);margin-top:6px">${r.size[0]}×${r.size[1]} · ${r.note}</figcaption>
      </figure>
      <div class="acts"><a href="${r.url}" download><button>Download PNG</button></a></div>
      <p class="meta">Saved to <code>out/${r.file}</code> · seed ${r.seed}</p>`;
    toast('Drawn. Alpha-only, so recolour it in Clearcoat.');
  } catch (e) {
    el.innerHTML = `<p style="color:var(--bad)">${e.message}</p>`;
    toast(e.message, true);
  }
  busy(false);
};

/* -------------------------------------------------------- squint check */

$('#btnCheck').onclick = async () => {
  const f = $('#checkFile').files[0];
  if (!f) { toast('Choose an image first.', true); return; }
  const el = $('#checkResult');
  el.classList.remove('empty');
  busy(true, el, 'Measuring…');
  try {
    const fd = new FormData();
    fd.append('image', f);
    fd.append('mode', $('#checkMode').value);
    const r = await api('/api/analyze', fd, true);
    const vr = r.value_range;
    el.innerHTML = `
      <figure style="margin:0;max-width:100%">
        <img src="${r.squint_url}?t=${Date.now()}" alt="squint">
        <figcaption style="font-size:11px;color:var(--mute);margin-top:6px">At track distance</figcaption>
      </figure>
      <div class="verdict ${vr.ok ? 'good' : 'bad'}">
        <b>Value range ${vr.spread}</b> — ${vr.verdict}<br><span class="meta">measured on ${vr.scope || 'whole image'}</span>
      </div>`;
  } catch (e) {
    el.innerHTML = `<p style="color:var(--bad)">${e.message}</p>`;
    toast(e.message, true);
  }
  busy(false);
};

/* ------------------------------------------------------------- providers */

async function loadProviders() {
  try {
    const d = await (await fetch('/api/providers')).json();
    STATE.providers = d.providers;
    renderProviders();
  } catch (e) { /* engine list is not critical to the rest of the UI */ }
}

function renderProviders() {
  $('#providers').innerHTML = STATE.providers.map((p) =>
    `<button data-id="${p.id}" title="${esc(p.hint)}" class="${p.id === STATE.provider ? 'on' : ''}">
       <b>${esc(p.name)}</b><i>${p.cloud ? 'cloud · paid' : 'local · free'}</i></button>`).join('');
  $$('#providers button').forEach((b) => {
    b.onclick = () => {
      STATE.provider = b.dataset.id;
      $$('#providers button').forEach((x) => x.classList.toggle('on', x === b));
      applyProvider();
    };
  });
  applyProvider();
}

function applyProvider() {
  const p = STATE.providers.find((x) => x.id === STATE.provider);
  if (!p) return;
  $('#provNote').textContent = p.hint;
  $('#genSize').innerHTML = p.sizes.map((sz, i) =>
    `<option value="${sz}"${i === 0 ? ' selected' : ''}>${sz} × ${sz}</option>`).join('');
  $$('.cloudOnly').forEach((e) => e.classList.toggle('hidden', !p.cloud));
  $$('.localOnly').forEach((e) => e.classList.toggle('hidden', p.cloud));
}

$('#btnKey').onclick = async () => {
  const v = $('#oaiKey').value.trim();
  if (!v) { toast('Paste a key first.', true); return; }
  $('#btnKey').disabled = true;
  try {
    const r = await api('/api/providers/key', { openai_api_key: v });
    toast(r.message);
    $('#oaiKey').value = '';
    loadProviders();
  } catch (e) { toast(e.message, true); }
  $('#btnKey').disabled = false;
};

/* ---------------------------------------------------------------- setup */

function gb(n) { return (n / 2 ** 30).toFixed(1) + ' GB'; }

function row(state, title, detail) {
  const ic = { ok: '✓', no: '✕', warn: '!' }[state];
  return `<div class="check-row ${state}"><span class="ic">${ic}</span>
    <div><b>${title}</b><span>${detail}</span></div></div>`;
}

let setupTimer = null;

async function refreshSetup(showSpinner) {
  const el = $('#setupResult');
  if (showSpinner) el.innerHTML = '<div class="spin"></div>';
  let s;
  try { s = await (await fetch('/api/setup')).json(); }
  catch (e) { el.innerHTML = `<p style="color:var(--bad)">${esc(e.message)}</p>`; return; }

  const rows = [];
  rows.push(s.comfy_found
    ? row('ok', 'ComfyUI found', `<code>${esc(s.comfy_dir)}</code>`)
    : row('no', 'ComfyUI not found',
        `Looked in the usual places without luck. Install ComfyUI, then press Re-check. ` +
        `If it lives somewhere unusual, set a <code>COMFYUI_DIR</code> environment variable pointing at it.`));

  if (s.comfy_found) {
    rows.push(s.comfy_venv
      ? row('ok', 'ComfyUI has its own Python', 'Its venv will be used to launch it.')
      : row('warn', 'No venv found inside ComfyUI',
          'It will be launched with the system Python, which usually lacks torch. ' +
          'Running ComfyUI once on its own normally creates the venv.'));

    rows.push(s.model_ready
      ? row('ok', `FLUX model ready (${esc(s.layout)} layout)`,
          s.layout === 'checkpoint'
            ? 'Single all-in-one checkpoint.'
            : 'Separate UNet, text encoders and VAE.')
      : row('no', 'FLUX model missing',
          'About 16 GB, downloaded and verified for you. Press <b>Download model</b>.'));

    rows.push(row(s.free_disk_gb > 20 ? 'ok' : 'warn', `${s.free_disk_gb} GB free on that drive`,
      s.free_disk_gb > 20 ? 'Enough room for the model.' : 'The model needs roughly 16 GB plus headroom.'));

    rows.push(s.running
      ? row('ok', 'Engine running', 'Ready to forge. Stop it before racing to free VRAM.')
      : row('warn', 'Engine stopped', 'Press <b>Start engine</b> in the header when you want to generate.'));
  }

  const p = s.progress || {};
  let prog = '';
  if (p.active || p.error || (p.finished && p.percent === 100)) {
    const pct = p.percent || 0;
    prog = `<div class="bar-out"><div class="bar-in" style="width:${pct}%"></div></div>
      <p class="meta">${esc(p.file || '')} ${p.total ? `${gb(p.done)} / ${gb(p.total)}` : ''}
      ${p.speed ? `· ${gb(p.speed)}/s` : ''} ${p.message ? `· ${esc(p.message)}` : ''}</p>`;
    if (p.error) prog += `<div class="verdict bad"><b>Download failed</b> — ${esc(p.error)}</div>`;
  }

  el.classList.remove('empty');
  el.innerHTML = `<div class="checks">${rows.join('')}</div>${prog}`;
  $('#btnInstall').disabled = !s.comfy_found || s.model_ready || p.active;
  $('#setupNote').textContent = s.model_ready
    ? 'Everything is in place.'
    : (p.active ? 'Downloading — you can leave this tab open.' : '');

  clearTimeout(setupTimer);
  if (p.active) setupTimer = setTimeout(() => refreshSetup(false), 1000);
}

$('#btnRecheck').onclick = () => refreshSetup(true);
$('#btnInstall').onclick = async () => {
  $('#btnInstall').disabled = true;
  try {
    const r = await api('/api/setup/install', { kind: 'checkpoint' });
    toast(r.message);
  } catch (e) { toast(e.message, true); }
  refreshSetup(false);
};

function applyTexMode() {
  const describing = STATE.texMode === 'describe';
  $$('#texMode button').forEach((x) => x.classList.toggle('on', (x.dataset.m === 'describe') === describing));
  $('#describeBox').classList.toggle('hidden', !describing);
  $('#presetBox').classList.toggle('hidden', describing);
  $$('.presetOnly').forEach((e) => e.classList.toggle('hidden', describing));
}

applyTexMode();
loadProviders();
refreshStatus();
setInterval(refreshStatus, 15000);
