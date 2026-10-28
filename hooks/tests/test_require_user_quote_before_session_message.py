"""Cases for require-user-quote-before-session-message.py, run on transcripts built here."""

import json
import os
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "require-user-quote-before-session-message.py")


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def call(tid, name, inp):
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def result(tid, text):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": text}]}}


def send(tid, to, summary="x"):
    return call(tid, "SendMessage", {"to": to, "summary": summary, "message": "m"})


def run(rows, to, summary, agent_id=None):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
        for r in rows:
            r.setdefault("sessionId", "s")
            fh.write(json.dumps(r) + "\n")
    payload = {"tool_name": "SendMessage", "transcript_path": fh.name,
               "tool_input": {"to": to, "summary": summary, "message": "m"}}
    if agent_id:
        payload["agent_id"] = agent_id
    try:
        return subprocess.run([sys.executable, "-I", HOOK], input=json.dumps(payload), text=True,
                              capture_output=True).returncode
    finally:
        os.unlink(fh.name)


ASK = [call("q1", "AskUserQuestion", {"questions": []}),
       result("q1", 'User has answered your questions: "Send the long question the agent wrote here?"="Yes, tell the reviewer"')]
SPAWN = [call("a1", "Agent", {"description": "d", "prompt": "p", "name": "reviewer"}),
         result("a1", "Async agent launched successfully.\nagentId: a07bcb8441794d92e (internal)")]
GRANT = [user("what is more efficient? you guys collaborate among each other. no need to ask me"),
         send("g1", "peer", 'User said "you guys collaborate among each other"'), result("g1", "ok")]

