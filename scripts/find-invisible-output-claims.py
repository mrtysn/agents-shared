#!/usr/bin/env python3
# DESC: Survey Claude Code transcripts for assistant claims about content the user never saw
"""
find-invisible-output-claims: survey a failure pattern where the assistant

points at a result the user cannot see and the user has to ask "what above?".

The shape: a tool result the user cannot read directly (a background-task
task-notification, a subagent hand-back / agent-message, a Monitor event, or
raw Bash output) lands in the transcript, and within the next few assistant
turns the assistant writes "as shown above", "see the table above", "the
report above" etc. as though the user had read it. Separately, the user's own
confused replies ("what above", "I don't see anything", "show me") are found
and paired with the assistant message that provoked them.

Read-only. Streams every session transcript under each Claude config dir
(~/.claude*, plus CLAUDE_CONFIG_DIR — see claude_dirs.config_dirs()).

Usage:
  find-invisible-output-claims.py                  text report to stdout
  find-invisible-output-claims.py --json            machine-readable output
  find-invisible-output-claims.py --since 2026-08-01
  find-invisible-output-claims.py --within-turns 5  widen the "recently" window
  find-invisible-output-claims.py --examples 40     more paired examples
  find-invisible-output-claims.py --reference-regex 'per the log above' --reference-regex 'as noted above'
"""

import argparse
import collections
import glob
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from claude_dirs import config_dirs  # noqa: E402

# ---------------------------------------------------------------- defaults

DEFAULT_REFERENCE_PHRASES = [
    r"as shown above",
    r"shown above",
    r"as (?:i |we )?reported",
    r"as the agent reported",
    r"see the (?:table|report|output|result|list) above",
    r"the (?:table|report|output|result|list) above",
    r"the above (?:table|report|output|result|list)",
    r"above (?:table|report|output|result|list)",
    r"per the (?:above|log above|output above)",
    r"as noted above",
    r"the results? (?:is|are) above",
    r"you can see (?:it |the results? )?above",
    r"as you can see above",
    r"in the (?:output|result|report) above",
    r"see above",
]

DEFAULT_CONFUSION_PHRASES = [
    r"what above",
    r"where is (?:it|that|this)",
    r"\bwhere\??$",
    r"i don'?t see (?:anything|it|that|this)",
    r"nothing here",
    r"can'?t see (?:it|that|anything)",
    r"i can'?t see",
    r"which table",
    r"show me",
    r"what are you clicking",
    r"i dont see",
    r"what is above",
    r"what'?s above",
    r"i see nothing",
]

# markers of a tool result the user cannot read directly
TASK_NOTIFICATION_RE = re.compile(r"^\s*<task-notification>")
AGENT_MESSAGE_RE = re.compile(r"<agent-message\b|SubagentHandback|Another Claude session sent a message")
MONITOR_TAG_RE = re.compile(r"<task-notification>[\s\S]*?Monitor\b", re.IGNORECASE)


def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def slug_name(slug):
    decoded = slug.replace("-", "/")
    base = os.path.basename(decoded.rstrip("/"))
    return base or slug


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def classify_invisible_user_entry(content):
    """Return a kind string if this 'user' entry is an injected message the
    user did not type and whose full content they cannot read inline, else
    None.

    Deliberately narrow: an ordinary synchronous Bash/Monitor tool_result
    renders inline in the transcript UI, so it is not "invisible" by itself.
    What is genuinely invisible is the class of injected notices that only
    summarize a result and point at a file or a separate agent transcript --
    a backgrounded task's task-notification, or another session's
    agent-message / SubagentHandback report."""
    if isinstance(content, str):
        if TASK_NOTIFICATION_RE.search(content):
            if MONITOR_TAG_RE.search(content):
                return "task-notification (monitor)"
            if "Agent" in content or "Subagent" in content:
                return "task-notification (agent)"
            return "task-notification (background command)"
        if AGENT_MESSAGE_RE.search(content):
            return "agent-message / SubagentHandback"
    return None


def clean_excerpt(text, limit):
    t = " ".join(text.split())
    if len(t) > limit:
        t = t[: limit - 1].rstrip() + "…"
    return t


