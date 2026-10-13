#!/usr/bin/env python3
"""Tests for transcript_items.py and extract-session-text.py against fake transcripts in a temp dir.

Nothing in ~/.claude is read.   Run: python3 scripts/tests/test_transcript_items.py
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
import transcript_items as ti  # noqa: E402

EXTRACT = SCRIPTS / "extract-session-text.py"


def user(ts, text, **extra):
    return {"type": "user", "timestamp": ts, "message": {"content": text}, **extra}


def assistant(ts, blocks, **extra):
    return {"type": "assistant", "timestamp": ts, "message": {"content": blocks}, **extra}


def text(s):
    return {"type": "text", "text": s}


def call(id_, name, **inp):
    return {"type": "tool_use", "id": id_, "name": name, "input": inp}


def result(id_, s):
    return {"type": "tool_result", "tool_use_id": id_, "content": s}


SESSION = [
    user("2026-10-01T10:00:00Z", "scour my chats"),
    assistant("2026-10-01T10:00:05Z", [text("starting"), call("t1", "Bash", command="ls ~/.claude/projects")]),
    {"type": "user", "timestamp": "2026-10-01T10:00:06Z", "message": {"content": [result("t1", "a\nb")]}},
    assistant("2026-10-01T10:00:09Z", [call("t2", "AskUserQuestion", questions=[{"question": "which?"}])]),
    {"type": "user", "timestamp": "2026-10-01T10:00:10Z", "message": {"content": [result("t2", "A")]}},
    user("2026-10-01T10:01:00Z", "<cross-session-message from=x>hi</cross-session-message>"),
    user("2026-10-01T10:02:00Z", "continue"),
    assistant("2026-10-01T10:02:05Z", [text("sub-agent step")], isSidechain=True),
    assistant("2026-10-01T10:03:00Z", [text("API Error: connection lost")], isApiErrorMessage=True),
    {"type": "queue-operation", "operation": "enqueue", "timestamp": "2026-10-01T10:04:00Z", "content": "later"},
    {"type": "system", "subtype": "away_summary", "timestamp": "2026-10-01T10:05:00Z", "content": "recap"},
]


def write_session(root, project, sid, entries):
    d = Path(root) / "projects" / project
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{sid}.jsonl"
    p.write_text("".join(json.dumps(e) + "\n" for e in entries) + "not json\n", encoding="utf-8")
    return p


class ItemsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = write_session(self.tmp.name, "-p", "s1", SESSION)

    def tearDown(self):
        self.tmp.cleanup()

    def test_groups_and_labels_in_order(self):
        got = [(i["group"], i["label"]) for i in ti.items(str(self.path), "p")]
        self.assertEqual(got[:6], [
            ("user", "USER"), ("assistant", "ASSISTANT"), ("calls", "CALL Bash"),
            ("tools", "TOOL-RESULT Bash"), ("agents", "ASK"), ("agents", "RESULT AskUserQuestion")])
        self.assertIn(("user", "USER(queued)"), got)
        self.assertIn(("user", "RECAP"), got)

    def test_call_carries_input_and_text_is_its_command(self):
        c = next(i for i in ti.items(str(self.path)) if i["group"] == "calls")
        self.assertEqual(c["text"], "ls ~/.claude/projects")
        self.assertEqual(c["tool"], "Bash")
        self.assertEqual(c["input"], {"command": "ls ~/.claude/projects"})
        r = next(i for i in ti.items(str(self.path)) if i["group"] == "tools")
        self.assertEqual((r["tool"], r["tool_use_id"], r["text"]), ("Bash", "t1", "a\nb"))

    def test_want_limits_groups(self):
        got = {i["group"] for i in ti.items(str(self.path), want={"assistant"})}
        self.assertEqual(got, {"assistant"})

    def test_flags_survive_for_callers_own_predicates(self):
        rows = list(ti.items(str(self.path)))
        self.assertTrue(any(r["sidechain"] for r in rows))
        self.assertTrue(any(r["api_error"] for r in rows))

    def test_next_user_skips_injected_messages_and_sidechains(self):
        rows = ti.add_next_user(list(ti.items(str(self.path))))
        first = next(r for r in rows if r["label"] == "ASSISTANT")
        self.assertEqual(first["next_user"], "continue")
        last = rows[-1]
        self.assertIsNone(last["next_user"])
        self.assertFalse(ti.is_typed_prompt(next(r for r in rows if r["text"].startswith("<cross-session"))))

    def test_clip_input_cuts_nested_strings(self):
        out = ti.clip_input({"a": "x" * 10, "b": ["y" * 3, {"c": "z" * 10}]}, 5)
        self.assertEqual(out["a"], "xxxxx...[5 more]")
        self.assertEqual(out["b"][0], "yyy")
        self.assertEqual(out["b"][1]["c"], "zzzzz...[5 more]")


class TranscriptsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        write_session(self.tmp.name, "-Users-x-dev-alpha", "aaaa1111", SESSION)
        write_session(self.tmp.name, "-Users-x-dev-beta", "bbbb2222", SESSION[:2] + [user("2026-10-01T11:00:00Z", "archify please")])
        sub = Path(self.tmp.name) / "projects" / "-Users-x-dev-alpha" / "aaaa1111" / "subagents"
        sub.mkdir(parents=True)
        (sub / "agent-1.jsonl").write_text(json.dumps(assistant("2026-10-01T10:00:00Z", [text("in sub")], isSidechain=True)) + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def found(self, **kw):
        return [(proj, sid) for _, proj, sid in ti.transcripts(config_dir_list=[self.tmp.name], **kw)]

    def test_all_sessions_and_project_filter(self):
        self.assertEqual(len(self.found()), 2)
        self.assertEqual([s for _, s in self.found(project="beta")], ["bbbb2222"])

    def test_mention_filter_reads_whole_file(self):
        self.assertEqual([s for _, s in self.found(mention="archify")], ["bbbb2222"])

    def test_exclude_by_prefix_and_subagents_opt_in(self):
        self.assertEqual([s for _, s in self.found(exclude=("aaaa",))], ["bbbb2222"])
        self.assertEqual(len(self.found(subagents=True)), 3)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = write_session(self.tmp.name, "-p", "s1", SESSION)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(EXTRACT), str(self.path), *args], capture_output=True, text=True)

    def test_default_text_output_unchanged_shape(self):
        out = self.run_cli().stdout
        self.assertIn("===== [1] USER 10:00:00 =====\nscour my chats", out)
        self.assertNotIn("ls ~/.claude/projects", out)  # calls are off by default
        self.assertNotIn("sub-agent step", out)

    def test_calls_kind_and_json_rows_with_next_user(self):
        out = self.run_cli("--kinds", "assistant,calls", "--json", "--next-user").stdout
        rows = [json.loads(line) for line in out.splitlines()]
        self.assertEqual([r["group"] for r in rows[:2]], ["assistant", "calls"])
        self.assertEqual(rows[0]["next_user"], "continue")

    def test_max_chars_cuts_tool_text_and_input_not_prose(self):
        out = self.run_cli("--kinds", "assistant,calls", "--json", "--max-chars", "5").stdout
        rows = [json.loads(line) for line in out.splitlines()]
        call_row = next(r for r in rows if r["group"] == "calls")
        self.assertTrue(call_row["text"].startswith("ls ~/") and "more]" in call_row["text"])
        self.assertIn("more]", call_row["input"]["command"])
        self.assertEqual(rows[0]["text"], "starting")

    def test_subagents_flag_includes_sidechain_rows(self):
        out = self.run_cli("--kinds", "assistant", "--json", "--subagents").stdout
        self.assertTrue(any(json.loads(line)["sidechain"] for line in out.splitlines()))

    def test_argument_errors(self):
        self.assertNotEqual(self.run_cli("--next-user").returncode, 0)
        bare = subprocess.run([sys.executable, str(EXTRACT)], capture_output=True, text=True)
        self.assertNotEqual(bare.returncode, 0)
        self.assertIn("give a session, or --all", bare.stderr)


if __name__ == "__main__":
    unittest.main()
