#!/usr/bin/env python3
"""Tests for report-token-use.py's message reader and weighting, on a fake transcript.

Nothing in ~/.claude is read.   Run: python3 scripts/tests/test_report_token_use.py
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "report-token-use.py"


def load():
    spec = importlib.util.spec_from_file_location("report_token_use_under_test", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def entry(msg_id, ts, out, model="claude-x", read=100):
    return {"type": "assistant", "timestamp": ts,
            "message": {"id": msg_id, "model": model,
                        "usage": {"input_tokens": 5, "cache_creation_input_tokens": 20,
                                  "cache_read_input_tokens": read, "output_tokens": out}}}


class ReadMessagesTest(unittest.TestCase):
    def read(self, entries):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "s.jsonl"
            p.write_text("".join(json.dumps(e) + "\n" for e in entries))
            return load().read_messages(str(p))

    def test_snapshots_of_one_message_count_once_at_the_largest_output(self):
        got = self.read([entry("m1", "2026-10-14T10:00:00Z", 3), entry("m1", "2026-10-14T10:00:01Z", 40)])
        self.assertEqual(len(got), 1)
        self.assertEqual(got["m1"][2]["output"], 40)

    def test_synthetic_and_usage_free_entries_are_skipped(self):
        got = self.read([entry("m1", "2026-10-14T10:00:00Z", 3, model="<synthetic>"),
                         {"type": "assistant", "message": {"id": "m2", "model": "x"}}])
        self.assertEqual(got, {})


class SubagentSplitTest(unittest.TestCase):
    def test_subagent_transcripts_are_counted_in_total_and_in_sub(self):
        mod = load()
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-p"
            (proj / "sess" / "subagents").mkdir(parents=True)
            (proj / "sess.jsonl").write_text(json.dumps(entry("a", "2026-10-14T10:00:00Z", 1)) + "\n")
            (proj / "sess" / "subagents" / "agent-1.jsonl").write_text(
                json.dumps(entry("b", "2026-10-14T10:01:00Z", 1)) + "\n")
            mod.transcripts = lambda **kw: mod_transcripts(tmp, **kw)
            rows, projects = mod.summarise(None, None)
        self.assertEqual(rows[0]["total"]["requests"], 2)
        self.assertEqual(rows[0]["sub"]["requests"], 1)
        self.assertEqual(projects[0]["sub"]["requests"], 1)


def mod_transcripts(tmp, **kw):
    from transcript_items import transcripts
    return transcripts(config_dir_list=[tmp], **kw)


class IntervalsTest(unittest.TestCase):
    def test_cuts_sum_the_weighted_tokens_between_each_pair(self):
        mod = load()
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-p"
            proj.mkdir(parents=True)
            (proj / "s.jsonl").write_text("".join(json.dumps(e) + "\n" for e in [
                entry("a", "2026-10-14T10:00:00Z", 0, read=0),
                entry("b", "2026-10-14T11:00:00Z", 0, read=0),
                entry("c", "2026-10-14T12:30:00Z", 0, read=0)]))
            mod.transcripts = lambda **kw: mod_transcripts(tmp, **kw)
            cuts = [mod.parse_time("2026-10-14T09:00:00Z"), mod.parse_time("2026-10-14T11:00:00Z"),
                    mod.parse_time("2026-10-14T13:00:00Z")]
            buckets = []
            mod.summarise(None, None, cuts=cuts, buckets=buckets)
        one = 5 + 1.25 * 20  # input + cache write, no cache read, no output
        self.assertEqual(buckets, [one, 2 * one])


class WeightTest(unittest.TestCase):
    def test_weighted_uses_the_price_ratios(self):
        t = {"input": 10, "cache_write": 8, "cache_read": 100, "output": 2}
        self.assertEqual(load().weighted(t), 10 + 10 + 10 + 10)


if __name__ == "__main__":
    unittest.main()
