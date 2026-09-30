#!/usr/bin/env python3
# DESC: Extract a session transcript's user, assistant and sub-agent text as ordered plain text
"""
extract-session-text: Turn a Claude Code transcript (.jsonl) into ordered plain
text so a very large session can be read in chunks or mined for lessons.

The input is a transcript path or a session id; an id is resolved by searching
${CLAUDE_CONFIG_DIR:-~/.claude}/projects/*/<id>.jsonl (then every other config
dir claude_dirs.py knows). Each entry is printed under a numbered header
carrying its kind and time. Kinds:

  user       typed messages, queued messages, compaction summaries, recaps
  assistant  the assistant's text blocks (not its tool calls)
  agents     sub-agent spawn prompts, SendMessage calls, questions asked of
             the user, and the hand-back results that answer them
  tools      every other tool result (off by default; can be huge)

Sidechain (sub-agent internal) entries are never included.

Example:
  extract-session-text.py edb80266-8503-443e-8398-d29d6002e446 --out session.txt
  extract-session-text.py session.jsonl --kinds user,agents --chunk-chars 60000 --out /tmp/s/chunk
  extract-session-text.py session.jsonl --grep 'rebuild' --since 2026-09-20
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claude_dirs import find_transcript  # noqa: E402

KINDS = ("user", "assistant", "agents", "tools")
AGENT_TOOLS = ("Agent", "SendMessage", "AskUserQuestion")
UUID_ONLY = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def resolve(arg):
    p = Path(arg).expanduser()
    if p.is_file():
        return p
    if UUID_ONLY.match(arg):
        cfg = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
        for m in sorted(Path(cfg).glob(f"projects/*/{arg}.jsonl")):
            return m
        found, _ = find_transcript(arg)
        if found:
            return Path(found)
    sys.exit(f"extract-session-text: no transcript for '{arg}'")


def result_text(x):
    cc = x.get("content")
    if isinstance(cc, list):
        cc = "\n".join(y.get("text", "") for y in cc if y.get("type") == "text")
    return str(cc)


def entries(path, want):
    """Yield (group, label, timestamp, text) in transcript order."""
    tool_names = {}  # tool_use_id -> tool name
    for raw in open(path, encoding="utf-8"):
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            continue
        t, ts = d.get("type"), d.get("timestamp", "")
        if t == "system" and d.get("subtype") == "away_summary":
            yield "user", "RECAP", ts, d.get("content", "")
        if t == "queue-operation" and d.get("operation") == "enqueue":
            yield "user", "USER(queued)", ts, d.get("content", "")
        if t not in ("user", "assistant") or d.get("isSidechain"):
            continue
        c = d["message"]["content"]
        if t == "user":
            if isinstance(c, str):
                label = "USER"
                if d.get("isCompactSummary"):
                    label = "COMPACT-SUMMARY"
                elif "<task-notification>" in c:
                    label = "NOTIFY"
                elif d.get("isMeta"):
                    label = "META"
                yield "user", label, ts, c
                continue
            for x in c:
                if x.get("type") == "text":
                    yield "user", "USER", ts, x["text"]
                elif x.get("type") == "tool_result":
                    name = tool_names.get(x.get("tool_use_id"))
                    if name in AGENT_TOOLS:
                        yield "agents", "RESULT " + name, ts, result_text(x)
                    elif "tools" in want:
                        yield "tools", "TOOL-RESULT " + (name or "?"), ts, result_text(x)
        else:
            for x in c:
                if x.get("type") == "text":
                    yield "assistant", "ASSISTANT", ts, x["text"]
                elif x.get("type") == "tool_use":
                    tool_names[x["id"]] = x["name"]
                    inp = x.get("input", {})
                    if x["name"] == "Agent":
                        yield "agents", "AGENT-SPAWN", ts, f"{inp.get('description')}\n{inp.get('prompt', '')[:4000]}"
                    elif x["name"] == "SendMessage":
                        yield "agents", "SENDMSG", ts, json.dumps(inp, ensure_ascii=False)[:3000]
                    elif x["name"] == "AskUserQuestion":
                        yield "agents", "ASK", ts, json.dumps(inp, ensure_ascii=False)[:4000]


def is_noise(label, text):
    if label == "META" and text.startswith("Another Claude session"):
        return True
    if "task-notification" in text and "delivered to you as a message" in text:
        return True
    if label.startswith("RESULT") and "Async agent launched" in text:
        return True
    return False


def main():
    ap = argparse.ArgumentParser(
        description="Extract a Claude Code transcript's messages as ordered plain text.",
        epilog="example: extract-session-text.py <session-id> --kinds user,assistant --chunk-chars 60000 --out /tmp/s/chunk",
    )
    ap.add_argument("session", help="transcript .jsonl path, or a session id")
    ap.add_argument("--kinds", default="user,assistant,agents",
                    help=f"comma list of {','.join(KINDS)} (default: user,assistant,agents)")
    ap.add_argument("--out", help="output file; stdout if omitted. With --chunk-chars, a prefix for <out>-001.txt, ...")
    ap.add_argument("--chunk-chars", type=int, metavar="N",
                    help="write numbered chunk files of about N characters (needs --out); entries are never split")
    ap.add_argument("--since", metavar="YYYY-MM-DD[THH:MM]", help="keep entries at or after this UTC timestamp")
    ap.add_argument("--grep", metavar="REGEX", help="keep entries whose text matches (case-insensitive)")
    a = ap.parse_args()

    want = {k.strip() for k in a.kinds.split(",") if k.strip()}
    bad = want - set(KINDS)
    if bad or not want:
        ap.error(f"--kinds takes {', '.join(KINDS)}")
    if a.chunk_chars and not a.out:
        ap.error("--chunk-chars needs --out")
    rx = re.compile(a.grep, re.I) if a.grep else None

    blocks, n = [], 0
    for group, label, ts, text in entries(resolve(a.session), want):
        if group not in want or is_noise(label, text):
            continue
        if a.since and ts and ts < a.since:
            continue
        if rx and not rx.search(text):
            continue
        if "Base directory for this skill" in text:
            text = text[:300]
        n += 1
        blocks.append(f"\n===== [{n}] {label} {ts[11:19] if ts else ''} =====\n{text.strip()}\n")

    total = sum(len(b) for b in blocks)
    if a.chunk_chars:
        chunks, cur, size = [], [], 0
        for b in blocks:
            if cur and size + len(b) > a.chunk_chars:
                chunks.append(cur)
                cur, size = [], 0
            cur.append(b)
            size += len(b)
        if cur:
            chunks.append(cur)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        for i, ch in enumerate(chunks, 1):
            Path(f"{a.out}-{i:03d}.txt").write_text("".join(ch), encoding="utf-8")
        print(f"{n} entries, {total} chars, {len(chunks)} chunks", file=sys.stderr)
    elif a.out:
        Path(a.out).write_text("".join(blocks), encoding="utf-8")
        print(f"{n} entries, {total} chars", file=sys.stderr)
    else:
        sys.stdout.write("".join(blocks))
        print(f"{n} entries, {total} chars", file=sys.stderr)


if __name__ == "__main__":
    main()