def scan_transcript(path, slug, ref_re, conf_re, within_turns, since_dt):
    project = slug_name(slug)
    ref_hits = []       # dicts: project, ts, phrase, assistant_excerpt, invisible_kind
    conf_pairs = []      # dicts: project, ts, assistant_excerpt, user_excerpt

    pending_kind = None
    turns_after = None  # None = no pending invisible event
    last_assistant_text = ""
    turns_since_ref_hit = None  # None = no recent ref-phrase hit
    all_confusion_hits = [0]  # mutable counter, boxed so the caller can read it

    try:
        fh = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return ref_hits, conf_pairs, 0
    with fh:
        for line in fh:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = e.get("type")
            if t not in ("user", "assistant"):
                continue
            ts = e.get("timestamp")
            dt = parse_ts(ts)
            if since_dt and dt and dt < since_dt:
                continue

            msg = e.get("message") or {}
            content = msg.get("content")

            if t == "user":
                kind = classify_invisible_user_entry(content)
                if kind:
                    pending_kind = kind
                    turns_after = 0
                    continue

                # typed user prompt (skip attachments / system reminders)
                if isinstance(content, str):
                    stripped = content.strip()
                    if not stripped or stripped.startswith("<system-reminder>") or stripped.startswith("<local-command"):
                        continue
                    low = stripped.lower()
                    if conf_re.search(low) and last_assistant_text:
                        all_confusion_hits[0] += 1
                        # keep it as a "clearest" paired example only when an
                        # invisible tool result (task-notification, agent
                        # hand-back, Monitor event, Bash output) is still in
                        # the recent-turns window, or the preceding assistant
                        # message itself used a reference phrase -- otherwise
                        # "show me"/"where" is just an ordinary follow-up, not
                        # this failure pattern
                        recent_invisible = (pending_kind is not None and turns_after is not None
                                            and turns_after <= within_turns)
                        recent_ref_hit = (turns_since_ref_hit is not None
                                          and turns_since_ref_hit <= within_turns)
                        if recent_invisible or recent_ref_hit:
                            conf_pairs.append({
                                "project": project, "ts": ts,
                                "assistant_excerpt": clean_excerpt(last_assistant_text, 200),
                                "user_excerpt": clean_excerpt(stripped, 120),
                            })
                continue

            # assistant entry
            if not isinstance(content, list):
                continue
            text_here = ""
            for b in content:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "text":
                    txt = b.get("text") or ""
                    if txt.strip():
                        text_here = txt
                        last_assistant_text = txt
                        if pending_kind and turns_after is not None and turns_after <= within_turns:
                            for m in ref_re.finditer(txt.lower()):
                                turns_since_ref_hit = 0
                                ref_hits.append({
                                    "project": project, "ts": ts,
                                    "phrase": m.group(0),
                                    "assistant_excerpt": clean_excerpt(txt, 200),
                                    "invisible_kind": pending_kind,
                                    "turns_after": turns_after,
                                })
            if pending_kind is not None:
                turns_after = (turns_after or 0) + 1
                if turns_after > within_turns:
                    pending_kind = None
                    turns_after = None
            if turns_since_ref_hit is not None:
                turns_since_ref_hit += 1
                if turns_since_ref_hit > within_turns:
                    turns_since_ref_hit = None

    return ref_hits, conf_pairs, all_confusion_hits[0]


def month_key(ts):
    dt = parse_ts(ts)
    return dt.strftime("%Y-%m") if dt else "?"


