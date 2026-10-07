#!/usr/bin/env python3
"""Unit tests for the parsers in skill_tree_insights.py, on fixture strings: no transcripts walked.
Run: python3 scripts/tests/test_skill_tree_insights.py"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import skill_tree_insights as ins  # noqa: E402

CHECK = """\
-- claude/skills/board/SKILL.md: own skill lacks argument-hint
-- claude/skills/board/SKILL.md: own skill lacks allowed-tools
!! claude/skills/finance-import/SKILL.md: missing or empty description
!! claude/skills/interface/skills/better-ui/SKILL.md: frontmatter is not closed with ---
-- claude/skills/interface/skills/better-ui/SKILL.md: description lacks "Use when"
!! claude/rules/x.md: link to y.md does not resolve
!! claude/skills/interface: pack has no skills/*/SKILL.md
checked 3 skills, 1 rules: 3 problems, 3 warnings
"""


class Findings(unittest.TestCase):
    def test_flat_skill_collects_warnings(self):
        got = ins.parse_findings(CHECK)["board"]
        self.assertEqual(got["problems"], [])
        self.assertEqual(len(got["warnings"]), 2)
        self.assertIn("lacks argument-hint", got["warnings"][0])

    def test_problem_is_kept_apart_from_warning(self):
        got = ins.parse_findings(CHECK)["finance-import"]
        self.assertEqual(len(got["problems"]), 1)
        self.assertEqual(got["warnings"], [])

    def test_pack_skill_is_keyed_pack_colon_skill(self):
        got = ins.parse_findings(CHECK)["interface:better-ui"]
        self.assertEqual((len(got["problems"]), len(got["warnings"])), (1, 1))

    def test_rules_and_summary_are_not_skills(self):
        # a directory-level finding is keyed by that directory (a pack finds no skill record)
        self.assertEqual(set(ins.parse_findings(CHECK)),
                         {"board", "finance-import", "interface:better-ui", "interface"})

    def test_empty_text(self):
        self.assertEqual(ins.parse_findings(""), {})


class Usage(unittest.TestCase):
    SURVEY = {
        "skills": {"outstanding": 3, "only-tool": 2},
        "skills_last": {"outstanding": "2026-10-01T10:00:00.000Z", "only-tool": "2026-09-01T00:00:00Z"},
        "slash": {"outstanding": 10, "only-slash": 4},
        "slash_last": {"outstanding": "2026-10-06T23:59:59Z", "only-slash": "2026-08-02T01:02:03Z"},
    }

    def test_tool_and_typed_counts_are_summed(self):
        self.assertEqual(ins.parse_usage(self.SURVEY)["outstanding"], {"count": 13, "last": "2026-10-06"})

    def test_either_source_alone(self):
        got = ins.parse_usage(self.SURVEY)
        self.assertEqual(got["only-tool"], {"count": 2, "last": "2026-09-01"})
        self.assertEqual(got["only-slash"], {"count": 4, "last": "2026-08-02"})

    def test_missing_last_is_none(self):
        self.assertEqual(ins.parse_usage({"skills": {"a": 1}})["a"], {"count": 1, "last": None})

    def test_empty_survey(self):
        self.assertEqual(ins.parse_usage({}), {})


if __name__ == "__main__":
    unittest.main()
