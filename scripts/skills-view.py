#!/usr/bin/env python3
"""
Launcher-style board for the Claude skills directory.

Renders every skill the way tools/launcher does for OJ: sections, cards, and a
bottom line naming the action. The split is the same one that tool makes —
trial-skill.sh holds all the truth, this only draws `trial-skill.sh list --json`
and prints the command that changes something. Nothing here mutates state, so
the view can never disagree with the directory it describes.

Why a view at all: a trial skill's default fate is to live forever, because
nothing deletes it but the user happening to look. Rather than have a timer
delete things on its own, this makes looking cheap — and puts the cost of
keeping a skill on screen, in tokens, next to the decision to keep it.

Trials are drawn as cards because each one is a pending decision. Managed skills
are drawn as rows because they are not.

Usage:
    ./scripts/skills-view.py            # the board
    ./scripts/skills-view.py --stale    # only what has gone stale
    ./scripts/skills-view.py --all      # managed skills as cards too
    ./scripts/skills-view.py --html     # write the board as a page, print its path

The HTML board is the same picture with room for what a card cannot hold: the
full description, install and last-used dates, source commit, a copy button on
every command, and a budget bar of frontmatter tokens by source. Selecting
cards composes one trial-skill.sh command for the set; search and chips filter;
a bar segment jumps to its section. It is written for the case where the board
is being read inside a chat pane, whose width the script cannot know.
"""

import argparse
import html
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

# ANSI, matching jira-board.py: 16 colours, no truecolor, so the board keeps the
# terminal's own theme instead of imposing one.
RST = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
BLUE = "\033[34m"
GREEN = "\033[32m"
MAGENTA = "\033[35m"
WHITE = "\033[37m"

# One colour per group, cycling — the same reasoning as the launcher's four
# section hues: a colour that identifies a source repo at a glance, and means
# nothing beyond that.
GROUP_PALETTE = [CYAN, GREEN, MAGENTA, BLUE]

CARD_W = 24                     # inner width; 4 cards fit a standard 110-col term
CARD_GAP = "  "
# Without a terminal the output is being captured and pasted into a chat pane
# whose width is unknown; two cards (54 cols) fit any pane without shearing.
NO_TTY_WIDTH = 60


def term_width():
    try:
        return os.get_terminal_size().columns
    except OSError:
        return NO_TTY_WIDTH


def tokens(chars):
    """Frontmatter cost in tokens. Deliberately the crude chars/4 — the point is
    the order of magnitude, and a real tokenizer would be a dependency."""
    return round(chars / 4)


def fmt_tokens(chars):
    t = tokens(chars)
    return f"{t / 1000:.1f}k" if t >= 1000 else str(t)


def wrap_name(name, width):
    """Wrap a skill name, breaking at hyphens as well as spaces — skill names are
    hyphenated and would otherwise overflow every card."""
    words, cur = [], ""
    for part in name.replace("-", "-\x00").split("\x00"):
        if len(cur) + len(part) <= width:
            cur += part
        else:
            if cur:
                words.append(cur)
            cur = part
    if cur:
        words.append(cur)
    return words or [name[:width]]


