# Never hand-roll a transcript parser

**To read Claude Code transcripts (`~/.claude/projects/**/*.jsonl`), use the shared
reader: `$AGENTS_SHARED/scripts/extract-session-text.py`.** Never write an inline
`python3` or `jq` parser over the raw files, or a script that does the same. For a
task like "scour my chat logs", use the mine-chat-logs skill.

A hook adds a longer note, once per session, the first time a command or written
file reads a Claude projects folder with python, jq or similar. The full text is in
`docs/on-demand/never-hand-roll-a-transcript-parser.md`.
