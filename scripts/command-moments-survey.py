#!/usr/bin/env python3
"""command-moments-survey: when does the user type a given slash command, and
could a Stop-time classifier predict that moment?

Companion to usage-survey.py, built for the same system-one shadow-mode
evaluation (see notebook/2026-09-25-frequent-commands-survey.md). Streams
every transcript once, line by line (never loads a file whole), and builds
one row per candidate Stop: the last stop before each human-typed prompt
(labelled by that prompt), intermediate stops inside a turn, and session
ends. Also pulls per-week/month/project frequency for the target commands
straight from history.jsonl, which holds typed prompts back further than
transcripts (transcripts here only go back about 5.5 weeks; history.jsonl to
January).

Corrected extraction (folded in 2026-09-25 from the Opus-reviewed second pass
of the survey above -- see its "Opus review" section for the full writeup).
Bugs the first draft had, that this pass avoids:
  1. Skill-injection text (the `isMeta` user message injected right after a
     slash command, carrying the skill body) was counted as a typed prompt,
     so every positive got a near-identical negative twin one row later.
     A prompt now counts only when it is human-origin
     (`origin.kind == "human"`, not `isMeta`), never `<task-notification>`,
     `<system-reminder>`, `<local-command>`, or an interrupt marker.
  2. "Dirty tree" was set true from the first non-empty tool result of ANY
     tool that ran after a `git status`/`diff`, not the result of that git
     call itself. It is now matched to the git call by `tool_use_id`.
  3. The negative comparison sample was a random fixed-seed draw from the
     whole pool, not matched on session or time, which overstated precision
     roughly tenfold. Rules (`--rules`) now score against the FULL stop pool;
     the descriptive feature table also builds a same-session nearest-
     neighbour matched sample per positive, alongside the full pool.
  4. The main confound -- about a third of `/outstanding` prompts directly
     follow a `/stg-msg-cmt` answer -- is now its own explicit feature
     (`prompt_slash == 'stg-msg-cmt'`, or `opened_by_<cmd>` for --rules)
     rather than being hidden inside the "done wording" / "git dirty"
     signals it was driving in the first draft.

`--cv` (the cross-validated model comparison from the Opus review's cv.py) is
NOT folded in here: it needs scikit-learn and numpy, which nothing else in
this script or usage-survey.py depends on. Its verdict was "not actionable"
for both commands anyway (AP ~0.1-0.26, no better than the rule search
below); run it by hand from wherever it's kept if that changes.

Usage:
  command-moments-survey.py --commands outstanding,stg-msg-cmt --out-dir DIR
  command-moments-survey.py --commands outstanding,stg-msg-cmt --history-only
  command-moments-survey.py --commands outstanding,stg-msg-cmt --rules

Writes <out-dir>/command_moments_rows.jsonl -- one row per candidate Stop,
labelled with the target command name, "other", "intermediate", or
"session_end". Prints history.jsonl frequency tables, a per-feature
prevalence report (each target vs. its same-session matched sample vs. the
full pool), and, with --rules, an exhaustive search over conjunctions of up
to 3 features, scored for precision/recall/F1 on the full stop pool. Read-only
on all Claude Code data.
"""
import argparse
import collections
import glob
import itertools
import json
import os
import re
import statistics
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from claude_dirs import config_dirs  # noqa: E402

LOCAL = {"model", "effort", "compact", "clear", "config", "status", "cost", "context", "resume",
         "login", "logout", "mcp", "permissions", "hooks", "statusline", "theme", "exit", "rewind",
         "usage", "agents", "memory", "ide", "vim", "doctor", "help", "export", "add-dir", "fast",
         "output-style", "plugin", "plugins", "skills", "release-notes", "tasks", "bashes", "rename"}
CMD_RE = re.compile(r"<command-name>/?([\w:-]+)</command-name>")
GIT_STATUS_RE = re.compile(r"\bgit\b[^|;&\n]*\b(status|diff)\b")
GIT_COMMIT_RE = re.compile(r"\bgit\b[^|;&\n]*\bcommit\b")
DIRTY_RE = re.compile(r"Changes not staged|Changes to be committed|Untracked files|^\s?[MADRCU?!]{1,2} \S", re.M)
BASH_WRITE_RE = re.compile(r"sed -i|(?<![<>0-9&])>{1,2}\s*[\"']?[~/\w.$-]+\.\w+|\btee\b|\bcat\s*>|write_text|\.write\(|\bmv\b|\bcp\b")
DONE_RE = re.compile(r"\bdone\b|\ball (set|clean)\b|\bnothing (else )?outstanding\b|\bcomplete(d)?\b|"
                      r"\bfinished\b|\bpushed\b|\bcommitted\b", re.I)
