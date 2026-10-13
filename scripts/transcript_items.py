"""One normalized stream over Claude Code transcripts.

Every script that reads ~/.claude/projects/**/*.jsonl goes through here, so the
transcript format is parsed in one place. `transcripts()` finds the files across
every config dir; `items()` turns one file into a flat stream of dicts, one per
content block, in transcript order:

  group       user | assistant | agents | tools | calls
  label       USER, ASSISTANT, AGENT-SPAWN, CALL Bash, TOOL-RESULT Read, ...
  text        the block's text (a tool call's text is its command or path)
  tool        tool name, on calls and results
  tool_use_id links a call to its result
  input       the call's input dict, on calls and on sub-agent/question calls

plus entry-level fields every item carries: session, project, time, cwd, line,
sidechain, meta, origin, api_error. Callers apply their own predicates over those
fields (what counts as a typed human prompt differs between scripts).

`agents` holds sub-agent spawns, SendMessage, AskUserQuestion and their results;
`tools` every other tool result; `calls` every other tool call.
"""

import glob
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claude_dirs import config_dirs  # noqa: E402

AGENT_TOOLS = ("Agent", "SendMessage", "AskUserQuestion")
HOME_SLUG = os.path.expanduser("~").replace("/", "-") + "-"
NOT_TYPED = ("<system-reminder", "<command-", "<local-command", "<task-notification", "[Request interrupted",
             "<agent-message", "<cross-session-message", "<teammate-message", "Another Claude session")


def result_text(x):
    cc = x.get("content")
    if isinstance(cc, list):
        cc = "\n".join(y.get("text", "") for y in cc if y.get("type") == "text")
    return str(cc)


def call_text(inp):
    """The part of a tool call worth reading: its command, path or pattern."""
    for key in ("command", "file_path", "pattern", "url", "query", "skill", "description"):
        if isinstance(inp.get(key), str) and inp[key]:
            return inp[key]
    return json.dumps(inp, ensure_ascii=False)


def transcripts(project=None, days=None, mention=None, subagents=False, exclude=(), config_dir_list=None):
    """Yield (path, project, session) for transcripts under every config dir.

    project   substring of the project folder name, without the home prefix
    days      skip files not modified in the last N days
    mention   regex; keep only files whose text matches it anywhere
    subagents also yield each session's sub-agent transcripts
    exclude   session id prefixes to leave out
    """
    cutoff = time.time() - days * 86400 if days else None
    rx = re.compile(mention) if mention else None
    for cfg in config_dir_list if config_dir_list is not None else config_dirs():
        patterns = [f"{cfg}/projects/*/*.jsonl"]
        if subagents:
            patterns.append(f"{cfg}/projects/*/*/subagents/*.jsonl")
        for pattern in patterns:
            for path in sorted(glob.glob(pattern)):
                parts = path.split("/")
                if "subagents" in parts:
                    folder, session = parts[-4], parts[-3]
                else:
                    folder, session = parts[-2], parts[-1][:-6]
                name = folder.removeprefix(HOME_SLUG) or "~"
                if project and project not in name:
                    continue
                if any(session.startswith(x) for x in exclude):
                    continue
                if cutoff and os.path.getmtime(path) < cutoff:
                    continue
                if rx:
                    try:
                        if not rx.search(Path(path).read_text(encoding="utf-8", errors="replace")):
                            continue
                    except OSError:
                        continue
                yield path, name, session


def items(path, project="", session=None, want=None):
    """Yield one dict per content block of a transcript, in order.

    want limits the groups built (a set of group names); None builds all."""
    session = session or os.path.basename(path)[:-6]
    tool_names = {}  # tool_use_id -> tool name

    def keep(group):
        return want is None or group in want

    with open(path, encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh):
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                continue
            t = d.get("type")
            base = {
                "session": session, "project": project, "time": d.get("timestamp", ""), "cwd": d.get("cwd", ""),
                "line": line_no, "sidechain": bool(d.get("isSidechain")), "meta": bool(d.get("isMeta")),
                "origin": (d.get("origin") or {}).get("kind"), "api_error": bool(d.get("isApiErrorMessage")),
            }

            def item(group, label, text, **extra):
                return {**base, "group": group, "label": label, "text": text, **extra}

            if t == "system" and d.get("subtype") == "away_summary" and keep("user"):
                yield item("user", "RECAP", d.get("content", ""))
            if t == "queue-operation" and d.get("operation") == "enqueue" and keep("user"):
                yield item("user", "USER(queued)", d.get("content", ""))
            if t not in ("user", "assistant"):
                continue
            c = (d.get("message") or {}).get("content")
            if c is None:
                continue
            if t == "user":
                if isinstance(c, str):
                    label = "USER"
                    if d.get("isCompactSummary"):
                        label = "COMPACT-SUMMARY"
                    elif "<task-notification>" in c:
                        label = "NOTIFY"
                    elif d.get("isMeta"):
                        label = "META"
                    if keep("user"):
                        yield item("user", label, c)
                    continue
                for x in c:
                    if x.get("type") == "text":
                        if keep("user"):
                            yield item("user", "USER", x["text"])
                    elif x.get("type") == "tool_result":
                        name = tool_names.get(x.get("tool_use_id"))
                        group = "agents" if name in AGENT_TOOLS else "tools"
                        label = ("RESULT " if group == "agents" else "TOOL-RESULT ") + (name or "?")
                        if keep(group):
                            yield item(group, label, result_text(x), tool=name, tool_use_id=x.get("tool_use_id"))
            else:
                for x in c:
                    if x.get("type") == "text":
                        if keep("assistant"):
                            yield item("assistant", "ASSISTANT", x["text"])
                    elif x.get("type") == "tool_use":
                        tool_names[x["id"]] = x["name"]
                        inp = x.get("input", {})
                        name = x["name"]
                        extra = {"tool": name, "tool_use_id": x["id"], "input": inp}
                        if name == "Agent":
                            if keep("agents"):
                                yield item("agents", "AGENT-SPAWN", f"{inp.get('description')}\n{inp.get('prompt', '')[:4000]}", **extra)
                        elif name == "SendMessage":
                            if keep("agents"):
                                yield item("agents", "SENDMSG", json.dumps(inp, ensure_ascii=False)[:3000], **extra)
                        elif name == "AskUserQuestion":
                            if keep("agents"):
                                yield item("agents", "ASK", json.dumps(inp, ensure_ascii=False)[:4000], **extra)
                        elif keep("calls"):
                            yield item("calls", "CALL " + name, call_text(inp), **extra)


def is_typed_prompt(it):
    """True for an item that is something a person typed: not injected, not a tool result."""
    return (it["group"] == "user" and it["label"] in ("USER", "USER(queued)") and not it["sidechain"]
            and not it["meta"] and bool(it["text"].strip()) and not it["text"].lstrip().startswith(NOT_TYPED))


def add_next_user(rows):
    """Set next_user on every row: the next typed prompt later in the same session, or None.

    rows must be one session's items in order."""
    nxt = None
    for it in reversed(rows):
        it["next_user"] = nxt
        if is_typed_prompt(it):
            nxt = it["text"]
    return rows


def clip_input(value, limit):
    """Copy of a tool input with every string value cut to limit characters."""
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + f"...[{len(value) - limit} more]"
    if isinstance(value, dict):
        return {k: clip_input(v, limit) for k, v in value.items()}
    if isinstance(value, list):
        return [clip_input(v, limit) for v in value]
    return value
