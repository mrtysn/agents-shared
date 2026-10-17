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


def entry(msg_id, ts, out, model="claude-sonnet-5-5", read=100):
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
        # per message: 5 input at $2 plus 20 cache-write tokens, all 1-hour at $4, per million
        one = (5 * 2 + 20 * 4) / 1e6
        self.assertAlmostEqual(buckets[0], one)
        self.assertAlmostEqual(buckets[1], 2 * one)


class TitleTest(unittest.TestCase):
    def test_the_last_ai_title_of_the_session_file_is_reported(self):
        mod = load()
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-p"
            proj.mkdir(parents=True)
            (proj / "s.jsonl").write_text("".join(json.dumps(e) + "\n" for e in [
                {"type": "ai-title", "aiTitle": "First name", "sessionId": "s"},
                entry("a", "2026-10-14T10:00:00Z", 1),
                {"type": "ai-title", "aiTitle": "Better name", "sessionId": "s"}]))
            mod.transcripts = lambda **kw: mod_transcripts(tmp, **kw)
            rows, projects = mod.summarise(None, None)
        self.assertEqual(rows[0]["title"], "Better name")
        self.assertEqual(projects[0]["first"], "2026-10-14T10:00:00Z")


def sized(msg_id, ts, read, write):
    return {"type": "assistant", "timestamp": ts,
            "message": {"id": msg_id, "model": "claude-sonnet-5-5",
                        "usage": {"input_tokens": 0, "cache_creation_input_tokens": write,
                                  "cache_read_input_tokens": read, "output_tokens": 0}}}


class RewriteTest(unittest.TestCase):
    def test_a_full_rewrite_after_idle_counts_and_a_compaction_does_not(self):
        mod = load()
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "projects" / "-p"
            proj.mkdir(parents=True)
            (proj / "s.jsonl").write_text("".join(json.dumps(e) + "\n" for e in [
                sized("a", "2026-10-14T10:00:00Z", 0, 100_000),
                sized("b", "2026-10-14T10:00:30Z", 100_000, 5_000),
                sized("c", "2026-10-14T12:00:00Z", 0, 105_000),       # cache gone after 2 hours
                sized("d", "2026-10-14T12:00:20Z", 105_000, 3_000),
                sized("e", "2026-10-14T12:00:40Z", 0, 30_000)]))      # compacted: smaller prompt
            mod.transcripts = lambda **kw: mod_transcripts(tmp, **kw)
            rows, _ = mod.summarise(None, None)
        t = rows[0]["total"]
        self.assertEqual(t["rewrites"], 1)
        self.assertEqual(t["rewrites_after_idle"], 1)
        self.assertEqual(t["rewrite_tokens"], 105_000)
        self.assertAlmostEqual(t["rewrite_cost"], 105_000 * 4 / 1e6)


class CostTest(unittest.TestCase):
    def usage(self, **kw):
        base = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0, "write_1h": 0}
        return {**base, **kw}

    def test_sonnet_55_prices_each_line_from_its_row(self):
        mod = load()
        # 1M of each: input 2, 5m write 2.5, read 0.10, output 10 x scale 2
        v = self.usage(input=1_000_000, cache_write=1_000_000, cache_read=1_000_000, output=1_000_000)
        self.assertAlmostEqual(mod.message_cost("claude-sonnet-5-5", v), 2 + 2.5 + 0.10 + 20)

    def test_the_one_hour_part_of_a_write_costs_the_one_hour_price(self):
        mod = load()
        v = self.usage(cache_write=1_000_000, write_1h=1_000_000)
        self.assertAlmostEqual(mod.message_cost("claude-opus-5-5", v), 8.0)

    def test_fable_51_reads_at_a_40th_of_input(self):
        mod = load()
        v = self.usage(cache_read=1_000_000)
        self.assertAlmostEqual(mod.message_cost("claude-fable-5-1", v), 0.25)

    def test_haiku_55_changes_row_above_100k_prompt_tokens(self):
        mod = load()
        small = mod.message_cost("claude-haiku-5-5", self.usage(input=50_000))
        big = mod.message_cost("claude-haiku-5-5", self.usage(input=200_000))
        self.assertAlmostEqual(small, 50_000 * 0.10 / 1e6)
        self.assertAlmostEqual(big, 200_000 * 0.50 / 1e6)

    def test_a_model_with_no_row_has_no_cost(self):
        self.assertIsNone(load().message_cost("claude-unknown-9", self.usage(input=1)))


if __name__ == "__main__":
    unittest.main()
