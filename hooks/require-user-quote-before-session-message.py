#!/usr/bin/env python3
# DESC: PreToolUse hook on SendMessage — refuses a message to another session that cites no words the user typed
"""Refuse a message to a peer session unless the call quotes the user.

A message to another session lands in a context the user meant to keep, and cannot be
taken back (docs/on-demand/messages-between-sessions.md). The rule is that the user's own
words are the only authority for sending one. This hook makes the call prove it: the call's
`summary` (the one field the recipient never sees) must contain a quotation, in double
quotes, that appears in a prompt the user typed, or in an answer they gave to an
AskUserQuestion, later than this session's previous message to a peer. A question or remark
about a session ("isn't X working on that?") authorises nothing unless it is quoted as the
instruction it is not.

An instruction covers the conversation with the peer it was first quoted to, not one message:
a later send to that same peer may quote the same words again, however many messages the
exchange takes. Allowing one message per instruction made the user re-authorise every reply of
a two-session exchange ("what if the convo needs to take 20 turns??", 2026-10-28). Another peer
still needs a fresh quote.

  summary: User said "let that session know of what they are causing"

It checks provenance, not intent: any quoted user words pass. What it removes is the send
with no user words behind it, and it leaves a grep-able claim on every send.

A standing grant ("you two collaborate among each other", "no need to ask me") covers more
than one message, to the peers already in the conversation. A summary marked `(standing)` may
quote user words from anywhere in the session if three things hold: the user typed them, they
contain one of STANDING_STEMS, and an earlier send to the same recipient went out. The grant need
not have been quoted in that earlier send: requiring it once left a grant given between two sends
unusable, and the user was asked for words again after saying "please collaborate fully"
(2026-10-28). A peer never messaged before still needs a fresh quote.

  summary: User said (standing) "you guys collaborate among each other"

A peer that messaged this session first is the exception: its own `<cross-session-message>` names
it, and a reply pollutes nothing. A quote that grants answering ("if any other agents asks you
questions, I sent them, you can answer") covers a reply to every peer the transcript holds an
inbound message from, marked `(standing)` or not, however old it is next to the last send. Without
this a grant typed before the peer wrote was refused three ways and the user was asked again: "didnt
I already approve this ... I really dislike this asking again" (2026-11-12). The inbound message must
be one the transcript holds from that peer; an outbound-first send to a fresh session stays gated.

Not gated: a send to `main`; a send to a sub-agent this session spawned (matched by the
agentId in its spawn result, or the name it was given), which is no other session. A sub-agent
has no typed prompts, so its send to anyone else is refused: it hands back to `main`.

The user's text is read through scripts/transcript_items.py (is_typed_prompt, is_reply_boundary),
never parsed here. Fails closed on input or a transcript it cannot read.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from transcript_items import is_reply_boundary, is_typed_prompt, items  # noqa: E402

MIN_QUOTE = 8
# Wordings that hand coordination to the agents for good, not for one message.
STANDING_STEMS = ("collab", "coordinat", "work together", "among each other", "between each other",
                  "among yourselves", "between yourselves", "work it out", "sort it out",
                  "no need to ask", "without asking", "don't ask me", "dont ask me",
                  "no need to continously prompt", "no need to continuously prompt",
                  "you can answer", "you can reply", "answer them", "reply to them")


def norm(s):
    return " ".join(s.lower().split())


def inbound_peers(rows):
    """The `from` address and `from-name` of every peer message the transcript holds."""
    peers = set()
    for it in rows:
        if it["group"] != "user":
            continue
        m = re.match(r"\s*<cross-session-message\b([^>]*)>", it["text"] or "")
        if not m:
            continue
        for attr in ("from", "from-name"):
            a = re.search(r"(?<![\w-])" + attr + r"=(?:\"([^\"]*)\"|(\S+))", m.group(1))
            if a and (a.group(1) or a.group(2)):
                peers.add(a.group(1) or a.group(2))
    return peers


def refuse(reason, stale=None):
    if stale:
        print(
            "BLOCKED: " + reason + "\n\n"
            "Do not ask the user again: the quote is in their words, only older than your last send.\n"
            "If it is a standing grant (it says to collaborate, or to answer or reply), mark the summary\n"
            "and send again:\n\n"
            '    summary: User said (standing) "' + stale + '"\n\n'
            "A `(standing)` quote passes for a peer this session has already messaged, and for a reply\n"
            "to a peer that messaged this session first (its `from` address or `from-name`).\n"
            "Docs: docs/on-demand/messages-between-sessions.md and send-message-gate.md.",
            file=sys.stderr,
        )
        sys.exit(2)
    print(
        "BLOCKED: " + reason + "\n\n"
        "A message to another session needs the user's own words behind it. Put them in the call's\n"
        "`summary` (the recipient never sees it) as a quotation from something the user typed, or\n"
        "answered in an AskUserQuestion, after your previous message to a peer:\n\n"
        '    summary: User said "<their words>"\n\n'
        "The quote that opened a conversation with a peer covers every later send to that same peer:\n"
        "quote it again.\n"
        "A question or remark about a session is not an instruction to message it. If the user has not\n"
        "told you to send this, do not send it; tell the user what you found, in your reply. A send\n"
        "your own work is stuck on, with no instruction, is asked of the user with AskUserQuestion.\n"
        "A standing grant the user gave (\"collaborate among each other\") is reused by marking the\n"
        "summary `User said (standing) \"<their words>\"`, for a peer this session has already messaged.\n"
        "Docs: docs/on-demand/messages-between-sessions.md and send-message-gate.md.",
        file=sys.stderr,
    )
    sys.exit(2)


def answers(text):
    """The user's part of an AskUserQuestion result: what follows each `"="`, not the question."""
    return [p.split('"', 1)[0] for p in text.split('"="')[1:]] or [text]


