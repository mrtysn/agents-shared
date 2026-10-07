#!/usr/bin/env python3
# DESC: PreToolUse hook: hold Firefox add-on signings to addons.mozilla.org's own rate limits
"""Refuse a signing that addons.mozilla.org would throttle, before it is sent.

AMO limits new versions per account (addons-server src/olympia/api/throttling.py): 3 a minute,
10 an hour and 24 in any 24 hours. Past the daily one it refuses for up to a day — on 2026-10-07 a
session that signed after every change hit it and the add-on could not be updated for 11 hours. So
each signing is logged, and one that would pass a limit is refused with the time it is allowed.

A signing is a command, in any segment (; && || | and inside sh/bash/zsh -c), that runs
`web-ext … sign` — through npx, yarn, pnpm dlx, env, doppler run --, with a version or flags — or
a repo's `release.zsh`, or a request to AMO's upload or versions API. Quoted text, a grep, a
commit message mentioning it are not.

  SIGNED_RELEASE_LOG   one epoch second per signing, appended
                       (default <config>/signed-releases.log; <config> = $CLAUDE_CONFIG_DIR or ~/.claude)

The limits are AMO's and per account, so one log serves every repo; a second config dir should
point SIGNED_RELEASE_LOG at the same file. There is no override: past a limit, the user runs the
command in their own shell. Fails closed on input it cannot read.
"""

import json
import os
import re
import shlex
import sys
import time

LIMITS = [(60, 3, "a minute"), (3600, 10, "an hour"), (86400, 24, "24 hours")]
LAUNCHERS = {"npx", "yarn", "pnpm", "dlx", "exec", "bunx", "env", "command", "time", "sudo", "nice", "nohup"}
SHELLS = {"sh", "bash", "zsh"}
SEPARATORS = {";", "&&", "||", "|", "&", "\n", "(", ")", "{", "}"}
AMO_API = re.compile(r"addons\.mozilla\.org/api/v\d+/addons/(upload|addon/[^/\s]+/versions)")


def segments(command):
    lex = shlex.shlex(command, posix=True, punctuation_chars=";&|()\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    seg = []
    for tok in lex:
        if tok in SEPARATORS or set(tok) <= set(";&|()\n"):
            if seg:
                yield seg
            seg = []
        else:
            seg.append(tok)
    if seg:
        yield seg


def dry(args):
    """A release script asked only to describe itself signs nothing."""
    return any(a in ("--dry-run", "--help", "-h") for a in args)


def is_web_ext(tok):
    return re.fullmatch(r"(.*/)?web-ext(@\S+)?", tok) is not None


def signs(seg):
    """Whether one segment's command is a signing; recurses into sh -c strings."""
    i = 0
    while i < len(seg):
        tok = seg[i]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tok) or tok in LAUNCHERS or tok.startswith("-"):
            i += 1
            continue
        if tok == "doppler":
            # doppler run [flags] -- <command>
            i = seg.index("--") + 1 if "--" in seg[i:] else len(seg)
            continue
        if tok in SHELLS:
            rest = seg[i + 1:]
            if "-c" in rest and rest.index("-c") + 1 < len(rest):
                return is_signing(rest[rest.index("-c") + 1])
            return any(t.endswith("release.zsh") for t in rest) and not dry(rest)
        if tok.endswith("release.zsh"):
            return not dry(seg[i + 1:])
        if is_web_ext(tok):
            for arg in seg[i + 1:]:
                if not arg.startswith("-"):
                    return arg == "sign"
            return False
        if tok in {"curl", "wget", "http", "https"}:
            return any(AMO_API.search(t) for t in seg[i + 1:])
        return False
    return False


def is_signing(command):
    try:
        return any(signs(seg) for seg in segments(command))
    except ValueError:
        # Unbalanced quotes: judge the raw text, erring on the side of a signing.
        return re.search(r"web-ext\S*\s+(-\S+\s+)*sign\b|release\.zsh|" + AMO_API.pattern, command) is not None


def main():
    try:
        command = json.load(sys.stdin).get("tool_input", {}).get("command") or ""
    except Exception:
        print("BLOCKED: limit-signed-releases could not read the tool call", file=sys.stderr)
        sys.exit(2)
    if not command or not is_signing(command):
        sys.exit(0)

    log = os.environ.get("SIGNED_RELEASE_LOG") or os.path.join(
        os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "signed-releases.log")
    now = time.time()
    try:
        with open(log) as f:
            stamps = sorted(float(x) for x in f.read().split() if x.strip())
    except FileNotFoundError:
        stamps = []

    for window, limit, name in LIMITS:
        recent = [s for s in stamps if s > now - window]
        if len(recent) >= limit:
            free = recent[-limit] + window
            when = time.strftime("%a %H:%M", time.localtime(free))
            print(f"BLOCKED: {len(recent)} add-on signings in the last {name}; addons.mozilla.org allows {limit}.", file=sys.stderr)
            print(f"The next one is allowed after {when}. Sign once per finished batch: keep committing and ship", file=sys.stderr)
            print("the batch then. If a release cannot wait, ask the user to run the signing themselves.", file=sys.stderr)
            sys.exit(2)

    os.makedirs(os.path.dirname(log) or ".", exist_ok=True)
    # Appended, never rewritten, so two sessions signing at once cannot lose a line.
    with open(log, "a") as f:
        f.write(f"{int(now)}\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
