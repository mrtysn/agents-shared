#!/usr/bin/env python3
"""Tests for report-subagent-token-use.py against a fake session in a temp dir.

Nothing in ~/.claude is read.   Run: python3 scripts/tests/test_report_subagent_token_use.py
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "report-subagent-token-use.py"


def load():
    spec = importlib.util.spec_from_file_location("report_subagent_token_use_under_test", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def assistant(msg_id, ts, read, made, inp=10, tool=False):
    content = [{"type": "tool_use", "name": "Read", "input": {}}] if tool else [{"type": "text", "text": "x"}]
    return {"type": "assistant", "timestamp": ts,
            "message": {"id": msg_id, "content": content,
                        "usage": {"input_tokens": inp, "cache_read_input_tokens": read,
                                  "cache_creation_input_tokens": made}}}


class SummariseTest(unittest.TestCase):
    def test_counts_requests_context_and_cache(self):
        m = load()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "agent-abc123.jsonl"
            rows = [
                assistant("m1", "2026-10-13T10:00:00.000Z", 0, 60000, tool=True),
                assistant("m1", "2026-10-13T10:00:01.000Z", 0, 60000),  # same message id, a later row of it
                assistant("m2", "2026-10-13T10:00:30.000Z", 60000, 5000),
                {"type": "user", "timestamp": "2026-10-13T10:01:00.000Z", "message": {"content": "hi"}},
            ]
            p.write_text("\n".join(json.dumps(r) for r in rows))
            (Path(d) / "agent-abc123.meta.json").write_text(json.dumps({"description": "Review of plan", "model": "fable"}))
            r = m.summarise(str(p))
        self.assertEqual(r["requests"], 2)
        self.assertEqual(r["tool_calls"], 1)
        self.assertEqual(r["context_start"], 60010)
        self.assertEqual(r["context_end"], 65010)
        self.assertEqual(r["context_growth"], 5000)
        self.assertEqual(r["cache_read"], 60000)
        self.assertEqual(r["cache_created"], 65000)
        self.assertEqual(r["seconds"], 60)
        self.assertEqual(r["description"], "Review of plan")
        self.assertEqual(r["model"], "fable")

    def test_per_request_series_is_added_only_on_request(self):
        m = load()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "agent-abc123.jsonl"
            rows = [assistant("m1", "2026-10-13T10:00:00.000Z", 0, 60000),
                    assistant("m2", "2026-10-13T10:00:30.000Z", 60000, 5000)]
            p.write_text("\n".join(json.dumps(r) for r in rows))
            plain = m.summarise(str(p))
            full = m.summarise(str(p), per_request=True)
        self.assertNotIn("per_request", plain)
        self.assertEqual(full["fresh_input"], 20)
        self.assertEqual(full["per_request"], [
            {"context": 60010, "cache_read": 0, "cache_created": 60000, "fresh_input": 10},
            {"context": 65010, "cache_read": 60000, "cache_created": 5000, "fresh_input": 10}])

    def test_agent_with_no_requests_is_skipped(self):
        m = load()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "agent-none.jsonl"
            p.write_text(json.dumps({"type": "user", "timestamp": "2026-10-13T10:00:00.000Z"}))
            self.assertIsNone(m.summarise(str(p)))


if __name__ == "__main__":
    unittest.main()