CASES = [
    ("quote of a typed prompt passes", [user("please let that session know of what they are causing")],
     "job-search-8d", 'User said "let that session know of what they are causing"', None, 0),
    ("case and spacing are normalised", [user("Please  let that\nsession KNOW")], "x", 'User said "let that session know"', None, 0),
    ("no summary", [user("tell them about it now")], "x", "", None, 2),
    ("summary without a quotation", [user("tell them about it now")], "x", "User said to tell them", None, 2),
    ("quote the user never typed", [user("what is going on")], "x", 'User said "tell them about the CI"', None, 2),
    ("a remark quoted back still needs words that exist",
     [user("isnt session notebook-b5 working on that")], "notebook-b5", 'User said "send the findings"', None, 2),
    ("a queued peer message is not the user",
     [{"type": "user", "message": {"role": "user", "content": "<cross-session-message>tell them about the CI</cross-session-message>"}}],
     "x", 'User said "tell them about the CI"', None, 2),
    ("a skill's injected text is not the user",
     [user("<command-message>vet-fable</command-message> tell the reviewer everything")], "x",
     'User said "tell the reviewer everything"', None, 2),
    ("send to main is never gated", [], "main", "", None, 0),
    ("an own sub-agent, by id, is no other session", SPAWN, "a07bcb8441794d92e", "", None, 0),
    ("an own sub-agent, by name", SPAWN, "reviewer", "", None, 0),
    ("an AskUserQuestion answer counts", ASK, "x", 'User said "Yes, tell the reviewer"', None, 0),
    ("the question text inside the result does not count", ASK, "x",
     'User said "Send the long question the agent wrote here"', None, 2),
    ("one instruction covers one message",
     [user("tell the session about the CI"), send("s1", "x", 'User said "tell the session about the CI"'), result("s1", "ok")],
     "y", 'User said "tell the session about the CI"', None, 2),
    ("a new instruction after a send covers the next",
     [user("tell the session about the CI"), send("s1", "x"), result("s1", "ok"), user("now tell the other one too")],
     "y", 'User said "now tell the other one too"', None, 0),
    ("a refused send does not use up the instruction",
     [user("tell the session about the CI"), send("s1", "x"), result("s1", "PreToolUse:SendMessage hook error: BLOCKED")],
     "x", 'User said "tell the session about the CI"', None, 0),
    ("a send to a sub-agent does not use up the instruction",
     SPAWN + [user("tell the session about the CI"), send("s1", "reviewer"), result("s1", "ok")],
     "x", 'User said "tell the session about the CI"', None, 0),
    ("a standing grant covers later sends to the peer it was first quoted to",
     GRANT + [user("okay, carry on")], "peer", 'User said (standing) "you guys collaborate among each other"', None, 0),
    ("a standing grant does not reach another peer",
     GRANT, "other", 'User said (standing) "you guys collaborate among each other"', None, 2),
    ("a grant already quoted to a peer needs no (standing) marker for that peer",
     GRANT, "peer", 'User said "you guys collaborate among each other"', None, 0),
    ("an instruction covers the conversation with its peer",
     [user("answer to that other session i sent them"),
      send("s1", "peer", 'User said "answer to that other session i sent them"'), result("s1", "ok"),
      user("fix the hook"), send("s2", "peer", 'User said "answer to that other session i sent them"'), result("s2", "ok")],
     "peer", 'User said "answer to that other session i sent them"', None, 0),
    ("an instruction quoted to one peer does not open another",
     [user("tell the session about the CI"), send("s1", "peer", 'User said "tell the session about the CI"'), result("s1", "ok")],
     "other", 'User said "tell the session about the CI"', None, 2),
    ("a refused send does not open the conversation",
     [user("tell the session about the CI"), send("s1", "peer", 'User said "tell the session about the CI"'),
      result("s1", "PreToolUse:SendMessage hook error: BLOCKED"), send("s2", "other", 'User said "x y z w v u"'), result("s2", "ok")],
     "peer", 'User said "tell the session about the CI"', None, 2),
    ("a standing grant given between sends covers a peer already messaged",
     [send("s0", "peer", 'User said "something else entirely"'), result("s0", "ok"),
      user("no need to prompt me like that again. please collaborate fully"),
      send("s1", "peer", 'User said "another instruction here"'), result("s1", "ok")],
     "peer", 'User said (standing) "please collaborate fully"', None, 0),
    ("a grant in casual wording counts",
     [send("s0", "peer", 'User said "something else entirely"'), result("s0", "ok"),
      user("lets continue, continue collabing with the other session"), send("s1", "peer"), result("s1", "ok")],
     "peer", 'User said (standing) "continue collabing with the other session"', None, 0),
    ("a standing grant does not open a first message to a peer",
     [user("you guys collaborate among each other"), send("s1", "other"), result("s1", "ok")],
     "peer", 'User said (standing) "you guys collaborate among each other"', None, 2),
    ("a refused send does not count as having messaged the peer",
     [user("you guys collaborate among each other"),
      send("s1", "peer", 'User said "you guys collaborate among each other"'),
      result("s1", "PreToolUse:SendMessage hook error: BLOCKED"), send("s2", "other"), result("s2", "ok")],
     "peer", 'User said (standing) "you guys collaborate among each other"', None, 2),
    ("a standing grant must be the user's words",
     GRANT, "peer", 'User said (standing) "collaborate freely with every session"', None, 2),
    ("a sub-agent never messages a peer", [user("tell the session about the CI")], "x",
     'User said "tell the session about the CI"', "sub-1", 2),
    ("a sub-agent may hand back to main", [], "main", "", "sub-1", 0),
]


def main():
    failed = 0
    for name, rows, to, summary, agent, want in CASES:
        got = run(rows, to, summary, agent)
        if got != want:
            failed += 1
            print("FAIL  %s: want exit %s, got %s" % (name, want, got))
    # An unreadable transcript fails closed.
    payload = json.dumps({"tool_name": "SendMessage", "transcript_path": "/nonexistent.jsonl",
                          "tool_input": {"to": "x", "summary": 'User said "abcdefgh"'}})
    if subprocess.run([sys.executable, "-I", HOOK], input=payload, text=True, capture_output=True).returncode != 2:
        failed += 1
        print("FAIL  unreadable transcript must be refused")
    print("\n%d cases, %d failed" % (len(CASES) + 1, failed))
    sys.exit(1 if failed else 0)


main()
