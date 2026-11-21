#!/usr/bin/env python3
# DESC: PostToolUse hook (Bash, Read, Grep) — notes when a tool's output holds text shaped like a credential
"""Say it when a tool shows a secret.

A command, file read or search can print a password, token or key the agent did not set out to
read. From then on it is in the session transcript and has gone to the model provider: it is
exposed, and only the user can change it. This hook scans the output of Bash, Read and Grep calls
for text shaped like a credential and adds a note: tell the user once, repeat nothing of it, do not
open its source again or use it. What it misses is covered by the "Private content" section of
claude/rules/working-style.md.

It never blocks, and never prints, logs or stores what it matched. The note names the kind of match
and its source: the file for Read, the path searched for Grep, "this command" for Bash, as a command
can carry a token itself. Once per source per session, marked by a hash of the source under
${XDG_CACHE_HOME:-~/.cache}/agents-shared/note-secret-in-tool-output/. Fails open: any error adds
no note.
"""

import hashlib
import json
import os
import re
import sys

# Shapes of credentials that are hard to mistake, each with the words the note names it by.
TOKENS = [
    ("a private key block", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----")),
    ("an Anthropic or OpenAI key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}")),
    ("a GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("a Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("an AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("a Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("a Stripe key", re.compile(r"\b[rs]k_live_[0-9A-Za-z]{20,}")),
    ("a JSON web token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("a bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}")),
]

# A field that names a secret, followed by a value. The value must look like a literal: code that
# fetches the secret from elsewhere, a type, a template or a placeholder is not one.
FIELD = re.compile(
    r"""(?ix)(?<![\w-])
    (?P<key>password|passwd|passphrase|parola|şifre|sifre|secret|client[_-]?secret|api[_-]?key|
            access[_-]?key|secret[_-]?key|auth[_-]?token|access[_-]?token|token)
    ["']?\s*[:=]\s*(?P<value>"[^"\n]*"|'[^'\n]*'|[^\s,;]+)"""
)
SHORT_KEYS = {"password", "passwd", "passphrase", "parola", "şifre", "sifre"}
PLACEHOLDER = re.compile(
    r"(?i)^(?:x+|\*+|\.+|-+|<.*>|\{.*\}|your[_-].*|change[_-]?me|example|placeholder|redacted|hidden|"
    r"secret|password|token|null|none|nil|true|false|undefined|string|str|bytes|int|required|optional|"
    r"env|\[secret removed\])$"
)
CODE = re.compile(r"[()\[\]{}$<>`]|\b(?:os\.|process\.env|environ|getenv|input|request|args|self\.|this\.)")
DOTTED_NAME = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$")
# A variable's name, as code assigns it: camelCase or with an underscore, and no digit.
VARIABLE = re.compile(r"^(?=[A-Za-z_]*(?:[a-z][A-Z]|_))[A-Za-z_]+$")
# A pointer to where a secret is kept, not the secret.
STORE = re.compile(r"(?i)^(?:keychain|op|vault|env|file|secret|ssm|kms|pass)(?::|://)")

MAX_SCAN = 1_000_000


def literal_value(key, value):
    """Whether a field's value looks like a secret written out, not code or a placeholder."""
    value = value.strip().rstrip(",;")
    quoted = len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'"
    inner = value[1:-1] if quoted else value
    if not inner or CODE.search(inner) or PLACEHOLDER.match(inner) or DOTTED_NAME.match(inner) or STORE.match(inner):
        return False
    if not quoted and VARIABLE.match(inner):
        return False
    if key.lower() in SHORT_KEYS:
        return len(inner) >= 6
    return len(inner) >= 16 and any(c.isdigit() for c in inner)


def kinds_in(text):
    """The kinds of credential shapes in `text`, in a stable order, without the matches themselves."""
    text = text[:MAX_SCAN]
    found = [name for name, pattern in TOKENS if pattern.search(text)]
    if any(literal_value(m.group("key"), m.group("value")) for m in FIELD.finditer(text)):
        found.append("a password or secret field")
    return found


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def source_of(tool, tool_input):
    if tool == "Read":
        return tool_input.get("file_path") or "this file"
    if tool == "Grep":
        path = tool_input.get("path")
        return f"a search of {path}" if path else "this search"
    return "this command"


def marker_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "agents-shared", "note-secret-in-tool-output")


def first_time(session, tool, tool_input):
    """Whether this source has not had a note in this session yet; records it if so."""
    key = json.dumps([tool, tool_input.get("file_path"), tool_input.get("path"), tool_input.get("pattern"),
                      tool_input.get("command")], ensure_ascii=False)
    digest = hashlib.sha256(key.encode()).hexdigest()
    folder = marker_dir()
    os.makedirs(folder, exist_ok=True)
    marker = os.path.join(folder, re.sub(r"[^\w-]", "_", session or "no-session"))
    seen = set(open(marker).read().split()) if os.path.exists(marker) else set()
    if digest in seen:
        return False
    with open(marker, "a") as f:
        f.write(digest + "\n")
    return True


def note(tool, kinds, source):
    kind = " and ".join(kinds[:2])
    return (f"This {tool} output holds text shaped like a credential ({kind}), from {source}. "
            "Treat it as exposed: it is now in the session transcript and went to the model provider. "
            "In your next reply tell the user once where it came from and that it is exposed; repeat nothing "
            "of it there or in summaries, compact messages, memory, handoffs or subagent briefs, and do not "
            "open the source again or use it. If it is plainly not a secret (a placeholder, an example, code "
            "that reads one from elsewhere), say that in one line instead.")


def main():
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name", "")
    if tool not in ("Bash", "Read", "Grep"):
        return
    tool_input = payload.get("tool_input") or {}
    kinds = []
    for text in strings(payload.get("tool_response")):
        for kind in kinds_in(text):
            if kind not in kinds:
                kinds.append(kind)
    if not kinds or not first_time(payload.get("session_id"), tool, tool_input):
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                             "additionalContext": note(tool, kinds, source_of(tool, tool_input))}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
