#!/usr/bin/env python3
# DESC: Build a browsable local HTML catalog of upstream skills we have not copied, with a vendor/ignore/later choice per skill
"""
Build a self-contained HTML page listing every SKILL.md in the upstream repos we vendor
from that no source.json vendors and scripts/external-skills-ignore.txt does not cover,
each with its own description, so a person can decide per skill: copy it (vendor), ignore
it, or leave it for later. The page exports the choices as lines to hand back:

    vendor <owner/repo> <path-to-SKILL.md>
    ignore <owner/repo> <path-to-SKILL.md>

Ignored lines go into scripts/external-skills-ignore.txt, which makes both this catalog and
sync-external-skills.sh silent about them.

Network use: one blobless clone per upstream repo, then ONE batched fetch of that repo's
SKILL.md blobs (sparse checkout), paced by --delay seconds. The first failed git command
stops all further contact with GitHub.

Usage:
    scripts/catalog-unvendored-skills.py [--out /absolute/catalog.html] [--json /absolute/data.json] [--delay 2]

--json writes {"generated": <iso time>, "items": [{repo, path, name, desc}, ...]}, which the Upstream
view in Skill Tree reads. At least one of --out and --json is required.
"""
import argparse
import fnmatch
import glob
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SKILLS = os.path.join(ROOT, "claude", "skills")
IGNORE_FILE = os.path.join(ROOT, "scripts", "external-skills-ignore.txt")


def source_files():
    pats = ["*/source.json", "*/skills/*/source.json", "*/off/*/source.json"]
    out = []
    for p in pats:
        out += glob.glob(os.path.join(SKILLS, p))
    return sorted(out)


