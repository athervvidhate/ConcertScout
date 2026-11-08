// Concert Scout fluid Search study, round 2. Every Concert, status line, interpretation and candidate
// list comes from a real Search replayed offline (data.js). Nothing on the page is invented.
gsap.registerPlugin(Flip, ScrollTrigger);

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const D = (s) => (reduce ? 0 : s);
const sleep = (ms) => new Promise((r) => setTimeout(r, reduce ? Math.min(ms, 60) : ms));

const SEARCHES = window.SEARCHES;
const byId = Object.fromEntries(SEARCHES.map((s) => [s.id, s]));
const ROLL = [
  ['house-chicago', 'House in <b>Chicago</b>'],
  ['new-york-jazz', 'Jazz in <b>New York</b>'],
  ['khruangbin-chicago', 'Like <b>Khruangbin</b>'],
  ['dreamy-guitar-seattle', 'Dreamy <b>guitars</b>'],
];
const DEMO = 'khruangbin-chicago';
const STUDY = ['house-chicago', 'techno-detroit', 'khruangbin-chicago', 'boise-shoegaze', 'four-tet-boise', 'sparse-answer'];

const ICONS = {
  interpret: '<path d="M4 6h16M4 12h11M4 18h7"/>',
  resolve: '<path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
  pool: '<path d="M4 7.5A1.5 1.5 0 0 0 5.5 6h13A1.5 1.5 0 0 0 20 7.5V10a2 2 0 0 0 0 4v2.5a1.5 1.5 0 0 0-1.5 1.5h-13A1.5 1.5 0 0 0 4 16.5V14a2 2 0 0 0 0-4z"/><path d="M14.5 6.5v11" stroke-dasharray="2 2.4"/>',
  match: '<path d="M4 12v0M8 8v8M12 4.5v15M16 8.5v7M20 11v2"/>',
  rank: '<path d="M12 3.5l2.4 5 5.4.7-4 3.8 1 5.4L12 15.8l-4.8 2.6 1-5.4-4-3.8 5.4-.7z"/>',
  done: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  place: '<path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
  artist: '<circle cx="12" cy="8" r="3.6"/><path d="M5 20c1.2-3.6 4-5.5 7-5.5s5.8 1.9 7 5.5"/>',
  sound: '<path d="M4 12v0M8 8v8M12 4.5v15M16 8.5v7M20 11v2"/>',
  when: '<rect x="4" y="5.5" width="16" height="14" rx="2.5"/><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4"/>',
  bookmark: '<path d="M7 4h10v16l-5-3.5L7 20z"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  arrow: '<path d="M4 12h15m-6-6 6 6-6 6"/>',
  out: '<path d="M7 17 17 7M9 7h8v8"/>',
};
const svg = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
const STEPS = ['interpret', 'resolve', 'pool', 'match', 'rank'];

// ---------- Formatting: only what the source record holds ----------
const asDate = (d) => { const [y, m, day] = d.split('-').map(Number); return new Date(y, m - 1, day); };
const fmt = (d, o) => asDate(d).toLocaleDateString('en-US', o);
const shortDate = (d) => fmt(d, { weekday: 'short', month: 'short', day: 'numeric' });
const longDate = (d) => fmt(d, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
const span = (a, b) => (!b || a === b ? fmt(a, { month: 'short', day: 'numeric' }) : asDate(a).getMonth() === asDate(b).getMonth() ? `${fmt(a, { month: 'short', day: 'numeric' })}–${asDate(b).getDate()}` : `${fmt(a, { month: 'short', day: 'numeric' })} – ${fmt(b, { month: 'short', day: 'numeric' })}`);
const clock = (t) => { if (!t) return null; const [h, m] = t.split(':').map(Number); return new Date(2000, 0, 1, h, m).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }); };
const money = (p) => { if (!p || p.min == null) return null; const f = new Intl.NumberFormat('en-US', { style: 'currency', currency: p.currency || 'USD', maximumFractionDigits: 2, minimumFractionDigits: 0 }); return p.max != null && p.max !== p.min ? `${f.format(p.min)}–${f.format(p.max)}` : f.format(p.min); };
const place = (c) => [c.city, c.region].filter(Boolean).join(', ');
const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
const eventOf = (s, kind) => s.events.find((e) => e.event === kind)?.data;
const posterOf = (s) => eventOf(s, 'poster');
const whereOf = (s) => s.events.find((e) => e.event === 'status' && e.data.step === 'pool')?.data.message.replace(/^Looking for Concerts near /, '').replace(/, United States of America$/, '') || null;
// A Concert's lead Artist names it; the rest of the bill follows. A bill with no Artists keeps its own title.
const lead = (c) => c.artists[0] || c.name;
const support = (c) => c.artists.slice(1);

// ---------- Elements ----------
const body = document.body, form = $('#composer'), query = $('#query'), roll = $('#roll'), strip = $('#strip');
const understood = $('#understood'), note = $('#note'), run = $('#run'), runIcon = $('#runIcon'), runText = $('#runText');
const cloud = $('#cloud'), cloudHead = $('#cloudHead'), poster = $('#poster'), results = $('#results'), passed = $('#passed');
const dialog = $('#ticket'), ticketImg = $('#ticketImg');
const saved = new Set();
let runToken = 0, current = null;
let view = 'grid';
try { view = localStorage.getItem('fluid-view') === 'list' ? 'list' : 'grid'; } catch {}

// ---------- Home: rolling example Search + photo strip ----------
const tiles = [];
(function buildStrip() {
  const seen = new Set();
  for (const [id] of ROLL) {
    let n = 0;
    for (const rec of posterOf(byId[id])) {
      const c = rec.concert, name = lead(c);
      if (seen.has(name) || n >= 3) continue;
      seen.add(name); n++;
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'tile'; b.dataset.search = id;
      b.setAttribute('aria-label', `Run the Search “${byId[id].text}”, which found ${name}`);
      b.innerHTML = `<img src="${c.image}" alt="" loading="lazy"><span class="tile-text"><span class="tile-name">${esc(name)}</span><span class="tile-meta">${shortDate(c.date)} · ${esc(c.venue || place(c))}</span></span>`;
      b.addEventListener('click', () => run_(byId[id]));
      strip.append(b); tiles.push(b);
    }
  }
})();

