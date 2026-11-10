#!/usr/bin/env python3
"""usage-survey.py's per-file index gives the same --json as a full parse, after a file is
appended to, a file is rewritten shorter, a file is deleted and a file is added.

Fake transcripts in a temp dir; nothing in ~/.claude is read.
Run: python3 scripts/tests/test_usage_survey_index.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SURVEY = Path(__file__).resolve().parent.parent / "usage-survey.py"


def user(ts, text):
    return {"type": "user", "timestamp": ts, "message": {"content": text}}


def tool(ts, name, **inp):
    return {"type": "assistant", "timestamp": ts,
            "message": {"content": [{"type": "text", "text": "looks like it, shall I?"},
                                    {"type": "tool_use", "id": f"t{ts}", "name": name, "input": inp}]}}


def write(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))


def bump(path):
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))


class IndexMatchesFullRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cfg = root / "claude"
        self.index = root / "cache" / "index.json"
        proj = self.cfg / "projects" / "-Users-x-dev-alpha"
        self.a = proj / "aaaa.jsonl"
        self.b = proj / "bbbb.jsonl"
        self.c = self.cfg / "projects" / "-Users-x-dev-beta" / "cccc.jsonl"
        self.sub = proj / "aaaa" / "subagents" / "agent-1.jsonl"
        write(self.a, [user("2026-11-01T10:00:00Z", "/handoff now"),
                       tool("2026-11-01T10:00:01Z", "Skill", skill="outstanding"),
                       tool("2026-11-01T10:00:02Z", "Bash", command="git status && ls")])
        write(self.b, [user("2026-11-02T10:00:00Z", "why is this slow?"),
                       tool("2026-11-02T10:00:01Z", "Skill", skill="handoff"),
                       tool("2026-11-02T10:00:02Z", "Edit", file_path="/m/memory/x.md")])
        write(self.c, [user("2026-11-03T10:00:00Z", "no, wrong file"),
                       tool("2026-11-03T10:00:01Z", "Skill", skill="outstanding")])
        write(self.sub, [tool("2026-11-01T10:05:00Z", "Read", file_path="/a/b.py")])

    def tearDown(self):
        self.tmp.cleanup()

    def survey(self, *extra):
        env = dict(os.environ, HOME=self.tmp.name)
        r = subprocess.run([sys.executable, str(SURVEY), "--json", "--config-dir", str(self.cfg), *extra],
                           capture_output=True, text=True, env=env, check=True)
        return r.stdout

    def full(self):
        return self.survey("--no-index")

    def indexed(self):
        return self.survey("--index", str(self.index))

    def test_index_matches_full_run_through_changes(self):
        self.assertEqual(self.indexed(), self.full())
        self.assertTrue(self.index.exists())
        self.assertEqual(self.indexed(), self.full())  # every file from the index

        with self.a.open("a") as fh:  # appended to
            fh.write(json.dumps(tool("2026-11-04T10:00:00Z", "Skill", skill="refactor")) + "\n")
            fh.write(json.dumps(user("2026-11-04T10:00:01Z", "/compact-time")) + "\n")
        bump(self.a)
        out = self.indexed()
        self.assertEqual(out, self.full())
        self.assertIn("refactor", json.loads(out)["skills"])

        write(self.b, [user("2026-11-05T10:00:00Z", "ok")])  # rewritten shorter
        bump(self.b)
        out = self.indexed()
        self.assertEqual(out, self.full())
        self.assertNotIn("handoff", json.loads(out)["skills"])

        self.c.unlink()  # deleted
        out = self.indexed()
        self.assertEqual(out, self.full())
        self.assertEqual(json.loads(out)["sessions"], 2)
        self.assertNotIn(str(self.c), json.loads(self.index.read_text())["files"])

        write(self.cfg / "projects" / "-Users-x-dev-beta" / "dddd.jsonl",  # added
              [tool("2026-11-06T10:00:00Z", "Skill", skill="gs")])
        self.assertEqual(self.indexed(), self.full())

    def test_index_from_another_script_version_is_ignored(self):
        self.indexed()
        data = json.loads(self.index.read_text())
        for entry in data["files"].values():
            entry["scan"]["skills"] = {"stale": 99}
        data["version"] = "not-this-script"
        self.index.write_text(json.dumps(data))
        self.assertEqual(self.indexed(), self.full())


if __name__ == "__main__":
    unittest.main()
