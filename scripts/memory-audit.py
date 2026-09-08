#!/usr/bin/env python3
# DESC: Report per-project agent-memory health — index size, entry age, oversized index lines
"""
memory-audit: Report-only health check of Claude Code memory dirs.

For each <config>/projects/*/memory/ dir, reports memory file count, MEMORY.md
index size (loaded unconditionally every session in that project), average and
oversized index lines, lazily-loaded body bytes, and entry age from frontmatter
`modified:` timestamps. Also totals the unconditional rules channel
(<config>/rules/*.md) and CLAUDE.md. Deletes and changes nothing.
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from claude_dirs import config_dirs

LINE_CAP = 160  # index lines above this are flagged as oversized
STALE_DAYS = 180

MODIFIED_RE = re.compile(r"^\s*modified:\s*['\"]?(\d{4}-\d{2}-\d{2})", re.M)


def index_lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [l.rstrip("\n") for l in f if l.startswith("- ")]
    except OSError:
        return []


def entry_dates(memory_dir, files):
    dates = []
    for name in files:
        try:
            with open(os.path.join(memory_dir, name), encoding="utf-8") as f:
                head = f.read(2048)
        except OSError:
            continue
        m = MODIFIED_RE.search(head)
        if m:
            dates.append(datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc))
    return dates


def audit_project(memory_dir):
    files = sorted(
        f for f in os.listdir(memory_dir)
        if f.endswith(".md") and f != "MEMORY.md"
    )
    index_path = os.path.join(memory_dir, "MEMORY.md")
    index_bytes = os.path.getsize(index_path) if os.path.isfile(index_path) else 0
    lines = index_lines(index_path)
    body_bytes = sum(os.path.getsize(os.path.join(memory_dir, f)) for f in files)
    dates = entry_dates(memory_dir, files)
    now = datetime.now(timezone.utc)
    return {
        "project": os.path.basename(os.path.dirname(memory_dir)),
        "files": len(files),
        "index_bytes": index_bytes,
        "lines": len(lines),
        "avg_line": sum(map(len, lines)) // len(lines) if lines else 0,
        "over_cap": sum(1 for l in lines if len(l) > LINE_CAP),
        "body_bytes": body_bytes,
        "oldest_days": max(((now - d).days for d in dates), default=None),
        "stale": sum(1 for d in dates if (now - d).days > STALE_DAYS),
    }


def channel_bytes(directory):
    if not os.path.isdir(directory):
        return 0, 0
    mds = [f for f in os.listdir(directory) if f.endswith(".md")]
    return len(mds), sum(os.path.getsize(os.path.join(directory, f)) for f in mds)


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--all", action="store_true", help="include projects with zero memories")
    args = parser.parse_args()

    for cfg in config_dirs():
        rows = []
        projects_root = os.path.join(cfg, "projects")
        for slug in sorted(os.listdir(projects_root)):
            memory_dir = os.path.join(projects_root, slug, "memory")
            if os.path.isdir(memory_dir):
                row = audit_project(memory_dir)
                if row["files"] or args.all:
                    rows.append(row)

        print(f"config: {cfg}")
        header = f"{'project':<40} {'files':>5} {'index':>7} {'lines':>5} {'B/line':>6} {'>cap':>4} {'bodies':>7} {'oldest':>6} {'stale':>5}"
        print(header)
        print("-" * len(header))
        for r in sorted(rows, key=lambda r: -r["index_bytes"]):
            oldest = f"{r['oldest_days']}d" if r["oldest_days"] is not None else "-"
            print(
                f"{r['project']:<40} {r['files']:>5} {r['index_bytes']:>6}B {r['lines']:>5} "
                f"{r['avg_line']:>6} {r['over_cap']:>4} {r['body_bytes']:>6}B {oldest:>6} {r['stale']:>5}"
            )

        total_index = sum(r["index_bytes"] for r in rows)
        n_rules, rules_bytes = channel_bytes(os.path.join(cfg, "rules"))
        claude_md = os.path.join(cfg, "CLAUDE.md")
        claude_bytes = os.path.getsize(claude_md) if os.path.isfile(claude_md) else 0
        print(
            f"\nunconditional per session: rules {rules_bytes}B ({n_rules} files) "
            f"+ CLAUDE.md {claude_bytes}B + that project's index (max {max((r['index_bytes'] for r in rows), default=0)}B)"
        )
        print(f"all indexes combined: {total_index}B; index lines over {LINE_CAP}B and entries idle >{STALE_DAYS}d are flagged\n")


if __name__ == "__main__":
    main()
