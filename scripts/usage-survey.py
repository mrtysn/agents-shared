#!/usr/bin/env python3
"""
usage-survey: profile how Claude Code is actually used, from the transcripts.

Streams every session transcript under each Claude config dir (never loads a
file whole) plus the config dir's history.jsonl, and aggregates:

  - sessions per project and per ISO week, date range, short sessions
  - tool-use counts overall and per project, including sub-agent transcripts
  - Skill invocations and typed slash commands
  - Bash verb histogram (first token; two tokens for git/docker/ssh/npm/uv/...)
  - user-prompt shapes: opener trigrams, length buckets, question / imperative /
    wish / url / error-paste / ack classes, and question prompts that were
    answered with an edit
  - assistant judgment phrases ("looks like", "I'll assume", "ambiguous", ...)
  - hook fires: PreToolUse blocks (tool_result "hook error"), hook asks
    (permissionDecision in hook stdout), user interruptions
  - stalls: consecutive typed prompts with no tool use between them
  - Agent spawns (subagent_type, model, description) and sub-agent models
  - memory writes by file
  - correction moments: typed prompts opening with no / wrong / stop / don't /
    "I said" / again, paired with the assistant's preceding action

Built for the shadow-mode evaluation of a local decision model (system-one):
the same extraction feeds the labelled samples, so keep the field names stable.

Usage:
  usage-survey.py                 text tables to stdout
  usage-survey.py --json          one JSON object with every aggregate
  usage-survey.py --since 2026-08-01
  usage-survey.py --samples 20    also print sample corrections / judgments
"""

import argparse
import collections
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from claude_dirs import config_dirs  # noqa: E402

# ---------------------------------------------------------------- constants

TWO_TOKEN_VERBS = {
    "git", "docker", "ssh", "npm", "uv", "gh", "brew", "make", "launchctl",
    "adb", "godot", "pnpm", "yarn", "cargo", "pip", "pip3", "python3", "python",
    "uvx", "npx", "systemctl", "kubectl", "xcodebuild", "swift", "go", "gradle",
}
ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
WRAPPERS = {"sudo", "nohup", "time", "env", "command", "exec", "caffeinate"}
SEGMENT_SPLIT = re.compile(r"\s*(?:&&|\|\||;|\||\n)\s*")
HEREDOC_RE = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\1\s*(?:\n|$)", re.DOTALL)
SHELL_NOISE = re.compile(r"^[^A-Za-z]")

QUESTION_WORDS = {
    "what", "why", "how", "is", "are", "can", "could", "do", "does", "did",
    "should", "would", "will", "which", "where", "when", "who", "any", "isn't",
    "aren't", "shall", "was", "were", "has", "have", "am", "whats", "hows",
    "dont", "doesnt", "didnt", "wouldnt", "shouldnt", "cant",
}
WISH_OPENERS = (
    "i want", "i'd like", "i would like", "it would be nice", "it'd be nice",
    "would be nice", "i wish", "i need", "i'd love", "i would love", "it would be good",
)
ACK_WORDS = {
    "yes", "y", "ok", "okay", "go", "do it", "go ahead", "no", "sure", "yep",
    "yup", "nope", "continue", "proceed", "k", "yes please", "correct", "right",
    "good", "great", "thanks", "thank you", "done", "next", "fine", "agreed",
}
ERROR_PASTE = re.compile(
    r"(Traceback \(most recent|\bError:|\berror:|Exception\b|\bfatal:|npm ERR|panic:|"
    r"SyntaxError|TypeError|ENOENT|command not found|Permission denied|"
    r"Segmentation fault|zsh: |bash: |exit code [1-9])"
)
URL_RE = re.compile(r"^(https?://|file://)\S+\s*$")
CORRECTION_RE = re.compile(
    r"\b(no|wrong|stop|don't|dont|do not|again|not what|i said|i asked|i told|"
    r"why did you|you didn't|you did not|that's not|thats not|undo|revert)\b",
    re.IGNORECASE,
)
JUDGMENT_PHRASES = [
    "is this a question", "should i", "looks like", "seems", "i'll assume",
    "i'm assuming", "assuming", "ambiguous", "which of", "before i",
    "i'll treat", "reading this as", "i take this as", "i read this as",
    "not sure whether", "unclear whether", "do you want", "shall i",
    "want me to", "let me know if", "i'll go with", "i'll interpret",
]
JUDGMENT_RE = re.compile("|".join(re.escape(p) for p in JUDGMENT_PHRASES), re.IGNORECASE)
HOOK_ERROR_RE = re.compile(r"PreToolUse:(\w+) hook error: \[(.*?)\]: (.*)", re.DOTALL)
HOOK_SCRIPT_RE = re.compile(r"hooks/([\w-]+)\.sh")
USER_INTERRUPT_RE = re.compile(
    r"(Request interrupted by user|The user doesn't want to (?:proceed|take this action)|"
    r"user rejected|User rejected|\[Request interrupted)"
)
COMMAND_NAME_RE = re.compile(r"<command-name>/?([\w:-]+)</command-name>")
LENGTH_BUCKETS = [(5, "<=5w"), (15, "6-15w"), (40, "16-40w"), (100, "41-100w"), (10 ** 9, ">100w")]


# ---------------------------------------------------------------- helpers

def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def slug_name(slug):
    """Project slug -> short name: last path component of the decoded path."""
    if slug == os.path.expanduser("~").replace("/", "-"):
        return "home"
    decoded = slug.replace("-", "/")
    base = os.path.basename(decoded.rstrip("/"))
    if slug.startswith("-private-tmp") or slug.startswith("-private-var"):
        return "scratch:" + base
    return base or slug