def main():
    try:
        data = json.load(sys.stdin)
        tool_input = data.get("tool_input") or {}
        to = str(tool_input.get("to") or "")
        summary = str(tool_input.get("summary") or "")
        path = data.get("transcript_path") or ""
    except (ValueError, AttributeError):
        refuse("the hook could not read its input.")

    if data.get("tool_name") != "SendMessage" or to == "main":
        return
    if data.get("agent_id"):
        refuse("a sub-agent does not message other sessions; hand back to `main`.")
    if not path or not os.path.isfile(path):
        refuse("the hook cannot read this session's transcript (%r)." % path)

    try:
        rows = list(items(path, want={"user", "agents"}))
    except OSError:
        refuse("the hook cannot read this session's transcript.")

    own = set()  # agent ids and names of sub-agents this session spawned
    results = {}  # tool_use_id -> result text
    for it in rows:
        if it["group"] != "agents":
            continue
        if it["label"].startswith("RESULT"):
            results[it.get("tool_use_id")] = it["text"]
            m = re.search(r"agentId: (\S+)", it["text"])
            if m:
                own.add(m.group(1))
        elif it["label"] == "AGENT-SPAWN" and (it.get("input") or {}).get("name"):
            own.add(it["input"]["name"])
    if to in own:
        return

    # Messages to peers that went out: sent (the result is not a refusing hook's), not to a sub-agent.
    last, sent = -1, []
    for n, it in enumerate(rows):
        if it["label"] != "SENDMSG":
            continue
        res = results.get(it.get("tool_use_id"))
        inp = it.get("input") or {}
        target = inp.get("to")
        if res is None or res.lstrip().startswith("PreToolUse:") or target in own or target == "main":
            continue
        last = n
        sent.append((target, norm(str(inp.get("summary") or ""))))

    inbound = inbound_peers(rows)
    said, said_ever = [], []
    for n, it in enumerate(rows):
        if is_typed_prompt(it):
            words = [norm(it["text"])]
        elif is_reply_boundary(it):
            words = [norm(a) for a in answers(it["text"])]
        else:
            continue
        said_ever.extend(words)
        if n > last:
            said.extend(words)

    quotes = [norm(q) for q in re.findall(r'"([^"]+)"', summary)]
    quotes = [q for q in quotes if len(q) >= MIN_QUOTE]
    if not quotes:
        refuse("the call's `summary` has no quotation of the user (found %r)." % summary[:80])
    if any(q in s for q in quotes for s in said):
        return
    # An instruction to message a peer covers the conversation with that peer, not one message.
    for q in quotes:
        if any(q in s for s in said_ever) and any(t == to and q in sm for t, sm in sent):
            return
    # A standing grant covers a reply to a peer that wrote first, marked or not, however old it is.
    if to in inbound:
        for q in quotes:
            if any(stem in q for stem in STANDING_STEMS) and any(q in s for s in said_ever):
                return
    if "(standing)" in summary.lower():
        for q in quotes:
            if (any(stem in q for stem in STANDING_STEMS) and any(q in s for s in said_ever)
                    and any(t == to for t, _ in sent)):
                return
        refuse("a `(standing)` quote must be the user's words, grant coordination or answering in its "
               "wording (e.g. \"collaborate among each other\", \"you can answer\"), and go to a peer "
               "this session has already messaged or one that messaged this session first; a first "
               "message to any other peer needs a fresh quote.")
    stale = next((q for q in quotes if any(q in s for s in said_ever)), None)
    if stale:
        refuse("the quotation in `summary` is something the user said, but before your previous "
               "message to a peer.", stale=stale)
    refuse("no quotation in `summary` appears in anything the user typed or answered since your "
           "previous message to a peer (or since the session began).")

if __name__ == "__main__":
    main()
