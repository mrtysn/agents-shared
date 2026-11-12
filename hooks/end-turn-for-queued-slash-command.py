#!/usr/bin/env python3
# DESC: PreToolUse/PostToolUse hook — tells the agent to end its turn when the user has queued a slash command
"""End the turn when the user has queued a slash command.

Claude Code folds a plain-text message the user queues mid-turn into the running turn, but holds
a queued slash command until the turn ends. The agent never sees it, and a turn kept open by more
work, or by the AskUserQuestion that claude/rules/end-every-turn-with-a-next-step.md asks for,
keeps the user waiting on their own command.

  PostToolUse, any tool   once per queued command, a note: finish this step, end the turn in text
  PreToolUse AskUserQuestion   refused while a command is queued: a question keeps the turn open
  PreToolUse Skill for the queued command   refused: the queue runs it at turn end, so it would run twice

Queue state comes from scripts/transcript_items.py (pending_queued_commands), never parsed here.
The once-per-command marker lives under ${XDG_CACHE_HOME:-~/.cache}/agents-shared/end-turn-for-queued-slash-command/.
Fails open: any error lets the call through with no note.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from transcript_items import pending_queued_commands  # noqa: E402


def hhmm(ts):
    return ts[11:16] if len(ts) >= 16 else "earlier"


def command_name(content):
    return content.split()[0].lstrip("/")


def message(p, opener):
    cmd = p["content"].split()[0]
    return (f"{opener}The user queued `{p['content'][:120]}` at {hhmm(p['time'])} (UTC). Claude Code runs a queued "
            f"slash command only when this turn ends. Finish the current step, commit it, and end the turn with a "
            f"short text report. No AskUserQuestion, and do not run `{cmd}` yourself.")


def marker_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "agents-shared", "end-turn-for-queued-slash-command")


def main():
    data = json.load(sys.stdin)
    path = data.get("transcript_path") or ""
    if not os.path.isfile(path):
        return
    pending = pending_queued_commands(path)
    if not pending:
        return
    event, tool = data.get("hook_event_name"), data.get("tool_name")
    if event == "PreToolUse":
        reason = None
        if tool == "AskUserQuestion":
            reason = message(pending[0], "Not now: ")
        elif tool == "Skill":
            skill = str((data.get("tool_input") or {}).get("skill", "")).lstrip("/")
            hit = next((p for p in pending if command_name(p["content"]) == skill), None)
            if hit:
                reason = (f"`/{skill}` is queued (at {hhmm(hit['time'])} UTC) and runs when this turn ends; invoking it "
                          f"here runs it twice. End the turn with a short text report instead.")
        if reason:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                     "permissionDecision": "deny",
                                                     "permissionDecisionReason": reason}}))
        return
    if event == "PostToolUse":
        session = os.path.basename(path).removesuffix(".jsonl")
        os.makedirs(marker_dir(), exist_ok=True)
        marker = os.path.join(marker_dir(), session)
        try:
            with open(marker, encoding="utf-8") as fh:
                told = set(fh.read().split("\n"))
        except FileNotFoundError:
            told = set()
        new = [p for p in pending if p["time"] not in told]
        if not new:
            return
        with open(marker, "a", encoding="utf-8") as fh:
            fh.write("".join(p["time"] + "\n" for p in new))
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                 "additionalContext": message(new[0], "")}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