def words(text):
    return re.findall(r"[\w'’]+", text.lower())


def length_bucket(n):
    for limit, label in LENGTH_BUCKETS:
        if n <= limit:
            return label
    return LENGTH_BUCKETS[-1][1]


def classify_prompt(text):
    t = text.strip()
    low = t.lower()
    if t.startswith("/") or "<command-name>" in t:
        return "slash"
    if URL_RE.match(t):
        return "url"
    if ERROR_PASTE.search(t) and len(t) > 120:
        return "error-paste"
    if low in ACK_WORDS or (len(words(low)) <= 2 and low.rstrip(".!") in ACK_WORDS):
        return "ack"
    if any(low.startswith(w) for w in WISH_OPENERS):
        return "wish"
    first_line = low.splitlines()[0] if low else ""
    ws = words(first_line)
    if t.endswith("?") or (ws and ws[0] in QUESTION_WORDS):
        return "question"
    if "?" in first_line:
        return "question"
    return "imperative-or-statement"


def bash_verbs(command):
    """(primary_verb, [all segment verbs]) for one Bash command string."""
    verbs = []
    command = HEREDOC_RE.sub("<<HEREDOC\n", command)
    for seg in SEGMENT_SPLIT.split(command.strip()):
        toks = seg.strip().split()
        while toks and (ENV_ASSIGN.match(toks[0]) or toks[0] in WRAPPERS):
            toks.pop(0)
        if not toks:
            continue
        head = toks[0]
        if head in ("(", "{", "for", "while", "if", "do", "then", "fi", "done", "else", "elif", "case", "esac") or SHELL_NOISE.match(head):
            continue
        head = os.path.basename(head) if head.startswith(("/", "~", ".")) else head
        if head in TWO_TOKEN_VERBS and len(toks) > 1:
            sub = toks[1]
            if not sub.startswith("-"):
                head = f"{head} {sub}"
        verbs.append(head)
    primary = verbs[0] if verbs else "(empty)"
    if primary == "cd" and len(verbs) > 1:
        primary = verbs[1]
    return primary, verbs


def tool_summary(name, inp):
    if not isinstance(inp, dict):
        return name
    if name == "Bash":
        return "Bash: " + (inp.get("command") or "")[:70].replace("\n", " ")
    if name in ("Edit", "Write", "Read", "MultiEdit"):
        return f"{name}: {os.path.basename(inp.get('file_path') or '')}"
    if name in ("Agent", "Task"):
        return f"{name}: {inp.get('description') or ''}"
    if name == "Skill":
        return f"Skill: {inp.get('skill')}"
    return name


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


# ---------------------------------------------------------------- per-file scan