let rollIndex = 0, rollTimer = null;
function showRoll(i, animate) {
  const [id, html] = ROLL[i];
  const next = document.createElement('span');
  next.className = 'roll-word'; next.innerHTML = html;
  const prev = $('.roll-word', roll);
  roll.append(next);
  roll.setAttribute('aria-label', next.textContent);
  tiles.forEach((t) => t.classList.toggle('on', t.dataset.search === id));
  tiles.forEach((t) => t.classList.toggle('lead', t === tiles.find((x) => x.dataset.search === id)));
  if (!animate || reduce) { prev?.remove(); return; }
  if (prev) gsap.to(prev, { yPercent: -100, opacity: 0, duration: 0.5, ease: 'power3.in', onComplete: () => prev.remove() });
  gsap.fromTo(next, { yPercent: 100, opacity: 0 }, { yPercent: 0, opacity: 1, duration: 0.8, delay: 0.18, ease: 'expo.out' });
}
function startRoll() { stopRoll(); if (!reduce) rollTimer = setInterval(() => { rollIndex = (rollIndex + 1) % ROLL.length; showRoll(rollIndex, true); }, 3600); }
function stopRoll() { clearInterval(rollTimer); rollTimer = null; }
showRoll(0, false);
startRoll();

if (!reduce) {
  gsap.from('.headline-lead', { y: 16, opacity: 0, duration: 0.8, ease: 'expo.out', delay: 0.05 });
  gsap.from('.roll-word', { yPercent: 100, opacity: 0, duration: 1, ease: 'expo.out', delay: 0.12 });
  gsap.from([form, '#pitch'], { y: 24, opacity: 0, duration: 1, ease: 'expo.out', delay: 0.25, stagger: 0.08 });
  gsap.from(tiles, { y: 40, opacity: 0, duration: 1, ease: 'expo.out', stagger: 0.05, delay: 0.4 });
}

// ---------- Home: how a Search works, replayed from one real Search, on a loop ----------
const demo = byId[DEMO];
$('#howQuery').textContent = demo.text;
const demoEls = { input: $('#demoInput'), chips: $('#demoChips'), count: $('#demoCount'), names: $('#demoNames'), picks: $('#demoPicks') };
const markDemo = (n) => $$('.how-step').forEach((s, i) => { s.classList.toggle('active', i === n); s.classList.toggle('done', i < n); });
let demoToken = 0;

// The demo replays one fixed Search, so its finished panels are known up front.
const demoEnd = (() => {
  const interp = eventOf(demo, 'interpreted'), cand = eventOf(demo, 'candidates'), recs = posterOf(demo), where = whereOf(demo);
  const sample = [...recs.flatMap((r) => r.concert.artists.filter((a) => cand.names.includes(a))), ...cand.names].filter((n, i, a) => a.indexOf(n) === i).slice(0, 16);
  sample.sort((a, b) => cand.names.indexOf(a) - cand.names.indexOf(b));
  return {
    interp, cand, recs, where,
    picked: new Set(recs.flatMap((r) => r.concert.artists)),
    countHTML: (v) => `<b>${Math.round(v)}</b>Artists with Concerts near ${esc(where)}`,
    html: {
      input: esc(demo.text),
      chips: chipsHTML(interp),
      names: sample.map((a) => `<span class="name">${esc(a)}</span>`).join('') + `<span class="name more">+${cand.total - sample.length} more</span>`,
      picks: recs.map((r) => `<div class="demo-pick"><img src="${r.concert.image}" alt=""><div><b>${esc(lead(r.concert))}</b><span>${shortDate(r.concert.date)} · ${esc(r.concert.venue)}</span></div></div>`).join('')
        + `<p class="demo-why"><b>Why ${esc(lead(recs[0].concert))}:</b> ${esc(recs[0].reason)}</p>`,
    },
  };
})();
demoEnd.html.count = demoEnd.countHTML(demoEnd.cand.total);

// Each panel keeps the height of its finished state at the current width, so the band never changes size
// while the panels fill and empty. Steps that share a row share the tallest height.
function sizeDemo() {
  const panels = $$('.how-demo');
  const heights = panels.map((panel) => {
    const copy = panel.cloneNode(true);
    copy.removeAttribute('id'); copy.querySelectorAll('[id]').forEach((el) => el.removeAttribute('id'));
    Object.assign(copy.style, { position: 'absolute', visibility: 'hidden', height: 'auto', width: panel.offsetWidth + 'px' });
    for (const [key, el] of Object.entries(demoEls)) {
      const twin = el === panel ? copy : panel.contains(el) && copy.querySelector(`.${el.classList[0]}`);
      if (twin) twin.innerHTML = demoEnd.html[key];
    }
    panel.after(copy);
    const h = copy.offsetHeight;
    copy.remove();
    return h;
  });
  const tops = $$('.how-step').map((s) => Math.round(s.getBoundingClientRect().top));
  const oneRow = tops.every((t) => t === tops[0]);
  panels.forEach((p, i) => (p.style.height = (oneRow ? Math.max(...heights) : heights[i]) + 'px'));
}
sizeDemo();
document.fonts.ready.then(sizeDemo);
let sizeTimer;
addEventListener('resize', () => { clearTimeout(sizeTimer); sizeTimer = setTimeout(sizeDemo, 150); });

