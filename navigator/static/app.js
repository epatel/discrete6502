const BASE = document.body.dataset.base || '';  // URL prefix when reverse-proxied
// Reads are open; changing the board needs the token.  Supply it as ?key=... and
// this page becomes a controller — without it the map is simply read-only.
const KEY = new URLSearchParams(location.search).get('key') || '';
const keyed = p => KEY ? p + (p.includes('?') ? '&' : '?') + 'key=' + encodeURIComponent(KEY) : p;
// A deployment gates writes, so say so once rather than failing silently.
let toldReadOnly = false;
async function write(path, opts) {
  const r = await fetch(keyed(BASE + path), opts);
  if (r.status === 401 && !toldReadOnly) {
    toldReadOnly = true;
    const b = document.createElement('div');
    b.className = 'readonly';
    b.textContent = 'read-only — this navigator is shared; annotating needs the token';
    document.body.appendChild(b);
    setTimeout(() => b.remove(), 6000);
  }
  return r;
}
/* discrete6502 board navigator — canvas viewer + live agent channel */
'use strict';

const $ = s => document.querySelector(s);
const cv = $('#cv'), ctx = cv.getContext('2d');

let B = null;                    // board bundle
let PARTS = [], BYREF = new Map(), NETS = new Map();
let side = 'F';
let view = { cx: 0, cy: 0, scale: 2 };   // display-mm -> px
let selected = null, hover = null;
let state = { annotations: [], highlight: { refs: [], label: '', color: '#ffd23f' }, note: {}, seq: -1 };
let hlSet = new Set();
let images = {};                 // side -> Image
let grid = {};                   // side -> Map(cellkey -> [part])
let lastViewTs = 0;
let pinMode = false;
let pending = null;              // pin being placed

const COLORS = {
  'fet/pulldown': '#4a86d6', 'fet/vcc_side': '#e2653f', 'fet/pass_a': '#9b7bff',
  'fet/pass_b': '#9b7bff', 'fet/led_driver': '#e0a93f',
  'resistor': '#43a06f', 'capacitor': '#a4794c', 'led': '#ff4757',
  'diode': '#c792ff', 'testpoint': '#ffd23f', 'module': '#3fd0ff',
};
const LEGEND = [
  ['pull-down FET', '#4a86d6'], ['VCC-side FET', '#e2653f'], ['pass pair', '#9b7bff'],
  ['LED driver', '#e0a93f'], ['resistor', '#43a06f'], ['capacitor', '#a4794c'],
  ['LED', '#ff4757'], ['clamp diode', '#c792ff'], ['bond pad', '#ffd23f'], ['Pico site', '#3fd0ff'],
];

const colorOf = p => COLORS[p.type + '/' + p.role] || COLORS[p.type] || '#7c8b99';

/* ---------------------------------------------------------------- geometry */
const U = x => (side === 'B' ? B.board.w - x : x);      // board mm -> display mm
const invU = u => (side === 'B' ? B.board.w - u : u);
const sx = u => (u - view.cx) * view.scale + cv.clientWidth / 2;
const sy = v => (v - view.cy) * view.scale + cv.clientHeight / 2;
const wx = px => (px - cv.clientWidth / 2) / view.scale + view.cx;
const wy = py => (py - cv.clientHeight / 2) / view.scale + view.cy;

function fit() {
  const pad = 16;
  view.scale = Math.min((cv.clientWidth - pad) / B.board.w, (cv.clientHeight - pad) / B.board.h);
  view.cx = B.board.w / 2; view.cy = B.board.h / 2;
  draw();
}

function flyTo(x, y, zoom, span) {
  // span = {w,h} in mm: frame a whole group, since only the page knows the canvas
  let scale = zoom;
  if (!scale && span) {
    scale = Math.min((cv.clientWidth - 60) / (span.w + 8), (cv.clientHeight - 60) / (span.h + 8));
    scale = Math.max(0.5, Math.min(40, scale));
  }
  const target = { cx: U(x), cy: y, scale: scale || Math.max(view.scale, 9) };
  const from = { ...view }, t0 = performance.now(), dur = 420;
  (function step(t) {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    view.cx = from.cx + (target.cx - from.cx) * e;
    view.cy = from.cy + (target.cy - from.cy) * e;
    view.scale = from.scale * Math.pow(target.scale / from.scale, e);
    draw();
    if (k < 1) requestAnimationFrame(step);
  })(t0);
}