def load_state(trial_sh):
    """Every field this draws comes from trial-skill.sh, so the two can never
    drift. Errors are returned rather than raised so the caller reports them the
    same way for a missing script and a broken one."""
    try:
        out = subprocess.run(
            [str(trial_sh), "list", "--json"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"could not run {trial_sh}: {exc}"
    if out.returncode != 0:
        return None, (out.stderr.strip() or f"trial-skill.sh exited {out.returncode}")
    try:
        return json.loads(out.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"trial-skill.sh returned unparseable JSON: {exc}"


def flag_of(skill):
    if skill.get("pinned"):
        return "PINNED"
    if skill.get("stale"):
        return "STALE"
    if skill["kind"] == "untracked":
        return "UNTRACKED"
    return ""


def card_lines(skill, title_rows, show_flag):
    """One card as a list of plain strings, borders included. Colour is applied
    by the caller so width maths never has to see an escape sequence.

    title_rows and show_flag come from the section rather than the card, so every
    card in a section is the same height without any of them reserving space the
    section never uses."""
    inner = CARD_W
    title = wrap_name(skill["name"], inner - 2)[:title_rows]

    idle = skill.get("idle_days")
    age = "—" if idle is None or idle < 0 else f"idle {idle}d"
    cost = fmt_tokens(skill.get("desc_chars", 0)) + "t"

    body = [f"┌{'─' * inner}┐"]
    for line in title:
        body.append(f"│ {line:<{inner - 2}} │")
    for _ in range(title_rows - len(title)):
        body.append(f"│{' ' * inner}│")
    if show_flag:
        body.append(f"│ {flag_of(skill):<{inner - 2}} │")
    body.append(f"│ {age:<{inner - 2 - len(cost) - 1}} {cost} │")
    body.append(f"└{'─' * inner}┘")
    return body


def print_cards(skills, colors):
    """Cards in rows that fit the terminal. Height is decided once for the whole
    section, so a row prints as a fixed block."""
    title_rows = max(len(wrap_name(s["name"], CARD_W - 2)) for s in skills)
    title_rows = min(title_rows, 3)
    show_flag = any(flag_of(s) for s in skills)

    per_row = max(1, (term_width() + len(CARD_GAP)) // (CARD_W + 2 + len(CARD_GAP)))
    for start in range(0, len(skills), per_row):
        chunk = skills[start:start + per_row]
        built = [(card_lines(s, title_rows, show_flag), colors(s)) for s in chunk]
        height = max(len(b) for b, _ in built)
        for row in range(height):
            out = []
            for body, color in built:
                line = body[row] if row < len(body) else " " * (CARD_W + 2)
                out.append(f"{color}{line}{RST}")
            print("  " + CARD_GAP.join(out))
        print()


def print_rows(skills):
    """Managed skills as dotted rows. They are not decisions, so they get the
    least ink that still shows what they cost."""
    width = min(term_width() - 4, 78)
    for s in skills:
        cost = fmt_tokens(s.get("desc_chars", 0))
        tag = "ext" if s.get("external") else "own"
        dots = "." * max(1, width - len(s["name"]) - len(cost) - len(tag) - 4)
        print(f"  {s['name']} {DIM}{dots}{RST} {cost:>5}  {DIM}{tag}{RST}")
    print()


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def section(title, detail, color=WHITE):
    print(f"  {color}{BOLD}{title}{RST}  {DIM}{detail}{RST}")


def group_trials(trials):
    """Trials sectioned by source repo — one decision per repo, since eleven
    skills pulled from one place are rarely eleven separate judgements. A repo
    with a single trial gets no section of its own; that would be ceremony
    around a set of one. Returns (groups keyed by repo or None, set of repos)."""
    counts = {}
    for s in trials:
        counts[s.get("repo")] = counts.get(s.get("repo"), 0) + 1
    sets = {r for r, n in counts.items() if r and n > 1}
    groups = {}
    for s in trials:
        repo = s.get("repo")
        groups.setdefault(repo if repo in sets else None, []).append(s)
    return groups, sets


HTML_CSS = """
:root{color-scheme:light;
 --bg:#f3f4f6;--panel:#fafbfc;--card:#ffffff;--ink:#16181c;--ink-2:#5f6570;--ink-3:#8b919b;--line:#d8dbe0;--line-2:#e9ebee;
 --code:#eceef1;--focus:#2a78d6;
 --g0:#2a78d6;--g1:#eb6834;--g2:#1baf7a;--g3:#eda100;--managed:#4a3aa7;
 --stale:#c8321f;--pin:#8b919b;--hatch:rgba(22,24,28,.55)}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;
 --bg:#15171a;--panel:#1b1e22;--card:#1f2226;--ink:#e6e8eb;--ink-2:#9aa1ab;--ink-3:#6f7680;--line:#2c3037;--line-2:#24282e;
 --code:#272b31;--focus:#3987e5;
 --g0:#3987e5;--g1:#d95926;--g2:#199e70;--g3:#c98500;--managed:#9085e9;
 --stale:#ff7a6b;--pin:#6f7680;--hatch:rgba(230,232,235,.55)}}
:root[data-theme=dark]{color-scheme:dark;
 --bg:#15171a;--panel:#1b1e22;--card:#1f2226;--ink:#e6e8eb;--ink-2:#9aa1ab;--ink-3:#6f7680;--line:#2c3037;--line-2:#24282e;
 --code:#272b31;--focus:#3987e5;
 --g0:#3987e5;--g1:#d95926;--g2:#199e70;--g3:#c98500;--managed:#9085e9;
 --stale:#ff7a6b;--pin:#6f7680;--hatch:rgba(230,232,235,.55)}
*{box-sizing:border-box}
[hidden]{display:none!important}
html{scroll-padding-top:200px}
body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums;padding:0 0 120px}
button{font:inherit;color:inherit;background:none;border:1px solid var(--line);border-radius:4px;padding:2px 9px;cursor:pointer;line-height:1.4}
button:hover{border-color:var(--ink-3)}
button[aria-pressed=true]{color:var(--ink);border-color:var(--ink);background:var(--panel)}
button:focus-visible,input:focus-visible,article:focus-visible,[tabindex]:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
input[type=search]{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:4px;padding:4px 10px;min-width:280px;flex:1}
input[type=search]::placeholder{color:var(--ink-3)}
.top{position:sticky;top:0;z-index:5;background:var(--panel);border-bottom:1px solid var(--line);padding:16px 32px 12px;display:grid;gap:12px}
.brand{display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap}
h1{font-size:16px;margin:0;letter-spacing:.02em}
.brand .sub{color:var(--ink-2);margin:0}
.budget{display:grid;gap:6px}
.budget-head{display:flex;justify-content:space-between;gap:16px;color:var(--ink-2);flex-wrap:wrap}
.budget-head b{color:var(--ink);font-weight:600}
.budget-head .freed{color:var(--stale)}
svg.bar{width:100%;height:26px;display:block}
svg.bar rect.seg{cursor:pointer}
svg.bar rect.seg:hover,svg.bar rect.seg.hot{stroke:var(--ink);stroke-width:1.5}
svg.bar text{font:11px ui-monospace,Menlo,monospace;fill:#fff;pointer-events:none}
.legend{display:flex;gap:4px 18px;flex-wrap:wrap;color:var(--ink-2)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.legend i{width:10px;height:10px;border-radius:2px;background:var(--c);display:inline-block}
.legend b{color:var(--ink);font-weight:600}
.tools{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.tools .grow{flex:1}
.hint{margin:0;color:var(--ink-3);font-size:12px}
kbd{font:inherit;color:var(--ink-3);border:1px solid var(--line);border-radius:3px;padding:0 5px}
main{padding:22px 32px 0;display:grid;gap:30px}
section>h2{font-size:13px;margin:0 0 6px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
section>h2 .dot{width:10px;height:10px;border-radius:2px;background:var(--c);display:inline-block;align-self:center}
section>h2 .detail{color:var(--ink-2);font-weight:normal}
section>h2 .shown{color:var(--ink-3);font-weight:normal}
section>h2 .spacer{flex:1}
section>h2 button{font-size:12px}
.controls{color:var(--ink-3);margin:0 0 10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-size:12px}
.controls button{font-size:12px;padding:1px 8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px;align-items:start}
article.card{--c:var(--line);border:1px solid var(--line);border-left:4px solid var(--c);background:var(--card);border-radius:4px;padding:9px 12px 10px;display:flex;flex-direction:column;gap:6px;cursor:pointer;position:relative}
article.card:hover{border-color:var(--ink-3);border-left-color:var(--c)}
article.card.stale{--c:var(--stale)}
article.card.pinned{--c:var(--pin);opacity:.7}
article.card[aria-selected=true]{background:color-mix(in srgb,var(--c) 10%,var(--card));border-color:var(--c)}
article.card .head{display:flex;gap:8px;align-items:baseline}
article.card input[type=checkbox]{margin:0;position:relative;top:2px;accent-color:var(--focus);flex:none}
article.card .name{font-weight:600;flex:1;word-break:break-word}
article.card .cost{color:var(--ink-2);white-space:nowrap}
article.card .cost b{color:var(--ink);font-weight:600}
article.card .flag{font-size:10px;letter-spacing:.08em;color:var(--c);text-transform:uppercase}
article.card .desc{font:13px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);opacity:.88;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
article.card.open .desc,body.expanded article.card .desc{display:block;-webkit-line-clamp:unset}
article.card .more{align-self:flex-start;border:0;padding:0;color:var(--ink-3);font-size:12px}
article.card .more:hover{color:var(--ink)}
body.expanded article.card .more{display:none}
article.card .meta{color:var(--ink-2);font-size:12px;display:flex;flex-wrap:wrap;gap:2px 14px}
article.card .meta b{color:var(--ink);font-weight:normal}
.actions{margin:10px 0 0;display:flex;flex-direction:column;gap:6px}
.cmd{display:flex;align-items:center;gap:10px;color:var(--ink-2);flex-wrap:wrap}
.cmd code{background:var(--code);padding:2px 8px;border-radius:4px;color:var(--ink);user-select:all}
.cmd button{font-size:12px;padding:1px 8px}
table{border-collapse:collapse;width:100%}
td,th{text-align:left;padding:5px 12px 5px 0;border-bottom:1px solid var(--line-2);vertical-align:top}
th{color:var(--ink-2);font-weight:normal;cursor:pointer;user-select:none;white-space:nowrap}
th[data-dir]{color:var(--ink)}
th[data-dir]::after{content:" ▾"}th[data-dir=asc]::after{content:" ▴"}
td.num{text-align:right;white-space:nowrap}
td.desc{font:13px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;opacity:.88;max-width:640px}
td.tag{color:var(--ink-2)}
tr[hidden]{display:none}
.foot{padding:24px 32px 0;color:var(--ink-2)}
.foot b{color:var(--ink)}
.foot .stale{color:var(--stale)}
#tray{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);z-index:6;background:var(--panel);border:1px solid var(--ink-3);border-radius:6px;box-shadow:0 8px 28px rgba(0,0,0,.25);padding:12px 16px;display:grid;gap:8px;min-width:min(760px,calc(100vw - 40px));max-width:calc(100vw - 40px)}
#tray .row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
#tray .count b{color:var(--ink);font-weight:600}
#tray .count{color:var(--ink-2);flex:1}
#tray code{background:var(--code);padding:4px 10px;border-radius:4px;flex:1;overflow-x:auto;white-space:nowrap}
#tray .verbs{display:flex;gap:6px}
#tip{position:fixed;z-index:9;pointer-events:none;background:var(--ink);color:var(--bg);padding:8px 10px;border-radius:4px;font-size:12px;line-height:1.5;max-width:300px;box-shadow:0 4px 14px rgba(0,0,0,.25)}
#tip b{font-weight:600;font-size:13px}
#tip .k{opacity:.7}
.empty{color:var(--ink-3);padding:8px 0}
@media(prefers-reduced-motion:no-preference){article.card,button{transition:border-color .12s,background-color .12s}}
"""

HTML_JS = r"""
(()=>{
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const fmt=t=>t>=1000?(t/1000).toFixed(1)+'k':String(t);
const copy=(text,btn)=>{
  const done=()=>{const t=btn.textContent;btn.textContent='copied';setTimeout(()=>btn.textContent=t,900)};
  if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(text).then(done);return}
  const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity='0';
  document.body.appendChild(ta);ta.select();try{document.execCommand('copy');done()}finally{ta.remove()}
};
$$('.cmd button[data-copy]').forEach(b=>b.addEventListener('click',e=>{e.stopPropagation();copy(b.dataset.copy,b)}));

// ── theme ──────────────────────────────────────────────────────────────────
const root=document.documentElement, themeBtn=$('#theme');
const cycle=['system','light','dark'];
let theme='system';try{theme=localStorage.getItem('theme')||'system'}catch(e){}
const applyTheme=()=>{if(theme==='system')root.removeAttribute('data-theme');else root.dataset.theme=theme;
  themeBtn.textContent='theme: '+theme;try{localStorage.setItem('theme',theme)}catch(e){}};
themeBtn.addEventListener('click',()=>{theme=cycle[(cycle.indexOf(theme)+1)%3];applyTheme()});
applyTheme();

// ── selection ──────────────────────────────────────────────────────────────
const cards=$$('article.card'), tray=$('#tray'), trayCmd=$('#tray-cmd'), trayCount=$('#tray-count');
const freed=$('#freed'); let verb='rm';
const selected=()=>cards.filter(c=>c.getAttribute('aria-selected')==='true');
const setSel=(card,on)=>{card.setAttribute('aria-selected',on?'true':'false');$('input',card).checked=on};
const render=()=>{
  const sel=selected(), names=sel.map(c=>c.dataset.name), tok=sel.reduce((a,c)=>a+ +c.dataset.tokens,0);
  tray.hidden=sel.length===0;
  if(sel.length){
    trayCount.innerHTML=`<b>${sel.length}</b> selected · <b>${fmt(tok)}</b> tokens`;
    trayCmd.textContent='trial-skill.sh '+verb+' '+names.join(' ');
  }
  freed.hidden=tok===0; if(tok)freed.textContent='− '+fmt(tok)+' if removed';
  // hatched overlay per segment: selected tokens eat the segment from its right edge
  $$('svg.bar rect.seg').forEach(seg=>{
    const g=seg.dataset.group, w=+seg.getAttribute('width'), x=+seg.getAttribute('x'), total=+seg.dataset.tokens;
    const t=sel.filter(c=>c.dataset.group===g).reduce((a,c)=>a+ +c.dataset.tokens,0);
    const ov=$(`rect.sel[data-group="${CSS.escape(g)}"]`);
    if(!ov)return; const sw=total?w*t/total:0;
    ov.setAttribute('x',x+w-sw);ov.setAttribute('width',sw);ov.hidden=sw===0;
  });
  $$('section[data-group]').forEach(sec=>{
    const all=$$('article.card',sec), on=all.filter(c=>c.getAttribute('aria-selected')==='true').length;
    const b=$('button.sel-all',sec); if(b)b.textContent=on===all.length?'clear':'select all';
  });
};
cards.forEach(card=>{
  card.addEventListener('click',e=>{
    if(e.target.closest('button,a'))return;
    setSel(card,card.getAttribute('aria-selected')!=='true');render();
  });
  card.addEventListener('keydown',e=>{
    if(e.target!==card)return;
    if(e.key===' '||e.key==='Enter'){e.preventDefault();setSel(card,card.getAttribute('aria-selected')!=='true');render()}
    if(e.key==='ArrowRight'||e.key==='ArrowDown'){e.preventDefault();const v=visible();v[(v.indexOf(card)+1)%v.length]?.focus()}
    if(e.key==='ArrowLeft'||e.key==='ArrowUp'){e.preventDefault();const v=visible();v[(v.indexOf(card)-1+v.length)%v.length]?.focus()}
  });
  $('input',card).addEventListener('click',e=>{e.stopPropagation();setSel(card,e.target.checked);render()});
  $('button.more',card)?.addEventListener('click',e=>{e.stopPropagation();card.classList.toggle('open');
    e.target.textContent=card.classList.contains('open')?'less':'more'});
});
$$('button.sel-all').forEach(b=>b.addEventListener('click',()=>{
  const sec=b.closest('section'), all=$$('article.card:not([hidden])',sec);
  const on=all.every(c=>c.getAttribute('aria-selected')==='true');
  all.forEach(c=>setSel(c,!on));render();
}));
$$('#tray .verbs button').forEach(b=>b.addEventListener('click',()=>{
  verb=b.dataset.verb;$$('#tray .verbs button').forEach(x=>x.setAttribute('aria-pressed',x===b));render();
}));
$('#tray-copy').addEventListener('click',e=>copy(trayCmd.textContent,e.target));
const clearSel=()=>{cards.forEach(c=>setSel(c,false));render()};
$('#tray-clear').addEventListener('click',clearSel);

// ── filter & search ────────────────────────────────────────────────────────
const q=$('#q'); let chip='all';
const visible=()=>cards.filter(c=>!c.hidden);
const matches=(el,needle)=>!needle||(el.dataset.name+' '+(el.dataset.desc||'')).toLowerCase().includes(needle);
const passChip=el=>{
  switch(chip){case 'stale':return el.dataset.stale==='1';case 'pinned':return el.dataset.pinned==='1';
    case 'trial':return el.dataset.kind!=='managed';case 'managed':return el.dataset.kind==='managed';
    case 'selected':return el.getAttribute('aria-selected')==='true';default:return true}
};
const filter=()=>{
  const needle=q.value.trim().toLowerCase();
  cards.forEach(c=>{c.hidden=!(matches(c,needle)&&passChip(c))});
  $$('tbody tr[data-name]').forEach(r=>{r.hidden=!(matches(r,needle)&&passChip(r))});
  $$('section').forEach(sec=>{
    const all=$$('article.card, tbody tr[data-name]',sec), shown=all.filter(x=>!x.hidden);
    sec.hidden=shown.length===0; const s=$('.shown',sec); if(s)s.textContent=shown.length===all.length?'':`${shown.length} of ${all.length} shown`;
  });
  $('#none').hidden=$$('section:not([hidden])').length>0;
};
q.addEventListener('input',filter);
$$('.chips button').forEach(b=>b.addEventListener('click',()=>{
  chip=b.dataset.f;$$('.chips button').forEach(x=>x.setAttribute('aria-pressed',x===b));filter();
}));
$('#expand').addEventListener('click',e=>{document.body.classList.toggle('expanded');
  e.target.setAttribute('aria-pressed',document.body.classList.contains('expanded'))});
document.addEventListener('keydown',e=>{
  if(e.key==='/'&&document.activeElement!==q&&!e.metaKey&&!e.ctrlKey){e.preventDefault();q.focus();q.select()}
  else if(e.key==='Escape'){
    if(document.activeElement===q&&q.value){q.value='';filter()}
    else if(document.activeElement===q){q.blur()}
    else clearSel();
  }
});

// ── section sort ───────────────────────────────────────────────────────────
$$('.controls button[data-sort]').forEach(b=>b.addEventListener('click',()=>{
  const key=b.dataset.sort, grid=$('.grid',b.closest('section'));
  b.parentElement.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',x===b));
  [...grid.children].sort((a,c)=>{const x=a.dataset[key],y=c.dataset[key];
    return key==='name'?x.localeCompare(y):(+y)-(+x)}).forEach(el=>grid.appendChild(el));
}));
$$('th[data-key]').forEach(th=>th.addEventListener('click',()=>{
  const tb=th.closest('table').tBodies[0], key=th.dataset.key, dir=th.dataset.dir==='desc'?'asc':'desc';
  th.parentElement.querySelectorAll('th').forEach(x=>x.removeAttribute('data-dir'));th.dataset.dir=dir;
  [...tb.rows].sort((a,b)=>{const x=a.dataset[key],y=b.dataset[key];
    const r=key==='tokens'?(+x)-(+y):x.localeCompare(y);return dir==='asc'?r:-r}).forEach(r=>tb.appendChild(r));
}));

// ── budget chart hover ─────────────────────────────────────────────────────
const tip=$('#tip');
$$('svg.bar rect.seg').forEach(seg=>{
  const show=e=>{
    const g=seg.dataset.group, sel=selected().filter(c=>c.dataset.group===g), st=sel.reduce((a,c)=>a+ +c.dataset.tokens,0);
    tip.innerHTML='';
    const b=document.createElement('b');b.textContent=fmt(+seg.dataset.tokens)+' tokens';
    const l1=document.createElement('div');l1.textContent=seg.dataset.label;
    const l2=document.createElement('div');l2.className='k';l2.textContent=`${seg.dataset.share}% of frontmatter · ${seg.dataset.count} skills`;
    tip.append(b,l1,l2);
    if(st){const l3=document.createElement('div');l3.className='k';l3.textContent=`${sel.length} selected · ${fmt(st)} tokens`;tip.append(l3)}
    tip.hidden=false; move(e);
  };
  const move=e=>{const x=Math.min(e.clientX+14,innerWidth-320), y=e.clientY+16;tip.style.left=x+'px';tip.style.top=y+'px'};
  seg.addEventListener('pointerenter',show);seg.addEventListener('pointermove',move);
  seg.addEventListener('pointerleave',()=>tip.hidden=true);
  seg.addEventListener('click',()=>{const sec=$(`section[data-group="${CSS.escape(seg.dataset.group)}"]`);
    if(sec){sec.scrollIntoView({behavior:'smooth',block:'start'})}});
  seg.addEventListener('focus',e=>show({clientX:seg.getBoundingClientRect().left,clientY:seg.getBoundingClientRect().bottom}));
  seg.addEventListener('blur',()=>tip.hidden=true);
});
$$('.legend span[data-group]').forEach(l=>{
  const seg=$(`svg.bar rect.seg[data-group="${CSS.escape(l.dataset.group)}"]`); if(!seg)return;
  l.addEventListener('pointerenter',()=>seg.classList.add('hot'));l.addEventListener('pointerleave',()=>seg.classList.remove('hot'));
  l.addEventListener('click',()=>seg.dispatchEvent(new Event('click')));
});
render();filter();
})();
"""

# Series slots: three named repos get their own hue; everything else that is a
# trial folds into a fourth "other trials" slot; managed gets the fifth. Five is
# what the palette validates at, and a sixth hue would not be told apart.
MAX_REPO_SLOTS = 3


def group_key(s, sets, slot_repos):
    """Which chart segment / colour a skill belongs to."""
    if s["kind"] == "managed":
        return "managed"
    repo = s.get("repo")
    if repo in sets and repo in slot_repos:
        return repo
    return "other"


def html_card(s, gkey, cvar, in_group=False):
    """in_group: the section title already names the repo, so the card shows
    only the commit."""
    e = html.escape
    cls = "card" + (" stale" if s.get("stale") else "") + (" pinned" if s.get("pinned") else "")
    idle = s.get("idle_days")
    idle_txt = "—" if idle is None or idle < 0 else f"idle {idle}d"
    flag = flag_of(s)
    meta = []
    sha = (s.get("commit") or "")[:7]
    if s.get("repo") and not in_group:
        meta.append(f"<span>{e(s['repo'])}{(' @ ' + sha) if sha else ''}</span>")
    elif sha:
        meta.append(f"<span>@ {sha}</span>")
    if s.get("installed"):
        meta.append(f"<span>installed <b>{e(s['installed'])}</b></span>")
    if s.get("last_used"):
        meta.append(f"<span>last used <b>{e(s['last_used'])}</b></span>")
    if s.get("files"):
        meta.append(f"<span>{plural(s['files'], 'file')}</span>")
    style = f' style="--c:var({cvar})"' if not (s.get("stale") or s.get("pinned")) else ""
    desc = s.get("description") or ""
    tok = tokens(s.get("desc_chars", 0))
    selectable = s["kind"] == "trial"
    return (
        f'<article class="{cls}"{style} tabindex="0" aria-selected="false" '
        f'data-name="{e(s["name"])}" data-desc="{e(desc)}" data-group="{e(gkey)}" data-kind="{s["kind"]}" '
        f'data-stale="{1 if s.get("stale") else 0}" data-pinned="{1 if s.get("pinned") else 0}" '
        f'data-idle="{idle if idle is not None else -1}" data-cost="{tok}" data-tokens="{tok}">'
        f'<div class="head"><input type="checkbox" aria-label="select {e(s["name"])}"{"" if selectable else " disabled"}>'
        f'<span class="name">{e(s["name"])}</span>'
        f'<span class="cost">{idle_txt} · <b>{fmt_tokens(s.get("desc_chars", 0))}</b>t</span></div>'
        + (f'<div class="flag">{flag}</div>' if flag else "")
        + f'<div class="desc">{e(desc)}</div>'
        + ('<button type="button" class="more">more</button>' if len(desc) > 180 else "")
        + (f'<div class="meta">{"".join(meta)}</div>' if meta else "")
        + "</article>"
    )


def html_cmd(cmd, note):
    e = html.escape
    return (f'<div class="cmd"><code>{e(cmd)}</code>'
            f'<button type="button" data-copy="{e(cmd)}">copy</button>'
            f'<span>{e(note)}</span></div>')


def html_budget(segments, total_tokens):
    """One stacked bar: frontmatter tokens by group. Direct labels where they
    fit; the tooltip and legend carry the rest. A hatched overlay per segment is
    driven by selection on the page."""
    e = html.escape
    W, H, GAP = 1000, 26, 2
    parts = ['<svg class="bar" viewBox="0 0 1000 26" preserveAspectRatio="none" role="img" '
             'aria-label="frontmatter tokens by group">'
             '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
             '<line x1="0" y1="0" x2="0" y2="6" stroke="var(--hatch)" stroke-width="3"/></pattern></defs>']
    x = 0.0
    n = len(segments)
    for i, (key, label, tok, count, cvar) in enumerate(segments):
        w = (W - GAP * (n - 1)) * tok / total_tokens if total_tokens else 0
        share = round(tok / total_tokens * 100) if total_tokens else 0
        parts.append(f'<rect class="seg" tabindex="0" x="{x:.1f}" y="0" width="{w:.1f}" height="{H}" rx="2" '
                     f'fill="var({cvar})" data-group="{e(key)}" data-label="{e(label)}" '
                     f'data-tokens="{tok}" data-count="{count}" data-share="{share}"/>')
        parts.append(f'<rect class="sel" x="{x:.1f}" y="0" width="0" height="{H}" rx="2" '
                     f'fill="url(#hatch)" data-group="{e(key)}" hidden/>')
        if w > 70:
            parts.append(f'<text x="{x + 8:.1f}" y="17">{fmt_tokens(tok * 4)}</text>')
        x += w + GAP
    parts.append("</svg>")
    legend = "".join(
        f'<span data-group="{e(key)}" style="--c:var({cvar})"><i></i>{e(label)} <b>{fmt_tokens(tok * 4)}</b></span>'
        for key, label, tok, count, cvar in segments)
    return "".join(parts) + f'<div class="legend">{legend}</div>'


def render_html(state, stale_only=False):
    e = html.escape
    skills = state["skills"]
    stale_days = state["stale_days"]
    trials = [s for s in skills if s["kind"] in ("trial", "untracked")]
    managed = [s for s in skills if s["kind"] == "managed"]
    stale = [s for s in trials if s.get("stale")]
    total_chars = sum(s.get("desc_chars", 0) for s in skills)
    trial_chars = sum(s.get("desc_chars", 0) for s in trials)
    total_tok = tokens(total_chars)

    groups, sets = group_trials(trials)
    # Biggest repos take the named slots, so the hues go where the tokens are.
    ranked = sorted((k for k in groups if k),
                    key=lambda k: -sum(m.get("desc_chars", 0) for m in groups[k]))
    slot_repos = ranked[:MAX_REPO_SLOTS]
    cvar_of = {r: f"--g{i}" for i, r in enumerate(slot_repos)}
    cvar_of["other"] = f"--g{MAX_REPO_SLOTS}"
    cvar_of["managed"] = "--managed"

    segments = []
    for r in slot_repos:
        tok = tokens(sum(m.get("desc_chars", 0) for m in groups[r]))
        segments.append((r, r, tok, len(groups[r]), cvar_of[r]))
    other = [m for k, ms in groups.items() if k not in slot_repos for m in ms]
    if other:
        label = "other trials" if len(slot_repos) < len(ranked) else "sole trials"
        segments.append(("other", label, tokens(sum(m.get("desc_chars", 0) for m in other)), len(other), cvar_of["other"]))
    if managed:
        segments.append(("managed", "managed", tokens(sum(m.get("desc_chars", 0) for m in managed)), len(managed), cvar_of["managed"]))

    if stale_only:
        trials, managed = stale, []
        groups, sets = group_trials(trials)

    head = [
        "<title>Skills Board</title>",
        f"<style>{HTML_CSS}</style>",
        '<header class="top">',
        '<div class="brand"><h1>Skills board</h1>'
        f'<p class="sub">{len(skills)} installed · {e(state.get("today") or date.today().isoformat())}'
        f' · {e(state.get("config_dir") or "")}/skills</p></div>',
        '<div class="budget"><div class="budget-head">'
        f'<span>~<b>{fmt_tokens(total_chars)}</b> tokens of skill frontmatter in every session'
        f' · trials are <b>{(trial_chars / total_chars * 100) if total_chars else 0:.0f}%</b></span>'
        '<span id="freed" class="freed" hidden></span></div>',
        html_budget(segments, total_tok),
        "</div>",
        '<div class="tools">'
        '<input type="search" id="q" placeholder="filter by name or description" aria-label="filter skills">'
        '<div class="chips">'
        '<button type="button" data-f="all" aria-pressed="true">all</button>'
        f'<button type="button" data-f="stale" aria-pressed="false">stale ({len(stale)})</button>'
        f'<button type="button" data-f="pinned" aria-pressed="false">pinned ({sum(1 for s in skills if s.get("pinned"))})</button>'
        f'<button type="button" data-f="trial" aria-pressed="false">trials ({len([s for s in skills if s["kind"] != "managed"])})</button>'
        f'<button type="button" data-f="managed" aria-pressed="false">managed ({len([s for s in skills if s["kind"] == "managed"])})</button>'
        '<button type="button" data-f="selected" aria-pressed="false">selected</button>'
        '</div><span class="grow"></span>'
        '<button type="button" id="expand" aria-pressed="false">full descriptions</button>'
        '<button type="button" id="theme">theme: system</button>'
        '<span><kbd>/</kbd> search · <kbd>esc</kbd> clear · click a card to select</span>'
        "</div></header>",
        "<main>",
    ]
    parts = head

    controls = ('<div class="controls"><span>sort</span>'
                '<button type="button" data-sort="idle" aria-pressed="false">idle</button>'
                '<button type="button" data-sort="cost" aria-pressed="false">cost</button>'
                '<button type="button" data-sort="name" aria-pressed="true">name</button></div>')

    for g in sorted(groups, key=lambda k: (k is None, k or "")):
        members = sorted(groups[g], key=lambda s: s["name"])
        cost = sum(m.get("desc_chars", 0) for m in members)
        detail = f"{plural(len(members), 'skill')} · ~{fmt_tokens(cost)} tokens"
        gkey = g if g in slot_repos else "other"
        cvar = cvar_of[gkey]
        title = e(g) if g else "sole install from their repo"
        parts.append(f'<section data-group="{e(gkey)}"><h2><span class="dot" style="--c:var({cvar})"></span>'
                     f'trials · {title} <span class="detail">{detail}</span><span class="shown"></span>'
                     '<span class="spacer"></span><button type="button" class="sel-all">select all</button></h2>'
                     f'{controls}<div class="grid">')
        parts.extend(html_card(m, gkey, cvar, in_group=bool(g)) for m in members)
        parts.append("</div>")
        if g:
            parts.append('<div class="actions">'
                         + html_cmd(f"trial-skill.sh rm --repo {g}", f"removes all {len(members)}")
                         + html_cmd(f"trial-skill.sh promote --repo {g}", "keeps them permanently")
                         + "</div>")
        parts.append("</section>")

    if managed:
        cost = sum(s.get("desc_chars", 0) for s in managed)
        parts.append('<section data-group="managed"><h2><span class="dot" style="--c:var(--managed)"></span>managed '
                     f'<span class="detail">{plural(len(managed), "skill")} · ~{fmt_tokens(cost)} tokens · '
                     'symlinks into agents-shared</span><span class="shown"></span></h2>'
                     '<div style="overflow-x:auto"><table><thead><tr><th data-key="name" data-dir="asc">skill</th>'
                     '<th data-key="tokens">tokens</th><th data-key="tag">src</th><th>description</th></tr></thead><tbody>')
        for s in sorted(managed, key=lambda s: s["name"]):
            tag = "ext" if s.get("external") else "own"
            desc = s.get("description") or ""
            parts.append(f'<tr data-name="{e(s["name"])}" data-desc="{e(desc)}" data-kind="managed" '
                         f'data-tokens="{tokens(s.get("desc_chars", 0))}" data-tag="{tag}" data-stale="0" data-pinned="0">'
                         f'<td>{e(s["name"])}</td><td class="num">{fmt_tokens(s.get("desc_chars", 0))}</td>'
                         f'<td class="tag">{tag}</td><td class="desc">{desc and e(desc)}</td></tr>')
        parts.append("</tbody></table></div></section>")

    parts.append('<p id="none" class="empty" hidden>Nothing matches.</p></main>')

    if stale:
        names = ", ".join(e(s["name"]) for s in stale)
        parts.append(f'<p class="foot"><span class="stale">{len(stale)} stale</span> '
                     f"(unused {stale_days}d+): {names}</p>")
    else:
        parts.append(f'<p class="foot">Nothing stale — stale means unused for {stale_days}d. '
                     "Pin anything you want to keep aging out. Removal is cheap: "
                     "<code>trial-skill.sh restore &lt;name&gt;</code> refetches the same bytes.</p>")

    parts.append(
        '<aside id="tray" hidden aria-label="selection">'
        '<div class="row"><span class="count" id="tray-count"></span>'
        '<span class="verbs">'
        '<button type="button" data-verb="rm" aria-pressed="true">rm</button>'
        '<button type="button" data-verb="pin" aria-pressed="false">pin</button>'
        '<button type="button" data-verb="unpin" aria-pressed="false">unpin</button>'
        '<button type="button" data-verb="promote" aria-pressed="false">promote</button></span>'
        '<button type="button" id="tray-clear">clear</button></div>'
        '<div class="row"><code id="tray-cmd"></code><button type="button" id="tray-copy">copy</button></div>'
        "</aside>"
        '<div id="tip" role="tooltip" hidden></div>'
        f"<script>{HTML_JS}</script>")
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width">' + "".join(parts) + "</html>")


def write_html(state, path, stale_only=False):
    if not path:
        cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
        path = cache / "skills-board" / "index.html"
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(state, stale_only), encoding="utf-8")
    return str(path)


def main():
    ap = argparse.ArgumentParser(add_help=True, description=__doc__)
    ap.add_argument("--stale", action="store_true", help="only trials past the idle threshold")
    ap.add_argument("--all", action="store_true", help="draw managed skills as cards too")
    ap.add_argument("--html", nargs="?", const="", metavar="PATH",
                    help="write the board as a self-contained page and print its path "
                         "(default: $XDG_CACHE_HOME/skills-board/index.html)")
    args = ap.parse_args()

    trial_sh = Path(__file__).resolve().parent / "trial-skill.sh"
    state, err = load_state(trial_sh)
    if err:
        print(f"{RED}error:{RST} {err}", file=sys.stderr)
        return 1

    if args.html is not None:
        out = write_html(state, args.html, stale_only=args.stale)
        print(out)
        return 0

    skills = state["skills"]
    stale_days = state["stale_days"]
    trials = [s for s in skills if s["kind"] in ("trial", "untracked")]
    managed = [s for s in skills if s["kind"] == "managed"]
    stale = [s for s in trials if s.get("stale")]

    # The footer always reports the whole machine, never the current filter — a
    # --stale run that said "trials are 3% of your frontmatter" would be
    # measuring the filter rather than the problem.
    total_chars = sum(s.get("desc_chars", 0) for s in skills)
    trial_chars = sum(s.get("desc_chars", 0) for s in trials)

    if args.stale:
        trials = stale
        managed = []

    print()
    section("SKILLS",
            f"{len(skills)} installed · ~{fmt_tokens(total_chars)} tokens of frontmatter "
            f"in every session on this machine", YELLOW)
    print(f"  {DIM}{'─' * min(term_width() - 4, 92)}{RST}")
    print()

    groups, sets = group_trials(trials)

    palette_for = {}
    for i, g in enumerate(sorted(k for k in groups if k)):
        palette_for[g] = GROUP_PALETTE[i % len(GROUP_PALETTE)]

    def color_of(s):
        if s.get("stale"):
            return RED
        if s.get("pinned"):
            return DIM
        repo = s.get("repo")
        return palette_for.get(repo if repo in sets else None, YELLOW)

    for g in sorted(groups, key=lambda k: (k is None, k or "")):
        members = sorted(groups[g], key=lambda s: s["name"])
        cost = sum(m.get("desc_chars", 0) for m in members)
        detail = f"{plural(len(members), 'skill')} · ~{fmt_tokens(cost)} tokens"
        if g:
            section(f"TRIALS · {g}", detail, palette_for[g])
        else:
            section("TRIALS · sole install from their repo", detail, YELLOW)
        print()
        print_cards(members, color_of)
        if g:
            print(f"  {DIM}→ trial-skill.sh rm --repo {g}{RST}"
                  f"{DIM} removes all {len(members)}{RST}")
            print(f"  {DIM}→ trial-skill.sh promote --repo {g}{RST}"
                  f"{DIM} keeps them permanently{RST}")
            print()

    if managed:
        cost = sum(s.get("desc_chars", 0) for s in managed)
        section("MANAGED", f"{plural(len(managed), 'skill')} · ~{fmt_tokens(cost)} tokens · "
                           f"symlinks into agents-shared", BLUE)
        print()
        if args.all:
            print_cards(sorted(managed, key=lambda s: s["name"]), lambda s: BLUE)
        else:
            print_rows(sorted(managed, key=lambda s: s["name"]))

    # The bottom explainer, as in the launcher: what this state costs and the one
    # command that changes it.
    print(f"  {DIM}{'─' * min(term_width() - 4, 92)}{RST}")
    share = (trial_chars / total_chars * 100) if total_chars else 0
    print(f"  Trials are {BOLD}{share:.0f}%{RST} of your skill frontmatter "
          f"({fmt_tokens(trial_chars)} of {fmt_tokens(total_chars)} tokens).")
    if stale:
        names = ", ".join(s["name"] for s in stale[:4])
        more = f" +{len(stale) - 4} more" if len(stale) > 4 else ""
        print(f"  {RED}{len(stale)} stale{RST} "
              f"{DIM}(unused {stale_days}d+): {names}{more}{RST}")
    else:
        print(f"  {DIM}Nothing stale — stale means unused for {stale_days}d. "
              f"Pin anything you want to keep aging out.{RST}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