async function playDemo(live) {
  const { input, chips, count, names, picks } = demoEls;
  const { cand, picked, countHTML, html } = demoEnd;

  // 1. The words, then what was understood
  markDemo(0);
  if (!reduce) for (let i = 1; i <= demo.text.length; i++) { if (!live()) return; input.innerHTML = `${esc(demo.text.slice(0, i))}<span class="caret"></span>`; await sleep(34); }
  input.textContent = demo.text;
  chips.innerHTML = html.chips;
  if (!reduce) gsap.from($$('.chip', chips), { y: 10, scale: 0.85, opacity: 0, duration: 0.6, ease: 'back.out(1.8)', stagger: 0.1 });
  await sleep(1100); if (!live()) return;

  // 2. Every Artist with a Concert there
  markDemo(1);
  const n = { v: reduce ? cand.total : 0 };
  const label = () => (count.innerHTML = countHTML(n.v));
  label();
  if (!reduce) gsap.to(n, { v: cand.total, duration: 1.2, ease: 'power2.out', onUpdate: label });
  names.innerHTML = html.names;
  if (!reduce) gsap.from($$('.name', names), { y: 8, opacity: 0, duration: 0.45, ease: 'expo.out', stagger: 0.04 });
  await sleep(1700); if (!live()) return;

  // 3. The ones that fit
  markDemo(2);
  const pills = $$('.name', names);
  pills.forEach((p) => p.classList.toggle('pick', picked.has(p.textContent)));
  if (!reduce) gsap.to(pills.filter((p) => !p.classList.contains('pick')), { opacity: 0.25, duration: 0.5 });
  picks.innerHTML = html.picks;
  if (!reduce) gsap.from(picks.children, { y: 14, opacity: 0, duration: 0.7, ease: 'expo.out', stagger: 0.12 });
  await sleep(900);
  if (live()) markDemo(3);
}

// Everything in the three panels fades and lifts away together, then the panels are emptied.
async function resetDemo() {
  const parts = Object.values(demoEls);
  markDemo(-1);
  if (!reduce && demoEls.input.textContent) await gsap.to(parts, { opacity: 0, y: -8, duration: 0.6, ease: 'power2.inOut' });
  demoEls.input.replaceChildren();
  for (const el of parts.slice(1)) el.replaceChildren();
  gsap.set(parts, { clearProps: 'opacity,transform' });
}

async function loopDemo() {
  const token = ++demoToken, live = () => token === demoToken;
  await resetDemo();
  while (live()) {
    await playDemo(live);
    if (reduce || !live()) return;
    await sleep(2400); if (!live()) return;
    await resetDemo();
    await sleep(350);
  }
}
const stopDemo = () => demoToken++;
ScrollTrigger.create({ trigger: '#how', start: 'top 70%', end: 'bottom 20%', onEnter: loopDemo, onEnterBack: loopDemo, onLeave: stopDemo, onLeaveBack: stopDemo });

// ---------- Composer ----------
function syncComposer() {
  query.style.height = 'auto';
  query.style.height = Math.min(query.scrollHeight, 140) + 'px';
  form.classList.toggle('ready', query.value.trim().length > 0);
}
query.addEventListener('input', () => { syncComposer(); note.replaceChildren(); if (body.dataset.state === 'home') stopRoll(); });
query.addEventListener('focus', () => { if (body.dataset.state === 'home') stopRoll(); });
query.addEventListener('blur', () => { if (body.dataset.state === 'home' && !query.value.trim()) startRoll(); });
query.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } });
form.addEventListener('submit', (e) => { e.preventDefault(); submit(); });

