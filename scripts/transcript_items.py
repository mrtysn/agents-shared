"""One normalized stream over Claude Code transcripts.

Every script that reads ~/.claude/projects/**/*.jsonl goes through here, so the
transcript format is parsed in one place. `transcripts()` finds the files across
every config dir; `items()` turns one file into a flat stream of dicts, one per
content block, in transcript order:

  group       user | assistant | agents | tools | calls | attachments | thinking
  label       USER, ASSISTANT, AGENT-SPAWN, CALL Bash, TOOL-RESULT Read, ...
  text        the block's text (a tool call's text is its command or path)
  tool        tool name, on calls and results
  tool_use_id links a call to its result
  input       the call's input dict, on calls and on sub-agent/question calls
  delivered   on USER(queued) rows: True once Claude Code has folded the message into the turn
              (or run it at the turn's end), False while it still waits in the queue

plus entry-level fields every item carries: session, project, time, cwd, line,
sidechain, meta, origin, api_error, and for user/assistant entries entry_type
("user" or "assistant") and content_kind ("str" when the message content is a
plain string, "list" when it is a block list). Callers apply their own predicates
over those fields (what counts as a typed human prompt differs between scripts).

A user or assistant entry with no text, tool call or tool result block
(thinking only, an image only, no content) yields one marker item, group "empty", label "EMPTY",
text "", so a caller counting turns or delimiting them still sees the entry.
Pass want without "empty" to leave markers out.

`agents` holds sub-agent spawns, SendMessage, AskUserQuestion and their results;
`tools` every other tool result; `calls` every other tool call; `attachments` the rule
text a path match loaded (label RULE-LOADED <file>, with path and globs) and the context
a hook added (label HOOK-CONTEXT <hook>, with hook, hook_event and tool_use_id). A caller
gets attachments only by naming the group in want; want=None leaves them out.

`thinking` holds the assistant's thinking blocks that carry words, and is built only when
want names it. Label NARRATION is a block the API server made from reply text written
between tool calls: a short summary of that text, stored with no text block. Label THINKING
is reasoning. A caller that asks "did the assistant write anything since X" selects
NARRATION; reasoning was never addressed to the user. An entry whose only
block is thinking still yields its EMPTY marker when the group is not named.
"""

import base64
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


def thinking_label(signature):
    """NARRATION for a thinking block the server made from reply text written between tool
    calls, THINKING for reasoning. The kind is a word in the first 30 bytes of the base64
    signature; a signature that is missing or does not decode is THINKING."""
    try:
        head = base64.b64decode((signature or "")[:40])
    except (ValueError, TypeError):
        return "THINKING"
    return "NARRATION" if b"narration" in head else "THINKING"


def blocks(d, t, c, tool_names, keep, thinking=False):
    """The content blocks of one user or assistant entry as (group, label, text, extra).

    text is None for a block that exists but whose group is not wanted, so the caller
    can tell an entry with no blocks from one whose blocks were filtered out."""
    if c is None:
        return
    if t == "user":
        if isinstance(c, str):
            label = "USER"
            if d.get("isCompactSummary"):
                label = "COMPACT-SUMMARY"
            elif "<task-notification>" in c:
                label = "NOTIFY"
            elif d.get("isMeta"):
                label = "META"
            yield "user", label, c if keep("user") else None, {}
            return
        for x in c:
            if x.get("type") == "text":
                yield "user", "USER", x["text"] if keep("user") else None, {}
            elif x.get("type") == "tool_result":
                name = tool_names.get(x.get("tool_use_id"))
                group = "agents" if name in AGENT_TOOLS else "tools"
                label = ("RESULT " if group == "agents" else "TOOL-RESULT ") + (name or "?")
                yield group, label, result_text(x) if keep(group) else None, {"tool": name, "tool_use_id": x.get("tool_use_id")}
        return
    for x in c:
        if x.get("type") == "text":
            yield "assistant", "ASSISTANT", x["text"] if keep("assistant") else None, {}
        elif x.get("type") == "thinking" and thinking and (x.get("thinking") or "").strip():
            yield "thinking", thinking_label(x.get("signature")), x["thinking"], {}
        elif x.get("type") == "tool_use":
            tool_names[x["id"]] = x["name"]
            inp = x.get("input", {})
            name = x["name"]
            extra = {"tool": name, "tool_use_id": x["id"], "input": inp}
            if name == "Agent":
                yield "agents", "AGENT-SPAWN", f"{inp.get('description')}\n{inp.get('prompt', '')[:4000]}", extra
            elif name == "SendMessage":
                yield "agents", "SENDMSG", json.dumps(inp, ensure_ascii=False)[:3000], extra
            elif name == "AskUserQuestion":
                yield "agents", "ASK", json.dumps(inp, ensure_ascii=False)[:4000], extra
            else:
                yield "calls", "CALL " + name, call_text(inp), extra