/* ------------------------------------------------------------------ render */
function resize() {
  const dpr = window.devicePixelRatio || 1;
  cv.width = cv.clientWidth * dpr; cv.height = cv.clientHeight * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  draw();
}

let raf = 0;
function draw() { if (!raf) raf = requestAnimationFrame(() => { raf = 0; paint(); }); }

function paint() {
  const W = cv.clientWidth, H = cv.clientHeight;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#07090b'; ctx.fillRect(0, 0, W, H);

  const x0 = sx(0), y0 = sy(0), x1 = sx(B.board.w), y1 = sy(B.board.h);

  // board render underlay
  const img = images[side], meta = B.images[side], op = +$('#opacity').value / 100;
  if (img && img.complete && op > 0) {
    const [bx0, by0, bx1, by1] = meta.box;
    ctx.globalAlpha = op;
    ctx.imageSmoothingEnabled = view.scale < 8;
    ctx.drawImage(img, bx0, by0, bx1 - bx0 + 1, by1 - by0 + 1, x0, y0, x1 - x0, y1 - y0);
    ctx.globalAlpha = 1;
  } else {
    ctx.fillStyle = '#0f1a14'; ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
  }
  ctx.strokeStyle = '#2a333d'; ctx.lineWidth = 1; ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);

  // parts
  const showParts = $('#tParts').checked, showLabels = $('#tLabels').checked;
  const s = view.scale, minU = wx(0), maxU = wx(W), minV = wy(0), maxV = wy(H);
  if (showParts) {
    ctx.lineWidth = Math.max(0.6, s * 0.06);
    for (const p of PARTS) {
      if (p.layer !== side) continue;
      const u = U(p.x);
      if (u < minU - 4 || u > maxU + 4 || p.y < minV - 4 || p.y > maxV + 4) continue;
      const px = sx(u - p.w / 2), py = sy(p.y - p.h / 2), pw = p.w * s, ph = p.h * s;
      ctx.fillStyle = colorOf(p);
      // fade the overlay out as you zoom out, so the board render stays readable
      ctx.globalAlpha = Math.max(0.22, Math.min(0.5, 0.1 + s * 0.09));
      ctx.fillRect(px, py, Math.max(1, pw), Math.max(1, ph));
      ctx.globalAlpha = 1;
      if (hlSet.has(p.ref)) {
        ctx.strokeStyle = state.highlight.color || '#ffd23f';
        ctx.lineWidth = Math.max(1.5, s * 0.16);
        ctx.strokeRect(px - 1, py - 1, pw + 2, ph + 2);
        ctx.lineWidth = Math.max(0.6, s * 0.06);
      }
    }
    if (showLabels && s > 7) {
      ctx.font = `${Math.min(14, s * 0.7)}px ui-monospace,Menlo,monospace`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillStyle = '#e6edf3';
      for (const p of PARTS) {
        if (p.layer !== side) continue;
        const u = U(p.x);
        if (u < minU || u > maxU || p.y < minV || p.y > maxV) continue;
        ctx.fillText(p.ref, sx(u), sy(p.y));
      }
    }
  }

  // selection
  if (selected && selected.layer === side) ring(U(selected.x), selected.y, '#4bd0a0', selected.ref);

  // annotations
  if ($('#tAnn').checked) for (const a of state.annotations) {
    if (a.side !== side) continue;
    drawAnnotation(a);
  }

  // scale bar
  scaleBar();
}

function ring(u, v, color, label) {
  const x = sx(u), y = sy(v), r = Math.max(9, view.scale * 2.2);
  ctx.strokeStyle = color; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x - r * 1.9, y); ctx.lineTo(x - r * 1.2, y);
  ctx.moveTo(x + r * 1.2, y); ctx.lineTo(x + r * 1.9, y);
  ctx.moveTo(x, y - r * 1.9); ctx.lineTo(x, y - r * 1.2);
  ctx.moveTo(x, y + r * 1.2); ctx.lineTo(x, y + r * 1.9);
  ctx.stroke();
  if (label) {
    ctx.font = '12px ui-monospace,Menlo,monospace'; ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
    ctx.fillStyle = color; ctx.fillText(label, x + r + 6, y - r * 0.5);
  }
}

