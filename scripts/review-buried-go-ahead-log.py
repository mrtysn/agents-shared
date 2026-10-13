#!/usr/bin/env python3
# DESC: Score the log-only go-ahead hook's rows against the user's next typed message
"""
review-buried-go-ahead-log: join each row hooks/log-buried-go-ahead.sh logged with
the user's next typed message in that session's transcript. A bare go-ahead
("proceed", "go", "continue", "yes", "do it", "go ahead", with an optional
"ok" or "lets") after the row is a true match; any other reply is a false one.

Verdict: with at least MIN_ROWS rows, a true-match rate of TRUE_RATE or more
means the hook is ready to block (see TODO.md); below it, tighten the pattern.
Fewer rows than MIN_ROWS: not enough data yet.

    review-buried-go-ahead-log.py [--log-dir DIR]
"""

import argparse
import bisect
import datetime
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from claude_dirs import config_dirs  # noqa: E402

MIN_ROWS = 20
TRUE_RATE = 0.7
GO = re.compile(r"^(ok(ay)?[ ,.]*)?(yes[ ,.]*)?(lets |let's |you can )?(proceed|go ahead|go|continue|do it|yes|yea|yep)( now)?[ .!]*$", re.I)


def epoch(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def typed_messages(session):
    for d in config_dirs():
        for path in glob.glob(f"{d}/projects/*/{session}.jsonl"):
            out = []
            with open(path) as fh:
                for line in fh:
                    if '"user"' not in line:
                        continue
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if e.get("type") != "user" or e.get("isSidechain") or e.get("isMeta"):
                        continue
                    c = e.get("message", {}).get("content")
                    if isinstance(c, list):
                        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                            continue
                        c = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
                    if isinstance(c, str) and c.strip() and not c.startswith(("<", "[Request")):
                        out.append((epoch(e["timestamp"]), c.strip()))
            return sorted(out)
    return []


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    default = os.path.join(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")), "log-buried-go-ahead")
    ap.add_argument("--log-dir", default=default)
    a = ap.parse_args()
    rows = true = unanswered = 0
    false_examples = []
    for path in glob.glob(f"{a.log_dir}/*.jsonl"):
        for line in open(path):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            msgs = typed_messages(r["session_id"])
            i = bisect.bisect_right([t for t, _ in msgs], epoch(r["ts"]))
            if i >= len(msgs):
                unanswered += 1
                continue
            rows += 1
            if GO.match(msgs[i][1]):
                true += 1
            elif len(false_examples) < 8:
                false_examples.append((r["phrase"], msgs[i][1][:80]))
    print(f"rows with a next message: {rows}  true matches: {true}  not yet answered: {unanswered}")
    if rows:
        print(f"true-match rate: {true / rows:.2f}")
    if rows < MIN_ROWS:
        print(f"verdict: not enough data (need {MIN_ROWS} rows)")
    elif true / rows >= TRUE_RATE:
        print("verdict: ready to block (change the hook per TODO.md)")
    else:
        print("verdict: tighten the pattern first")
    for phrase, nxt in false_examples:
        print(f"  false: [{phrase}] -> {nxt!r}")


if __name__ == "__main__":
    main()
