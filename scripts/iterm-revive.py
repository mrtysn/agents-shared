#!/usr/bin/env python3
"""Triage Claude Code sessions across open iTerm2 tabs.

Classifies every tab into:
  live       — a claude process is attached to the tab's tty
  ended      — dead shell, session UUID in restored text, transcript untouched
               since iTerm2 last started (killed by the relaunch)
  moved-on   — session ended but the tab was used for other work afterwards
  unresolved — tab name says claude ran here, but no UUID is visible on screen

Modes:
  (none) | table   human-readable triage table
  resume           copy-pasteable `cd <cwd> && claude --resume <uuid>` one-liners
  json             full machine-readable dump (consumed by the skill's
                   summarize / handoff modes)
"""

import datetime
import glob
import json
import os
import re
import subprocess
import sys

from claude_dirs import DEFAULT_CONFIG_DIR, UUID_RE, config_dirs
# tab-name prefixes that only a claude statusline sets
CLAUDE_NAME_RE = re.compile(r"(: done|: ready|needs approval|✳|●)")
# commands that precede launching claude rather than indicating new work
PRE_LAUNCH_CMDS = ("claude", "cadc", "bm", "at ")

DUMP_SCRIPT = """
tell application "iTerm2"
    set out to ""
    set wIdx to 0
    repeat with w in windows
        set wIdx to wIdx + 1
        set tIdx to 0
        repeat with t in tabs of w
            set tIdx to tIdx + 1
            repeat with s in sessions of t
                set out to out & "===TAB=== w" & wIdx & ".t" & tIdx & " tty=" & (tty of s) & " name=" & (name of s) & linefeed
                try
                    set out to out & (contents of s) & linefeed
                end try
            end repeat
        end repeat
    end repeat
    return out
end tell
"""


def iterm_start_time():
    ps = subprocess.run(["ps", "-axo", "pid=,lstart=,comm="], capture_output=True, text=True).stdout
    for line in ps.splitlines():
        if line.rstrip().endswith("/iTerm2"):
            fields = line.split()
            return datetime.datetime.strptime(" ".join(fields[1:6]), "%a %b %d %H:%M:%S %Y").timestamp()
    return None


def live_claude_ttys():
    """tty -> {pid, argv} for every running claude process."""
    ps = subprocess.run(["ps", "-axo", "pid=,tty=,command="], capture_output=True, text=True).stdout
    ttys = {}
    for line in ps.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and (parts[2] == "claude" or parts[2].startswith("claude ")):
            ttys[parts[1]] = {"pid": parts[0], "argv": parts[2]}
    return ttys