def scan_transcript(path, slug, sidechain=False):
    """One streamed pass over a transcript. Returns a dict of per-session facts."""
    s = {
        "slug": slug,
        "project": slug_name(slug),
        "session_id": os.path.basename(path)[:-6],
        "sidechain": sidechain,
        "first_ts": None, "last_ts": None,
        "typed_prompts": 0, "assistant_msgs": 0,
        "tools": collections.Counter(),
        "skills": collections.Counter(),
        "slash": collections.Counter(),
        "bash_primary": collections.Counter(),
        "bash_all": collections.Counter(),
        "prompt_class": collections.Counter(),
        "prompt_len": collections.Counter(),
        "openers": collections.Counter(),
        "judgments": collections.Counter(),
        "judgment_samples": [],
        "hook_blocks": collections.Counter(),
        "hook_asks": collections.Counter(),
        "hook_block_samples": [],
        "user_interrupts": 0,
        "stalls": 0, "stalls_after_question": 0,
        "question_then_edit": 0,
        "agent_spawns": [],
        "memory_writes": collections.Counter(),
        "corrections": [],
        "assistant_questions": 0,
        "bash_heredocs": 0,
        "correction_terms": collections.Counter(),
        "ask_user_question": 0,
        "queued_user_msgs": 0,
        "models": collections.Counter(),
        "cost_usd": 0.0,
        "ai_title": None,
        "compactions": 0,
    }
    last_tool = None            # summary of the last tool_use
    tools_since_prompt = 0
    edits_since_prompt = 0
    last_prompt_class = None
    last_assistant_text = ""
    last_prompt_text = ""

    try:
        fh = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return s
    with fh:
        for line in fh:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = e.get("type")
            ts = e.get("timestamp")
            if ts and t in ("user", "assistant"):
                if s["first_ts"] is None or ts < s["first_ts"]:
                    s["first_ts"] = ts
                if s["last_ts"] is None or ts > s["last_ts"]:
                    s["last_ts"] = ts

            if t == "ai-title":
                s["ai_title"] = e.get("aiTitle")
                continue
            if t == "queue-operation":
                s["queued_user_msgs"] += 1
                continue
            if t == "cost-state":
                s["cost_usd"] = e.get("totalCostUSD") or s["cost_usd"]
                for model, u in (e.get("modelUsage") or {}).items():
                    s["models"][model] = (u.get("inputTokens", 0) + u.get("outputTokens", 0)
                                          + u.get("cacheReadInputTokens", 0))
                continue
            if t == "system" and e.get("subtype") == "compact_boundary":
                s["compactions"] += 1
                continue
            if t == "attachment":
                a = e.get("attachment") or {}
                if a.get("type") == "hook_success" and "permissionDecision" in (a.get("stdout") or ""):
                    try:
                        out = json.loads(a["stdout"])
                        dec = out["hookSpecificOutput"]["permissionDecision"]
                    except (ValueError, KeyError, TypeError):
                        dec = "?"
                    m = HOOK_SCRIPT_RE.search(a.get("command") or "")
                    script = m.group(1) if m else (a.get("hookName") or "?")
                    s["hook_asks"][f"{script}:{dec}"] += 1
                continue
            if t not in ("user", "assistant"):
                continue

            msg = e.get("message") or {}
            content = msg.get("content")

            if t == "user":
                if isinstance(content, str) or (
                    isinstance(content, list) and content and all(
                        isinstance(b, dict) and b.get("type") == "text" for b in content)
                ):
                    text = text_of(content).strip()
                    if not text or text.startswith("<task-notification>") or text.startswith("<system-reminder>"):
                        continue
                    if text.startswith("<local-command"):
                        continue
                    # typed prompt
                    s["typed_prompts"] += 1
                    cls = classify_prompt(text)
                    s["prompt_class"][cls] += 1
                    ws = words(text.splitlines()[0]) if text else []
                    s["prompt_len"][length_bucket(len(words(text)))] += 1
                    m = COMMAND_NAME_RE.search(text)
                    if m:
                        s["slash"][m.group(1)] += 1
                    elif text.startswith("/"):
                        s["slash"][text.split()[0].lstrip("/")] += 1
                    if cls not in ("slash", "url", "error-paste") and ws:
                        s["openers"][" ".join(ws[:3])] += 1
                    # stall: previous prompt had no tool use after it
                    if s["typed_prompts"] > 1 and tools_since_prompt == 0:
                        s["stalls"] += 1
                        if last_assistant_text.rstrip().endswith("?"):
                            s["stalls_after_question"] += 1
                    if last_prompt_class == "question" and edits_since_prompt > 0:
                        s["question_then_edit"] += 1
                    head = " ".join(ws[:10])
                    cm = CORRECTION_RE.search(head)
                    if cm and cls not in ("slash", "url"):
                        s["correction_terms"][cm.group(1).lower()] += 1
                        s["corrections"].append({
                            "ts": ts, "prompt": text[:100].replace("\n", " "),
                            "prev_action": last_tool or "(text only)",
                            "prev_asked": last_assistant_text.rstrip().endswith("?"),
                        })
                    tools_since_prompt = 0
                    edits_since_prompt = 0
                    last_prompt_class = cls
                    last_prompt_text = text
                elif isinstance(content, list):
                    for b in content:
                        if not isinstance(b, dict) or b.get("type") != "tool_result":
                            continue
                        rtxt = text_of(b.get("content")) if not isinstance(b.get("content"), str) else b["content"]
                        if not isinstance(rtxt, str):
                            continue
                        m = HOOK_ERROR_RE.search(rtxt[:3000])
                        if m:
                            sm = HOOK_SCRIPT_RE.search(m.group(2))
                            script = sm.group(1) if sm else m.group(1)
                            s["hook_blocks"][script] += 1
                            if len(s["hook_block_samples"]) < 50:
                                s["hook_block_samples"].append(
                                    {"script": script, "msg": m.group(3)[:120].replace("\n", " "),
                                     "action": last_tool})
                        elif USER_INTERRUPT_RE.search(rtxt[:500]):
                            s["user_interrupts"] += 1
                continue

            # assistant
            s["assistant_msgs"] += 1
            model = msg.get("model")
            if model and sidechain:
                s["models"][model] += 1
            if not isinstance(content, list):
                continue
            for b in content:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "text":
                    txt = b.get("text") or ""
                    if txt.strip():
                        last_assistant_text = txt
                        if txt.rstrip().endswith("?"):
                            s["assistant_questions"] += 1
                        for jm in JUDGMENT_RE.finditer(txt):
                            key = jm.group(0).lower()
                            s["judgments"][key] += 1
                            if len(s["judgment_samples"]) < 40:
                                st = max(0, jm.start() - 60)
                                s["judgment_samples"].append(
                                    {"phrase": key, "ctx": txt[st:jm.end() + 80].replace("\n", " "),
                                     "prompt": last_prompt_text[:80].replace("\n", " ")})
                elif bt == "tool_use":
                    name = b.get("name") or "?"
                    inp = b.get("input") or {}
                    s["tools"][name] += 1
                    tools_since_prompt += 1
                    last_tool = tool_summary(name, inp)
                    if name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                        edits_since_prompt += 1
                        fp = inp.get("file_path") or ""
                        if "/memory/" in fp:
                            s["memory_writes"][os.path.basename(fp)] += 1
                    elif name == "Bash":
                        p, allv = bash_verbs(inp.get("command") or "")
                        s["bash_primary"][p] += 1
                        if "<<" in (inp.get("command") or ""):
                            s["bash_heredocs"] += 1
                        for v in allv:
                            s["bash_all"][v] += 1
                    elif name == "Skill":
                        s["skills"][inp.get("skill") or "?"] += 1
                    elif name in ("Agent", "Task"):
                        s["agent_spawns"].append({
                            "type": inp.get("subagent_type") or "general-purpose",
                            "model": inp.get("model") or "(inherit)",
                            "description": (inp.get("description") or "")[:60],
                            "prompt_len": len(inp.get("prompt") or ""),
                            "background": bool(inp.get("run_in_background")),
                        })
                    elif name == "AskUserQuestion":
                        s["ask_user_question"] += 1
    return s


# ---------------------------------------------------------------- history.jsonl

