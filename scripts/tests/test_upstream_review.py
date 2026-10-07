#!/usr/bin/env python3
"""Tests for vendor-upstream-skill.py and the Upstream view actions of skill_tree_skin.py.

Builds a fake upstream repo and a fake agents-shared checkout in a temp dir; no network, and nothing
in the real checkout is touched.   Run: python3 scripts/tests/test_upstream_review.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REAL_SCRIPTS = Path(__file__).resolve().parent.parent


def git(*args, cwd=None):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=cwd, check=True,
                   capture_output=True)


def load_skin():
    spec = importlib.util.spec_from_file_location("skill_tree_skin_under_test", REAL_SCRIPTS / "skill_tree_skin.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class UpstreamReview(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="upstream-review-test-"))
        work = self.tmp / "work"
        for name in ("foo", "bar", "baz"):
            (work / "skills" / name).mkdir(parents=True)
            (work / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: the {name} skill\n---\n")
        (work / "skills" / "foo" / "run.sh").write_text("#!/bin/sh\n")
        os.chmod(work / "skills" / "foo" / "run.sh", 0o755)
        (work / "SKILL.md").write_text("---\nname: top\ndescription: root\n---\n")
        git("init", "-q", ".", cwd=work)
        git("add", "-A", cwd=work)
        git("commit", "-qm", "init", cwd=work)
        bare = self.tmp / "up" / "owner" / "repo.git"
        bare.parent.mkdir(parents=True)
        git("clone", "-q", "--bare", str(work), str(bare))
        git("config", "uploadpack.allowFilter", "true", cwd=bare)
        os.environ["VENDOR_GIT_BASE"] = "file://" + str(self.tmp / "up")

        root = self.tmp / "root"
        (root / "claude" / "skills" / "interface" / "skills").mkdir(parents=True)
        (root / "scripts").mkdir()
        for tool in ("vendor-upstream-skill.py",):
            (root / "scripts" / tool).symlink_to(REAL_SCRIPTS / tool)
        (root / "scripts" / "init-global.sh").write_text("#!/bin/sh\ntouch \"$(dirname \"$0\")/init-ran\"\n")
        (root / "scripts" / "external-skills-ignore.txt").write_text("# header\n")
        self.root = root
        self.make_installed(root)

        self.m = load_skin()
        m = self.m
        m.AGENTS_ROOT, m.SCRIPTS = root, root / "scripts"
        m.UP_CACHE = self.tmp / "cache"
        m.UP_DATA, m.UP_STATUS = m.UP_CACHE / "d.json", m.UP_CACHE / "s.json"
        m.UP_LOG, m.UP_IGNORE = m.UP_CACHE / "l.log", root / "scripts" / "external-skills-ignore.txt"
        m.UP_CACHE.mkdir()
        items = [{"repo": "owner/repo", "path": f"skills/{n}/SKILL.md", "name": n, "desc": f"the {n} skill"}
                 for n in ("foo", "bar", "baz")]
        items.append({"repo": "owner/repo", "path": "SKILL.md", "name": "top", "desc": "root"})
        m.UP_DATA.write_text(json.dumps({"generated": "2026-10-07T00:00:00", "items": items}))

    def make_installed(self, root):
        """An installed skill in a group (with a local override), a flat one, and one of our own; all committed."""
        skills = root / "claude" / "skills"
        (skills / "interface" / ".claude-plugin").mkdir(parents=True)
        (skills / "interface" / ".claude-plugin" / "plugin.json").write_text('{"name": "interface"}')

        def skill(path, name, source=None, patch=None):
            path.mkdir(parents=True)
            (path / "SKILL.md").write_text(f"---\nname: {name}\ndescription: the {name} skill\n---\nbody\n")
            if source:
                (path / "source.json").write_text(json.dumps(source))
            if patch:
                (path / "override.patch").write_text(patch)

        skill(skills / "interface" / "skills" / "ext", "ext",
              {"repo": "owner/repo", "path": "skills/ext/SKILL.md", "commit": "abcdef1234", "updated": "2026-09-01", "files": ["SKILL.md"]},
              "--- a/SKILL.md\n+++ b/SKILL.md\n@@ -1 +1 @@\n-old\n+new\n+more\n")
        skill(skills / "flatx", "flatx", {"repo": "owner/repo", "path": "skills/flatx/SKILL.md", "commit": "1234567", "updated": "2026-09-02", "files": ["SKILL.md"]})
        skill(skills / "own", "own")
        git("init", "-q", ".", cwd=root)
        git("add", "-A", cwd=root)
        git("commit", "-qm", "installed skills", cwd=root)

    def by_name(self, name):
        return next(s for s in self.m.action_installed({})["skills"] if s["name"] == name)

    def test_installed_lists_everything_with_source_override_and_dates(self):
        names = {s["name"]: s for s in self.m.action_installed({})["skills"]}
        self.assertEqual(set(names), {"ext", "flatx", "own"})
        ext = names["ext"]
        self.assertEqual((ext["group"], ext["external"], ext["repo"], ext["synced"], ext["pinned"]),
                         ("interface", True, "owner/repo", "2026-09-01", "abcdef1"))
        self.assertEqual(ext["override"], {"files": 1, "lines": 3})
        self.assertIsNone(names["flatx"]["override"])
        self.assertFalse(names["own"]["external"])
        self.assertTrue(ext["changed"], "last-changed time comes from git history")
        self.assertFalse(ext["dirty"])

    def test_uncommitted_changes_are_flagged(self):
        (self.root / "claude" / "skills" / "flatx" / "SKILL.md").write_text("edited\n")
        self.assertTrue(self.by_name("flatx")["dirty"])
        self.assertFalse(self.by_name("ext")["dirty"])

    def test_remove_plan_warns_and_refuses_what_it_should(self):
        (self.root / "claude" / "skills" / "flatx" / "SKILL.md").write_text("edited\n")
        r = self.m.action_upstream_plan({"choices": [
            {"choice": "remove", "dir": "claude/skills/interface/skills/ext"},
            {"choice": "remove", "dir": "claude/skills/flatx"},
            {"choice": "remove", "dir": "claude/skills/own"},
            {"choice": "remove", "dir": "claude/skills/../../scripts"},
            {"choice": "remove", "dir": "claude/skills/ghost"}]})
        self.assertEqual({x["name"] for x in r["remove"]}, {"ext", "flatx"})
        warns = {x["name"]: x["warnings"] for x in r["remove"]}
        self.assertIn("3 lines of local changes", warns["ext"][0])
        self.assertIn("uncommitted", warns["flatx"][0])
        self.assertEqual(len(r["problems"]), 3)
        self.assertTrue(any("own skill" in p["error"] for p in r["problems"]))

    def test_remove_deletes_the_folder_ignores_it_and_relinks_flat_skills(self):
        r = self.m.action_upstream_apply({"choices": [
            {"choice": "remove", "dir": "claude/skills/interface/skills/ext"},
            {"choice": "remove", "dir": "claude/skills/flatx"}]})
        self.assertTrue(r["ok"], r)
        skills = self.root / "claude" / "skills"
        self.assertFalse((skills / "interface" / "skills" / "ext").exists())
        self.assertFalse((skills / "flatx").exists())
        self.assertTrue((skills / "own").is_dir(), "an own skill is never removed")
        ignore = self.m.UP_IGNORE.read_text()
        self.assertIn("owner/repo skills/ext/SKILL.md", ignore)
        self.assertIn("owner/repo skills/flatx/SKILL.md", ignore)
        self.assertTrue((self.root / "scripts" / "init-ran").exists(), "removing a flat skill must relink")
        self.assertEqual({s["name"] for s in self.m.action_installed({})["skills"]}, {"own"})

    def test_the_remover_refuses_anything_that_is_not_a_skill_folder(self):
        for rel in ("claude/skills", "scripts", "claude/skills/interface", ".."):
            with self.assertRaises(ValueError):
                self.m._remove_skill(rel)
        self.assertTrue((self.root / "scripts").is_dir())

    def choices(self, *rows):
        return {"choices": [dict(repo="owner/repo", path=p, choice=c, dest=d) for p, c, d in rows]}

    def test_catalog_lists_items_and_groups(self):
        r = self.m.action_upstream({})
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["items"]), 4)
        self.assertEqual(r["groups"], ["interface"])

    def test_plan_flags_each_problem_and_keeps_good_choices(self):
        r = self.m.action_upstream_plan(self.choices(
            ("skills/foo/SKILL.md", "copy", "flat"),
            ("skills/bar/SKILL.md", "copy", "nogroup"),
            ("SKILL.md", "copy", "flat"),
            ("skills/baz/SKILL.md", "ignore", None),
            ("skills/ghost/SKILL.md", "ignore", None)))
        self.assertEqual([v["name"] for v in r["vendor"]], ["foo"])
        self.assertEqual([i["path"] for i in r["ignore"]], ["skills/baz/SKILL.md"])
        self.assertEqual(len(r["problems"]), 3)
        self.assertEqual(r["requests"], 2)

    def test_apply_copies_ignores_and_forgets_what_it_did(self):
        r = self.m.action_upstream_apply(self.choices(
            ("skills/foo/SKILL.md", "copy", "flat"),
            ("skills/bar/SKILL.md", "copy", "interface"),
            ("skills/baz/SKILL.md", "ignore", None)))
        self.assertTrue(r["ok"], r)
        skills = self.root / "claude" / "skills"
        self.assertTrue((skills / "foo" / "SKILL.md").is_file())
        self.assertTrue((skills / "foo" / ".upstream" / "SKILL.md").is_file())
        self.assertTrue(os.access(skills / "foo" / "run.sh", os.X_OK))
        self.assertEqual(json.loads((skills / "foo" / "source.json").read_text())["files"], ["SKILL.md", "run.sh"])
        self.assertTrue((skills / "interface" / "skills" / "bar" / "source.json").is_file())
        self.assertIn("owner/repo skills/baz/SKILL.md", self.m.UP_IGNORE.read_text())
        self.assertTrue((self.root / "scripts" / "init-ran").exists(), "init-global.sh must run for a flat copy")
        left = [i["path"] for i in self.m.action_upstream({})["items"]]
        self.assertEqual(left, ["SKILL.md"])
        again = self.m.action_upstream_apply(self.choices(("skills/foo/SKILL.md", "copy", "flat")))
        self.assertFalse(again["ok"])

    def test_ignore_is_not_duplicated_and_header_is_kept(self):
        for _ in range(2):
            self.m.action_upstream_apply(self.choices(("skills/baz/SKILL.md", "ignore", None)))
        text = self.m.UP_IGNORE.read_text()
        self.assertEqual(text.count("skills/baz/SKILL.md"), 1)
        self.assertTrue(text.startswith("# header"))

    def test_refresh_runs_the_catalog_script_and_reports_progress(self):
        fake = self.root / "scripts" / "catalog-unvendored-skills.py"
        fake.write_text("import sys,json,time\nprint('[1/1] owner/repo',file=sys.stderr,flush=True)\n"
                        "time.sleep(0.5)\njson.dump({'generated':'now','items':[]},open(sys.argv[2],'w'))\n")
        self.assertTrue(self.m.action_upstream_refresh({})["ok"])
        self.assertFalse(self.m.action_upstream_refresh({})["ok"], "a second refresh must be refused while one runs")
        self.assertEqual(self.m.action_upstream_status({})["refresh"]["state"], "running")
        for _ in range(50):
            if self.m.action_upstream_status({})["refresh"]["state"] != "running":
                break
            time.sleep(0.1)
        self.assertEqual(self.m.action_upstream_status({})["refresh"]["state"], "done")
        self.assertEqual(self.m.action_upstream({})["items"], [])

    def test_vendor_tool_refuses_bad_input(self):
        tool = str(REAL_SCRIPTS / "vendor-upstream-skill.py")
        run = subprocess.run([sys.executable, tool, "skills/foo/SKILL.md", "owner/repo", "--flat", "--root", str(self.root)],
                             capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("expected <owner/repo>", run.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
