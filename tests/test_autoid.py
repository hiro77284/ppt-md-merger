"""indexer.autoid（#id の無い見出しに {{#id:...:AUTOHEAD:N}} を自動で付ける）のテスト。

実行: python -m unittest tests.test_autoid
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from md_merge._autoid import AutoIdError, add_auto_ids
from md_merge._inventory import extract_entries
from md_merge._render import build_resolved_map, render_content
from md_merge._resolve import expand_title_label_refs, resolve_entries
from md_merge.validate import validate_recipe

_SRC = Path(__file__).resolve().parents[1] / "src"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(_SRC))
    return subprocess.run(
        [sys.executable, "-m", "md_merge", *args],
        cwd=cwd, env=env, capture_output=True, text=True,
        encoding="utf-8", stdin=subprocess.DEVNULL,
    )


def _render(md: str) -> str:
    base = Path("/tmp")
    entries = extract_entries(md, base / "merged.md", base)
    resolve_entries(entries, ".", ") ")
    expand_title_label_refs(entries, ") ")
    return render_content(md, build_resolved_map({"entries": entries}))


def _headings(md: str) -> list[str]:
    return [l for l in md.splitlines() if l.startswith("#")]


class TestAddAutoIds(unittest.TestCase):
    def test_headings_get_ids_by_level(self):
        out, n = add_auto_ids("# 章\n\n## 節\n\n### 項\n\n#### 細目\n")
        self.assertEqual(n, 3)
        self.assertIn("{{#id:chapter:AUTOHEAD:1}}\n# 章", out)
        self.assertIn("{{#id:section:AUTOHEAD:2}}\n## 節", out)
        self.assertIn("{{#id:subsection:AUTOHEAD:3}}\n### 項", out)
        self.assertNotIn("{{#id:", out.split("#### 細目")[0].splitlines()[-2])

    def test_existing_id_is_kept_and_skipped(self):
        md = "{{#id:chapter:doc:intro}}\n# 序論\n\n## 背景\n"
        out, n = add_auto_ids(md)
        self.assertEqual(n, 1)
        self.assertEqual(out.count("{{#id:"), 2)
        self.assertIn("{{#id:chapter:doc:intro}}\n# 序論", out)
        self.assertIn("{{#id:section:AUTOHEAD:1}}\n## 背景", out)

    def test_nonum_heading_is_left_alone(self):
        md = "# 章\n\n{{#id:section:doc:x}} {{nonum}}\n## 補足\n"
        out, n = add_auto_ids(md)
        self.assertEqual(n, 1)
        self.assertNotIn("AUTOHEAD:2", out)

    def test_fence_comment_frontmatter_are_ignored(self):
        md = textwrap.dedent("""\
            <!-- source: a.md -->
            ---
            title: x
            # yaml comment
            ---
            # 章
            ```bash
            # shell comment
            ```
            <!--
            # commented out
            -->
            ~~~
            ## in tilde fence
            ~~~
            """)
        out, n = add_auto_ids(md)
        self.assertEqual(n, 1)
        self.assertIn("{{#id:chapter:AUTOHEAD:1}}\n# 章", out)

    def test_not_a_heading_without_space(self):
        out, n = add_auto_ids("#tag\n#!shebang\n")
        self.assertEqual(n, 0)

    def test_reserved_part_is_error(self):
        with self.assertRaises(AutoIdError):
            add_auto_ids("{{#id:chapter:AUTOHEAD:9}}\n# 章\n")

    def test_section_before_chapter_warns(self):
        with self.assertLogs(level="WARNING") as cm:
            add_auto_ids("## 節\n\n# 章\n")
        self.assertTrue(any("0.1" in m for m in cm.output))

    def test_numbering_through_render(self):
        md = "# 序論\n\n## 背景\n\n## 目的\n\n# 本論\n\n{{#id:section:doc:m}}\n## 方法\n\n### 手順\n"
        out, _ = add_auto_ids(md)
        self.assertEqual(_headings(_render(out)), [
            "# 1) 序論", "## 1.1) 背景", "## 1.2) 目的",
            "# 2) 本論", "## 2.1) 方法", "### 2.1.1) 手順",
        ])


class TestValidate(unittest.TestCase):
    def test_key_known_and_no_warning_with_idresolve(self):
        w = validate_recipe({"version": 4, "indexer": {"autoid": True, "pptxnumbering": "idresolve"}})
        self.assertEqual([x for x in w if "autoid" in x], [])

    def test_warns_when_numbering_is_no(self):
        w = validate_recipe({"version": 4, "indexer": {"autoid": True}})
        self.assertTrue(any("autoid" in x and "no" in x for x in w))

    def test_warns_on_non_bool(self):
        w = validate_recipe({"version": 4, "indexer": {"autoid": "yes"}})
        self.assertTrue(any("true / false" in x for x in w))


class TestMergeEndToEnd(unittest.TestCase):
    def _merge(self, indexer: str) -> tuple[subprocess.CompletedProcess, Path]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "a.md").write_text("# 序論\n\n本文\n\n## 背景\n", encoding="utf-8")
        recipe = root / "r_recipe.yaml"
        recipe.write_text(
            "version: 4\nindexer:\n" + indexer + "\n" + textwrap.dedent("""\
            output:
              targetbasefilename: r
            procedure:
              - chapter: "+"
                title: 前書き
              - insertmd: a.md
            """), encoding="utf-8")
        return _run("merge", str(recipe), "--force", cwd=root), root

    def test_merge_adds_ids_only_to_headings_without_id(self):
        res, root = self._merge("  autoid: true\n  pptxnumbering: idresolve")
        self.assertEqual(res.returncode, 0, res.stderr)
        merged = (root / "work_r_merged.md").read_text(encoding="utf-8")
        self.assertIn("{{#id:chapter:AUTOHEAD:1}}\n# 序論", merged)
        self.assertIn("{{#id:section:AUTOHEAD:2}}\n## 背景", merged)
        # procedure の chapter が入れる見出しは既に ID 付きなので重ねない
        self.assertEqual(merged.count(":AUTOHEAD:"), 2)
        self.assertIn("AUTOCHAPTER:AUTOID_1}}\n# 前書き", merged)

    def test_merge_without_autoid_is_unchanged(self):
        res, root = self._merge("  pptxnumbering: idresolve")
        self.assertEqual(res.returncode, 0, res.stderr)
        merged = (root / "work_r_merged.md").read_text(encoding="utf-8")
        self.assertNotIn("AUTOHEAD", merged)


if __name__ == "__main__":
    unittest.main()