def scan_history(cfg, since):
    """Typed prompts from history.jsonl: fuller than transcripts for older dates."""
    path = os.path.join(cfg, "history.jsonl")
    out = {"count": 0, "first": None, "last": None, "per_week": collections.Counter(),
           "per_project": collections.Counter(), "slash": collections.Counter(),
           "openers": collections.Counter(), "classes": collections.Counter(),
           "sessions": set()}
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            ms = e.get("timestamp")
            if not ms:
                continue
            dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
            if since and dt < since:
                continue
            text = (e.get("display") or "").strip()
            if not text:
                continue
            out["count"] += 1
            out["first"] = min(out["first"] or dt, dt)
            out["last"] = max(out["last"] or dt, dt)
            iso = dt.isocalendar()
            out["per_week"][f"{iso[0]}-W{iso[1]:02d}"] += 1
            out["per_project"][os.path.basename((e.get("project") or "").rstrip("/")) or "?"] += 1
            if e.get("sessionId"):
                out["sessions"].add(e["sessionId"])
            cls = classify_prompt(text)
            out["classes"][cls] += 1
            if text.startswith("/"):
                out["slash"][text.split()[0].lstrip("/")] += 1
            elif cls not in ("url", "error-paste"):
                ws = words(text.splitlines()[0])
                if ws:
                    out["openers"][" ".join(ws[:3])] += 1
    out["sessions"] = len(out["sessions"])
    return out


# ---------------------------------------------------------------- aggregate

def merge_counter(dst, src):
    for k, v in src.items():
        dst[k] += v


def aggregate(sessions, history):
    main = [s for s in sessions if not s["sidechain"]]
    side = [s for s in sessions if s["sidechain"]]
    agg = {
        "files": len(sessions), "sessions": len(main), "subagent_transcripts": len(side),
        "first_ts": min((s["first_ts"] for s in main if s["first_ts"]), default=None),
        "last_ts": max((s["last_ts"] for s in main if s["last_ts"]), default=None),
        "sessions_per_week": collections.Counter(),
        "sessions_per_project": collections.Counter(),
        "prompts_per_project": collections.Counter(),
        "tools": collections.Counter(), "tools_subagent": collections.Counter(),
        "tools_per_project": collections.defaultdict(collections.Counter),
        "skills": collections.Counter(), "slash": collections.Counter(),
        "bash_primary": collections.Counter(), "bash_all": collections.Counter(),
        "prompt_class": collections.Counter(), "prompt_len": collections.Counter(),
        "openers": collections.Counter(), "judgments": collections.Counter(),
        "judgment_samples": [], "hook_blocks": collections.Counter(),
        "hook_asks": collections.Counter(), "hook_block_samples": [],
        "user_interrupts": 0, "stalls": 0, "stalls_after_question": 0,
        "question_then_edit": 0, "short_sessions": 0, "typed_prompts": 0,
        "assistant_msgs": 0, "assistant_questions": 0, "ask_user_question": 0,
        "queued_user_msgs": 0, "compactions": 0,
        "agent_spawns": 0, "agent_by_model": collections.Counter(),
        "agent_by_type": collections.Counter(), "agent_background": 0,
        "agent_descriptions": collections.Counter(),
        "subagent_models": collections.Counter(),
        "memory_writes": collections.Counter(), "corrections": [],
        "bash_heredocs": 0, "correction_terms": collections.Counter(),
        "cost_usd": 0.0, "model_tokens": collections.Counter(),
        "titled_sessions": 0,
        "history": history,
    }
    for s in main:
        dt = parse_ts(s["first_ts"])
        if dt:
            iso = dt.isocalendar()
            agg["sessions_per_week"][f"{iso[0]}-W{iso[1]:02d}"] += 1
        agg["sessions_per_project"][s["project"]] += 1
        agg["prompts_per_project"][s["project"]] += s["typed_prompts"]
        merge_counter(agg["tools"], s["tools"])
        merge_counter(agg["tools_per_project"][s["project"]], s["tools"])
        for key in ("skills", "slash", "bash_primary", "bash_all", "prompt_class",
                    "prompt_len", "openers", "judgments", "hook_blocks", "hook_asks",
                    "memory_writes", "model_tokens", "correction_terms"):
            merge_counter(agg[key], s[key if key != "model_tokens" else "models"])
        for key in ("user_interrupts", "stalls", "stalls_after_question", "question_then_edit",
                    "typed_prompts", "assistant_msgs", "assistant_questions",
                    "ask_user_question", "queued_user_msgs", "compactions", "bash_heredocs"):
            agg[key] += s[key]
        agg["cost_usd"] += s["cost_usd"] or 0
        if s["typed_prompts"] < 5:
            agg["short_sessions"] += 1
        if s["ai_title"]:
            agg["titled_sessions"] += 1
        agg["judgment_samples"].extend(s["judgment_samples"])
        agg["hook_block_samples"].extend(s["hook_block_samples"])
        for c in s["corrections"]:
            c = dict(c, project=s["project"], session=s["session_id"])
            agg["corrections"].append(c)
        for a in s["agent_spawns"]:
            agg["agent_spawns"] += 1
            agg["agent_by_model"][a["model"]] += 1
            agg["agent_by_type"][a["type"]] += 1
            agg["agent_background"] += a["background"]
            agg["agent_descriptions"][a["description"]] += 1
    for s in side:
        merge_counter(agg["tools_subagent"], s["tools"])
        merge_counter(agg["subagent_models"], s["models"])
        merge_counter(agg["bash_all"], s["bash_all"])
    return agg


# ---------------------------------------------------------------- output

def table(title, counter, n=25, total=None):
    print(f"\n## {title}")
    items = counter.most_common(n) if hasattr(counter, "most_common") else list(counter)[:n]
    width = max((len(str(k)) for k, _ in items), default=10)
    for k, v in items:
        pct = f"  {100 * v / total:5.1f}%" if total else ""
        print(f"  {str(k):<{width}}  {v:>6}{pct}")


