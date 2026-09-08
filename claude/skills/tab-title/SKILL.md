---
description: Suggest a short tab title for the current chat, sized for the iTerm2 tab strip, as a ready-to-paste /rename line. Suggests only — never touches the terminal.
user-invocable: true
disable-model-invocation: true
argument-hint: [ignored]
---

# tab-rename

Read the conversation already in context and name it. No transcript parsing — the
chat is right here. No tools, no terminal writes: the output is a title and the
line that applies it.

## The title

Eighteen characters is what survives the tab strip; the status glyph and its space
cost two of them. Everything below serves that budget.

- **Lowercase throughout**, first word included. Keep capitals only where the thing
  is genuinely cased — `node01`, `iOS`, `Caddy`.
- **Name the subject, not the activity or the state.** `watchface compiler`, never
  `building the watchface compiler` or `watchface done`.
- **Most distinguishing word first.** Truncation eats the right end.
- **No prefixes.** Not the project, not the directory, not `claude`, `session`,
  `chat`, `task`, `fix`. The window already says where you are.
- **No trailing punctuation, no ellipsis, no articles** that can be dropped.
- Nouns, no filler. Two or three words is the usual shape.

Weight the *current* work over the opening prompt: a session that began as a bug
report and turned into a refactor is named for the refactor.

## Output

One code block, one line, nothing else:

```
/rename <title>
```

No preamble, no defence of the title, no alternates unless asked. It is visible in
the tab a second after it is pasted.

## Note

The title sticks because `/rename` outranks Claude Code's own generated topic title
(setting `terminalTitleFromRename`, default true). The status glyph in front of it
keeps working.
