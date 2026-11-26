"""形式が崩れた {{#id:...}} マーカー（3 部そろっていない等）の警告のテスト。

実行: python -m unittest discover -s tests
"""

import tempfile
import unittest
from pathlib import Path

import yaml
from pptx import Presentation

from md_merge._idmarker import find_malformed_id_markers, malformed_reason
from md_merge._inventory import extract_entries
from md_merge._procedure import normalize_recipe
from md_merge.pptmerge._slide_titles import postprocess_idresolve
from md_merge.validate._lint import Source, lint


class MalformedReasonTest(unittest.TestCase):
    def test_valid(self):
        self.assertIsNone(malformed_reason("section:p:s"))

    def test_local_may_contain_colon(self):
        self.assertIsNone(malformed_reason("section:p:a:b"))

    def test_two_parts(self):
        self.assertIn("2 つ", malformed_reason("section:PARTonly"))

    def test_one_part(self):
        self.assertIn("1 つ", malformed_reason("section"))
        self.assertIn("1 つ", malformed_reason(""))

    def test_empty_parts(self):
        self.assertIn("PART", malformed_reason("section::s"))
        self.assertIn("LOCAL", malformed_reason("section:p:"))
        self.assertIn("TYPE", malformed_reason(":p:s"))

    def test_find_only_malformed(self):
        line = "{{#id:section:p:s}} {{#id:section:PARTonly}}"
        self.assertEqual([m for m, _ in find_malformed_id_markers(line)], ["{{#id:section:PARTonly}}"])


class InventoryWarningTest(unittest.TestCase):
    def test_warns_and_not_registered(self):
        md = "{{#id:section:PARTonly}}\n## 節\n\n{{#id:section:p:ok}}\n## 節2\n"
        base = Path("/tmp")
        with self.assertLogs(level="WARNING") as cm:
            entries = extract_entries(md, base / "merged.md", base)
        self.assertEqual([e["full_id"] for e in entries], ["section:p:ok"])
        out = "\n".join(cm.output)
        self.assertIn("{{#id:section:PARTonly}}", out)
        self.assertIn("line 1", out)

    def test_valid_no_warning(self):
        md = "{{#id:section:p:a:b}}\n## 節\n"
        base = Path("/tmp")
        with self.assertNoLogs(level="WARNING"):
            entries = extract_entries(md, base / "merged.md", base)
        self.assertEqual(entries[0]["local_id"], "a:b")


class LintWarningTest(unittest.TestCase):
    def _lint(self, text: str):
        recipe = {"version": 2, "procedure": [{"insertmd": "a.md"}]}
        normalized = normalize_recipe(dict(recipe), warn_deprecated=False)
        return lint(recipe, normalized, Path("r.yaml"), None, sources=[Source("a.md", text)])

    def test_malformed_warned(self):
        res = self._lint("{{#id:section:PARTonly}}\n## 節\n")
        self.assertTrue(any("{{#id:section:PARTonly}}" in w and "line 1" in w for w in res.warnings))
        self.assertEqual(res.errors, [])

    def test_valid_not_warned(self):
        res = self._lint("{{#id:section:p:s}}\n## 節\n")
        self.assertFalse(any("形式が不正" in w for w in res.warnings))

    def test_inside_code_fence_not_warned(self):
        res = self._lint("```\n{{#id:...}}\n```\n")
        self.assertFalse(any("形式が不正" in w for w in res.warnings))


class IdresolveWarningTest(unittest.TestCase):
    def test_note_malformed_warned_title_kept(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            pptx_path = tmp / "merged.pptx"
            resolved = tmp / "resolved.yaml"
            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[5])
            slide.shapes.title.text = "元タイトル"
            slide.notes_slide.notes_text_frame.text = "{{#id:section:PARTonly}}"
            prs.save(str(pptx_path))
            resolved.write_text(yaml.safe_dump({"entries": []}), encoding="utf-8")
            with self.assertLogs(level="WARNING") as cm:
                postprocess_idresolve(pptx_path, resolved, tmp / "log.txt")
            log = (tmp / "log.txt").read_text(encoding="utf-8")
            title = Presentation(str(pptx_path)).slides[0].shapes.title.text
        self.assertIn("形式が不正", log)
        self.assertNotIn("resolved に見つかりません", log)
        self.assertTrue(any("malformed" in o for o in cm.output))
        self.assertEqual(title, "元タイトル")


if __name__ == "__main__":
    unittest.main()