def attachments(a, item):
    """The items of one attachment entry that carry instruction text Claude Code put into the
    session: a rule loaded because a matching file was touched (nested_memory) and the context
    a hook added (hook_additional_context). Every other attachment type yields nothing."""
    kind = a.get("type")
    if kind == "nested_memory":
        c = a.get("content")
        text = c.get("content") if isinstance(c, dict) else c
        yield item("attachments", "RULE-LOADED " + os.path.basename(a.get("path") or "?"), str(text or ""),
                   path=a.get("path"), globs=(c or {}).get("globs") if isinstance(c, dict) else None)
    elif kind == "hook_additional_context":
        c = a.get("content")
        text = "\n".join(str(x) for x in c) if isinstance(c, list) else str(c or "")
        yield item("attachments", "HOOK-CONTEXT " + (a.get("hookName") or "?"), text,
                   hook=a.get("hookName"), hook_event=a.get("hookEvent"), tool_use_id=a.get("toolUseID"))


def items(path, project="", session=None, want=None):
    """Yield one dict per content block of a transcript, in order.

    want limits the groups built (a set of group names); None builds all."""
    session = session or os.path.basename(path)[:-6]
    tool_names = {}  # tool_use_id -> tool name
    queue = None  # enqueue line -> state, replayed on the first queued message

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
                if queue is None:
                    queue = {e["line"]: e["state"] for e in replay_queue(path)}
                # delivered: Claude Code has put this message in front of the model (folded into the
                # running turn, or run at the turn's end). A queued plain message that is not delivered yet
                # has not been seen, so nothing the model did before it can be a failure to answer it.
                yield item("user", "USER(queued)", d.get("content", ""),
                           delivered=queue.get(line_no) in ("removed", "dequeued"))
            if t == "attachment" and want is not None and "attachments" in want:
                yield from attachments(d.get("attachment") or {}, item)
            if t not in ("user", "assistant"):
                continue
            c = (d.get("message") or {}).get("content")
            base["entry_type"] = t
            base["content_kind"] = "str" if isinstance(c, str) else "list"
            seen = False
            for group, label, text, extra in blocks(d, t, c, tool_names, keep, want is not None and "thinking" in want):
                seen = True
                if text is not None and keep(group):
                    yield item(group, label, text, **extra)
            if not seen and keep("empty"):
                yield item("empty", "EMPTY", "")


def _queue_key(content):
    # A cross-session message is enqueued with a hop-chain="…" attribute that its remove record
    # leaves out; matched exactly, the message stayed queued and a later dequeue popped it instead
    # of the slash command behind it.
    return re.sub(r' hop-chain="[^"]*"', "", content.strip())


def replay_queue(path):
    """Replay the transcript's queue records into one entry per message the user queued.

    Claude Code folds a queued plain-text message into the running turn (a `remove` record follows
    its `enqueue` within seconds), but holds a queued slash command until the turn ends (`dequeue`).
    `enqueue` appends, `remove` drops the entry with its content, `dequeue` (which carries no content)
    takes the head, and `popAll` (the user pulled the queue back into the prompt) empties it.
    Returns [{"line", "time", "content", "state"}] in enqueue order; line is the 0-based line of the
    enqueue record (the `line` of the reader's USER(queued) row) and state is "queued" (still
    waiting), "removed" (folded into the turn), "dequeued" (run at the turn's end) or "popped".
    """
    entries, waiting = [], []
    with open(path, encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh):
            if '"queue-operation"' not in raw:
                continue
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "queue-operation":
                continue
            op, content = d.get("operation"), d.get("content") or ""
            if op == "enqueue":
                entry = {"line": line_no, "time": d.get("timestamp", ""), "content": content.strip(), "state": "queued"}
                entries.append(entry)
                waiting.append(entry)
            elif op == "popAll":
                for e in waiting:
                    e["state"] = "popped"
                waiting = []
            elif op == "dequeue":
                if waiting:
                    waiting.pop(0)["state"] = "dequeued"
            elif op == "remove":
                for i, e in enumerate(waiting):
                    if _queue_key(e["content"]) == _queue_key(content):
                        waiting.pop(i)["state"] = "removed"
                        break
    return entries


def pending_queued_commands(path):
    """The slash commands the user queued that Claude Code has not delivered yet.

    Returns [{"time", "content"}], oldest first (see replay_queue for how the queue is replayed).
    """
    return [{"time": e["time"], "content": e["content"]} for e in replay_queue(path)
            if e["state"] == "queued" and e["content"].startswith("/")]


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


def is_reply_boundary(it):
    """True for an item that ends the assistant's turn from the user's side: a typed prompt, or the
    answer to an AskUserQuestion call (the user's choice, typed text, or rejection). A question a
    PreToolUse hook refused never reached the user, so its result is not a reply."""
    return is_typed_prompt(it) or (it["label"] == "RESULT AskUserQuestion" and not it["sidechain"]
                                   and not it["text"].lstrip().startswith("PreToolUse:"))


def since_last_user(rows):
    """The rows after the last user reply in one session's items, in order.

    A reply is a typed prompt or an AskUserQuestion answer (see is_reply_boundary), so the
    result is what the assistant has done since the user last spoke. rows must have been
    built with the user and agents groups, or the boundary is not visible. With no reply at
    all, every row is returned."""
    last = max((n for n, it in enumerate(rows) if is_reply_boundary(it)), default=-1)
    return rows[last + 1:]


def clip_input(value, limit):
    """Copy of a tool input with every string value cut to limit characters."""
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + f"...[{len(value) - limit} more]"
    if isinstance(value, dict):
        return {k: clip_input(v, limit) for k, v in value.items()}
    if isinstance(value, list):
        return [clip_input(v, limit) for v in value]
    return value
