// The Upstream view of the Skill Tree skin: a full-page overlay listing the upstream skills we have
// not copied, with a Copy / Ignore / Later choice per skill. Choices are queued in this browser and
// only change files when "Apply" is confirmed. Appended to the skin's client_js (same page, after the
// skin registered itself); it must not call LRL.register again.
(function () {
  const L = window.LRL;
  const KEY = 'upstream';
  let D = null, cards = [], ov = null, list = null, pollTimer = null;
  let choices = L.store.get(KEY, {});
  const view = { q: '', undecided: false };

  const h = (tag, props, ...kids) => {
    const e = document.createElement(tag);
    for (const [a, v] of Object.entries(props || {})) {
      if (a === 'class') e.className = v;
      else if (a.startsWith('on')) e[a] = v;
      else if (v === true) e.setAttribute(a, '');
      else if (v !== false && v != null) e.setAttribute(a, v);
    }
    for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c)));
    return e;
  };
  const key = s => s.repo + '\t' + s.path;
  const saveChoices = () => L.store.set(KEY, choices);
  const queued = () => Object.keys(choices).length;
  const say = (t, cls) => L.say(t, cls);

  function updateButton() {
    const b = document.getElementById('up-open');
    if (b) b.textContent = D ? `Upstream skills (${D.items.length})` : 'Upstream skills';
  }

  async function loadData() {
    const r = await L.api('upstream', {});
    if (!r.ok) { say(r.error || 'could not read the upstream list', 'err'); return; }
    D = r;
    const known = new Set(D.items.map(key));
    for (const k of Object.keys(choices)) if (!known.has(k)) delete choices[k];
    saveChoices();
    updateButton();
    if (ov) buildList();
    if (D.refresh && D.refresh.state === 'running') watchRefresh();
  }

  // ── overlay shell ──────────────────────────────────────────────────────────
  function openOverlay() {
    if (ov) { ov.hidden = false; return; }
    ov = h('div', { class: 'up', role: 'dialog', 'aria-label': 'Upstream skills' });
    const search = h('input', { type: 'search', placeholder: 'Search name, path or description', 'aria-label': 'Search upstream skills',
      oninput: e => { view.q = e.target.value.toLowerCase(); update(); } });
    const und = h('input', { type: 'checkbox', onchange: e => { view.undecided = e.target.checked; update(); } });
    ov.append(
      h('div', { class: 'up-top' },
        h('strong', {}, 'Upstream skills'), h('span', { class: 'up-stat', id: 'up-stat' }),
        search, h('label', {}, und, ' only undecided'),
        h('button', { class: 'plain', id: 'up-refresh', onclick: askRefresh }, 'Refresh from GitHub'),
        h('button', { class: 'plain', onclick: () => { ov.hidden = true; } }, 'Close')),
      h('div', { class: 'up-bar', id: 'up-bar', hidden: true }),
      (list = h('div', { class: 'up-list', id: 'up-list' })),
      h('div', { class: 'up-foot' },
        h('span', { id: 'up-queue' }),
        h('button', { class: 'plain up-apply', id: 'up-apply', onclick: planApply }, 'Apply choices')));
    document.body.append(ov);
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && ov && !ov.hidden && !document.querySelector('.up-modal')) ov.hidden = true; });
    buildList();
  }

  function buildList() {
    list.replaceChildren();
    cards = [];
    if (!D || !D.items.length) {
      list.append(h('p', { class: 'up-empty' },
        D && D.generated ? 'Nothing undecided: every upstream skill we know of is copied or ignored.'
          : 'No upstream list yet. Use "Refresh from GitHub" to build it (a few minutes, paced requests).'));
      update();
      return;
    }
    const byRepo = new Map();
    for (const s of D.items) { if (!byRepo.has(s.repo)) byRepo.set(s.repo, []); byRepo.get(s.repo).push(s); }
    for (const [repo, items] of byRepo) {
      const stat = h('span', { class: 'up-n' });
      const det = h('details', { class: 'up-repo' }, h('summary', {}, h('span', { class: 'mono' }, repo), ' ', stat));
      det.append(h('div', { class: 'up-bulk' },
        h('button', { class: 'plain', onclick: () => { items.forEach(s => { choices[key(s)] = { c: 'ignore' }; }); saveChoices(); update(); } }, 'Ignore all in this repo'),
        h('button', { class: 'plain', onclick: () => { items.forEach(s => { delete choices[key(s)]; }); saveChoices(); update(); } }, 'Clear this repo')));
      for (const s of items) det.append(card(s));
      cards.push({ det, stat, items });
      list.append(det);
    }
    update();
  }

  function card(s) {
    const name = `up-${cards.length}-${Math.random().toString(36).slice(2, 7)}`;
    const desc = h('div', { class: 'up-desc', title: 'Click to expand', onclick: e => e.currentTarget.classList.toggle('open') }, s.desc);
    const dest = h('select', { 'aria-label': `Where to put ${s.name}`, onchange: e => { choices[key(s)] = { c: 'copy', d: e.target.value }; saveChoices(); update(); } },
      h('option', { value: 'flat' }, 'flat (always loaded)'),
      D.groups.map(g => h('option', { value: g }, `group: ${g}`)));
    const radio = (val, label) => {
      const r = h('input', { type: 'radio', name, value: val, onchange: () => {
        if (!val) delete choices[key(s)];
        else choices[key(s)] = val === 'copy' ? { c: 'copy', d: (D.suggest[s.repo] || 'flat') } : { c: 'ignore' };
        saveChoices(); update(); } });
      s['_r_' + val] = r;
      return h('label', { class: 'up-' + (val || 'later') }, r, ' ' + label);
    };
    const node = h('div', { class: 'up-skill' },
      h('div', { class: 'up-name' }, h('strong', {}, s.name), ' ', h('span', { class: 'up-path mono' }, s.path)),
      desc,
      h('div', { class: 'up-choice' }, radio('copy', 'Copy it'), radio('ignore', 'Ignore'), radio('', 'Decide later'), dest));
    s._node = node; s._dest = dest;
    return node;
  }

  function update() {
    if (!D) return;
    let copy = 0, ign = 0;
    for (const { det, stat, items } of cards) {
      let shown = 0, c = 0, i = 0;
      for (const s of items) {
        const ch = choices[key(s)];
        const cur = ch ? ch.c : '';
        s['_r_' + cur].checked = true;
        s._node.className = 'up-skill' + (cur ? ' ' + cur : '');
        s._dest.hidden = cur !== 'copy';
        if (cur === 'copy') { s._dest.value = ch.d || 'flat'; c++; } else if (cur === 'ignore') i++;
        const hit = !view.q || (s.name + ' ' + s.path + ' ' + s.desc).toLowerCase().includes(view.q);
        const vis = hit && !(view.undecided && cur);
        s._node.hidden = !vis;
        if (vis) shown++;
      }
      stat.textContent = `${items.length} skill${items.length === 1 ? '' : 's'}` + (c ? `, ${c} to copy` : '') + (i ? `, ${i} ignored` : '');
      det.hidden = shown === 0;
      if (view.q && shown) det.open = true;
      copy += c; ign += i;
    }
    const total = D.items.length;
    const st = document.getElementById('up-stat');
    if (st) st.textContent = `${total - copy - ign} undecided of ${total} · ${copy} to copy · ${ign} to ignore` + (D.generated ? ` · list from ${D.generated.slice(0, 10)}` : '');
    const q = document.getElementById('up-queue');
    if (q) q.textContent = queued() ? `${queued()} choice${queued() === 1 ? '' : 's'} queued; nothing changes until you apply them.` : 'No choices queued.';
    const ap = document.getElementById('up-apply');
    if (ap) { ap.disabled = !queued(); ap.textContent = queued() ? `Apply ${queued()} choice${queued() === 1 ? '' : 's'}` : 'Apply choices'; }
  }

  // ── refresh the list from GitHub ───────────────────────────────────────────
  function bar(...kids) {
    const b = document.getElementById('up-bar');
    b.replaceChildren(...kids.flat());
    b.hidden = !kids.length;
  }

  function askRefresh() {
    const n = D && D.repo_count ? D.repo_count : 0;
    bar(h('span', {}, `This fetches ${n} upstream repositories from GitHub, one blobless clone and one batched download each, with a 2-second pause between repositories (about ${n * 2} requests, a few minutes). Continue?`),
      h('button', { class: 'plain', onclick: startRefresh }, 'Fetch now'),
      h('button', { class: 'plain', onclick: () => bar() }, 'Cancel'));
  }

  async function startRefresh() {
    bar(h('span', {}, 'Starting...'));
    const r = await L.api('upstream-refresh', {});
    if (!r.ok) { bar(h('span', { class: 'up-err' }, r.error || 'could not start'), h('button', { class: 'plain', onclick: () => bar() }, 'OK')); return; }
    watchRefresh();
  }

  function watchRefresh() {
    clearTimeout(pollTimer);
    const tick = async () => {
      const r = await L.api('upstream-status', {});
      const s = r.refresh || {};
      if (s.state === 'running') {
        if (ov) bar(h('span', {}, 'Fetching from GitHub: ' + (s.progress || 'starting')));
        pollTimer = setTimeout(tick, 2000);
      } else if (s.state === 'error') {
        if (ov) bar(h('span', { class: 'up-err' }, 'Refresh stopped: ' + (s.error || 'unknown error')), h('button', { class: 'plain', onclick: () => bar() }, 'OK'));
      } else {
        if (ov) bar();
        await loadData();
        say('Upstream list refreshed');
      }
    };
    tick();
  }

  // ── plan and apply ─────────────────────────────────────────────────────────
  const picked = () => D.items.filter(s => choices[key(s)]).map(s => ({
    repo: s.repo, path: s.path, choice: choices[key(s)].c, dest: choices[key(s)].d || null }));

  function modal(...kids) {
    document.querySelectorAll('.up-modal').forEach(m => m.remove());
    const m = h('div', { class: 'up-modal', role: 'dialog' }, h('div', { class: 'up-box' }, kids.flat()));
    ov.append(m);
    return m;
  }

  async function planApply() {
    const r = await L.api('upstream-plan', { choices: picked() });
    if (!r.ok) { say(r.error || 'could not plan', 'err'); return; }
    const m = modal(
      h('h2', {}, 'Apply your choices?'),
      r.ignore.length ? h('div', {}, h('h3', {}, `Ignore ${r.ignore.length} skill${r.ignore.length === 1 ? '' : 's'}`),
        h('p', { class: 'up-note' }, 'One line per skill is added to scripts/external-skills-ignore.txt; the update tool then stops listing them. No network.'),
        h('details', {}, h('summary', {}, 'Show the skills'),
          h('ul', {}, r.ignore.map(i => h('li', {}, h('span', { class: 'mono' }, i.repo + ' ' + i.path)))))) : null,
      r.vendor.length ? h('div', {}, h('h3', {}, `Copy ${r.vendor.length} skill${r.vendor.length === 1 ? '' : 's'} from GitHub`),
        h('p', { class: 'up-note' }, `About ${r.requests} GitHub requests from your IP, paced. Each skill becomes an external skill (source.json, pristine .upstream copy) kept current by the update tool.`),
        h('ul', {}, r.vendor.map(v => h('li', {}, h('span', { class: 'mono' }, v.name), ' → ', v.target)))) : null,
      r.problems.length ? h('div', {}, h('h3', { class: 'up-err' }, `${r.problems.length} cannot be applied`),
        h('ul', {}, r.problems.map(p => h('li', {}, h('span', { class: 'mono' }, p.path), ': ', p.error)))) : null,
      h('div', { class: 'up-actions' },
        h('button', { class: 'plain up-apply', disabled: !(r.ignore.length || r.vendor.length), onclick: () => runApply(m) }, 'Apply'),
        h('button', { class: 'plain', onclick: () => m.remove() }, 'Back')));
  }

  async function runApply(m) {
    m.replaceChildren(h('div', { class: 'up-box' }, h('p', {}, 'Applying... copying skills can take a few minutes.')));
    const r = await L.api('upstream-apply', { choices: picked() });
    const res = r.results || [];
    for (const x of res) if (x.ok) delete choices[x.repo + '\t' + x.path];
    saveChoices();
    const bad = res.filter(x => !x.ok);
    m.replaceChildren(h('div', { class: 'up-box' },
      h('h2', {}, r.ok ? 'Done' : 'Finished with problems'),
      h('p', {}, `${res.filter(x => x.ok).length} applied, ${bad.length} failed.`),
      bad.length ? h('ul', {}, bad.map(x => h('li', {}, h('span', { class: 'mono' }, x.path), ': ', x.error))) : null,
      r.note ? h('p', { class: 'up-note' }, r.note) : null,
      h('div', { class: 'up-actions' }, h('button', { class: 'plain', onclick: () => m.remove() }, 'OK'))));
    await loadData();
    await L.refresh();
  }

  // ── wire the header button ─────────────────────────────────────────────────
  function wire() {
    const b = document.getElementById('up-open');
    if (!b) return;
    b.onclick = async () => { if (!D) await loadData(); openOverlay(); };
    loadData();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire); else wire();
})();
