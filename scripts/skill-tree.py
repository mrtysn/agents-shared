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
import shutil
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


def claude_bin() -> str | None:
    """The claude CLI that group switches run. PATH first; then the installer's default
    location, which a launcher started from Spotlight does not have on its PATH."""
    found = shutil.which("claude")
    if found:
        return found
    default = Path.home() / ".local" / "bin" / "claude"
    return str(default) if os.access(default, os.X_OK) else None


CLAUDE = claude_bin()


# ── discovery ────────────────────────────────────────────────────────────────

def dev_root() -> Path:
    env = os.environ.get("DEV_ROOT")
    if env:
        return Path(env).expanduser()
    agents = os.environ.get("AGENTS_SHARED")
    if agents:
        return Path(agents).expanduser().parent
    return Path(__file__).resolve().parent.parent.parent


SKIP_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".git", "dist", "build", ".next", "target"}


def git_root(path: Path) -> Path | None:
    """The repository holding `path`, stopping at the dev root's parent."""
    stop = dev_root().parent
    for p in (path, *path.parents):
        if (p / ".git").exists():
            return p
        if p == stop:
            break
    return None


def under_dev_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(dev_root().resolve())
        return True
    except ValueError:
        return path.resolve() == dev_root().resolve()


def subdirs(path: Path) -> list[Path]:
    try:
        return sorted(d for d in path.iterdir()
                      if d.is_dir() and not d.name.startswith(".") and d.name not in SKIP_DIRS)
    except OSError:
        return []


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
    """Where Claude Code reads each scope for a session started in `project`: the shared file
    from that folder itself, the local file from the repository root."""
    if scope == "user":
        return CONFIG_DIR / "settings.json"
    if project is None:
        return None
    if scope == "project":
        return project / ".claude" / "settings.json"
    return (git_root(project) or project) / ".claude" / "settings.local.json"


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
    return {"project": str(project) if project else None, "dev_root": str(dev_root()),
            "groups": groups, "flat": flat, "always_on": always_on,
            "config_dir": str(CONFIG_DIR)}


def folder_states(groups: list[dict], user: dict) -> callable:
    """Effective on/off per group for a folder, from user + its own project file + its repo's local file."""
    def for_dir(d: Path) -> dict:
        proj = read_json(d / ".claude" / "settings.json").get("enabledPlugins", {})
        root = git_root(d)
        loc = read_json((root or d) / ".claude" / "settings.local.json").get("enabledPlugins", {})
        states = {}
        for g in groups:
            v = user.get(g["id"])
            v = proj.get(g["id"], v)
            v = loc.get(g["id"], v)
            states[g["name"]] = True if v is None else bool(v)
        return {"name": d.name, "path": str(d), "on": states,
                "has_project": (d / ".claude" / "settings.json").is_file(),
                "is_repo": (d / ".git").exists(),
                "has_children": bool(subdirs(d))}
    return for_dir