def print_text(agg, samples):
    h = agg["history"]
    print("# usage-survey")
    print(f"transcripts: {agg['files']} files, {agg['sessions']} sessions, "
          f"{agg['subagent_transcripts']} sub-agent transcripts")
    print(f"transcript range: {agg['first_ts']} .. {agg['last_ts']}")
    if h["count"]:
        print(f"history.jsonl: {h['count']} typed prompts, {h['sessions']} sessions, "
              f"{h['first'].date()} .. {h['last'].date()}")
    print(f"typed prompts in transcripts: {agg['typed_prompts']}, assistant messages: {agg['assistant_msgs']}, "
          f"cost USD {agg['cost_usd']:.0f}")
    print(f"short sessions (<5 prompts): {agg['short_sessions']}, titled: {agg['titled_sessions']}, "
          f"compactions: {agg['compactions']}")
    table("sessions per week (transcripts)", collections.Counter(dict(sorted(agg["sessions_per_week"].items()))), 60)
    table("prompts per week (history.jsonl)", collections.Counter(dict(sorted(h["per_week"].items()))), 60)
    table("sessions per project", agg["sessions_per_project"], 30)
    table("typed prompts per project (history.jsonl)", h["per_project"], 30, h["count"])
    tot = sum(agg["tools"].values())
    table("tool use (main sessions)", agg["tools"], 30, tot)
    table("tool use (sub-agent transcripts)", agg["tools_subagent"], 15)
    for proj, c in agg["sessions_per_project"].most_common(8):
        table(f"tools: {proj}", agg["tools_per_project"][proj], 8)
    table("Skill tool invocations", agg["skills"], 40)
    table("typed slash commands (transcripts)", agg["slash"], 40)
    table("typed slash commands (history.jsonl)", h["slash"], 40)
    table("Bash primary verb", agg["bash_primary"], 40, sum(agg["bash_primary"].values()))
    table("Bash all-segment verbs (heredoc bodies stripped)", agg["bash_all"], 40)
    print(f"\nBash commands containing a heredoc: {agg['bash_heredocs']}")
    table("prompt classes (transcripts)", agg["prompt_class"], 10, agg["typed_prompts"])
    table("prompt classes (history.jsonl)", h["classes"], 10, h["count"])
    table("prompt length", agg["prompt_len"], 10, agg["typed_prompts"])
    table("prompt openers (history.jsonl, 3 words)", h["openers"], 30)
    table("assistant judgment phrases", agg["judgments"], 30)
    table("hook blocks (tool_result hook error)", agg["hook_blocks"], 20)
    table("hook asks (permissionDecision)", agg["hook_asks"], 20)
    print(f"\nuser interrupts: {agg['user_interrupts']}; stalls (re-prompt with no tool use): {agg['stalls']} "
          f"of which after an assistant question: {agg['stalls_after_question']}")
    print(f"question prompts followed by an edit before the next prompt: {agg['question_then_edit']}")
    print(f"assistant messages ending in '?': {agg['assistant_questions']}; AskUserQuestion: {agg['ask_user_question']}; "
          f"queued user messages while working: {agg['queued_user_msgs']}")
    print(f"\nagent spawns: {agg['agent_spawns']} (background {agg['agent_background']})")
    table("agent spawns by model", agg["agent_by_model"], 10)
    table("agent spawns by type", agg["agent_by_type"], 10)
    table("sub-agent transcript models (assistant msgs)", agg["subagent_models"], 10)
    table("model tokens (main sessions, cost-state)", agg["model_tokens"], 10)
    table("memory writes by file", agg["memory_writes"], 30)
    print(f"\ncorrection moments: {len(agg['corrections'])}")
    prev = collections.Counter(c["prev_action"].split(":")[0] for c in agg["corrections"])
    table("correction: preceding action kind", prev, 10)
    table("correction: opening term", agg["correction_terms"], 15)
    asked = sum(1 for c in agg["corrections"] if c["prev_asked"])
    print(f"  preceding assistant turn ended with a question: {asked}")
    if samples:
        print(f"\n## correction samples ({samples})")
        for c in agg["corrections"][:samples]:
            print(f"  [{c['project']}] {c['prompt'][:70]!r}  <- {c['prev_action'][:60]}")
        print(f"\n## judgment samples ({samples})")
        for j in agg["judgment_samples"][:samples]:
            print(f"  ({j['phrase']}) {j['ctx'][:140]!r}")
        print(f"\n## hook block samples ({samples})")
        for b in agg["hook_block_samples"][:samples]:
            print(f"  {b['script']}: {b['msg'][:90]}  <- {(b['action'] or '')[:50]}")


SIMPLIFY_RE = re.compile(
    r"\b(simpler|simplify|shorter|plainer|too long|less verbose|just answer|"
    r"be brief|tl;?dr|shorten|too much|less detail|more concise|too verbose)\b",
    re.IGNORECASE,
)

# --------------------------------------------------------- AskUserQuestion dump

