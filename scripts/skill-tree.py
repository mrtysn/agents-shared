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
:root{color-scheme:light dark;--bg:#f6f7f9;--card:#fff;--ink:#16181c;--ink2:#555b66;--line:#d8dbe0;--line2:#e9ebee;--focus:#2a78d6;--on:#0f7a52;--off:#8a8f98;--knob:#fff;--code:#eceef1}
@media(prefers-color-scheme:dark){:root{--bg:#15171a;--card:#1f2226;--ink:#e6e8eb;--ink2:#a3aab4;--line:#2c3037;--line2:#262a30;--focus:#3987e5;--on:#3fbf88;--off:#6b717b;--knob:#e6e8eb;--code:#272b31}}
*{box-sizing:border-box}[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;padding:0 0 60px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-variant-numeric:tabular-nums}
.sr{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
.top{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:14px 28px;display:flex;gap:10px 18px;align-items:center;flex-wrap:wrap}
h1{font-size:16px;margin:0;font-weight:600}.sum{color:var(--ink2);margin:0}
.top label{display:inline-flex;gap:6px;align-items:center;color:var(--ink2)}
select,input[type=search],button.plain{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:5px 10px;min-height:32px}
input[type=search]{min-width:200px}button.plain{cursor:pointer}button.plain[aria-pressed=true]{background:var(--code)}
@media(hover:hover){button.plain:hover{border-color:var(--ink2)}}
.msg{margin:0;min-height:1.4em;color:var(--ink2);flex-basis:100%}.msg.err{color:#b32d1c}@media(prefers-color-scheme:dark){.msg.err{color:#ff8b74}}
main{padding:16px 28px;max-width:60rem}
.tree{list-style:none;margin:0;padding:0}.tree ul{list-style:none;margin:0;padding:0 0 4px 34px}
.row{display:grid;grid-template-columns:24px 1fr auto;gap:10px;align-items:center;min-height:38px;padding:0 6px;border-radius:6px}
@media(hover:hover){.row:hover{background:var(--card)}}
.row.g{font-weight:600}.row.g .n{font-size:15px}
.tw{width:24px;height:24px;border:0;background:none;padding:0;color:var(--ink2);cursor:pointer;font-size:12px;border-radius:4px}
.tw::before{content:"▸"}.tw[aria-expanded=true]::before{content:"▾"}
.n{display:flex;gap:10px;align-items:baseline;min-width:0}.n .name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.n .k{color:var(--ink2);font-weight:normal;font-size:13px}
.details{color:var(--ink2);font-size:13px;line-height:1.45;padding:0 6px 10px 40px;display:grid;gap:4px;text-wrap:pretty}
.details .sc{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.details .sc span{color:var(--ink2)}
.tri{display:inline-flex;border:1px solid var(--line);border-radius:4px;overflow:hidden;background:var(--card)}
.tri button{border:0;border-radius:0;min-height:24px;padding:1px 8px;background:none;color:var(--ink2);font:inherit;font-size:12px;cursor:pointer}
.tri button+button{border-left:1px solid var(--line2)}.tri button[aria-pressed=true]{background:var(--code);color:var(--ink);font-weight:600}
.sw{display:inline-flex;align-items:center;gap:8px;border:0;background:none;padding:4px;font:inherit;color:var(--ink2);cursor:pointer;border-radius:6px;min-height:32px}
.sw i{width:34px;height:20px;border-radius:10px;background:var(--off);position:relative;display:inline-block;flex:none}
.sw i::after{content:"";position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:var(--knob)}
.sw[aria-checked=true] i{background:var(--on)}.sw[aria-checked=true] i::after{left:16px}
.sw[aria-checked=true]{color:var(--on)}.sw:disabled{opacity:.45;cursor:default}
.sw .lab{min-width:3.5em;text-align:left;font-size:13px}
@media(prefers-reduced-motion:no-preference){.sw i,.sw i::after{transition:background-color .15s,left .15s}}
.mixed .lab::after{content:" ·";color:var(--ink2)}
h2{font-size:13px;color:var(--ink2);font-weight:600;margin:22px 0 6px;padding-left:40px}
.hint{color:var(--ink2);font-size:13px;margin:18px 0 0 40px;max-width:70ch}.hint code{font-family:ui-monospace,Menlo,monospace;background:var(--code);padding:1px 6px;border-radius:3px;color:var(--ink)}
@media(max-width:640px){.top,main{padding-left:14px;padding-right:14px}.tree ul{padding-left:18px}.sw .lab{display:none}}
</style></head><body>
<div class="top">
 <h1>Skill Tree</h1><p class="sum" id="sum"></p>
 <label>Project <select id="project"><option value="">None (user scope only)</option></select></label>
 <label>Write to <select id="scope" aria-label="Scope that switches write to"><option value="user">user scope</option><option value="project">project scope</option><option value="local">local scope</option></select></label>
 <label class="sr" for="q">Filter skills</label><input type="search" id="q" placeholder="Filter">
 <button class="plain" id="details" aria-pressed="false">Show details</button>
 <p class="msg" id="msg" role="status"></p>
</div>
<main>
 <ul class="tree" id="tree"></ul>
 <h2>Flat skills</h2>
 <ul class="tree" id="flat"></ul>
 <p class="hint">A group switch writes <code>enabledPlugins</code> at the scope chosen above; local beats project beats user. A skill switch inside a group is global: on means Claude may invoke it, off keeps it slash-only. Open sessions pick changes up on <code>/reload-plugins</code>.</p>
</main>
<script>
const $=(s,r=document)=>r.querySelector(s);let S=null,DET=false;const fmt=t=>t>=1000?(t/1000).toFixed(1)+'k':String(t);
let open={};try{open=JSON.parse(localStorage.getItem('open')||'{}')}catch(e){}
async function api(path,body){const r=await fetch(path,body?{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)}:{});return r.json()}
async function load(p){S=await api('/api/state'+(p!==undefined?'?project='+encodeURIComponent(p):''));render()}
function el(tag,attrs={},...kids){const e=document.createElement(tag);for(const[k,v]of Object.entries(attrs)){if(k==='class')e.className=v;else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);else if(v!==null&&v!==undefined&&v!==false)e.setAttribute(k,v===true?'':v)}for(const k of kids)e.append(k);return e}
function sw(on,name,disabled,cb,labels=['on','off']){return el('button',{class:'sw',role:'switch','aria-checked':String(on),'aria-label':name,disabled,onclick:()=>cb(!on)},el('i'),el('span',{class:'lab'},on?labels[0]:labels[1]))}
function tri(cur,scope,cb){const t=el('span',{class:'tri',role:'group','aria-label':scope+' scope'});for(const[lab,val,name]of[['on',true,'on'],['–',null,'not set'],['off',false,'off']])t.append(el('button',{'aria-label':name,'aria-pressed':String(cur===val),onclick:()=>cb(val)},lab));return t}
async function act(p,body,done){say('');const r=await api(p,body);if(!r.ok){say(r.error,'err');return}say(done);load(S.project)}
function scope(){return $('#scope').value}
function render(){
 const ps=$('#project');ps.replaceChildren(el('option',{value:''},'None (user scope only)'));
 for(const p of S.projects)ps.append(el('option',{value:p.path,selected:S.project===p.path},p.name));
 const noProj=!S.project;for(const o of $('#scope').options)o.disabled=o.value!=='user'&&noProj;if(noProj)$('#scope').value='user';
 const onG=S.groups.filter(g=>g.enabled).length;
 $('#sum').textContent=`${onG} of ${S.groups.length} groups on. About ${fmt(S.always_on)} tokens of skill descriptions load in every session${S.project?' in '+S.project.split('/').pop():''}.`;
 const tree=$('#tree');tree.replaceChildren();
 for(const g of S.groups){
  const li=el('li',{'data-name':g.name,'data-desc':g.description});
  const isOpen=!!open[g.name];
  const tw=el('button',{class:'tw','aria-expanded':String(isOpen),'aria-label':(isOpen?'Collapse ':'Expand ')+g.name,onclick:()=>{open[g.name]=!isOpen;try{localStorage.setItem('open',JSON.stringify(open))}catch(e){}render()}});
  const hidden=g.skills.filter(k=>k.slash_only).length;
  const row=el('div',{class:'row g'},tw,el('span',{class:'n'},el('span',{class:'name mono'},g.name),el('span',{class:'k'},`${g.skills.length} skills`+(hidden?`, ${hidden} slash-only`:'')),el('span',{class:'k '+(g.enabled?'':'off')},g.enabled?'':'off')),
   sw(g.enabled,`${g.name} group`,false,v=>act('/api/group',{id:g.id,scope:scope(),value:v,project:S.project},`${g.name}: ${v?'on':'off'} at ${scope()} scope`)));
  li.append(row);
  if(DET){const d=el('div',{class:'details'},el('div',{},g.description),el('div',{class:'sc'},el('span',{},`~${fmt(g.tokens)} tokens`),el('span',{},g.enabled_by==='default'?'no setting anywhere':'decided at '+g.enabled_by+' scope')));
   const sc=el('div',{class:'sc'});for(const s of ['user','project','local'])if(s==='user'||!noProj)sc.append(el('span',{},s),tri(g.scopes[s],s,v=>act('/api/group',{id:g.id,scope:s,value:v,project:S.project},`${g.name}: ${s} scope ${v===null?'cleared':v?'on':'off'}`)));
   d.append(sc);li.append(d)}
  if(isOpen){const ul=el('ul');for(const k of g.skills){
   const kli=el('li',{'data-name':k.name,'data-desc':k.description});
   kli.append(el('div',{class:'row'},el('span'),el('span',{class:'n'},el('span',{class:'name mono',title:k.description},'/'+g.name+':'+k.name),k.has_override?el('span',{class:'k',title:'Has a local override'},'edited'):''),
    sw(!k.slash_only,`${k.name} invocable by Claude`,false,v=>act('/api/skill',{dir:k.dir,slash_only:!v},`${k.name}: ${v?'auto':'slash-only'}`),['auto','slash'])));
   if(DET)kli.append(el('div',{class:'details'},el('div',{},k.description),el('div',{class:'sc'},el('span',{},`~${fmt(k.tokens)} tokens`))));
   ul.append(kli)}li.append(ul)}
  tree.append(li)}
 const fl=$('#flat');fl.replaceChildren();
 for(const k of S.flat){
  const li=el('li',{'data-name':k.name,'data-desc':k.description});const on=k.state==='on';
  li.append(el('div',{class:'row'},el('span'),el('span',{class:'n'},el('span',{class:'name mono',title:k.description},'/'+k.name),el('span',{class:'k '+(on?'':'off')},on?'':k.state==='off'?'off':k.state==='name-only'?'name only':'slash-only')),
   sw(on,`${k.name}`,false,v=>act('/api/override',{name:k.name,scope:scope(),value:v?'on':'off',project:S.project},`${k.name}: ${v?'on':'off'} at ${scope()} scope`))));
  if(DET){const d=el('div',{class:'details'},el('div',{},k.description),el('div',{class:'sc'},el('span',{},`~${fmt(k.tokens)} tokens`),el('span',{},k.state_by==='default'?'':'decided at '+k.state_by+' scope')));
   const sc=el('div',{class:'sc'},el('span',{},'state at '+scope()+' scope'));const seg=el('span',{class:'tri',role:'group','aria-label':'visibility for '+k.name});
   for(const[lab,val]of[['on','on'],['name only','name-only'],['slash only','user-invocable-only'],['off','off']])seg.append(el('button',{'aria-pressed':String((k.scopes[scope()]||'on')===val),onclick:()=>act('/api/override',{name:k.name,scope:scope(),value:val,project:S.project},`${k.name}: ${lab} at ${scope()} scope`)},lab));
   sc.append(seg);d.append(sc);li.append(d)}
  fl.append(li)}
 filter()}
function say(t,cls){const m=$('#msg');m.textContent=t||'';m.className='msg'+(cls?' '+cls:'')}
function filter(){const q=$('#q').value.trim().toLowerCase();const hit=e=>!q||(e.dataset.name+' '+(e.dataset.desc||'')).toLowerCase().includes(q);
 for(const g of $('#tree').children){const gh=hit(g);let any=gh;for(const k of g.querySelectorAll('ul>li')){const h=gh||hit(k);k.hidden=!h;any=any||h}g.hidden=!any;if(q&&any&&!gh){const ul=g.querySelector('ul');if(!ul){open[g.dataset.name]=true;render();return}}}
 for(const k of $('#flat').children)k.hidden=!hit(k)}
$('#project').addEventListener('change',e=>load(e.target.value));$('#scope').addEventListener('change',()=>render());$('#q').addEventListener('input',filter);
$('#details').addEventListener('click',e=>{DET=!DET;e.currentTarget.setAttribute('aria-pressed',DET);e.currentTarget.textContent=DET?'Hide details':'Show details';render()});
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