def dirs(path: Path) -> dict:
    groups, _ = collect()
    user = read_json(CONFIG_DIR / "settings.json").get("enabledPlugins", {})
    f = folder_states(groups, user)
    return {"path": str(path), "self": f(path), "children": [f(d) for d in subdirs(path)],
            "group_names": [g["name"] for g in groups]}


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
    if not CLAUDE:
        return {"ok": False, "error": "claude CLI not found; start skill-tree from a shell that has it"}
    try:
        res = subprocess.run([CLAUDE, "plugin", verb, gid, "--scope", scope, "--json"],
                             cwd=str(project) if project else None, capture_output=True,
                             text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": f"could not run {CLAUDE}: {e}"}
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
:root{color-scheme:light dark;--bg:#f6f7f9;--card:#fff;--ink:#16181c;--ink2:#555b66;--line:#d8dbe0;--line2:#e9ebee;--focus:#2a78d6;--on:#0f7a52;--off:#8a8f98;--knob:#fff;--code:#eceef1;--sel:#e6eefb}
@media(prefers-color-scheme:dark){:root{--bg:#15171a;--card:#1f2226;--ink:#e6e8eb;--ink2:#a3aab4;--line:#2c3037;--line2:#262a30;--focus:#3987e5;--on:#3fbf88;--off:#6b717b;--knob:#e6e8eb;--code:#272b31;--sel:#1f2a3a}}
*{box-sizing:border-box}[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-variant-numeric:tabular-nums}
.sr{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
.top{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 24px;display:flex;gap:8px 18px;align-items:center;flex-wrap:wrap}
h1{font-size:16px;margin:0;font-weight:600}.sum{color:var(--ink2);margin:0}
.top label{display:inline-flex;gap:6px;align-items:center;color:var(--ink2)}
select,input[type=search],button.plain{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:5px 10px;min-height:32px}
input[type=search]{min-width:180px}button.plain{cursor:pointer}button.plain[aria-pressed=true]{background:var(--code)}
@media(hover:hover){button.plain:hover{border-color:var(--ink2)}}
.msg{margin:0;min-height:1.4em;color:var(--ink2);flex-basis:100%}.msg.err{color:#b32d1c}@media(prefers-color-scheme:dark){.msg.err{color:#ff8b74}}
.wrap{display:grid;gap:28px;padding:12px 24px 60px;max-width:80rem}
h2 .k{color:var(--ink2);font-weight:normal;font-size:12px}
.grid-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}
table.grid{border-collapse:separate;border-spacing:0;min-width:100%}
.grid th,.grid td{padding:0 6px;border-bottom:1px solid var(--line2);text-align:center;white-space:nowrap;height:36px}
.grid thead th{position:sticky;top:0;background:var(--card);z-index:1;font-size:12px;font-weight:600;color:var(--ink2);padding:8px 10px}
.grid th.fcol,.grid td.fcol{text-align:left;position:sticky;left:0;background:var(--card);z-index:2;min-width:16rem}
.grid td.fcol{padding-left:calc(6px + var(--d,0)*20px);display:flex;align-items:center;gap:2px;height:36px}
.grid tr.sel td{background:var(--sel)}.grid tr:last-child td{border-bottom:0}
@media(hover:hover){.grid tbody tr:hover td{background:var(--sel)}}
.cell{min-width:52px;height:26px;border-radius:13px;border:1px solid var(--line);background:none;color:var(--ink2);font:inherit;font-size:12px;cursor:pointer;padding:0 10px}
.cell.on{background:var(--on);border-color:var(--on);color:#fff;font-weight:600}
@media(prefers-color-scheme:dark){.cell.on{color:#101412}}
.cell.diff{box-shadow:0 0 0 2px var(--bg),0 0 0 3.5px var(--focus)}
h2{font-size:13px;color:var(--ink2);font-weight:600;margin:14px 0 6px;display:flex;gap:10px;align-items:baseline}h2 .act{margin-left:auto;font-weight:normal;font-size:12px}
h2 .act button{border:0;background:none;color:var(--ink2);text-decoration:underline;text-underline-offset:3px;cursor:pointer;font:inherit;font-size:12px;padding:2px 4px}
.tree,.tree ul{list-style:none;margin:0;padding:0}.tree ul{padding-left:22px}
.row{display:grid;grid-template-columns:24px minmax(0,1fr) auto;gap:8px;align-items:center;min-height:36px;padding:0 6px 0 2px;border-radius:6px}
@media(hover:hover){.row:hover{background:var(--card)}}
.row.sel{background:var(--sel)}
.tw{width:24px;height:24px;border:0;background:none;padding:0;color:var(--ink2);cursor:pointer;font-size:12px;border-radius:4px}
.tw::before{content:"▸"}.tw[aria-expanded=true]::before{content:"▾"}.tw.leaf{visibility:hidden}
.n{display:flex;gap:8px;align-items:baseline;min-width:0}.n .name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.n .k{color:var(--ink2);font-weight:normal;font-size:13px;white-space:nowrap}
.row.g .name{font-weight:600}
.pick{border:0;background:none;padding:0;font:inherit;color:inherit;cursor:pointer;text-align:left;min-width:0;display:flex;gap:8px;align-items:baseline;min-height:32px}
.dots{display:inline-flex;gap:3px;align-items:center}.dots i{width:9px;height:9px;border-radius:50%;background:var(--off);display:inline-block}.dots i.on{background:var(--on)}
.dots i.pj{outline:2px solid var(--focus);outline-offset:1px}
.details{color:var(--ink2);font-size:13px;line-height:1.45;padding:0 6px 10px 34px;display:grid;gap:4px;text-wrap:pretty}
.details .sc{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.tri{display:inline-flex;border:1px solid var(--line);border-radius:4px;overflow:hidden;background:var(--card)}
.tri button{border:0;border-radius:0;min-height:24px;padding:1px 8px;background:none;color:var(--ink2);font:inherit;font-size:12px;cursor:pointer}
.tri button+button{border-left:1px solid var(--line2)}.tri button[aria-pressed=true]{background:var(--code);color:var(--ink);font-weight:600}
.sw{display:inline-flex;align-items:center;gap:8px;border:0;background:none;padding:4px;font:inherit;color:var(--ink2);cursor:pointer;border-radius:6px;min-height:32px}
.sw i{width:34px;height:20px;border-radius:10px;background:var(--off);position:relative;display:inline-block;flex:none}
.sw i::after{content:"";position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:var(--knob)}
.sw[aria-checked=true] i{background:var(--on)}.sw[aria-checked=true] i::after{left:16px}.sw[aria-checked=true]{color:var(--on)}
.sw .lab{min-width:3.5em;text-align:left;font-size:13px}
@media(prefers-reduced-motion:no-preference){.sw i,.sw i::after{transition:background-color .15s,left .15s}}
.hint{color:var(--ink2);font-size:13px;margin:18px 0 0;max-width:70ch}.hint code{font-family:ui-monospace,Menlo,monospace;background:var(--code);padding:1px 6px;border-radius:3px;color:var(--ink)}
.legend{color:var(--ink2);font-size:12px;margin:6px 0 0 2px;display:flex;gap:10px;flex-wrap:wrap}
@media(max-width:640px){.top,.wrap{padding-left:14px;padding-right:14px}.sw .lab{display:none}}
</style></head><body>
<div class="top">
 <h1>Skill Tree</h1><p class="sum" id="sum"></p>
 <label>Write to <select id="scope" aria-label="Scope that switches write to"><option value="user">user scope</option><option value="project">project scope</option><option value="local">local scope</option></select></label>
 <label class="sr" for="q">Filter skills</label><input type="search" id="q" placeholder="Filter skills">
 <button class="plain" id="details" aria-pressed="false">Show details</button>
 <p class="msg" id="msg" role="status"></p>
</div>
<div class="wrap">
 <section>
  <h2>Folders and groups <span class="k">click a cell to switch that group for that folder at the scope above; click a folder to see its skills below</span></h2>
  <div class="grid-wrap"><table class="grid" id="grid"><thead><tr id="grid-head"></tr></thead><tbody id="grid-body"></tbody></table></div>
  <p class="legend" id="legend"></p>
 </section>
 <section>
  <h2 id="tree-h">Groups <span class="act"><button id="expand-all">Expand all</button> <button id="collapse-all">Collapse all</button></span></h2>
  <ul class="tree" id="tree"></ul>
  <h2>Flat skills</h2>
  <ul class="tree" id="flat"></ul>
  <p class="hint">A cell or group switch writes <code>enabledPlugins</code> at the scope chosen above: project scope is that folder's own <code>.claude/settings.json</code>, local scope is its repository's <code>settings.local.json</code>; local beats project beats user. A session started in a subfolder reads the project file from that subfolder, not from the repository root. A skill switch inside a group is global: on lets Claude invoke it, off keeps it slash-only. Open sessions pick changes up on <code>/reload-plugins</code>.</p>
 </section>
</div>
<script>
const $=(s,r=document)=>r.querySelector(s);let S=null,DET=false,SEL='',GN=[],ROOT=null;const fmt=t=>t>=1000?(t/1000).toFixed(1)+'k':String(t);
let open={},fopen={};try{open=JSON.parse(localStorage.getItem('open')||'{}');fopen=JSON.parse(localStorage.getItem('fopen')||'{}');SEL=localStorage.getItem('sel')||''}catch(e){}
const save=()=>{try{localStorage.setItem('open',JSON.stringify(open));localStorage.setItem('fopen',JSON.stringify(fopen));localStorage.setItem('sel',SEL)}catch(e){}};
async function api(path,body){const r=await fetch(path,body?{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)}:{});return r.json()}
function el(tag,attrs={},...kids){const e=document.createElement(tag);for(const[k,v]of Object.entries(attrs)){if(k==='class')e.className=v;else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);else if(v!==null&&v!==undefined&&v!==false)e.setAttribute(k,v===true?'':v)}for(const k of kids)e.append(k);return e}
async function load(){S=await api('/api/state'+(SEL?'?project='+encodeURIComponent(SEL):''));if(S.error){SEL='';save();return load()}render();loadGrid()}
function sw(on,name,cb,labels=['on','off']){return el('button',{class:'sw',role:'switch','aria-checked':String(on),'aria-label':name,onclick:()=>cb(!on)},el('i'),el('span',{class:'lab'},on?labels[0]:labels[1]))}
function tri(cur,scope,cb){const t=el('span',{class:'tri',role:'group','aria-label':scope+' scope'});for(const[lab,val,name]of[['on',true,'on'],['–',null,'not set'],['off',false,'off']])t.append(el('button',{'aria-label':name,'aria-pressed':String(cur===val),onclick:()=>cb(val)},lab));return t}
async function act(p,body,done){say('');const r=await api(p,body);if(!r.ok){say(r.error,'err');return}say(done);load()}
function scope(){return $('#scope').value}
// ── matrix ──
async function loadGrid(){const root=await api('/api/dirs');GN=root.group_names;ROOT=root.self;
 const head=$('#grid-head');head.replaceChildren(el('th',{scope:'col',class:'fcol'},'Folder'),...GN.map(g=>el('th',{scope:'col',class:'mono'},g)));
 const body=$('#grid-body');body.replaceChildren();await gridRows(body,root.self,root.children,0,true);
 $('#legend').replaceChildren(el('span',{},'A filled cell is on for a session started in that folder. A ring marks a value that differs from user scope; ⚙ marks a folder with its own committed settings.'))}
async function gridRows(body,f,children,depth,isRoot){const isOpen=isRoot||!!fopen[f.path];const sel=SEL===f.path||(isRoot&&!SEL);const forScope=isRoot?'':f.path;
 const tw=el('button',{class:'tw'+(f.has_children?'':' leaf'),'aria-expanded':String(isOpen),'aria-label':(isOpen?'Collapse ':'Expand ')+f.name,onclick:()=>{fopen[f.path]=!isOpen;save();loadGrid()}});
 const pick=el('button',{class:'pick','aria-pressed':String(sel),onclick:()=>{SEL=forScope;save();load()}},el('span',{class:'name mono'},isRoot?'~/dev (user scope)':f.name),f.has_project?el('span',{class:'k',title:'Has its own committed .claude/settings.json'},'⚙'):'');
 const tr=el('tr',{class:sel?'sel':'','data-path':f.path});tr.append(el('td',{class:'fcol',style:`--d:${depth}`},tw,pick));
 for(const g of GN){const on=!!f.on[g],diff=!isRoot&&on!==!!ROOT.on[g];
  tr.append(el('td',{},el('button',{class:'cell'+(on?' on':'')+(diff?' diff':''),role:'switch','aria-checked':String(on),'aria-label':`${g} in ${isRoot?'user scope':f.name}`,
   onclick:()=>{const sc=isRoot?'user':scope();if(!isRoot&&sc==='user'){say('Choose project or local scope above to change one folder; user scope changes every folder.','err');return}
    act('/api/group',{id:g+'@skills-dir',scope:sc,value:!on,project:forScope},`${g}: ${!on?'on':'off'} for ${isRoot?'every folder':f.name} at ${sc} scope`)}},on?'on':'off')))}
 body.append(tr);
 if(isOpen&&f.has_children){const kids=children||(await api('/api/dirs?path='+encodeURIComponent(f.path))).children;for(const c of kids)await gridRows(body,c,null,depth+1,false)}}
// ── groups ──
function render(){
 const noProj=!S.project;for(const o of $('#scope').options)o.disabled=o.value!=='user'&&noProj;if(noProj)$('#scope').value='user';
 const onG=S.groups.filter(g=>g.enabled).length,where=S.project?S.project.split('/').pop():'user scope';
 $('#sum').textContent=`${where}: ${onG} of ${S.groups.length} groups on, about ${fmt(S.always_on)} tokens of skill descriptions per session.`;
 $('#tree-h').firstChild.textContent=`Groups and skills for ${where} `;
 const tree=$('#tree');tree.replaceChildren();
 for(const g of S.groups){
  const li=el('li',{'data-name':g.name,'data-desc':g.description});const isOpen=!!open[g.name];
  const tw=el('button',{class:'tw','aria-expanded':String(isOpen),'aria-label':(isOpen?'Collapse ':'Expand ')+g.name,onclick:()=>{open[g.name]=!isOpen;save();render()}});
  const hidden=g.skills.filter(k=>k.slash_only).length;
  li.append(el('div',{class:'row g'},tw,el('span',{class:'n'},el('span',{class:'name mono'},g.name),el('span',{class:'k'},`${g.skills.length} skills`+(hidden?`, ${hidden} slash-only`:''))),
   sw(g.enabled,`${g.name} group`,v=>act('/api/group',{id:g.id,scope:scope(),value:v,project:S.project},`${g.name}: ${v?'on':'off'} at ${scope()} scope`))));
  if(DET){const d=el('div',{class:'details'},el('div',{},g.description),el('div',{class:'sc'},el('span',{},`~${fmt(g.tokens)} tokens`),el('span',{},g.enabled_by==='default'?'no setting anywhere':'decided at '+g.enabled_by+' scope')));
   const sc=el('div',{class:'sc'});for(const s of ['user','project','local'])if(s==='user'||!noProj)sc.append(el('span',{},s),tri(g.scopes[s],s,v=>act('/api/group',{id:g.id,scope:s,value:v,project:S.project},`${g.name}: ${s} scope ${v===null?'cleared':v?'on':'off'}`)));
   d.append(sc);li.append(d)}
  if(isOpen){const ul=el('ul');for(const k of g.skills){const kli=el('li',{'data-name':k.name,'data-desc':k.description});
   kli.append(el('div',{class:'row'},el('span'),el('span',{class:'n'},el('span',{class:'name mono',title:k.description},'/'+g.name+':'+k.name),k.has_override?el('span',{class:'k',title:'Has a local override'},'edited'):''),
    sw(!k.slash_only,`${k.name} invocable by Claude`,v=>act('/api/skill',{dir:k.dir,slash_only:!v},`${k.name}: ${v?'auto':'slash-only'}`),['auto','slash'])));
   if(DET)kli.append(el('div',{class:'details'},el('div',{},k.description),el('div',{class:'sc'},el('span',{},`~${fmt(k.tokens)} tokens`))));
   ul.append(kli)}li.append(ul)}
  tree.append(li)}
 const fl=$('#flat');fl.replaceChildren();
 for(const k of S.flat){const li=el('li',{'data-name':k.name,'data-desc':k.description});const on=k.state==='on';
  li.append(el('div',{class:'row'},el('span'),el('span',{class:'n'},el('span',{class:'name mono',title:k.description},'/'+k.name),el('span',{class:'k'},on?'':k.state==='off'?'off':k.state==='name-only'?'name only':'slash-only')),
   sw(on,k.name,v=>act('/api/override',{name:k.name,scope:scope(),value:v?'on':'off',project:S.project},`${k.name}: ${v?'on':'off'} at ${scope()} scope`))));
  if(DET){const d=el('div',{class:'details'},el('div',{},k.description),el('div',{class:'sc'},el('span',{},`~${fmt(k.tokens)} tokens`),el('span',{},k.state_by==='default'?'':'decided at '+k.state_by+' scope')));
   const sc=el('div',{class:'sc'},el('span',{},'state at '+scope()+' scope'));const seg=el('span',{class:'tri',role:'group','aria-label':'visibility for '+k.name});
   for(const[lab,val]of[['on','on'],['name only','name-only'],['slash only','user-invocable-only'],['off','off']])seg.append(el('button',{'aria-pressed':String((k.scopes[scope()]||'on')===val),onclick:()=>act('/api/override',{name:k.name,scope:scope(),value:val,project:S.project},`${k.name}: ${lab} at ${scope()} scope`)},lab));
   sc.append(seg);d.append(sc);li.append(d)}
  fl.append(li)}
 filter()}
function say(t,cls){const m=$('#msg');m.textContent=t||'';m.className='msg'+(cls?' '+cls:'')}
function filter(){const q=$('#q').value.trim().toLowerCase();const hit=e=>!q||(e.dataset.name+' '+(e.dataset.desc||'')).toLowerCase().includes(q);
 for(const g of $('#tree').children){const gh=hit(g);let any=gh;for(const k of g.querySelectorAll('ul>li')){const h=gh||hit(k);k.hidden=!h;any=any||h}g.hidden=!any;if(q&&any&&!gh&&!g.querySelector('ul')){open[g.dataset.name]=true;render();return}}
 for(const k of $('#flat').children)k.hidden=!hit(k)}
$('#scope').addEventListener('change',()=>render());$('#q').addEventListener('input',filter);
$('#details').addEventListener('click',e=>{DET=!DET;e.currentTarget.setAttribute('aria-pressed',DET);e.currentTarget.textContent=DET?'Hide details':'Show details';render()});
$('#expand-all').addEventListener('click',()=>{for(const g of S.groups)open[g.name]=true;save();render()});
$('#collapse-all').addEventListener('click',()=>{open={};save();render()});
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
        if not p.is_dir() or not under_dev_root(p):
            raise ValueError("folder must be under the dev root")
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
        if u.path == "/api/dirs":
            from urllib.parse import unquote
            q = dict(x.split("=", 1) for x in u.query.split("&") if "=" in x)
            raw = unquote(q.get("path", "")) or str(dev_root())
            try:
                return self._json(dirs(self._project(raw)))
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
        except OSError as e:
            return self._json({"ok": False, "error": str(e)}, 500)
        self._send(404, b"not found", "text/plain")

    def log_message(self, fmt: str, *args) -> None:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Serve the Skill Tree page on loopback.")
    ap.add_argument("--port", type=int, default=8797)
    ap.add_argument("--no-open", action="store_true", help="do not open the browser")
    ap.add_argument("--project", help="folder to select at start (anywhere under $DEV_ROOT)")
    ap.add_argument("--idle-exit", type=float, metavar="MINUTES", default=0,
                    help="quit after this many minutes without a request (0 = never)")
    args = ap.parse_args()
    if not SKILLS_DIR.is_dir():
        print(f"no skills directory at {SKILLS_DIR}", file=sys.stderr)
        return 1
    if not CLAUDE:
        print("claude CLI not found on PATH or in ~/.local/bin; group switches need it", file=sys.stderr)
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