function drawAnnotation(a) {
  const x = sx(U(a.x)), y = sy(a.y);
  const r = Math.max(10, a.r * view.scale);
  ctx.strokeStyle = a.color; ctx.lineWidth = 2.5;
  if (a.shape === 'rect') {
    ctx.strokeRect(x - a.w * view.scale / 2, y - a.h * view.scale / 2,
                   a.w * view.scale, a.h * view.scale);
  } else if (a.shape === 'cross') {
    ctx.beginPath();
    ctx.moveTo(x - r, y - r); ctx.lineTo(x + r, y + r);
    ctx.moveTo(x + r, y - r); ctx.lineTo(x - r, y + r); ctx.stroke();
  } else {
    ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.stroke();
  }
  const text = a.label || a.ref || '';
  if (!text) return;
  ctx.font = '600 12px ui-sans-serif,system-ui,sans-serif';
  const tw = ctx.measureText(text).width;
  const lx = x + r + 8, ly = y - r - 8;
  ctx.beginPath(); ctx.moveTo(x + r * 0.7, y - r * 0.7); ctx.lineTo(lx - 2, ly + 9); ctx.stroke();
  ctx.fillStyle = '#0b0f13ee'; ctx.fillRect(lx - 4, ly - 3, tw + 10, 19);
  ctx.strokeStyle = a.color; ctx.lineWidth = 1; ctx.strokeRect(lx - 4, ly - 3, tw + 10, 19);
  ctx.fillStyle = a.color; ctx.textAlign = 'left'; ctx.textBaseline = 'top';
  ctx.fillText(text, lx + 1, ly + 1);
}

function scaleBar() {
  const targets = [0.5, 1, 2, 5, 10, 20, 50, 100];
  const mm = targets.find(t => t * view.scale > 70) || 100;
  const w = mm * view.scale, x = 16, y = cv.clientHeight - 22;
  ctx.strokeStyle = '#8b9bab'; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + w, y);
  ctx.moveTo(x, y - 4); ctx.lineTo(x, y + 4);
  ctx.moveTo(x + w, y - 4); ctx.lineTo(x + w, y + 4); ctx.stroke();
  ctx.fillStyle = '#8b9bab'; ctx.font = '11px ui-monospace,Menlo,monospace';
  ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
  ctx.fillText(mm + ' mm', x + w + 8, y + 5);
}

/* -------------------------------------------------------------- hit testing */
const CELL = 5;
function buildGrid() {
  grid = { F: new Map(), B: new Map() };
  for (const p of PARTS) {
    const key = Math.floor(p.x / CELL) + ',' + Math.floor(p.y / CELL);
    const m = grid[p.layer];
    if (!m.has(key)) m.set(key, []);
    m.get(key).push(p);
  }
}
function pick(bx, by) {                // board mm
  const m = grid[side]; let best = null, bd = 1e9;
  for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) {
    const arr = m.get((Math.floor(bx / CELL) + i) + ',' + (Math.floor(by / CELL) + j));
    if (!arr) continue;
    for (const p of arr) {
      const dx = Math.abs(p.x - bx), dy = Math.abs(p.y - by);
      if (dx > p.w / 2 + 0.4 || dy > p.h / 2 + 0.4) continue;
      const d = dx * dx + dy * dy;
      if (d < bd) { bd = d; best = p; }
    }
  }
  return best;
}

/* ------------------------------------------------------------------- panels */
function refRow(p, extra) {
  const d = document.createElement('div');
  d.className = 'row' + (selected && selected.ref === p.ref ? ' sel' : '');
  d.innerHTML = `<b style="color:${colorOf(p)}">${p.ref}</b><span>${extra ||
    (p.value + ' · ' + (p.role || p.type) + ' · ' + p.layer)}</span>`;
  d.onclick = () => select(p.ref, true);
  return d;
}

function renderResults(hits, q) {
  const box = $('#results'); box.innerHTML = '';
  if (!q) { $('#hint').textContent = `${PARTS.length.toLocaleString()} parts · ${NETS.size.toLocaleString()} nets`; return; }
  $('#hint').textContent = `${hits.length} match${hits.length === 1 ? '' : 'es'}` +
    (hits.length >= 200 ? ' (first 200)' : '');
  hits.forEach(r => box.appendChild(refRow(BYREF.get(r.ref) || r)));
}

