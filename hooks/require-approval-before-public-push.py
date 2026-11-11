#!/usr/bin/env python3
# DESC: PreToolUse hook on Bash — refuses a git push to a public GitHub repo until the push says what it discloses
"""Refuse a push to a public repository that has not been cleared for personal content.

Pushing to a public repo publishes; a force-push afterwards does not unpublish, because
GitHub keeps serving the commits by id. The rule (claude/rules/commit-atomically-as-you-build.md)
is that new personal information goes to a public repo only after the user approves it item
by item. This hook enforces it at the push, for GitHub remotes whose visibility is PUBLIC.

A push to a public repo passes when the command carries one of two markers, in a comment:

  git push  # public-push: no personal content
      The agent states that the outgoing commits add no personal information. Refused when
      those commits add or change an image, video, audio or PDF file: a picture of private
      work is the disclosure this marker cannot vouch for.

  git push  # public-push: user approved "<the user's words>"
      The quotation (8+ characters, case and spacing ignored) must appear in a prompt the
      user typed, or an answer they gave to an AskUserQuestion, later than this session's
      previous approved public push.

A push that sends no new commits (a rewind, a branch delete, an up-to-date push) passes with
no marker. Private, internal and non-GitHub remotes pass. Visibility comes from `gh repo view`,
cached a day under ${XDG_CACHE_HOME:-~/.cache}/agents-shared/repo-visibility/; when it cannot be
found the push is refused. Provenance: 2026-11-10, a site rebuild full of new personal content
went to a public repo in a routine push, and the user said "we will only commit such sensitive
data after my individual approvals".
"""

import json
import os
import re
import shlex
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

MIN_QUOTE = 8
CACHE_SECONDS = 86400
MEDIA = re.compile(r"\.(png|jpe?g|gif|webp|avif|heic|bmp|tiff?|svg|ico|mp4|mov|webm|mkv|m4v|mp3|wav|m4a|ogg|flac|pdf)$", re.I)
PUSH = re.compile(r"(?:^|[;&|(]\s*|\s)git((?:\s+-[Cc]\s+\S+)*)\s+push\b([^;&|\n#]*)")
MARK_CODE = re.compile(r"#\s*public-push:\s*no personal content", re.I)
MARK_USER = re.compile(r'#\s*public-push:\s*user approved\s+"([^"]+)"', re.I)

HOW = (
    "Before pushing, list what the outgoing commits make public that was not public before:\n"
    "names of people or companies, contact addresses, clients, business terms or prices,\n"
    "unreleased projects, private repos described, screenshots or images of private work.\n\n"
    "  - Nothing of that kind: add  # public-push: no personal content  to the command.\n"
    "  - Anything of that kind: show the list to the user, ask with AskUserQuestion, push only\n"
    "    what they approve, and add  # public-push: user approved \"<their words>\"  to the command.\n\n"
    "Unapproved work stays committed locally, on a branch with no upstream."
)


def refuse(reason):
    print("BLOCKED: " + reason + "\n\n" + HOW, file=sys.stderr)
    sys.exit(2)


def norm(s):
    return " ".join(s.lower().split())


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=10)
    return r.stdout if r.returncode == 0 else None


def repo_dir(command, start, git_opts, cwd):
    m = re.findall(r"-C\s+(\S+)", git_opts)
    if m:
        return os.path.expanduser(m[-1].strip("'\""))
    cds = re.findall(r"(?:^|[;&|]\s*)cd\s+(\"[^\"]+\"|'[^']+'|\S+)\s*(?:&&|;)", command[:start])
    if cds:
        d = os.path.expanduser(cds[-1].strip("'\""))
        return d if os.path.isabs(d) else os.path.join(cwd, d)
    return cwd