def build_report(ref_hits, conf_pairs, all_confusion_count, examples_n):
    lines = []
    lines.append(f"Reference-phrase hits (assistant pointed at unseen content): {len(ref_hits)}")
    lines.append(f"Confusion-regex matches, any context: {all_confusion_count}")
    lines.append(f"  ...of which paired with a preceding invisible-content claim: {len(conf_pairs)}")
    lines.append("")

    by_project_ref = collections.Counter(h["project"] for h in ref_hits)
    by_project_conf = collections.Counter(p["project"] for p in conf_pairs)
    lines.append("Per project (reference hits / confusion replies):")
    for proj in sorted(set(by_project_ref) | set(by_project_conf)):
        lines.append(f"  {proj}: {by_project_ref.get(proj, 0)} / {by_project_conf.get(proj, 0)}")
    lines.append("")

    by_month_ref = collections.Counter(month_key(h["ts"]) for h in ref_hits)
    by_month_conf = collections.Counter(month_key(p["ts"]) for p in conf_pairs)
    lines.append("Per month (reference hits / confusion replies):")
    for mo in sorted(set(by_month_ref) | set(by_month_conf)):
        lines.append(f"  {mo}: {by_month_ref.get(mo, 0)} / {by_month_conf.get(mo, 0)}")
    lines.append("")

    lines.append(f"Clearest paired examples (confusion reply + preceding assistant message), top {examples_n}:")
    for p in conf_pairs[:examples_n]:
        date = (parse_ts(p["ts"]) or "").strftime("%Y-%m-%d") if parse_ts(p["ts"]) else "?"
        lines.append(f"  [{p['project']} {date}] assistant: {p['assistant_excerpt']}")
        lines.append(f"      user: {p['user_excerpt']}")
    lines.append("")

    phrase_counts = collections.Counter(h["phrase"] for h in ref_hits)
    lines.append("Assistant phrasings ranked by frequency:")
    for phrase, n in phrase_counts.most_common(30):
        lines.append(f"  {n:4d}  {phrase}")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="Survey Claude Code transcripts for assistant claims about content the user never saw.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--since", help="only consider entries at/after this ISO date (YYYY-MM-DD)")
    ap.add_argument("--within-turns", type=int, default=3,
                     help="how many assistant turns after an invisible tool result still count as 'recent' (default 3)")
    ap.add_argument("--examples", type=int, default=25, help="number of paired examples to print (default 25)")
    ap.add_argument("--reference-regex", action="append", default=None,
                     help="additional reference-phrase regex (repeatable); replaces defaults if given without --extend-defaults")
    ap.add_argument("--confusion-regex", action="append", default=None,
                     help="additional confusion-phrase regex (repeatable)")
    ap.add_argument("--extend-defaults", action="store_true",
                     help="add --reference-regex/--confusion-regex to the built-in lists instead of replacing them")
    ap.add_argument("--json", action="store_true", help="print machine-readable JSON instead of a text report")
    args = ap.parse_args()

    since_dt = None
    if args.since:
        try:
            since_dt = datetime.fromisoformat(args.since)
            if since_dt.tzinfo is None:
                from datetime import timezone
                since_dt = since_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            ap.error(f"--since: could not parse {args.since!r} as an ISO date")

    ref_phrases = list(DEFAULT_REFERENCE_PHRASES)
    conf_phrases = list(DEFAULT_CONFUSION_PHRASES)
    if args.reference_regex:
        ref_phrases = ref_phrases + args.reference_regex if args.extend_defaults else args.reference_regex
    if args.confusion_regex:
        conf_phrases = conf_phrases + args.confusion_regex if args.extend_defaults else args.confusion_regex

    ref_re = re.compile("|".join(f"(?:{p})" for p in ref_phrases), re.IGNORECASE)
    conf_re = re.compile("|".join(f"(?:{p})" for p in conf_phrases), re.IGNORECASE)

    all_ref_hits = []
    all_conf_pairs = []
    all_confusion_count = 0
    for cfg in config_dirs():
        for path in glob.glob(os.path.join(cfg, "projects", "*", "*.jsonl")):
            slug = os.path.basename(os.path.dirname(path))
            ref_hits, conf_pairs, confusion_count = scan_transcript(
                path, slug, ref_re, conf_re, args.within_turns, since_dt)
            all_ref_hits.extend(ref_hits)
            all_conf_pairs.extend(conf_pairs)
            all_confusion_count += confusion_count

    all_ref_hits.sort(key=lambda h: h["ts"] or "")
    all_conf_pairs.sort(key=lambda p: p["ts"] or "")

    if args.json:
        json.dump({
            "reference_hits": all_ref_hits,
            "confusion_pairs": all_conf_pairs,
            "all_confusion_matches": all_confusion_count,
        }, sys.stdout, indent=2)
        print()
        return

    print(build_report(all_ref_hits, all_conf_pairs, all_confusion_count, args.examples))


if __name__ == "__main__":
    main()