function select(ref, fly) {
  const p = BYREF.get(ref);
  if (!p) return;
  selected = p;
  if (p.layer !== side) setSide(p.layer);
  if (fly) flyTo(p.x, p.y); else draw();
  const nets = Object.entries(p.pins || {});
  $('#detail').classList.remove('hidden');
  $('#detail').innerHTML = `
    <h3 style="color:${colorOf(p)}">${p.ref}</h3>
    <dl>
      <dt>value</dt><dd>${p.value}</dd>
      <dt>role</dt><dd>${p.role || '—'}</dd>
      <dt>type</dt><dd>${p.type}${p.dnp ? ' · DNP' : ''}</dd>
      <dt>side</dt><dd>${p.layer === 'F' ? 'top (F)' : 'bottom (B)'}</dd>
      <dt>position</dt><dd>x ${p.x.toFixed(2)} &nbsp; y ${p.y.toFixed(2)} mm</dd>
      ${p.origin ? `<dt>origin</dt><dd>${p.origin}</dd>` : ''}
    </dl>
    <div class="pins">${nets.map(([pin, net]) =>
      `<div class="pin"><i>${pin}</i><a data-net="${net}">${net}</a></div>`).join('')}</div>
    <div class="tags">
      <span class="tag" data-act="pin">+ annotate here</span>
      <span class="tag" data-act="near">nearby parts</span>
    </div>`;
  $('#detail').querySelectorAll('a[data-net]').forEach(a =>
    a.onclick = () => { $('#q').value = 'net:' + a.dataset.net; runSearch(); });
  $('#detail').querySelector('[data-act=pin]').onclick = () => openPinDialog(p.x, p.y, p.ref);
  $('#detail').querySelector('[data-act=near]').onclick = () => showNearby(p);
}

function showNearby(p) {
  const near = PARTS.filter(q => q.layer === p.layer && q.ref !== p.ref)
    .map(q => [(q.x - p.x) ** 2 + (q.y - p.y) ** 2, q])
    .sort((a, b) => a[0] - b[0]).slice(0, 12);
  const box = $('#results'); box.innerHTML = '';
  $('#hint').textContent = `12 parts nearest ${p.ref}`;
  near.forEach(([d2, q]) => box.appendChild(refRow(q,
    `${Math.sqrt(d2).toFixed(2)} mm · ${q.value} · ${q.role || q.type}`)));
}

function renderState() {
  hlSet = new Set(state.highlight.refs || []);
  const bar = $('#hlbar');
  if (hlSet.size) {
    bar.classList.remove('hidden');
    bar.textContent = (state.highlight.label || 'highlighted') + ` · ${hlSet.size} part${hlSet.size === 1 ? '' : 's'}`;
    bar.style.borderColor = bar.style.color = state.highlight.color || '#ffd23f';
  } else bar.classList.add('hidden');

  const n = state.note || {};
  $('#noteCard').hidden = !(n.title || n.text);
  $('#noteTitle').textContent = n.title || 'Note';
  $('#noteBody').textContent = n.text || '';

  const list = $('#annList'); list.innerHTML = '';
  $('#annCount').textContent = state.annotations.length;
  for (const a of state.annotations) {
    const el = document.createElement('div');
    el.className = 'ann';
    el.innerHTML = `<span class="dot" style="background:${a.color}"></span>
      <span class="t"><b>${a.label || a.ref || a.id}</b>
      <small>${a.ref ? a.ref + ' · ' : ''}${a.side} ${a.x.toFixed(1)},${a.y.toFixed(1)}${a.text ? '\n' + a.text : ''}</small></span>
      <button class="x" title="delete">×</button>`;
    el.onclick = e => {
      if (e.target.classList.contains('x')) {
        write('/api/annotation/' + encodeURIComponent(a.id), { method: 'DELETE' });
        return;
      }
      if (a.side !== side) setSide(a.side);
      flyTo(a.x, a.y);
      if (a.ref) select(a.ref, false);
    };
    list.appendChild(el);
  }
  if (state.view && state.view.ts > lastViewTs) {
    lastViewTs = state.view.ts;
    if (state.view.side && state.view.side !== side) setSide(state.view.side);
    flyTo(state.view.x, state.view.y, state.view.zoom,
          state.view.w ? { w: state.view.w, h: state.view.h } : null);
  }
  draw();
}