def read_ignores():
    rules = []
    if os.path.isfile(IGNORE_FILE):
        for line in open(IGNORE_FILE, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                rules.append((parts[0], parts[1]))
    return rules


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("%s -> %s" % (" ".join(cmd), r.stderr.strip()[:300]))
    return r.stdout


def parse_frontmatter(text):
    """Minimal reader for the `name:` and `description:` keys (plain, quoted, or block scalar)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)", text, re.S)
    if not m:
        return {}
    lines = m.group(1).split("\n")
    out, i = {}, 0
    while i < len(lines):
        km = re.match(r"^([A-Za-z_-]+):\s*(.*)$", lines[i])
        if not km:
            i += 1
            continue
        key, val = km.group(1), km.group(2).strip()
        i += 1
        if val in (">", "|", ">-", "|-", ">+", "|+"):
            block = []
            while i < len(lines) and (lines[i].startswith(" ") or lines[i] == ""):
                block.append(lines[i].strip())
                i += 1
            val = " ".join(b for b in block if b)
        else:
            cont = []
            while i < len(lines) and lines[i].startswith(" ") and not re.match(r"^\s*[A-Za-z_-]+:\s", lines[i]):
                cont.append(lines[i].strip())
                i += 1
            if cont:
                val = (val + " " + " ".join(cont)).strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
            val = val[1:-1]
        out[key] = val
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="absolute path of the HTML file to write")
    ap.add_argument("--json", help="absolute path of the JSON data file to write")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between repos")
    args = ap.parse_args()
    if not (args.out or args.json):
        sys.exit("give --out and/or --json")
    for given in (args.out, args.json):
        if given and not os.path.isabs(given):
            sys.exit("%s must be an absolute path" % given)

    vendored, repos = set(), []
    for sf in source_files():
        s = json.load(open(sf, encoding="utf-8"))
        vendored.add((s["repo"], s["path"]))
        if s["repo"] not in repos:
            repos.append(s["repo"])
    ignores = read_ignores()

    items, skipped = [], 0
    work = tempfile.mkdtemp(prefix="catalog-")
    for n, repo in enumerate(repos):
        if n:
            time.sleep(args.delay)
        d = os.path.join(work, repo.replace("/", "__"))
        sys.stderr.write("[%d/%d] %s\n" % (n + 1, len(repos), repo))
        try:
            run(["git", "clone", "-q", "--depth=1", "--filter=blob:none", "--no-checkout",
                 "https://github.com/%s.git" % repo, d])
            tree = run(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=d).split("\n")
            paths = [p for p in tree if re.search(r"(^|/)SKILL\.md$", p)]
            wanted = [p for p in paths if (repo, p) not in vendored
                      and not any(r == repo and fnmatch.fnmatchcase(p, g) for r, g in ignores)]
            if not wanted:
                continue
            run(["git", "sparse-checkout", "set", "--no-cone", "SKILL.md"], cwd=d)
            run(["git", "checkout", "-q"], cwd=d)
        except RuntimeError as e:
            sys.exit("stopping, no further requests: %s" % e)
        for p in wanted:
            fp = os.path.join(d, p)
            try:
                text = open(fp, encoding="utf-8", errors="replace").read()
            except OSError:
                skipped += 1
                continue
            fm = parse_frontmatter(text)
            items.append({
                "repo": repo, "path": p,
                "name": fm.get("name") or os.path.basename(os.path.dirname(p)) or "(root)",
                "desc": fm.get("description", "(no description in frontmatter)"),
            })

    items.sort(key=lambda x: (x["repo"], x["path"]))
    note = " (%d unreadable)" % skipped if skipped else ""
    if args.json:
        tmp = args.json + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "items": items}, f, ensure_ascii=False)
        os.replace(tmp, args.json)
        print("wrote %d skills from %d repos to %s%s" % (len(items), len(repos), args.json, note))
    if args.out:
        data = json.dumps(items).replace("<", "\\u003c")
        page = PAGE.replace("__DATA__", data).replace("__COUNT__", str(len(items)))
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(page)
        print("wrote %d skills from %d repos to %s%s" % (len(items), len(repos), args.out, note))


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Unvendored upstream skills</title>
<style>
:root{--bg:#fafaf8;--fg:#1c1c1a;--mut:#6b6b66;--line:#dcdcd5;--card:#fff;--acc:#2a5bd7;--ok:#1f7a3d;--no:#a33a2a}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--fg:#ecece6;--mut:#9a9a92;--line:#34342f;--card:#1f1f1c;--acc:#7da2ff;--ok:#5fd18a;--no:#ff8a78}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,system-ui,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;z-index:5}
h1{font-size:17px;margin:0 0 6px}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
input[type=search]{flex:1;min-width:200px;padding:7px 10px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg)}
button{padding:6px 11px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer}
button:hover{border-color:var(--acc)}main{padding:12px 16px;max-width:980px;margin:0 auto}
details.repo{margin:12px 0;border:1px solid var(--line);border-radius:8px;background:var(--card)}
summary{padding:10px 12px;cursor:pointer;font-weight:600}summary .n{color:var(--mut);font-weight:400}
.bulk{padding:0 12px 8px;display:flex;gap:8px;flex-wrap:wrap}
.skill{padding:10px 12px;border-top:1px solid var(--line)}.skill h3{margin:0;font-size:15px}
.path{color:var(--mut);font:12px ui-monospace,monospace;word-break:break-all}
.desc{margin:6px 0;white-space:pre-wrap;max-height:4.6em;overflow:hidden;cursor:pointer}.desc.open{max-height:none}
.choice label{margin-right:14px;cursor:pointer}.v{color:var(--ok)}.i{color:var(--no)}
.skill.vendor{border-left:4px solid var(--ok)}.skill.ignore{border-left:4px solid var(--no)}
#out{width:100%;height:160px;font:12px ui-monospace,monospace;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px}
.hide{display:none}
</style></head><body>
<header>
<h1>Unvendored upstream skills <span id="stat" style="color:var(--mut);font-weight:400"></span></h1>
<div class="row">
<input id="q" type="search" placeholder="Search name, path or description">
<label><input type="checkbox" id="undec"> only undecided</label>
<button id="exp">Export my choices</button>
</div>
<div id="exportbox" class="hide" style="margin-top:8px">
<textarea id="out" readonly></textarea>
<div class="row"><button id="copy">Copy to clipboard</button><span style="color:var(--mut)">Paste this back into the Claude session. Choices are also saved in this browser.</span></div>
</div>
</header>
<main id="main"></main>
<script>
const DATA = __DATA__;
const KEY = "unvendored-skills-choices-v1";
let choice = {};
try { choice = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { choice = {}; }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(choice)); } catch (e) {} };
const id = s => s.repo + " " + s.path;
const el = (t, c, x) => { const e = document.createElement(t); if (c) e.className = c; if (x != null) e.textContent = x; return e; };
const main = document.getElementById("main");
const byRepo = {};
DATA.forEach(s => (byRepo[s.repo] = byRepo[s.repo] || []).push(s));
const cards = [];
Object.keys(byRepo).forEach(repo => {
  const det = el("details", "repo"); const sum = el("summary");
  sum.append(repo + " ", el("span", "n", "(" + byRepo[repo].length + " skills)")); det.append(sum);
  const bulk = el("div", "bulk");
  [["Ignore all in this repo", "ignore"], ["Clear this repo", ""]].forEach(([label, val]) => {
    const b = el("button", "", label);
    b.onclick = () => { byRepo[repo].forEach(s => { if (val) choice[id(s)] = val; else delete choice[id(s)]; }); save(); render(); };
    bulk.append(b);
  });
  det.append(bulk);
  byRepo[repo].forEach(s => {
    const c = el("div", "skill"); c.append(el("h3", "", s.name), el("div", "path", s.path));
    const d = el("div", "desc", s.desc); d.title = "click to expand"; d.onclick = () => d.classList.toggle("open"); c.append(d);
    const ch = el("div", "choice");
    [["vendor", "Copy it (vendor)", "v"], ["ignore", "Ignore", "i"], ["", "Decide later", ""]].forEach(([val, label, cls]) => {
      const l = el("label", cls); const r = document.createElement("input"); r.type = "radio"; r.name = id(s); r.value = val;
      r.onchange = () => { if (val) choice[id(s)] = val; else delete choice[id(s)]; save(); render(); };
      l.append(r, " " + label); ch.append(l); s["_r_" + val] = r;
    });
    c.append(ch); det.append(c); cards.push([s, c]);
  });
  main.append(det);
});
function render() {
  const q = document.getElementById("q").value.toLowerCase(), und = document.getElementById("undec").checked;
  let v = 0, i = 0;
  cards.forEach(([s, c]) => {
    const cur = choice[id(s)] || "";
    s["_r_" + cur].checked = true;
    c.className = "skill" + (cur ? " " + cur : "");
    if (cur === "vendor") v++; if (cur === "ignore") i++;
    const hit = !q || (s.name + " " + s.path + " " + s.desc).toLowerCase().includes(q);
    c.classList.toggle("hide", !hit || (und && cur));
  });
  document.getElementById("stat").textContent = "· " + v + " to copy · " + i + " ignored · " + (DATA.length - v - i) + " undecided of " + DATA.length;
}
document.getElementById("q").oninput = render;
document.getElementById("undec").onchange = render;
document.getElementById("exp").onclick = () => {
  const lines = DATA.filter(s => choice[id(s)]).map(s => choice[id(s)] + " " + s.repo + " " + s.path);
  document.getElementById("out").value = lines.join("\n");
  document.getElementById("exportbox").classList.remove("hide");
};
document.getElementById("copy").onclick = () => { const t = document.getElementById("out"); t.select(); try { navigator.clipboard.writeText(t.value); } catch (e) { document.execCommand("copy"); } };
render();
</script></body></html>
"""

if __name__ == "__main__":
    main()