# The tool_result Claude Code synthesises for an answered AskUserQuestion call:
#   The user answered: "Q1"="A1", "Q2"="A2". Read the answers carefully ...
# An unanswered item in a multi-question call reads
#   "Q"=(no option selected) notes: <free text>
# so the value side is either a quoted string or that bare marker plus
# whatever notes follow it up to the next `, "` or the trailing sentence.
ASK_QA_RE = re.compile(
    r'"((?:[^"\\]|\\.)*)"\s*=\s*(?:"((?:[^"\\]|\\.)*)"'
    r'|(\(no option selected\)(?:\s*notes:\s*.*?)?)(?=,\s*"|\.\s*Read the answers|\s*$))',
    re.S,
)
ROUTINE_ANSWER_RE = re.compile(
    r"\b(just do (it|that|whatever)|whatever you (think|want|prefer|say)|"
    r"you decide|your call|up to you|i don'?t (care|mind)|"
    r"whichever( you (prefer|think))?|go with (the )?(recommend|first|default)|"
    r"do what you think( is best)?)\b",
    re.IGNORECASE,
)
NAMING_OR_IRREVERSIBLE_RE = re.compile(
    r"\b(name|naming|alias|rename|call it|hostname|branch name|file ?name|"
    r"directory name|repo name|commit message|delete|remove|discard|drop|"
    r"commit|push|publish|send|share|email|post|overwrite|force[- ]?push|"
    r"merge|deploy|destroy|wipe)\b",
    re.IGNORECASE,
)
ASK_ROW_KEYS = ("answered_in_context", "routine_default", "naming_or_irreversible", "options_complete",
                "call", "index", "count", "project", "question_json", "answer", "recent")
ASK_NOT_A_PROMPT_RE = re.compile(r"\[Request interrupted|Base directory for this skill:|This session is being continued")
ASK_RECENT_PROMPTS = 5      # prompts kept per row; the harness cuts to state.recent_prompts
ASK_RECENT_CHARS = 600      # last chars kept per message; the harness cuts to state.recent_chars


def _ask_option_labels(options):
    return [re.sub(r"\s*\(recommended\)\s*", "", (o.get("label") or ""), flags=re.I).strip()
            for o in options]


def _options_complete(answer, options):
    """Heuristic for the options_complete gold label: 1 unless the answer reads
    as free text that does not match any offered option (the survey's "answered
    outside the offered options" cases)."""
    ans_low = answer.lower()
    ans_words = set(re.findall(r"[a-z0-9]+", ans_low))
    for label in _ask_option_labels(options):
        low = label.lower()
        if not low:
            continue
        if low in ans_low or ans_low in low:
            return 1
        label_words = {w for w in re.findall(r"[a-z0-9]+", low) if len(w) > 2}
        if label_words and len(label_words & ans_words) / len(label_words) >= 0.6:
            return 1
    return 0


def _answered_in_context(answer, recent_text):
    """Heuristic: does the answer's content already appear in the last 3 user
    prompts (the user stated it before being asked)?"""
    ans_words = {w for w in re.findall(r"[a-z0-9]{4,}", answer.lower())}
    if not ans_words:
        return 0
    recent_low = recent_text.lower()
    hits = sum(1 for w in ans_words if w in recent_low)
    return 1 if hits >= max(2, len(ans_words) * 0.5) else 0


def _routine_default(answer):
    a = answer.strip()
    # A bare pick of the recommended option, copied with its "(Recommended)"
    # suffix and no added commentary, is the conventional-default case (a
    # senior engineer would have picked it without asking); a longer answer
    # ending the same way still carries its own reasoning and is not this.
    if a.lower().endswith("(recommended)") and len(a) < 60:
        return 1
    return 1 if ROUTINE_ANSWER_RE.search(a) else 0


def _naming_or_irreversible(question):
    text = (question.get("question") or "") + " " + (question.get("header") or "")
    return 1 if NAMING_OR_IRREVERSIBLE_RE.search(text) else 0


def _flat(text):
    """One-line cell text: tabs and newlines escaped, the home directory
    scrubbed to ~ so a cases file never carries a machine path."""
    return text.replace("\t", " ").replace("\n", "\\n").replace(os.path.expanduser("~"), "~")


