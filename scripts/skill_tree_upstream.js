// The Upstream view of the Skill Tree skin: a full-page overlay with two tabs.
//   "Not copied": upstream skills we have not copied, each with Copy it / Ignore / Decide later.
//   "Installed": every skill in this checkout with its source, local changes and timestamps, each with
//                Keep / Remove (only skills copied from upstream can be removed).
//   "Review":    every queued choice in one editable list; "Continue to apply" opens the Apply dialog.
// Choices are queued in this browser and only change files when "Apply" is confirmed. Appended to the
// skin's client_js (same page, after the skin registered itself); it must not call LRL.register again.
(function () {
  const L = window.LRL;
  const KEY = 'upstream';
  let D = null, INST = null, ov = null, listBox = null, pollTimer = null;
  let tab = 'new';
  let newCards = [], instCards = [];
  let choices = L.store.get(KEY, {});
  const view = { q: '', undecided: false, modified: false };

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
  const rmKey = s => 'rm\t' + s.dir;
  const saveChoices = () => L.store.set(KEY, choices);
  const queued = () => Object.keys(choices).length;
  const say = (t, cls) => L.say(t, cls);
  const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
  const day = iso => (iso || '').slice(0, 10);
  const ago = iso => {
    if (!iso) return '';
    const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
    return d <= 0 ? 'today' : d === 1 ? 'yesterday' : d < 60 ? `${d} days ago` : `${Math.round(d / 30)} months ago`;
  };
  const when = iso => iso ? `${day(iso)} (${ago(iso)})` : 'unknown';

  function updateButton() {
    const b = document.getElementById('up-open');
    if (b) b.textContent = D ? `Upstream skills (${D.items.length})` : 'Upstream skills';
  }

  async function loadData() {
    const r = await L.api('upstream', {});
    if (!r.ok) { say(r.error || 'could not read the upstream list', 'err'); return; }
    D = r;
    const known = new Set(D.items.map(key));
    for (const k of Object.keys(choices)) if (!k.startsWith('rm\t') && !known.has(k)) delete choices[k];
    saveChoices();
    updateButton();
    if (ov) buildNew();
    if (D.refresh && D.refresh.state === 'running') watchRefresh();
  }

  async function loadInstalled() {
    const r = await L.api('installed', {});
    if (!r.ok) { say(r.error || 'could not read the installed skills', 'err'); return; }
    INST = r.skills;
    const known = new Set(INST.map(s => 'rm\t' + s.dir));
    for (const k of Object.keys(choices)) if (k.startsWith('rm\t') && !known.has(k)) delete choices[k];
    saveChoices();
    if (ov) buildInstalled();
  }

  // ── overlay shell ──────────────────────────────────────────────────────────
  function openOverlay() {
    if (ov) { ov.hidden = false; return; }
    ov = h('div', { class: 'up', role: 'dialog', 'aria-label': 'Upstream skills' });
    const search = h('input', { type: 'search', placeholder: 'Search name, path or description', 'aria-label': 'Search skills',
      oninput: e => { view.q = e.target.value.toLowerCase(); update(); } });
    const und = h('label', { id: 'up-f-und' }, h('input', { type: 'checkbox', onchange: e => { view.undecided = e.target.checked; update(); } }), ' only undecided');
    const mod = h('label', { id: 'up-f-mod' }, h('input', { type: 'checkbox', onchange: e => { view.modified = e.target.checked; update(); } }), ' only with local changes');
    ov.append(
      h('div', { class: 'up-top' },
        h('strong', {}, 'Skills'),
        h('div', { class: 'up-tabs', role: 'tablist' },
          h('button', { class: 'plain', id: 'up-t-new', role: 'tab', onclick: () => setTab('new') }, 'Not copied'),
          h('button', { class: 'plain', id: 'up-t-inst', role: 'tab', onclick: () => setTab('installed') }, 'Installed'),
          h('button', { class: 'plain', id: 'up-t-rev', role: 'tab', onclick: () => setTab('review') }, 'Review')),
        h('span', { class: 'up-stat', id: 'up-stat' }),
        search, und, mod,
        h('button', { class: 'plain', id: 'up-refresh', onclick: askRefresh }, 'Refresh from GitHub'),
        h('button', { class: 'plain', onclick: () => { ov.hidden = true; } }, 'Close')),
      h('div', { class: 'up-bar', id: 'up-bar', hidden: true }),
      (listBox = h('div', { class: 'up-list', id: 'up-list' })),
      h('div', { class: 'up-foot' },
        h('span', { id: 'up-queue' }),
        h('button', { class: 'plain up-apply', id: 'up-apply', onclick: () => { if (tab === 'review') planApply(); else setTab('review'); } }, 'Review choices')));
    document.body.append(ov);
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && ov && !ov.hidden && !document.querySelector('.up-modal')) ov.hidden = true; });
    buildNew();
    setTab(tab);
  }

  async function setTab(t) {
    tab = t;
    if ((t === 'installed' || (t === 'review' && Object.keys(choices).some(k => k.startsWith('rm\t')))) && !INST) await loadInstalled();
    document.getElementById('up-t-new').setAttribute('aria-selected', String(t === 'new'));
    document.getElementById('up-t-inst').setAttribute('aria-selected', String(t === 'installed'));
    document.getElementById('up-t-new').textContent = `Not copied${D ? ` (${D.items.length})` : ''}`;
    document.getElementById('up-t-inst').textContent = `Installed${INST ? ` (${INST.length})` : ''}`;
    document.getElementById('up-t-rev').setAttribute('aria-selected', String(t === 'review'));
    document.getElementById('up-f-und').hidden = t !== 'new';
    document.getElementById('up-f-mod').hidden = t !== 'installed';
    document.getElementById('up-refresh').hidden = t !== 'new';
    update();
  }

  function mount(id) {
    let p = document.getElementById(id);
    if (!p) { p = h('div', { id }); listBox.append(p); }
    p.replaceChildren();
    return p;
  }

  // ── tab: not copied ────────────────────────────────────────────────────────
  function buildNew() {
    const pane = mount('up-pane-new');
    newCards = [];
    if (!D || !D.items.length) {
      pane.append(h('p', { class: 'up-empty' },
        D && D.generated ? 'Nothing undecided: every upstream skill we know of is copied or ignored.'
          : 'No upstream list yet. Use "Refresh from GitHub" to build it (a few minutes, paced requests).'));
      update();
      return;
    }
    const byRepo = new Map();
    for (const s of D.items) { if (!byRepo.has(s.repo)) byRepo.set(s.repo, []); byRepo.get(s.repo).push(s); }
    for (const [repo, items] of byRepo) {
      const stat = h('span', { class: 'up-n' });
      const upd = items[0].repo_updated ? ` · upstream last commit ${day(items[0].repo_updated)}` : '';
      const det = h('details', { class: 'up-repo' }, h('summary', {}, h('span', { class: 'mono' }, repo), ' ', stat, h('span', { class: 'up-n' }, upd)));
      det.append(h('div', { class: 'up-bulk' },
        h('button', { class: 'plain', onclick: () => { items.forEach(s => { choices[key(s)] = { c: 'ignore' }; }); saveChoices(); update(); } }, 'Ignore all in this repo'),
        h('button', { class: 'plain', onclick: () => { items.forEach(s => { delete choices[key(s)]; }); saveChoices(); update(); } }, 'Clear this repo')));
      for (const s of items) det.append(newCard(s));
      newCards.push({ det, stat, items });
      pane.append(det);
    }
    update();
  }

  function newCard(s) {
    const name = `up-${newCards.length}-${Math.random().toString(36).slice(2, 7)}`;
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

  // ── tab: installed ─────────────────────────────────────────────────────────
  function buildInstalled() {
    const pane = mount('up-pane-inst');
    instCards = [];
    if (!INST || !INST.length) { pane.append(h('p', { class: 'up-empty' }, 'No installed skills found.')); update(); return; }
    const byGroup = new Map();
    for (const s of INST) { if (!byGroup.has(s.group)) byGroup.set(s.group, []); byGroup.get(s.group).push(s); }
    const order = [...byGroup.keys()].sort((a, b) => a === 'flat' ? -1 : b === 'flat' ? 1 : a.localeCompare(b));
    for (const g of order) {
      const items = byGroup.get(g).sort((a, b) => a.name.localeCompare(b.name));
      const stat = h('span', { class: 'up-n' });
      const det = h('details', { class: 'up-repo' }, h('summary', {}, h('span', { class: 'mono' }, g === 'flat' ? 'flat skills (always loaded)' : `group: ${g}`), ' ', stat));
      for (const s of items) det.append(instCard(s));
      instCards.push({ det, stat, items });
      pane.append(det);
    }
    update();
  }

  function instCard(s) {
    const name = `ui-${Math.random().toString(36).slice(2, 9)}`;
    const badges = [];
    if (s.override) badges.push(h('span', { class: 'up-badge mod', title: 'override.patch: our edits on top of upstream' }, `local changes: ${plural(s.override.lines, 'line')} in ${plural(s.override.files, 'file')}`));
    if (s.dirty) badges.push(h('span', { class: 'up-badge dirty', title: 'git status shows uncommitted changes in this skill' }, 'uncommitted changes'));
    if (s.off) badges.push(h('span', { class: 'up-badge' }, 'switched off'));
    if (s.slash_only) badges.push(h('span', { class: 'up-badge' }, 'slash-only'));
    badges.push(h('span', { class: 'up-badge' + (s.external ? '' : ' own') }, s.external ? s.repo : 'own skill'));
    const times = s.external
      ? `Last synced from upstream: ${when(s.synced)} · pinned ${s.pinned} · last changed in this repo: ${when(s.changed)}`
      : `Last changed in this repo: ${when(s.changed)}`;
    const radio = (val, label) => {
      const r = h('input', { type: 'radio', name, value: val, onchange: () => {
        if (val) choices[rmKey(s)] = { c: 'remove' }; else delete choices[rmKey(s)];
        saveChoices(); update(); } });
      s['_i_' + val] = r;
      return h('label', { class: val ? 'up-remove' : 'up-keep' }, r, ' ' + label);
    };
    const node = h('div', { class: 'up-skill' },
      h('div', { class: 'up-name' }, h('strong', {}, s.name), ' ', (s.dir.split('/').pop() === s.name && s.group === 'flat') ? null : h('span', { class: 'up-path mono' }, s.dir.replace(/^claude\/skills\//, ''))),
      h('div', { class: 'up-badges' }, badges),
      h('div', { class: 'up-desc', title: 'Click to expand', onclick: e => e.currentTarget.classList.toggle('open') }, s.description || '(no description)'),
      h('div', { class: 'up-times' }, times),
      s.external
        ? h('div', { class: 'up-choice' }, radio('', 'Keep'), radio('remove', 'Remove'))
        : h('div', { class: 'up-times' }, 'Your own skill: not copied from upstream, so it is removed by hand.'));
    s._node = node;
    return node;
  }

  // ── redraw both tabs from the queue ───────────────────────────────────────
  function update() {
    if (!D) return;
    for (const [id, on] of [['up-pane-new', tab === 'new'], ['up-pane-inst', tab === 'installed'], ['up-pane-review', tab === 'review']]) {
      const p = document.getElementById(id);
      if (p) p.hidden = !on;
    }
    if (tab === 'review') buildReview();
    let copy = 0, ign = 0, rem = 0;
    for (const { det, stat, items } of newCards) {
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
      stat.textContent = plural(items.length, 'skill') + (c ? `, ${c} to copy` : '') + (i ? `, ${i} ignored` : '');
      det.hidden = shown === 0;
      if (view.q && shown) det.open = true;
      copy += c; ign += i;
    }
    let mods = 0;
    for (const { det, stat, items } of instCards) {
      let shown = 0, r = 0, m = 0;
      for (const s of items) {
        const cur = choices[rmKey(s)] ? 'remove' : '';
        if (s.external) s['_i_' + cur].checked = true;
        s._node.className = 'up-skill' + (cur ? ' remove' : '');
        if (cur) r++;
        const modified = !!(s.override || s.dirty);
        if (modified) m++;
        const hit = !view.q || (s.name + ' ' + s.dir + ' ' + (s.repo || '') + ' ' + s.description).toLowerCase().includes(view.q);
        const vis = hit && !(view.modified && !modified);
        s._node.hidden = !vis;
        if (vis) shown++;
      }
      stat.textContent = plural(items.length, 'skill') + (m ? `, ${m} with local changes` : '') + (r ? `, ${r} to remove` : '');
      det.hidden = shown === 0;
      if (view.q && shown) det.open = true;
      rem += r; mods += m;
    }
    const total = D.items.length;
    const rv = document.getElementById('up-t-rev');
    if (rv) rv.textContent = `Review (${queued()})`;
    const st = document.getElementById('up-stat');
    if (st) {
      st.textContent = tab === 'review' ? `${queued()} queued · ${copy} to copy · ${ign} to ignore · ${rem} to remove`
        : tab === 'new'
        ? `${total - copy - ign} undecided of ${total} · ${copy} to copy · ${ign} to ignore` + (D.generated ? ` · list from ${day(D.generated)}` : '')
        : INST ? `${INST.length} installed · ${INST.filter(s => s.override || s.dirty).length} with local changes · ${rem} to remove` : '';
    }
    const q = document.getElementById('up-queue');
    if (q) q.textContent = queued() ? `${plural(queued(), 'choice')} queued; nothing changes until you apply them.` : 'No choices queued.';
    const ap = document.getElementById('up-apply');
    if (ap) {
      ap.disabled = !queued();
      ap.textContent = tab === 'review' ? 'Continue to apply' : queued() ? `Review ${plural(queued(), 'choice')}` : 'Review choices';
    }
  }

  // ── tab: review ────────────────────────────────────────────────────────────
  function reviewRows() {
    const byNew = new Map((D ? D.items : []).map(s => [key(s), s]));
    const byDir = new Map((INST || []).map(s => ['rm\t' + s.dir, s]));
    const rows = [];
    for (const [k, v] of Object.entries(choices)) {
      if (k.startsWith('rm\t')) {
        const s = byDir.get(k);
        rows.push({ k, kind: 'remove', s, name: s ? s.name : k.slice(3), path: k.slice(3).replace(/^claude\/skills\//, ''), src: s ? (s.repo || '') : '', desc: s ? s.description : '' });
      } else {
        const s = byNew.get(k);
        if (s) rows.push({ k, kind: v.c, s, name: s.name, path: s.path, src: s.repo, desc: s.desc, dest: v.d });
      }
    }
    return rows.sort((a, b) => (a.src + a.name).localeCompare(b.src + b.name));
  }

  function setChoice(r, val) {
    if (!val) delete choices[r.k];
    else if (r.k.startsWith('rm\t')) choices[r.k] = { c: 'remove' };
    else choices[r.k] = val === 'copy' ? { c: 'copy', d: r.dest || (D.suggest[r.s.repo] || 'flat') } : { c: 'ignore' };
    saveChoices();
    update();
  }

  function reviewRow(r) {
    const inst = r.k.startsWith('rm\t');
    const opt = (v, label) => h('option', { value: v }, label);
    const act = h('select', { 'aria-label': `Choice for ${r.name}`, onchange: e => setChoice(r, e.target.value) },
      inst ? [opt('remove', 'Remove'), opt('', 'Keep (take out of the queue)')]
        : [opt('copy', 'Copy it'), opt('ignore', 'Ignore'), opt('', 'Decide later (take out of the queue)')]);
    act.value = r.kind;
    const controls = [act];
    if (r.kind === 'copy') {
      const dest = h('select', { 'aria-label': `Where to put ${r.name}`, onchange: e => { choices[r.k] = { c: 'copy', d: e.target.value }; saveChoices(); update(); } },
        opt('flat', 'flat (always loaded)'), D.groups.map(g => opt(g, `group: ${g}`)));
      dest.value = r.dest || 'flat';
      controls.push(dest);
    }
    controls.push(h('button', { class: 'plain', onclick: () => setChoice(r, '') }, 'Take out'));
    const warn = [];
    if (r.kind === 'remove' && r.s) {
      if (r.s.override) warn.push(h('span', { class: 'up-badge mod' }, `local changes lost: ${plural(r.s.override.lines, 'line')} in ${plural(r.s.override.files, 'file')}`));
      if (r.s.dirty) warn.push(h('span', { class: 'up-badge dirty' }, 'uncommitted changes lost'));
    }
    return h('div', { class: 'up-skill ' + r.kind },
      h('div', { class: 'up-name' }, h('strong', {}, r.name), ' ', h('span', { class: 'up-path mono' }, r.path), r.src ? h('span', { class: 'up-badge' }, r.src) : null),
      warn.length ? h('div', { class: 'up-badges' }, warn) : null,
      h('div', { class: 'up-desc', title: 'Click to expand', onclick: e => e.currentTarget.classList.toggle('open') }, r.desc || '(no description)'),
      h('div', { class: 'up-choice' }, controls));
  }

  function buildReview() {
    const pane = mount('up-pane-review');
    if (!queued()) {
      pane.append(h('p', { class: 'up-empty' }, 'Nothing is queued. Choose Copy it, Ignore or Remove in the other tabs and every pick shows up here to review and change before you apply.'));
      return;
    }
    const rows = reviewRows().filter(r => !view.q || (r.name + ' ' + r.path + ' ' + r.src + ' ' + r.desc).toLowerCase().includes(view.q));
    pane.append(h('div', { class: 'up-bulk' },
      h('button', { class: 'plain', onclick: askClearAll }, 'Take everything out of the queue'),
      h('span', { class: 'up-note' }, 'Nothing has been applied yet. Change a pick with its menu, or take it out.')));
    if (!rows.length) pane.append(h('p', { class: 'up-empty' }, 'No queued choice matches the search.'));
    for (const [kind, title] of [['copy', 'Copy from GitHub'], ['ignore', 'Ignore'], ['remove', 'Remove installed skills']]) {
      const sec = rows.filter(r => r.kind === kind);
      if (!sec.length) continue;
      pane.append(h('h3', { class: 'up-sec' + (kind === 'remove' ? ' up-warnh' : '') }, `${title} (${sec.length})`));
      sec.forEach(r => pane.append(reviewRow(r)));
    }
  }

  function askClearAll() {
    bar(h('span', {}, `Take all ${plural(queued(), 'choice')} out of the queue? Nothing has been applied, so no file changes.`),
      h('button', { class: 'plain', onclick: () => { choices = {}; saveChoices(); bar(); update(); } }, 'Take them all out'),
      h('button', { class: 'plain', onclick: () => bar() }, 'Cancel'));
  }

  // ── refresh the not-copied list from GitHub ───────────────────────────────
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
  const picked = () => {
    const out = [];
    for (const [k, v] of Object.entries(choices)) {
      if (k.startsWith('rm\t')) { out.push({ choice: 'remove', dir: k.slice(3) }); continue; }
      const [repo, path] = k.split('\t');
      out.push({ repo, path, choice: v.c, dest: v.d || null });
    }
    return out;
  };

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
      r.remove.length ? h('div', {}, h('h3', { class: 'up-warnh' }, `Remove ${plural(r.remove.length, 'installed skill')}`),
        h('p', { class: 'up-note' }, 'The folder is deleted from this repo (committed history keeps it, so git can restore it) and the skill is added to scripts/external-skills-ignore.txt so it is not offered as new again. Nothing is committed for you.'),
        h('ul', {}, r.remove.map(x => h('li', {}, h('span', { class: 'mono' }, x.name), ' (', x.dir.replace(/^claude\/skills\//, ''), ')',
          x.warnings.map(w => h('div', { class: 'up-err' }, 'Warning: ' + w)))))) : null,
      r.ignore.length ? h('div', {}, h('h3', {}, `Ignore ${plural(r.ignore.length, 'skill')}`),
        h('p', { class: 'up-note' }, 'One line per skill is added to scripts/external-skills-ignore.txt; the update tool then stops listing them. No network.'),
        h('details', {}, h('summary', {}, 'Show the skills'),
          h('ul', {}, r.ignore.map(i => h('li', {}, h('span', { class: 'mono' }, i.repo + ' ' + i.path)))))) : null,
      r.vendor.length ? h('div', {}, h('h3', {}, `Copy ${plural(r.vendor.length, 'skill')} from GitHub`),
        h('p', { class: 'up-note' }, `About ${r.requests} GitHub requests from your IP, paced. Each skill becomes an external skill (source.json, pristine .upstream copy) kept current by the update tool.`),
        h('ul', {}, r.vendor.map(v => h('li', {}, h('span', { class: 'mono' }, v.name), ' → ', v.target)))) : null,
      r.problems.length ? h('div', {}, h('h3', { class: 'up-err' }, `${r.problems.length} cannot be applied`),
        h('ul', {}, r.problems.map(p => h('li', {}, h('span', { class: 'mono' }, p.path), ': ', p.error)))) : null,
      h('div', { class: 'up-actions' },
        h('button', { class: 'plain up-apply', disabled: !(r.ignore.length || r.vendor.length || r.remove.length), onclick: () => runApply(m) }, 'Apply'),
        h('button', { class: 'plain', onclick: () => m.remove() }, 'Back')));
  }

  async function runApply(m) {
    m.replaceChildren(h('div', { class: 'up-box' }, h('p', {}, 'Applying... copying skills can take a few minutes.')));
    const r = await L.api('upstream-apply', { choices: picked() });
    const res = r.results || [];
    for (const x of res) if (x.ok) delete choices[x.action === 'remove' ? 'rm\t' + x.dir : x.repo + '\t' + x.path];
    saveChoices();
    const bad = res.filter(x => !x.ok);
    m.replaceChildren(h('div', { class: 'up-box' },
      h('h2', {}, r.ok ? 'Done' : 'Finished with problems'),
      h('p', {}, `${res.filter(x => x.ok).length} applied, ${bad.length} failed.`),
      bad.length ? h('ul', {}, bad.map(x => h('li', {}, h('span', { class: 'mono' }, x.dir || x.path), ': ', x.error))) : null,
      r.note ? h('p', { class: 'up-note' }, r.note) : null,
      h('div', { class: 'up-actions' }, h('button', { class: 'plain', onclick: () => m.remove() }, 'OK'))));
    INST = null;
    await loadData();
    if (tab !== 'new') await loadInstalled();
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