def process_cwd(pid):
    out = subprocess.run(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.startswith("n"):
            return line[1:]
    return None


def dump_tabs():
    res = subprocess.run(["osascript", "-e", DUMP_SCRIPT], capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"osascript failed (is iTerm2 running?): {res.stderr.strip()}")
    tabs, cur = [], None
    for line in res.stdout.splitlines():
        if line.startswith("===TAB==="):
            m = re.match(r"===TAB=== (\S+) tty=(\S+) name=(.*)", line)
            cur = {"tab": m.group(1), "tty": m.group(2).replace("/dev/", ""), "name": m.group(3).strip(), "lines": []}
            tabs.append(cur)
        elif cur is not None:
            cur["lines"].append(line)
    for t in tabs:
        t["text"] = "\n".join(t.pop("lines"))
    return tabs


def index_transcripts():
    """uuid -> {path, mtime, config}; cwd/branch/version read lazily."""
    idx = {}
    for cfg in config_dirs():
        for p in glob.glob(f"{cfg}/projects/*/*.jsonl"):
            idx[os.path.basename(p)[:-6]] = {"path": p, "mtime": os.path.getmtime(p), "config": cfg}
    return idx


def transcript_meta(path):
    """First entry carrying cwd/version/gitBranch."""
    try:
        with open(path, errors="replace") as f:
            for line in f:
                if '"cwd"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("cwd"):
                    return {"cwd": d["cwd"], "branch": d.get("gitBranch"), "version": d.get("version")}
    except OSError:
        pass
    return {"cwd": None, "branch": None, "version": None}


def age(mtime):
    d = datetime.datetime.now() - datetime.datetime.fromtimestamp(mtime)
    return f"{d.days}d{d.seconds // 3600}h" if d.days else f"{d.seconds // 3600}h{d.seconds % 3600 // 60}m"


def classify():
    started = iterm_start_time()
    if started is None:
        sys.exit("iTerm2 is not running.")
    ttys = live_claude_ttys()
    transcripts = index_transcripts()
    tabs = dump_tabs()

    out = {"iterm_started": started, "live": [], "ended": [], "moved_on": [], "unresolved": []}
    claimed = set()
    pending = []  # live tabs with no argv/on-screen UUID; resolved after all claims are in
    for t in tabs:
        # dedupe keeping LAST occurrence order, so uuids[-1] is the uuid lowest
        # on the screen — the statusline of whatever ran most recently, not a
        # stray uuid printed mid-scrollback (e.g. by this very skill's output)
        matches = [u for u in UUID_RE.findall(t["text"]) if u in transcripts]
        uuids = list(dict.fromkeys(reversed(matches)))[::-1]
        entry = {"tab": t["tab"], "tty": t["tty"], "name": t["name"]}

        if t["tty"] in ttys:
            proc = ttys[t["tty"]]
            m = UUID_RE.search(proc["argv"])
            sid = m.group(0) if m else (uuids[-1] if uuids else None)
            entry["session"] = sid
            if sid:
                claimed.add(sid)
                entry.update(transcript_meta(transcripts[sid]["path"]))
                entry["last_active"] = transcripts[sid]["mtime"]
                entry["transcript"] = transcripts[sid]["path"]
                entry["config"] = transcripts[sid]["config"]
            else:
                pending.append((entry, proc["pid"]))
            out["live"].append(entry)
            continue

        if uuids:
            sid = uuids[-1]
            # claim every uuid in this dead tab's text, not just the last: the
            # earlier ones are this tab's session ancestry and must not be
            # handed to another tab by the inference pass
            claimed.update(uuids)
            info = transcripts[sid]
            entry["session"] = sid
            entry.update(transcript_meta(info["path"]))
            entry["last_active"] = info["mtime"]
            entry["transcript"] = info["path"]
            entry["config"] = info["config"]
            # commands typed after the last claude block mean the tab moved on
            tail = t["text"][t["text"].rfind(sid):]
            cmds = [c for c in re.findall(r"^\s*[>❯]\s+(\S.*)$", tail, re.M) if not c.startswith(PRE_LAUNCH_CMDS)]
            if info["mtime"] > started or cmds:
                entry["reason"] = "exited after restart" if info["mtime"] > started else f"commands after exit: {cmds[:2]}"
                out["moved_on"].append(entry)
            else:
                out["ended"].append(entry)
        elif CLAUDE_NAME_RE.search(t["name"]):
            # dead shell, claude-flavored tab name, UUID scrolled off screen
            out["unresolved"].append(entry)

    # fallback pass, after every tab's direct claim is registered: freshest
    # transcript still being written in the process's actual cwd (per lsof),
    # excluding transcripts already owned by another tab. Stays "?" on no match.
    for entry, pid in pending:
        cwd = process_cwd(pid)
        if not cwd:
            continue
        cand = [(v["mtime"], u) for u, v in transcripts.items()
                if v["mtime"] > started and u not in claimed]
        for _, u in sorted(cand, reverse=True):
            meta = transcript_meta(transcripts[u]["path"])
            if meta["cwd"] == cwd:
                claimed.add(u)
                entry["session"] = u
                entry.update(meta)
                entry["last_active"] = transcripts[u]["mtime"]
                entry["transcript"] = transcripts[u]["path"]
                entry["config"] = transcripts[u]["config"]
                break

    # inference pass: a dead tab titled "<project>: ..." whose uuid scrolled off
    # can still be resolved if exactly one unclaimed transcript in that project
    # was active shortly before the restart killed it. Zero or several
    # candidates stay unresolved — with no screen evidence, uniqueness is the
    # only safe assignment.
    infer_floor = started - 30 * 60
    for entry in list(out["unresolved"]):
        m = re.match(r"[^\w.-]*([\w.-]+):", entry["name"])
        if not m:
            continue
        project = m.group(1)
        cands = []
        for u, v in transcripts.items():
            if not infer_floor <= v["mtime"] < started or u in claimed:
                continue
            if not os.path.dirname(v["path"]).endswith(f"-{project}"):
                continue
            meta = transcript_meta(v["path"])
            if meta["cwd"] and os.path.basename(meta["cwd"]) == project:
                cands.append((u, meta))
        if len(cands) == 1:
            u, meta = cands[0]
            claimed.add(u)
            entry["session"] = u
            entry.update(meta)
            entry["last_active"] = transcripts[u]["mtime"]
            entry["transcript"] = transcripts[u]["path"]
            entry["config"] = transcripts[u]["config"]
            entry["inferred"] = True
            out["unresolved"].remove(entry)
            out["ended"].append(entry)
    return out


def print_table(data):
    print(f"iTerm2 up since {datetime.datetime.fromtimestamp(data['iterm_started']):%b %d %H:%M}\n")
    for state, rows in (("LIVE", data["live"]), ("ENDED BY RESTART", data["ended"]),
                        ("MOVED ON (skipped)", data["moved_on"]), ("UNRESOLVED", data["unresolved"])):
        print(f"{state} ({len(rows)})")
        for r in rows:
            sid = r.get("session") or "?"
            extra = f"  idle {age(r['last_active'])}" if r.get("last_active") else ""
            cfg = r.get("config")
            if cfg and cfg != DEFAULT_CONFIG_DIR:
                extra += f"  ({os.path.basename(cfg)})"
            if r.get("inferred"):
                extra += "  (inferred)"
            cwd = r.get("cwd") or ""
            print(f"  {r['tab']:<7} {sid:<36} {cwd}{extra}  [{r['name']}]")
        print()
    if data["unresolved"]:
        print("unresolved: claude ran here but its UUID scrolled off the visible screen —")
        print("cross-check with /recent-sessions, or scroll the tab and re-run.")


def print_resume(data):
    if not data["ended"]:
        print("No ended sessions to resume.")
        return
    for r in data["ended"]:
        if not r.get("cwd"):
            print(f"# {r['tab']} {r['session']}: no cwd recorded in transcript")
        elif not os.path.isdir(r["cwd"]):
            print(f"# {r['tab']} {r['session']}: cwd {r['cwd']} no longer exists")
        else:
            cfg = r.get("config", DEFAULT_CONFIG_DIR)
            env = f"CLAUDE_CONFIG_DIR={cfg} " if cfg != DEFAULT_CONFIG_DIR else ""
            print(f"cd {r['cwd']} && {env}claude --resume {r['session']}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "table"
    data = classify()
    if mode == "json":
        print(json.dumps(data, indent=1))
    elif mode == "resume":
        print_resume(data)
    else:
        print_table(data)
