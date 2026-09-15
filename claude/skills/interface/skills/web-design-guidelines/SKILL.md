---
name: web-design-guidelines
description: Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best practices".
metadata:
  author: vercel
  version: "1.0.0"
  argument-hint: <file-or-pattern>
---

# Web Interface Guidelines

Review files for compliance with Web Interface Guidelines.

## How It Works

1. Read the guidelines from `references/command.md` in this skill's directory
2. Read the specified files (or prompt user for files/pattern)
3. Check against all rules in those guidelines
4. Output findings in the terse `file:line` format

## Guidelines Source

<!-- LOCAL: the rules are vendored as references/command.md from vercel-labs/web-interface-guidelines at e3d624baaf29dc1fc645aff3e38f03e564d2d6b1 (2026-08-17), MIT, with its Title Case rule removed because better-writing sets sentence case; no fetch at review time -->
Read `references/command.md` next to this file. It contains all the rules and output format instructions. Do not fetch the upstream URL.
<!-- LOCAL END -->

## Usage

When a user provides a file or pattern argument:
1. Read `references/command.md`
2. Read the specified files
3. Apply all rules from those guidelines
4. Output findings using the format specified in the guidelines

If no files specified, ask the user which files to review.