def _dump_asks_from(path, slug):
    """Yields one row dict per question of every answered AskUserQuestion call
    in one transcript (an ask the user rejected with Escape has no answer and
    is skipped). Heuristic labels only, same convention as _dump_one for
    --dump-prompts/--dump-stops: regex over the answer text and the
    question/header text, not a hand-graded pass over every row. The call id
    groups a multi-question call's rows so a whole-ask measurement can
    rebuild the call."""
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return
    with fh:
        lines = fh.readlines()
    parsed = []
    for line in lines:
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            parsed.append(None)

    recent_prompts = collections.deque(maxlen=ASK_RECENT_PROMPTS)
    last_assistant_text = ""
    session = os.path.basename(path)[:-6][:8]
    for i, e in enumerate(parsed):
        if e is None:
            continue
        t = e.get("type")
        msg = e.get("message") or {}
        content = msg.get("content")
        if t == "user":
            if isinstance(content, str) or (
                isinstance(content, list) and content and all(
                    isinstance(b, dict) and b.get("type") == "text" for b in content)
            ):
                text = text_of(content).strip()
                # Typed prompts only: skip harness markers, skill expansions
                # and interrupt notices, which the user did not write.
                if text and not text.startswith("<") and not ASK_NOT_A_PROMPT_RE.match(text):
                    recent_prompts.append(text)
            continue
        if t != "assistant" or not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                txt = b.get("text") or ""
                if txt.strip():
                    last_assistant_text = txt
                continue
            if b.get("type") != "tool_use" or b.get("name") != "AskUserQuestion":
                continue
            questions = (b.get("input") or {}).get("questions") or []
            if not questions:
                continue
            tool_id = b.get("id")
            # The matching tool_result is usually the next user entry, but a
            # progress or sidechain entry can sit between; search a bounded
            # window and stop at the entry that carries this id.
            answer_text = ""
            for j in range(i + 1, min(i + 40, len(parsed))):
                e2 = parsed[j]
                if not e2 or e2.get("type") != "user":
                    continue
                c2 = (e2.get("message") or {}).get("content")
                if not isinstance(c2, list):
                    continue
                for bb in c2:
                    if isinstance(bb, dict) and bb.get("type") == "tool_result" \
                            and bb.get("tool_use_id") == tool_id:
                        rc = bb.get("content")
                        answer_text = rc if isinstance(rc, str) else text_of(rc) or json.dumps(rc)
                if answer_text:
                    break
            if not answer_text:
                continue
            pairs = ASK_QA_RE.findall(answer_text)
            if len(pairs) != len(questions):
                continue
            answers = [(a if a else marker).strip() for _q, a, marker in pairs]
            recent_text = "\n".join(list(recent_prompts)[-3:])
            recent_excerpt = "\\n".join("user: " + _flat(p[-ASK_RECENT_CHARS:]) for p in recent_prompts)
            if last_assistant_text.strip():
                recent_excerpt += ("\\n" if recent_excerpt else "") + \
                    "assistant: " + _flat(last_assistant_text.strip()[-ASK_RECENT_CHARS:])
            call = f"{session}-{(tool_id or '')[-6:]}"
            for k, (q, a) in enumerate(zip(questions, answers)):
                qjson = json.dumps({
                    "question": q.get("question"), "header": q.get("header"),
                    "multiSelect": bool(q.get("multiSelect")),
                    "options": [{"label": o.get("label"), "description": o.get("description")}
                                for o in (q.get("options") or [])],
                }, ensure_ascii=False)
                yield {
                    "answered_in_context": _answered_in_context(a, recent_text),
                    "routine_default": _routine_default(a),
                    "naming_or_irreversible": _naming_or_irreversible(q),
                    "options_complete": _options_complete(a, q.get("options") or []),
                    "call": call, "index": k + 1, "count": len(questions),
                    "project": slug_name(slug),
                    "question_json": _flat(qjson), "answer": _flat(a),
                    "recent": recent_excerpt,
                }


def dump_asks(project_filter=None):
    for cfg in config_dirs():
        projects = os.path.join(cfg, "projects")
        if not os.path.isdir(projects):
            continue
        for slug in sorted(os.listdir(projects)):
            if project_filter and project_filter.lower() not in slug.lower():
                continue
            pdir = os.path.join(projects, slug)
            if not os.path.isdir(pdir):
                continue
            for entry in sorted(os.listdir(pdir)):
                if entry.endswith(".jsonl"):
                    yield from _dump_asks_from(os.path.join(pdir, entry), slug)


def sample_asks(rows, n, seed):
    """Stratified across projects, whole calls at a time: round-robin over the
    projects (each shuffled by the seed) until at least n question rows are
    taken, so a multi-question call is never split between sampled and not.
    Deterministic for a given seed and transcript set."""
    import random
    by_project = collections.defaultdict(dict)
    for r in rows:
        by_project[r["project"]].setdefault(r["call"], []).append(r)
    rng = random.Random(seed)
    queues = {p: list(calls.values()) for p, calls in by_project.items()}
    for q in queues.values():
        rng.shuffle(q)
    order = sorted(queues)
    taken, count = [], 0
    while count < n and any(queues.values()):
        for p in order:
            if not queues[p]:
                continue
            call = queues[p].pop()
            taken.extend(call)
            count += len(call)
            if count >= n:
                break
    return taken


def _dump_one(path, mode):
    """Yields labelled rows from one transcript for --dump-prompts /
    --dump-stops. Heuristic labels only (the same regex classifiers the rest
    of this file already uses for classify_prompt and CORRECTION_RE), not a
    hand-graded pass over every row -- see the system-one design doc section
    10 for how these seed the hooks' test cases."""
    last_assistant_text = ""
    last_prompt_text = ""
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return
    with fh:
        for line in fh:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = e.get("type")
            msg = e.get("message") or {}
            content = msg.get("content")
            if t == "user":
                if isinstance(content, str) or (
                    isinstance(content, list) and content and all(
                        isinstance(b, dict) and b.get("type") == "text" for b in content)
                ):
                    text = text_of(content).strip()
                    if not text or text.startswith("<"):
                        continue
                    if mode == "prompts":
                        head = " ".join(words(text.splitlines()[0])[:10])
                        cm = CORRECTION_RE.search(head)
                        cls = classify_prompt(text)
                        if cm:
                            kind = "correction"
                        elif cls == "wish":
                            kind = "wish"
                        elif cls == "question":
                            kind = "question"
                        elif cls in ("ack", "slash", "url", "error-paste"):
                            kind = "other"
                        else:
                            kind = "order"
                        wants_action = 1 if kind in ("order", "correction") else 0
                        clean = text[:200].replace("\t", " ").replace("\n", " ")
                        prev = last_assistant_text[-600:].replace("\t", " ").replace("\n", "\\n")
                        yield (kind, wants_action, clean, prev)
                        # the prompt that led to a correction, labelled the same
                        # heuristic way, per the design doc's request for the
                        # "moment before" set
                        if kind == "correction" and last_prompt_text:
                            pcls = classify_prompt(last_prompt_text)
                            if pcls == "wish":
                                pkind = "wish"
                            elif pcls == "question":
                                pkind = "question"
                            elif pcls in ("ack", "slash", "url", "error-paste"):
                                pkind = "other"
                            else:
                                pkind = "order"
                            pclean = last_prompt_text[:200].replace("\t", " ").replace("\n", " ")
                            yield (pkind, 1 if pkind == "order" else 0, pclean, "")
                    elif mode == "stops" and last_assistant_text:
                        is_simplify = bool(SIMPLIFY_RE.search(text)) and len(words(text)) < 20
                        yield ("padded" if is_simplify else "fitting", last_assistant_text, text[:160])
                    last_prompt_text = text
                continue
            if t != "assistant" or not isinstance(content, list):
                continue
            for b in content:
                if isinstance(b, dict) and b.get("type") == "text":
                    txt = b.get("text") or ""
                    if txt.strip():
                        last_assistant_text = txt


