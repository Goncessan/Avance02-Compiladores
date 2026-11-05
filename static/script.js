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

/* ---------- Grafo SVG por capas (izquierda → derecha) ---------- */
function dibujar(el, a, id) {
  const R = 16, LW = 84, LH = 58, n = a.estados.length, capa = {}, x = {}, y = {};
  a.estados.forEach(i => capa[i] = 0);
  for (let k = 0; k < n; k++) a.aristas.forEach(e => { if (e.de !== e.a && capa[e.a] < capa[e.de] + 1 && capa[e.de] + 1 <= n) capa[e.a] = capa[e.de] + 1; });
  const cols = {}; a.estados.forEach(i => (cols[capa[i]] ||= []).push(i));
  const maxL = Math.max(...Object.keys(cols).map(Number)), H = Math.max(...Object.values(cols).map(c => c.length)) * LH + 50;
  const bar = i => { const p = a.aristas.filter(e => e.a === i && y[e.de] !== undefined).map(e => y[e.de]); return p.length ? p.reduce((s, v) => s + v, 0) / p.length : 0; };
  for (let l = 0; l <= maxL; l++) {
    const c = cols[l] || []; c.sort((p, q) => bar(p) - bar(q) || p - q);
    c.forEach((i, k) => { x[i] = 45 + l * LW; y[i] = H / 2 + (k - (c.length - 1) / 2) * LH; });
  }
  const mapa = {}; a.aristas.forEach(e => (mapa[e.de + '>' + e.a] ||= []).push(e.et));
  const rec = (p, c) => { const d = Math.hypot(c.x - p.x, c.y - p.y) || 1; return { x: p.x + (c.x - p.x) / d * R, y: p.y + (c.y - p.y) / d * R }; };
  let s = `<svg width="${90 + maxL * LW}" height="${H}"><defs><marker id="ar${id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="#94a3b8"/></marker></defs>`;
  for (const k in mapa) {
    const [u, v] = k.split('>').map(Number), p = { x: x[u], y: y[u] }, q = { x: x[v], y: y[v] }, dl = capa[v] - capa[u];
    let et = mapa[k].join(', '); if (et.length > 14) et = et.slice(0, 13) + '…';
    const c = { x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 - (dl > 1 ? Math.min(70, 12 + 10 * dl) : 0) };
    const i0 = rec(p, c), i1 = rec(q, c);
    s += `<path class="ed" marker-end="url(#ar${id})" d="M${i0.x} ${i0.y} Q${c.x} ${c.y} ${i1.x} ${i1.y}"/>
          <text class="lb" x="${.25 * i0.x + .5 * c.x + .25 * i1.x}" y="${.25 * i0.y + .5 * c.y + .25 * i1.y - (dl > 1 ? 0 : 5)}">${esc(et)}</text>`;
  }
  a.estados.forEach(i => {
    const f = a.finales.includes(i);
    s += `<g class="n" id="${id}-q${i}"><circle cx="${x[i]}" cy="${y[i]}" r="${R}"/>${f ? `<circle cx="${x[i]}" cy="${y[i]}" r="${R - 4}"/>` : ''}<text x="${x[i]}" y="${y[i] + 3}">q${i}</text></g>`;
  });
  s += `<path class="ed" marker-end="url(#ar${id})" d="M${x[a.inicial] - 40} ${y[a.inicial]} L${x[a.inicial] - R} ${y[a.inicial]}"/></svg>`;
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
  $('trans').textContent = q.delta.join('\n');
  $('quin').textContent = `M = (Q, Σ, δ, q0, F)\n\nQ = {${q.Q.join(', ')}}\nΣ = ${q.Sigma}\nδ = ver tabla y transiciones\nq0 = ${q.q0}\nF = {${q.F.join(', ')}}`;
  $('simOut').textContent = '';
  $('cadena').placeholder = 'Ej: ' + ['NOC12345-21PE', 'LOT2026-X09', 'EXP:2028-12-31', 'FARMA', 'VIGENTE', ';', '\\n'][i];
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
  const cod = l => l.map(x => `<code>${esc(x)}</code>`).join(', ') || '—';
  let h = AUT.map(t => `<tr><td><b>TOKEN_${t.token}</b></td><td><code>${esc(t.ejemplo)}</code></td><td><code>${esc(t.er)}</code></td><td>${cod(grupos[t.token] || [])}</td></tr>`).join('');
  if (errores.length) h += `<tr><td><b>ERROR</b></td><td>—</td><td>No pertenece a ningún token</td><td>${cod(errores)}</td></tr>`;
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
  $('ast').textContent = '—'; $('deriv').textContent = '—';
}

/* ---------- Eventos ---------- */
$('tRes').addEventListener('click', e => {
  const tr = e.target.closest('tr[data-i]'); if (!tr || !ultimo) return;
  const l = ultimo.lineas[tr.dataset.i];
  $('deriv').textContent = l.deriv.join('\n⇒ ') || '—';
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
  $('chips').innerHTML = AUT.map((t, i) => `<button data-i="${i}">TOKEN_${t.token}</button>`).join('');
  $('chips').onclick = e => e.target.dataset.i && mostrar(+e.target.dataset.i);
  pintarTokens();
  mostrar(0);
})();
