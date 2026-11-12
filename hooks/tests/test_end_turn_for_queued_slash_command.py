"""Cases for end-turn-for-queued-slash-command.py, run on transcripts built here."""

import json
import os
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "end-turn-for-queued-slash-command.py")
CACHE = tempfile.mkdtemp()


def q(op, content, ts="2026-11-12T14:17:15.307Z"):
    return {"type": "queue-operation", "operation": op, "timestamp": ts, "sessionId": "s", "content": content}


def run(rows, event, tool, tool_input=None, name="t"):
    path = os.path.join(CACHE, name + ".jsonl")
    with open(path, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    payload = {"hook_event_name": event, "tool_name": tool, "transcript_path": path, "tool_input": tool_input or {}}
    out = subprocess.run([sys.executable, "-I", HOOK], input=json.dumps(payload), text=True, capture_output=True,
                         env={**os.environ, "XDG_CACHE_HOME": CACHE}).stdout
    return json.loads(out)["hookSpecificOutput"] if out.strip() else None


fails = 0


def check(name, ok):
    global fails
    print(("ok   " if ok else "FAIL ") + name)
    fails += not ok


queued = [q("enqueue", "/pattern-discovery-agent-fix")]
r = run(queued, "PreToolUse", "AskUserQuestion")
check("a question is refused while a slash command is queued", r and r["permissionDecision"] == "deny"
      and "/pattern-discovery-agent-fix" in r["permissionDecisionReason"])
r = run([q("enqueue", "/pattern-discovery-agent-fix why did this problem occur")], "PreToolUse", "AskUserQuestion")
check("the refusal names the command, not the words typed after it or a time",
      r and "/pattern-discovery-agent-fix" in r["permissionDecisionReason"]
      and "why did this problem occur" not in r["permissionDecisionReason"]
      and "UTC" not in r["permissionDecisionReason"])
r = run(queued, "PreToolUse", "Skill", {"skill": "pattern-discovery-agent-fix"})
check("invoking the queued skill is refused", r and r["permissionDecision"] == "deny"
      and "UTC" not in r["permissionDecisionReason"])
check("another skill is let through", run(queued, "PreToolUse", "Skill", {"skill": "vet-fable"}) is None)
check("other tools are let through before the call", run(queued, "PreToolUse", "Bash") is None)
r = run(queued, "PostToolUse", "Bash", name="once")
check("after a tool call the agent is told to end the turn", r and "end the turn" in r["additionalContext"])
check("the note comes once per command", run(queued, "PostToolUse", "Bash", name="once") is None)
check("a delivered command is not pending",
      run(queued + [{"type": "queue-operation", "operation": "dequeue", "timestamp": "2026-11-12T14:35:56Z"}],
          "PreToolUse", "AskUserQuestion") is None)
check("a dequeue takes the head of the queue, not a later command",
      run([q("enqueue", "plain text first")] + queued + [{"type": "queue-operation", "operation": "dequeue"}],
          "PreToolUse", "AskUserQuestion") is not None)
check("a removed cross-session message whose remove lacks its hop-chain leaves the queue",
      run([q("enqueue", '<cross-session-message from="x" hop-chain="ab12" from-name="peer">\nhi'),
           q("remove", '<cross-session-message from="x" from-name="peer">\nhi')] + queued
          + [{"type": "queue-operation", "operation": "dequeue"}], "PreToolUse", "AskUserQuestion") is None)
check("a plain-text queued message is not a command",
      run([q("enqueue", "also, how do I detach?")], "PreToolUse", "AskUserQuestion") is None)
check("a queue pulled back into the prompt is not pending",
      run(queued + [q("popAll", "/pattern-discovery-agent-fix")], "PreToolUse", "AskUserQuestion") is None)
check("an unreadable transcript fails open",
      subprocess.run([sys.executable, "-I", HOOK], input="{", text=True, capture_output=True).returncode == 0)

print(f"end-turn-for-queued-slash-command: {fails} failed")
sys.exit(1 if fails else 0)