REMAIN_RE = re.compile(r"\b(remaining|remains|still (open|pending|to do|needed|missing|unverified|untested)|"
                        r"left to|not yet|outstanding|next steps?|todo|to-do|pending|open items?|"
                        r"follow-?ups?|blocked|unresolved|not done)\b", re.I)
LIST_RE = re.compile(r"^\s*([-*]|\d+[.)])\s+\S", re.M)
IMPER_RE = re.compile(r"^\s*(ok(ay)?[,.]?\s+|please\s+|now\s+|then\s+|yes[,.]?\s+)*(fix|add|implement|build|make|"
                       r"write|create|change|update|remove|delete|drop|refactor|rename|move|replace|convert|"
                       r"rewrite|edit|apply|set ?up|install|wire|hook|go ahead|do it|do that|ship|land|port|"
                       r"extract|merge|split|bump|patch|clean ?up|restore|revert|put|use|switch|migrate|"
                       r"generate|draft|save|persist|commit|push|deploy)\b", re.I)


def slug_name(slug):
    decoded = slug.replace("-", "/")
    base = os.path.basename(decoded.rstrip("/"))
    return base or slug


def ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def mins(a, b):
    return (b - a).total_seconds() / 60 if a and b else None


def text_of(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def is_human(e, c):
    """True only for an actually-typed prompt: not isMeta, not a tool result,
    origin.kind == 'human' when present, and never a skill-injection body,
    interrupt marker, task-notification, or system-reminder (bug #1)."""
    if e.get("isMeta"):
        return False
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return False
    o = (e.get("origin") or {}).get("kind")
    if o is not None:
        return o == "human"
    if e.get("turnOrigin") not in (None, "human"):
        return False
    t = text_of(c).lstrip()
    return bool(t) and not t.startswith(("[Request interrupted", "<local-command", "This session is being continued",
                                          "<task-notification", "<system-reminder"))


# --- transcript pass (moments2.py logic) -----------------------------------

def scan(path, project, targets):
    rows = []
    sess = {"turn_idx": 0, "last_commit_turn": None, "edits_since_commit": 0,
            "last_status_dirty": None, "last_event_ts": None, "prev_prompt": None, "prev_slash": None}
    turn = None
    snaps = []  # snapshots at Stop markers in the current turn
    pending_git = {}
    stop_seen_since_activity = False

    def new_turn(prompt_text, slash, t):
        return {"tool_calls": 0, "edit_paths": set(), "bash_writes": 0, "git_seen": False, "git_dirty": None,
                "commit": False, "ask": False, "notif": 0, "last_input": "human", "interrupted": False,
                "last_text": "", "start": t, "last_asst_ts": None, "prompt": prompt_text, "slash": slash,
                "agent_launch": False}

    def snapshot(at_ts):
        if turn is None or (not turn["last_text"] and turn["tool_calls"] == 0):
            return None
        lt = turn["last_text"]
        tail = lt[-500:]
        return {
            "project": project, "session": os.path.basename(path)[:-6], "ts": at_ts.isoformat() if at_ts else None,
            "msg_len": len(lt), "tool_calls": turn["tool_calls"],
            "files_edited": len(turn["edit_paths"]), "bash_writes": turn["bash_writes"],
            "edits_in_turn": len(turn["edit_paths"]) + turn["bash_writes"],
            "edits_since_commit": sess["edits_since_commit"],
            "turns_since_commit": (sess["turn_idx"] - sess["last_commit_turn"]) if sess["last_commit_turn"] is not None else sess["turn_idx"],
            "ever_committed": sess["last_commit_turn"] is not None,
            "commit_in_turn": turn["commit"],
            "git_seen": turn["git_seen"], "git_dirty": turn["git_dirty"],
            "last_status_dirty": sess["last_status_dirty"],
            "ask": turn["ask"], "notif_in_turn": turn["notif"] > 0,
            "ended_after_notif": turn["last_input"] == "task-notification",
            "interrupted": turn["interrupted"], "agent_launch": turn["agent_launch"],
            "done_word": bool(DONE_RE.search(tail)),
            "remain_word": bool(REMAIN_RE.search(lt)),
            "has_list": bool(LIST_RE.search(lt)),
            "ends_q": lt.rstrip().endswith("?"),
            "prompt_imperative": bool(IMPER_RE.match(turn["prompt"] or "")),
            "prompt_slash": turn["slash"],
            "turn_min": mins(turn["start"], turn["last_asst_ts"]),
            "turn_idx": sess["turn_idx"],
            "last_text": lt[-1500:],
            # The whole message, for a consumer that must rebuild exactly what a Stop
            # hook sees (head excerpt plus counts over the full text): system-one-train-data.py.
            "last_text_full": lt,
        }

    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return rows
    away = False
    with fh:
        for line in fh:
            try:
                e = json.loads(line)
            except Exception:
                continue
            et = e.get("type")
            t = ts(e.get("timestamp") or "")
            msg = e.get("message") or {}
            c = msg.get("content")
            if et == "system":
                st = e.get("subtype")
                if st in ("stop_hook_summary", "turn_duration") and turn is not None and not stop_seen_since_activity:
                    s = snapshot(t)
                    if s:
                        snaps.append(s)
                    stop_seen_since_activity = True
                if st == "away_summary":
                    away = True
                continue
            if et == "user":
                if is_human(e, c):
                    txt = text_of(c).strip()
                    m = CMD_RE.search(txt)
                    slash = m.group(1) if m else (txt.split()[0].lstrip("/") if txt.startswith("/") and txt.split() else None)
                    if slash in LOCAL:
                        continue
                    if turn is not None:
                        if not stop_seen_since_activity:
                            s = snapshot(sess["last_event_ts"])
                            if s:
                                snaps.append(s)
                        for i, s in enumerate(snaps):
                            last = i == len(snaps) - 1
                            s["label"] = (slash if slash in targets else "other") if last else "intermediate"
                            s["next_slash"] = slash if last else None
                            s["idle_min"] = mins(sess["last_event_ts"], t) if last else 0.0
                            s["away_summary"] = away if last else False
                            s["next_prompt"] = txt[:200] if last else None
                            s["prev_turn_slash"] = sess["prev_slash"]
                            rows.append(s)
                    snaps = []
                    away = False
                    sess["turn_idx"] += 1
                    sess["prev_slash"] = turn["slash"] if turn else None
                    turn = new_turn(txt[:500], slash, t)
                    stop_seen_since_activity = False
                    sess["last_event_ts"] = t
                    continue
                if turn is None:
                    continue
                if isinstance(c, list):
                    for b in c:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            rid = b.get("tool_use_id")
                            if rid in pending_git:
                                out = text_of(b.get("content")) if not isinstance(b.get("content"), str) else b.get("content")
                                if DIRTY_RE.search(out or "") or "diff --git" in (out or ""):
                                    turn["git_dirty"] = True
                                    sess["last_status_dirty"] = True
                                elif turn["git_dirty"] is not True:
                                    turn["git_dirty"] = False
                                    sess["last_status_dirty"] = False
                                pending_git.pop(rid)
                    txt = text_of(c)
                    if "[Request interrupted" in txt:
                        turn["interrupted"] = True
                    turn["last_input"] = "tool_result"
                elif isinstance(c, str):
                    if c.startswith("[Request interrupted"):
                        turn["interrupted"] = True
                    if c.lstrip().startswith("<task-notification") or (e.get("origin") or {}).get("kind") == "task-notification":
                        turn["notif"] += 1
                        turn["last_input"] = "task-notification"
                        stop_seen_since_activity = False
                if (e.get("origin") or {}).get("kind") == "task-notification" and not isinstance(c, str):
                    turn["notif"] += 1
                    turn["last_input"] = "task-notification"
                    stop_seen_since_activity = False
                if t:
                    sess["last_event_ts"] = t
                continue
            if et != "assistant" or turn is None or not isinstance(c, list):
                continue
            stop_seen_since_activity = False
            if t:
                turn["last_asst_ts"] = t
                sess["last_event_ts"] = t
            for b in c:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and (b.get("text") or "").strip():
                    turn["last_text"] = b["text"]
                elif b.get("type") == "tool_use":
                    turn["tool_calls"] += 1
                    n, inp = b.get("name"), b.get("input") or {}
                    if n == "AskUserQuestion":
                        turn["ask"] = True
                    elif n == "Agent":
                        turn["agent_launch"] = True
                    elif n in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
                        p = inp.get("file_path") or inp.get("notebook_path")
                        if p:
                            turn["edit_paths"].add(p)
                            sess["edits_since_commit"] += 1
                    elif n == "Bash":
                        cmd = inp.get("command") or ""
                        if GIT_STATUS_RE.search(cmd):
                            turn["git_seen"] = True
                            pending_git[b.get("id")] = 1
                        if GIT_COMMIT_RE.search(cmd):
                            turn["commit"] = True
                            sess["last_commit_turn"] = sess["turn_idx"]
                            sess["edits_since_commit"] = 0
                        elif BASH_WRITE_RE.search(cmd) and not cmd.lstrip().startswith(("git ", "ls", "cat ", "grep")):
                            turn["bash_writes"] += 1
                            sess["edits_since_commit"] += 1
        if turn is not None:
            if not stop_seen_since_activity:
                s = snapshot(sess["last_event_ts"])
                if s:
                    snaps.append(s)
            for i, s in enumerate(snaps):
                s["label"] = "session_end" if i == len(snaps) - 1 else "intermediate"
                s["next_slash"] = None
                s["idle_min"] = None
                s["away_summary"] = False
                s["next_prompt"] = None
                s["prev_turn_slash"] = sess["prev_slash"]
                rows.append(s)
    return rows


def scan_all_transcripts(targets):
    rows = []
    for cfg in config_dirs():
        root = os.path.join(cfg, "projects")
        if not os.path.isdir(root):
            continue
        for p in sorted(glob.glob(os.path.join(root, "*", "*.jsonl"))):
            proj = slug_name(os.path.basename(os.path.dirname(p)))
            rows.extend(scan(p, proj, targets))
    return rows


# --- feature step (feat.py logic) -------------------------------------------

def feature_defs(targets):
    defs = [
        ("edits in turn >=1", lambda r: r["edits_in_turn"] >= 1),
        ("edits in turn >=3", lambda r: r["edits_in_turn"] >= 3),
        ("edits since last commit >=1", lambda r: r["edits_since_commit"] >= 1),
        ("edits since last commit >=5", lambda r: r["edits_since_commit"] >= 5),
        (">=3 turns since last commit (or none yet)", lambda r: r["turns_since_commit"] >= 3),
        ("commit ran in this turn", lambda r: r["commit_in_turn"]),
        ("git status/diff run in turn", lambda r: r["git_seen"]),
        ("git status parsed dirty in turn", lambda r: r["git_dirty"] is True),
        ("last parsed status in session dirty", lambda r: r["last_status_dirty"] is True),
        ("prompt that opened the turn is build imperative", lambda r: r["prompt_imperative"]),
        ("prompt that opened the turn was a slash cmd", lambda r: bool(r["prompt_slash"])),
        ("away_summary before the prompt (resume)", lambda r: r["away_summary"]),
        ("idle >=10 min before next prompt", lambda r: (r["idle_min"] or 0) >= 10),
        ("idle >=30 min before next prompt", lambda r: (r["idle_min"] or 0) >= 30),
        ("turn ended after bg-agent notification", lambda r: r["ended_after_notif"]),
        ("bg notification arrived in turn", lambda r: r["notif_in_turn"]),
        ("turn interrupted", lambda r: r["interrupted"]),
        ("Agent launched in turn", lambda r: r["agent_launch"]),
        ("last msg: remaining-items wording", lambda r: r["remain_word"]),
        ("last msg: remaining wording + list", lambda r: r["remain_word"] and r["has_list"]),
        ("last msg: done wording (tail)", lambda r: r["done_word"]),
        ("last msg: ends with ?", lambda r: r["ends_q"]),
        ("AskUserQuestion in turn", lambda r: r["ask"]),
    ]
    for cmd in sorted(targets):
        defs.append((f"prompt that opened the turn was /{cmd}",
                      (lambda c: (lambda r: r["prompt_slash"] == c))(cmd)))
    return defs


def matched_sample(rows, targets, positives):
    """For each positive, the nearest other same-session stop labelled
    'other' whose opening prompt was not itself one of the target commands
    -- matched on time, not a random draw (bug #3)."""
    by_session = collections.defaultdict(list)
    for r in rows:
        if r["label"] == "other" and r["prompt_slash"] not in targets:
            by_session[r["session"]].append(r)
    out = []
    for p in positives:
        pt = ts(p["ts"]) if p["ts"] else None
        cands = by_session.get(p["session"], [])
        cands = [(r, ts(r["ts"])) for r in cands]
        cands = [(r, t) for r, t in cands if t and pt]
        if cands:
            out.append(min(cands, key=lambda rt: abs((rt[1] - pt).total_seconds()))[0])
    return out


def pct(rows, f):
    return 100 * sum(1 for r in rows if f(r)) / len(rows) if rows else 0


def med(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return statistics.median(vals) if vals else None


def print_feature_report(rows, targets):
    print("\n--- feature prevalence: target vs. same-session matched sample vs. full pool ---")
    pool = [r for r in rows if r["label"] not in targets]
    defs = feature_defs(targets)
    for cmd in sorted(targets):
        pos = [r for r in rows if r["label"] == cmd]
        mset = matched_sample(rows, targets, pos)
        print(f"\n/{cmd}: n={len(pos)} positives, {len(mset)} matched, {len(pool)} pool")
        header = f"{'feature':55s} {'cmd':>6} {'matched':>8} {'pool':>6}"
        print(header)
        for name, f in defs:
            print(f"{name:55s} {pct(pos, f):6.0f} {pct(mset, f):8.0f} {pct(pool, f):6.0f}")
        print("medians:")
        for key in ("msg_len", "tool_calls", "edits_in_turn", "edits_since_commit",
                    "turns_since_commit", "idle_min", "turn_min"):
            print(f"  {key:25s} cmd={med(pos, key)!s:>8} matched={med(mset, key)!s:>8} pool={med(pool, key)!s:>8}")


# --- rule search (rules.py logic, --rules only) -----------------------------

def rule_features(targets):
    feats = {
        "edits_turn>=1": lambda r: r["edits_in_turn"] >= 1,
        "edits_turn>=3": lambda r: r["edits_in_turn"] >= 3,
        "edits_since_commit>=1": lambda r: r["edits_since_commit"] >= 1,
        "edits_since_commit>=3": lambda r: r["edits_since_commit"] >= 3,
        "no_commit_in_turn": lambda r: not r["commit_in_turn"],
        "commit_in_turn": lambda r: r["commit_in_turn"],
        "git_dirty_turn": lambda r: r["git_dirty"] is True,
        "opened_by_plain": lambda r: not r["prompt_slash"],
        "remain_word": lambda r: r["remain_word"],
        "done_word": lambda r: r["done_word"],
        "no_ask": lambda r: not r["ask"],
        "tool_calls>=5": lambda r: r["tool_calls"] >= 5,
        "msg_len<600": lambda r: r["msg_len"] < 600,
        "msg_len>=1000": lambda r: r["msg_len"] >= 1000,
    }
    for cmd in sorted(targets):
        feats[f"opened_by_{cmd}"] = (lambda c: (lambda r: r["prompt_slash"] == c))(cmd)
    return feats


def search_rules(rows, targets):
    feats = rule_features(targets)
    names = list(feats)
    print(f"\n--- rule search: conjunctions of 1-3 features, scored on the full pool ({len(rows)} stops) ---")
    for tgt in sorted(targets):
        positives = sum(1 for r in rows if r["label"] == tgt)
        print(f"\n{tgt}: positives {positives} of {len(rows)} stops, base rate {100 * positives / len(rows):.1f}%")
        results = []
        for k in (1, 2, 3):
            for combo in itertools.combinations(names, k):
                fns = [feats[c] for c in combo]
                hit = [r for r in rows if all(fn(r) for fn in fns)]
                if not hit:
                    continue
                tp = sum(1 for r in hit if r["label"] == tgt)
                if tp == 0:
                    continue
                p = tp / len(hit)
                rc = tp / positives
                f1 = 2 * p * rc / (p + rc)
                results.append((f1, p, rc, len(hit), combo))
        results.sort(reverse=True)
        print("  top by F1:")
        for f1, p, rc, n, combo in results[:6]:
            print(f"    F1 {f1:.2f} P {p:.2f} R {rc:.2f} flagged {n}  {' & '.join(combo)}")
        best_p = sorted((x for x in results if x[2] >= 0.30), key=lambda x: -x[1])
        print("  best precision at recall>=0.30:")
        for f1, p, rc, n, combo in best_p[:3]:
            print(f"    P {p:.2f} R {rc:.2f} flagged {n}  {' & '.join(combo)}")


# --- history.jsonl frequency pass (unchanged from the original) ------------

def scan_history_freq(targets):
    per_week = collections.defaultdict(collections.Counter)
    per_month = collections.defaultdict(collections.Counter)
    per_project = collections.defaultdict(collections.Counter)
    first_ts, last_ts = {}, {}
    total = 0
    for cfg in config_dirs():
        path = os.path.join(cfg, "history.jsonl")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ms = e.get("timestamp")
                if not ms:
                    continue
                dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
                text = (e.get("display") or "").strip()
                if not text:
                    continue
                total += 1
                if not text.startswith("/"):
                    continue
                cmd = text.split()[0].lstrip("/")
                if cmd not in targets:
                    continue
                iso = dt.isocalendar()
                per_week[f"{iso[0]}-W{iso[1]:02d}"][cmd] += 1
                per_month[f"{dt.year}-{dt.month:02d}"][cmd] += 1
                proj = os.path.basename((e.get("project") or "").rstrip("/")) or "?"
                per_project[proj][cmd] += 1
                first_ts[cmd] = min(first_ts.get(cmd, dt), dt)
                last_ts[cmd] = max(last_ts.get(cmd, dt), dt)
    return {"total": total, "per_week": per_week, "per_month": per_month,
            "per_project": per_project, "first_ts": first_ts, "last_ts": last_ts}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commands", required=True, help="comma-separated target slash command names, no leading /")
    ap.add_argument("--out-dir", default=".", help="where to write command_moments_rows.jsonl")
    ap.add_argument("--history-only", action="store_true", help="skip the transcript pass, print frequency tables only")
    ap.add_argument("--rules", action="store_true",
                     help="search conjunctions of up to 3 features and report precision/recall on the full stop pool")
    args = ap.parse_args()
    targets = {c.strip().lstrip("/") for c in args.commands.split(",") if c.strip()}

    hist = scan_history_freq(targets)
    print("total typed prompts in history.jsonl:", hist["total"])
    print("\nper month:")
    for mo in sorted(hist["per_month"]):
        c = hist["per_month"][mo]
        print("  " + mo + ": " + "  ".join(f"{k}={c.get(k, 0)}" for k in sorted(targets)))
    print("\nper week:")
    for wk in sorted(hist["per_week"]):
        c = hist["per_week"][wk]
        print("  " + wk + ": " + "  ".join(f"{k}={c.get(k, 0)}" for k in sorted(targets)))
    print("\nper project (top 12 by total):")
    proj_totals = sorted(hist["per_project"].items(), key=lambda kv: -sum(kv[1].values()))[:12]
    for proj, c in proj_totals:
        print("  " + f"{proj:20s} " + "  ".join(f"{k}={c.get(k, 0)}" for k in sorted(targets)))
    print("\nfirst/last seen:")
    for cmd in sorted(targets):
        if cmd in hist["first_ts"]:
            print(f"  {cmd}: {hist['first_ts'][cmd].date()} .. {hist['last_ts'][cmd].date()}")

    if args.history_only:
        return

    rows = scan_all_transcripts(targets)

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, "command_moments_rows.jsonl")
    with open(out_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    print(f"\ntotal stop-moments scanned: {len(rows)}")
    for cmd in sorted(targets):
        print(f"positives for {cmd}: {sum(1 for r in rows if r['label'] == cmd)}")
    print(f"intermediate stops (inside a turn): {sum(1 for r in rows if r['label'] == 'intermediate')}")
    print(f"session-end stops: {sum(1 for r in rows if r['label'] == 'session_end')}")
    print(f"other non-command stops: {sum(1 for r in rows if r['label'] == 'other')}")
    print(f"wrote {out_path}")

    print_feature_report(rows, targets)

    if args.rules:
        search_rules(rows, targets)


if __name__ == "__main__":
    main()