def github_slug(url):
    m = re.match(r"(?:git@github\.com:|ssh://git@github\.com/|https://(?:[^@/]+@)?github\.com/)([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    return (m.group(1), m.group(2)) if m else None


def visibility(owner, name):
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    path = os.path.join(base, "agents-shared", "repo-visibility", f"{owner}__{name}")
    try:
        if time.time() - os.path.getmtime(path) < CACHE_SECONDS:
            with open(path) as fh:
                return fh.read().strip()
    except OSError:
        pass
    try:
        r = subprocess.run(["gh", "repo", "view", f"{owner}/{name}", "--json", "visibility", "-q", ".visibility"],
                           capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return None
    vis = r.stdout.strip()
    if r.returncode != 0 or not vis:
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(vis + "\n")
    return vis


def outgoing(cwd, args):
    """Commits the push would send that the remote does not have, and the remote's name."""
    try:
        words = shlex.split(args)
    except ValueError:
        words = args.split()
    opts = [w for w in words if w.startswith("-")]
    pos = [w for w in words if not w.startswith("-")]
    remote = pos[0] if pos else "origin"
    if any(o in ("--all", "--mirror", "--branches") for o in opts):
        srcs = ["--branches"]
    else:
        srcs = []
        for spec in pos[1:] or ["HEAD"]:
            src = spec.lstrip("+").split(":", 1)[0]
            if src:
                srcs.append(src)
        if "--tags" in opts:
            srcs.append("--tags")
    if not srcs:
        return remote, []
    out = git(cwd, "rev-list", *srcs, "--not", f"--remotes={remote}", "--")
    if out is None:
        refuse(f"could not list the commits this push sends from {cwd} (sources {srcs}).")
    return remote, out.split()


def user_words_since_last_approved_push(path):
    from transcript_items import is_reply_boundary, is_typed_prompt, items  # noqa: E402
    rows = list(items(path, want={"user", "agents", "calls", "tools"}))
    refused = {it.get("tool_use_id") for it in rows
               if it["label"].startswith("TOOL-RESULT") and it["text"].lstrip().startswith("PreToolUse:")}
    last = -1
    for n, it in enumerate(rows):
        if it["label"] == "CALL Bash" and MARK_USER.search(it["text"]) and it.get("tool_use_id") not in refused:
            last = n
    said = []
    for n, it in enumerate(rows):
        if n <= last:
            continue
        if is_typed_prompt(it):
            said.append(norm(it["text"]))
        elif is_reply_boundary(it):
            said.extend(norm(p.split('"', 1)[0]) for p in it["text"].split('"="')[1:])
    return said


def main():
    try:
        data = json.load(sys.stdin)
        command = str((data.get("tool_input") or {}).get("command") or "")
        cwd = data.get("cwd") or os.getcwd()
    except (ValueError, AttributeError):
        refuse("the hook could not read its input.")
    if data.get("tool_name") != "Bash":
        return
    m = PUSH.search(command)
    if not m:
        return

    d = repo_dir(command, m.start(1), m.group(1), cwd)
    remote, commits = outgoing(d, m.group(2))
    url = git(d, "remote", "get-url", "--push", remote)
    slug = github_slug(url) if url else None
    if not slug or not commits:
        return
    vis = visibility(*slug)
    if vis is None:
        refuse(f"could not tell whether {slug[0]}/{slug[1]} is public (`gh repo view` failed).")
    if vis.upper() != "PUBLIC":
        return

    repo = f"{slug[0]}/{slug[1]}"
    mu = MARK_USER.search(command)
    if mu:
        q = norm(mu.group(1))
        if len(q) < MIN_QUOTE:
            refuse(f"the approval quote for {repo} is shorter than {MIN_QUOTE} characters.")
        path = data.get("transcript_path") or ""
        if not path or not os.path.isfile(path):
            refuse("the hook cannot read this session's transcript to check the approval.")
        if any(q in s for s in user_words_since_last_approved_push(path)):
            return
        refuse(f"the quote {mu.group(1)!r} is not in anything the user typed or answered since "
               f"this session's previous approved public push.")
    if MARK_CODE.search(command):
        media = git(d, "log", "--format=", "--name-only", "--diff-filter=AM", *commits[:200], "--no-walk") or ""
        found = sorted({f for f in media.split() if MEDIA.search(f)})
        if not found:
            return
        refuse(f"{repo} is public and this push adds or changes media, which needs the user's approval: "
               + ", ".join(found[:8]) + ("…" if len(found) > 8 else "") + ".")
    refuse(f"{repo} is PUBLIC, and this push sends {len(commits)} new commit(s) with no "
           f"`# public-push:` marker.")


if __name__ == "__main__":
    main()