function setSide(s) {
  side = s;
  $('#sideF').classList.toggle('on', s === 'F');
  $('#sideB').classList.toggle('on', s === 'B');
  draw();
}

/* ------------------------------------------------------------------ events */
function bindCanvas() {
  let dragging = false, moved = 0, lx = 0, ly = 0;

  cv.addEventListener('mousedown', e => {
    dragging = true; moved = 0; lx = e.clientX; ly = e.clientY; cv.classList.add('dragging');
  });
  window.addEventListener('mouseup', e => {
    cv.classList.remove('dragging');
    if (!dragging) return;
    dragging = false;
    if (moved > 4) return;
    const r = cv.getBoundingClientRect();
    const bx = invU(wx(e.clientX - r.left)), by = wy(e.clientY - r.top);
    if (bx < 0 || by < 0 || bx > B.board.w || by > B.board.h) return;
    if (pinMode) { openPinDialog(bx, by, ''); togglePin(false); return; }
    const p = pick(bx, by);
    if (p) select(p.ref, false); else { selected = null; $('#detail').classList.add('hidden'); draw(); }
  });
  window.addEventListener('mousemove', e => {
    const r = cv.getBoundingClientRect();
    const px = e.clientX - r.left, py = e.clientY - r.top;
    if (dragging) {
      moved += Math.abs(e.clientX - lx) + Math.abs(e.clientY - ly);
      view.cx -= (e.clientX - lx) / view.scale;
      view.cy -= (e.clientY - ly) / view.scale;
      lx = e.clientX; ly = e.clientY; draw();
      return;
    }
    if (px < 0 || py < 0 || px > r.width || py > r.height) { $('#tip').classList.add('hidden'); return; }
    const bx = invU(wx(px)), by = wy(py);
    $('#coords').textContent = `x ${bx.toFixed(2)}  y ${by.toFixed(2)} mm  ·  ${side === 'F' ? 'top' : 'bottom'}`;
    const p = pick(bx, by);
    hover = p;
    const tip = $('#tip');
    if (p) {
      const pins = Object.entries(p.pins || {}).map(([k, v]) => `  ${k}: ${v}`).join('\n');
      tip.textContent = `${p.ref}  ${p.value}\n${p.role || p.type}\n${pins}`;
      tip.classList.remove('hidden');
      tip.style.left = Math.min(px + 16, r.width - tip.offsetWidth - 8) + 'px';
      tip.style.top = Math.min(py + 16, r.height - tip.offsetHeight - 8) + 'px';
    } else tip.classList.add('hidden');
  });
  cv.addEventListener('wheel', e => {
    e.preventDefault();
    const r = cv.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
    const bu = wx(px), bv = wy(py);
    const k = Math.exp(-e.deltaY * 0.0016);
    view.scale = Math.max(0.4, Math.min(400, view.scale * k));
    view.cx = bu - (px - cv.clientWidth / 2) / view.scale;
    view.cy = bv - (py - cv.clientHeight / 2) / view.scale;
    draw();
  }, { passive: false });

  window.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
      if (e.key === 'Escape') e.target.blur();
      return;
    }
    if (e.key === '/') { e.preventDefault(); $('#q').focus(); }
    else if (e.key === 'f') fit();
    else if (e.key === 't') setSide('F');
    else if (e.key === 'b') setSide('B');
    else if (e.key === 'p') togglePin(!pinMode);
    else if (e.key === 'Escape') { selected = null; $('#detail').classList.add('hidden'); togglePin(false); draw(); }
  });
}

function togglePin(on) {
  pinMode = on;
  $('#pinMode').classList.toggle('armed', on);
  cv.classList.toggle('pinning', on);
}

function openPinDialog(x, y, ref) {
  pending = { x, y, ref, side };
  const dlg = $('#pinDlg');
  dlg.querySelector('[name=label]').value = ref || '';
  dlg.querySelector('[name=text]').value = '';
  dlg.returnValue = '';
  dlg.showModal();
}

