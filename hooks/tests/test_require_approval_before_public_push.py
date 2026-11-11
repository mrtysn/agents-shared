"""Cases for require-approval-before-public-push.py, on throwaway repos and transcripts built here.

Visibility is seeded in the hook's cache, so no case calls `gh`."""

import json
import os
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "require-approval-before-public-push.py")
TMP = tempfile.mkdtemp()
CACHE = os.path.join(TMP, "cache")
os.makedirs(os.path.join(CACHE, "agents-shared", "repo-visibility"))
for slug, vis in (("t__pub", "PUBLIC"), ("t__priv", "PRIVATE")):
    with open(os.path.join(CACHE, "agents-shared", "repo-visibility", slug), "w") as fh:
        fh.write(vis + "\n")


def sh(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def repo(name, url, files):
    """A repo whose origin has the first commit; later commits, one per file, are outgoing."""
    d = os.path.join(TMP, name)
    os.makedirs(d)
    sh(d, "git", "init", "-q", "-b", "main")
    sh(d, "git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "base")
    sh(d, "git", "remote", "add", "origin", url)
    sh(d, "git", "update-ref", "refs/remotes/origin/main", "HEAD")
    for f in files:
        with open(os.path.join(d, f), "w") as fh:
            fh.write(f)
        sh(d, "git", "add", f)
        sh(d, "git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", f)
    return d


PUB = repo("pub", "git@github.com:t/pub.git", ["a.ts"])
PUB_IMG = repo("pubimg", "https://github.com/t/pub.git", ["a.ts", "shot.jpg"])
PRIV = repo("priv", "git@github.com:t/priv.git", ["a.ts"])
SAME = repo("same", "git@github.com:t/pub.git", [])
OTHER = repo("other", "git@gitlab.com:t/pub.git", ["a.ts"])


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def call(tid, name, inp):
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def result(tid, text):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": text}]}}


ASK = [call("q1", "AskUserQuestion", {"questions": []}),
       result("q1", 'User has answered your questions: "Push these two items?"="yes push those two items"')]
APPROVED_PUSH = [call("b1", "Bash", {"command": 'git push  # public-push: user approved "yes push those two items"'}),
                 result("b1", "pushed")]


FORM = os.path.join(TMP, "form.html")
with open(os.path.join(TMP, "form.answers.json"), "w") as fh:
    json.dump({"answers": {"arch-page": {"choice": "remove", "text": "no names in the images as well"},
                           "side": {"choices": ["oj", "lavalamp"]}}}, fh)
FORM_CALL = [call("f1", "Bash", {"command": f"project-lifecycle decision-wait {FORM} --json"}), result("f1", "running")]


def run(command, cwd, rows=()):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, dir=TMP) as fh:
        for r in rows:
            r.setdefault("sessionId", "s")
            fh.write(json.dumps(r) + "\n")
    payload = {"tool_name": "Bash", "cwd": cwd, "transcript_path": fh.name, "tool_input": {"command": command}}
    env = {**os.environ, "XDG_CACHE_HOME": CACHE}
    return subprocess.run([sys.executable, "-I", HOOK], input=json.dumps(payload), text=True,
                          capture_output=True, env=env).returncode


CASES = [
    ("not a push", "git status", PUB, [], 0),
    ("public push with no marker", "git push", PUB, [], 2),
    ("public push via cd prefix", f"cd {PUB} && git push origin main", "/", [], 2),
    ("cd prefix from an unrelated cwd", f"cd {PUB} && git push origin main  # public-push: no personal content", PRIV, [], 0),
    ("public push via git -C", f"git -C {PUB} push", "/", [], 2),
    ("code-only marker passes", "git push  # public-push: no personal content", PUB, [], 0),
    ("code-only marker refused when an image goes out", "git push  # public-push: no personal content", PUB_IMG, [], 2),
    ("approved quote passes", 'git push  # public-push: user approved "yes push those two items"', PUB_IMG, ASK, 0),
    ("quote the user never gave", 'git push  # public-push: user approved "push everything now"', PUB, ASK, 2),
    ("short quote", 'git push  # public-push: user approved "yes"', PUB, [user("yes")], 2),
    ("an approval covers one push", 'git push  # public-push: user approved "yes push those two items"', PUB,
     ASK + APPROVED_PUSH, 2),
    ("a refused push does not use up the approval", 'git push  # public-push: user approved "yes push those two items"',
     PUB, ASK + [APPROVED_PUSH[0], result("b1", "PreToolUse:Bash hook error: BLOCKED")], 0),
    ("a decision-form note passes", 'git push  # public-push: user approved "no names in the images as well"', PUB, FORM_CALL, 0),
    ("a decision-form pick passes", 'git push  # public-push: user approved "arch-page: remove"', PUB, FORM_CALL, 0),
    ("a pick the form does not hold", 'git push  # public-push: user approved "arch-page: keep it"', PUB, FORM_CALL, 2),
    ("a command that only contains the marker text is not a push",
     'git push  # public-push: user approved "arch-page: remove"', PUB,
     FORM_CALL + [call("w1", "Bash", {"command": "cat > t.py <<'X'\n('git push  # public-push: user approved \"x y z w v\"', 0)\nX"}),
                  result("w1", "")], 0),
    ("prose mentioning a push is not a push", 'echo "this is a git push test"', PUB, [], 0),
    ("a form served before the last approved push does not count",
     'git push  # public-push: user approved "arch-page: remove"', PUB,
     FORM_CALL + [call("b2", "Bash", {"command": 'git push  # public-push: user approved "arch-page: remove"'}), result("b2", "pushed")], 2),
    ("private repo passes", "git push", PRIV, [], 0),
    ("non-GitHub remote passes", "git push", OTHER, [], 0),
    ("nothing new to send passes", "git push", SAME, [], 0),
    ("rewind to an ancestor passes", "git push --force-with-lease origin HEAD~1:refs/heads/main", PUB, [], 0),
    ("explicit refspec with new commits", "git push origin main:refs/heads/main", PUB, [], 2),
]

failed = 0
for name, command, cwd, rows, want in CASES:
    got = run(command, cwd, [dict(r) for r in rows])
    ok = got == want
    failed += not ok
    print(("ok   " if ok else "FAIL ") + f"{name} (want {want}, got {got})")
sys.exit(1 if failed else 0)
