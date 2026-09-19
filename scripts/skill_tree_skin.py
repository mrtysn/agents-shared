"""The "skills" skin for local-repos-list serve: every Claude Code skill group
and skill, with toggles that write the real settings.

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

This module is a skin for `local-repos-list serve` (see that repo's README for the skin
interface). The base owns the page, the folder lane and the whole canvas (selection, dimming,
keyboard navigation, pan/zoom, side-panel shell); this module supplies the skill-group domain
logic (node_state/actions), and client hooks that add the groups and skills lanes with their
connections, the folder badges, the header scope selector and the side-panel content.

Everything read from disk is memoised on file mtimes: the skill/group collection on the skills
directory tree (every group, skill folder, SKILL.md and source.json), settings files on their own
stat. A folder's badge therefore costs a few stats, and nothing is re-parsed until it changes.
"""

from __future__ import annotations

import copy
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
SKILLS_DIR = CONFIG_DIR / "skills"
SCOPES = ("user", "project", "local")
OVERRIDE_STATES = ("on", "name-only", "user-invocable-only", "off")
LOCAL_OPEN = "<!-- LOCAL: slash-only; set from skill-tree -->"
LOCAL_CLOSE = "<!-- LOCAL END -->"
SKIP_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".git", "dist", "build", ".next", "target"}


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


def git_root(path: Path) -> Path | None:
    """The repository holding `path`, stopping at the dev root's parent."""
    stop = dev_root().parent
    for p in (path, *path.parents):
        if (p / ".git").exists():
            return p
        if p == stop:
            break
    return None


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
        "enabled": skill_dir.parent.name != "off",
    }


