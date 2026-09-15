#!/usr/bin/env python3
# DESC: Skill Tree — a local page showing every Claude Code skill group and skill, with toggles that write the real settings
"""One page for the whole skill collection, with the switches Claude Code actually honours.

Groups are the skills-directory plugins under ~/.claude/skills (each a symlink into agents-shared
with a .claude-plugin/plugin.json). A group is on or off per scope through `enabledPlugins`:
user (~/.claude/settings.json), project (<repo>/.claude/settings.json, committed) and local
(<repo>/.claude/settings.local.json). The page shows all three for the project you pick and the
effective result, and a switch runs `claude plugin enable|disable <group>@skills-dir --scope <s>`
in that project, which is exactly what the CLI would do.

A skill inside a group cannot be scoped per project — Claude Code applies `skillOverrides` to
plain skills only — so its one control is global: auto (description loaded, Claude may invoke it)
or slash-only (`disable-model-invocation: true` in its frontmatter). That edit lands in the
agents-shared working copy, fenced as a LOCAL override, and override.patch is regenerated, so it
is committed like every other local adaptation and survives an upstream sync.

Flat skills (your own, plus single external ones) get the four `skillOverrides` states per
scope: on, name-only, slash-only, off.

Usage:
    skill-tree                       # serve on 127.0.0.1, open the browser, Ctrl-C to stop
    skill-tree --port 8797 --no-open
    skill-tree --project ~/dev/game-venture   # start with that project selected
    skill-tree --idle-exit 20        # quit after 20 minutes without a request (the app uses this)

Nothing leaves the machine: the server binds to loopback and makes no network calls.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

CONFIG_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
SKILLS_DIR = CONFIG_DIR / "skills"
SCOPES = ("user", "project", "local")
OVERRIDE_STATES = ("on", "name-only", "user-invocable-only", "off")
LOCAL_OPEN = "<!-- LOCAL: slash-only; set from skill-tree -->"
LOCAL_CLOSE = "<!-- LOCAL END -->"


# ── discovery ────────────────────────────────────────────────────────────────

def dev_root() -> Path:
    env = os.environ.get("DEV_ROOT")
    if env:
        return Path(env).expanduser()
    agents = os.environ.get("AGENTS_SHARED")
    if agents:
        return Path(agents).expanduser().parent
    return Path(__file__).resolve().parent.parent.parent


def projects() -> list[dict]:
    root = dev_root()
    out = []
    for p in sorted(root.iterdir()):
        if p.is_dir() and (p / ".git").exists():
            out.append({"name": p.name, "path": str(p)})
    return out


def frontmatter(text: str) -> tuple[dict, str, str]:
    """(fields, frontmatter block including fences, body). Values are raw strings; folded
    descriptions (`>`) are joined so the length estimate is honest."""
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    if not m:
        return {}, "", text
    fields: dict[str, str] = {}
    key = None
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if km:
            key, val = km.group(1), km.group(2).strip()
            fields[key] = "" if val in (">", "|", ">-", "|-") else val
        elif key and line.startswith((" ", "\t")):
            fields[key] = (fields[key] + " " + line.strip()).strip()
    return fields, m.group(0), text[m.end():]


def tokens_of(fields: dict) -> int:
    text = (fields.get("description", "") + " " + fields.get("when_to_use", "")).strip()
    return round(len(text) / 4)


def skill_record(skill_dir: Path, group: str | None) -> dict | None:
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return None
    fields, _, _ = frontmatter(md.read_text(encoding="utf-8", errors="replace"))
    name = fields.get("name") or skill_dir.name
    source = skill_dir / "source.json"
    external = json.loads(source.read_text()) if source.is_file() else None
    return {
        "name": name,
        "dir": str(skill_dir.resolve()),
        "group": group,
        "description": fields.get("description", ""),
        "tokens": tokens_of(fields),
        "slash_only": fields.get("disable-model-invocation", "").lower() == "true",
        "user_invocable": fields.get("user-invocable", "").lower() != "false",
        "external": bool(external),
        "repo": external.get("repo") if external else None,
        "has_override": (skill_dir / "override.patch").is_file(),
    }


def collect() -> tuple[list[dict], list[dict]]:
    groups, flat = [], []
    for entry in sorted(SKILLS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        manifest = entry / ".claude-plugin" / "plugin.json"
        if manifest.is_file():
            meta = json.loads(manifest.read_text())
            skills = [r for d in sorted((entry / "skills").iterdir()) if d.is_dir()
                      for r in [skill_record(d, entry.name)] if r]
            groups.append({
                "name": entry.name, "id": f"{entry.name}@skills-dir",
                "description": meta.get("description", ""),
                "managed": entry.is_symlink(), "skills": skills,
            })
        else:
            rec = skill_record(entry, None)
            if rec:
                rec["managed"] = entry.is_symlink()
                flat.append(rec)
    return groups, flat


# ── settings ─────────────────────────────────────────────────────────────────

def settings_path(scope: str, project: Path | None) -> Path | None:
    if scope == "user":
        return CONFIG_DIR / "settings.json"
    if project is None:
        return None
    return project / ".claude" / ("settings.json" if scope == "project" else "settings.local.json")


def read_json(path: Path | None) -> dict:
    if not path or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def write_json(path: Path, data: dict) -> None:
    raw = path.read_text() if path.is_file() else ""
    indent = 4 if re.search(r"\n {4}\"", raw) and not re.search(r"\n {2}\"", raw) else 2
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=indent, ensure_ascii=False) + "\n")


def state(project: Path | None) -> dict:
    groups, flat = collect()
    per_scope = {s: read_json(settings_path(s, project)) for s in SCOPES}
    for g in groups:
        g["scopes"] = {s: per_scope[s].get("enabledPlugins", {}).get(g["id"]) for s in SCOPES}
        # local > project > user; a skills-dir plugin defaults to on
        eff, src = True, "default"
        for s in ("user", "project", "local"):
            if g["scopes"][s] is not None:
                eff, src = bool(g["scopes"][s]), s
        g["enabled"], g["enabled_by"] = eff, src
        g["tokens"] = sum(k["tokens"] for k in g["skills"] if not k["slash_only"])
    for k in flat:
        k["scopes"] = {s: per_scope[s].get("skillOverrides", {}).get(k["name"]) for s in SCOPES}
        eff, src = "on", "default"
        for s in ("user", "project", "local"):
            if k["scopes"][s] is not None:
                eff, src = k["scopes"][s], s
        if k["slash_only"] and eff == "on":
            eff = "user-invocable-only"
        k["state"], k["state_by"] = eff, src
    always_on = sum(g["tokens"] for g in groups if g["enabled"]) + sum(
        k["tokens"] for k in flat if k["state"] == "on")
    return {"project": str(project) if project else None, "projects": projects(),
            "groups": groups, "flat": flat, "always_on": always_on,
            "config_dir": str(CONFIG_DIR)}


# ── mutations ────────────────────────────────────────────────────────────────

def set_group(gid: str, scope: str, value: bool | None, project: Path | None) -> dict:
    if scope != "user" and project is None:
        return {"ok": False, "error": "pick a project for project or local scope"}
    if value is None:  # clear the entry at this scope
        path = settings_path(scope, project)
        data = read_json(path)
        data.get("enabledPlugins", {}).pop(gid, None)
        if not data.get("enabledPlugins"):
            data.pop("enabledPlugins", None)
        if path and not data and scope == "local" and path.exists():
            path.unlink()   # a local file holding nothing is noise in someone's .claude/
        elif path:
            write_json(path, data)
        return {"ok": True}
    verb = "enable" if value else "disable"
    res = subprocess.run(["claude", "plugin", verb, gid, "--scope", scope, "--json"],
                         cwd=str(project) if project else None, capture_output=True, text=True)
    if res.returncode != 0:
        return {"ok": False, "error": (res.stderr or res.stdout).strip()[:300]}
    return {"ok": True}


def set_override(name: str, scope: str, value: str | None, project: Path | None) -> dict:
    if scope != "user" and project is None:
        return {"ok": False, "error": "pick a project for project or local scope"}
    if value is not None and value not in OVERRIDE_STATES:
        return {"ok": False, "error": f"unknown state {value}"}
    path = settings_path(scope, project)
    data = read_json(path)
    ov = data.setdefault("skillOverrides", {})
    if value is None or value == "on":
        ov.pop(name, None)
    else:
        ov[name] = value
    if not ov:
        data.pop("skillOverrides", None)
    write_json(path, data)
    return {"ok": True}


def regen_override_patch(skill_dir: Path) -> None:
    """Same output as sync-external-skills.sh's regen_patch: diff(.upstream → working) for the
    files source.json lists, or no patch when the two are identical."""
    source = json.loads((skill_dir / "source.json").read_text())
    base = skill_dir / ".upstream"
    chunks = []
    for f in source.get("files", ["SKILL.md"]):
        a, b = base / f, skill_dir / f
        if not (a.is_file() and b.is_file()):
            continue
        at, bt = a.read_text(encoding="utf-8", errors="replace"), b.read_text(encoding="utf-8", errors="replace")
        if at == bt:
            continue
        chunks.append("".join(difflib.unified_diff(
            at.splitlines(True), bt.splitlines(True), fromfile=f"a/{f}", tofile=f"b/{f}")))
    patch = skill_dir / "override.patch"
    if chunks:
        patch.write_text("".join(chunks))
    elif patch.exists():
        patch.unlink()


def set_slash_only(skill_dir: Path, slash_only: bool) -> dict:
    md = skill_dir / "SKILL.md"
    text = md.read_text(encoding="utf-8")
    fields, block, body = frontmatter(text)
    if not block:
        return {"ok": False, "error": "no frontmatter"}
    lines = block.rstrip("\n").split("\n")          # ['---', ..., '---']
    lines = [l for l in lines[1:-1] if not re.match(r"^disable-model-invocation:", l)]
    if slash_only:
        lines.append("disable-model-invocation: true")
    new_block = "---\n" + "\n".join(lines) + "\n---\n"
    note = f"{LOCAL_OPEN}\n{LOCAL_CLOSE}\n"
    body = body.replace(note, "", 1)
    if slash_only and (skill_dir / "source.json").is_file():
        body = note + body.lstrip("\n") if not body.startswith("\n") else "\n" + note + body.lstrip("\n")
    md.write_text(new_block + body, encoding="utf-8")
    if (skill_dir / "source.json").is_file():
        regen_override_patch(skill_dir)
    return {"ok": True}


# ── page ─────────────────────────────────────────────────────────────────────

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Skill Tree</title>
<style>
:root{color-scheme:light dark;--bg:#f3f4f6;--panel:#fafbfc;--card:#fff;--ink:#16181c;--ink2:#5f6570;--ink3:#8b919b;--line:#d8dbe0;--focus:#2a78d6;--on:#1baf7a;--off:#c8321f;--part:#eda100;--code:#eceef1}
@media(prefers-color-scheme:dark){:root{--bg:#15171a;--panel:#1b1e22;--card:#1f2226;--ink:#e6e8eb;--ink2:#9aa1ab;--ink3:#6f7680;--line:#2c3037;--focus:#3987e5;--on:#199e70;--off:#ff7a6b;--part:#c98500;--code:#272b31}}
*{box-sizing:border-box}[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;font-variant-numeric:tabular-nums;padding-bottom:80px}
.top{position:sticky;top:0;z-index:5;background:var(--panel);border-bottom:1px solid var(--line);padding:14px 28px 12px;display:grid;gap:10px}
.brand{display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}h1{font-size:16px;margin:0}.sub{color:var(--ink2)}
.tools{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
select,input[type=search],button{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:4px;padding:4px 9px}
input[type=search]{flex:1;min-width:220px}button{cursor:pointer}button:hover{border-color:var(--ink3)}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
main{padding:20px 28px;display:grid;gap:22px}
section h2{font-size:13px;margin:0 0 8px;display:flex;gap:10px;align-items:baseline}section h2 .d{color:var(--ink2);font-weight:normal}
.group{border:1px solid var(--line);border-radius:6px;background:var(--card);margin-bottom:10px}
.ghead{display:grid;grid-template-columns:auto 1fr auto auto;gap:12px;align-items:center;padding:10px 14px;border-left:4px solid var(--line)}
.group.on .ghead{border-left-color:var(--on)}.group.off .ghead{border-left-color:var(--off)}.group.mixed .ghead{border-left-color:var(--part)}
.ghead .name{font-weight:600}.ghead .desc{color:var(--ink2);font:13px system-ui,-apple-system,sans-serif}
.ghead .cost{color:var(--ink2);white-space:nowrap}.ghead .cost b{color:var(--ink)}
.scopes{display:inline-flex;gap:6px;align-items:center;flex-wrap:wrap}.scopes label{color:var(--ink3);font-size:11px}
.ghead>*,.skill>*{min-width:0}.ghead .cost,.skill .cost{white-space:normal}
.tri{display:inline-flex;border:1px solid var(--line);border-radius:4px;overflow:hidden}
.tri button{border:0;border-radius:0;padding:2px 8px;background:none;color:var(--ink3)}
.tri button[aria-pressed=true]{background:var(--code);color:var(--ink)}.tri button.on[aria-pressed=true]{color:var(--on)}.tri button.off[aria-pressed=true]{color:var(--off)}
.tri button:disabled{opacity:.35;cursor:default}
.eff{font-size:11px;padding:1px 7px;border-radius:10px;border:1px solid var(--line);color:var(--ink2);white-space:nowrap}
.group.on .eff{color:var(--on);border-color:var(--on)}.group.off .eff{color:var(--off);border-color:var(--off)}
.skills{border-top:1px solid var(--line);padding:4px 14px 8px 30px}
.skill{display:grid;grid-template-columns:auto 1fr auto auto;gap:12px;align-items:baseline;padding:5px 0;border-bottom:1px solid color-mix(in srgb,var(--line) 50%,transparent)}
.skill:last-child{border-bottom:0}.skill .n{font-weight:600}.skill .n small{color:var(--ink3);font-weight:normal}
.skill .desc{color:var(--ink2);font:12px/1.4 system-ui,-apple-system,sans-serif;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.skill.open .desc{-webkit-line-clamp:unset}.skill .cost{color:var(--ink3);white-space:nowrap}.skill .cost b{color:var(--ink)}
.skill.hidden .cost b{color:var(--ink3);text-decoration:line-through}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:4px;overflow:hidden}
.seg button{border:0;border-radius:0;padding:1px 7px;background:none;color:var(--ink3);font-size:11px}
.seg button[aria-pressed=true]{background:var(--code);color:var(--ink)}
.flat .skill{grid-template-columns:auto 1fr auto auto auto}
.budget{display:grid;gap:4px}.bar{height:14px;display:flex;border-radius:3px;overflow:hidden;background:var(--code)}
.bar i{display:block;height:100%}.legend{display:flex;gap:4px 16px;flex-wrap:wrap;color:var(--ink2)}.legend b{color:var(--ink)}
.msg{color:var(--off);min-height:1.2em}code{background:var(--code);padding:1px 6px;border-radius:3px}
.hint{color:var(--ink3);font-size:12px;margin:0}
@media(max-width:720px){.ghead,.skill,.flat .skill{grid-template-columns:1fr}}
</style></head><body>
<div class="top">
 <div class="brand"><h1>Skill Tree</h1><span class="sub" id="sub"></span></div>
 <div class="budget"><div class="bar" id="bar"></div><div class="legend" id="legend"></div></div>
 <div class="tools">
  <label>project <select id="project"><option value="">(none: user scope only)</option></select></label>
  <input type="search" id="q" placeholder="filter  ( / )">
  <button id="expand" aria-pressed="false">full descriptions</button>
  <span class="msg" id="msg" role="status"></span>
 </div>
 <p class="hint">A group switch runs <code>claude plugin enable|disable &lt;group&gt;@skills-dir --scope …</code>; local beats project beats user. A skill inside a group is global: auto or slash-only, written to its frontmatter in agents-shared. Open sessions pick changes up on <code>/reload-plugins</code>.</p>
</div>
<main>
 <section id="groups"><h2>Groups <span class="d" id="gcount"></span></h2><div id="glist"></div></section>
 <section id="flat" class="flat"><h2>Flat skills <span class="d" id="fcount"></span></h2><div class="group"><div class="skills" id="flist"></div></div></section>
</main>
<script>
const $=(s,r=document)=>r.querySelector(s);let S=null;const fmt=t=>t>=1000?(t/1000).toFixed(1)+'k':String(t);
const HUES=['#3987e5','#d95926','#199e70','#c98500','#9085e9','#c2417a','#2a9aa0','#8a6d3b'];
async function api(path,body){const r=await fetch(path,body?{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)}:{});return r.json()}
async function load(p){S=await api('/api/state'+(p!==undefined?'?project='+encodeURIComponent(p):''));render()}
function el(tag,attrs={},...kids){const e=document.createElement(tag);for(const[k,v]of Object.entries(attrs)){if(k==='class')e.className=v;else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);else if(v!==null&&v!==undefined)e.setAttribute(k,v)}for(const k of kids)e.append(k);return e}
function tri(cur,scope,disabled,cb){const t=el('span',{class:'tri',title:scope});for(const[lab,val,cls]of[['on',true,'on'],['–',null,''],['off',false,'off']]){const b=el('button',{class:cls,'aria-pressed':String(cur===val),disabled:disabled?'':null,onclick:()=>cb(val)},lab);t.append(b)}return t}
function render(){
 const sel=$('#project');sel.replaceChildren(el('option',{value:''},'(none: user scope only)'));
 for(const p of S.projects)sel.append(el('option',{value:p.path,selected:S.project===p.path?'':null},p.name));
 const noProj=!S.project;
 $('#sub').textContent=`${S.groups.length} groups · ${S.groups.reduce((a,g)=>a+g.skills.length,0)+S.flat.length} skills · ~${fmt(S.always_on)} tokens of descriptions in every session${S.project?' in '+S.project.split('/').pop():''}`;
 const bar=$('#bar'),leg=$('#legend');bar.replaceChildren();leg.replaceChildren();
 const segs=[...S.groups.filter(g=>g.enabled).map((g,i)=>({n:g.name,t:g.tokens})),{n:'flat',t:S.flat.filter(k=>k.state==='on').reduce((a,k)=>a+k.tokens,0)}].filter(s=>s.t>0);
 const tot=segs.reduce((a,s)=>a+s.t,0)||1;
 segs.forEach((s,i)=>{const c=HUES[i%HUES.length];bar.append(el('i',{style:`width:${100*s.t/tot}%;background:${c}`,title:`${s.n} ~${fmt(s.t)}`}));leg.append(el('span',{},el('b',{style:`color:${c}`},s.n),` ~${fmt(s.t)}`))});
 const gl=$('#glist');gl.replaceChildren();$('#gcount').textContent=`${S.groups.filter(g=>g.enabled).length} on`;
 for(const g of S.groups){
  const box=el('div',{class:'group '+(g.enabled?'on':'off'),'data-name':g.name,'data-desc':g.description});
  const scopes=el('span',{class:'scopes'});
  for(const sc of ['user','project','local'])scopes.append(el('label',{},sc),tri(g.scopes[sc],sc,sc!=='user'&&noProj,async v=>{say('');const r=await api('/api/group',{id:g.id,scope:sc,value:v,project:S.project});if(!r.ok)say(r.error);load(S.project)}));
  box.append(el('div',{class:'ghead'},el('span',{class:'name'},g.name),el('span',{class:'desc'},g.description),el('span',{class:'cost'},el('b',{},'~'+fmt(g.tokens)),' tok'),el('span',{},scopes,' ',el('span',{class:'eff'},g.enabled?'on':'off',g.enabled_by!=='default'?' · '+g.enabled_by:''))));
  const list=el('div',{class:'skills'});
  for(const k of g.skills){
   const row=el('div',{class:'skill'+(k.slash_only?' hidden':''),'data-name':k.name,'data-desc':k.description});
   const seg=el('span',{class:'seg'});
   for(const[lab,val]of[['auto',false],['slash-only',true]])seg.append(el('button',{'aria-pressed':String(k.slash_only===val),onclick:async()=>{say('');const r=await api('/api/skill',{dir:k.dir,slash_only:val});if(!r.ok)say(r.error);load(S.project)}},lab));
   row.append(el('span',{class:'n'},'/'+g.name+':'+k.name,k.has_override?el('small',{title:'carries a local override'},' ✎'):''),el('span',{class:'desc',onclick:()=>row.classList.toggle('open')},k.description),el('span',{class:'cost'},el('b',{},'~'+fmt(k.tokens))),seg);
   list.append(row)}
  box.append(list);gl.append(box)}
 const fl=$('#flist');fl.replaceChildren();$('#fcount').textContent=`${S.flat.filter(k=>k.state==='on').length} on`;
 for(const k of S.flat){
  const row=el('div',{class:'skill'+(k.state!=='on'?' hidden':''),'data-name':k.name,'data-desc':k.description});
  const scopeSel=el('select',{title:'scope for the state below'});for(const sc of ['user','project','local'])scopeSel.append(el('option',{value:sc,disabled:sc!=='user'&&noProj?'':null},sc+(k.scopes[sc]?': '+k.scopes[sc]:'')));
  const seg=el('span',{class:'seg'});
  for(const[lab,val]of[['on','on'],['name only','name-only'],['slash only','user-invocable-only'],['off','off']])seg.append(el('button',{'aria-pressed':String(k.state===val),onclick:async()=>{say('');const r=await api('/api/override',{name:k.name,scope:scopeSel.value,value:val,project:S.project});if(!r.ok)say(r.error);load(S.project)}},lab));
  row.append(el('span',{class:'n'},'/'+k.name,k.slash_only?el('small',{title:'disable-model-invocation in its frontmatter'},' ⌘'):''),el('span',{class:'desc',onclick:()=>row.classList.toggle('open')},k.description),el('span',{class:'cost'},el('b',{},'~'+fmt(k.tokens))),scopeSel,seg);
  fl.append(row)}
 filter()}
function say(t){$('#msg').textContent=t||''}
function filter(){const q=$('#q').value.trim().toLowerCase();document.querySelectorAll('.skill,[data-name].group').forEach(e=>{const hit=!q||(e.dataset.name+' '+(e.dataset.desc||'')).toLowerCase().includes(q);if(e.classList.contains('group')){const kids=[...e.querySelectorAll('.skill')];let any=hit;kids.forEach(k=>{const h=!q||(k.dataset.name+' '+(k.dataset.desc||'')).toLowerCase().includes(q)||hit;k.hidden=!h;any=any||h});e.hidden=!any}else if(!e.closest('[data-name].group'))e.hidden=!hit})}
$('#project').addEventListener('change',e=>load(e.target.value));$('#q').addEventListener('input',filter);
$('#expand').addEventListener('click',e=>{document.body.classList.toggle('expanded');const on=document.body.classList.contains('expanded');e.target.setAttribute('aria-pressed',on);document.querySelectorAll('.skill').forEach(s=>s.classList.toggle('open',on))});
document.addEventListener('keydown',e=>{if(e.key==='/'&&document.activeElement!==$('#q')){e.preventDefault();$('#q').focus()}});
load();
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "skill-tree/1.0"
    last_hit = time.time()

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: dict, code: int = 200) -> None:
        self._send(code, json.dumps(data).encode(), "application/json")

    def _project(self, raw: str | None) -> Path | None:
        if not raw:
            return None
        p = Path(raw).expanduser()
        if not any(p == Path(x["path"]) for x in projects()):
            raise ValueError("unknown project")
        return p

    def do_GET(self) -> None:
        Handler.last_hit = time.time()
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        if u.path == "/api/state":
            q = dict(x.split("=", 1) for x in u.query.split("&") if "=" in x)
            from urllib.parse import unquote
            raw = unquote(q.get("project", "")) or self.server.default_project
            try:
                return self._json(state(self._project(raw)))
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        Handler.last_hit = time.time()
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            project = self._project(body.get("project"))
            if u.path == "/api/group":
                return self._json(set_group(body["id"], body["scope"], body.get("value"), project))
            if u.path == "/api/override":
                return self._json(set_override(body["name"], body["scope"], body.get("value"), project))
            if u.path == "/api/skill":
                # Only a directory the listing itself produced may be edited.
                groups, flat = collect()
                known = {k["dir"] for g in groups for k in g["skills"]} | {k["dir"] for k in flat}
                if body.get("dir") not in known:
                    return self._json({"ok": False, "error": "not a listed skill"}, 400)
                return self._json(set_slash_only(Path(body["dir"]), bool(body.get("slash_only"))))
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            return self._json({"ok": False, "error": str(e)}, 400)
        self._send(404, b"not found", "text/plain")

    def log_message(self, fmt: str, *args) -> None:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Serve the Skill Tree page on loopback.")
    ap.add_argument("--port", type=int, default=8797)
    ap.add_argument("--no-open", action="store_true", help="do not open the browser")
    ap.add_argument("--project", help="project to select at start (a repo under $DEV_ROOT)")
    ap.add_argument("--idle-exit", type=float, metavar="MINUTES", default=0,
                    help="quit after this many minutes without a request (0 = never)")
    args = ap.parse_args()
    if not SKILLS_DIR.is_dir():
        print(f"no skills directory at {SKILLS_DIR}", file=sys.stderr)
        return 1
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as e:
        print(f"port {args.port} is busy ({e}); is skill-tree already running?", file=sys.stderr)
        return 1
    srv.default_project = str(Path(args.project).expanduser().resolve()) if args.project else ""
    url = f"http://127.0.0.1:{args.port}/"
    print(url)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if not args.no_open:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
            if args.idle_exit and time.time() - Handler.last_hit > args.idle_exit * 60:
                break
    except KeyboardInterrupt:
        pass
    srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
