const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

let STATE = { presets: [], shapes: [], preset: 'storm', shape: 'mountains', busy: false };

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
    const dot = $('#engineDot');
    dot.className = 'dot ' + (s.comfy_up ? 'up' : 'down');
    $('#engineText').textContent = s.comfy_up
      ? (s.vram ? `FLUX ready · ${s.vram.free_gb}/${s.vram.total_gb} GB free` : 'FLUX ready')
      : 'engine stopped';
    $('#btnStart').disabled = s.comfy_up;
    $('#btnStop').disabled = !s.comfy_up;
    if (!$('#presets').children.length) { renderPresets(); renderShapes(); }
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
    <p class="meta">Saved to <code>out/${r.file}</code>${r.seed ? ` · seed ${r.seed}` : ''}</p>`;
}

$('#btnGen').onclick = async () => {
  if (STATE.busy) return;
  const el = $('#texResult');
  el.classList.remove('empty');
  busy(true, el, 'Forging… first run also loads the model, so allow a minute.');
  try {
    const r = await api('/api/generate', {
      preset: STATE.preset,
      color: $('#color').value || null,
      extra: $('#extra').value || null,
      width: +$('#genSize').value, height: +$('#genSize').value,
      steps: +$('#steps').value,
      seed: $('#seed').value ? +$('#seed').value : null,
      devignette: $('#devig').checked,
      tile: $('#tile').checked,
      contrast: +$('#contrast').value,
      saturation: +$('#sat').value,
    });
    el.innerHTML = resultBlock(r, 'Texture');
    toast(r.value_range.ok
      ? 'Forged. This one will read at distance.'
      : 'Forged — but the value range is low, so it may go flat on track. Try raising contrast.');
  } catch (e) {
    el.innerHTML = `<p style="color:var(--bad);max-width:52ch">${e.message}</p>`;
    toast(e.message, true);
  }
  busy(false);
};

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

refreshStatus();
setInterval(refreshStatus, 15000);
