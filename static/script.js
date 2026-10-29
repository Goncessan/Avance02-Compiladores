const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const EJEMPLO = `# REG_SANITARIO ; LOTE ; EXP:AAAA-MM-DD [; TIPO ; ESTADO]
NOC12345-21PE ; LOT2026-X09 ; EXP:2028-12-31
EN54321-19PE ; LOT2025-A1B2 ; EXP:2027-06-15 ; FARMA ; VIGENTE
NSO00123-22PE ; LOT2026-C77 ; EXP:2026-11-20 ; COSMETICO ; VIGENTE
NOC12345-21PE ; LOT2026-X09 ; EXP:2029-01-10
NOC1234-21PE ; LOT2026-X09 ; EXP:2028-12-31
RD22222-20PE ; LOT2026-Z90 ; EXP:2028-02-30
NOC99999-20PE ; LOT2026-Q12 ; EXP:2026-03-01
NOC11111-20PE ; LOT2026-Q12 ; EXP:2028-03-01 ; DIETA ; VIGENTE
NOC11111-20PE ; LOT2026-Q13 ; EXP:2028-03-01 ;`;

let AUT = [], actual = 0, ultimo = null;

/* ---------- Grafo SVG generado por código ---------- */
function dibujar(el, a, id) {
  const n = a.estados.length, cols = Math.min(8, n), W = 110, H = 110, R = 17;
  const pos = i => ({ x: 50 + (i % cols) * W, y: 50 + Math.floor(i / cols) * H });
  const mapa = {};
  a.aristas.forEach(e => (mapa[e.de + '>' + e.a] ||= []).push(e.et));
  let s = `<svg width="${cols * W + 20}" height="${Math.ceil(n / cols) * H + 20}"><defs>
    <marker id="ar${id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
    <path d="M0 0L10 5L0 10z" fill="#94a3b8"/></marker></defs>`;
  for (const k in mapa) {
    const [de, hasta] = k.split('>').map(Number), p = pos(de), q = pos(hasta);
    let et = mapa[k].join(', ');
    if (et.length > 16) et = et.slice(0, 15) + '…';
    if (de === hasta) {
      s += `<path class="ed" marker-end="url(#ar${id})" d="M${p.x - 9} ${p.y - 14} C${p.x - 24} ${p.y - 50} ${p.x + 24} ${p.y - 50} ${p.x + 9} ${p.y - 14}"/>
            <text class="lb" x="${p.x}" y="${p.y - 42}">${esc(et)}</text>`;
      continue;
    }
    const dx = q.x - p.x, dy = q.y - p.y, len = Math.hypot(dx, dy);
    const ady = Math.abs(de - hasta) === 1 && p.y === q.y;
    const curva = ady ? 0 : (de < hasta ? -1 : 1) * (28 + len / 8);
    const c = { x: (p.x + q.x) / 2 - dy / len * curva, y: (p.y + q.y) / 2 + dx / len * curva };
    const rec = (a1, b1) => { const d = Math.hypot(b1.x - a1.x, b1.y - a1.y); return { x: a1.x + (b1.x - a1.x) / d * R, y: a1.y + (b1.y - a1.y) / d * R }; };
    const i0 = rec(p, c), i1 = rec(q, c);
    s += `<path class="ed" marker-end="url(#ar${id})" d="M${i0.x} ${i0.y} Q${c.x} ${c.y} ${i1.x} ${i1.y}"/>
          <text class="lb" x="${.25 * i0.x + .5 * c.x + .25 * i1.x}" y="${.25 * i0.y + .5 * c.y + .25 * i1.y}">${esc(et)}</text>`;
  }
  a.estados.forEach(i => {
    const p = pos(i), f = a.finales.includes(i);
    s += `<g class="n" id="${id}-q${i}"><circle cx="${p.x}" cy="${p.y}" r="${R}"/>${f ? `<circle cx="${p.x}" cy="${p.y}" r="${R - 4}"/>` : ''}
          <text x="${p.x}" y="${p.y + 3}">q${i}</text></g>`;
  });
  const p0 = pos(a.inicial);
  s += `<path class="ed" marker-end="url(#ar${id})" d="M${p0.x - 42} ${p0.y} L${p0.x - R} ${p0.y}"/></svg>`;
  el.innerHTML = s;
}

/* ---------- Etapa 2: ER, AFND, AFD, tabla, quíntupla ---------- */
function mostrar(i) {
  actual = i;
  const t = AUT[i], d = t.afd;
  document.querySelectorAll('#chips button').forEach((b, k) => b.classList.toggle('on', k === i));
  $('er').textContent = t.er;
  dibujar($('gAfnd'), t.afnd, 'gAfnd');
  dibujar($('gAfd'), d, 'gAfd');
  let h = '<thead><tr><th>Estado</th>' + d.clases.map(c => `<th>${esc(c)}</th>`).join('') + '</tr></thead><tbody>';
  d.estados.forEach(e => {
    const ini = e === d.inicial ? '→' : '', fin = d.finales.includes(e) ? '*' : '';
    h += `<tr><td class="${fin ? 'fin' : ini ? 'ini' : ''}">${ini}${fin}q${e}</td>` +
      d.clases.map(c => { const x = d.tabla[e][c]; return `<td>${x === undefined ? '–' : 'q' + x}</td>`; }).join('') + '</tr>';
  });
  $('tTrans').innerHTML = h + '</tbody>';
  const q = d.quintupla;
  $('quin').textContent = `M = (Q, Σ, δ, q0, F)\n\nQ = {${q.Q.join(', ')}}\nΣ = ${q.Sigma}\nq0 = ${q.q0}\nF = {${q.F.join(', ')}}\n\nδ:\n${q.delta.join('\n')}`;
  $('simOut').textContent = '';
  $('cadena').placeholder = 'Ej: ' + ['NOC12345-21PE', 'LOT2026-X09', 'EXP:2028-12-31', 'FARMA', 'VIGENTE', ';'][i];
}

