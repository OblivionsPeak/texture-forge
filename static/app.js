const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

let STATE = { presets: [], shapes: [], treatments: [], styles: [], providers: [], provider: 'local', style: 'woodblock',
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
    STATE.styles = s.styles || [];
    const dot = $('#engineDot');
    dot.className = 'dot ' + (s.comfy_up ? 'up' : 'down');
    $('#engineText').textContent = s.comfy_up
      ? (s.vram ? `FLUX ready · ${s.vram.free_gb}/${s.vram.total_gb} GB free` : 'FLUX ready')
      : 'engine stopped';
    $('#btnStart').disabled = s.comfy_up;
    $('#btnStop').disabled = !s.comfy_up;
    if (!$('#presets').children.length) { renderPresets(); renderShapes(); renderTreatments(); renderStyles(); }
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

function decalBlock(r) {
  const cut = r.cutout > 0
    ? `background removed (${r.cutout}% of frame)`
    : (r.transparent ? 'returned with transparency' : 'no flat background found to remove');
  return `
    <figure style="margin:0;max-width:100%">
      <img src="${r.url}?t=${Date.now()}" alt="decal"
           style="background:repeating-conic-gradient(#2a2f3a 0 25%,#20242c 0 50%) 0 0/22px 22px">
      <figcaption style="font-size:11px;color:var(--mute);margin-top:6px">
        ${r.size[0]}×${r.size[1]} · ${esc(cut)}</figcaption>
    </figure>
    <div class="acts"><a href="${r.url}" download><button>Download PNG</button></a></div>`;
}

function resultBlock(r, title) {
  const vr = r.value_range || { spread: '—', verdict: 'not measured', ok: true };
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
  const single = STATE.texMode === 'single';
  if (STATE.texMode === 'describe' && !$('#subject').value.trim()) {
    toast('Describe what it is inspired by first.', true); return;
  }
  if (single && !$('#subjectSingle').value.trim()) {
    toast('Say what the image should be first.', true); return;
  }
  const el = $('#texResult');
  el.classList.remove('empty');
  busy(true, el, prov && prov.cloud ? 'Forging via GPT Image 2…' : 'Forging… first run also loads the model, so allow a minute.');
  try {
    const describing = STATE.texMode === 'describe';
    const r = await api('/api/generate', {
      kind: single ? 'decal' : 'texture',
      subject: single ? $('#subjectSingle').value : (describing ? $('#subject').value : null),
      style: STATE.style,
      provider: STATE.provider,
      quality: $('#quality') ? $('#quality').value : 'high',
      freeform: describing,
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
    el.innerHTML = (single ? decalBlock(r) : resultBlock(r, 'Texture'))
      + (r.prompt ? `<div class="prompt-peek"><b>Prompt sent:</b> ${esc(r.prompt)}</div>` : '');
    // A decal has no value range: the metric predicts how a SURFACE reads at
    // distance, which says nothing useful about a cut-out badge. Reading it
    // unconditionally crashed Single image mode after every successful
    // generation - the file was written, only the result rendering blew up.
    if (single) {
      toast(r.cutout > 0
        ? `Forged. Background removed (${r.cutout}% of frame).`
        : (r.transparent
            ? 'Forged with a transparent background.'
            : 'Forged — no flat background was found to remove, so it came back opaque.'));
    } else if (r.value_range) {
      toast(r.value_range.ok
        ? 'Forged. This one will read at distance.'
        : 'Forged — but the value range is low, so it may go flat on track. Try raising contrast.');
    } else {
      toast('Forged.');
    }
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

function renderStyles() {
  const box = $('#styles');
  if (!box) return;
  box.innerHTML = STATE.styles.map((t) =>
    `<button data-id="${t.id}" title="${esc(t.hint)}" class="${t.id === STATE.style ? 'on' : ''}">
       <b>${esc(t.name)}</b><i>${esc(t.hint.split('.')[0])}</i></button>`).join('');
  $$('#styles button').forEach((b) => {
    b.onclick = () => {
      STATE.style = b.dataset.id;
      $$('#styles button').forEach((x) => x.classList.toggle('on', x === b));
    };
  });
}

function applyTexMode() {
  const m = STATE.texMode;
  $$('#texMode button').forEach((x) => x.classList.toggle('on', x.dataset.m === m));
  $('#describeBox').classList.toggle('hidden', m !== 'describe');
  $('#presetBox').classList.toggle('hidden', m !== 'preset');
  $('#singleBox').classList.toggle('hidden', m !== 'single');
  $$('.presetOnly').forEach((e) => e.classList.toggle('hidden', m !== 'preset'));
  // Tiling and vignette controls make no sense for a cut-out decal.
  $$('.textureOnly').forEach((e) => e.classList.toggle('hidden', m === 'single'));
}

/* -------------------------------------------------------------- concept */

const C = { style: 'vinyl', provider: 'local', wordmark: null, job: null, timer: null, suggestTimer: null, lastTheme: null };

function renderConceptStyles() {
  const box = $('#cStyles');
  if (!box || !STATE.styles.length) return;
  box.innerHTML = STATE.styles.map((t) =>
    `<button data-id="${t.id}" title="${esc(t.hint)}" class="${t.id === C.style ? 'on' : ''}">
       <b>${esc(t.name)}</b><i>${esc(t.hint.split('.')[0])}</i></button>`).join('');
  $$('#cStyles button').forEach((b) => {
    b.onclick = () => {
      C.style = b.dataset.id;
      $$('#cStyles button').forEach((x) => x.classList.toggle('on', x === b));
    };
  });
}

function renderConceptProviders() {
  const box = $('#cProviders');
  if (!box || !STATE.providers.length) return;
  box.innerHTML = STATE.providers.map((p) =>
    `<button data-id="${p.id}" title="${esc(p.hint)}" class="${p.id === C.provider ? 'on' : ''}">
       <b>${esc(p.name)}</b><i>${p.cloud ? 'cloud · paid · writes text' : 'local · free · no text'}</i></button>`).join('');
  $$('#cProviders button').forEach((b) => {
    b.onclick = () => {
      C.provider = b.dataset.id;
      $$('#cProviders button').forEach((x) => x.classList.toggle('on', x === b));
      conceptProvNote();
    };
  });
  conceptProvNote();
}

function conceptProvNote() {
  const p = STATE.providers.find((x) => x.id === C.provider);
  if (!p) return;
  $('#cProvNote').textContent = p.cloud
    ? 'GPT Image 2 can write the team name onto the render legibly. Each motif is a separate paid image.'
    : 'Local FLUX leaves a blank white panel where the team name goes; the wordmark ships separately. Roughly 40s per image.';
}

async function conceptSuggest(force) {
  const brief = $('#cBrief').value.trim();
  try {
    const r = await api('/api/concept/suggest', { brief });
    if (!$('#cCar').children.length) {
      $('#cCar').innerHTML = r.cars.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
    }
    if (!brief) { $('#cSuggest').textContent = ''; return; }
    const ta = $('#cMotifs');
    // Refill when the box is untouched OR the brief now points at a different
    // theme. Editing the list once used to freeze it for every later brief,
    // which read as "auto-fill stopped working".
    const themeKey = r.theme || '(generic)';
    if (force || !ta.value.trim() || ta.dataset.auto === '1' || C.lastTheme !== themeKey) {
      ta.value = r.motifs.join('\n');
      ta.dataset.auto = '1';
    }
    C.lastTheme = themeKey;
    if (r.palette_hint && !$('#cPalette').value.trim()) $('#cPalette').placeholder = r.palette_hint;
    if (r.style) { C.style = r.style; renderConceptStyles(); }
    $('#cSuggest').innerHTML = (r.theme
      ? `Recognised as "${esc(r.theme)}" — motif list filled in. Edit it freely.`
      : 'No known theme matched. Replace the three generic lines with the motifs you want.')
      + ' <a href="#" id="cRefill">Refill from brief</a>';
    $('#cRefill').onclick = (e) => { e.preventDefault(); conceptSuggest(true); };
  } catch (e) { /* suggestion is a convenience */ }
}

$('#cBrief').addEventListener('input', () => {
  clearTimeout(C.suggestTimer);
  C.suggestTimer = setTimeout(conceptSuggest, 350);
});
$('#cMotifs').addEventListener('input', () => { $('#cMotifs').dataset.auto = '0'; });

$('#cWordmark').addEventListener('change', async () => {
  const f = $('#cWordmark').files[0];
  if (!f) { C.wordmark = null; return; }
  try {
    const fd = new FormData();
    fd.append('image', f);
    const r = await api('/api/concept/wordmark', fd, true);
    C.wordmark = r.file;
    toast('Wordmark will ship in the pack.');
  } catch (e) { C.wordmark = null; toast(e.message, true); }
});

function packBlock(j, motifs) {
  const done = j.done && !j.error;
  const pct = j.total ? Math.round(100 * j.progress / j.total) : 0;
  const status = j.error
    ? `<div class="verdict bad"><b>Failed</b> — ${esc(j.error)}</div>`
    : (done
        ? `<div class="verdict good"><b>Pack built</b> — ${j.assets.length} motif${j.assets.length === 1 ? '' : 's'}${j.render ? ' + render' : ''}${j.wordmark ? ' + wordmark' : ''}. Saved to <code>out/${esc(j.folder)}/</code></div>`
        : `<div class="bar-out"><div class="bar-in" style="width:${pct}%"></div></div>
           <p class="steps"><span class="spin" style="display:inline-block;width:12px;height:12px;vertical-align:middle;margin-right:8px"></span><b>${esc(j.step)}</b> · ${j.progress}/${j.total}</p>`);

  const hero = j.render
    ? `<div class="hero"><img src="${j.render.url}?t=${j.render.seed}" alt="concept render">
         <p class="meta" style="margin-top:6px">Studio render · ${j.render.size[0]}×${j.render.size[1]} · seed ${j.render.seed} · a pitch image, not a paint file</p></div>`
    : (j.step.startsWith('rendering') ? `<div class="hero"><div class="spin"></div><p class="meta">Rendering the car…</p></div>` : '');

  const pal = j.palette && j.palette.length
    ? `<div><h3>Palette</h3><div class="swatches">${j.palette.map((p) =>
        `<div class="swatch" title="click to copy" onclick="navigator.clipboard.writeText('${p.hex}')">
           <i style="background:${p.hex}"></i><b>${p.hex}</b>${p.role ? `<span>${p.role}</span>` : ''}</div>`).join('')}
       </div></div>` : '';

  const doneNames = new Set(j.assets.map((a) => a.subject));
  const cards = motifs.map((m, i) => {
    const a = j.assets.find((x) => x.subject === m);
    if (a) {
      const cut = a.cutout > 0 ? `bg removed ${a.cutout}%` : (a.transparent ? 'transparent' : 'opaque — no flat bg found');
      return `<figure><img src="${a.url}" alt="${esc(m)}">
        <figcaption>${esc(m)}<br><span class="meta">${a.size[0]}×${a.size[1]} · ${cut}</span><br>
        <a href="${a.url}" download>Download</a></figcaption></figure>`;
    }
    return `<figure class="pending"><img alt=""><figcaption>${esc(m)}<br><span class="meta">${j.step.includes(`${i + 1}/`) ? 'forging…' : 'queued'}</span></figcaption></figure>`;
  }).join('');
  const motifBlock = motifs.length ? `<div><h3>Motifs</h3><div class="motifs">${cards}</div></div>` : '';

  const wm = j.wordmark
    ? `<div><h3>Wordmark</h3><div class="motifs"><figure><img src="${j.wordmark.url}" alt="wordmark"><figcaption>${esc(j.wordmark.name)} · passed through untouched</figcaption></figure></div></div>` : '';

  const acts = done
    ? `<div class="acts"><a href="${j.zip}" download><button class="primary">Download pack (.zip)</button></a>
       ${j.render ? `<a href="${j.render.url}" download><button>Render PNG</button></a>` : ''}</div>` : '';

  return `<div class="pack">${status}${hero}${pal}${motifBlock}${wm}${acts}
    ${j.render && j.render.prompt ? `<div class="prompt-peek"><b>Render prompt:</b> ${esc(j.render.prompt)}</div>` : ''}</div>`;
}

$('#btnConcept').onclick = async () => {
  if (STATE.busy) return;
  const brief = $('#cBrief').value.trim();
  if (!brief) { toast('Write the brief first.', true); return; }
  const motifs = $('#cMotifs').value.split('\n').map((s) => s.trim()).filter(Boolean);
  const el = $('#conceptResult');
  el.classList.remove('empty');
  busy(true, el, 'Starting…');
  try {
    const r = await api('/api/concept/start', {
      brief, team: $('#cTeam').value, car: $('#cCar').value,
      palette_hint: $('#cPalette').value, motifs, style: C.style,
      provider: C.provider, quality: 'high', steps: 20,
      render: $('#cRender').checked,
      seed: $('#cSeed').value ? +$('#cSeed').value : null,
      wordmark_file: C.wordmark,
    });
    C.job = r.job;
    const poll = async () => {
      let j;
      try { j = await (await fetch('/api/concept/job/' + C.job)).json(); }
      catch (e) { C.timer = setTimeout(poll, 2000); return; }
      el.innerHTML = packBlock(j, motifs);
      if (j.done) {
        busy(false);
        toast(j.error ? j.error : 'Concept pack built.', !!j.error);
      } else {
        C.timer = setTimeout(poll, 2000);
      }
    };
    poll();
  } catch (e) {
    el.innerHTML = `<p style="color:var(--bad);max-width:52ch">${esc(e.message)}</p>`;
    toast(e.message, true);
    busy(false);
  }
};

/* ---------------------------------------------------------------- paint */

const P = { base: 'gpt', templates: [], packs: [], textures: [], kontext: false, job: null, timer: null };

async function loadPaintLists() {
  try {
    const t = await (await fetch('/api/templates')).json();
    P.templates = t.templates || [];
    P.kontext = !!t.kontext_ready;
    const cur = $('#pTemplate').value;
    $('#pTemplate').innerHTML = P.templates.length
      ? P.templates.map((x) => `<option value="${x.slug}">${esc(x.name)} · ${x.sponsor_blocks} sponsor / ${x.number_blocks} number zones</option>`).join('')
      : '<option value="">— no template ingested yet —</option>';
    if (cur && P.templates.some((x) => x.slug === cur)) $('#pTemplate').value = cur;
    paintTemplateInfo();
    $('#pKontextNote').textContent = P.kontext
      ? 'FLUX Kontext paints the design straight onto the flattened sheet, panel by panel. About a minute.'
      : 'Kontext model not installed: models/diffusion_models/flux1-dev-kontext_fp8_scaled.safetensors. Use Texture or Colour until then.';
  } catch (e) { /* lists are a convenience */ }
  try {
    const p = await (await fetch('/api/packs')).json();
    P.packs = p.packs || []; P.textures = p.textures || [];
    $('#pPack').innerHTML = '<option value="">— none —</option>' + P.packs.map((k) =>
      `<option value="${k.id}">${esc(k.brief.slice(0, 60))} (${k.motifs.length} motifs${k.wordmark ? ' + wordmark' : ''})</option>`).join('');
    $('#pTexture').innerHTML = P.textures.map((x) => `<option value="${x.file}">${esc(x.file)}</option>`).join('');
    paintPackPreview();
  } catch (e) { /* same */ }
}

function paintTemplateInfo() {
  const t = P.templates.find((x) => x.slug === $('#pTemplate').value);
  $('#pTemplateInfo').textContent = t
    ? `${t.size[0]}×${t.size[1]} · ${Math.round(t.paintable * 100)}% paintable · ${t.has_wire ? 'mesh found' : 'no mesh layer'}`
    : '';
}

function paintPackPreview() {
  const k = P.packs.find((x) => x.id === $('#pPack').value);
  $('#pPackPreview').innerHTML = k
    ? `<div class="swatches" style="margin-top:6px">${k.motifs.map((u) => `<img src="${u}" style="width:44px;height:44px;object-fit:contain;border-radius:6px;background:repeating-conic-gradient(#2a2f3a 0 25%,#20242c 0 50%) 0 0/11px 11px">`).join('')}${k.wordmark ? `<img src="${k.wordmark}" style="height:44px;object-fit:contain;border-radius:6px;background:#333">` : ''}</div>`
    : '';
  if (k && !$('#pBrief').value.trim()) $('#pBrief').value = k.brief;
}

$('#pTemplate').onchange = paintTemplateInfo;
$('#pPack').onchange = paintPackPreview;

$$('#pBaseMode button').forEach((b) => {
  b.onclick = () => {
    P.base = b.dataset.m;
    $$('#pBaseMode button').forEach((x) => x.classList.toggle('on', x === b));
    $('#pBriefBox').classList.toggle('hidden', P.base !== 'kontext' && P.base !== 'gpt');
    $('#pGptBox').classList.toggle('hidden', P.base !== 'gpt');
    $('#pKontextBox').classList.toggle('hidden', P.base !== 'kontext');
    $('#pTextureBox').classList.toggle('hidden', P.base !== 'texture');
    $('#pColorBox').classList.toggle('hidden', P.base !== 'color');
    // The cloud painter already places the motifs; stacking cut-outs on top
    // doubles them up. Wordmark and number still go on.
    if (P.base === 'gpt') $('#pUseMotifs').checked = false;
  };
});

$('#pPsd').addEventListener('change', async () => {
  const f = $('#pPsd').files[0];
  if (!f) return;
  const el = $('#paintResult');
  el.classList.remove('empty');
  busy(true, el, `Reading ${f.name} — a paint kit PSD takes a few seconds…`);
  try {
    const fd = new FormData();
    fd.append('psd', f);
    const r = await api('/api/templates/ingest', fd, true);
    await loadPaintLists();
    $('#pTemplate').value = r.slug;
    paintTemplateInfo();
    el.innerHTML = templateBlock(r);
    toast(`${r.name}: ${r.sponsor_blocks} sponsor zones, ${r.number_blocks} number zones${r.blocks_auto ? ' (found automatically — this kit has no block layers)' : ''}.`);
  } catch (e) {
    el.innerHTML = `<p style="color:var(--bad);max-width:52ch">${esc(e.message)}</p>`;
    toast(e.message, true);
  }
  busy(false);
  $('#pPsd').value = '';
});

function templateBlock(r) {
  const s = r.size[0];
  const rects = (r.blocks || []).map((b) =>
    `<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" fill="${b.kind === 'number' ? 'rgba(0,200,255,.45)' : 'rgba(255,140,0,.45)'}" stroke="${b.kind === 'number' ? '#3cf' : '#fa0'}" stroke-width="3"><title>${b.id} · curvature ${b.curvature}</title></rect>`).join('');
  return `<div class="pack">
    <div class="verdict good"><b>${esc(r.name)}</b> — ${r.sponsor_blocks} sponsor zones (orange), ${r.number_blocks} number zones (blue)${r.blocks_auto ? '. No block layers in this kit, so zones were found from flat areas of the mesh.' : ', read from iRacing\'s own hidden block layers.'}</div>
    <div class="hero" style="position:relative">
      <img src="/out/templates/${r.slug}/guide.png?t=${Date.now()}" alt="template" style="width:100%">
      <svg viewBox="0 0 ${s} ${r.size[1]}" style="position:absolute;inset:0;width:100%;height:100%">${rects}</svg>
    </div></div>`;
}

function paintBlock(j) {
  const r = j.result;
  const pct = j.total ? Math.round(100 * j.progress / j.total) : 0;
  if (j.error) return `<div class="pack"><div class="verdict bad"><b>Failed</b> — ${esc(j.error)}</div></div>`;
  if (!j.done) return `<div class="pack"><div class="bar-out"><div class="bar-in" style="width:${pct}%"></div></div>
    <p class="steps"><span class="spin" style="display:inline-block;width:12px;height:12px;vertical-align:middle;margin-right:8px"></span><b>${esc(j.step)}</b></p></div>`;
  const warn = r.warnings && r.warnings.length
    ? `<div class="verdict bad"><b>Check in the sim</b> — ${r.warnings.map(esc).join('; ')}</div>` : '';
  return `<div class="pack">
    <div class="verdict good"><b>Painted</b> — ${r.placements.length} placements. Saved to <code>out/${esc(r.folder)}/</code></div>
    ${warn}
    <div class="hero"><img src="${r.preview}?t=${r.seed}" alt="preview"><p class="meta" style="margin-top:6px">Shaded preview · flat sheet with the kit's own shading</p></div>
    <div class="pair">
      <figure><img src="${r.paint}?t=${r.seed}" alt="paint" class="checkerbg"><figcaption>paint.png — what ships as car.tga</figcaption></figure>
      <figure><img src="${r.spec}?t=${r.seed}" alt="spec"><figcaption>spec map — derived, not painted</figcaption></figure>
    </div>
    <div class="acts">
      <a href="${r.zip}" download><button class="primary">Download all (.zip)</button></a>
      <a href="${r.tga}" download><button>car.tga</button></a>
      <a href="${r.spec_tga}" download><button>car_spec.tga</button></a>
      <a href="${r.paint}" download><button>paint.png</button></a>
    </div>
    ${j.prompt ? `<div class="prompt-peek"><b>Prompt sent:</b> ${esc(j.prompt)}</div>` : ''}
    <p class="meta">Seed ${r.seed}. Rename the TGAs to <code>car_&lt;your iRacing ID&gt;.tga</code> and <code>car_spec_&lt;id&gt;.tga</code> in the car's paint folder, or load paint.png in Clearcoat to keep editing.</p>
  </div>`;
}

$('#btnPaint').onclick = async () => {
  if (STATE.busy) return;
  if (!$('#pTemplate').value) { toast('Ingest a template first.', true); return; }
  const el = $('#paintResult');
  el.classList.remove('empty');
  busy(true, el, 'Starting…');
  try {
    const r = await api('/api/paint/start', {
      template: $('#pTemplate').value,
      base: P.base,
      brief: $('#pBrief').value, palette_hint: $('#pPalette').value,
      guidance: +$('#pGuidance').value,
      gpt_size: $('#pGptSize').value, use_render: $('#pUseRender').checked,
      texture: $('#pTexture').value, texture_mode: $('#pTextureMode').value,
      color: $('#pColor').value,
      pack: $('#pPack').value || null,
      use_motifs: $('#pUseMotifs').checked, use_wordmark: $('#pUseWordmark').checked,
      number: $('#pNumber').value, number_color: $('#pNumColor').value, number_outline: $('#pNumOutline').value,
      seed: $('#pSeed').value ? +$('#pSeed').value : null,
    });
    P.job = r.job;
    const poll = async () => {
      let j;
      try { j = await (await fetch('/api/paint/job/' + P.job)).json(); }
      catch (e) { P.timer = setTimeout(poll, 2000); return; }
      el.innerHTML = paintBlock(j);
      if (j.done) { busy(false); toast(j.error ? j.error : 'Painted.', !!j.error); }
      else P.timer = setTimeout(poll, 2000);
    };
    poll();
  } catch (e) {
    el.innerHTML = `<p style="color:var(--bad);max-width:52ch">${esc(e.message)}</p>`;
    toast(e.message, true);
    busy(false);
  }
};

$$('.tabs button').forEach((b) => {
  if (b.dataset.tab === 'paint') b.addEventListener('click', () => loadPaintLists());
});
loadPaintLists();

const _loadProviders = loadProviders;
loadProviders = async function () { await _loadProviders(); renderConceptProviders(); };
const _refreshStatus = refreshStatus;
refreshStatus = async function () {
  await _refreshStatus();
  if (!$('#cStyles').children.length) renderConceptStyles();
};
conceptSuggest();

applyTexMode();
loadProviders();
refreshStatus();
setInterval(refreshStatus, 15000);
