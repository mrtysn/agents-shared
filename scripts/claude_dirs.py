#!/usr/bin/env python3
"""Discovery of Claude Code config dirs, transcripts, and live sessions.

Shared by iterm-revive, recent-sessions, and search-history so that every
CLAUDE_CONFIG_DIR is visible, not just ~/.claude.
"""

import glob
import os
import re
import subprocess

DEFAULT_CONFIG_DIR = os.path.expanduser("~/.claude")
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")


def config_dirs():
    """Every claude config dir holding transcripts: ~/.claude*, the current
    CLAUDE_CONFIG_DIR, and any CLAUDE_CONFIG_DIR found in the environment of
    a running claude process."""
    dirs = {d for d in glob.glob(os.path.expanduser("~/.claude*")) if os.path.isdir(f"{d}/projects")}
    env_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if env_dir and os.path.isdir(f"{env_dir}/projects"):
        dirs.add(env_dir)
    for pid in _claude_pids():
        env = subprocess.run(["ps", "eww", "-o", "command=", "-p", pid], capture_output=True, text=True).stdout
        m = re.search(r"CLAUDE_CONFIG_DIR=(\S+)", env)
        if m and os.path.isdir(f"{m.group(1)}/projects"):
            dirs.add(m.group(1))
    return sorted(dirs)


def find_transcript(session_id):
    """(path, config_dir) for a session uuid, searching all config dirs."""
    for cfg in config_dirs():
        matches = glob.glob(f"{cfg}/projects/*/{session_id}.jsonl")
        if matches:
            return matches[0], cfg
    return None, None


def _claude_pids():
    return subprocess.run(["pgrep", "-x", "claude"], capture_output=True, text=True).stdout.split()


def live_resume_uuids():
    """Session uuids named in a running claude's --resume argv: definitely live."""
    ps = subprocess.run(["ps", "-axo", "command="], capture_output=True, text=True).stdout
    uuids = set()
    for line in ps.splitlines():
        stripped = line.strip()
        if stripped.startswith("claude ") and "--resume" in stripped:
            m = UUID_RE.search(stripped)
            if m:
                uuids.add(m.group(0))
    return uuids


def live_claude_cwds():
    """cwd of every running claude process, via lsof."""
    cwds = set()
    for pid in _claude_pids():
        out = subprocess.run(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if line.startswith("n"):
                cwds.add(line[1:])
    return cwds