def dump_dataset(mode, project_filter=None):
    """Streams labelled rows across every transcript under every config dir.
    mode: 'prompts' (kind, wants_action, prompt<=200 chars, previous assistant
    message's last 600 chars with newlines escaped as \\n) or 'stops'
    ('padded'/'fitting', assistant message, the next prompt)."""
    for cfg in config_dirs():
        projects = os.path.join(cfg, "projects")
        if not os.path.isdir(projects):
            continue
        for slug in sorted(os.listdir(projects)):
            if project_filter and project_filter.lower() not in slug.lower():
                continue
            pdir = os.path.join(projects, slug)
            if not os.path.isdir(pdir):
                continue
            for entry in sorted(os.listdir(pdir)):
                if entry.endswith(".jsonl"):
                    yield from _dump_one(os.path.join(pdir, entry), mode)


def jsonable(obj):
    if isinstance(obj, collections.Counter):
        return dict(obj.most_common())
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, set):
        return len(obj)
    return obj


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Profile Claude Code usage from transcripts.")
    ap.add_argument("--since", help="only sessions starting on or after YYYY-MM-DD")
    ap.add_argument("--json", action="store_true", help="emit one JSON object instead of tables")
    ap.add_argument("--samples", type=int, default=0, help="print N sample corrections/judgments/blocks")
    ap.add_argument("--project", help="substring filter on the project slug")
    ap.add_argument("--dump-prompts", action="store_true",
                     help="stream kind<TAB>wants_action<TAB>prompt<TAB>previous rows for the system-one prompt-kind cases file, heuristically labelled, and exit")
    ap.add_argument("--dump-stops", action="store_true",
                     help="stream label<TAB>message rows (padded/fitting, newlines escaped, a # next: comment before each row naming the prompt that followed) for the system-one stop cases file, heuristically labelled, and exit")
    ap.add_argument("--dump-asks", action="store_true",
                     help="stream one row per AskUserQuestion question (columns: " + ", ".join(ASK_ROW_KEYS) +
                          ") for the system-one ask cases file, heuristically labelled, and exit")
    ap.add_argument("--sample", type=int, default=0, metavar="N",
                     help="--dump-asks: keep about N question rows, whole calls, stratified across projects")
    ap.add_argument("--seed", type=int, default=1, help="--sample: shuffle seed (default 1)")
    args = ap.parse_args()

    if args.dump_prompts:
        for kind, wants_action, prompt, prev in dump_dataset("prompts", args.project):
            print(f"{kind}\t{wants_action}\t{prompt}\t{prev}")
        return
    if args.dump_asks:
        rows = list(dump_asks(args.project))
        if args.sample:
            rows = sample_asks(rows, args.sample, args.seed)
        for r in rows:
            print("\t".join(str(r[k]) for k in ASK_ROW_KEYS))
        return
    if args.dump_stops:
        # Newlines are escaped as a literal backslash-n so the message's
        # structure (tables, headers, bullets) survives the one-row-per-line
        # file; readers unescape. Every row is preceded by a comment naming
        # the prompt that followed the message (the one that labelled it), so
        # a hand audit can tell a shape complaint from a content one.
        for label, message, nxt in dump_dataset("stops", args.project):
            if nxt:
                print(f"# next: {nxt.replace(chr(9), ' ').replace(chr(10), ' ')}")
            print(f"{label}\t{message.replace(chr(9), ' ').replace(chr(10), '\\n')}")
        return

    since = None
    if args.since:
        since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)

    sessions = []
    history = None
    for cfg in config_dirs():
        projects = os.path.join(cfg, "projects")
        for slug in sorted(os.listdir(projects)):
            pdir = os.path.join(projects, slug)
            if not os.path.isdir(pdir):
                continue
            if args.project and args.project.lower() not in slug.lower():
                continue
            for entry in sorted(os.listdir(pdir)):
                full = os.path.join(pdir, entry)
                if entry.endswith(".jsonl"):
                    s = scan_transcript(full, slug)
                    dt = parse_ts(s["first_ts"])
                    if since and (dt is None or dt < since):
                        continue
                    sessions.append(s)
                elif os.path.isdir(os.path.join(full, "subagents")):
                    for sub in os.listdir(os.path.join(full, "subagents")):
                        if sub.endswith(".jsonl"):
                            s = scan_transcript(os.path.join(full, "subagents", sub), slug, sidechain=True)
                            dt = parse_ts(s["first_ts"])
                            if since and (dt is None or dt < since):
                                continue
                            sessions.append(s)
        h = scan_history(cfg, since)
        if history is None:
            history = h
        else:
            for key in ("per_week", "per_project", "slash", "openers", "classes"):
                merge_counter(history[key], h[key])
            history["count"] += h["count"]
            history["sessions"] += h["sessions"]

    agg = aggregate(sessions, history)
    if args.json:
        json.dump(jsonable(agg), sys.stdout, indent=1)
        print()
    else:
        print_text(agg, args.samples)


if __name__ == "__main__":
    main()
