#!/usr/bin/env python3
# DESC: Mine three labelled system-one training datasets (skill_route, will_correct, delegate) from local Claude Code transcripts
"""
system-one-mine-tasks: build three labelled JSONL datasets for "system-one"
local decision-model hooks, from the user's own Claude Code transcripts.

Streams every transcript under every Claude config dir once (never loads a
file whole; same discovery as scripts/usage-survey.py and
scripts/command-moments-survey.py via claude_dirs.config_dirs()) and turns it
into a list of "turns": one per human-typed prompt, carrying that prompt's
text/word-count/slash-ness, every Skill tool_use and Agent tool_use the
assistant made in response, and the assistant's final text message of the
turn. A prompt counts as human-typed under the same rule
command-moments-survey.py uses (origin.kind == "human" when present, never
isMeta, a tool_result, or a harness marker like <task-notification>).

Three tasks are built from that shared per-turn structure, each with the same
row schema scripts/system-one-train-data.py writes --
    {"task", "split", "row_id", "state", "question", "target", "label"}
-- with "state" built by IMPORTING scripts/system-one-measure.py's
build_prompt_state / build_stop_state by path (as system-one-train-data.py
does), so a training state is byte-identical to the runtime state the hooks
build, and "question" in Laya's internal shape ({"t","ins","crit"}) via
laya.Agent._to_internal, so system-one-train.py can hand it straight to
laya.common.build_sequence.

  skill_route (choice): state = hooks/system-one-prompt.sh's state for a
    turn's opening prompt (build_prompt_state, prompt_chars=600,
    previous_chars=0 -- the file's own defaults). Anchor prompts: typed,
    non-slash, not isMeta, >=3 words. Label: the first skill or command the
    ASSISTANT invoked in that turn -- a Skill tool_use (input.skill, last
    ':'-segment so "interface:better-colors" and the older bare
    "better-colors" collapse to one label), or an isMeta command-expansion
    entry the assistant's own turn triggered. Failing that, a USER-typed
    slash command right after this prompt still labels it, but only when the
    command is a correction of how the prompt was handled -- it transforms
    or redoes the previous reply (USER_CORRECTION_COMMANDS: humanizer,
    be-literal, archify, plan-not-ready, i-have-adhd, aristocrat, caveman,
    refocus, go-back, no-chat-in-code). A workflow command that marks the
    work finished (stg-msg-cmt, outstanding, handoff, new-repo, new-tool,
    homelab-connect, ...) is never a label when user-typed, only when the
    assistant itself invoked it. Else "none". Options are the roster actually present under
    ~/.claude/skills and ~/.claude/commands (grouped skills keyed by their
    bare subdirectory name), narrowed to the 15 most frequently invoked
    labels found in the mined data plus "none" and "other" (any roster name
    outside that top 15). Option descriptions are each skill's/command's
    frontmatter `description`, first sentence, cut to 120 chars. "none" is
    downsampled to --none-ratio (default 3) times the positive (non-"none")
    row count, fixed --seed.

  will_correct (noul): state = build_correct_state(prev_prompt, reply) --
    the turn's own prompt (the one that produced `reply`, capped 400 chars)
    plus hooks/system-one-stop.sh's state for the reply (build_stop_state,
    message_chars=1500): "correction after a correction" is the strongest
    observed pattern, so the previous prompt goes in the state alongside the
    reply it produced (2026-09-26 audit finding A2). Label: whether the NEXT
    prompt is a correction, decided by calling the live Laya server's full-v1
    model on the exact "kind" choice question from
    hooks/system-one-prompt-questions.json, built over that next prompt's
    own build_prompt_state -- true when the top class is "correction" at
    p>=--correction-threshold (default 0.70), false when the top class is
    order/question/wish at p>=threshold, dropped otherwise. A next prompt
    that is itself a slash command is DROPPED, not labelled false, so every
    negative is model-labelled exactly like every positive (2026-09-26 audit
    finding A1; previously ~303 negatives came from this rule with no model
    call). Candidates are capped at --max-candidates (default 3000), sampled
    round-robin across (project, year-month) buckets so no single project or
    month dominates; negatives are then downsampled to --neg-ratio (default
    3) times positives. A 60-row hand-check sample (30 true, 30 false) is
    written to <out-dir>/will_correct-check.tsv with the next prompt's text,
    for a human to grade -- this script does not grade it.

  delegate (noul): state = the same prompt state as skill_route. Anchor
    prompts: typed, non-slash, >=8 words. Label: "spawn" if the assistant
    made any Agent tool_use in the turn (any model), else "self" (2026-09-26
    audit finding B: relabelled two-way, dropping the small/large split).
    "self" is downsampled to --self-ratio (default 3) times the spawn row
    count, fixed --seed. Question: "Should this prompt be handed to a
    subagent rather than done inline?"

Every task's rows are split 60/20/20 train/val/test, stratified per task by
its own label, shuffled with random.Random(--seed) per label stratum.

Real session text (prompts, assistant messages) never goes in the repo: the
three JSONL files, splits-mined.json, per-task *_meta.jsonl (project/month/ts index
for --stats, since the shared row schema itself carries neither), and the
will_correct-check.tsv all land under --out-dir, which defaults to
$XDG_STATE_HOME/system-one/train (or ~/.local/state/system-one/train).

Runs fully offline (HF_HUB_OFFLINE=1 is set before `import laya`); needs no
model weights, only laya.Agent._to_internal (a staticmethod). will_correct's
label pass is the one network-touching step: sequential POSTs to a live,
already-running /v1/systemone server (never restarted, never parallelised;
see --endpoint).

Must run under the system-one venv's interpreter (it imports laya directly):
    $HOME/.local/share/system-one/venv/bin/python system-one-mine-tasks.py

Usage:
    system-one-mine-tasks.py [--out-dir DIR] [--agents-shared DIR] [--claude-dir DIR]
                              [--seed N] [--endpoint URL] [--correction-model NAME]
                              [--max-candidates N] [--skill-topn N]
                              [--none-ratio F] [--neg-ratio F] [--self-ratio F]
                              [--correction-threshold F] [--timeout S] [--retries N]
    system-one-mine-tasks.py --stats [--out-dir DIR]
"""
import argparse
import collections
import importlib.util
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from claude_dirs import config_dirs  # noqa: E402