const norm = (s) => s.toLowerCase().replace(/[^a-z0-9 ]/g, '').replace(/\s+/g, ' ').trim();
function submit() {
  const text = query.value.trim();
  if (!text) { query.focus(); gsap.fromTo(form, { x: -6 }, { x: 0, duration: D(0.5), ease: 'elastic.out(1,.3)' }); return; }
  const match = SEARCHES.find((s) => norm(s.text) === norm(text));
  if (!match) return explain();
  play(match);
}
function run_(search) { query.value = search.text; syncComposer(); play(search); }
function explain() {
  note.innerHTML = `This study replays eight real Searches captured on November 7, 2026. Try one:<div class="picks">${SEARCHES.map((s) => `<button type="button" data-id="${s.id}">${esc(s.text)}</button>`).join('')}</div>`;
  $$('button', note).forEach((b) => b.addEventListener('click', () => run_(byId[b.dataset.id])));
  if (!reduce) gsap.from($$('button', note), { y: 10, opacity: 0, stagger: 0.04, duration: 0.5, ease: 'expo.out' });
}
const outside = (what) => () => { note.textContent = `${what} is outside this study.`; };
$('#locate').addEventListener('click', outside('Location'));
$('#yoursLocate').addEventListener('click', outside('Location'));
$('#spotify').addEventListener('click', outside('Spotify'));
$('#privacy').addEventListener('click', (e) => { e.preventDefault(); outside('The Privacy page')(); window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' }); });

// ---------- State changes: the composer travels, everything else makes room ----------
function setState(next) {
  gsap.killTweensOf(form);
  gsap.set(form, { clearProps: 'transform,opacity,translate,scale,rotate' });
  const flip = Flip.getState(form);
  body.dataset.state = next;
  syncComposer();
  Flip.from(flip, { duration: D(0.8), ease: 'expo.inOut', scale: false, onComplete: syncComposer });
}

// ---------- A Search ----------
async function play(search) {
  const token = ++runToken;
  const live = () => token === runToken;
  stopRoll(); demoToken++; note.replaceChildren(); query.blur();
  if (dialog.open) dialog.close();
  markStudy(search.id);

  if (body.dataset.state === 'home') {
    await gsap.to(['#headline', '#pitch', '#home'], { opacity: 0, y: -14, duration: D(0.28), ease: 'power2.in' });
    gsap.set(['#headline', '#pitch', '#home'], { clearProps: 'opacity,transform' });
  } else {
    await gsap.to([poster, run, understood], { opacity: 0, duration: D(0.25) });
  }
  query.value = search.text; syncComposer();
  understood.replaceChildren(); cloud.replaceChildren(); cloudHead.textContent = ''; results.replaceChildren(); passed.replaceChildren();
  poster.hidden = true; run.hidden = false;
  gsap.set([poster, run, understood], { clearProps: 'opacity,height' });
  $$('.run-bar i').forEach((i) => i.classList.remove('done'));
  runIcon.innerHTML = ''; runText.innerHTML = '';
  setState('working');
  query.readOnly = true;
  gsap.from('.run-card', { y: 30, opacity: 0, duration: D(0.8), ease: 'expo.out', delay: D(0.25) });
  window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' });

  const where = whereOf(search);
  for (const ev of search.events) {
    if (!live()) return;
    if (ev.event === 'status') {
      setStatus(ev.data.step, ev.data.message);
      await sleep(ev.data.step === 'rank' ? 900 : 700);
    } else if (ev.event === 'interpreted') {
      understood.innerHTML = chipsHTML(ev.data);
      if (!reduce) gsap.from($$('.chip', understood), { y: 12, scale: 0.85, opacity: 0, duration: 0.7, ease: 'back.out(1.8)', stagger: 0.08 });
      await sleep(400);
    } else if (ev.event === 'candidates') {
      cloudHead.textContent = `${ev.data.total} Artists with Concerts${where ? ` near ${where}` : ''}`;
      cloud.innerHTML = ev.data.names.map((n) => `<span class="name">${esc(n)}</span>`).join('');
      if (!reduce) gsap.from($$('.name', cloud), { y: 10, opacity: 0, scale: 0.9, duration: 0.5, ease: 'expo.out', stagger: 0.018 });
      await sleep(1400);
    } else if (ev.event === 'poster') {
      query.readOnly = false;
      await showPoster(ev.data, search, live);
    }
  }
}

function setStatus(step, message) {
  const i = STEPS.indexOf(step);
  $$('.run-bar i').forEach((seg, j) => seg.classList.toggle('done', j <= i));
  swap(runIcon, svg(step in ICONS ? step : 'interpret'), 'svg');
  swap(runText, `<span>${esc(message)}</span>`, 'span');
}
function swap(box, html, sel) {
  const prev = $(sel, box);
  box.insertAdjacentHTML('beforeend', html);
  const next = box.lastElementChild;
  if (reduce) { prev?.remove(); return; }
  if (prev) gsap.to(prev, { yPercent: -110, opacity: 0, duration: 0.35, ease: 'power2.in', onComplete: () => prev.remove() });
  gsap.fromTo(next, { yPercent: 110, opacity: 0 }, { yPercent: 0, opacity: 1, duration: 0.6, ease: 'expo.out', delay: prev ? 0.1 : 0 });
}

function chipsHTML({ place: where, artists = [], genres = [], start, end }) {
  const chips = [];
  for (const a of artists) chips.push(['artist', 'Artist', a]);
  if (where) chips.push(['place', 'Place', where.replace(/, United States$/, '')]);
  for (const g of genres) chips.push(['sound', 'Sound', g]);
  if (start) chips.push(['when', 'When', span(start, end)]);
  return chips.map(([kind, label, value]) => `<span class="chip" data-kind="${kind}"><span class="chip-icon">${svg(kind)}</span><span class="chip-kind">${label}</span>${esc(value)}</span>`).join('');
}

// ---------- The Poster ----------
async function showPoster(recs, search, live) {
  setStatus('rank', search.events.filter((e) => e.event === 'status').at(-1).data.message);
  $$('.run-bar i').forEach((s) => s.classList.add('done'));
  swap(runIcon, svg('done'), 'svg');

  const picked = new Set(recs.flatMap((r) => r.concert.artists));
  const pills = $$('.name', cloud);
  pills.forEach((p) => p.classList.toggle('pick', picked.has(p.textContent)));
  if (!reduce) {
    gsap.to(pills.filter((p) => !p.classList.contains('pick')), { opacity: 0.18, scale: 0.94, duration: 0.5, ease: 'power2.out' });
    gsap.from(pills.filter((p) => p.classList.contains('pick')), { scale: 1.12, duration: 0.5, ease: 'back.out(2)' });
  }
  await sleep(recs.length ? 950 : 600);
  if (!live()) return;

  const from = {};
  for (const p of pills) if (p.classList.contains('pick') && !from[p.textContent]) from[p.textContent] = { el: p, rect: p.getBoundingClientRect() };
  run.hidden = true; poster.hidden = false;
  body.dataset.state = 'results';
  current = { search, recs };

  const cand = eventOf(search, 'candidates'), where = whereOf(search), interp = eventOf(search, 'interpreted');
  const when = interp.start ? ` ${span(interp.start, interp.end)}` : '';
  $('#count').textContent = recs.length;
  $('#countWord').textContent = recs.length === 1 ? 'Concert' : 'Concerts';
  $('#posterSub').textContent = cand ? `Picked from ${cand.total} Artists playing${where ? ` near ${where}` : ''}${when}` : '';
  $('#views').hidden = recs.length < 2;
  body.toggleAttribute('data-empty', !recs.length);
  syncViews();
  render();
  renderPassed(recs, cand, where, when);

  if (reduce) return;
  const count = $('#count'), n = { v: 0 };
  gsap.to(n, { v: recs.length, duration: 0.9, ease: 'power2.out', onUpdate: () => { const v = Math.round(n.v); count.textContent = v; $("#countWord").textContent = v === 1 ? "Concert" : "Concerts"; } });
  gsap.from('.poster-head', { y: 16, opacity: 0, duration: 0.7, ease: 'expo.out' });
  if (!recs.length) { gsap.from('.empty > *', { y: 24, opacity: 0, duration: 0.8, ease: 'expo.out', stagger: 0.1 }); }
  revealCards(from);
  if (passed.firstChild) gsap.from(passed, { opacity: 0, y: 12, duration: 0.7, delay: 0.8, ease: 'expo.out' });
}

function revealCards(from) {
  $$('[data-card]', results).forEach((card, i) => {
    const img = $('img', card);
    gsap.fromTo(card, { clipPath: 'inset(0 0 100% 0 round 16px)' }, { clipPath: 'inset(0 0 0% 0 round 16px)', duration: 1, ease: 'expo.inOut', delay: 0.1 + i * 0.07, clearProps: 'clipPath' });
    if (img) gsap.from(img, { scale: 1.18, duration: 1.4, ease: 'expo.out', delay: 0.1 + i * 0.07, clearProps: 'transform' });
    const title = $('.card-name', card), rec = current.recs.find((r) => r.concert.id === card.dataset.card);
    const start = from[lead(rec.concert)];
    if (!start) { gsap.from(title, { opacity: 0, y: 16, duration: 0.7, ease: 'expo.out', delay: 0.5 + i * 0.07 }); return; }
    morphName(start, title, 0.12 + i * 0.06);
  });
}

// The chosen name travels as one pill: the chip, its background and its text move together. The pill keeps
// its proportions while it grows to the title's size and widens to the title's measure. Right as it leaves,
// its text hands over to the title's type on the same left edge and centre line; the dark background fades
// out over the last stretch, leaving the title exactly where the card sets it.
function morphName(start, title, delay) {
  const end = title.getBoundingClientRect(), cs = getComputedStyle(title), pcs = getComputedStyle(start.el);
  const titleSize = parseFloat(cs.fontSize), pillSize = parseFloat(pcs.fontSize), pillPad = parseFloat(pcs.paddingLeft);
  const k = (pillSize * 1.15) / titleSize;                  // scale at which the title's capitals match the pill's letters
  const range = document.createRange(); range.selectNodeContents(title);
  const text = range.getBoundingClientRect();               // the title's own text box, not the full card width
  const padX = pillPad / k;                                 // the pill's own padding, in title-sized units
  const padY = Math.max((start.rect.height / k - text.height) / 2, titleSize * 0.12);
  const endX = titleSize * 0.18, endY = titleSize * 0.08; // tighter as it lands, so the fading pill stays inside the card
  const fly = document.createElement('div');
  fly.className = 'name-fly';
  fly.innerHTML = `<span class="as-pill"></span><span class="as-title"></span>`;
  const [asPill, asTitle] = fly.children;
  asPill.textContent = start.el.textContent;
  Object.assign(asPill.style, { left: padX + 'px', fontSize: pillSize / k + 'px', color: pcs.color });
  asTitle.textContent = title.textContent;
  Object.assign(asTitle.style, { left: padX + 'px', width: Math.ceil(text.width) + 1 + 'px', font: cs.font, textTransform: cs.textTransform, letterSpacing: cs.letterSpacing, color: cs.color, opacity: 0 });
  Object.assign(fly.style, { left: start.rect.left + 'px', top: start.rect.top + 'px', width: start.rect.width / k + 'px', height: start.rect.height / k + 'px', background: pcs.backgroundColor, transform: `scale(${k})` });
  document.body.append(fly);
  gsap.set(title, { opacity: 0 });
  const D = 0.95;
  gsap.timeline({ delay, onComplete: () => { gsap.set(title, { opacity: 1 }); fly.remove(); } })
    .to(fly, { left: end.left - endX, top: end.top - endY, width: text.width + endX * 2, height: text.height + endY * 2, scale: 1, duration: D, ease: 'expo.inOut' }, 0)
    .to(asTitle, { left: endX, duration: D, ease: 'expo.inOut' }, 0)
    .to(asPill, { opacity: 0, duration: D * 0.12, ease: 'none' }, 0)
    .to(asTitle, { opacity: 1, duration: D * 0.14, ease: 'none' }, D * 0.08)
    .to(fly, { backgroundColor: 'rgba(0,0,0,0)', duration: D * 0.4, ease: 'power1.inOut' }, D * 0.45);
}

// Grid sizes follow the count, so 2 or 3 Concerts fill the page as deliberately as 8.
function layout(n) {
  if (n === 2) return ['pair', 'pair'];
  if (n === 4) return ['half', 'half', 'half', 'half'];
  const out = ['hero', 'side', 'side'].slice(0, n);
  let rest = n - out.length;
  while (rest > 0) {
    if (rest === 2 || rest === 4) { out.push('half', 'half'); rest -= 2; }
    else { out.push('', '', ''); rest -= 3; }
  }
  return out;
}

function render() {
  const { recs } = current;
  results.className = 'results';
  if (!recs.length) return renderEmpty();
  if (recs.length === 1) return renderSolo(recs[0]);
  if (view === 'list') return renderList(recs);
  const sizes = layout(recs.length);
  results.className = 'results grid';
  results.innerHTML = recs.map((r, i) => cardHTML(r, sizes[i])).join('');
  wireCards();
}

function factsHTML(c, withDate = true) {
  const facts = [withDate && ['Date', longDate(c.date)], ['Time', clock(c.time)], ['Venue', c.venue], ['City', place(c)], ['Price', money(c.price)]].filter((f) => f && f[1]);
  return facts.map(([k, v], i) => `<div${facts.length % 2 && i === 0 ? ' style="grid-column:1/-1"' : ''}><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join('');
}
const metaOf = (c) => [c.venue, c.city, clock(c.time)].filter(Boolean).map(esc).join(' · ');
const withOf = (c) => (support(c).length ? `with ${support(c).map(esc).join(', ')}` : '');
const imgHTML = (c) => `<img src="${c.image}" alt="">`;
const openHTML = (c) => `<button class="card-open" type="button" data-open="${c.id}" aria-label="Open the Ticket for ${esc(lead(c))}, ${shortDate(c.date)}${c.venue ? ' at ' + esc(c.venue) : ''}"></button>`;

function cardHTML(rec, size) {
  const c = rec.concert;
  return `<article class="card ${size}" data-card="${c.id}">
    <div class="card-photo">${imgHTML(c)}</div>
    <span class="card-date">${shortDate(c.date)}</span>
    ${saveButton(c, false)}
    <div class="card-body"><h3 class="card-name">${esc(lead(c))}</h3><p class="card-meta">${[withOf(c), metaOf(c)].filter(Boolean).join(' · ')}</p><p class="card-why">${esc(rec.reason)}</p></div>
    ${openHTML(c)}
  </article>`;
}

function renderSolo(rec) {
  const c = rec.concert;
  results.className = 'results';
  results.innerHTML = `<article class="solo" data-card="${c.id}">
    <div class="solo-photo">${imgHTML(c)}</div>
    <div class="solo-body">
      <span class="solo-date">${longDate(c.date)}</span>
      <h3 class="card-name">${esc(lead(c))}</h3>
      ${withOf(c) ? `<p class="solo-meta">${withOf(c)}</p>` : ''}
      <dl class="facts">${factsHTML(c, false)}</dl>
      <div class="why"><span class="why-label">Why it fits</span><p>${esc(rec.reason)}</p></div>
      <div class="actions"><a class="primary" href="${esc(c.url)}" target="_blank" rel="noopener">Get tickets${svg('out')}</a>${saveButton(c, true)}</div>
    </div>
  </article>`;
  $$('[data-save]', results).forEach(wireSave);
}

function renderList(recs) {
  results.className = 'results list';
  results.innerHTML = recs.map((r) => {
    const c = r.concert, d = asDate(c.date);
    return `<article class="row" data-card="${c.id}">
      <div class="row-date"><b>${d.getDate()}</b><span>${fmt(c.date, { month: 'short' })} · ${fmt(c.date, { weekday: 'short' })}</span></div>
      <div><h3 class="card-name">${esc(lead(c))}</h3><p class="row-meta">${[withOf(c), metaOf(c)].filter(Boolean).join(' · ')}</p><p class="row-why">${esc(r.reason)}</p>${saveButton(c, false)}</div>
      <div class="row-photo">${imgHTML(c)}</div>
      ${openHTML(c)}
    </article>`;
  }).join('');
  wireCards();
}

function renderEmpty() {
  const s = current.search, cand = eventOf(s, 'candidates'), where = whereOf(s), interp = eventOf(s, 'interpreted');
  const when = interp.start ? ` ${span(interp.start, interp.end)}` : '';
  results.className = 'results';
  results.innerHTML = `<div class="empty">
    <div><h3>Nothing here fits</h3><p>${cand.total} ${cand.total === 1 ? 'Artist plays' : 'Artists play'} near ${esc(where)}${when}. None of them is close to “${esc(s.text)}”.</p></div>
    <div class="empty-actions">
      ${interp.start ? `<button type="button" data-try="dates">Look at the next three months${svg('arrow')}</button>` : ''}
      <button type="button" data-try="anywhere">Look anywhere${svg('arrow')}</button>
      <button type="button" data-try="edit">Change the Search${svg('arrow')}</button>
    </div>
  </div>`;
  $$('[data-try]', results).forEach((b) => b.addEventListener('click', () => {
    if (b.dataset.try === 'edit') { query.focus(); query.select(); return; }
    note.textContent = 'Running a wider Search is outside this study: it replays captured Searches only.';
  }));
}

// Few results invite "is that all?", so show what else was there, as plain names from the same pool.
function renderPassed(recs, cand, where, when) {
  passed.replaceChildren();
  if (!cand || recs.length > 3) return;
  const picked = new Set(recs.flatMap((r) => r.concert.artists));
  const rest = cand.names.filter((n) => !picked.has(n));
  if (!rest.length) return;
  const all = rest.length >= cand.total - picked.size;
  passed.innerHTML = `<h3>${recs.length ? 'Also playing, not picked' : `Everything near ${esc(where)}${when}`}</h3>
    <p>${all ? `${recs.length ? 'The rest of the ' : 'All '}${cand.total} Artists with Concerts near ${esc(where)}${when}.` : `${rest.length} of the ${cand.total} Artists with Concerts near ${esc(where)}${when}.`}</p>
    <div class="names">${rest.map((n, i) => `<span class="name"${i >= 18 ? ' hidden' : ''}>${esc(n)}</span>`).join('')}${rest.length > 18 ? `<button class="name more" type="button">Show ${rest.length - 18} more</button>` : ''}</div>`;
  $('.more', passed)?.addEventListener('click', (e) => { $$('.name[hidden]', passed).forEach((n) => (n.hidden = false)); e.currentTarget.hidden = true; });
}

// ---------- Views: the same Concerts as a grid or a list ----------
function syncViews() {
  $$('#views [role=radio]').forEach((b) => b.setAttribute('aria-checked', b.dataset.view === view));
  const on = $(`#views [data-view="${view}"]`), thumb = $('.views-thumb');
  requestAnimationFrame(() => { thumb.style.width = on.offsetWidth + 'px'; thumb.style.transform = `translateX(${on.offsetLeft - 4}px)`; });
  body.dataset.view = view;
}
let swapping = false;
async function setView(next) {
  if (!current || !current.recs.length || next === view || swapping) return;
  view = next;
  try { localStorage.setItem('fluid-view', view); } catch {}
  syncViews();
  if (reduce) return render();
  swapping = true;
  await gsap.to(results, { opacity: 0, y: -8, duration: 0.2, ease: 'power2.in' });
  render();
  gsap.set(results, { opacity: 1, y: 0 });
  const items = $$('[data-card]', results);
  gsap.from(items, { opacity: 0, y: 16, duration: 0.55, ease: 'expo.out', stagger: 0.04, clearProps: 'opacity,transform' });
  gsap.from($$('img', results), { scale: 1.06, duration: 0.8, ease: 'expo.out', stagger: 0.04, clearProps: 'transform' });
  swapping = false;
}
$$('#views [role=radio]').forEach((b) => b.addEventListener('click', () => setView(b.dataset.view)));
$('#views').addEventListener('keydown', (e) => {
  if (!['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
  e.preventDefault();
  setView(view === 'grid' ? 'list' : 'grid');
  $(`#views [data-view="${view}"]`).focus();
});

// ---------- Saving ----------
function wireCards() {
  const map = Object.fromEntries(current.recs.map((r) => [r.concert.id, r]));
  $$('[data-open]', results).forEach((b) => b.addEventListener('click', () => openTicket(map[b.dataset.open], b.closest('[data-card]'))));
  $$('[data-save]', results).forEach(wireSave);
}
function saveButton(c, wide) {
  const on = saved.has(c.id);
  return `<button class="save${wide ? ' save-wide' : ''}" type="button" data-save="${c.id}" aria-pressed="${on}" aria-label="Save ${esc(lead(c))}, ${shortDate(c.date)}"><span class="off">${svg('bookmark')}</span><span class="on">${svg('check')}</span><span class="save-label">${wide && !on ? 'Save' : 'Saved'}</span></button>`;
}
function wireSave(btn) {
  btn.addEventListener('click', (e) => {
    const r = btn.getBoundingClientRect();
    btn.style.setProperty('--x', (e.clientX ? e.clientX - r.left : r.width / 2) + 'px');
    btn.style.setProperty('--y', (e.clientY ? e.clientY - r.top : r.height / 2) + 'px');
    const id = btn.dataset.save;
    saved.has(id) ? saved.delete(id) : saved.add(id);
    $$(`[data-save="${id}"]`).forEach((b) => {
      const on = saved.has(id);
      b.setAttribute('aria-pressed', on);
      if (b.classList.contains('save-wide')) $('.save-label', b).textContent = on ? 'Saved' : 'Save';
      if (on && !reduce) gsap.fromTo($('.on svg', b), { scale: 0.3, rotate: -30 }, { scale: 1, rotate: 0, duration: 0.6, ease: 'back.out(2.5)' });
    });
    updateBadge();
  });
}
function updateBadge() {
  const badge = $('#badge'), num = $('.badge-num', badge), n = saved.size;
  badge.setAttribute('aria-label', `${n} saved`);
  if (!n) { gsap.to(badge, { scale: 0, duration: D(0.25), onComplete: () => { badge.hidden = true; gsap.set(badge, { clearProps: 'scale' }); } }); return; }
  const wasHidden = badge.hidden, up = n > Number(num.textContent);
  badge.hidden = false;
  num.textContent = n;
  if (reduce) return;
  if (wasHidden) gsap.from(badge, { scale: 0, duration: 0.6, ease: 'back.out(2.5)' });
  else gsap.fromTo(num, { yPercent: up ? 100 : -100, opacity: 0 }, { yPercent: 0, opacity: 1, duration: 0.45, ease: 'expo.out' });
}

// ---------- Ticket: the photo opens into it ----------
let openCard = null;
function openTicket(rec, card) {
  const c = rec.concert;
  $('#ticketTitle').textContent = lead(c);
  const bill = [support(c).length ? `with ${support(c).join(', ')}` : '', c.name && !c.name.toLowerCase().startsWith(lead(c).toLowerCase()) ? c.name : ''].filter(Boolean).join(' · ');
  $('#ticketLineup').textContent = bill;
  $('#ticketFacts').innerHTML = factsHTML(c);
  $('#ticketWhy').textContent = rec.reason;
  const also = rec.also.slice(0, 6);
  $('#ticketAlso').innerHTML = also.length ? `<h3>Other dates</h3><div class="also-list">${also.map((a) => `<a href="${esc(a.url)}" target="_blank" rel="noopener">${shortDate(a.date)}${a.venue && a.venue !== c.venue ? ' · ' + esc(a.venue) : ''}</a>`).join('')}</div>` : '';
  $('#ticketLink').href = c.url;
  $('#ticketSave').outerHTML = saveButton(c, true).replace('<button class="save save-wide"', '<button id="ticketSave" class="save save-wide"');
  wireSave($('#ticketSave'));

  const cardImg = $('img', card);
  ticketImg.src = c.image;
  openCard = card;
  dialog.showModal();
  if (reduce) return;
  const sheet = $('.ticket-sheet'), box = $('.ticket-photo');
  sheet.scrollTop = 0;
  const frame = frameOf(card), fly = travel(cardImg, frame.rect, frame.radius);
  gsap.set([cardImg, ticketImg], { opacity: 0 });
  const to = box.getBoundingClientRect(), clip = sheetClip();
  // The photo lands first. The sheet then appears clipped to exactly the photo and opens out from behind it.
  gsap.set(sheet, { opacity: 0, clipPath: clip.photo });
  gsap.timeline()
    .from('#scrim', { opacity: 0, duration: 0.45, ease: 'power2.out' }, 0)
    .to(fly, { left: to.left, top: to.top, width: to.width, height: to.height, borderRadius: photoRadius(), duration: 0.7, ease: 'expo.inOut',
      onComplete: () => { gsap.set(sheet, { opacity: 1 }); gsap.set(ticketImg, { opacity: 1 }); fly.remove(); } }, 0)
    .to(sheet, { clipPath: clip.whole, duration: 0.6, ease: 'expo.out', clearProps: 'clipPath' }, 0.7)
    .from($$('.ticket-body > *'), { x: clip.stacked ? 0 : -24, y: clip.stacked ? -16 : 0, opacity: 0, duration: 0.55, ease: 'expo.out', stagger: 0.04 }, 0.72)
    .fromTo('#close', { scale: 0, rotate: -90 }, { scale: 1, rotate: 0, duration: 0.5, ease: 'back.out(2)', clearProps: 'transform' }, 0.85);
}

// Clip paths for the sheet: just its photo, or all of it. Same shape of string, so GSAP can tween between them.
function sheetClip() {
  const sheet = $('.ticket-sheet'), sr = sheet.getBoundingClientRect(), pr = $('.ticket-photo').getBoundingClientRect();
  const r = radiusOf(sheet).split(' ')[0] || '0px', stacked = pr.width >= sr.width - 1;
  const right = stacked ? 0 : Math.round(sr.right - pr.right), bottom = stacked ? Math.round(sr.bottom - pr.bottom) : 0;
  return { stacked, photo: `inset(0px ${right}px ${bottom}px 0px round ${r})`, whole: `inset(0px 0px 0px 0px round ${r})` };
}

// A copy of the photo travels between the card and the Ticket inside the dialog's top layer.
// It keeps object-fit: cover while its box changes, so the crop eases instead of stretching or snapping.
function travel(img, rect, radius) {
  const fly = document.createElement('img');
  fly.className = 'fly-photo'; fly.src = img.currentSrc || img.src; fly.alt = '';
  Object.assign(fly.style, { left: rect.left + 'px', top: rect.top + 'px', width: rect.width + 'px', height: rect.height + 'px', borderRadius: radius });
  dialog.append(fly);
  return fly;
}
const radiusOf = (el) => getComputedStyle(el).borderRadius;
// What the visitor sees of a card's photo: the frame that crops it, with that frame's corners.
function frameOf(card) {
  const row = $('.row-photo', card), solo = $('.solo-photo', card);
  const box = row || solo || card;
  return { rect: box.getBoundingClientRect(), radius: radiusOf(row || card) };
}
function photoRadius() {
  if (innerWidth <= 640) return '0px';
  const r = radiusOf($('.ticket-sheet'));
  return innerWidth <= 900 ? `${r} ${r} 0 0` : `${r} 0 0 ${r}`;
}

let closing = false;
function closeTicket() {
  if (!dialog.open || closing) return;
  const cardImg = openCard && $('img', openCard);
  const done = () => {
    closing = false;
    dialog.close();
    if (cardImg) gsap.set(cardImg, { opacity: 1 });
    $('[data-open]', openCard)?.focus({ preventScroll: true });
  };
  if (reduce || !cardImg) return done();
  closing = true;
  const sheet = $('.ticket-sheet'), clip = sheetClip(), from = $('.ticket-photo').getBoundingClientRect(), frame = frameOf(openCard), to = frame.rect;
  // The details fold back behind the photo, then the photo returns to its card.
  gsap.timeline({ onComplete: () => { gsap.set(['#scrim', sheet, ticketImg, '.ticket-body > *'], { clearProps: 'opacity,transform,clipPath' }); done(); } })
    .to($$('.ticket-body > *'), { opacity: 0, duration: 0.18, ease: 'power1.in' }, 0)
    .fromTo(sheet, { clipPath: clip.whole }, { clipPath: clip.photo, duration: 0.32, ease: 'power3.in' }, 0)
    .add(() => {
      const fly = travel(ticketImg, from, photoRadius());
      gsap.set(sheet, { opacity: 0 });
      gsap.to(fly, { left: to.left, top: to.top, width: to.width, height: to.height, borderRadius: frame.radius, duration: 0.6, ease: 'expo.inOut', onComplete: () => fly.remove() });
    }, 0.32)
    .to('#scrim', { opacity: 0, duration: 0.5, ease: 'power2.inOut' }, 0.3)
    .to({}, { duration: 0.6 }, 0.32);
}
$('#close').addEventListener('click', closeTicket);
dialog.addEventListener('cancel', (e) => { e.preventDefault(); closeTicket(); });
dialog.addEventListener('click', (e) => { if (e.target === dialog || e.target.id === 'scrim') closeTicket(); });

// ---------- Back to the start ----------
$('#brand').addEventListener('click', async () => {
  runToken++;
  if (dialog.open) closeTicket();
  markStudy(null);
  if (body.dataset.state === 'home') return;
  await gsap.to([poster, run, understood], { opacity: 0, duration: D(0.25) });
  poster.hidden = true; run.hidden = true; understood.replaceChildren(); results.replaceChildren(); passed.replaceChildren();
  gsap.set([poster, run, understood], { clearProps: 'opacity' });
  query.value = ''; query.readOnly = false; syncComposer();
  setState('home');
  window.scrollTo({ top: 0 });
  if (!reduce) gsap.from(['#headline', '#pitch', '#home'], { opacity: 0, y: 20, duration: 0.8, ease: 'expo.out', delay: 0.3, stagger: 0.08 });
  showRoll(rollIndex, false);
  startRoll();
  ScrollTrigger.refresh();
});
$('#savedLink').addEventListener('click', () => { note.textContent = saved.size ? `${saved.size} saved. Saved Concerts is outside this study.` : 'Save a Concert from a Search and it lands here. Saved Concerts is outside this study.'; });
$('#tasteLink').addEventListener('click', outside('Your Taste'));

// ---------- Study bar: jump to a Search by how many Concerts it found ----------
$('#studyPicks').innerHTML = STUDY.map((id) => `<button type="button" data-study="${id}" title="${esc(byId[id].text)}" aria-label="${posterOf(byId[id]).length} results: ${esc(byId[id].text)}">${posterOf(byId[id]).length}</button>`).join('');
$$('[data-study]').forEach((b) => b.addEventListener('click', () => run_(byId[b.dataset.study])));
function markStudy(id) { $$('[data-study]').forEach((b) => b.setAttribute('aria-current', b.dataset.study === id)); }

// ---------- Study bar: light or dark Moss. The colours live in style.css; this sets data-mode on <html>. ----------
const root = document.documentElement, modeBtn = $('#modeBtn');
function setMode(mode, animate) {
  try { localStorage.setItem('fluid-mode', mode); } catch {}
  try { const url = new URL(location.href); url.searchParams.set('mode', mode); history.replaceState(null, '', url); } catch {}
  const apply = () => { root.dataset.mode = mode; modeBtn.setAttribute('aria-pressed', mode === 'dark'); };
  if (animate && !reduce && document.startViewTransition) document.startViewTransition(apply); else apply();
}
modeBtn.addEventListener('click', () => setMode(root.dataset.mode === 'dark' ? 'light' : 'dark', true));
setMode(root.dataset.mode === 'dark' ? 'dark' : 'light', false);