def _collect() -> tuple[list[dict], list[dict]]:
    groups, flat = [], []
    for entry in sorted(SKILLS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        manifest = entry / ".claude-plugin" / "plugin.json"
        if manifest.is_file():
            meta = json.loads(manifest.read_text())
            skills = [r for sub in ("skills", "off") if (entry / sub).is_dir()
                      for d in sorted((entry / sub).iterdir()) if d.is_dir()
                      for r in [skill_record(d, entry.name)] if r]
            skills.sort(key=lambda r: r["name"].casefold())
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


def _mtime(path) -> int | None:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def skills_signature() -> tuple:
    """Every mtime `_collect` depends on: the skills directory, each entry (through its
    symlink), each group's manifest and skills/ and off/ folders, and every skill folder with
    its SKILL.md and source.json. Moving a skill, editing its frontmatter or adding an
    override.patch (which changes the skill folder's mtime) all change it."""
    parts: list = [_mtime(SKILLS_DIR)]
    try:
        names = sorted(os.listdir(SKILLS_DIR))
    except OSError:
        return tuple(parts)
    for name in names:
        entry = os.path.join(SKILLS_DIR, name)
        manifest = os.path.join(entry, ".claude-plugin", "plugin.json")
        m = _mtime(manifest)
        parts.append((name, _mtime(entry), m))
        dirs = []
        if m is not None:
            for sub in ("skills", "off"):
                subdir = os.path.join(entry, sub)
                parts.append(_mtime(subdir))
                try:
                    dirs.extend(os.path.join(subdir, d) for d in sorted(os.listdir(subdir)))
                except OSError:
                    pass
        else:
            dirs.append(entry)
        for d in dirs:
            parts.append((d, _mtime(d), _mtime(os.path.join(d, "SKILL.md")),
                          _mtime(os.path.join(d, "source.json"))))
    return tuple(parts)


_memo: dict = {}
SIGNATURE_TTL = 1.0   # seconds one skills_signature() walk is trusted, so a tree request
                      # badging every folder stats the skills tree once, not once per folder


def _skills_sig() -> tuple:
    now = time.monotonic()
    hit = _memo.get("sig")
    if hit and now - hit[0] < SIGNATURE_TTL:
        return hit[1]
    sig = skills_signature()
    _memo["sig"] = (now, sig)
    return sig


def forget() -> None:
    """Drop every memo; mutations call it so their effect never waits on SIGNATURE_TTL."""
    _memo.clear()


def _disk_cache() -> Path:
    """Beside local-repos-list's own scan cache, so a fresh server process starts warm."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return Path(base) / "local-repos-list" / "skills-collect.json"


def _load_or_collect(sig: tuple) -> tuple[list[dict], list[dict]]:
    key = hashlib.sha1(repr((str(SKILLS_DIR), sig)).encode()).hexdigest()
    path = _disk_cache()
    try:
        data = json.loads(path.read_text())
        if data.get("key") == key:
            return data["groups"], data["flat"]
    except (OSError, ValueError, KeyError):
        pass
    groups, flat = _collect()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"key": key, "groups": groups, "flat": flat}))
        os.replace(tmp, path)
    except OSError:
        pass
    return groups, flat


def collect() -> tuple[list[dict], list[dict]]:
    """(groups, flat), recomputed only when the skills signature changes (and persisted, so a
    new process reuses it). Callers get their own copy, since state() annotates the records
    in place."""
    sig = _skills_sig()
    hit = _memo.get("collect")
    if not hit or hit[0] != sig:
        hit = (sig, _load_or_collect(sig))
        _memo["collect"] = hit
    return copy.deepcopy(hit[1])


def _groups_view() -> list[tuple[str, str]]:
    """[(name, id)] of the groups, shared (not copied): the per-folder badge only needs these."""
    sig = _skills_sig()
    hit = _memo.get("collect")
    if not hit or hit[0] != sig:
        collect()
        hit = _memo["collect"]
    return [(g["name"], g["id"]) for g in hit[1][0]]


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


_json_memo: dict = {}


def _read_json_shared(path: Path | None) -> dict:
    """A settings file's parsed content, re-read only when its mtime or size changes. The
    returned dict is shared: read it, never modify it (read_json gives a private copy)."""
    if not path:
        return {}
    try:
        st = os.stat(path)
    except OSError:
        return {}
    key = (st.st_mtime_ns, st.st_size)
    hit = _json_memo.get(str(path))
    if hit and hit[0] == key:
        return hit[1]
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    _json_memo[str(path)] = (key, data)
    return data


def read_json(path: Path | None) -> dict:
    return copy.deepcopy(_read_json_shared(path))


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
        eff, src = True, "default"
        for s in ("user", "project", "local"):
            if g["scopes"][s] is not None:
                eff, src = bool(g["scopes"][s]), s
        g["enabled"], g["enabled_by"] = eff, src
        g["tokens"] = sum(k["tokens"] for k in g["skills"] if k["enabled"] and not k["slash_only"])
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


def _folder_state(path: Path) -> dict:
    """Effective on/off per group for `path`, from user + its own project file + its repo's
    local file — the badge payload for the base's folder lane. Only stats when nothing changed."""
    user = _read_json_shared(CONFIG_DIR / "settings.json").get("enabledPlugins", {})
    proj_file = path / ".claude" / "settings.json"
    proj = _read_json_shared(proj_file).get("enabledPlugins", {})
    root = git_root(path)
    loc = _read_json_shared((root or path) / ".claude" / "settings.local.json").get("enabledPlugins", {})
    on = {}
    for name, gid in _groups_view():
        v = user.get(gid)
        v = proj.get(gid, v)
        v = loc.get(gid, v)
        on[name] = True if v is None else bool(v)
    return {
        "on": on,
        "has_project": proj_file.is_file(),
        "has_local": root is not None and (root / ".claude" / "settings.local.json").is_file() and bool(loc),
    }


def node_state(path: Path) -> dict:
    try:
        return _folder_state(path)
    except OSError:
        return {}


def signature() -> str:
    """Changes when the skills or the user settings change, so an open page redraws after a
    switch flipped elsewhere (the CLI, another tab)."""
    user = CONFIG_DIR / "settings.json"
    raw = repr((skills_signature(), _mtime(user)))
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


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
        return {"ok": False, "error": "claude CLI not found; start local-repos-list from a shell that has it"}
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


def set_enabled(skill_dir: Path, enabled: bool) -> dict:
    """A skill in a group is on when its folder sits in <group>/skills/ and off when it sits in
    <group>/off/, which no session scans. Nothing inside the folder changes, so auto/slash-only,
    provenance and any local override travel with it. In git the move is a rename."""
    if skill_dir.parent.name not in ("skills", "off"):
        return {"ok": False, "error": "only a skill inside a group can be switched off; a flat skill uses its visibility states"}
    group = skill_dir.parent.parent
    dest = group / ("skills" if enabled else "off") / skill_dir.name
    if dest == skill_dir:
        return {"ok": True}
    if dest.exists():
        return {"ok": False, "error": f"{dest.parent.name}/{dest.name} already exists"}
    dest.parent.mkdir(exist_ok=True)
    skill_dir.rename(dest)
    return {"ok": True, "dir": str(dest)}


def regen_override_patch(skill_dir: Path) -> None:
    """Same output as sync-external-skills.sh's regen_patch: diff(.upstream -> working) for the
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


def _known_skill_dirs() -> set[str]:
    groups, flat = collect()
    return {k["dir"] for g in groups for k in g["skills"]} | {k["dir"] for k in flat}


# ── actions (what the client_js calls through LRL.api) ──────────────────────

def _under_dev_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(dev_root().resolve())
        return True
    except ValueError:
        return path.resolve() == dev_root().resolve()


def _project(raw: str | None) -> Path | None:
    """Validate a project path from a request payload: it must exist and sit
    under the dev root, same guard the original skill-tree.py applied."""
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_dir() or not _under_dev_root(p):
        raise ValueError("folder must be under the dev root")
    return p


def action_state(payload: dict) -> dict:
    return state(_project(payload.get("project")))


def action_group(payload: dict) -> dict:
    return set_group(payload["id"], payload["scope"], payload.get("value"),
                      _project(payload.get("project")))


def action_override(payload: dict) -> dict:
    return set_override(payload["name"], payload["scope"], payload.get("value"),
                         _project(payload.get("project")))


def action_skill(payload: dict) -> dict:
    if payload.get("dir") not in _known_skill_dirs():
        return {"ok": False, "error": "not a listed skill"}
    try:
        return set_slash_only(Path(payload["dir"]), bool(payload.get("slash_only")))
    finally:
        forget()


def action_skill_enable(payload: dict) -> dict:
    if payload.get("dir") not in _known_skill_dirs():
        return {"ok": False, "error": "not a listed skill"}
    try:
        return set_enabled(Path(payload["dir"]), bool(payload.get("enabled")))
    finally:
        forget()




# ── front end ────────────────────────────────────────────────────────────────
# Hooks on local-repos-list's shared tree view (window.LRL). The base draws the folder lane
# (each folder's node_state arrives as f.state = {on, has_project, has_local}) and owns the
# canvas; this adds the groups and skills lanes and their connections, the folder badges,
# what a selection lights, the scope selector's behaviour and the side-panel content.

CSS = r"""
.node.group rect{stroke:var(--on);stroke-width:1.2}.node.group.off rect{stroke:var(--off);stroke-dasharray:3 2}
.node.skill rect{rx:10}.node.skill.slash rect{stroke-dasharray:3 2}.node.skill.off rect{stroke:var(--off);fill:none}.node.skill.off text{text-decoration:line-through;fill:var(--ink2)}
table.skills{border-collapse:collapse;width:100%;table-layout:fixed}table.skills th{text-align:left;font-weight:600;font-size:11px;color:var(--ink2);padding:2px 4px 4px;border-bottom:1px solid var(--line);letter-spacing:.01em}table.skills th:not(:first-child){width:5.2em}table.skills td{padding:1px 4px;vertical-align:middle;height:28px}table.skills td.name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}table.skills td.name button.link{text-decoration:none;text-overflow:ellipsis;overflow:hidden;white-space:nowrap;max-width:100%;display:block}table.skills .sw{padding:2px 0;gap:4px}table.skills .sw .lab{min-width:2.6em}
.details{color:var(--ink2);font-size:12px;display:grid;gap:4px;margin-top:4px}.details .sc{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
"""

CONTROLS = r"""<label>Write to <select id="scope" aria-label="Scope that switches write to"><option value="user">user scope, every folder</option><option value="local">this repo, this machine</option><option value="project">this folder, committed</option></select></label>"""

HELP = r"""
 <h3>The canvas</h3>
 <p>Folders on the left, groups in the middle, skills on the right. Click a node to focus it: its connections stay lit, the rest dims. Click it again, press Escape or use Clear selection to unfocus. Drag to pan, wheel to zoom, Fit to see everything. Arrow keys move between nodes.</p>
 <p>A solid line means a folder has its own setting for that group. A folder without lines inherits user scope; focus it and dashed lines show what it gets.</p>
 <h3>Where switches write</h3>
 <p>The “Write to” selector picks the file a group switch edits. <b>User scope</b> is <code>~/.claude/settings.json</code>, the default for every folder. <b>This repo, this machine</b> is the repository’s gitignored <code>.claude/settings.local.json</code>, the usual choice for one project. <b>This folder, committed</b> is that folder’s <code>.claude/settings.json</code>, for the rare setting a repository’s other readers should share. Local beats project beats user. A session started in a subfolder reads the committed file from that subfolder, not the repository root.</p>
 <h3>Groups and skills</h3>
 <p>A group is a plugin; Claude Code loads it whole. Off in a folder means none of its skills exist there. A skill inside a group has two global switches. <b>Loaded</b> decides whether any session loads it; off moves its folder to <code>off/</code> inside the group. <b>Claude sees it</b> decides whether its description enters every session, auto, or only when you type its name, slash. Neither switch changes the other.</p>
 <p>Flat skills have a per-scope visibility: on, name only, slash only, off.</p>
 <p>Open sessions pick up changes on <code>/reload-plugins</code>. Nothing here commits; changes to committed files show up in git for you to commit.</p>
"""

CLIENT_JS = r"""
(function(){
const L=window.LRL,{el,sw,tri,link,fmt}=L;const $=(s,r=document)=>r.querySelector(s);
const ROW=L.ROW,XG=560,XS=800,WG=150,WS=190;
let S=null,stateFor=null,DET=false,scopeTouched=false,gopen=L.store.get('gclosed',{});
const saveG=()=>L.store.set('gclosed',gopen);
const GN=()=>S?S.groups.map(g=>g.name):[];
const onOf=f=>(f&&f.state&&f.state.on)||{};
const rootOn=g=>onOf(L.root)[g];
function scope(){return $('#scope').value}
async function act(name,body,done){L.say('');const r=await L.api(name,body);if(!r.ok){L.say(r.error,'err');return}L.say(done);await L.refresh()}
async function load({ctx,force}){if(!force&&stateFor===ctx&&S)return;const r=await L.api('state',{project:ctx||null});if(r.error){L.reset();return load({ctx:'',force:true})}S=r;stateFor=ctx}
function graph(){const gn=GN();const nodes=[],skills=[],edges=[];let gy=30;
 S.groups.forEach(g=>{const open=!gopen[g.name];const n=open?g.skills.length:0;const h=Math.max(1,n)*ROW;
  nodes.push({id:'g:'+g.name,lane:1,x:XG,y:gy+h/2-ROW/2,w:WG,cls:'group'+(g.enabled?'':' off'),label:g.name,sub:(g.enabled?'on':'off')+(gopen[g.name]?` · ${g.skills.length}`:''),
   twisty:{open,onToggle:()=>{if(open)gopen[g.name]=true;else delete gopen[g.name];saveG();L.draw()}}});
  if(open)g.skills.forEach((k,j)=>skills.push({g,k,y:gy+j*ROW}));gy+=h+(open?14:6)});
 L.folders.forEach(f=>{const on=onOf(f);gn.forEach(g=>{const o=!!on[g];if(f.isRoot){if(o)edges.push({a:'f:'+f.path,b:'g:'+g,on:true})}else if(o!==!!rootOn(g))edges.push({a:'f:'+f.path,b:'g:'+g,on:o})})});
 skills.forEach(({g,k})=>edges.push({a:'g:'+g.name,b:'s:'+g.name+':'+k.name,on:g.enabled&&!k.slash_only}));
 skills.forEach(({g,k,y})=>{const on=g.enabled&&k.enabled;nodes.push({id:'s:'+g.name+':'+k.name,lane:2,x:XS,y,w:WS,cls:'skill'+(on?(k.slash_only?' slash':''):' off'),label:k.name,sub:on?(k.slash_only?'slash':''):'off'})});
 return{lanes:[{x:XG,title:'groups'},{x:XS,title:'skills'}],nodes,edges}}
function decorate(f){const gn=GN();const on=onOf(f);const st=f.state||{};const n=gn.filter(g=>on[g]).length;
 const sub=f.isRoot?'user scope':`${(st.has_local||st.has_project)?'⚙ ':''}${n}/${gn.length}`;
 return{sub,title:!f.isRoot&&sub.includes('⚙')?f.name+': '+sub.split(' ').pop()+' groups on; has its own settings, not inherited from user scope':null}}
function lit(id){const l=new Set([id]);const kind=id[0];const F=L.folders;
 if(kind==='f'){const f=F.find(x=>'f:'+x.path===id);if(f){const on=onOf(f);GN().forEach(g=>{if(on[g])l.add('g:'+g)});for(const g of S.groups)if(on[g.name])g.skills.forEach(k=>{if(k.enabled&&!k.slash_only)l.add('s:'+g.name+':'+k.name)})}}
 else if(kind==='g'){const gname=id.slice(2);F.forEach(f=>{if(onOf(f)[gname])l.add('f:'+f.path)});const g=S.groups.find(x=>x.name===gname);g&&g.skills.forEach(k=>l.add('s:'+gname+':'+k.name))}
 else{const[gname]=id.slice(2).split(':');l.add('g:'+gname);F.forEach(f=>{if(onOf(f)[gname])l.add('f:'+f.path)})}
 return l}
// a folder with no edges of its own gets its effective edges drawn while focused, so every folder answers the click
function focusEdges(id){if(id[0]!=='f')return[];const f=L.folders.find(x=>'f:'+x.path===id);if(!f||f.isRoot)return[];const on=onOf(f);
 if(GN().some(g=>!!on[g]!==!!rootOn(g)))return[];return GN().filter(g=>on[g]).map(g=>({a:id,b:'g:'+g,cls:'derived'}))}
// opening a closed group (or a skill's group) re-lays out without the network
function onSelect(id){const[kind,...rest]=id.split(':');const key=rest.join(':');const g=kind==='g'?key:kind==='s'?key.split(':')[0]:null;if(g&&gopen[g]){delete gopen[g];saveG();return true}return false}
function panel(a,sel){const noProj=!S.project;for(const o of $('#scope').options)o.disabled=o.value!=='user'&&noProj;if(noProj)$('#scope').value='user';else if(!scopeTouched&&$('#scope').value==='user')$('#scope').value='local';
 const kind=sel.id?sel.id[0]:'';const SEL=sel.id?sel.id.slice(2):'';const CTX=sel.ctx;
 const ctxName=CTX?CTX.split('/').pop():'user scope';
 if(kind===''||kind==='f'){const f=sel.folder;const onG=S.groups.filter(g=>g.enabled).length;const st=f.state||{};
  a.append(el('p',{class:'title'},el('span',{class:'mono'},f.isRoot?f.name:f.path.slice(L.root.path.length+1)),el('span',{class:'k'},f.isRoot?'user scope, what every folder inherits':(st.has_local?'has its own settings on this machine':st.has_project?'has its own committed settings':'inherits user scope'))));
  a.append(el('p',{class:'lead'},`A session started here gets ${onG} of ${S.groups.length} groups, about ${fmt(S.always_on)} tokens of skill descriptions.`));
  const det=el('button',{class:'link',style:'margin-left:auto;font-size:12px','aria-pressed':String(DET),onclick:()=>{DET=!DET;L.side()}},DET?'Hide scopes and descriptions':'Show scopes and descriptions');
  a.append(el('h2',{style:'display:flex;align-items:baseline;gap:8px'},'Groups',det));const ul=el('ul',{class:'list'});
  for(const g of S.groups){const li=el('li',{},el('span',{class:'name'},link('g:'+g.name,g.name,'mono'),' ',el('span',{class:'k'},`${g.skills.length} skills`+(g.enabled_by!=='default'&&g.enabled_by!=='user'?`, set at ${g.enabled_by}`:''))),
   sw(g.enabled,`${g.name} group here`,v=>act('group',{id:g.id,scope:scope(),value:v,project:S.project},`${g.name}: ${v?'on':'off'} at ${scope()} scope`)));
   if(DET){const d=el('div',{class:'details'},el('div',{},g.description),el('div',{class:'sc'},el('span',{},`~${fmt(g.tokens)} tokens`)));const sc=el('div',{class:'sc'});for(const s of ['user','project','local'])if(s==='user'||!noProj)sc.append(el('span',{},s),tri(g.scopes[s],s,v=>act('group',{id:g.id,scope:s,value:v,project:S.project},`${g.name}: ${s} scope ${v===null?'cleared':v?'on':'off'}`)));d.append(sc);li.append(d);li.style.gridTemplateColumns='minmax(0,1fr) auto';d.style.gridColumn='1/3'}
   ul.append(li)}a.append(ul);
  a.append(el('h2',{},'Flat skills'));const fl=el('ul',{class:'list'});
  for(const k of S.flat){const on=k.state==='on';fl.append(el('li',{},el('span',{class:'name'},el('span',{class:'mono',title:k.description},k.name),' ',el('span',{class:'k'},on?'':k.state==='off'?'off':k.state==='name-only'?'name only':'slash-only')),
   sw(on,k.name,v=>act('override',{name:k.name,scope:scope(),value:v?'on':'off',project:S.project},`${k.name}: ${v?'on':'off'} at ${scope()} scope`))))}a.append(fl)}
 else if(kind==='g'){const g=S.groups.find(x=>x.name===SEL);if(!g)return;
  a.append(el('p',{class:'title'},el('span',{class:'mono'},g.name),el('span',{class:'k'},g.description)));
  a.append(el('p',{class:'lead'},`${g.skills.length} skills, ~${fmt(g.tokens)} tokens of descriptions when on.`));
  const inl=el('ul',{class:'list'});inl.append(el('li',{},el('span',{class:'name'},'In ',el('span',{class:'mono'},ctxName)),sw(g.enabled,`${g.name} in ${ctxName}`,v=>act('group',{id:g.id,scope:scope(),value:v,project:S.project},`${g.name}: ${v?'on':'off'} at ${scope()} scope`))));a.append(inl);
  a.append(el('h2',{},'Skills'));const tb=el('table',{class:'skills'},el('thead',{},el('tr',{},el('th',{scope:'col'},'Skill'),el('th',{scope:'col'},'Loaded'),el('th',{scope:'col'},'Claude sees it'))));const tbody=el('tbody');for(const k of g.skills){tbody.append(el('tr',{},el('td',{class:'name'},link('s:'+g.name+':'+k.name,k.name,'mono'),k.has_override?el('span',{class:'k',title:'Carries a local override'},' ✎'):''),el('td',{},sw(k.enabled,`${k.name} loaded`,v=>act('skill-enable',{dir:k.dir,enabled:v},`${k.name}: ${v?'on':'off'} in every folder`))),el('td',{},sw(!k.slash_only,`${k.name} visible to Claude`,v=>act('skill',{dir:k.dir,slash_only:!v},`${k.name}: ${v?'auto':'slash-only'}`),['auto','slash']))))}tb.append(tbody);a.append(tb);
  a.append(el('h2',{},'Folders with their own setting'));const fl=el('ul',{class:'list'});const own=L.folders.filter(f=>!f.isRoot&&!!onOf(f)[g.name]!==!!rootOn(g.name));
  if(!own.length)fl.append(el('li',{},el('span',{class:'k'},'none; every folder follows user scope')));for(const f of own)fl.append(el('li',{},el('span',{class:'name'},link('f:'+f.path,f.name,'mono')),el('span',{class:'k'},onOf(f)[g.name]?'on':'off')));a.append(fl)}
 else{const[gname,kname]=SEL.split(':');const g=S.groups.find(x=>x.name===gname);const k=g&&g.skills.find(x=>x.name===kname);if(!k)return;
  a.append(el('p',{class:'title'},el('span',{class:'mono'},'/'+gname+':'+kname),el('span',{class:'k'},k.description)));
  const gOn=g.enabled,on=gOn&&k.enabled;a.append(el('p',{class:'lead'},`In ${ctxName}: `,el('b',{},on?(k.slash_only?'slash-only':'auto'):'off'),on?(k.slash_only?', loaded but hidden from Claude; works when you type its name.':`, loaded with its description, ~${fmt(k.tokens)} tokens.`):(!k.enabled?', switched off in every folder.':'')));if(!on&&k.enabled)a.lastChild.append(', because the ',link('g:'+gname,gname,'mono'),' group is off here.');
  const ul=el('ul',{class:'list'});ul.append(el('li',{},el('span',{class:'name'},'On',el('span',{class:'k'},' in every folder')),sw(k.enabled,`${k.name} on`,v=>act('skill-enable',{dir:k.dir,enabled:v},`${k.name}: ${v?'on':'off'} in every folder`))));ul.append(el('li',{},el('span',{class:'name'},'Claude may invoke it',el('span',{class:'k'},' when on')),sw(!k.slash_only,`${k.name} invocable by Claude`,v=>act('skill',{dir:k.dir,slash_only:!v},`${k.name}: ${v?'auto':'slash-only'}`),['auto','slash'])));a.append(ul);
  if(k.has_override)a.append(el('p',{class:'hint'},'Carries a local override in agents-shared.'))}
}
L.register({
 findLabel:'Find a folder, group or skill',canvasLabel:'Folders, groups and skills',
 init(){$('#scope').addEventListener('change',()=>{scopeTouched=true;L.side()})},
 load,graph,decorate,lit,focusEdges,onSelect,panel,
});
})();
"""

SKIN = {
    "id": "skills",
    "title": "Skills",
    "heading": "Skill Tree",
    "folders": "all",
    "node_state": node_state,
    "signature": signature,
    "actions": {
        "state": action_state,
        "group": action_group,
        "override": action_override,
        "skill": action_skill,
        "skill-enable": action_skill_enable,
    },
    "css": CSS,
    "controls": CONTROLS,
    "help": HELP,
    "client_js": CLIENT_JS,
}
