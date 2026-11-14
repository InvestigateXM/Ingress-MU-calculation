// Players for the animations on how-it-works.html.
// Each player draws one trace file (site/traces/aN.json, written by tools/export_traces.py).
// The drawing is a pure function of (trace, step): states are replayed from step 0 up to the
// current step, so playing, stepping and scrubbing all use the same code.
const NS = 'http://www.w3.org/2000/svg';

const el = (tag, attrs = {}, text) => {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (text !== undefined) e.textContent = text;
  return e;
};
const h = (tag, attrs = {}, text) => {
  const e = document.createElement(tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (text !== undefined) e.textContent = text;
  return e;
};
const num = (v, d) => Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

// States of all elements at a step. Ops with a key starting with '@' set a whole group.
function states(tr, k) {
  const st = {};
  for (let i = 0; i <= k; i++) {
    const ops = tr.steps[i].s;
    for (const key in ops) {
      if (key[0] === '@') for (const id of tr.groups[key.slice(1)] || []) st[id] = ops[key];
      else st[key] = ops[key];
    }
  }
  return st;
}

function build(root, tr) {
  const [vx, vy, vw, vh] = tr.view;
  const svg = el('svg', { class: 'stage', viewBox: `${vx} ${vy} ${vw} ${vh}`, role: 'img',
    'aria-label': tr.title + '. The caption below describes each step.' });
  // hatch patterns whose spacing follows the screen size (see sizeStage)
  const defs = el('defs');
  for (const [name, cross] of [['merged', false], ['kept', true]]) {
    const pat = el('pattern', { id: `hatch-${name}-${tr.id}`, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' });
    pat.append(el('rect', { class: 'hb ' + name }), el('line', { class: 'hl ' + name, x1: 0, y1: 0, x2: 0 }));
    if (cross) pat.append(el('line', { class: 'hl ' + name, x1: 0, y1: 0, y2: 0 }));
    defs.appendChild(pat);
    svg.style.setProperty('--fill-' + name, `url(#hatch-${name}-${tr.id})`);
  }
  svg.appendChild(defs);
  const nodes = {};
  for (const [id, kind, g, text] of tr.els) {
    let n;
    if (kind === 'p') n = el('polygon', { points: g.map(p => p.join(',')).join(' ') });
    else if (kind === 'd') n = el('circle', { cx: g[0], cy: g[1] });
    else if (kind === 'l') n = el('line', { x1: g[0][0], y1: g[0][1], x2: g[1][0], y2: g[1][1] });
    else { n = el('text', { x: g[0], y: g[1], 'text-anchor': g[2] || 'middle', 'dominant-baseline': 'central' }, text); }
    n.setAttribute('class', 'e k-' + kind);
    n.setAttribute('data-s', '');
    if (tr.bins && tr.bins[id] !== undefined) n.setAttribute('data-d', tr.bins[id]);
    n.setAttribute('vector-effect', 'non-scaling-stroke');
    nodes[id] = n;
    if (tr.id === 'a1' && id.startsWith('d13:')) {
      const i = Number(id.split(':')[1]);
      const row = tr.tables.samples.r[i];
      const label = `Sample ${i + 1}: pixel (${row[1]}, ${row[2]}), count ${num(row[3], 4)}`;
      n.appendChild(el('title', {}, label));
      n.setAttribute('tabindex', '0');
      n.setAttribute('aria-label', label);
    }
    svg.appendChild(n);
  }
  // scale bar and north marker, in the lower left and upper right corner
  const sb = el('g', { class: 'sb' });
  const bx = vx + 0.04 * vw, by = vy + vh - 0.05 * vh;
  sb.append(el('line', { x1: bx, y1: by, x2: bx + tr.scale_km, y2: by, 'vector-effect': 'non-scaling-stroke' }),
    el('line', { x1: bx, y1: by - 0.012 * vh, x2: bx, y2: by + 0.012 * vh, 'vector-effect': 'non-scaling-stroke' }),
    el('line', { x1: bx + tr.scale_km, y1: by - 0.012 * vh, x2: bx + tr.scale_km, y2: by + 0.012 * vh, 'vector-effect': 'non-scaling-stroke' }),
    el('text', { x: bx + tr.scale_km / 2, y: by - 0.035 * vh, 'text-anchor': 'middle' },
      (tr.scale_km < 1 ? num(tr.scale_km * 1000, 0) + ' m' : num(tr.scale_km, 0) + ' km')));
  const nx = vx + vw - 0.05 * vw, ny = vy + 0.12 * vh;
  sb.append(el('line', { x1: nx, y1: ny + 0.05 * vh, x2: nx, y2: ny - 0.01 * vh, 'vector-effect': 'non-scaling-stroke' }),
    el('text', { x: nx, y: ny - 0.04 * vh, 'text-anchor': 'middle' }, 'N'));
  svg.appendChild(sb);

  const wrap = h('div', { class: 'stage-wrap', tabindex: '0', role: 'group',
    'aria-label': 'Animation, ' + tr.title + '. Left and right arrow keys change the step, space starts and stops.' });
  wrap.appendChild(svg);
  const sampleInfo = h('div', { class: 'sample-info', hidden: '' });
  wrap.appendChild(sampleInfo);
  for (const [id, n] of Object.entries(nodes)) {
    if (!id.startsWith('d13:')) continue;
    const reveal = () => { sampleInfo.textContent = n.getAttribute('aria-label'); sampleInfo.hidden = false; };
    const hide = () => { sampleInfo.hidden = true; };
    n.addEventListener('focus', reveal); n.addEventListener('mouseenter', reveal);
    n.addEventListener('blur', hide); n.addEventListener('mouseleave', hide);
  }
  const legend = h('div', { class: 'legend' });
  wrap.appendChild(legend);

  const cap = h('p', { class: 'cap', 'aria-live': 'polite' });
  const eq = h('p', { class: 'eq' });
  const bud = h('div', { class: 'bud', hidden: '' });
  const tbl = h('div', { class: 'tb' });
  const side = h('div', { class: 'side' });
  side.append(cap, eq, bud, tbl);

  const btn = (label, cls) => h('button', { type: 'button', class: cls || 'sec' }, label);
  const prevB = btn('Previous'), playB = btn('Play', 'pri'), nextB = btn('Next'), firstB = btn('Restart');
  const range = h('input', { type: 'range', min: 0, max: tr.steps.length - 1, value: 0, step: 1, 'aria-label': 'Step' });
  const count = h('span', { class: 'count' });
  const speed = h('select', { 'aria-label': 'Speed' });
  [['0.5×', 0.5], ['1×', 1], ['2×', 2], ['4×', 4]].forEach(([t, v]) => speed.appendChild(h('option', { value: v }, t)));
  speed.value = '1';
  const ctl = h('div', { class: 'ctl' });
  ctl.append(firstB, prevB, playB, nextB, range, count, speed);

  root.replaceChildren(wrap, ctl, side);

  // summary
  const sum = tr.summary ? h('table', { class: 'sum' }) : null;
  if (sum) {
    const body = sum.createTBody();
    for (const [a, b] of tr.summary) {
      const r = body.insertRow();
      r.appendChild(h('th', { scope: 'row' }, a));
      r.appendChild(h('td', {}, b));
    }
    root.appendChild(h('h3', {}, 'Numbers'));
    root.appendChild(sum);
  }
  const extra = [['cells', 'Covering cells'], ['cells2', 'Covering cells of field G']];
  for (const [key, title] of extra) {
    const c = tr[key];
    if (!c) continue;
    const d = h('details', {});
    d.appendChild(h('summary', {}, (key === 'cells2' ? title : (key === 'cells' && tr.cells2 ? 'Covering cells of field F' : title)) + ' (' + c.rows.length + ')'));
    d.appendChild(makeTable(c.head, c.rows, c.fmt, c.rows.length));
    root.appendChild(d);
  }
  if (tr.attribution) root.appendChild(h('p', { class: 'hint' }, tr.attribution));
  return { svg, nodes, legend, cap, eq, bud, tbl, range, count, playB, prevB, nextB, firstB, speed, wrap };
}

function makeTable(head, rows, fmts, n, hl) {
  const t = h('table');
  const hr = t.createTHead().insertRow();
  head.forEach((x, i) => { const c = h('th', { scope: 'col' }, x); if (fmts[i] !== 's') c.className = 'num'; hr.appendChild(c); });
  const body = t.createTBody();
  rows.slice(0, n).forEach((r, ri) => {
    const tr = body.insertRow();
    if (hl === ri) tr.className = 'hl';
    r.forEach((x, i) => {
      const c = tr.insertCell();
      c.textContent = fmts[i] === 's' ? x : num(x, fmts[i]);
      if (fmts[i] !== 's') c.className = 'num';
    });
  });
  return t;
}

function sizeStage(ui, tr) {
  const w = ui.svg.getBoundingClientRect().width || 640;
  const u = tr.view[2] / w;
  ui.svg.style.setProperty('--u', u);
  // Vertex labels move a fixed screen distance outward from their triangle.
  for (const [id, kind, g] of tr.els) {
    if (kind !== 't' || !/^t(A|B|C|F3|G3)$/.test(id)) continue;
    const field = tr.els.find(e => e[0] === (tr.id === 'a5' ? (id === 'tG3' ? 'fG' : 'fF') : 'fld'));
    if (!field) continue;
    const centre = field[2].reduce((a, p) => [a[0] + p[0] / 3, a[1] + p[1] / 3], [0, 0]);
    const dx = g[0] - centre[0], dy = g[1] - centre[1], len = Math.hypot(dx, dy);
    ui.nodes[id].setAttribute('x', g[0] + dx / len * 18 * u);
    ui.nodes[id].setAttribute('y', g[1] + dy / len * 18 * u);
  }
  for (const [id, kind] of tr.els) if (kind === 'd') ui.nodes[id].setAttribute('r', 3.6 * u);
  const sp = 6 * u;
  ui.svg.querySelectorAll('pattern').forEach(p => {
    p.setAttribute('width', sp); p.setAttribute('height', sp);
    p.querySelector('rect').setAttribute('width', sp); p.querySelector('rect').setAttribute('height', sp);
    p.querySelectorAll('line').forEach(l => {
      l.setAttribute('stroke-width', 1.6 * u);
      if (l.hasAttribute('x2')) l.setAttribute('y2', sp); else l.setAttribute('x2', sp);
    });
  });
  placeLabels(ui, tr);
}

function placeLabels(ui, tr) {
  const u = tr.view[2] / (ui.svg.getBoundingClientRect().width || 640);
  const [x, y, w, ht] = tr.view;
  const occupied = [];
  ui.svg.querySelectorAll('.label-leader').forEach(n => n.remove());
  // Give vertex names priority; move numeric labels only as far as necessary.
  const labels = tr.els.filter(e => e[1] === 't' && ui.nodes[e[0]].dataset.s === 't')
    .sort((a, b) => Number(/^t(A|B|C|F3|G3)$/.test(b[0])) - Number(/^t(A|B|C|F3|G3)$/.test(a[0])));
  for (const [id, , g] of labels) {
    const n = ui.nodes[id], vertex = /^t(A|B|C|F3|G3)$/.test(id);
    const bx = vertex ? Number(n.getAttribute('x')) : g[0];
    const by = vertex ? Number(n.getAttribute('y')) : g[1];
    const box = n.getBBox(), hw = box.width / 2 + 3 * u, hh = box.height / 2 + 2 * u;
    let chosen;
    search: for (const shift of [0, -24, 24, -48, 48]) {
    for (const offset of [0, -18, 18, -36, 36, -54, 54, -72, 72]) {
      const cx = Math.max(x + hw, Math.min(x + w - hw, bx + shift * u));
      const cy = Math.max(y + hh, Math.min(y + ht - hh, by + offset * u));
      const r = [cx - hw, cy - hh, cx + hw, cy + hh];
      if (!occupied.some(b => r[0] < b[2] && b[0] < r[2] && r[1] < b[3] && b[1] < r[3])) {
        chosen = [cx, cy, r]; break search;
      }
    }
    }
    if (!chosen) chosen = [bx, by, [bx - hw, by - hh, bx + hw, by + hh]];
    n.setAttribute('x', chosen[0]); n.setAttribute('y', chosen[1]);
    occupied.push(chosen[2]);
    if (!vertex && Math.hypot(chosen[0] - g[0], chosen[1] - g[1]) > 8 * u) {
      ui.svg.insertBefore(el('line', { class: 'label-leader', x1: g[0], y1: g[1],
        x2: chosen[0], y2: chosen[1], 'vector-effect': 'non-scaling-stroke' }), n);
    }
  }
  const firstLabel = ui.svg.querySelector('.k-t');
  ui.svg.querySelectorAll('.label-leader').forEach(n => ui.svg.insertBefore(n, firstLabel));
}

function render(ui, tr, k) {
  const st = states(tr, k);
  const step = tr.steps[k];
  const used = {};
  for (const [id, kind] of tr.els) {
    const s = st[id] || '';
    ui.nodes[id].setAttribute('data-s', s);
    if (kind === 'd') ui.nodes[id].setAttribute('tabindex', s && id.startsWith('d13:') ? '0' : '-1');
    if (s) used[kind + ':' + s] = true;
  }
  // field outlines are drawn on top of the cells
  for (const [id, kind] of tr.els) if (kind === 'p' && (st[id] === 'field' || st[id] === 'field2')) ui.svg.insertBefore(ui.nodes[id], ui.svg.querySelector('.sb'));
  for (const [id, kind] of tr.els) if (kind === 't') ui.svg.insertBefore(ui.nodes[id], ui.svg.querySelector('.sb'));
  ui.cap.textContent = step.c;
  ui.eq.textContent = step.eq || '';
  ui.eq.hidden = !step.eq;
  // legend: only the states in use, with the ramp when densities are shaded
  ui.legend.replaceChildren();
  for (const key in tr.legend) {
    const [kind, s] = key.includes(':') ? key.split(':') : ['p', key];
    if (!used[kind + ':' + s]) continue;
    const item = h('span', { class: 'lg' });
    const sw = el('svg', { class: 'sw', viewBox: '0 0 22 14', 'aria-hidden': 'true' });
    const shape = kind === 'd' ? el('circle', { cx: 11, cy: 7, r: 4.5 }) : el('rect', { x: 2, y: 2, width: 18, height: 10 });
    shape.setAttribute('class', 'e k-' + (kind === 'd' ? 'd' : 'p'));
    shape.setAttribute('data-s', s);
    shape.setAttribute('vector-effect', 'non-scaling-stroke');
    if (s === 'heat') shape.setAttribute('data-d', 6);
    sw.appendChild(shape);
    item.append(sw, document.createTextNode(tr.legend[key]));
    ui.legend.appendChild(item);
  }
  if (tr.ramp && used['p:heat']) {
    const item = h('span', { class: 'lg ramp' });
    item.append(document.createTextNode(tr.ramp.label + ' ' + num(tr.ramp.min, tr.ramp.min < 10 ? 1 : 0) + ' '));
    for (let i = 0; i < 10; i++) {
      const sw = el('svg', { class: 'sw r', viewBox: '0 0 8 14', 'aria-hidden': 'true' });
      const r = el('rect', { x: 0, y: 2, width: 8, height: 10 });
      r.setAttribute('class', 'e k-p'); r.setAttribute('data-s', 'heat'); r.setAttribute('data-d', i);
      sw.appendChild(r); item.appendChild(sw);
    }
    item.append(document.createTextNode(' ' + num(tr.ramp.max, tr.ramp.max < 10 ? 1 : 0) + (tr.ramp.log ? ' (log scale)' : '')));
    ui.legend.appendChild(item);
  }
  // budget bar
  const b = step.bud;
  ui.bud.hidden = !b;
  if (b) {
    const total = b.r + b.q + b.k;
    const slots = Math.max(b.max, total);
    const bar = h('div', { class: 'slots', role: 'img', 'aria-label': `Budget: result ${b.r}, queue ${b.q}, children ${b.k}; total ${total} of ${b.max}` });
    for (let i = 0; i < slots; i++) {
      const cls = i < b.r ? 'res' : i < b.r + b.q ? 'que' : 'kid';
      bar.appendChild(h('span', { class: 'slot ' + cls + (i >= b.max ? ' over' : '') + (i === b.max ? ' edge' : '') }));
    }
    const legend = h('p', { class: 'hint' }, `Result ${b.r} (solid), queue ${b.q} (outlined), children ${b.k} (dotted); the limit is ${b.max}.`);
    ui.bud.replaceChildren(h('p', { class: 'bt' }, `${b.r} + ${b.q} + ${b.k} = ${total} ${total <= b.max ? '≤' : '>'} ${b.max}`), bar, legend);
  }
  // table
  ui.tbl.replaceChildren();
  if (step.tb) {
    const t = tr.tables[step.tb[0]];
    ui.tbl.appendChild(makeTable(t.h, t.r, t.f, step.tb[1], step.tb[2]));
  }
  ui.range.value = k;
  ui.range.setAttribute('aria-valuetext', `Step ${k + 1} of ${tr.steps.length}`);
  ui.count.textContent = `Step ${k + 1} / ${tr.steps.length}`;
  ui.prevB.disabled = k === 0;
  ui.firstB.disabled = k === 0;
  ui.nextB.disabled = k === tr.steps.length - 1;
  placeLabels(ui, tr);
}

async function init(section) {
  const root = section.querySelector('.player');
  let tr;
  try {
    const res = await fetch(section.dataset.trace);
    if (!res.ok) throw new Error(res.status);
    tr = await res.json();
  } catch (e) {
    root.textContent = 'The data for this animation could not be loaded.';
    return;
  }
  const ui = build(root, tr);
  let k = 0, timer = null;
  const last = tr.steps.length - 1;
  const show = n => { k = Math.max(0, Math.min(last, n)); render(ui, tr, k); if (!timer) ui.playB.textContent = k === last ? 'Replay' : 'Play'; };
  const stop = () => { clearTimeout(timer); timer = null; ui.playB.textContent = k === last ? 'Replay' : 'Play'; ui.cap.setAttribute('aria-live', 'polite'); };
  const dwell = () => (2200 + tr.steps[k].c.length * 22) / Number(ui.speed.value);
  const tick = () => {
    if (k >= last) return stop();
    show(k + 1);
    if (k >= last) return stop();
    timer = setTimeout(tick, dwell());
  };
  const play = () => {
    if (k >= last) show(0);
    ui.playB.textContent = 'Pause';
    ui.cap.setAttribute('aria-live', 'off');
    timer = setTimeout(tick, dwell());
  };
  const toggle = () => (timer ? stop() : play());
  ui.playB.onclick = toggle;
  ui.nextB.onclick = () => { stop(); show(k + 1); };
  ui.prevB.onclick = () => { stop(); show(k - 1); };
  ui.firstB.onclick = () => { stop(); show(0); };
  ui.range.oninput = () => { stop(); show(Number(ui.range.value)); };
  ui.wrap.addEventListener('keydown', e => {
    const map = { ArrowRight: () => { stop(); show(k + 1); }, ArrowLeft: () => { stop(); show(k - 1); },
      Home: () => { stop(); show(0); }, End: () => { stop(); show(last); }, ' ': toggle };
    if (map[e.key]) { e.preventDefault(); map[e.key](); }
  });
  let measuredWidth = 0;
  new ResizeObserver(() => {
    sizeStage(ui, tr);
    const width = ui.svg.getBoundingClientRect().width;
    if (width === measuredWidth) return;
    measuredWidth = width;
    // Reserve the largest step at this width, including its legend and table.
    const side = ui.cap.parentElement;
    side.style.minHeight = ui.legend.style.minHeight = '0';
    let sideHeight = 0, legendHeight = 0;
    ui.cap.setAttribute('aria-live', 'off');
    for (let i = 0; i <= last; i++) {
      render(ui, tr, i);
      sideHeight = Math.max(sideHeight, side.getBoundingClientRect().height);
      legendHeight = Math.max(legendHeight, ui.legend.getBoundingClientRect().height);
    }
    side.style.minHeight = `${Math.ceil(sideHeight)}px`;
    ui.legend.style.minHeight = `${Math.ceil(legendHeight)}px`;
    show(k);
    ui.cap.setAttribute('aria-live', timer ? 'off' : 'polite');
  }).observe(ui.svg);
  sizeStage(ui, tr);
  show(0);
  stop();
  // #a3-5 opens the third animation at its fifth step
  const m = /^#(a\d)-(\d+)$/.exec(location.hash);
  if (m && m[1] === section.id) { show(Number(m[2]) - 1); section.scrollIntoView(); }
  section.dataset.ready = '1';
}

document.querySelectorAll('section.anim').forEach(init);
