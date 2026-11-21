"""Cases for hooks/note-secret-in-tool-output.py.

Every credential here is made up, and the token-shaped ones are built at run time from pieces, so no
literal in this file looks like a live key to a scanner. Each positive case also checks that the
note never holds the matched text.
"""

import json
import os
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "note-secret-in-tool-output.py")

GITHUB = "gh" + "p_" + "A1b2C3d4E5" * 4
OPENAI = "sk" + "-proj-" + "Zx9Yw8Vu7T" * 3
PEM = "-----BEGIN " + "OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----"


def run(payload, cache):
    out = subprocess.run([sys.executable, "-I", HOOK], input=json.dumps(payload) if not isinstance(payload, str) else payload,
                         capture_output=True, text=True, env={**os.environ, "XDG_CACHE_HOME": cache})
    assert out.returncode == 0, out.stderr
    return out.stdout


def bash(stdout, command="cat notes.txt", session="s1"):
    return {"session_id": session, "tool_name": "Bash", "tool_input": {"command": command},
            "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False}}


def read(content, path="/tmp/example/config.txt", session="s1"):
    return {"session_id": session, "tool_name": "Read", "tool_input": {"file_path": path},
            "tool_response": {"type": "text", "file": {"filePath": path, "content": content}}}


# (name, payload, expected words in the note or None for no note, secret that must not appear)
CASES = [
    ("password field in command output", bash("login: someone\npassword: correct-horse-9\n"),
     ["a password or secret field", "from this command"], "correct-horse-9"),
    ("Turkish password field", bash("şifre: Gizli1234\n", command="head -3 note.txt"),
     ["a password or secret field"], "Gizli1234"),
    ("quoted JSON password", read('{"user": "a", "password": "hunter2-x"}', path="/tmp/example/a.json"),
     ["a password or secret field", "/tmp/example/a.json"], "hunter2-x"),
    ("GitHub token in a file", read(f"GITHUB_TOKEN={GITHUB}\n", path="/tmp/example/.env"),
     ["a GitHub token", "/tmp/example/.env"], GITHUB),
    ("OpenAI key in a .env", read(f"OPENAI_API_KEY={OPENAI}\n", path="/tmp/example/b.env"),
     ["an Anthropic or OpenAI key"], OPENAI),
    ("private key block", bash(PEM + "\n", command="cat id_test"), ["a private key block"], "b3BlbnNzaC1rZXktdjEAAAAA"),
    ("a token only in the command adds no note", bash("ok\n", command=f"curl -H 'Authorization: Bearer {GITHUB}' x"),
     None, None),
    ("code reading the password from the environment", read('password = os.environ["DB_PASSWORD"]\n'), None, None),
    ("type hint", read("def login(user: str, password: str) -> bool:\n"), None, None),
    ("prose about passwords", read("Never print a password, token or key.\n"), None, None),
    ("placeholder value", read("API_KEY=your-api-key-here\n"), None, None),
    ("short token value", bash("token: abc123\n"), None, None),
    ("template value", read("password: ${DB_PASSWORD}\n"), None, None),
    ("dotted name value", read("password = settings.db_password\n"), None, None),
    ("code assigning a variable", read("const token = journeyOwnerToken;\npassword = userPassword\n"), None, None),
    ("pointer to the keychain", read('Password=keychain:example/account"\n'), None, None),
    ("token field with a long literal value", bash("token: a8F3kd92LmQ0zXv71\n"), ["a password or secret field"],
     "a8F3kd92LmQ0zXv71"),
    ("blanked transcript text", bash("password: [secret removed]\n"), None, None),
    ("tool not watched", {"session_id": "s1", "tool_name": "Edit", "tool_input": {"file_path": "/tmp/x"},
                          "tool_response": {"content": "password: correct-horse-9"}}, None, None),
]


def main():
    failures = 0
    for name, payload, expect, secret in CASES:
        with tempfile.TemporaryDirectory() as cache:
            out = run(payload, cache)
        ok = (not out) if expect is None else all(w in out for w in expect) and (secret is None or secret not in out)
        if expect is not None and out:
            note = json.loads(out)["hookSpecificOutput"]
            ok = ok and note["hookEventName"] == "PostToolUse"
        print(f"{'ok  ' if ok else 'FAIL'} {name}")
        failures += not ok

    with tempfile.TemporaryDirectory() as cache:
        first = run(bash("password: correct-horse-9\n"), cache)
        again = run(bash("password: correct-horse-9\n"), cache)
        other_session = run(bash("password: correct-horse-9\n", session="s2"), cache)
        other_source = run(bash("password: correct-horse-9\n", command="cat other.txt"), cache)
    ok = bool(first) and not again and bool(other_session) and bool(other_source)
    print(f"{'ok  ' if ok else 'FAIL'} once per source per session")
    failures += not ok

    with tempfile.TemporaryDirectory() as cache:
        out = run("not json", cache)
    print(f"{'ok  ' if not out else 'FAIL'} unreadable input adds no note")
    failures += bool(out)

    print(f"{len(CASES) + 2 - failures} of {len(CASES) + 2} passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