async function simular() {
  document.querySelectorAll('#gAfd .n').forEach(g => g.classList.remove('on', 'bad'));
  const r = await (await fetch('/api/simular', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: AUT[actual].token, cadena: $('cadena').value }) })).json();
  r.ruta.forEach(p => $('gAfd-q' + p.estado)?.classList.add('on'));
  if (r.falla) $('gAfd-q' + r.ruta.at(-1).estado)?.classList.add('bad');
  const camino = r.ruta.map(p => (p.simbolo ? ` —${p.simbolo}→ ` : '') + 'q' + p.estado).join('');
  $('simOut').textContent = camino + (r.falla ? `  ✗ sin transición con «${r.falla}»` : r.ok ? '  ✓ aceptada' : '  ✗ estado no final');
}

/* ---------- Etapa 1: tokens y lexemas ---------- */
function pintarTokens(grupos = {}, errores = []) {
  let h = AUT.map(t => `<tr><td><b>${t.token}</b></td><td>${(grupos[t.token] || []).map(x => `<code>${esc(x)}</code>`).join(', ') || '—'}</td><td><code>${esc(t.er)}</code></td></tr>`).join('');
  if (errores.length) h += `<tr><td><b>ERROR</b></td><td>${errores.map(x => `<code>${esc(x)}</code>`).join(', ')}</td><td>No pertenece a ningún token</td></tr>`;
  $('tTokens').querySelector('tbody').innerHTML = h;
}

/* ---------- Compilar archivo ---------- */
async function compilar() {
  const r = await (await fetch('/api/compilar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ texto: $('texto').value }) })).json();
  ultimo = r;
  const err = [...new Set(r.lineas.flatMap(l => l.tokens.filter(t => t.tok === 'ERROR').map(t => t.lex)))];
  pintarTokens(r.grupos, err);
  const s = r.stats;
  $('sTotal').textContent = s.total; $('sConf').textContent = s.conforme; $('sObs').textContent = s.observado; $('sRec').textContent = s.rechazado;
  $('tRes').querySelector('tbody').innerHTML = r.lineas.map((l, i) =>
    `<tr data-i="${i}"><td>${l.n}</td><td><code>${esc(l.tokens[0]?.lex || l.texto)}</code></td><td><span class="tag ${l.estado}">${l.estado}</span></td><td>${l.fase}</td><td>${esc(l.msg)}</td></tr>`).join('')
    || '<tr><td colspan="5" class="vacio">El archivo no tiene líneas para analizar.</td></tr>';
  $('tSim').querySelector('tbody').innerHTML = r.simbolos.map(x =>
    `<tr><td>${x.registro}</td><td>${x.lote}</td><td>${x.vence}</td><td>${x.tipo}</td><td>${x.estado}</td></tr>`).join('');
  $('ast').textContent = '—';
}

/* ---------- Eventos ---------- */
$('tRes').addEventListener('click', e => {
  const tr = e.target.closest('tr[data-i]'); if (!tr || !ultimo) return;
  const l = ultimo.lineas[tr.dataset.i];
  $('ast').textContent = l.ast || `Sin árbol: error ${l.fase.toLowerCase()}\n${l.msg}`;
});
const leer = f => { if (!f) return; const r = new FileReader(); r.onload = () => { $('texto').value = r.result; compilar(); }; r.readAsText(f); };
$('archivo').addEventListener('change', e => leer(e.target.files[0]));
['dragover', 'dragleave', 'drop'].forEach(ev => $('drop').addEventListener(ev, e => {
  e.preventDefault(); $('drop').classList.toggle('on', ev === 'dragover');
  if (ev === 'drop') leer(e.dataTransfer.files[0]);
}));
$('btnCompilar').onclick = compilar;
$('btnSim').onclick = simular;
$('btnReset').onclick = () => { $('cadena').value = ''; mostrar(actual); };
$('cadena').addEventListener('keydown', e => e.key === 'Enter' && simular());

(async () => {
  $('texto').value = EJEMPLO;
  AUT = await (await fetch('/api/automatas')).json();
  $('chips').innerHTML = AUT.map((t, i) => `<button data-i="${i}">${t.token}</button>`).join('');
  $('chips').onclick = e => e.target.dataset.i && mostrar(+e.target.dataset.i);
  pintarTokens();
  mostrar(0);
})();