/* ------------------------------------------------------------------ search */
let searchTimer = 0;
function runSearch() {
  const q = $('#q').value.trim();
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    if (!q) { renderResults([], ''); return; }
    const r = await fetch(BASE + '/api/find?limit=200&q=' + encodeURIComponent(q));
    const j = await r.json();
    renderResults(j.parts, q);
    if (j.parts.length === 1) select(j.parts[0].ref, true);
  }, 120);
}

/* ------------------------------------------------------------------ groups */
let activeGroup = '';
async function loadGroups() {
  const { groups } = await (await fetch(BASE + '/api/groups')).json();
  const box = $('#groups'); box.innerHTML = '';
  for (const g of groups) {
    const el = document.createElement('button');
    el.className = 'grp' + (g.error ? ' bad' : '');
    el.innerHTML = `<i style="background:${g.color}"></i>
      <span class="g"><b>${g.label}</b><small>${g.error || g.desc}</small></span>
      <span class="n">${g.error ? '!' : g.count + (g.side === 'B' ? ' · B' : '')}</span>`;
    el.title = g.error || `${g.desc}\n${g.count} parts on the ${g.side === 'B' ? 'bottom' : 'top'} face`;
    el.disabled = !!g.error;
    el.onclick = async () => {
      if (activeGroup === g.id) {                 // click again to drop it
        await write('/api/clear', { method: 'POST', body: JSON.stringify({ what: 'all' }) });
        activeGroup = '';
      } else {
        await write('/api/group', { method: 'POST', body: JSON.stringify({ id: g.id }) });
        activeGroup = g.id;
      }
      markGroups();
    };
    el.dataset.id = g.id;
    box.appendChild(el);
  }
}
function markGroups() {
  document.querySelectorAll('.grp').forEach(el =>
    el.classList.toggle('on', el.dataset.id === activeGroup));
}

/* --------------------------------------------------------------- websocket */
function connect() {
  const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + BASE + '/ws');
  ws.onopen = () => { $('#live').className = 'live on'; $('#live').textContent = 'live'; };
  ws.onclose = () => {
    $('#live').className = 'live off'; $('#live').textContent = 'offline';
    setTimeout(connect, 1500);
  };
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.type === 'state') { state = m.state; renderState(); }
  };
}

/* ------------------------------------------------------------------- start */
async function main() {
  B = await (await fetch(BASE + '/api/board')).json();
  const keys = B.schema;
  PARTS = B.parts.map(row => {
    const o = {}; keys.forEach((k, i) => o[k] = row[i]); return o;
  });
  BYREF = new Map(PARTS.map(p => [p.ref, p]));
  for (const p of PARTS) for (const net of Object.values(p.pins || {})) {
    if (!NETS.has(net)) NETS.set(net, []);
    NETS.get(net).push(p.ref);
  }
  buildGrid();

  for (const [s, meta] of Object.entries(B.images)) {
    const im = new Image();
    im.onload = draw;
    im.src = BASE + '/img/' + meta.file;
    images[s] = im;
  }

  await loadGroups();

  $('#legend').innerHTML = LEGEND.map(([n, c]) =>
    `<li><i style="background:${c}"></i>${n}</li>`).join('');

  $('#sideF').onclick = () => setSide('F');
  $('#sideB').onclick = () => setSide('B');
  $('#fit').onclick = fit;
  $('#pinMode').onclick = () => togglePin(!pinMode);
  $('#clearAnn').onclick = () =>
    write('/api/clear', { method: 'POST', body: JSON.stringify({ what: 'annotations' }) });
  ['tParts', 'tLabels', 'tAnn', 'opacity'].forEach(id => $('#' + id).oninput = draw);
  $('#q').oninput = runSearch;

  $('#pinDlg').addEventListener('close', () => {
    const dlg = $('#pinDlg');
    if (dlg.returnValue !== 'ok' || !pending) { pending = null; return; }
    const f = dlg.querySelector('form');
    write('/api/annotate', {
      method: 'POST',
      body: JSON.stringify({
        x: pending.x, y: pending.y, side: pending.side, ref: pending.ref,
        label: f.label.value, text: f.text.value, color: f.color.value,
      })
    });
    pending = null;
  });

  bindCanvas();
  window.addEventListener('resize', resize);
  resize(); fit();

  state = await (await fetch(BASE + '/api/state')).json();
  if (state.view) lastViewTs = state.view.ts;      // do not fly on first load
  renderState();
  connect();
  renderResults([], '');
}
main();
