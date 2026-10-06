#!/usr/bin/env python3
# DESC: Review what the ssh-request-guard hook stopped, with whether each ask was approved or denied
"""Reads the hook's ask log (one JSON line per ask: at, session, cwd, transcript, tool_use_id,
command, reason) and joins each line with its session transcript to find the outcome:

    approved    the command ran (a tool result follows the ask)
    denied      the user rejected it, or the auto-mode classifier did
    unanswered  no result in the transcript (session ended, or still open)

    review-ssh-guard-asks.py [--days N] [--denied] [--json] [--log FILE]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claude_dirs import find_transcript  # noqa: E402

REJECTED = "The user doesn't want to proceed with this tool use"
CLASSIFIER = "denied by the Claude Code auto mode classifier"


def default_log() -> Path:
    cfg = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return Path(os.environ.get("SSH_REQUEST_GUARD_LOG") or f"{cfg}/ssh-request-guard/asks.jsonl")


def read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def outcomes(transcript: Path) -> dict[str, str]:
    """tool_use_id -> outcome, for every Bash call a PreToolUse hook asked about."""
    asked: dict[str, str] = {}
    try:
        lines = transcript.read_text().splitlines()
    except OSError:
        return asked
    for line in lines:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        a = d.get("attachment") or {}
        if a.get("hookEvent") == "PreToolUse" and '"ask"' in (a.get("stdout") or ""):
            asked.setdefault(a.get("toolUseID", ""), "unanswered")
        if d.get("type") != "user":
            continue
        for c in (d.get("message") or {}).get("content") or []:
            if not isinstance(c, dict) or c.get("type") != "tool_result" or c.get("tool_use_id") not in asked:
                continue
            text = c.get("content")
            text = text if isinstance(text, str) else json.dumps(text)
            if REJECTED in text:
                asked[c["tool_use_id"]] = "denied"
            elif CLASSIFIER in text:
                asked[c["tool_use_id"]] = "denied by classifier"
            else:
                asked[c["tool_use_id"]] = "approved"
    return asked


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=0, help="only asks from the last N days (0 = all)")
    ap.add_argument("--denied", action="store_true", help="only asks that were denied")
    ap.add_argument("--json", action="store_true", help="print one JSON object per ask")
    ap.add_argument("--log", type=Path, default=default_log(), help="the ask log (default: the hook's)")
    args = ap.parse_args()

    rows = read_log(args.log)
    if args.days:
        since = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = [r for r in rows if r.get("at", "") >= since]
    cache: dict[str, dict[str, str]] = {}
    for r in rows:
        path = r.get("transcript") or ""
        if not path:
            found, _ = find_transcript(r.get("session", ""))
            path = found or ""
        if path and path not in cache:
            cache[path] = outcomes(Path(path))
        r["outcome"] = cache.get(path, {}).get(r.get("tool_use_id", ""), "unanswered") if path else "no transcript"
        r["project"] = os.path.basename(r.get("cwd") or "") or "?"
    if args.denied:
        rows = [r for r in rows if r["outcome"].startswith("denied")]

    if args.json:
        for r in rows:
            print(json.dumps(r))
        return 0
    if not rows:
        what = "denied asks" if args.denied else "asks"
        print(f"no {what} recorded" + (f" in the last {args.days} days" if args.days else "") + f" ({args.log})")
        return 0
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    print(f"{len(rows)} asks: " + ", ".join(f"{n} {k}" for k, n in sorted(counts.items())))
    print()
    for r in rows:
        cmd = " ".join((r.get("command") or "").split())
        if len(cmd) > 110:
            cmd = cmd[:107] + "..."
        reason = (r.get("reason") or "").split(".")[0]
        print(f"{r.get('at', '')[:16]}  {r['outcome']:<21} {r['project']:<18} {cmd}")
        print(f"{'':18}{reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