DEFAULT_OUT_DIR = os.path.join(
    os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state"),
    "system-one", "train")
DEFAULT_CLAUDE_DIR = os.path.expanduser("~/.claude")
DEFAULT_ENDPOINT = "http://127.0.0.1:7811/v1/systemone"

CMD_RE = re.compile(r"<command-name>/?([\w:-]+)</command-name>")
NOT_A_PROMPT = ("[Request interrupted", "<local-command", "This session is being continued",
                "<task-notification", "<system-reminder")


# --------------------------------------------------------------------- misc

def default_agents_shared() -> str:
    return os.path.dirname(HERE)


def load_measure_module(agents_shared: str):
    """Import scripts/system-one-measure.py by path (hyphenated filename, so a
    plain `import` cannot reach it) to reuse build_prompt_state/build_stop_state
    verbatim -- the exact functions the hooks and system-one-train-data.py use."""
    path = os.path.join(agents_shared, "scripts", "system-one-measure.py")
    spec = importlib.util.spec_from_file_location("system_one_measure", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def to_internal(qdef: dict) -> dict:
    import laya
    return laya.Agent._to_internal(qdef)


def one_hot(n: int, i: int) -> list:
    v = [0.0] * n
    v[i] = 1.0
    return v


def noul_target(is_true: bool) -> list:
    return [0.0, 1.0] if is_true else [1.0, 0.0]


def slug_name(slug: str) -> str:
    decoded = slug.replace("-", "/")
    base = os.path.basename(decoded.rstrip("/"))
    return base or slug


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def is_human_prompt(e: dict, content) -> bool:
    """Same rule command-moments-survey.py uses: a typed prompt only, never a
    skill-injection body, tool_result, interrupt marker, task-notification or
    system-reminder."""
    if e.get("isMeta"):
        return False
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return False
    o = (e.get("origin") or {}).get("kind")
    if o is not None:
        return o == "human"
    if e.get("turnOrigin") not in (None, "human"):
        return False
    t = text_of(content).lstrip()
    return bool(t) and not t.startswith(NOT_A_PROMPT)


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------- roster

def first_sentence(text: str, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return ""
    m = re.match(r"(.*?[.!?])(\s|$)", text)
    s = m.group(1) if m else text
    if len(s) > limit:
        s = s[:limit - 1].rstrip() + "…"
    return s


def parse_frontmatter_description(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return ""
    if not lines or lines[0].strip() != "---":
        return ""
    end = None
    for i in range(1, min(len(lines), 300)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return ""
    block = lines[1:end]
    for i, line in enumerate(block):
        m = re.match(r"^description:\s*(.*)$", line)
        if not m:
            continue
        rest = m.group(1).strip()
        if rest in (">", "|", ">-", "|-", ">+", "|+", ""):
            fold = rest == "" or rest.startswith(">")
            base_indent = len(line) - len(line.lstrip())
            collected = []
            for nxt in block[i + 1:]:
                if nxt.strip() == "":
                    collected.append("")
                    continue
                indent = len(nxt) - len(nxt.lstrip())
                if indent <= base_indent:
                    break
                collected.append(nxt.strip())
            return " ".join(c for c in collected if c) if fold else "\n".join(collected)
        return rest.strip("\"'")
    return ""


def build_roster(claude_dir: str) -> dict:
    """name -> first-sentence description, for every skill (flat or inside a
    group's skills/ subdir, keyed by its own bare directory name) and every
    slash command under claude_dir."""
    roster = {}
    skills_dir = os.path.join(claude_dir, "skills")
    if os.path.isdir(skills_dir):
        for entry in sorted(os.listdir(skills_dir)):
            p = os.path.join(skills_dir, entry)
            if not os.path.isdir(p):
                continue
            flat_md = os.path.join(p, "SKILL.md")
            if os.path.isfile(flat_md):
                roster[entry] = first_sentence(parse_frontmatter_description(flat_md))
                continue
            sub = os.path.join(p, "skills")
            if os.path.isdir(sub):
                for sentry in sorted(os.listdir(sub)):
                    sp = os.path.join(sub, sentry, "SKILL.md")
                    if os.path.isfile(sp):
                        roster[sentry] = first_sentence(parse_frontmatter_description(sp))
    commands_dir = os.path.join(claude_dir, "commands")
    if os.path.isdir(commands_dir):
        for entry in sorted(os.listdir(commands_dir)):
            if not entry.endswith(".md"):
                continue
            name = entry[:-3]
            roster.setdefault(name, first_sentence(parse_frontmatter_description(os.path.join(commands_dir, entry))))
    return roster


def norm_skill_name(name) -> str:
    if not name:
        return ""
    return name.split(":")[-1].strip()


# --------------------------------------------------------- transcript pass

def new_turn(prompt_text, is_slash, slash_name, word_count, t):
    return {"prompt": prompt_text, "is_slash": is_slash, "slash_name": slash_name,
            "word_count": word_count, "ts": t, "skills": [], "agent_spawns": [], "last_text": ""}


def scan_transcript(path: str, project: str):
    """One streamed pass -> list of turn dicts (see new_turn), each already
    carrying next_* fields describing the immediately following typed prompt
    (or None at session end), and session/project/ts for the meta index."""
    turns = []
    turn = None
    session = os.path.basename(path)[:-6]
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return turns
    with fh:
        for line in fh:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            et = e.get("type")
            t = parse_ts(e.get("timestamp"))
            msg = e.get("message") or {}
            content = msg.get("content")

            if et == "user":
                if is_human_prompt(e, content):
                    txt = text_of(content).strip()
                    m = CMD_RE.search(txt)
                    is_slash = bool(m) or txt.startswith("/")
                    slash_name = (m.group(1) if m else (txt.split()[0].lstrip("/") if is_slash and txt.split() else None))
                    wc = len(txt.split()) if not is_slash else 0
                    if turn is not None:
                        turn["next_is_slash"] = is_slash
                        turn["next_slash_name"] = slash_name
                        turn["next_prompt"] = txt[:600]
                        turns.append(turn)
                    turn = new_turn(txt[:2000], is_slash, slash_name, wc, t)
                    continue
                # isMeta command expansion: the harness's own synthetic turn
                # carrying a command's body, injected when something in this
                # turn (the model, a skill) triggered it rather than the
                # human typing it. Counts as a skill_route invocation, same
                # as a Skill tool_use, if it falls inside the current turn.
                if e.get("isMeta") and turn is not None:
                    etxt = text_of(content)
                    em = CMD_RE.search(etxt)
                    if em:
                        turn["skills"].append(em.group(1))
                continue
            if et != "assistant" or turn is None or not isinstance(content, list):
                continue
            for b in content:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "text":
                    txt = b.get("text") or ""
                    if txt.strip():
                        turn["last_text"] = txt
                elif bt == "tool_use":
                    name = b.get("name")
                    inp = b.get("input") or {}
                    if name == "Skill":
                        turn["skills"].append(inp.get("skill"))
                    elif name == "Agent":
                        turn["agent_spawns"].append({"model": inp.get("model"),
                                                      "subagent_type": inp.get("subagent_type")})
    if turn is not None:
        turn["next_is_slash"] = None
        turn["next_slash_name"] = None
        turn["next_prompt"] = None
        turns.append(turn)
    for tu in turns:
        tu["project"] = project
        tu["session"] = session
    return turns


def scan_all(claude_dir_filter=None):
    turns = []
    for cfg in config_dirs():
        root = os.path.join(cfg, "projects")
        if not os.path.isdir(root):
            continue
        for slug in sorted(os.listdir(root)):
            pdir = os.path.join(root, slug)
            if not os.path.isdir(pdir):
                continue
            proj = slug_name(slug)
            for entry in sorted(os.listdir(pdir)):
                if entry.endswith(".jsonl"):
                    turns.extend(scan_transcript(os.path.join(pdir, entry), proj))
    return turns


# --------------------------------------------------------------- delegate

DELEGATE_QUESTION = {
    "type": "noul",
    "instructions": "Should this prompt be handed to a subagent rather than done inline?",
}


def delegate_label(turn) -> str:
    return "spawn" if turn["agent_spawns"] else "self"


def build_delegate_items(m, turns, self_ratio: float, seed: int):
    q = to_internal(DELEGATE_QUESTION)
    eligible = [t for t in turns if not t["is_slash"] and t["word_count"] >= 8]
    spawns = [t for t in eligible if t["agent_spawns"]]
    selfs = [t for t in eligible if not t["agent_spawns"]]
    before = collections.Counter(delegate_label(t) for t in eligible)
    n_keep_self = min(len(selfs), round(self_ratio * len(spawns)))
    kept_self = random.Random(seed).sample(selfs, n_keep_self)
    combined = spawns + kept_self
    random.Random(seed + 1).shuffle(combined)

    items, meta, strat = [], [], {}
    for row_id, t in enumerate(combined):
        state = m.build_prompt_state(t["prompt"], "", 600, 0)
        label = delegate_label(t)
        is_spawn = label == "spawn"
        strat.setdefault(label, []).append(row_id)
        items.append({"task": "delegate", "row_id": row_id, "state": state, "question": q,
                      "target": noul_target(is_spawn), "label": label})
        meta.append({"row_id": row_id, "project": t["project"], "session": t["session"],
                    "ts": t["ts"].isoformat() if t["ts"] else None})
    after = collections.Counter(it["label"] for it in items)
    return items, strat, meta, before, after


# -------------------------------------------------------------- skill_route

# Roster commands whose whole point is to transform/redo/restyle the
# assistant's PREVIOUS reply, rather than do new work: read every roster
# description for "restyling, simplifying, redoing or re-planning the
# previous reply" and kept these --
#   humanizer            "Remove signs of AI-generated writing from text."
#   be-literal            "Take the question literally." (redo the
#                         interpretation of what was just answered)
#   archify               explicitly named by the coordinator (also covers
#                         "convert/beautify" an existing diagram)
#   plan-not-ready        "Signal that the plan needs more refinement
#                         before implementation." (redo the plan)
#   i-have-adhd           "Shape output for a reader with ADHD..." (restyle
#                         the previous answer's shape)
#   aristocrat            "Adopt aristocratic communication style..."
#                         (restyle communication going forward)
#   caveman               "Ultra-compressed communication mode. Cuts token
#                         usage ~75%..." (simplify/shorten a reply -- the
#                         design doc's top correction phrase, "say it
#                         simpler")
#   refocus               "Reset focus when Claude loses the plot." (a
#                         correction of drift, by definition)
#   go-back               "Rewind a drifted conversation by editing an
#                         earlier user message." (a redo mechanism)
#   no-chat-in-code       "Keep code free of conversational artifacts and
#                         steering commentary." (redo the previous code
#                         output's style)
# Workflow/finishing commands (stg-msg-cmt, outstanding, handoff, new-repo,
# new-tool, homelab-connect, cmt, cmt-msg, gs, send-it, standup, board,
# search-history, and the rest of the roster) are deliberately excluded:
# they mark work as done or start something new, not correct the prior turn.
USER_CORRECTION_COMMANDS = {
    "humanizer", "be-literal", "archify", "plan-not-ready", "i-have-adhd",
    "aristocrat", "caveman", "refocus", "go-back", "no-chat-in-code",
}


def skill_route_label(turn, roster: dict):
    """A label comes from the ASSISTANT invoking a skill or command in the
    turn after the prompt: a Skill tool_use (input.skill), or an isMeta
    command-expansion entry the assistant's own turn triggered (see
    scan_transcript) -- checked first. Failing that, a USER-typed slash
    command right after this prompt still counts, but only when it is one of
    USER_CORRECTION_COMMANDS above: a command whose purpose is to correct how
    this very prompt's reply was handled (redo/restyle/re-plan it), not a
    workflow command that simply marks the work finished (stg-msg-cmt,
    outstanding, handoff, ...) or starts something new. A label only counts
    when it names something actually present in the roster today (per the
    task's own definition of "options"): a Skill tool_use/expansion or a
    slash command for something no longer under ~/.claude/skills or
    ~/.claude/commands falls back to "none"."""
    for s in turn["skills"]:
        n = norm_skill_name(s)
        if n and n in roster:
            return n
    if turn.get("next_is_slash") and turn.get("next_slash_name"):
        name = turn["next_slash_name"]
        if name in roster and name in USER_CORRECTION_COMMANDS:
            return name
    return "none"


def build_skill_route_items(m, turns, roster: dict, topn: int, none_ratio: float, seed: int):
    eligible = [t for t in turns if not t["is_slash"] and t["word_count"] >= 3]
    raw_labels = [skill_route_label(t, roster) for t in eligible]
    counts = collections.Counter(l for l in raw_labels if l != "none")
    top = [name for name, _ in counts.most_common(topn)]
    keep_set = set(top)

    def bucketed(label):
        if label == "none":
            return "none"
        return label if label in keep_set else "other"

    option_order = top + ["other", "none"]
    descriptions = {}
    for name in top:
        descriptions[name] = roster.get(name) or "(no description in its frontmatter)"
    descriptions["other"] = "a skill or slash command outside the 15 most frequently invoked, not itself an option"
    descriptions["none"] = "no skill or slash command was invoked for this prompt"
    question = {"type": "choice",
                "instructions": "Which skill or slash command, if any, will the assistant invoke for this prompt?",
                "criteria": {name: descriptions[name] for name in option_order}}
    q = to_internal(question)

    before = collections.Counter(bucketed(l) for l in raw_labels)
    positives = [(t, bucketed(l)) for t, l in zip(eligible, raw_labels) if bucketed(l) != "none"]
    negatives = [(t, "none") for t, l in zip(eligible, raw_labels) if bucketed(l) == "none"]
    n_keep_neg = min(len(negatives), round(none_ratio * len(positives)))
    kept_neg = random.Random(seed).sample(negatives, n_keep_neg)
    combined = positives + kept_neg
    random.Random(seed + 1).shuffle(combined)

    items, meta, strat = [], [], {}
    for row_id, (t, label) in enumerate(combined):
        state = m.build_prompt_state(t["prompt"], "", 600, 0)
        strat.setdefault(label, []).append(row_id)
        items.append({"task": "skill_route", "row_id": row_id, "state": state, "question": q,
                      "target": one_hot(len(option_order), option_order.index(label)), "label": label})
        meta.append({"row_id": row_id, "project": t["project"], "session": t["session"],
                    "ts": t["ts"].isoformat() if t["ts"] else None})
    after = collections.Counter(it["label"] for it in items)
    return items, strat, meta, before, after, option_order, descriptions, counts


# -------------------------------------------------------------- will_correct

WILL_CORRECT_QUESTION = {
    "type": "noul",
    "instructions": "Will the user's next typed message be a correction -- saying the previous action or answer was wrong or unwanted?",
}
KIND_FALSE_CLASSES = {"order", "question", "wish"}


def http_kind(endpoint: str, model: str, state: str, kind_q_raw: dict, timeout: float, retries: int):
    body = json.dumps({"state": state, "model": model,
                       "questions": {"kind": {"type": kind_q_raw["type"], "instructions": kind_q_raw["instructions"],
                                             "criteria": kind_q_raw.get("criteria")}}}).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body, headers={"content-type": "application/json"})
    err = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            err = e
            if attempt < retries:
                time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"request to {endpoint} failed after {retries + 1} attempts: {err}")


def round_robin_sample(bucketed: dict, n: int, seed: int) -> list:
    rng = random.Random(seed)
    queues = {k: list(v) for k, v in bucketed.items()}
    for q in queues.values():
        rng.shuffle(q)
    order = sorted(queues)
    taken = []
    while len(taken) < n and any(queues.values()):
        for k in order:
            if queues[k]:
                taken.append(queues[k].pop())
                if len(taken) >= n:
                    break
    return taken


def build_will_correct_items(m, agents_shared, turns, endpoint, model, max_candidates, neg_ratio,
                             threshold, timeout, retries, seed, out_dir):
    with open(os.path.join(agents_shared, "hooks", "system-one-prompt-questions.json"), encoding="utf-8") as f:
        prompt_doc = json.load(f)
    kind_q_raw = prompt_doc["questions"]["kind"]
    with open(os.path.join(agents_shared, "hooks", "system-one-stop-questions.json"), encoding="utf-8") as f:
        message_chars = int(json.load(f).get("state", {}).get("message_chars", 1500))

    candidates = [t for t in turns if t["last_text"] and t.get("next_prompt") is not None]
    by_bucket = collections.defaultdict(list)
    for t in candidates:
        month = t["ts"].strftime("%Y-%m") if t["ts"] else "?"
        by_bucket[(t["project"], month)].append(t)
    sampled = round_robin_sample(by_bucket, min(max_candidates, len(candidates)), seed)

    kept = []  # (turn, label_bool, prob)
    n_calls = 0
    for i, t in enumerate(sampled):
        if t["next_is_slash"]:
            # Dropped, not labelled false: a slash-command next prompt is not a
            # model-derived verdict, and every negative must be model-labelled
            # like the positives (2026-09-26 audit finding A1).
            continue
        state = m.build_prompt_state(t["next_prompt"], "", 600, 0)
        try:
            resp = http_kind(endpoint, model, state, kind_q_raw, timeout, retries)
        except RuntimeError as e:
            print(f"[will_correct] {e} -- skipping row", file=sys.stderr)
            continue
        n_calls += 1
        if n_calls % 200 == 0:
            print(f"[will_correct] {n_calls} model calls done ({i + 1}/{len(sampled)} candidates)", file=sys.stderr)
        ans = resp["answers"]["kind"]
        choice = ans.get("choice")
        prob = float((ans.get("probabilities") or {}).get(choice, 0.0))
        if choice == "correction" and prob >= threshold:
            kept.append((t, True, prob))
        elif choice in KIND_FALSE_CLASSES and prob >= threshold:
            kept.append((t, False, prob))
        # else: dropped -- ambiguous verdict, neither threshold met

    before = collections.Counter("true" if k[1] else "false" for k in kept)
    positives = [k for k in kept if k[1]]
    negatives = [k for k in kept if not k[1]]
    n_keep_neg = min(len(negatives), round(neg_ratio * len(positives)))
    kept_neg = random.Random(seed).sample(negatives, n_keep_neg)
    combined = positives + kept_neg
    random.Random(seed + 1).shuffle(combined)

    q = to_internal(WILL_CORRECT_QUESTION)
    items, meta, strat = [], [], {}
    for row_id, (t, is_true, prob) in enumerate(combined):
        # State carries the previous prompt (the one that produced this reply)
        # alongside the reply itself: "correction after a correction" is the
        # strongest observed pattern (2026-09-26 audit finding A2). prev_prompt
        # is t["prompt"], already sourced from the same transcript scan pass
        # that built this turn (scan_transcript), keyed by t["session"]/t["ts"].
        state = m.build_correct_state(t["prompt"], t["last_text"], 400, message_chars)
        label = "true" if is_true else "false"
        strat.setdefault(label, []).append(row_id)
        items.append({"task": "will_correct", "row_id": row_id, "state": state, "question": q,
                      "target": noul_target(is_true), "label": label})
        meta.append({"row_id": row_id, "project": t["project"], "session": t["session"],
                    "ts": t["ts"].isoformat() if t["ts"] else None,
                    "next_prompt": t["next_prompt"], "prob": prob})
    after = collections.Counter(it["label"] for it in items)

    # 60-row hand-check TSV: 30 true, 30 false, ungraded by this script.
    check_path = os.path.join(out_dir, "will_correct-check.tsv")
    trues = [x for x in combined if x[1]]
    falses = [x for x in combined if not x[1]]
    rng = random.Random(seed + 2)
    sample_true = rng.sample(trues, min(30, len(trues)))
    sample_false = rng.sample(falses, min(30, len(falses)))
    check_rows = sample_true + sample_false
    rng.shuffle(check_rows)
    with open(check_path, "w", encoding="utf-8") as f:
        f.write("label\tmodel_prob\tproject\tnext_prompt\n")
        for t, is_true, prob in check_rows:
            np = (t["next_prompt"] or "").replace("\t", " ").replace("\n", "\\n")
            f.write(f"{'true' if is_true else 'false'}\t{prob if prob is not None else ''}\t{t['project']}\t{np}\n")

    return items, strat, meta, before, after, check_path, len(candidates), len(sampled), n_calls


# --------------------------------------------------------------------- splits

def stratified_split_602020(ids_by_label: dict, seed: int) -> dict:
    train, val, test = [], [], []
    for label in sorted(ids_by_label):
        ids = sorted(ids_by_label[label])
        random.Random(seed).shuffle(ids)
        n = len(ids)
        n_train = round(0.6 * n)
        n_val = round(0.2 * n)
        train += ids[:n_train]
        val += ids[n_train:n_train + n_val]
        test += ids[n_train + n_val:]
    return {"train": sorted(train), "val": sorted(val), "test": sorted(test)}


# ------------------------------------------------------------------------ stats

def print_histogram(title, counter):
    total = sum(counter.values())
    print(f"  {title}: (n={total})")
    for label, n in counter.most_common():
        print(f"    {label:<20} {n:>6}  {100 * n / total if total else 0:5.1f}%")


def run_stats(out_dir: str):
    tasks = ["skill_route", "will_correct", "delegate"]
    splits_path = os.path.join(out_dir, "splits-mined.json")
    if not os.path.exists(splits_path):
        sys.exit(f"{splits_path}: not found -- run this script without --stats first")
    with open(splits_path, encoding="utf-8") as f:
        splits = json.load(f)
    for task in tasks:
        data_path = os.path.join(out_dir, f"{task}.jsonl")
        meta_path = os.path.join(out_dir, f"{task}_meta.jsonl")
        if not os.path.exists(data_path):
            print(f"\n## {task}: no data file at {data_path}")
            continue
        rows = [json.loads(l) for l in open(data_path, encoding="utf-8") if l.strip()]
        meta = {}
        if os.path.exists(meta_path):
            for l in open(meta_path, encoding="utf-8"):
                if l.strip():
                    r = json.loads(l)
                    meta[r["row_id"]] = r
        print(f"\n## {task}  (n={len(rows)})")
        for split_name in ("train", "val", "test"):
            ids = set(splits.get(task, {}).get(split_name, []))
            sub = [r for r in rows if r["row_id"] in ids]
            labels = collections.Counter(r["label"] for r in sub)
            print(f"  {split_name}: {len(sub)} rows, labels {dict(labels)}")
        projects = {meta[r["row_id"]]["project"] for r in rows if r["row_id"] in meta}
        dates = sorted(meta[r["row_id"]]["ts"] for r in rows if r["row_id"] in meta and meta[r["row_id"]].get("ts"))
        print(f"  distinct projects: {len(projects)} {sorted(projects)[:10]}{'...' if len(projects) > 10 else ''}")
        if dates:
            print(f"  date range: {dates[0]} .. {dates[-1]}")


# ------------------------------------------------------------------------ main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                    help="where the 3 task JSONLs, splits-mined.json, per-task *_meta.jsonl, and "
                         "will_correct-check.tsv are written; default $XDG_STATE_HOME/system-one/train "
                         "(or ~/.local/state/system-one/train) -- never the repo, rows carry real session text")
    ap.add_argument("--agents-shared", default=default_agents_shared(),
                    help="agents-shared repo root (default: derived from this script's own path)")
    ap.add_argument("--claude-dir", default=DEFAULT_CLAUDE_DIR,
                    help="where ~/.claude/skills and ~/.claude/commands live, for the skill_route roster")
    ap.add_argument("--seed", type=int, default=0, help="split + downsample + sampling seed")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="live /v1/systemone server for will_correct labels")
    ap.add_argument("--correction-model", default="full-v1", help="model name to send to --endpoint")
    ap.add_argument("--max-candidates", type=int, default=3000,
                    help="will_correct: candidate turns sampled (round-robin across project x month) before labelling")
    ap.add_argument("--skill-topn", type=int, default=15, help="skill_route: options kept besides none/other")
    ap.add_argument("--none-ratio", type=float, default=3.0, help="skill_route: 'none' rows kept per positive row")
    ap.add_argument("--neg-ratio", type=float, default=3.0, help="will_correct: false rows kept per true row")
    ap.add_argument("--self-ratio", type=float, default=3.0, help="delegate: 'self' rows kept per spawn row")
    ap.add_argument("--correction-threshold", type=float, default=0.70,
                    help="will_correct: probability threshold for both the true and false verdict")
    ap.add_argument("--timeout", type=float, default=30.0, help="will_correct: per-request HTTP timeout, seconds")
    ap.add_argument("--retries", type=int, default=2, help="will_correct: retries before skipping a candidate row")
    ap.add_argument("--stats", action="store_true",
                    help="print per-task rows-per-split, label balance, distinct projects and date range "
                         "from an already-written --out-dir, and exit (no mining, no model/network calls)")
    args = ap.parse_args()

    if args.stats:
        run_stats(args.out_dir)
        return

    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        import laya  # noqa: F401
    except ImportError:
        sys.exit("laya is not importable; run this script with the system-one venv's interpreter, e.g.\n"
                  "  $HOME/.local/share/system-one/venv/bin/python " + os.path.abspath(__file__))

    os.makedirs(args.out_dir, exist_ok=True)
    m = load_measure_module(args.agents_shared)
    roster = build_roster(args.claude_dir)

    print(f"scanning transcripts under {[c for c in config_dirs()]}...", file=sys.stderr)
    t0 = time.perf_counter()
    turns = scan_all()
    scan_s = time.perf_counter() - t0
    print(f"{len(turns)} turns from {len({t['session'] for t in turns})} sessions, "
          f"{len({t['project'] for t in turns})} projects, in {scan_s:.1f}s", file=sys.stderr)

    print("\n=== skill_route ===")
    sr_items, sr_strat, sr_meta, sr_before, sr_after, sr_options, sr_desc, sr_counts = \
        build_skill_route_items(m, turns, roster, args.skill_topn, args.none_ratio, args.seed)
    print("roster (skills + commands found):", len(roster))
    print(f"top {args.skill_topn} invoked labels kept as options (rest -> 'other'):")
    for name, n in sr_counts.most_common(args.skill_topn):
        print(f"    {name:<26} {n:>5}  in_roster={name in roster}")
    print_histogram("before downsampling", sr_before)
    print_histogram("after downsampling", sr_after)

    print("\n=== delegate ===")
    dg_items, dg_strat, dg_meta, dg_before, dg_after = build_delegate_items(m, turns, args.self_ratio, args.seed)
    print_histogram("before downsampling", dg_before)
    print_histogram("after downsampling", dg_after)

    print("\n=== will_correct ===")
    t0 = time.perf_counter()
    (wc_items, wc_strat, wc_meta, wc_before, wc_after, check_path,
     n_candidates, n_sampled, n_calls) = build_will_correct_items(
        m, args.agents_shared, turns, args.endpoint, args.correction_model, args.max_candidates,
        args.neg_ratio, args.correction_threshold, args.timeout, args.retries, args.seed, args.out_dir)
    wc_s = time.perf_counter() - t0
    print(f"candidates found: {n_candidates}, sampled: {n_sampled}, model calls made: {n_calls} in {wc_s:.1f}s")
    print_histogram("before downsampling", wc_before)
    print_histogram("after downsampling", wc_after)
    print(f"hand-check TSV: {check_path}")

    tasks = {"skill_route": (sr_items, sr_strat, sr_meta), "will_correct": (wc_items, wc_strat, wc_meta),
             "delegate": (dg_items, dg_strat, dg_meta)}

    splits = {}
    row_split = {}
    for task, (items, strat, meta) in tasks.items():
        sp = stratified_split_602020(strat, args.seed)
        splits[task] = sp
        for split_name, ids in sp.items():
            for rid in ids:
                row_split[(task, rid)] = split_name

    print("\n=== writing ===")
    for task, (items, strat, meta) in tasks.items():
        data_path = os.path.join(args.out_dir, f"{task}.jsonl")
        meta_path = os.path.join(args.out_dir, f"{task}_meta.jsonl")
        with open(data_path, "w", encoding="utf-8") as out:
            for it in items:
                it["split"] = row_split[(task, it["row_id"])]
                out.write(json.dumps(it) + "\n")
        with open(meta_path, "w", encoding="utf-8") as out:
            for r in meta:
                out.write(json.dumps(r) + "\n")
        row_counts = {s: len(splits[task][s]) for s in ("train", "val", "test")}
        print(f"wrote {data_path}  train/val/test = {row_counts['train']}/{row_counts['val']}/{row_counts['test']}")

    splits_path = os.path.join(args.out_dir, "splits-mined.json")
    with open(splits_path, "w", encoding="utf-8") as f:
        json.dump(splits, f, indent=2)
    print(f"wrote {splits_path}")


if __name__ == "__main__":
    main()
