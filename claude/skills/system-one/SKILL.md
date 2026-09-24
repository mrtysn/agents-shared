---
name: system-one
description: Use when a session needs a bounded judgment over some text - classify, route, triage, a yes/no gate, a score on an ordered scale, or pick one of N options - with a confidence attached, cheaply and locally, instead of reasoning it out in prose or spawning an LLM sub-agent for it. Covers routing, filtering, labelling loops, and replacing a throwaway `claude -p` yes/no check. Not for generation, multi-step reasoning, or pixel/coordinate precision.
---

# system-one

A local decision model (Laya, one warm server on loopback, port 7811). It
answers typed questions about a text state and returns calibrated
probabilities, not prose, in roughly 65 ms once warm. Nothing leaves the
machine; the model does not generate text, it only scores the options given.

## When to use it

A bounded check: a yes/no gate, routing to one of a fixed set of choices, a
score on an ordered scale, triage in a labelling loop, or replacing a
throwaway LLM call that only needs one word back.

Not for generation, multi-step reasoning, open-ended judgment, or
pixel/coordinate precision. It scores options you already know how to
enumerate; it does not invent them.

## The call

Check the server, then send one request:

```bash
system-one status
```

If it is not running, `system-one start` (returns at once, model loads in a
few seconds). Only from an interactive session, never from a hook. Never
stop a server you did not start.

```bash
printf '%s' '{
  "state": "cwd: /path/to/repo\ncommand:\nrm -rf build/tmp",
  "questions": {
    "irreversible": {"type": "noul", "instructions": "Does this command destroy data or history with no backup and no way to get it back?"},
    "target": {"type": "choice", "instructions": "What kind of thing does this command primarily act on?", "criteria": {"filesystem": "local files or directories", "process": "a running process or service", "network": "a remote host or network resource"}},
    "destructiveness": {"type": "score", "instructions": "How destructive is this command?", "criteria": ["low", "medium", "high"]}
  }
}' | system-one ask
```

Use `printf`, not `echo` (some shells mangle its quoting). Batch every
question a task needs into one call.

Answer shape, under `answers`:
- `noul`: `answers.<q>.noul` is P(yes), 0 to 1.
- `choice`: `answers.<q>.choice` is the picked key, plus
  `answers.<q>.probabilities` per criteria key.
- `score`: `answers.<q>.score` is the expected value over the ordered levels
  (a float), plus `answers.<q>.probabilities` keyed by level index string.

Verified live against the running server: the call above returned
`irreversible.noul: 0.74`, `target.choice: "filesystem"` with
`target.probabilities`, and `destructiveness.score: 0.82` with
`destructiveness.probabilities` keyed `"0"/"1"/"2"` - matching this shape.

## Thresholds

Read the probability, do not take the top pick on faith. Pick a threshold
sized to the cost of a false positive and state it where you call this
(0.7-0.9 for anything gating a risky action; see
`hooks/system-one-bash-questions.json` for real numbers). Below threshold,
fall back to full LLM reasoning or ask the user; at or above, act. For
`score`, normalise by dividing by `k - 1` (levels minus one) first.

## Fail-open

Empty output or a non-zero exit means the server is down or timed out.
Treat that as no answer and fall back to what you would have done without
it - never start the server from a hook to recover, never retry in a loop.
From an interactive session, `system-one start` is fine.

## Shadow mode

The Bash PreToolUse hook already runs this in shadow mode on every command,
logging what it would have done without acting. `system-one shadow-report`
shows the would-act rate and recent verdicts.
