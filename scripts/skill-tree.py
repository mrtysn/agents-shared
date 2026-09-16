#!/usr/bin/env python3
# DESC: Skill Tree — a local page showing every Claude Code skill group and skill, with toggles that write the real settings
"""One page for the whole skill collection, with the switches Claude Code actually honours.

Groups are the skills-directory plugins under ~/.claude/skills (each a symlink into agents-shared
with a .claude-plugin/plugin.json). A group is on or off per scope through `enabledPlugins`:
user (~/.claude/settings.json, the default for every folder), local (<repo>/.claude/settings.local.json,
gitignored: this machine's override for one repository) and project (<folder>/.claude/settings.json,
committed, for the rare setting a repository's other readers should share). The page shows all three
for the folder you pick and the effective result, and a switch runs
`claude plugin enable|disable <group>@skills-dir --scope <s>` in that folder, which is exactly what
the CLI would do. Local is the default target when a folder is selected.

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
        return sorted((d for d in path.iterdir()
                       if d.is_dir() and not d.name.startswith(".") and d.name not in SKIP_DIRS),
                      key=lambda d: d.name.casefold())
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
                "has_local": root is not None and (root / ".claude" / "settings.local.json").is_file()
                and bool(loc),
                "is_repo": (d / ".git").exists(),
                "has_children": bool(subdirs(d))}
    return for_dir


def dirs(path: Path, open_paths: set[str] = frozenset()) -> dict:
    """The folder at `path` with its children; a child whose path is in `open_paths` carries its
    own children too, recursively, so one request serves the whole expanded tree."""
    groups, _ = collect()
    user = read_json(CONFIG_DIR / "settings.json").get("enabledPlugins", {})
    f = folder_states(groups, user)

    def node(d: Path, depth: int) -> dict:
        rec = f(d)
        if (depth == 0 or str(d) in open_paths) and rec["has_children"] and depth < 12:
            rec["children"] = [node(c, depth + 1) for c in subdirs(d)]
        return rec

    return {"path": str(path), "self": node(path, 0), "group_names": [g["name"] for g in groups]}


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
:root{color-scheme:light dark;--bg:#f6f7f9;--card:#fff;--ink:#16181c;--ink2:#555b66;--line:#d8dbe0;--line2:#e9ebee;--focus:#2a78d6;--on:#0f7a52;--off:#8a8f98;--knob:#fff;--code:#eceef1;--sel:#e6eefb;--edge:#b9bec7;--edge-on:#0f7a52;--node:#fff;--node-line:#c9cdd4}
@media(prefers-color-scheme:dark){:root{--bg:#15171a;--card:#1f2226;--ink:#e6e8eb;--ink2:#a3aab4;--line:#2c3037;--line2:#262a30;--focus:#3987e5;--on:#3fbf88;--off:#6b717b;--knob:#e6e8eb;--code:#272b31;--sel:#1f2a3a;--edge:#3a3f47;--edge-on:#3fbf88;--node:#22262b;--node-line:#3a3f47}}
*{box-sizing:border-box}[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;height:100vh;display:grid;grid-template-rows:auto minmax(0,1fr)}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-variant-numeric:tabular-nums}
.sr{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
.top{background:var(--bg);border-bottom:1px solid var(--line);padding:8px 16px;display:flex;gap:6px 14px;align-items:center;flex-wrap:wrap}
h1{font-size:14px;margin:0;font-weight:600}.top label{display:inline-flex;gap:6px;align-items:center;color:var(--ink2)}
select,input[type=search],button.plain{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:3px 9px;min-height:28px}
input[type=search]{min-width:160px}button.plain{cursor:pointer}button.plain[aria-pressed=true]{background:var(--code)}
@media(hover:hover){button.plain:hover{border-color:var(--ink2)}}
.msg{margin:0 0 0 auto;color:var(--ink2)}.msg.err{color:#b32d1c}@media(prefers-color-scheme:dark){.msg.err{color:#ff8b74}}
.wrap{display:grid;grid-template-columns:minmax(0,1fr) 22rem;min-height:0}
@media(max-width:860px){.wrap{grid-template-columns:1fr;grid-template-rows:60vh auto}}
/* canvas */
.canvas{position:relative;overflow:hidden;background:var(--bg);cursor:grab;touch-action:none;user-select:none}
.canvas.drag{cursor:grabbing}
.canvas svg{position:absolute;inset:0;width:100%;height:100%}
.lane{font-size:11px;font-weight:600;fill:var(--ink2);letter-spacing:.02em}
.edge{fill:none;stroke:var(--edge);stroke-width:1.2}.edge.on{stroke:var(--edge-on);stroke-width:1.6}.edge.hov{stroke:var(--focus);stroke-width:2;opacity:1!important}
.node rect{fill:var(--node);stroke:var(--node-line);stroke-width:1;rx:6}
.node text{fill:var(--ink);font-size:12px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;pointer-events:none}
.node text.sub{fill:var(--ink2);font-size:10.5px;font-family:system-ui,-apple-system,sans-serif}
.node .dot{fill:var(--off)}.node .dot.on{fill:var(--on)}
.node.folder rect{stroke-width:1}.node.group rect{stroke:var(--on);stroke-width:1.2}.node.group.off rect{stroke:var(--off);stroke-dasharray:3 2}
.node.skill rect{rx:10}.node.skill.slash rect{stroke-dasharray:3 2}
.node.sel rect{stroke:var(--focus);stroke-width:2;fill:var(--sel)}
.node .tw{fill:var(--ink2);font-size:10px;font-family:system-ui,sans-serif}
.node{cursor:pointer}
svg.dim .node:not(.lit){opacity:.18}svg.dim .edge:not(.lit){opacity:.12}svg.dim .lane{opacity:.6}
@media(prefers-reduced-motion:no-preference){.node{transition:opacity .15s}}
.fab{position:absolute;right:12px;bottom:12px;display:flex;gap:6px}
/* detail */
aside{border-left:1px solid var(--line);padding:12px 16px;overflow:auto;min-height:0}
@media(max-width:860px){aside{border-left:0;border-top:1px solid var(--line)}}
aside h2{font-size:12px;color:var(--ink2);font-weight:600;margin:12px 0 4px}aside h2:first-child{margin-top:0}
.title{margin:0;font-weight:600;font-size:13px;overflow-wrap:anywhere}.title .k{color:var(--ink2);font-weight:normal;display:block;font-size:12px}
.lead{margin:6px 0 0;color:var(--ink2);text-wrap:pretty}
.list{list-style:none;margin:0;padding:0}.list li{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;min-height:28px;padding:0 4px;border-radius:5px}
.list .name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.list .k{color:var(--ink2);font-size:12px}
.list button.link{border:0;background:none;padding:0;font:inherit;color:inherit;cursor:pointer;text-align:left;min-width:0;text-decoration:underline;text-underline-offset:3px;text-decoration-color:var(--line)}
.sw{display:inline-flex;align-items:center;gap:6px;border:0;background:none;padding:2px 3px;font:inherit;font-size:12px;color:var(--ink2);cursor:pointer;border-radius:5px;min-height:24px}
.sw i{width:26px;height:16px;border-radius:8px;background:var(--off);position:relative;display:inline-block;flex:none}
.sw i::after{content:"";position:absolute;top:2px;left:2px;width:12px;height:12px;border-radius:50%;background:var(--knob)}
.sw[aria-checked=true] i{background:var(--on)}.sw[aria-checked=true] i::after{left:12px}.sw[aria-checked=true]{color:var(--on)}
.sw .lab{min-width:3.2em;text-align:left}
.tri{display:inline-flex;border:1px solid var(--line);border-radius:4px;overflow:hidden;background:var(--card)}
.tri button{border:0;border-radius:0;min-height:22px;padding:1px 7px;background:none;color:var(--ink2);font:inherit;font-size:12px;cursor:pointer}
.tri button+button{border-left:1px solid var(--line2)}.tri button[aria-pressed=true]{background:var(--code);color:var(--ink);font-weight:600}
.details{color:var(--ink2);font-size:12px;display:grid;gap:4px;margin-top:4px}.details .sc{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.hint{color:var(--ink2);font-size:12px;margin:16px 0 0}.hint code{font-family:ui-monospace,Menlo,monospace;background:var(--code);padding:1px 5px;border-radius:3px;color:var(--ink)}
</style></head><body>
<div class="top">
 <h1>Skill Tree</h1>
 <label>Write to <select id="scope" aria-label="Scope that switches write to"><option value="user">user scope, every folder</option><option value="local">this repo, this machine</option><option value="project">this folder, committed</option></select></label>
 <label class="sr" for="q">Find a folder, group or skill</label><input type="search" id="q" placeholder="Find">
 <button class="plain" id="details" aria-pressed="false">Show details</button>
 <p class="msg" id="msg" role="status"></p>
</div>
<div class="wrap">
 <div class="canvas" id="canvas">
  <svg id="svg" aria-label="Folders, groups and skills"><g id="view"><g id="edges"></g><g id="nodes"></g></g></svg>
  <div class="fab"><button class="plain" id="fit">Fit</button><button class="plain" id="clear">Clear selection</button></div>
 </div>
 <aside id="side"></aside>
</div>
<script>
const $=(s,r=document)=>r.querySelector(s);const NS='http://www.w3.org/2000/svg';
let S=null,DET=false,SEL='',SELKIND='',CTX='',GN=[],ROOT=null,FOLDERS=[],fopen={},gopen={},view={x:0,y:0,k:1};const fmt=t=>t>=1000?(t/1000).toFixed(1)+'k':String(t);
try{fopen=JSON.parse(localStorage.getItem('fopen')||'{}');gopen=JSON.parse(localStorage.getItem('gclosed')||'{}');SEL=localStorage.getItem('sel')||'';SELKIND=localStorage.getItem('selkind')||'';CTX=localStorage.getItem('ctx')||''}catch(e){}
const save=()=>{try{localStorage.setItem('gclosed',JSON.stringify(gopen));localStorage.setItem('fopen',JSON.stringify(fopen));localStorage.setItem('sel',SEL);localStorage.setItem('selkind',SELKIND);localStorage.setItem('ctx',CTX)}catch(e){}};
async function api(path,body){const r=await fetch(path,body?{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)}:{});return r.json()}
function el(tag,attrs={},...kids){const e=document.createElement(tag);for(const[k,v]of Object.entries(attrs)){if(k==='class')e.className=v;else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);else if(v!==null&&v!==undefined&&v!==false)e.setAttribute(k,v===true?'':v)}for(const k of kids)e.append(k);return e}
function sv(tag,attrs={},...kids){const e=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attrs)){if(k==='class')e.setAttribute('class',v);else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);else if(v!==null&&v!==undefined)e.setAttribute(k,v)}for(const k of kids)e.append(k);return e}
function scope(){return $('#scope').value}
async function act(p,body,done){say('');const r=await api(p,body);if(!r.ok){say(r.error,'err');return}say(done);load()}
function say(t,cls){const m=$('#msg');m.textContent=t||'';m.className='msg'+(cls?' '+cls:'')}
const folderProject=()=>CTX;
// Data: /api/state depends on the context folder, /api/dirs on which folders are open. They are
// fetched in parallel and only when their inputs changed; focus changes never touch the network.
let stateFor=null,treeFor=null,TREE=null;
async function fetchState(){const key=folderProject();if(stateFor===key&&S)return;const r=await api('/api/state'+(key?'?project='+encodeURIComponent(key):''));if(r.error){SEL='';SELKIND='';CTX='';save();return fetchState()}S=r;stateFor=key}
async function fetchTree(force){const opened=Object.keys(fopen).filter(k=>fopen[k]);const key=JSON.stringify(opened);if(!force&&treeFor===key&&TREE)return;TREE=await api('/api/dirs?open='+encodeURIComponent(key));treeFor=key;GN=TREE.group_names;ROOT=TREE.self;FOLDERS=[];walk(TREE.self,0)}
function walk(f,depth){const isRoot=depth===0;const isOpen=isRoot||!!fopen[f.path];FOLDERS.push({...f,children:undefined,depth,isOpen,isRoot});if(isOpen&&f.children)for(const c of f.children)walk(c,depth+1)}
async function load(){await Promise.all([fetchState(),fetchTree(false)]);draw();side()}
async function refresh(){stateFor=null;await Promise.all([fetchState(),fetchTree(true)]);draw();side()}
async function act(p,body,done){say('');const r=await api(p,body);if(!r.ok){say(r.error,'err');return}say(done);refresh()}
// ── graph ──
const ROW=26,X0=24,XG=560,XS=800,W0=280,WG=150,WS=190;
let NODES=new Map(),EDGES=[],ADJ=new Map(),POS={};
const measure=(()=>{const c=document.createElement('canvas').getContext('2d');const cache=new Map();return(txt,font)=>{const k=font+' '+txt;let w=cache.get(k);if(w===undefined){c.font=font;w=c.measureText(txt).width;cache.set(k,w)}return w}})();
const FONT_NODE='12px ui-monospace, SFMono-Regular, Menlo, monospace',FONT_SUB='10.5px system-ui, -apple-system, sans-serif';
function trunc(label,room){if(measure(label,FONT_NODE)<=room)return label;let lo=1,hi=label.length;while(lo<hi){const mid=(lo+hi+1)>>1;if(measure(label.slice(0,mid)+'…',FONT_NODE)<=room)lo=mid;else hi=mid-1}return label.slice(0,lo)+'…'}
function draw(){const t0=performance.now();const edges=$('#edges'),nodes=$('#nodes');edges.replaceChildren();nodes.replaceChildren();NODES=new Map();EDGES=[];ADJ=new Map();
 const lanes=$('#view');lanes.querySelectorAll('.lane').forEach(l=>l.remove());
 for(const[x,t]of[[X0,'folders'],[XG,'groups'],[XS,'skills']])lanes.insertBefore(sv('text',{class:'lane',x,y:14},t),edges);
 const pos=POS={};FOLDERS.forEach((f,i)=>{pos['f:'+f.path]={x:X0+f.depth*16,y:30+i*ROW,w:W0-f.depth*16,lane:0}});
 const skills=[];let gy=30;S.groups.forEach(g=>{const open=!gopen[g.name];const n=open?g.skills.length:0;const h=Math.max(1,n)*ROW;pos['g:'+g.name]={x:XG,y:gy+h/2-ROW/2,w:WG,lane:1};if(open)g.skills.forEach((k,j)=>{pos['s:'+g.name+':'+k.name]={x:XS,y:gy+j*ROW,w:WS,lane:2};skills.push({g,k})});gy+=h+(open?14:6)});
 const path=(a,b)=>{const x1=a.x+a.w,y1=a.y+ROW/2-3,x2=b.x,y2=b.y+ROW/2-3,mx=(x1+x2)/2;return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`};
 const E=[];
 FOLDERS.forEach(f=>{GN.forEach(g=>{const on=!!f.on[g];if(f.isRoot){if(on)E.push({a:'f:'+f.path,b:'g:'+g,on:true})}else if(on!==!!ROOT.on[g])E.push({a:'f:'+f.path,b:'g:'+g,on})})});
 skills.forEach(({g,k})=>E.push({a:'g:'+g.name,b:'s:'+g.name+':'+k.name,on:g.enabled&&!k.slash_only}));
 const efrag=document.createDocumentFragment();
 for(const e of E){const a=pos[e.a],b=pos[e.b];if(!a||!b)continue;const el_=sv('path',{class:'edge'+(e.on?' on':''),d:path(a,b)});e.el=el_;EDGES.push(e);efrag.append(el_);(ADJ.get(e.a)||ADJ.set(e.a,[]).get(e.a)).push(e);(ADJ.get(e.b)||ADJ.set(e.b,[]).get(e.b)).push(e)}
 edges.append(efrag);
 const sel=selId();const nfrag=document.createDocumentFragment();
 const node=(id,cls,p,label,sub,extra)=>{const g=sv('g',{class:'node '+cls+(id===sel?' sel':''),transform:`translate(${p.x},${p.y})`,'data-id':id,tabindex:0,role:'button','aria-label':label+(sub?', '+sub:'')});
  g.append(sv('rect',{width:p.w,height:ROW-6}));if(extra)extra(g);const subW=sub?measure(sub,FONT_SUB)+8:0;const room=p.w-(extra?22:10)-8-subW;const shown=trunc(label,room);
  g.append(sv('text',{x:extra?22:10,y:ROW/2+1},shown));if(shown!==label)g.append(sv('title',{},label));if(sub)g.append(sv('text',{class:'sub',x:p.w-8,y:ROW/2+1,'text-anchor':'end'},sub));
  g.addEventListener('click',e=>{if(e.target.classList.contains('tw'))return;select(id)});g.addEventListener('keydown',nodeKeys);
  g.addEventListener('pointerenter',()=>hover(id,true));g.addEventListener('pointerleave',()=>hover(id,false));
  NODES.set(id,g);nfrag.append(g);return g};
 FOLDERS.forEach(f=>{const p=pos['f:'+f.path];const n=GN.filter(g=>f.on[g]).length;
  node('f:'+f.path,'folder',p,f.isRoot?'~/dev':f.name,f.isRoot?'user scope':((f.has_local||f.has_project)?'⚙ own':`${n}/${GN.length}`),g=>{if(f.has_children&&!f.isRoot){const t=sv('text',{class:'tw',x:8,y:ROW/2+1,role:'button','aria-label':(f.isOpen?'Collapse ':'Expand ')+f.name},f.isOpen?'▾':'▸');t.addEventListener('click',e=>{e.stopPropagation();toggleFolder(f)});g.append(t)}else if(f.isRoot){g.append(sv('text',{class:'tw',x:8,y:ROW/2+1},'●'))}})});
 S.groups.forEach(g=>node('g:'+g.name,'group'+(g.enabled?'':' off'),pos['g:'+g.name],g.name,(g.enabled?'on':'off')+(gopen[g.name]?` · ${g.skills.length}`:''),n=>{const open=!gopen[g.name];const t=sv('text',{class:'tw',x:8,y:ROW/2+1,role:'button','aria-label':(open?'Collapse ':'Expand ')+g.name},open?'▾':'▸');t.addEventListener('click',e=>{e.stopPropagation();if(open)gopen[g.name]=true;else delete gopen[g.name];save();draw()});n.append(t)}));
 skills.forEach(({g,k})=>node('s:'+g.name+':'+k.name,'skill'+(k.slash_only?' slash':''),pos['s:'+g.name+':'+k.name],k.name,k.slash_only?'slash':''));
 nodes.append(nfrag);applyView();highlight();window.__lastDraw=performance.now()-t0}
async function toggleFolder(f){if(f.isOpen)delete fopen[f.path];else fopen[f.path]=true;save();await fetchTree(false);draw()}
function selId(){return SELKIND==='folder'?'f:'+(SEL||ROOT.path):SELKIND==='group'?'g:'+SEL:SELKIND==='skill'?'s:'+SEL:''}
// Focus is client-side: the context folder changes only when a folder is picked, and only then is
// state refetched (it depends on the folder). Opening a closed group re-lays out without the network.
async function select(id){const[kind,...rest]=id.split(':');const key=rest.join(':');let relayout=false;const prevCtx=CTX;
 if(kind==='f'){SELKIND='folder';SEL=key===ROOT.path?'':key;CTX=SEL}else if(kind==='g'){SELKIND='group';SEL=key;if(gopen[key]){delete gopen[key];relayout=true}}else{SELKIND='skill';SEL=key;const g=key.split(':')[0];if(gopen[g]){delete gopen[g];relayout=true}}
 save();const cur=selId();NODES.forEach((n,nid)=>n.classList.toggle('sel',nid===cur));
 if(relayout)draw();else highlight();
 if(CTX!==prevCtx){await fetchState();draw()}side()}
function litSet(id){const lit=new Set([id]);const kind=id[0];
 if(kind==='f'){const f=FOLDERS.find(x=>'f:'+x.path===id);if(f){GN.forEach(g=>{if(f.on[g])lit.add('g:'+g)});for(const g of S.groups)if(f.on[g.name])g.skills.forEach(k=>{if(!k.slash_only)lit.add('s:'+g.name+':'+k.name)});if(!f.isRoot&&!(f.has_local||f.has_project))lit.add('f:'+ROOT.path)}}
 else if(kind==='g'){const gname=id.slice(2);FOLDERS.forEach(f=>{if(f.on[gname])lit.add('f:'+f.path)});const g=S.groups.find(x=>x.name===gname);g&&g.skills.forEach(k=>lit.add('s:'+gname+':'+k.name))}
 else{const [gname]=id.slice(2).split(':');lit.add('g:'+gname);FOLDERS.forEach(f=>{if(f.on[gname])lit.add('f:'+f.path)})}
 return lit}
function highlight(){const svg=$('#svg');const id=selId();if(!id){svg.classList.remove('dim');NODES.forEach(n=>n.classList.remove('lit'));EDGES.forEach(e=>e.el.classList.remove('lit'));return}
 const lit=litSet(id);svg.classList.add('dim');NODES.forEach((n,nid)=>n.classList.toggle('lit',lit.has(nid)));EDGES.forEach(e=>e.el.classList.toggle('lit',lit.has(e.a)&&lit.has(e.b)))}
function hover(id,on){const adj=ADJ.get(id);if(!adj)return;for(const e of adj)e.el.classList.toggle('hov',on)}
// Keyboard: up/down walk a lane by position, left/right jump to the nearest node in the next lane.
function nodeKeys(e){const id=e.currentTarget.dataset.id;if(e.key==='Enter'||e.key===' '){e.preventDefault();select(id);return}
 const dir={ArrowUp:[0,-1],ArrowDown:[0,1],ArrowLeft:[-1,0],ArrowRight:[1,0]}[e.key];if(!dir)return;e.preventDefault();
 const p=POS[id];if(!p)return;let best=null,bd=Infinity;
 for(const[nid,q]of Object.entries(POS)){if(nid===id)continue;if(dir[0]){if(q.lane!==p.lane+dir[0])continue;const d=Math.abs(q.y-p.y);if(d<bd){bd=d;best=nid}}else{if(q.lane!==p.lane)continue;const dy=(q.y-p.y)*dir[1];if(dy>0&&dy<bd){bd=dy;best=nid}}}
 if(best)NODES.get(best)?.focus()}
// ── pan / zoom (one transform write per frame) ──
let viewDirty=false;function applyView(){if(viewDirty)return;viewDirty=true;requestAnimationFrame(()=>{viewDirty=false;$('#view').setAttribute('transform',`translate(${view.x},${view.y}) scale(${view.k})`)})}
(()=>{const c=$('#canvas');let drag=null;c.addEventListener('pointerdown',e=>{if(e.target.closest('.node,.fab'))return;drag={x:e.clientX-view.x,y:e.clientY-view.y};c.classList.add('drag');c.setPointerCapture(e.pointerId)});
 c.addEventListener('pointermove',e=>{if(!drag)return;view.x=e.clientX-drag.x;view.y=e.clientY-drag.y;applyView()});
 const end=()=>{drag=null;c.classList.remove('drag')};c.addEventListener('pointerup',end);c.addEventListener('pointercancel',end);
 c.addEventListener('wheel',e=>{e.preventDefault();const r=c.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;const dy=e.deltaMode===1?e.deltaY*16:e.deltaMode===2?e.deltaY*r.height:e.deltaY;const k=Math.min(3,Math.max(.3,view.k*Math.exp(-dy*(e.ctrlKey?.01:.0025))));view.x=mx-(mx-view.x)*k/view.k;view.y=my-(my-view.y)*k/view.k;view.k=k;applyView()},{passive:false});
 $('#fit').addEventListener('click',fit)})();
function fit(){const b=$('#view').getBBox(),c=$('#canvas').getBoundingClientRect();const k=Math.min(1.25,(c.width-32)/b.width,(c.height-32)/b.height);view={k,x:16-b.x*k,y:16-b.y*k};applyView()}
// ── detail pane ──
function sw(on,name,cb,labels=['on','off']){return el('button',{class:'sw',role:'switch','aria-checked':String(on),'aria-label':name,onclick:()=>cb(!on)},el('i'),el('span',{class:'lab'},on?labels[0]:labels[1]))}
function tri(cur,scope,cb){const t=el('span',{class:'tri',role:'group','aria-label':scope+' scope'});for(const[lab,val,name]of[['on',true,'on'],['–',null,'not set'],['off',false,'off']])t.append(el('button',{'aria-label':name,'aria-pressed':String(cur===val),onclick:()=>cb(val)},lab));return t}
let scopeTouched=false;
function side(){const a=$('#side');a.replaceChildren();const noProj=!S.project;for(const o of $('#scope').options)o.disabled=o.value!=='user'&&noProj;if(noProj)$('#scope').value='user';else if(!scopeTouched&&$('#scope').value==='user')$('#scope').value='local';
 const link=(id,text,cls='')=>el('button',{class:'link '+cls,onclick:()=>select(id)},text);
 const ctxName=CTX?CTX.split('/').pop():'user scope';
 if(SELKIND===''||SELKIND==='folder'){const f=FOLDERS.find(x=>x.path===(CTX||ROOT.path))||ROOT;const onG=S.groups.filter(g=>g.enabled).length;
  a.append(el('p',{class:'title'},el('span',{class:'mono'},f.isRoot?'~/dev':f.path.slice(S.dev_root.length+1)),el('span',{class:'k'},f.isRoot?'user scope, what every folder inherits':(f.has_local?'has its own settings on this machine':f.has_project?'has its own committed settings':'inherits user scope'))));
  a.append(el('p',{class:'lead'},`A session started here gets ${onG} of ${S.groups.length} groups, about ${fmt(S.always_on)} tokens of skill descriptions.`));
  a.append(el('h2',{},'Groups'));const ul=el('ul',{class:'list'});
  for(const g of S.groups){const li=el('li',{},el('span',{class:'name'},link('g:'+g.name,g.name,'mono'),' ',el('span',{class:'k'},`${g.skills.length} skills`+(g.enabled_by!=='default'&&g.enabled_by!=='user'?`, set at ${g.enabled_by}`:''))),
   sw(g.enabled,`${g.name} group here`,v=>act('/api/group',{id:g.id,scope:scope(),value:v,project:S.project},`${g.name}: ${v?'on':'off'} at ${scope()} scope`)));
   if(DET){const d=el('div',{class:'details'},el('div',{},g.description),el('div',{class:'sc'},el('span',{},`~${fmt(g.tokens)} tokens`)));const sc=el('div',{class:'sc'});for(const s of ['user','project','local'])if(s==='user'||!noProj)sc.append(el('span',{},s),tri(g.scopes[s],s,v=>act('/api/group',{id:g.id,scope:s,value:v,project:S.project},`${g.name}: ${s} scope ${v===null?'cleared':v?'on':'off'}`)));d.append(sc);li.append(d);li.style.gridTemplateColumns='minmax(0,1fr) auto';d.style.gridColumn='1/3'}
   ul.append(li)}a.append(ul);
  a.append(el('h2',{},'Flat skills'));const fl=el('ul',{class:'list'});
  for(const k of S.flat){const on=k.state==='on';fl.append(el('li',{},el('span',{class:'name'},el('span',{class:'mono',title:k.description},k.name),' ',el('span',{class:'k'},on?'':k.state==='off'?'off':k.state==='name-only'?'name only':'slash-only')),
   sw(on,k.name,v=>act('/api/override',{name:k.name,scope:scope(),value:v?'on':'off',project:S.project},`${k.name}: ${v?'on':'off'} at ${scope()} scope`))))}a.append(fl)}
 else if(SELKIND==='group'){const g=S.groups.find(x=>x.name===SEL);if(!g)return;const where=FOLDERS.filter(f=>f.on[g.name]&&!f.isRoot);
  a.append(el('p',{class:'title'},el('span',{class:'mono'},g.name),el('span',{class:'k'},g.description)));
  a.append(el('p',{class:'lead'},`${g.skills.length} skills, ~${fmt(g.tokens)} tokens of descriptions when on.`));
  const inl=el('ul',{class:'list'});inl.append(el('li',{},el('span',{class:'name'},'In ',el('span',{class:'mono'},ctxName)),sw(g.enabled,`${g.name} in ${ctxName}`,v=>act('/api/group',{id:g.id,scope:scope(),value:v,project:S.project},`${g.name}: ${v?'on':'off'} at ${scope()} scope`))));a.append(inl);
  a.append(el('h2',{},'Skills'));const ul=el('ul',{class:'list'});for(const k of g.skills)ul.append(el('li',{},el('span',{class:'name'},link('s:'+g.name+':'+k.name,k.name,'mono'),k.has_override?el('span',{class:'k'},' edited'):''),sw(!k.slash_only,`${k.name} invocable by Claude`,v=>act('/api/skill',{dir:k.dir,slash_only:!v},`${k.name}: ${v?'auto':'slash-only'}`),['auto','slash'])));a.append(ul);
  a.append(el('h2',{},'Folders with their own setting'));const fl=el('ul',{class:'list'});const own=FOLDERS.filter(f=>!f.isRoot&&!!f.on[g.name]!==!!ROOT.on[g.name]);
  if(!own.length)fl.append(el('li',{},el('span',{class:'k'},'none; every folder follows user scope')));for(const f of own)fl.append(el('li',{},el('span',{class:'name'},link('f:'+f.path,f.name,'mono')),el('span',{class:'k'},f.on[g.name]?'on':'off')));a.append(fl)}
 else{const [gname,kname]=SEL.split(':');const g=S.groups.find(x=>x.name===gname);const k=g&&g.skills.find(x=>x.name===kname);if(!k)return;
  a.append(el('p',{class:'title'},el('span',{class:'mono'},'/'+gname+':'+kname),el('span',{class:'k'},k.description)));
  a.append(el('p',{class:'lead'},`~${fmt(k.tokens)} tokens of description when auto. In group `,link('g:'+gname,gname,'mono'),'.'));
  const ul=el('ul',{class:'list'});ul.append(el('li',{},el('span',{class:'name'},'Claude may invoke it'),sw(!k.slash_only,`${k.name} invocable by Claude`,v=>act('/api/skill',{dir:k.dir,slash_only:!v},`${k.name}: ${v?'auto':'slash-only'}`),['auto','slash'])));a.append(ul);
  if(k.has_override)a.append(el('p',{class:'hint'},'Carries a local override in agents-shared.'))}
 a.append(el('p',{class:'hint'},'Click a node to focus it; drag to pan, wheel to zoom. Switches write at the scope chosen at the top. “This repo, this machine” is the repository’s gitignored ',el('code',{},'.claude/settings.local.json'),' and is the usual choice; “this folder, committed” is that folder’s ',el('code',{},'.claude/settings.json'),' for anything the repository’s other readers should share. Local beats project beats user. A skill switch is global: on lets Claude invoke it, off keeps it slash-only.'))}
$('#scope').addEventListener('change',()=>{scopeTouched=true;side()});
$('#details').addEventListener('click',e=>{DET=!DET;e.currentTarget.setAttribute('aria-pressed',DET);e.currentTarget.textContent=DET?'Hide details':'Show details';side()});
$('#clear').addEventListener('click',async()=>{SEL='';SELKIND='';CTX='';save();await fetchState();draw();side()});
$('#q').addEventListener('input',e=>{const q=e.target.value.trim().toLowerCase();const svg=$('#svg');if(!q){highlight();return}svg.classList.add('dim');NODES.forEach((n,id)=>n.classList.toggle('lit',id.toLowerCase().includes(q)));EDGES.forEach(x=>x.el.classList.remove('lit'))});
document.addEventListener('keydown',e=>{if(e.key==='/'&&document.activeElement!==$('#q')){e.preventDefault();$('#q').focus()}if(e.key==='Escape'&&document.activeElement!==$('#q')){SEL='';SELKIND='';save();NODES.forEach(n=>n.classList.remove('sel'));highlight();side()}});
let first=true;const _draw=draw;draw=function(){_draw();if(first){first=false;fit()}};
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
                opened = json.loads(unquote(q.get("open", "") or "[]"))
                return self._json(dirs(self._project(raw), set(map(str, opened))))
            except (ValueError, TypeError) as e:
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
